# Recorded runs

Raw per-trial output, checked in so a number in `docs/roadmap.md` can be traced to the
trials that produced it rather than believed. Roadmap G1 asks for a benchmark somebody
else can reproduce; a result whose inputs live only in a transcript is not one.

## `e2_pilot_trials.json`

The first six E2 trials: three tasks, both arms, on
`experiments/prevention_tasks_stratified.json`. Each record carries what the attempt
changed (read from `git status`, not from the agent's account of itself), the three
scored modes, the cost the runner observed, and — for the `with_tool` arm — every
CodeSextant invocation the shim recorded.

**Six trials is a pilot.** It exists to show the instruments work end to end. Nothing in
it establishes an effect, and `docs/roadmap.md` E2 says what it does and does not say.
