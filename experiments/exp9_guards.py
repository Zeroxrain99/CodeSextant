"""Would `guards` have told you about the fence, before you hit it?

`guards` shipped in 0.28.0 on the strength of exp8, which measured what a guard index
could *contain* -- how many fences there are and whether anyone wrote down why. It never
measured whether the fences it names are the ones that would have blocked you. That is
this experiment, and until it exists the section is a design with unit tests behind it.

Protocol
--------
The same shape as exp4, with one deliberate difference that is the whole point.

exp4 and exp6 hold out ``sorted(files)``' first ``.py`` entry, and path sorting puts
``tests/`` after ``src/``, ``httpie/``, ``rich/`` and most package directories. A guard
file is present in 0.54 to 0.57 of sampled commits and is the held-out one in only 0.06
to 0.12 of them, so **everything in this directory is nearly silent about the guard
case**. Here the held-out file is chosen *because* it holds guards, which is the only
way to ask the question at all.

For each sampled commit: check out the parent, apply every file except one that holds
guards, and ask `guards` what the applied change is about to meet. The held-out file is
the answer -- the commit really did have to touch a fence in it, and the question is
whether a reader would have known before the build told them.

    guards          what ships: three tiers of evidence, ranked, six shown
    guards_symbols  the first two tiers alone -- the version that shipped in 0.28.0,
                    where a fence is reachable only by naming what you changed. Kept as
                    the control the history tier had to beat to be built
    guards_perfile  the version that was built and rejected -- a guard inherits its
                    file's relevance. Kept as a control because the rejection was made
                    by eye, and this is the measurement that should have made it
    cochange@k      guards in the files history says change with this one
    same_dir@k      guards in the directories the change touched
    frequency@k     guards in the project's most-changed files

Two candidates, measured here before either is built -- the rule this directory has paid
for five times. Both exist for the one repository `guards` loses on: jinja, where the
per-file design it rejects scores 0.133 against its 0.067, because a template engine's
tests reach their subjects through indirection and never spell the names. Both take
what ships and fill only the slots it left empty, so what is measured is the addition:

    +filemention    a file names a changed symbol somewhere but no fence in it does.
                    The weakest possible relaxation of the per-guard rule
    +importer       a file *imports a module* you changed and holds fences. A per-file
                    claim like history, but a structural one -- this is the "imports what
                    you changed" tier that was built and removed by eye, now scored

**cochange@k is the control that matters.** `check`'s companion section already names
the forgotten test at 0.169-0.250 recall using nothing but history, and it ships. If
reading the fences themselves does not beat reading the history, `guards` is a longer
way to the same answer and should be told so.

Every control is given exactly as many guards as `guards` printed, and each is ordered
by the thing that would order a real answer -- co-change confidence, change frequency --
because truncating a baseline arbitrarily is how this directory once turned a real
1.4x into a claimed 5.9x.

Recall is the statistic and ``mean n`` sits beside it. Differences are bootstrapped per
case, paired, because every predictor sees the same cases.

**The cap.** Six shown is the last knob in this section set by argument rather than by a
number -- exp1's finding that a predictor naming twenty files stops being read. That
finding is about whether a section is read, which this cannot measure. What it can
measure is what the cap *costs*: the rank at which the held-out file first appears in the
untruncated ranked list, which gives recall at every k in one run. A cap that leaves
nothing on the table is free whatever exp1 says; one that leaves a lot is a trade
somebody should have to make on purpose.

    python -m experiments.exp9_guards --limit 60
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

from codesextant import cochange, diffscan, engine, references, storage  # noqa: E402
from codesextant import guards as guards_module  # noqa: E402
from experiments import corpus  # noqa: E402
from experiments.exp4_check import paired_difference  # noqa: E402

PREDICTORS = ("guards", "guards+filemention", "guards+importer", "guards_symbols",
              "guards_perfile", "cochange@k", "same_dir@k", "frequency@k")


def _git(root: str, *args: str) -> tuple[int, str]:
    done = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.returncode, done.stdout


def _guard_bearing(repo: str, sha: str, files) -> list[str]:
    """The commit's Python files that actually hold a fence, at that commit.

    Read from the commit's own blobs rather than from a checkout, because this runs
    during sampling -- before any worktree exists -- and the answer decides whether the
    commit is a usable case at all.
    """
    holders = []
    for relative in sorted(files):
        if not relative.endswith(".py"):
            continue
        code, blob = _git(repo, "show", f"{sha}:{relative}")
        if code != 0 or not blob:
            continue
        if guards_module.extract(relative, blob):
            holders.append(relative)
    return holders


def _extract_from(tree: str, relatives) -> list[dict]:
    found = []
    for relative in relatives:
        absolute = os.path.join(tree, relative)
        if os.path.isfile(absolute):
            found.extend(guard.as_row()
                         for guard in guards_module.extract_file(absolute, relative))
    return found


def _key(row: dict) -> tuple[str, int]:
    return (row["path"], row["line"])


def _full_rank(tree: str, applied: list[str], held_out: str,
               symbols: set[str]) -> int | None:
    """Where the held-out file first appears in the *untruncated* ranked list.

    Runs the same four tiers `guards` runs and stops before the cap, which is the only
    part of the pipeline this is asking about. It duplicates the assembly rather than
    calling `guards`, because `guards` returns six rows by construction and six rows
    cannot answer a question about the seventh.
    """
    changed_map = {f: "M" for f in applied}
    notes: list[str] = []
    ranked = engine._rank_guards(engine._guards_in_reach(
        tree, engine._guard_reach(tree, changed_map, symbols, notes), changed_map,
        symbols, engine._guard_history_reach(tree, changed_map),
        engine._guard_importer_reach(tree, changed_map, notes)))
    return next((index for index, row in enumerate(ranked)
                 if row["path"] == held_out), None)


def _score_one(repo: str, home: str, sha: str, files: set[str], holders: list[str],
               changed_total: Counter, directory_files: dict,
               outcomes: dict, sizes: Counter, kinds: Counter,
               ranks: list) -> int:
    code, parent = _git(repo, "rev-parse", f"{sha}^")
    if code != 0:
        return 0
    parent = parent.strip()
    # Hold out a fence-bearing file, preferring a test: "the test I forgot" is the
    # canonical form of this failure and tests are 72-89% of all guards.
    held_out = next((f for f in holders if guards_module.is_test_file(f)), holders[0])
    applied = [f for f in sorted(files) if f != held_out]
    if not applied:
        return 0

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
        answer = engine.guards(tree, token_budget=100_000)
        shown = answer["guards"][:engine._GUARDS_SHOWN]
        budget = max(len(shown), 1)

        predicted: dict[str, list[dict]] = {"guards": shown}

        # 0.28.0's answer: the two tiers whose evidence is the fence's own text. The
        # history tier was added on the strength of the difference between this row and
        # the one above, so it stays here to be re-measured rather than remembered.
        symbols = _changed_symbols(tree, applied)
        changed_map = {f: "M" for f in applied}
        reach = engine._guard_reach(tree, changed_map, symbols, [])
        symbols_only = engine._rank_guards(
            engine._guards_in_reach(tree, reach, changed_map, symbols))
        predicted["guards_symbols"] = symbols_only[:engine._GUARDS_SHOWN]

        # Candidate one: files the change reaches by name that contributed no fence,
        # because no individual guard in them named anything. Ordered by how many of the
        # changed symbols each mentions -- a file naming three of them is a better lead
        # than one naming a single common word.
        contributed = {row["path"] for row in symbols_only}
        mentions = {}
        for relative in sorted(reach):
            if relative in contributed or relative in set(applied):
                continue
            absolute = os.path.join(tree, relative)
            if not os.path.isfile(absolute):
                continue
            with open(absolute, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            hits = sum(1 for name in symbols
                       if references._word_re(name).search(text))
            if hits:
                mentions[relative] = hits
        predicted["guards+filemention"] = _fill(
            shown, sorted(mentions, key=lambda p: (-mentions[p], p)), tree)

        # Candidate two: files importing a module the change touched.
        importers = references.module_dependents(
            tree, [f for f in applied if f.endswith(".py")], skip=set(applied))
        predicted["guards+importer"] = _fill(
            shown, sorted(importers, key=lambda p: (-importers[p], p)), tree)

        # The rejected design, rebuilt here so the rejection is measured rather than
        # asserted: every guard in a file the change reaches, with no per-guard check.
        perfile = _extract_from(tree, sorted(reach))
        predicted["guards_perfile"] = perfile[:budget]

        predicted["cochange@k"] = _extract_from(
            tree, _cochange_companions(tree, applied))[:budget]

        # Ranked by how often each neighbour has changed, not by path order: exp1's
        # directory baseline was truncated alphabetically once and it tripled the
        # apparent advantage of the thing it was measured against.
        neighbours = [p for p in sorted(
            {p for f in applied
             for p in directory_files.get(os.path.dirname(f), set())},
            key=lambda p: (-changed_total[p], p))
            if p.endswith(".py") and p not in set(applied)]
        predicted["same_dir@k"] = _extract_from(tree, neighbours)[:budget]

        frequent = [p for p, _n in changed_total.most_common(60)
                    if p.endswith(".py") and p not in set(applied)]
        predicted["frequency@k"] = _extract_from(tree, frequent)[:budget]

        ranks.append(_full_rank(tree, applied, held_out, symbols))

        for name in PREDICTORS:
            rows = predicted[name]
            hit = int(any(row["path"] == held_out for row in rows))
            outcomes[name].append(hit)
            sizes[name] += len(rows)
            if name == "guards" and hit:
                for row in rows:
                    if row["path"] == held_out:
                        kinds[row["kind"]] += 1
        return 1
    finally:
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", tree],
                       check=False, capture_output=True)


def _fill(shown: list[dict], extra_files, tree: str, per_file: int = 2) -> list[dict]:
    """`guards`' answer, then the empty slots filled from `extra_files` in order.

    A candidate tier is only worth anything where the section is short, so this is the
    shape any of them would ship in: it never displaces a fence read off its own text,
    and it costs nothing when six are already there.
    """
    rows = list(shown)
    seen = {_key(row) for row in rows}
    for relative in extra_files:
        if len(rows) >= engine._GUARDS_SHOWN:
            break
        taken = 0
        for row in _extract_from(tree, [relative]):
            if taken >= per_file or len(rows) >= engine._GUARDS_SHOWN:
                break
            if _key(row) in seen:
                continue
            seen.add(_key(row))
            rows.append(row)
            taken += 1
    return rows


def _cochange_companions(tree: str, applied: list[str]) -> list[str]:
    """Files history says follow the ones changed, strongest first.

    The same call `check` makes, so what is measured is the control that actually
    ships rather than a reimplementation of it.
    """
    stats = engine._ensure_cochange(tree)
    if not stats.get("available"):
        return []
    best: dict[str, float] = {}
    with storage.ProjectStore.open_readonly(tree) as store:
        for relative in sorted(applied):
            for rule in store.cochange_rules_for(
                    relative, min_support=cochange.min_support(),
                    min_confidence=cochange.min_confidence()):
                companion = rule["companion"]
                if companion in set(applied) or not companion.endswith(".py"):
                    continue
                best[companion] = max(best.get(companion, 0.0), rule["confidence"])
    return sorted(best, key=lambda path: (-best[path], path))


def _changed_symbols(tree: str, applied: list[str]) -> set[str]:
    names: set[str] = set()
    with storage.ProjectStore.open_readonly(tree) as store:
        for relative in sorted(applied):
            abs_file = os.path.abspath(os.path.join(tree, relative))
            if not os.path.isfile(abs_file) or not relative.endswith(".py"):
                continue
            ranges = diffscan.changed_ranges(tree, relative)
            names.update(item["name"] for item
                         in engine._changed_definitions(store, abs_file, ranges["added"]))
    return names


def evaluate(repo: str, *, limit: int = 60, seed: int = 0,
             warmup_fraction: float = 0.3) -> dict:
    commits = corpus.history(repo)
    warmup = int(len(commits) * warmup_fraction)
    candidates = [index for index, (_sha, files) in enumerate(commits)
                  if index >= warmup and 2 <= len(files) <= 25
                  and sum(1 for f in files if f.endswith(".py")) >= 2]
    random.Random(seed).shuffle(candidates)

    changed_total: Counter[str] = Counter()
    directory_files: dict[str, set[str]] = {}
    outcomes = {name: [] for name in PREDICTORS}
    sizes: Counter = Counter()
    kinds: Counter = Counter()
    ranks: list[int | None] = []
    scored = 0
    considered = 0
    wanted = set(candidates)

    with tempfile.TemporaryDirectory() as home:
        os.environ["CODESEXTANT_HOME"] = home
        for index, (sha, files) in enumerate(commits):
            if index in wanted and scored < limit:
                considered += 1
                holders = _guard_bearing(repo, sha, files)
                # A commit whose Python files hold no fence cannot answer the question,
                # and counting it as a miss would score the sampler rather than the tool.
                if holders and len(files) - len(holders) >= 1:
                    scored += _score_one(repo, home, sha, files, holders, changed_total,
                                         directory_files, outcomes, sizes, kinds, ranks)
            for path in files:
                changed_total[path] += 1
                directory_files.setdefault(os.path.dirname(path), set()).add(path)

    return {"repo": os.path.basename(repo), "scored": scored, "considered": considered,
            "outcomes": outcomes, "sizes": dict(sizes), "kinds": dict(kinds),
            "ranks": ranks}


def _print(report: dict) -> None:
    total = report["scored"] or 1
    print(f"\n=== {report['repo']}  ({report['scored']} cases scored of "
          f"{report['considered']} commits considered)")
    print(f"{'predictor':20} {'recall':>8} {'mean n':>8}")
    for name in PREDICTORS:
        print(f"{name:20} {sum(report['outcomes'][name]) / total:8.3f} "
              f"{report['sizes'].get(name, 0) / total:8.1f}")
    if report["kinds"]:
        print(f"  kinds of fence found: {report['kinds']}")
    found = [rank for rank in report.get("ranks", []) if rank is not None]
    if found:
        print("  what the six-shown cap costs -- recall at k, untruncated:")
        print("    " + "  ".join(
            f"@{k}:{sum(1 for r in found if r < k) / total:.3f}"
            for k in (1, 3, 6, 10, 20, 50)))
    print("  paired differences (same cases, so the difference is the statistic):")
    for left, right in (("guards+filemention", "guards"), ("guards+importer", "guards"),
                        ("guards", "guards_symbols"), ("guards", "guards_perfile"),
                        ("guards", "cochange@k"), ("guards", "same_dir@k"),
                        ("guards", "frequency@k")):
        delta = paired_difference(report["outcomes"][left], report["outcomes"][right])
        if not delta:
            continue
        verdict = "real" if delta["excludes_zero"] else "not established"
        print(f"    {left:18} - {right:16} {delta['mean']:+.3f}  "
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
