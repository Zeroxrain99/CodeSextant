---
name: codesextant
description: Use CodeSextant's shared local symbol graph before modifying a repository, tracing callers, estimating change impact, locating relevant files, reviewing architecture, or checking whether similar code already exists.
---

# CodeSextant

Use the installed `codesextant` package as an opportunistic navigation accelerator before broad
text search. It is never a prerequisite for modifying code. It runs locally, and all agents on
the machine share one active daemon and one persistent index per project.

## First: are the CodeSextant tools already in your tool list?

Look for `preflight`, `code_map`, `find_references`, `impact`, `symbols`, `find_duplicates`,
`index`, and `status`. If they are there, CodeSextant is connected over MCP — call them
directly and skip the Python entirely:

```text
preflight(file="codesextant/storage.py", symbol="project_key")
```

Everything else in this skill still applies: *when* to call preflight (before writing, not
after), how to read the three sections, and what each confidence label means. Only the
transport differs, and the tool names are the same as the client methods below without the
`cs.` prefix. An unindexed project is indexed on the first call, so there is nothing to set
up first.

If those tools are not in your list, the user can add them once with
`claude mcp add codesextant -- codesextant mcp` (or the equivalent `mcpServers` entry for
their client). Until then, use the Python client below — it reaches the same daemon and the
same index.

## Start a task

1. Resolve the repository root to an absolute path.
2. Create a client, make one bounded connection attempt, and inspect the cheap status view:

```python
from codesextant import CodesextantClient

repo = r"ABSOLUTE_REPOSITORY_PATH"
try:
    cs = CodesextantClient(project=repo)
    lifecycle = cs.ensure()
    if lifecycle["action"] not in {"already-running", "spawned"}:
        cs = None
    state = cs.status(fresh=False) if cs is not None else None
    if state is not None and (
        not state.get("indexed")
        or state.get("partial")
        or state.get("index_status_error")
    ):
        cs = None
except Exception:
    cs = None
```

Fall back to narrow local AST queries, `rg`, and direct source reads **when a call actually
fails**: `TimeoutError`, HTTP 503 or 504, an authentication or upgrade action, a partial
status, or no index. Do not retry the same failed heavy query in the same task. A delayed
graph is less useful than a focused local read, and CodeSextant must never become a
modification gate.

That is a response to an observed failure, not a standing licence to skip the tool. There
is no paused, disabled, or owner-suspended state to infer: if `ensure()` returns
`already-running` or `spawned` and `status` reports an index, CodeSextant is available and
declining to use it costs the task the three checks it exists to provide. Do not attribute a
decision to skip to a rule of CodeSextant's — the only rules it has are the failure
conditions listed above, and each one is something a call returned, not something to assume
in advance. Concern about cost is not one of them: the queries in this skill are bounded and
measured in milliseconds, and the daemon is shared, so a second agent on the same machine
reuses it rather than starting anything.

3. If `cs` is available, call `cs.get_map(budget=1500, focus_files=[...], focus_symbols=[...])`
   once to identify the small set of files and symbols worth reading. Interactive graph calls
   have a short deadline and reserved daemon capacity.

   `budget` is the size of the response you will actually receive, envelope included, not a
   count of symbols. Spend it deliberately: raise it when you want a wider map, and read
   `truncated_by_budget` to learn whether more symbols were available than it paid for.
4. **Before you write or change anything in a file, call
   `cs.preflight(file, symbol=...)`.** One call, a few milliseconds, and it answers the
   three questions that are otherwise answered too late:

   - `already_exists` — definitions that resemble the `symbol` you are about to add.
     Check this before writing a second implementation of something the repository
     already has. Pass the name you intend to use; without `symbol` this section is
     skipped and you lose the only check that has to happen *before* the code exists.
   - `co_change` — files that history says change together with this one, with the
     confidence and the commit counts behind each. This is where the obligations no
     one wrote down live: the version constant that goes with the packaging file, the
     route that goes with the allowlist and the routing test, the language that goes
     with its fixture. A high-confidence companion you are not touching is the single
     most likely thing you are about to forget.

     Each entry carries a `scope`. With `symbol` given, entries scoped `symbol` are
     keyed to that one definition rather than the whole file, which matters on a large
     module: changing `daemon.py` anywhere brings its reliability test 70% of the time,
     while changing `serve` has brought it every time. A `symbol` entry supersedes the
     `file` entry for the same companion. Symbol scope needs a definition that has been
     edited a few times, so a new or rarely touched one falls back to file scope, which
     is never worse than having asked nothing.
   - `blast_radius` — files with resolved references into this one. When nothing has
     been resolved for the symbol yet, preflight resolves it on the spot if a cost
     measurement says that is cheap, and otherwise reports the files that *name* it as
     leads with the reason it stopped short. Read `blast_radius.resolution.status`:
     `resolved` and `cached` mean an empty list is a measured absence, while
     `declined`, `unsupported` and `off` mean the question is still open and
     `find_references` is the way to close it. `name_match_files` are leads, never
     callers — they are kept in their own key precisely so they cannot be read as one
     list with the confirmed ones, and they are reported *beside* confirmed callers,
     not instead of them. A lead is usually a same-named symbol elsewhere, but it is
     also what a caller reached through dynamic dispatch, a re-export or a registry
     looks like, since no static resolver can follow those. When a lead matters to
     your change, read it; do not resolve the ambiguity by trusting either list.

   Every section states its own evidence, and a claim with weak evidence says so.
   Treat co-change as advice, not law: history records what people did, and a rule at
   100% over three commits is still three commits.

5. Before changing a symbol in particular, call `cs.impact(symbol, def_path=...)` for the
   transitive picture: preflight resolves one hop, and impact follows the caller chain
   and separates production code from tests. Call `cs.find_references(symbol,
   def_path=...)` when preflight's resolution status was `declined`, `unsupported` or
   `off` — that is preflight telling you the question is still open.

## Why preflight rather than remembering

Three failures repeat regardless of how careful the author is, because all three depend
on knowing something that is not in the file being edited:

- building a second copy of something that already exists,
- missing a companion change that nothing in the source mentions,
- changing something whose callers are elsewhere.

Each already had a query, and each query was one more thing to remember, so under time
pressure all three were skipped. preflight is one call, cheap enough that calling it
every time costs nothing, which is the only property that makes it actually get called.

## Use confidence labels

- Auto-trust only `confidence="high"` references.
- Treat low-confidence name matches as search leads and verify them in source.
- Map ordering is mostly name-level evidence unless resolved edges exist, so read it as
  "where to look first", not as a verified call graph. Several same-named definitions
  (`close`, `run`) can share adjacent ranks; `def_path` tells them apart.
- Pass `def_path` when names are ambiguous.
- Use the correct `src_root` when a Python import root is below the repository root.
- CodeSextant narrows what to read. It does not replace reading the selected code.

## Keep the index current

The daemon watches source files through native OS events. Creates, edits, moves, and deletes
are debounced and applied only to the dirty paths. Do not run a full reindex after every edit.

After editing, allow the debounce window to finish, then query the changed file or affected
symbol again. Use `cs.health()["watcher"]["watched"]` to confirm the repository is watched.
A new agent session reconnects to the persistent index. After a daemon restart, the first real
symbol or graph query may return the existing graph while reconciliation runs in the background.
Check `index_lifecycle.stale_possible` and verify affected source when it is true. Run
`cs.reindex()` as a separate maintenance action only for the first index, a reported recovery
failure, or an explicit rebuild. Never make an interactive coding task wait for a first full
index, and never use `force=True` unless the user requests a full rebuild.

## Disconnect, reconnect, and cleanup

- **Short interrupt / reconnect:** call `cs.ensure()` again. `action=="already-running"` with
  `reconnect=true` means reuse the shared daemon and the existing per-project index. Do not
  force-reindex and do not spawn a second daemon.
- **Heavy work containment:** route workers run in a disposable process tree owned by the
  daemon. Deadlines and parent death reap them; do not PID-kill the shared daemon when one
  agent session drops.
- **Session finished / forgotten:** prefer automatic GC. Optional explicit reclaim:
  `codesextant cache --forget ABSOLUTE_REPO_PATH`. Machine-wide reclaim of idle/missing indexes
  and orphaned temp workspaces: `codesextant cache --prune` (add `--dry-run` first). Never
  delete `~/.codesextant` wholesale while a daemon is busy.

## Finish a task

Recheck references and impact for changed public symbols. Report confidence labels and any
unresolved low-confidence edges instead of presenting them as confirmed callers.
