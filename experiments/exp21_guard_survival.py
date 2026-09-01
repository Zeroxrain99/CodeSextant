"""How often does an agent take away a fence that the real developers kept?

E4 is meant to test the half of the first demand that E2 could not reach. E2 measured
"changing A breaks B" -- companion finding -- and came back null. The other half is the
one the demand actually leads with: *立意良善的測試、安全閥、守衛、功能,遺忘後變成災難* --
a guard whose reason nobody remembers, deleted because deleting it is cheaper than
understanding it.

**This module exists to decide whether E4 is worth running, before it is run.** A
longitudinal A/B costs roughly 1.4M tokens per chain; the honest question to ask first
is how often the event it measures happens at all. If an agent removes a kept fence in
one change out of forty, then eight-step chains produce a fraction of an event per arm
and no affordable E4 has the power to separate the arms -- which is a finding, not a
setback, and a much cheaper one.

The estimate is free: E2's forty checkouts are still on disk, each one a real agent's
real change to a real repository, and every one of them has a ground truth sitting next
to it -- the commit the human actually made from the same parent. So for each trial:

    removed_by_agent  explained guards present at the parent and gone from the agent's
                      tree, after the same rename/move/weakening filters `check` ships
    removed_by_real   the same computation against the reference commit
    took_a_kept_fence removed_by_agent minus removed_by_real

The subtraction is what makes it a fair question. A guard the real commit also removed
was *supposed* to go: the feature it fenced was deleted, the limit genuinely changed.
Counting those would score an agent for agreeing with history.

**This reads E2's trees but not E2's endpoint.** The arms are reported separately
because the number is needed per arm to size E4, and that is the one thing to be careful
about: E2's registered endpoints were tokens and the three scored modes. A guard-removal
difference found here is *not* an E2 result -- E2 could not have been stopped early or
extended on it, and this is a power calculation on already-finished trials, not a
hypothesis test. It is reported as an event rate, with no p-value and no claim.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine  # noqa: E402
from codesextant import guards as guards_module  # noqa: E402
from experiments import corpus  # noqa: E402
from experiments import exp14_prevention_run as run  # noqa: E402
from experiments import exp19_e2 as e2  # noqa: E402


def _key(guard) -> tuple:
    return (guard.kind, guard.name)


def removals(before: dict[str, str], after: dict[str, str]) -> list[dict]:
    """Explained fences in `before` that are gone or loosened in `after`.

    The same pairing and the same filters `engine._removed_guards` ships, and for the same measured
    reasons (exp20, 1,382 commits): only guards carrying a stated reason, a rename or a
    move is not a removal, and a `test` whose body was edited is not a weakening. They
    are reimplemented here against text rather than against a worktree because both
    sides of this comparison are historical trees, and one of them -- the reference
    commit -- has no checkout anywhere.

    `after` maps the same relative paths; a path missing from it means the file was
    deleted, which is a real removal rather than a reason to skip.
    """
    landed_keys, landed_rules, landed_reasons = set(), set(), set()
    for rel, text in after.items():
        for guard in guards_module.extract(rel, text):
            if guard.kind in engine._NAMED:
                landed_keys.add(_key(guard))
            landed_rules.add((guard.kind, guard.rule))
            if guard.reason:
                landed_reasons.add((guard.kind, guard.reason))

    found = []
    for rel, previous in before.items():
        was = guards_module.extract(rel, previous)
        now = guards_module.extract(rel, after.get(rel, ""))
        survivors: dict = {}
        for guard in now:
            survivors.setdefault(_key(guard), []).append(guard)
        leftover = []
        for guard in was:
            same = [g for g in survivors.get(_key(guard), []) if g.rule == guard.rule]
            if same:
                survivors[_key(guard)].remove(same[0])
            else:
                leftover.append(guard)
        for guard in leftover:
            if not guard.reason:
                continue
            replacement = survivors.get(_key(guard)) or []
            if replacement:
                replacement.pop(0)
                if guard.kind not in engine._WEAKENABLE:
                    continue
                change = "weakened"
            else:
                if ((guard.kind in engine._NAMED
                     and _key(guard) in landed_keys)
                        or (guard.kind, guard.rule) in landed_rules
                        or (guard.kind, guard.reason) in landed_reasons):
                    continue
                change = "removed"
            found.append({"change": change, "kind": guard.kind,
                          "name": guard.name or "", "path": rel,
                          "rule": guard.rule, "reason": guard.reason,
                          "reason_source": guard.reason_source})
    return found


# ------------------------------------------------------------------ reading a tree

def _show(mirror: str, ref: str, path: str) -> str | None:
    done = subprocess.run(["git", "-C", mirror, "show", f"{ref}:{path}"],
                          capture_output=True, text=True,
                          env={**os.environ, "E2_GIT_ALLOW": "1"})
    return done.stdout if done.returncode == 0 else None


def _changed_by(mirror: str, sha: str) -> list[str]:
    done = subprocess.run(
        ["git", "-C", mirror, "diff", "--name-only", "-M", f"{sha}^", sha],
        capture_output=True, text=True)
    return [p for p in done.stdout.split() if p.endswith(".py")]


def _read_tree(root: str, paths: list[str]) -> dict[str, str]:
    out = {}
    for rel in paths:
        absolute = os.path.join(root, rel)
        if os.path.isfile(absolute):
            with open(absolute, encoding="utf-8", errors="replace") as handle:
                out[rel] = handle.read()
        else:
            out[rel] = ""            # the agent deleted it
    return out


def one(trial: dict) -> dict:
    """One E2 trial, re-read for fences rather than for companions."""
    task = e2.task_for(trial["task_id"])
    mirror = run._full_mirror(task["repo"])
    tree = os.path.join(e2.home_of(trial["run_id"]), "repo")

    agent_paths = [p for p in trial["changed"] if p.endswith(".py")]
    real_paths = _changed_by(mirror, task["sha"])

    def before(paths):
        out = {}
        for rel in paths:
            text = _show(mirror, task["parent"], rel)
            if text is not None:
                out[rel] = text
        return out

    agent_removed = removals(before(agent_paths), _read_tree(tree, agent_paths))
    real_before = before(real_paths)
    real_after = {rel: (_show(mirror, task["sha"], rel) or "") for rel in real_before}
    real_removed = removals(real_before, real_after)

    agreed = {(e["kind"], e["name"], e["path"]) for e in real_removed}
    kept_fences = [e for e in agent_removed
                   if (e["kind"], e["name"], e["path"]) not in agreed]
    return {"run_id": trial["run_id"], "task_id": trial["task_id"],
            "condition": trial["condition"], "stratum": trial["stratum"],
            "repo": task["repo"], "py_files_changed": len(agent_paths),
            "agent_removed": len(agent_removed), "real_removed": len(real_removed),
            "took_a_kept_fence": kept_fences}


def sweep() -> list[dict]:
    return [one(trial) for trial in e2.trials()]


def summarise(rows: list[dict]) -> dict:
    out: dict = {"trials": len(rows), "by_condition": {}}
    for condition in ("with_tool", "without_tool"):
        side = [r for r in rows if r["condition"] == condition]
        events = [r for r in side if r["took_a_kept_fence"]]
        out["by_condition"][condition] = {
            "trials": len(side),
            "trials_that_took_a_kept_fence": len(events),
            "fences_taken": sum(len(r["took_a_kept_fence"]) for r in side),
            "rate_per_change": round(len(events) / len(side), 4) if side else None,
            "run_ids": [r["run_id"] for r in events],
        }
    out["examples"] = [
        {"run_id": r["run_id"], "condition": r["condition"], "repo": r["repo"],
         **fence}
        for r in rows for fence in r["took_a_kept_fence"]]
    return out


def main(argv: list[str] | None = None) -> int:
    rows = sweep()
    result = summarise(rows)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ------------------------------------------------- how often would the mode interrupt

def interruptions(repo: str, limit: int = 300) -> dict:
    """What `check`'s fourth mode would have said, over real commits, by kind.

    exp20 asked whether the mode was worth building and answered from an identity of
    `(kind, name, rule)`. **The shipped engine keys on `(kind, name)`**, and that is not
    the same instrument: a `raise`'s rule *is* its message, so rewording one reads as a
    weakening, and an `assert`'s name is the empty string, so every assert in a file
    shares one key and the comparison is between whichever two happened to be last.

    Neither shows up in a unit test -- both fixtures have one assert and one raise. It
    showed up on the first real change measured: E2's run_02 raised alembic's Python
    floor from 2.6 to 2.7, *tightening* the fence, and the mode called it weakened.

    So this counts what the shipped filters would report, per kind, over real history.
    A kind that fires often and is right rarely is what gets a mode switched off.
    """
    mirror = run._full_mirror(repo) if repo in dict(corpus.PREVENTION) else \
        corpus.ensure(repo, dict(corpus.EXTERNAL)[repo])
    done = subprocess.run(
        ["git", "-C", mirror, "log", "-n", str(limit), "--format=%H", "HEAD"],
        capture_output=True, text=True)
    tally: dict = {}
    commits = 0
    for sha in done.stdout.split():
        paths = _changed_by(mirror, sha)
        if not paths:
            continue
        commits += 1
        before, after = {}, {}
        for rel in paths:
            text = _show(mirror, f"{sha}^", rel)
            if text is None:
                continue
            before[rel] = text
            after[rel] = _show(mirror, sha, rel) or ""
        for entry in removals(before, after):
            key = f"{entry['change']}/{entry['kind']}"
            tally[key] = tally.get(key, 0) + 1
    return {"repo": repo, "commits": commits, "reports": tally,
            "total": sum(tally.values())}
