"""Does co-change actually predict the companion change, or does it just look clever?

The claim under test is the second of preflight's three: that history knows which
files have to change together, including the pairings nothing in the source mentions,
and that this beats what a careful person would guess without it.

Protocol
--------
Prequential (rolling origin), which is the only honest way to evaluate a predictor
trained on the same history it is scored against. Commits are replayed oldest first.
Before commit C is counted into the model, every file in C is used as a query: the
predictor sees only commits strictly older than C, and is scored against the rest of
C as ground truth. Nothing about C can reach the model that predicts it.

The treatment is not a reimplementation. Counting goes through ``cochange.tally`` and
the query through ``ProjectStore.cochange_rules_for`` -- the same two calls preflight
makes -- so what is measured is what ships.

Controls
--------
none        predicts nothing. The floor, and the honest description of an agent that
            does not consult history at all.
same_dir    every other file ever touched in the same directory. "Look around you."
frequency   the globally most-changed files. "What usually changes."

At a matched budget both are ranked by how often each candidate has changed, not
truncated arbitrarily: a control cut alphabetically would be a straw man, and beating
a straw man would say nothing.

The two controls are also scored at a *matched budget*: given exactly as many guesses
as co-change made for that query, are co-change's guesses better ones? Without that,
a control can buy recall with an unusable number of predictions and the comparison
says nothing.
"""
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import cochange, storage  # noqa: E402
from experiments import corpus  # noqa: E402

PREDICTORS = ("cochange", "same_dir", "frequency", "same_dir@k", "frequency@k", "none")


class Tally:
    """Micro-averaged counts plus the per-case record a bootstrap needs."""

    def __init__(self):
        self.tp = self.fp = self.fn = 0
        self.cases = 0
        self.alerts = 0          # cases where the predictor said anything
        self.hits = 0            # cases where what it said contained something real
        self.predicted = 0       # total predictions, for mean list length

    def add(self, predicted: set[str], truth: set[str]) -> None:
        hit = predicted & truth
        self.tp += len(hit)
        self.fp += len(predicted - truth)
        self.fn += len(truth - predicted)
        self.cases += 1
        self.predicted += len(predicted)
        if predicted:
            self.alerts += 1
            if hit:
                self.hits += 1

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def row(self) -> dict:
        return {
            "precision": self.precision, "recall": self.recall, "f1": self.f1,
            "alert_rate": self.alerts / self.cases if self.cases else 0.0,
            # Of the times it spoke up, how often was it saying something true. This is
            # the number an agent feels: a reminder that is usually noise gets ignored.
            "useful_when_it_speaks": self.hits / self.alerts if self.alerts else 0.0,
            "mean_predictions": self.predicted / self.cases if self.cases else 0.0,
            "cases": self.cases,
        }


def evaluate(repo_path: str, *, warmup_fraction: float = 0.3,
             seed: int = 0) -> dict:
    commits = corpus.history(repo_path)
    window = [(sha, files) for sha, files in commits]
    warmup = int(len(window) * warmup_fraction)
    cap = cochange.max_commit_files()
    min_support, min_confidence = cochange.min_support(), cochange.min_confidence()

    changed_total: Counter[str] = Counter()
    directory_files: dict[str, set[str]] = {}
    tallies = {name: Tally() for name in PREDICTORS}
    per_commit: list[dict] = []

    with tempfile.TemporaryDirectory() as home:
        os.environ["CODESEXTANT_HOME"] = home
        project = os.path.join(home, "project")
        os.makedirs(project)
        with storage.ProjectStore.open(project) as store:
            for index, (sha, files) in enumerate(window):
                evaluating = index >= warmup and 2 <= len(files) <= cap
                if evaluating:
                    record = {name: Tally() for name in PREDICTORS}
                    for path in sorted(files):
                        truth = set(files) - {path}
                        rules = store.cochange_rules_for(
                            path, min_support=min_support,
                            min_confidence=min_confidence)
                        treatment = {rule["companion"] for rule in rules}
                        budget = len(treatment)

                        directory = os.path.dirname(path)
                        neighbours = directory_files.get(directory, set()) - {path}
                        frequent = [p for p, _n in changed_total.most_common(60)
                                    if p != path]
                        # Truncating the directory alphabetically would be a weak
                        # control and would flatter the treatment. Rank it by how
                        # often each neighbour has changed, which is what someone
                        # looking around the directory would actually notice.
                        local = sorted(neighbours,
                                       key=lambda p: (-changed_total[p], p))

                        predictions = {
                            "cochange": treatment,
                            "same_dir": neighbours,
                            "frequency": set(frequent[:20]),
                            "same_dir@k": set(local[:budget]),
                            "frequency@k": set(frequent[:budget]),
                            "none": set(),
                        }
                        for name, predicted in predictions.items():
                            tallies[name].add(predicted, truth)
                            record[name].add(predicted, truth)
                    per_commit.append({name: (t.tp, t.fp, t.fn, t.alerts, t.hits,
                                              t.cases)
                                       for name, t in record.items()})

                # Only now does this commit become part of what the model knows.
                changes, pairs = cochange.tally([(sha, files)])
                if changes:
                    store.add_cochange_counts(changes, pairs, sha)
                for path in files:
                    changed_total[path] += 1
                    directory_files.setdefault(os.path.dirname(path), set()).add(path)

    return {
        "repo": os.path.basename(repo_path),
        "commits_read": len(window),
        "warmup": warmup,
        "evaluated_commits": len(per_commit),
        "results": {name: tally.row() for name, tally in tallies.items()},
        "per_commit": per_commit,
        "bootstrap": _bootstrap(per_commit, seed=seed),
    }


def _bootstrap(per_commit: list[dict], *, seed: int, rounds: int = 1000) -> dict:
    """Resample commits, not cases: cases inside one commit are not independent."""
    if not per_commit:
        return {}
    rng = random.Random(seed)
    samples: dict[str, list[float]] = {name: [] for name in PREDICTORS}
    size = len(per_commit)
    for _ in range(rounds):
        picked = [per_commit[rng.randrange(size)] for _ in range(size)]
        for name in PREDICTORS:
            tp = sum(c[name][0] for c in picked)
            fp = sum(c[name][1] for c in picked)
            fn = sum(c[name][2] for c in picked)
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            samples[name].append(
                2 * precision * recall / (precision + recall) if precision + recall
                else 0.0)
    out = {}
    for name, values in samples.items():
        ordered = sorted(values)
        out[name] = {"f1_lo": ordered[int(rounds * 0.025)],
                     "f1_hi": ordered[int(rounds * 0.975)],
                     "f1_median": statistics.median(ordered)}
    # **The paired difference, because two marginal intervals are the wrong test.**
    # Every round above resamples one set of commits and scores *all* the predictors on
    # it, so the samples were already paired and the pairing was being thrown away at
    # the last step. Reading overlap between two marginal CIs as "no difference" is the
    # classic error: it is conservative in the wrong direction, and on a control that
    # tracks the treatment commit-for-commit it can hide a difference that is present
    # in every single round. What is reported here is the interval of
    # `F1(cochange) - F1(control)` over the same rounds, which is the quantity the
    # comparison is actually about.
    for name in PREDICTORS:
        if name == "cochange":
            continue
        deltas = sorted(a - b for a, b in zip(samples["cochange"], samples[name], strict=True))
        out[name].update({"d_lo": deltas[int(rounds * 0.025)],
                          "d_hi": deltas[int(rounds * 0.975)],
                          "d_median": statistics.median(deltas)})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None,
                        help="path to a repository; repeatable. Defaults to the corpus.")
    parser.add_argument("--warmup", type=float, default=0.3)
    args = parser.parse_args()

    repos = args.repo or [corpus.ensure(name, url) for name, url in corpus.EXTERNAL]
    reports = []
    for repo in repos:
        report = evaluate(repo, warmup_fraction=args.warmup)
        reports.append(report)
        print(f"\n=== {report['repo']}  "
              f"({report['evaluated_commits']} commits evaluated of "
              f"{report['commits_read']} read, {report['warmup']} warm-up)")
        print(f"{'predictor':14} {'prec':>6} {'recall':>7} {'F1':>6} "
              f"{'F1 95% CI':>16} {'paired dF1 vs cochange':>24} "
              f"{'speaks':>7} {'useful':>7} {'mean n':>7}")
        for name in PREDICTORS:
            row = report["results"][name]
            ci = report["bootstrap"].get(name, {})
            span = (f"[{ci.get('f1_lo', 0):.3f},{ci.get('f1_hi', 0):.3f}]"
                    if ci else "")
            # The paired interval is the comparison; a star marks the ones that exclude
            # zero, which is the only place "better" may be said out loud.
            if "d_lo" in ci:
                beats = " *" if ci["d_lo"] > 0 else ("  " if ci["d_hi"] > 0 else " !")
                delta = (f"{ci['d_median']:+.3f} "
                         f"[{ci['d_lo']:+.3f},{ci['d_hi']:+.3f}]{beats}")
            else:
                delta = ""
            print(f"{name:14} {row['precision']:6.3f} {row['recall']:7.3f} "
                  f"{row['f1']:6.3f} {span:>16} {delta:>24} "
                  f"{row['alert_rate']:7.3f} "
                  f"{row['useful_when_it_speaks']:7.3f} {row['mean_predictions']:7.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
