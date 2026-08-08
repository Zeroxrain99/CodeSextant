"""Build name-level reference edges for map ranking and unwired detection.

Without name-level edges:
  - index_project only extracts symbols and **builds no reference edges at all**. The
    refs table only gains high-confidence jedi/ts-morph edges once
    find_references(persist=True) has run against a symbol.
  - get_map → compute_pagerank consumes store.all_refs(). Out of the box refs=[], so
    everything rests on the uniform teleport P=[1/n] and every symbol ends up with an
    identical rank.

The implementation follows the repomap approach of building edges from name
intersections before running PageRank:
  - aider connects referencer→definer for any identifier that is both defined and
    referenced, then runs PageRank. CodeSextant's symbols table already holds every
    definition (the nodes); what is missing is "which defined names does each file
    use". Regex tokenization supplies those name-level edges, **body-aware**, so a
    definition's own self-tokens are excluded.

Safety constraints:
  1. **In-memory only**: name-level edges **must never be persisted to the refs
     table**. callgraph/impact/find_references all read that table, and persisting
     name-level edges would pollute their resolver-backed results with low-confidence
     same-name noise. Name-level edges are built on the spot inside get_map, fed to
     compute_pagerank, and discarded.
  2. **Always low confidence**: a plain textual intersection carries same-name
     interference plus string and comment noise, so every such edge is
     confidence="low" (compute_pagerank weights it 0.25). The database's high edges
     (real import resolution) keep weight 1.0 and still dominate; name-level edges
     only supply the structural floor for the "no edges out of the box" case.
  3. **Stay out of the four traps**: no embedding-based semantic similarity, no heavy
     LSP backend, no changes to symbols, no graph library. Just regex, a body-aware
     scan, and the existing pure-Python power iteration.

Body-aware matching:
  - For each identifier occurrence, **exclude self-tokens falling inside that
    definition's own [line, end_line] range** (the definition line and recursive
    self-calls), but **keep** occurrences inside other symbols in the same file and in
    other files.
  - The old approach, excluding a file's own defined names across the whole file,
    over-excluded: it erased genuine same-file mutual calls, so projects built around
    a single module or same-file calls ended up with zero name edges and fell straight
    back to a uniform distribution.
  - One cross-reference occurrence produces one edge, **with no deduplication**, so
    compute_pagerank accumulates naturally and "called more often means more
    important" affects the rank.

Constraints imposed by compute_pagerank (confirmed by reading ranking.py):
  - It only accepts edges that have both def_path and def_line, and whose
    (normcase(def_path), def_line) matches some symbol node's (path, line). Name-level
    edges therefore have to **fan out**: name X occurring in file F produces one edge
    (src_path=F, def_path=dp, def_line=dl, confidence=low) for every symbol (dp, dl)
    that defines X.
  - Paths are normcase(abspath) throughout (matching ranking._norm and
    storage.project_key), which removes a latent false negative where Windows
    case differences broke body exclusion. src_path is mapped through file_rep to that
    file's representative symbol; compute_pagerank skips self-loops (i==j) itself.
  Known limitation of the file-rep collapse: in single-file or same-file structures
    every edge source collapses onto that file's first symbol, so caller granularity
    ("who calls") is blurred, but "who is called" (the referenced symbol) still stands
    out and escapes the uniform distribution.

Switches accept case-insensitive values:
  - CODESEXTANT_NAMEGRAPH_DISABLED=1/true/yes/on → get_map builds no name-level edges
    (reverting to the degraded behaviour).
  - CODESEXTANT_NAMEGRAPH_MAX_FANOUT=<int>  fan-out cap for same-name definitions
    (default 20; stops a flooded name from producing a Cartesian explosion of edges).
  - CODESEXTANT_NAMEGRAPH_MAX_FILES=<int>   explicit file-scan count for map; when
    unset it adapts to the symbol count (12-5000).
  - CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES=<int> hard cap on unique edges (default
    250000; stops a single query from eating all available RAM).
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict

# Identifier token: starts with a letter or underscore, followed by letters, digits or
# underscores. Extract every identifier in a file in one pass, then intersect with the
# set of defined names. Keywords (def/class/if…) are simply absent from that set and
# drop out, so no keyword blacklist is needed. Same-name hits inside strings and
# comments are noise, suppressed four ways: the intersection with defined names, the
# low weight, the quality coefficient, and body-aware exclusion.
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, ""))
        return v if v > 0 else default
    except ValueError:
        return default


def namegraph_enabled() -> bool:
    """Whether name-level edges are enabled (on by default; CODESEXTANT_NAMEGRAPH_DISABLED turns them off)."""
    return not _env_on("CODESEXTANT_NAMEGRAPH_DISABLED")


def map_file_limit(symbol_count: int) -> tuple[int, bool]:
    """File-count cap for computing a large map on the fly; returns (limit, is_adaptive).

    An explicit CODESEXTANT_NAMEGRAPH_MAX_FILES always wins. When unset, the limit is a
    fixed work budget divided by symbol_count: small projects still scan all 5000 files,
    while a monorepo with 570k symbols lands at roughly 12 files, which gives a cold
    query a hard bound near 30 seconds instead of building several GB until the shell
    times out.
    """
    raw = os.environ.get("CODESEXTANT_NAMEGRAPH_MAX_FILES")
    if raw:
        try:
            explicit = int(raw)
            if explicit > 0:
                return explicit, False
        except ValueError:
            pass
    work_budget = _env_int("CODESEXTANT_NAMEGRAPH_MAP_WORK_BUDGET", 7_000_000)
    limit = work_budget // max(1, int(symbol_count))
    return min(5000, max(12, limit)), True


def _read_text(path: str) -> str | None:
    """Read a file as text (errors=replace, so it never raises); returns None if unreadable."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _normp(path: str) -> str:
    """Path normalization, normcase(abspath), matching ranking._norm and storage.project_key.

    Using normcase matters on Windows because
    'E:\\..\\M.py' and 'e:\\..\\m.py' name the same file yet compare unequal → body
    exclusion silently failed → self-tokens on the definition line were not excluded →
    real dead code went unreported. The whole module now uses normcase.
    """
    return os.path.normcase(os.path.abspath(path))


def _defs_by_name(symbols: list[dict]) -> dict[str, list[tuple[str, int, int]]]:
    """name → [(norm_path, line, end_line), ...]: which symbols define each name, where,
    and over what body range.

    Includes all symbols (methods, nested definitions, top-level variables), matching
    compute_pagerank's by_pos node set. end_line is what body-aware exclusion uses to
    drop self-tokens falling inside a symbol's own [line, end_line].
    """
    d: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    path_cache: dict[object, str] = {}
    for s in symbols:
        p = s.get("path")
        if p is None:
            continue
        try:
            np = path_cache[p]
        except KeyError:
            np = _normp(p)
            path_cache[p] = np
        line = s["line"]
        end_line = int(s.get("end_line", line) or line)
        d[s["name"]].append((np, line, end_line))
    return d


def _select_indexed_files(indexed_files, max_files, preferred_files=None):
    """Deterministic stratified sampling: focus files first, the rest spread evenly across
    the repo, so the scan never just looks at the prefix of the sort order."""
    files = list(indexed_files)
    limit = max(1, int(max_files))
    if len(files) <= limit:
        return files, "all"

    available = set(files)
    chosen: list[str] = []
    seen: set[str] = set()
    for path in preferred_files or []:
        np = _normp(path)
        if np in available and np not in seen:
            chosen.append(np)
            seen.add(np)
            if len(chosen) >= limit:
                return chosen, "focus"

    remaining = [p for p in files if p not in seen]
    slots = min(limit - len(chosen), len(remaining))
    if slots > 0:
        # Take the midpoint of each equal-width bucket: covers head, middle and tail, and is reproducible.
        for i in range(slots):
            index = min(len(remaining) - 1, int((i + 0.5) * len(remaining) / slots))
            path = remaining[index]
            if path not in seen:
                chosen.append(path)
                seen.add(path)
    return chosen, "stratified"


def _scan_cross_refs(symbols, indexed_files, read_text, max_fanout, max_files,
                     preferred_files=None):
    """The body-aware whole-repo scan (shared by build_name_edges and
    compute_external_usage, so the logic lives in one place).

    Returns (refs, defs, over_fanout, meta):
      refs = {(src_norm, src_line, name, def_norm, def_line): multiplicity}: every
             occurrence of a defined name that does **not** fall inside that
             definition's own body. Repeats of the same target on the same line fold
             into one entry while keeping the reference count. src_line records the
             real occurrence line, which lets compute_pagerank map the source to the
             actual caller symbol instead of collapsing it onto the file's first symbol.
      defs = the result of _defs_by_name. over_fanout = names whose same-name definition
             count exceeds the cap. meta = scan statistics.

    Body-aware: a token falling inside a definition's own [line, end_line] is not
    counted as a reference to it (this excludes self-tokens on the definition line and
    recursion); occurrences inside other symbols in the same file and in other files all
    count, which preserves genuine same-file mutual calls. over_fanout names are skipped
    entirely. ``max_files`` bounds work on very large repositories.
    """
    defs = _defs_by_name(symbols)
    over_fanout = {n for n, lst in defs.items() if len(lst) > max_fanout}
    target_names = set(defs) - over_fanout
    meta = {"defined_names": len(defs), "scanned_files": 0, "total_files": 0,
            "truncated": False, "over_fanout_names": len(over_fanout),
            "skipped_fanout_names": len(over_fanout), "sampling": "all",
            "truncation_reasons": []}
    if not target_names:
        return {}, defs, over_fanout, meta

    if indexed_files is None:
        indexed_files = sorted({_normp(s["path"]) for s in symbols if s.get("path")})
    else:
        indexed_files = [_normp(p) for p in indexed_files]
    meta["total_files"] = len(indexed_files)
    if len(indexed_files) > max_files:
        indexed_files, sampling = _select_indexed_files(
            indexed_files, max_files, preferred_files)
        meta["sampling"] = sampling
        meta["truncated"] = True
        meta["truncation_reasons"].append("file_budget")

    refs: dict[tuple[str, int, str, str, int], int] = {}
    max_unique_edges = _env_int("CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES", 250_000)
    edge_budget_hit = False
    for fp in indexed_files:
        text = read_text(fp)
        if not text:
            continue
        meta["scanned_files"] += 1
        for occ_line, line_text in enumerate(text.splitlines(), 1):
            names = Counter(
                m.group() for m in _IDENT_RE.finditer(line_text)
                if m.group() in target_names)
            for name, multiplicity in names.items():
                for (dp, dl, el) in defs[name]:
                    if fp == dp and dl <= occ_line <= el:
                        continue  # inside its own body → a self-token, not a reference
                    key = (fp, occ_line, name, dp, dl)
                    if key not in refs and len(refs) >= max_unique_edges:
                        edge_budget_hit = True
                        break
                    refs[key] = refs.get(key, 0) + multiplicity
                if edge_budget_hit:
                    break
            if edge_budget_hit:
                break
        if edge_budget_hit:
            break
    if edge_budget_hit:
        meta["truncated"] = True
        meta["truncation_reasons"].append("edge_budget")
    return refs, defs, over_fanout, meta


def build_name_edges(symbols: list[dict], *, indexed_files: list[str] | None = None,
                     read_text=_read_text, max_fanout: int | None = None,
                     max_files: int | None = None,
                     preferred_files: list[str] | None = None) -> tuple[list[dict], dict]:
    """Build the name-level whole-graph low-confidence edges that feed compute_pagerank.
    Body-aware: genuine same-file mutual calls are preserved, definition-line noise is not.

    Parameters
    ----------
    symbols : the project's full symbol list (store.get_symbols()); each entry needs
        path/name/line/end_line.
    indexed_files : the files to scan for "which names are used"; None means every path
        that appears in symbols.
    read_text : the file-reading function (injectable, which makes testing easy).
    max_fanout / max_files : override the corresponding env caps (None uses env or the
        default).

    Returns (edges, meta):
      edges = [{src_path, src_line, symbol_name, def_path, def_line, confidence:"low",
                multiplicity}, ...] (repeats of the same target on one line fold into a
                single edge, with multiplicity keeping the reference count).
      meta  = {defined_names, scanned_files, total_files, truncated, over_fanout_names,
               skipped_fanout_names, total_edges}
    No symbols, or no usable target names → ([], meta).
    """
    if max_fanout is None:
        max_fanout = _env_int("CODESEXTANT_NAMEGRAPH_MAX_FANOUT", 20)
    if max_files is None:
        max_files = _env_int("CODESEXTANT_NAMEGRAPH_MAX_FILES", 5000)
    refs, _defs, _over, meta = _scan_cross_refs(
        symbols, indexed_files, read_text, max_fanout, max_files, preferred_files)
    edges = [{
        "src_path": sp, "src_line": sl, "symbol_name": name,
        "def_path": dp, "def_line": dl, "confidence": "low",
        "multiplicity": multiplicity,
    } for (sp, sl, name, dp, dl), multiplicity in refs.items()]
    meta["unique_edges"] = len(edges)
    meta["total_edges"] = sum(refs.values())
    return edges, meta


def compute_external_usage(symbols: list[dict], *, indexed_files: list[str] | None = None,
                           read_text=_read_text, max_fanout: int | None = None,
                           max_files: int | None = None
                           ) -> tuple[dict[tuple, int], set[str], dict]:
    """Count mentions of each defined symbol outside its own body.

    Body-aware: self-tokens on the definition line and recursive self-calls are
    excluded; mentions inside other symbols in the same file and in other files are kept.
    Zero external usage means nothing outside the symbol's own body mentions this name,
    which makes it an unwired candidate.

    Limits of name-level matching:
      - Multiple definitions of one name: names alone cannot tell which definition a call
        refers to, so the genuinely unused one is credited with usage because somewhere
        else uses a different definition of the same name (an under-report).
      - Plain tokenization does not distinguish strings from comments: a symbol name
        appearing in any string or comment counts as external usage, so a genuinely
        unwired symbol can be under-reported because something mentions it in a string or
        comment. This errs toward caution and never toward wrongly deleting something.
    The result is low-confidence evidence and should be cross-checked with resolver-backed
    dead-code analysis.

    Returns (usage, over_fanout, meta):
      usage = {(norm_def_path, def_line, name): external_usage_count} (zeros included;
              only names whose fan-out is within the cap are counted).
      over_fanout = names whose same-name definition count exceeds the fan-out cap. These
              are not counted and are reported as UNKNOWN_FANOUT.
      meta = scan statistics, including whether file or edge limits truncated the scan.
    """
    if max_fanout is None:
        max_fanout = _env_int("CODESEXTANT_NAMEGRAPH_MAX_FANOUT", 20)
    if max_files is None:
        max_files = _env_int("CODESEXTANT_NAMEGRAPH_MAX_FILES", 5000)
    refs, defs, over_fanout, meta = _scan_cross_refs(
        symbols, indexed_files, read_text, max_fanout, max_files)
    usage: dict[tuple, int] = {}
    for name, lst in defs.items():
        if name in over_fanout:
            continue
        for (dp, dl, _el) in lst:
            usage[(dp, dl, name)] = 0
    for (_sp, _sl, name, dp, dl), multiplicity in refs.items():
        key = (dp, dl, name)
        if key in usage:
            usage[key] += multiplicity
    return usage, over_fanout, meta
