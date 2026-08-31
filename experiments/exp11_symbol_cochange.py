"""Is "you changed *this function*" a better question than "you changed this file"?

Symbol-level co-change is mined, stored, shipped and asserted in `check` and `preflight`,
and it has never been scored. It is the last retrievable claim in this tool with no number
at all, which is why `HANDOFF.md` puts it first among the next steps.

The claim, from `cochange.mine_symbols`' own docstring: narrowing the *query* from a
two-thousand-line module to one function makes the answer sharper, while keeping the
answer a file so the rule still clears the support thresholds. The obvious risk is the
opposite: a symbol changes far less often than its file, so its rules rest on less
support and may simply be noisier versions of the file's.

Protocol
--------
Prequential, the same shape as exp1 and for the same reason: a predictor mined from the
history it is scored on has to be scored on history it has not seen. Commits are replayed
oldest first, and a commit is used as a query only against strictly older commits.

For each sampled commit and each Python file it changed, the ground truth is the *other*
files in that commit.

    symbol+file **what actually ships.** `engine._merge_cochange` puts symbol-scoped
                rules first and adds the file-scoped ones they do not already cover, so
                the section a reader sees is the union with the symbol ones labelled.
                Scoring `symbol` alone would be scoring a component, not the product
    symbol      companions of the symbols this commit actually touched in that file --
                the narrowed question, through the shipped `cochange.mine_symbols`
    file        companions of the file as a whole, through the same
                `ProjectStore.cochange_rules_for` that `check` calls. **This is the
                control that matters**: the symbol tier only earns its place by adding
                something to this, since this is what the tool would print without it
    file@k      the same, truncated to the symbol predictor's budget, because a predictor
                that names more files buys recall with volume
    same_dir@k  neighbours in the directory, ranked by how often each has changed
    frequency@k the project's most-changed files

Every control is given exactly as many guesses as the treatment made and ranked by what
would rank a real answer, because this directory once turned a real 1.4x into a claimed
5.9x by truncating a baseline alphabetically.

One deviation, stated because it is a deviation: `cochange.read_symbol_commits` shells out
to `git log -p` for one file, and the mining is re-run per query against a shrinking
window. The git read does not depend on the window, so it is memoised per file. The
function under test is still the shipped `mine_symbols`; only the redundant subprocess is
removed.

    python -m experiments.exp11_symbol_cochange --limit 300
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import cochange, storage  # noqa: E402
from experiments import corpus  # noqa: E402
from experiments.exp1_cochange import Tally  # noqa: E402

PREDICTORS = ("symbol+file", "symbol", "file", "file@k", "same_dir@k", "frequency@k")


def paired_bootstrap(per_commit: list[dict], left: str, right: str, *,
                     seed: int = 0, rounds: int = 1000) -> dict:
    """The difference in recall between two predictors, resampling *commits*.

    Commits rather than cases, because the files inside one commit are not independent
    of each other -- they were changed together, which is the very thing being
    predicted. Paired, because both predictors see exactly the same queries, and two
    overlapping one-sample intervals can hide a difference every case agrees on.
    """
    if not per_commit:
        return {}
    rng = random.Random(seed)
    size = len(per_commit)
    deltas = []
    for _ in range(rounds):
        picked = [per_commit[rng.randrange(size)] for _ in range(size)]
        scores = []
        for name in (left, right):
            tp = sum(c[name][0] for c in picked)
            fn = sum(c[name][2] for c in picked)
            scores.append(tp / (tp + fn) if tp + fn else 0.0)
        deltas.append(scores[0] - scores[1])
    deltas.sort()
    low, high = deltas[int(rounds * 0.025)], deltas[int(rounds * 0.975)]
    return {"mean": statistics.fmean(deltas), "low": low, "high": high,
            "excludes_zero": low > 0 or high < 0}


def _memoise_symbol_reads():
    """One `git log -p` per file instead of one per query, with the same answer.

    The read is over the file's whole history and the window is applied afterwards by
    `mine_symbols`, so caching it changes nothing about what is measured -- it only stops
    the experiment running the same subprocess four hundred times.
    """
    cache: dict[tuple[str, str], dict | None] = {}
    original = cochange.read_symbol_commits

    def cached(repo_path: str, rel_path: str, **kwargs):
        key = (repo_path, rel_path)
        if key not in cache:
            cache[key] = original(repo_path, rel_path, **kwargs)
        return cache[key]

    cochange.read_symbol_commits = cached
    return original


def evaluate(repo_path: str, *, limit: int = 300, warmup_fraction: float = 0.3,
             seed: int = 0) -> dict:
    commits = corpus.history(repo_path)
    warmup = int(len(commits) * warmup_fraction)
    cap = cochange.max_commit_files()
    min_support, min_confidence = cochange.min_support(), cochange.min_confidence()

    changed_total: Counter[str] = Counter()
    directory_files: dict[str, set[str]] = {}
    tallies = {name: Tally() for name in PREDICTORS}
    per_commit: list[dict] = []
    scored = 0
    no_symbol_rule = 0

    restore = _memoise_symbol_reads()
    try:
        with tempfile.TemporaryDirectory() as home:
            os.environ["CODESEXTANT_HOME"] = home
            project = os.path.join(home, "project")
            os.makedirs(project)
            with storage.ProjectStore.open(project) as store:
                for index, (sha, files) in enumerate(commits):
                    if (index >= warmup and 2 <= len(files) <= cap
                            and scored < limit):
                        record = {name: Tally() for name in PREDICTORS}
                        used = False
                        window = commits[:index]
                        for path in sorted(files):
                            if not path.endswith(".py"):
                                continue
                            touched = cochange.read_symbol_commits(repo_path, path)
                            symbols_now = (touched or {}).get(sha) or set()
                            if not symbols_now:
                                # This commit changed no *named* thing in the file --
                                # an import block, a constant, whitespace. The shipped
                                # query would not be asked here either.
                                continue
                            truth = set(files) - {path}
                            mined = cochange.mine_symbols(repo_path, path,
                                                          commits=window)
                            treatment = {rule["companion"]
                                         for rule in mined["rules"]
                                         if rule["symbol"] in symbols_now}
                            budget = len(treatment)
                            if not treatment:
                                no_symbol_rule += 1

                            file_rules = store.cochange_rules_for(
                                path, min_support=min_support,
                                min_confidence=min_confidence)
                            by_file = [rule["companion"] for rule in file_rules]

                            frequent = [p for p, _n in changed_total.most_common(60)
                                        if p != path]
                            local = sorted(
                                directory_files.get(os.path.dirname(path), set())
                                - {path},
                                key=lambda p: (-changed_total[p], p))

                            predictions = {
                                "symbol+file": treatment | set(by_file),
                                "symbol": treatment,
                                "file": set(by_file),
                                "file@k": set(by_file[:budget]),
                                "same_dir@k": set(local[:budget]),
                                "frequency@k": set(frequent[:budget]),
                            }
                            for name, predicted in predictions.items():
                                tallies[name].add(predicted, truth)
                                record[name].add(predicted, truth)
                            used = True
                        if used:
                            scored += 1
                            per_commit.append(
                                {name: (t.tp, t.fp, t.fn, t.alerts, t.hits, t.cases)
                                 for name, t in record.items()})

                    # Only now does this commit become part of what the model knows.
                    changes, pairs = cochange.tally([(sha, files)])
                    if changes:
                        store.add_cochange_counts(changes, pairs, sha)
                    for path in files:
                        changed_total[path] += 1
                        directory_files.setdefault(
                            os.path.dirname(path), set()).add(path)
    finally:
        cochange.read_symbol_commits = restore

    return {
        "repo": os.path.basename(repo_path),
        "evaluated_commits": len(per_commit),
        "queries": tallies["symbol"].cases,
        "silent_symbol_queries": no_symbol_rule,
        "results": {name: tally.row() for name, tally in tallies.items()},
        "per_commit": per_commit,
        "superset_gain": superset_gain(per_commit, "symbol+file", "file"),
        "differences": {
            f"{left}-{right}": paired_bootstrap(per_commit, left, right, seed=seed)
            for left, right in (("symbol+file", "file"), ("symbol", "file"),
                                ("symbol", "file@k"), ("symbol", "same_dir@k"),
                                ("symbol", "frequency@k"))
        },
    }


def superset_gain(per_commit: list[dict], superset: str, base: str) -> dict:
    """How many true companions the wider predictor gains, and what it prints for them.

    `symbol+file` contains `file` by construction, so its recall can never be lower and
    the paired interval's lower bound is 0 whenever it ever helps -- "excludes zero"
    stops being a test. HANDOFF.md layer 3 carries this trap and its remedy: report the
    count gained beside the interval, and the predictions bought to get them.
    """
    gained = sum(c[superset][0] - c[base][0] for c in per_commit)
    extra = sum((c[superset][0] + c[superset][1]) - (c[base][0] + c[base][1])
                for c in per_commit)
    truth = sum(c[base][0] + c[base][2] for c in per_commit)
    return {"true_companions_gained": gained, "extra_predictions": extra,
            "truth": truth,
            "precision_of_the_addition": gained / extra if extra else 0.0}


def _print(report: dict) -> None:
    print(f"\n=== {report['repo']}  ({report['queries']} symbol queries over "
          f"{report['evaluated_commits']} commits)")
    silent = report["silent_symbol_queries"]
    if report["queries"]:
        print(f"  the symbol side said nothing in {silent}/{report['queries']} "
              f"({silent / report['queries']:.2f}) of them")
    print(f"{'predictor':13} {'precision':>10} {'recall':>8} {'mean n':>8} "
          f"{'useful when it speaks':>23}")
    for name in PREDICTORS:
        row = report["results"][name]
        print(f"{name:13} {row['precision']:10.3f} {row['recall']:8.3f} "
              f"{row['mean_predictions']:8.2f} {row['useful_when_it_speaks']:23.3f}")
    gain = report.get("superset_gain") or {}
    if gain.get("extra_predictions"):
        print(f"  what the symbol tier adds on top of the file tier: "
              f"{gain['true_companions_gained']} more true companions found out of "
              f"{gain['truth']}, for {gain['extra_predictions']} more predictions "
              f"({gain['precision_of_the_addition']:.2f} of the additions were real)")
    print("  paired difference in recall (same queries, so the difference is the "
          "statistic):")
    for key, value in (report.get("differences") or {}).items():
        if not value:
            continue
        verdict = "real" if value["excludes_zero"] else "not established"
        print(f"    {key:24} {value['mean']:+.3f}  "
              f"[{value['low']:+.3f},{value['high']:+.3f}]  {verdict}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--dump", default=None)
    args = parser.parse_args()
    repos = args.repo or [corpus.ensure(name, url) for name, url in corpus.EXTERNAL]
    reports = []
    for repo in repos:
        report = evaluate(repo, limit=args.limit)
        reports.append(report)
        _print(report)
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as handle:
            json.dump(reports, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
