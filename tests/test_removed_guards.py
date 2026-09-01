"""`check`'s fourth question: what did this change take *away*?

The other three modes -- rebuilt, companions, callers -- all ask what the change forgot
to **add**, and none of them can see a fence that is now gone. That is the first demand
almost verbatim: a guard its author wrote months ago blocks them now, they do not
remember why it is there, and the cheapest way out looks like deleting it.

**Both directions are pinned here, and the silent half is the one that decides whether
anybody leaves the mode switched on.** exp20 measured the cost of getting it wrong: over
1,382 real commits, 108 of 183 apparent removals -- 59% -- were the same fence under a
new name or in a new file. A mode that interrupts for those is noise.
"""
from __future__ import annotations

import subprocess

import pytest

from codesextant import engine

BEFORE_SOURCE = '''
import os

# The upstream API rate-limits above five in flight; more just queues and times out.
MAX_INFLIGHT = 5

DEBUG = os.environ.get("APP_DEBUG")

UNEXPLAINED_CAP = 7


def submit(n):
    # Deliberate: a caller that batches past the cap silently loses the tail.
    assert n <= MAX_INFLIGHT, "too many in flight"
    if n < 0:
        raise ValueError("negative batch size")
    return n
'''

BEFORE_TEST = '''
from src.limits import submit


def test_submit_rejects_over_cap():
    """Regression: batching past the cap used to drop the tail silently."""
    try:
        submit(99)
    except AssertionError:
        return
    raise AssertionError("expected the cap to hold")
'''


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True)


@pytest.fixture
def fenced(tmp_path, monkeypatch):
    """A committed project with three explained fences and one unexplained one."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "limits.py").write_text(BEFORE_SOURCE, encoding="utf-8")
    (root / "tests" / "test_limits.py").write_text(BEFORE_TEST, encoding="utf-8")
    _git(root.parent, "init", "-q", str(root))
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def _reported(root):
    return engine.check(str(root))["removed_guards"]


def test_a_deleted_fence_is_reported_with_the_reason_its_author_wrote(fenced):
    """Removing the assert, deleting the test, and loosening the threshold."""
    (fenced / "src" / "limits.py").write_text('''
import os

MAX_INFLIGHT = 5000

DEBUG = os.environ.get("APP_DEBUG")


def submit(n):
    if n < 0:
        raise ValueError("negative batch size")
    return n
''', encoding="utf-8")
    (fenced / "tests" / "test_limits.py").unlink()

    found = {(e["change"], e["kind"]): e for e in _reported(fenced)}
    assert ("removed", "test") in found
    assert ("removed", "assert") in found
    assert ("weakened", "threshold") in found

    # The author's sentence, verbatim and attributed -- a reader deciding whether to
    # put the fence back needs the reason, not a paraphrase or a confidence score.
    assert "drop the tail silently" in found[("removed", "test")]["reason"]
    assert found[("removed", "test")]["reason_source"] == "docstring"
    assert "silently loses the tail" in found[("removed", "assert")]["reason"]
    assert found[("removed", "assert")]["reason_source"] == "comment"

    loosened = found[("weakened", "threshold")]
    assert loosened["rule"] == "MAX_INFLIGHT = 5"
    assert loosened["now"] == "MAX_INFLIGHT = 5000"


def test_an_unexplained_fence_is_not_reported(fenced):
    """Four guards in five carry nothing but a name (exp8). A bare name gives the
    reader nothing to weigh against deleting it, so it is not worth an interruption."""
    source = (fenced / "src" / "limits.py").read_text(encoding="utf-8")
    (fenced / "src" / "limits.py").write_text(
        source.replace("UNEXPLAINED_CAP = 7\n", ""), encoding="utf-8")
    assert _reported(fenced) == []


def test_a_renamed_test_is_not_a_removal(fenced):
    """Even when the body changes too.

    A rename alone is caught by the derived rule; a rename *plus* an edit changes the
    name and the rule together, and from outside that is indistinguishable from a
    deletion plus an unrelated addition. What survives both is the docstring.
    """
    (fenced / "tests" / "test_limits.py").write_text('''
from src.limits import submit


def test_submit_rejects_over_cap_renamed():
    """Regression: batching past the cap used to drop the tail silently."""
    try:
        submit(99)
        submit(100)
    except AssertionError:
        return
    raise AssertionError("expected the cap to hold")
''', encoding="utf-8")
    assert _reported(fenced) == []


def test_a_test_moved_to_another_file_is_not_a_removal(fenced):
    moved = (fenced / "tests" / "test_limits.py").read_text(encoding="utf-8")
    (fenced / "tests" / "test_limits.py").unlink()
    (fenced / "tests" / "test_caps.py").write_text(moved, encoding="utf-8")
    assert _reported(fenced) == []


def test_editing_a_test_body_is_not_a_weakening(fenced):
    """A test's derived rule changes whenever its body does. exp20 measured 356 of 420
    weakenings as tests being edited normally -- 85% -- so `test` weakening is not
    reported at all. Deleting a test still is."""
    (fenced / "tests" / "test_limits.py").write_text(BEFORE_TEST.replace(
        "submit(99)", "submit(99)\n        submit(101)"), encoding="utf-8")
    assert _reported(fenced) == []


def test_the_empty_answer_carries_the_key(tmp_path, monkeypatch):
    """A caller that reads `removed_guards` on the answered path must not hit a
    KeyError on the path where there is no worktree."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "home"))
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    (plain / "m.py").write_text("x = 1\n", encoding="utf-8")
    assert engine.check(str(plain))["removed_guards"] == []
