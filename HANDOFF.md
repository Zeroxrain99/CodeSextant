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
| version | 0.27.0 (`codesextant/__init__.py` and `pyproject.toml`, bound by a test) |
| tests | `python -m pytest -q` → 729 passed, 6 skipped |
| lint | `python -m ruff check codesextant tests experiments` → **clean**, and a CI job enforces it. The baseline used to be "12 pre-existing", written here and checked by nobody; a number you have to remember is a guard with a memory requirement. |
| experiments | `experiments/README.md` — protocol, results, and what they do not establish |

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

**For agents:** `codesextant mcp` speaks MCP over stdio, nine tools, no new dependency.
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

## What is not established

- **Prevention.** Everything here measures retrieval. Whether an author who saw the
  answer made a better change needs agents doing tasks with and without the tool.
- **Whether DEPENDENTS helps a reader.** It names 0.6 more files per run for +0.046
  recall, so roughly one added file in thirteen is the forgotten one. Whether that
  reads as a hint or as noise is a question about people, and belongs to the prevention
  experiment.
- **Symbol-level co-change.** It is mined, shipped and asserted, and never scored.
- **Thresholds.** `min_support=3`, `min_confidence=0.5` predate the corpus that could
  justify them. Tuning must use the held-out repositories, not the derivation set.
- **Twelve of thirteen languages.** Only Python gets import resolution.
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
| `mcp_server.py` | JSON-RPC 2.0 over stdio, nine tools, no SDK |
| `storage.py` | SQLite schema, derived-state markers, co-change counters |
| `references.py` | name sweeps, jedi resolution, and the module-import scan behind DEPENDENTS |
| `experiments/` | seven experiments, corpus management, the results and the caveats |

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

**1. Score symbol-level co-change.** It ships and is asserted and has never been
measured. An exp1 variant, cheap, and it either justifies the per-file diff mining or
retires it. It is first because it is the last shipped claim in this tool that has never
been scored at all — the caller side is now worked out on both surfaces, and every
remaining idea there has been measured and rejected.

**2. Tune the thresholds against the corpus.** `min_support` and `min_confidence`
predate any evidence. Co-change recall is ~0.10 and there is very likely a better
trade available. Sweep on the derivation set, confirm on the held-out set, never the
other way round.

**3. The prevention experiment.** Agents doing tasks with and without the tool, on a
task set nobody here wrote. It is the only design that answers the actual question, and
everything above is a proxy for it.

**4. Language coverage.** Resolution is Python-only; twelve other languages degrade to
name matching, and exp2 says nothing about any of them.
