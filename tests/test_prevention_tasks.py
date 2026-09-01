"""The scorer for the only experiment that would answer "does this help?".

Everything else in `experiments/` measures retrieval. `exp12_prevention` measures what
an attempt actually did, so its scorer is the one piece of that directory whose bugs
would be invisible: a mode that is trivially satisfied still produces a plausible number,
and a benchmark that reports a plausible wrong number is worse than no benchmark.

One of these tests exists because that already happened. The first version scored
"rebuilt the wheel" by matching identifiers against every name the repository defines,
which made `name`, `set`, `open` and `run` count as helpers -- any attempt writing
plausible Python scored well without reusing anything. The `null` baseline could not see
it, because a predictor that touches no files scores zero on a broken mode too.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from experiments import exp12_prevention as prevention

TASKS = pathlib.Path(__file__).resolve().parent.parent / "experiments" / \
    "prevention_tasks.json"
STRATIFIED = pathlib.Path(__file__).resolve().parent.parent / "experiments" / \
    "prevention_tasks_stratified.json"


def _task(**truth):
    base = {"files": [], "companions": [], "guard_files": [], "reuse": {}}
    base.update(truth)
    return {"id": "t@0", "repo": "r", "sha": "0" * 40, "parent": "1" * 40,
            "instruction": "do the thing", "start_in": "a.py", "truth": base}


def test_a_mode_with_nothing_to_measure_scores_none_rather_than_one():
    """The difference decides whether an easy task inflates a rate. A commit that
    touched no fence has not had its fence remembered -- it had no fence, and averaging
    a 1.0 in for it would make the whole corpus look better the less it contained."""
    scored = prevention.score(_task(companions=["b.py"]), {"b.py"}, {})
    assert scored["changed_a_broke_b"] == 1.0
    assert scored["forgot_the_guard"] is None
    assert scored["rebuilt_the_wheel"] is None


def test_each_mode_is_a_recall_over_what_that_commit_actually_had():
    task = _task(companions=["b.py", "c.py", "d.py"], guard_files=["b.py", "c.py"])
    scored = prevention.score(task, {"b.py"}, {})
    assert scored["changed_a_broke_b"] == pytest.approx(1 / 3)
    assert scored["forgot_the_guard"] == pytest.approx(1 / 2)


def test_touching_the_file_is_not_reaching_for_the_helper():
    """The defect that made the mode vacuous, pinned. Reuse is scored on what the file
    imports afterwards, so an attempt that opened the right file and wrote its own
    version of the helper scores zero -- which is the failure being measured."""
    task = _task(companions=["b.py"], reuse={"b.py": ["existing_helper"]})
    rewrote = "def existing_helper():\n    return 1\n"
    assert prevention.score(task, {"b.py"}, {"b.py": rewrote})[
        "rebuilt_the_wheel"] == 0.0
    reused = "from pkg.util import existing_helper\n\nexisting_helper()\n"
    assert prevention.score(task, {"b.py"}, {"b.py": reused})[
        "rebuilt_the_wheel"] == 1.0


def test_a_mention_is_not_an_import():
    """`name`, `set` and `open` are defined somewhere in every repository. Counting
    mentions is what made this mode meaningless the first time."""
    task = _task(companions=["b.py"], reuse={"b.py": ["helper"]})
    mentions = "# helper is what we want\nhelper = lambda: None\n"
    assert prevention.score(task, {"b.py"}, {"b.py": mentions})[
        "rebuilt_the_wheel"] == 0.0


def test_an_alias_still_counts_as_reaching_for_it():
    task = _task(companions=["b.py"], reuse={"b.py": ["short"]})
    aliased = "from pkg.util import a_very_long_helper as short\nshort()\n"
    assert prevention.score(task, {"b.py"}, {"b.py": aliased})[
        "rebuilt_the_wheel"] == 1.0


def test_unparseable_source_is_not_credited_with_importing_anything():
    task = _task(companions=["b.py"], reuse={"b.py": ["helper"]})
    broken = "from pkg import helper\ndef (:\n"
    assert prevention.score(task, {"b.py"}, {"b.py": broken})[
        "rebuilt_the_wheel"] == 0.0


# The frozen task set. It is checked in on purpose: a benchmark regenerated per run is
# one nobody can reproduce, and roadmap G1 asks for the opposite.

def test_the_published_task_set_is_well_formed():
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    assert len(tasks) >= 100
    seen = set()
    for task in tasks:
        assert task["id"] not in seen, f"duplicate task {task['id']}"
        seen.add(task["id"])
        for key in ("repo", "sha", "parent", "instruction", "start_in", "truth"):
            assert task[key], f"{task['id']} has no {key}"
        truth = task["truth"]
        assert truth["companions"], "a task with no companion cannot measure anything"
        assert task["start_in"] not in truth["companions"], (
            f"{task['id']}: the file the attempt starts in is not part of what it has "
            "to discover")
        assert task["start_in"] not in truth["guard_files"], (
            f"{task['id']}: a fence in the starting file is not one anybody forgot")


def test_the_task_instructions_do_not_hand_over_the_answer():
    """An instruction naming the companion files is not a task, it is the answer. The
    builder takes the commit's message and nothing else; this is what says so."""
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    leaked = [task["id"] for task in tasks
              if any(companion in task["instruction"]
                     for companion in task["truth"]["companions"])]
    assert not leaked, f"these instructions name a file to be discovered: {leaked[:5]}"


# ── the stratified set ──
# It exists because the frozen one above is not a sample: exp15 found 2% of its tasks
# had a companion no grep could reach, and exp17 measured 7-11% on real commits from the
# same repositories. A set that under-represents the only stratum this tool can help
# with cannot answer whether it helps.

def _stratified():
    if not STRATIFIED.is_file():
        pytest.skip("the stratified set has not been built in this checkout")
    return json.loads(STRATIFIED.read_text(encoding="utf-8"))


def test_the_stratified_set_holds_to_the_same_shape():
    """Same contract as the frozen set. A second task file that answers to a different
    standard is two benchmarks pretending to be one."""
    for task in _stratified():
        for key in ("repo", "sha", "parent", "instruction", "start_in", "truth",
                    "stratum"):
            assert task[key], f"{task['id']} has no {key}"
        truth = task["truth"]
        assert truth["companions"], "a task with no companion cannot measure anything"
        assert task["start_in"] not in truth["companions"]
        assert task["start_in"] not in truth["guard_files"]
        assert not any(companion in task["instruction"]
                       for companion in truth["companions"]), (
            f"{task['id']}: the instruction names a file to be discovered")


def test_the_stratified_set_actually_contains_the_stratum_it_was_built_for():
    """The whole point, pinned as a number.

    This file can be regenerated, and a regeneration that quietly reverts to the old
    proportions would leave every downstream result looking fine while measuring the
    easy half again. The frozen set has 2 hidden tasks of 120; anything near that is a
    regression whatever the total.
    """
    tasks = _stratified()
    hidden = [task for task in tasks if task["stratum"] == "hidden"]
    assert len(hidden) >= 30, (
        f"only {len(hidden)} of {len(tasks)} tasks are hidden -- an A/B on this set "
        "would measure the stratum a grep already handles")
    assert len(hidden) / len(tasks) >= 0.20


def test_the_two_sets_do_not_silently_become_one():
    """The frozen set is the record of what E1 and E1b measured. Overwriting it would
    make every published number unverifiable, so its size is pinned here rather than
    trusted to whoever runs the builder next."""
    frozen = json.loads(TASKS.read_text(encoding="utf-8"))
    assert len(frozen) == 120, "prevention_tasks.json is the frozen record; do not rebuild it"
    assert not any("stratum" in task for task in frozen), (
        "the frozen set predates stratification and gaining that field means it was "
        "regenerated")
