"""Resolve symbol references with jedi, ts-morph, or name matching.

Python lookup uses a text prefilter followed by jedi resolution at each candidate
site. TypeScript and JavaScript use the ts-morph bridge when available. Other
languages return low-confidence name matches. The engine owns persistence and
result assembly.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

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


def _prefilter_candidate_files(src_root: str, symbol: str) -> list[str]:
    """Stage 1 (coarse filter): which files does the name appear in. Cheap and loose, so it is better to over-include a few.

    Returns every .py file that contains the symbol name (as a standalone word). jedi only does precise resolution on these.
    """
    pat = _word_re(symbol)
    candidates: list[str] = []
    for fp in _iter_python_files(src_root):
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        if pat.search(text):
            candidates.append(fp)
    return candidates


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


def _locate_definition_position(src_root: str, def_name: str,
                                def_path: str | None) -> tuple[str, int, int] | None:
    """Locate the def/class line for `def_name` in its definition file (jedi's get_references needs a starting point).

    If def_path is given, search only that file; otherwise search src_root for the first hit.
    Returns (path, line, column 1-based, pointing at the start of the name) or None.
    """
    pat = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(" + re.escape(def_name) + r")\b")
    search_files = [def_path] if def_path else list(_iter_python_files(src_root))
    for fp in search_files:
        if not fp or not os.path.exists(fp):
            continue
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                for i, line_text in enumerate(f, 1):
                    m = pat.match(line_text)
                    if m:
                        return (fp, i, m.start(1) + 1)
        except OSError:
            continue
    return None


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
    located = _locate_definition_position(src_root, symbol, def_path)
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
            # Does this occurrence point at the "target definition"?
            points_to_target = any(
                d.module_path
                and os.path.normcase(os.path.abspath(str(d.module_path))) == def_file_norm
                and d.line == def_line
                for d in defs
            )
            # Exclude "the definition's own line" (doesn't count as a reference)
            is_definition_site = (os.path.normcase(os.path.abspath(fp)) == def_file_norm
                                  and line == def_line)
            if points_to_target and not is_definition_site:
                result["high_confidence"].append({
                    "src_path": fp, "line": line, "column": col, "confidence": "high"})
            elif include_low_confidence and not is_definition_site:
                result["low_confidence"].append({
                    "src_path": fp, "line": line, "column": col, "confidence": "low",
                    "note": "name matches, but goto points at a different same-named symbol (not this definition)"})

    result["name_match_hit_count"] = total_hits
    return result


# Low-confidence reference lookup for languages without an import resolver.
_SKIP_DIRS_MULTI = (".git", "__pycache__", ".venv", "venv", "node_modules",
                    ".mypy_cache", ".pytest_cache", "build", "dist", "target", ".tox")


def _iter_files_by_ext(root: str, exts):
    """Scan files under root with the given extensions (skipping noise directories). Used by cross-language name matching."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS_MULTI]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in exts:
                yield os.path.join(dirpath, fn)


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


def ts_morph_available() -> bool:
    """node is on PATH and ts_bridge is ready (find_refs.mjs + node_modules/ts-morph).
    If either condition is unmet, the caller falls back to name matching.

    Set CODESEXTANT_TS_MORPH_DISABLED=1 to disable the Node subprocess."""
    if os.environ.get("CODESEXTANT_TS_MORPH_DISABLED", "").lower() in ("1", "true", "yes", "on"):
        return False
    if shutil.which("node") is None:
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
    try:
        _kw = {"input": raw, "capture_output": True, "cwd": bridge, "timeout": timeout}
        if os.name == "nt":
            _kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        proc = subprocess.run(["node", os.path.join(bridge, "find_refs.mjs")], **_kw)
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
