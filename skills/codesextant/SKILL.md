---
name: codesextant
description: Use CodeSextant's shared local symbol graph before modifying a repository, tracing callers, estimating change impact, locating relevant files, reviewing architecture, or checking whether similar code already exists.
---

# CodeSextant

Use the installed `codesextant` package as the navigation layer before broad text search.
It runs locally. All agents on the machine share one daemon and one index per project.

## Start a task

1. Resolve the repository root to an absolute path.
2. Create a client, ensure the daemon, and inspect status:

```python
from codesextant import CodesextantClient

repo = r"ABSOLUTE_REPOSITORY_PATH"
cs = CodesextantClient(project=repo)
cs.ensure()
state = cs.status(fresh=True)
if not state["indexed"]:
    cs.reindex()
```

3. Call `cs.get_map(budget=1500, focus_files=[...], focus_symbols=[...])` to identify the
   small set of files and symbols worth reading.
4. Before changing a symbol, call `cs.find_references(symbol, def_path=...)` and
   `cs.impact(symbol, def_path=...)`.

## Use confidence labels

- Auto-trust only `confidence="high"` references.
- Treat low-confidence name matches as search leads and verify them in source.
- Pass `def_path` when names are ambiguous.
- Use the correct `src_root` when a Python import root is below the repository root.
- CodeSextant narrows what to read. It does not replace reading the selected code.

## Keep the index current

The daemon watches source files through native OS events. Creates, edits, moves, and deletes
are debounced and applied only to the dirty paths. Do not run a full reindex after every edit.

After editing, allow the debounce window to finish, then query the changed file or affected
symbol again. Use `cs.health()["watcher"]["watched"]` to confirm the repository is watched.
Call `cs.reindex()` only for the first index, daemon-restart recovery, a lost watcher event,
or an explicit rebuild. Never use `force=True` unless the user requests a full rebuild.

## Finish a task

Recheck references and impact for changed public symbols. Report confidence labels and any
unresolved low-confidence edges instead of presenting them as confirmed callers.
