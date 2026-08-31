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
```

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
