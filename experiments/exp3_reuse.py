"""Would the reuse check have found the wheel that was actually reinvented?

The claim under test is the first of preflight's three: that before you write a
function, it tells you one like it already exists. The check is name-based, which is
a real limitation with an unknown size -- these numbers are what size it is.

Ground truth is not invented. ``find_duplicates`` locates structural duplicates in a
repository: units with the same shape, which is code someone genuinely wrote twice.
For each such pair, one member is treated as "the thing about to be written": the
reuse check is asked, with only that name and its file, whether anything resembling
it exists -- and scored on whether it returns the other member.

Control is what an agent does without the tool: grep for the exact name. That is the
honest baseline, because it is free and everyone already has it. Results are therefore
reported in two strata, because the two say different things:

* same-named pairs -- grep already finds these, so the only question is whether the
  reuse check does no *worse* than free;
* differently-named pairs -- grep finds none of these by construction, so this is the
  entire value the reuse check can add.

Known bias, stated up front rather than discovered in the discussion: structural
duplicates in a mature codebase are mostly *deliberate*. requests' md5_utf8 /
sha256_utf8 / sha512_utf8 and click's get_binary_stdin / stdout / stderr are families
someone meant to write; tqdm's discord, telegram and slack classes implement one
interface. None of them is a wheel anybody reinvented by forgetting. So this measures
retrieval -- given a name, is the structurally equivalent definition surfaced -- and
not prevention. Prevention has no ground truth in this corpus, and inventing one
would be worse than saying so.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine, storage  # noqa: E402
from experiments import corpus  # noqa: E402


def _pairs_from_duplicates(report: dict) -> list[tuple[dict, dict]]:
    """Every ordered pair inside every duplicate group, as (existing, about_to_write)."""
    pairs = []
    for group in report.get("groups") or []:
        members = group.get("members") or []
        for i, first in enumerate(members):
            for second in members[i + 1:]:
                if first.get("name") and second.get("name"):
                    pairs.append((first, second))
                    pairs.append((second, first))
    return pairs


def _score(store, pairs: list[tuple[dict, dict]]) -> dict:
    strata = {"same_name": {"n": 0, "found": 0},
              "different_name": {"n": 0, "found": 0}}
    listable = {"n": 0, "found": 0}
    withheld = 0
    for existing, writing in pairs:
        candidates, shared = engine._reuse_candidates(
            store, writing["name"], os.path.abspath(writing["path"]),
            limit=engine._common_name_max())
        if shared > engine._common_name_max():
            withheld += 1
        hit = any(os.path.normcase(os.path.abspath(c["path"]))
                  == os.path.normcase(os.path.abspath(existing["path"]))
                  and c["line"] == existing["line"] for c in candidates)
        is_same_name = existing["name"] == writing["name"]
        bucket = strata["same_name" if is_same_name else "different_name"]
        bucket["n"] += 1
        bucket["found"] += bool(hit)
        if is_same_name and shared <= engine._common_name_max():
            listable["n"] += 1
            listable["found"] += bool(hit)
    return {"strata": strata, "listable": listable, "withheld": withheld}


def evaluate(repo_path: str) -> dict:
    with tempfile.TemporaryDirectory() as home:
        os.environ["CODESEXTANT_HOME"] = home
        engine.index_project(repo_path, force=True)
        duplicates = engine.find_duplicates(repo_path)
        pairs = _pairs_from_duplicates(duplicates)

        with storage.ProjectStore.open_readonly(repo_path) as store:
            treatment = _score(store, pairs)
            # Ablation: the same run with the same-shape family rule switched off,
            # which is the state of the code before the rule existed. Reporting it
            # beside the treatment is the only way to say what the rule bought.
            original = engine._same_shape_family
            engine._same_shape_family = lambda _left, _right: False
            try:
                ablated = _score(store, pairs)
            finally:
                engine._same_shape_family = original
    return {
        "repo": os.path.basename(repo_path),
        "groups": len(duplicates.get("groups") or []),
        "pairs": len(pairs),
        "with_family_rule": treatment,
        "without_family_rule": ablated,
    }


def _rate(bucket: dict) -> float:
    return bucket["found"] / bucket["n"] if bucket["n"] else float("nan")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    repos = args.repo or [corpus.ensure(name, url) for name, url in corpus.EXTERNAL]
    if args.label:
        print(f"### {args.label}")
    print(f"{'repo':12} {'groups':>6} {'diff-name n':>12} "
          f"{'off':>7} {'on':>7} {'delta':>7}   "
          f"{'same-name n':>12} {'listable':>9} {'withheld':>9}")
    for repo in repos:
        row = evaluate(repo)
        on, off = row["with_family_rule"], row["without_family_rule"]
        diff_on, diff_off = _rate(on["strata"]["different_name"]), _rate(
            off["strata"]["different_name"])
        delta = diff_on - diff_off
        print(f"{row['repo']:12} {row['groups']:6} "
              f"{on['strata']['different_name']['n']:12} "
              f"{diff_off:7.3f} {diff_on:7.3f} {delta:+7.3f}   "
              f"{on['strata']['same_name']['n']:12} "
              f"{_rate(on['listable']):9.3f} {on['withheld']:9}")
    print("\noff / on = recall on differently-named structural duplicates with the "
          "same-shape family rule disabled and enabled. An exact-name grep scores "
          "0.000 on this column by construction.")
    print("listable = same-name recall over pairs whose name was rare enough to list. "
          "Below 1.000 is a defect; the rest of the same-name gap is deliberate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
