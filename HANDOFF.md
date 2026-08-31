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
| branch | `claude/codesextant-handoff-us93o7`, head `49d858d`, 27 commits ahead of master |
| version | 0.25.0 (`codesextant/__init__.py` and `pyproject.toml`, bound by a test) |
| tests | `python -m pytest -q` → 715 passed, 6 skipped |
| lint | `python -m ruff check codesextant tests experiments` → 12 errors, all pre-existing. **12 is the baseline; 13 means you added one.** |
| experiments | `experiments/README.md` — protocol, results, and what they do not establish |

**The two things that matter most.**

```bash
python -m codesextant preflight . path/to/file.py --symbol name_you_will_add
python -m codesextant check .
```

`preflight` runs before an edit, from a name. `check` runs after, from the diff, and
takes no arguments. They ask the same three questions; `check` has more to work with
and is the one that catches a helper reinvented under a different name.

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
| 3. changed A, broke B | `check` → `callers` | **open.** Recall 0.068–0.086. The gap is quantified and two explanations for it are refuted; see below. |

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

## What is not established

- **Prevention.** Everything here measures retrieval. Whether an author who saw the
  answer made a better change needs agents doing tasks with and without the tool.
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

**`render.py` is the only renderer.** The CLI and the MCP server print the same lines
from the same function, with a test pinning it, so the two surfaces cannot describe a
result differently.

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

## Where the code lives

| file | what it owns |
|---|---|
| `engine.py` | `preflight`, `check`, indexing, the blast-radius cost gate, reuse scoring |
| `diffscan.py` | what the working tree changed, as files and line ranges |
| `cochange.py` | mining change coupling from git, file-level and symbol-level |
| `render.py` | every result-to-text renderer, shared by the CLI and MCP |
| `mcp_server.py` | JSON-RPC 2.0 over stdio, nine tools, no SDK |
| `storage.py` | SQLite schema, derived-state markers, co-change counters |
| `experiments/` | four experiments, corpus management, the results and the caveats |

## Reproducing the experiments

```bash
python -m experiments.exp1_cochange        # ~3 min
python -m experiments.exp2_blast_radius    # ~15 min, checks out worktrees
python -m experiments.exp3_reuse           # ~2 min
python -m experiments.exp4_check --limit 120 --dump outcomes.json   # ~55 min
```

The corpus clones itself into `~/.cache/codesextant-corpus` or `$CODESEXTANT_CORPUS`.
`--repo PATH` scores a repository of your own, which is the only way to know whether
these numbers hold for the code you actually work on.

---

# Next steps, in order

**1. Close the caller gap — the owner's third problem, still open.**
Recall 0.068–0.086 against a ceiling of 0.305–0.759: the information is there and
resolution is not reaching it. Two mechanical explanations are already refuted (the
`src/` layout does not degrade jedi; the cost gate declines only 7.8% of symbols) and
one candidate is already rejected (ranking outside files by how many changed symbols
they name is worse than what ships once truncated to a readable length). Untried:
combining the name-level signal with co-change confidence rather than with itself;
targeted jedi resolution of the top name candidates rather than of the first ten
changed symbols; treating a test file that names the changed symbol as its own signal.
**Measure the candidate before building it** — that discipline has already saved one
build in this directory.

**2. Score symbol-level co-change.** It ships and is asserted and has never been
measured. An exp1 variant, cheap, and it either justifies the per-file diff mining or
retires it.

**3. Tune the thresholds against the corpus.** `min_support` and `min_confidence`
predate any evidence. Co-change recall is ~0.10 and there is very likely a better
trade available. Sweep on the derivation set, confirm on the held-out set, never the
other way round.

**4. The prevention experiment.** Agents doing tasks with and without the tool, on a
task set nobody here wrote. It is the only design that answers the actual question, and
everything above is a proxy for it.

**5. Language coverage.** Resolution is Python-only; twelve other languages degrade to
name matching, and exp2 says nothing about any of them.
