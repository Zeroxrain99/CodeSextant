"""Run the prevention A/B: the same task, with the tool available and without.

`exp12` built the task set and the scorer. This is the half that needs agents, and it is
the only design that answers the question this project was started for -- whether
somebody who *saw* CodeSextant's answer made a better change, or spent less fixing it.

Everything above it in `experiments/` measures retrieval: given a query, is the right
thing returned. That is a proxy. This is not.

What one trial is
-----------------
1. Build a throwaway repository holding the task's parent commit and its ancestors
   -- and nothing after it. `checkout_for` says why that is not a `git worktree`.
2. Hand an agent the commit's own message and the one file it starts in -- never the
   file list. Finding the rest is the task.
3. Let it work. Under `with_tool` it is told CodeSextant is installed and what the three
   commands do; under `without_tool` that paragraph is absent and nothing else differs.
4. Read back which files it touched, and score with `exp12.score`.

Paired on purpose: both conditions see the same task, so the difference is the statistic
and the variance between tasks cancels.

**This module only prepares and scores.** It does not call an agent -- the caller does,
because agent invocation belongs to whatever is driving the session. `prepare` returns
the checkout and the prompt; `collect` reads the result back out.
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

**Work only from this checkout and its own git history.** Do not consult the project
upstream, its issue tracker, its commit history on any hosting service, or any other
network source -- not with git, not with a web request, not with a repository API.
Finding the companions here is the task; looking up what somebody else did is not.

Edit the files you believe have to change. Make the edits real -- do not leave notes
saying what should be done. When you are finished, stop; do not commit.
{tool}"""


def _full_mirror(repo: str) -> str:
    """A bare clone that actually holds its blobs.

    `corpus.ensure` clones `--filter=blob:none`, which is right for mining -- history
    and trees are all it reads -- and wrong here: `git bundle` has to write every
    object it packs, and a promisor repository answers `unable to read <oid>` for
    blobs it never fetched. So the prevention runs get their own full mirror. It is
    cheap: alembic is 5.8 MB and clones in two seconds.
    """
    root = os.path.join(corpus.corpus_root(), "_full")
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, f"{repo}.git")
    if not os.path.isdir(path):
        url = dict(corpus.PREVENTION)[repo]
        # `exp19.arm_git_guard` takes the network away from `git` for everything in the
        # container while a run is on. This mirror is the one clone that is *supposed*
        # to reach the network, so it carries the flag that says so.
        subprocess.run(["git", "clone", "-q", "--bare", url, path], check=True,
                       env={**os.environ, "E2_GIT_ALLOW": "1"})
    return path


def checkout_for(task: dict, home: str, *, name: str = "repo") -> str | None:
    """A checkout of the task's parent commit that does not contain the answer.

    **The first version of this used `git worktree add`, and every trial run against
    it is void.** A worktree shares the parent repository's object store, so the
    checkout was detached at the parent while still carrying the whole future: the
    reference commit was one `git show` away, `git log --all` listed it, and because
    the instruction *is* the commit message, `git log --all --grep=` found it in a
    single step. An agent volunteered that it had read `--stat` on the answer. Grepping
    the pilot transcripts for history probes found 8 of 19 trials touching it.

    So the checkout is rebuilt from a bundle of the parent alone. `git bundle` packs
    exactly what is reachable from the ref it is given, so the descendants are not
    copied -- not unreferenced, *absent*: `git cat-file` cannot get object info for the
    reference commit, and `git fsck` reports nothing dangling. The 1404 ancestors stay,
    because co-change and the tool under test both need them.

    Two further leaks were in the path, not the repository, and both were mine:
    the worktree was named `<repo>_<sha>` inside a home named `<repo>_<sha>_<condition>`,
    and `prompt_for` prints the path to the agent. Hence `name`, and the assertion.
    """
    sha = task["sha"][:7]
    tree = os.path.join(home, name)
    if sha in tree:
        raise ValueError(
            f"the checkout path {tree!r} contains the answer's sha {sha!r}; "
            "the prompt shows the agent this path")

    mirror = _full_mirror(task["repo"])
    ref = "refs/heads/__cs_base"
    bundle = os.path.join(home, "_base.bundle")
    try:
        subprocess.run(["git", "-C", mirror, "update-ref", ref, task["parent"]],
                       check=True, capture_output=True)
        made = subprocess.run(["git", "-C", mirror, "bundle", "create", bundle, ref],
                              capture_output=True, text=True)
    finally:
        subprocess.run(["git", "-C", mirror, "update-ref", "-d", ref],
                       capture_output=True)
    if made.returncode != 0:
        return None

    done = subprocess.run(
        ["git", "clone", "-q", "-b", "__cs_base", bundle, tree],
        capture_output=True, text=True)
    os.unlink(bundle)
    if done.returncode != 0:
        return None

    # The bundle is a remote, `__cs_base` is a tell, and the reflog still names what
    # was fetched. None of the three survives into what the agent sees.
    for argv in (["remote", "remove", "origin"],
                 ["branch", "-m", "__cs_base", "main"],
                 ["reflog", "expire", "--all", "--expire=now",
                  "--expire-unreachable=now"],
                 ["gc", "--prune=now", "--quiet"]):
        subprocess.run(["git", "-C", tree, *argv], capture_output=True)
    return tree


def ancestors(tree: str) -> int:
    """How much history the checkout kept. Co-change mines this; an empty answer here
    would make both arms of the trial equally blind and the comparison meaningless."""
    done = subprocess.run(["git", "-C", tree, "rev-list", "--count", "HEAD"],
                          capture_output=True, text=True)
    return int(done.stdout.strip() or 0)


def leaks(task: dict, tree: str) -> list[str]:
    """Everything about this checkout that could hand the agent the answer.

    Run before every trial. A leak found after the run is a run thrown away; this is
    the check that was missing when the pilot was run.
    """
    found = []
    if task["sha"][:7] in tree:
        found.append(f"path names the answer: {tree}")
    present = subprocess.run(["git", "-C", tree, "cat-file", "-e", task["sha"]],
                             capture_output=True)
    if present.returncode == 0:
        found.append(f"the reference commit {task['sha'][:10]} is in the object store")
    head = subprocess.run(["git", "-C", tree, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    if head != task["parent"]:
        found.append(f"HEAD is {head[:10]}, not the parent {task['parent'][:10]}")
    remotes = subprocess.run(["git", "-C", tree, "remote"],
                             capture_output=True, text=True).stdout.split()
    if remotes:
        found.append(f"remotes can refetch the future: {remotes}")
    dangling = [line for line in subprocess.run(
        ["git", "-C", tree, "fsck", "--no-progress"],
        capture_output=True, text=True).stdout.splitlines() if "dangling" in line]
    if dangling:
        found.append(f"{len(dangling)} dangling objects")
    return found


def release_checkout(tree: str) -> None:
    shutil.rmtree(tree, ignore_errors=True)


def prompt_for(task: dict, tree: str, condition: str, cli: str) -> str:
    """The two prompts differ in exactly one paragraph, and in nothing else.

    Anything else that differed would be measured as if it were the tool.

    **Nothing here asks the agent what it cost.** A line requesting a tool-call count
    was added to both arms on the belief that cost could not be observed from outside,
    and the first pilot trial refuted it twice over: the harness reports tokens, tool
    uses and duration for every agent it runs, and the agent's own count read **18**
    where the harness read **31**. Asking cost him thirty tokens to produce a number
    42% low, next to one that is free and right. See `cost_from_usage`.
    """
    # The paragraph forbidding upstream lookups is in `_PROMPT`, so it is in **both**
    # arms, identical, and cannot favour either. It is there because three of the first
    # eight trials fetched the reference commit rather than working the companions out:
    # the corpus repositories are public and the instruction *is* the upstream commit
    # message, so one search finds the answer. Blocking the roads (`exp19.arm_git_guard`
    # and the curl guard beside it) closes what can be closed from outside the agent;
    # this closes what cannot. It changes how hard the task is, equally on both sides,
    # which is the point -- the question is whether the tool helps you find companions
    # in a repository, not whether an agent can look up a diff.
    tool = _TOOL_PARAGRAPH.format(cli=cli) if condition == "with_tool" else ""
    return _PROMPT.format(repo=task["repo"], tree=tree,
                          instruction=task["instruction"],
                          start_in=task["start_in"], tool=tool)


def collect(task: dict, tree: str) -> dict:
    """What the attempt actually did, scored.

    Read from `git status` rather than from anything the agent says about itself: an
    agent that reports what it meant to do is a worse instrument than the checkout.
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


def cli_shim(home: str, cli: str) -> str:
    """A `codesextant` that records every invocation before running the real one.

    **Without this the experiment cannot tell its two most different outcomes apart.**
    "The agent used the tool and it did not help" and "the agent never ran it" call for
    opposite responses -- fix the answers, or fix the affordance -- and a file-change
    score reads identically for both.

    The first pilot trial tried to read this from the daemon log and got zero, which was
    not a measurement: `preflight`, `check` and `guards` run in the CLI's own process
    against the SQLite index, so a daemon that never starts writes no log. A column
    reading zero everywhere is a defect until proven otherwise, and that one was.

    **It also exports `CODESEXTANT_HOME`, and without that line the tool the agent gets
    is not the tool that was prepared.** `index_for_agent` indexes into the run's home;
    an invocation that does not name that home looks in `~/.codesextant`, finds nothing,
    and answers `This project had never been indexed; CodeSextant indexed it before
    answering` -- so the agent pays the whole indexing cost inside its own budget, gets
    an answer mined from no history, and every run shares one index directory. Measured
    on a prepared checkout before the twenty-pair run: the note is printed, verbatim, on
    the first call. `exp19.prepare` now asserts the note is absent before an agent is
    spent.

    It is named `codesextant` and placed in its own `bin/`, because the path appears in
    the prompt and is therefore part of the stimulus. A first version called it
    `cs-shim`, which tells the agent it is being watched -- and an agent that knows it is
    being watched for whether it uses a tool is not measuring what it would do.
    """
    binary = os.path.join(home, "bin")
    os.makedirs(binary, exist_ok=True)
    path = os.path.join(binary, "codesextant")
    log = os.path.join(home, "invocations.log")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            "#!/bin/sh\n"
            f'printf "%s\\t%s\\n" "$(date -u +%FT%TZ)" "$*" >> {log}\n'
            f'CODESEXTANT_HOME={home}\n'
            "export CODESEXTANT_HOME\n"
            f'exec {cli} "$@"\n')
    os.chmod(path, 0o755)
    return path


def invocations(home: str) -> list[str]:
    """What the agent actually ran, from the shim's log. Absent file means it ran
    nothing -- which is only meaningful because the shim was definitely in place."""
    log = os.path.join(home, "invocations.log")
    if not os.path.isfile(log):
        return []
    with open(log, encoding="utf-8", errors="replace") as handle:
        return [line.split("\t", 1)[-1].strip() for line in handle if line.strip()]


def cost_from_usage(usage: dict) -> dict:
    """The cost side of a trial, taken from the runner rather than from the agent.

    Whatever invokes the agent reports what it actually spent -- tokens, tool calls,
    wall-clock. That is the measurement; the agent's account of itself is not. Measured
    on the first pilot trial: self-reported 18 tool calls against 31 observed, low by
    42%, in a report that was otherwise careful and detailed. Being wrong about your own
    behaviour is not carelessness, it is what self-report is.

    Accepts whatever keys the runner supplies and normalises the three this experiment
    reads. A key the runner does not have stays absent rather than becoming zero: an
    unmeasured cost is not a free one, and `report` drops unmeasured pairs on purpose.
    """
    out: dict = {}
    for key, names in (("tokens", ("subagent_tokens", "tokens", "total_tokens")),
                       ("tool_calls", ("tool_uses", "tool_calls")),
                       ("seconds", ("duration_ms", "duration_sec", "seconds"))):
        for name in names:
            if usage.get(name) is None:
                continue
            value = float(usage[name])
            out[key] = value / 1000.0 if name == "duration_ms" else value
            break
    return out


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

    Two halves. The checkout/prompt/collect path is checked on a real task. Then
    `report` is fed trials whose answer is known -- one arm perfect, the other empty,
    and a cost difference put in by hand -- because a reporting function nobody has run
    against a known answer is a reporting function that can report anything. The first
    version of this file's scorer shipped a mode that scored well for any plausible
    Python, and it took a third baseline to see it.
    """
    tasks = load_tasks()
    with tempfile.TemporaryDirectory() as home:
        task = tasks[0]
        tree = checkout_for(task, home)
        print(f"{task['id']} ({task.get('stratum')}): "
              f"checkout {'ok' if tree else 'FAILED'}")
        if not tree:
            return 1
        with_bytes = len(prompt_for(task, tree, "with_tool", "cs"))
        without_bytes = len(prompt_for(task, tree, "without_tool", "cs"))
        print(f"  files present: {len(os.listdir(tree))}")
        print(f"  ancestors:     {ancestors(tree)}")
        print(f"  prompt bytes:  with={with_bytes} without={without_bytes}")
        print(f"  clean collect: {collect(task, tree)['scored']}")
        # The isolation is the experiment's validity, so it is asserted, not printed.
        found = leaks(task, tree)
        print(f"  leaks:         {found or 'none'}")
        if found:
            return 1
        # And the guard itself is exercised: a path that names the answer must not
        # merely be reported, it must refuse to be built.
        try:
            checkout_for(task, home, name=f"x_{task['sha'][:7]}")
        except ValueError:
            print("  path guard:    refuses a path naming the sha")
        else:
            print("  path guard:    FAILED -- built a checkout naming the sha")
            return 1
        release_checkout(tree)

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
