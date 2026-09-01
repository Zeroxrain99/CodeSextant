"""The task set for the only experiment that answers "does this actually help?"

Every number in this directory measures **retrieval**: given a query, is the right thing
returned. Not one of them says an author who *saw* the answer made a better change, or
spent less fixing it. That is the demand this project was started for, stated exactly,
and it is untouched.

This file is the prerequisite: a task set, and a scorer, both fixed and published before
any run. It does not run the A/B -- that needs agents -- but it makes the A/B
reproducible by somebody else, which `docs/roadmap.md` G1 requires anyway.

Where the tasks come from
-------------------------
Real commits from `corpus.PREVENTION` -- flask, pytest, alembic -- chosen and written
down before a single commit in any of them was read. Every rule in this repository was
derived on the derivation set and confirmed on the held-out set, so both have been
looked at; a prevention experiment run on either would be scoring a tool against
repositories that shaped it.

The agent is given the parent tree, the commit's own message, and **one starting file**
-- the Python file the commit changed most. It is not given the rest of the file list.
Finding the rest is the task.

The starting file matters and the first version did not have it. Without it "the files
this commit touched" is the whole ground truth, and a mode like "did you remember the
fence" is satisfied by editing the file you were already in. Naming the file where the
change begins is what makes the other files *the blast radius* rather than *the change*,
which is the failure being measured: you changed A, what did you break.

What is scored, one rate per failure mode rather than one blended number
-----------------------------------------------------------------------
    changed_a_broke_b   of the files the commit touched *other than the one the attempt
                        started in*, how many did the attempt touch?
    forgot_the_guard    of those, the ones holding a fence -- a test, an assertion, an
                        allowlist, a limit. The same question narrowed to where getting
                        it wrong stops a build
    rebuilt_the_wheel   the commit **imported** a helper the repository already defined
                        and this file was not already importing. Did the attempt import
                        it too, or write its own?
    tokens              what it cost. Not a rate; recorded beside the rates because
                        "wasted tokens fixing it" is the fourth failure and a tool that
                        wins on the first three by tripling the bill has not won.

`rebuilt_the_wheel` is deliberately **not** scored with this tool's own duplicate
detector. Marking your own homework is how a benchmark stops meaning anything: the truth
here is what the human author actually did -- they imported an existing helper -- and the
question is only whether the attempt did the same.

It counts *imports* rather than mentions, and the first version did not. Counting
mentions made the mode vacuous: matching identifiers against every name the repository
defines turned `name`, `set`, `open`, `run` and `error` into "helpers", so any attempt
that wrote plausible Python scored well without reusing anything. The `parent` baseline
below exists because the `null` baseline could not see that -- a predictor that touches
no files scores zero on everything, including on a mode that is broken.

Validating the scorer
---------------------
A scorer nobody has tried to break is a scorer that reports whatever you hoped. Two
baselines run against every task set, and `--validate` fails if either misbehaves:

    oracle   apply the real commit. Must score 1.0 on every mode; anything less means
             the ground truth cannot be satisfied even by the answer it was taken from.
    null     change nothing. Must score 0.0; anything more means the mode is free.
    parent   touch exactly the right files and change nothing in them. Must score 1.0 on
             the two modes that ask *which files*, and **0.0 on rebuilt_the_wheel** --
             which is the only baseline that can tell reuse from coincidence, because it
             is the one that gets the files right for the wrong reason.

    python -m experiments.exp12_prevention --build --limit 40 --out tasks.json
    python -m experiments.exp12_prevention --validate tasks.json
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import guards as guards_module  # noqa: E402
from experiments import corpus  # noqa: E402

MODES = ("changed_a_broke_b", "forgot_the_guard", "rebuilt_the_wheel")

# A subject that says nothing cannot be a task: an agent given "fix tests" has not been
# told what to do, and scoring it measures guessing.
_UNUSABLE = re.compile(
    r"^(merge|bump|release|version|prepare|update changelog|fix typo|typo|wip|"
    r"revert|\[pre-commit)", re.IGNORECASE)


def _git(root: str, *args: str) -> tuple[int, str]:
    done = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.returncode, done.stdout


def _defined_names(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    return {node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _read_blobs(root: str, sha: str, paths) -> dict[str, str]:
    """Every listed file at one commit, in one subprocess.

    The first version ran ``git show`` per file: four hundred processes per task, three
    repositories deep, and the build did not finish. ``cat-file --batch`` reads them all
    down one pipe -- the same data, about two orders of magnitude less of the time spent
    on process startup.
    """
    wanted = list(paths)
    if not wanted:
        return {}
    request = "".join(f"{sha}:{relative}\n" for relative in wanted)
    done = subprocess.run(["git", "-C", root, "cat-file", "--batch"],
                          input=request.encode(), stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL)
    out = done.stdout
    found: dict[str, str] = {}
    cursor = 0
    for relative in wanted:
        newline = out.find(b"\n", cursor)
        if newline < 0:
            break
        header = out[cursor:newline].decode("utf-8", "replace").split()
        cursor = newline + 1
        if len(header) < 3:      # "<oid> missing" for a path not in this tree
            continue
        size = int(header[2])
        found[relative] = out[cursor:cursor + size].decode("utf-8", "replace")
        cursor += size + 1       # the newline cat-file adds after each blob
    return found


_VOCABULARY: dict[tuple[str, str], set[str]] = {}


def _repo_symbols(root: str, sha: str, paths) -> set[str]:
    """Every function and class the repository defines at ``sha``.

    Memoised per commit: consecutive tasks in one repository often share a parent, and
    the answer is a pure function of the tree.
    """
    key = (root, sha)
    if key not in _VOCABULARY:
        names: set[str] = set()
        for source in _read_blobs(root, sha, paths).values():
            names.update(_defined_names(source))
        _VOCABULARY[key] = names
    return _VOCABULARY[key]


def _python_files(root: str, sha: str) -> list[str]:
    code, out = _git(root, "ls-tree", "-r", "--name-only", sha)
    if code != 0:
        return []
    return [line for line in out.splitlines() if line.endswith(".py")]


def _imported_names(source: str) -> set[str]:
    """What a file imports, by the name it binds locally.

    Imports rather than mentions, because an import is unambiguous evidence that the
    author went looking for something that already existed, while a mention is mostly
    evidence that English has short words.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update((alias.asname or alias.name).split(".")[0]
                         for alias in node.names)
    return names


def _reuse_events(root: str, sha: str, parent: str, changed: list[str],
                  vocabulary: set[str]) -> dict[str, list[str]]:
    """Helpers a file started importing in this commit that already existed before it.

    "Already existed" is the whole point: a name defined by this same commit is the
    author building the thing, not reusing one. Those are excluded by taking the
    vocabulary from the *parent* tree.
    """
    python = [relative for relative in changed if relative.endswith(".py")]
    before_all = _read_blobs(root, parent, python)
    after_all = _read_blobs(root, sha, python)
    events: dict[str, list[str]] = {}
    for relative in python:
        after = after_all.get(relative)
        if not after:
            continue
        before = before_all.get(relative)
        was = _imported_names(before) if before else set()
        now = _imported_names(after)
        # Names this file defines itself are not reuse however new they look, and the
        # helper has to be one the repository already had.
        gained = sorted(((now - was) & vocabulary) - _defined_names(after))
        if gained:
            events[relative] = gained
    return events


def _seed_file(root: str, sha: str, files) -> str | None:
    """The Python file this commit changed most, which the attempt is told to start in.

    Most-changed rather than first-alphabetically: the alphabetical file is as likely to
    be a changelog as the thing the work is about, and picking it would make the task
    "find the code from the changelog entry" instead of "you are changing this, what
    else moves".
    """
    _code, out = _git(root, "show", "--numstat", "--format=", sha)
    sizes: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[2].endswith(".py"):
            continue
        added, deleted = parts[0], parts[1]
        if added == "-" or deleted == "-":     # a binary file has no line counts
            continue
        if parts[2] in files:
            sizes[parts[2]] = int(added) + int(deleted)
    if not sizes:
        return None
    return max(sorted(sizes), key=lambda path: sizes[path])


def _guard_bearing(root: str, sha: str, files) -> list[str]:
    python = [relative for relative in sorted(files) if relative.endswith(".py")]
    blobs = _read_blobs(root, sha, python)
    return [relative for relative in python
            if blobs.get(relative) and guards_module.extract(relative, blobs[relative])]


_TRAILER = re.compile(r"^[A-Za-z-]+: ")


def _messages_and_parents(root: str) -> dict[str, tuple[str, str]]:
    """{sha: (first parent, message)} for the whole history, in one subprocess.

    Read in one pass because the alternative was two `git` processes per *candidate*,
    and the candidate list is thousands long before the subject filter thins it: 42
    seconds to produce three tasks from alembic, nearly all of it process startup for
    commits that were then discarded.

    The body is kept -- it is where an author says *why*, which is the context a real
    request would carry. Trailers are dropped: they name the answer's author, not the
    task, and one of them would hand the attempt the commit it is being scored against.
    """
    _code, out = _git(root, "log", "--format=%x00%H%x01%P%x01%s%n%b")
    found: dict[str, tuple[str, str]] = {}
    for record in out.split("\x00"):
        if not record.strip():
            continue
        head, _, body = record.partition("\n")
        parts = head.split("\x01")
        if len(parts) < 3:
            continue
        sha, parents, subject = parts[0], parts[1].split(), parts[2]
        if not parents:
            continue
        lines = [line for line in f"{subject}\n{body}".strip().splitlines()
                 if not _TRAILER.match(line)]
        found[sha] = (parents[0], "\n".join(lines).strip())
    return found


def build(repo_path: str, *, limit: int = 40, seed: int = 0,
          warmup_fraction: float = 0.5) -> list[dict]:
    name = os.path.basename(os.path.abspath(repo_path))
    commits = corpus.history(repo_path)
    # The second half only: a task whose repository barely exists yet is a task about
    # bootstrapping, not about changing something that already has structure.
    candidates = [(index, sha, files)
                  for index, (sha, files) in enumerate(commits)
                  if index >= len(commits) * warmup_fraction
                  and 2 <= len(files) <= 15
                  and sum(1 for f in files if f.endswith(".py")) >= 2]
    random.Random(seed).shuffle(candidates)
    described = _messages_and_parents(repo_path)

    tasks: list[dict] = []
    for _index, sha, files in candidates:
        if len(tasks) >= limit:
            break
        described_here = described.get(sha)
        if not described_here:
            continue                      # a root commit has no tree to start from
        parent, instruction = described_here
        subject = instruction.splitlines()[0] if instruction else ""
        if len(subject) < 20 or _UNUSABLE.match(subject):
            continue

        ordered = sorted(files)
        seed = _seed_file(repo_path, sha, set(files))
        if seed is None:
            continue
        companions = [path for path in ordered if path != seed]
        if not companions:
            continue

        vocabulary = _repo_symbols(repo_path, parent,
                                   _python_files(repo_path, parent))
        reuse = _reuse_events(repo_path, sha, parent, ordered, vocabulary)
        # Only fences outside the file the attempt is already editing. A fence in the
        # starting file is not one anybody forgot.
        guard_files = [path for path in _guard_bearing(repo_path, sha, files)
                       if path != seed]

        tasks.append({
            "id": f"{name}@{sha[:10]}",
            "repo": name, "sha": sha, "parent": parent,
            "instruction": instruction,
            "start_in": seed,
            "truth": {
                "files": ordered,
                "companions": companions,
                "guard_files": guard_files,
                "reuse": reuse,
            },
        })
    return tasks


def score(task: dict, changed: set[str], sources: dict[str, str] | None = None) -> dict:
    """One rate per failure mode for one attempt.

    ``changed`` is the set of repository-relative paths the attempt touched.
    ``sources`` maps those paths to their contents afterwards, which the reuse mode
    needs -- touching the file is not the same as reaching for the helper. A mode with
    nothing to measure in this task returns None rather than 1.0, so an easy task cannot
    inflate a rate by being satisfied vacuously.
    """
    truth = task["truth"]
    sources = sources or {}

    companions = set(truth["companions"])
    broke_b = (len(changed & companions) / len(companions)) if companions else None

    fences = set(truth["guard_files"])
    forgot = (len(changed & fences) / len(fences)) if fences else None

    wanted = {(path, name) for path, names in truth["reuse"].items() for name in names}
    if wanted:
        imported = {path: _imported_names(text) for path, text in sources.items()}
        reached = sum(1 for path, name in wanted if name in imported.get(path, ()))
        rebuilt = reached / len(wanted)
    else:
        rebuilt = None

    return {"changed_a_broke_b": broke_b, "forgot_the_guard": forgot,
            "rebuilt_the_wheel": rebuilt}


def _apply_oracle(repo_path: str, task: dict) -> tuple[set[str], dict[str, str]]:
    """What the real commit did: the upper bound the ground truth was taken from."""
    changed = set(task["truth"]["files"])
    return changed, _read_blobs(repo_path, task["sha"], sorted(changed))


def _apply_shotgun(repo_path: str, task: dict) -> tuple[set[str], dict[str, str]]:
    """Touch every file in the tree: the attempt that finds everything by finding nothing.

    Added after the E2 pilot, where one arm changed a file the other did not and both
    scored identically. `changed_a_broke_b` and `forgot_the_guard` are recall over the
    truth, with no precision term, so an attempt that sprays edits across the repository
    is credited with every companion it hit by accident. `null` cannot see that -- it
    changes nothing and scores zero on a mode that is wide open.

    A benchmark whose top score is reachable without doing the task measures nothing,
    and this repository has already shipped one mode like that (`rebuilt_the_wheel`,
    which any plausible Python satisfied until the `parent` baseline caught it).
    """
    changed = set(_python_files(repo_path, task["parent"]))
    changed.update(task["truth"]["files"])
    return changed, _read_blobs(repo_path, task["parent"], sorted(changed))


BASELINES = ("oracle", "parent", "null", "shotgun")


def validate(tasks: list[dict], roots: dict[str, str]) -> dict:
    """Three baselines the scorer must separate, or it is not measuring anything."""
    totals = {name: {mode: [] for mode in MODES} for name in BASELINES}
    broken: list[str] = []
    for task in tasks:
        root = roots[task["repo"]]
        changed, sources = _apply_oracle(root, task)
        # The right files with their old contents: everything a file-level mode asks
        # for and nothing a content-level mode should accept.
        stale = _read_blobs(root, task["parent"], sorted(changed))
        wide, wide_sources = _apply_shotgun(root, task)
        scored = {"oracle": score(task, changed, sources),
                  "parent": score(task, changed, stale),
                  "null": score(task, set(), {}),
                  "shotgun": score(task, wide, wide_sources)}
        for mode in MODES:
            if scored["oracle"][mode] is None:
                continue
            for name in BASELINES:
                totals[name][mode].append(scored[name][mode] or 0.0)
            if scored["oracle"][mode] < 1.0:
                broken.append(f"{task['id']}: {mode} scores "
                              f"{scored['oracle'][mode]:.2f} for the commit the truth "
                              "was taken from")
    average = {name: {mode: (sum(v) / len(v) if v else None)
                      for mode, v in totals[name].items()} for name in BASELINES}
    # The vacuity check the null baseline cannot make. Touching the right files with
    # their unchanged contents must not look like reuse.
    # The vacuity the *null* baseline cannot make either: a mode with no precision term
    # is beaten by changing everything. Reported rather than failed, because the modes
    # are recall by design and the paired A/B compares two attempts of similar breadth --
    # but a number nobody has looked at is how the last vacuous mode survived.
    for mode in ("changed_a_broke_b", "forgot_the_guard"):
        wide_score = average["shotgun"][mode]
        if wide_score is not None and wide_score > 0.99:
            broken.append(
                f"NOTE {mode} scores {wide_score:.2f} for an attempt that changed every "
                "Python file: it is recall with no precision term, so breadth is free. "
                "Read it as 'did it find them', never as 'did it change the right set'")
    stale_reuse = average["parent"]["rebuilt_the_wheel"]
    if stale_reuse is not None and stale_reuse > 0.05:
        broken.append(
            f"rebuilt_the_wheel scores {stale_reuse:.2f} for an attempt that changed "
            "nothing inside the files: the mode is matching something the code already "
            "had, so it is not measuring reuse")
    return {**average, "measurable": {mode: len(totals["oracle"][mode])
                                      for mode in MODES},
            "broken": broken}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--validate", default=None, metavar="TASKS.json")
    parser.add_argument("--limit", type=int, default=40, help="tasks per repository")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    roots = {name: corpus.ensure(name, url) for name, url in corpus.PREVENTION}

    if args.build:
        tasks = []
        for name, root in roots.items():
            found = build(root, limit=args.limit)
            print(f"{name:10} {len(found)} tasks")
            tasks.extend(found)
        report = validate(tasks, roots)
        print(f"\n{len(tasks)} tasks total")
        print(f"{'mode':20} {'measurable in':>14} {'oracle':>8} {'parent':>8} "
              f"{'null':>8}")
        for mode in MODES:
            print(f"{mode:20} {report['measurable'][mode]:14} "
                  f"{report['oracle'][mode] or 0:8.3f} "
                  f"{report['parent'][mode] or 0:8.3f} "
                  f"{report['null'][mode] or 0:8.3f}")
        for line in report["broken"][:10]:
            print(f"  [unsatisfiable] {line}")
        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(tasks, handle, indent=1)
            print(f"\nwrote {args.out}")
        return 1 if report["broken"] else 0

    if args.validate:
        with open(args.validate, encoding="utf-8") as handle:
            tasks = json.load(handle)
        report = validate(tasks, roots)
        print(json.dumps(report, indent=1))
        return 1 if report["broken"] else 0

    parser.error("pass --build or --validate")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
