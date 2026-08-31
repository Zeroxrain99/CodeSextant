"""Turn engine results into the compact text an agent reads.

Every renderer here answers the same question: what would a caller need to see to
act, and what would it need to see to *doubt* the answer? Counts, confidences and
"nothing found" notes are part of the rendering rather than an afterthought,
because a reader who cannot tell a weak claim from a strong one cannot weigh it.

Renderers return a list of lines. ``codesextant preflight`` and the MCP
``preflight`` tool share :func:`preflight_lines` verbatim, so the two surfaces
cannot describe the same result differently.
"""
from __future__ import annotations

import os

# Lists are capped so a single answer cannot crowd out an agent's context. The
# renderer always says how many entries it withheld: a silent cut reads as
# "there were only five", which is a different and wrong answer.
_MAX_ROWS = 20


def short(path: str, root: str | None) -> str:
    """Path relative to the project root, or unchanged when that is not possible."""
    if not path or not root:
        return path or ""
    try:
        relative = os.path.relpath(path, os.path.abspath(root))
    except ValueError:  # different drive on Windows
        return path
    return path if relative.startswith("..") else relative


def _elided(lines: list[str], total: int, noun: str, indent: str = "  ") -> None:
    if total > _MAX_ROWS:
        lines.append(f"{indent}… and {total - _MAX_ROWS} more {noun}")


def preflight_lines(result: dict, root: str | None = None) -> list[str]:
    """The three pillars: what already exists, what changes with it, who breaks."""
    lines = [f"Preflight {short(result['target'], root)}"
             + (f"  symbol={result['symbol']}" if result.get("symbol") else "")]

    if result.get("already_exists"):
        lines.append(f"\n  ALREADY EXISTS   {len(result['already_exists'])} similar definition(s)")
        for entry in result["already_exists"]:
            here = "  (this file)" if entry["same_file"] else ""
            lines.append(f"    {entry['similarity']:.2f}  [{entry['kind']:8}] {entry['name']:28} "
                         f"{short(entry['path'], root)}:{entry['line']}{here}")
    elif result.get("symbol"):
        lines.append("\n  ALREADY EXISTS   nothing resembles it; it looks new")

    if result.get("co_change"):
        scoped = sum(1 for e in result["co_change"] if e["scope"] == "symbol")
        headline = f"{len(result['co_change'])} file(s) usually change with this one"
        if scoped:
            headline += (f"; {scoped} keyed to {result['symbol']} rather than the whole file")
        lines.append(f"\n  CO-CHANGE        {headline}")
        for entry in result["co_change"]:
            marker = f"{result['symbol']}  " if entry["scope"] == "symbol" else ""
            lines.append(
                f"    {entry['confidence'] * 100:3.0f}%  "
                f"({entry['support']}/{entry['changes']} commits)  {marker}-> {entry['path']}")

    blast = result.get("blast_radius") or {}
    if blast.get("dependent_files"):
        lines.append(f"\n  BLAST RADIUS     {blast['dependent_count']} file(s) with "
                     "resolved references")
        for dependent in blast["dependent_files"]:
            lines.append(f"    {short(dependent, root)}")

    for note in result.get("notes") or []:
        lines.append(f"\n  Note: {note}")
    return lines


def map_lines(result: dict, root: str | None = None) -> list[str]:
    symbols = result.get("symbols") or []
    lines = [f"Code map: the {result.get('count', len(symbols))} most important symbols "
             f"(token budget {result.get('token_budget')} ≈ {result.get('approx_tokens')})"]
    if result.get("note"):
        lines.append(f"  Note: {result['note']}")
    for i, entry in enumerate(symbols[:_MAX_ROWS], 1):
        scope = f"{entry['scope']}." if entry.get("scope") else ""
        lines.append(f"  {i:3}. [{entry['rank']:.4f}] [{entry['kind']:8}] {scope}{entry['name']:28} "
                     f"{short(entry['path'], root)}:{entry['line']}")
    _elided(lines, len(symbols), "symbol(s), lower-ranked")
    return lines


def references_lines(result: dict, root: str | None = None) -> list[str]:
    lines = [f"References to '{result['symbol']}'"]
    if result.get("error"):
        lines.append(f"  Warning: {result['error']}")
    definition = result.get("definition")
    if definition:
        lines.append(f"  Definition: {short(definition['path'], root)}:{definition['line']}")
    high = result.get("high_confidence") or []
    lines.append(f"  High confidence (import-resolved): {len(high)}")
    for ref in high[:_MAX_ROWS]:
        lines.append(f"    {short(ref['src_path'], root)}:{ref['line']}:{ref['column']}")
    _elided(lines, len(high), "reference(s)")
    low = result.get("low_confidence") or []
    lines.append(f"  Name matching alone would sweep in {result.get('name_match_file_count', 0)} "
                 f"file(s); {len(low)} file(s) are name-only matches, not resolved")
    candidates = result.get("candidate_definitions") or []
    if len(candidates) > 1:
        lines.append(f"  Warning: {len(candidates)} definitions share this name; pass def_path "
                     "to say which one you mean:")
        for candidate in candidates[:10]:
            lines.append(f"    {short(candidate['path'], root)}:{candidate['line']} "
                         f"(scope={candidate['scope'] or 'module top level'})")
    reliability = result.get("reliability") or {}
    if reliability.get("level"):
        lines.append(f"  Reliability {reliability['level']}: {reliability.get('advice')}")
    return lines


def impact_lines(result: dict, root: str | None = None) -> list[str]:
    summary = result.get("summary") or {}
    lines = [f"Change impact: editing '{result['symbol']}' affects "
             f"{summary.get('total_confirmed_affected', 0)} symbol(s) "
             f"({summary.get('direct', 0)} direct / {summary.get('transitive', 0)} transitive)",
             f"  prod={summary.get('prod', 0)} test={summary.get('test', 0)} "
             f"entrypoint={summary.get('entrypoint', 0)} "
             f"high_importance={summary.get('high_importance', 0)} "
             f"uncertain={summary.get('uncertain', 0)}"]
    important = result.get("high_importance_affected") or []
    for entry in important[:_MAX_ROWS]:
        lines.append(f"  High importance: {entry['name']} @ "
                     f"{short(entry['path'], root)}:{entry['line']}")
    _elided(lines, len(important), "high-importance symbol(s)")
    if result.get("error"):
        lines.append(f"  Warning: {result['error']}")
    return lines


def symbols_lines(result: dict, root: str | None = None) -> list[str]:
    symbols = result.get("symbols") or []
    lines = [f"Symbols: {result.get('count', len(symbols))}"]
    if result.get("note"):
        lines.append(f"  Note: {result['note']}")
    for entry in symbols[:_MAX_ROWS]:
        scope = f"{entry['scope']}." if entry.get("scope") else ""
        lines.append(f"  [{entry['kind']:8}] {scope}{entry['name']:30} "
                     f"{short(entry['path'], root)}:{entry['line']}")
    _elided(lines, len(symbols), "symbol(s)")
    return lines


def duplicates_lines(result: dict, root: str | None = None) -> list[str]:
    summary = result.get("summary") or {}
    groups = result.get("groups") or []
    lines = [f"Duplicates: scanned {summary.get('total_units_scanned', 0)} unit(s) → "
             f"EXACT {summary.get('exact', 0)} / RENAMED {summary.get('renamed', 0)} / "
             f"NEAR {summary.get('structural_near', 0)} / CALL {summary.get('call_pattern', 0)}"]
    for group in groups[:_MAX_ROWS]:
        members = ", ".join(f"{short(m['path'], root)}:{m['line']} {m['name']}"
                            for m in group["members"])
        similarity = f" sim={group['similarity']}" if group.get("similarity") is not None else ""
        lines.append(f"  {group['verdict']}{similarity}: {members}")
    _elided(lines, len(groups), "group(s)")
    if result.get("verification_reminder"):
        lines.append(f"  Note: {result['verification_reminder']}")
    return lines


def status_lines(result: dict, root: str | None = None) -> list[str]:
    if not result.get("indexed"):
        return [f"Not indexed yet: {result.get('repo_path')}",
                "  Call the index tool once; after that the index updates incrementally."]
    lines = [f"Project {result.get('repo_path')}",
             f"  {result.get('indexed_files', 0)} file(s) / {result.get('symbols', 0)} symbol(s) / "
             f"{result.get('refs', 0)} resolved reference edge(s)"]
    if result.get("git_stale"):
        lines.append("  The index is behind git HEAD; call the index tool to catch it up.")
    return lines


def index_lines(result: dict, root: str | None = None) -> list[str]:
    lines = [f"Indexed: {result.get('indexed', 0)} file(s) recomputed / "
             f"{result.get('skipped', 0)} unchanged / {result.get('removed', 0)} removed / "
             f"{result.get('errors', 0)} with errors",
             f"  {result.get('symbols_total', 0)} symbols total, "
             f"{result.get('elapsed_sec', 0)}s elapsed"]
    for failed in (result.get("error_files") or [])[:5]:
        lines.append(f"  [error] {short(failed['path'], root)}: {failed['error']}")
    return lines
