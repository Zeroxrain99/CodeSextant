"""E2, run for real: twenty pairs, sampled and pre-registered before the first agent.

This is `exp14`'s design driven end to end. `exp14` owns the checkout, the prompt, the
shim and the scorer; this module owns the three things that have to be fixed *before*
anything is run, because fixing them afterwards is how a result becomes a story:

  1. **which tasks**, drawn by a seed written down here;
  2. **which arm each run is**, hidden behind an opaque run id so nothing in a path or
     a directory listing tells an agent what condition it is in;
  3. **what the answer will be read from**, decided before the numbers exist.

The nine-pair pilot that preceded this was thrown away whole: its checkouts were
`git worktree` and carried the answer's commit. `exp14.checkout_for` is the fix and
`exp14.leaks` is the assertion; `prepare` refuses to write a prompt for a checkout that
fails it, so a leaked trial cannot be run, let alone reported.

Pre-registration
----------------
**Sample.** Twenty tasks from `prevention_tasks_stratified.json` (155 tasks: 60
grep_reachable, 51 convention, 44 hidden), drawn with ``SEED`` by
``sample()``: **7 grep_reachable, 7 convention, 6 hidden**.

*Equal allocation, not proportional.* exp17 measured real commits at ~7% hidden on this
corpus, so a proportional draw of twenty would be roughly 16/2/2 and would spend the
budget on the stratum a grep already handles -- the one place the tool cannot help. Equal
allocation buys the most information per agent about the strata where the answer is not
already known.

**The price of that choice, stated before the numbers exist: the unweighted pool over
this sample is not an estimate of the average real change**, and must never be quoted as
one. It over-represents `hidden` by roughly four times. The per-stratum numbers are the
result; the pool is a summary of this sample and nothing wider. A prevalence-weighted
headline needs exp17's three-way breakdown, which it does not currently report.

**Primary endpoint: tokens, per stratum.** Fixed in `exp14.report` before the pilot and
unchanged. exp17 put 80% of real commits within reach of a grep, so in the majority of
cases both arms find the companion and a success rate ties; what differs is the cost of
finding it. That is "浪費時間和 token 修復" from the demand this project exists for.

**Secondary: the three scored modes** (`changed_a_broke_b`, `forgot_the_guard`,
`rebuilt_the_wheel`), read as "did it find them", never as "did it change the right
set" -- a shotgun that edits every Python file scores 1.00 on the first two.

**Statistic.** Paired bootstrap over tasks, as `exp14.report` implements it, 95%
interval. A pair is dropped, and named, unless **both** arms produced a cost reading.

**Stopping rule.** Twenty pairs, drawn now, run to completion. No pair is added,
re-run or dropped on the basis of its result. A pair may be dropped only for a
mechanical failure named here: `prepare` refused it, the agent produced no diff at
all, or a cost reading is missing. Every drop is reported with its reason.

**Validity checks, all recorded per run.** `exp14.leaks` clean before the agent starts;
the shim log for the `with_tool` arm (a `with_tool` run that never invoked the tool is
reported, not discarded -- "it did not help" and "it was never opened" are different
findings); and a global log of *every* `codesextant` invocation in the container, which
is how a `without_tool` agent stumbling onto the binary on `PATH` would be caught.

Amendment, after the first eight trials and before any of them was scored
-------------------------------------------------------------------------
**Three of the first eight fetched the reference commit instead of working the
companions out.** One cloned the upstream project and diffed against the answer's blob,
one called a repository API for the full patch and curled the `.patch` URL, one searched
upstream for the commit by its own instruction text. The corpus repositories are public
and the instruction *is* the upstream commit message, so a single search finds the
answer. `checkout_for` had taken the answer off the disk; nothing had taken away the
road to it.

Recorded as an amendment rather than folded in silently, because the numbers it changes
are the ones this file exists to protect. Three things change, and none of them is the
endpoint, the sample, or the statistic:

1. **A trial that looked the answer up is void and is re-run**, in the same class as
   `prepare` refusing one. `contaminated()` is the test, and it reads tool *calls*, not
   prose -- matching a bare `github.com` flagged a repository whose own `tox.ini` names
   it. On the eight finished trials it separates 5 clean from 3 contaminated with
   nothing in between.
2. **The roads are blocked where they can be blocked from outside the agent**:
   `arm_git_guard` refuses remote `git`, and a guard beside it refuses `curl` at a code
   host. Both sit ahead of `/usr/bin` on `PATH`, so deleting one file restores the
   original binary.
3. **The prompt says not to, in both arms, identically** -- see `exp14.prompt_for`. A
   restricted agent with no network tools at all would have been better and was written
   (`.claude/agents/e2-trial.md`), but a new agent definition is not loadable inside a
   running session, so the prompt carries what the sandbox could not.

**All forty runs are re-run under this**, including the five that came back clean: the
prompt changed, and a trial run under a different prompt is not comparable to one run
under this one. The eight already spent are reported as what they cost and not as a
result.

**The residual risk, stated rather than hoped:** a repository API tool remains in the
agent's hands and cannot be taken away from here, and a hand-written HTTP fetch from
Bash would reach the network. That is what `contaminated()` is for, and why it runs on
every trial rather than on the ones that look suspicious.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments import corpus  # noqa: E402
from experiments import exp14_prevention_run as run  # noqa: E402

SEED = 20260901
ALLOCATION = {"grep_reachable": 7, "convention": 7, "hidden": 6}

ROOT = os.environ.get("CODESEXTANT_E2_ROOT", "/tmp/e2run")
REAL_CLI = "/usr/local/bin/codesextant-real"
PATH_CLI = "/usr/local/bin/codesextant"
GLOBAL_LOG = os.path.join(ROOT, "all-invocations.log")
GIT_LOG = os.path.join(ROOT, "all-git.log")
GIT_GUARD = "/usr/local/bin/git"


# --------------------------------------------------------------------------- sample

def sample(seed: int = SEED, allocation: dict | None = None) -> list[dict]:
    """The twenty tasks, drawn deterministically.

    Within a stratum the draw is round-robin over repositories before it is random, so
    a stratum cannot come out all-alembic by luck and turn a repository effect into a
    tool effect. Everything else is `random.Random(seed)`, so the sample is a function
    of the seed and can be recomputed by anybody.
    """
    allocation = allocation or ALLOCATION
    tasks = run.load_tasks()
    rng = random.Random(seed)
    drawn: list[dict] = []
    for stratum, wanted in sorted(allocation.items()):
        pool: dict[str, list[dict]] = {}
        for task in tasks:
            if task["stratum"] == stratum:
                pool.setdefault(task["repo"], []).append(task)
        for repo in pool:
            rng.shuffle(pool[repo])
        repos = sorted(pool)
        rng.shuffle(repos)
        taken = 0
        while taken < wanted:
            progressed = False
            for repo in repos:
                if taken >= wanted:
                    break
                if pool[repo]:
                    drawn.append(pool[repo].pop())
                    taken += 1
                    progressed = True
            if not progressed:                    # a stratum too small to fill
                break
    return drawn


def plan(seed: int = SEED) -> list[dict]:
    """Forty runs behind opaque ids.

    The run id is all an agent can see of its own trial: the checkout lives at
    `<root>/runs/<run_id>/repo`, and `exp14.prompt_for` prints that path. So the id
    carries neither the task, nor the answer's sha, nor -- and this is the one that is
    easy to miss -- the condition. `run_07` tells an agent nothing; `..._with_tool`
    would tell it that somebody is watching whether it uses a tool, and an agent that
    knows that is not measuring what it would do.
    """
    rng = random.Random(seed + 1)
    runs = [{"task_id": task["id"], "stratum": task["stratum"], "condition": condition}
            for task in sample(seed) for condition in run.CONDITIONS]
    rng.shuffle(runs)
    for index, item in enumerate(runs, start=1):
        item["run_id"] = f"run_{index:02d}"
    return runs


def _plan_path() -> str:
    return os.path.join(ROOT, "plan.json")


def load_plan() -> list[dict]:
    with open(_plan_path(), encoding="utf-8") as handle:
        return json.load(handle)


def find(run_id: str) -> dict:
    for item in load_plan():
        if item["run_id"] == run_id:
            return item
    raise KeyError(run_id)


def task_for(task_id: str) -> dict:
    for task in run.load_tasks():
        if task["id"] == task_id:
            return task
    raise KeyError(task_id)


# ---------------------------------------------------------------------- the git guard

_GIT_GUARD_SCRIPT = """#!/bin/sh
# E2 ground-truth guard: log every git call, refuse the ones that reach a remote.
printf "%s\\t%s\\t%s\\n" "$(date -u +%FT%TZ)" "$(pwd)" "$*" >> {log} 2>/dev/null
if [ "$E2_GIT_ALLOW" != "1" ]; then
  for arg in "$@"; do
    case "$arg" in
      https://*|http://*|git://*|ssh://*|git@*)
        echo "git: remote access is disabled in this environment" >&2
        exit 128
        ;;
    esac
  done
fi
exec /usr/bin/git "$@"
"""


def arm_git_guard() -> str:
    """Take the network away from `git`, and write down every call either way.

    **Isolating the checkout is not isolating the trial.** The repositories under test
    are public, the task instruction *is* the upstream commit message, and the
    container has a network -- so an agent that cannot find the answer locally can
    clone the project and read it. One did, in the first batch of eight: it cloned
    `sqlalchemy/alembic` into a scratch directory, found the commit whose parent was
    this checkout's HEAD, and compared its own edit against the upstream blob. That
    trial measured a lookup, not a change.

    `checkout_for` removed the answer from the repository. This removes the road to it.

    The guard is written to `/usr/local/bin/git`, which precedes `/usr/bin` on `PATH`,
    so deleting the file restores the original binary and nothing was moved. Local git
    keeps working -- `checkout_for` needs `bundle` and a clone from a file path -- and
    any argument carrying a remote scheme is refused unless `E2_GIT_ALLOW=1` marks the
    caller as the harness.

    **What it does not cover, stated rather than hoped:** an agent that calls
    `/usr/bin/git` by its full path, or reads the upstream over HTTP by another route.
    So the log is kept as well as the block, and `contaminated` reads both.
    """
    os.makedirs(ROOT, exist_ok=True)
    with open(GIT_GUARD, "w", encoding="utf-8") as handle:
        handle.write(_GIT_GUARD_SCRIPT.format(log=GIT_LOG))
    os.chmod(GIT_GUARD, 0o755)
    return GIT_GUARD


_FETCH_GUARD_SCRIPT = """#!/bin/sh
# E2 ground-truth guard: log every {name}, refuse the ones aimed at a code host.
printf "%s\\t%s\\t{name} %s\\n" "$(date -u +%FT%TZ)" "$(pwd)" "$*" >> {log} 2>/dev/null
if [ "$E2_GIT_ALLOW" != "1" ]; then
  for arg in "$@"; do
    case "$arg" in
      *github.com*|*githubusercontent.com*|*gitlab.com*|*bitbucket.org*|*codeload*)
        echo "{name}: this host is not reachable from this environment" >&2
        exit {code}
        ;;
    esac
  done
fi
exec /usr/bin/{name} "$@"
"""

# `git` is not the only road. One trial reached the answer with `curl` at a `.patch`
# URL, so the fetchers get the same treatment: log everything, refuse a code host.
FETCH_GUARDS = {"curl": 6, "wget": 4}


def arm_fetch_guards() -> list[str]:
    armed = []
    os.makedirs(ROOT, exist_ok=True)
    for name, code in FETCH_GUARDS.items():
        if not os.path.isfile(f"/usr/bin/{name}"):
            continue
        path = f"/usr/local/bin/{name}"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_FETCH_GUARD_SCRIPT.format(name=name, log=GIT_LOG, code=code))
        os.chmod(path, 0o755)
        armed.append(path)
    return armed


def disarm_fetch_guards() -> None:
    for name in FETCH_GUARDS:
        path = f"/usr/local/bin/{name}"
        if os.path.isfile(path):
            os.unlink(path)


def disarm_git_guard() -> None:
    if os.path.isfile(GIT_GUARD):
        os.unlink(GIT_GUARD)


_REMOTE_SUBCOMMANDS = ("clone", "fetch", "pull", "ls-remote", "remote", "archive")

# What a lookup looks like in a transcript, as observed rather than imagined. Each of
# these was used by a real trial in the first batch of eight: `mcp__github__` twice
# (`search_commits` with the instruction text, then `get_commit` with `full_patch`),
# `curl` at a `.patch` URL, and `git clone` of the upstream project. Matched against
# tool *inputs* only -- a bare `github.com` matches a repository's own `tox.ini` and
# was a false positive on the first pass.
_LOOKUP_MARKERS = (
    ('"name":"mcp__github__', "called a GitHub API tool"),
    ('"name":"WebFetch"', "fetched a web page"),
    ('"name":"WebSearch"', "searched the web"),
)


def _lookups(text: str, slug: str, sha: str) -> list[str]:
    """Calls that actually fetched something about *this* task's upstream.

    Three refinements, each from a false positive rather than from imagination:

    * A bare `github.com` match flagged a repository whose own `tox.ini` names it, so
      only tool **inputs** are searched, never prose.
    * A call has to name this task's repository. run_22 asked a repository API about
      `astral-sh/ruff-pre-commit` to resolve a pre-commit hook's pinned SHA -- tooling,
      nothing to do with the answer.
    * A call has to have **returned** something. The same call came back
      `Access denied: repository ... is not configured for this session`. An attempt
      that obtained nothing taught the agent nothing, and voiding a trial for it would
      throw away a clean run to look strict.

    Naming the reference commit is decisive on its own: there is no innocent way to
    know a sha that appears nowhere in the checkout, the prompt or the path.
    """
    import json as _json
    found = []
    if sha[:10] in text:
        found.append(f"names the reference commit: {sha[:10]}")

    fetchers = ("mcp__github__", "WebFetch", "WebSearch")
    pending: dict[str, str] = {}
    for line in text.splitlines():
        try:
            record = _json.loads(line)
        except Exception:
            continue
        message = record.get("message") or {}
        for block in (message.get("content") or []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = str(block.get("name", ""))
                if not any(name.startswith(f) or name == f for f in fetchers):
                    continue
                if slug in _json.dumps(block.get("input") or {}):
                    pending[block.get("id")] = name
            elif block.get("type") == "tool_result":
                name = pending.pop(block.get("tool_use_id"), None)
                if name and not block.get("is_error"):
                    found.append(f"{name} returned data about {slug}")
    for chunk in text.split('"name":"Bash"')[1:]:
        command = chunk[:400]
        if slug in command or "githubusercontent" in command:
            found.append("shells out to the upstream repository")
            break
    return found


def contaminated(run_id: str, transcript: str | None = None) -> list[str]:
    """Evidence that this trial looked the answer up instead of working it out.

    Two sources, because neither alone is enough. The git log catches a remote
    operation wherever it was run from -- the leak is not confined to the checkout, so
    neither is the check. The transcript catches what the block does not.

    A hit is a mechanical failure of the trial, in the same class as `prepare`
    refusing it. It is not a result, and it is not read as one.
    """
    found = []
    task = task_for(find(run_id)["task_id"])
    url = dict(corpus.PREVENTION)[task["repo"]]
    slug = url.split("github.com/")[-1].removesuffix(".git")
    # **The git log is container-wide and append-only, so it has to be attributed
    # before it can be read.** Unscoped, it flagged all twenty-three finished trials
    # identically -- with the harness's own corpus clones, a `pip install` from a git
    # URL, and pre-commit's temporary clones of its hook repositories. A signal that
    # fires on every case is not a signal. Two conditions: the call has to come from
    # inside this run's checkout, and it has to name *this task's* upstream.
    marker = os.path.join(ROOT, "runs", run_id)
    if os.path.isfile(GIT_LOG):
        with open(GIT_LOG, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) != 3 or "://" not in parts[2]:
                    continue
                if not parts[1].startswith(marker) or slug not in parts[2]:
                    continue
                if any(word in _REMOTE_SUBCOMMANDS for word in parts[2].split()):
                    found.append(f"remote git in {parts[1]}: {parts[2]}")
    if transcript and os.path.isfile(transcript):
        with open(transcript, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        found.extend(f"transcript {why}" for why in _lookups(text, slug, task["sha"]))
    return sorted(set(found))


# ------------------------------------------------------------------- global tripwire

def arm_global_log() -> str:
    """Log every `codesextant` the container runs, whoever runs it.

    The `with_tool` arm gets `exp14.cli_shim`, which is in its prompt. The
    `without_tool` arm is never told the tool exists -- but the real binary is on
    `PATH`, so "it never occurred to it" and "it found it anyway" are two different
    experiments and only one of them is this one. This wrapper makes the difference
    observable instead of assumed. It records the working directory, which is what
    attributes an invocation back to a run.
    """
    os.makedirs(ROOT, exist_ok=True)
    if not os.path.exists(REAL_CLI):
        shutil.move(PATH_CLI, REAL_CLI)
    with open(PATH_CLI, "w", encoding="utf-8") as handle:
        handle.write(
            "#!/bin/sh\n"
            f'printf "%s\\t%s\\t%s\\n" "$(date -u +%FT%TZ)" "$(pwd)" "$*" '
            f'>> {GLOBAL_LOG} 2>/dev/null\n'
            f'exec {REAL_CLI} "$@"\n')
    os.chmod(PATH_CLI, 0o755)
    return PATH_CLI


def disarm_global_log() -> None:
    if os.path.exists(REAL_CLI):
        shutil.move(REAL_CLI, PATH_CLI)


def global_invocations(run_id: str, skip: int = 0) -> list[str]:
    """Every logged invocation whose working directory is inside this run.

    `skip` drops the ones `prepare` made itself. The log is append-only and shared by
    every run, so a run's own setup sits in front of whatever the agent did.
    """
    if not os.path.isfile(GLOBAL_LOG):
        return []
    marker = os.path.join(ROOT, "runs", run_id)
    out = []
    with open(GLOBAL_LOG, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3 and parts[1].startswith(marker):
                out.append(parts[2])
    return out[skip:]


# ------------------------------------------------------------------------- one trial

def home_of(run_id: str) -> str:
    return os.path.join(ROOT, "runs", run_id)


_NEVER_INDEXED = "had never been indexed"


def _served_the_prepared_index(tree: str, cli: str, task: dict) -> dict:
    """Ask the tool one question the way the agent will, and check who answers.

    The agent invokes the shim with whatever environment it happens to have. If that
    invocation does not reach the index `index_for_agent` just built, the tool the
    trial measures is not the tool that was prepared: it re-indexes from scratch inside
    the agent's own budget, mines no history, and writes into a directory every other
    run shares. CodeSextant says so in as many words -- "This project had never been
    indexed; CodeSextant indexed it before answering" -- and before the shim exported
    `CODESEXTANT_HOME` that note was printed on the first call of every `with_tool`
    trial. So the check is: strip the environment, ask, and refuse the run if the note
    comes back.
    """
    bare = {k: v for k, v in os.environ.items() if k != "CODESEXTANT_HOME"}
    done = subprocess.run([cli, "preflight", ".", task["start_in"]],
                          cwd=tree, capture_output=True, text=True, env=bare,
                          timeout=900)
    text = (done.stdout or "") + (done.stderr or "")
    return {"ok": done.returncode == 0 and _NEVER_INDEXED not in text,
            "answered": [line.strip() for line in text.splitlines()
                         if line.strip().startswith(("CO-CHANGE", "BLAST RADIUS",
                                                     "ALREADY EXISTS"))]}


def prepare(run_id: str, *, force: bool = False) -> dict:
    """Everything that must be true before an agent is spent, or nothing is written.

    Order matters: the checkout is built, then `exp14.leaks` is run against it, and the
    prompt is only written if it comes back empty. A trial that cannot be shown to be
    isolated does not get to happen.
    """
    item = find(run_id)
    task = task_for(item["task_id"])
    home = home_of(run_id)

    # **One agent per checkout, and `prepare` is where that is enforced.**
    # run_22's first attempt finished without a cost reading, so it was re-prepared and
    # re-run -- while the first agent was *still working*. It finished four minutes
    # later and wrote its edits into the freshly rebuilt checkout, so the second agent
    # was handed a tree in which the task was already done. Caught from file mtimes
    # (prepare 13:49:53, edits 13:54-13:56) rather than from anything going wrong, which
    # is the point: nothing failed, and the second trial would have been reported as a
    # measurement of an agent that had most of its work done for it.
    #
    # A prepared run that has not been collected is presumed live. Re-preparing it
    # requires saying so.
    prepared = os.path.isfile(os.path.join(home, "state.json"))
    collected = os.path.isfile(os.path.join(ROOT, "trials", f"{run_id}.json"))
    if prepared and not collected and not force:
        return {"run_id": run_id,
                "error": "already prepared and not yet collected -- an agent may still "
                         "be working in this checkout; stop it first, then pass force"}

    shutil.rmtree(home, ignore_errors=True)
    os.makedirs(home, exist_ok=True)

    tree = run.checkout_for(task, home, name="repo")
    if tree is None:
        return {"run_id": run_id, "error": "checkout failed"}
    found = run.leaks(task, tree)
    if found:
        shutil.rmtree(home, ignore_errors=True)
        return {"run_id": run_id, "error": "leaks", "leaks": found}

    cli = run.cli_shim(home, REAL_CLI if os.path.exists(REAL_CLI) else PATH_CLI)
    indexed = None
    if item["condition"] == "with_tool":
        # Indexed before the agent sees it, so the trial measures the tool and not the
        # wait. The `without_tool` arm is not indexed: it is not told the tool exists.
        ok, note = run.index_for_agent(tree, cli, home)
        indexed = {"ok": ok, "note": note}
        if not ok:
            return {"run_id": run_id, "error": "index failed", "indexed": indexed}
        served = _served_the_prepared_index(tree, cli, task)
        indexed["serves_prepared_index"] = served["ok"]
        indexed["answered"] = served["answered"]
        if not served["ok"]:
            return {"run_id": run_id, "error": "the shim does not serve the prepared "
                    "index", "indexed": indexed}
        # That check ran through the shim, so both logs now hold an invocation the
        # agent did not make. An experiment that counts its own setup as behaviour
        # reports the tool as used in every trial.
        open(os.path.join(home, "invocations.log"), "w").close()

    prompt = run.prompt_for(task, tree, item["condition"], cli)
    with open(os.path.join(home, "prompt.txt"), "w", encoding="utf-8") as handle:
        handle.write(prompt)
    state = {"run_id": run_id, "task_id": task["id"], "stratum": item["stratum"],
             "condition": item["condition"], "tree": tree, "home": home, "cli": cli,
             "leaks": [], "indexed": indexed, "prompt_bytes": len(prompt),
             "global_log_offset": len(global_invocations(run_id))}
    with open(os.path.join(home, "state.json"), "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=1)
    return state


def _offset(home: str) -> int:
    path = os.path.join(home, "state.json")
    if not os.path.isfile(path):
        return 0
    with open(path, encoding="utf-8") as handle:
        return int(json.load(handle).get("global_log_offset", 0))


def finish(run_id: str, usage: dict | None = None) -> dict:
    """Read the trial back out of the checkout, not out of anything the agent said."""
    item = find(run_id)
    task = task_for(item["task_id"])
    home = home_of(run_id)
    tree = os.path.join(home, "repo")
    result = run.collect(task, tree)
    trial = {"run_id": run_id, "task_id": task["id"], "stratum": item["stratum"],
             "condition": item["condition"],
             "changed": result["changed"], "scored": result["scored"],
             "invocations": run.invocations(home),
             "global_invocations": global_invocations(run_id, _offset(home))}
    if usage:
        trial["usage"] = usage
        trial["cost"] = run.cost_from_usage(usage)
    out = os.path.join(ROOT, "trials")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, f"{run_id}.json"), "w", encoding="utf-8") as handle:
        json.dump(trial, handle, indent=1)
    return trial


def trials() -> list[dict]:
    out = os.path.join(ROOT, "trials")
    if not os.path.isdir(out):
        return []
    collected = []
    for name in sorted(os.listdir(out)):
        if name.endswith(".json"):
            with open(os.path.join(out, name), encoding="utf-8") as handle:
                collected.append(json.load(handle))
    return collected


# -------------------------------------------------------------------------- analysis

def analyse(collected: list[dict] | None = None) -> dict:
    collected = collected if collected is not None else trials()
    result = run.report(collected)
    used, silent = [], []
    for trial in collected:
        if trial["condition"] != "with_tool":
            continue
        (used if trial.get("invocations") else silent).append(trial["run_id"])
    strays = [t["run_id"] for t in collected
              if t["condition"] == "without_tool" and t.get("global_invocations")]
    result["validity"] = {"with_tool_used": used, "with_tool_silent": silent,
                          "without_tool_reached_the_binary": strays}
    return result


def _print(result: dict) -> None:
    def one(name: str, slice_: dict) -> None:
        print(f"\n{name}: {slice_['pairs']} pairs")
        for key, value in sorted(slice_.items()):
            if key == "pairs":
                continue
            print(f"  {key:<28} {value}")
    one("pooled (this sample, not the world)", result["pooled"])
    for stratum, slice_ in sorted(result["by_stratum"].items()):
        one(stratum, slice_)
    if result.get("dropped_unpaired"):
        print(f"\ndropped unpaired: {result['dropped_unpaired']}")
    validity = result["validity"]
    print(f"\nwith_tool arms that ran the tool:  {len(validity['with_tool_used'])}")
    print(f"with_tool arms that never did:    {validity['with_tool_silent']}")
    print(f"without_tool arms that found it:  "
          f"{validity['without_tool_reached_the_binary']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    for name in ("prepare", "finish"):
        one = sub.add_parser(name)
        one.add_argument("run_id")
        if name == "prepare":
            one.add_argument("--force", action="store_true",
                             help="rebuild a checkout that is prepared but not yet "
                                  "collected. Only after the agent working in it has "
                                  "been stopped.")
        if name == "finish":
            one.add_argument("--usage", default=None,
                             help="JSON from the runner: subagent_tokens, tool_uses, "
                                  "duration_ms")
    sub.add_parser("report")
    sub.add_parser("arm")
    sub.add_parser("disarm")
    check = sub.add_parser("contaminated")
    check.add_argument("run_id")
    check.add_argument("--transcript", default=None)
    args = parser.parse_args(argv)

    if args.command == "plan":
        os.makedirs(ROOT, exist_ok=True)
        runs = plan()
        with open(_plan_path(), "w", encoding="utf-8") as handle:
            json.dump(runs, handle, indent=1)
        drawn = sample()
        print(f"seed {SEED}: {len(drawn)} tasks, {len(runs)} runs -> {_plan_path()}")
        for stratum in sorted(ALLOCATION):
            picked = [t["id"] for t in drawn if t["stratum"] == stratum]
            print(f"  {stratum:<16} {len(picked):>2}  {' '.join(picked)}")
        return 0
    if args.command == "arm":
        print(arm_global_log())
        print(arm_git_guard())
        print("\n".join(arm_fetch_guards()))
        return 0
    if args.command == "disarm":
        disarm_global_log()
        disarm_git_guard()
        disarm_fetch_guards()
        print(PATH_CLI)
        return 0
    if args.command == "contaminated":
        print(json.dumps(contaminated(args.run_id, args.transcript), indent=1))
        return 0
    if args.command == "prepare":
        print(json.dumps(prepare(args.run_id, force=args.force), indent=1))
        return 0
    if args.command == "finish":
        usage = json.loads(args.usage) if args.usage else None
        print(json.dumps(finish(args.run_id, usage), indent=1))
        return 0
    _print(analyse())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
