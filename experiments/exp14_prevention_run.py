"""Run the prevention A/B: the same task, with the tool available and without.

`exp12` built the task set and the scorer. This is the half that needs agents, and it is
the only design that answers the question this project was started for -- whether
somebody who *saw* CodeSextant's answer made a better change, or spent less fixing it.

Everything above it in `experiments/` measures retrieval: given a query, is the right
thing returned. That is a proxy. This is not.

What one trial is
-----------------
1. Check the task's parent commit out into a throwaway worktree.
2. Hand an agent the commit's own message and the one file it starts in -- never the
   file list. Finding the rest is the task.
3. Let it work. Under `with_tool` it is told CodeSextant is installed and what the three
   commands do; under `without_tool` that paragraph is absent and nothing else differs.
4. Read back which files it touched, and score with `exp12.score`.

Paired on purpose: both conditions see the same task, so the difference is the statistic
and the variance between tasks cancels.

**This module only prepares and scores.** It does not call an agent -- the caller does,
because agent invocation belongs to whatever is driving the session. `prepare` returns
the worktree and the prompt; `collect` reads the result back out.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments import (
    corpus,  # noqa: E402
    exp4_check,  # noqa: E402
)
from experiments import exp12_prevention as prevention  # noqa: E402

CONDITIONS = ("with_tool", "without_tool")

_TOOL_PARAGRAPH = """
CodeSextant is installed and indexed for this checkout. It exists to answer three
questions you cannot answer by reading one file:

  {cli} preflight . <file> --symbol <name>
      before you edit: does this already exist, what changes with this file
      historically, and what depends on it
  {cli} check .
      after you edit, reading your own diff: what the change looks like it forgot
  {cli} guards .
      which fence -- test, assertion, allowlist, limit -- your change is about to meet

Use it or do not; it is a tool, not an instruction.
"""

_PROMPT = """You are making a change to the {repo} repository, checked out at {tree}.

The change to make, in the words of the person who originally made it:

    {instruction}

Start in `{start_in}`. That file is where the change begins.

**A real change is rarely one file.** Other files in this repository may have to change
with it -- callers, tests, documentation, changelogs, anything that would break or go
stale. Finding them is the substance of this task; you are not given a list.

Edit the files you believe have to change. Make the edits real -- do not leave notes
saying what should be done. When you are finished, stop; do not commit.
{tool}
When you have finished, end your reply with one line in exactly this format, and nothing after it:
TOOLCALLS: <the number of tool calls you made>
"""


def worktree_for(task: dict, home: str) -> str | None:
    """A throwaway checkout of the task's parent commit."""
    root = corpus.ensure(task["repo"],
                         dict(corpus.PREVENTION)[task["repo"]])
    tree = os.path.join(home, f"{task['id'].replace('@', '_')}")
    done = subprocess.run(
        ["git", "-C", root, "worktree", "add", "-q", "--detach", tree, task["parent"]],
        capture_output=True, text=True)
    return tree if done.returncode == 0 else None


def release_worktree(task: dict, tree: str) -> None:
    root = corpus.ensure(task["repo"], dict(corpus.PREVENTION)[task["repo"]])
    subprocess.run(["git", "-C", root, "worktree", "remove", "--force", tree],
                   capture_output=True)
    shutil.rmtree(tree, ignore_errors=True)


def prompt_for(task: dict, tree: str, condition: str, cli: str) -> str:
    """The two prompts differ in exactly one paragraph, and in nothing else.

    Anything else that differed would be measured as if it were the tool. That includes
    the tool-call request at the end: it is in **both** arms, because a cost question
    asked of one condition and not the other is not a comparison.

    Self-report is a weak instrument and it is here only for the cost endpoint, never
    for what the attempt did -- `collect` reads the worktree for that. For the
    `with_tool` arm it is checkable: the daemon writes every request to its log, so how
    often the tool was actually reached is observable independently of what the agent
    says about itself. Where the two disagree, the log is the measurement.
    """
    tool = _TOOL_PARAGRAPH.format(cli=cli) if condition == "with_tool" else ""
    return _PROMPT.format(repo=task["repo"], tree=tree,
                          instruction=task["instruction"],
                          start_in=task["start_in"], tool=tool)


def collect(task: dict, tree: str) -> dict:
    """What the attempt actually did, scored.

    Read from `git status` rather than from anything the agent says about itself: an
    agent that reports what it meant to do is a worse instrument than the worktree.
    """
    done = subprocess.run(["git", "-C", tree, "status", "--porcelain"],
                          capture_output=True, text=True)
    changed: set[str] = set()
    for line in done.stdout.splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:                       # a rename reports both sides
            path = path.split(" -> ", 1)[1]
        if path:
            changed.add(path)

    sources: dict[str, str] = {}
    for relative in changed:
        absolute = os.path.join(tree, relative)
        if os.path.isfile(absolute):
            try:
                with open(absolute, encoding="utf-8", errors="replace") as handle:
                    sources[relative] = handle.read()
            except OSError:
                pass
    return {"changed": sorted(changed), "scored": prevention.score(task, changed, sources)}


def load_tasks(path: str | None = None) -> list[dict]:
    """The task set to run against.

    Defaults to the **stratified** set rather than the frozen one. exp15 measured 2% of
    the frozen tasks as having a companion no grep could reach and exp17 put the real
    rate at 7-11%; running the A/B on the frozen set would spend the agents on the
    stratum a grep already handles. `prevention_tasks.json` still works if passed
    explicitly, and it is the right instrument for `rebuilt_the_wheel`, which the
    stratified set can only measure on twelve tasks.
    """
    if path is None:
        path = os.path.join(os.path.dirname(__file__),
                            "prevention_tasks_stratified.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def report(trials: list[dict], *, seed: int = 0) -> dict:
    """Pair the two conditions per task, and answer per stratum.

    **Tokens are the primary endpoint, and that is a result rather than a preference.**
    exp17 measured 80% of real commits as grep-reachable: in that majority both arms
    find the companion, so a success rate ties and says nothing. What differs is the
    cost of finding it -- the agent without the tool still has to work out which symbols
    changed, grep each one, and read the results. That is "浪費時間和 token 修復" from
    the demand this project was started for, stated exactly.

    **Per stratum, because a pooled number would hide the answer.** With 60
    grep-reachable tasks against 44 hidden, a real difference on the hidden ones can be
    averaged into nothing by the majority where both arms succeed. Reporting the pool
    only is how an experiment concludes "no difference" about a population it never
    looked at separately.

    Each trial is `{"task_id", "stratum", "condition", "scored", "cost"}` where `cost`
    carries whatever the driver counted -- `tokens`, `tool_calls`, `seconds`. A trial
    missing its pair is dropped and counted, never filled in with a default: an absent
    measurement is not a zero.

    **One confound the success endpoint did not have.** The `with_tool` prompt is longer
    by exactly the tool paragraph -- about 540 bytes, call it 135 tokens -- so that arm
    starts every task in debt. The driver should count the prompt in, and *not* subtract
    the difference: leaving it in makes the tool look worse, so a measured saving is a
    lower bound rather than an estimate. Subtracting it would turn a conservative number
    into a flattering one, and the flattering version is the one nobody could check.
    """
    paired: dict[str, dict[str, dict]] = {}
    strata: dict[str, str] = {}
    for trial in trials:
        paired.setdefault(trial["task_id"], {})[trial["condition"]] = trial
        strata[trial["task_id"]] = trial.get("stratum", "unknown")

    complete = {task_id: sides for task_id, sides in paired.items()
                if set(sides) == set(CONDITIONS)}
    dropped = sorted(set(paired) - set(complete))

    def _slice(task_ids: list[str]) -> dict:
        out: dict = {"pairs": len(task_ids)}
        if not task_ids:
            return out
        for mode in ("changed_a_broke_b", "forgot_the_guard", "rebuilt_the_wheel"):
            usable = [t for t in task_ids
                      if complete[t]["with_tool"]["scored"].get(mode) is not None
                      and complete[t]["without_tool"]["scored"].get(mode) is not None]
            if not usable:
                continue
            with_tool = [complete[t]["with_tool"]["scored"][mode] for t in usable]
            without = [complete[t]["without_tool"]["scored"][mode] for t in usable]
            out[mode] = {
                "n": len(usable),
                "with_tool": sum(with_tool) / len(with_tool),
                "without_tool": sum(without) / len(without),
                **exp4_check.paired_difference(with_tool, without, seed=seed),
            }
        for metric in ("tokens", "tool_calls", "seconds"):
            usable = [t for t in task_ids
                      if complete[t]["with_tool"].get("cost", {}).get(metric) is not None
                      and complete[t]["without_tool"].get("cost", {}).get(metric)
                      is not None]
            if not usable:
                continue
            with_tool = [complete[t]["with_tool"]["cost"][metric] for t in usable]
            without = [complete[t]["without_tool"]["cost"][metric] for t in usable]
            out[metric] = {
                "n": len(usable),
                "with_tool": sum(with_tool) / len(with_tool),
                "without_tool": sum(without) / len(without),
                # Signed so that a *negative* difference means the tool cost less, which
                # is the direction the claim is about.
                **exp4_check.paired_difference(with_tool, without, seed=seed),
            }
        return out

    by_stratum = {}
    for stratum in sorted({strata[t] for t in complete}):
        by_stratum[stratum] = _slice(
            [t for t in complete if strata[t] == stratum])
    return {"pooled": _slice(sorted(complete)), "by_stratum": by_stratum,
            "dropped_unpaired": dropped}


def index_for_agent(tree: str, cli: str, home: str) -> tuple[bool, str]:
    """Index the checkout before the agent sees it, so the trial measures the tool
    rather than the wait. Returns (ok, what happened)."""
    done = subprocess.run([cli, "index", tree], capture_output=True, text=True,
                          env={**os.environ, "CODESEXTANT_HOME": home}, timeout=900)
    return done.returncode == 0, (done.stdout or done.stderr).strip().splitlines()[-1:]


def _self_test() -> int:
    """Prove the plumbing and the report, without an agent.

    Two halves. The worktree/prompt/collect path is checked on a real task. Then
    `report` is fed trials whose answer is known -- one arm perfect, the other empty,
    and a cost difference put in by hand -- because a reporting function nobody has run
    against a known answer is a reporting function that can report anything. The first
    version of this file's scorer shipped a mode that scored well for any plausible
    Python, and it took a third baseline to see it.
    """
    tasks = load_tasks()
    with tempfile.TemporaryDirectory() as home:
        task = tasks[0]
        tree = worktree_for(task, home)
        print(f"{task['id']} ({task.get('stratum')}): "
              f"worktree {'ok' if tree else 'FAILED'}")
        if not tree:
            return 1
        with_bytes = len(prompt_for(task, tree, "with_tool", "cs"))
        without_bytes = len(prompt_for(task, tree, "without_tool", "cs"))
        print(f"  files present: {len(os.listdir(tree))}")
        print(f"  prompt bytes:  with={with_bytes} without={without_bytes}")
        print(f"  clean collect: {collect(task, tree)['scored']}")
        release_worktree(task, tree)

    trials = []
    for index, task in enumerate(tasks[:12]):
        trials.append({"task_id": task["id"], "stratum": task["stratum"],
                       "condition": "with_tool",
                       "scored": {"changed_a_broke_b": 1.0},
                       "cost": {"tokens": 1000 + index}})
        trials.append({"task_id": task["id"], "stratum": task["stratum"],
                       "condition": "without_tool",
                       "scored": {"changed_a_broke_b": 0.0},
                       "cost": {"tokens": 3000 + index}})
    # One unpaired trial: it must be dropped and named, not silently completed.
    trials.append({"task_id": "lonely@0", "stratum": "hidden",
                   "condition": "with_tool", "scored": {"changed_a_broke_b": 1.0},
                   "cost": {"tokens": 1}})

    result = report(trials)
    pooled = result["pooled"]
    ok = True
    checks = [
        ("12 pairs", pooled["pairs"] == 12),
        ("perfect arm reads 1.0", pooled["changed_a_broke_b"]["with_tool"] == 1.0),
        ("empty arm reads 0.0", pooled["changed_a_broke_b"]["without_tool"] == 0.0),
        ("difference excludes zero",
         pooled["changed_a_broke_b"]["excludes_zero"] is True),
        ("tokens read as saved", pooled["tokens"]["mean"] == -2000.0),
        ("token difference excludes zero", pooled["tokens"]["excludes_zero"] is True),
        ("unpaired trial dropped and named",
         result["dropped_unpaired"] == ["lonely@0"]),
        ("strata reported separately", len(result["by_stratum"]) >= 1),
    ]
    for label, passed in checks:
        print(f"  {'ok  ' if passed else 'FAIL'} {label}")
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_self_test())
