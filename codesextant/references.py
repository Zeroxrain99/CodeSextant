"""Resolve symbol references with jedi, ts-morph, or name matching.

Python lookup uses a text prefilter followed by jedi resolution at each candidate
site. TypeScript and JavaScript use the ts-morph bridge when available. Other
languages return low-confidence name matches. The engine owns persistence and
result assembly.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from typing import NamedTuple

import jedi

from . import symbols

# Pattern cache for the coarse filter's "this line might use symbol X" check (avoids recompiling the regex per file)
_word_re_cache: dict[str, re.Pattern] = {}


def _word_re(symbol: str) -> re.Pattern:
    pat = _word_re_cache.get(symbol)
    if pat is None:
        pat = re.compile(r"\b" + re.escape(symbol) + r"\b")
        _word_re_cache[symbol] = pat
    return pat


def _iter_python_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip the usual noise directories (avoid scanning .git / venv / __pycache__)
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__", ".venv", "venv",
                                    "node_modules", ".mypy_cache", ".pytest_cache")]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


# Every language's noise directories, for the sweeps that are not Python-only.
_SKIP_DIRS_MULTI = (".git", "__pycache__", ".venv", "venv", "node_modules",
                    ".mypy_cache", ".pytest_cache", "build", "dist", "target", ".tox")


def _iter_files_by_ext(root: str, exts):
    """Scan files under root with the given extensions (skipping noise directories). Used by cross-language name matching."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS_MULTI]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in exts:
                yield os.path.join(dirpath, fn)


class NameSweep(NamedTuple):
    """Which files name a symbol, and a fingerprint of exactly that.

    ``digest`` covers every matching file's path and content, which makes it a sound
    answer to "could the set of callers have changed since last time?". A caller has
    to name the symbol, so these files are a complete superset of the possible
    callers: if none of them has changed and no new one has appeared, no caller can
    have appeared either. That is what lets an expensive resolution be cached without
    the cache going quietly stale -- see engine._ensure_blast_radius.

    ``truncated`` means the walk stopped at ``limit``, so the set is partial and the
    digest describes a prefix rather than the whole answer.
    """

    files: list[str]
    digest: str
    truncated: bool


def name_sweep(src_root: str, symbol: str, *, lang: str | None = None,
               limit: int | None = None) -> NameSweep:
    """Files whose text names ``symbol`` as a standalone word: stage one, without jedi.

    This is the cheap half of reference finding -- a text sweep costing roughly seven
    microseconds per file, against about a tenth of a second per file for
    per-occurrence resolution. It is therefore also the honest way to decide whether
    the expensive half is worth starting: the number of files a name appears in is
    the thing that drives that cost, and it can be measured before committing to it.

    Files are read as bytes and rejected on a substring test before anything is
    decoded, because decoding every file in the repository to look for one name is
    the sweep's entire cost and almost none of it buys anything -- the overwhelming
    majority of files do not contain the name at all.

    ``lang`` restricts the scan to one language's extensions; None scans every
    supported extension. ``limit`` stops the walk once that many files have matched,
    so a caller asking only "is this cheap?" does not pay for the whole repository to
    find out that it is not.
    """
    if lang == "python":
        paths = _iter_python_files(src_root)
    elif lang and lang in symbols.LANGUAGE_SPECS:
        paths = _iter_files_by_ext(
            src_root, frozenset(symbols.LANGUAGE_SPECS[lang]["exts"]))
    else:
        paths = _iter_files_by_ext(src_root, symbols.SUPPORTED_EXTENSIONS)
    needle = symbol.encode("utf-8")
    pat = _word_re(symbol)
    found: list[str] = []
    fingerprints: list[tuple[str, str]] = []
    truncated = False
    for fp in paths:
        try:
            with open(fp, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if needle not in data:
            continue
        if not pat.search(data.decode("utf-8", "replace")):
            continue
        found.append(fp)
        fingerprints.append((os.path.relpath(fp, src_root).replace(os.sep, "/"),
                             hashlib.sha256(data).hexdigest()))
        if limit is not None and len(found) >= limit:
            truncated = True
            break
    accumulator = hashlib.sha256()
    for relative, content in sorted(fingerprints):
        accumulator.update(f"{relative}\0{content}\0".encode())
    return NameSweep(found, accumulator.hexdigest(), truncated)


def candidate_files(src_root: str, symbol: str, *, lang: str | None = None,
                    limit: int | None = None) -> list[str]:
    """The file list from :func:`name_sweep`, for callers that need nothing else."""
    return name_sweep(src_root, symbol, lang=lang, limit=limit).files


def _prefilter_candidate_files(src_root: str, symbol: str) -> list[str]:
    """Stage 1 (coarse filter): which files does the name appear in. Cheap and loose, so it is better to over-include a few.

    Returns every .py file that contains the symbol name (as a standalone word). jedi only does precise resolution on these.
    """
    return candidate_files(src_root, symbol, lang="python")


def _make_project(src_root: str) -> jedi.Project:
    """One jedi.Project per project (isolates by project root naturally)."""
    return jedi.Project(path=os.path.abspath(src_root))


def goto_definition(src_root: str, file_path: str, line: int, column: int) -> list[dict]:
    """jedi goto: where is the symbol at this position defined (follow_imports, points precisely across import chains).

    Parameters line/column: line is 1-based, column is 0-based (jedi's convention: column points inside the identifier).
    Returns list[dict]: {path, line, name, type, confidence:"high"}.
    Returns [] when unresolved (this is a genuine jedi miss, not an error, but the caller should treat it as "no high-confidence definition").
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
    except OSError as exc:
        raise FileNotFoundError(f"goto failed: cannot read {file_path} ({exc})") from exc

    project = _make_project(src_root)
    script = jedi.Script(source, path=file_path, project=project)
    defs = script.goto(line, column, follow_imports=True)
    out = []
    for d in defs:
        out.append({
            "path": str(d.module_path) if d.module_path else None,
            "line": d.line,
            "name": d.name,
            "type": d.type,
            "confidence": "high",  # jedi resolution hit = high confidence
        })
    return out


def _locate_definition_positions(src_root: str, def_name: str,
                                 def_path: str | None) -> list[tuple[str, int, int]]:
    """Every def/class line for `def_name` in its definition file, not just the first.

    One file may define a name more than once, and it happens in ordinary code rather
    than in pathological code: ``send`` on two classes, ``run`` on a base and its
    override, a function redefined under ``if TYPE_CHECKING``. Taking the first match
    and comparing jedi's answer against that one line scores every reference to any of
    the others as pointing somewhere else -- so the blast radius comes back empty for
    the symbol most likely to have callers, and says nothing about why.

    All of them are returned because the answer this feeds is a list of *files*, and
    the edges are stored per (file, name): "something named ``send`` and defined in
    ``dec.py`` is used here" is exactly the claim, and it is true of every definition
    in the file. The first entry keeps the position the single-position callers used.
    """
    pat = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(" + re.escape(def_name) + r")\b")
    search_files = [def_path] if def_path else list(_iter_python_files(src_root))
    found: list[tuple[str, int, int]] = []
    for fp in search_files:
        if not fp or not os.path.exists(fp):
            continue
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                for i, line_text in enumerate(f, 1):
                    m = pat.match(line_text)
                    if m:
                        found.append((fp, i, m.start(1) + 1))
        except OSError:
            continue
        if found:
            # Without def_path this walks the project, and the first file that defines
            # the name is the one meant -- carrying on would mix unrelated definitions
            # that merely share a spelling.
            break
    return found


def _locate_definition_position(src_root: str, def_name: str,
                                def_path: str | None) -> tuple[str, int, int] | None:
    """The first definition position, for callers that only need a starting point."""
    found = _locate_definition_positions(src_root, def_name, def_path)
    return found[0] if found else None


def _occurrences_in_file(file_path: str, symbol: str) -> list[tuple[int, int]]:
    """Every occurrence of `symbol` (as a standalone word) inside a file, returns [(line 1-based, col 0-based), ...].

    col is 0-based (jedi's goto/column convention). Feeds stage 2's per-occurrence goto call.
    """
    pat = _word_re(symbol)
    out: list[tuple[int, int]] = []
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            for li, line_text in enumerate(f, 1):
                for m in pat.finditer(line_text):
                    out.append((li, m.start()))
    except OSError:
        pass
    return out


# The languages whose imports are actually resolved. Everything else degrades to name
# matching, which is a weaker claim and has to be labelled as one wherever it surfaces --
# `impact` in particular, which builds its chain from *resolved* edges and would
# otherwise tell a reader to go and generate edges that can never exist.
RESOLVED_LANGUAGES = frozenset({"python", "typescript", "tsx", "javascript"})


def resolves_imports(lang: str | None) -> bool:
    """Whether a real import resolver exists for this language."""
    return lang in RESOLVED_LANGUAGES


def find_references(src_root: str, symbol: str, def_path: str | None = None,
                    *, include_low_confidence: bool = True,
                    max_candidate_files: int = 400) -> dict:
    """Find "who uses symbol": two-stage precise resolution (direction: call site goto's back to the definition).

    Candidate files are selected with a text filter. Each occurrence is then resolved
    from the call site back to the target definition. This distinguishes same-named
    definitions without asking jedi to scan the entire project at once.

    Parameters
    ----------
    src_root : project source root (the isolation + import-resolution root for jedi.Project).
    symbol   : the symbol name to find references for (e.g. "check").
    def_path : the file containing that symbol's definition; when given, precisely pins down
               "which same-named definition's references we're looking for".
    include_low_confidence : when True, also returns points where "the name matches but goto
               doesn't point at the target definition" (marked low).
    max_candidate_files : cap on the number of candidate files (prevents a goto-count blowup on
               a very large repo). Exceeding it truncates the list and flags it.

    Returns a dict (JSON-serializable directly):
      {
        "symbol", "definition": {path,line,column} or None,
        "high_confidence": [{src_path, line, column, confidence:"high"}, ...],
        "low_confidence":  [{src_path, line, column, confidence:"low", note}, ...],
        "name_match_file_count": int,        # how many files a pure name match would catch (baseline for comparison)
        "name_match_hit_count": int,         # total text hits from pure name matching (includes the definition/same names)
        "candidates_scanned": int,           # candidate files actually scanned by goto
        "truncated": bool,
      }
    """
    positions = _locate_definition_positions(src_root, symbol, def_path)
    located = positions[0] if positions else None
    candidate_files = _prefilter_candidate_files(src_root, symbol)

    result: dict = {
        "symbol": symbol,
        "definition": None,
        "high_confidence": [],
        "low_confidence": [],
        "name_match_file_count": len(candidate_files),
        "name_match_hit_count": 0,
        "candidates_scanned": 0,
        "truncated": False,
        "engine": "jedi",
    }

    if located is None:
        result["error"] = (
            f"could not find a def/class definition line for '{symbol}' within src_root "
            f"(def_path={def_path}); cannot do high-confidence reference resolution."
        )
        return result

    def_file, def_line, def_col = located
    result["definition"] = {"path": def_file, "line": def_line, "column": def_col}
    # Every same-named definition in that file counts as the target: see
    # _locate_definition_positions. The line jedi actually landed on is kept per
    # reference, so the persisted edge points at the definition that was really
    # used rather than at whichever one came first in the file.
    result["definitions"] = [{"path": path, "line": line, "column": column}
                             for path, line, column in positions]
    def_lines = {line for _path, line, _column in positions}
    def_file_norm = os.path.normcase(os.path.abspath(def_file))

    project = _make_project(src_root)

    scan_files = candidate_files
    if len(scan_files) > max_candidate_files:
        scan_files = scan_files[:max_candidate_files]
        result["truncated"] = True
    result["candidates_scanned"] = len(scan_files)

    total_hits = 0
    for fp in scan_files:
        occ = _occurrences_in_file(fp, symbol)
        total_hits += len(occ)
        if not occ:
            continue
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                source = f.read()
        except OSError:
            continue
        script = jedi.Script(source, path=fp, project=project)
        for (line, col) in occ:
            try:
                defs = script.goto(line, col, follow_imports=True)
            except Exception:
                # A goto failure at a single position (broken syntax, etc.) shouldn't blow up
                # the whole query; record it as low confidence
                if include_low_confidence:
                    result["low_confidence"].append({
                        "src_path": fp, "line": line, "column": col,
                        "confidence": "low", "note": "goto resolution failed, cannot confirm target"})
                continue
            # Does this occurrence point at the "target definition"? Any same-named
            # definition in the target file counts, and which one is remembered.
            landed = next(
                (d.line for d in defs
                 if d.module_path
                 and os.path.normcase(os.path.abspath(str(d.module_path))) == def_file_norm
                 and d.line in def_lines),
                None,
            )
            # Exclude "the definition's own line" (doesn't count as a reference)
            is_definition_site = (os.path.normcase(os.path.abspath(fp)) == def_file_norm
                                  and line in def_lines)
            if landed is not None and not is_definition_site:
                result["high_confidence"].append({
                    "src_path": fp, "line": line, "column": col,
                    "def_line": landed, "confidence": "high"})
            elif include_low_confidence and not is_definition_site:
                result["low_confidence"].append({
                    "src_path": fp, "line": line, "column": col, "confidence": "low",
                    "note": "name matches, but goto points at a different same-named symbol (not this definition)"})

    result["name_match_hit_count"] = total_hits
    return result


# An import statement, anchored to the start of a line so a mention inside an
# expression cannot match. Indentation is allowed on purpose: an import inside a
# function or a TYPE_CHECKING block is exactly the kind of dependency a
# top-of-file-only scan would miss, and this project's own lazy modules are written
# that way.
#
# The parenthesised alternative is not a nicety. ``from . import (\n cochange,\n ... )``
# is how a package imports several of its own submodules, and there the imported names
# *are* the modules -- so a pattern stopping at the newline loses precisely the
# intra-package dependencies this is for, while losing nothing but member names in the
# ``from .cookies import (...)`` case where the module is on the first line anyway.
_IMPORT_LINE = re.compile(
    r"^[ \t]*(?:from[ \t]+(?P<dots>\.*)(?P<module>[\w.]*)[ \t]+import[ \t]+"
    r"(?:\((?P<block>[^)]*)\)|(?P<names>[^\n#]+))"
    r"|import[ \t]+(?P<plain>[\w.]+(?:[ \t]*,[ \t]*[\w.]+)*))", re.M)
_TRIPLE_QUOTE = re.compile(r'"""' + "|" + r"'''")


def _without_triple_quoted(text: str) -> str:
    """The same text with triple-quoted regions blanked, keeping the line structure.

    Docstrings and test fixtures are full of example code, and every ``import`` inside
    one would otherwise read as the enclosing file importing it -- which is how a
    dependents list fills up with files that merely *document* the module. Regions
    become newlines rather than disappearing, so the line-anchored import pattern still
    sees real statements at the starts of the lines that follow.

    This is a heuristic and not a parse: a triple quote inside a single-quoted string
    opens a region that is not there. It is the cheap half of a trade made on purpose.
    Parsing each file with ``ast`` is the exact answer and costs about two milliseconds
    a file, which across a project is more than the whole check is allowed to take.
    """
    if '"""' not in text and "'''" not in text:
        return text
    out: list[str] = []
    position = 0
    while True:
        opened = _TRIPLE_QUOTE.search(text, position)
        if opened is None:
            out.append(text[position:])
            break
        out.append(text[position:opened.start()])
        # The closer must be the same kind of quote, or a ''' inside a \"\"\" block
        # would end a region that has not started.
        closed = text.find(opened.group(0), opened.end())
        body_end = len(text) if closed == -1 else closed + 3
        out.append("\n" * text.count("\n", opened.start(), body_end))
        if closed == -1:
            break
        position = body_end
    return "".join(out)


def imported_modules(text: str, relative: str) -> set[str]:
    """Every module name a Python file imports, with relative imports made absolute.

    ``relative`` is the file's path from the project root, and it is what makes
    ``from . import x`` and ``from ..pkg import y`` resolvable at all: the leading dots
    count upwards from the file's own package, so without knowing where the file sits
    there is no way to say what they name. Both forms are the common case inside a
    package, and a scanner skipping them would be blind to exactly the intra-project
    dependencies this exists to find.

    Prefixes count as well as full names -- ``import a.b.c`` also depends on ``a`` and
    ``a.b`` -- because importing a submodule executes every package above it.
    """
    package = relative.split("/")[:-1]
    found: set[str] = set()
    for match in _IMPORT_LINE.finditer(_without_triple_quoted(text)):
        plain = match.group("plain")
        if plain:
            for piece in plain.split(","):
                name = piece.strip()
                if not name:
                    continue
                found.add(name)
                found.update(name.rsplit(".", index)[0]
                             for index in range(1, name.count(".") + 1))
            continue
        dots, module = match.group("dots") or "", match.group("module") or ""
        if dots:
            # One dot means "this package", two means the one above it.
            base = package[:len(package) - len(dots) + 1]
            prefix = ".".join([*base, module]) if module else ".".join(base)
        else:
            prefix = module
        if not prefix:
            continue
        found.add(prefix)
        # ``from pkg import mod`` names a module when mod is one, which is how a
        # package exposes its submodules. The caller intersects against real files, so
        # offering the longer name costs nothing on the occasions it is not one.
        for piece in (match.group("names") or match.group("block") or "").split(","):
            name = piece.strip().split(" as ")[0].strip().strip("()").strip()
            if name and name != "*" and name.isidentifier():
                found.add(f"{prefix}.{name}")
    return found


def module_names_for(relative: str) -> set[str]:
    """Every dotted name under which a file could be imported.

    A project keeping its package under ``src/`` imports ``src/requests/sessions.py``
    as ``requests.sessions`` and never as ``src.requests.sessions``; a project without
    that layout does the opposite. Rather than detect the layout -- which needs
    packaging metadata that need not be present -- every suffix of the path is offered,
    and the importing file decides which one it actually wrote.
    """
    if not relative.endswith(".py"):
        return set()
    parts = relative[:-3].split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return {".".join(parts[index:]) for index in range(len(parts))} if parts else set()


def module_dependents(src_root: str, relatives, *, skip=frozenset(),
                      limit: int = 200) -> dict[str, int]:
    """Files importing any of ``relatives``, and how many of them each one imports.

    This is the blast radius asked one level up from :func:`find_references`. A Python
    caller of a changed function has to import the module defining it, and module
    imports are recoverable without a resolver: no inference, no type propagation, no
    conservative refusal on a dynamically dispatched call. It is a weaker claim than a
    resolved reference -- importing a module is not calling the function that changed --
    and it is one that can still be made where the stronger claim comes back empty,
    which measurement says is most of the time.

    Cost is one pass over the project's Python files with a byte-level rejection before
    anything is decoded, the same shape and the same reason as :func:`name_sweep`.
    ``limit`` stops the walk once that many dependents are found, because a module two
    hundred files import is not one whose dependents are worth listing.
    """
    targets: set[str] = set()
    for relative in relatives:
        targets |= module_names_for(relative)
    if not targets:
        return {}
    # Importing one of these means containing its last component as text, so the
    # overwhelming majority of files are rejected without ever being decoded.
    needles = {name.rsplit(".", 1)[-1].encode("utf-8") for name in targets}
    skipped = {os.path.normcase(os.path.abspath(os.path.join(src_root, path)))
               for path in skip}

    dependents: dict[str, int] = {}
    for path in _iter_python_files(src_root):
        if os.path.normcase(os.path.abspath(path)) in skipped:
            continue
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            continue
        if not any(needle in data for needle in needles):
            continue
        relative = os.path.relpath(path, src_root).replace(os.sep, "/")
        count = len(imported_modules(data.decode("utf-8", "replace"), relative) & targets)
        if count:
            dependents[relative] = count
            if len(dependents) >= limit:
                break
    return dependents


def name_match_references(src_root: str, symbol: str, *, def_path: str | None = None,
                          lang: str | None = None, include_low_confidence: bool = True,
                          max_candidate_files: int = 400) -> dict:
    """Find references through low-confidence name matching.

    The result shape matches ``find_references``, but ``high_confidence`` is always
    empty. TypeScript and JavaScript callers use ``ts_morph_references`` before
    falling back here.

    Parameter lang: scan only that language's extensions (None scans every supported extension).
    """
    if lang and lang in symbols.LANGUAGE_SPECS:
        exts = frozenset(symbols.LANGUAGE_SPECS[lang]["exts"])
    else:
        exts = symbols.SUPPORTED_EXTENSIONS

    result: dict = {
        "symbol": symbol,
        "definition": None,
        "high_confidence": [],
        "low_confidence": [],
        "name_match_file_count": 0,
        "name_match_hit_count": 0,
        "candidates_scanned": 0,
        "truncated": False,
        "engine": "name-match",
        "note": (
            f"High-confidence import resolution for language '{lang or '?'}' is not yet supported "
            "(jedi is Python-only); the results below are from name matching and are all low "
            "confidence and can include same-name noise. TypeScript and JavaScript use "
            "ts-morph when the bridge is available."
        ),
    }
    if def_path and os.path.exists(def_path):
        # Name matching can't precisely locate the definition line, only tag the file (line/column left None)
        result["definition"] = {"path": def_path, "line": None, "column": None}

    files = list(_iter_files_by_ext(src_root, exts))
    result["name_match_file_count"] = len(files)
    if len(files) > max_candidate_files:
        files = files[:max_candidate_files]
        result["truncated"] = True
    result["candidates_scanned"] = len(files)

    if not include_low_confidence:
        return result

    total = 0
    for fp in files:
        for (line, col) in _occurrences_in_file(fp, symbol):
            total += 1
            result["low_confidence"].append({
                "src_path": fp, "line": line, "column": col,
                "confidence": "low", "note": "name matching (no real import resolution)",
            })
    result["name_match_hit_count"] = total
    return result


# ── High-confidence TS/JS resolution through the ts-morph bridge ──
def _ts_bridge_dir() -> str:
    """ts_bridge/ lives at the CodeSextant root (references.py is inside codesextant/, one level up is the root)."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ts_bridge")


def _node_executable() -> str:
    """Return the Node executable selected by the host application, or PATH's node."""
    return os.environ.get("CODESEXTANT_NODE", "").strip() or "node"


def ts_morph_available() -> bool:
    """node is on PATH and ts_bridge is ready (find_refs.mjs + node_modules/ts-morph).
    If either condition is unmet, the caller falls back to name matching.

    Set CODESEXTANT_TS_MORPH_DISABLED=1 to disable the Node subprocess."""
    if os.environ.get("CODESEXTANT_TS_MORPH_DISABLED", "").lower() in ("1", "true", "yes", "on"):
        return False
    node = _node_executable()
    if not (os.path.isfile(node) if os.path.isabs(node) else shutil.which(node)):
        return False
    bridge = _ts_bridge_dir()
    return (os.path.isfile(os.path.join(bridge, "find_refs.mjs"))
            and os.path.isdir(os.path.join(bridge, "node_modules", "ts-morph")))


def _run_ts_bridge(payload: dict, timeout: float) -> dict | None:
    """Run ts_bridge/find_refs.mjs (stdin JSON -> stdout JSON). Failure/malformed output/timeout -> None. Never raises.

    Uses bytes stdin (UTF-8), so non-ASCII paths sent via stdin don't get mangled the way PowerShell's
    Invoke-WebRequest can mangle them.
    CREATE_NO_WINDOW keeps the Node subprocess hidden on Windows.
    """
    bridge = _ts_bridge_dir()
    raw = json.dumps(payload).encode("utf-8")
    deadline_raw = os.environ.get("CODESEXTANT_ROUTE_DEADLINE_MONOTONIC")
    if deadline_raw:
        try:
            remaining = float(deadline_raw) - time.monotonic() - 0.1
        except (TypeError, ValueError):
            remaining = timeout
        if remaining <= 0:
            return None
        timeout = min(timeout, remaining)
    try:
        _kw = {"input": raw, "capture_output": True, "cwd": bridge, "timeout": timeout}
        if os.name == "nt":
            _kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        proc = subprocess.run([_node_executable(), os.path.join(bridge, "find_refs.mjs")], **_kw)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _shape_ts_one(symbol: str, r: dict) -> dict:
    """Normalize one bridge result to the common reference-result shape.

    Malformed entries are skipped and paths are normalized for persisted edge
    comparisons. Re-export flags remain available to orphan detection.
    """
    high = []
    reexport = 0
    for ref in (r.get("high_confidence") or []):
        if not isinstance(ref, dict) or not ref.get("src_path") or ref.get("line") is None:
            continue
        rx = bool(ref.get("is_reexport"))
        if rx:
            reexport += 1
        high.append({
            "src_path": os.path.normpath(ref["src_path"]),
            "line": ref["line"],
            "column": ref.get("column", 0),
            "confidence": "high",
            "is_reexport": rx,
        })
    definition = r.get("definition")
    if isinstance(definition, dict) and definition.get("path"):
        definition = {**definition, "path": os.path.normpath(definition["path"])}
    return {
        "symbol": symbol,
        "definition": definition,
        "high_confidence": high,
        "low_confidence": [],
        "name_match_file_count": 0,
        "name_match_hit_count": len(high),
        "candidates_scanned": 0,
        "truncated": False,
        "engine": "ts-morph",
        "reexport_count": reexport,
        "error": r.get("error"),
    }


def ts_morph_references(src_root: str, symbol: str, *, def_path: str | None,
                        timeout: float | None = None) -> dict | None:
    """High-confidence TS/JS import resolution for a single symbol (findReferences excludes same-name noise).

    Unavailable (no node / npm install not run / subprocess failure / timeout / definition not
    found / malformed output) -> returns None, and the caller falls back to name_match_references
    (low-confidence name matching). The function does not raise.

    When timeout is None, CODESEXTANT_TS_MORPH_TIMEOUT supplies the value, with a
    default of 30 seconds. A timeout falls back to name matching.
    """
    if not def_path or not ts_morph_available():
        return None
    if timeout is None:
        try:
            timeout = float(os.environ.get("CODESEXTANT_TS_MORPH_TIMEOUT", "30"))
        except ValueError:
            timeout = 30.0
    data = _run_ts_bridge({
        "projectRoot": os.path.abspath(src_root),
        "defFile": os.path.abspath(def_path),
        "symbol": symbol,
    }, timeout)
    if data is None:
        return None
    # ts-morph couldn't find the definition (error, no references) -> treat as unavailable, fall back to name matching (the common query case)
    if data.get("error") and not data.get("high_confidence"):
        return None
    try:
        return _shape_ts_one(symbol, data)
    except (KeyError, TypeError, AttributeError):
        return None


def ts_morph_references_batch(src_root: str, def_file: str, symbols,
                              *, timeout: float | None = None) -> dict | None:
    """Resolve multiple symbols from one file in a single Node process.

    Returns {symbol: result_dict|None}; ts-morph unavailable / subprocess failure / malformed
    output -> None (the caller falls back per-symbol or marks the whole batch UNKNOWN).
    The function does not raise.

    Key difference from the single-symbol version: an error does **not** return None, it returns
    a dict carrying the error; orphan detection wants "ts-morph couldn't locate it ->
    UNKNOWN_UNRESOLVED"; it must not fall back to name matching and pass off low-confidence junk as an answer.

    timeout: when None, reads env CODESEXTANT_TS_MORPH_BATCH_TIMEOUT (default 90 seconds; longer because batches have more symbols).
    """
    syms = [s for s in (symbols or []) if s]
    if not syms or not def_file or not ts_morph_available():
        return None
    if timeout is None:
        try:
            timeout = float(os.environ.get("CODESEXTANT_TS_MORPH_BATCH_TIMEOUT", "90"))
        except ValueError:
            timeout = 90.0
    data = _run_ts_bridge({
        "projectRoot": os.path.abspath(src_root),
        "defFile": os.path.abspath(def_file),
        "symbols": syms,
    }, timeout)
    if data is None:
        return None
    results = data.get("results")
    if not isinstance(results, dict):
        return None
    out: dict = {}
    for sym in syms:
        r = results.get(sym)
        try:
            out[sym] = _shape_ts_one(sym, r) if isinstance(r, dict) else None
        except (KeyError, TypeError, AttributeError):
            out[sym] = None
    return out
