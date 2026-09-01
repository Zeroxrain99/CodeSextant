"""How often does a real commit delete a fence that someone had explained?

`check` has three modes -- rebuilt, companions, callers -- and **all three ask what the
change forgot to add. None of them notices what it removed.** That is the gap the first
demand names most directly:

    立意良善的測試、安全閥、守衛、功能,遺忘後變成災難

A guard the author wrote months ago blocks them now, they do not remember why it is
there, and the cheapest way out looks like deleting it. E2 could not have detected this:
all twenty of its tasks were "make this change", none was "here is a fence that looks
wrong".

**So the fourth mode is a candidate, and a candidate gets measured before it is built.**
Rule 1 of `docs/plan.md`, and the rule that has already refused five features here. Two
numbers decide it:

1. **How often is a reasoned guard removed?** If a commit deletes an explained fence
   once in a thousand, the mode is over-engineering and belongs on the refusal list.
2. **Of the guards a commit removes, how many carried a reason at all?** exp8 measured
   that four guards in five carry nothing but a name. If that holds for the removed
   ones, the mode can only speak about a fifth of them and its ceiling is low.

Method
------
Prequential is unnecessary -- nothing here is trained. For each commit that touches a
Python file, `guards.extract` runs on the file's **parent** blob and on its **commit**
blob, through the shipped extractor rather than a reimplementation. A guard present
before and absent after is a removal.

Identity, stated because it decides the numbers: a guard is the triple
`(kind, name, rule)` within a file. Name alone would call every rewritten assert a
removal; rule alone would merge the two asserts on adjacent lines. A guard whose rule
changed but whose name survived is a **weakening**, counted separately -- moving a
threshold from 250 to 5000 is not a deletion and is exactly as worth interrupting over.

**What this over-counts, and it is not corrected away.** A test renamed, a file moved,
a helper inlined, a fence genuinely obsolete -- all read as removals here. The number is
therefore an upper bound on how often the mode would have something to say, and the
honest reading of a low number is "do not build", while a high number still needs the
precision question asking separately. That is the same asymmetry `changed_a_broke_b`
has, and it is why the counts below are reported per kind and per reason source rather
than pooled into one rate.
"""
from __future__ import annotations

import argparse
import collections
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import guards  # noqa: E402
from experiments import corpus  # noqa: E402
from experiments import exp12_prevention as prevention  # noqa: E402


def _commits(root: str, limit: int) -> list[str]:
    done = subprocess.run(
        ["git", "-C", root, "log", "--no-merges", "--format=%H", f"-{limit}"],
        capture_output=True, text=True)
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def _python_touched(root: str, sha: str) -> list[str]:
    done = subprocess.run(
        ["git", "-C", root, "show", "--name-only", "--format=", "-m", "--first-parent",
         sha],
        capture_output=True, text=True)
    return sorted({line.strip() for line in done.stdout.splitlines()
                   if line.strip().endswith(".py")})


def _key(guard: guards.Guard) -> tuple[str, str]:
    """Identity within a file: kind plus name. The rule is compared separately, because
    a guard whose rule moved is a weakening rather than a removal."""
    return (guard.kind, guard.name)


def survey(root: str, limit: int) -> dict:
    removed = collections.Counter()
    relocated = collections.Counter()
    removed_with_reason = collections.Counter()
    weakened = collections.Counter()
    weakened_with_reason = collections.Counter()
    by_source = collections.Counter()
    commits_touching = commits_removing = commits_removing_reasoned = 0
    commits_weakening_reasoned = 0
    examples: list[dict] = []

    for sha in _commits(root, limit):
        paths = _python_touched(root, sha)
        if not paths:
            continue
        commits_touching += 1
        before = prevention._read_blobs(root, f"{sha}~1", paths)
        after = prevention._read_blobs(root, sha, paths)

        # **A rename is not a removal, and neither is a move.** Without this the
        # number is an upper bound made mostly of tests that still exist under
        # another name or in another file -- and a mode that interrupts for those
        # is a mode nobody leaves switched on. Everything the commit *has* after it
        # lands, across every file it touched, counts as somewhere the guard could
        # have gone: same identity in a different file, or the same rule under a
        # different name.
        landed_keys, landed_rules = set(), set()
        for path in paths:
            for guard in guards.extract(path, after.get(path, "")):
                landed_keys.add(_key(guard))
                landed_rules.add((guard.kind, guard.rule))

        gone_here = reasoned_here = weak_reasoned_here = 0
        for path in paths:
            if path not in before:
                continue                      # added by this commit; nothing to lose
            was = {_key(g): g for g in guards.extract(path, before[path])}
            now = {_key(g): g for g in guards.extract(path, after.get(path, ""))}
            for key, guard in was.items():
                if key not in now and (key in landed_keys
                                       or (guard.kind, guard.rule) in landed_rules):
                    relocated[guard.kind] += 1
                    continue                  # it moved; it did not go
                if key not in now:
                    removed[guard.kind] += 1
                    gone_here += 1
                    if guard.reason:
                        removed_with_reason[guard.kind] += 1
                        by_source[guard.reason_source] += 1
                        reasoned_here += 1
                        if len(examples) < 12:
                            examples.append({
                                "repo": os.path.basename(root), "sha": sha[:10],
                                "path": path, "kind": guard.kind,
                                "name": guard.name or "(anonymous)",
                                "reason": guard.reason,
                                "source": guard.reason_source})
                elif now[key].rule != guard.rule:
                    weakened[guard.kind] += 1
                    if guard.reason:
                        weakened_with_reason[guard.kind] += 1
                        weak_reasoned_here += 1
        if gone_here:
            commits_removing += 1
        if reasoned_here:
            commits_removing_reasoned += 1
        if weak_reasoned_here:
            commits_weakening_reasoned += 1

    return {"repo": os.path.basename(root),
            "commits_touching_python": commits_touching,
            "commits_removing_a_guard": commits_removing,
            "commits_removing_a_reasoned_guard": commits_removing_reasoned,
            "commits_weakening_a_reasoned_guard": commits_weakening_reasoned,
            "removed": dict(removed), "removed_with_reason": dict(removed_with_reason),
            "relocated": dict(relocated),
            "weakened": dict(weakened),
            "weakened_with_reason": dict(weakened_with_reason),
            "reason_source": dict(by_source), "examples": examples}


def _print(report: dict) -> None:
    n = report["commits_touching_python"]
    gone = sum(report["removed"].values())
    reasoned = sum(report["removed_with_reason"].values())
    weak = sum(report["weakened"].values())
    weak_reasoned = sum(report["weakened_with_reason"].values())
    print(f"\n=== {report['repo']}  ({n} commits touching Python)")
    if not n:
        return
    print(f"  commits removing a guard:            "
          f"{report['commits_removing_a_guard']:>4}  "
          f"({report['commits_removing_a_guard'] / n:.0%})")
    print(f"  commits removing a REASONED guard:   "
          f"{report['commits_removing_a_reasoned_guard']:>4}  "
          f"({report['commits_removing_a_reasoned_guard'] / n:.0%})   <- the mode's ceiling")
    print(f"  guards removed: {gone}, of which explained: {reasoned}"
          f"{f'  ({reasoned / gone:.0%})' if gone else ''}")
    print(f"  guards weakened (rule changed, name kept): {weak}, "
          f"of which explained: {weak_reasoned}")
    moved = sum(report.get("relocated", {}).values())
    print(f"  renames/moves excluded (would have read as removals): {moved}")
    if report["removed"]:
        print(f"  removed by kind:  {report['removed']}")
    print(f"  weakened by kind: {report['weakened']}")
    print(f"  weakened+explained by kind: {report['weakened_with_reason']}")
    print(f"  commits weakening a REASONED guard: "
          f"{report['commits_weakening_a_reasoned_guard']} "
          f"({report['commits_weakening_a_reasoned_guard'] / n:.0%})")
    if report["reason_source"]:
        print(f"  reason came from: {report['reason_source']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=300,
                        help="commits per repository, newest first")
    parser.add_argument("--repo", action="append", default=None)
    args = parser.parse_args(argv)

    roots = args.repo or [corpus.ensure(name, url)
                          for name, url in corpus.EXTERNAL + corpus.PREVENTION]
    reports = [survey(root, args.limit) for root in roots]
    for report in reports:
        _print(report)

    total = sum(r["commits_touching_python"] for r in reports)
    removing = sum(r["commits_removing_a_guard"] for r in reports)
    reasoned = sum(r["commits_removing_a_reasoned_guard"] for r in reports)
    gone = sum(sum(r["removed"].values()) for r in reports)
    explained = sum(sum(r["removed_with_reason"].values()) for r in reports)
    moved = sum(sum(r.get("relocated", {}).values()) for r in reports)
    weak = sum(sum(r["weakened"].values()) for r in reports)
    weak_reasoned = sum(sum(r["weakened_with_reason"].values()) for r in reports)
    print(f"\n=== pooled over {len(reports)} repositories, {total} commits")
    print(f"  removes a guard:          {removing:>5}  ({removing / total:.1%})")
    print(f"  removes a REASONED guard: {reasoned:>5}  ({reasoned / total:.1%})")
    print(f"  guards removed {gone}, explained {explained}"
          f"{f' ({explained / gone:.0%})' if gone else ''}")
    print(f"  renames/moves excluded: {moved}")
    print(f"  guards weakened {weak}, explained {weak_reasoned}")
    cw = sum(r["commits_weakening_a_reasoned_guard"] for r in reports)
    print(f"  weakens a REASONED guard: {cw:>5}  ({cw / total:.1%})")
    print("\n--- a reasoned guard a real commit deleted, in the author's words ---")
    for example in [e for r in reports for e in r["examples"]][:8]:
        print(f"  {example['repo']}@{example['sha']} {example['path']}:"
              f"{example['kind']} {example['name']}")
        print(f"      [{example['source']}] {example['reason'][:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
