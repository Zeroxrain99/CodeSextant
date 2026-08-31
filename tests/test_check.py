"""The half preflight cannot do, because it runs before there is anything to look at.

preflight asks its three questions from a name and an intention. Two limits come with
that and neither is fixable on that side of the edit: it only runs if the author
remembers to ask, and a name is all it has -- no body to compare shapes against, no
diff to say what actually happened. Measured, its reuse check finds no differently
named duplicate at all in some repositories.

After the edit both go away. These tests pin the difference: that a wheel reinvented
*and renamed* is caught, that a companion left out of the diff is named, that a caller
outside the diff is named, and that none of the three inflates its claim when it has
nothing.
"""
from __future__ import annotations

import subprocess
import textwrap

import pytest

from codesextant import engine, render


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _write(root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return path


def _commit(root, message, files):
    for rel, content in files.items():
        _write(root, rel, content)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    return root


DURATION = """
    def {name}({arg}):
        if {arg} is None:
            return 0
        total = 0
        for part in str({arg}).split(":"):
            total = total * 60 + int(part)
        if total < 0:
            raise ValueError("negative")
        return total
"""


# The wheel that was reinvented *and* renamed.

def test_a_renamed_duplicate_is_found_where_a_name_check_finds_nothing(repo):
    """Two names with no word in common, one body. This is the case that motivated it."""
    _commit(repo, "seed", {
        "util.py": DURATION.format(name="normalise_duration", arg="raw"),
        "app.py": "print('app')\n",
    })
    engine.index_project(str(repo), force=True)
    _write(repo, "app.py", DURATION.format(name="seconds_from_clock", arg="value"))

    found = engine.check(str(repo))["rebuilt"]

    assert [entry["name"] for entry in found] == ["seconds_from_clock"]
    assert [m["name"] for m in found[0]["matches"]] == ["normalise_duration"]

    # And the name-based check, asked the same question before the edit, cannot see it.
    ahead = engine.preflight(str(repo), "app.py", symbol="seconds_from_clock")
    assert "normalise_duration" not in {e["name"] for e in ahead["already_exists"]}


def test_a_unit_that_merely_moved_is_not_called_a_duplicate(repo):
    """Both halves of a move are in the diff. Reporting it would be a false positive.

    One of those in a section is enough to teach a reader to skip the section.
    """
    _commit(repo, "seed", {
        "old.py": DURATION.format(name="parse_duration", arg="raw"),
        "new.py": "PLACEHOLDER = 1\n",
    })
    engine.index_project(str(repo), force=True)
    _write(repo, "old.py", "PLACEHOLDER = 1\n")
    _write(repo, "new.py", DURATION.format(name="parse_duration", arg="raw"))

    assert engine.check(str(repo))["rebuilt"] == []


def test_a_trivial_body_is_not_offered_as_a_duplicate(repo):
    """Every one-line getter has the shape of every other one."""
    _commit(repo, "seed", {
        "a.py": "def first():\n    return 1\n",
        "b.py": "X = 1\n",
    })
    engine.index_project(str(repo), force=True)
    _write(repo, "b.py", "def second():\n    return 1\n")

    assert engine.check(str(repo))["rebuilt"] == []


# The companion nobody wrote down.

def test_a_companion_left_out_of_the_diff_is_named(repo):
    """version.py and packaging.toml never mention each other; history knows they pair."""
    for n in range(4):
        _commit(repo, f"release {n}", {
            "version.py": f"VERSION_STRING = '1.0.{n}'\n",
            "packaging.toml": f"version = '1.0.{n}'\n",
        })
    engine.index_project(str(repo), force=True)
    _write(repo, "version.py", "VERSION_STRING = '2.0.0'\n")

    companions = engine.check(str(repo))["companions"]

    assert [c["path"] for c in companions] == ["packaging.toml"]
    assert companions[0]["support"] == 4 and companions[0]["confidence"] == 1.0
    assert companions[0]["because"] == "version.py"


def test_a_companion_you_did_change_is_not_reported(repo):
    """The section is a list of omissions. Anything in the diff is not an omission."""
    for n in range(4):
        _commit(repo, f"release {n}", {
            "version.py": f"VERSION_STRING = '1.0.{n}'\n",
            "packaging.toml": f"version = '1.0.{n}'\n",
        })
    engine.index_project(str(repo), force=True)
    _write(repo, "version.py", "VERSION_STRING = '2.0.0'\n")
    _write(repo, "packaging.toml", "version = '2.0.0'\n")

    assert engine.check(str(repo))["companions"] == []


# The caller you did not open.

def test_a_caller_outside_the_diff_is_named(repo):
    _commit(repo, "seed", {
        "core.py": "def load_settings(path):\n    return {'path': path}\n",
        "app.py": ("from core import load_settings\n\n\n"
                   "def main():\n    return load_settings('x')\n"),
    })
    engine.index_project(str(repo), force=True)
    _write(repo, "core.py",
           "def load_settings(path, strict=False):\n    return {'path': path}\n")

    callers = engine.check(str(repo))["callers"]

    assert [c["symbol"] for c in callers] == ["load_settings"]
    assert callers[0]["callers"] == ["app.py"]


def test_a_caller_you_did_open_is_not_reported(repo):
    _commit(repo, "seed", {
        "core.py": "def load_settings(path):\n    return {'path': path}\n",
        "app.py": ("from core import load_settings\n\n\n"
                   "def main():\n    return load_settings('x')\n"),
    })
    engine.index_project(str(repo), force=True)
    _write(repo, "core.py",
           "def load_settings(path, strict=False):\n    return {'path': path}\n")
    _write(repo, "app.py", ("from core import load_settings\n\n\n"
                            "def main():\n    return load_settings('x', strict=True)\n"))

    assert engine.check(str(repo))["callers"] == []


# Saying nothing, honestly.

def test_finding_nothing_is_not_reported_as_a_clean_bill_of_health(repo):
    _commit(repo, "seed", {"a.py": "def alpha():\n    return 1\n"})
    engine.index_project(str(repo), force=True)
    _write(repo, "a.py", "def alpha():\n    return 2\n")

    result = engine.check(str(repo))

    assert not result["rebuilt"] and not result["companions"] and not result["callers"]
    note = next(n for n in result["notes"] if "Nothing found" in n)
    assert "heuristic" in note


def test_an_unchanged_tree_says_so_rather_than_finding_nothing(repo):
    """"No changes" and "changes with no findings" are different answers."""
    _commit(repo, "seed", {"a.py": "def alpha():\n    return 1\n"})
    engine.index_project(str(repo), force=True)

    result = engine.check(str(repo))

    assert result["changed_count"] == 0
    assert any("nothing to check" in n for n in result["notes"])


def test_a_project_without_git_says_what_it_needs(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "nogit"
    root.mkdir()
    _write(root, "a.py", "def alpha():\n    return 1\n")
    engine.index_project(str(root), force=True)

    result = engine.check(str(root))

    assert result["changed_count"] == 0
    assert any("Git worktree" in n for n in result["notes"])


def test_an_unindexed_project_says_so_instead_of_answering_from_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "fresh"
    root.mkdir()
    with pytest.raises(RuntimeError, match="not been indexed"):
        engine.check(str(root))


# Scope and cost.

def test_only_the_staged_change_is_read_when_asked(repo):
    for n in range(4):
        _commit(repo, f"release {n}", {
            "version.py": f"VERSION_STRING = '1.0.{n}'\n",
            "packaging.toml": f"version = '1.0.{n}'\n",
        })
    engine.index_project(str(repo), force=True)
    _write(repo, "version.py", "VERSION_STRING = '2.0.0'\n")
    _write(repo, "unrelated.py", "def spare():\n    return 1\n")
    _git(repo, "add", "version.py")

    staged = engine.check(str(repo), staged=True)
    assert staged["changed_files"] == ["version.py"]
    assert [c["path"] for c in staged["companions"]] == ["packaging.toml"]

    everything = engine.check(str(repo))
    assert "unrelated.py" in everything["changed_files"]


def test_a_branch_is_reviewed_against_where_it_left_the_base(repo):
    """Three-dot: what this branch added, not what the base gained meanwhile."""
    _commit(repo, "seed", {"a.py": "A = 1\n"})
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feature work", {"b.py": "def added():\n    return 1\n"})
    _git(repo, "checkout", "-q", "master")
    _commit(repo, "moved on", {"c.py": "C = 1\n"})
    _git(repo, "checkout", "-q", "feature")
    engine.index_project(str(repo), force=True)

    result = engine.check(str(repo), base="master")

    assert result["changed_files"] == ["b.py"], "c.py is the base's work, not this branch's"


def test_the_answer_stays_inside_its_token_budget(repo):
    files = {f"mod{n}.py": f"VALUE_{n} = {n}\n" for n in range(20)}
    for n in range(4):
        _commit(repo, f"sweep {n}", {k: f"{v.rsplit('=', 1)[0]}= {n}\n"
                                     for k, v in files.items()})
    engine.index_project(str(repo), force=True)
    _write(repo, "mod0.py", "VALUE_0 = 99\n")

    result = engine.check(str(repo), token_budget=200)

    assert result["approx_tokens"] <= 200
    assert result["truncated_by_budget"] is True


def test_the_rendering_marks_a_rebuilt_unit_against_what_it_repeats(repo):
    _commit(repo, "seed", {
        "util.py": DURATION.format(name="normalise_duration", arg="raw"),
        "app.py": "print('app')\n",
    })
    engine.index_project(str(repo), force=True)
    _write(repo, "app.py", DURATION.format(name="seconds_from_clock", arg="value"))

    text = "\n".join(render.check_lines(engine.check(str(repo)), str(repo)))

    assert "REBUILT" in text
    assert "seconds_from_clock  app.py:1" in text
    assert "already exists as  normalise_duration  util.py:1" in text
