"""Can a one-word query find the wheel already in the file you have open?

**Why this exists.** `codesextant stop` was built as a second `/shutdown` route beside
the `/_shutdown` that already existed, and a second `stop_running` beside the real one,
in a file the author had open. `preflight codesextant/daemon.py --symbol shutdown`
answered *"nothing resembles it; it looks new"*. `engine._name_similarity` requires two
shared words, so a single-word query can only ever match exactly: `shutdown` scores 0.0
against `initiate_shutdown`.

**Why the obvious fix is not on trial here.** exp13 already priced relaxing that rule
globally: containment-over-the-shorter-name reaches 0.983 of duplicates but surfaces
**55.8 names per query**, ten times the shipped matcher's output for +0.068 reach. That
was measured and refused, and a one-word query is exactly where it is worst -- `get`
would match every `get_*` in the tree.

**What is on trial.** The same relaxation with one restriction: it only looks inside the
file being edited. The cost term is what changes. Globally, a loose rule scores against
every name in the repository; in one file it scores against the tens of names in that
file, and those are names the author is already looking at. If the reach it buys is
real and the cost stays small, the rule is worth having; if the duplicates simply are
not in the same file, the idea is dead and the number says so.

    ceiling       of the duplicates found, how many live in the file being edited?
                  Nothing scoped to that file can ever beat this
    shipped       what preflight runs today, globally
    +in-file      shipped, plus one-shared-word *within the target file only*
    +rare(k)      shipped, plus one shared word that names at most k functions in the
                  whole tree. Added after the first run: in-file bought no reach at all
                  and cost eleven times the output, and the reason was visible in the
                  numbers -- a shared word is cheap to find and usually a common verb.
                  `shutdown` names two things in a repository and `get` names ninety, so
                  the frequency of the shared word, not the scope of the search, is what
                  separates the useful match from the noise. k is swept rather than
                  chosen, because a threshold picked to fit is not a result

The cost column is names surfaced per query -- for every added function, duplicate or
not, because a check that fires on every edit is paid for on every edit. exp1 found a
section stops being read somewhere above five entries, so the extra names matter more
than the extra reach.

**Shared with exp13 on purpose.** The shape hash, the corpus, the warm-up fraction and
the dunder and `_MIN_NODES` exclusions are imported from it rather than rewritten, so a
difference between the two reports is a difference in the matcher and nothing else. The
first version of exp13 reported tqdm at 0.312 because `__init__` matched `__init__`;
re-deriving that machinery here would have been a second chance to make that mistake.

Run
---
    python experiments/exp16_infile_reuse.py                 # derivation set
    python experiments/exp16_infile_reuse.py --repo ~/.cache/codesextant-corpus/jinja \
        --repo ~/.cache/codesextant-corpus/httpie --repo ~/.cache/codesextant-corpus/rich
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments import corpus  # noqa: E402
from experiments import exp13_reuse_ceiling as exp13  # noqa: E402

# 999 is 'no rarity gate at all', to price what the gate itself is doing:
# reach came out flat across 2/4/8, so the floor may be carrying the whole
# result and the gate may be complexity nobody is paying for.
RARE_THRESHOLDS = (2, 4, 8, 999)
MATCHERS = (("shipped", "shipped+infile")
            + tuple(f"shipped+rare{k}" for k in RARE_THRESHOLDS)
            + tuple(f"shipped+gated{k}" for k in RARE_THRESHOLDS))


def _matches(matcher: str, query: str, other: str, *,
             same_file: bool, word_freq: dict[str, int]) -> bool:
    """Does `matcher` surface `other` for a query named `query`?

    Every matcher is the shipped one *plus* something, so none of them can score below
    it -- the question is only what the addition costs. `same_file` and `word_freq` are
    passed in rather than derived here, so the caller owns what "the file being edited"
    and "rare in this tree" mean and this function cannot quietly answer a different
    question than the one the report is labelled with.
    """
    if exp13._matches("shipped", exp13._tokens(query), exp13._tokens(other),
                      query, other):
        return True
    shared = exp13._tokens(query) & exp13._tokens(other)
    if not shared:
        return False
    if matcher == "shipped+infile":
        return same_file
    if matcher.startswith("shipped+rare"):
        ceiling = int(matcher.removeprefix("shipped+rare"))
        # The *rarest* shared word decides. Two names sharing one rare word are related;
        # that they also both contain `get` says nothing either way.
        return min(word_freq.get(word, 0) for word in shared) <= ceiling
    if matcher.startswith("shipped+gated"):
        # **The rule as it would actually ship.** `rare` above is the gate alone, and
        # measuring that instead of this would be measuring something nobody runs. Two
        # reasons for the extra floor, and the second is the one that matters:
        #
        #  - `CODESEXTANT_PREFLIGHT_NAME_SIMILARITY` is a knob a user turns to get
        #    fewer candidates. A rule that ignores it silently stops answering to it,
        #    and an existing test caught exactly that.
        #  - A short rare word should not drag in a long unrelated name. `parse`
        #    against `parse_and_validate_user_supplied_duration` shares one word out of
        #    six; the gate alone accepts it and the overlap says it is not the same
        #    idea.
        ceiling = int(matcher.removeprefix("shipped+gated"))
        if min(word_freq.get(word, 0) for word in shared) > ceiling:
            return False
        union = exp13._tokens(query) | exp13._tokens(other)
        return len(shared) / len(union) >= 0.5
    return False


def evaluate(repo_path: str, *, limit: int = 60, seed: int = 0,
             warmup_fraction: float = 0.3) -> dict:
    commits = corpus.history(repo_path)
    warmup = int(len(commits) * warmup_fraction)
    candidates = [(index, sha, files) for index, (sha, files) in enumerate(commits)
                  if index >= warmup and any(f.endswith(".py") for f in files)
                  and len(files) <= 25]
    random.Random(seed).shuffle(candidates)

    cache: dict[str, dict] = {}
    reached: Counter = Counter()
    cost: Counter = Counter()
    duplicates = 0
    in_file_duplicates = 0
    one_word_queries = 0
    one_word_duplicates = 0
    one_word_reached: Counter = Counter()
    queries = 0
    scored = 0
    examples: list[dict] = []

    for _index, sha, files in candidates:
        if scored >= limit:
            break
        code, parent = exp13._git(repo_path, "rev-parse", f"{sha}^")
        if code != 0:
            continue
        parent = parent.strip()
        python = sorted(f for f in files if f.endswith(".py"))
        before = exp13._read_blobs(repo_path, parent, python)
        after = exp13._read_blobs(repo_path, sha, python)

        # The file each function was added to is the whole point of this experiment, so
        # unlike exp13 it is carried through rather than dropped.
        added: list[tuple[str, str, str]] = []
        for relative in python:
            was = exp13._functions(before.get(relative, ""))
            now = exp13._functions(after.get(relative, ""))
            for name, (shape, _size) in now.items():
                if name not in was:
                    added.append((name, shape, relative))
        if not added:
            continue
        scored += 1

        known, all_names = exp13._tree_shapes(repo_path, parent, cache)
        word_freq = _word_frequency(all_names, cache, parent)
        # Where every existing name lives, so "is it in the file being edited" is a
        # lookup rather than a second walk of the tree.
        homes = _names_by_file(repo_path, parent, cache)

        for name, shape, relative in added:
            queries += 1
            single_word = len(exp13._tokens(name)) == 1
            if single_word:
                one_word_queries += 1
            local = homes.get(relative, set())
            for matcher in MATCHERS:
                cost[matcher] += sum(
                    1 for other in all_names
                    if other != name
                    and _matches(matcher, name, other, same_file=other in local,
                                 word_freq=word_freq))

            existing = known.get(shape)
            if not existing:
                continue
            duplicates += 1
            here = [other for other in existing if other in local and other != name]
            if here:
                in_file_duplicates += 1
            if single_word:
                one_word_duplicates += 1
            for matcher in MATCHERS:
                hit = any(_matches(matcher, name, other, same_file=other in local,
                                   word_freq=word_freq)
                          for other in existing if other != name)
                if hit:
                    reached[matcher] += 1
                    if single_word:
                        one_word_reached[matcher] += 1
            # The cases this change is for: an in-file duplicate today's matcher misses.
            missed = not any(_matches("shipped", name, other, same_file=False,
                                      word_freq=word_freq)
                             for other in existing if other != name)
            if here and missed and len(examples) < 8:
                examples.append({"repo": os.path.basename(repo_path),
                                 "added": name, "file": relative,
                                 "already_there": sorted(here)[:3]})

    return {"repo": os.path.basename(repo_path), "commits_scored": scored,
            "queries": queries, "duplicates": duplicates,
            "in_file_duplicates": in_file_duplicates,
            "one_word_queries": one_word_queries,
            "one_word_duplicates": one_word_duplicates,
            "one_word_reached": dict(one_word_reached),
            "reached": dict(reached), "cost": dict(cost), "examples": examples}


def _word_frequency(all_names, cache: dict, sha: str) -> dict[str, int]:
    """How many distinct function names in this tree contain each word.

    Distinct *names*, not definitions: a helper defined in forty files is one name and
    one idea, and counting it forty times would make every widely-reused word look rare
    in a small repository and common in a large one.
    """
    key = f"words:{sha}"
    if key not in cache:
        freq: Counter = Counter()
        for name in all_names:
            for word in exp13._tokens(name):
                freq[word] += 1
        cache[key] = dict(freq)
    return cache[key]


def _names_by_file(repo_path: str, sha: str, cache: dict) -> dict[str, set[str]]:
    """Function names per file in one tree, memoised beside exp13's shape cache."""
    key = f"homes:{sha}"
    if key in cache:
        return cache[key]
    homes: dict[str, set[str]] = {}
    paths = exp13._python_files(repo_path, sha)
    blobs = exp13._read_blobs(repo_path, sha, paths)
    for relative, source in blobs.items():
        names = set(exp13._functions(source))
        if names:
            homes[relative] = names
    cache[key] = homes
    return homes


def _print(report: dict) -> None:
    queries = max(1, report["queries"])
    duplicates = max(1, report["duplicates"])
    print(f"\n{report['repo']}: {report['commits_scored']} commits, "
          f"{report['queries']} added functions")
    print(f"  duplicates found            {report['duplicates']}")
    print(f"  ceiling: duplicate is in the same file  "
          f"{report['in_file_duplicates'] / duplicates:.3f} "
          f"({report['in_file_duplicates']}/{report['duplicates']})")
    print(f"  one-word queries            {report['one_word_queries']}"
          f" of {report['queries']}"
          f"   (of which {report['one_word_duplicates']} were duplicates)")
    for matcher in MATCHERS:
        reach = report["reached"].get(matcher, 0) / duplicates
        names = report["cost"].get(matcher, 0) / queries
        single = report["one_word_reached"].get(matcher, 0)
        print(f"  {matcher:16s} reach {reach:.3f}   names/query {names:5.2f}"
              f"   one-word hits {single}")
    for example in report["examples"][:4]:
        print(f"    missed today: {example['added']}  in {example['file']}"
              f"  beside {example['already_there']}")


def _pooled(reports: list[dict]) -> None:
    queries = sum(r["queries"] for r in reports) or 1
    duplicates = sum(r["duplicates"] for r in reports) or 1
    in_file = sum(r["in_file_duplicates"] for r in reports)
    print(f"\npooled over {len(reports)} repositories: "
          f"{duplicates} duplicates, {queries} queries")
    print(f"  ceiling (duplicate in the edited file)  {in_file / duplicates:.3f}")
    for matcher in MATCHERS:
        reach = sum(r["reached"].get(matcher, 0) for r in reports) / duplicates
        names = sum(r["cost"].get(matcher, 0) for r in reports) / queries
        print(f"  {matcher:16s} reach {reach:.3f}   names/query {names:5.2f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--dump", default=None)
    args = parser.parse_args()
    repos = args.repo or [corpus.ensure(name, url) for name, url in corpus.EXTERNAL]
    reports = [evaluate(repo, limit=args.limit) for repo in repos]
    for report in reports:
        _print(report)
    _pooled(reports)
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as handle:
            json.dump(reports, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
