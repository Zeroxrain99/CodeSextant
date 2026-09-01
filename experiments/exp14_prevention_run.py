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

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments import corpus  # noqa: E402
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
{tool}"""


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

    Anything else that differed would be measured as if it were the tool.
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


def index_for_agent(tree: str, cli: str, home: str) -> tuple[bool, str]:
    """Index the checkout before the agent sees it, so the trial measures the tool
    rather than the wait. Returns (ok, what happened)."""
    done = subprocess.run([cli, "index", tree], capture_output=True, text=True,
                          env={**os.environ, "CODESEXTANT_HOME": home}, timeout=900)
    return done.returncode == 0, (done.stdout or done.stderr).strip().splitlines()[-1:]


if __name__ == "__main__":  # a smoke check of the plumbing, not the experiment
    import json
    with open(os.path.join(os.path.dirname(__file__), "prevention_tasks.json"),
              encoding="utf-8") as handle:
        tasks = json.load(handle)
    with tempfile.TemporaryDirectory() as home:
        task = tasks[0]
        tree = worktree_for(task, home)
        print(f"{task['id']}: worktree {'ok' if tree else 'FAILED'}")
        if tree:
            print(f"  files present: {len(os.listdir(tree))}")
            print(f"  prompt bytes:  with={len(prompt_for(task, tree, 'with_tool', 'cs'))} "
                  f"without={len(prompt_for(task, tree, 'without_tool', 'cs'))}")
            print(f"  clean collect: {collect(task, tree)['scored']}")
            release_worktree(task, tree)
