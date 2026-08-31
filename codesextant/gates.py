"""The fences that run against every push, whether or not you go near them.

`guards` answers "which fence is my change about to meet" by retrieval: hundreds of
candidates, ranked, six shown. `experiments/exp10_invisible_guards.py` counted what that
reader cannot see and found the shape of the answer is different for these:

* there are **4 to 15 CI checks, 0 to 14 lint rules and 8 to 21 pre-commit hooks** per
  repository, against 182 to 964 Python guards -- two orders of magnitude fewer;
* and they apply to **everything**. A required check blocks a push whether or not the
  author has ever opened its workflow file, so the question "is this one relevant" has
  the same answer every time.

A handful of entries that always apply does not want ranking, relevance, or progressive
disclosure. It wants stating. So this module reads them once and hands back a short list
that the answer prints whole, and the machinery `guards` exists to provide is deliberately
not used on it.

The failure this treats is the one this repository committed itself: `target-version =
py311` sitting against a `requires-python >= 3.10` floor, unnoticed until CI said so. No
amount of ranking would have surfaced that. One line naming both would have.

**Read as a floor.** Workflows are read line by line rather than parsed, because this
package takes no YAML dependency: flow-style mappings are missed, and a `uses:` pointing
at a reusable workflow contributes checks that are not counted here. The TOML and INI
readers are exact. Where a reader is approximate the answer says so rather than implying
a completeness it does not have.
"""
from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10, where `tomli` is declared
    import tomli as tomllib

# Enough to say what runs without becoming the list nobody reads. One row per kind is
# the shape rather than one row per file: httpie has fifteen workflows, and listing them
# individually pushed the lint configuration and the language floor off the end -- the
# two rows that carry the most and are hardest to find by hand.
MAX_GATES = 6
_MAX_NAMES = 4
_MAX_WORKFLOWS = 3

_JOB = re.compile(r"^  ([A-Za-z_][\w-]*):\s*$")
_KEY = re.compile(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*)$")
_WORKFLOWS = os.path.join(".github", "workflows")


@dataclass(frozen=True)
class Gate:
    """One thing that runs against a push, and what would satisfy it."""

    kind: str
    name: str
    rule: str
    path: str

    def as_row(self) -> dict:
        return {"kind": self.kind, "name": self.name, "rule": self.rule,
                "path": self.path}


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _names(items, limit: int = _MAX_NAMES) -> str:
    shown = list(items)[:limit]
    more = len(items) - len(shown)
    return ", ".join(shown) + (f" +{more} more" if more > 0 else "")


def _block(text: str, key: str) -> list[str]:
    """The indented lines under a top-level ``key:``, and nothing after it."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            body = []
            for following in lines[index + 1:]:
                if following.strip() and not following[0].isspace():
                    break
                body.append(following)
            return body
    return []


def _gates_a_push(text: str) -> bool:
    """Whether this workflow runs against an ordinary change to a branch.

    The distinction is the difference between a true statement and a false one. A
    release workflow triggered by ``push: tags: v*`` is not standing in front of the
    edit you are making, and listing it as though it were would make this section wrong
    in the only direction that matters -- claiming something gates you when it does not.
    """
    for line in text.splitlines():
        matched = _KEY.match(line)
        if matched and matched.group(2) == "on" and not matched.group(1):
            inline = matched.group(3).strip()
            if inline:  # `on: [push, pull_request]` or `on: push`
                return any(word in inline
                           for word in ("push", "pull_request", "merge_group"))
            break
    body = _block(text, "on")
    triggers = {}
    for line in body:
        matched = _KEY.match(line)
        if matched and len(matched.group(1)) == 2:
            triggers[matched.group(2)] = []
        elif triggers and matched and len(matched.group(1)) == 4:
            triggers[next(reversed(triggers))].append(matched.group(2))
    if "pull_request" in triggers or "merge_group" in triggers:
        return True
    if "push" in triggers:
        # `push:` with no filter fires on every branch; with `branches:` it fires on
        # some; with only `tags:` it fires on none of them.
        return "tags" not in triggers["push"] or "branches" in triggers["push"]
    return False


def _jobs(text: str) -> list[str]:
    """Job keys under a top-level ``jobs:``, which is the one structural fact a line
    reader can trust. Everything from the next top-level key onwards is outside it."""
    inside = False
    found = []
    for line in text.splitlines():
        if line.startswith("jobs:"):
            inside = True
            continue
        if inside:
            if line and not line[0].isspace():
                break
            matched = _JOB.match(line)
            if matched:
                found.append(matched.group(1))
    return found


def _ci_gates(root: str) -> list[Gate]:
    """One row for everything CI runs against a push, not one row per workflow file.

    Which file a check lives in is not what a reader needs; what will go red is. Where
    the workflows are few they are named, and past that the count stands in for them.
    """
    directory = os.path.join(root, _WORKFLOWS)
    if not os.path.isdir(directory):
        return []
    workflows: list[str] = []
    jobs: list[str] = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith((".yml", ".yaml")):
            continue
        text = _read(os.path.join(directory, name))
        found = _jobs(text)
        # A workflow that only runs on a tag or a schedule is not a fence in front of
        # this change, and listing it would make the section wrong in the direction that
        # matters -- claiming something gates you when it does not.
        if not found or not _gates_a_push(text):
            continue
        workflows.append(name)
        jobs.extend(found)
    if not jobs:
        return []
    where = (f"{_WORKFLOWS}/".replace(os.sep, "/") + workflows[0]
             if len(workflows) == 1
             else f"{_WORKFLOWS}/".replace(os.sep, "/") + f"({len(workflows)} files)")
    rule = f"{len(jobs)} job(s) across {len(workflows)} workflow(s): {_names(jobs, 5)}"
    if len(workflows) <= _MAX_WORKFLOWS:
        rule = f"{len(jobs)} job(s) in {_names(workflows, _MAX_WORKFLOWS)}: " \
               f"{_names(jobs, 5)}"
    return [Gate("ci", "on push", rule, where)]


def _hook_gate(root: str) -> Gate | None:
    """pre-commit, which fires before the author can even push.

    exp10's first version reported zero of these everywhere, from a regex missing
    ``re.MULTILINE``; five of the seven repositories have between 8 and 21. The number
    that was wrong is the reason this row exists.
    """
    for name in (".pre-commit-config.yaml", ".pre-commit-config.yml"):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        ids = re.findall(r"^\s*-\s*id:\s*(\S+)", _read(path), re.MULTILINE)
        if ids:
            return Gate("hook", "pre-commit",
                        f"{len(ids)} hook(s): {_names(ids, 5)}", name)
    return None


def _ruff_gate(data: dict, relative: str) -> Gate | None:
    ruff = (data.get("tool", {}) or {}).get("ruff", {}) or {}
    lint = ruff.get("lint", {}) or {}
    selected = list(lint.get("select") or ruff.get("select") or [])
    ignored = list(lint.get("ignore") or ruff.get("ignore") or [])
    target = ruff.get("target-version") or lint.get("target-version")
    if not (selected or ignored or target):
        return None
    parts = []
    if selected:
        parts.append(f"select {_names(selected)}")
    if ignored:
        parts.append(f"ignore {_names(ignored)}")
    if target:
        parts.append(f"target-version {target}")
    return Gate("lint", "ruff", "; ".join(parts), relative)


def _floor_gate(data: dict, relative: str) -> Gate | None:
    """The language floor, printed beside the lint target on purpose.

    These are two numbers that have to agree and live in different keys of the same
    file. This repository shipped them disagreeing -- `py311` against a 3.10 floor -- and
    nothing said so until a CI job did. Putting them on adjacent lines is the whole
    intervention; a reader who sees both sees the mismatch.
    """
    requires = (data.get("project", {}) or {}).get("requires-python")
    if not requires:
        return None
    return Gate("floor", "requires-python", str(requires), relative)


def _mypy_gate(data: dict, relative: str) -> Gate | None:
    mypy = (data.get("tool", {}) or {}).get("mypy", {}) or {}
    strict = sorted(key for key, value in mypy.items()
                    if isinstance(value, bool) and value)
    if not strict:
        return None
    return Gate("lint", "mypy", _names(strict), relative)


def _cfg_gates(root: str) -> list[Gate]:
    found = []
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
            if not section.startswith(("flake8", "mypy", "pycodestyle")):
                continue
            parts = []
            for key in ("select", "ignore", "extend-ignore"):
                if parser.has_option(section, key):
                    entries = [p.strip() for p in
                               re.split(r"[,\n]", parser.get(section, key)) if p.strip()]
                    if entries:
                        parts.append(f"{key} {_names(entries)}")
            if parts:
                found.append(Gate("lint", section, "; ".join(parts), name))
    return found


def in_force(root: str) -> list[Gate]:
    """Everything that will run against a push, strongest-blocking first.

    CI leads because a red required check is the block that stops a merge outright;
    pre-commit follows because it fires even earlier, before a push exists at all; the
    lint configuration comes next because it is what both usually run; and the language
    floor sits last and beside it, since its whole value is being read next to the lint
    target it has to agree with.
    """
    found = list(_ci_gates(root))
    hook = _hook_gate(root)
    if hook is not None:
        found.append(hook)
    pyproject = os.path.join(root, "pyproject.toml")
    if os.path.isfile(pyproject):
        try:
            with open(pyproject, "rb") as handle:
                data = tomllib.load(handle)
        except (OSError, ValueError):
            data = {}
        for gate in (_ruff_gate(data, "pyproject.toml"),
                     _mypy_gate(data, "pyproject.toml"),
                     _floor_gate(data, "pyproject.toml")):
            if gate is not None:
                found.append(gate)
    found.extend(_cfg_gates(root))
    return found[:MAX_GATES]
