# CodeSextant

**A local code map service for AI agents. No cloud, no API keys. Every agent on your machine shares one import-resolved symbol graph, so they can understand a codebase without reading all of it.**

Before an agent writes or changes any real code, it needs three answers: who calls this symbol, what breaks if I change it, and does something like this already exist. CodeSextant answers those from a resolved graph rather than a text search. It does not replace reading the code. It tells you *which few places* are worth reading.

The name is from the **sextant**: an instrument for fixing your position when there is no landmark in sight.

---

## The problem

The hidden cost of agentic coding is token budget. An agent that starts editing without a global picture rewrites things that already exist, misses call sites, and creates conflicts.

The usual fallback is `grep`. But name matching treats every identically-named symbol as the same thing, so in a codebase with common names like `handle`, `run`, or `Config`, the results are mostly noise. We have measured cases where **every returned "reference" was wrong**.

CodeSextant resolves imports instead of matching text, and it keeps the resulting graph in a single resident service that every agent on the machine queries.

## What makes it different

| | |
|---|---|
| **Import resolution, not name matching** | Python goes through jedi (which understands import chains and scope); TS/JS through ts-morph (`findReferences`, so same-name symbols in unrelated modules do not collide). Results are labelled high or low confidence, and an agent is expected to auto-trust only the high-confidence ones. |
| **One daemon, shared by every agent** | A single process per machine (cross-process file lock plus an exclusive listen socket, with idempotent startup). Claude Code, Cursor, or any HTTP client talk to the same instance. Projects are isolated by `sha1(absolute repo path)` into separate SQLite databases. |
| **Python and TypeScript/JavaScript** | These are the languages CodeSextant actually resolves imports for, and the ones it is tested against. tree-sitter can extract symbols from a dozen more (Go, Rust, C#, Java, C, C++, Kotlin, Swift, PHP, Ruby, Bash, Lua) but **those get name-matched references, not resolved ones**. Treat them as experimental. Broader real support is a goal, not a claim. |
| **Local only** | No cloud calls, no API key, nothing leaves the machine. This is stricter than "local LSP tooling": there is no key to configure at all. |
| **Budgeted output** | `map` uses weighted PageRank to return the most important N symbols that fit a token budget, rather than dumping the whole graph. |

## Quick start

Requires Python 3.10 or newer.

```bash
pip install codesextant
```

High-confidence TS/JS resolution needs two more things: Node on your PATH, and a one-time `npm install` inside `ts_bridge/`. That directory ships in the git repository, not in the pip package. So a `pip install` gives you resolved references for Python and name-matched ones for TS/JS; clone the repository instead if you need TS/JS resolved. Either way the result carries its confidence label, and a missing bridge degrades the answer rather than breaking the tool.

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
┌── CodeSextant daemon (Python, port 8790, single instance, shared by all agents) ──┐
│   tree-sitter symbol extraction + jedi / ts-morph import resolution               │
│   incremental SQLite (content hash + git HEAD freshness) + weighted PageRank      │
│   per-project isolation: sha1(repo path) -> ~/.codesextant/<key>.db               │
│   HTTP API, plus a self-contained dashboard on GET /                              │
└───────────────────────────────────────────────────────────────────────────────────┘
        ▲ one daemon, many front-ends: standalone shell, IDE webview, agent HTTP clients
```

Single-instance startup is what makes "every agent shares one map" work at all. Without it, each agent would build and hold its own copy of the graph.

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
| `CODESEXTANT_TS_MORPH_DISABLED` | off | force TS/JS to name matching |
| `CODESEXTANT_TS_MORPH_TIMEOUT` | `30` | ts-morph subprocess timeout, seconds |
| `CODESEXTANT_GIT_FRESHNESS_DISABLED` | off | stop comparing the index against git HEAD |
| `CODESEXTANT_CSRF_GUARD` | on | Origin check on POST endpoints (allows localhost, Tauri and IDE webviews; blocks cross-site) |

A few lower-level language-inference knobs (`CODESEXTANT_INFER_LANG_*`) are documented in the source.

## Testing

```bash
python -m pytest tests/ -q
```

430 tests, about a minute on a developer laptop. They cover the daemon lifecycle, incremental indexing, map scalability, snapshot invalidation, and reference resolution across the supported languages.

## Known limitations

We would rather state these than have you discover them.

- Reference lookup needs the right `--src-root` when the import root lives in a subdirectory (`.../src`). Get it wrong and high-confidence references are silently missed.
- When several symbols share a name, omitting `--def-path` means the first candidate definition wins, and high-confidence results may legitimately come back as zero. All candidates are listed so you can disambiguate.
- PageRank quality depends on how dense the reference edges are, and those accumulate as `find_references` is called. A freshly indexed repo produces a rougher map than one that has been queried for a while.
- High-confidence TS/JS resolution requires `npm install` in `ts_bridge/`, which only the git repository carries. A pip install therefore gets name-matched TS/JS references, and the confidence label says so rather than hiding it.
- Go and Rust get tree-sitter symbols but name-matched references. This is a real accuracy ceiling, not a temporary gap.
- Index freshness is content-hash incremental plus a git HEAD comparison; `status?fresh=1` tells you whether the index has fallen behind.

## Repository layout

| Path | What it is |
|---|---|
| `codesextant/` | The Python implementation. This is what `pip install codesextant` gives you and what the docs above describe. |
| `ts_bridge/` | A small Node helper the Python side shells out to for ts-morph reference resolution. Git only; the pip package does not carry it. |
| `tests/` | Test suite for the Python implementation. |
| `ts/` | **An in-progress TypeScript rewrite, not yet wired to anything.** Nothing in `codesextant/` imports it and it is not published. It is in the repository because the work is real and ongoing, but do not mistake it for the shipping implementation. |

## Licence

MIT. See [LICENSE](https://github.com/Zeroxrain99/CodeSextant/blob/master/LICENSE).

The core is free and open source. A commercial edition is planned around what open source deliberately does not cover: a shared central map for teams and multi-agent fleets, access control with audit logs, private deployment, and supported integrations.
