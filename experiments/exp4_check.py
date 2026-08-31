"""Hold one file out of a real commit and see whether check names it.

This is the closest thing to the actual question available without running agents.
Every commit in a repository's history is a record of files that had to change
together. Take one, hide one of its files, present the rest as a working tree, and ask
check what the change looks like to have forgotten. The hidden file is the answer.

Protocol
--------
Prequential, like exp1: commits replay oldest first and the baselines only ever see
history older than the commit being scored. For a sampled subset the repository is
checked out at the commit's parent, every file of the commit *except* the held-out one
is applied, and check runs on the result.

    check            what ships: rebuilt + companions + callers, unioned
    companions       the co-change section alone -- what preflight already had
    callers          the resolved-caller section alone
    callers_ceiling  every file naming any definition that lives in a changed file
    same_dir@k       the most-changed neighbours of the files that did change
    frequency@k      the most-changed files in the project

`callers_ceiling` is looser than the caller section it bounds, and exp5 measures by how
much: it counts a file as reachable if it names *any* definition living in a file the
commit touched, while the caller section only ever resolves the definitions the diff
wrote into. Restricted to those, the ceiling is 0.153/0.439/0.350 rather than
0.305/0.759/0.419. Read it as the ceiling for a file-level signal, which is what it is,
and not as the headroom above the resolver.

`callers_ceiling` is not a candidate for shipping -- it is a text sweep naming about
eight files per case, which is a list nobody reads. It is here to separate two
explanations for a weak caller section: import resolution missing real callers, or the
held-out file simply not being one. The gap between it and `callers` is the first; the
gap between it and 1.0 is the second.

`callers_named@2` and `callers_named@k` sit between the two and are the candidates. A
file that names *one* symbol a change touched has probably just got a same-named
function of its own; a file that names several is much more likely to be using the
thing that changed. Whether that intuition survives contact with the corpus is the
question, and it is asked before anything is built on it rather than after.

The two section-only rows exist to answer the question the union cannot: does reading
the diff add anything over mining history, or is check just co-change with extra steps?

Intervals are bootstrapped over cases, which here are whole commits and so independent
of each other. They are reported because an earlier experiment in this directory
produced a repository whose result reversed, and a number without error bars could not
say whether that mattered.

Two predictors scored on the same cases are *paired*, and comparing their separate
intervals understates the evidence badly -- two intervals can overlap while every case
moves the same way. Differences that matter to a decision are therefore bootstrapped as
differences, per case. Per-case outcomes are also written out, so a later question can
be asked of a finished run instead of costing another hour of one.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine, references, storage  # noqa: E402
from experiments import corpus  # noqa: E402

PREDICTORS = ("check", "companions", "callers", "callers_named@2", "callers_named@k",
              "callers_ceiling", "same_dir@k", "frequency@k")


def _git(root: str, *args: str) -> tuple[int, str]:
    done = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.returncode, done.stdout


class Tally:
    def __init__(self):
        self.cases = 0
        self.hits = 0        # the held-out file was named
        self.spoke = 0       # anything was named at all
        self.predicted = 0   # total names, for the noise a reader would carry
        self.outcomes: list[int] = []

    def add(self, predicted: set[str], held_out: str) -> None:
        self.cases += 1
        self.predicted += len(predicted)
        if predicted:
            self.spoke += 1
        hit = int(held_out in predicted)
        self.hits += hit
        self.outcomes.append(hit)

    def recall_interval(self, *, seed: int = 0, rounds: int = 2000) -> tuple[float, float]:
        if not self.outcomes:
            return (0.0, 0.0)
        rng = random.Random(seed)
        size = len(self.outcomes)
        values = []
        for _ in range(rounds):
            values.append(sum(self.outcomes[rng.randrange(size)]
                              for _i in range(size)) / size)
        values.sort()
        return (values[int(rounds * 0.025)], values[int(rounds * 0.975)])

    def row(self) -> dict:
        low, high = self.recall_interval()
        return {"recall": self.hits / self.cases if self.cases else 0.0,
                "recall_ci": (low, high),
                "speaks": self.spoke / self.cases if self.cases else 0.0,
                "mean_n": self.predicted / self.cases if self.cases else 0.0,
                "cases": self.cases}


def _predicted_files(result: dict) -> dict[str, set[str]]:
    companions = {entry["path"] for entry in result.get("companions") or []}
    callers = {path for entry in result.get("callers") or []
               for path in entry.get("callers") or []}
    rebuilt = {match["path"] for entry in result.get("rebuilt") or []
               for match in entry.get("matches") or []}
    return {"companions": companions, "callers": callers,
            "check": companions | callers | rebuilt}


def evaluate(repo: str, *, limit: int = 60, seed: int = 0,
             warmup_fraction: float = 0.3) -> dict:
    commits = corpus.history(repo)
    warmup = int(len(commits) * warmup_fraction)
    eligible = [index for index, (_sha, files) in enumerate(commits)
                if index >= warmup and 2 <= len(files) <= 25
                and any(f.endswith(".py") for f in files)]
    random.Random(seed).shuffle(eligible)
    sampled = set(eligible[:limit])

    changed_total: Counter[str] = Counter()
    directory_files: dict[str, set[str]] = {}
    tallies = {name: Tally() for name in PREDICTORS}
    scored = 0

    with tempfile.TemporaryDirectory() as home:
        os.environ["CODESEXTANT_HOME"] = home
        for index, (sha, files) in enumerate(commits):
            if index in sampled:
                scored += _score_one(
                    repo, home, sha, files, changed_total, directory_files, tallies)
            for path in files:
                changed_total[path] += 1
                directory_files.setdefault(os.path.dirname(path), set()).add(path)

    return {"repo": os.path.basename(repo), "scored": scored,
            "results": {name: tally.row() for name, tally in tallies.items()},
            "outcomes": {name: tally.outcomes for name, tally in tallies.items()}}


def paired_difference(left: list[int], right: list[int], *, seed: int = 0,
                      rounds: int = 4000) -> dict:
    """Bootstrap the per-case difference in recall, resampling cases not predictors.

    The two predictors saw the same cases, so the question is whether the difference
    is real -- not whether two separately estimated rates happen to sit apart. An
    interval on the difference that excludes zero says the first is better; one that
    contains zero says this many cases cannot tell.
    """
    if not left or len(left) != len(right):
        return {}
    rng = random.Random(seed)
    size = len(left)
    values = []
    for _ in range(rounds):
        total = 0
        for _i in range(size):
            pick = rng.randrange(size)
            total += left[pick] - right[pick]
        values.append(total / size)
    values.sort()
    low, high = values[int(rounds * 0.025)], values[int(rounds * 0.975)]
    return {"mean": sum(a - b for a, b in zip(left, right)) / size,  # noqa: B905
            "low": low, "high": high, "excludes_zero": low > 0 or high < 0}


def _naming_counts(tree: str, applied: list[str]) -> Counter:
    """How many symbols each outside file names, for symbols the change touched.

    The ceiling the resolved caller section works against: a caller has to name the
    symbol, so nothing outside this set is reachable by any amount of resolution. The
    counts are kept rather than collapsed because "names one of them" and "names five
    of them" are very different claims, and the difference is what might make a
    name-level signal short enough to be worth printing.
    """
    counts: Counter = Counter()
    changed_abs = {os.path.normcase(os.path.abspath(os.path.join(tree, f)))
                   for f in applied}
    with storage.ProjectStore.open_readonly(tree) as store:
        for relative in applied:
            if not relative.endswith(".py"):
                continue
            absolute = os.path.abspath(os.path.join(tree, relative))
            rows = store.conn.execute(
                "SELECT DISTINCT name FROM symbols WHERE path=? AND kind IN "
                "('function','method','class') LIMIT 40", (absolute,)).fetchall()
            for row in rows:
                for hit in references.candidate_files(
                        tree, row["name"], lang="python", limit=60):
                    if os.path.normcase(os.path.abspath(hit)) in changed_abs:
                        continue
                    counts[os.path.relpath(hit, tree).replace(os.sep, "/")] += 1
    return counts


def _score_one(repo: str, home: str, sha: str, files: set[str],
               changed_total: Counter, directory_files: dict, tallies: dict) -> int:
    code, parent = _git(repo, "rev-parse", f"{sha}^")
    if code != 0:
        return 0
    parent = parent.strip()
    ordered = sorted(files)
    # Hold out a Python file when there is one: the caller and rebuilt sections have
    # nothing to say about a file no resolver reads, and scoring them on one would
    # measure co-change while claiming to measure check.
    held_out = next((f for f in ordered if f.endswith(".py")), ordered[0])
    applied = [f for f in ordered if f != held_out]

    tree = os.path.join(home, "tree")
    subprocess.run(["git", "-C", repo, "worktree", "add", "-q", "--detach", tree, parent],
                   check=False, capture_output=True)
    if not os.path.isdir(tree):
        return 0
    try:
        restored = subprocess.run(
            ["git", "-C", tree, "checkout", sha, "--", *applied],
            capture_output=True, text=True)
        if restored.returncode != 0:
            return 0
        engine.index_project(tree, force=True)
        result = engine.check(tree, token_budget=100_000)
        predicted = _predicted_files(result)
        counts = _naming_counts(tree, applied)
        predicted["callers_ceiling"] = set(counts)
        predicted["callers_named@2"] = {f for f, n in counts.items() if n >= 2}

        changed = set(applied)
        neighbours = {p for f in applied
                      for p in directory_files.get(os.path.dirname(f), set())} - changed
        frequent = [p for p, _n in changed_total.most_common(80) if p not in changed]
        budget = len(predicted["check"])
        local = sorted(neighbours, key=lambda p: (-changed_total[p], p))
        predicted["same_dir@k"] = set(local[:budget])
        predicted["frequency@k"] = set(frequent[:budget])
        ranked = sorted(counts, key=lambda f: (-counts[f], f))
        predicted["callers_named@k"] = set(ranked[:budget])

        for name in PREDICTORS:
            tallies[name].add(predicted[name], held_out)
        return 1
    finally:
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", tree],
                       check=False, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--dump", default=None,
                        help="write per-case outcomes here, so later questions are free")
    args = parser.parse_args()
    dumped = {}
    repos = args.repo or [corpus.ensure(name, url) for name, url in corpus.EXTERNAL]
    for repo in repos:
        report = evaluate(repo, limit=args.limit)
        print(f"\n=== {report['repo']}  ({report['scored']} held-out cases)")
        print(f"{'predictor':14} {'recall':>8} {'recall 95% CI':>16} {'speaks':>8} "
              f"{'mean n':>8} {'cases':>7}")
        for name in PREDICTORS:
            row = report["results"][name]
            low, high = row["recall_ci"]
            print(f"{name:14} {row['recall']:8.3f} {f'[{low:.3f},{high:.3f}]':>16} "
                  f"{row['speaks']:8.3f} {row['mean_n']:8.1f} {row['cases']:7}")
        outcomes = report["outcomes"]
        print("  paired differences (same cases, so the difference is the statistic):")
        for left, right in (("check", "companions"), ("check", "same_dir@k"),
                            ("callers_named@k", "check")):
            delta = paired_difference(outcomes[left], outcomes[right])
            if not delta:
                continue
            verdict = "real" if delta["excludes_zero"] else "not established"
            print(f"    {left} - {right:16} {delta['mean']:+.3f}  "
                  f"[{delta['low']:+.3f},{delta['high']:+.3f}]  {verdict}")
        dumped[report["repo"]] = outcomes
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as handle:
            json.dump(dumped, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
