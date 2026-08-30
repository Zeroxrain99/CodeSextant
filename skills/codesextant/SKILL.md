---
name: codesextant
description: Use CodeSextant's shared local symbol graph before modifying a repository, tracing callers, estimating change impact, locating relevant files, reviewing architecture, or checking whether similar code already exists.
---

# CodeSextant

Use the installed `codesextant` package as an opportunistic navigation accelerator before broad
text search. It is never a prerequisite for modifying code. It runs locally, and all agents on
the machine share one active daemon and one persistent index per project.

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

If ensure, status, or a graph query raises `TimeoutError`, returns HTTP 503 or 504, reports an
authentication or upgrade action, a partial status, or no index, stop using CodeSextant for this task. Fall
back immediately to narrow local AST queries, `rg`, and direct source reads. Do not retry the
same failed heavy query in the same task. A delayed graph is less useful than a focused local
read, and CodeSextant must never become a modification gate.

3. If `cs` is available, call `cs.get_map(budget=1500, focus_files=[...], focus_symbols=[...])`
   once to identify the small set of files and symbols worth reading. Interactive graph calls
   have a short deadline and reserved daemon capacity.

   `budget` is the size of the response you will actually receive, envelope included, not a
   count of symbols. Spend it deliberately: raise it when you want a wider map, and read
   `truncated_by_budget` to learn whether more symbols were available than it paid for.
4. Before changing a symbol, call `cs.find_references(symbol, def_path=...)` and
   `cs.impact(symbol, def_path=...)`.

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
