# Audit: what E2 actually measured, and why its null was decided in advance

E2 concluded "no measurable difference" and the project was paused on that. **The
conclusion about the tool is right and the reason recorded for it was wrong.** This is
the post-mortem, written from the E2 checkouts rather than from memory, and every number
below is reproducible with `experiments/exp21_guard_survival.py` and the trial JSONs.

The short version: **E2 tested whether a tool that names 8% of the answer changes an
agent that already finds 67% of it.** That question has one possible answer, and no
sample size would have changed it.

---

## 1. The tool was silent where the agents failed

Re-running the same `preflight` the `with_tool` arms ran, against each task's ground
truth — the files the human's commit actually touched:

| | |
|---|---|
| companions the agents found | **40 / 60 (67%)** |
| companions `preflight` named | **5 / 60 (8%)** |

And on the eight `with_tool` trials that scored below 1.00, `preflight` named **zero** of
the missed files. Eight for eight. Not "the advice was ignored" — there was no advice.

## 2. The answer set is mostly outside the tool's model

| companion kind | n | share | exists at parent | agent found | preflight named |
|---|---|---|---|---|---|
| CI / build / dependency config | 26 | 43% | 26/26 | 14/26 | **0/26** |
| release note / AUTHORS | 13 | 22% | **4/13** | 6/13 | 2/13 |
| test | 11 | 18% | 11/11 | 10/11 | 1/11 |
| source code | 7 | 12% | 7/7 | **7/7** | 2/7 |
| prose docs | 3 | 5% | 3/3 | 3/3 | 0/3 |

Three things follow, and each of them caps the result independently.

**43% of the answer is configuration and CI wiring, and the model has nothing for it.**
`docs/plan.md` P1 already says so — "設定與路由的接線 … 目前的模型完全看不見" — and E2 ran
anyway with a task set that is nearly half that category.

**22% is release notes, and 9 of those 13 files do not exist at the parent commit.** They
are changelog fragments named after an issue number, created by the commit itself. No
index of an existing tree can name a file that is not there. The right output for this
class is a *convention* — "changes like this add a file under `changelog/`" — which is a
directory-level claim the current design never makes.

**Only 30% (code + tests) is in scope for a symbol-and-reference model at all**, and on
source code specifically the agents scored 7/7. Where the tool could speak, there was
nothing left to win.

## 3. A ceiling on top of that

**12 of the 20 tasks were solved perfectly by both arms.** Two more scored zero in both.
Six pairs out of twenty had any room to differ, and they matched exactly.

`preflight`'s co-change section spoke at all in **11 of 20** tasks. In the other nine it
printed "History shows nothing that reliably changes with this file."

## 4. The task set contains problems that are not the problem

The `hidden` stratum is the one the tool exists for. Three of its six tasks are chores,
and they are the three lowest scores in the entire experiment:

```
flask@8285adf5a4   [hidden]  instruction: "update dev dependencies"                  0.25
flask@165af0a090   [hidden]  instruction: "update dev dependencies"                  0.67
alembic@b19ac41f19 [hidden]  "Alembic 1.13 now supports Python 3.8 and above"        0.44
```

The first one tells an agent to start in `src/flask/cli.py`, gives it "update dev
dependencies" as the change, and then scores it on whether it edited
`.github/workflows/zizmor.yaml`. That is not 改 A 壞 B. It is an unanswerable task
wearing a hard one's clothes.

**The stratification selected for it.** `hidden` means "no companion reachable by grep
from the start file", and the commits that satisfy that most reliably are chores —
precisely because a chore's file set has no semantic relationship to the start file.
The stratum meant to isolate the hard-but-answerable case isolated the unanswerable one.

## 5. The methodological failure, stated plainly

**exp1 had already measured co-change recall at 0.08–0.11 on Python. E2's quality
endpoint was recall.** Nobody put those two numbers side by side, and 3.6M tokens were
spent re-deriving one of them: 8% named is exactly what exp1 predicts.

Rule 1 of `docs/plan.md` is "measure the candidate before building it". The rule that was
missing is its twin: **measure the instrument's own ceiling before spending agents on
it.** A tool cannot cause a difference in an outcome it has no information about, and
whether it has that information is a question with zero agent cost.

## 6. Cleaning the design up does not rescue the result

Removing the four chore tasks and re-running the paired bootstrap. **This is a post-hoc
exclusion, which is exactly how a null is turned into a finding, so it is reported as an
exploration and not as a result:**

| | pairs | difference | 95% interval | sign test |
|---|---|---|---|---|
| all 20 (pre-registered) | 20 | −5.4% | [−14,032, +2,561] | 11/20 |
| chores removed (post-hoc) | 16 | −8.0% | [−17,456, +1,405] | 10/16 |

The point estimate improves and the interval still contains zero. **The design flaw did
not hide an effect.** Both things are true at once: the experiment was badly aimed, and
the tool as it stands is too weak for the aim to have mattered.

---

## What this changes

**Not the pause.** What is refuted stays refuted: on Python, on single-file-start tasks,
this tool does not change what a capable agent does.

**The reason.** "We measured it and it does not help" and "we measured a tool with 8%
recall against an answer set that is 70% outside its model" support very different
decisions about whether to come back to it.

**The order of work if anyone does come back.** Not features. The first move is the one
that costs no agents at all:

1. Build a task set that contains the problem — real code changes, chores excluded, and
   the front-end corpus included, since co-change reaches precision 0.81 / recall 0.39 on
   vite against 0.09 recall on Python and no agent experiment has ever touched it.
2. Measure `preflight`'s own recall on that set. **If it is still 8%, the project is
   finished and this is the number that finishes it.**
3. Only if that number moves is an agent A/B worth running, and then it should be
   powered for the effect it expects rather than for the budget that was available.

---

## 7. What the literature says the low recall is

The 8% is not a mystery and it is not new. What this repository implements is **ROSE**
(Zimmermann et al.): pairwise association rules, thresholded at `support >= 3` and
`confidence >= 0.5`, precomputed and stored. Its known failure mode is exactly the one
measured here — **ROSE is reported as able to give an answer only about 25% of the time**,
because a query whose file has no pair clearing both thresholds gets silence. exp1
measured `speaks` at 0.46-0.59, and E2's co-change section spoke in 11 of 20 tasks.

**TARMAQ** (Rolfsnes, Di Alesio, Behjati, Moonen, Binkley — SANER 2016) exists to fix
precisely that. Given a transaction history and a query Q (the files changed so far), it:

1. **filters transactions** to those with the largest intersection with Q — keep `T` where
   `|T ∩ Q| = k`, and `k` is the size of the largest subset of Q that history has ever
   seen change together;
2. **generates rules** `Q' → x` where `Q' ⊆ Q`, `|Q'| = k`, and `x` is a single file;
3. **ranks** the consequents by an interestingness score and returns the ranked list.

The degradation is graceful rather than a threshold: when the full query never co-occurred
it falls back to the largest subset that did, and in the worst case `k = 1`. It is reported
**applicable 100% of the time**, against ROSE's ~25%, and to outperform both ROSE and SVD.

Two follow-ups matter here as well:

* **Aggregating rules beats taking the best one** (Rolfsnes et al., MSR 2016; extended in
  *Empirical Software Engineering* 2018). Several rules recommending the same file are
  more evidence than one strong rule, and aggregating their scores with cumulative-gain
  functions improves accuracy over the single-highest-interestingness convention this
  repository follows.
* **Evolutionary coupling alone is not enough.** Work integrating it with structural
  change relationships (ESEM 2024) reports significant gains in both recall and MAP over
  TARMAQ alone — which is the same conclusion §2 above reaches from the other direction:
  43% of the answer here is configuration wiring that no history-only or reference-only
  model addresses.

**None of this is a claim that fixing it produces a benefit.** It says the instrument is a
decade behind the technique it implements, that the gap has a named remedy, and that the
remedy's effect on *this* corpus is measurable for zero agent cost. That measurement is
step 2 of the list above, and it is the one that decides whether step 3 is ever worth
running.

---

## 8. Why the tool scores below the agent, and four fixes the data refused

> **This section measures the wrong thing, and the correction is §9.** It asks whether
> the tool can name the companion files as well as an agent can find them. That is the
> car being asked to drive itself while the driver walks. Nobody wants that: the driver
> can walk, and the car is for arriving with less fuel. The numbers below are correct and
> the question they answer is not the one this project exists for. Kept as recorded,
> because replacing it would hide that the target moved.

E5 moved `preflight` from naming 4 of E2's 60 companions to 10. Replaying the *actual*
invocations the agents made -- with the symbols they passed, which two earlier passes of
this measurement got wrong -- puts it at **12 of 60 (20%)** against the agents' **40 of 60
(67%)**. This section is the root-cause hunt for that gap, and its result is that none of
the obvious repairs survives its own control.

| companion kind | n | agent | co-change | blast radius | either |
|---|---|---|---|---|---|
| CI / deps config | 26 | 14 | 1 | 1 | 2 |
| release note | 13 | 6 | 3 | 0 | 3 |
| test | 11 | 10 | 3 | 2 | 4 |
| source code | 7 | 7 | 2 | 2 | 3 |
| prose docs | 3 | 3 | 0 | 0 | 0 |
| **total** | **60** | **40** | **9** | **5** | **12** |

**The agent's advantage is spread evenly across every class.** It is not one mechanism
failing; it is a different question being answered.

### One real defect, found on the way

**The reference graph is empty.** Measured in the E2 indexes: alembic, 91 files and 2,614
symbols, **0 reference edges**; flask, 75 files and 1,642 symbols, **8**; pytest, 278 files
and 7,281 symbols, **3**. `index_project` records files and symbols and does not build the
reference graph -- edges appear only when `_ensure_blast_radius` resolves one symbol on
request. So "改 A 壞 B", the flagship claim, is answered from a graph with single-digit
edges, and `blast_radius` reports `dependent_count` of 0 or 1 in nearly every call because
there is nothing there to report.

It is working as designed rather than broken, and the design is why the one symbol with
real fan-out was refused: `Flask` was `declined` because 47 files name it, above an inline
limit of 25. **The limit exists because the graph is not built, and it declines exactly the
high-fan-out case where 改 A 壞 B is a real risk.**

### Four candidate fixes, and what killed each

**1. "The agent reads the issue number out of the instruction."** Eight companions are
issue-numbered changelog fragments; the instruction prints the matching number for **3 of
8**, and in one case prints a *different* number (13448 against a companion named 13420).
Mostly rejected.

**2. "Index the import graph, in both directions."** 11 of the 18 code companions are
reachable by a reference in one direction or the other -- and 10 of those run
*seed → companion*, which is the direction `blast_radius` never reports: when the edit
starts in a test, the thing that must move with it is the module it tests, a dependency
rather than a dependent. That looked decisive. Measured before building: a bidirectional
import graph names **6 of 60 (10%)**, *below* the 20% already achieved, and its
who-imports-me half scores **0 of 60 while listing up to 48 files per query**. Rejected.

**3. "Predict at directory granularity instead of file granularity."** The release-note
class is 22% of the answer and 9 of its 13 files do not exist at the parent, so no
file-level predictor can ever name them -- but their *directory* can be named. Directory
co-change from the seed's directory hits **37 of 60 (62%)**, which is nearly the agent's
67%. Then the matched control: naming simply the five most-changed directories in the
repository, ignoring the seed entirely, hits **36 of 60 (60%)**, and *any* directory in
these repositories covers 59 of 60. **The 62% is the base rate.** Rejected.

**4. "The agent's edge shrinks on repositories too large to grep."** Unaided agent recall
by repository: alembic 162 files 58%, flask 236 files 64%, pytest 650 files **81%**. Recall
rises with size here. Three repositories and heavily confounded by convention regularity,
so this is weak evidence -- but it is evidence against, not for. Not supported.

### What is actually left

**`preflight` asks "what usually moves with this file". The agent asks "what does this
change require".** The second question is strictly more informative and the tool never sees
the input that makes it askable: the instruction. The agent knows a pytest bugfix needs a
changelog entry, that these five workflow files move together, that this test covers that
module -- not by retrieval, by having understood the change and read the repository.

No index converts the first question into the second, which is what four measurements above
say from four directions. That makes the gap architectural rather than a defect, and it
bounds what any amount of retrieval engineering can recover here.

**The consequence for scope, stated as a cost rather than a conclusion:** on this task set
`blast_radius` contributes 5 companions of 60 while its module-dependents tier alone will
list up to 48 files for one query. That is attention spent for almost nothing, and it is
the part of the design that measurement supports least. Whether it pays elsewhere is exp2's
question and not this one's -- but nothing here argues for building more of it.


---

## 9. The correction: this is a car, and the driver can already walk

> CodeSextant 就像是車子,你開著他到目的地,而 LLM 是駕駛。今天駕駛沒有車子也能走到
> 目的地,但有車子會更便利、更快速、更省力。

**That reframes every measurement above, and §8 is the clearest example of getting it
wrong.** "Does the index name the files as well as the agent finds them" is a question
about replacing the driver. The tool is mechanical: it should do the finding, the
tracing and the remembering so the agent spends its budget on deciding. The endpoints
that follow are two, and neither is recall:

1. **Fuel.** Tokens, tool calls and wall clock for the same destination. Less spent
   looking is less context consumed, and less context consumed is a lower chance of the
   session rotting out from under the work.
2. **The instruments.** The things the driver would otherwise miss: this change reaches
   code B, there is a test over there, that guard will block you, this convention fails
   the build.

**E2 measured the first one, and all three of its effort readings point the same way:**

| | with tool | without | difference | 95% interval |
|---|---|---|---|---|
| tokens | 87,758 | 92,810 | **−5.4%** | includes zero |
| tool calls | 47.5 | 49.3 | **−3.5%** | includes zero |
| wall clock | 560 s | 638 s | **−12.2%** | includes zero |

Three measures, one direction, none of them detectable. And the reason is in the task
size rather than in the tool: **E2's median task has two companion files.** A car saves
nothing on a two-hundred-metre walk, and the endpoint this project registered was
measured on twenty of them.

**The model makes a prediction, and E2's own data cannot test it.** If the saving comes
from work the agent no longer has to do, it should grow with how much there is to find:

| task size | pairs | token difference | |
|---|---|---|---|
| ≤ 2 companions | 13 | **−10.1%** | 8 of 13 cheaper |
| ≥ 4 companions | 5 | +0.8% | 2 of 5 cheaper |

The slope runs the wrong way, +1,357 tokens per additional companion. **It is also
worthless as a test**: three of the five large tasks are the chores §4 identified —
"update dev dependencies" twice and a Python-version bump — where "large" means nine
workflow files rather than nine coupled modules, and where the tool has nothing to
contribute by construction. Five pairs, three of them contaminated. Not evidence in
either direction.

**So the honest position on what has been tested.** The effort endpoint is the right one
and it was measured at a scale where the mechanism cannot operate. The instruments
endpoint has never been measured at all: `guards` was invoked 25 times across E2 and
nobody ever asked whether it warned about a fence the change actually met.

**And what stops being worth doing.** Recall against the commit's file set. It compares
the tool to the agent at the agent's own job, on tasks small enough for the agent to do
it by grep, and every conclusion drawn from it above — including the four rejected fixes
— answers a question that was never the point.
