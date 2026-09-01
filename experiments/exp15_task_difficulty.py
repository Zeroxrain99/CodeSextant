"""Which prevention tasks could a grep have solved, and which could not?

The pilot A/B tied. One agent had CodeSextant, one had only grep, and both edited the
same four files -- because the symbol that linked them, `explain_ignored_app_run`, is
distinctive enough that one grep finds it.

That is a real answer for that task and it raises the question this file exists for. If
most tasks are like it, the A/B will report "no difference", and the honest reading will
be that the baseline is already good enough rather than that the tool is useless. Either
way, running 60 agents to learn it is the expensive way round when the task set can be
stratified for nothing.

The strata, from what a grep-only reader can actually reach
----------------------------------------------------------
Work out which symbols the commit changed *in the starting file* -- the only names such
a reader would have to search on -- and ask where each companion stands:

    grep_reachable   the companion contains one of those names. A grep finds it, and
                     the tool has to beat free rather than beat nothing
    convention       a changelog, a docs page, a `.rst`/`.md`/`.txt`. Found by knowing
                     the project's habits, not by searching for a symbol
    hidden           neither. Nothing textual connects it to the change, so only
                     history or the import graph could suggest it. **This is the only
                     stratum where the tool can add something grep cannot.**

A task is as hard as its hardest companion, so a task counts as hidden if any companion
is hidden.

    python -m experiments.exp15_task_difficulty
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments import corpus  # noqa: E402
from experiments import exp12_prevention as prevention  # noqa: E402

TASKS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "prevention_tasks.json")
STRATA = ("grep_reachable", "convention", "hidden")

# Long enough that a search on it is not hopeless. `run`, `app` and `get` appear
# everywhere and nobody greps them expecting an answer, so counting them as reachable
# would credit the baseline with finding things it cannot.
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{4,}")
_CONVENTION = (".rst", ".md", ".txt", ".cfg", ".ini", ".toml")
_CONVENTION_NAMES = ("changes", "changelog", "news", "history", "authors")


def _changed_identifiers(root: str, task: dict) -> set[str]:
    """Names the commit touched in the starting file -- what a reader would search on.

    Added *and* removed lines: a reader who deletes a helper greps for it exactly as a
    reader who adds one does, and the pilot task turned on precisely that.
    """
    done = subprocess.run(
        ["git", "-C", root, "diff", "--unified=0", task["parent"], task["sha"],
         "--", task["start_in"]],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    names: set[str] = set()
    for line in done.stdout.splitlines():
        if line.startswith(("+++", "---", "@@")) or line[:1] not in "+-":
            continue
        names.update(_IDENTIFIER.findall(line))
    return names


def _is_convention(path: str) -> bool:
    base = os.path.basename(path).lower()
    return (path.lower().endswith(_CONVENTION)
            or any(base.startswith(name) for name in _CONVENTION_NAMES)
            or path.lower().startswith(("doc/", "docs/")))


def classify(root: str, task: dict) -> dict:
    names = _changed_identifiers(root, task)
    companions = task["truth"]["companions"]
    blobs = prevention._read_blobs(root, task["sha"], companions)
    where: dict[str, str] = {}
    for companion in companions:
        text = blobs.get(companion)
        if text and names and _IDENTIFIER.findall(text) and (
                names & set(_IDENTIFIER.findall(text))):
            where[companion] = "grep_reachable"
        elif _is_convention(companion):
            where[companion] = "convention"
        else:
            where[companion] = "hidden"
    # A task is as hard as its hardest companion.
    hardest = ("hidden" if "hidden" in where.values()
               else "convention" if "convention" in where.values()
               else "grep_reachable")
    return {"id": task["id"], "repo": task["repo"], "searchable_names": len(names),
            "companions": where, "stratum": hardest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", default=None)
    args = parser.parse_args()
    with open(TASKS, encoding="utf-8") as handle:
        tasks = json.load(handle)
    roots = {name: corpus.ensure(name, url) for name, url in corpus.PREVENTION}

    rows = [classify(roots[task["repo"]], task) for task in tasks]
    by_task: Counter = Counter(row["stratum"] for row in rows)
    by_companion: Counter = Counter(
        stratum for row in rows for stratum in row["companions"].values())

    print(f"{len(rows)} tasks, {sum(by_companion.values())} companions\n")
    print(f"{'stratum':16} {'tasks':>7} {'':>6} {'companions':>12}")
    for name in STRATA:
        print(f"{name:16} {by_task[name]:7} {by_task[name]/len(rows):6.0%} "
              f"{by_companion[name]:12} {by_companion[name]/sum(by_companion.values()):6.0%}")

    hidden = [row for row in rows if row["stratum"] == "hidden"]
    print(f"\nTasks a grep cannot finish: {len(hidden)}")
    for row in hidden[:8]:
        unreachable = [c for c, s in row["companions"].items() if s == "hidden"]
        print(f"  {row['id']:22} {unreachable[:3]}")
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=1)
        print(f"\nwrote {args.dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
