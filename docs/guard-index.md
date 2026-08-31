# The guard index: design, grounded in what the corpus actually contains

## The failure

Not "the change forgot its test". This one:

> A guard you wrote yourself months ago blocks you now. You do not remember it exists.
> You cannot see why it is there. The cheapest way out looks like deleting it, and the
> honest way out costs an hour of reading logs and git history.

Every guard in that sentence was written on purpose and most of them work. That is what
makes the failure expensive rather than merely annoying: the fence is load-bearing, the
person hitting it is the person who built it, and the information needed to get past it
in thirty seconds exists somewhere in the repository already.

This is the second of CodeSextant's three problems, sharpened. `check`'s companion
section addresses the blunt version — history says this file usually changes with that
one — at a recall of 0.169 to 0.250. It says *which file*. It never says *which fence,
what it checks, or what satisfies it*.

## What the field already does, and where each approach stops

| approach | what it gets right | why it does not solve this |
|---|---|---|
| [Architecture Decision Records](https://www.martinfowler.com/bliki/ArchitectureDecisionRecord.html) | The insight that rationale is the perishable part, not the code | Hand-written, stored away from the code, and unlinked to the guard that enforces the decision. Goes stale for the same reason the registry was wanted. |
| [Feature-flag registries](https://docs.getunleash.io/topics/feature-flags/best-practices-using-feature-flags-at-scale) — LaunchDarkly Code References, Unleash, GrowthBook's MCP server, Uber's [Piranha](https://www.growthbook.io/blog/engineering-guide-feature-flag-technical-debt) | The closest industrial analogue: every flag gets an owner, an expiry, and code references; stale ones are found and removed automatically | Covers one guard kind out of six. A flag registry knows nothing about the test, the allowlist or the threshold that will block you. |
| [Design by contract](https://www.eiffel.org/doc/eiffel/ET-_Design_by_Contract_(tm),_Assertions_and_Exceptions) and [C++ contracts](https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2024/p3361r0.pdf) | The guard and its documentation are one artifact, so they cannot drift apart | Only covers assertions, requires the code to have been written that way, and says nothing about tests or config. |
| [Agent Skills' progressive disclosure](https://www.newsletter.swirlai.com/p/agent-skills-progressive-disclosure) — metadata always loaded (~80 tokens), body on relevance (~2k), resources on demand | Exactly the three-layer shape this needs, with measured token economics: 17 skills cost ~1,700 tokens total | A packaging convention for hand-written knowledge. Nothing derives the layers from a repository. |
| [Code knowledge graphs](https://sourcegraph.com/resources/context-compare) — SCIP, CodeGraph, GitNexus, codebase-memory-mcp | Local-first tree-sitter + SQLite + MCP, reported ~10× token reduction and 2.1× fewer tool calls | Indexes structure, not intent. Knows that B calls A; does not know that B is a fence and what it is fencing. |
| [Traceability link recovery](https://arxiv.org/html/2509.20149) (R2Code and LLM-based TLR) | Automatic recovery of requirement↔code links, ~28% F1 gains | Research-grade, needs labelled data, and recovers links to requirements documents most repositories do not have. |
| [Chesterton's fence](https://thoughtbot.com/blog/chestertons-fence) and characterization tests | The correct framing of the problem | A principle. No tooling attached. |

**The gap is the join.** Flag registries know flags. ADRs know decisions. Contracts know
assertions. Knowledge graphs know structure. Nothing holds all six guard kinds in one
index, links them to the code they protect, and — decisively — nothing *derives* the
index, which is why the two hand-maintained approaches both rot.

CodeSextant is unusually well placed for the join: tree-sitter symbols in thirteen
languages, a comments table that already records tags and owning symbols, resolved
references, mined co-change, module dependents, one renderer, and an MCP surface.

## What the repository actually contains — exp8

`python -m experiments.exp8_guard_inventory`. Six external repositories plus this one,
read with `ast` to report the ceiling rather than one extractor's reach.

### Guards are dense, so a flat index is impossible

| repo | lines | guards | per kLOC | tests as a share |
|---|---|---|---|---|
| requests | 12,032 | 411 | 34.2 | 0.84 |
| click | 28,581 | 630 | 22.0 | 0.89 |
| tqdm | 9,615 | 182 | 18.9 | 0.87 |
| jinja | 22,875 | 777 | 34.0 | 0.89 |
| httpie | 19,002 | 505 | 26.6 | 0.85 |
| rich | 51,866 | 834 | 16.1 | 0.86 |
| CodeSextant | 36,235 | 935 | 25.8 | 0.72 |

16 to 34 per thousand lines, 182 to 935 per project. **Progressive disclosure is not a
nicety here, it is the only shape that fits.** A flat registry of 935 entries is a second
codebase to maintain, which is the failure mode this is supposed to prevent.

### The reason is usually not written down — and this is the finding that changes the design

Share of guards carrying a stated reason anywhere in the source:

| kind | requests | click | tqdm | jinja | httpie | rich | CodeSextant |
|---|---|---|---|---|---|---|---|
| `raise` (message) | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `assert` | 0.19 | 0.46 | 0.00 | 0.94 | 0.24 | 0.29 | — |
| `test` | 0.24 | 0.34 | 0.96 | 0.03 | 0.07 | 0.09 | 0.39 |
| `allowlist` | 0.00 | 0.00 | 1.00 | 0.50 | 0.17 | 0.33 | 0.83 |
| `threshold` | 0.00 | 0.00 | — | 1.00 | 0.00 | 0.12 | 0.42 |
| `env_switch` | 0.00 | 0.14 | — | — | 0.29 | 0.00 | 0.12 |

Two readings, and both matter:

1. **`raise` and `assert` guards mostly document themselves**, because the message is the
   documentation. For those, the middle disclosure layer is free.
2. **Everything else mostly does not.** Tests are 3% documented in jinja and 7% in httpie.
   Thresholds and environment switches — the literal safety valves — are at or near zero
   in most repositories, *including this one*, where 88% of 78 environment switches carry
   no stated reason at all.

So the categories that bite hardest are exactly the categories with nothing to disclose.

### Mining the commit message does not rescue them

The obvious repair, and the one this tool is best positioned for, since it already reads
history: when the source says nothing, read the commit that introduced the line. Sampled
250 undocumented guards per repository and searched the full commit message — body, not
just subject — for an explanatory clause:

| repo | rescued |
|---|---|
| requests | 0.02 |
| click | 0.04 |
| jinja | 0.03 |
| httpie | 0.01 |
| rich | 0.00 |
| CodeSextant | 0.10 |
| tqdm | 0.56 (of only 25 orphans — small and not to be leaned on) |

**Two to four percent.** The reason is not in the commit either. This kills the design
that was about to be built, before it was built, which is the third time that discipline
has paid for itself in this project.

## What the measurement implies

The naive design — index the guards, show name → reason → full text — would have shipped
a middle layer that is empty for most of the guards that actually block people. The
corpus says to invert it:

**Lead with the rule, not the prose.** What a guard *does* is machine-readable even when
nobody wrote down why. That is also what a blocked person needs first:

- a threshold: its name, its value, the branch it gates, who reads it, what a violation
  looks like;
- an allowlist: its members, where membership is tested, what happens to a non-member;
- an environment switch: its variable, its default, what changes when it is set;
- a test: what it asserts on and which symbols it touches — which is to say, *what it is
  fencing*;
- a `raise`/`assert`: the message, which is already the reason.

**Treat prose as a bonus, and capture it where it is cheapest.** The moment a guard blocks
you is the moment you have just reconstructed why it exists. That is the only moment the
missing sentence is cheap, and the tool should be there to take it.

**Three layers, sized by the Agent Skills economics** — the one place where the prior art
transfers almost directly:

| layer | content | cost |
|---|---|---|
| 1 — always | one line per guard *relevant to what you are touching*: kind, name, location | tens of tokens |
| 2 — on relevance | the rule: what it checks, what satisfies it, what it protects | hundreds |
| 3 — on demand | the source itself, the test body, the history | whatever it costs, paid only when asked |

Layer 1 is bounded by relevance rather than by the repository, which is what makes 935
guards affordable: you never see 935, you see the four that your diff can trip.

## The methodological problem this uncovered, which affects existing numbers

exp4 and exp6 hold out `sorted(files)`' first `.py` entry. Path sorting puts `tests/`
after `src/`, `httpie/`, `rich/` and most package directories, so test files are
systematically under-sampled as the held-out file:

| set | a guard file is in the commit | is the held-out one |
|---|---|---|
| derivation (176 cases) | 0.57 | 0.12 |
| held out (175 cases) | 0.54 | 0.06 |

Asked how often `check` names the held-out file when that file is a guard, the answer is
0.476 on 21 derivation cases and 0.182 on 11 held-out cases — opposite directions, both
samples far too small to read. **So this directory currently says almost nothing about
the case this document is about.** Any experiment on the guard index has to hold out a
guard file deliberately rather than take whatever sorting hands it.

## What shipped, in 0.28.0

`codesextant guards`, the `guards` MCP tool, and the `/guards` daemon route. The design
above, built as measured:

| decision | where it came from |
|---|---|
| Lead with the derived **rule**; prose is a bonus | four guards in five have no stated reason, and the commit does not carry it either |
| **Three layers**: which fences are in reach → the rule for each → `--full` for the source | 182 to 935 guards per repository; a flat list is a second codebase |
| Six shown, the rest **counted not dropped** | exp1's finding that a predictor naming twenty files stops being read |
| Relevance decided **per guard** wherever the fence's own text is the evidence | built the per-file version first: on this repository it put eleven unrelated environment switches ahead of the three tests that actually fenced the symbol. exp9 later scored the same comparison across 360 commits: **+0.189 held out**, so the rejection made by eye was right |
| Two **file-level tiers** admitted anyway — history says a file moves with yours, or it imports what you changed — ranked below every fence read off its own text and labelled with the claim they rest on | both were refused by the same argument as the row above, and the argument was wrong twice. Against the symbol tiers alone the held-out difference from reading co-change instead was +0.056, **interval crossing zero** — `guards` was a longer way to an answer `check` already gives. The offline union was +0.111, because the signals hit different commits; that built the history tier. The import tier was then measured as a predictor before anything was built: +0.072 held out, positive on all six repositories. Together **+0.100 held out** over what 0.28.0 shipped |
| The decision rule for the second tier **fixed and committed before its numbers existed** | choosing what counts as success after seeing which candidate wins is how a held-out set stops being one. Two candidates were measured; the weaker was refused even though it was real, because the stronger beat it by +0.039 and the ceiling of running both was +0.014 |
| Reason labelled with its source (`docstring` / `comment` / `message`) | "the author said this" and "the tool derived this" are different claims |
| The **always-on block** — CI jobs, pre-commit hooks, lint rules, language floor — printed whole and **not ranked at all** | exp10 counted the population at 4–15 CI checks, 8–21 hooks and 0–14 lint rules against 182–964 Python guards, and every one applies to every change. Relevance has the same answer each time, so asking is the waste. It has no corpus score and cannot have one: retrieval recall is meaningless for a fence that always applies |
| A workflow triggered only by `push: tags:` **excluded** from that block | claiming something gates you when it does not sends a reader looking for a check that will never run — the cost this tool exists to remove, not to add to |

Cost, warm, on this repository, median of nine on an idle machine: `guards` 244–255 ms
reading a full diff, `check` 309–344 ms — both under the 475 ms `check` was held to
before any of this. The two file-level tiers are most of what `guards` spends: one cached
co-change probe, one pass for importers, and a bounded number of AST parses. On a change
whose per-guard tiers already fill six slots they add no *output* at all, which is the
case they were bounded for. The always-on block costs **0.6 ms** and about 50 tokens,
which is what makes printing it whole the cheap option rather than the reckless one. The first build was 316 ms; profiling put 2.4 of
3.1 seconds in `ast.get_source_segment`, which re-splits the whole file on every call.
Slicing from lines already in hand is a quarter of the cost and the same output.

**Not yet done, and named rather than implied**: Python only; no CI, lint, pre-commit,
schema-constraint or database guards, all of which block people and none of which are in
the 16-34 per kLOC above; nothing measured about whether seeing this makes a change
better, which is the prevention experiment and is still the only design that answers it.

**And one shape of repository it is measurably wrong for.** On jinja, exp9 scored
`guards` below every control — three real losses. The two file-level tiers took it from
0.067 to 0.150 and left one: the project's most-changed files still beat it by 0.167.
The per-file version it rejects still edges it there (0.167 against 0.150). A template
engine reaches its subjects through indirection, so its tests never spell the names they
exercise and a per-guard name rule has nothing to match. Five repositories say per-guard
evidence is right and one says it is wrong, and nothing here tells a new repository which
it is before the fact.

## A worked example, added while writing this

`tests/test_portability.py` is a guard of exactly the kind catalogued above, written
because two names that do not exist everywhere — `signal.SIGKILL` on Windows, `tomllib`
before 3.11 — were used as though they did. It is worth looking at as the shape the index
is meant to surface:

- the **rule** is machine-derivable and is what a blocked reader needs first: *this name
  is not on every platform; guard it with a branch, a matching `except`, a `getattr`
  default, or a stated precondition*;
- the **reason** happens to be written down, in the docstring, because the failure was
  expensive enough that someone bothered — which is the 3–39% case, not the common one;
- and the guard it replaces was **a convention with no enforcement**, followed correctly
  six times and forgotten twice, in the two places its author could not run.

That last point is the whole thesis in miniature. The problem was never that the author
did not know the rule. It was that nothing held the rule where the author would meet it
at the moment of breaking it.

## What is not established

- **That an index shortens time-to-fix.** Everything above is about what can be built and
  what it would contain. Whether a person or an agent that saw it made a better change,
  faster, is the prevention experiment, and it is still the only design that answers the
  real question.
- **That the rules are extractable at useful precision, at corpus scale.** They are
  pinned by `tests/test_guards.py` on a constructed project and they read correctly on
  this repository, which is two anecdotes and a unit test rather than a measurement.
  What is missing is the corpus equivalent of exp4: hold out a commit, ask which fences
  it was about to meet, and score whether the one it actually broke was named.
- **Coverage beyond Python.** exp8 reads `ast`. Twelve other languages have the same
  guards and would need tree-sitter patterns per language.
- **Guard kinds not counted**: CI workflow rules, lint and type-checker configuration,
  pre-commit hooks, database constraints, schema versions. All of these block people and
  none of them is in the 16–34 per kLOC above, so that number is a floor.
