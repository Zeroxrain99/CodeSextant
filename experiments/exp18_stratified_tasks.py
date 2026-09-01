"""Build the prevention task set as a sample instead of as a convenience.

**Why the frozen set had to be rebuilt.** exp15 stratified
`prevention_tasks.json` and found 2% of tasks had a companion no grep could reach.
exp17 ran the same classifier over 900 real commits from the same repositories and
found 7-11%. The task set under-represents the only stratum where this tool can beat
a grep by three to five times, and every number E1 and E1b produced is therefore a
number about the easy half.

**Where the bias came from: not established, and the first guess was wrong.** The
obvious suspect was exp12's candidate filter, which requires
``sum(1 for f in files if f.endswith(".py")) >= 2`` -- two Python files change together
mostly because they share a symbol, so the filter looked like it selected for exactly
the linkage that makes a companion greppable. This experiment prints the check, and it
comes back mostly negative: **82% of the hidden tasks it finds touch two or more Python
files**, so the old filter would have kept four in five of them. It costs about a fifth
of the stratum, not four fifths of it.

What is left is the shortfall itself. The candidate population exp12 draws from is about
7% hidden, the same rate exp17 measured on unfiltered commits; taking 120 tasks from it
should yield around eight, and the frozen set has two. Removing a further 18% for the
Python-file filter still leaves six or seven expected. That is roughly two standard
deviations low -- unlikely rather than impossible -- and no mechanism accounts for it.

*(The first version of this paragraph said "every hidden task", from a smoke run of
eleven. At forty-five it is 82%. A correction written from a sample too small to
correct anything is the same error one level up, and it is in HANDOFF.md now.)*

**Sampling per stratum makes the question moot rather than answering it**, which is why
this is the fix. A stratified sample is right whatever the cause, and does not depend on
a mechanism nobody has demonstrated.

What this builds
----------------
The same task shape as exp12, from the same repositories, with two changes:

    at least one .py file rather than two, so a commit whose companion is a config,
    a fixture, or a sibling module can be a candidate at all

    sampled per stratum rather than first-N-after-shuffle, so the hidden cases are
    present in a number that an A/B can resolve

Everything else is exp12's, imported rather than re-implemented: the instruction
comes from the commit subject, the seed file from `_seed_file`, and the guard and
reuse ground truth from the same functions the scorer reads. A task built differently
from the tasks it will be compared against is not a control.

Classification runs *before* the expensive part. `_repo_symbols` walks the whole tree
at the parent commit, so building every candidate to throw most away costs minutes per
repository; exp15's classifier needs one diff and a few blobs.

Honest limits
-------------
- **Hidden is scarce by nature.** At 7% of commits, filling a stratum takes scanning
  about fourteen candidates per task, and a repository may simply run out. The report
  prints achieved counts per stratum, and a stratum that came up short says so rather
  than being padded from another.
- **`start_in` is exp12's `_seed_file`**, the same guess about what the author was
  asked to edit that the original set makes. This experiment does not fix that; it
  fixes the sampling.
- The old file is not overwritten. `prevention_tasks.json` is what E1 and E1b
  measured and it stays exactly as it was.

Run
---
    python experiments/exp18_stratified_tasks.py --per-stratum 20 \
        --out experiments/prevention_tasks_stratified.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments import corpus  # noqa: E402
from experiments import exp12_prevention as prevention  # noqa: E402
from experiments import exp15_task_difficulty as exp15  # noqa: E402


def _candidates(repo_path: str, *, seed: int, warmup_fraction: float = 0.5):
    """exp12's candidate filter with the two-Python-files requirement relaxed to one."""
    commits = corpus.history(repo_path)
    rows = [(index, sha, files)
            for index, (sha, files) in enumerate(commits)
            if index >= len(commits) * warmup_fraction
            and 2 <= len(files) <= 15
            and any(f.endswith(".py") for f in files)]
    random.Random(seed).shuffle(rows)
    return rows


def _shell(repo_path: str, sha: str, files, described) -> dict | None:
    """Enough of a task to classify it, without the tree walk that costs the minutes."""
    described_here = described.get(sha)
    if not described_here:
        return None
    parent, instruction = described_here
    subject = instruction.splitlines()[0] if instruction else ""
    if len(subject) < 20 or prevention._UNUSABLE.match(subject):
        return None
    ordered = sorted(files)
    start_in = prevention._seed_file(repo_path, sha, set(files))
    if start_in is None:
        return None
    companions = [path for path in ordered if path != start_in]
    if not companions:
        return None
    # An instruction that names a file to be discovered is not a task, it is the answer.
    # exp12 never had to check this because its `>= 2 Python files` filter kept out the
    # commits whose message is *about* a file -- "switch to pyproject.toml", "move
    # package metadata to setup.cfg". Relaxing that filter let them in, and
    # `tests/test_prevention_tasks.py` caught four of them.
    if any(companion in instruction for companion in companions):
        return None
    return {"id": f"{os.path.basename(repo_path)}@{sha[:10]}",
            "repo": os.path.basename(repo_path), "sha": sha, "parent": parent,
            "instruction": instruction, "start_in": start_in,
            "ordered": ordered, "companions": companions,
            "python_files": sum(1 for f in ordered if f.endswith(".py"))}


def _finish(repo_path: str, shell: dict) -> dict:
    """The expensive half: the ground truth the scorer reads, from exp12's own code."""
    vocabulary = prevention._repo_symbols(
        repo_path, shell["parent"],
        prevention._python_files(repo_path, shell["parent"]))
    reuse = prevention._reuse_events(
        repo_path, shell["sha"], shell["parent"], shell["ordered"], vocabulary)
    guard_files = [path for path in prevention._guard_bearing(
        repo_path, shell["sha"], shell["ordered"]) if path != shell["start_in"]]
    return {
        "id": shell["id"], "repo": shell["repo"], "sha": shell["sha"],
        "parent": shell["parent"], "instruction": shell["instruction"],
        "start_in": shell["start_in"],
        "stratum": shell["stratum"],
        "truth": {"files": shell["ordered"], "companions": shell["companions"],
                  "guard_files": guard_files, "reuse": reuse},
    }


def build(repo_path: str, *, per_stratum: int, seed: int = 0,
          scan_limit: int = 900) -> tuple[list[dict], Counter, Counter]:
    described = prevention._messages_and_parents(repo_path)
    wanted = {name: per_stratum for name in exp15.STRATA}
    chosen: dict[str, list[dict]] = defaultdict(list)
    seen: Counter = Counter()
    py_counts: Counter = Counter()
    scanned = 0

    for _index, sha, files in _candidates(repo_path, seed=seed):
        if scanned >= scan_limit or not any(wanted.values()):
            break
        shell = _shell(repo_path, sha, files, described)
        if shell is None:
            continue
        scanned += 1
        verdict = exp15.classify(repo_path, {
            "id": shell["id"], "repo": shell["repo"], "sha": shell["sha"],
            "parent": shell["parent"], "start_in": shell["start_in"],
            "truth": {"companions": shell["companions"]}})
        stratum = verdict["stratum"]
        seen[stratum] += 1
        if not wanted[stratum]:
            continue
        wanted[stratum] -= 1
        shell["stratum"] = stratum
        # How many .py files this commit touched, kept so the report can say whether
        # the old filter's `>= 2` is what excluded the hidden cases or something else.
        py_counts[(stratum, "multi" if shell["python_files"] >= 2 else "single")] += 1
        chosen[stratum].append(shell)

    tasks = [_finish(repo_path, shell)
             for stratum in exp15.STRATA for shell in chosen[stratum]]
    return tasks, seen, py_counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-stratum", type=int, default=20,
                        help="target tasks per stratum per repository")
    parser.add_argument("--scan-limit", type=int, default=900)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    roots = {name: corpus.ensure(name, url) for name, url in corpus.PREVENTION}
    everything: list[dict] = []
    totals: Counter = Counter()
    py_totals: Counter = Counter()

    for name, root in roots.items():
        tasks, seen, py_counts = build(
            root, per_stratum=args.per_stratum, scan_limit=args.scan_limit)
        got = Counter(task["stratum"] for task in tasks)
        everything.extend(tasks)
        totals.update(got)
        py_totals.update(py_counts)
        print(f"\n{name}: {len(tasks)} tasks from {sum(seen.values())} candidates")
        for stratum in exp15.STRATA:
            short = "" if got[stratum] >= args.per_stratum else "   (ran out)"
            print(f"  {stratum:16} {got[stratum]:3} of {args.per_stratum}"
                  f"   available {seen[stratum]:4}{short}")

    print(f"\n{len(everything)} tasks total")
    for stratum in exp15.STRATA:
        print(f"  {stratum:16} {totals[stratum]:3}"
              f"  {totals[stratum]/max(1, len(everything)):5.0%}")
    print("\nHow many Python files each chosen commit touched -- the old filter kept "
          "only 'multi':")
    for stratum in exp15.STRATA:
        multi = py_totals[(stratum, "multi")]
        single = py_totals[(stratum, "single")]
        total = max(1, multi + single)
        print(f"  {stratum:16} multi {multi:3} ({multi/total:4.0%})"
              f"   single {single:3} ({single/total:4.0%})")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(everything, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
