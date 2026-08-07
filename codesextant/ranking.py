"""Importance ranking module: PageRank for "the N most important symbols".

Design origin (borrowed from the PoC / aider repomap approach):
  - Treat each "defined symbol" as a graph node, and each reference edge
    (who uses whom) as a link.
  - A symbol referenced by more symbols that are themselves important is
    more important (PageRank's recursive definition).
  - aider's repomap uses the same graph-rank idea to pick which symbols
    are worth showing the LLM within a token budget.

The implementation deliberately uses plain Python power iteration instead
of pulling in a networkx/scipy dependency (keeps the engine lightweight
and easy to bundle into the daemon; power iteration at this scale is fast
enough even with tens of thousands of symbols).

Single responsibility: take a symbol list + a reference-edge list, emit
symbols sorted high to low by rank score. Does not touch SQLite, does not
touch jedi. All state is local to the functions, which makes them reentrant and
free of global pollution.
"""
from __future__ import annotations

import os
from bisect import bisect_right
from collections import Counter
from heapq import nlargest

# Weight of high-confidence reference edges (a jedi-confirmed target is more trustworthy
# than a name match, so it gets a higher weight)
_CONFIDENCE_WEIGHT = {"high": 1.0, "low": 0.25}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


def _well_named(name: str) -> bool:
    """Well-formed public symbol (underscore-separated or mixed case = snake/camel/Pascal)."""
    if name.startswith("_"):
        return False
    return ("_" in name) or (name != name.lower() and name != name.upper())


def _symbol_quality_mult(name: str, defines_count: int) -> float:
    """queue 5 (edge-weight symbol-quality factor, an aider-inspired heuristic): surfaces
    architecturally significant public APIs and downweights low-signal/generic symbols.

    Well-named public symbols (len>=threshold) get ×WELLNAMED; private, underscore-prefixed
    symbols get ×PRIVATE; symbols redefined in >N files (overly generic names like
    utils/handle/run) get ×COMMON. All configurable (L0 hard rule #6).
    """
    mult = 1.0
    if name.startswith("_"):
        mult *= _env_float("CODESEXTANT_RANK_PRIVATE_MULT", 0.1)
    elif len(name) >= _env_int("CODESEXTANT_RANK_WELLNAMED_MINLEN", 8) and _well_named(name):
        mult *= _env_float("CODESEXTANT_RANK_WELLNAMED_MULT", 10.0)
    if defines_count > _env_int("CODESEXTANT_RANK_COMMON_THRESHOLD", 5):
        mult *= _env_float("CODESEXTANT_RANK_COMMON_MULT", 0.1)
    return mult


def _build_personalization(symbols: list[dict], focus_symbols=None,
                           focus_files=None) -> dict | None:
    """queue 4 (query-aware PageRank): turns a caller-supplied focus set into a
    personalization vector.

    ⛔ The boost NEVER comes from listening to a conversation or calling an LLM. It only
    comes from the caller explicitly saying "I'm working on X" (focus_symbols/focus_files).
    This holds the zero-cloud / no-LLM hard rule: aider listens to chat because it is a chat
    frontend, CodeSextant is a tool that gets called, not one that eavesdrops.
    Symbols matching focus get their teleport weight boosted by `boost`x. No focus returns
    None (falls back to uniform teleport = the original static behavior).
    """
    fs = set(focus_symbols or [])
    ff = {_norm(f) for f in (focus_files or [])}
    if not fs and not ff:
        return None
    boost = _env_float("CODESEXTANT_PAGERANK_FOCUS_BOOST", 10.0)
    p: dict[str, float] = {}
    for s in symbols:
        w = 1.0
        if s.get("name") in fs:
            w += boost
        if _norm(s.get("path")) in ff:
            w += boost
        p[_symbol_id(s)] = w
    return p


def _symbol_id(sym: dict) -> str:
    """The symbol's unique identifier: path::scope::name::line.
    Including the line in the id avoids same-file same-name symbols (e.g. multiple
    getters/setters sharing a name) overwriting each other.
    """
    return f"{sym['path']}::{sym.get('scope', '')}::{sym['name']}::{sym['line']}"


def _norm(path: str | None) -> str:
    return os.path.normcase(os.path.abspath(path)) if path else ""


def _compute_pagerank_scores(symbols: list[dict], refs: list[dict],
                             *, damping: float = 0.85, max_iter: int = 100,
                             tol: float = 1.0e-6,
                             personalization: dict[str, float] | None = None
                             ) -> list[float]:
    """Run PageRank on the symbol graph, return a score list in the same order as symbols.

    Edge direction: src (the representative symbol of the file containing the reference) ->
    def (the referenced symbol's definition). PageRank flows score from the referencing end
    to the referenced end, so a symbol referenced by many important symbols scores high.
    When src can't be mapped to a symbol node (e.g. a module-level top-level call), it is
    counted as "external inflow" distributed evenly.

    queue 5: edge weight is further multiplied by the referenced symbol's quality factor
    (well-named public ×10 / private ×0.1 / overly generic ×0.1).
    queue 4: personalization ({symbol_id: preference weight}) feeds the teleport vector for
    query-aware ranking; None falls back to uniform teleport (the original static behavior,
    backward compatible).

    Returns [] for empty symbols. Uses list index as the internal node id; the public
    compute_pagerank only converts to string ids at the very end, while rank_symbols
    consumes the list directly, which avoids building two giant string dicts for a graph
    with 570K nodes.
    """
    if not symbols:
        return []

    n = len(symbols)

    # namegraph can already fold repeated occurrences on the same line via multiplicity;
    # older db edges lacking this field are treated as 1.
    # Aggregating before building the graph preserves the original weights while letting
    # everything downstream work with unique edges only.
    collapsed_refs: dict[tuple, int] = {}
    for e in refs:
        key = (e.get("src_path"), e.get("src_line"), e.get("def_path"),
               e.get("def_line"), e.get("confidence", "low"))
        try:
            multiplicity = int(e.get("multiplicity", 1) or 1)
        except (TypeError, ValueError):
            multiplicity = 1
        if multiplicity < 1:
            multiplicity = 1
        collapsed_refs[key] = collapsed_refs.get(key, 0) + multiplicity

    # Path normalization is not cheap on Windows; 570K symbols are typically spread across
    # tens of thousands of files, so caching by the original string avoids the same path
    # being recomputed by os.path.abspath dozens of times across the defines/by_pos/by_body
    # layers.
    norm_cache: dict[object, str] = {}

    def _norm_cached(path) -> str:
        if not path:
            return ""
        try:
            return norm_cache[path]
        except KeyError:
            value = _norm(path)
            norm_cache[path] = value
            return value

    target_positions = {
        (_norm_cached(dp), dl)
        for (_sp, _sl, dp, dl, _confidence) in collapsed_refs
        if dp is not None and dl is not None
    }
    source_paths = {
        _norm_cached(sp)
        for (sp, _sl, _dp, _dl, _confidence) in collapsed_refs
        if sp
    }

    # Build the position tables only for the target/source of actual reference edges. The
    # old version built by_pos/by_body for all 570K symbols, paying the full-graph dict/list
    # cost even when the graph only had a few thousand edges.
    by_pos: dict[tuple, int] = {}
    target_name_of: dict[int, str] = {}
    file_rep: dict[str, int] = {}
    file_rep_line: dict[str, int] = {}
    by_body: dict[str, list] = {}
    for pos, s in enumerate(symbols):
        p = s.get("path")
        if p is None:
            continue
        np = _norm_cached(p)
        line = s["line"]
        if (np, line) in target_positions:
            by_pos[(np, line)] = pos
            target_name_of[pos] = s["name"]
        if np in source_paths:
            if np not in file_rep_line or line < file_rep_line[np]:
                file_rep[np] = pos
                file_rep_line[np] = line
            by_body.setdefault(np, []).append(
                (line, int(s.get("end_line", line) or line), pos))
    for lst in by_body.values():
        lst.sort()
    body_starts = {path: [row[0] for row in rows] for path, rows in by_body.items()}
    src_node_cache: dict[tuple[str, int], int | None] = {}

    # queue 5: only compute, for names that actually become edge targets, how many distinct
    # files define them; the other 570K nodes never use the quality factor, so there's no
    # need to build a full name->file set.
    target_names = set(target_name_of.values())
    _seen_np: set = set()
    defines: Counter[str] = Counter()
    if target_names:
        for s in symbols:
            name = s["name"]
            if name not in target_names:
                continue
            k = (name, _norm_cached(s.get("path")))
            if k not in _seen_np:
                _seen_np.add(k)
                defines[name] += 1

    def _src_node(src_path, src_line):
        """Maps src_line to "the innermost symbol that contains it" as the source node; no
        src_line / not found -> falls back to file_rep (backward compatible: db
        high-confidence edges carry src_line = a more precise caller; src_line=0 falls back
        to file_rep)."""
        np = _norm_cached(src_path) if src_path else ""
        cache_key = (np, int(src_line or 0))
        if cache_key in src_node_cache:
            return src_node_cache[cache_key]
        if src_line and np in by_body:
            rows = by_body[np]
            pos = bisect_right(body_starts[np], src_line) - 1
            while pos >= 0:
                ln, el, node_index = rows[pos]
                if ln <= src_line <= el:
                    src_node_cache[cache_key] = node_index
                    return node_index
                pos -= 1
        result = file_rep.get(np)
        src_node_cache[cache_key] = result
        return result

    # Build the sparse weighted adjacency out_targets[i] = {j: summed_weight}; only sources
    # with an edge occupy a dict entry.
    # namegraph keeps every occurrence to express reference counts, so the same
    # caller->target pair can end up with tens of thousands of duplicate edges. PageRank
    # only needs the total weight: aggregating first preserves the exact same math while
    # avoiding walking every occurrence on every iteration (a large TS repo once made
    # /get_map exceed the client's 30s timeout because of this).
    out_targets: dict[int, dict[int, float]] = {}
    external_inflow: dict[int, float] = {}
    quality_cache: dict[tuple[str, int], float] = {}

    for (src_path, src_line, dp, dl, confidence), multiplicity in collapsed_refs.items():
        if dp is None or dl is None:
            continue
        j = by_pos.get((_norm_cached(dp), dl))
        if j is None:
            continue
        w = _CONFIDENCE_WEIGHT.get(confidence, 0.25) * multiplicity
        # queue 5: multiply in the referenced symbol's quality factor (well-named public
        # ×10 / private ×0.1 / overly generic ×0.1)
        tname = target_name_of.get(j, "")
        quality_key = (tname, defines.get(tname, 1))
        try:
            quality = quality_cache[quality_key]
        except KeyError:
            quality = _symbol_quality_mult(*quality_key)
            quality_cache[quality_key] = quality
        w *= quality

        i = _src_node(src_path, src_line)
        if i is None:
            external_inflow[j] = external_inflow.get(j, 0.0) + w
            continue
        if i == j:
            continue
        edges = out_targets.setdefault(i, {})
        edges[j] = edges.get(j, 0.0) + w

    n_refs = max(1, sum(collapsed_refs.values()))
    # queue 4: personalization teleport vector P (focus preference); otherwise uniform 1/n
    # (original static behavior, backward compatible)
    if personalization:
        raw_p = [personalization.get(_symbol_id(s), 1.0) for s in symbols]
        tot_p = sum(raw_p) or 1.0
        P = [value / tot_p for value in raw_p]
    else:
        P = [1.0 / n] * n
    # Pre-normalize the sparse transition. When there are no usable edges/external inflow,
    # P itself is the fixed point.
    transitions: dict[int, list[tuple[int, float]]] = {}
    for i, edges in out_targets.items():
        total_w = sum(edges.values())
        if total_w > 0:
            transitions[i] = [(j, w / total_w) for j, w in edges.items()]
    active = set(external_inflow)
    active.update(out_targets)
    for edges in out_targets.values():
        active.update(edges)
    if not active:
        return P

    # For isolated nodes with no in/out edges at all, the score is always the same
    # scalar x P[j]. Aggregate hundreds of thousands of isolated nodes into a single
    # inactive_factor state; each round only walks active endpoints, and the full result
    # is materialized only at the end.
    active_p_sum = sum(P[i] for i in active)
    inactive_p_sum = max(0.0, 1.0 - active_p_sum)
    inactive_factor = 1.0
    active_score = {i: P[i] for i in active}

    for _ in range(max_iter):
        dangling_sum = inactive_factor * inactive_p_sum
        for i in active:
            if i not in transitions:
                dangling_sum += active_score[i]

        base_factor = (1.0 - damping) + damping * dangling_sum
        new_active = {i: base_factor * P[i] for i in active}
        for i, edges in transitions.items():
            source_score = active_score[i]
            for j, portion in edges:
                new_active[j] += damping * source_score * portion
        for j, infl in external_inflow.items():
            new_active[j] += damping * infl / n_refs

        delta = sum(abs(new_active[i] - active_score[i]) for i in active)
        delta += abs(base_factor - inactive_factor) * inactive_p_sum
        active_score = new_active
        inactive_factor = base_factor
        if delta < tol:
            break

    return [
        active_score[i] if i in active_score else inactive_factor * P[i]
        for i in range(n)
    ]


def compute_pagerank(symbols: list[dict], refs: list[dict],
                     *, damping: float = 0.85, max_iter: int = 100,
                     tol: float = 1.0e-6,
                     personalization: dict[str, float] | None = None) -> dict[str, float]:
    """Public compatibility layer: run PageRank on the symbol graph, return {symbol_id: score}."""
    scores = _compute_pagerank_scores(
        symbols, refs, damping=damping, max_iter=max_iter, tol=tol,
        personalization=personalization)
    return {_symbol_id(s): scores[i] for i, s in enumerate(symbols)}


def _line_of(sid: str) -> int:
    """Extract the line from a symbol_id (id format path::scope::name::line)."""
    try:
        return int(sid.rsplit("::", 1)[1])
    except (IndexError, ValueError):
        return 1 << 30


def rank_symbols(symbols: list[dict], refs: list[dict], *, top_n: int | None = None,
                 damping: float = 0.85, focus_symbols=None, focus_files=None) -> list[dict]:
    """Rank symbols by importance, return a symbol list with a "rank" score, sorted high to low.

    Each returned dict = the original symbol fields + "rank" (a float score). If top_n is
    given, only the top N are returned.
    focus_symbols/focus_files (queue 4, query-aware): the caller explicitly passes "the
    symbols/files being edited or asked about" to bias ranking toward relevant areas
    (converted into a personalization vector); omitted = the original static
    structural-centrality ranking.
    """
    personalization = _build_personalization(symbols, focus_symbols, focus_files)
    scores = _compute_pagerank_scores(
        symbols, refs, damping=damping, personalization=personalization)
    if top_n is not None:
        # A map usually only needs the top 100~200; don't copy all 570K dicts and sort
        # everything first.
        chosen = nlargest(
            top_n, enumerate(symbols),
            key=lambda item: (scores[item[0]], -item[0]),
        )
        return [dict(s, rank=scores[i]) for i, s in chosen]
    ranked = [dict(s, rank=scores[i]) for i, s in enumerate(symbols)]
    ranked.sort(key=lambda x: x["rank"], reverse=True)
    return ranked
