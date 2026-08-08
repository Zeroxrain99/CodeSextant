"""Dependency-free output compression based on semantic partitions.

Long call graphs, impact results, and repository maps can exceed an agent's context
budget. This module allocates a display budget across semantic partitions, replaces
overflow with a short breadcrumb, and supports full output on demand.

The partitioning idea comes from FieldRead, but this implementation is original and
self-contained. It does not copy FieldRead or aider code, and it avoids FieldRead's
AGPL-3.0 package and transitive application dependencies. Compression affects only the
human-readable summary. The engine dictionary and ``--json`` or ``--full`` output remain
complete.
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
