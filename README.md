# CodeSextant

**A practical code navigation and change-impact tool for AI coding agents and human developers.**

CodeSextant builds a local graph of symbols and reference edges so agents and developers can trace callers, locate code, and estimate change impact before editing.

For AI agents, the index turns repository structure into targeted queries for the files and symbols worth reading. Developers can use the same graph through the CLI or HTTP API. The daemon updates it from native file events.

Python and TypeScript/JavaScript references are resolved through imports. Other supported languages return low-confidence name matches. CodeSextant runs locally without an API key and does not send source code off the machine.

[Install](#quick-start) · [Give it to an AI agent](#give-codesextant-to-your-agent) · [Language support](#how-it-works)

## See the codebase

![A selected CodeSextant symbol with its source and resolved callers](https://raw.githubusercontent.com/Zeroxrain99/CodeSextant/master/docs/assets/visual-map-symbol-inspector.png)

*CodeSextant indexed its own repository for this WebGPU prototype. The published package exposes the graph through the CLI and HTTP API in text or JSON. The renderer is not included in the package.*

Each star is a symbol with a file, line number, and source snippet. Selecting one opens the code and highlights its direct callers while unrelated symbols fade. Production and test edges use separate styles.

The selected symbol is `index_paths()` at `codesextant/engine.py:257`. The inspector shows six high-confidence callers across two affected files.

## Quick start

Requires Python 3.10 or newer.

```bash
pip install codesextant
codesextant index .
codesextant map . --budget 1500
```

To connect an AI coding agent, add the [CodeSextant skill](#give-codesextant-to-your-agent) after installation.

## Visual map

![CodeSextant visual map prototype](https://raw.githubusercontent.com/Zeroxrain99/CodeSextant/master/docs/assets/visual-map-prototype.png)

The overview groups symbols by their reference edges. Tightly connected code forms compact constellations, while tangled coupling produces overlap and visual noise.

The prototype supports source inspection, rotation, semantic zoom, and navigation from the repository overview to an individual symbol. It does not yet normalize layouts across machines or aggregate modules for very large repositories.

## Why use an index

Name matching cannot distinguish same-named symbols in different scopes. In collision-heavy repositories, searches for names such as `handle`, `run`, and `Config` can return many false positives. For Python and TypeScript/JavaScript, CodeSextant resolves imports and stores the graph in a shared local service.

## How it works

| | |
|---|---|
| **Import resolution** | Python uses jedi, and TS/JS uses ts-morph `findReferences`. Resolved references are high confidence, while name matches are low confidence and require source verification. |
| **One shared daemon** | A cross-process file lock and exclusive listen socket keep one process alive per machine. Claude Code, Cursor, the CLI, and HTTP clients can use the same instance. Projects have separate SQLite databases keyed by absolute repository path. |
| **Language coverage** | Python and TypeScript/JavaScript have import-resolved references. Go, Rust, C#, Java, C, C++, Kotlin, Swift, PHP, Ruby, Bash, and Lua use tree-sitter symbol extraction with low-confidence name-matched references. |
| **Event-driven updates** | Native file events send created, edited, moved, and deleted paths to the indexer. Full scans are reserved for initial indexing and recovery. |
| **Local only** | Runs without cloud calls or API keys. Source and index data stay on the machine. |
| **Budgeted output** | `map` uses weighted PageRank to return the most important N symbols that fit a token budget, rather than dumping the whole graph. |

## Give CodeSextant to your agent

Download the single [CodeSextant SKILL.md](https://raw.githubusercontent.com/Zeroxrain99/CodeSextant/master/skills/codesextant/SKILL.md) after installation and
place it in your agent's skill directory. For example:

```text
.agents/skills/codesextant/SKILL.md    # Codex and compatible agents
.claude/skills/codesextant/SKILL.md   # Claude Code
```

Keep the entry filename as `SKILL.md`. The containing `codesextant` directory is the skill
name under the Agent Skills specification.

If an agent does not support skill directories, attach that one Markdown file and ask the agent
to follow it before editing. The skill starts the shared daemon, binds the current repository,
uses the map to narrow what should be read, checks references and impact before changes, and
preserves confidence labels instead of treating name matches as confirmed callers.

Resolved TS/JS references require Node and `npm install` inside `ts_bridge/`, which is available only in the GitHub repository. The PyPI package resolves Python references and returns low-confidence name matches for TS/JS. Clone the repository if you need ts-morph resolution.

## Commands

```bash
python -m codesextant index      <repo>                     # build or incrementally update the index
python -m codesextant map        <repo> [--budget N]        # most important symbols, within a token budget
python -m codesextant references <repo> <symbol> [--src-root R] [--def-path D]
python -m codesextant symbols    <repo> [--file F]
python -m codesextant status     <repo>
# any command takes --json for machine-readable output
```

Running it as a resident service:

```bash
python -m codesextant.daemon ensure   # idempotent: starts one only if none is running
python -m codesextant.daemon ping     # strict liveness check (verifies /health brand, not just the port)
python -m codesextant.daemon stop
# then open http://127.0.0.1:8790/ for a self-contained dashboard (inline CSS/JS, no CDN, works offline)
```

HTTP endpoints, all taking `project=<absolute repo path>`:
`GET /health` `/get_symbols` `/get_map` `/status` (`?fresh=1` to compare against git HEAD) `/projects`;
`POST /find_references` `/reindex`.

On Windows, `tools/register_windows_startup.ps1` registers the daemon to start on login (run it as administrator to get boot-time start as well). It is idempotent, so re-running it is safe. A supervisor task probes liveness every 5 seconds and restarts the daemon if it exits.

## Architecture

```text
┌── CodeSextant daemon (Python, port 8790, single instance, shared by local tools) ─┐
│   tree-sitter symbol extraction + jedi / ts-morph import resolution               │
│   incremental SQLite (content hash + git HEAD freshness) + weighted PageRank      │
│   per-project isolation: sha1(repo path) -> ~/.codesextant/<key>.db               │
│   HTTP API, plus a self-contained dashboard on GET /                              │
└───────────────────────────────────────────────────────────────────────────────────┘
        ▲ one daemon, many clients: CLI, agent skills, IDE webviews, HTTP clients
```

An exclusive socket and cross-process file lock keep one daemon alive per machine, so agents and developer tools share one graph instead of starting separate indexers.

Large cold `map` queries are served from a SQLite covering index plus a revision-checked JSON snapshot, with a small in-process LRU on top. Every snapshot is a cache keyed on index revision and query parameters; SQLite remains the only source of truth, and any change invalidates them.

## Configuration

All settings are environment variables. Boolean flags accept `1/true/yes/on` case-insensitively.

| Variable | Default | Effect |
|---|---|---|
| `CODESEXTANT_HOME` | `~/.codesextant` | SQLite database directory |
| `CODESEXTANT_PORT` | `8790` | daemon port |
| `CODESEXTANT_SUPERVISOR_INTERVAL_SEC` | `5` | liveness probe interval, minimum 1 |
| `CODESEXTANT_MAP_TIMEOUT_SEC` | `60` | client deadline for cold `map` queries only |
| `CODESEXTANT_MAP_CACHE_SIZE` | `4` | trimmed map results cached per DB revision |
| `CODESEXTANT_NAMEGRAPH_MAX_FILES` | adaptive | override the file-scan cap; adapts 12 to 5000 by symbol count when unset |
| `CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES` | `250000` | hard cap so generated code cannot exhaust memory |
| `CODESEXTANT_WATCH_ENABLED` | on | filesystem watcher for proactive incremental indexing |
| `CODESEXTANT_WATCH_DEBOUNCE_MS` | `2000` | delay that combines a burst of file events into one dirty-path update |
| `CODESEXTANT_TS_MORPH_DISABLED` | off | force TS/JS to name matching |
| `CODESEXTANT_TS_MORPH_TIMEOUT` | `30` | ts-morph subprocess timeout, seconds |
| `CODESEXTANT_GIT_FRESHNESS_DISABLED` | off | stop comparing the index against git HEAD |
| `CODESEXTANT_CSRF_GUARD` | on | Origin check on POST endpoints (allows localhost, Tauri and IDE webviews; blocks cross-site) |

A few lower-level language-inference knobs (`CODESEXTANT_INFER_LANG_*`) are documented in the source.

## Testing

```bash
python -m pytest tests/ -q
```

The suite covers the daemon lifecycle, incremental indexing, map scalability, snapshot invalidation, and reference resolution across the supported languages.

## Known limitations

- Reference lookup needs the right `--src-root` when the import root lives in a subdirectory (`.../src`). Get it wrong and high-confidence references are silently missed.
- When several symbols share a name, omitting `--def-path` means the first candidate definition wins, and high-confidence results may legitimately come back as zero. All candidates are listed so you can disambiguate.
- PageRank quality depends on how dense the reference edges are, and those accumulate as `find_references` is called. A freshly indexed repo produces a rougher map than one that has been queried for a while.
- High-confidence TS/JS resolution requires `npm install` in `ts_bridge/`, which is included only in the GitHub repository. PyPI installations return low-confidence name matches for TS/JS.
- Go and Rust use tree-sitter symbols and low-confidence name-matched references. Their imports are not resolved.
- Event-driven updates require the daemon to be running. After downtime or a missed event, `status?fresh=1` checks the index against git HEAD and a reindex restores it.

## Repository layout

| Path | What it is |
|---|---|
| `codesextant/` | The Python implementation. This is what `pip install codesextant` gives you and what the docs above describe. |
| `ts_bridge/` | A small Node helper the Python side shells out to for ts-morph reference resolution. Git only; the pip package does not carry it. |
| `tests/` | Test suite for the Python implementation. |
| `ts/` | In-progress TypeScript rewrite. It is not imported by `codesextant/` or included in the published package. |

## Licence

MIT. See [LICENSE](https://github.com/Zeroxrain99/CodeSextant/blob/master/LICENSE).

The name comes from the sextant, an instrument used to find a position when landmarks are out of sight.

The core is free and open source. A planned commercial edition will add a shared team index, multi-agent access controls and audit logs, private deployment, and supported integrations.
