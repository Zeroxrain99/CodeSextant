# Roadmap

This file exists because the work keeps outliving the context that remembers why it
started. It is the same failure the tool treats, so it gets the same treatment: written
down, in one place, with the reason attached to each item.

**Rule for whoever picks this up, including a future session of the same agent: update
the status line in the same commit as the work.** A roadmap that lags the code is worse
than none, because it is believed.

---

## The two demands, verbatim

> **1.** 解決我真實遇到的 AI 編碼問題 — 立意良善的測試、安全閥、守衛、功能，遺忘後變成災難：
> 重造輪子、浪費時間和 token 修復、改 A 壞 B。
>
> **2.** 成為 SOTA。

### What "done" means for each, so it cannot quietly drift

**Demand 1 is done** when someone working in a repository with CodeSextant makes
measurably fewer of those four mistakes than without it. Not "the tool retrieves the
right file" — that is a proxy, and it is all that has ever been measured here. The thing
itself is the **prevention experiment** (Phase E).

**Demand 2 is done** when there is a public, reproducible number comparing CodeSextant
against alternatives on a task set nobody here designed. Today the honest position is:
the *design* is at or past what is published — no tool found derives a multi-kind,
code-linked, relevance-bounded, progressively-disclosed guard index — but "nobody else
built it" is not "it works better", and there is no comparative measurement at all.

**Both converge on the same thing: a benchmark and an A/B.** Every phase before E is
either making the tool reachable, making a claim true, or making the A/B possible.

### The four failure modes, and where each actually stands

| failure | what answers it | status |
|---|---|---|
| 重造輪子 | `check → rebuilt` compares bodies, so a wheel reinvented *and renamed* is caught | **solved in principle.** `preflight` cannot do this at all — before the code exists there is only a name, and on requests its name check found 0 of 18 differently-named duplicates |
| 忘記守衛 / 安全閥 | `check → companions` (history) and `guards` (the fences themselves) | `companions` recall 0.169–0.250, measured. **`guards` now measured too**: 0.306 held out over 360 commits, beating all four controls with every interval excluding zero — and still last on one of the six repositories |
| 改 A 壞 B | `check → callers` + `dependents`, `preflight` blast radius | weakest of the three. Resolved callers 0.094 pooled; the whole of `check` 0.326 held out. Mechanism of the remainder is mapped (exp5); two cheapest repairs measured and refused |
| 浪費 token 修復 | nothing | **never measured.** This is Phase E and nothing else touches it |

---

## Phases, in order, with the reason for the order

Ordering rule inherited from `experiments/README.md` and paid for five times over:
**measure a candidate before building it.** Five candidates have been rejected on
measurement alone in this repository, each saving a build.

---

### Phase A — reach: make it installable at all

Nothing else matters if the work does not reach a machine. Until 0.28.0, PyPI carried
**0.19.2**, which has neither `preflight` nor `check` — every user was installing a
version from before the tool became what its README describes.

| step | done when | status |
|---|---|---|
| A1 · merge the branch to `master` | `master` carries 0.28.0 | **done** — `5d4506b`, 93 commits, CI green on 14 jobs |
| A2 · a release workflow that needs no local checkout | one click in the Actions tab cuts the release | **done** — `.github/workflows/release.yml`. Run **Actions → Release → Run workflow** with `v0.28.0`: it creates the tag, builds, checks the tag matches `pyproject`, proves the wheel installs and runs, and publishes the Release with the wheel attached |
| A3 · cut `v0.28.0` on GitHub | the Release exists with the wheel on it | **needs one click from the owner.** This session cannot do it: `git push origin refs/tags/v0.28.0` returns **HTTP 403 on git-receive-pack** — the credential here is scoped to branch refs — and the GitHub MCP server exposes no release- or tag-creating tool |
| A4 · PyPI | — | **deferred by the owner.** GitHub Releases are the distribution channel for now, which is why the workflow attaches the wheel |

**A3 is one click.** Everything else in Phase A is finished, and the click is no longer
followed by any manual step.

---

### Phase B — make the guard index true, not just built

`guards` leads with a machine-derived rule because `exp8` measured that the author's
reason is absent for four guards in five and the introducing commit does not carry it
either. That much is evidence. **Whether the fences it names are the ones that would
have blocked you is not measured at all** — it is pinned by unit tests and it reads
correctly on this repository, which is a unit test and two anecdotes.

| step | what | status |
|---|---|---|
| B1 · **exp9: score `guards` against the corpus** | Hold out a file the commit had to touch *that holds a fence*, apply the rest, and ask `guards` what the change is about to meet. Four matched controls, each given as many guards as `guards` printed and ordered the way a real answer would be | **done.** 360 cases. Held out **0.306** at 4.9 fences named, beating all four controls with every interval excluding zero |
| B2 · fix the sampling bias first | exp4/exp6 hold out `sorted(files)`' first `.py`, and path sorting puts `tests/` after `src/`: a guard file is in 0.54–0.57 of commits but is the held-out one in only 0.06–0.12. **The existing numbers said almost nothing about the guard case** | **done.** exp9 selects a fence-bearing file deliberately, preferring a test, and reports how many commits that discards |
| B3 · act on what B1 says | ranking, the six-shown cap, the kinds admitted — all chosen by argument, not evidence | **done for the tiers, open for the cap.** The per-file rejection is now measured rather than asserted (+0.189). Two tiers refused by argument were measured and both reversed: history (+0.111 offline union → built) and imports (+0.072 as a predictor → built), together **+0.100 held out** over 0.28.0. The six-shown cap is still argued from exp1 rather than scored here, and is the last knob in this section with no number under it |
| B4 · confirm on the held-out repositories | jinja, httpie, rich, untouched during B1–B3 | **done, and it found a real loss.** On jinja `guards` started below every control (−0.133 vs co-change, −0.250 vs frequency). Reported in `experiments/README.md` and `docs/guard-index.md` rather than buried |
| B5 · the jinja loss | two candidates measured *as predictors* before either was built: `+filemention` (a file names a changed symbol but no fence in it does) and `+importer` (a file imports a module you changed and holds fences — the tier removed by eye) | **done.** Decision rule fixed and committed before the numbers. `+importer` passed and shipped; `+filemention` was real (+0.033) and still refused, because `+importer` beat it by +0.039 and the ceiling of running both was +0.014. jinja went 0.067 → 0.150: two of its three losses are gone, and `frequency@k` still beats it by 0.167 |
| B6 · the six-shown cap | the only knob in this section still set by argument — exp1's finding that a predictor naming twenty files stops being read | **open.** `mean n` is now 4.9 and every control is scored at whatever `guards` printed, so the harness to vary it already exists |

**B before C** because B1 tells us *which guard kinds appear in the misses*, which is
the only non-guesswork way to order C. It did: the fences `guards` finds are 88–116 tests
against 2–13 `raise` and a single threshold, and on jinja — where it loses — it found no
test at all. C is about the kinds a Python reader cannot see, and that is now an ordering
with evidence under it rather than a list of plausible ideas.

---

### Phase C — cover the guards that actually block people

`exp8` counted 16–34 guards per thousand lines **reading Python only** and said the
number was a floor. **exp10 measured the floor, and it reshaped this phase rather than
confirming it.** Counted across seven repositories: 4–15 CI checks and 0–14 lint rules
against 182–964 Python guards — two orders of magnitude — and **zero pre-commit
configurations and zero `.sql` files anywhere in the corpus**.

More important, exp10 found that its own statistic is the wrong one for a required
check. "How often does a commit touch the workflow file" answers how often somebody
*moves* that fence. A required check blocks every push whether or not you have opened
it, so the rate that matters is 1.0. A CI check is not a needle in hundreds; it is a
fixed handful that applies to everything. **It does not want ranking, relevance or
progressive disclosure. It wants stating.**

| step | what | status |
|---|---|---|
| C1 · CI workflow rules | required checks, matrix entries, timeouts, `fail-fast` | **reshaped by exp10.** Not a ranked tier in `guards` — a short always-on statement, because the population is 4–15 and universally applicable |
| C2 · lint and type configuration | ruff `select`/`ignore`, per-file ignores, mypy strictness, and the language floor beside the target version | same shape as C1, same reason. This repository's own `target-version = py311` against a 3.10 floor was exactly this class and went unnoticed until CI said so — a line stating both would have shown it, and no ranking would have |
| C3 · pre-commit hooks | `.pre-commit-config.yaml` | **blocked on a corpus.** Zero instances in all seven repositories. Building an extractor whose score is undefined is what `guards` was doing before exp9 |
| C4 · schema, migration and database constraints | `NOT NULL`, `UNIQUE`, migration ordering | **blocked on a corpus.** Zero `.sql` files anywhere here. These live in applications; the corpus is seven libraries |

C1 and C2 still have to earn their place by moving a number, but it is not exp9's
number — retrieval recall is meaningless for a fence that always applies. The claim they
make is "this is what will run against your push", and the honest test of it is whether
it is *correct and complete*, not whether it was *retrieved*.

---

### Phase D — the two failure modes still visibly short

| step | what | what is already known |
|---|---|---|
| D1 · reuse before the code exists | `preflight`'s reuse check compares spellings, so an equivalent under an unrelated name never had a chance. The same-shape family rule bought +0.077 to +0.167 held out | the ceiling is unknown: nobody has measured how many real duplications are reachable from a name and an intention alone |
| D2 · the caller gap, what is left of it | symbol-level ceiling is 0.153/0.439/0.350 and resolution reaches 0.094; module-level `dependents` took `check` to 0.326 held out | exp5 mapped the mechanism: **no single cause dominates**, and the two cheapest repairs (removing the resolution budget; printing the cost gate's leads) were measured and bought nothing |
| D3 · score symbol-level co-change | mined, shipped, asserted, **never scored** | an exp1 variant, cheap. It either justifies the per-symbol diff mining or retires it. This is the last shipped claim in the tool with no number at all |

---

### Phase E — prevention: the only thing that answers "有用嗎"

Everything above measures **retrieval**: given a query, is the right thing returned.
Not one number here says an author who saw the answer made a better change, or spent
fewer tokens fixing it. That is demand 1 stated exactly, and it is untouched.

| step | what | done when |
|---|---|---|
| E1 · a task set nobody here wrote | real commits from repositories outside the derivation set, or an existing public suite. The tasks must include the four failure modes, not just "make the test pass" | the task set is fixed and published before any run |
| E2 · the A/B | same model, same tasks, tool available against not | paired per task, with an interval |
| E3 · measure what was asked for | task success, **tokens spent**, whether a guard was tripped, whether something was rebuilt that existed, whether an unrelated thing broke | each of the four failure modes has its own rate, not one blended score |

**This is the expensive one and the only one that closes demand 1.** Everything before
it exists to make it worth running.

---

### Phase F — language coverage

Resolution is Python-only and so is `guards`. Twelve other languages are indexed and
degrade to name matching; `exp2` says nothing about any of them. `ts_bridge` already
exists for TypeScript, which makes it the cheapest second language.

### Phase G — the comparison that makes "SOTA" a fact

| step | what |
|---|---|
| G1 · publish the benchmark | the E1 task set and the harness, so a number can be reproduced rather than believed |
| G2 · run the alternatives on it | local-first code-intelligence tools report ~10× token reduction and 2.1× fewer tool calls on their own benchmarks; none of those benchmarks is shared, so the comparison has to be built |
| G3 · report where it loses | the results section that only lists wins is an advertisement — `experiments/README.md` already says this and the comparison must hold to it |

---

## What is deliberately not on this list

- **A hand-maintained guard registry.** ADRs and feature-flag inventories both rot for
  the reason the registry was wanted. Everything here is derived from the repository.
- **Merging `dependents` into `callers`, or `guards` into `check`.** Separate claims stay
  separately labelled; that invariant is in `HANDOFF.md` layer 3 with its reason.
- **Any number quoted from the derivation set when a held-out number exists.** +0.778 on
  the repository that suggested a rule against +0.08 held out is why the held-out set
  exists.
