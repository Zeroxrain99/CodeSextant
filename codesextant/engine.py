"""Engine facade: coordinates the symbols / references / storage / ranking modules.

This is C1's public "pure engine API", and the layer the C2 daemon wraps as HTTP.
Design rules (which keep C2 simple):
  - Every public function's arguments and return values use simple serializable types
    (str/int/dict/list), so they pass straight through json.dumps and the HTTP daemon
    needs almost no conversion.
  - One HTTP endpoint per function:
        /reindex  ← index_project(path)
        /get_symbols ← get_symbols(path, file)
        /find_references ← find_references(path, symbol, ...)
        /get_map ← get_map(path, token_budget)
        /status ← status(path)
  - Fail loudly: a missing path or an unindexed project raises, rather than silently
    returning None or an empty result.

Hybrid architecture (proved out by the PoC):
  - index_project: tree-sitter extracts every symbol (fast) and does not run jedi.
  - find_references: runs jedi's two-stage resolution only on demand.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from collections import OrderedDict
from copy import deepcopy
from threading import RLock, Thread

from . import clones, comments, namegraph, references, storage, symbols
from .ranking import rank_symbols
from .symbols import SUPPORTED_EXTENSIONS

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
_MAP_CACHE_ENV = (
    "CODESEXTANT_NAMEGRAPH_DISABLED", "CODESEXTANT_NAMEGRAPH_MAX_FANOUT",
    "CODESEXTANT_NAMEGRAPH_MAX_FILES", "CODESEXTANT_NAMEGRAPH_MAP_WORK_BUDGET",
    "CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES", "CODESEXTANT_RANK_PRIVATE_MULT",
    "CODESEXTANT_RANK_WELLNAMED_MINLEN", "CODESEXTANT_RANK_WELLNAMED_MULT",
    "CODESEXTANT_RANK_COMMON_THRESHOLD", "CODESEXTANT_RANK_COMMON_MULT",
    "CODESEXTANT_PAGERANK_FOCUS_BOOST",
)


def _schedule_symbol_snapshot(db_file, revision: tuple, symbols: list[dict]) -> None:
    """Write the snapshot lazily, off the response path; one writer per revision per process."""
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
            print(f"  ⚠ failed to write symbols snapshot: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
        finally:
            with _MAP_CACHE_LOCK:
                _SYMBOL_SNAPSHOT_INFLIGHT.discard(key)

    Thread(target=worker, name="codesextant-symbol-snapshot", daemon=True).start()

# The kinds of definition treated as referenceable when finding references. variable is
# included because TS/JS exported consts, arrow functions and const objects are all
# first-class reference targets (C5b found in practice that excluding variable leaves a TS
# const with no candidate definition → def_path=None → it wrongly takes the jedi dead end
# and reports high=0, which is the common case behind review issue 4).
_REFERENCEABLE_KINDS = {"function", "class", "method", "interface", "type",
                        "enum", "struct", "trait", "variable",
                        # Symbol kinds added with the 2026-06-22 batch of mainstream languages:
                        "constructor",   # C#/Java/Swift constructors
                        "property",      # C#/Swift properties
                        "module",        # Ruby module
                        "protocol"}      # Swift protocol


def _iter_source_files(root: str):
    """Scan every source file in a supported language under root (C5: multi-language;
    noise directories are skipped)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in SUPPORTED_EXTENSIONS:
                yield os.path.join(dirpath, fn)


def _env_on(name: str) -> bool:
    """Parse an env flag (always via .lower(), so =True/=TRUE are not read as unset)."""
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def _infer_project_language(root: str, *, sample_cap: int | None = None) -> str | None:
    """Pitfall 9: when finding references turns up no candidate definition for a symbol
    (def_path=None) and jedi cannot locate the definition either, sample the project's
    dominant language as a **fallback** (not an override; see find_references), so a
    non-Python symbol does not get stuck on the name-matching dead end.

    Returns a language only when its share is at or above the threshold; a tie or a mixed
    project deliberately does not force a choice and returns None, which falls back to the
    conservative jedi path and costs the least when wrong. Undecidable also returns None.
    Switches (L0 hard rule #6, all tolerant via .lower()):
      - CODESEXTANT_INFER_LANG_DISABLED=1/true/yes/on → return None (disabled).
      - CODESEXTANT_INFER_LANG_SAMPLE_CAP=<int> → sampling cap (default 1000; <=0 means
        scan everything without truncating).
      - CODESEXTANT_INFER_LANG_MIN_RATIO=<float> → dominant-share threshold (default 0.6).
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
    # Dominant share below the threshold (mixed or tied) → return None and take the
    # conservative jedi path: deterministic, and the cheapest outcome when wrong.
    if top_n / total < min_ratio:
        return None
    return top_lang


def _git_head_sha(repo_path: str) -> str | None:
    """Pitfall 6: read the repo's git HEAD sha (used for freshness comparison). Not a git
    repo, git unavailable, or the switch turned off → None. Does not flash a console window
    under a detached Windows daemon (CREATE_NO_WINDOW).
    Switch (L0 hard rule #6, tolerant via .lower()):
    CODESEXTANT_GIT_FRESHNESS_DISABLED=1/true/yes/on → None.
    """
    if _env_on("CODESEXTANT_GIT_FRESHNESS_DISABLED"):
        return None
    try:
        import subprocess
        kwargs = {"capture_output": True, "text": True, "timeout": 5}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW (no console flash when detached)
        out = subprocess.run(["git", "-C", repo_path, "rev-parse", "HEAD"], **kwargs)
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception:
        pass
    return None


def index_project(path: str, *, force: bool = False) -> dict:
    """Build (or incrementally update) a project's index.

    tree-sitter extracts every symbol, and a content hash drives the incremental pass:
    only files whose hash changed are recomputed.
    ⛔ This step does not run jedi (running it over everything is far too slow); reference
    resolution is left to find_references, on demand.

    Parameters
    ----------
    path  : the project root (absolute or relative; it is normalized internally).
    force : True ignores hashes and recomputes everything (for debugging or rebuilding).

    Returns a dict (JSON-serializable):
      {indexed, skipped, removed, errors, total_files, elapsed_sec,
       project_key, db_file, symbols_total}
    A path that is not a directory → NotADirectoryError (fail loudly).
    """
    if not os.path.isdir(path):
        raise NotADirectoryError(f"index_project: '{path}' is not a valid directory")

    abs_path = os.path.abspath(path)
    t0 = time.perf_counter()
    indexed = skipped = errors = 0
    error_files: list[dict] = []

    with storage.ProjectStore.open(abs_path) as store:
        seen_files: set[str] = set()
        for fp in _iter_source_files(abs_path):
            seen_files.add(fp)
            # Red team L4-MEDIUM: read each file's bytes once (content_hash is computed
            # from those bytes too), which removes the previous 4 disk reads per file.
            try:
                with open(fp, "rb") as _f:
                    source = _f.read()
            except OSError as exc:
                errors += 1
                error_files.append({"path": fp, "error": f"failed to read file: {exc}"})
                continue
            h = hashlib.sha256(source).hexdigest()

            if not force and not store.needs_reindex(fp, h):
                skipped += 1
                continue

            try:
                # Red team L4-MEDIUM: parse each file once and share the tree across
                # symbols/comments/fingerprints, avoiding repeated parses.
                lang = symbols.language_for_file(fp)
                tree = symbols.parse_source(source, lang) if lang else None
                syms = (symbols.extract_symbols_from_source(source, lang, file_path=fp, tree=tree)
                        if lang else [])
                store.store_file_symbols(fp, h, syms, indexed_at=time.time())
                indexed += 1
                # Feature B: extract and persist comments (sharing the tree). A comment
                # failure must not break indexing. The symbols are already persisted and
                # the next reindex will fill the gap.
                if lang and comments.comments_enabled():
                    try:
                        store.store_file_comments(fp, comments.extract_comments_from_source(
                            source, lang, file_path=fp, tree=tree))
                    except Exception as exc:  # do not break indexing, but log to stderr rather than swallowing it (observability)
                        print(f"  ⚠ comment extraction failed ({fp}): {type(exc).__name__}: {exc}",
                              file=sys.stderr)
                # Feature B: extract structural fingerprints + the winnowing inverted index
                # and persist them (sharing the tree; a failure must not break indexing).
                if lang and clones.dedup_enabled():
                    try:
                        fps = clones.extract_fingerprints_from_source(
                            source, lang, file_path=fp, tree=tree)
                        winnow_idx = [{"line": f["line"], "fp_value": v}
                                      for f in fps for v in f.get("winnow", [])]
                        store.store_file_fingerprints(fp, fps, winnow_idx)
                    except Exception as exc:  # do not break indexing, but log to stderr rather than swallowing it (adversarial review CRITICAL #2③)
                        print(f"  ⚠ fingerprint/complexity extraction failed ({fp}): {type(exc).__name__}: {exc}",
                              file=sys.stderr)
            except Exception as exc:  # one file failing to parse must not break the whole index, but it must be recorded, not swallowed
                errors += 1
                error_files.append({"path": fp, "error": f"{type(exc).__name__}: {exc}"})

        # Handle files that have disappeared from disk (remove them from the index, so it
        # stays the single source of truth).
        removed = 0
        for old_path in store.all_indexed_files():
            if old_path not in seen_files and not os.path.exists(old_path):
                store.remove_file(old_path)
                removed += 1

        # Pitfall 6: record the repo's git HEAD sha at index time (not a git repo → None, nothing recorded).
        sha = _git_head_sha(abs_path)
        if sha:
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
    with storage.ProjectStore.open(abs_path) as store:
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
    other language degrades to name matching (all low confidence, honestly labelled)."""
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
    """Step 6: self-assess the reliability of a find_references result and say when you
    should go back and read the source.

    level: high = trust it directly / medium = partly trustworthy but it has blind spots,
    read a bit more / low = read the code, do not treat this as a verdict.
    ⛔ No level **replaces reading the code to judge whether the logic is right**. This
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
    db_file = storage.db_path_for(abs_path)
    if db_file.exists():
        with storage.ProjectStore.open(abs_path) as store:
            candidate_defs = [d for d in store.find_symbol_definitions(symbol)
                              if d["kind"] in _REFERENCEABLE_KINDS]
    if def_path is None and candidate_defs:
        def_path = candidate_defs[0]["path"]

    # C5 dispatches on the definition file's language: Python (or an undeterminable
    # extension) takes jedi's real import resolution; every other language goes through
    # _refs_non_python (ts-morph, degrading to name matching).
    lang = symbols.language_for_file(def_path) if def_path else None
    if lang in (None, "python"):
        result = references.find_references(
            root, symbol, def_path=def_path,
            include_low_confidence=include_low_confidence,
        )
        # Pitfall 9 (fixed in adversarial review: fallback, not override): only retry with
        # the sampled language when def_path is None *and* jedi found no definition.
        # ⚠ This must run *after* jedi fails, because jedi does not depend on the index or
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
    # Step 1 safety net: all three sources (references.find_references / name_match /
    # ts_morph) already set engine, but a fallback swapping the result, or a future new
    # path, could miss it, so default conservatively (lowest confidence, never claiming
    # real resolution that did not happen).
    result.setdefault("engine", "name-match")
    # Step 2 (Gap3-A, lowering confidence): state the capability boundary honestly.
    # reference lookup and unused detection are not the same as passing compilation, type
    # checking or lint, and all-green refs do not mean it builds. After clearing dead code
    # or changing a signature, run build/CI yourself.
    result["verification_reminder"] = (
        "CodeSextant reports reference relationships, which is not the same as passing "
        "compilation, type checking or lint; after clearing dead code or changing a "
        "signature, always run build/CI to verify."
    )
    # Step 6: awareness of its own boundaries. Self-assess the reliability of this result
    # and volunteer when you should go back and read the source.
    # ⛔ The tool is a navigation map, not the code itself: on name-match results, zero
    # references, or far more low-confidence hits, it says so, so nobody assumes coverage
    # it does not have.
    result["reliability"] = _refs_reliability(result)

    # Persist the high-confidence reference edges, grouped by source file, for PageRank later.
    if persist and db_file.exists() and result.get("definition"):
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
                "def_line": d["line"],
                "confidence": "high",
            })
        if edges_by_src:
            with storage.ProjectStore.open(abs_path) as store:
                for sp, edges in edges_by_src.items():
                    # Note: replace_refs_for clears *all* of that source file's old edges.
                    # To avoid wiping other symbols' edges, accumulate instead: read the
                    # file's existing edges back and merge.
                    existing = [e for e in store.all_refs() if e["src_path"] == sp
                                and e["symbol_name"] != symbol]
                    store.replace_refs_for(sp, existing + edges)

    return result


def call_hierarchy(path: str, symbol: str, *, direction: str = "both",
                   max_hops: int | None = None, def_path: str | None = None,
                   src_root: str | None = None, build_edges: bool = True) -> dict:
    """Transitive call chain: upgrades single-level refs into transitive caller/callee chains.

    direction: up = who (transitively) calls this symbol (callers) / down = who this symbol
    (transitively) calls (callees) / both.
    Underneath it uses storage.traverse_call_graph (a WITH RECURSIVE CTE over the refs
    table); max_hops stops cycles from recursing forever.

    ⚠ The call chain is built from **persisted reference edges** (the refs table, which only
    accumulates once find_references has run against a symbol). With build_edges=True, the
    target gets one find_references(persist=True) pass first to build its direct caller
    edges, which makes the direct level of the up direction accurate immediately; the
    transitive levels and the down direction still depend on whatever edges the refs table
    already holds. The note says so honestly, in keeping with the "honest UNKNOWN"
    philosophy: if the edges are incomplete, say so rather than pretending otherwise.
    Static derivation cannot see dynamic or reflective calls.

    Parameters
    ----------
    max_hops : when None, taken from env CODESEXTANT_CALL_HIERARCHY_MAX_HOPS (default 5,
               adjustable per L0 hard rule #6).
    Returns a dict: {symbol, direction, definition, callers?, callees?, max_hops,
             edges_in_graph, candidate_definitions, note, verification_reminder}.
    An unindexed project → RuntimeError.
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

    with storage.ProjectStore.open(abs_path) as store:
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

    with storage.ProjectStore.open(abs_path) as store:
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


def _is_test_path(p: str) -> bool:
    """Path heuristic for identifying test files (used by blast radius to split test from
    prod; costs nothing)."""
    pl = p.replace("\\", "/").lower()
    base = os.path.basename(pl)
    return (base.startswith("test_") or base.endswith("_test.py") or base.endswith("_test.go")
            or ".test." in base or ".spec." in base or base == "conftest.py"
            or "/__tests__/" in pl or "/tests/" in pl or "/test/" in pl or "/spec/" in pl)


def _mark_high_importance(path: str, callers: list[dict]) -> list[dict]:
    """Flag the affected callers that PageRank considers highly important (by intersecting
    with get_map's top symbol names).

    Red team L2-MEDIUM fix: with_name_edges=False takes the lightweight path. impact and
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
    The honesty layer is mandatory: low-confidence transitive dependencies from name matching
    are listed separately as "may also be affected (unconfirmed)" and ⛔ are never mixed into
    the confirmed set, where they would mislead. Static derivation cannot see dynamic or
    reflective calls.

    Returns a dict: {symbol, definition, direct_callers, transitive_callers, affected_files,
             by_kind:{test/prod/entrypoint}, high_importance_affected, uncertain_maybe_affected,
             summary, note, verification_reminder}. An unindexed project → RuntimeError.
    """
    from . import deadcode

    ch = call_hierarchy(path, symbol, direction="up", max_hops=max_hops,
                        def_path=def_path, src_root=src_root)
    callers = ch.get("callers", []) or []
    confirmed = [c for c in callers if c.get("confidence") == "high"]
    uncertain = [c for c in callers if c.get("confidence") != "high"]

    by_kind: dict[str, list] = {"test": [], "prod": [], "entrypoint": []}
    for c in confirmed:
        # ⚠ test takes priority over entrypoint: deadcode.is_entrypoint treats test_*.py as
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
        # ⛔ Low-confidence transitive dependencies are listed separately, never mixed into
        # the confirmed set (the honesty layer).
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
                      (red team L2-MEDIUM).

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

    # Rough conversion: one symbol summary (kind name @file:line) is about 12 tokens.
    tokens_per_symbol = 12
    top_n = max(1, token_budget // tokens_per_symbol)

    with storage.ProjectStore.open(abs_path) as store:
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
        # Red team L4-MEDIUM: when the scan was truncated, the note must not claim it
        # covered the whole project (the honesty layer).
        truncated = bool((ng_meta or {}).get("truncated"))
        coverage = (f"stratified sample of {(ng_meta or {}).get('scanned_files')} of "
                    f"{(ng_meta or {}).get('total_files')} files (truncated, reason="
                    f"{','.join((ng_meta or {}).get('truncation_reasons') or [])}; adjustable via "
                    "env CODESEXTANT_NAMEGRAPH_MAX_FILES), so the ordering covers only part of "
                    "the project and later symbols may be underrated"
                    if truncated else "covers the whole project")
        if not refs:
            note = ("No reference edges at all (refs=0 and no name-level edges either), so "
                    "PageRank degrades to a uniform distribution. This usually means the "
                    "project has no internal cross-references, or namegraph is disabled.")
        elif not db_refs:
            note = (f"PageRank ordered by name-level whole-graph edges ({name_edge_count} "
                    f"low-confidence references folded into {name_unique_count} unique edges, "
                    f"{coverage}). The ordering has escaped the uniform distribution and "
                    "surfaces structurally central symbols. For more precision, run "
                    "find_references(persist=True) on hot symbols to accumulate "
                    "high-confidence edges.")
        else:
            note = (f"PageRank ordered by a mix of {len(db_refs)} high-confidence edges (real "
                    f"resolution, dominant) and {name_edge_count} name-level low-confidence "
                    f"references (folded into {name_unique_count} unique edges, {coverage}).")
        result = {
            "project_key": store.project_key,
            "token_budget": token_budget,
            "approx_tokens": len(ranked) * tokens_per_symbol,
            "count": len(ranked),
            "symbols": ranked,
            "edge_sources": {
                "db_high_edges": len(db_refs),
                "name_low_edges": name_edge_count,
                "name_low_unique_edges": name_unique_count,
                "symbol_snapshot_hit": symbol_snapshot_hit,
                "namegraph_meta": ng_meta,
            },
            "note": note,
        }
        if not symbol_snapshot_hit:
            _schedule_symbol_snapshot(store.db_file, symbol_revision, symbols)
        return result


def _map_cache_key(path: str, token_budget: int, damping: float,
                   focus_symbols, focus_files, with_name_edges: bool) -> tuple:
    db_file = storage.db_path_for(path)
    stat = db_file.stat()
    env_signature = tuple((name, os.environ.get(name)) for name in _MAP_CACHE_ENV)
    return (
        os.path.normcase(os.path.abspath(path)), stat.st_mtime_ns, stat.st_size,
        int(token_budget), float(damping), tuple(focus_symbols or ()),
        tuple(focus_files or ()), bool(with_name_edges), env_signature,
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

    # Finish the idempotent schema/index migration before reading the revision, so an
    # upgrade does not store the result under the pre-migration key and recompute it from
    # scratch next time. open() no longer modifies meta unconditionally, so a normal cache
    # hit costs only one cheap open/close of the database.
    with storage.ProjectStore.open(abs_path):
        pass
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
        print(f"  ⚠ failed to write map snapshot: {type(exc).__name__}: {exc}",
              file=sys.stderr)
    return result


def status(path: str, *, check_freshness: bool = False) -> dict:
    """A project's index status (for the /status endpoint and the panel).

    A project that has never been indexed returns indexed=False rather than raising, because a
    status query should be able to report "not indexed".
    Only check_freshness=True compares the git HEAD sha, which spawns a git subprocess. The
    default is False, so an unauthenticated GET /status cannot be turned into a git spawn
    storm by a malicious local web page using no-cors (pit7-1).
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {
            "indexed": False,
            "project_key": storage.project_key(abs_path),
            "repo_path": abs_path,
            "db_file": str(db_file),
        }
    with storage.ProjectStore.open(abs_path) as store:
        st = store.stats()
        st["indexed"] = True
        if check_freshness:
            # Pitfall 6: git freshness. The sha recorded at index time vs the current HEAD sha.
            indexed_sha = st.get("indexed_git_sha")
            current_sha = _git_head_sha(abs_path)
            st["current_git_sha"] = current_sha
            if indexed_sha and current_sha:
                st["git_stale"] = (indexed_sha != current_sha)
            elif indexed_sha and not current_sha:
                # A sha was recorded before, but git is now unavailable (.git deleted, moved,
                # or dubious-ownership) → undecidable. ⛔ Do not silently return False and
                # claim it is fresh (pit6-1).
                st["git_stale"] = None
                st["git_note"] = "git is currently unavailable, so freshness cannot be determined (the sha recorded at index time is still here)"
            else:
                # Not a git repo, or no sha recorded at index time → freshness does not apply.
                st["git_stale"] = False
                if not indexed_sha and current_sha:
                    st["git_note"] = "this database recorded no git sha at index time; reindex to enable freshness checking"
        return st


def list_projects() -> dict:
    """List every project indexed on this machine (for the /projects endpoint and the panel).

    Scans each SQLite database in the database directory, looks up its repo_path and
    gathers statistics. It takes no project argument, because it is the data source for the
    panel's overview and complements the per-project endpoints.

    Returns {db_dir, count, projects:[...]}; count only counts databases that were read
    successfully, though broken ones are still listed with an error.
    """
    projects = storage.list_indexed_projects()
    return {
        "db_dir": str(storage.default_db_dir()),
        "count": sum(1 for p in projects if "error" not in p),
        "projects": projects,
    }


# ── C5c: dead-code clue layer (step 3): reuses find_references' real resolution and assembles it with the deadcode helpers ──
def _orphans_for_file(root: str, scope_file: str, lang: str | None) -> list[dict]:
    """Judge orphan status for each top-level exportable symbol in scope_file, reusing
    find_references' real resolution.

    ⛔ UNKNOWN gate (fix 1's safety gate): check resolver_available **before** running
    find_references. If the engine is unavailable the whole symbol returns
    UNKNOWN_NO_RESOLVER and **the high=0 decision is skipped** (red team B2: otherwise an
    unavailable ts-morph marks every export in a TS project deletable, which is a disaster).
    Only top-level symbols are considered (methods and nested definitions are not orphan
    candidates).
    """
    from . import deadcode  # deferred: engine → deadcode is one-way, avoiding a cycle

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
        if not ok:  # ⛔ Safety gate: engine unavailable → skip the high=0 decision and return an honest UNKNOWN
            out.append({**s, "verdict": "UNKNOWN_NO_RESOLVER",
                        "icon": deadcode.verdict_icon("UNKNOWN_NO_RESOLVER"),
                        "reason": reason})
            continue
        pending.append((name, s))

    if pending and file_lang in ("typescript", "tsx", "javascript"):
        # Step 5: for TS/JS, query every pending symbol in one batch (one new Project loads
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

    ⚠ This is a clue layer, not a decision maker: it produces clues carrying a safety grade
    (LIKELY_UNUSED 🟡 / UNKNOWN ❔ / PUBLIC_API ⚪ / KEEP ✅). Review them yourself and run
    build/CI before deleting anything. All-green refs are not the same as compiling. The
    core discipline: when an engine or linter is unavailable, always return UNKNOWN_*
    (honest), and never degrade into a confident false positive.

    Parameters
    ----------
    path       : the project root (the root for the unused-import scan, and the jedi/ts-morph
                 resolution root for orphans).
    scope_file : orphan analysis only runs when this is given (resolving each top-level
                 symbol in that file for real; doing it symbol by symbol across a whole
                 project is far too heavy, so step 3 requires a specific file).
    lang       : override language inference (by default it is inferred from scope_file's
                 extension, or from the project).

    Returns a dict (JSON-serializable): {root, scope_file, unused_imports, orphans, summary,
    verification_reminder}.
    A path that is not a directory → NotADirectoryError (fail loudly).
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
        # Step 6: spell out this result's blind spots, where the tool could not help and a
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

    ⚠ Name-level clues are not proof of execution; before judging something direct (a
    violation), read the code and confirm it really hits a metered endpoint.
    A path that is not a directory → NotADirectoryError (fail loudly).
    """
    from . import ai_usage
    if not os.path.isdir(path):
        raise NotADirectoryError(f"find_ai_usage: '{path}' is not a valid directory")
    abs_path = os.path.abspath(path)
    return ai_usage.scan_ai_usage(
        abs_path, _iter_source_files(abs_path),
        scope_file=os.path.abspath(scope_file) if scope_file else None)


# ── Feature A: unwired check (working closely with namegraph): a coarse sweep for the
# root cause of code rot: things written but never wired in ──
def find_unwired(path: str, *, max_fanout: int | None = None) -> dict:
    """Unwired check: uses the name-level whole graph to quickly frame defined top-level
    symbols that have zero external references.

    This detects the root cause of code rot: a function, class, type or constant is defined,
    but nothing outside its own body ever mentions its name, which makes it a suspected
    unwired symbol. It works closely with namegraph, computing external usage from the same
    whole-graph name-level edges (body-aware: self-tokens on the definition line and
    recursive self-calls are excluded, while calls from elsewhere in the same file are kept,
    so a same-file helper is not misreported).

    ⚠ A clue layer, not a decision maker (the same philosophy as deadcode, honestly
    low-confidence throughout):
      - The ceiling of name-level analysis: same-name interference causes **under-reports**
        (another definition of the same name being used elsewhere credits the genuinely
        unused one with references); dynamic, reflective and string-concatenated calls are
        invisible, causing **false positives**; and a **public API** imported from outside
        this repo but unused within it has exactly zero internal references, so it is
        misreported too (TS/JS `export` has no __all__ equivalent to exempt it, which makes
        this especially dangerous).
      - Exemptions: filename conventions, decorator entrypoints, Python __all__, dunders,
        and pyproject console_scripts entrypoints (reusing deadcode.is_entrypoint and
        entry_point_func_names). ⚠ __all__ is Python-only; a TS/JS export public API has no
        equivalent exemption and will be misreported.
      - Flooded names with too many same-named definitions (> the fan-out cap) →
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
    An unindexed project → RuntimeError.
    """
    from . import deadcode

    if not os.path.isdir(path):
        raise NotADirectoryError(f"find_unwired: '{path}' is not a valid directory")
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"find_unwired: project has not been indexed yet (no {db_file}); call index_project first.")

    with storage.ProjectStore.open(abs_path) as store:
        syms = store.get_symbols()
        indexed = store.all_indexed_files()

    usage, over_fanout, ng_meta = namegraph.compute_external_usage(
        syms, indexed_files=indexed, max_fanout=max_fanout)
    # Red team L3-HIGH: exempt pyproject console_scripts entrypoints (called reflectively by
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
        # Dunders (__all__/__version__/__main__…) go through special mechanisms that
        # name-level analysis cannot see → exempt.
        if name.startswith("__") and name.endswith("__"):
            exempt += 1
            continue
        # pyproject console_scripts entrypoint exemption (red team L3-HIGH).
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
            # Red team L3-MEDIUM: name-level confidence is even lower for variables and
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
            "silence ⛔ does not mean they are unwired.")
    if ng_meta.get("truncated"):
        advisory.append(
            f"⚠ Truncated: only {ng_meta.get('scanned_files')} of {ng_meta.get('total_files')} "
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


# ── Feature B: comment management (the engine's query layer, design §3.B.2) ──
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
    """Repo comment summary (feature B, "see it all at once"): docstring coverage by kind +
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

    with storage.ProjectStore.open(abs_path) as store:
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

        # Red team L3-MEDIUM: tag_counts now scans the text line by line instead of doing a
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
    """TODO/FIXME index (feature B, "know which line"): scans for markers line by line and
    returns the **real source line**, including multi-line block and doc comments.

    FIX-3b: for block and doc comments, a marker's line number is computed exactly by
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

    with storage.ProjectStore.open(abs_path) as store:
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
    """Retrieve comments with precise filtering (feature B, "only what is worth reading",
    mirroring get_symbols). Unindexed → count=0 plus a note, rather than pretending."""
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {"project_key": storage.project_key(abs_path), "count": 0, "comments": [],
                "note": f"project has not been indexed yet (no {db_file}); call index_project first."}
    target = os.path.abspath(file) if file else None
    with storage.ProjectStore.open(abs_path) as store:
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


# ── Feature B: duplicate / near-duplicate detection (the engine's assembly layer, design §3.A) ──
_DUP_VERDICT_ICON = {
    "EXACT_DUP": "🟥", "RENAMED_DUP": "🟧", "STRUCTURAL_NEAR": "🟨",
    "CALL_PATTERN_SIM": "🟦", "BOILERPLATE_SUPPRESSED": "⚪", "UNKNOWN_TOO_SMALL": "❔",
}


def _make_dup_group(verdict: str, members: list[dict], similarity, reason: str) -> dict:
    """Assemble one duplicate group (jscpd compact format: location + name + confidence).
    ⛔ It never includes the source itself, upholding the read-only navigation map."""
    return {
        "verdict": verdict, "icon": _DUP_VERDICT_ICON[verdict], "similarity": similarity,
        "members": [{"path": m["path"], "line": m["line"], "end_line": m.get("end_line"),
                     "name": m.get("name"), "scope": m.get("scope")} for m in members],
        "representative": members[0].get("name"),
        "node_count": members[0].get("node_count"),
        "reason": reason,
    }


def get_health(path: str) -> dict:
    """Per-symbol code health (the numeric layer: D1 bloat + D3 cognitive complexity + D5
    duplication → health; D6 dead code → dead).

    It composes clean-code discipline into a per-symbol health in [0,1] (low means worth
    reviewing) plus dead (unwired).
    ⛔ A read-only clue, not a decision maker: low health does not mean "should be deleted",
    it means "worth reading yourself and checking with build/CI".
    ⛔ It contains no visual mapping (saturation or opacity formulas). That belongs to the
    presentation layer; this API returns numbers only.
    UNKNOWN / N-A dimensions (classes and variables have no fingerprint; cognitive complexity
    is unavailable outside high-confidence languages) are excluded and the remaining weights
    renormalized, so nothing is inflated to a perfect score.

    Returns a dict (JSON-serializable): {root, symbols:[{path,name,line,kind,health,dead}],
                          summary:{n_nodes,n_covered,coverage,n_dead,clone_pairs}}。
    An unindexed project → RuntimeError (same as get_map).
    """
    from collections import Counter

    from . import health as _health
    if not os.path.isdir(path):
        raise NotADirectoryError(f"get_health: '{path}' is not a valid directory")
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(f"get_health: project has not been indexed yet (no {db_file}); call index_project first.")

    with storage.ProjectStore.open(abs_path) as store:
        syms = store.get_symbols()
        fps = store.conn.execute(
            "SELECT path,line,node_count,shape_hash,cognitive FROM fingerprints").fetchall()
    shape_cnt = Counter(r["shape_hash"] for r in fps)
    fp_by = {(os.path.normcase(r["path"]), int(r["line"])):
             (int(r["node_count"] or 0), r["shape_hash"], r["cognitive"]) for r in fps}
    try:   # D6 unwired (→ the dead flag); a failure here must not break health (fail soft)
        uw = find_unwired(abs_path)
        dead_keys = {(os.path.normcase(os.path.abspath(c["path"])), int(c["line"]))
                     for c in uw.get("candidates", []) if c.get("verdict") == "UNWIRED_CANDIDATE"}
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠ get_health: find_unwired failed (D6 skipped): {exc}", file=sys.stderr)
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
    """One shape_hash group → (output groups, summary deltas, keys of members already grouped).

    Within the group, a second clustering pass on raw_token splits it further: verbatim
    matches each become an EXACT_DUP, and representatives across clusters form a RENAMED_DUP
    (red team L1-MEDIUM: both coexist and neither swallows the other; f1/f2 match verbatim
    and get EXACT, f1/f3 differ only by renaming and get RENAMED).
    """
    if len(members) < 2:
        return [], {}, set()
    # Red team L1-HIGH: structural significance = has_control_flow + node_count. ⛔ Do not
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

    ⚠ Red team L5-HIGH: always run against the whole repo's fingerprints and never apply a
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

    ⚠ Red team L4-HIGH: count the **true document frequency** with
    DISTINCT(path,line,fp_value), meaning how many different functions it appears in, not
    fingerprint_index's total row count. Otherwise a fingerprint repeating inside a single
    function blows past df_cap on its own and the genuine fingerprints get dropped.
    """
    return {r[0] for r in conn.execute(
        "SELECT fp_value FROM (SELECT DISTINCT path,line,fp_value FROM fingerprint_index) "
        "GROUP BY fp_value HAVING COUNT(*)>?", (df_cap,)).fetchall()}


def _dup_load_fingerprint_rows(conn, target: str | None, flood: set) -> list:
    """Load the fingerprint rows to compare.

    ⚠ Red team L2-MEDIUM: in scope_file mode, load only the units whose fingerprints intersect
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
    # Red team L2-LOW: identical shapes belong to stage 1's EXACT/RENAMED, so stage 2 reports
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
    """Turn the numbers into "what you should go and check next". ⛔ It never emits a
    "should be deleted / should be merged" decision."""
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
                        "level; this tool honestly cannot detect Type-4 semantic clones.")
    return advisory


def find_duplicates(path: str, *, scope_file: str | None = None, near_global: bool = False,
                    min_similarity: float | None = None,
                    include_call_pattern: bool = False) -> dict:
    """Duplicate / near-duplicate detection (shared core): grouping by structural
    fingerprint, strictly non-semantic (design §3.A).

    Three stages (red team FIX-1: without a scope, only stage 1 runs by default, which is
    genuinely O(n); global near-duplicate stages 2/3 must be opted into):
      Stage 1: GROUP BY shape_hash → EXACT_DUP (raw_token matches too, so verbatim) /
               RENAMED_DUP (same shape, renamed). A structural-significance hard gate
               (control flow required, plus sufficient node_count/nstmts) stops the flood of
               getter and __init__ false positives.
      Stage 2/3 (only with scope_file or near_global): winnowing inverted index + DF-cap,
               through three gates → STRUCTURAL_NEAR.
      call_pattern (only with include_call_pattern, lowest confidence 🟦): matching call_hash
               with a different structure.

    ⛔ It never emits a "should be deleted / should be merged" decision (upholding hard rule 3,
    the read-only navigation map); identical structure is not identical semantics, so read the
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
    read_code_advisory}. An unindexed project → RuntimeError.
    """
    if not os.path.isdir(path):
        raise NotADirectoryError(f"find_duplicates: '{path}' is not a valid directory")
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"find_duplicates: project has not been indexed yet (no {db_file}); call index_project first.")

    min_node = clones._env_int("CODESEXTANT_DEDUP_MIN_NODE_COUNT", 15)
    sim_thresh = (min_similarity if min_similarity is not None
                  else clones._env_float("CODESEXTANT_DEDUP_SIMILARITY_THRESHOLD", 0.8))
    sim_thresh = max(0.0, min(1.0, sim_thresh))   # red team L4-LOW: clamp so an out-of-range value cannot break the threshold's meaning
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

    with storage.ProjectStore.open(abs_path) as store:
        conn = store.conn
        # ⚠ Red team L5-HIGH: stage 1 (EXACT/RENAMED) **always runs against the whole repo's
        # fingerprints** with no WHERE path filter. Otherwise scope_file mode turns stage 1
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
            "too. ⛔ The tool never says something should be deleted or merged; read the code "
            "yourself and pass build/CI before merging."),
        "read_code_advisory": advisory,
    }
