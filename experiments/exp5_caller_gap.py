"""Why does the caller section reach so much less than the name sweep?

exp4 left this open and quantified. Of the files held out of a real commit, 0.305 to
0.759 *name* a symbol that commit changed, and the resolved caller section finds 0.068
to 0.086 of them. The information is in the repository and resolution is not reaching
it. exp4 also refuted two mechanical explanations -- requests' ``src/`` layout does not
degrade jedi, and the cost gate declines only 7.8% of symbols -- and rejected one
candidate built on ranking by how many changed symbols a file names.

What is missing is the mechanism. A ratio of one to four says resolution loses three
files in four; it does not say *where*, and every possible repair depends on where.
Ranking candidates differently cannot help if jedi is being pointed at the wrong
definition; pointing it better cannot help if the name only ever appears inside a
docstring.

So this classifies the misses instead of scoring another predictor. For every case
where the held-out file names a symbol the change touched and ``check`` did not name
that file, exactly one reason is recorded:

    beyond_budget      the symbol was past CODESEXTANT_CHECK_MAX_SYMBOLS
    declined           the cost gate refused to resolve it
    unsupported/failed resolution could not run
    locator_mismatch   the regex locator pinned a different same-named definition than
                       the one the diff actually touched, so every real reference to the
                       touched one was scored as pointing somewhere else
    text_only          the name occurs only inside strings or comments
    goto_empty         jedi resolved nothing at any occurrence
    resolves_elsewhere jedi resolved to a genuinely different definition
    other_line         jedi resolved into the defining file at a different line
    should_have_found  jedi does point at the definition, so the loss is downstream

The categories are ordered, and the first that applies wins, because a symbol past the
budget is never resolved at all and asking what jedi would have said about it is a
question about a call that never happened.

    python -m experiments.exp5_caller_gap --limit 40

Nothing is built on this. It is the measurement that says which of the repairs is worth
building, which is the discipline that has already saved one build in this directory.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import tokenize
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jedi  # noqa: E402

from codesextant import diffscan, engine, references, storage  # noqa: E402
from experiments import corpus  # noqa: E402

REASONS = ("beyond_budget", "declined", "unsupported", "failed", "locator_mismatch",
           "text_only", "goto_empty", "resolves_elsewhere", "other_line",
           "should_have_found")


def _git(root: str, *args: str) -> tuple[int, str]:
    done = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.returncode, done.stdout


def _name_token_positions(path: str, symbol: str) -> set[tuple[int, int]]:
    """Positions where ``symbol`` appears as a real identifier, not as text.

    The name sweep is a word-boundary regex over bytes, so it counts a mention in a
    docstring, a changelog line inside a triple-quoted string, or a commented-out call.
    None of those is a caller and no resolver can make one out of them. Separating them
    is the difference between "resolution is failing" and "there was nothing to
    resolve".
    """
    positions: set[tuple[int, int]] = set()
    try:
        with open(path, "rb") as handle:
            data = handle.read()
        for token in tokenize.tokenize(io.BytesIO(data).readline):
            if token.type == tokenize.NAME and token.string == symbol:
                positions.add((token.start[0], token.start[1]))
    except (OSError, SyntaxError, tokenize.TokenError, IndentationError, ValueError):
        # An unparseable file cannot be split into code and text, so decline to claim
        # either. The caller treats an empty set as "unknown" rather than "text only".
        return set()
    return positions


def _classify(tree: str, held_abs: str, symbol: str, def_abs: str, def_line: int,
              status: str, beyond_budget: bool) -> str:
    if beyond_budget:
        return "beyond_budget"
    if status in ("declined", "unsupported", "failed"):
        return status
    located = references._locate_definition_position(tree, symbol, def_abs)
    if located is not None and located[1] != def_line:
        return "locator_mismatch"

    occurrences = references._occurrences_in_file(held_abs, symbol)
    code_positions = _name_token_positions(held_abs, symbol)
    if code_positions and not (set(occurrences) & code_positions):
        return "text_only"
    real = [pos for pos in occurrences if not code_positions or pos in code_positions]
    if not real:
        return "text_only"

    try:
        with open(held_abs, encoding="utf-8", errors="replace") as handle:
            source = handle.read()
        script = jedi.Script(source, path=held_abs,
                             project=jedi.Project(path=os.path.abspath(tree)))
    except Exception:
        return "failed"

    def_norm = os.path.normcase(os.path.abspath(def_abs))
    saw_definition_file = False
    saw_anything = False
    for line, column in real[:40]:
        try:
            definitions = script.goto(line, column, follow_imports=True)
        except Exception:
            continue
        for found in definitions:
            if not found.module_path:
                continue
            saw_anything = True
            if os.path.normcase(os.path.abspath(str(found.module_path))) != def_norm:
                continue
            saw_definition_file = True
            if found.line == def_line:
                return "should_have_found"
    if saw_definition_file:
        return "other_line"
    if saw_anything:
        return "resolves_elsewhere"
    return "goto_empty"


def _score_one(repo: str, home: str, sha: str, files: set[str],
               reasons: Counter, totals: Counter, records: list) -> int:
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

        totals["cases"] += 1
        held_abs = os.path.abspath(os.path.join(tree, held_out))
        if not held_out.endswith(".py") or not os.path.isfile(held_abs):
            # A file the commit created has no parent version, so it cannot have been
            # calling anything at the moment the change was made.
            totals["held_out_absent"] += 1
            return 1

        # The same list check works from, in the same order, so "beyond the budget"
        # means what it means inside check rather than approximately that.
        definitions: list[tuple[str, dict]] = []
        with storage.ProjectStore.open_readonly(tree) as store:
            for rel in sorted(applied):
                abs_file = os.path.abspath(os.path.join(tree, rel))
                if not os.path.isfile(abs_file):
                    continue
                ranges = diffscan.changed_ranges(tree, rel)
                for definition in engine._changed_definitions(
                        store, abs_file, ranges["added"]):
                    definitions.append((rel, definition))
        budget = engine._check_max_symbols()
        totals["changed_definitions"] += len(definitions)
        if not definitions:
            totals["no_changed_definitions"] += 1

        with open(held_abs, encoding="utf-8", errors="replace") as handle:
            held_text = handle.read()
        # Two ceilings, on the same cases, because they are not the same claim. exp4
        # counted a held-out file as reachable if it named *any* definition living in a
        # file the commit touched; the caller section only ever resolves the definitions
        # the diff actually wrote into. The looser one is the number the handoff quotes
        # as the gap to close, so the two are measured side by side rather than argued
        # about.
        with storage.ProjectStore.open_readonly(tree) as store:
            resident = set()
            for rel in sorted(applied):
                abs_file = os.path.abspath(os.path.join(tree, rel))
                for row in store.conn.execute(
                        "SELECT DISTINCT name FROM symbols WHERE path=? AND kind IN "
                        "('function','method','class') LIMIT 40", (abs_file,)).fetchall():
                    resident.add(row["name"])
        if any(references._word_re(name).search(held_text) for name in resident):
            totals["names_resident_symbol"] += 1

        named = [(index, rel, definition) for index, (rel, definition)
                 in enumerate(definitions)
                 if references._word_re(definition["name"]).search(held_text)]
        if not named:
            totals["names_nothing"] += 1
            return 1
        totals["names_something"] += 1

        found = {path for entry in result.get("callers") or []
                 for path in entry.get("callers") or []}
        if held_out in found:
            totals["found_by_check"] += 1
            return 1
        totals["missed_by_check"] += 1

        # One reason per case, from the symbol with the best excuse: if any symbol the
        # file names should have resolved, the case is not explained by the ones that
        # were never tried.
        verdicts = []
        for index, rel, definition in named[:6]:
            def_abs = os.path.abspath(os.path.join(tree, rel))
            beyond = index >= budget
            status = ""
            if not beyond:
                outcome = engine._ensure_blast_radius(
                    tree, def_abs, definition["name"], resolve="auto", defined_here=True)
                status = outcome["status"]
            verdicts.append(_classify(tree, held_abs, definition["name"], def_abs,
                                      definition["line"], status, beyond))
        verdict = min(verdicts, key=REASONS.index)
        reasons[verdict] += 1
        records.append({"repo": os.path.basename(repo), "sha": sha,
                        "held_out": held_out, "reason": verdict,
                        "symbols": [d["name"] for _i, _r, d in named[:6]]})
        return 1
    finally:
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", tree],
                       check=False, capture_output=True)


def evaluate(repo: str, *, limit: int = 40, seed: int = 0,
             warmup_fraction: float = 0.3) -> dict:
    commits = corpus.history(repo)
    warmup = int(len(commits) * warmup_fraction)
    eligible = [index for index, (_sha, files) in enumerate(commits)
                if index >= warmup and 2 <= len(files) <= 25
                and any(f.endswith(".py") for f in files)]
    random.Random(seed).shuffle(eligible)
    sampled = set(eligible[:limit])

    reasons: Counter = Counter()
    totals: Counter = Counter()
    records: list = []
    with tempfile.TemporaryDirectory() as home:
        os.environ["CODESEXTANT_HOME"] = home
        for index, (sha, files) in enumerate(commits):
            if index in sampled:
                _score_one(repo, home, sha, files, reasons, totals, records)
    return {"repo": os.path.basename(repo), "reasons": dict(reasons),
            "totals": dict(totals), "records": records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--dump", default=None)
    args = parser.parse_args()
    repos = args.repo or [corpus.ensure(name, url) for name, url in corpus.EXTERNAL]
    reports = []
    for repo in repos:
        report = evaluate(repo, limit=args.limit)
        reports.append(report)
        totals = report["totals"]
        print(f"\n=== {report['repo']}  ({totals.get('cases', 0)} cases)")
        for key in ("held_out_absent", "names_nothing", "names_something",
                    "found_by_check", "missed_by_check", "changed_definitions",
                    "no_changed_definitions", "names_resident_symbol"):
            print(f"  {key:20} {totals.get(key, 0):5}")
        missed = totals.get("missed_by_check", 0) or 1
        print(f"  {'reason':20} {'n':>5} {'share of misses':>16}")
        for reason in REASONS:
            count = report["reasons"].get(reason, 0)
            if count:
                print(f"  {reason:20} {count:5} {count / missed:16.3f}")
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as handle:
            json.dump(reports, handle, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
