# Recorded runs

**Read [`docs/audit.md`](../../docs/audit.md) before quoting E2.** It re-reads E2's own checkouts and finds that `preflight` named 5 of the 60 companion files those tasks turned on, against 40 the agents found on their own -- so the null was determined before the first agent ran, and the reason recorded at the time was wrong even though the conclusion was not.

Raw per-trial output, checked in so a number in `docs/roadmap.md` can be traced to the
trials that produced it rather than believed. Roadmap G1 asks for a benchmark somebody
else can reproduce; a result whose inputs live only in a transcript is not one.

## `exp1_paired_python_and_frontend.txt`

exp1 over all six repositories — the Python derivation corpus and the front-end corpus
declared in `corpus.FRONTEND` — with the paired difference against every control.

Two things in it are worth not having to re-derive. The paired interval changed a
reading: on express the marginal intervals for co-change and `frequency@k` overlap
(0.292–0.404 against 0.216–0.306) while the paired difference is +0.085 [+0.068,+0.108],
which is the comparison the question was actually about. And the front-end numbers are
higher than the Python ones on every measure, against every control, which is the
opposite of what `docs/plan.md` was written expecting.

## `exp21.json` — E4's event rate, and why E4 was not run

`interruptions` is what `check`'s fourth mode reports over 581 real commits of flask,
alembic and pytest, tallied by kind: **20 findings, 3.4% of commits**. `e2` re-reads E2's
forty checkouts for fences instead of companions, against the commit the human actually
made from the same parent: **569 explained fences within reach of those forty changes,
70% of the changes carrying at least one, and zero of them taken.**

Those two numbers are what `experiments/results/E4.md` costs the longitudinal experiment
against. They also found two defects in shipped code — `(kind, name)` does not identify an
assert or a raise, and the same key was deciding whether a fence had merely moved — which
between them accounted for 8 false findings and 14 masked real ones in the 581 commits.

## `e2_pilot_void_*.json` — void, kept as evidence

**Do not quote a number out of these files.** The nine E2 pilot pairs were run in
checkouts built with `git worktree add`, which shares the parent repository's object
store: the reference commit, the whole future history, and `origin/main` were all
present, and the instruction handed to the agent is the commit message, so
`git log --all --grep=` reached the answer in one step. Grepping the transcripts for
history probes found **8 of 19 trials** touching history. Quality and cost are both
contaminated — an agent that has read the diff needs fewer tokens to find the files.

`e2_pilot_void_trials.json` holds the three pairs that were scored: what the attempt
changed (read from `git status`, not from the agent's account of itself), the three
scored modes, the cost the runner observed, and — for the `with_tool` arm — every
CodeSextant invocation the shim recorded. `e2_pilot_void_usage.json` holds the runner's
cost for all nine pairs; the other six were never scored.

They are checked in because the failure is worth more than the result would have been:
this is what an experiment looks like when the isolation was never asserted.
`exp14_prevention_run.checkout_for` is the fix and `leaks()` is the assertion that was
missing.
