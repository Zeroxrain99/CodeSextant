"""What runs against every push, and why this one is not ranked like everything else.

`guards` retrieves: hundreds of candidates, per-guard evidence, six shown. exp10 counted
the fences a Python reader cannot see and found the answer wants a different shape --
4 to 15 CI checks, 8 to 21 pre-commit hooks, 0 to 14 lint rules, and every one of them
applies to every change. Asking "is this relevant" has the same answer each time, so the
asking is the waste.

These pin the three claims that makes safe: it is short, it is true, and it does not say
something gates you when it does not.
"""
from __future__ import annotations

import textwrap

import pytest

from codesextant import gates


def _write(root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return path


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _write(root, ".github/workflows/tests.yml", """
        name: Tests
        on:
          push:
            branches: [main]
          pull_request:
        jobs:
          test:
            runs-on: ubuntu-latest
            steps: []
          lint:
            runs-on: ubuntu-latest
            steps: []
    """)
    _write(root, ".github/workflows/release.yml", """
        name: Release
        on:
          workflow_dispatch:
          push:
            tags:
              - 'v*'
        jobs:
          release:
            runs-on: ubuntu-latest
            steps: []
    """)
    _write(root, ".pre-commit-config.yaml", """
        repos:
          - repo: local
            hooks:
              - id: ruff-check
                name: ruff
              - id: end-of-file-fixer
                name: eof
    """)
    _write(root, "pyproject.toml", """
        [project]
        name = "proj"
        requires-python = ">=3.10"

        [tool.ruff]
        target-version = "py311"

        [tool.ruff.lint]
        select = ["E", "F"]
        ignore = ["E501"]
    """)
    return root


def test_a_workflow_that_only_fires_on_a_tag_is_not_standing_in_your_way(project):
    """The one direction this section must never be wrong in.

    Saying a release workflow gates an ordinary edit is worse than saying nothing: it
    sends a reader looking for a check that will never run, which is the cost this whole
    tool exists to avoid rather than to add to.
    """
    found = gates.in_force(str(project))
    ci = [gate for gate in found if gate.kind == "ci"]
    assert len(ci) == 1
    assert "release" not in ci[0].rule
    assert "test" in ci[0].rule and "lint" in ci[0].rule


def test_the_lint_target_and_the_language_floor_are_printed_next_to_each_other(project):
    """The failure this row was written for, reproduced in the fixture: `py311` against
    a 3.10 floor. Two numbers in two keys of one file that have to agree. This
    repository shipped them disagreeing and nothing said so until a CI job did -- no
    ranking would have surfaced it, and adjacency does."""
    found = gates.in_force(str(project))
    kinds = [gate.kind for gate in found]
    assert "lint" in kinds and "floor" in kinds
    rendered = {gate.kind: gate.rule for gate in found}
    assert "py311" in rendered["lint"]
    assert "3.10" in rendered["floor"]
    assert kinds.index("floor") == kinds.index("lint") + 1


def test_pre_commit_hooks_are_counted(project):
    """exp10's first version reported zero of these in every repository, from a regex
    missing `re.MULTILINE`. Five of the seven have between 8 and 21."""
    hooks = [gate for gate in gates.in_force(str(project)) if gate.kind == "hook"]
    assert len(hooks) == 1
    assert "2 hook(s)" in hooks[0].rule
    assert "ruff-check" in hooks[0].rule


def test_the_section_stays_short_however_many_workflows_there_are(project):
    """httpie has fifteen workflows. One row per file pushed the lint configuration and
    the language floor off the end -- the two rows hardest to find by hand."""
    for index in range(20):
        _write(project, f".github/workflows/extra{index}.yml", f"""
            name: Extra {index}
            on: [push]
            jobs:
              job{index}:
                runs-on: ubuntu-latest
                steps: []
        """)
    found = gates.in_force(str(project))
    assert len(found) <= gates.MAX_GATES
    kinds = {gate.kind for gate in found}
    assert {"ci", "lint", "floor", "hook"} <= kinds, (
        "a repository with many workflows must not lose the rows that are not workflows")
    ci = next(gate for gate in found if gate.kind == "ci")
    assert "21 workflow(s)" in ci.rule


def test_a_project_with_none_of_this_says_nothing_rather_than_guessing(tmp_path):
    empty = tmp_path / "bare"
    empty.mkdir()
    assert gates.in_force(str(empty)) == []


def test_flow_style_triggers_are_understood(tmp_path):
    root = tmp_path / "flow"
    root.mkdir()
    _write(root, ".github/workflows/ci.yml", """
        on: [push, pull_request]
        jobs:
          build:
            runs-on: ubuntu-latest
            steps: []
    """)
    assert [gate.kind for gate in gates.in_force(str(root))] == ["ci"]


def test_guards_carries_it_and_keeps_it_apart_from_the_ranked_answer(project, monkeypatch):
    """Separate keys because they are separate claims. Merging a set that always applies
    into a list ranked by relevance would make the ranking a lie about half its rows --
    the invariant HANDOFF.md layer 3 holds for `dependents` against `callers`."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(project.parent / "_db"))
    from codesextant import engine  # noqa: PLC0415 - after the home is set
    found = engine.guards(str(project), target="pyproject.toml")
    assert found["in_force"], "the always-on set does not depend on there being a diff"
    assert all("why" not in row for row in found["in_force"])
    assert all(row.get("kind") for row in found["guards"])
