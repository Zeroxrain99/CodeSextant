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
import textwrap

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
             + (f"  symbol={result['symbol']}" if result.get("symbol") else ""),
             *scope_lines()]

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
        # **The denominator belongs in the headline.** "5 files usually change with this
        # one" reads as the set; "5 of 47 that history has seen change with it" reads
        # as a ranking, which is what it is. Same data, and only one of them lets a
        # reader stop looking.
        shown = len(result["co_change"])
        pool = result.get("co_change_pool") or 0
        headline = (
            f"{shown} of {pool} file(s) history has seen change with this one, "
            "strongest first"
            if pool > shown else f"{shown} file(s) usually change with this one")
        if scoped:
            headline += (f"; {scoped} keyed to {result['symbol']} rather than the whole file")
        lines.append(f"\n  CO-CHANGE        {headline}")
        for entry in result["co_change"]:
            marker = f"{result['symbol']}  " if entry["scope"] == "symbol" else ""
            lines.append(
                f"    {entry['confidence'] * 100:3.0f}%  "
                f"({entry['support']}/{entry['changes']} commits)  {marker}-> {entry['path']}")

    blast = result.get("blast_radius") or {}
    resolution = blast.get("resolution") or {}
    # When preflight spent real time resolving, say how much. A cost that only shows up
    # as the call feeling slow is a cost nobody can decide about.
    spent = (f"  (resolved in {resolution['elapsed_sec']}s)"
             if resolution.get("status") == "resolved" and resolution.get("elapsed_sec")
             else "")
    leads = blast.get("name_match_files") or []
    importers = blast.get("module_dependents") or []
    if blast.get("dependent_files") or leads or importers:
        headline = (f"{blast['dependent_count']} file(s) with resolved references"
                    if blast.get("dependent_files") else "nothing resolved")
        # Every count here is "shown of found", never just "shown". These two tiers are
        # the thinnest in the answer -- measured at 0.056 and 0.000 companions per
        # printed line against co-change's density -- so what they mostly owe a reader
        # is an honest denominator and a pointer, not a long list.
        if leads:
            headline += f"; {len(leads)} of {blast['name_match_count']} that name it"
        if importers:
            total = importers[0].get("of") or len(importers)
            headline += f"; {len(importers)} of {total} that import the module"
        lines.append(f"\n  BLAST RADIUS     {headline}{spent}")
        for dependent in blast.get("dependent_files") or []:
            lines.append(f"    {short(dependent, root)}")
        # Leads are marked so they cannot be read as callers. Printing them in one
        # undifferentiated list would be the inflation of confidence this tool exists
        # to avoid.
        for lead in leads:
            lines.append(f"    ?  {short(lead, root)}")
        # A third claim again: these name the module, not the symbol. Marked and
        # labelled rather than folded into the leads above them.
        for importer in importers:
            lines.append(f"    ?  {importer['path']}   (imports this module)")

    lines.extend(budget_lines(result))
    for note in result.get("notes") or []:
        lines.append(f"\n  Note: {note}")
    return lines


# **What this answer is, printed where it is read rather than in a manual.** The failure
# this exists to prevent is the one that makes a tool worse than no tool: a list that
# looks like the answer, so the reader stops looking and ships the thing it left out.
#
# Every clause is measured. `docs/audit.md` replayed E2's real invocations against the
# files those twenty commits actually touched: this named 12 of 60 where the developer
# changed 40, and of the 26 that were configuration or CI wiring it named 1. Naming the
# blind spots beats a general disclaimer, because a reader can act on "config is not
# indexed" and cannot act on "results may be incomplete".
_SCOPE = (
    "git history and resolved Python references. Config, CI and build wiring are not "
    "indexed, and a file that does not exist yet cannot be named. Measured on 20 real "
    "changes in flask/pytest/alembic this named 12 of 60 companion files where the "
    "developer changed 40 -- so it is where to start looking, not the list of what "
    "must change.")


_CHECK_SCOPE = (
    "your diff against git history and resolved Python references. Config, CI and "
    "build wiring are not indexed. Five heuristics, every one of which can be silent "
    "when it should not be -- so a short answer here is not a short list of problems, "
    "and an empty one is not a clean bill of health.")


def scope_lines(text: str | None = None) -> list[str]:
    """The scope statement, wrapped, as the second thing in every answer.

    Second rather than last on purpose: a caveat printed under a list is read as a
    footnote to it, and the same words printed above are read as the frame it belongs
    in. Nothing below this line means more than this line allows.
    """
    body = textwrap.wrap(text or _SCOPE, width=76)
    return [f"\n  SCOPE            {body[0]}"] + [f"                   {rest}"
                                                  for rest in body[1:]]


def budget_lines(result: dict) -> list[str]:
    """What the token budget removed, by kind, or nothing when it removed nothing.

    `truncated_by_budget` was computed and never rendered, so a list the budget had cut
    to three looked exactly like a list that had three in it. That is the same failure
    as the missing denominator and it is the one a caller can do least about, because
    nothing in the answer hints that anything is missing.
    """
    dropped = result.get("dropped_by_budget") or {}
    if not dropped:
        return []
    parts = ", ".join(f"{count} {kind}" for kind, count in sorted(dropped.items()))
    return [f"\n  Note: the token budget cut {parts} from this answer. What is shown "
            f"is the strongest of each, not all of it."]


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


def guards_lines(result: dict, root: str | None = None) -> list[str]:
    """The fences this change meets, in the two layers that are cheap to read.

    Two things, in the order a reader needs them. First what runs against every push --
    the CI jobs, the pre-commit hooks, the lint rules, the language floor -- which is
    short, always true, and the one place this tool does not rank anything, because
    relevance has the same answer every time.

    Then the fences this particular change reaches. Layer one is the heading line --
    kind, name, where. Layer two is the rule beneath it, and the reason when the author
    left one, marked with where it came from: a docstring is the author speaking and a
    derived rule is the tool speaking, and a reader deciding whether to satisfy a fence
    or move it needs to know which. Layer three is the source, printed only when it was
    asked for.
    """
    lines: list[str] = []
    forced = result.get("in_force") or []
    if forced:
        # Printed first and printed whole. It is short, it is true of every change, and
        # a reader who is about to be stopped by a lint rule or a Python floor is helped
        # more by seeing it than by seeing a sixth ranked test. exp10 measured the
        # population at 4-15 per repository, which is what makes "print it all" the
        # cheap option rather than the reckless one.
        lines.append(f"In force on every push: {len(forced)}")
        for gate in forced:
            # Same two-line shape as a guard below -- what and where on the heading,
            # the rule beneath it -- so the eye reads one block, not two formats.
            lines.append(f"\n  {gate['kind'].upper():11}  {gate['name']}"
                         f"   {gate['path']}")
            lines.append(f"    runs     {gate['rule']}")
        lines.append("")

    found = result.get("guards") or []
    total = result.get("total_in_reach", len(found))
    if not found:
        lines.append("Guards: none in reach of this change")
    else:
        more = f", showing {len(found)}" if total > len(found) else ""
        lines.append(f"Guards: {total} in reach of this change{more}")
    for entry in found:
        lines.append(f"\n  {entry['kind'].upper():11}  {entry['name'] or '—'}"
                     f"   {entry['path']}:{entry['line']}")
        lines.append(f"    checks   {entry['rule']}")
        if entry.get("reason"):
            # "why it exists" and "what it does" are different claims, and the corpus
            # says the first is missing four times in five. Where it exists, say so, and
            # say who said it.
            lines.append(f"    because  {entry['reason']}  ({entry['reason_source']})")
        # The history tier rests on a file-level claim rather than on the fence's own
        # text, so the strength of that claim is printed with it. A reader who sees
        # "0.42" weighs it differently from one who sees "0.91", and hiding the number
        # would make the weakest tier read like the strongest.
        confidence = entry.get("history_confidence")
        strength = f"  ({confidence} confidence)" if confidence else ""
        lines.append(f"    reached  {entry['why']}{strength}")
        if entry.get("source"):
            for source_line in entry["source"].splitlines():
                lines.append(f"      | {source_line}")

    for note in result.get("notes") or []:
        lines.append(f"\n  Note: {note}")
    return lines


def check_lines(result: dict, root: str | None = None) -> list[str]:
    """What the change already made looks like it forgot."""
    lines = [f"Check: {result.get('changed_count', 0)} file(s) changed",
             *scope_lines(_CHECK_SCOPE)]

    # First, because it is the only section about something that is no longer there.
    # The other four say what the change might have forgotten to add; a fence with a
    # stated reason that has just gone is a decision somebody is making right now,
    # possibly without knowing it, and it reads before the guesses.
    if result.get("removed_guards"):
        gone = [e for e in result["removed_guards"] if e["change"] == "removed"]
        weak = [e for e in result["removed_guards"] if e["change"] == "weakened"]
        summary = " and ".join(
            part for part in (f"{len(gone)} removed" if gone else "",
                              f"{len(weak)} loosened" if weak else "") if part)
        lines.append(f"\n  FENCES GONE      {summary} -- each had a reason written "
                     "beside it")
        for entry in result["removed_guards"]:
            label = entry["name"] or f"({entry['kind']})"
            verb = "removed" if entry["change"] == "removed" else "loosened"
            lines.append(f"    {verb}  {entry['kind']} {label}  "
                         f"{entry['path']}:{entry['line']}")
            lines.append(f"      was: {entry['rule']}")
            if entry.get("now"):
                lines.append(f"      now: {entry['now']}")
            # Verbatim, and attributed. A reader deciding whether to put the fence back
            # needs the author's sentence, not a paraphrase of it.
            lines.append(f"      [{entry['reason_source']}] {entry['reason']}")

    if result.get("rebuilt"):
        lines.append(f"\n  REBUILT          {len(result['rebuilt'])} changed unit(s) "
                     "repeat a shape already in the index")
        for entry in result["rebuilt"]:
            size = f"  ({entry['size']} nodes)" if entry.get("size") else ""
            lines.append(f"    {entry['name']}  {entry['path']}:{entry['line']}{size}")
            for match in entry["matches"]:
                lines.append(f"      already exists as  {match['name']}  "
                             f"{match['path']}:{match['line']}")

    if result.get("companions"):
        lines.append(f"\n  COMPANIONS       {len(result['companions'])} file(s) history "
                     "says follow what you changed, and you did not change")
        for entry in result["companions"]:
            lines.append(f"    {entry['confidence'] * 100:3.0f}%  "
                         f"({entry['support']}/{entry['changes']} commits)  "
                         f"{entry['path']}   <- {entry['because']}")

    if result.get("callers"):
        lines.append(f"\n  CALLERS          {len(result['callers'])} changed symbol(s) "
                     "have resolved callers outside your diff")
        for entry in result["callers"]:
            shown = ", ".join(entry["callers"][:4])
            more = (f" (+{entry['count'] - 4} more)" if entry["count"] > 4 else "")
            lines.append(f"    {entry['symbol']}  ({entry['defined_in']})  -> {shown}{more}")

    if result.get("dependents"):
        # Marked, and under its own heading, because importing a module you changed is
        # not the same claim as calling a function you changed. Printing the two in one
        # list would read as more confirmation than there is -- the same reason
        # preflight marks its leads.
        lines.append(f"\n  DEPENDENTS       {len(result['dependents'])} file(s) import "
                     "what you changed; unconfirmed, nothing resolved to them")
        for entry in result["dependents"]:
            imports = (f"  ({entry['imports']} of the changed modules)"
                       if entry.get("imports", 0) > 1 else "")
            lines.append(f"    ?  {entry['path']}{imports}")

    lines.extend(budget_lines(result))
    for note in result.get("notes") or []:
        lines.append(f"\n  Note: {note}")
    return lines
