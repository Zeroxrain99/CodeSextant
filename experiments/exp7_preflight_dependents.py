"""Would preflight's blast radius be better with a module-level tier?

check gained one in 0.26.0 on measured grounds: files importing a changed module name
the held-out file far more often than resolved callers do. preflight has not, and the
result does not transfer for free. check reads a diff and knows every symbol that moved;
preflight is asked before the edit, about one file and one name, and the name may not
exist yet.

exp2 asked this first and answered it only halfway. As a *tier*, module dependents are
more precise than the leads tier they would replace -- established on three of six
repositories, positive in sign on five. As a *whole answer*, swapping them in is not
established on four of six, and adding them beside the leads is significantly worse on
one. exp2 also says plainly that its ground truth is loose: it scores against "files
that changed in the same commit", and a caller is not obliged to change.

So this asks the tighter question, on the protocol exp4 established for exactly that
reason. One file of a real commit is held out and treated as the thing the author forgot.
The repository is checked out at the parent and nothing is applied, because that is where
preflight runs. preflight is then asked about the files the commit did change, with the
symbols it changed in them, and scored on whether it names the held-out file:

    resolved       the confirmed caller tier
    leads@3        the "?" tier, as the token budget actually leaves it
    dependents@2   files importing the file being edited, cut to a printable two
    now            resolved + leads@3          -- what preflight prints today
    swap           resolved + dependents@2     -- the leads tier replaced
    both           resolved + leads@3 + dependents@2
    whole_now      now + co-change             -- the whole answer as printed
    whole_swap     swap + co-change
    whole_both     both + co-change

Recall is the statistic, as in exp4, and ``mean n`` sits beside it every time: a tier
that names ten files has not earned anything. Differences are bootstrapped per case,
paired, because every predictor sees the same cases.

    python -m experiments.exp7_preflight_dependents --limit 60
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import diffscan, engine, references, storage  # noqa: E402
from experiments import corpus  # noqa: E402
from experiments.exp4_check import paired_difference  # noqa: E402

PREDICTORS = ("resolved", "leads@3", "dependents@2", "now", "swap", "both",
              "whole_now", "whole_swap", "whole_both")
# The same shape exp2 samples, so the two are describing one workload.
MAX_FILES = 3
MAX_SYMBOLS = 2
LEADS_SHOWN = 3
DEPENDENTS_SHOWN = 2


def _git(root: str, *args: str) -> tuple[int, str]:
    done = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.returncode, done.stdout


def _relative(tree: str, paths) -> set[str]:
    return {os.path.relpath(p, tree).replace(os.sep, "/") for p in paths}


def _score_one(repo: str, home: str, sha: str, files: set[str],
               outcomes: dict, sizes: dict) -> int:
    code, parent = _git(repo, "rev-parse", f"{sha}^")
    if code != 0:
        return 0
    parent = parent.strip()
    ordered = sorted(files)
    held_out = next((f for f in ordered if f.endswith(".py")), ordered[0])
    others = [f for f in ordered if f != held_out and f.endswith(".py")]
    if not others:
        return 0

    tree = os.path.join(home, "tree")
    subprocess.run(["git", "-C", repo, "worktree", "add", "-q", "--detach", tree, parent],
                   check=False, capture_output=True)
    if not os.path.isdir(tree):
        return 0
    try:
        engine.index_project(tree, force=True)
        predicted: dict[str, set[str]] = {name: set() for name in PREDICTORS}
        asked = False
        for relative in others[:MAX_FILES]:
            abs_file = os.path.abspath(os.path.join(tree, relative))
            if not os.path.isfile(abs_file):
                continue
            # The symbols this commit went on to change, recovered from the diff and
            # looked up in the tree as it stands *before* it -- which is the state
            # preflight is asked from.
            spans = _changed_spans(repo, parent, sha, relative)
            with storage.ProjectStore.open_readonly(tree) as store:
                names = [item["name"] for item
                         in engine._changed_definitions(store, abs_file, spans)]
            importers = references.module_dependents(
                tree, [relative], skip={relative}, limit=200)
            top = sorted(importers, key=lambda rel: (-importers[rel], rel))
            dependents = set(top[:DEPENDENTS_SHOWN])
            for symbol in names[:MAX_SYMBOLS]:
                answer = engine.preflight(tree, relative, symbol=symbol,
                                          token_budget=100_000)
                blast = answer["blast_radius"]
                resolved = _relative(tree, blast["dependent_files"])
                leads = set(sorted(_relative(tree, blast["name_match_files"]))[:LEADS_SHOWN])
                companions = {entry["path"] for entry in answer["co_change"]}
                predicted["resolved"] |= resolved
                predicted["leads@3"] |= leads
                predicted["dependents@2"] |= dependents
                predicted["now"] |= resolved | leads
                predicted["swap"] |= resolved | dependents
                predicted["both"] |= resolved | leads | dependents
                predicted["whole_now"] |= resolved | leads | companions
                predicted["whole_swap"] |= resolved | dependents | companions
                predicted["whole_both"] |= resolved | leads | dependents | companions
                asked = True
        if not asked:
            return 0
        for name in PREDICTORS:
            # The file being edited is never the answer, and neither is any other file
            # of the commit except the one held out -- but those are legitimate things
            # to name, so only the queried files themselves are removed.
            found = predicted[name] - {f for f in others}
            outcomes[name].append(int(held_out in found))
            sizes[name] += len(found)
        return 1
    finally:
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", tree],
                       check=False, capture_output=True)


def _changed_spans(repo: str, parent: str, sha: str,
                   path: str) -> list[tuple[int, int]]:
    """Old-side line ranges the commit touched, for locating symbols in the parent tree.

    The old side, not the new one: preflight runs before the edit, so the definitions to
    ask about are the ones that exist now and are about to move, at the lines they
    occupy now.
    """
    code, out = _git(repo, "diff", "--unified=0", f"{parent}..{sha}", "--", path)
    if code != 0:
        return []
    spans = []
    for line in out.splitlines():
        match = diffscan._HUNK.match(line)
        if not match:
            continue
        start, length = int(match.group(1)), int(match.group(2) or 1)
        if length:
            spans.append((start, start + length - 1))
    return spans


def evaluate(repo: str, *, limit: int = 60, seed: int = 0,
             warmup_fraction: float = 0.3) -> dict:
    commits = corpus.history(repo)
    warmup = int(len(commits) * warmup_fraction)
    # Two Python files at least, not one: one is held out and the rest are what
    # preflight gets asked about, so a commit touching a single module has no query in
    # it. exp4's rule allowed those because check reads a whole diff at once.
    eligible = [index for index, (_sha, files) in enumerate(commits)
                if index >= warmup and 2 <= len(files) <= 25
                and sum(1 for f in files if f.endswith(".py")) >= 2]
    random.Random(seed).shuffle(eligible)
    sampled = set(eligible[:limit])

    outcomes: dict[str, list[int]] = {name: [] for name in PREDICTORS}
    sizes: dict[str, int] = dict.fromkeys(PREDICTORS, 0)
    scored = 0
    with tempfile.TemporaryDirectory() as home:
        os.environ["CODESEXTANT_HOME"] = home
        for index, (sha, files) in enumerate(commits):
            if index in sampled:
                scored += _score_one(repo, home, sha, files, outcomes, sizes)
    return {"repo": os.path.basename(repo), "scored": scored,
            "outcomes": outcomes, "sizes": sizes}


def _print(report: dict) -> None:
    total = report["scored"] or 1
    print(f"\n=== {report['repo']}  ({report['scored']} held-out cases)")
    print(f"{'predictor':14} {'recall':>8} {'mean n':>8}")
    for name in PREDICTORS:
        print(f"{name:14} {sum(report['outcomes'][name]) / total:8.3f} "
              f"{report['sizes'][name] / total:8.1f}")
    print("  paired differences (same cases, so the difference is the statistic):")
    for left, right in (("dependents@2", "leads@3"), ("swap", "now"), ("both", "now"),
                        ("whole_swap", "whole_now"), ("whole_both", "whole_now")):
        delta = paired_difference(report["outcomes"][left], report["outcomes"][right])
        if not delta:
            continue
        verdict = "real" if delta["excludes_zero"] else "not established"
        print(f"    {left:13} - {right:10} {delta['mean']:+.3f}  "
              f"[{delta['low']:+.3f},{delta['high']:+.3f}]  {verdict}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--limit", type=int, default=60)
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
