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
    truth       the other files that commit changed

The first two are the two tiers preflight prints, and the third is what you get
without resolution. Their union is by definition the third row -- a caller has to name
the symbol -- so the question resolution answers is not "which files" but "which of
these files is worth believing", and only a split table can show whether it does.

Precision is the comparison that means something here. Recall is reported but must be
read carefully: a caller is not obliged to change when a callee does, so no predictor
can reach 1.0, and a predictor that names half the repository will always lead on
recall while being useless to a reader.
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

    def add(self, predicted: set[str], truth: set[str]) -> None:
        self.tp += len(predicted & truth)
        self.fp += len(predicted - truth)
        self.fn += len(truth - predicted)
        self.cases += 1
        self.predicted += len(predicted)

    def row(self) -> dict:
        precision = self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0
        recall = self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0
        return {"precision": precision, "recall": recall,
                "f1": 2 * precision * recall / (precision + recall)
                if precision + recall else 0.0,
                "mean_predictions": self.predicted / self.cases if self.cases else 0.0,
                "cases": self.cases}


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
    scores = {"resolved": Score(), "leads_only": Score(), "name_match": Score()}
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
                            scored_here = True
                used_commits += scored_here
            finally:
                subprocess.run(["git", "-C", repo, "worktree", "remove", "--force",
                                tree], check=False, capture_output=True)
    return {"repo": os.path.basename(repo), "commits_scored": used_commits,
            "results": {name: score.row() for name, score in scores.items()}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--limit", type=int, default=120)
    args = parser.parse_args()
    repos = args.repo or [corpus.ensure(name, url) for name, url in corpus.EXTERNAL]
    for repo in repos:
        report = evaluate(repo, limit=args.limit)
        print(f"\n=== {report['repo']}  ({report['commits_scored']} commits scored)")
        print(f"{'predictor':12} {'prec':>7} {'recall':>7} {'F1':>7} "
              f"{'mean n':>8} {'cases':>7}")
        for name in ("resolved", "leads_only", "name_match"):
            row = report["results"][name]
            print(f"{name:12} {row['precision']:7.3f} {row['recall']:7.3f} "
                  f"{row['f1']:7.3f} {row['mean_predictions']:8.1f} {row['cases']:7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
