"""How much of what blocks people is outside what a Python reader can see?

`exp8` counted guards by reading Python with `ast`: 16 to 34 per thousand lines, 182 to
935 per repository. It said in its own conclusion that the number is a *floor*, because
the kinds it cannot see are conspicuously the ones that stop a build -- a required check,
a lint rule, a pre-commit hook, a column constraint. `exp9` then scored the shipped
`guards` at 0.306 held out over the guards it *can* see, which says nothing at all about
the ones it cannot.

Phase C of the roadmap proposes covering them. The rule in `experiments/README.md` is
that a candidate is measured before it is built, and the thing to measure here is not
"do these exist" -- they obviously do -- but **how often would the index have needed to
say something about one**. A kind that is dense and never touched is a bigger index and
not a better one.

So two numbers per repository, and the second is the one that orders the work:

1. **Inventory.** How many of each invisible kind exist at HEAD, beside the Python
   count from the same repository, so the ratio is readable.
2. **Reach.** Over the sampled history, what fraction of commits touch a file holding
   one. That is an upper bound on how often the kind could have mattered, and it is
   directly comparable to the 0.54-0.57 that `exp8` measured for Python guard files.

    ci_check       a job in a GitHub Actions workflow -- the thing that goes red
    lint_rule      a ruff/flake8 select or ignore entry, a mypy strictness flag
    hook           a pre-commit hook
    db_constraint  NOT NULL, UNIQUE, CHECK, PRIMARY KEY, FOREIGN KEY -- in `.sql`, and
                   in the Python where a Python project actually keeps them: a
                   SQLAlchemy `Column(..., nullable=False)`, a `UniqueConstraint`, a
                   Django field with `null=False`

**What this is not.** The workflow and pre-commit readers here are line-based, because
this package takes no YAML dependency and a feasibility probe should not add one. They
will miss anything written in flow style and will not resolve `uses:` into the checks a
reusable workflow contributes. The TOML and INI readers are exact. Read every workflow
number as a floor; if the floor is already small, the ceiling does not matter.

    python -m experiments.exp10_invisible_guards
"""
from __future__ import annotations

import argparse
import ast
import configparser
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10
    import tomli as tomllib

from codesextant import guards as guards_module  # noqa: E402
from experiments import corpus  # noqa: E402

KINDS = ("ci_check", "lint_rule", "hook", "db_constraint")

_JOB = re.compile(r"^  ([A-Za-z_][\w-]*):\s*$")
# MULTILINE is load-bearing and was missing in the first version: without it ``^`` only
# matches the start of the string, so ``findall`` over a whole file returns at most one
# hook. It reported zero pre-commit hooks in every repository and the conclusion drawn
# from that -- "this kind does not exist in the corpus" -- was false in five of seven.
_HOOK = re.compile(r"^\s*-\s*id:\s*(\S+)", re.MULTILINE)
_CONSTRAINT = re.compile(
    r"\b(NOT\s+NULL|UNIQUE|CHECK\s*\(|PRIMARY\s+KEY|FOREIGN\s+KEY)\b", re.IGNORECASE)

# Where a Python project actually keeps its schema fences. The first version of this
# experiment looked only in `.sql` and reported zero everywhere -- including in alembic,
# a migration tool, which was added to the corpus specifically to unblock this and turned
# out to write every constraint through SQLAlchemy instead. A detector that finds nothing
# in a database library is looking in the wrong place, not describing the world.
_CONSTRAINT_CALLS = {"ForeignKey", "ForeignKeyConstraint", "UniqueConstraint",
                     "CheckConstraint", "PrimaryKeyConstraint", "Index"}
_CONSTRAINT_KWARGS = {"nullable", "unique", "primary_key", "null", "blank", "index"}


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _ci_checks(text: str) -> int:
    """Jobs in a workflow, counted by the one structural fact a line reader can trust:
    a two-space key under a top-level ``jobs:``. Everything after the next top-level key
    is out of the block."""
    inside = False
    found = 0
    for line in text.splitlines():
        if line.startswith("jobs:"):
            inside = True
            continue
        if inside:
            if line and not line[0].isspace():
                break
            if _JOB.match(line):
                found += 1
    return found


def _python_constraints(source: str) -> int:
    """Schema fences expressed in Python.

    A `Column(..., nullable=False)` is exactly the guard this kind is about: it fails at
    runtime, in production, which is the most expensive place a fence can fire. Counted
    by AST rather than by regex so that a keyword inside a docstring or a comment does
    not become a constraint.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return 0
    found = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name in _CONSTRAINT_CALLS:
            found += 1
            continue
        # A keyword only counts where it is constraining something: `nullable=False`
        # and `unique=True` are fences, `nullable=True` and `unique=False` are the
        # absence of one.
        for keyword in node.keywords:
            if keyword.arg not in _CONSTRAINT_KWARGS:
                continue
            if not isinstance(keyword.value, ast.Constant):
                continue
            # `nullable=False` fences; `nullable=True` is the absence of a fence.
            # `unique=True` fences; `unique=False` is the absence of one. The value
            # that constrains is the opposite one for the two families.
            forbidding = keyword.arg in {"nullable", "null", "blank"}
            if keyword.value.value is not forbidding:
                found += 1
    return found


def _lint_rules(root: str) -> int:
    found = 0
    pyproject = os.path.join(root, "pyproject.toml")
    if os.path.isfile(pyproject):
        try:
            with open(pyproject, "rb") as handle:
                data = tomllib.load(handle)
        except (OSError, ValueError):
            data = {}
        tools = data.get("tool", {})
        ruff = tools.get("ruff", {})
        for section in (ruff, ruff.get("lint", {})):
            for key in ("select", "extend-select", "ignore", "extend-ignore"):
                found += len(section.get(key, []) or [])
            found += sum(len(v or []) for v in
                         (section.get("per-file-ignores", {}) or {}).values())
        # A mypy strictness flag set to a non-default is a fence: it fails a build that
        # would otherwise pass, and nothing in the Python source mentions it.
        found += sum(1 for key, value in (tools.get("mypy", {}) or {}).items()
                     if isinstance(value, bool) and value)
    for name in ("setup.cfg", "tox.ini", ".flake8"):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        parser = configparser.ConfigParser()
        try:
            parser.read(path, encoding="utf-8")
        except (configparser.Error, OSError, UnicodeDecodeError):
            continue
        for section in parser.sections():
            if not any(section.startswith(prefix)
                       for prefix in ("flake8", "mypy", "pycodestyle", "isort")):
                continue
            for key in ("select", "ignore", "extend-ignore", "per-file-ignores"):
                if parser.has_option(section, key):
                    found += len([part for part in
                                  re.split(r"[,\n]", parser.get(section, key))
                                  if part.strip()])
    return found


def _walk(root: str):
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".tox", ".venv"}]
        for name in files:
            yield os.path.join(base, name)


def _classify(relative: str, text: str) -> dict[str, int]:
    """Which invisible guards a single file holds. Path-driven, because that is what
    decides the file's role: a workflow is a workflow because of where it lives."""
    found = dict.fromkeys(KINDS, 0)
    normalised = relative.replace(os.sep, "/")
    if (normalised.startswith(".github/workflows/")
            and normalised.endswith((".yml", ".yaml"))):
        found["ci_check"] = _ci_checks(text)
    elif os.path.basename(normalised) in {".pre-commit-config.yaml",
                                          ".pre-commit-config.yml"}:
        found["hook"] = len(_HOOK.findall(text))
    elif normalised.endswith(".sql"):
        found["db_constraint"] = len(_CONSTRAINT.findall(text))
    return found


def inventory(root: str) -> dict:
    per_kind = dict.fromkeys(KINDS, 0)
    holders: dict[str, set[str]] = {kind: set() for kind in KINDS}
    python_guards = 0
    python_files: set[str] = set()

    for absolute in _walk(root):
        relative = os.path.relpath(absolute, root).replace(os.sep, "/")
        if relative.endswith(".py"):
            found = guards_module.extract_file(absolute, relative)
            if found:
                python_guards += len(found)
                python_files.add(relative)
            constraints = _python_constraints(_read(absolute))
            if constraints:
                per_kind["db_constraint"] += constraints
                holders["db_constraint"].add(relative)
            continue
        counted = _classify(relative, _read(absolute))
        for kind, number in counted.items():
            if number:
                per_kind[kind] += number
                holders[kind].add(relative)

    rules = _lint_rules(root)
    per_kind["lint_rule"] += rules
    if rules:
        for name in ("pyproject.toml", "setup.cfg", "tox.ini", ".flake8"):
            if os.path.isfile(os.path.join(root, name)):
                holders["lint_rule"].add(name)

    return {"per_kind": per_kind, "holders": {k: sorted(v) for k, v in holders.items()},
            "python_guards": python_guards, "python_files": sorted(python_files)}


def reach(repo: str, found: dict, *, warmup_fraction: float = 0.3) -> dict:
    """How often a sampled commit touches a file holding each kind.

    Compared against the same statistic for Python guard files, which exp8 put at
    0.54-0.57 -- that is the bar, and a kind well under it is a bigger index rather than
    a better one however many entries it has.
    """
    commits = corpus.history(repo)
    warmup = int(len(commits) * warmup_fraction)
    sampled = commits[warmup:]
    if not sampled:
        return {}
    sets = {kind: set(found["holders"][kind]) for kind in KINDS}
    sets["python"] = set(found["python_files"])
    touched = dict.fromkeys(sets, 0)
    for _sha, files in sampled:
        for kind, paths in sets.items():
            if files & paths:
                touched[kind] += 1
    return {kind: number / len(sampled) for kind, number in touched.items()} | {
        "commits": len(sampled)}


def _print(report: dict) -> None:
    found, seen = report["inventory"], report["reach"]
    print(f"\n=== {report['repo']}")
    print(f"{'kind':16} {'count':>8} {'files':>7} {'commits touching':>17}")
    print(f"{'python (exp8)':16} {found['python_guards']:8} "
          f"{len(found['python_files']):7} {seen.get('python', 0):17.3f}")
    for kind in KINDS:
        print(f"{kind:16} {found['per_kind'][kind]:8} "
              f"{len(found['holders'][kind]):7} {seen.get(kind, 0):17.3f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--dump", default=None)
    args = parser.parse_args()
    repos = args.repo or [corpus.ensure(name, url) for name, url in corpus.EXTERNAL]
    reports = []
    for repo in repos:
        found = inventory(repo)
        report = {"repo": os.path.basename(os.path.abspath(repo)),
                  "inventory": found, "reach": reach(repo, found)}
        reports.append(report)
        _print(report)
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as handle:
            json.dump(reports, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
