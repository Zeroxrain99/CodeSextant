# Experiments

CodeSextant makes three claims. Until this directory existed, all three were supported
by unit tests, microbenchmarks and anecdotes — which establish that the code does what
it says, and say nothing at all about whether what it says is worth having.

These are controlled experiments with control groups, on repositories nobody involved
in building CodeSextant has written. They are reproducible: every number below comes
from a command in this directory, and the corpus is cloned on first run.

```bash
python -m experiments.exp1_cochange       # does history predict the companion change?
python -m experiments.exp2_blast_radius   # is a resolved reference better than grep?
python -m experiments.exp3_reuse          # is the equivalent definition surfaced?
python -m experiments.exp4_check          # hold a file out of a commit: does check name it?
python -m experiments.exp5_caller_gap     # where does the caller section lose?
python -m experiments.exp6_caller_candidates   # which repair for it is worth building?
python -m experiments.exp7_preflight_dependents # does preflight want the same repair?
python -m experiments.exp8_guard_inventory    # can the guards be found, and do they say why?
python -m experiments.exp9_guards             # does `guards` name the fence that would have blocked you?
python -m experiments.exp10_invisible_guards  # how much blocks people outside what a Python reader sees?
```

The corpus is cloned on first run into `~/.cache/codesextant-corpus`, or wherever
`CODESEXTANT_CORPUS` points. Clones are blobless — history and trees are all the mining
reads, though exp2 checks trees out and so fetches the blobs it needs. Pass `--repo` to
score a repository of your own; that is the only way to find out whether these numbers
hold for the code you actually work on, and they may not.

## Why not CodeSextant's own history

It is the obvious corpus and it is disqualified twice over. It has 67 commits, 32 of
them in the window the miner uses — too few to separate a result from noise. And most
of it was written while building the thing being measured, with recent commits shaped
by preflight telling the author what to change. Scoring the tool on those measures its
own advice coming back.

It is still reported, as a contrast, and the contrast is the point: see exp1.

## Corpus

Three long-lived Python projects, chosen before any result was seen. Picking them
afterwards would make every number a selection.

| repo | commits read | why |
|---|---|---|
| psf/requests | 2000 | small surface, long life, many hands |
| pallets/click | 2000 | larger surface, disciplined maintainers |
| tqdm/tqdm | 1814 | many small contributors |

A second set — httpie/cli, pallets/jinja, Textualize/rich — is held out. It exists
because exp3 produced an idea for a change, and a change tested on the data that
suggested it is not tested at all.

## exp1 — does history predict the companion change?

Prequential (rolling origin), the only honest protocol for a predictor scored against
the history it learns from. Commits replay oldest first; **before** commit C enters
the model, every file in C is used as a query and scored against the rest of C.
Nothing about C can reach the model that predicts it.

Counting goes through `cochange.tally` and the query through
`ProjectStore.cochange_rules_for` — the two calls preflight makes — so what is
measured is what ships, not a reimplementation.

Controls: predict nothing; predict the whole directory; predict the globally
most-changed files. The last two are also scored at a **matched budget** — given
exactly as many guesses as co-change made, are co-change's guesses better ones —
because a control that buys recall with twenty predictions has not won anything.

## exp2 — is a resolved reference better than grep?

Each sampled commit is one question. The repository is checked out at the commit's
**parent**, so the tool sees what an author would see before making the change. The
symbols the commit actually modified are recovered from the diff's hunk ranges. The
resolved references, the name matches, and the union preflight actually returns are
each scored against the other files that commit changed.

Precision is the comparison that means something. Recall must be read carefully: a
caller is not obliged to change when a callee does, so nothing can reach 1.0, and a
predictor naming half the repository leads on recall while being useless.

**What this actually measures, stated plainly.** The blast radius claims to answer *who
breaks*. The ground truth available here is *who changed in the same commit*, which is
a proxy and not a tight one: a caller need not change, and files change together for
reasons that have nothing to do with calls. Measuring breakage directly would mean
running each commit's test suite against the parent tree with the change applied, which
this corpus cannot support. So exp2 scores the blast radius as a predictor of
co-change, and a perfect blast radius would not score 1.0 on it.

## exp3 — is the equivalent definition surfaced?

Ground truth is `find_duplicates`' structural groups: units of the same shape, which
is code someone wrote twice. One member is treated as the thing about to be written;
the reuse check is asked, with only its name and file, whether anything resembling it
exists.

**Stated bias, up front rather than in a footnote.** Structural duplicates in a mature
codebase are mostly *deliberate*. requests' `md5_utf8` / `sha256_utf8` / `sha512_utf8`
and click's `get_binary_stdin` / `stdout` / `stderr` are families someone meant to
write; tqdm's discord, telegram and slack classes implement one interface. None is a
wheel reinvented by forgetting. So this measures **retrieval**, not prevention.
Prevention has no ground truth in this corpus, and inventing one would be worse than
saying so.

Results are split into same-named and differently-named pairs, because grep already
solves the first for free and can never solve the second.

## exp5 — where does the caller section lose?

exp4 left the caller section weak and the reason unmeasured. A ratio says three files in
four are lost; it does not say where, and every possible repair depends on where.
Ranking candidates differently cannot help if jedi is being pointed at the wrong
definition, and pointing it better cannot help if the name only ever appears inside a
docstring.

So this classifies rather than scores. For every case where the held-out file names a
symbol the change touched and `check` does not name the file, exactly one reason is
recorded: the symbol was past the resolution budget, the cost gate declined it,
the regex locator pinned a different same-named definition than the one the diff
touched, the name occurs only inside strings, jedi resolved nothing, or jedi resolved to
a genuinely different definition. The categories are ordered and the first that applies
wins, because a symbol never resolved at all cannot also have been misresolved.

It measures **two ceilings on the same cases**, which is the point that mattered most:
how often the held-out file names a definition the diff *wrote into* — what the caller
section resolves — and how often it names any definition *living in* a changed file,
which is what exp4's `callers_ceiling` counted.

## exp6 — which repair is worth building?

An hour per candidate is what leaves candidates unmeasured, so this splits the expensive
half from the cheap half. One pass over the corpus writes, per case, a table of features
for every file any caller-side signal could reach: how many changed symbols it mentions,
how many changed modules it imports, whether resolution confirmed it, what co-change
thinks of it, whether it is a test. Scoring a predictor is then a pure function over that
table, so a new idea costs a second instead of an hour, and `--score` re-runs the whole
comparison on a dump written days earlier.

Every candidate is scored at the length `check` already prints. A predictor naming twenty
files reaches three times the recall and stops being read — exp1's finding, and the
ground exp4 rejected a caller candidate on.

## exp7 — does preflight want the same repair?

`check` gained a module-level tier in 0.26.0 on measured grounds. preflight had not, and
the result does not transfer for free: `check` reads a diff and knows every symbol that
moved, while preflight is asked before the edit, about one file and one name, and the
name may not exist yet.

exp2 asked this first and answered half of it. As a *tier*, module dependents are more
precise than the leads tier they would replace; as a *whole answer*, exp2 could not
separate swapping from adding from doing nothing. exp2 also says plainly that its ground
truth is loose — it scores against "files that changed in the same commit".

So exp7 asks the same question on exp4's protocol, which was built for exactly this
reason. One file of a real commit is held out as the thing the author forgot. The
repository is checked out at the parent and **nothing is applied**, because that is where
preflight runs. preflight is then asked about the files the commit did change, with the
symbols it changed in them, and scored on whether it names the held-out file. Three whole
answers are compared, because a ship decision is between whole answers: what preflight
prints today, the same with the leads tier swapped for module dependents, and the same
with both.

Sampling requires **two** Python files in a commit rather than exp4's one: one is held
out and the rest are what preflight gets asked about, so a commit touching a single
module contains no query.

## What these experiments changed

Two defects and one improvement came out of running them, which is the reason to have
run them:

1. **The reuse check scored below plain grep on tqdm.** Every structural duplicate
   there is called `__init__`, of which the repository has 38 — all scoring 1.0, of
   which an arbitrary 8 were shown. Fixed by making the cutoff and the list length one
   number: either every match fits and you see all of them, or the name is a
   convention and you are told that instead.
2. **Ties were ordered by descending line number**, which is deterministic and
   meaningless. Now ordered by proximity to the file being edited.
3. **The two-shared-words rule missed every differently-named duplicate in requests.**
   `md5_utf8` and `sha256_utf8` share one word and are the same code twice; so do
   `list_domains` and `list_paths`. What separates them from a shared verb
   (`release_version` against `release`) is not how many words are shared but whether
   the names have the same *shape*. The rule now admits equal-length names differing
   in exactly one position, scored at the default threshold so it is the first thing
   to go when anyone raises the bar — and was validated on the held-out set, where it
   had not been fitted.
4. **The reference locator accepted only the first definition of a name in a file.**
   A file defining `send` on two classes had every reference to the second scored as
   pointing somewhere else, so the blast radius came back empty while claiming to have
   looked. exp5 puts it at 17.5% of caller misses; the fix gains 3 cases in 176 and
   loses none, which is a correctness fix and not a measurable recall gain.
5. **check answered "who breaks" only at symbol level.** exp5 showed the reachable
   signal is one level up — a file that imports a changed module reaches 0.217 against
   0.094 for resolved callers — so `check` grew a DEPENDENTS tier, marked `?` and kept
   apart from the resolved callers. exp6 measured it before it was built, and again
   afterwards through the shipped code path.
6. **preflight then wanted the same tier, added rather than swapped in.** exp7 asked
   the held-out-file question of preflight and separated three whole answers that exp2
   could not: adding module dependents beside the leads is +0.036 [+0.018, +0.065] held
   out, while replacing the leads with them is +0.004 and not established. The leads
   stay, and the third tier is the only one of the three that says anything about a
   symbol that does not exist yet.

---

# Results

Run on 2026-08-31. exp1 to exp3 on CodeSextant 0.24.0, exp4 on 0.25.0, exp5 and
exp6 on 0.26.0, exp7 on 0.27.0. Reproduce with the commands at the top.

## exp1 — co-change against three baselines

Micro-averaged over every (commit, file) query. `speaks` is how often the predictor
said anything at all; `useful` is how often what it said contained a file that really
did change. F1 confidence intervals are bootstrapped over commits, not queries,
because queries inside one commit are not independent.

At a matched budget both baselines are ranked by how often each candidate has changed.
An earlier version of this table truncated the directory baseline alphabetically; that
tripled the apparent advantage of co-change and was a straw man. The numbers below are
against the stronger control.

| repo | predictor | prec | recall | F1 | F1 95% CI | speaks | useful | mean n |
|---|---|---|---|---|---|---|---|---|
| requests | **cochange** | **0.536** | 0.093 | 0.158 | [0.121, 0.204] | 0.465 | **0.651** | 0.8 |
| requests | same_dir | 0.110 | 0.318 | 0.164 | [0.130, 0.204] | 0.987 | 0.626 | 13.8 |
| requests | frequency | 0.081 | 0.339 | 0.131 | [0.101, 0.163] | 1.000 | 0.672 | 20.0 |
| requests | same_dir@k | 0.389 | 0.060 | 0.104 | [0.082, 0.134] | 0.464 | 0.460 | 0.7 |
| requests | frequency@k | 0.114 | 0.020 | 0.034 | [0.024, 0.046] | 0.465 | 0.168 | 0.8 |
| click | **cochange** | **0.548** | 0.105 | **0.177** | [0.153, 0.203] | 0.515 | 0.687 | 1.0 |
| click | same_dir | 0.077 | 0.326 | 0.125 | [0.101, 0.150] | 0.988 | 0.553 | 20.9 |
| click | frequency | 0.071 | 0.285 | 0.113 | [0.102, 0.123] | 1.000 | 0.741 | 20.0 |
| click | same_dir@k | 0.345 | 0.066 | 0.111 | [0.092, 0.131] | 0.515 | 0.429 | 1.0 |
| click | frequency@k | 0.240 | 0.046 | 0.078 | [0.065, 0.093] | 0.515 | 0.403 | 1.0 |
| tqdm | **cochange** | **0.492** | 0.082 | **0.141** | [0.118, 0.168] | 0.481 | 0.610 | 0.7 |
| tqdm | same_dir | 0.073 | 0.396 | 0.123 | [0.099, 0.148] | 0.992 | 0.577 | 21.7 |
| tqdm | frequency | 0.076 | 0.379 | 0.126 | [0.110, 0.141] | 1.000 | 0.734 | 20.0 |
| tqdm | same_dir@k | 0.231 | 0.039 | 0.066 | [0.052, 0.084] | 0.481 | 0.275 | 0.7 |
| tqdm | frequency@k | 0.150 | 0.025 | 0.043 | [0.034, 0.055] | 0.481 | 0.199 | 0.7 |

**At a matched budget co-change is 1.4× to 2.1× more precise than the strongest
control**, and its F1 interval clears `same_dir@k` on click and tqdm. On requests the
two intervals overlap: there, against a directory baseline ranked by change frequency,
this experiment does not establish an advantage. Two of three is the honest score.

**Against unbounded baselines it is a draw on F1, and that draw is the interesting
part.** `same_dir` and `frequency` reach 3–4× the recall by naming 14–22 files on
every single query. As a number that is a fair trade; as a reminder shown before an
edit it is not a reminder, and an agent told twenty files every time learns to skip the
section. co-change speaks on about half of queries and is right on roughly two thirds
of those, against 0.43–0.46 for the matched directory baseline.

**Recall is low and no framing fixes that.** Co-change catches about one companion file
in ten. It is a high-precision hint, not a safety net, and the documentation should not
imply otherwise.

### The contrast: CodeSextant's own history

30 commits evaluated — far too few to conclude anything, and included because it is
the case that goes the other way.

| predictor | prec | recall | F1 | F1 95% CI | mean n |
|---|---|---|---|---|---|
| cochange | 0.575 | 0.107 | 0.180 | [0.077, 0.268] | 1.4 |
| **frequency** | 0.221 | **0.583** | **0.321** | [0.233, 0.396] | 20.0 |

On a 67-commit single-author project, "predict the twenty most-changed files" wins
outright, because a handful of files really are in almost every commit. Co-change earns
its place on repositories where change is distributed across many hands and many
areas — which is the case it was built for, but it is worth saying plainly that on a
young project it is beaten by a heuristic you can write in one line.

## exp2 — resolved references against grep

100 commits sampled per repository, at most two symbols in each of at most three files.
`resolved` and `leads_only` are the two tiers preflight prints; `name_match` is their
union, which is what grep gives you undifferentiated. Precision intervals are
bootstrapped over commits.

| repo | predictor | prec | prec 95% CI | recall | mean n |
|---|---|---|---|---|---|
| requests | **resolved** | **0.314** | [0.247, 0.391] | 0.125 | 0.9 |
| requests | leads_only | 0.099 | [0.069, 0.125] | 0.135 | 3.1 |
| requests | name_match | 0.147 | [0.121, 0.177] | 0.260 | 4.0 |
| click | **resolved** | **0.154** | [0.108, 0.212] | 0.056 | 1.3 |
| click | leads_only | 0.069 | [0.049, 0.093] | 0.098 | 4.8 |
| click | name_match | 0.086 | [0.065, 0.113] | 0.154 | 6.1 |
| tqdm | resolved | 0.095 | [0.069, 0.125] | 0.093 | 2.3 |
| tqdm | leads_only | 0.069 | [0.045, 0.100] | 0.115 | 3.9 |
| tqdm | name_match | 0.079 | [0.059, 0.106] | 0.209 | 6.3 |
| jinja | resolved | 0.108 | [0.074, 0.158] | 0.045 | 1.9 |
| jinja | **leads_only** | **0.180** | [0.131, 0.232] | 0.088 | 2.2 |
| jinja | name_match | 0.147 | [0.106, 0.195] | 0.133 | 4.1 |

**Two of four, not four of four.** On requests and click the resolved tier is 2.2× to
3.2× more precise than the leads tier, with intervals that do not overlap. On tqdm the
two intervals overlap and no difference is established. On jinja the sign reverses —
the leads tier is the more precise one — though there the intervals overlap slightly
and the reversal is suggested rather than shown.

Against plain grep the picture is thinner still: the resolved tier's interval clears
`name_match` cleanly only on requests, marginally on click, and not at all on tqdm or
jinja.

**What that does and does not mean.** It is not a refutation, because the ground truth
is co-change and resolution optimises for callers — the two come apart, and this
experiment cannot tell a wrong caller from a caller who had no reason to edit. But it
does mean the blast radius must not be sold as a reliable predictor of what else you
have to change, and the documentation should not imply that it is.

It also supports a decision made earlier for a different reason. Leads were originally
reported only when nothing resolved; they are now reported beside the confirmed callers
because CodeSextant's own lazily-bound modules were invisible to resolution. jinja is a
second, independent instance of the same thing: a template engine full of runtime
dispatch, where the half jedi cannot confirm is the more useful half. A tool that
showed only the confirmed tier would be at its worst exactly where indirection is
heaviest.

## exp3 — reuse retrieval, and what the same-shape rule bought

`off` / `on` is recall over differently-named structural duplicates with the same-shape
family rule disabled and enabled. An exact-name grep scores 0.000 on that column by
construction, and 1.000 on same-named pairs.

**Held out** — cloned and left unexamined until the rule was written:

| repo | diff-name n | off | on | delta | listable |
|---|---|---|---|---|---|
| httpie/cli | 12 | 0.333 | 0.500 | **+0.167** | — |
| pallets/jinja | 20 | 0.400 | 0.500 | **+0.100** | 1.000 |
| Textualize/rich | 26 | 0.462 | 0.538 | **+0.077** | — |

**Derivation set** — the rule was written after looking at these, so these numbers are
not evidence for it:

| repo | diff-name n | off | on | delta | listable |
|---|---|---|---|---|---|
| requests | 18 | 0.000 | 0.778 | +0.778 | 1.000 |
| click | 44 | 0.705 | 0.705 | +0.000 | 1.000 |
| tqdm | 0 | — | — | — | 1.000 |
| CodeSextant | 40 | 0.300 | 0.300 | +0.000 | 1.000 |

+0.778 on the repository that suggested the rule, against +0.08 to +0.17 where it had
not been fitted. That gap is the entire reason the held-out set exists, and the smaller
numbers are the ones to believe.

`listable` is 1.000 everywhere: every same-named duplicate whose name was rare enough
to list at all was found. The remaining same-name gap is the tool declining to offer an
arbitrary sample of a name the project uses as a convention, which the metric scores as
a miss and which is the right behaviour anyway.

## exp4 — hold a file out of a real commit and see whether check names it

120 commits sampled per repository, 351 scored cases. One file of each commit is
hidden, the rest is applied to a worktree at the parent, and `check` runs on the
result. The hidden file is the answer.

| repo | predictor | recall | recall 95% CI | speaks | mean n |
|---|---|---|---|---|---|
| requests | **check** | **0.220** | [0.153, 0.305] | 0.619 | 1.5 |
| requests | companions | 0.169 | [0.110, 0.246] | 0.542 | 1.1 |
| requests | callers | 0.068 | [0.025, 0.119] | 0.169 | 0.5 |
| requests | callers_named@2 | 0.271 | [0.195, 0.356] | 0.356 | 5.3 |
| requests | callers_named@k | 0.161 | [0.102, 0.229] | 0.314 | 0.9 |
| requests | callers_ceiling | 0.305 | [0.220, 0.390] | 0.356 | 8.2 |
| requests | same_dir@k | 0.068 | [0.025, 0.119] | 0.619 | 1.5 |
| requests | frequency@k | 0.025 | [0.000, 0.059] | 0.619 | 1.5 |
| click | **check** | **0.284** | [0.198, 0.371] | 0.707 | 1.8 |
| click | companions | 0.250 | [0.172, 0.328] | 0.638 | 1.4 |
| click | callers | 0.086 | [0.043, 0.138] | 0.250 | 0.6 |
| click | callers_named@2 | 0.681 | [0.595, 0.759] | 0.793 | 21.1 |
| click | callers_named@k | 0.259 | [0.181, 0.336] | 0.655 | 1.8 |
| click | callers_ceiling | 0.759 | [0.681, 0.836] | 0.802 | 34.7 |
| click | same_dir@k | 0.129 | [0.078, 0.198] | 0.707 | 1.8 |
| click | frequency@k | 0.086 | [0.043, 0.138] | 0.707 | 1.8 |
| jinja | **check** | **0.274** | [0.197, 0.359] | 0.521 | 1.5 |
| jinja | companions | 0.239 | [0.162, 0.316] | 0.487 | 0.9 |
| jinja | callers | 0.068 | [0.026, 0.120] | 0.205 | 0.6 |
| jinja | callers_named@2 | 0.350 | [0.265, 0.436] | 0.564 | 12.0 |
| jinja | callers_named@k | 0.111 | [0.060, 0.171] | 0.470 | 1.4 |
| jinja | callers_ceiling | 0.419 | [0.333, 0.513] | 0.667 | 19.5 |
| jinja | same_dir@k | 0.094 | [0.043, 0.145] | 0.521 | 1.5 |
| jinja | frequency@k | 0.094 | [0.043, 0.145] | 0.521 | 1.5 |

### Paired differences, which are the statistic that applies

Every predictor sees the same cases, so comparing their separate intervals
understates the evidence — two intervals can overlap while every case moves the same
way. Bootstrapped per case:

| difference | requests | click | jinja |
|---|---|---|---|
| check − companions | **+0.051** [+0.017, +0.093] | **+0.034** [+0.009, +0.069] | **+0.034** [+0.009, +0.068] |
| check − same_dir@k | **+0.153** [+0.076, +0.229] | **+0.155** [+0.069, +0.241] | **+0.179** [+0.094, +0.265] |
| callers_named@k − check | −0.059 [−0.127, +0.008] | −0.026 [−0.121, +0.060] | **−0.162** [−0.248, −0.085] |

**check beats the strongest matched control in all three repositories**, by 0.15 to
0.18, every interval excluding zero, while naming 1.5 to 1.8 files per case.

**Reading the diff adds to mining history, and the paired test is what shows it.** The
lift over co-change alone is +0.03 to +0.05 and every interval excludes zero. Compared
as two separate intervals it looked like noise; it is not.

### A candidate measured and rejected

The caller section is the weak one — recall 0.068 to 0.086 — against a `callers_ceiling`
of 0.305 to 0.759. **That ceiling is looser than it reads, and exp5 says by how much.**
It counts a held-out file as reachable if it names *any* definition living in a file the
commit touched; the caller section only ever resolves the definitions the diff wrote
into. Restricted to those, the ceiling is 0.153, 0.439 and 0.350. Roughly half of the
gap described here was a difference between two questions rather than a resolver falling
short of one. Two mechanical explanations were
checked and are both wrong. requests' `src/` layout does not degrade jedi (the same
symbol resolves identically with and without an explicit `src_root`), and the cost gate
is not swallowing the work either (of 116 changed symbols in click, 89.7% resolve and
7.8% are declined).

So a name-level signal was proposed on the intuition that a file naming *several*
changed symbols is more likely to be using them than one naming a single symbol.
Measured before it was built:

`callers_named@2` recalls far more than the resolved tier — 0.681 against 0.086 on
click — but names 5 to 21 files per case, which is the "twenty files every query"
problem exp1 criticised the unbounded baselines for. Truncated to what `check` already
prints, it is *worse* on all three and significantly worse on jinja.

**Nothing was built on it.** The gap between resolution and naming is real and still
open; ranking by name count is not the way across it.

## exp5 — where the caller section loses

60 commits sampled per repository, on the derivation set.

**Two ceilings, on the same cases.** `check`'s caller section resolves the definitions
the diff wrote into. exp4's `callers_ceiling` counted a held-out file as reachable if it
named *any* definition living in a changed file. They are not the same question:

| repo | cases | names a definition the diff touched | names any definition in a changed file | `check`'s callers find it |
|---|---|---|---|---|
| requests | 59 | **0.153** | 0.288 | 0.051 |
| click | 57 | **0.439** | 0.719 | 0.053 |
| tqdm | 60 | **0.350** | 0.583 | 0.150 |

The right-hand column reproduces exp4's ceiling (0.305 and 0.759 there, on a larger
sample). **About half the gap exp4 described was a difference between two questions**,
not a resolver falling short of one. The headroom above the caller section is roughly
0.10 to 0.39, not 0.24 to 0.71.

**Why the rest is lost.** 40 misses pooled across the three repositories:

| reason | n | share |
|---|---|---|
| the cost gate declined the symbol | 13 | 0.325 |
| the symbol was past the resolution budget | 8 | 0.200 |
| jedi resolved to a genuinely different definition | 7 | 0.175 |
| the locator pinned the wrong same-named definition | 7 | 0.175 |
| jedi resolved nothing at any occurrence | 5 | 0.125 |

Two of these correct a number in exp4. The cost gate declines **7.8% of symbols** and
causes **32.5% of misses** — different denominators, and the per-symbol figure hid it,
because the symbols it declines are the widely-named ones that a held-out file is most
likely to mention. And no single mechanism dominates: there was no one bug to fix.

## exp6 — which repair is worth building

60 commits per repository, 351 cases, all six repositories. `check` here is the union
of rebuilt, companions and callers, as in exp4. Every candidate is cut to the length
`check` already prints.

| repo | check | callers | importers | importers@k | dependents (shipped) | check + dependents |
|---|---|---|---|---|---|---|
| requests | 0.271 | 0.051 | 0.186 | 0.169 | 0.085 | **0.356** |
| click | 0.263 | 0.070 | 0.193 | 0.140 | 0.070 | **0.333** |
| tqdm | 0.450 | 0.183 | 0.333 | 0.267 | 0.050 | **0.500** |
| jinja | 0.237 | 0.068 | 0.169 | 0.119 | 0.034 | **0.271** |
| httpie | 0.140 | 0.105 | 0.228 | 0.175 | 0.088 | **0.228** |
| rich | 0.458 | 0.085 | 0.186 | 0.102 | 0.017 | **0.475** |

`dependents` is low on its own by construction: it only ever names files no other
section reached, so it is a gap-filler and the union is the number that means anything.

**Pooled, paired over the same cases.** Each repository alone carries fewer than sixty
cases, enough to separate a large effect and not a small one.

| | derivation (176) | held out (175) | all six (351) |
|---|---|---|---|
| `check` recall | 0.330 | 0.280 | 0.305 |
| `check + dependents` recall | 0.398 | 0.326 | 0.362 |
| paired difference | **+0.068** [+0.034, +0.108] | **+0.046** [+0.017, +0.080] | **+0.057** [+0.034, +0.083] |
| files named per run | 1.8 → 2.5 | 2.3 → 2.8 | 2.1 → 2.7 |

`importers − callers` is **+0.136, +0.140, +0.183** on the derivation set and **+0.102,
+0.123, +0.102** held out — every interval excluding zero, six repositories out of six.
That is the finding: **the reachable caller-side signal is at module level, not at
changed-symbol level.**

The held-out numbers were produced by the shipped code path — the cheap import scanner,
the cap of two, the cutoff at twenty, the skipping of files another section already named
— not by the prototype that suggested it. They match the prototype to three decimals.

### Five candidates measured and rejected

Nothing was built on any of these, which is the reason to measure first.

- **Removing the resolution budget.** `beyond_budget` is 20% of misses, so raising
  `CODESEXTANT_CHECK_MAX_SYMBOLS` looks like the obvious lever. Resolving *every*
  changed symbol instead of the first ten buys +0.017 pooled on the derivation set and
  +0.006 held out, neither established. The cases it would reach fail for other reasons
  as well. A diagnostic share is not a repair's value.
- **Test files that name a changed symbol** — the third of the handoff's untried ideas.
  0.031 pooled against 0.094 for the callers it would replace, naming 2.9 files a case:
  **−0.063** [−0.094, −0.034]. Worse and longer.
- **Name-level signal combined with co-change confidence** — the first of them. 0.094
  pooled, exactly level with the resolved callers, at 0.4 files a case: **+0.000**
  [−0.034, +0.034]. It finds nothing the two do not find separately.
- **Ranking dependents by anything cleverer than import count.** Ranked by symbol
  mentions, by co-change confidence, or by imports alone, the pooled recall is 0.162,
  0.160 and 0.162. The tiebreaker buys nothing, so the plumbing to carry it into
  `check` was not built.
- **Printing leads for the symbols the cost gate declined.** This was the largest
  remaining mechanism — 32.5% of caller misses — and the sweep has already run, so the
  leads are free. Measured on top of what 0.26.0 now ships:

  | | derivation (176) | held out (175) | all six (351) |
  |---|---|---|---|
  | `ships` | 0.398 | 0.326 | 0.362 |
  | `+ declined leads @2` | 0.409 | 0.326 | 0.368 |
  | paired difference | +0.011 [+0.000, +0.028] | **+0.000** [+0.000, +0.000] | +0.006 [+0.000, +0.014] |
  | narrowed to files that also import a changed module | — | — | **+0.000 exactly** |

  Two cases in 351, none of them held out, for 0.2 to 0.5 more files named every run.
  The gate declines a symbol precisely when many files name it, so its leads are the
  noisiest ones there are — and the import-narrowed version adds *nothing at all*,
  because the dependents tier already reaches those files. **The second instance of the
  same lesson: a mechanism's share of the failures is not a repair's value.** The
  budget explained 20% of misses and repaid nothing; the cost gate explains 32.5% and
  repays nothing.

### The locator fix, reported honestly

exp5 attributes 17.5% of misses to the reference locator taking the first `def` of a
name in a file and rejecting jedi answers landing on any other. That is a defect with a
reproduction — `tests/test_codemap.py::test_find_references_finds_the_second_definition_of_a_name`
fails without the fix, returning an empty blast radius while claiming to have looked.

Its effect on retrieval, measured paired on the same 176 cases before and after: **3
cases gained, 0 lost, +0.017 [+0.000, +0.040], not established.** It is justified as a
correctness fix, not as a recall improvement, and the difference between those two
claims is the kind this directory exists to keep straight.

## exp7 — preflight, asked the held-out-file question

150 commits sampled per repository, 525 scored cases, all six repositories. `now` is
what preflight prints today (resolved callers plus the leads tier as the token budget
leaves it); `swap` replaces the leads with module dependents; `both` adds them beside;
`shipped` is what the code now actually returns, which differs from `both` only in
passing over files the symbol-level tiers already named.

| | derivation (247) | held out (278) | all six (525) |
|---|---|---|---|
| blast radius, `now` | 0.344 | 0.183 | 0.259 |
| blast radius, `shipped` | 0.405 | 0.230 | 0.312 |
| paired difference | **+0.061** [+0.032, +0.093] | **+0.047** [+0.025, +0.072] | **+0.053** [+0.034, +0.074] |
| whole answer, `now` | 0.506 | 0.385 | 0.442 |
| whole answer, `shipped` | 0.538 | 0.421 | 0.476 |
| paired difference | **+0.032** [+0.012, +0.057] | **+0.036** [+0.018, +0.061] | **+0.034** [+0.019, +0.051] |
| files named, whole answer | 4.3 → 5.3 | 5.3 → 6.2 | 4.8 → 5.7 |

**Add, do not swap, and the corpus is clear about which.** Replacing the leads tier is
+0.004 held out and −0.010 pooled, neither established; adding beside it is established
on both halves of the corpus. As a tier on its own, `dependents@2` beats `leads@3` by
**+0.072** [+0.025, +0.119] held out at the same length — but the leads still earn their
place in the union, which is what a ship decision is about, and jinja is on record as the
repository where the unconfirmed symbol-level tier is the useful one.

The `shipped` row was produced by the code that runs, not by the prototype: it reproduces
`both` to within a thousandth on both halves.

**One caveat, stated rather than buried.** The whole-answer rows model the two blast-radius
tiers at the lengths preflight really prints, but the run used a large token budget, so
co-change was never trimmed by it. The blast-radius rows carry no such assumption and point
the same way, which is why the conclusion does not rest on the whole-answer rows alone.

**Cost.** +2.3 ms on a 10 ms warm preflight, one byte-level pass over the project's Python
files with the same early rejection as `name_sweep`.

**Where it matters most is the case the other two tiers cannot reach at all.** Ask preflight
about a function you are about to add and both symbol-level tiers are empty by construction
— nothing to resolve, nothing to name — while the file's importers are there to be read.

## exp8 — the guard inventory, and the design it stopped

Full write-up in [`docs/guard-index.md`](../docs/guard-index.md). Two numbers decide the
shape of a guard registry and both are cheap, so both were taken before anything was
designed.

**Guards are dense.** 16 to 34 per thousand lines, 182 to 935 per repository, of which
72–89% are tests. A flat registry of that many entries is a second codebase, so
progressive disclosure is the only shape that fits.

**The reason is usually not written down.** `raise` and `assert` guards carry their
message and are 94–100% self-documenting. Everything else is not: tests are 3%
documented in jinja and 7% in httpie; thresholds and environment switches — the literal
safety valves — sit at or near zero almost everywhere, this repository included, where
88% of 78 environment switches say nothing about why they exist.

**And the commit does not rescue them.** Sampling 250 undocumented guards per repository
and searching the whole commit message, body included, for an explanatory clause: 0.00 to
0.04 in the five large repositories, 0.10 here. The reason is not in history either.

That result killed the obvious design before it was built — an index whose middle layer
is prose would be empty for exactly the guards that block people. The design that
replaces it leads with the machine-derivable *rule* and treats prose as a bonus.

### A sampling bias this uncovered in exp4 and exp6

Both hold out `sorted(files)`' first `.py` entry, and path sorting puts `tests/` after
`src/` and most package directories. A guard file is present in 0.54–0.57 of sampled
commits but is the held-out one in only 0.06–0.12 of them. Asked how often `check` names
a held-out *guard*, the answer is 0.476 on 21 derivation cases and 0.182 on 11 held-out
cases — opposite directions, both far too small to read.

**So the numbers in this directory say very little about the guard case specifically.**
Any experiment on it has to hold out a guard file deliberately rather than take whatever
sorting hands it.

## exp9 — does the guard index name the fence that would have blocked you?

`guards` shipped in 0.28.0 on the strength of exp8, which measured what a guard index
could *contain*. It never measured whether the fences it names are the ones that would
have stopped the change. Until this experiment that section was a design with unit tests
behind it.

**The sampler is the experiment's first result.** exp4 and exp6 hold out
`sorted(files)`' first `.py` entry and almost never land on a guard file, so nothing else
in this directory can answer the question. Here the held-out file is chosen *because* it
holds a fence, preferring a test — "the test I forgot" is the canonical form of the
failure and tests are 72–89% of all guards. 60 cases per repository, 360 in all.

Every control gets exactly as many guards as `guards` printed, ordered by the thing that
would order a real answer, because truncating a baseline alphabetically is how this
directory once turned a real 1.4× into a claimed 5.9×.

| | requests | click | tqdm | **jinja** | **httpie** | **rich** | pooled |
|---|---|---|---|---|---|---|---|
| `guards` | 0.517 | 0.450 | 0.483 | 0.150 | 0.283 | 0.483 | **0.394** |
| `guards_symbols` (0.28.0) | 0.333 | 0.317 | 0.417 | 0.050 | 0.167 | 0.400 | 0.281 |
| `guards_perfile` (rejected) | 0.117 | 0.083 | 0.350 | 0.167 | 0.117 | 0.067 | 0.150 |
| `cochange@k` | 0.033 | 0.117 | 0.400 | 0.200 | 0.083 | 0.167 | 0.167 |
| `same_dir@k` | 0.200 | 0.050 | 0.250 | 0.250 | 0.100 | 0.150 | 0.167 |
| `frequency@k` | 0.267 | 0.100 | 0.533 | 0.317 | 0.067 | 0.150 | 0.239 |

Held out (jinja, httpie, rich): **0.306**, naming 4.9 fences. Paired against each
control, held-out set only, and it beats all five:

| against | difference | interval | |
|---|---|---|---|
| `guards_perfile` | +0.189 | [+0.111, +0.261] | real |
| `cochange@k` | +0.156 | [+0.072, +0.239] | real |
| `same_dir@k` | +0.139 | [+0.044, +0.222] | real |
| `frequency@k` | +0.128 | [+0.033, +0.222] | real |
| `guards_symbols` — what 0.28.0 shipped | +0.100 | [+0.056, +0.144] | real |

**The rejection that was made by eye is confirmed by measurement.** `guards_perfile` —
every guard in a file the change reaches, no per-guard check — is the design that was
built and thrown away on one reading. It loses by +0.189 held out.

**And a second rejection made by eye is reversed by it.** The first version of `guards`
reached a fence only through the fence's own text: you edited its file, or it spells a
symbol you changed. Two tiers whose evidence is about the *file* were written down as
refused — history says this file moves with yours, and this file imports what you
changed — on the argument that per-file relevance is what made the rejected design
unreadable. The argument was sound and the conclusion was wrong on both counts:

- Against the two symbol tiers alone, the held-out difference from **reading history
  instead** was +0.056 with an interval crossing zero. On that evidence `guards` was a
  longer way to an answer `check` already gives. Pooling the outcomes offline showed
  why — the signals hit different commits — and the union was worth +0.111 held out.
  That measurement built the history tier, in that order.
- The **import tier** was then measured the same way, as a predictor, before anything
  was built: +0.072 held out, positive on all six repositories, and beating the weakest
  possible relaxation of the per-guard rule (admit a file that names a changed symbol
  when no fence in it does) by +0.039.

Together they take the section from 0.206 to 0.306 held out at a cost of 1.5 fences
printed. Both are ranked below every fence read off its own text and labelled with the
file-level claim they rest on, so a reader can tell a lead from a hit.

**The decision rule was fixed before the numbers existed** — build only if the derivation
difference excludes zero and the held-out difference is positive — and committed
separately, because choosing the criterion after seeing which candidate wins is how a
held-out set stops being one.

### Where it loses, and why

**On jinja `guards` is still last.** It began three real losses down — against co-change,
proximity and frequency — and the two file-level tiers took it from 0.067 to 0.150,
leaving one: `frequency@k` beats it by 0.167 [0.017, 0.317]. jinja is also the repository
where exp2's resolved-reference result reversed, and the two have one cause: both signals
start from symbol names, and a template engine drives its subjects through indirection.

The diagnostic was visible before the repair and remains readable in the table. On jinja
alone, `guards_perfile` (0.167) still edges `guards` (0.150): the fences are reachable at
*file* level and not at *guard* level, because jinja's tests do not spell the names they
exercise. Per-guard evidence is the right rule on five repositories and the wrong one on
this one, and no number here says which case a new repository is before the fact.

`frequency@k` — the project's most-changed files, no index, no analysis — is a strong
baseline and worth keeping in mind: it is beaten by +0.128 held out, but it wins outright
on tqdm and jinja, and it costs nothing to compute.

## exp10 — how much of what blocks people is outside what a Python reader sees?

`exp8` said its own count was a floor: it reads Python, and the kinds it cannot see are
conspicuously the ones that stop a build. Phase C of the roadmap proposed covering four
of them. This measures whether that is worth doing, and the answer reshaped the phase
rather than confirming it.

Counted at HEAD across seven repositories, beside the Python count from the same tree,
with the fraction of sampled commits that *touch a file holding* each kind:

| | Python guards | ci_check | lint_rule | hook | db_constraint |
|---|---|---|---|---|---|
| CodeSextant | 964 · 0.676 | 4 · 0.056 | 11 · 0.268 | 0 | 0 |
| requests | 411 · 0.129 | 13 · 0.075 | 14 · 0.024 | 0 | 0 |
| click | 630 · 0.395 | 10 · 0.072 | 10 · 0.034 | 0 | 0 |
| tqdm | 182 · 0.265 | 8 · 0.065 | 0 | 0 | 0 |
| jinja | 779 · 0.255 | 7 · 0.057 | 10 · 0.007 | 0 | 0 |
| httpie | 505 · 0.297 | 15 · 0.043 | 2 · 0.014 | 0 | 0 |
| rich | 834 · 0.548 | 6 · 0.032 | 2 · 0.090 | 0 | 0 |

*(count · fraction of commits touching a file that holds one)*

**Two of the four kinds do not exist in this corpus at all.** Not one of the seven
repositories has a pre-commit configuration, and not one has a `.sql` file. C3 and C4
were on the roadmap because they block people — which they do — but nothing here can
measure them, and building an extractor whose corpus score is undefined is exactly what
`guards` was doing before exp9. They need an application corpus or they stay speculative,
and that is now written down rather than assumed.

**The other two are tiny.** Four to fifteen CI checks and zero to fourteen lint rules,
against 182 to 964 Python guards. Two orders of magnitude.

### The measurement's own flaw, and what it changes

"Commits touching a file that holds one" is the right statistic for a Python guard — the
fence lives next to the code and you meet it by editing near it. **It is the wrong
statistic for a required check**, which blocks every push whether or not you have ever
opened its workflow file. The number above says how often a commit *moves* a CI fence,
not how often one *stops* somebody. The true rate for the second is 1.0.

That is the finding. A required check is not a needle to retrieve out of hundreds; it is
a fixed set of four to fifteen entries that applies to everything. It does not want
ranking, relevance or progressive disclosure — the machinery `guards` exists to provide.
It wants stating. This repository's own `target-version = py311` against a 3.10 floor was
exactly this class, and it went unnoticed until CI said so; a line naming the lint rule
and the floor would have shown it, and no amount of relevance ranking would have.

So Phase C is not "four more guard kinds behind the same ranked section". It is a small
always-on statement for two kinds, and two kinds waiting for a corpus that contains them.

## What these experiments do not establish

Written down because the gaps are easier to see now than they will be later, and
because a results section that only lists wins is an advertisement.

- **Guards outside Python.** exp9 scores `guards` only on what an `ast` walk can see.
  exp10 counted what it misses and found the population small (4-15 CI checks, 0-14 lint
  rules) and two kinds absent from this corpus entirely — but "small" is not "harmless",
  and nothing here measures how often one of them is what actually blocked somebody.
- **Whether a required check needs retrieving at all.** exp10 argues it does not, from
  a population count and one anecdote about this repository. That is an argument, not a
  measurement, and it is the kind this directory exists to be suspicious of.
- **Which repositories `guards` is wrong for.** It loses to every control on jinja, and
  the reason — tests that never spell the symbol they exercise — is visible only after
  the fact. Nothing here predicts it in advance from a repository.
- **Prevention.** Every experiment here measures retrieval — given a query, is the
  right thing returned. exp4 comes closest, since a held-out file is a thing that was
  genuinely forgotten, but it still does not measure whether an author who saw the
  answer went on to make a better change. That needs agents doing tasks with and
  without the tool, and a task set nobody involved wrote.
- ~~**Why resolution reaches so much less than naming.**~~ **Answered by exp5**, and
  the answer was partly that the gap was mismeasured: about half of it was the ceiling
  counting a looser signal than the caller section resolves. Of what remains, the cost
  gate causes 32.5% of misses, the resolution budget 20%, a locator defect 17.5%, and
  genuine resolver limits — resolving elsewhere or resolving nothing — 30%. No single
  mechanism dominates, which is why the repair that shipped changes the question rather
  than the resolver.
- **Whether the dependents tier helps an author, as opposed to scoring better.** It
  names 0.6 more files per run for +0.046 held-out recall, so roughly one file in
  thirteen that it adds is the one that was forgotten. Whether that ratio reads as a
  useful hint or as noise is a question about people, and belongs to the prevention
  experiment below rather than to this directory.
- **Symbol-level co-change is unmeasured.** preflight mines per-symbol rules from hunk
  headers as well as per-file ones, and exp1 scores only the file-level rules. The
  symbol-level claim — that changing `serve` brings a different companion set than
  changing `daemon.py` — is still an assertion.
- **Thresholds are untuned.** `min_support=3` and `min_confidence=0.5` were chosen
  before any of this existed. A sweep would very likely trade some of that 0.53
  precision for more than 0.09 recall, and the corpus can now say by how much. It has
  to be done against the held-out set, not this one.
- **Python only.** jedi resolves Python; everything else degrades to name matching, so
  exp2's result says nothing about the twelve other languages CodeSextant indexes.
- **Three repositories, all libraries.** No application, no monorepo, no repository
  where a single commit spans several services. `--repo` exists so you can check your
  own rather than trust these.
- **exp2 samples 100 commits per repository** and scores at most two symbols in each of
  at most three files, to keep a full run inside a coffee break. Wider sampling would
  narrow the intervals it does not currently report.
