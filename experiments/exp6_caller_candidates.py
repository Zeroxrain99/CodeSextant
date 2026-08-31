"""Score every caller-side candidate at once, from one expensive pass.

exp4 established that the caller section is the weak one and rejected the first
candidate for widening it. exp5 says where the losses are. This is the third step:
given a mechanism, which repair is worth building.

The cost of asking that question the obvious way is an hour per candidate, which is
what makes candidates go unmeasured. So this separates the expensive half from the
cheap half. One pass over the corpus writes, for every case, a small table of *features*
for every file that could plausibly be named -- how many changed symbols it mentions,
how many changed modules it imports, whether resolution confirmed it, what co-change
thinks of it, whether it is a test. Scoring a predictor is then a function over that
table, and a new idea costs a second rather than an hour.

    python -m experiments.exp6_caller_candidates --limit 60 --dump features.json
    python -m experiments.exp6_caller_candidates --score features.json

The candidates, and where each came from:

    callers          what ships: jedi-resolved references to changed symbols
    importers        outside files whose imports resolve to a file the change touched.
                     A Python caller must import the module, and module imports resolve
                     with the standard library instead of with jedi, so this is the same
                     question asked where the answer is not conservative.
    importers@k      the same, truncated to the length check already prints
    names@k          files naming a changed symbol, ranked by how many -- the candidate
                     exp4 rejected, kept as the control it became
    names_imports    files that both name a changed symbol and import a changed module
    names_cochange   files that name a changed symbol and that history also links to the
                     change -- the handoff's "combine the name-level signal with
                     co-change confidence rather than with itself"
    test_names       test files naming a changed symbol, the third untried idea

Recall is measured against the held-out file, as in exp4, and ``mean_n`` is reported
beside it every time: a predictor that names twenty files per case has not won anything,
which is the finding exp4 already recorded once. Differences against what ships are
bootstrapped as paired differences over cases, because both predictors see the same
cases and two separate intervals understate that badly.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import random
import subprocess
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import diffscan, engine, references, storage  # noqa: E402
from experiments import corpus  # noqa: E402
from experiments.exp4_check import paired_difference  # noqa: E402

CANDIDATES = ("check", "callers", "callers_unbudgeted", "check_unbudgeted",
              "importers", "importers@k", "importers_cochange@k",
              "importers_names@k", "check+importers@k", "check+importers@2",
              "names@k", "names_imports", "names_cochange", "test_names",
              "check+dependents@2", "check+importers@2/cut10",
              "check+importers@2/cut20", "check+importers@2/cut40",
              "check+importers@2/cut80", "shipped", "check+shipped")


def _git(root: str, *args: str) -> tuple[int, str]:
    done = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.returncode, done.stdout


def _module_targets(tree: str, relative: str) -> set[str]:
    """Every import path that would land on this file, as dotted names.

    A file is imported under as many names as it has plausible roots: ``requests``
    keeps its package under ``src/``, so ``src/requests/sessions.py`` is imported as
    ``requests.sessions`` and never as ``src.requests.sessions``. Rather than guess the
    layout, every suffix of the path is offered and the importer decides which one it
    actually wrote.
    """
    if not relative.endswith(".py"):
        return set()
    parts = relative[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return set()
    return {".".join(parts[index:]) for index in range(len(parts))}


def _imported_modules(abs_file: str, relative: str) -> set[str]:
    """Dotted module names this file imports, with relative imports made absolute.

    Read with ``ast`` rather than with a regex because ``from . import x`` and
    ``from ..pkg import y`` carry the importing file's own position in the package, and
    a text match cannot recover it. Both forms are common in exactly the libraries this
    corpus is made of.
    """
    try:
        with open(abs_file, "rb") as handle:
            tree = ast.parse(handle.read(), filename=abs_file)
    except (OSError, SyntaxError, ValueError):
        return set()
    package = relative.split("/")[:-1]
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
                out.update(alias.name.rsplit(".", index)[0]
                           for index in range(1, alias.name.count(".") + 1))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:len(package) - node.level + 1]
                prefix = ".".join([*base, node.module]) if node.module else ".".join(base)
            else:
                prefix = node.module or ""
            if not prefix:
                continue
            out.add(prefix)
            # ``from pkg.mod import name`` also reaches ``pkg.mod.name`` when the name
            # is itself a module, which is how a package re-exports a submodule.
            out.update(f"{prefix}.{alias.name}" for alias in node.names
                       if alias.name != "*")
    return out


def _iter_outside(tree: str, changed: set[str]):
    for dirpath, dirnames, filenames in os.walk(tree):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__", ".venv", "venv",
                                    "node_modules", ".mypy_cache", ".pytest_cache",
                                    "build", "dist", ".tox")]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            absolute = os.path.join(dirpath, name)
            relative = os.path.relpath(absolute, tree).replace(os.sep, "/")
            if relative in changed:
                continue
            yield relative, absolute


def _is_test(relative: str) -> bool:
    base = os.path.basename(relative)
    return (base.startswith("test_") or base.endswith("_test.py")
            or "tests/" in relative or relative.startswith("test/"))


def _changed_names(tree: str, applied: list[str]) -> list[str]:
    """The names check would resolve, in the order check would resolve them.

    Order matters and is the reason this mirrors check rather than collecting a set:
    only the first ``CODESEXTANT_CHECK_MAX_SYMBOLS`` are ever resolved, so a file whose
    only mention is of the twelfth changed symbol is unreachable for a reason that has
    nothing to do with resolution being conservative.
    """
    names: list[str] = []
    with storage.ProjectStore.open_readonly(tree) as store:
        for relative in sorted(applied):
            abs_file = os.path.abspath(os.path.join(tree, relative))
            if not os.path.isfile(abs_file):
                continue
            ranges = diffscan.changed_ranges(tree, relative)
            names.extend(item["name"] for item
                         in engine._changed_definitions(store, abs_file, ranges["added"]))
    return [name for name in names if name]


def _features(tree: str, applied: list[str], result: dict,
              names_in_order: list[str]) -> dict[str, dict]:
    """One row per outside Python file that any caller-side signal could reach."""
    changed = set(applied)
    modules = {module for relative in applied for module in _module_targets(tree, relative)}

    resolved = {path for entry in result.get("callers") or []
                for path in entry.get("callers") or []}
    companions = {entry["path"]: entry.get("confidence", 0.0)
                  for entry in result.get("companions") or []}

    rows: dict[str, dict] = {}
    for relative, absolute in _iter_outside(tree, changed):
        try:
            with open(absolute, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        hit = [index for index, name in enumerate(names_in_order)
               if references._word_re(name).search(text)]
        imports = len(_imported_modules(absolute, relative) & modules)
        confidence = companions.get(relative, 0.0)
        if not (hit or imports or confidence or relative in resolved):
            continue
        rows[relative] = {"names": len(set(names_in_order[index] for index in hit)),
                          # Where in check's queue this file first becomes reachable.
                          "first": hit[0] if hit else -1,
                          "imports": imports,
                          "resolved": int(relative in resolved),
                          "cochange": confidence, "test": int(_is_test(relative))}
    return rows


def _collect(repo: str, home: str, sha: str, files: set[str], cases: list) -> int:
    code, parent = _git(repo, "rev-parse", f"{sha}^")
    if code != 0:
        return 0
    parent = parent.strip()
    ordered = sorted(files)
    held_out = next((f for f in ordered if f.endswith(".py")), ordered[0])
    applied = [f for f in ordered if f != held_out]

    tree = os.path.join(home, "tree")
    subprocess.run(["git", "-C", repo, "worktree", "add", "-q", "--detach", tree, parent],
                   check=False, capture_output=True)
    if not os.path.isdir(tree):
        return 0
    try:
        restored = subprocess.run(["git", "-C", tree, "checkout", sha, "--", *applied],
                                  capture_output=True, text=True)
        if restored.returncode != 0:
            return 0
        engine.index_project(tree, force=True)
        result = engine.check(tree, token_budget=100_000)
        names_in_order = _changed_names(tree, applied)

        # The same question asked with the queue removed. "Only the first ten symbols
        # are resolved" is the cheapest explanation for a thin caller section and the
        # easiest to act on, so it is worth one extra resolution pass to find out
        # whether it is the true one. Anything this finds and the budgeted run does not
        # is recall a larger budget would buy, at a cost this measures rather than
        # assumes.
        previous = os.environ.get("CODESEXTANT_CHECK_MAX_SYMBOLS")
        os.environ["CODESEXTANT_CHECK_MAX_SYMBOLS"] = "500"
        try:
            unbudgeted = engine.check(tree, token_budget=100_000)
        finally:
            if previous is None:
                os.environ.pop("CODESEXTANT_CHECK_MAX_SYMBOLS", None)
            else:
                os.environ["CODESEXTANT_CHECK_MAX_SYMBOLS"] = previous

        rebuilt = {match["path"] for entry in result.get("rebuilt") or []
                   for match in entry.get("matches") or []}
        cases.append({
            "sha": sha, "held_out": held_out, "applied": applied,
            "definitions": len(names_in_order),
            "features": _features(tree, applied, result, names_in_order),
            "companions": [entry["path"] for entry in result.get("companions") or []],
            "callers": sorted({path for entry in result.get("callers") or []
                               for path in entry.get("callers") or []}),
            "callers_unbudgeted": sorted({path for entry in unbudgeted.get("callers") or []
                                          for path in entry.get("callers") or []}),
            "rebuilt": sorted(rebuilt),
            # What the shipped tier really produced, so the candidate can be scored as
            # the code that would run rather than as the prototype that measured it.
            "dependents": [entry["path"] for entry in result.get("dependents") or []],
        })
        return 1
    finally:
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", tree],
                       check=False, capture_output=True)


def collect(repo: str, *, limit: int = 60, seed: int = 0,
            warmup_fraction: float = 0.3) -> dict:
    commits = corpus.history(repo)
    warmup = int(len(commits) * warmup_fraction)
    eligible = [index for index, (_sha, files) in enumerate(commits)
                if index >= warmup and 2 <= len(files) <= 25
                and any(f.endswith(".py") for f in files)]
    random.Random(seed).shuffle(eligible)
    sampled = set(eligible[:limit])

    cases: list = []
    with tempfile.TemporaryDirectory() as home:
        os.environ["CODESEXTANT_HOME"] = home
        for index, (sha, files) in enumerate(commits):
            if index in sampled:
                _collect(repo, home, sha, files, cases)
    return {"repo": os.path.basename(repo), "cases": cases}


# --- scoring, which is pure and therefore free to re-run ---------------------------


def _predict(case: dict, name: str) -> set[str]:
    features = case["features"]
    budget = max(len(set(case["companions"]) | set(case["callers"])
                      | set(case["rebuilt"])), 1)
    if name == "check":
        return set(case["companions"]) | set(case["callers"]) | set(case["rebuilt"])
    if name == "callers":
        return set(case["callers"])
    if name == "callers_unbudgeted":
        return set(case.get("callers_unbudgeted") or ())
    if name == "check_unbudgeted":
        return (set(case["companions"]) | set(case["rebuilt"])
                | set(case.get("callers_unbudgeted") or ()))
    if name == "importers":
        return {path for path, row in features.items() if row["imports"]}
    if name == "names_imports":
        return {path for path, row in features.items()
                if row["imports"] and row["names"]}
    if name == "names_cochange":
        return {path for path, row in features.items()
                if row["names"] and row["cochange"]}
    if name == "test_names":
        return {path for path, row in features.items() if row["test"] and row["names"]}
    if name == "importers@k":
        return _importers_at(features, budget, ("imports", "names"))
    if name == "importers_cochange@k":
        return _importers_at(features, budget, ("cochange", "imports", "names"))
    if name == "importers_names@k":
        return _importers_at(features, budget, ("names", "imports"))
    if name == "check+importers@k":
        return _predict(case, "check") | _importers_at(features, budget,
                                                       ("imports", "names"))
    if name == "check+importers@2":
        return _predict(case, "check") | _importers_at(features, 2, ("imports", "names"))
    if name == "names@k":
        ranked = sorted(((row["names"], path) for path, row in features.items()
                         if row["names"]), key=lambda item: (-item[0], item[1]))
        return {path for _n, path in ranked[:budget]}
    if name.startswith("check+importers@2/cut"):
        # The common-name invariant, applied to dependents: past some number of
        # importers, showing two of them is showing an arbitrary two. Where that number
        # falls is measured here rather than chosen, because every cutoff costs recall
        # and the question is how much.
        cutoff = int(name.rsplit("cut", 1)[1])
        importers = {path for path, row in features.items() if row["imports"]}
        shown = set() if len(importers) > cutoff else _shipped_dependents(case, 2)
        return _predict(case, "check") | shown
    if name == "check+dependents@2":
        return _predict(case, "check") | _shipped_dependents(case, 2)
    if name == "check+shipped":
        return _predict(case, "check") | set(case.get("dependents") or ())
    if name == "shipped":
        return set(case.get("dependents") or ())
    raise KeyError(name)


def _shipped_dependents(case: dict, cap: int) -> set[str]:
    """What the shipped tier would show: the top ``cap`` importers nobody else named.

    Two departures from the candidate that was measured, both of which only ever help
    and both of which are re-measured rather than assumed. Files another section
    already names are passed over instead of spending a slot on a repeat, and the
    ranking drops the tiebreaker on how many changed symbols a file mentions -- pooled
    over six repositories, ranking by imports, by symbol mentions, or by co-change
    scored 0.162, 0.162 and 0.160, so the tiebreaker bought nothing and the plumbing to
    carry it into check would have been paid for nothing.
    """
    already = (set(case["companions"]) | set(case["callers"]) | set(case["rebuilt"]))
    features = case["features"]
    ranked = sorted((path for path, row in features.items()
                     if row["imports"] and path not in already),
                    key=lambda path: (-features[path]["imports"], path))
    return set(ranked[:cap])


def _importers_at(features: dict, budget: int, keys: tuple[str, ...]) -> set[str]:
    """The importers of a changed module, ranked by ``keys`` and cut to ``budget``.

    Truncation is not a detail. exp1 found that a predictor naming fourteen to
    twenty-two files on every query reaches three times the recall and stops being read,
    and exp4 rejected a caller candidate for exactly that. So every candidate here is
    scored at the length check already prints, and the ranking is the only thing that
    varies.
    """
    ranked = sorted((path for path, row in features.items() if row["imports"]),
                    key=lambda path: (*(-features[path][key] for key in keys), path))
    return set(ranked[:budget])


def score(report: dict) -> dict:
    outcomes: dict[str, list[int]] = {name: [] for name in CANDIDATES}
    sizes: Counter = Counter()
    spoke: Counter = Counter()
    for case in report["cases"]:
        for name in CANDIDATES:
            predicted = _predict(case, name)
            outcomes[name].append(int(case["held_out"] in predicted))
            sizes[name] += len(predicted)
            spoke[name] += bool(predicted)
    total = len(report["cases"]) or 1
    return {"repo": report["repo"], "cases": len(report["cases"]),
            "outcomes": outcomes,
            "rows": {name: {"recall": sum(outcomes[name]) / total,
                            "mean_n": sizes[name] / total,
                            "speaks": spoke[name] / total}
                     for name in CANDIDATES}}


def _print(scored: dict) -> None:
    print(f"\n=== {scored['repo']}  ({scored['cases']} cases)")
    print(f"{'candidate':16} {'recall':>8} {'speaks':>8} {'mean n':>8}")
    for name in CANDIDATES:
        row = scored["rows"][name]
        print(f"{name:16} {row['recall']:8.3f} {row['speaks']:8.3f} {row['mean_n']:8.1f}")
    print("  paired against what ships (same cases, so the difference is the statistic):")
    for name in CANDIDATES:
        if name in ("check", "callers"):
            continue
        for reference in ("callers", "check"):
            delta = paired_difference(scored["outcomes"][name],
                                      scored["outcomes"][reference])
            if not delta:
                continue
            verdict = "real" if delta["excludes_zero"] else "not established"
            print(f"    {name:14} - {reference:9} {delta['mean']:+.3f}  "
                  f"[{delta['low']:+.3f},{delta['high']:+.3f}]  {verdict}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--dump", default=None, help="write the feature tables here")
    parser.add_argument("--score", default=None,
                        help="score a dump written earlier instead of collecting one")
    args = parser.parse_args()

    if args.score:
        with open(args.score, encoding="utf-8") as handle:
            for report in json.load(handle):
                _print(score(report))
        return 0

    repos = args.repo or [corpus.ensure(name, url) for name, url in corpus.EXTERNAL]
    reports = []
    for repo in repos:
        report = collect(repo, limit=args.limit)
        reports.append(report)
        _print(score(report))
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as handle:
            json.dump(reports, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
