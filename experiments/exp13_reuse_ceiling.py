"""How often is a function somebody just wrote one the repository already had?

`preflight`'s first question is "does this already exist". exp3 measured whether the
check *finds* a known duplicate given its name. It could not measure the thing that
bounds the whole feature: **how often the failure happens at all.** A check cannot
prevent more wheels than get reinvented, and nobody had counted them. `docs/roadmap.md`
D1 has carried "the ceiling is unknown" since it was written.

What is counted
---------------
Replaying real commits: every function a commit *added*, and whether a function with the
same shape already existed in the parent tree. Shape rather than name, because a wheel
reinvented under the same name is one grep already finds -- the interesting reinvention
is the one with a new name.

Then the stratum that decides what a *name-based* check could ever reach:

    same name       grep finds it. The reuse check has to not be worse than free
    shares a word   `parse_timestamp` against `timestamp_parser`. Reachable from a name
    shares nothing  `seconds_from_clock` against `normalise_duration`. **Unreachable
                    from a name and an intention, by construction.** This stratum is the
                    argument for comparing bodies, and its size is the argument's size

The shape hash is written here rather than imported from `codesextant`
--------------------------------------------------------------------
`find_duplicates` would give the same answer and that is the problem: a ground truth
computed by the thing under test measures the tool's agreement with itself. This walks
the AST and records node *types* only -- identifiers, literals and formatting discarded
-- which is the same idea implemented independently, and it can disagree.

Bodies below `_MIN_NODES` are ignored. Two three-line wrappers have the same shape as a
matter of arithmetic, not of duplication, and counting them would put the prevalence
wherever the threshold was set.

Dunder methods are ignored too, and the first run is why. It reported tqdm at 0.312 --
and 37 of those 40 "duplicates" were `__init__` matching another `__init__`. Two
constructors that assign the same number of attributes have the same shape as a matter
of Python, not of anybody reinventing anything. Counting them measures how many classes
a project has.

Second question, asked of the same population
---------------------------------------------
If 0.994 of duplicates are reachable from the name, how much of that does the shipped
matcher actually reach? `preflight` scores names by Jaccard overlap with a floor of 0.5,
which rejects `escape_control_codes` against `make_control_codes_readable`: they share
the whole meaningful core and Jaccard is 2/5, because the longer name is punished for
being longer.

So three matchers are scored on the duplicates this experiment found, against the cost
that decides whether a looser one is usable at all -- **how many functions in the tree it
would also surface for the same query.** A matcher that names everything has recall 1.0
and is worthless, which is the failure mode every other experiment in this directory
guards against with a matched budget.

    shipped       what `preflight` runs today: `engine._name_similarity` over 0.5
    containment   the same word overlap divided by the *shorter* name's length, so a
                  long name does not lose for being long
    any_word      one shared word. The loosest thing that could be called matching, here
                  to price the ceiling rather than to be proposed

    python -m experiments.exp13_reuse_ceiling --limit 60
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine  # noqa: E402
from experiments import corpus  # noqa: E402

MATCHERS = ("shipped", "containment", "any_word")

# Small enough to include a real helper, large enough that `return self._x` is not a
# duplicate of `return self._y`. Reported beside the result because the number moves
# with it and a prevalence quoted without it means nothing.
_MIN_NODES = 25

_WORD = re.compile(r"[a-z0-9]+")


def _git(root: str, *args: str) -> tuple[int, str]:
    done = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.returncode, done.stdout


def _read_blobs(root: str, sha: str, paths) -> dict[str, str]:
    wanted = list(paths)
    if not wanted:
        return {}
    request = "".join(f"{sha}:{relative}\n" for relative in wanted)
    done = subprocess.run(["git", "-C", root, "cat-file", "--batch"],
                          input=request.encode(), stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL)
    out, found, cursor = done.stdout, {}, 0
    for relative in wanted:
        newline = out.find(b"\n", cursor)
        if newline < 0:
            break
        header = out[cursor:newline].decode("utf-8", "replace").split()
        cursor = newline + 1
        if len(header) < 3:
            continue
        size = int(header[2])
        found[relative] = out[cursor:cursor + size].decode("utf-8", "replace")
        cursor += size + 1
    return found


def _shape(node) -> tuple[str, int]:
    """The structure of a function body with every name and value removed.

    Node types in walk order. Two functions share a shape when they do the same thing
    to different things, which is what "somebody wrote this twice" looks like once the
    naming is stripped away.
    """
    kinds = [type(child).__name__ for child in ast.walk(node)]
    return ("|".join(kinds), len(kinds))


def _functions(source: str) -> dict[str, tuple[str, int]]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("__") and node.name.endswith("__"):
            continue  # a constructor is required, not reinvented
        shape, size = _shape(node)
        if size >= _MIN_NODES:
            found[node.name] = (shape, size)
    return found


def _python_files(root: str, sha: str) -> list[str]:
    code, out = _git(root, "ls-tree", "-r", "--name-only", sha)
    return [line for line in out.splitlines() if line.endswith(".py")] if code == 0 \
        else []


def _tree_shapes(root: str, sha: str, cache: dict) -> tuple[dict, list[str]]:
    """({shape: [names]}, every function name in the tree) at one commit, memoised.

    The second half is what prices a matcher: recall means nothing without the number of
    things the same matcher would also have surfaced.
    """
    if sha not in cache:
        shapes: dict[str, list[str]] = {}
        names: list[str] = []
        for source in _read_blobs(root, sha, _python_files(root, sha)).values():
            for name, (shape, _size) in _functions(source).items():
                shapes.setdefault(shape, []).append(name)
                names.append(name)
        cache[sha] = (shapes, sorted(set(names)))
    return cache[sha]


def _tokens(name: str) -> frozenset[str]:
    return frozenset(_WORD.findall(name.lower()))


def _matches(matcher: str, left: frozenset[str], right: frozenset[str],
             left_name: str, right_name: str) -> bool:
    if matcher == "shipped":
        return engine._name_similarity(left_name, right_name) >= 0.5
    shared = left & right
    if not shared:
        return False
    if matcher == "any_word":
        return True
    return len(shared) / min(len(left), len(right)) >= 0.5


def _stratum(new_name: str, existing: list[str]) -> str:
    if new_name in existing:
        return "same name"
    new_words = set(_WORD.findall(new_name.lower()))
    for other in existing:
        if new_words & set(_WORD.findall(other.lower())):
            return "shares a word"
    return "shares nothing"


def evaluate(repo_path: str, *, limit: int = 60, seed: int = 0,
             warmup_fraction: float = 0.3) -> dict:
    commits = corpus.history(repo_path)
    warmup = int(len(commits) * warmup_fraction)
    candidates = [(index, sha, files) for index, (sha, files) in enumerate(commits)
                  if index >= warmup and any(f.endswith(".py") for f in files)
                  and len(files) <= 25]
    random.Random(seed).shuffle(candidates)

    cache: dict[str, dict] = {}
    strata: Counter = Counter()
    reached: Counter = Counter()
    cost: Counter = Counter()
    queries = 0
    by_stratum: dict[str, list[dict]] = {"same name": [], "shares a word": [],
                                         "shares nothing": []}
    added_total = 0
    scored = 0

    for _index, sha, files in candidates:
        if scored >= limit:
            break
        code, parent = _git(repo_path, "rev-parse", f"{sha}^")
        if code != 0:
            continue
        parent = parent.strip()
        python = sorted(f for f in files if f.endswith(".py"))
        before = _read_blobs(repo_path, parent, python)
        after = _read_blobs(repo_path, sha, python)

        added: list[tuple[str, str]] = []
        for relative in python:
            was = _functions(before.get(relative, ""))
            now = _functions(after.get(relative, ""))
            for name, (shape, _size) in now.items():
                if name not in was:
                    added.append((name, shape))
        if not added:
            continue
        scored += 1
        added_total += len(added)

        known, all_names = _tree_shapes(repo_path, parent, cache)
        token_cache = {other: _tokens(other) for other in all_names}
        for name, shape in added:
            mine = _tokens(name)
            # What each matcher would surface for this query, duplicate or not. Counted
            # for every added function so the cost is an average over queries actually
            # made rather than over the ones that happened to hit.
            for matcher in MATCHERS:
                surfaced = sum(1 for other in all_names
                               if other != name
                               and _matches(matcher, mine, token_cache[other],
                                            name, other))
                cost[matcher] += surfaced
            queries += 1

            existing = known.get(shape)
            if not existing:
                strata["not a duplicate"] += 1
                continue
            for matcher in MATCHERS:
                if any(_matches(matcher, mine, _tokens(other), name, other)
                       for other in existing):
                    reached[matcher] += 1
            where = _stratum(name, existing)
            strata[where] += 1
            # Examples for every stratum, not only the interesting one: the first run
            # reported a prevalence three times too high and it was visible in the
            # examples long before it was visible in the rate.
            if len(by_stratum[where]) < 4:
                by_stratum[where].append(
                    {"repo": os.path.basename(repo_path), "added": name,
                     "already_there": sorted(existing)[:3]})

    return {"repo": os.path.basename(repo_path), "commits_scored": scored,
            "functions_added": added_total, "strata": dict(strata),
            "reached": dict(reached), "cost": dict(cost), "queries": queries,
            "examples": by_stratum, "min_nodes": _MIN_NODES}


def _print(report: dict) -> None:
    total = report["functions_added"] or 1
    strata = report["strata"]
    duplicated = total - strata.get("not a duplicate", 0)
    print(f"\n=== {report['repo']}  ({report['functions_added']} functions added over "
          f"{report['commits_scored']} commits)")
    print(f"  already existed in some shape: {duplicated}/{total} = "
          f"{duplicated / total:.3f}   <- the ceiling for any reuse check")
    for name in ("same name", "shares a word", "shares nothing"):
        count = strata.get(name, 0)
        share = count / duplicated if duplicated else 0.0
        print(f"    {name:16} {count:5}  {share:.3f} of the duplicates")
    duplicates = total - strata.get("not a duplicate", 0)
    if duplicates and report.get("queries"):
        print(f"  {'matcher':13} {'reaches':>9} {'names per query':>17}")
        for matcher in MATCHERS:
            found = report["reached"].get(matcher, 0)
            print(f"  {matcher:13} {found / duplicates:9.3f} "
                  f"{report['cost'].get(matcher, 0) / report['queries']:17.1f}")
    for name, shown in report["examples"].items():
        for example in shown[:2]:
            print(f"      [{name}] {example['added']} repeats "
                  f"{', '.join(example['already_there'])}")


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
