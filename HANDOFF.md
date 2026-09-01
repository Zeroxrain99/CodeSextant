# CodeSextant handoff

Three layers. Read layer 1 to start working, layer 2 before making a claim about what
the tool is worth, layer 3 before changing anything load-bearing.

---

# Layer 1 — three minutes

**What it is.** A local code index that answers three questions an author cannot answer
from the file in front of them: does this already exist, what else has to change with
it, and who breaks. Python, stdlib plus tree-sitter, jedi and watchdog. Nothing leaves
the machine.

**Where things are.**

| | |
|---|---|
| branch | `claude/codesextant-handoff-us93o7`, 34 commits ahead of master. Last commit touching `codesextant/` is `a382e99`; anything after it is this document. |
| version | 0.28.0 (`codesextant/__init__.py` and `pyproject.toml`, bound by a test) |
| tests | `python -m pytest -q` → 739 passed, 6 skipped |
| lint | `python -m ruff check codesextant tests experiments` → **clean**, and a CI job enforces it. The baseline used to be "12 pre-existing", written here and checked by nobody; a number you have to remember is a guard with a memory requirement. |
| experiments | `experiments/README.md` — protocol, results, and what they do not establish |
| **plan** | **`docs/roadmap.md`** — the two demands this serves, what "done" means for each, and the ordered steps. Read it before choosing what to work on, and update its status line in the same commit as the work. |

**The two things that matter most.**

```bash
python -m codesextant preflight . path/to/file.py --symbol name_you_will_add
python -m codesextant check .
```

`preflight` runs before an edit, from a name. `check` runs after, from the diff, and
takes no arguments. They ask the same three questions; `check` has more to work with
and is the one that catches a helper reinvented under a different name. `check` prints
four sections: REBUILT, COMPANIONS, CALLERS, and DEPENDENTS — the last marked `?`,
because importing a module you changed is not calling the thing you changed.
preflight's BLAST RADIUS carries the same three claims in one place: resolved callers,
files that name the symbol (`?`), and files that import the module (`?`). The third is
the only one that can say anything about a symbol you have not written yet.

`guards` is the third command and answers what neither of the other two can: *which
fence* your change is about to meet, what it checks, and what would satisfy it. See
`docs/guard-index.md` for why it leads with a derived rule rather than with prose.

**For agents:** `codesextant mcp` speaks MCP over stdio, ten tools, no new dependency.
`claude mcp add codesextant -- codesextant mcp`.

**Do not** create a pull request unless asked.

---

# Layer 2 — what is true, and how well it is known

Every number below comes from a command in `experiments/`. None of it is an
impression. Where something is unmeasured this says so, because the expensive mistake
in this project has been asserting things that turned out to be artefacts.

## The three problems this exists for

The owner stated them, and they are the standard everything is judged against:

1. rebuilding something that already exists, because it was forgotten;
2. forgetting the test, the allowlist, the safety valve, and blocking yourself;
3. ignoring the blast radius, so changing A breaks B.

## Where each one stands

| problem | tool | status |
|---|---|---|
| 1. rebuilt wheel | `check` → `rebuilt` | **solved in principle.** Compares bodies, so a wheel reinvented *and renamed* is found. `preflight` cannot do this at all: before the code exists there is no body, only a name, and on requests its name-based reuse check finds 0 of 18 differently-named structural duplicates. |
| 2. forgotten companion | `check` → `companions` | **usable.** Recall 0.169–0.250 across three repositories, 2–3× the strongest matched control, intervals excluding zero. A high-precision hint, **not a safety net**. |
| 3. changed A, broke B | `check` → `callers` + `dependents`; `preflight` → blast radius | **improved on both surfaces, still the weakest of the three.** Resolved callers alone recall 0.094 pooled over 351 cases. The module-level tier takes `check` from 0.280 to 0.326 and preflight's whole answer from 0.385 to 0.421, both on three repositories nothing was tuned against, both intervals excluding zero. What is still lost has been mechanism-mapped, and the two largest mechanisms were both measured and found not worth repairing. |

## Headline results

**exp4 (the closest thing to the real question).** Hide one file from a real commit,
apply the rest, ask `check` what the change forgot. 351 cases, three repositories.

- `check` recall 0.220 / 0.284 / 0.274, naming 1.5–1.8 files per case.
- Against the strongest matched control: **+0.153, +0.155, +0.179**, all intervals
  excluding zero. This is the one unambiguous result in the directory.
- Against co-change alone: **+0.051, +0.034, +0.034**, all excluding zero — but only
  when compared as a *paired difference*. As two separate intervals it looks like
  noise. Both predictors score the same cases; that is what makes the paired
  comparison the correct one, and it changed the conclusion.

**exp1 (co-change against baselines, prequential).** Precision 0.49–0.55 at matched
budget, 1.4–2.1× the strongest control, intervals separating on 2 of 3 repositories.
Recall ~0.10. On CodeSextant's own 67-commit history a plain frequency baseline beats
it outright — it earns its place where change is spread across many hands.

**exp2 (resolved references vs grep).** Resolution is 2.2–3.2× more precise than the
name matches beside it on 2 of 4 repositories, no difference on a third, and **reversed
on jinja**, where the tier jedi could not confirm scored higher. Not a refutation — the
ground truth is co-change while resolution optimises for callers — but the blast radius
must not be sold as a reliable predictor of what else has to change.

**exp3 (reuse retrieval).** The same-shape family rule (`md5_utf8` beside
`sha256_utf8`) buys +0.077 to +0.167 on a held-out set. On the repository that
suggested it, +0.778. The gap between those two numbers is why the held-out set exists.

**exp5 (why the caller section is thin).** Two findings, and the first is a correction.
exp4's `callers_ceiling` counted a held-out file as reachable if it named *any*
definition living in a changed file; the caller section only resolves the definitions
the diff wrote into. Restricted to those the ceiling is **0.153 / 0.439 / 0.350**, not
0.305 / 0.759 / 0.419 — **about half the gap the previous handoff described was a
difference between two questions.** Of the misses that remain, none dominates: cost gate
32.5%, resolution budget 20%, a locator defect 17.5%, genuine resolver limits 30%. Note
that the cost gate declines 7.8% of *symbols* and causes a third of the *misses* — the
symbols it declines are the widely-named ones a held-out file is most likely to mention.

**exp6 (which repair was worth building).** The reachable signal is at module level, not
at changed-symbol level. Files importing a changed module beat resolved callers by
**+0.102 to +0.183 in all six repositories**, every interval excluding zero. Shipped as
the DEPENDENTS tier: `check` 0.305 → 0.362 pooled, **+0.046 [+0.017, +0.080] held out**,
for 0.6 more files named per run. Five other candidates were measured and **not** built —
see "what was tried and refuted" below.

**exp7 (whether preflight wanted the same thing).** It did, added rather than swapped in.
525 cases on exp4's held-out-file protocol, checked out at the parent with nothing
applied, which is where preflight runs. The blast radius goes **0.183 → 0.230** held out
(+0.047 [+0.025, +0.072]) and the whole answer **0.385 → 0.421** (+0.036 [+0.018,
+0.061]). *Replacing* the leads tier with it is +0.004 and not established, so the leads
stay — jinja is on record as the repository where the unconfirmed symbol-level tier is
the useful one. The new tier earns most where the other two are empty by construction:
asked about a function not yet written, there is nothing to resolve and nothing to name,
and the file's importers are still there to read.

## What was tried and refuted

Written down so nobody spends the hour again. Every one was measured before anything
was built on it, and nothing was built on any of them.

| candidate | result | pooled |
|---|---|---|
| Removing the resolution budget (resolve every changed symbol, not the first ten) | no gain, though `beyond_budget` is 20% of misses | +0.006 held out, not established |
| Test files that name a changed symbol | worse than what it would replace, and three times longer | −0.063 [−0.094, −0.034] |
| Name-level signal combined with co-change confidence | exactly level; finds nothing the two do not find apart | +0.000 [−0.034, +0.034] |
| Ranking dependents by symbol mentions or co-change instead of import count | identical, so the plumbing was not built | 0.162 / 0.160 / 0.162 |
| Ranking outside files by how many changed symbols they name (exp4) | worse than what ships once cut to a readable length | — |
| Printing leads for the symbols the cost gate declined — 32.5% of caller misses, and the sweep has already run | two cases in 351, none held out, for 0.2–0.5 more files a run; narrowed to importers it adds *nothing at all* | +0.000 held out |
| Swapping preflight's leads tier for module dependents rather than adding it | not established either way; the leads keep their place | +0.004 held out, ns |

The cost-gate row is the one that changed how this project reasons. It was the largest
remaining mechanism and the cheapest possible fix, and it repaid nothing: the gate
declines a symbol precisely when many files name it, which is to say it declines exactly
the symbols whose leads are worthless.

The rule to carry forward: **a mechanism's share of the failures is not the same as a
repair's value.** Two independent confirmations now. The resolution budget explains a
fifth of the caller misses and removing it buys nothing; the cost gate explains a third
and printing its leads buys nothing. In both cases the cases it would reach fail for
other reasons as well. Diagnose to shortlist, then measure the repair — never ship on
the diagnosis.

## The guard index

The second of the three problems, sharpened: *a fence you built yourself blocks you, you
do not remember it, and deleting it looks cheaper than understanding it.* exp8 surveyed
seven repositories before anything was designed and **refused the obvious design**:
guards run 16-34 per thousand lines (182-935 per project), the author's reason is absent
for four in five, and the commit that added them does not carry it either (0.00-0.04).
So `guards` leads with a rule derived from the code and discloses in layers.

**exp9 measured it**, holding out a file the commit had to touch *that holds a fence* --
which no other experiment here can do, because exp4/exp6 hold out `sorted(files)`' first
`.py` and almost never land on one. 360 cases. Held out **0.306** at 4.9 fences named,
beating all four controls with every interval excluding zero: the per-file design it
replaced by +0.189, reading co-change instead by +0.156, proximity by +0.139, the
project's most-changed files by +0.128.

**Two rejections made by eye were reversed by that measurement.** `guards` originally
reached a fence only through the fence's own text. Two tiers resting on a claim about the
*file* -- history says it moves with yours, it imports what you changed -- were written
down as refused on the argument that per-file relevance is what made an earlier version
unreadable. Both were then scored and both were worth building: together **+0.100 held
out**. They rank below every fence read off its own text and say which claim they rest on.

**And one thing it is not, deliberately.** The always-on block above the ranked answer --
CI jobs, pre-commit hooks, lint rules, the language floor -- is not ranked, retrieved or
disclosed progressively. exp10 counted the population at 4-15 CI checks, 8-21 hooks and
0-14 lint rules against 182-964 Python guards, and every one applies to every change, so
relevance has the same answer every time. It has **no corpus score and cannot have one**:
retrieval recall is meaningless for a fence that always applies.

**Where it loses.** On jinja it is last -- beaten by simply reading the most-changed files
by 0.167 -- because a template engine's tests reach their subjects through indirection and
never spell the names. Five repositories say per-guard evidence is right and one says it
is wrong, and nothing predicts which a new repository is.

## What is not established

- **Prevention.** Everything here measures retrieval. Whether an author who saw the
  answer made a better change needs agents doing tasks with and without the tool.
- **Whether DEPENDENTS helps a reader.** It names 0.6 more files per run for +0.046
  recall, so roughly one added file in thirteen is the forgotten one. Whether that
  reads as a hint or as noise is a question about people, and belongs to the prevention
  experiment.
- ~~**Symbol-level co-change.**~~ **Scored by exp11**, and the reason it exists was
  wrong. Asked alone the narrowed question loses to the file-level one; what ships is the
  union, and the union is +0.056 held out over the file tier — 409 more true companions
  for 1,377 more predictions, three in ten of them real. A supplement, not a better
  version, and `mine_symbols` now says so.
- **The always-on gates block.** Correct and complete on seven repositories by unit test,
  with no corpus score -- the position `guards` itself was in before exp9.
- **Whether six fences is the right default.** exp9 priced it: 0.306 at six against 0.394
  at twenty and 0.506 uncapped, so six costs 0.088. Whether a longer section is *read* is
  the other half and no experiment here can test it. `--limit` exists so the reader
  decides.
- **Thresholds.** `min_support=3`, `min_confidence=0.5` predate the corpus that could
  justify them. Tuning must use the held-out repositories, not the derivation set.
- **Thirteen of seventeen languages.** Only Python, TypeScript, JavaScript and TSX
  get import resolution; the rest degrade to name matching and say so. PineScript
  is weaker still -- it is read line by line, because no grammar exists for it.
- **Repository shape.** Three libraries. No application, no monorepo.

---

# Layer 3 — what not to break, and what will bite you

## Invariants, with the reason

Each of these was arrived at expensively. Changing one is allowed; changing one without
knowing why it is there will reintroduce a defect that is silent.

**Name-level edges are never written to the `refs` table.** `all_refs()` feeds PageRank,
and `traverse_call_graph` feeds call hierarchy and impact. Persisting low-confidence
edges from a preflight or check call would change what those three return as a side
effect of an unrelated query. `engine.py` says so at the point it matters.

**The resolution cache is keyed to a digest of the name sweep, not to the edited
file's content hash.** A caller has to name the symbol, so the files naming it are a
complete superset of the possible callers: if none has changed and no new one appeared,
no caller can have appeared. Keying to the definition — the obvious choice — goes stale
the moment a caller is added *somewhere else*, and keeps reporting a confident
"measured absence" that stopped being true. `storage.symbol_references_resolved`.

**`LazyModule` bindings are declared under `if TYPE_CHECKING:`.** The branch never runs,
so the laziness a cold route worker depends on is untouched, but jedi can see the name.
Without it every call through the proxy resolves to nothing and this repository is blind
to its own call edges. `tests/test_lazy_resolution.py` walks each module's AST and fails
if a binding is added without one — the failure mode is otherwise completely silent.

**The common-name cutoff and the candidate list length are one number.** If a name has
more definitions than the cutoff it is a convention and none are listed; otherwise all
of them are. Two numbers create a band where an arbitrary subset gets shown, which is
how the reuse check once scored *below plain grep* on a repository whose duplicates were
all called `__init__`.

**Leads are never merged with confirmed callers.** Separate key, separate rendering,
marked with `?`. Merging them is the confidence inflation the whole tool exists to
avoid. jinja is the independent evidence that the unconfirmed tier can be the more
useful one.

**Dependents are never merged with callers, and never counted as them.** On both
surfaces: `check`'s DEPENDENTS section and preflight's third blast-radius tier. Separate
key, separate heading, marked `?`. A resolved reference says B calls the thing you changed; an
import says B depends on the module it lives in. Merging them would be the same
confidence inflation that leads are kept apart from callers to avoid, and it would make
the caller section's measured recall a number about something else. The tier also skips
any file another section already named — a slot spent repeating a stronger claim is a
slot not spent on a file nothing else reached.

**preflight keeps its leads tier.** Replacing it with module dependents was measured
over 525 cases and came back +0.004 held out, not established — while *adding* the third
tier came back +0.036 and established. Three tiers is the measured answer, not an
oversight, and jinja remains the independent evidence that the unconfirmed symbol-level
tier can be the useful one. The token budget takes the module tier first, because
"imports this module" is the weakest of the three claims.

**The dependents cutoff and the list length are one pair of numbers, chosen together.**
Past 20 importers nothing is listed and a note says why, because two of forty would be an
arbitrary two — the same reasoning as the common-name cutoff above. 20 was measured to
cost no recall at all against no cutoff; 10 costs 0.012. If you raise the shown count,
re-measure the cutoff, because the pair is what makes the section honest rather than
either number alone.

**The import scan is a regex over text with triple-quoted regions blanked, not `ast`.**
`ast.parse` is the exact answer and costs about 2 ms a file, which is 194 ms on a 92-file
repository — 40% of the whole check budget, and worse the larger the project. The cheap
scanner agrees with `ast` on 676 of 682 files across the six corpus repositories, with
**zero false positives**; the six differences are imported *member* names inside a
parenthesised block, never the module. Blanking triple-quoted regions is what buys the
zero: without it, every code sample in a docstring reads as an import. If you change the
pattern, re-run the agreement check before trusting it.

Measured cost of the tier, warm, on this repository: a one-file diff goes 25 ms → 38 ms
(+13 ms, and the answer got *shorter* in tokens, because a section that says something
replaces the long "nothing found" note). A diff wide enough to trip the cutoff costs
+1.2 ms, since `limit` stops the walk at 21 dependents. Worst case is one full pass with
no early stop: 13 ms on a 213-file repository. `check` already walks the tree once per
resolved symbol, so this is one more walk against up to ten.

**A name that does not exist on every platform and Python is guarded, and a test says
so.** `signal.SIGKILL` is absent on Windows; `tomllib` arrived in 3.11 and the floor is
3.10. Both were used unguarded, both were pushed green from Linux on 3.11, and both were
red on six of thirteen CI jobs — one of them in a daemon exception handler, so every
route-worker failure on Windows raised AttributeError instead of the 503 it meant to.
`tests/test_portability.py` walks the AST of the whole repository and fails on any such
name used as though it were universal. Accepted: an `os.name` / `sys.platform` branch, a
`try/except` catching **what would actually be raised**, `getattr(mod, "NAME", default)`,
or the word `posix-only` in the function's docstring when the caller guarantees the
platform. The distinction between what an import raises and what an attribute raises is
load-bearing — the first version of that checker treated `except OSError` as a guard and
therefore passed over the very hole it was written for.

**One Python floor, three places that each believe it.** `requires-python` says what is
supported, the CI matrix says what is proven, and ruff's `target-version` says what the
linter will accept. They disagreed — ruff targeted 3.11 against a 3.10 floor, so the one
tool reading every file on every commit was quietly agreeing to syntax a third of the
matrix cannot run. `test_the_python_floor_is_the_same_number_in_all_three_places` now
joins them.

**Removing a crash is not the same as keeping the behaviour.** The first repair of
`signal.SIGKILL` resolved it to `None`, which stopped the AttributeError and quietly
made `killed_externally` answer False on Windows — a *different definition of the
question* by platform, which only Windows CI could report, one push later. What is
compared is a number: multiprocessing encodes a signal death as the negated signal
number and SIGKILL is 9 wherever POSIX defines it, so the fallback is 9 and the reading
holds with or without the symbol. `test_the_kill_reading_survives_a_platform_without_SIGKILL`
deletes `signal.SIGKILL` and reloads the module, so the Windows path is now exercised
from whichever platform you have.

**`render.py` is the only renderer.** The CLI and the MCP server print the same lines
from the same function, with a test pinning it, so the two surfaces cannot describe a
result differently.

**A test may not assert that designed degradation did not happen.** The daemon refuses
overload with 503 plus Retry-After and answers a busy index with `partial` plus a stated
reason; both are the contract working. `test_real_contention` asserted neither ever
occurred, which is an assertion about how fast the runner is, and it duly failed on two
of thirteen jobs — on two *different* lines, on two different machines. It now asserts
the contract instead: a refusal must be a 503 carrying Retry-After, a partial answer must
name its reason, and the reindex loop must still make real progress. Same teeth, no
dependence on the weather.

**`time.sleep` may advance time, never establish a precondition.** `CONTRIBUTING.md`
carries the rule and `tests/conftest.py::wait_until` is the alternative. An assert that
can fail because the machine is slow is a race wearing a version-difference costume.

**Degradations are announced, never silent.** The daemon falling back in-process, a
project being indexed on first use, a resolution declined for cost — each leaves a note
on the answer. A caller told nothing weighs a cold answer as if it were warm.

## Traps this session actually fell into

- **A rejection made by eye is a hypothesis.** Two tiers of `guards` were refused with
  written reasons that were individually sound -- per-file relevance with no per-guard
  evidence, the defect that made an earlier version unreadable. Measured, both were worth
  building, together +0.100 held out. The argument being correct did not make the
  conclusion correct. Anything refused without a number is a candidate, not a decision.
- **A column that reads zero everywhere is a defect until proven otherwise.** exp10
  reported zero pre-commit hooks in all seven repositories, from a regex missing
  `re.MULTILINE` -- without it `^` anchors to the start of the *string*, so `findall` over
  a file returns at most one match. Five of seven have between 8 and 21, and the roadmap
  briefly carried the wrong conclusion. It was caught sideways: two repositories run a CI
  job *named* `pre-commit`, which cannot be true of a repository with no pre-commit
  configuration.
- **A guard that excludes silently is worse than one that fails.** `.gitignore` carries
  `docs/*` with an allowlist under it. Three documents were written into `docs/` over a
  session and never added to it; every `git add -A` reported success and dropped them.
  `HANDOFF.md` pointed at a roadmap that was not in the repository, and the release
  workflow would have published a generated changelog instead of the notes written for
  it. Nothing failed, which is why it survived. `tests/test_published_docs.py` is the
  fix -- not remembering the allowlist.
- **A test asserting an absolute wall-clock time asserts the speed of the machine.**
  **Three** tests now, on three separate Windows runs, while the behaviour they guard
  was correct every time. The worst runner indexed 73 files in 27 seconds -- against 55
  to 289 files *per second* everywhere else, so between twenty and a hundred times
  slower. Derive the threshold from something the test controls: the length of the wait
  it claims not to have made, an uncontended baseline measured on the same machine, or
  the service's own contract. And state the behavioural half of the claim first, because
  that half holds at any speed.
  **A fourth run, and the same test again.** On Windows it failed with a client-side
  `TimeoutError` rather than the 504 the test allows. `work_coordinator`'s own docstring
  says why that is not a defect: "CPython cannot safely interrupt a thread inside Jedi,
  tree-sitter, SQLite, or another native call. Those calls may return after the request
  deadline." So on a slow enough machine the client's deadline passes before the refusal
  can be delivered, and a test that demands the 504 is demanding an interrupt CPython
  will not perform. The contract that does hold -- and is now what is asserted -- is that
  the service stayed up and kept serving through the overrun. **The limit was written
  down in the module the test exercises, and the test was written as though it were not.**
  Read the known-limits section of what you are testing before deciding what it promises.

  **A fifth, and the second time this test stated the right rule in a comment and broke
  it on the next line.** `assert len(reindex_results) >= 2` sat directly under a
  paragraph explaining that a slow runner reaching the queue-full condition is the
  admission control working. The macOS log gave the mechanism rather than leaving it to
  a guess: `503: the route worker was killed before answering: route worker exited
  without a result (exit=-9)`. **SIGKILL** -- the OS reclaimed the child process that
  runs heavy engine work, and the daemon reported a retryable 503 instead of crashing.
  Two completed rebuilds is a throughput claim; what the test exists to show is that
  rebuild work does not starve the interactive routes, and `active_seen` and
  `simultaneous_seen` already assert exactly that. **Five instances now. When a test
  writes down a rule, check every assertion under it against that rule, not just the one
  that failed.**
  **A sixth, in a different test, and the fix for it was wrong first.**
  `test_interactive_contention` compared p99 under a rebuild against p99 while idle. p99
  over sixty samples is *one observation* -- the slowest -- weighed against p99 over
  fifteen, which is also one: a max against a max, which on a shared runner reports the
  worst scheduling hiccup rather than anything the code did. It failed at 392 ms against
  a 34 ms baseline while a healthy run here sits at a ratio of about **1.05**, so the 8x
  allowance was never being approached and a single sample tripped it. Starvation is
  sustained, so the statistic became the median. **Then the floor swallowed the
  assertion**: 250 ms was derived for a p99 and carried across unchanged, and against a
  healthy median of 23 ms it is eleven times too generous -- a starved run with a 160 ms
  median passed. Caught only because the repaired test was checked against a *starved*
  distribution, not just a healthy one. **When you change the statistic, re-derive every
  constant tuned for the old one**, and verify a repaired test against the failure it is
  supposed to catch.

  **A seventh, and the third distinct assertion inside `test_real_contention`.** The
  control-plane probes in its measurement loop were unprotected, so a `status` call that
  outran its 1.5 s client budget raised straight out of the test -- on a runner whose
  server logged `/status -> 200 (2551 ms)` while a reindex took 9.6 s. Patching one
  assertion at a time had by then cost six CI runs on this file, so the fix is the
  pattern rather than the line: **every timing claim in it is now a multiple of a
  baseline measured on the same machine moments earlier**, the control plane gets the
  same three outcomes the graph routes already had, and total starvation is caught by
  requiring that not every probe overran. Measured to derive it, four local runs: health
  2.1-2.8 ms quiet against 3.9-6.0 ms busy, status 6.4-7.6 against 12.4-17.9 --
  **a healthy ratio near 2.5, not 1**, which is what makes a 4x multiple thin and the
  floor load-bearing on a fast machine. Written down because the previous two fixes each
  carried a constant to a baseline it was not derived for.

  **An eighth, the fourth assertion in this same file, and the lesson is the file
  rather than the line.** `simultaneous_seen` watched for a four-way concurrency
  coincidence inside a fixed five-second window. That window is a machine-speed
  assertion in another hat: the slower the runner, the more each poll costs and the
  fewer looks fit inside it, so the machine that most needs time to line four jobs up
  gets the fewest chances. It now rides the twelve-round measurement loop, which already
  fetches `/health` and already carries `active_jobs` -- no extra calls, and the window
  becomes however long the measurement takes, which *grows* on a slow machine. Verified
  to still have teeth rather than assumed: 8 to 11 rounds of 12 observe it here, never
  12, and the count is printed so a run reporting 1 reads as a warning before it becomes
  a failure. **Four distinct assertions in one file, each on a different runner, none
  repeating.** After the second, the thing to fix is the file's whole approach to time,
  not whichever line fired.

  **A ninth, and this one was my own assertion firing on healthy code.** The fix for
  the seventh replaced absolute deadlines with a ratio to a baseline measured on the
  same machine -- and then tuned the multiple from four runs on *one* machine (health
  1.4-2.5x, status 1.7-2.5x). Windows read **4.4x** and failed, on a run with **zero
  overruns** where every probe answered inside its 1.5 s budget. Not starvation: a false
  positive.
  **A ratio is not automatically machine-independent.** Quiet status is 6-8 ms here and
  50 ms on that runner; busy is 12-18 ms here and 218 ms there -- 7x slower quiet but
  **14x slower busy**, because contention costs proportionally more where there is less
  machine to go round. The ratio scales with the machine too, so tuning one needs the
  population and not one host. What replaced it is scale-free and is what the service
  actually promises: most control-plane probes must be answered inside their own client
  budget, and a starved control plane overruns them. Checked against five distributions
  including the run that had just failed.

- **A commit message claimed a file was updated when the edit had silently failed.**
  `d90b23b` says "HANDOFF.md carries this as the sixth instance". It did not: the edit
  was bundled into the same shell call as a two-minute background test run, its
  assertion failed, and only the pytest tail was read. Both entries above were missing
  until the next failure went looking for them. **Never put an unverified edit in the
  same command as a long-running one and read only the end of the output** -- and when a
  commit message says a file changed, the diff is what decides, not the intent.

  **The third one is the instructive case.** `test_real_contention` failed on a 504 --
  which is the daemon doing exactly what it promises, refusing a call it cannot serve
  inside the deadline. The test already knew this: it says so in a comment, for
  *reindex*, and then asserted raw latency for the interactive routes beside it. A rule
  applied to one half of a test and not the other is the same forgotten fence this whole
  project is about. The claim is now "answered inside the deadline, or refused under the
  contract", which is what the code actually promises.
- **`pkill -f <pattern>` kills your own shell** when your command line contains the
  pattern. Happened three times. Kill by PID from `ps -eo pid,args | awk '/patt[e]rn/'`.
- **The Bash tool caps at 10 minutes.** Long experiments must use `run_in_background`.
- **A weak control inflates everything.** Truncating a baseline alphabetically turned a
  real 1.4–2.1× into a claimed 2.3–5.9×. Rank controls by the same thing you would rank
  a real answer by.
- **n=1 is not a result.** requests alone made exp2 look like a clean win; jinja
  reversed it. Add intervals before reading anything into the first repository.
- **Paired measurements need paired statistics.** Two overlapping intervals can hide a
  difference where every single case moves the same way.
- **A rule derived from a repository cannot be tested on it.** +0.778 on the derivation
  set, +0.08–0.17 held out. Clone the held-out repositories *before* looking.
- **A ceiling is only a ceiling for the question it counts.** exp4's caller ceiling
  counted a looser signal than the caller section resolves, and half of a "gap" that
  drove a whole plan item was the difference between the two. When a number bounds
  something, check that it bounds the thing you are about to try to improve.
  **This happened again, in the session that wrote the sentence above.** exp3's "the
  name check found 0 of 18 differently-named duplicates on requests" was carried into
  exp13 to argue that name matching was the largest unexploited margin in the whole
  directory, and it was published in three files. exp3 scores structural duplicate
  *groups in the current tree* — mostly deliberate families, as its own docstring says —
  while exp13 scores *newly added* functions that repeat something. Same words, different
  population. Measured on the right one, the shipped matcher already reaches 0.915 held
  out and the proposed loosening costs ten times the output for +0.068. A number quoted
  from another experiment is a hypothesis about this one, never a premise.
- **A mechanism's share of the failures is not a repair's value.** The resolution budget
  causes 20% of caller misses and removing it buys nothing measurable, because those
  cases fail for other reasons as well. Diagnose to shortlist, then measure the repair.
- **When one predictor contains another, the paired bootstrap is degenerate.** `check ∪ X`
  can never score below `check`, so the interval's lower bound is 0 by construction and
  "excludes zero" stops being the right test at small n. Pool the cases across
  repositories — 351 separates what 59 cannot — and report the count of cases gained and
  lost beside the interval.
- **The local loop is one of twelve.** Linux on 3.11 here; CI is three operating
  systems times four Pythons, and the other eleven combinations can only report a
  mistake after it is pushed. Both defects found this way were conventions the
  repository already followed correctly in six other places — `os.name == "nt"` branches
  four times, the `tomllib`/`tomli` fallback three times — forgotten in exactly the spot
  the author could not run. That is not a discipline problem and more discipline will
  not fix it; a checker that reads the AST from whichever platform you happen to have
  will. Three rounds of this in one sitting: the original two defects; then a repair
  that removed the crash and changed the behaviour instead; then a *test written to
  catch that* which itself said `signal.SIGKILL` while saving the value, and a checker
  that missed it because the import was aliased. Each round was caught one push later.
  What ended it was making the condition reproducible locally — deleting the name and
  reloading — rather than being more careful.
- **The tool failed to stop its own author rebuilding a wheel, on this repository, in
  this file.** `codesextant stop` was built as a new HTTP endpoint (`/shutdown`), a new
  client method and a new drain confirmation. All three already existed: `/_shutdown`,
  `daemon.stop_running`, and its port-release loop, roughly eighty lines above the edit,
  in the file that was open. The new one was also *worse* -- it called `shutdown()`
  rather than `initiate_shutdown()`, so the daemon kept accepting requests on its way
  out. This is demand #1, committed by the project that exists to prevent it.
  **Both commands were asked and both missed it**, and the reason is one rule:
  `check` has no `rebuilt` signal for "second endpoint beside an existing one" -- it
  counts imports (exp12), and this added no import. `preflight codesextant/daemon.py
  --symbol shutdown` answered **"nothing resembles it; it looks new"** while
  `initiate_shutdown`, `_shutdown_for_idle` and `stop_running` were all indexed in that
  file. `_name_similarity` requires **two** shared words, so a single-word query can
  only ever match exactly: `shutdown` scores 0.0 against `initiate_shutdown`. The same
  rule missed `stop_running` for the query `stop`. The two-word rule was a deliberate,
  documented choice with a good reason (one shared word is usually a common verb), and
  it has now been measured wrong on one real case. **`docs/roadmap.md` Phase D4 is the
  experiment**; do not relax the threshold without it, because the reason the rule
  exists -- `get_user` against `get` -- is still real.
  **Measured since, and the rule changed: exp16, roadmap D4.** A single shared word now
  counts when the word is rare *and* the overlap still clears the threshold: +0.014 held
  out for +0.05 names per query. The two-word requirement was written by eye with a good
  reason, and the good reason turned out to be carried mostly by the overlap denominator
  rather than by the word count -- `get` only ever matched two-word names anyway.

- **A sample of fifty gave the opposite sign.** The first exp16 run scored 60 commits per
  repository: 50 duplicates, and the in-file variant read **+0.000** reach. At 250
  commits -- 190 duplicates -- the same variant read **+0.053**, and held out **+0.110**.
  A conclusion was nearly written from the small run. Nothing about it looked wrong; it
  was simply too small to see the effect, and "no difference" is what a small sample
  reports by default. Check what n a rate is over before believing a zero, the same way
  a column of zeros is a defect until proven otherwise.

- **Measure the rule you would ship, not the one that is easy to score.** exp16 first
  scored the rarity gate alone: +0.050 held out. The rule that could actually ship also
  has to clear the user's similarity threshold -- otherwise
  `CODESEXTANT_PREFLIGHT_NAME_SIMILARITY` silently stops working, which an existing test
  caught -- and with that floor the same idea reaches +0.014. Three and a half times
  smaller. Had the floor been added quietly after the measurement, the shipped feature
  would have carried a number it does not earn.

- **A variant that reads 143 when the baseline reads 2.4 is a defect, not a finding.**
  exp16 tried counting a word's frequency over production names only, on the theory that
  five `test_shutdown_*` names are one concept rather than five uses. A word appearing
  *only* in tests then has a production frequency of **zero**, and zero passes every
  ceiling, so that variant matched everything. Same shape as the exp10 regex that read
  zero pre-commit hooks everywhere: the number was extreme enough to check, and checking
  it took one minute against the hours of building on it.

- **A curated set is not a sample, and the difference was a factor of five.** exp15
  stratified the 120 frozen prevention tasks and found 2% where a grep could not reach
  the companion -- enough to stop E2 from being run as designed, which was the right
  call. What it could not say is whether 2% describes software or describes the
  curation. exp17 ran the *same classifier* over 900 real commits from the *same
  repositories*: **11% on the derivation set, 7% on the prevention set.** The task
  Nothing about `prevention_tasks.json` is wrong; it is simply the easy half, and every
  number E1 and E1b produced is a number about the easy half. **Before trusting a rate
  from a curated set, measure the same rate on the uncurated population.** The
  measurement cost ten minutes and it moved a decision that would have cost 240 agent
  runs.
  **And then the explanation was wrong too.** The obvious mechanism -- exp12 requires a
  commit to touch two Python files, and two Python files usually change together because
  they share a symbol -- was written into a commit message and a PR before it was
  checked. exp18 checks it: **every hidden task it finds touches two or more Python
  files**, so that filter would have kept four in five. The shortfall is real and its
  cause is not established. Naming a plausible mechanism is not the same as measuring
  one, and a number that survives is not evidence for the story told about it.
  **The correction then repeated the mistake at one level up.** "Every hidden task
  touches two or more Python files" was written from the smoke run of eleven. At
  forty-five it is 82%, not 100%, and the filter costs about a fifth of the stratum
  rather than none of it. Two entries above, this file already says a sample of fifty
  gave the opposite sign; a sample of eleven was used to overturn a claim within the
  hour of writing that down. **A correction needs the sample size a finding needs.**

- **Two instruments were broken and the pilot found both before it found a result.**
  That is what a pilot is for and it is the cheapest six agent runs this project has
  spent. The cost question was put to the agent, which reported **18** tool calls
  against **31** the runner observed -- while the runner had been reporting tokens, tool
  uses and duration for free the whole time. And "the tool did not help" was
  indistinguishable from "the agent never opened it", two findings that call for
  opposite responses and score identically on file changes; the first attempt to tell
  them apart counted daemon-log requests and got zero, from a log that did not exist,
  because the CLI answers in its own process. **Before spending agents, check that every
  number the design depends on can actually be produced.**

- **A mode with no precision term is beaten by changing everything.** The E2 pilot had
  one pair where the arms changed different files and scored identically, which is how
  this surfaced: `changed_a_broke_b` and `forgot_the_guard` are recall over the truth,
  so breadth is free. A `shotgun` baseline that touches every Python file now runs in
  `--validate` and scores **1.00** on both -- measured, not assumed. It does not fail the
  suite, because the modes are recall by design and the paired A/B compares two attempts
  of similar breadth. It prints, because the last mode that could be satisfied without
  doing the task survived by nobody looking. Read those two rates as "did it find them",
  never as "did it change the right set".

- **Dump features, not verdicts.** exp4 dumped per-case hit/miss, which answers only the
  question already asked. exp6 dumps a feature table per candidate file, so a new idea is
  scored by `--score` on an old dump in one second instead of an hour. Four candidates
  were rejected this way for the cost of one run.

## Where the code lives

| file | what it owns |
|---|---|
| `engine.py` | `preflight`, `check`, indexing, the blast-radius cost gate, reuse scoring |
| `diffscan.py` | what the working tree changed, as files and line ranges |
| `cochange.py` | mining change coupling from git, file-level and symbol-level |
| `render.py` | every result-to-text renderer, shared by the CLI and MCP |
| `mcp_server.py` | JSON-RPC 2.0 over stdio, ten tools, no SDK |
| `guards.py` | the six Python fence kinds, their derived rules, and where a reason lives |
| `gates.py` | what runs against every push: CI jobs, pre-commit hooks, lint rules, the language floor. Deliberately none of this tool's ranking machinery |
| `storage.py` | SQLite schema, derived-state markers, co-change counters |
| `references.py` | name sweeps, jedi resolution, and the module-import scan behind DEPENDENTS |
| `experiments/` | thirteen experiments, three corpora, the frozen prevention task set, the results and the caveats |

## Reproducing the experiments

```bash
python -m experiments.exp1_cochange        # ~3 min
python -m experiments.exp2_blast_radius    # ~15 min, checks out worktrees
python -m experiments.exp3_reuse           # ~2 min
python -m experiments.exp4_check --limit 120 --dump outcomes.json   # ~55 min
python -m experiments.exp5_caller_gap --limit 60            # ~6 min
python -m experiments.exp6_caller_candidates --limit 60 --dump features.json   # ~25 min
python -m experiments.exp6_caller_candidates --score features.json             # instant
python -m experiments.exp7_preflight_dependents --limit 150 # ~35 min, preflight's side
```

`exp6 --score` is the one to reach for first. It re-runs every candidate over a dump
written earlier, so a new idea costs a second; only a candidate needing a *feature the
dump does not carry* costs another collection run.

The corpus clones itself into `~/.cache/codesextant-corpus` or `$CODESEXTANT_CORPUS`.
`--repo PATH` scores a repository of your own, which is the only way to know whether
these numbers hold for the code you actually work on.

---

# Next steps, in order

**These are now the detail under `docs/roadmap.md`.** That file carries the two demands
this project serves, what finishing each one means, and the phase ordering. This section
is the near-term view; the roadmap is the reason any of it is next.

**1. The prevention experiment — run it.** The task set and scorer now exist and are
checked in: `experiments/exp12_prevention.py` and `experiments/prevention_tasks.json`,
120 real commits over a third corpus (flask, pytest, alembic) chosen before any of it was
read, one rate per failure mode, and three baselines proving no mode is free. What is
left is E2: the same model on the same tasks with the tool available and without, paired,
with tokens recorded. **It needs agents, which is the only reason it is not done.**
Everything cheaper is: every retrievable claim in the tool has a held-out number, and
this is the only design that answers the question the tool exists for.

**2. Tune the thresholds against the corpus.** `min_support` and `min_confidence`
predate any evidence. exp11 gives a second reason to look: the symbol tier is silent in
52–78% of queries because a symbol's rules rest on less support than its file's, so the
same floor may be wrong for the two tiers. Sweep on the derivation set, confirm on the
held-out set, never the other way round.

**3. Language coverage.** Resolution is Python-only; twelve other languages degrade to
name matching, and exp2 says nothing about any of them.
