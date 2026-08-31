"""Is a resolved reference a better guess at "what else has to change" than grep?

The claim under test is the third of preflight's three, and the one CodeSextant's
whole design rests on: that import-resolved references are worth the machinery,
because name matching returns the same shape of answer with far more of it wrong.

Protocol
--------
Each sampled commit is ground truth for one question. The repository is checked out
at the commit's *parent*, so the tool sees the code exactly as an author would before
making the change. The symbols the commit actually modified are recovered from the
diff's hunk ranges. For each of them:

    resolved    files with import-resolved references to the symbol (engine)
    leads_only  files that name the symbol but do not resolve to it -- the `?` tier
    name_match  every file that names it, undifferentiated  (references.name_sweep)
    dependents  files importing the module the symbol lives in, at any length
    dependents@2  the same, cut to what a printed tier could afford
    truth       the other files that commit changed

The last two are a file-level question asked among symbol-level ones. check gained that
tier in 0.26.0 on measured grounds; preflight has not, and the two do not automatically
transfer, because preflight is asked before the edit about a file whose symbol may not
exist yet. They are scored here rather than assumed, on the protocol that already asks
preflight's question. Being file-level they give the same answer for both symbols
sampled from one file, which is not a defect: it is what the predictor is.

The first two are the two tiers preflight prints, and the third is what you get
without resolution. Their union is by definition the third row -- a caller has to name
the symbol -- so the question resolution answers is not "which files" but "which of
these files is worth believing", and only a split table can show whether it does.

Precision is the comparison that means something here. Recall is reported but must be
read carefully: a caller is not obliged to change when a callee does, so no predictor
can reach 1.0, and a predictor that names half the repository will always lead on
recall while being useless to a reader.

Intervals are bootstrapped over commits rather than queries, because the queries inside
one commit share its ground truth and are not independent. They exist because the first
run of this experiment produced one repository where the resolved tier was *less*
precise than the leads tier, and a surprising result without error bars is not a result
either way.
"""
from __future__ import annotations

import argparse
import os
import random
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine, references, storage  # noqa: E402
from experiments import corpus  # noqa: E402

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+")
MAX_FILES_PER_COMMIT = 3
MAX_SYMBOLS_PER_FILE = 2
# What the leads tier amounts to once preflight's token budget has trimmed it. The
# budget pops leads first and stops at three, so three is what a reader usually sees --
# and the sweep is unordered, so those three are an arbitrary three. Scoring the full
# tier as if all of it were printed would flatter it.
LEADS_SHOWN = 3

PREDICTORS = ("resolved", "leads_only", "leads@3", "name_match",
              "dependents", "dependents@2",
              # The three whole answers, which is what a ship decision is actually
              # between: what preflight prints today, the same with the leads tier
              # swapped for module dependents, and the same with both.
              "now", "swap", "both")


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True,
                          capture_output=True, text=True).stdout


def _changed_ranges(repo: str, parent: str, sha: str, path: str) -> list[tuple[int, int]]:
    """Old-side line ranges the commit touched, from the diff's hunk headers."""
    try:
        diff = _git(repo, "diff", "--unified=0", parent, sha, "--", path)
    except subprocess.CalledProcessError:
        return []
    spans = []
    for line in diff.splitlines():
        match = _HUNK.match(line)
        if match:
            start = int(match.group(1))
            length = int(match.group(2) or 1)
            spans.append((start, start + max(length, 1) - 1))
    return spans


def _touched_symbols(store, abs_file: str, spans: list[tuple[int, int]]) -> list[str]:
    rows = store.conn.execute(
        "SELECT name,line,end_line FROM symbols WHERE path=? AND kind IN "
        "('function','method','class')", (abs_file,)).fetchall()
    touched = []
    for row in rows:
        end = row["end_line"] or row["line"]
        if any(start <= end and row["line"] <= stop for start, stop in spans):
            touched.append(row["name"])
    return touched


class Score:
    def __init__(self):
        self.tp = self.fp = self.fn = 0
        self.cases = 0
        self.predicted = 0
        # (tp, fp) per commit, so an interval can be resampled over the unit that is
        # actually independent.
        self.by_commit: list[tuple[int, int]] = []
        self._commit_tp = self._commit_fp = 0

    def start_commit(self) -> None:
        self._commit_tp = self._commit_fp = 0

    def end_commit(self) -> None:
        self.by_commit.append((self._commit_tp, self._commit_fp))

    def add(self, predicted: set[str], truth: set[str]) -> None:
        hit, miss = len(predicted & truth), len(predicted - truth)
        self.tp += hit
        self.fp += miss
        self.fn += len(truth - predicted)
        self.cases += 1
        self.predicted += len(predicted)
        self._commit_tp += hit
        self._commit_fp += miss

    def precision_interval(self, *, seed: int = 0, rounds: int = 2000) -> tuple[float, float]:
        records = [r for r in self.by_commit if r[0] + r[1]]
        if not records:
            return (0.0, 0.0)
        rng = random.Random(seed)
        size = len(records)
        values = []
        for _ in range(rounds):
            tp = fp = 0
            for _i in range(size):
                hit, miss = records[rng.randrange(size)]
                tp += hit
                fp += miss
            values.append(tp / (tp + fp) if tp + fp else 0.0)
        values.sort()
        return (values[int(rounds * 0.025)], values[int(rounds * 0.975)])

    def row(self) -> dict:
        precision = self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0
        recall = self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0
        return {"precision": precision, "recall": recall,
                "f1": 2 * precision * recall / (precision + recall)
                if precision + recall else 0.0,
                "mean_predictions": self.predicted / self.cases if self.cases else 0.0,
                "cases": self.cases}


def paired_precision_difference(left: Score, right: Score, *, seed: int = 0,
                                rounds: int = 4000) -> dict:
    """Bootstrap the difference in precision, resampling commits jointly.

    Both predictors answered the same queries in the same commits, so comparing their
    separate intervals understates the evidence -- two intervals can overlap while every
    commit moves the same way. exp4 found that once already, where it turned a
    conclusion from "not established" to established in all three repositories.

    Commits are the resampled unit because queries inside one commit share its ground
    truth. Commits where neither predictor said anything carry no information about
    precision and drop out.
    """
    pairs = [(a, b) for a, b in zip(left.by_commit, right.by_commit)  # noqa: B905
             if a[0] + a[1] or b[0] + b[1]]
    if not pairs:
        return {}
    rng = random.Random(seed)
    size = len(pairs)
    values = []
    for _ in range(rounds):
        ltp = lfp = rtp = rfp = 0
        for _i in range(size):
            (atp, afp), (btp, bfp) = pairs[rng.randrange(size)]
            ltp += atp
            lfp += afp
            rtp += btp
            rfp += bfp
        values.append((ltp / (ltp + lfp) if ltp + lfp else 0.0)
                      - (rtp / (rtp + rfp) if rtp + rfp else 0.0))
    values.sort()
    low, high = values[int(rounds * 0.025)], values[int(rounds * 0.975)]
    observed = ((left.tp / (left.tp + left.fp) if left.tp + left.fp else 0.0)
                - (right.tp / (right.tp + right.fp) if right.tp + right.fp else 0.0))
    return {"mean": observed, "low": low, "high": high,
            "excludes_zero": low > 0 or high < 0}


def _eligible(repo: str, limit: int, seed: int) -> list[tuple[str, list[str]]]:
    raw = _git(repo, "log", "--no-merges", "--format=%H%x00", "--name-only")
    commits, sha, files = [], None, []
    for line in raw.splitlines():
        if "\0" in line:
            if sha and 2 <= len(files) <= 25 and any(f.endswith(".py") for f in files):
                commits.append((sha, files))
            sha, files = line.split("\0")[0], []
        elif line.strip():
            files.append(line.strip())
    if sha and 2 <= len(files) <= 25 and any(f.endswith(".py") for f in files):
        commits.append((sha, files))
    random.Random(seed).shuffle(commits)
    return commits[:limit]


def evaluate(repo: str, *, limit: int = 120, seed: int = 0) -> dict:
    scores = {name: Score() for name in PREDICTORS}
    used_commits = 0
    with tempfile.TemporaryDirectory() as home:
        os.environ["CODESEXTANT_HOME"] = home
        for sha, files in _eligible(repo, limit, seed):
            try:
                parent = _git(repo, "rev-parse", f"{sha}^").strip()
            except subprocess.CalledProcessError:
                continue
            tree = os.path.join(home, "tree")
            subprocess.run(["git", "-C", repo, "worktree", "add", "-q", "--detach",
                            tree, parent], check=False, capture_output=True)
            if not os.path.isdir(tree):
                continue
            try:
                engine.index_project(tree, force=True)
                for score in scores.values():
                    score.start_commit()
                scored_here = False
                with storage.ProjectStore.open_readonly(tree) as store:
                    python_files = [f for f in files if f.endswith(".py")
                                    and os.path.isfile(os.path.join(tree, f))]
                    for path in python_files[:MAX_FILES_PER_COMMIT]:
                        abs_file = os.path.abspath(os.path.join(tree, path))
                        spans = _changed_ranges(repo, parent, sha, path)
                        symbols = _touched_symbols(store, abs_file, spans)
                        truth = {os.path.abspath(os.path.join(tree, f))
                                 for f in files if f != path}
                        # Computed once per file: importers depend on the module, not
                        # on which symbol inside it the author is about to touch.
                        importers = references.module_dependents(
                            tree, [path], skip={path}, limit=200)
                        dependents = {os.path.abspath(os.path.join(tree, rel))
                                      for rel in importers}
                        top = sorted(importers, key=lambda rel: (-importers[rel], rel))[:2]
                        dependents_cut = {os.path.abspath(os.path.join(tree, rel))
                                          for rel in top}
                        for symbol in symbols[:MAX_SYMBOLS_PER_FILE]:
                            result = engine.find_references(
                                tree, symbol, def_path=abs_file,
                                include_low_confidence=False, persist=False)
                            resolved = {os.path.abspath(r["src_path"])
                                        for r in result["high_confidence"]} - {abs_file}
                            named = {os.path.abspath(p) for p in references.name_sweep(
                                tree, symbol, lang="python", limit=400).files} - {abs_file}
                            scores["resolved"].add(resolved, truth)
                            scores["leads_only"].add(named - resolved, truth)
                            scores["name_match"].add(named, truth)
                            scores["dependents"].add(dependents, truth)
                            scores["dependents@2"].add(dependents_cut, truth)
                            leads = named - resolved
                            leads_cut = set(sorted(leads)[:LEADS_SHOWN])
                            scores["leads@3"].add(leads_cut, truth)
                            scores["now"].add(resolved | leads_cut, truth)
                            scores["swap"].add(resolved | dependents_cut, truth)
                            scores["both"].add(
                                resolved | leads_cut | dependents_cut, truth)
                            scored_here = True
                for score in scores.values():
                    score.end_commit()
                used_commits += scored_here
            finally:
                subprocess.run(["git", "-C", repo, "worktree", "remove", "--force",
                                tree], check=False, capture_output=True)
    comparisons = {}
    for left, right in (("dependents@2", "leads@3"), ("swap", "now"), ("both", "now")):
        delta = paired_precision_difference(scores[left], scores[right])
        if delta:
            comparisons[f"{left} - {right}"] = delta
    return {"repo": os.path.basename(repo), "commits_scored": used_commits,
            "results": {name: dict(score.row(),
                                   precision_ci=score.precision_interval())
                        for name, score in scores.items()},
            "comparisons": comparisons}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--limit", type=int, default=120)
    args = parser.parse_args()
    repos = args.repo or [corpus.ensure(name, url) for name, url in corpus.EXTERNAL]
    for repo in repos:
        report = evaluate(repo, limit=args.limit)
        print(f"\n=== {report['repo']}  ({report['commits_scored']} commits scored)")
        print(f"{'predictor':14} {'prec':>7} {'prec 95% CI':>16} {'recall':>7} "
              f"{'F1':>7} {'mean n':>8} {'cases':>7}")
        for name in PREDICTORS:
            row = report["results"][name]
            low, high = row["precision_ci"]
            print(f"{name:14} {row['precision']:7.3f} "
                  f"{f'[{low:.3f},{high:.3f}]':>16} {row['recall']:7.3f} "
                  f"{row['f1']:7.3f} {row['mean_predictions']:8.1f} {row['cases']:7}")
        print("  paired precision differences (same queries, so this is the statistic):")
        for label, delta in report["comparisons"].items():
            verdict = "real" if delta["excludes_zero"] else "not established"
            print(f"    {label:24} {delta['mean']:+.3f}  "
                  f"[{delta['low']:+.3f},{delta['high']:+.3f}]  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
