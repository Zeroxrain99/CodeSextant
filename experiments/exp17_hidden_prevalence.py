"""How often is a companion file one that no grep would have found?

exp15 stratified the 120 curated prevention tasks and found **86% grep-reachable, 2%
hidden**. That result stopped E2 from being run as designed, and it immediately raises
the question it cannot answer: is 2% a property of those three repositories and that
curation, or of software?

The difference decides what to do next. If hidden companions are rare everywhere, then
the failure mode this tool is built for is rare, and the honest response is to say so in
the README rather than to keep hunting for a task set that flatters it. If they are
common elsewhere, the task set is the problem and it can be rebuilt.

What this does
--------------
The same classifier as exp15 -- imported, not re-implemented, so a difference between
the two reports is a difference in the population and nothing else -- applied to real
commits rather than to curated tasks. For each multi-file commit:

    start_in     the file with the most changed lines: the one an author would most
                 plausibly have been asked to edit
    companions   every other file the commit touched
    stratum      exp15's, unchanged: does the companion contain a long identifier the
                 commit changed in the starting file, is it a convention file, or is it
                 reachable only through history or the import graph

**A known limitation, stated because it bounds the answer.** Choosing `start_in` by diff
size is a guess at what the author was asked to do. A commit where the author started in
a small file and the large change was the consequence gets classified backwards. The
curated tasks in exp15 do not have that problem, which is why this experiment
supplements them rather than replacing them.

Run
---
    python experiments/exp17_hidden_prevalence.py                       # all three sets
    python experiments/exp17_hidden_prevalence.py --repo <path>
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments import corpus  # noqa: E402
from experiments import exp15_task_difficulty as exp15  # noqa: E402

_MAX_COMMIT_FILES = 25  # a sweeping change couples everything it touched; exp1's cap


def _numstat(root: str, sha: str) -> list[tuple[int, str]]:
    """(changed lines, path) for one commit, excluding what cannot be classified.

    ``--no-renames`` because numstat otherwise writes a rename as
    ``{old => new}/file.py``, which is not a path and blew up the blob reader on the
    first run. ``--diff-filter=d`` because a file the commit *deleted* cannot be read at
    that commit, and a companion whose text comes back empty is classified as unreachable
    by construction -- a measurement artifact that would inflate exactly the number this
    experiment exists to report. Deletions are real companions and their absence here is
    a limitation, not a claim that they do not happen.
    """
    done = subprocess.run(
        ["git", "-C", root, "show", "--numstat", "--no-renames", "--diff-filter=d",
         "--format=", sha],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    rows: list[tuple[int, str]] = []
    for line in done.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, path = parts
        if added == "-" or removed == "-":       # binary
            continue
        rows.append((int(added) + int(removed), path))
    return rows


def evaluate(repo_path: str, *, limit: int = 200, warmup_fraction: float = 0.3) -> dict:
    commits = corpus.history(repo_path)
    warmup = int(len(commits) * warmup_fraction)
    by_task: Counter = Counter()
    by_companion: Counter = Counter()
    scored = 0
    examples: list[dict] = []

    for index, (sha, files) in enumerate(commits):
        if scored >= limit:
            break
        if index < warmup or not (1 < len(files) <= _MAX_COMMIT_FILES):
            continue
        rows = _numstat(repo_path, sha)
        python = [row for row in rows if row[1].endswith(".py")]
        if not python or len(rows) < 2:
            continue
        start_in = max(python, key=lambda row: row[0])[1]
        companions = sorted(path for _size, path in rows if path != start_in)
        if not companions:
            continue
        parent = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", f"{sha}^"],
            capture_output=True, text=True).stdout.strip()
        if not parent:
            continue

        verdict = exp15.classify(repo_path, {
            "id": f"{os.path.basename(repo_path)}@{sha[:10]}",
            "repo": os.path.basename(repo_path),
            "sha": sha, "parent": parent, "start_in": start_in,
            "truth": {"companions": companions},
        })
        scored += 1
        by_task[verdict["stratum"]] += 1
        for stratum in verdict["companions"].values():
            by_companion[stratum] += 1
        if verdict["stratum"] == "hidden" and len(examples) < 6:
            examples.append({
                "id": verdict["id"], "start_in": start_in,
                "hidden": [c for c, s in verdict["companions"].items()
                           if s == "hidden"][:3]})

    return {"repo": os.path.basename(repo_path), "commits": scored,
            "tasks": dict(by_task), "companions": dict(by_companion),
            "examples": examples}


def _report(reports: list[dict], label: str) -> None:
    tasks = Counter()
    companions = Counter()
    for report in reports:
        tasks.update(report["tasks"])
        companions.update(report["companions"])
    total_tasks = max(1, sum(tasks.values()))
    total_companions = max(1, sum(companions.values()))
    print(f"\n{label}: {total_tasks} commits, {total_companions} companions "
          f"({', '.join(r['repo'] for r in reports)})")
    print(f"  {'stratum':16} {'commits':>9} {'':>6} {'companions':>12}")
    for name in exp15.STRATA:
        print(f"  {name:16} {tasks[name]:9} {tasks[name]/total_tasks:6.0%} "
              f"{companions[name]:12} {companions[name]/total_companions:6.0%}")
    for report in reports:
        for example in report["examples"][:2]:
            print(f"    hidden: {example['id']:24} {example['start_in']}"
                  f"  ->  {example['hidden']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--dump", default=None)
    args = parser.parse_args()

    if args.repo:
        groups = {"repos": [(os.path.basename(p), p) for p in args.repo]}
    else:
        groups = {
            "derivation": [(n, corpus.ensure(n, u)) for n, u in corpus.EXTERNAL],
            "prevention": [(n, corpus.ensure(n, u)) for n, u in corpus.PREVENTION],
        }
    dumped = {}
    for label, repos in groups.items():
        reports = [evaluate(path, limit=args.limit) for _name, path in repos]
        _report(reports, label)
        dumped[label] = reports
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as handle:
            json.dump(dumped, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
