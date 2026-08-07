"""FieldRead-lite: CodeSextant's output compression layer (MIT, self-contained,
zero dependencies).

Why it exists: CodeSextant's long outputs (callgraph transitive chains, impact
with a pile of callers, map with a pile of symbols) eat tokens. The compression
idea comes from **FieldRead**: split the budget proportionally across semantic
namespaces, elide whatever exceeds the budget behind a breadcrumb (a one-line
path summary), and expand it on demand.

Why this is a local reimplementation rather than a dependency on the existing
FieldRead package (decided 2026-06-19):
  - Licences are contagious. That package is **AGPL-3.0** (a strong copyleft
    licence). Depending on it would pull CodeSextant from MIT to AGPL and kill
    the "anyone, and any agent, can use this" position outright. AGPL blocks
    commercial and closed-source integration.
  - The dependency tree balloons. It transitively requires two LLM SDKs and a
    full web framework. A code-map tool should not carry that just to make its
    output shorter.
  - The algorithm itself is simple (plain string and item handling), so carrying
    our own copy costs far less than either of the above.

⛔ The general lesson here: borrowing an *idea* does not spread a licence,
   borrowing *code* does. For a tool that wants to stay usable by anyone, the
   dependency list is a statement of position.

⛔ Do not copy aider's TreeContext (it only compresses code display). Use
FieldRead's semantic-partition idea, but partition by **code semantics**
(high confidence / low / test / prod / entrypoint / UNKNOWN). This is display-layer
compression only. The engine still returns the complete dict, --json/--full still
return everything, and only the human-readable summary is compressed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Section:
    """The pending content of one semantic partition.

    Higher priority means kept first and given more budget. min_keep is how many
    items are kept no matter what. Set it high on important partitions so they
    cannot be squeezed out.
    """
    name: str
    label: str
    items: list
    priority: int = 1
    min_keep: int = 0


@dataclass
class CompressedSection:
    name: str
    label: str
    shown: list
    elided: int   # how many were elided (behind the breadcrumb)
    total: int


def compress(sections: list[Section], *, budget: int, full: bool = False) -> list[CompressedSection]:
    """Compress by proportional per-partition budget, with an expandable breadcrumb
    (the core of FieldRead-lite).

    full=True, or a total item count <= budget, returns everything uncompressed.
    Otherwise:
      1. give every partition its min_keep first (so important ones cannot be
         squeezed out);
      2. distribute the remaining budget weighted by priority × remaining items
         (higher priority is served first and gets more);
      3. truncate whatever exceeds its allocation and record it in elided (the
         "…N more elided" breadcrumb).
    Returns list[CompressedSection] in the original partition order. budget <= 0 is
    treated as "keep min_keep only".
    """
    secs = list(sections)
    total = sum(len(s.items) for s in secs)
    if full or total <= max(0, budget):
        return [CompressedSection(s.name, s.label, list(s.items), 0, len(s.items)) for s in secs]

    alloc: dict[str, int] = {s.name: 0 for s in secs}

    # 1. min_keep first, a hard floor. Important partitions are kept even if that
    #    overruns the budget; min_keep is the "must be visible" guarantee.
    for s in secs:
        alloc[s.name] = min(s.min_keep, len(s.items))
    remaining = budget - sum(alloc.values())

    # 2. Distribute the rest weighted by priority × remaining items (higher priority served first).
    while remaining > 0:
        hungry = [s for s in secs if alloc[s.name] < len(s.items)]
        if not hungry:
            break
        wsum = sum(s.priority * (len(s.items) - alloc[s.name]) for s in hungry) or 1
        progressed = False
        for s in sorted(hungry, key=lambda x: -x.priority):
            if remaining <= 0:
                break
            want = max(1, round(remaining * s.priority * (len(s.items) - alloc[s.name]) / wsum))
            give = min(want, len(s.items) - alloc[s.name], remaining)
            if give > 0:
                alloc[s.name] += give
                remaining -= give
                progressed = True
        if not progressed:
            break

    out: list[CompressedSection] = []
    for s in secs:
        k = alloc[s.name]
        out.append(CompressedSection(s.name, s.label, list(s.items[:k]),
                                     len(s.items) - k, len(s.items)))
    return out


def render(sections: list[Section], *, budget: int, full: bool = False,
           item_fmt=str, indent: str = "  ") -> list[str]:
    """Compress, then render to text lines (partition heading + items + breadcrumb).
    Returns list[str].

    item_fmt is the function that turns a single item into its display string
    (default str). Empty partitions (total=0) are not printed.
    """
    lines: list[str] = []
    for cs in compress(sections, budget=budget, full=full):
        if cs.total == 0:
            continue
        head = f"{indent}{cs.label}: {cs.total}"
        if cs.elided:
            head += f" (showing {len(cs.shown)}, {cs.elided} elided; use --full to see all)"
        lines.append(head)
        for it in cs.shown:
            lines.append(f"{indent}  {item_fmt(it)}")
    return lines
