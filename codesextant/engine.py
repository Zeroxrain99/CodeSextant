"""Public engine API for indexing, references, storage, and ranking.

Public functions accept and return JSON-serializable values so the HTTP daemon can
expose them with little conversion. Each endpoint maps to one engine function:
  - /reindex: index_project(path)
  - /get_symbols: get_symbols(path, file)
  - /find_references: find_references(path, symbol, ...)
  - /get_map: get_map(path, token_budget)
  - /status: status(path)

Missing paths and unindexed projects raise errors instead of returning ambiguous empty
results. Indexing uses tree-sitter to extract symbols. Jedi resolves Python references
only when requested.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from collections import OrderedDict
from copy import deepcopy
from threading import RLock, Thread
from typing import TYPE_CHECKING

from . import (
    cochange,
    diffscan,
    namegraph,
    project_state,
    storage,
    work_coordinator,
)
from . import guards as guards_module
from .lazy_import import LazyModule
from .ranking import is_test_path as ranking_is_test_path
from .ranking import rank_symbols

# Deferred because a spawned route worker imports this module from cold on every heavy
# request. jedi (references) and the tree-sitter language pack (symbols) together cost
# about 85ms, and a cached get_map -- which resolves nothing and parses nothing -- was
# paying all of it. Each still resolves on first attribute access.
# The TYPE_CHECKING branch never runs; it exists so that static analysis -- jedi's
# included, which is what CodeSextant resolves references with -- can see what these
# names are. Without it every call through one of these proxies is invisible to
# resolution, and this file's own callers went missing from its own blast radius.
if TYPE_CHECKING:
    from . import clones, comments, references, symbols
else:
    clones = LazyModule(f"{__package__}.clones")
    comments = LazyModule(f"{__package__}.comments")
    references = LazyModule(f"{__package__}.references")
    symbols = LazyModule(f"{__package__}.symbols")

# Directories skipped while scanning source files during indexing (target = Rust build output).
_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules",
              ".mypy_cache", ".pytest_cache", "build", "dist", "target", ".tox"}

# The daemon keeps only the small result already trimmed to token_budget, never 570k
# symbols or a full edge graph.
# The cache key is bound to the SQLite revision plus every parameter and env var that can
# change the ordering; once an index or a ref updates, the db mtime changes and the entry
# misses automatically.
_MAP_CACHE: OrderedDict[tuple, dict] = OrderedDict()
_MAP_CACHE_LOCK = RLock()
_SYMBOL_SNAPSHOT_INFLIGHT: set[tuple[str, tuple]] = set()
_SYMBOL_SNAPSHOT_THREADS: set[Thread] = set()
_MAP_CACHE_ENV = (
    "CODESEXTANT_NAMEGRAPH_DISABLED", "CODESEXTANT_NAMEGRAPH_MAX_FANOUT",
    "CODESEXTANT_NAMEGRAPH_MAX_FILES", "CODESEXTANT_NAMEGRAPH_MAP_WORK_BUDGET",
    "CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES", "CODESEXTANT_RANK_PRIVATE_MULT",
    "CODESEXTANT_RANK_WELLNAMED_MINLEN", "CODESEXTANT_RANK_WELLNAMED_MULT",
    "CODESEXTANT_RANK_COMMON_THRESHOLD", "CODESEXTANT_RANK_COMMON_MULT",
    "CODESEXTANT_RANK_TEST_MULT", "CODESEXTANT_NAMEGRAPH_MIN_NAME_LEN",
    "CODESEXTANT_PAGERANK_FOCUS_BOOST",
)


def _schedule_symbol_snapshot(db_file, revision: tuple, symbols: list[dict]) -> None:
    """Write the snapshot lazily, off the response path; one writer per revision per process."""
    if os.environ.get("CODESEXTANT_ROUTE_WORKER_CHILD") == "1":
        # A disposable route worker exits as soon as its response is delivered,
        # so a delayed daemon thread would never publish the snapshot.
        storage.write_symbol_snapshot(db_file, revision, symbols)
        return
    key = (str(db_file), tuple(revision))
    with _MAP_CACHE_LOCK:
        if key in _SYMBOL_SNAPSHOT_INFLIGHT:
            return
        _SYMBOL_SNAPSHOT_INFLIGHT.add(key)

    def worker():
        try:
            time.sleep(1.0)  # let the HTTP handler finish sending the small map result first, so the JSON writer does not fight it for the GIL
            storage.write_symbol_snapshot(db_file, revision, symbols)
        except Exception as exc:
            print(f"  Warning: failed to write symbols snapshot: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
        finally:
            with _MAP_CACHE_LOCK:
                _SYMBOL_SNAPSHOT_INFLIGHT.discard(key)
                _SYMBOL_SNAPSHOT_THREADS.discard(thread)

    thread = Thread(
        target=worker,
        name="codesextant-symbol-snapshot",
        daemon=True,
    )
    with _MAP_CACHE_LOCK:
        _SYMBOL_SNAPSHOT_THREADS.add(thread)
    try:
        thread.start()
    except Exception:
        with _MAP_CACHE_LOCK:
            _SYMBOL_SNAPSHOT_THREADS.discard(thread)
            _SYMBOL_SNAPSHOT_INFLIGHT.discard(key)
        raise


def wait_for_snapshot_writers(timeout: float | None = None) -> bool:
    """Wait for delayed cache writers before daemon ownership is released."""
    deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
    while True:
        with _MAP_CACHE_LOCK:
            threads = [thread for thread in _SYMBOL_SNAPSHOT_THREADS if thread.is_alive()]
        if not threads:
            return True
        for thread in threads:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return False
            thread.join(timeout=remaining)

# Definitions that can be reference targets. The variable kind covers exported TS/JS
# constants, arrow functions, and object literals. Without it, those definitions have no
# candidate path and can be misrouted through the Python resolver.
_REFERENCEABLE_KINDS = {"function", "class", "method", "interface", "type",
                        "enum", "struct", "trait", "variable",
                        # Symbol kinds added with the 2026-06-22 batch of mainstream languages:
                        "constructor",   # C#/Java/Swift constructors
                        "property",      # C#/Swift properties
                        "module",        # Ruby module
                        "protocol"}      # Swift protocol


def _iter_source_files(root: str):
    """Scan supported source files while respecting Git's standard ignore rules."""
    git_files = _git_visible_files(root)
    if git_files is not None:
        yield from git_files
        return

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in symbols.SUPPORTED_EXTENSIONS:
                yield os.path.join(dirpath, fn)


def _git_command_kwargs() -> dict:
    kwargs = {"capture_output": True, "text": False, "timeout": 10}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return kwargs


def _git_visible_files(root: str) -> list[str] | None:
    """Return tracked and untracked non-ignored files, or None outside a Git worktree."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                root,
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
            ],
            **_git_command_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    files = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative = os.fsdecode(raw_path)
        candidate = os.path.abspath(os.path.join(root, relative))
        if (
            os.path.isfile(candidate)
            and os.path.splitext(candidate)[1].lower() in symbols.SUPPORTED_EXTENSIONS
            and not any(part in _SKIP_DIRS for part in relative.replace("\\", "/").split("/"))
        ):
            files.append(candidate)
    return files


def _env_on(name: str) -> bool:
    """Parse an env flag (always via .lower(), so =True/=TRUE are not read as unset)."""
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def _infer_project_language(root: str, *, sample_cap: int | None = None) -> str | None:
    """Infer a fallback language when reference lookup finds no candidate definition.

    When finding references turns up no candidate definition for a symbol
    (def_path=None) and jedi cannot locate the definition either, sample the project's
    dominant language as a fallback, not an override, so a
    non-Python symbol does not get stuck on the name-matching dead end.

    Returns a language only when its share is at or above the threshold; a tie or a mixed
    project deliberately does not force a choice and returns None, which falls back to the
    conservative jedi path and costs the least when wrong. Undecidable also returns None.
    Environment switches, parsed case-insensitively:
      - CODESEXTANT_INFER_LANG_DISABLED=1/true/yes/on: return None.
      - CODESEXTANT_INFER_LANG_SAMPLE_CAP=<int>: sampling cap (default 1000; <=0 means
        scan everything without truncating).
      - CODESEXTANT_INFER_LANG_MIN_RATIO=<float>: dominant-share threshold (default 0.6).
    """
    if _env_on("CODESEXTANT_INFER_LANG_DISABLED"):
        return None
    if sample_cap is None:
        try:
            sample_cap = int(os.environ.get("CODESEXTANT_INFER_LANG_SAMPLE_CAP", "1000"))
        except ValueError:
            sample_cap = 1000
    try:
        min_ratio = float(os.environ.get("CODESEXTANT_INFER_LANG_MIN_RATIO", "0.6"))
    except ValueError:
        min_ratio = 0.6

    from collections import Counter
    counts: Counter[str] = Counter()
    for seen, fp in enumerate(_iter_source_files(root), start=1):
        lang = symbols.language_for_file(fp)
        if lang:
            counts[lang] += 1
        if sample_cap > 0 and seen >= sample_cap:
            break
    total = sum(counts.values())
    if total == 0:
        return None
    top_lang, top_n = counts.most_common(1)[0]
    # A mixed or tied sample returns None and takes the
    # conservative jedi path: deterministic, and the cheapest outcome when wrong.
    if top_n / total < min_ratio:
        return None
    return top_lang


def _git_head_sha(repo_path: str) -> str | None:
    """Read the repository's Git HEAD SHA for freshness checks.

    A non-Git repository, unavailable Git executable, or disabled check returns None.
    The subprocess does not flash a console window
    under a detached Windows daemon (CREATE_NO_WINDOW).
    CODESEXTANT_GIT_FRESHNESS_DISABLED=1/true/yes/on disables the check. The value is
    parsed case-insensitively.
    """
    return project_state.git_head_sha(repo_path)


def _index_source_file(store: storage.ProjectStore, fp: str, *, force: bool = False):
    """Index one supported source file without discovering any other paths."""
    work_coordinator.cancellation_point()
    try:
        with open(fp, "rb") as source_file:
            source = source_file.read()
    except OSError as exc:
        return "error", {"path": fp, "error": f"failed to read file: {exc}"}

    content_hash = hashlib.sha256(source).hexdigest()
    if not force and not store.needs_reindex(fp, content_hash):
        return "skipped", None

    try:
        lang = symbols.language_for_file(fp)
        tree = symbols.parse_source(source, lang) if lang else None
        extracted = (
            symbols.extract_symbols_from_source(source, lang, file_path=fp, tree=tree)
            if lang else []
        )
        # Clone fingerprints and comments are deliberately not computed here. Together
        # they cost more than twice the CPU and seven times the storage of the symbol
        # index itself, and nothing on the navigation path -- get_map, find_references,
        # impact -- reads either one. find_duplicates and the comment queries materialize
        # what they need on first use; see _materialize_derived.

        # No cancellation point belongs inside the SQLite transaction. Once
        # replacement starts, every derived table must advance or roll back as
        # one file revision.
        work_coordinator.cancellation_point()
        store.store_file_index(fp, content_hash, extracted, indexed_at=time.time())
        work_coordinator.cancellation_point()
        return "indexed", None
    except work_coordinator.HeavyWorkDeadlineExceeded:
        raise
    except Exception as exc:
        return "error", {"path": fp, "error": f"{type(exc).__name__}: {exc}"}


def _derive_one_file(store: storage.ProjectStore, path: str, content_hash: str,
                     kind: str) -> bool:
    """Compute and store one optional analysis for one file. True when it was stored.

    Reads and parses the source once for whichever kind is asked for. A file that cannot
    be read or parsed is skipped rather than raised: a single unreadable file must not
    fail a whole find_duplicates run.
    """
    try:
        with open(path, "rb") as source_file:
            source = source_file.read()
    except OSError:
        return False
    if hashlib.sha256(source).hexdigest() != content_hash:
        # The file changed since it was indexed. The watcher or the next index pass owns
        # reconciling it; deriving from content the index does not describe would store
        # fingerprints that disagree with the symbols beside them.
        return False
    lang = symbols.language_for_file(path)
    if not lang:
        return False
    try:
        tree = symbols.parse_source(source, lang)
        if kind == "comments":
            store.store_file_comments(
                path,
                comments.extract_comments_from_source(
                    source, lang, file_path=path, tree=tree),
                content_hash=content_hash)
        else:
            fingerprints = clones.extract_fingerprints_from_source(
                source, lang, file_path=path, tree=tree)
            store.store_file_fingerprints(
                path, fingerprints,
                [{"line": fingerprint["line"], "fp_value": value}
                 for fingerprint in fingerprints
                 for value in fingerprint.get("winnow", [])],
                content_hash=content_hash)
    except Exception as exc:
        print(f"  Warning: {kind} extraction failed ({path}): {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return False
    return True


def _materialize_derived(abs_path: str, kind: str, *,
                         paths: list[str] | None = None) -> dict:
    """Bring one optional analysis up to date before a query that reads it.

    Indexing extracts symbols only. Clone fingerprints and comments are computed here, on
    the first query that needs them and again only for files whose content changed since,
    so a project that never asks for duplicates never pays for them.

    ``paths`` narrows the work to specific files. Leave it None for the project-wide
    queries: duplicate detection and the comment overview read every row in their table,
    so materializing a subset would quietly answer from partial data.

    Only the non-interactive heavy routes call this -- find_duplicates, get_health and
    the comment queries -- which share a daemon lane with /reindex. The interactive
    routes an agent uses to navigate (get_map, find_references, impact, call_hierarchy,
    get_symbols) never derive anything, so first use of a rarely-used analysis cannot
    slow down the path that is on the critical line of a coding task.

    Returns {"kind", "computed", "pending"}; ``pending`` counts files that could not be
    derived this pass (unreadable, unsupported language, or changed under us).
    """
    if kind == "comments" and not comments.comments_enabled():
        return {"kind": kind, "computed": 0, "pending": 0}
    if kind == "fingerprints" and not clones.dedup_enabled():
        return {"kind": kind, "computed": 0, "pending": 0}
    if not storage.db_path_for(abs_path).exists():
        return {"kind": kind, "computed": 0, "pending": 0}

    with storage.ProjectStore.open(abs_path) as store:
        stale = store.paths_missing_derived(kind, paths)
        if not stale:
            return {"kind": kind, "computed": 0, "pending": 0}
        computed = 0
        for path, content_hash in stale:
            work_coordinator.cancellation_point()
            if _derive_one_file(store, path, content_hash, kind):
                computed += 1
        return {"kind": kind, "computed": computed, "pending": len(stale) - computed}


def _target_path(root: str, raw_path: str) -> str | None:
    candidate = raw_path if os.path.isabs(raw_path) else os.path.join(root, raw_path)
    candidate = os.path.abspath(candidate)
    try:
        if os.path.commonpath((root, candidate)) != root:
            return None
    except ValueError:
        return None
    if os.path.exists(candidate):
        real_root = os.path.realpath(root)
        real_candidate = os.path.realpath(candidate)
        try:
            if os.path.commonpath((real_root, real_candidate)) != real_root:
                return None
        except ValueError:
            return None
    return candidate


def _path_is_skipped(root: str, path: str) -> bool:
    relative = os.path.relpath(path, root)
    parts = relative.split(os.sep)
    if not os.path.isdir(path):
        parts = parts[:-1]
    if any(part in _SKIP_DIRS for part in parts):
        return True
    try:
        result = subprocess.run(
            ["git", "-C", root, "check-ignore", "-q", "--", os.path.abspath(path)],
            **_git_command_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def index_paths(path: str, changed_paths) -> dict:
    """Apply a file-event batch without traversing the repository.

    Existing files are hashed and parsed individually. Missing paths remove exact indexed
    files, while a missing directory path removes indexed descendants. An existing directory
    is scanned only inside that event-targeted subtree.
    """
    if not os.path.isdir(path):
        raise NotADirectoryError(f"index_paths: '{path}' is not a valid directory")

    work_coordinator.cancellation_point()
    abs_path = os.path.abspath(path)
    targets = sorted({
        target
        for raw_path in changed_paths
        if (target := _target_path(abs_path, os.fspath(raw_path))) is not None
    })
    started = time.perf_counter()
    indexed = skipped = removed = errors = 0
    error_files: list[dict] = []

    with storage.ProjectStore.open(abs_path) as store:
        indexed_files = None
        candidates: set[str] = set()
        removed_paths: set[str] = set()
        for target in targets:
            work_coordinator.cancellation_point()
            if os.path.isdir(target):
                if _path_is_skipped(abs_path, target):
                    continue
                candidates.update(_iter_source_files(target))
                continue
            if os.path.isfile(target):
                if (_path_is_skipped(abs_path, target)
                        or os.path.splitext(target)[1].lower() not in symbols.SUPPORTED_EXTENSIONS):
                    continue
                candidates.add(target)
                continue

            if store.has_indexed_file(target):
                store.remove_file(target)
                removed += 1
                removed_paths.add(target)
                continue

            prefix = target.rstrip(os.sep) + os.sep
            if indexed_files is None:
                indexed_files = store.all_indexed_files()
            descendants = [
                old for old in indexed_files
                if old.startswith(prefix) and old not in removed_paths
            ]
            for old in descendants:
                work_coordinator.cancellation_point()
                store.remove_file(old)
                removed += 1
                removed_paths.add(old)

        for source_path in sorted(candidates):
            work_coordinator.cancellation_point()
            outcome, error = _index_source_file(store, source_path)
            if outcome == "indexed":
                indexed += 1
            elif outcome == "skipped":
                skipped += 1
            else:
                if not os.path.exists(source_path) and store.has_indexed_file(source_path):
                    store.remove_file(source_path)
                    removed += 1
                    removed_paths.add(source_path)
                else:
                    errors += 1
                    error_files.append(error)

        work_coordinator.cancellation_point()
        sha = _git_head_sha(abs_path)
        if sha:
            work_coordinator.cancellation_point()
            store.record_git_sha(sha)
        stats = store.stats()

    return {
        "indexed": indexed,
        "skipped": skipped,
        "removed": removed,
        "errors": errors,
        "error_files": error_files,
        "total_paths": len(targets),
        "elapsed_sec": round(time.perf_counter() - started, 3),
        "project_key": stats["project_key"],
        "db_file": stats["db_file"],
        "symbols_total": stats["symbols"],
    }


def index_project(path: str, *, force: bool = False) -> dict:
    """Build (or incrementally update) a project's index.

    tree-sitter extracts every symbol, and a content hash drives the incremental pass:
    only files whose hash changed are recomputed.
    This step does not run jedi because resolving every file would be too slow. Reference
    resolution is left to find_references, on demand.

    Parameters
    ----------
    path  : the project root (absolute or relative; it is normalized internally).
    force : True ignores hashes and recomputes everything (for debugging or rebuilding).

    Returns a dict (JSON-serializable):
      {indexed, skipped, removed, errors, total_files, elapsed_sec,
       project_key, db_file, symbols_total}
    A path that is not a directory raises NotADirectoryError.
    """
    if not os.path.isdir(path):
        raise NotADirectoryError(f"index_project: '{path}' is not a valid directory")

    work_coordinator.cancellation_point()
    abs_path = os.path.abspath(path)
    t0 = time.perf_counter()
    indexed = skipped = errors = 0
    error_files: list[dict] = []

    with storage.ProjectStore.open(abs_path) as store:
        seen_files: set[str] = set()
        for fp in _iter_source_files(abs_path):
            work_coordinator.cancellation_point()
            seen_files.add(fp)
            outcome, error = _index_source_file(store, fp, force=force)
            if outcome == "indexed":
                indexed += 1
            elif outcome == "skipped":
                skipped += 1
            else:
                errors += 1
                error_files.append(error)

        # Remove files that disappeared or became ignored so the index remains the source
        # of truth for the current project view.
        removed = 0
        for old_path in store.all_indexed_files():
            work_coordinator.cancellation_point()
            if old_path not in seen_files:
                store.remove_file(old_path)
                removed += 1

        # Record Git HEAD at index time. Non-Git repositories record nothing.
        work_coordinator.cancellation_point()
        sha = _git_head_sha(abs_path)
        if sha:
            work_coordinator.cancellation_point()
            store.record_git_sha(sha)

        elapsed = time.perf_counter() - t0
        st = store.stats()
        result = {
            "indexed": indexed,
            "skipped": skipped,
            "removed": removed,
            "errors": errors,
            "error_files": error_files,
            "total_files": indexed + skipped,
            "elapsed_sec": round(elapsed, 3),
            "project_key": st["project_key"],
            "db_file": st["db_file"],
            "symbols_total": st["symbols"],
        }
    return result


def get_symbols(path: str, file: str | None = None) -> dict:
    """Get a project's symbols (pass file for one file, otherwise the whole project).

    Returns {project_key, file, count, symbols:[...]}.
    A project that has never been indexed returns count=0 plus a note telling you to index
    first, and it does not pretend to have data.
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {
            "project_key": storage.project_key(abs_path),
            "file": file,
            "count": 0,
            "symbols": [],
            "note": f"project has not been indexed yet (no {db_file}); call index_project first.",
        }

    target_file = os.path.abspath(file) if file else None
    with storage.ProjectStore.open_readonly(abs_path) as store:
        syms = store.get_symbols(target_file)
        return {
            "project_key": store.project_key,
            "file": target_file,
            "count": len(syms),
            "symbols": syms,
        }


def _refs_non_python(root: str, symbol: str, def_path: str | None, lang: str,
                     include_low_confidence: bool) -> dict:
    """Reference dispatch for non-Python languages: TS/JS try ts-morph for high confidence
    first and fall back to name matching when it is unavailable (never raising); every
    other language degrades to name matching, with every result labelled low confidence."""
    if lang in ("typescript", "tsx", "javascript"):
        result = references.ts_morph_references(root, symbol, def_path=def_path)
        if result is None:
            result = references.name_match_references(
                root, symbol, def_path=def_path, lang=lang,
                include_low_confidence=include_low_confidence,
            )
        return result
    return references.name_match_references(
        root, symbol, def_path=def_path, lang=lang,
        include_low_confidence=include_low_confidence,
    )


def _refs_reliability(result: dict) -> dict:
    """Describe reference-result reliability and when source inspection is still needed.

    level: high = trust it directly / medium = partly trustworthy but it has blind spots,
    read a bit more / low = read the code, do not treat this as a verdict.
    No level replaces reading the code to judge whether the logic is right. This
    tool sees reference relationships, not semantics or business intent. Static resolution
    never sees dynamic, reflective or string-concatenated calls, which is exactly where
    reading the code matters most.
    """
    engine = result.get("engine")
    high = len(result.get("high_confidence") or [])
    low = len(result.get("low_confidence") or [])
    if engine == "name-match":
        return {"level": "low",
                "advice": "plain name matching, with no real import resolution. It includes "
                          "same-name interference and cannot see dynamic or reflective calls. "
                          "Read the source to confirm; do not treat this list as complete or precise."}
    if not result.get("definition"):
        return {"level": "low",
                "advice": "the symbol's definition was not located (a typo, not in this repo, or a "
                          "module-level variable). The result is incomplete, so read the source "
                          "directly to confirm."}
    if high == 0 and low == 0:
        return {"level": "medium",
                "advice": "real resolution found zero references. It may genuinely be unused, or it "
                          "may be called dynamically, reflectively or through string concatenation, "
                          "which static resolution never sees. Read the surrounding code before "
                          "deleting or changing it."}
    if low > high * 3 and low > 5:
        return {"level": "medium",
                "advice": f"far more low-confidence hits ({low}) than high-confidence ones ({high}), "
                          f"mostly same-name interference. Those {high} high-confidence hits are "
                          "trustworthy, but if the usage you are after is not among them, skim the "
                          "low-confidence list or read the source."}
    return {"level": "high",
            "advice": f"{high} high-confidence reference(s) from real resolution, so trust them and skip "
                      "chasing references by hand (still: run the build after changing a signature or "
                      "deleting something; **whether the logic is right still needs reading the code**)."}


def find_references(path: str, symbol: str, *, def_path: str | None = None,
                    src_root: str | None = None,
                    include_low_confidence: bool = True,
                    persist: bool = True) -> dict:
    """Find who uses a symbol: jedi's two-stage resolution, run only on demand.

    Parameters
    ----------
    path   : the project root (also jedi.Project's isolation root, unless src_root is given).
    symbol : the symbol name (e.g. "check").
    def_path : the file the symbol is defined in. If omitted, the index is queried for
               candidate definitions; a single match is used directly, and with several
               same-named matches the first is used and all candidates are listed in the
               return value.
    src_root : jedi.Project's root. Defaults to path. Some repos put their import root in a
               src/ subdirectory and can name it explicitly (a project using a src/ layout
               must point at .../src).
    include_low_confidence : whether to return files that name matching hit but jedi did not
               confirm (marked low).
    persist : True persists the resolved high-confidence reference edges, so PageRank and
               later queries can reuse them.

    Returns references.find_references's dict plus {candidate_definitions:[...]}.
    """
    abs_path = os.path.abspath(path)
    root = os.path.abspath(src_root) if src_root else abs_path

    # Without def_path, pull same-named definitions from the index as candidates (the
    # first stage's coarse filter benefits from the index too).
    candidate_defs: list[dict] = []
    reference_generation: int | None = None
    db_file = storage.db_path_for(abs_path)
    if db_file.exists():
        with storage.ProjectStore.open_readonly(abs_path) as store:
            # Pin both the generation and candidate definitions to one SQLite
            # snapshot. A reindex after this point makes persistence fail closed.
            store.conn.execute("BEGIN")
            try:
                reference_generation = store.index_generation()
                candidate_defs = [
                    d for d in store.find_symbol_definitions(symbol)
                    if d["kind"] in _REFERENCEABLE_KINDS
                ]
            finally:
                store.conn.rollback()
    if def_path is None and candidate_defs:
        def_path = candidate_defs[0]["path"]

    # Dispatch on the definition file's language. Python, or an undetermined
    # extension) takes jedi's real import resolution; every other language goes through
    # _refs_non_python (ts-morph, degrading to name matching).
    lang = symbols.language_for_file(def_path) if def_path else None
    if lang in (None, "python"):
        result = references.find_references(
            root, symbol, def_path=def_path,
            include_low_confidence=include_low_confidence,
        )
        # Use the sampled language only as a fallback after Jedi finds no definition.
        # the sampled language when def_path is None *and* jedi found no definition.
        # This must run after jedi fails because jedi does not depend on the index or
        # def_path, it scans the disk directly, so in a mixed repo it still finds a Python
        # symbol even with def_path=None. Overriding first would take that ability away
        # (regression pit9-1: a repo with more TS than Python returned empty for Python queries).
        if def_path is None and not result.get("definition"):
            inferred = _infer_project_language(root)
            if inferred and inferred != "python":
                lang = inferred
                result = _refs_non_python(root, symbol, None, lang,
                                          include_low_confidence)
    else:
        result = _refs_non_python(root, symbol, def_path, lang,
                                  include_low_confidence)
    result["language"] = lang or "python"
    result["candidate_definitions"] = candidate_defs
    result["src_root"] = root
    # All three current reference sources set the engine field, but a future path may not.
    # ts_morph) already set engine, but a fallback swapping the result, or a future new
    # path, could miss it, so default conservatively (lowest confidence, never claiming
    # real resolution that did not happen).
    result.setdefault("engine", "name-match")
    # State the capability boundary without raising the reported confidence.
    # reference lookup and unused detection are not the same as passing compilation, type
    # checking or lint, and all-green refs do not mean it builds. After clearing dead code
    # or changing a signature, run build/CI yourself.
    result["verification_reminder"] = (
        "CodeSextant reports reference relationships, which is not the same as passing "
        "compilation, type checking or lint; after clearing dead code or changing a "
        "signature, always run build/CI to verify."
    )
    # Report the result's reliability and when the source still needs inspection.
    # The tool maps references but does not interpret program semantics. On name-match results, zero
    # references, or far more low-confidence hits, it says so, so nobody assumes coverage
    # it does not have.
    result["reliability"] = _refs_reliability(result)

    # Persist the high-confidence reference edges, grouped by source file, for PageRank later.
    if (persist and db_file.exists() and result.get("definition")
            and reference_generation is not None):
        d = result["definition"]
        edges_by_src: dict[str, list[dict]] = {}
        for ref in result["high_confidence"]:
            sp = ref.get("src_path")
            if not sp:
                continue
            edges_by_src.setdefault(sp, []).append({
                "src_path": sp,
                "src_line": ref["line"],
                "symbol_name": symbol,
                "def_path": d["path"],
                # The definition this reference actually resolved to, which is not
                # always the first one of that name in the file. namegraph matches
                # edges to symbol nodes on (def_path, def_line), so the first-match
                # line would hang the edge off the wrong definition.
                "def_line": ref.get("def_line", d["line"]),
                "confidence": "high",
            })
        if edges_by_src:
            result["references_persisted"] = _persist_reference_edges(
                abs_path, symbol, edges_by_src, reference_generation)

    return result


def _persist_reference_edges(abs_path: str, symbol: str, edges_by_src: dict,
                             expected_generation: int | None) -> bool:
    """Store resolved edges, best effort. False when they were not stored.

    Persistence is a cache for PageRank and later queries; it is never part of the
    answer, because the references have already been resolved by the time this runs.
    The generation fence already skips the write when a reindex moved the index
    underneath, and a concurrent reindex simply holding the write lock is the same
    routine condition on a shared daemon. Letting that turn a computed result into a
    500 charged the caller their whole query to save a lookup it can redo.
    """
    try:
        with storage.ProjectStore.open(abs_path) as store:
            for src_path, edges in edges_by_src.items():
                if not store.replace_refs_for_symbol(
                        src_path, symbol, edges,
                        expected_generation=expected_generation):
                    return False
        return True
    except sqlite3.OperationalError as exc:
        # "database is locked" and friends: the index is busy, not broken.
        print(f"  Warning: reference edges for {symbol!r} were not persisted "
              f"({type(exc).__name__}: {exc})", file=sys.stderr)
        return False


def call_hierarchy(path: str, symbol: str, *, direction: str = "both",
                   max_hops: int | None = None, def_path: str | None = None,
                   src_root: str | None = None, build_edges: bool = True) -> dict:
    """Transitive call chain: upgrades single-level refs into transitive caller/callee chains.

    direction: up = who (transitively) calls this symbol (callers) / down = who this symbol
    (transitively) calls (callees) / both.
    Underneath it uses storage.traverse_call_graph (a WITH RECURSIVE CTE over the refs
    table); max_hops stops cycles from recursing forever.

    The call chain is built from persisted reference edges. The refs table only
    accumulates once find_references has run against a symbol). With build_edges=True, the
    target gets one find_references(persist=True) pass first to build its direct caller
    edges, which makes the direct level of the up direction accurate immediately; the
    transitive levels and the down direction still depend on whatever edges the refs table
    already holds. The result notes when those edges may be incomplete.
    Static derivation cannot see dynamic or reflective calls.

    Parameters
    ----------
    max_hops : when None, taken from env CODESEXTANT_CALL_HIERARCHY_MAX_HOPS (default 5,
               configurable through the environment).
    Returns a dict: {symbol, direction, definition, callers?, callees?, max_hops,
             edges_in_graph, candidate_definitions, note, verification_reminder}.
    An unindexed project raises RuntimeError.
    """
    if direction not in ("up", "down", "both"):
        raise ValueError(f"direction must be up/down/both, got {direction!r}")
    if max_hops is None:
        try:
            max_hops = int(os.environ.get("CODESEXTANT_CALL_HIERARCHY_MAX_HOPS", "5"))
        except ValueError:
            max_hops = 5
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"call_hierarchy: project has not been indexed yet (no {db_file}); call index_project first.")

    with storage.ProjectStore.open_readonly(abs_path) as store:
        candidate_defs = [d for d in store.find_symbol_definitions(symbol)
                          if d["kind"] in _REFERENCEABLE_KINDS]
    if def_path is None and candidate_defs:
        def_path = candidate_defs[0]["path"]

    result: dict = {
        "symbol": symbol,
        "direction": direction,
        "definition": ({"path": def_path} if def_path else None),
        "max_hops": max_hops,
        "candidate_definitions": candidate_defs,
        "verification_reminder": (
            "A call chain is derived statically from references and cannot see dynamic, "
            "reflective or string-concatenated calls; read the code before changing it."),
    }
    if def_path is None:
        result["callers"] = []
        result["callees"] = []
        result["error"] = (f"the index holds no referenceable definition for symbol '{symbol}'; "
                           "check the spelling, or run index_project first.")
        return result

    # build_edges: run find_references against the target to build its direct caller edges,
    # which makes the direct level of the up direction accurate immediately.
    if build_edges:
        try:
            find_references(abs_path, symbol, def_path=def_path, src_root=src_root,
                            persist=True)
        except Exception:
            pass  # failing to build edges is not fatal; fall back to whatever the refs table already holds

    with storage.ProjectStore.open_readonly(abs_path) as store:
        result["edges_in_graph"] = len(store.all_refs())
        if direction in ("up", "both"):
            result["callers"] = store.traverse_call_graph(
                symbol, def_path, direction="up", max_hops=max_hops)
        if direction in ("down", "both"):
            result["callees"] = store.traverse_call_graph(
                symbol, def_path, direction="down", max_hops=max_hops)
    result["note"] = (
        f"The call chain is built from persisted reference edges ({result['edges_in_graph']} "
        "in the refs table). Edges accumulate once you run find_references against a symbol "
        "(map and refs persist automatically). If there are too few edges, the transitive "
        "levels and the callees direction will look sparse; run refs against the related "
        "symbols first to fill them in.")
    return result


# Blast radius splits test from prod, and ranking demotes test definitions. One
# heuristic, defined in the dependency-light module, so the two cannot disagree.
_is_test_path = ranking_is_test_path


def _mark_high_importance(path: str, callers: list[dict]) -> list[dict]:
    """Flag the affected callers that PageRank considers highly important (by intersecting
    with get_map's top symbol names).

    With with_name_edges=False, impact and
    blast-radius are hot paths that only need the structurally central top symbol names to
    filter callers, which do not need name-level ordering precision. The old version
    triggered a whole-repo name-level scan on every impact call (measured at 5.5x slower,
    and in that scenario high_importance was usually 0, so it bought nothing).
    """
    try:
        m = get_map(path, token_budget=3000, with_name_edges=False)
        top_names = {s.get("name") for s in (m.get("symbols") or [])[:30]}
    except Exception:
        top_names = set()
    return [c for c in callers if c.get("name") in top_names]


def impact(path: str, symbol: str, *, max_hops: int | None = None,
           def_path: str | None = None, src_root: str | None = None) -> dict:
    """Change impact report / blast radius: who is affected by editing X.

    Built on call_hierarchy(direction=up): direct and transitive callers, callers split into
    test/prod/entrypoint, and PageRank used to flag the highly important affected symbols.
    Low-confidence transitive dependencies from name matching are listed separately as
    "may also be affected (unconfirmed)" and never mixed into the confirmed set. Static derivation cannot see dynamic or
    reflective calls.

    Returns a dict: {symbol, definition, direct_callers, transitive_callers, affected_files,
             by_kind:{test/prod/entrypoint}, high_importance_affected, uncertain_maybe_affected,
             summary, note, verification_reminder}. An unindexed project raises RuntimeError.
    """
    from . import deadcode

    ch = call_hierarchy(path, symbol, direction="up", max_hops=max_hops,
                        def_path=def_path, src_root=src_root)
    callers = ch.get("callers", []) or []
    confirmed = [c for c in callers if c.get("confidence") == "high"]
    uncertain = [c for c in callers if c.get("confidence") != "high"]

    by_kind: dict[str, list] = {"test": [], "prod": [], "entrypoint": []}
    for c in confirmed:
        # Test classification takes priority over entrypoint. deadcode.is_entrypoint treats test_*.py as
        # an entrypoint, which is right for dead-code exemptions. But blast radius is
        # classifying "does changing this only affect tests, or does it affect external
        # behaviour", so test files go to test first, and only non-test entries (routes,
        # CLI, __main__) count as entrypoint.
        if _is_test_path(c["path"]):
            by_kind["test"].append(c)
            continue
        is_entry, reason = deadcode.is_entrypoint(c["path"], symbol_name=c.get("name"))
        if is_entry:
            by_kind["entrypoint"].append({**c, "entry_reason": reason})
        else:
            by_kind["prod"].append(c)

    high_importance = _mark_high_importance(os.path.abspath(path), confirmed)
    return {
        "symbol": symbol,
        "definition": ch.get("definition"),
        "direct_callers": [c for c in confirmed if c.get("depth") == 1],
        "transitive_callers": [c for c in confirmed if c.get("depth", 0) > 1],
        "affected_files": sorted({c["path"] for c in confirmed}),
        "by_kind": by_kind,
        "high_importance_affected": high_importance,
        # Keep low-confidence transitive dependencies separate from the confirmed set.
        "uncertain_maybe_affected": uncertain,
        "max_hops": ch.get("max_hops"),
        "edges_in_graph": ch.get("edges_in_graph"),
        "candidate_definitions": ch.get("candidate_definitions"),
        "error": ch.get("error"),
        "summary": {
            "total_confirmed_affected": len(confirmed),
            "direct": sum(1 for c in confirmed if c.get("depth") == 1),
            "transitive": sum(1 for c in confirmed if c.get("depth", 0) > 1),
            "test": len(by_kind["test"]), "prod": len(by_kind["prod"]),
            "entrypoint": len(by_kind["entrypoint"]),
            "high_importance": len(high_importance),
            "uncertain": len(uncertain),
        },
        "note": ch.get("note"),
        "verification_reminder": (
            "Change impact is based on a static call chain and cannot see dynamic, reflective "
            "or string-concatenated calls; the 'may also be affected' section is low-confidence "
            "and unconfirmed, not a verdict. Read the affected code before changing it."),
    }


# Budget accounting measures the JSON the caller actually receives. Four characters
# per token is the usual approximation for this kind of payload, and erring toward
# over-estimating is deliberate: the caller pays for what the serializer emits, not
# for an idealized "kind name @file:line" summary line.
_CHARS_PER_TOKEN = 4
# A full float repr costs about 29 bytes per entry and tells the caller nothing it can
# use, because the symbol list is already ordered by rank.
_RANK_DIGITS = 6


def _json_tokens(value) -> int:
    """Approximate tokens for a value as the daemon will serialize it."""
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    return max(1, -(-len(encoded) // _CHARS_PER_TOKEN))


def _fit_symbols_to_budget(result: dict, ranked: list[dict], token_budget: int) -> None:
    """Fill result["symbols"] with as many ranked entries as token_budget really pays for.

    The envelope (note, edge_sources, project_key) is charged first, because the caller
    receives it whether it wanted it or not. At least one symbol is always returned, so
    even a tiny budget still answers "what is the most important symbol here".
    """
    # get_map annotates the delivered result with cache provenance after this runs, and
    # count/approx_tokens grow from their placeholder zeros. Charge the envelope at its
    # delivered size, or the payload overshoots the budget the caller asked for.
    result["truncated_by_budget"] = False
    probe = dict(result)
    probe["edge_sources"] = dict(result.get("edge_sources") or {})
    probe["edge_sources"]["map_cache_hit"] = False
    probe["edge_sources"]["map_cache_source"] = "compute"
    probe["count"] = len(ranked)
    probe["approx_tokens"] = token_budget
    # Count characters and convert once at the end. Rounding every entry to whole tokens
    # instead drifts by tens of tokens over a hundred entries, in both directions.
    budget_chars = max(1, token_budget) * _CHARS_PER_TOKEN
    used_chars = len(json.dumps(probe, ensure_ascii=False, default=str))
    fitted: list[dict] = []
    for symbol in ranked:
        entry = dict(symbol)
        rank = entry.get("rank")
        if isinstance(rank, float):
            entry["rank"] = round(rank, _RANK_DIGITS)
        # every entry after the first also pays for the ", " the array serializer inserts
        cost = len(json.dumps(entry, ensure_ascii=False, default=str)) + 2
        if fitted and used_chars + cost > budget_chars:
            break
        fitted.append(entry)
        used_chars += cost
    result["symbols"] = fitted
    result["count"] = len(fitted)
    result["approx_tokens"] = -(-used_chars // _CHARS_PER_TOKEN)
    result["truncated_by_budget"] = len(fitted) < len(ranked)


def _get_map_uncached(path: str, token_budget: int = 2000, *, damping: float = 0.85,
                      focus_symbols=None, focus_files=None,
                      with_name_edges: bool = True) -> dict:
    """Return the most important N symbols that fit a token budget, ordered by PageRank.

    focus_symbols / focus_files let the caller name the symbols and files currently being
    edited or asked about, which biases the ordering toward relevant code
    (personalization). Omitting them gives the plain static structural-centrality map.

    Parameters
    ----------
    path : the project root.
    token_budget : an approximate token budget. It is converted to a symbol count using a
                   rough estimate of about 12 tokens per symbol entry, then the top N by
                   PageRank are taken.
    damping : PageRank's damping factor.
    with_name_edges : True (the default) builds name-level whole-graph edges to fix the
                      out-of-the-box degradation; False takes the lightweight pure-SQLite
                      path with no disk scan and no name-level edges, for hot paths like
                      impact and blast-radius that only need the top structural symbol
                      names, so the name-level whole-graph scan does not slow them down
                      without slowing down structural queries.

    Returns {project_key, token_budget, approx_tokens, count, symbols:[...with rank...],
    edge_sources, note}.
    A project that has never been indexed fails loudly (RuntimeError), because producing a
    map requires an index.
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"get_map: project has not been indexed yet (no {db_file}); call index_project first."
        )

    # Rank a generous candidate pool, then fit entries to the measured budget. The pool
    # only has to over-supply: _fit_symbols_to_budget does the real accounting, and
    # nlargest over the pool is cheap next to building the graph.
    top_n = max(1, token_budget // 6)

    with storage.ProjectStore.open_readonly(abs_path) as store:
        # Keep revision, symbols, references, and indexed-file membership on
        # one SQLite snapshot while an explicit reindex may commit in parallel.
        store.conn.execute("BEGIN")
        symbol_revision = store.symbol_revision()
        symbols = store.load_symbol_snapshot(symbol_revision)
        symbol_snapshot_hit = symbols is not None
        if symbols is None:
            symbols = store.get_symbols()
        db_refs = store.all_refs()
        # namegraph: name-level whole-graph edges, computed in memory, **never persisted to
        # the refs table**, and always low confidence. This fixes the signature degradation
        # where a fresh reindex without any find_references run leaves refs=0 and PageRank
        # collapses to a uniform distribution. The database's high edges (jedi/ts-morph real
        # resolution, weight 1.0) still dominate; the name-level low edges (0.25 × a quality
        # coefficient) only supply the structural floor when there would otherwise be no
        # edges. callgraph, impact and find_references all read the refs table, so they are
        # unaffected.
        name_edges: list[dict] = []
        ng_meta = None
        if with_name_edges and namegraph.namegraph_enabled():
            map_file_limit, adaptive_limit = namegraph.map_file_limit(len(symbols))
            name_edges, ng_meta = namegraph.build_name_edges(
                symbols, indexed_files=store.all_indexed_files(),
                max_files=map_file_limit, preferred_files=focus_files)
            ng_meta["adaptive_file_limit"] = adaptive_limit
            ng_meta["effective_max_files"] = map_file_limit
        refs = db_refs + name_edges
        name_edge_count = int((ng_meta or {}).get("total_edges", len(name_edges)))
        name_unique_count = len(name_edges)
        ranked = rank_symbols(symbols, refs, top_n=top_n, damping=damping,
                              focus_symbols=focus_symbols, focus_files=focus_files)
        # When the scan is truncated, report sampled coverage instead of project-wide coverage.
        truncated = bool((ng_meta or {}).get("truncated"))
        # The note is charged to the caller's token budget on every call, so it states
        # what changes a decision and leaves the diagnostics to edge_sources.
        coverage = (f"sampled {(ng_meta or {}).get('scanned_files')}/"
                    f"{(ng_meta or {}).get('total_files')} files, later symbols underrated"
                    if truncated else "whole project")
        if not refs:
            note = ("No reference edges, so PageRank fell back to a uniform distribution and "
                    "this ordering is not meaningful. Either the project has no internal "
                    "cross-references, or namegraph is disabled.")
        elif not db_refs:
            note = (f"Ordered by {name_edge_count} name-level low-confidence references "
                    f"({name_unique_count} unique edges, {coverage}). Run "
                    "find_references(persist=True) on hot symbols to add resolved edges.")
        else:
            note = (f"Ordered by {len(db_refs)} high-confidence and {name_edge_count} "
                    f"name-level low-confidence references ({name_unique_count} unique edges, "
                    f"{coverage}).")
        result = {
            "project_key": store.project_key,
            "token_budget": token_budget,
            "approx_tokens": 0,
            "count": 0,
            "symbols": [],
            "edge_sources": {
                "db_high_edges": len(db_refs),
                "name_low_edges": name_edge_count,
                "name_low_unique_edges": name_unique_count,
                "symbol_snapshot_hit": symbol_snapshot_hit,
                "namegraph_meta": ng_meta,
            },
            "note": note,
        }
        _fit_symbols_to_budget(result, ranked, token_budget)
        if not symbol_snapshot_hit:
            _schedule_symbol_snapshot(store.db_file, symbol_revision, symbols)
        return result


def _map_cache_key(path: str, token_budget: int, damping: float,
                   focus_symbols, focus_files, with_name_edges: bool) -> tuple:
    db_file = storage.db_path_for(path)
    stat = db_file.stat()
    env_signature = tuple((name, os.environ.get(name)) for name in _MAP_CACHE_ENV)
    # The package version is part of the key because a map snapshot outlives the code
    # that produced it. Without it, upgrading CodeSextant kept serving maps built by the
    # previous ranking from the on-disk snapshot: every ranking fix would reach a new
    # project and never an existing one.
    from . import __version__ as engine_version
    return (
        os.path.normcase(os.path.abspath(path)), stat.st_mtime_ns, stat.st_size,
        int(token_budget), float(damping), tuple(focus_symbols or ()),
        tuple(focus_files or ()), bool(with_name_edges), env_signature,
        engine_version,
    )


def _map_cache_digest(key: tuple) -> str:
    return hashlib.sha256(repr(key).encode("utf-8")).hexdigest()


def _map_cache_limit() -> int:
    try:
        return max(1, int(os.environ.get("CODESEXTANT_MAP_CACHE_SIZE", "4")))
    except ValueError:
        return 4


def get_map(path: str, token_budget: int = 2000, *, damping: float = 0.85,
            focus_symbols=None, focus_files=None, with_name_edges: bool = True) -> dict:
    """The public map, with a revision-aware LRU; within the daemon, the same index and the
    same parameters return a copy of the cached small result directly."""
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return _get_map_uncached(
            abs_path, token_budget, damping=damping, focus_symbols=focus_symbols,
            focus_files=focus_files, with_name_edges=with_name_edges)

    key = _map_cache_key(
        abs_path, token_budget, damping, focus_symbols, focus_files, with_name_edges)
    key_digest = _map_cache_digest(key)
    with _MAP_CACHE_LOCK:
        cached = _MAP_CACHE.get(key)
        if cached is not None:
            _MAP_CACHE.move_to_end(key)
            result = deepcopy(cached)
            result["edge_sources"]["map_cache_hit"] = True
            result["edge_sources"]["map_cache_source"] = "memory"
            return result

    persisted = storage.load_map_snapshot(db_file, key_digest)
    if persisted is not None:
        result = deepcopy(persisted)
        result["edge_sources"]["map_cache_hit"] = True
        result["edge_sources"]["map_cache_source"] = "disk"
        with _MAP_CACHE_LOCK:
            _MAP_CACHE[key] = deepcopy(result)
            _MAP_CACHE.move_to_end(key)
            while len(_MAP_CACHE) > _map_cache_limit():
                _MAP_CACHE.popitem(last=False)
        return result

    result = _get_map_uncached(
        abs_path, token_budget, damping=damping, focus_symbols=focus_symbols,
        focus_files=focus_files, with_name_edges=with_name_edges)
    result["edge_sources"]["map_cache_hit"] = False
    result["edge_sources"]["map_cache_source"] = "compute"
    cache_size = _map_cache_limit()
    with _MAP_CACHE_LOCK:
        _MAP_CACHE[key] = deepcopy(result)
        _MAP_CACHE.move_to_end(key)
        while len(_MAP_CACHE) > cache_size:
            _MAP_CACHE.popitem(last=False)
    try:
        storage.write_map_snapshot(db_file, key_digest, result)
    except (OSError, TypeError, ValueError) as exc:
        print(f"  Warning: failed to write map snapshot: {type(exc).__name__}: {exc}",
              file=sys.stderr)
    return result


# ── preflight: what to know before changing something ──
#
# Three questions get asked after the damage instead of before it: does this already
# exist, what else has to change with it, and who breaks. Each already had a tool, and
# each tool was one more optional call to remember, so in practice all three were
# skipped. preflight answers them together, cheaply enough that always asking costs
# nothing, which is the only version of this that survives contact with a real task.


# A single shared word is not evidence on its own, but two names of the same shape
# that differ in exactly one slot are: md5_utf8 beside sha256_utf8, list_domains
# beside list_paths. Scored at the default threshold, so the match is included by
# default and drops out the moment anyone raises the bar.
_FAMILY_SIMILARITY = 0.5


def _identifier_words(name: str) -> list[str]:
    """Words inside an identifier, in order: parse_duration, parseDuration alike."""
    words: list[str] = []
    for chunk in name.replace("-", "_").split("_"):
        if not chunk:
            continue
        start = 0
        for index in range(1, len(chunk) + 1):
            at_end = index == len(chunk)
            boundary = not at_end and chunk[index].isupper() and not chunk[index - 1].isupper()
            if at_end or boundary:
                if index - start > 0:
                    words.append(chunk[start:index].lower())
                start = index
    return [w for w in words if w]


def _identifier_tokens(name: str) -> set[str]:
    """The same words, unordered, for callers that only ask whether one is present."""
    return set(_identifier_words(name))


def _same_shape_family(left: list[str], right: list[str]) -> bool:
    """Two names of the same length differing in exactly one word.

    This is what a copy-pasted family looks like -- md5_utf8 and sha256_utf8,
    get_binary_stdin and get_binary_stdout -- and what a shared verb does not:
    release_version against release differs in *length*, so it stays rejected. The
    thing that separates the two is not how many words are shared, which is one in
    both cases, but whether the names have the same shape. Single-word names are
    excluded, because two of those differing in their one position share nothing.
    """
    if len(left) != len(right) or len(left) < 2:
        return False
    return sum(1 for a, b in zip(left, right) if a != b) == 1  # noqa: B905


def _name_similarity(left: str, right: str) -> float:
    """Jaccard overlap of the words in two identifiers; 1.0 for the same name.

    Two names must share at least two words to count as similar at all, because one
    shared word is usually just a common verb: release_version against release, or
    get_user against get. Names of a single word are therefore only ever matched
    exactly, which is the correct standard for them -- run and runner are not the
    same function, and offering them as reuse candidates trains the reader to skim
    past the section that matters.

    The exception is a same-shape family: equal word counts differing in exactly one
    position. An experiment found the strict rule missing every differently-named
    structural duplicate in one repository -- md5_utf8 beside sha256_utf8,
    list_domains beside list_paths -- all of which share one word and all of which
    are the same code written twice. See :func:`_same_shape_family` for why shape and
    not count is the thing that separates those from a shared verb.
    """
    if left == right:
        return 1.0
    left_words, right_words = _identifier_words(left), _identifier_words(right)
    a, b = set(left_words), set(right_words)
    if not a or not b:
        return 0.0
    shared = a & b
    if len(shared) >= 2:
        return len(shared) / len(a | b)
    if shared and _same_shape_family(left_words, right_words):
        return _FAMILY_SIMILARITY
    return 0.0


def _common_name_max() -> int:
    """How many definitions may share a name before the name stops being evidence.

    This is also the list length, deliberately: one number, so there is no band where
    a name is uncommon enough to report but too common to report *fully*. Either the
    candidates all fit and you see all of them, or the name is a convention and you
    are told that instead. Showing an arbitrary eight of nine was the failure an
    experiment caught, and a second cutoff is how it would come back.
    """
    raw = os.environ.get("CODESEXTANT_PREFLIGHT_COMMON_NAME_MAX", "").strip()
    if not raw:
        return 8
    try:
        return max(1, int(raw))
    except ValueError:
        return 8


def _path_proximity(target: str, candidate: str) -> int:
    """Leading directory components two paths share. Higher is nearer."""
    left = os.path.normcase(os.path.dirname(target)).split(os.sep)
    right = os.path.normcase(os.path.dirname(candidate)).split(os.sep)
    shared = 0
    # Deliberately not strict=: the paths have different depths and the shorter one
    # ending is exactly where the shared prefix ends.
    for a, b in zip(left, right):  # noqa: B905
        if a != b:
            break
        shared += 1
    return shared


def _reuse_candidates(store, symbol: str, target: str,
                      limit: int) -> tuple[list[dict], int]:
    """Existing definitions that may already be what ``symbol`` is about to become.

    Name-based on purpose. This runs before the code exists, so there is no body to
    fingerprint; what the caller has is an intent with a name, and a name is enough to
    catch the common case of writing a second parse_duration next to the first.

    Returns (candidates, definitions sharing the name exactly). When that count is
    large the exact matches are dropped rather than sampled: a repository with
    thirty-eight definitions called ``__init__`` is telling you about a convention,
    and answering "here are eight of them" is worse than answering nothing, because
    it looks like a finding. Which eight would also have been arbitrary, which is how
    this was found -- an experiment scored the reuse check below plain grep on a
    repository whose duplicates were all called ``__init__``.
    """
    threshold = cochange._env_float(
        "CODESEXTANT_PREFLIGHT_NAME_SIMILARITY", 0.5)
    # Let SQLite discard the rows that cannot match. A candidate has to share a whole
    # word with the query, or be the same name, so anything else is not worth turning
    # into a Python dict -- and on a repository with half a million symbols, turning
    # them all into dicts to score and throw away is the entire cost of the call.
    tokens = _identifier_tokens(symbol)
    kinds = sorted(_REFERENCEABLE_KINDS)
    clauses = ["name = ?"]
    params: list = list(kinds) + [symbol]
    for token in sorted(tokens):
        clauses.append("name LIKE ? COLLATE NOCASE")
        params.append(f"%{token}%")
    query = (f"SELECT path,kind,name,line FROM symbols "
             f"WHERE kind IN ({','.join('?' for _ in kinds)}) "
             f"AND ({' OR '.join(clauses)})")
    scored: list[tuple[float, int, dict]] = []
    for row in store.conn.execute(query, params).fetchall():
        score = _name_similarity(symbol, row["name"])
        if score < threshold:
            continue
        same_file = os.path.normcase(row["path"]) == os.path.normcase(target)
        # A match in the very file being edited is the one most likely to be an
        # accidental second implementation, so it outranks a distant one; a test
        # helper is the least likely thing to reuse, so it sinks.
        rank = (score + (0.25 if same_file else 0.0)
                - (0.3 if ranking_is_test_path(row["path"]) else 0.0))
        # Ties are broken by proximity, then by path. Equal names used to be ordered by
        # descending line number, which is deterministic but means nothing: it decided
        # which of thirty-eight identical scores a caller got to see.
        scored.append((rank, _path_proximity(target, row["path"]), row["path"], {
            "name": row["name"], "kind": row["kind"], "path": row["path"],
            "line": row["line"], "similarity": round(score, 2),
            "same_file": same_file,
        }))
    exact = sum(1 for _r, _p, _path, entry in scored if entry["name"] == symbol)
    if exact > _common_name_max():
        scored = [item for item in scored if item[3]["name"] != symbol]
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [entry for _rank, _proximity, _path, entry in scored[:limit]], exact


def _repo_relative(root: str, target: str) -> str | None:
    """Git-style relative path, or None when target is outside the repository."""
    try:
        relative = os.path.relpath(target, root)
    except ValueError:
        return None
    if relative.startswith(os.pardir):
        return None
    return relative.replace(os.sep, "/")


def _ensure_cochange(abs_path: str) -> dict:
    """Bring co-change rules up to date with HEAD. Returns the mining stats.

    Re-mined when HEAD moves, which is cheap (reading `git log --name-only` costs about
    a tenth of a millisecond per commit and the read is capped), and stored even when it
    finds nothing so a thin history is not re-mined on every call.
    """
    if not cochange.enabled():
        return {"available": False, "reason": "disabled by CODESEXTANT_COCHANGE_DISABLED"}
    try:
        head = _git_head_sha(abs_path)
        # Probe read-only first. ProjectStore.open writes on every call -- schema
        # script, migrations, two meta rows, a commit -- and the common case here is
        # that nothing needs mining, so paying for a write connection to discover that
        # is most of the cost of a call meant to be too cheap to think about.
        with storage.ProjectStore.open_readonly(abs_path) as store:
            previous = store.cochange_head()
        if previous == (head or ""):
            return {"available": True, "cached": True, "head": head}

        # Read only what is new. The totals describe every commit read so far, so a new
        # commit costs one commit rather than the history -- unless that history was
        # rewritten under us, in which case `previous..HEAD` describes a different set of
        # commits than the totals assume and they have to be rebuilt.
        incremental = bool(previous) and cochange.is_ancestor(abs_path, previous)
        commits = cochange.read_commits(
            abs_path, since=previous if incremental else None)
        if commits is None:
            return {"available": False,
                    "reason": "not a Git worktree, or Git is unavailable"}
        changes, pairs = cochange.tally(commits)
        with storage.ProjectStore.open(abs_path) as store:
            if not incremental:
                store.clear_cochange_counts()
            store.add_cochange_counts(changes, pairs, head)
        cap = cochange.max_commit_files()
        return {"available": True, "cached": False, "head": head,
                "incremental": incremental, "commits_read": len(commits),
                "commits_used": sum(1 for _sha, files in commits
                                    if 2 <= len(files) <= cap),
                "commits_skipped_as_sweeping": sum(
                    1 for _sha, files in commits if len(files) > cap),
                "max_commit_files": cap,
                "min_support": cochange.min_support(),
                "min_confidence": cochange.min_confidence()}
    except Exception as exc:
        # One of three sections, and the only one that shells out. A slow Git, a busy
        # index or a repository shape nobody anticipated must cost this section, not the
        # answer: preflight is only useful if calling it is never a risk.
        return {"available": False,
                "reason": f"mining failed ({type(exc).__name__}: {exc})"}


def _merge_cochange(symbol_rules: list[dict], file_rules: list[dict],
                    symbol: str | None) -> list[dict]:
    """Symbol-scoped rules first, then file-scoped ones they do not already cover."""
    merged = [
        {"path": rule["companion"], "scope": "symbol", "symbol": symbol,
         "confidence": round(rule["confidence"], 3), "support": rule["support"],
         "changes": rule["changes"]}
        for rule in symbol_rules
    ]
    covered = {rule["companion"] for rule in symbol_rules}
    merged.extend(
        {"path": rule["companion"], "scope": "file",
         "confidence": round(rule["confidence"], 3), "support": rule["support"],
         "changes": rule["changes"]}
        for rule in file_rules if rule["companion"] not in covered
    )
    return merged


def _ensure_symbol_cochange(abs_path: str, relative: str) -> dict:
    """Bring one file's symbol-level rules up to date with HEAD.

    Per file rather than per repository: reading full diffs for a whole project costs
    tens of megabytes and seconds, while reading them for the one file preflight was
    asked about costs a hundredth of that. The caller already named the file, so there
    is no reason to mine the rest.
    """
    if not cochange.enabled():
        return {"available": False, "reason": "disabled by CODESEXTANT_COCHANGE_DISABLED"}
    try:
        head = _git_head_sha(abs_path)
        with storage.ProjectStore.open_readonly(abs_path) as store:
            if store.symbol_cochange_head(relative) == (head or ""):
                return {"available": True, "cached": True}
        with storage.ProjectStore.open(abs_path) as store:
            mined = cochange.mine_symbols(abs_path, relative)
            if not mined["stats"].get("available"):
                return mined["stats"]
            store.store_symbol_cochange(relative, mined["rules"], head)
            stats = dict(mined["stats"])
            stats["cached"] = False
            return stats
    except Exception as exc:
        return {"available": False,
                "reason": f"symbol mining failed ({type(exc).__name__}: {exc})"}


# How many files may name a symbol before resolving it inline is too expensive.
# Resolution costs on the order of a tenth of a second per file that names the symbol
# (jedi resolves every occurrence back to the definition), while the sweep that counts
# those files costs a fraction of a millisecond each. 25 keeps the worst case to a few
# seconds and covers the overwhelming majority of symbols; 0 turns inline resolution off.
_RESOLVE_MAX_FILES_DEFAULT = 25
# Beyond this the sweep stops counting. A name in four hundred files is not a name a
# per-symbol blast radius can say anything useful about, and finishing the count would
# only make the answer slower without making it better.
_SWEEP_LIMIT = 400


def _resolve_max_files() -> int:
    raw = os.environ.get("CODESEXTANT_PREFLIGHT_RESOLVE_MAX_FILES", "").strip()
    if not raw:
        return _RESOLVE_MAX_FILES_DEFAULT
    try:
        return max(0, int(raw))
    except ValueError:
        return _RESOLVE_MAX_FILES_DEFAULT


def _normalize_resolve(value) -> bool | str:
    """Coerce a caller's resolve flag to True, False or "auto".

    Normalized here rather than at each surface so the CLI flag, the query parameter
    and the MCP argument cannot come to mean three slightly different things.
    """
    if value is None or value == "":
        return "auto"
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return "auto"


def _resolvable_language(abs_target: str) -> str | None:
    """The language name if this file's references can really be resolved, else None.

    Everything outside this set degrades to name matching inside find_references, which
    persists nothing: running it would spend the time and leave the blast radius exactly
    where it started, which is worse than declining and saying why.
    """
    lang = symbols.language_for_file(abs_target)
    if lang in (None, "python"):
        return "python"
    if lang in ("typescript", "javascript") and references.ts_morph_available():
        return lang
    return None


def _ensure_blast_radius(abs_path: str, abs_target: str, symbol: str | None, *,
                         resolve, defined_here: bool) -> dict:
    """Make the blast radius mean something on the first ask, and keep it meaning it.

    An empty blast radius used to carry two readings a caller could not tell apart:
    nothing depends on this symbol, or nobody has resolved it yet. The refs table only
    fills in as find_references runs, so on a fresh index the second reading was always
    the true one -- the section was worth least on the call where it mattered most.

    Resolution is not simply run every time, because preflight is only worth calling
    before every edit if calling it is never a decision. The cost is driven by how many
    files name the symbol, and a text sweep measures that for about seven microseconds
    per file, against a tenth of a second per file to resolve. So: measure, resolve when
    the measurement says it is cheap, and when it is not, hand back the sweep as leads
    and say what was not done.

    The same sweep is what makes caching the expensive half safe. A caller has to name
    the symbol, so the files naming it are a complete superset of the possible callers;
    if none of them has changed and no new one has appeared, no caller can have
    appeared either. Keying the cache to the *defining* file instead -- the obvious
    choice, and the wrong one -- would go stale silently the moment a caller was added
    somewhere else, and would keep reporting a measured absence that had stopped being
    true.

    ``resolve`` is True to resolve regardless of the measurement, False never, and
    "auto" to let the measurement decide.

    Returns {status, reason, name_match_files, name_match_count, name_match_truncated,
    elapsed_sec}.
    """
    outcome: dict = {"status": "", "reason": "", "name_match_files": [],
                     "name_match_count": 0, "name_match_truncated": False,
                     "elapsed_sec": 0.0}

    def decided(status: str, reason: str = "") -> dict:
        outcome["status"] = status
        outcome["reason"] = reason
        return outcome

    if symbol is None:
        return decided("no-symbol", "resolution needs a symbol; without one every "
                                    "definition in the file would have to be resolved")
    if not defined_here:
        # The common case for a new symbol. There is nothing to resolve yet, and saying
        # so is more useful than an empty section that looks like a finding.
        return decided("undefined-in-target",
                       f"{symbol!r} is not defined in this file yet, so it has no callers "
                       "to resolve")
    if resolve is False:
        # The escape hatch for a caller who wants preflight to do nothing beyond
        # reading what is stored. It buys nothing else, including the sweep.
        return decided("off", "resolution was turned off for this call")

    language = _resolvable_language(abs_target)
    sweep_language = language or symbols.language_for_file(abs_target)
    try:
        sweep = references.name_sweep(
            abs_path, symbol, lang=sweep_language, limit=_SWEEP_LIMIT)
    except Exception as exc:
        return decided("failed", f"the name sweep failed ({type(exc).__name__}: {exc})")
    # The file being edited names the symbol by definition; listing it as a lead to
    # itself is noise. It stays in the digest, where its content still counts.
    matches = [m for m in sweep.files
               if os.path.normcase(os.path.abspath(m)) != os.path.normcase(abs_target)]
    outcome["name_match_files"] = matches
    outcome["name_match_count"] = len(matches)
    outcome["name_match_truncated"] = sweep.truncated

    try:
        with storage.ProjectStore.open_readonly(abs_path) as store:
            cached = store.symbol_references_resolved(abs_target, symbol, sweep.digest)
    except sqlite3.OperationalError:
        cached = False
    if cached:
        return decided("cached", "references were resolved against this exact evidence, "
                                 "and nothing that names the symbol has changed since")
    if language is None:
        return decided(
            "unsupported",
            f"CodeSextant has no import resolution for {sweep_language or 'this language'}"
            + (", and the ts-morph bridge is not installed"
               if sweep_language in ("typescript", "javascript") else ""))
    cap = _resolve_max_files()
    if resolve is not True and cap == 0:
        return decided("declined", "inline resolution is switched off by "
                                   "CODESEXTANT_PREFLIGHT_RESOLVE_MAX_FILES=0")
    if resolve is not True and len(matches) > cap:
        counted = f"{len(matches)}{'+' if sweep.truncated else ''}"
        return decided(
            "declined",
            f"{counted} file(s) name {symbol!r}, above the inline limit of {cap} "
            "(CODESEXTANT_PREFLIGHT_RESOLVE_MAX_FILES); resolving them would cost "
            "seconds, and preflight is only worth calling if calling it is never a "
            "decision")

    started = time.perf_counter()
    try:
        find_references(abs_path, symbol, def_path=abs_target,
                        include_low_confidence=False, persist=True)
    except Exception as exc:
        outcome["elapsed_sec"] = round(time.perf_counter() - started, 3)
        # One of three sections, and the expensive one. A failure here costs the section,
        # never the answer.
        return decided("failed", f"resolution failed ({type(exc).__name__}: {exc})")
    outcome["elapsed_sec"] = round(time.perf_counter() - started, 3)
    if sweep.truncated:
        # The digest describes a prefix of the evidence, so it cannot stand in for all
        # of it. Answer this call and re-resolve next time rather than cache a claim
        # about files the sweep never reached.
        return decided("resolved", "the name sweep hit its file limit, so this result "
                                   "is not cached")
    try:
        with storage.ProjectStore.open(abs_path) as store:
            store.mark_symbol_references_resolved(abs_target, symbol, sweep.digest)
    except sqlite3.OperationalError:
        # A busy index costs the marker, not the answer: the next call resolves again.
        return decided("resolved", "resolved, but the result could not be marked as "
                                   "current because the index was busy")
    return decided("resolved", "")


def _module_dependents_for(abs_path: str, relative: str | None, named,
                           notes: list) -> list[dict]:
    """Files importing the module being edited, for preflight's blast radius.

    check asks this of a whole diff and this asks it of one file, but it is the same
    claim and it is bounded the same way: at most ``_DEPENDENTS_SHOWN``, and none at all
    past ``_DEPENDENTS_MAX`` importers, where any two would be an arbitrary two.

    Files the symbol-level tiers already named are passed over. They are the stronger
    statement about the same file, and a slot spent repeating one is a slot not spent on
    a file neither tier reached -- which is the whole reason this tier is here.
    """
    if not relative or not relative.endswith(".py"):
        return []
    try:
        found = references.module_dependents(
            abs_path, [relative], skip={relative}, limit=_DEPENDENTS_MAX + 1)
    except OSError as exc:
        notes.append(f"Module dependents could not be scanned ({type(exc).__name__}).")
        return []
    if not found:
        return []
    if len(found) > _DEPENDENTS_MAX:
        notes.append(
            f"More than {_DEPENDENTS_MAX} files import this module, so no dependents "
            "are listed: at that width any two of them would be an arbitrary two.")
        return []
    already = {os.path.normcase(os.path.abspath(p)) for p in named}
    ranked = sorted((path for path in found
                     if os.path.normcase(os.path.abspath(os.path.join(abs_path, path)))
                     not in already),
                    key=lambda path: (-found[path], path))
    return [{"path": path, "imports": found[path]}
            for path in ranked[:_DEPENDENTS_SHOWN]]


def _read_blast_radius(store, abs_target: str, symbol: str | None) -> tuple[list[str], int]:
    """Files with resolved references into the target, and the project-wide edge total."""
    if symbol:
        rows = store.conn.execute(
            "SELECT DISTINCT src_path FROM refs WHERE def_path=? AND symbol_name=? "
            "AND confidence='high' ORDER BY src_path", (abs_target, symbol)).fetchall()
    else:
        rows = store.conn.execute(
            "SELECT DISTINCT src_path FROM refs WHERE def_path=? AND confidence='high' "
            "ORDER BY src_path", (abs_target,)).fetchall()
    total = store.conn.execute(
        "SELECT COUNT(*) AS n FROM refs WHERE confidence='high'").fetchone()["n"]
    return [r["src_path"] for r in rows], total


def preflight(path: str, target: str, *, symbol: str | None = None,
              token_budget: int = 1200, resolve="auto") -> dict:
    """Everything worth knowing before editing ``target``, in one answer.

    Parameters
    ----------
    path   : the project root.
    target : the file about to be changed.
    symbol : the name about to be added or changed. Supplying it turns on the reuse
             check, which is the half that has to happen before the code is written.
    resolve : whether to resolve this symbol's references when none are recorded yet.
             "auto" (the default) measures the cost first and resolves when it is
             small; True resolves regardless; False never does. See
             :func:`_ensure_blast_radius`.

    Returns {target, symbol, already_exists, co_change, blast_radius, notes,
    approx_tokens}. Each section states its own evidence, because all three are
    heuristics and a caller that cannot see the strength of a claim cannot weigh it.
    """
    abs_path = os.path.abspath(path)
    resolve = _normalize_resolve(resolve)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"preflight: project has not been indexed yet (no {db_file}); "
            "call index_project first.")
    abs_target = target if os.path.isabs(target) else os.path.join(abs_path, target)
    abs_target = os.path.abspath(abs_target)
    relative = _repo_relative(abs_path, abs_target)

    cochange_stats = _ensure_cochange(abs_path)
    symbol_stats: dict = {"available": False, "reason": "no symbol given"}
    if symbol and relative and cochange_stats.get("available"):
        symbol_stats = _ensure_symbol_cochange(abs_path, relative)
    notes: list[str] = []

    with storage.ProjectStore.open_readonly(abs_path) as store:
        already, shared_name_count = (
            _reuse_candidates(store, symbol, abs_target, limit=_common_name_max())
            if symbol else ([], 0))
        companions = (
            store.cochange_rules_for(
                relative, min_support=cochange.min_support(),
                min_confidence=cochange.min_confidence())
            if relative else [])
        symbol_companions = (
            store.symbol_cochange_for(relative, symbol)
            if symbol and relative and symbol_stats.get("available") else [])
        dependents, total_edges = _read_blast_radius(store, abs_target, symbol)
        defined_here = bool(symbol) and store.conn.execute(
            "SELECT 1 FROM symbols WHERE path=? AND name=? LIMIT 1",
            (abs_target, symbol)).fetchone() is not None

    resolution = _ensure_blast_radius(
        abs_path, abs_target, symbol, resolve=resolve, defined_here=defined_here)
    if resolution["status"] == "resolved":
        with storage.ProjectStore.open_readonly(abs_path) as store:
            dependents, total_edges = _read_blast_radius(store, abs_target, symbol)
    # Leads are what named the symbol and did not resolve to it. They are reported
    # beside confirmed callers rather than instead of them, because a resolver that
    # cannot see through dynamic dispatch, a re-export or a registry will resolve some
    # callers and miss others -- and "one file calls this" is a worse answer than "one
    # file calls this and one more names it" when the second one is also a caller.
    resolved_set = {os.path.normcase(p) for p in dependents}
    leads = [m for m in resolution["name_match_files"]
             if os.path.normcase(os.path.abspath(m)) not in resolved_set]

    # The same module-level question check asks, asked here about the file rather than
    # about a diff. Added beside the two symbol-level tiers rather than replacing the
    # leads: measured over 525 held-out-file cases, adding it is +0.050 [+0.029, +0.076]
    # on the blast radius and +0.040 [+0.018, +0.065] on the whole answer, while
    # swapping it for the leads is +0.004 and not established. The leads earn their
    # place -- jinja is the evidence -- and this earns a place beside them.
    module_dependents = _module_dependents_for(
        abs_path, relative, {*dependents, *leads}, notes)

    if symbol and shared_name_count > _common_name_max():
        notes.append(
            f"{shared_name_count} definitions in this project are named {symbol!r}. "
            "That is a naming convention here, not something you would be duplicating, "
            "so they are not listed: any eight of them would have been arbitrary. "
            "find_duplicates compares shape and can tell them apart.")
    elif symbol and not already:
        # "It looks new" was an overclaim: this compares names, and something
        # equivalent under an unrelated name never had a chance of showing up.
        notes.append(
            f"No indexed definition has a name resembling {symbol!r}. That is a name "
            "check; an equivalent under an unrelated name would not appear here, and "
            "find_duplicates is the one that compares shape.")
    elif not symbol:
        notes.append("Pass symbol= to check whether the thing you are adding already exists.")
    if not cochange_stats.get("available"):
        notes.append("Co-change is unavailable: " + str(cochange_stats.get("reason", "unknown")))
    elif not companions:
        notes.append("History shows nothing that reliably changes with this file.")
    notes.extend(_blast_radius_notes(symbol, dependents, leads, total_edges, resolution))

    result = {
        "project_key": storage.project_key(abs_path),
        "target": abs_target,
        "symbol": symbol,
        "already_exists": already,
        # Symbol-scoped rules come first and supersede the file-scoped rule for the
        # same companion: both are true, but "changing this function" is the question
        # the caller actually asked, and showing the coarser claim beside it only
        # invites reading the weaker number.
        "co_change": _merge_cochange(symbol_companions, companions, symbol),
        "blast_radius": {
            "dependent_files": dependents,
            "dependent_count": len(dependents),
            "resolved_edges_project_wide": total_edges,
            # The unresolved half, kept in its own key rather than merged in: these are
            # files whose text names the symbol, which is a lead, not a caller. Merging
            # the two would be the exact inflation of confidence this tool exists to
            # avoid, so the split is structural and the renderer marks them apart.
            "name_match_files": leads,
            "name_match_count": len(leads),
            # A third tier and a third kind of claim: not "calls this symbol" and not
            # "names this symbol", but "imports this module". Its own key so the
            # renderer can mark it apart, for the reason directly above.
            "module_dependents": module_dependents,
            "resolution": {"status": resolution["status"],
                           "reason": resolution["reason"],
                           "elapsed_sec": resolution["elapsed_sec"]},
        },
        "cochange_stats": dict(cochange_stats, symbol=symbol_stats),
        "notes": notes,
        "approx_tokens": 0,
    }
    # Every key the caller receives must exist before anything is measured, or the
    # reported figure describes a payload that was never sent.
    result["truncated_by_budget"] = False
    result["approx_tokens"] = _json_tokens(result)
    # Trim the longest lists rather than the explanations: a caller told nothing about
    # why a section is short cannot tell it from a section that was genuinely empty.
    # The two blast-radius lists are never both populated -- leads are reported only
    # when nothing resolved -- so the first two branches trim whichever one this answer
    # has. Leads alone may be drained below the floor the confirmed callers keep,
    # because a lead is the weaker thing to lose.
    while result["approx_tokens"] > token_budget:
        blast = result["blast_radius"]
        if blast["module_dependents"]:
            # Trimmed before either symbol-level tier: "imports this module" is the
            # weakest of the three claims, so it is the cheapest one to lose.
            blast["module_dependents"].pop()
        elif len(blast["name_match_files"]) > 3:
            blast["name_match_files"].pop()
        elif len(blast["dependent_files"]) > 3:
            blast["dependent_files"].pop()
        elif len(result["co_change"]) > 3:
            result["co_change"].pop()
        elif result["already_exists"]:
            result["already_exists"].pop()
        elif blast["name_match_files"]:
            blast["name_match_files"].pop()
        else:
            break  # the envelope alone exceeds the budget; say so rather than lie
        result["truncated_by_budget"] = True
        result["approx_tokens"] = _json_tokens(result)
    return result


def _check_max_symbols() -> int:
    """How many changed symbols may have their callers resolved in one check."""
    raw = os.environ.get("CODESEXTANT_CHECK_MAX_SYMBOLS", "").strip()
    if not raw:
        return 10
    try:
        return max(0, int(raw))
    except ValueError:
        return 10


def _changed_units(abs_path: str, abs_file: str,
                   added: list[tuple[int, int]]) -> list[dict]:
    """Fingerprints of the units this diff wrote, from the file as it stands now.

    This is the thing preflight structurally cannot do. Asked before the edit, there is
    no body to fingerprint -- only a name, which is why the reuse check misses an
    equivalent someone called something else. Asked after, the body exists, and shape
    is a far better question than spelling.
    """
    language = symbols.language_for_file(abs_file)
    if not language:
        return []
    try:
        with open(abs_file, "rb") as handle:
            source = handle.read()
        units = clones.extract_fingerprints_from_source(
            source, language, file_path=abs_file)
    except (OSError, TypeError, ValueError):
        return []
    return [unit for unit in units
            if diffscan.overlaps(added, unit["line"], unit.get("end_line") or unit["line"])]


def _changed_definitions(store, abs_file: str, added: list[tuple[int, int]]) -> list[dict]:
    """Definitions in this file whose body the diff wrote into, with their own lines.

    The line matters and is easy to drop. A file may define the same name twice --
    ``send`` on two classes, ``run`` on a base and its override -- and resolution asked
    only for the name has to guess which one, which it does by taking the first. The
    line says which one the diff actually touched, so anything resolving against these
    can pin the right definition instead of the first same-named one.
    """
    out = []
    for row in store.conn.execute(
            "SELECT name,line,end_line FROM symbols WHERE path=? AND "
            "kind IN ('function','method','class')", (abs_file,)).fetchall():
        end = row["end_line"] or row["line"]
        if diffscan.overlaps(added, row["line"], end):
            out.append({"name": row["name"], "line": row["line"], "end_line": end})
    return out


def _structurally_significant(unit) -> bool:
    """Whether repeating this shape would mean anything.

    The same gate find_duplicates applies, for the same reason and with the same
    knob: control flow plus a node-count floor. Every one-line getter has the shape
    of every other one, and a section that reports those is a section readers learn
    to skip -- which costs the findings that did matter.
    """
    minimum = clones._env_int("CODESEXTANT_DEDUP_MIN_NODE_COUNT", 15)
    return bool(unit["has_control_flow"]) and (unit["node_count"] or 0) >= minimum


def _structural_matches(store, unit: dict, abs_file: str, root: str,
                        changed: set[str], limit: int = 4) -> list[dict]:
    """Indexed units with this one's exact shape, outside the change itself.

    Matches inside the diff are excluded: a unit that moved between two files the same
    commit touched is one unit, and reporting it as a duplicate of itself is the kind
    of false positive that gets a whole section ignored.

    A shape shared by very many units is a pattern rather than a duplication -- the
    same reasoning that stops preflight listing eight of a project's thirty-eight
    ``__init__`` definitions -- so those are dropped instead of sampled.
    """
    if not _structurally_significant(unit):
        return []
    rows = store.conn.execute(
        "SELECT path,name,kind,line,node_count,has_control_flow FROM fingerprints "
        "WHERE shape_hash=? ORDER BY path,line", (unit["shape_hash"],)).fetchall()
    if len(rows) > _common_name_max():
        return []
    out = []
    for row in rows:
        normalized = os.path.normcase(os.path.abspath(row["path"]))
        if normalized in changed or not _structurally_significant(row):
            continue
        if (normalized == os.path.normcase(abs_file)
                and row["line"] == unit["line"]):
            continue
        out.append({"name": row["name"], "kind": row["kind"],
                    "path": _repo_relative(root, row["path"]) or row["path"],
                    "line": row["line"]})
        if len(out) >= limit:
            break
    return out


# How many dependents may be listed, and the number above which none are. These are
# deliberately one pair of numbers rather than a length and a separate cap: past the
# cutoff the two shown would be an arbitrary two of many, which is the same reasoning
# that stops the reuse check offering eight of a project's thirty-eight __init__
# definitions. Measured over 351 held-out-file cases in six repositories, a cutoff of
# 20 costs no recall at all against no cutoff (0.362 either way) while printing less;
# a cutoff of 10 costs 0.012.
_DEPENDENTS_SHOWN = 2
_DEPENDENTS_MAX = 20


def _module_dependents_tier(abs_path: str, supported: dict, changed: dict,
                            companions: dict, callers: list, rebuilt: list,
                            notes: list, *, skip: bool) -> list[dict]:
    """Files importing a module the diff changed, which nothing else already names.

    The caller section asks who calls a changed *symbol* and answers with jedi, which
    is precise and conservative. Measured against real commits, it names the file that
    was held out of the commit in 0.094 of cases; the file-level question -- who imports
    the module you changed -- reaches 0.217, because a module import can be read off the
    source without inference, and because a file that depends on a module often has to
    change with it without calling the exact function that moved.

    The claim is weaker and is kept separate for that reason. What ships is the two
    strongest dependents no other section has already named, which measured +0.046
    recall on three repositories nothing here was tuned against (interval [+0.017,
    +0.080]), for 0.7 more files named per run.
    """
    if skip:
        return []
    python_changed = [rel for rel in supported if rel.endswith(".py")]
    if not python_changed:
        return []
    try:
        found = references.module_dependents(
            abs_path, python_changed, skip=set(changed), limit=_DEPENDENTS_MAX + 1)
    except OSError as exc:
        notes.append(f"Module dependents could not be scanned ({type(exc).__name__}).")
        return []
    if not found:
        return []
    if len(found) > _DEPENDENTS_MAX:
        # Announced rather than silently truncated: a reader told nothing would read
        # the empty section as "nothing depends on this".
        notes.append(
            f"More than {_DEPENDENTS_MAX} files import the modules you changed, so no "
            "dependents are listed: at that width any two of them would be an "
            "arbitrary two.")
        return []
    already = ({entry["path"] for entry in companions.values()}
               | {path for entry in callers for path in entry["callers"]}
               | {match["path"] for entry in rebuilt for match in entry["matches"]})
    ranked = sorted((path for path in found if path not in already),
                    key=lambda path: (-found[path], path))
    return [{"path": path, "imports": found[path]}
            for path in ranked[:_DEPENDENTS_SHOWN]]


# How many fences layer one shows. Six is a glance; the seventh is a list, and a list
# is what a reader learns to skip -- exp1's finding, and the reason every candidate in
# experiments/ is scored at the length the tool actually prints.
_GUARDS_SHOWN = 6

# The history tier's three bounds, and the order they apply in matters. The first
# version truncated the *companion list* to three files and then looked for fences in
# them, which measured at +0.017 where the offline union said +0.100 was there: most
# companions are source files holding nothing, so cutting the list first threw away the
# guard-bearing companion sitting fifth. Walk the list instead, and cap the fences.
#
# _SCAN bounds the work (ten AST extractions, the same depth check mines co-change to),
# _PER_FILE stops one large test file spending the tier, and _SHOWN stops the tier from
# being longer than the section it is meant to finish.
_GUARDS_HISTORY_SCAN = 10
_GUARDS_HISTORY_PER_FILE = 2
_GUARDS_HISTORY_SHOWN = 6

# The importer tier, bounded the same way and for the same reason.
_GUARDS_IMPORTER_PER_FILE = 2
_GUARDS_IMPORTER_SHOWN = 6


def _guard_reach(abs_path: str, changed: dict, symbols_changed: set[str],
                 notes: list) -> dict[str, str]:
    """Which files could hold a fence this change will meet, and why each one is here.

    The two tiers whose evidence is the fence's own text, and the reason is kept
    alongside the file because "you are editing this" and "a test over there names what
    you touched" are different claims that deserve different attention:

    * the change is *inside* the guard's file -- you may be moving the fence itself;
    * a file names one of the symbols you changed -- the test that fences it;

    Bounded by the change rather than the repository, like everything else here: one
    name sweep per changed symbol, capped by the same gate the blast radius uses.

    The third tier is history, and it lives in _guard_history_reach because its evidence
    is about the file rather than about the fence.
    """
    reach = {relative for relative in changed if relative.endswith(".py")}

    for symbol in sorted(symbols_changed)[:_check_max_symbols()]:
        try:
            sweep = references.name_sweep(abs_path, symbol, lang="python",
                                          limit=_SWEEP_LIMIT)
        except Exception:  # noqa: BLE001 - a missing section is not a failed answer
            continue
        if len(sweep.files) > _resolve_max_files():
            # The same cost gate the blast radius uses, for the same reason and with the
            # same announcement: a name in forty files cannot single out a fence.
            notes.append(
                f"{len(sweep.files)} files name {symbol!r}, too many to attribute a "
                "guard to; its fences are not listed.")
            continue
        for found in sweep.files:
            reach.add(_repo_relative(abs_path, found) or found)

    # A tier -- "this file imports a module you changed" -- was built and then removed.
    # It is per-*file* relevance with no per-guard evidence, which is exactly the defect
    # the paragraph in _guards_in_reach exists to prevent: it filled the section with an
    # unrelated environment switch and two symbol-extraction tests while the three fences
    # that actually named the symbol sat above them. check's DEPENDENTS section already
    # answers "who imports what you changed", at file level, where that claim is true.
    #
    # _guard_history_reach is the one per-file tier that survived, and the difference is
    # that it was measured rather than argued: exp9 scores it at +0.111 held out
    # [+0.067,+0.161] on top of these two tiers. It is kept apart from them, labelled as
    # the file-level claim it is, and ranked below both.
    return reach


def _guard_history_reach(abs_path: str, changed: dict) -> dict[str, dict]:
    """Files history says change with the ones you did, strongest agreement first.

    A per-*file* claim, which is why it is a separate function ranked below the two
    per-guard tiers rather than mixed into them. It earns its place by measurement:
    exp9 holds out a fence-bearing file from 360 real commits and asks whether the
    section names it. The symbol tiers reach 0.206 held out, history alone 0.150, and
    the two together 0.317 -- +0.111 [+0.067,+0.161] over the symbol tiers, real in both
    the derivation and the held-out set. They miss different commits, which is the only
    reason to pay for both.

    The complement is the point. A fence is reachable by name only if it spells the
    symbol it guards, and a test suite that drives its subject through templates,
    fixtures or a CLI never does. On jinja -- a template engine, indirection throughout
    -- the symbol tiers find 0.050 and lose to every control; history is what answers
    there.
    """
    stats = _ensure_cochange(abs_path)
    if not stats.get("available"):
        return {}
    best: dict[str, dict] = {}
    with storage.ProjectStore.open_readonly(abs_path) as store:
        for relative in sorted(changed):
            for rule in store.cochange_rules_for(
                    relative, min_support=cochange.min_support(),
                    min_confidence=cochange.min_confidence()):
                companion = rule["companion"]
                if companion in changed or not companion.endswith(".py"):
                    continue
                known = best.get(companion)
                if known is None or rule["confidence"] > known["confidence"]:
                    best[companion] = {"confidence": rule["confidence"],
                                       "because": relative}
    ordered = sorted(best, key=lambda path: (-best[path]["confidence"], path))
    return {path: best[path] for path in ordered[:_GUARDS_HISTORY_SCAN]}


def _guard_importer_reach(abs_path: str, changed: dict, notes: list) -> dict[str, int]:
    """Files importing a module the change touched, most of them first.

    This is the tier that was built, rejected by eye, and then scored -- and the
    measurement reversed the rejection. It was thrown out for being per-*file* relevance
    with no per-guard evidence, which it is. exp9 put it against the shipped answer over
    360 commits: **+0.072 held out [+0.039,+0.111]**, taking recall from 0.228 to 0.300.
    The argument was sound and the conclusion was wrong, which is the case this
    repository writes experiments for.

    It is where it is because a test can import the module it exercises and never write
    the name of the function inside it -- through a fixture, a template, a CLI runner --
    and every tier above reads names. On jinja, the one repository `guards` loses on,
    this is what narrows the loss.

    Unlike check's DEPENDENTS section this is not shut off past twenty importers. There
    the claim is "these files are at risk" and any two of forty would be an arbitrary
    two; here the files are ranked by how much of the change they import and the tier
    only fills slots per-guard evidence left empty. That is the version that was
    measured, so it is the version that ships.
    """
    python_changed = [relative for relative in sorted(changed)
                      if relative.endswith(".py")]
    if not python_changed:
        return {}
    try:
        found = references.module_dependents(abs_path, python_changed,
                                             skip=set(changed))
    except OSError as exc:
        notes.append(f"Module dependents could not be scanned ({type(exc).__name__}); "
                     "fences reachable only through an import are not listed.")
        return {}
    ordered = sorted(found, key=lambda path: (-found[path], path))
    return {path: found[path] for path in ordered}


def _rank_guards(found: list) -> list:
    """Order fences by how directly this change meets them.

    Four tiers, strongest evidence first. A guard naming a symbol you just edited is the
    one about to fail; a guard sitting in a file you touched is context; a guard in a
    file history says moves with yours is a lead; a guard in a file that imports what you
    changed is a weaker lead still. The last two never displace the first two -- they are
    ordered below, so with six slots they fill only what the fence's own text left empty,
    which is the arrangement exp9 measured.

    Within a tier, the one whose author left no reason comes first, because that is the
    one that will cost the most to work out when it fires. Within the two file-level
    tiers, strongest first: co-change confidence, then how much of the change a file
    imports, since there that number *is* the evidence.
    """
    def key(entry):
        why = entry["why"]
        if why.startswith("names"):
            tier = 0
        elif why.startswith("history"):
            tier = 2
        elif why.startswith("imports"):
            tier = 3
        else:
            tier = 1
        return (tier, -entry.get("history_confidence", 0.0),
                -entry.get("imports", 0), entry["reason_source"] != "none",
                entry["path"], entry["line"])

    return sorted(found, key=key)


def _guard_source(abs_path: str, row: dict) -> str:
    """The fence's own lines -- layer three, read only when asked for.

    Kept out of the default answer on purpose. A test body can be forty lines, and six
    of those is the whole context window's worth of exactly the material a reader
    already knows how to open.
    """
    try:
        with open(os.path.join(abs_path, row["path"]),
                  encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return ""
    return "\n".join(lines[row["line"] - 1:row["end_line"]])


def _guards_in_reach(abs_path: str, reach: set[str], changed: dict,
                     symbols_changed: set[str],
                     history: dict[str, dict] | None = None,
                     importers: dict[str, int] | None = None) -> list[dict]:
    """Guards a change reaches, decided per guard rather than per file.

    The distinction is the whole difference between a section worth reading and a
    section people skip. A file that mentions ``module_dependents`` also holds eleven
    environment switches that have nothing to do with it; inheriting the file's reason
    would put all eleven in front of a reader looking for the two tests that actually
    fence the symbol. So a guard reached *because a file names a symbol* has to name
    that symbol **itself**, inside its own span.

    Guards in files the change edits are kept regardless: there the reader is standing
    inside the fence, and which lines they touched is a matter for the ranking rather
    than for admission.

    ``history`` and ``importers`` are the two exceptions to per-guard evidence, and both
    are bounded rather than argued away: at most two guards from each file, at most six
    from each tier, labelled with the file-level claim they rest on, and ranked below
    everything above. Both are here because exp9 measured what each adds and both numbers
    held up out of sample; the paragraphs in _guard_history_reach and
    _guard_importer_reach carry them.
    """
    history = history or {}
    importers = importers or {}
    collected: list[dict] = []
    for relative in sorted(reach):
        abs_file = os.path.abspath(os.path.join(abs_path, relative))
        if not os.path.isfile(abs_file):
            continue
        try:
            with open(abs_file, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().splitlines()
        except OSError:
            continue
        for guard in guards_module.extract_file(abs_file, relative):
            row = guard.as_row()
            if relative in changed:
                row["why"] = "you changed this file"
            else:
                span = "\n".join(lines[guard.line - 1:guard.end_line])
                named = sorted(
                    symbol for symbol in symbols_changed
                    if references._word_re(symbol).search(span))
                if named:
                    row["why"] = f"names {named[0]}"
                    row["names"] = named
                else:
                    continue  # the file mentions it; this fence does not
            collected.append(row)

    # Deduplicated per *guard*, not per file. A companion can be in `reach` because one
    # of its lines mentions a changed symbol while none of its fences do -- in which
    # case the loop above admitted nothing from it, and skipping the whole file here
    # would drop it twice for the same reason.
    already = {(row["path"], row["line"]) for row in collected}

    def take(files, per_file: int, budget: int, describe):
        added = 0
        for relative in files:
            if added >= budget:
                break
            abs_file = os.path.abspath(os.path.join(abs_path, relative))
            if not os.path.isfile(abs_file):
                continue
            from_file = 0
            for guard in guards_module.extract_file(abs_file, relative):
                if from_file >= per_file or added >= budget:
                    break
                row = guard.as_row()
                if (row["path"], row["line"]) in already:
                    continue
                already.add((row["path"], row["line"]))
                describe(row, relative)
                collected.append(row)
                from_file += 1
                added += 1

    def as_history(row, relative):
        evidence = history[relative]
        row["why"] = f"history: changes with {evidence['because']}"
        row["history_confidence"] = round(evidence["confidence"], 3)

    changed_python = [r for r in sorted(changed) if r.endswith(".py")]

    def as_importer(row, relative):
        count = importers[relative]
        row["why"] = (f"imports {changed_python[0]}" if len(changed_python) == 1
                      else f"imports {count} of the {len(changed_python)} modules "
                           "you changed")
        row["imports"] = count

    take(history, _GUARDS_HISTORY_PER_FILE, _GUARDS_HISTORY_SHOWN, as_history)
    take(importers, _GUARDS_IMPORTER_PER_FILE, _GUARDS_IMPORTER_SHOWN, as_importer)
    return collected


def guards(path: str, *, base: str | None = None, staged: bool = False,
           target: str | None = None, symbol: str | None = None,
           full: bool = False, token_budget: int = 1500) -> dict:
    """The fences your change is about to meet, with what each one checks.

    The failure this answers is the one a diff cannot: a guard written months ago blocks
    you now, you do not remember it, and the cheapest-looking way out is to delete it.
    ``check`` says *which file* you forgot. This says *which fence, what it checks, and
    what would satisfy it* -- before the build says it, and without reading a log.

    Two ways to ask, matching the two halves of the tool. With ``target`` it answers
    about one file the way ``preflight`` does, from a name and an intention. Without it,
    it reads the diff the way ``check`` does and answers about everything you touched.

    Progressive disclosure, because the measurement demanded it: a repository holds 182
    to 935 guards (``experiments/exp8_guard_inventory.py``), so a flat list is a second
    codebase and nobody would read it twice.

    * **Layer one** -- which fences are in reach at all: kind, name, ``path:line``. Six
      of them, because the seventh turns a glance into a list. Four tiers of evidence,
      strongest first: the fence names what you changed, the fence sits in a file you
      changed, history says its file moves with yours, or its file imports what you
      changed. The last two are file-level claims, printed with the number they rest on
      and never ahead of a fence read off its own text.
    * **Layer two** -- the rule: what each one checks, derived from the code, plus the
      author's reason when there is one and a note saying which of the two you are
      reading. Printed with layer one because both are short; this is the layer that
      answers "what would satisfy it".
    * **Layer three** -- ``full=True``, the guard's own source. Not fetched otherwise,
      which is the point: it is the expensive layer and it is rarely the one needed.
    """
    abs_path = os.path.abspath(path)
    notes: list[str] = []
    symbols_changed: set[str] = set()

    if target:
        relative = _repo_relative(abs_path, os.path.abspath(
            os.path.join(abs_path, target))) or target
        changed = {relative: "M"}
        if symbol:
            symbols_changed.add(symbol)
    else:
        found_changes = diffscan.changed_files(abs_path, base=base, staged=staged)
        if found_changes is None:
            return {"project_key": storage.project_key(abs_path), "guards": [],
                    "notes": ["guards needs a Git worktree, or a --target to ask about."],
                    "approx_tokens": 0, "truncated_by_budget": False}
        changed = found_changes
        if not changed:
            return {"project_key": storage.project_key(abs_path), "guards": [],
                    "notes": ["Nothing has changed, so there is no fence to meet yet. "
                              "Pass --target to ask about a file before editing it."],
                    "approx_tokens": 0, "truncated_by_budget": False}
        db_file = storage.db_path_for(abs_path)
        if db_file.exists():
            with storage.ProjectStore.open_readonly(abs_path) as store:
                for relative in sorted(changed):
                    abs_file = os.path.abspath(os.path.join(abs_path, relative))
                    if not os.path.isfile(abs_file) or not relative.endswith(".py"):
                        continue
                    ranges = diffscan.changed_ranges(
                        abs_path, relative, base=base, staged=staged)
                    symbols_changed.update(
                        item["name"] for item
                        in _changed_definitions(store, abs_file, ranges["added"]))

    reach = _guard_reach(abs_path, changed, symbols_changed, notes)
    history = _guard_history_reach(abs_path, changed)
    importers = _guard_importer_reach(abs_path, changed, notes)
    collected = _guards_in_reach(abs_path, reach, changed, symbols_changed,
                                 history, importers)

    ranked = _rank_guards(collected)
    if full:
        for row in ranked[:_GUARDS_SHOWN]:
            row["source"] = _guard_source(abs_path, row)
    if not ranked:
        notes.append(
            "No fence in reach of this change: nothing you touched holds a guard, "
            "nothing elsewhere names a symbol you changed, and neither history nor "
            "the import graph offers a file that holds one. That is a search, not a "
            "clean bill of health -- "
            "only Python is read, and a guard living in CI configuration or a database "
            "constraint is outside what this can see.")
    total = len(ranked)
    result = {
        "project_key": storage.project_key(abs_path),
        "changed_files": sorted(changed),
        "guards": ranked[:_GUARDS_SHOWN],
        "total_in_reach": total,
        "notes": notes,
        "approx_tokens": 0,
    }
    result["truncated_by_budget"] = total > _GUARDS_SHOWN
    result["approx_tokens"] = _json_tokens(result)
    while result["approx_tokens"] > token_budget and result["guards"]:
        result["guards"].pop()
        result["truncated_by_budget"] = True
        result["approx_tokens"] = _json_tokens(result)
    return result


def check(path: str, *, base: str | None = None, staged: bool = False,
          token_budget: int = 1500, resolve="auto") -> dict:
    """What the change you have already made looks like it forgot.

    preflight asks three questions before an edit, from a name and an intention. Two
    things limit it, and neither is fixable on that side of the edit: it only runs if
    the author remembers to ask, and it has nothing to work with but a name -- no body
    to compare shapes against, no diff to say what actually happened.

    After the edit both go away. The diff names every file and every line, so the same
    three questions get evidence instead of intent:

    * **rebuilt** -- a unit this change wrote whose exact shape already exists
      somewhere else. Not a name match: the body is there now, so this catches the
      wheel that was reinvented *and renamed*, which is the case preflight cannot see.
    * **companions** -- files history says follow the ones you changed, that you did
      not change. The test, the allowlist, the fixture, the version constant.
    * **callers** -- resolved references to the symbols you changed, in files outside
      your diff. Changing A while B calls it is how B breaks.

    Cost is bounded by the change rather than the repository, which is what makes it
    affordable to run on every edit: only changed files are re-indexed and parsed, and
    at most ``CODESEXTANT_CHECK_MAX_SYMBOLS`` symbols have their callers resolved.
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"check: project has not been indexed yet (no {db_file}); "
            "call index_project first.")
    resolve = _normalize_resolve(resolve)
    notes: list[str] = []

    changed = diffscan.changed_files(abs_path, base=base, staged=staged)
    if changed is None:
        return _empty_check(abs_path, [
            "check needs a Git worktree: it reads what you changed from the diff."])
    if not changed:
        return _empty_check(abs_path, [
            "Nothing has changed against " + (base or ("the index" if staged else "HEAD"))
            + ", so there is nothing to check."])

    supported = {rel: status for rel, status in changed.items()
                 if os.path.splitext(rel)[1].lower() in symbols.SUPPORTED_EXTENSIONS}
    truncated_diff = len(changed) > diffscan.MAX_CHANGED_FILES
    if truncated_diff:
        notes.append(
            f"The diff touches {len(changed)} files, beyond the {diffscan.MAX_CHANGED_FILES} "
            "this check reads. A change that large is reviewed by splitting it, not by "
            "a longer list; only co-change is reported below.")

    changed_abs = {os.path.normcase(os.path.abspath(os.path.join(abs_path, rel)))
                   for rel in changed}

    # The index has to describe the code as it stands, or the line ranges in the diff
    # will not line up with the symbols they touched. Only changed files are re-read.
    existing = [os.path.join(abs_path, rel) for rel in supported
                if os.path.isfile(os.path.join(abs_path, rel))]
    if existing and not truncated_diff:
        try:
            index_paths(abs_path, existing)
        except Exception as exc:  # noqa: BLE001 - a stale index costs precision, not the run
            notes.append(f"Changed files could not be re-indexed ({type(exc).__name__}); "
                         "line ranges may be out of date.")

    rebuilt: list[dict] = []
    changed_symbols: list[tuple[str, str]] = []
    if not truncated_diff and supported:
        # Shapes are derived lazily, so the first check on a project pays for them once
        # and later ones pay only for the files that changed.
        _materialize_derived(abs_path, "fingerprints")
        with storage.ProjectStore.open_readonly(abs_path) as store:
            for rel in sorted(supported):
                abs_file = os.path.abspath(os.path.join(abs_path, rel))
                if not os.path.isfile(abs_file):
                    continue
                ranges = diffscan.changed_ranges(
                    abs_path, rel, base=base, staged=staged)
                for unit in _changed_units(abs_path, abs_file, ranges["added"]):
                    matches = _structural_matches(
                        store, unit, abs_file, abs_path, changed_abs)
                    if matches:
                        rebuilt.append({
                            "name": unit["name"], "kind": unit["kind"],
                            "path": rel, "line": unit["line"],
                            "size": unit.get("node_count"),
                            "matches": matches,
                        })
                for definition in _changed_definitions(store, abs_file, ranges["added"]):
                    changed_symbols.append((rel, definition["name"]))

    cochange_stats = _ensure_cochange(abs_path)
    companions: dict[str, dict] = {}
    if cochange_stats.get("available"):
        with storage.ProjectStore.open_readonly(abs_path) as store:
            for rel in sorted(changed):
                for rule in store.cochange_rules_for(
                        rel, min_support=cochange.min_support(),
                        min_confidence=cochange.min_confidence()):
                    companion = rule["companion"]
                    if companion in changed:
                        continue
                    entry = companions.get(companion)
                    if entry is None or rule["confidence"] > entry["confidence"]:
                        companions[companion] = {
                            "path": companion,
                            "confidence": round(rule["confidence"], 3),
                            "support": rule["support"], "changes": rule["changes"],
                            "because": rel,
                        }
    else:
        notes.append("Co-change is unavailable: "
                     + str(cochange_stats.get("reason", "unknown")))

    callers: list[dict] = []
    budget = _check_max_symbols()
    for rel, symbol in changed_symbols[:budget]:
        abs_file = os.path.abspath(os.path.join(abs_path, rel))
        _ensure_blast_radius(abs_path, abs_file, symbol, resolve=resolve,
                             defined_here=True)
        with storage.ProjectStore.open_readonly(abs_path) as store:
            dependents, _total = _read_blast_radius(store, abs_file, symbol)
        outside = [_repo_relative(abs_path, d) or d for d in dependents
                   if os.path.normcase(os.path.abspath(d)) not in changed_abs]
        if outside:
            callers.append({"symbol": symbol, "defined_in": rel,
                            "callers": outside, "count": len(outside)})
    if len(changed_symbols) > budget:
        notes.append(
            f"{len(changed_symbols)} symbols changed; callers were resolved for the "
            f"first {budget} (CODESEXTANT_CHECK_MAX_SYMBOLS).")

    dependents = _module_dependents_tier(
        abs_path, supported, changed, companions, callers, rebuilt, notes,
        skip=truncated_diff)

    if not rebuilt and not companions and not callers and not dependents:
        notes.append("Nothing found: no changed unit repeats a shape already in the "
                     "index, no companion this history considers reliable was left "
                     "out, no resolved caller sits outside the diff, and nothing "
                     "outside it imports what you changed. Each of the four is a "
                     "heuristic, so this is not a clean bill of health.")

    result = {
        "project_key": storage.project_key(abs_path),
        "changed_files": sorted(changed),
        "changed_count": len(changed),
        # Sorted by how much of the existing code the new unit repeats: the biggest
        # repeat is the one most worth not having written.
        "rebuilt": sorted(rebuilt, key=lambda r: -(r["size"] or 0)),
        "companions": sorted(companions.values(),
                             key=lambda c: (-c["confidence"], -c["support"])),
        "callers": sorted(callers, key=lambda c: -c["count"]),
        # A separate key, never folded into callers: importing a module is not calling
        # the function that changed, and merging the two is the confidence inflation
        # this tool exists to avoid.
        "dependents": dependents,
        "notes": notes,
        "approx_tokens": 0,
    }
    result["truncated_by_budget"] = False
    result["approx_tokens"] = _json_tokens(result)
    while result["approx_tokens"] > token_budget:
        if len(result["changed_files"]) > 5:
            result["changed_files"].pop()
        elif result["dependents"]:
            # The weakest claim in the answer goes first when the budget bites: an
            # unconfirmed dependent is worth less than a resolved caller or a companion
            # history vouches for.
            result["dependents"].pop()
        elif len(result["callers"]) > 2:
            result["callers"].pop()
        elif len(result["companions"]) > 3:
            result["companions"].pop()
        elif len(result["rebuilt"]) > 2:
            result["rebuilt"].pop()
        else:
            break
        result["truncated_by_budget"] = True
        result["approx_tokens"] = _json_tokens(result)
    return result


def _empty_check(abs_path: str, notes: list[str]) -> dict:
    result = {"project_key": storage.project_key(abs_path), "changed_files": [],
              "changed_count": 0, "rebuilt": [], "companions": [], "callers": [],
              "notes": notes, "approx_tokens": 0, "truncated_by_budget": False}
    result["approx_tokens"] = _json_tokens(result)
    return result


def _blast_radius_notes(symbol: str | None, dependents: list[str], leads: list[str],
                        total_edges: int, resolution: dict) -> list[str]:
    """Say which of the two empty answers this is, and where the full one is thin.

    "No callers" and "nobody has looked" print identically and mean opposite things.
    Most of what follows exists to keep them apart. The rest exists because import
    resolution has blind spots -- dynamic dispatch, re-exports, registries -- so even
    a non-empty answer can be missing a caller that the sweep can still see.
    """
    status = resolution["status"]
    lead_text = (f" {len(leads)} file(s) name it without resolving to it; they are "
                 "listed as leads, not callers." if leads else "")
    if dependents:
        if not leads:
            return []
        return [f"{len(leads)} further file(s) name {symbol!r} without resolving to it. "
                "That is usually a same-named symbol elsewhere, but it is also what a "
                "caller reached through dynamic dispatch, a re-export or a registry "
                "looks like, because no static resolver can follow those. They are "
                "listed as leads; check them by reading, not by trusting either list."]
    if status in ("resolved", "cached"):
        when = ("just now" if status == "resolved" else
                "earlier, and nothing that names it has changed since")
        return [f"Nothing in this project resolves to {symbol!r} here. That is a measured "
                f"absence, not an unasked question: references were resolved {when}."
                + lead_text]
    if status == "undefined-in-target":
        return [f"{symbol!r} is not defined in this file yet, so it has no callers to "
                "find. The blast radius describes code that already exists."]
    if status in ("declined", "unsupported", "off", "failed"):
        return [f"The blast radius was not resolved: {resolution['reason']}."
                + lead_text
                + " Run find_references on the symbol, or ask preflight again with "
                  "resolve=true, for the confirmed answer."]
    if status == "no-symbol":
        return ["No resolved caller reaches this file. Pass symbol= to have preflight "
                "resolve one symbol's callers rather than reading only what is stored."
                if total_edges else
                "No references have been resolved for this project yet, so this section "
                "is empty for lack of asking rather than lack of callers. Pass symbol= "
                "and preflight will resolve that one symbol."]
    return [f"No resolved caller reaches this file, out of {total_edges} resolved edges "
            "project-wide."]


def status(path: str, *, check_freshness: bool = False) -> dict:
    """A project's index status (for the /status endpoint and the panel).

    A project that has never been indexed returns indexed=False rather than raising, because a
    status query should be able to report "not indexed".
    Only check_freshness=True compares the git HEAD sha, which spawns a git subprocess. The
    default is False, so an unauthenticated GET /status cannot be turned into a git spawn
    storm by a malicious local web page using no-cors (pit7-1).
    """
    return project_state.status(
        path, check_freshness=check_freshness, git_head_reader=_git_head_sha
    )


def list_projects() -> dict:
    """List every project indexed on this machine (for the /projects endpoint and the panel).

    Scans each SQLite database in the database directory, looks up its repo_path and
    gathers statistics. It takes no project argument, because it is the data source for the
    panel's overview and complements the per-project endpoints.

    Returns {db_dir, count, projects:[...]}; count only counts databases that were read
    successfully, though broken ones are still listed with an error.
    """
    return project_state.list_projects()


# ── Dead-code clues: combine resolved references with dead-code helpers ──
def _orphans_for_file(root: str, scope_file: str, lang: str | None) -> list[dict]:
    """Judge orphan status for each top-level exportable symbol in scope_file, reusing
    find_references' real resolution.

    Check resolver availability before running
    find_references. If the engine is unavailable the whole symbol returns
    UNKNOWN_NO_RESOLVER and skip the high=0 decision. Otherwise, unavailable ts-morph
    could mark every export in a TypeScript project as unused.
    Only top-level symbols are considered (methods and nested definitions are not orphan
    candidates).
    """
    from . import deadcode  # Deferred to keep the engine-to-deadcode dependency acyclic.

    scope_abs = os.path.abspath(scope_file)
    file_lang = lang or symbols.language_for_file(scope_abs)
    ok, reason = deadcode.resolver_available(file_lang)
    try:
        with open(scope_abs, encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError:
        source = None

    syms = get_symbols(root, file=scope_abs).get("symbols", [])
    out: list[dict] = []
    pending: list[tuple[str, dict]] = []  # top-level symbols that are not entrypoints and still need real resolution
    for s in syms:
        if s.get("kind") not in _REFERENCEABLE_KINDS:
            continue
        if s.get("scope"):  # top level only (nested definitions and methods are not orphan candidates)
            continue
        name = s.get("name")
        entry, er = deadcode.is_entrypoint(scope_abs, symbol_name=name, source=source)
        if entry:
            out.append({**s, **deadcode.classify_orphan(None, is_entry=True, entry_reason=er)})
            continue
        if not ok:  # An unavailable resolver cannot support a high=0 decision.
            out.append({**s, "verdict": "UNKNOWN_NO_RESOLVER",
                        "icon": deadcode.verdict_icon("UNKNOWN_NO_RESOLVER"),
                        "reason": reason})
            continue
        pending.append((name, s))

    if pending and file_lang in ("typescript", "tsx", "javascript"):
        # For TS/JS, query every pending symbol in one batch. One Project loads
        # the project, then loops over the symbols), replacing the N-fold waste of spawning
        # node and reloading the project once per symbol (measured: 9 symbols took 32s, one
        # batch replaces it).
        names = [n for n, _ in pending]
        batch = references.ts_morph_references_batch(root, scope_abs, names)
        for name, s in pending:
            refs = batch.get(name) if batch else None  # a failed batch gives None, and classify safely returns UNKNOWN
            out.append({**s, **deadcode.classify_orphan(refs, is_entry=False, entry_reason=None)})
    else:
        # Python and everything else: jedi per symbol (74ms each, so batching is unnecessary).
        for name, s in pending:
            refs = find_references(root, name, def_path=scope_abs, src_root=root, persist=False)
            out.append({**s, **deadcode.classify_orphan(refs, is_entry=False, entry_reason=None)})
    return out


def find_deadcode(path: str, *, scope_file: str | None = None,
                  lang: str | None = None) -> dict:
    """Dead-code clue layer: unused imports (wrapping ruff/eslint) + orphan grading
    (reusing real resolution) + entrypoint exemptions.

    This function returns graded clues, not deletion decisions: LIKELY_UNUSED, UNKNOWN,
    PUBLIC_API, or KEEP. Review them and run
    build/CI before deleting anything. Reference results are not a substitute for compiling.
    When an engine or linter is unavailable, it returns UNKNOWN_* instead of a confident
    false positive.

    Parameters
    ----------
    path       : the project root (the root for the unused-import scan, and the jedi/ts-morph
                 resolution root for orphans).
    scope_file : orphan analysis only runs when this is given (resolving each top-level
                 symbol in that file for real; doing it symbol by symbol across a whole
                 project is too expensive, so this check requires a specific file).
    lang       : override language inference (by default it is inferred from scope_file's
                 extension, or from the project).

    Returns a dict (JSON-serializable): {root, scope_file, unused_imports, orphans, summary,
    verification_reminder}.
    A path that is not a directory raises NotADirectoryError.
    """
    from collections import Counter

    from . import deadcode

    if not os.path.isdir(path):
        raise NotADirectoryError(f"find_deadcode: '{path}' is not a valid directory")
    abs_path = os.path.abspath(path)
    target = os.path.abspath(scope_file) if scope_file else abs_path

    unused = deadcode.detect_unused_imports(target, root=abs_path, lang=lang)
    orphans = _orphans_for_file(abs_path, scope_file, lang) if scope_file else []

    vc: Counter[str] = Counter(o.get("verdict", "?") for o in orphans)
    return {
        "root": abs_path,
        "scope_file": os.path.abspath(scope_file) if scope_file else None,
        "unused_imports": unused,
        "orphans": orphans,
        "summary": {
            "unused_import_count": len(unused.get("findings", [])),
            "unused_import_available": unused.get("available", False),
            "orphan_verdicts": dict(vc),
            "likely_unused": vc.get("LIKELY_UNUSED", 0),
            "keep": vc.get("KEEP", 0),
            "public_api": vc.get("PUBLIC_API", 0),
            # Total UNKNOWNs (no resolver, plus definitions the resolver could not locate,
            # such as module-level variables).
            "unknown": (vc.get("UNKNOWN_NO_RESOLVER", 0) + vc.get("UNKNOWN_UNRESOLVED", 0)),
        },
        "verification_reminder": (
            "The dead-code layer produces clues carrying a safety grade, not deletion "
            "decisions: even LIKELY_UNUSED must be reviewed by a human and pass build/CI "
            "before deletion; UNKNOWN_* means the tool cannot decide, not that it is "
            "deletable. Reference lookup and unused detection are not the same as compiling."
        ),
        # Spell out blind spots where the source still needs inspection.
        # human has to read the code (tool silence does not mean deletable).
        "read_code_advisory": deadcode.read_code_advisory(unused, orphans),
    }


# ── ai-usage: which AI/LLM services this repo uses, plus the dispatch_policy compliance
# dimension (a pure scan; it does not need the index database) ──
def find_ai_usage(path: str, *, scope_file: str | None = None) -> dict:
    """Scan which AI/LLM services a repo uses, labelling each per dispatch_policy as one of
    three channels: cli (compliant), direct (violation) or local.

    A plain-text regex scans SUPPORTED_EXTENSIONS files line by line (reusing
    _iter_source_files, skipping noise directories) and does not need the SQLite index (a
    pure scan, like find_deadcode). Returns {meta, nodes, edges, stats, read_code_advisory,
    verification_reminder}; nodes and edges are what ai_usage_html renders as the HUD
    relationship graph.

    Name-level clues do not prove execution. Before treating a call as direct,
    violation), read the code and confirm it really hits a metered endpoint.
    A path that is not a directory raises NotADirectoryError.
    """
    from . import ai_usage
    if not os.path.isdir(path):
        raise NotADirectoryError(f"find_ai_usage: '{path}' is not a valid directory")
    abs_path = os.path.abspath(path)
    return ai_usage.scan_ai_usage(
        abs_path, _iter_source_files(abs_path),
        scope_file=os.path.abspath(scope_file) if scope_file else None)


# ── Unwired-symbol check using the name graph ──
def find_unwired(path: str, *, max_fanout: int | None = None) -> dict:
    """Unwired check: uses the name-level whole graph to quickly frame defined top-level
    symbols that have zero external references.

    This detects the root cause of code rot: a function, class, type or constant is defined,
    but nothing outside its own body ever mentions its name, which makes it a suspected
    unwired symbol. It works closely with namegraph, computing external usage from the same
    whole-graph name-level edges (body-aware: self-tokens on the definition line and
    recursive self-calls are excluded, while calls from elsewhere in the same file are kept,
    so a same-file helper is not misreported).

    This is a low-confidence clue layer, not a deletion decision:
      - The ceiling of name-level analysis: same-name interference causes **under-reports**
        (another definition of the same name being used elsewhere credits the genuinely
        unused one with references); dynamic, reflective and string-concatenated calls are
        invisible, causing **false positives**; and a **public API** imported from outside
        this repo but unused within it has exactly zero internal references, so it is
        misreported too (TS/JS `export` has no __all__ equivalent to exempt it, which makes
        this especially dangerous).
      - Exemptions: filename conventions, decorator entrypoints, Python __all__, dunders,
        and pyproject console_scripts entrypoints (reusing deadcode.is_entrypoint and
        entry_point_func_names). __all__ is Python-only; a TS/JS export public API has no
        equivalent exemption and will be misreported.
      - Flooded names with too many same-named definitions (> the fan-out cap) become
        UNKNOWN_FANOUT (no edges were built, so it cannot be judged, and it may in fact be
        heavily referenced).
      - variable/constant downgrade marker: name-level judgement is even less reliable for
        module-level variables (deadcode's real resolution marks them UNKNOWN_UNRESOLVED and
        does not call them deletable).
    Where it fits: one coarse sweep over the whole project, then run find_deadcode
    (jedi/ts-morph real resolution) against the candidates and pass build/CI before deleting.

    Parameters
    ----------
    max_fanout : the same-name fan-out cap (None takes env CODESEXTANT_NAMEGRAPH_MAX_FANOUT,
                 default 20).

    Returns a dict (JSON-serializable): {root, candidates, namegraph_meta, summary,
                          verification_reminder, read_code_advisory}.
    An unindexed project raises RuntimeError.
    """
    from . import deadcode

    if not os.path.isdir(path):
        raise NotADirectoryError(f"find_unwired: '{path}' is not a valid directory")
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"find_unwired: project has not been indexed yet (no {db_file}); call index_project first.")

    with storage.ProjectStore.open_readonly(abs_path) as store:
        syms = store.get_symbols()
        indexed = store.all_indexed_files()

    usage, over_fanout, ng_meta = namegraph.compute_external_usage(
        syms, indexed_files=indexed, max_fanout=max_fanout)
    # Exempt pyproject console_scripts entrypoints, which wrappers call reflectively and
    # the installed wrapper, and never mentioned in the source).
    entry_funcs = deadcode.entry_point_func_names(abs_path)

    _src_cache: dict[str, str] = {}

    def _src_of(p: str) -> str:
        if p not in _src_cache:
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    _src_cache[p] = f.read()
            except OSError:
                _src_cache[p] = ""
        return _src_cache[p]

    candidates: list[dict] = []
    scanned = exempt = unknown = 0
    for s in syms:
        if s.get("kind") not in _REFERENCEABLE_KINDS:
            continue
        if s.get("scope"):              # top level only (methods and nested definitions are not unwired candidates)
            continue
        scanned += 1
        name = s["name"]
        dp = namegraph._normp(s["path"])   # aligned (normcase) with compute_external_usage's usage key
        # Dunder names use mechanisms that name-level analysis cannot see, so exempt them.
        if name.startswith("__") and name.endswith("__"):
            exempt += 1
            continue
        # Exempt pyproject console_scripts entrypoints.
        if name in entry_funcs:
            exempt += 1
            continue
        is_entry, _reason = deadcode.is_entrypoint(dp, symbol_name=name, source=_src_of(dp))
        if is_entry:
            exempt += 1
            continue
        if name in over_fanout:
            unknown += 1
            candidates.append({**s, "verdict": "UNKNOWN_FANOUT",
                               "icon": deadcode.verdict_icon("UNKNOWN_NO_RESOLVER"),
                               "reason": ("too many same-named definitions (> the fan-out cap), so no "
                                          "name-level edges were built and references cannot be "
                                          "judged; it may in fact be heavily referenced, so check with "
                                          "real resolution")})
            continue
        if usage.get((dp, s["line"], name)) == 0:
            # Name-level confidence is lower for variables and
            # constants (deadcode's real resolution marks module-level variables
            # UNKNOWN_UNRESOLVED and does not call them deletable), so mark them as a
            # downgrade rather than giving them the same weight as function candidates.
            is_var = s.get("kind") == "variable"
            cand = {**s, "verdict": "UNWIRED_CANDIDATE", "icon": "🔸",
                    "reason": ("nothing outside this symbol's own body mentions its name anywhere in "
                               "the name-level whole graph (zero external references); suspected "
                               "written but never wired in"
                               if not is_var else
                               "module-level variable or constant with zero external references. "
                               "name-level judgement carries lower confidence here, and deadcode's "
                               "real resolution marks it UNKNOWN_UNRESOLVED rather than deletable; "
                               "read the code to confirm (it may be a configuration constant or "
                               "read reflectively)")}
            if is_var:
                cand["low_confidence_kind"] = True
            candidates.append(cand)

    likely = sum(1 for c in candidates if c["verdict"] == "UNWIRED_CANDIDATE")
    var_likely = sum(1 for c in candidates
                     if c["verdict"] == "UNWIRED_CANDIDATE" and c.get("low_confidence_kind"))
    advisory = []
    if likely:
        advisory.append(
            f"{likely} unwired candidate(s) are a clue, not a verdict; they may be newly written "
            "dead code that was never wired in, or they may be dynamic/reflective calls, a CLI or "
            "test entrypoint, or **a public API imported by downstream consumers outside this "
            "repo** (which naturally has no references inside it). Read each one, or cross-check "
            "with find_deadcode's real resolution, before deleting anything. Deleting an export "
            "by mistake is a breaking change for downstream users.")
    else:
        advisory.append("No top-level symbol had zero external references (everything shows signs of "
                        "being wired in at the name level). Under-reports are still possible, so "
                        "important symbols are still worth checking.")
    if var_likely:
        advisory.append(
            f"{var_likely} of those are module-level variables or constants (marked "
            "low_confidence_kind). Name-level analysis is least accurate for variables, and "
            "deadcode's real resolution marks them UNKNOWN rather than deletable. Do not delete "
            "configuration constants on this basis.")
    if unknown:
        advisory.append(
            f"{unknown} flooded same-name symbol(s) the tool cannot decide on (no edges were "
            "built). These are usually common names that are heavily referenced, and the tool's "
            "silence does not mean they are unwired.")
    if ng_meta.get("truncated"):
        advisory.append(
            f"Truncated: only {ng_meta.get('scanned_files')} of {ng_meta.get('total_files')} "
            "files were scanned (adjustable via env CODESEXTANT_NAMEGRAPH_MAX_FILES), so usage "
            "counts for later symbols are incomplete. Do not judge them unwired on this basis.")
    return {
        "root": abs_path,
        "candidates": candidates,
        "namegraph_meta": {
            "scanned_files": ng_meta.get("scanned_files"),
            "total_files": ng_meta.get("total_files"),
            "truncated": ng_meta.get("truncated"),
            "usage_targets": len(usage),
            "over_fanout_names": len(over_fanout),
        },
        "summary": {
            "top_level_referenceable_scanned": scanned,
            "unwired_candidates": likely,
            "unwired_variable_candidates": var_likely,
            "unknown_fanout": unknown,
            "exempt_entry_or_dunder": exempt,
        },
        "verification_reminder": (
            "The unwired check is a low-confidence, name-level coarse sweep: same-name "
            "interference causes under-reports, dynamic/reflective/string-concatenated calls are "
            "invisible and cause false positives, and a public API consumed by other repos but "
            "never imported within this one is misreported. Always cross-check candidates with "
            "find_deadcode (jedi/ts-morph real resolution) and pass build/CI before deleting. "
            "zero external references is not the same as confirmed deletable."),
        "read_code_advisory": advisory,
    }


# ── Comment queries ──
def _comment_coverage_kinds() -> set[str]:
    raw = os.environ.get("CODESEXTANT_COMMENT_COVERAGE_KINDS", "function,class,method,interface")
    return {k.strip() for k in raw.split(",") if k.strip()}


def _comment_skip_private() -> bool:
    return os.environ.get("CODESEXTANT_COMMENT_COVERAGE_SKIP_PRIVATE", "").lower() not in (
        "0", "false", "no", "off")


def _comment_density_enabled() -> bool:
    return os.environ.get("CODESEXTANT_COMMENT_DENSITY_DISABLED", "").lower() not in (
        "1", "true", "yes", "on")


def get_comment_overview(path: str, *, scope_file: str | None = None) -> dict:
    """Summarize repository comments: docstring coverage by kind,
    TODO/FIXME counts + density.

    Coverage is how many COVERAGE_KINDS symbols have a docstring. Symbols are matched to
    comments(is_doc=1) on (path, owner_line)==(path, line), which is more reliable than
    comparing scope strings (design FIX lens-4).
    SKIP_PRIVATE excludes names starting with `_` by default, so this measures public-surface
    coverage rather than every symbol. An unindexed project returns a note rather than
    pretending.
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {"project_key": storage.project_key(abs_path), "indexed": False,
                "note": f"project has not been indexed yet (no {db_file}); call index_project first."}
    target = os.path.abspath(scope_file) if scope_file else None
    kinds = _comment_coverage_kinds()
    skip_private = _comment_skip_private()
    # Coverage joins docstring owners across the project, so a subset would under-report.
    _materialize_derived(abs_path, "comments")

    with storage.ProjectStore.open_readonly(abs_path) as store:
        conn = store.conn
        sym_q = "SELECT path,name,kind,line,scope FROM symbols"
        sym_p: list = []
        if target:
            sym_q += " WHERE path=?"
            sym_p.append(target)
        syms = conn.execute(sym_q, sym_p).fetchall()
        doc_rows = conn.execute(
            "SELECT path, owner_line FROM comments WHERE is_doc=1 AND owner_line IS NOT NULL"
        ).fetchall()
        doc_set = {(r["path"], r["owner_line"]) for r in doc_rows}

        by_kind: dict[str, dict] = {}
        undocumented: list[dict] = []
        for s in syms:
            if s["kind"] not in kinds:
                continue
            if skip_private and (s["name"] or "").startswith("_"):
                continue
            bk = by_kind.setdefault(s["kind"], {"documented": 0, "total": 0})
            bk["total"] += 1
            if (s["path"], s["line"]) in doc_set:
                bk["documented"] += 1
            else:
                undocumented.append({"name": s["name"], "kind": s["kind"],
                                     "path": s["path"], "line": s["line"], "scope": s["scope"]})
        for bk in by_kind.values():
            bk["pct"] = round(100.0 * bk["documented"] / bk["total"], 1) if bk["total"] else 0.0
        tot_doc = sum(b["documented"] for b in by_kind.values())
        tot_all = sum(b["total"] for b in by_kind.values())
        overall_pct = round(100.0 * tot_doc / tot_all, 1) if tot_all else 0.0

        # Scan text line by line instead of grouping on the stored tag column.
        # GROUP BY on the comments.tag column. That column stores only the first marker per
        # comment, so a block with several markers undercounts and swallows the rest, which
        # contradicted find_comment_tags' numbers.
        from collections import Counter as _Counter
        tag_q = "SELECT line, text FROM comments WHERE tag IS NOT NULL"
        if target:
            tag_q += " AND path=?"
        _marker_re = comments._marker_re()
        _tagc: _Counter = _Counter()
        for tr in conn.execute(tag_q, ([target] if target else [])).fetchall():
            for t in comments.scan_tags_in_text(tr["text"], tr["line"], _marker_re):
                _tagc[t["tag"]] += 1
        tag_counts = dict(_tagc)

        density = None
        if _comment_density_enabled():
            cl_q = "SELECT COALESCE(SUM(end_line-line+1),0) AS n FROM comments"
            sl_q = "SELECT COALESCE(SUM(end_line-line+1),0) AS n FROM symbols WHERE scope=''"
            cl_p, sl_p = [], []
            if target:
                cl_q += " WHERE path=?"
                cl_p.append(target)
                sl_q += " AND path=?"
                sl_p.append(target)
            comment_lines = conn.execute(cl_q, cl_p).fetchone()["n"]
            code_lines = conn.execute(sl_q, sl_p).fetchone()["n"]
            denom = code_lines or 1
            density = {"comment_lines": comment_lines, "code_lines": code_lines,
                       "ratio": round(comment_lines / denom, 3),
                       "caveat": "Rough estimate: code_lines is the sum of top-level symbol line "
                                 "spans and does not subtract blank or comment lines; density says "
                                 "nothing about comment quality"}

    undocumented.sort(key=lambda u: (u["path"], u["line"]))
    return {
        "project_key": store.project_key, "indexed": True,
        "scope_file": target,
        "docstring_coverage": {"by_kind": by_kind, "overall_pct": overall_pct,
                               "counted_kinds": sorted(kinds), "skip_private": skip_private},
        "tag_counts": tag_counts,
        "density": density,
        "top_undocumented": undocumented[:30],
        "caveat": ("Coverage and density are static structural statistics, not semantic ones: high "
                   "coverage does not mean the comments are correct or up to date. Docstring "
                   "detection is limited to the first string in a block or module (Python); other "
                   "languages rely on proximity and may not line up exactly."),
    }


def find_comment_tags(path: str, *, tags: list[str] | None = None,
                      scope_file: str | None = None) -> dict:
    """Index TODO and FIXME markers with their source lines.

    Scans markers line by line and
    returns the **real source line**, including multi-line block and doc comments.

    For block and doc comments, a marker's line number is computed exactly by
    scan_tags_in_text (base_line + offset), not taken from the comment's opening line.
    Passing tags returns only those markers.
    Returns {findings:[{tag,path,line,scope,text}], count_by_tag}.
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {"indexed": False, "findings": [], "count_by_tag": {},
                "note": f"project has not been indexed yet (no {db_file}); call index_project first."}
    target = os.path.abspath(scope_file) if scope_file else None
    want = {t.upper() for t in tags} if tags else None
    marker_re = comments._marker_re()
    _materialize_derived(abs_path, "comments",
                         paths=[target] if target else None)

    with storage.ProjectStore.open_readonly(abs_path) as store:
        q = "SELECT path,line,scope,text FROM comments WHERE tag IS NOT NULL"
        p: list = []
        if target:
            q += " AND path=?"
            p.append(target)
        rows = store.conn.execute(q, p).fetchall()

    findings: list[dict] = []
    for r in rows:
        for t in comments.scan_tags_in_text(r["text"], r["line"], marker_re):
            if want and t["tag"].upper() not in want:
                continue
            findings.append({"tag": t["tag"], "path": r["path"], "line": t["line"],
                             "scope": r["scope"], "text": t["text"]})
    findings.sort(key=lambda f: (f["path"], f["line"]))
    from collections import Counter
    count_by_tag = dict(Counter(f["tag"] for f in findings))
    return {"indexed": True, "scope_file": target, "findings": findings,
            "count_by_tag": count_by_tag,
            "verification_reminder": "Only standard markers the tool scanned for are listed; "
                                     "dynamically generated or non-standard markers are not found."}


def get_comments(path: str, file: str | None = None, *, scope: str | None = None,
                 doc_only: bool = False, tag: str | None = None) -> dict:
    """Retrieve comments with precise filters, mirroring get_symbols.

    An unindexed project returns count=0 with an explanatory note.
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {"project_key": storage.project_key(abs_path), "count": 0, "comments": [],
                "note": f"project has not been indexed yet (no {db_file}); call index_project first."}
    target = os.path.abspath(file) if file else None
    _materialize_derived(abs_path, "comments", paths=[target] if target else None)
    with storage.ProjectStore.open_readonly(abs_path) as store:
        q = ("SELECT path,line,end_line,kind,is_doc,tag,scope,owner_line,text "
             "FROM comments WHERE 1=1")
        p: list = []
        if target:
            q += " AND path=?"
            p.append(target)
        if doc_only:
            q += " AND is_doc=1"
        if tag:
            q += " AND tag=?"
            p.append(tag.upper())
        if scope is not None:
            q += " AND scope=?"
            p.append(scope)
        q += " ORDER BY path,line"
        rows = [dict(r) for r in store.conn.execute(q, p).fetchall()]
        return {"project_key": store.project_key, "file": target,
                "count": len(rows), "comments": rows}


# ── Duplicate and near-duplicate detection ──
_DUP_VERDICT_ICON = {
    "EXACT_DUP": "🟥", "RENAMED_DUP": "🟧", "STRUCTURAL_NEAR": "🟨",
    "CALL_PATTERN_SIM": "🟦", "BOILERPLATE_SUPPRESSED": "⚪", "UNKNOWN_TOO_SMALL": "❔",
}


def _make_dup_group(verdict: str, members: list[dict], similarity, reason: str) -> dict:
    """Assemble a compact duplicate group without embedding source text."""
    return {
        "verdict": verdict, "icon": _DUP_VERDICT_ICON[verdict], "similarity": similarity,
        "members": [{"path": m["path"], "line": m["line"], "end_line": m.get("end_line"),
                     "name": m.get("name"), "scope": m.get("scope")} for m in members],
        "representative": members[0].get("name"),
        "node_count": members[0].get("node_count"),
        "reason": reason,
    }


def get_health(path: str) -> dict:
    """Return per-symbol code health and unwired evidence.

    Health combines bloat, cognitive complexity, and duplication into a value in
    [0, 1]. Low health is an inspection clue, not a deletion decision. The ``dead``
    field records separate unwired evidence. Visual mapping belongs to the presentation
    layer; this API returns numbers only.
    UNKNOWN / N-A dimensions (classes and variables have no fingerprint; cognitive complexity
    is unavailable outside high-confidence languages) are excluded and the remaining weights
    renormalized, so nothing is inflated to a perfect score.

    Returns a dict (JSON-serializable): {root, symbols:[{path,name,line,kind,health,dead}],
                          summary:{n_nodes,n_covered,coverage,n_dead,clone_pairs}}.
    An unindexed project raises RuntimeError, as get_map does.
    """
    from collections import Counter

    from . import health as _health
    if not os.path.isdir(path):
        raise NotADirectoryError(f"get_health: '{path}' is not a valid directory")
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(f"get_health: project has not been indexed yet (no {db_file}); call index_project first.")

    _materialize_derived(abs_path, "fingerprints")

    with storage.ProjectStore.open_readonly(abs_path) as store:
        syms = store.get_symbols()
        fps = store.conn.execute(
            "SELECT path,line,node_count,shape_hash,cognitive FROM fingerprints").fetchall()
    shape_cnt = Counter(r["shape_hash"] for r in fps)
    fp_by = {(os.path.normcase(r["path"]), int(r["line"])):
             (int(r["node_count"] or 0), r["shape_hash"], r["cognitive"]) for r in fps}
    try:   # Unwired analysis is optional and must not break health scoring.
        uw = find_unwired(abs_path)
        dead_keys = {(os.path.normcase(os.path.abspath(c["path"])), int(c["line"]))
                     for c in uw.get("candidates", []) if c.get("verdict") == "UNWIRED_CANDIDATE"}
    except Exception as exc:  # noqa: BLE001
        print(f"  Warning: get_health could not compute unwired symbols: {exc}", file=sys.stderr)
        dead_keys = set()

    nodes = [{"path": s["path"], "name": s["name"], "line": s["line"], "kind": s.get("kind", "")}
             for s in syms]
    summary = _health.annotate(
        nodes, fp_by, shape_cnt, dead_keys,
        key_of=lambda n: (os.path.normcase(n["path"]), int(n["line"])))
    return {"root": abs_path, "symbols": nodes, "summary": summary}


def _merge_summary(summary: dict, delta: dict) -> None:
    """Merge one stage's reported count deltas back into the totals (each stage reports only
    what it counted and never touches another stage's fields)."""
    for key, value in delta.items():
        summary[key] = summary.get(key, 0) + value


def _dup_stage1_one_shape(members: list, *, min_node: int, in_scope) -> tuple[list, dict, set]:
    """Build duplicate groups and summary deltas for one shape hash.

    Within the group, a second clustering pass on raw_token splits it further: verbatim
    matches each become an EXACT_DUP, and representatives across clusters form a RENAMED_DUP
    so exact and renamed matches can coexist.
    """
    if len(members) < 2:
        return [], {}, set()
    # Structural significance requires control flow and a minimum node count. Do not
    # add an nstmts threshold: Go's body=block>statement_list adds a level, and a single
    # large switch/if dispatch has top-level nstmts=1 and would be killed off wrongly.
    # node_count is the better complexity indicator and matches the winnow gate.
    sig = [m for m in members if m["has_control_flow"] and m["node_count"] >= min_node]
    if len(sig) < 2:
        # Same shape, but all boilerplate or too small → suppress (counted only within
        # scope, otherwise the numbers inflate).
        return [], ({"boilerplate_suppressed_groups": 1} if in_scope(members) else {}), set()

    from collections import defaultdict
    by_raw: dict[str, list] = defaultdict(list)
    for m in sig:
        by_raw[m["raw_token_hash"]].append(m)

    groups: list[dict] = []
    delta: dict = {}
    keys: set = set()
    reps: list[dict] = []   # cross-raw representatives (the first of each raw sub-cluster), for the RENAMED group
    for cluster in by_raw.values():
        cluster.sort(key=lambda m: (m["path"], m["line"]))
        if len(cluster) >= 2 and in_scope(cluster):
            groups.append(_make_dup_group(
                "EXACT_DUP", cluster, 1.0,
                "Verbatim match (identical shape and raw_token). Identical structure does not "
                "mean identical semantics; read the code and run CI before merging."))
            delta["exact"] = delta.get("exact", 0) + 1
            keys.update((m["path"], m["line"]) for m in cluster)
        reps.append(cluster[0])

    if len(by_raw) > 1 and len(reps) >= 2:   # renamed variants exist → RENAMED (cross-raw representatives)
        reps.sort(key=lambda m: (m["path"], m["line"]))
        if in_scope(reps):
            groups.append(_make_dup_group(
                "RENAMED_DUP", reps, None,
                f"Identical structure with different identifiers or constants ({len(by_raw)} "
                "variants). These may just be the same kind of boilerplate, so read what they mean "
                "in context before merging."))
            delta["renamed"] = delta.get("renamed", 0) + 1
            keys.update((m["path"], m["line"]) for m in reps)
    return groups, delta, keys


def _dup_stage1(rows: list, *, min_node: int, in_scope) -> tuple[list, dict, set]:
    """Stage 1: group by shape_hash → EXACT_DUP (verbatim) / RENAMED_DUP (same shape, renamed).

    Always run against the whole repository's fingerprints without a
    scope filter. Otherwise scope_file mode degrades into comparing within a single file,
    every cross-file verbatim duplicate is missed, and the confidence ordering inverts. Scope
    only decides **which groups are output**; detection always spans the whole repo.
    """
    from collections import defaultdict
    by_shape: dict[str, list] = defaultdict(list)
    for r in rows:
        by_shape[r["shape_hash"]].append(r)

    groups: list[dict] = []
    delta: dict = {}
    member_key: set = set()
    for members in by_shape.values():
        g, d, keys = _dup_stage1_one_shape(members, min_node=min_node, in_scope=in_scope)
        groups.extend(g)
        _merge_summary(delta, d)
        member_key |= keys
    return groups, delta, member_key


def _dup_flood_fingerprints(conn, df_cap: int) -> set:
    """Gate 1: drop flooded fingerprints that appear everywhere.

    Count the true document frequency with
    DISTINCT(path,line,fp_value), meaning how many different functions it appears in, not
    fingerprint_index's total row count. Otherwise a fingerprint repeating inside a single
    function blows past df_cap on its own and the genuine fingerprints get dropped.
    """
    return {r[0] for r in conn.execute(
        "SELECT fp_value FROM (SELECT DISTINCT path,line,fp_value FROM fingerprint_index) "
        "GROUP BY fp_value HAVING COUNT(*)>?", (df_cap,)).fetchall()}


def _dup_load_fingerprint_rows(conn, target: str | None, flood: set) -> list:
    """Load the fingerprint rows to compare.

    In scope_file mode, load only units whose fingerprints intersect
    the target file's rather than the whole table, which decouples the cost of checking one
    file from the size of the entire repo. Only near_global loads everything.
    """
    if not target:
        return conn.execute("SELECT path,line,fp_value FROM fingerprint_index").fetchall()
    seed = {r[0] for r in conn.execute(
        "SELECT DISTINCT fp_value FROM fingerprint_index WHERE path=?", (target,)
    ).fetchall()} - flood
    rows_fp: list = []
    seed_list = list(seed)
    for i in range(0, len(seed_list), 900):   # batch the queries to stay under SQLite's IN-clause limit
        chunk = seed_list[i:i + 900]
        ph = ",".join("?" * len(chunk))
        rows_fp.extend(conn.execute(
            f"SELECT path,line,fp_value FROM fingerprint_index WHERE fp_value IN ({ph})",
            tuple(chunk)).fetchall())
    return rows_fp


def _dup_stage2_pair(ka, kb, shared, *, body_fps, meta, member_key, seen_pairs,
                     in_scope, min_shared: int, sim_thresh: float) -> dict | None:
    """One candidate pair passing the gates → a STRUCTURAL_NEAR group; None if it does not."""
    if shared < min_shared:                     # Gate 2: candidate threshold on shared fingerprint count
        return None
    pair = tuple(sorted([ka, kb]))
    if pair in seen_pairs:
        return None
    seen_pairs.add(pair)
    if pair[0] in member_key and pair[1] in member_key:
        return None                             # already grouped together in stage 1; do not report twice
    union = len(body_fps[ka] | body_fps[kb])
    sim = shared / union if union else 0.0
    if sim < sim_thresh:                        # Gate 3: exact Jaccard similarity threshold
        return None
    ma, mb = meta.get(pair[0]), meta.get(pair[1])
    if not ma or not mb:
        return None
    # Identical shapes belong to the exact or renamed groups, so this stage reports
    # only non-identical near matches. Otherwise you get the self-contradictory result of a
    # STRUCTURAL_NEAR group with similarity 1.0.
    if ma["shape_hash"] == mb["shape_hash"]:
        return None
    if not in_scope([ma, mb]):
        return None
    pair_members = sorted([ma, mb], key=lambda m: (m["path"], m["line"]))
    return _make_dup_group(
        "STRUCTURAL_NEAR", pair_members, round(sim, 3),
        f"Winnowing similarity {round(sim, 3)} (neither verbatim nor identical in shape); read "
        "the code to confirm whether this is really duplication.")


def _dup_stage2(conn, *, target, meta, member_key, in_scope,
                df_cap: int, min_shared: int, sim_thresh: float) -> tuple[list, dict]:
    """Stage 2/3: winnowing near-duplicate comparison (three gates: flooded fingerprints →
    shared count → Jaccard threshold)."""
    from collections import defaultdict
    flood = _dup_flood_fingerprints(conn, df_cap)
    rows_fp = _dup_load_fingerprint_rows(conn, target, flood)

    body_fps: dict[tuple, set] = defaultdict(set)
    for r in rows_fp:
        if r["fp_value"] not in flood:
            body_fps[(r["path"], r["line"])].add(r["fp_value"])
    inv: dict[int, list] = defaultdict(list)
    for k, fps in body_fps.items():
        for v in fps:
            inv[v].append(k)

    groups: list[dict] = []
    delta: dict = {}
    seen_pairs: set = set()
    scope_keys = [k for k in body_fps if (not target or k[0] == target)]
    for ka in scope_keys:
        cand: dict[tuple, int] = defaultdict(int)
        for v in body_fps[ka]:
            for kb in inv[v]:
                if kb != ka:
                    cand[kb] += 1
        for kb, shared in cand.items():
            group = _dup_stage2_pair(
                ka, kb, shared, body_fps=body_fps, meta=meta, member_key=member_key,
                seen_pairs=seen_pairs, in_scope=in_scope,
                min_shared=min_shared, sim_thresh=sim_thresh)
            if group is not None:
                groups.append(group)
                delta["structural_near"] = delta.get("structural_near", 0) + 1
    return groups, delta


def _dup_stage_call_pattern(rows: list, *, min_node: int, in_scope) -> tuple[list, dict]:
    """call_pattern (opt-in, lowest confidence 🟦): reported only when the set of called names
    matches but the structure differs."""
    from collections import defaultdict
    by_call: dict[str, list] = defaultdict(list)
    for r in rows:
        if r["call_hash"] and r["has_control_flow"] and r["node_count"] >= min_node:
            by_call[r["call_hash"]].append(r)

    groups: list[dict] = []
    delta: dict = {}
    for members in by_call.values():
        shapes = {m["shape_hash"] for m in members}
        if len(members) < 2 or len(shapes) == 1:
            continue   # same calls and same shape is already covered by stage 1; only a differing shape is an orthogonal clue
        if not in_scope(members):
            continue
        members.sort(key=lambda m: (m["path"], m["line"]))
        groups.append(_make_dup_group(
            "CALL_PATTERN_SIM", members, None,
            "Identical set of called names but different structure (an orthogonal clue, lowest "
            "confidence); they may simply happen to use the same helpers, so read the code."))
        delta["call_pattern"] = delta.get("call_pattern", 0) + 1
    return groups, delta


def _dup_advisory(summary: dict, target: str | None) -> list[str]:
    """Turn duplicate counts into inspection advice without making merge decisions."""
    advisory: list[str] = []
    if summary["exact"]:
        advisory.append(f"{summary['exact']} group(s) match verbatim (high-confidence Type-1), but they "
                        "may still be the same boilerplate legitimately repeated across modules. "
                        "🟥 This says they are identical, not that they should be merged.")
    if summary["renamed"] + summary["structural_near"]:
        advisory.append(f"{summary['renamed'] + summary['structural_near']} group(s) are renamed or "
                        "near matches. Looking alike is not the same as meaning the same (two "
                        "identical-looking if-return blocks can be entirely unrelated). Read the "
                        "code to decide whether they really duplicate each other.")
    if not summary["stage2_ran"]:
        advisory.append("Global near-duplicate detection (stage 2/3) did not run, so only verbatim "
                        "and same-shape duplicates are reported. To find Type-3 near duplicates, "
                        "pass scope_file or near_global.")
    if target:
        advisory.append("Scope mode: stage 1 (verbatim and same-shape) still detects across the "
                        "whole repo and only outputs groups containing a member from this file; "
                        "stage 2 near-duplicate detection only compares units whose fingerprints "
                        "intersect this file's. total_units_scanned is the whole-repo count.")
    if not advisory:
        advisory.append("No structurally identical groups were found at the name and structure "
                        "level; this analysis cannot detect Type-4 semantic clones.")
    return advisory


def find_duplicates(path: str, *, scope_file: str | None = None, near_global: bool = False,
                    min_similarity: float | None = None,
                    include_call_pattern: bool = False) -> dict:
    """Find duplicate and near-duplicate units by structural fingerprint.

    Without a scope, only the O(n) first stage runs by default. Global near-duplicate
    stages 2 and 3 must be enabled explicitly:
      Stage 1: GROUP BY shape_hash → EXACT_DUP (raw_token matches too, so verbatim) /
               RENAMED_DUP (same shape, renamed). A structural-significance hard gate
               (control flow required, plus sufficient node_count/nstmts) stops the flood of
               getter and __init__ false positives.
      Stage 2/3 (only with scope_file or near_global): winnowing inverted index + DF-cap,
               through three gates → STRUCTURAL_NEAR.
      call_pattern (only with include_call_pattern, lowest confidence 🟦): matching call_hash
               with a different structure.

    It never emits a "should be deleted / should be merged" decision. Identical structure
    is not identical semantics, so read the
    code and run CI before merging.

    Parameters
    ----------
    scope_file : restrict to this file (stages 2/3 run only here by default).
    near_global : opt into global stage 2/3 near-duplicate comparison (can be slow on a large
                  repo; DF-cap stops it from exploding).
    min_similarity : override the STRUCTURAL_NEAR threshold (None takes env, default 0.8).
    include_call_pattern : enable the CALL_PATTERN_SIM layer (highest false-positive rate, off
                  by default).

    Returns a dict: {root, scope_file, groups, summary, verification_reminder,
    read_code_advisory}. An unindexed project raises RuntimeError.
    """
    if not os.path.isdir(path):
        raise NotADirectoryError(f"find_duplicates: '{path}' is not a valid directory")
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"find_duplicates: project has not been indexed yet (no {db_file}); call index_project first.")

    # Detection spans the whole repository even when scope_file limits what is reported,
    # so every file's fingerprints have to exist before the first query runs.
    _materialize_derived(abs_path, "fingerprints")

    min_node = clones._env_int("CODESEXTANT_DEDUP_MIN_NODE_COUNT", 15)
    sim_thresh = (min_similarity if min_similarity is not None
                  else clones._env_float("CODESEXTANT_DEDUP_SIMILARITY_THRESHOLD", 0.8))
    sim_thresh = max(0.0, min(1.0, sim_thresh))   # Clamp to preserve threshold semantics.
    df_cap = clones._env_int("CODESEXTANT_DEDUP_FP_DF_CAP", 50)
    min_shared = clones._env_int("CODESEXTANT_DEDUP_MIN_SHARED_FP", 3)
    near_global = near_global or clones._env_on("CODESEXTANT_DEDUP_NEAR_GLOBAL")
    include_call_pattern = include_call_pattern or clones._env_on(
        "CODESEXTANT_DEDUP_INCLUDE_CALL_PATTERN")
    target = os.path.abspath(scope_file) if scope_file else None

    groups: list[dict] = []
    summary = {"exact": 0, "renamed": 0, "structural_near": 0, "call_pattern": 0,
               "boilerplate_suppressed_groups": 0, "total_units_scanned": 0,
               "stage2_ran": bool(target) or near_global}

    with storage.ProjectStore.open_readonly(abs_path) as store:
        conn = store.conn
        # Exact and renamed grouping always runs against the whole repository's
        # fingerprints with no WHERE path filter. Otherwise scope_file mode turns stage 1
        # into intra-file-only, cross-file verbatim duplicates are missed and the confidence
        # ordering inverts. scope_file is used solely to filter which groups are output:
        # detection still spans files, but only groups containing a member from that file are
        # reported.
        rows = [dict(r) for r in conn.execute(
            "SELECT path,name,kind,line,end_line,scope,shape_hash,raw_token_hash,call_hash,"
            "node_count,nstmts,has_control_flow FROM fingerprints").fetchall()]
        summary["total_units_scanned"] = len(rows)   # whole-repo unit count (stage 1 compares globally)
        meta = {(m["path"], m["line"]): m for m in rows}
        member_key: set = set()   # (path,line) already grouped by stage 1 EXACT/RENAMED; later stages do not repeat them

        def _in_scope(members) -> bool:
            """In scope_file mode, a group is output only if it contains at least one member
            from the target file (None means no restriction: output everything)."""
            return (not target) or any(os.path.abspath(m["path"]) == target for m in members)

        stage_groups, delta, member_key = _dup_stage1(
            rows, min_node=min_node, in_scope=_in_scope)
        groups.extend(stage_groups)
        _merge_summary(summary, delta)

        if summary["stage2_ran"]:
            stage_groups, delta = _dup_stage2(
                conn, target=target, meta=meta, member_key=member_key, in_scope=_in_scope,
                df_cap=df_cap, min_shared=min_shared, sim_thresh=sim_thresh)
            groups.extend(stage_groups)
            _merge_summary(summary, delta)

        if include_call_pattern:
            stage_groups, delta = _dup_stage_call_pattern(
                rows, min_node=min_node, in_scope=_in_scope)
            groups.extend(stage_groups)
            _merge_summary(summary, delta)

    summary["high_conf_typed_count"] = summary["exact"]
    summary["needs_human_judge_count"] = summary["renamed"] + summary["structural_near"] \
        + summary["call_pattern"]
    advisory = _dup_advisory(summary, target)
    return {
        "root": abs_path, "scope_file": target, "groups": groups, "summary": summary,
        "verification_reminder": (
            "Duplicate detection is a structural and lexical clue, not a semantic one: identical "
            "structure is not identical semantics, Type-4 semantic clones are invisible, and "
            "duplication produced dynamically, reflectively or by code generation is invisible "
            "too. The tool never says something should be deleted or merged; read the code "
            "yourself and pass build/CI before merging."),
        "read_code_advisory": advisory,
    }
