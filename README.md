# CodeSextant

[![Tests](https://github.com/Zeroxrain99/CodeSextant/actions/workflows/tests.yml/badge.svg)](https://github.com/Zeroxrain99/CodeSextant/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/codesextant)](https://pypi.org/project/codesextant/)
[![Python](https://img.shields.io/pypi/pyversions/codesextant)](https://pypi.org/project/codesextant/)
[![License](https://img.shields.io/github/license/Zeroxrain99/CodeSextant)](LICENSE)

**A practical code navigation and change-impact tool for AI coding agents and human developers.**

## See the codebase

![A selected CodeSextant symbol with its source and resolved callers](https://raw.githubusercontent.com/Zeroxrain99/CodeSextant/master/docs/assets/visual-map-symbol-inspector.png)

*CodeSextant indexed its own repository for this WebGPU prototype. The published package exposes the graph through the CLI and HTTP API in text or JSON. The renderer is not included in the package.*

Each star is a symbol with a file, line number, and source snippet. Selecting one opens the code and highlights its direct callers while unrelated symbols fade. Production and test edges use separate styles.

The selected symbol is `index_paths()` at `codesextant/engine.py:257`. The inspector shows six high-confidence callers across two affected files.

CodeSextant builds a local graph of symbols and reference edges so agents and developers can trace callers, locate code, and estimate change impact before editing.

For AI agents, the index turns repository structure into targeted queries for the files and symbols worth reading. Developers can use the same graph through the CLI or HTTP API. The daemon updates it from native file events.

Python and TypeScript/JavaScript references are resolved through imports. Other supported languages return low-confidence name matches. CodeSextant runs locally without an API key and does not send source code off the machine.

[Install](#quick-start) · [Open the GUI](#open-the-gui) · [Give it to an AI agent](#give-codesextant-to-your-agent) · [Language support](#how-it-works)

## Quick start

CodeSextant is tested on CPython 3.10 through 3.13.

```bash
python -m pip install codesextant
codesextant gui .
```

The second command indexes the current project, starts the local daemon, and opens the dashboard in your default browser. To connect an AI coding agent, also install the [CodeSextant skill](#give-codesextant-to-your-agent).

## Platform support

The complete test suite runs on every push across Windows, macOS, and Linux with CPython 3.10, 3.11, 3.12, and 3.13.

| Platform | Tested environment | Notes |
|---|---|---|
| Windows | GitHub-hosted Windows x64 runner | Use PowerShell, Command Prompt, or another terminal. Windows ARM64 and 32-bit are not covered by CI. |
| macOS | GitHub-hosted macOS runner | Intel and Apple Silicon dependency wheels are available, but CI covers the current hosted runner only. |
| Linux | GitHub-hosted Ubuntu runner | Other distributions may work when CodeSextant's binary dependencies provide compatible wheels. |

The CLI works without a desktop. The GUI requires a local browser. Git is optional, but repositories with Git automatically respect `.gitignore`, `.git/info/exclude`, and global Git ignore rules during indexing.

## Open the GUI

Run this from the project you want to inspect:

```bash
codesextant gui .
```

Use an absolute path if the project is elsewhere:

```powershell
codesextant gui "C:\path\to\your\project"
```

The command opens a short-lived local session URL, then redirects the browser to `http://127.0.0.1:8790/`. The long-lived API token never appears in the URL or page. The dashboard shows daemon status and indexed projects. From a project row, use **Reindex** to apply source changes, **Map** to list important symbols, and **References** to inspect callers by symbol name.

The dashboard is the current GUI. The star map shown above is a separate prototype and is not included in the published package. See the [getting started guide](https://github.com/Zeroxrain99/CodeSextant/blob/master/docs/getting-started.md) for headless use, daemon controls, and troubleshooting.

## Visual map

![CodeSextant visual map prototype](https://raw.githubusercontent.com/Zeroxrain99/CodeSextant/master/docs/assets/visual-map-prototype.png)

The overview groups symbols by their reference edges. Tightly connected code forms compact constellations, while tangled coupling produces overlap and visual noise.

The prototype supports source inspection, rotation, semantic zoom, and navigation from the repository overview to an individual symbol. It does not yet normalize layouts across machines or aggregate modules for very large repositories.

## Before you change a file

Three mistakes repeat no matter how careful the author is, because all three turn on knowing something that is not in the file being edited: writing a second copy of something that already exists, missing a companion change nothing in the source mentions, and changing something whose callers live elsewhere.

`preflight` answers all three in one call, in a few milliseconds:

```bash
python -m codesextant preflight . codesextant/storage.py --symbol project_key
```

```
  ALREADY EXISTS   4 similar definition(s)
    1.00  [function] project_key                  codesextant/storage.py:31  (this file)
    1.00  [function] projectKey                   ts/src/storage.ts:171
    1.00  [function] _project_key                 codesextant/cache_lease.py:91

  CO-CHANGE        2 file(s) usually change with this one
     80%  (4/5 commits)  codesextant/engine.py
     60%  (3/5 commits)  codesextant/daemon.py

  BLAST RADIUS     10 file(s) with resolved references; 2 more name it  (resolved in 1.4s)
    codesextant/engine.py
    ...
    ?  codesextant/daemon.py
```

The last section used to be empty on the call where it mattered most. Resolved references only accumulate as `references` runs, so on a fresh index there were none, and "no callers" and "nobody has looked" printed identically. With `--symbol`, preflight now resolves that one symbol itself — but only after measuring what it would cost, because a check worth running before every edit has to be one you never stop to think about. A text sweep counts the files naming the symbol first, at about seven microseconds each; resolution costs roughly a tenth of a second per file, so 25 files is the default ceiling for doing it inline. Above that preflight declines, reports the files that name the symbol as leads rather than callers, and says which limit it hit.

That same sweep is what makes caching the expensive half safe, and it is the reason the cache is not keyed to the file being edited. **A caller has to name the symbol**, so the files naming it are a complete superset of the possible callers: if none of them has changed and no new one has appeared, no caller can have appeared either. Keying the cache to the definition instead — the obvious choice — goes stale silently the moment a caller is added in some *other* file, and keeps reporting a measured absence that stopped being true.

Lines marked `?` are files that name the symbol without resolving to it. They are reported beside the confirmed callers, never merged into one list. Usually they are a same-named symbol elsewhere — but they are also what a caller reached through dynamic dispatch, a re-export or a registry looks like, because no static resolver can follow those.

`--resolve yes` spends whatever it takes for the exact answer; `--resolve no` reads only what is already stored, and is the one mode that skips the sweep.

With `--symbol`, the middle section narrows to that one definition where history supports it. On a two-thousand-line module the file-level claim is too coarse to act on: changing `daemon.py` anywhere brings its reliability test 70% of the time, while changing `serve` has brought it every time.

The middle section is mined from version-control history rather than written by hand. Some obligations are not in the code at all: bumping a version constant means editing the packaging file, adding a route means adding it to the allowlist and to the routing test. Files that keep appearing in the same commit are coupled whether or not anything imports anything, so the rule can be recovered instead of remembered. Sweeping commits are excluded, a pair needs several shared commits before it counts, and every rule shows the commit counts behind it, because history records what people did rather than what they should have done.

### What the three sections are actually worth

Measured, not asserted. [`experiments/`](experiments/README.md) replays the history of
psf/requests, pallets/click and tqdm/tqdm against control groups, prequentially, so no
prediction is made from a state that contains the commit it is predicting.

- **Co-change**, given exactly as many guesses as the baselines, is **1.4× to 2.1× more
  precise** than the strongest of them — the same directory, ranked by how often each
  file changes. Its F1 interval clears that baseline on two repositories of three; on
  the third they overlap and no advantage is established. It speaks on about half of
  queries and names a file that really did change on about two thirds of those. Its
  **recall is roughly one companion file in ten**: a high-precision hint, not a safety
  net.
- **On a young single-author repository the frequency baseline beats it outright.** It
  earns its place where change is spread across many hands and many areas.
- **Reuse detection** finds a differently-named structural duplicate about half the
  time on repositories it was not tuned against. An exact-name grep finds none of them.
- **Import-resolved references are 2.2× to 3.2× more precise than the name matches
  beside them on two repositories of four**, and on the other two the difference is not
  established — on one of them it reverses. Resolution optimises for callers while the
  only available ground truth is co-change, so this neither confirms nor refutes the
  claim; it does mean the blast radius is not a reliable predictor of what else you
  have to edit, and it is why both tiers are printed and labelled rather than one.

The experiments also found two defects in preflight and paid for themselves doing it;
both are described in `experiments/README.md`.

## Why use an index

Name matching cannot distinguish same-named symbols in different scopes. In collision-heavy repositories, searches for names such as `handle`, `run`, and `Config` can return many false positives. For Python and TypeScript/JavaScript, CodeSextant resolves imports and stores the graph in a shared local service.

## How it works

| | |
|---|---|
| **Import resolution** | Python uses jedi, and TS/JS uses ts-morph `findReferences`. Resolved references are high confidence, while name matches are low confidence and require source verification. |
| **One shared daemon** | A cross-process file lock and exclusive listen socket allow only one active process per machine. Claude Code, Cursor, the CLI, and HTTP clients can use the same instance. Projects have separate persistent SQLite databases keyed by absolute repository path. |
| **Language coverage** | Python and TypeScript/JavaScript have import-resolved references. Go, Rust, C#, Java, C, C++, Kotlin, Swift, PHP, Ruby, Bash, and Lua use tree-sitter symbol extraction with low-confidence name-matched references. |
| **Event-driven updates** | Native file events send created, edited, moved, and deleted paths to the indexer. Full scans are reserved for initial indexing and recovery. |
| **Persistent reconnect** | A new terminal, agent, or conversation reconnects to the existing SQLite index. The selected project is reconciled in the background after a daemon restart, so an existing graph can answer immediately. A full rebuild is not required. |
| **Local only** | Runs without cloud calls or API keys. Source and index data stay on the machine. |
| **Budgeted output** | `map` uses weighted PageRank to return the most important N symbols that fit a token budget, rather than dumping the whole graph. |

## Give CodeSextant to your agent

### As MCP tools (recommended)

CodeSextant speaks the Model Context Protocol over stdio, so an agent calls it directly
instead of writing a client:

```text
preflight(file="codesextant/storage.py", symbol="project_key")
```

Register it once. Claude Code:

```bash
claude mcp add codesextant -- codesextant mcp
```

Or, for any client that reads an `mcpServers` block (Codex, Cursor, Claude Desktop):

```json
{
  "mcpServers": {
    "codesextant": {
      "command": "codesextant",
      "args": ["mcp"]
    }
  }
}
```

Eight tools, and deliberately no more, because every tool description is context the agent
pays for on every turn: `preflight`, `code_map`, `find_references`, `impact`, `symbols`,
`find_duplicates`, `index`, `status`. Each one takes an optional `project` argument and
otherwise works in the directory the server was started in.

Calls are served by the shared local daemon, so several agents on one machine use one index
and one process rather than one each. If the daemon will not start, the same call runs
in-process and the answer says so instead of failing. A project that has never been indexed
is indexed on the first call, and the answer says that too.

`codesextant mcp --no-daemon` (or `CODESEXTANT_MCP_NO_DAEMON=1`) always answers in-process.

### As an Agent Skill

The PyPI package includes the [CodeSextant SKILL.md](https://raw.githubusercontent.com/Zeroxrain99/CodeSextant/master/skills/codesextant/SKILL.md). Install it after `pip install codesextant`:

```bash
codesextant install-skill
```

The command detects Codex, Claude Code, and the open Agent Skills home on the current machine.
To choose a skill root explicitly, pass it once or repeat it for several agents:

```bash
codesextant install-skill --target ~/.codex/skills
codesextant install-skill --target ~/.claude/skills
```

The installed layout is:

```text
.agents/skills/codesextant/SKILL.md    # Codex and compatible agents
.claude/skills/codesextant/SKILL.md   # Claude Code
```

Keep the entry filename as `SKILL.md`. The containing `codesextant` directory is the skill
name under the Agent Skills specification.

If an agent does not support skill directories, attach that one Markdown file and ask the agent
to use it while editing. The skill treats CodeSextant as an opportunistic accelerator, never a
hard gate: it makes one bounded attempt, uses the map to narrow what should be read, and falls
back immediately to focused AST, text, and source reads if the service is busy or unavailable.
It also preserves confidence labels instead of treating name matches as confirmed callers.

Resolved TS/JS references require Node 20 or newer and `npm install` inside `ts_bridge/`,
which is available only in the GitHub repository. The PyPI package resolves Python
references and returns low-confidence name matches for TS/JS. Clone the repository if
you need ts-morph resolution.

## Commands

```bash
python -m codesextant index      <repo>                     # build or incrementally update the index
python -m codesextant gui        <repo>                     # index, start the daemon, and open the GUI
python -m codesextant map        <repo> [--budget N]        # most important symbols, within a token budget
python -m codesextant preflight  <repo> <file> [--symbol S] [--resolve auto|yes|no]
python -m codesextant references <repo> <symbol> [--src-root R] [--def-path D]
python -m codesextant symbols    <repo> [--file F]
python -m codesextant status     <repo>
python -m codesextant mcp        [repo]                     # serve the index to an MCP client over stdio
python -m codesextant cache                                 # managed index cache usage
# any command takes --json for machine-readable output
```

Running the daemon without opening a browser:

```bash
codesextant gui . --no-browser
python -m codesextant.daemon ensure   # idempotent: starts one only if none is running
python -m codesextant.daemon ping     # strict liveness check (verifies /health brand, not just the port)
python -m codesextant.daemon stop
```

HTTP endpoints require a path-bound HMAC proof derived from the local secret in `~/.codesextant/daemon.token`. The secret itself is never sent over HTTP. Endpoints take `project=<absolute repo path>` where applicable, so use `CodesextantClient` instead of constructing authentication headers yourself:
`GET /health` `/get_symbols` `/get_map` `/status` (`?fresh=1` to compare against git HEAD) `/projects`;
`POST /find_references` `/reindex`.

On Windows, `tools/register_windows_startup.ps1` optionally registers one startup check at login. Run it as administrator to add boot-time start as well. It is idempotent, so re-running it also upgrades older repeating tasks. Normal recovery is demand-driven: the next client request starts a missing daemon and retries once.

## Architecture

```text
┌── CodeSextant daemon (Python, port 8790, single instance, shared by local tools) ─┐
│   tree-sitter symbol extraction + jedi / ts-morph import resolution               │
│   incremental SQLite (content hash + git HEAD freshness) + weighted PageRank      │
│   per-project isolation: sha1(repo path) -> ~/.codesextant/<key>.db               │
│   HTTP API + deadline-bound route workers + self-contained dashboard on GET /     │
└───────────────────────────────────────────────────────────────────────────────────┘
        ▲ one daemon, many clients: CLI, agent skills, IDE webviews, HTTP clients
```

An exclusive socket and cross-process file lock keep at most one daemon active per machine, so agents and developer tools share one graph instead of starting separate indexers. Interactive symbol, map, reference, hierarchy, and impact requests have short deadlines and reserved execution capacity separate from rebuild and background work. The daemon exits after three idle hours by default. The persistent indexes remain on disk, and the next client starts the daemon again.

Large cold `map` queries are served from a SQLite covering index plus a revision-checked JSON snapshot. Direct in-process callers also use a small memory LRU; isolated HTTP workers rely on the persistent snapshots across requests. Every snapshot is a cache keyed on index revision and query parameters; SQLite remains the only source of truth, and any change invalidates them.

Queue waits and coalesced followers honor their own request deadlines, and indexing checks cancellation between files. A timed-out follower detaches from a shared result. CPython cannot safely interrupt a thread in the middle of Jedi, tree-sitter, SQLite, or another native call, so production HTTP engine routes run in disposable child processes. When an owner reaches its request deadline, the daemon terminates and reaps that exact child process tree before releasing the execution slot. Background reconciliation retains a separate one-shot hard timeout for a native call that never returns. No periodic watchdog is used.

## Local security and stored data

Every data route is authenticated, including health and project listings. The dashboard shell contains no index data and its API calls require a short-lived session opened by `codesextant gui`. A single-use 60-second bootstrap stores that session only in the current tab's `sessionStorage`, then removes the code from the address bar. It does not use a cookie or persistent browser storage. Requests with a mismatched loopback `Host` header are rejected, request bodies and pre-auth connections are bounded, and the dashboard ships with a restrictive content security policy.

Indexes are ordinary SQLite files, not encrypted vaults. They contain absolute paths, symbols, references, hashes, and extracted comments or docstrings. They do not contain full source files. Processes running as the same OS user, or identities allowed by the storage directory ACL, can read them. At quiescent daemon shutdown, CodeSextant removes cache groups for repositories missing beyond the grace period, then applies least-recently-used cleanup only when managed indexes exceed the configured quota. Projects used by that daemon lifetime are excluded. Every SQLite and snapshot user holds an OS-locked project lease, so cleanup skips groups still open in another CLI or process. Credentials, logs, locks, and unknown files are never candidates. Run `codesextant cache` to inspect managed usage. To remove all local indexes and credentials, stop the daemon and delete `~/.codesextant`. CodeSextant sends no telemetry and uploads no index data.

## Configuration

All settings are environment variables. Boolean flags accept `1/true/yes/on` case-insensitively.

| Variable | Default | Effect |
|---|---|---|
| `CODESEXTANT_HOME` | `~/.codesextant` | SQLite database directory |
| `CODESEXTANT_PORT` | `8790` | daemon port |
| `CODESEXTANT_IDLE_TIMEOUT_SEC` | `10800` | idle seconds before the daemon exits; `0` disables idle shutdown |
| `CODESEXTANT_CACHE_MAX_BYTES` | `10737418240` | managed index bytes that trigger shutdown-time LRU cleanup |
| `CODESEXTANT_CACHE_TARGET_RATIO` | `0.9` | fraction of the quota retained after LRU cleanup |
| `CODESEXTANT_CACHE_MISSING_GRACE_DAYS` | `30` | age before a cache for a missing repository can be removed |
| `CODESEXTANT_CACHE_TOUCH_INTERVAL_SEC` | `60` | minimum interval between access marker updates per project |
| `CODESEXTANT_INTERACTIVE_TIMEOUT_SEC` | `15` | client deadline for symbols, map, references, hierarchy, and impact |
| `CODESEXTANT_MAP_TIMEOUT_SEC` | unset | optional client deadline override for cold `map` queries |
| `CODESEXTANT_MAP_CACHE_SIZE` | `4` | trimmed map results retained by direct in-process callers |
| `CODESEXTANT_NAMEGRAPH_MAX_FILES` | adaptive | override the file-scan cap; adapts 12 to 5000 by symbol count when unset |
| `CODESEXTANT_COCHANGE_DISABLED` | unset | turn off co-change mining; `preflight` then reports two sections |
| `CODESEXTANT_COCHANGE_MAX_COMMIT_FILES` | `25` | largest commit still counted; above this a sweeping change would couple every file it touched |
| `CODESEXTANT_COCHANGE_MAX_COMMITS` | `2000` | how far back history is read |
| `CODESEXTANT_COCHANGE_MIN_SUPPORT` | `3` | commits a pair must share before it is reported as a rule |
| `CODESEXTANT_COCHANGE_MIN_CONFIDENCE` | `0.5` | how often the companion must follow before the rule is worth showing |
| `CODESEXTANT_MCP_NO_DAEMON` | unset | make `codesextant mcp` answer in its own process instead of sharing the local daemon |
| `CODESEXTANT_PROJECT` | unset | default project root for `codesextant mcp` when no path is given |
| `CODESEXTANT_PREFLIGHT_RESOLVE_MAX_FILES` | `25` | how many files may name a symbol before `preflight` declines to resolve it inline and reports name-level leads instead; `0` never resolves |
| `CODESEXTANT_PREFLIGHT_NAME_SIMILARITY` | `0.5` | word overlap at which an existing definition counts as a reuse candidate |
| `CODESEXTANT_PREFLIGHT_COMMON_NAME_MAX` | `8` | how many definitions may share a name before `preflight` reports it as a convention instead of listing them; also the list length, so nothing is ever truncated arbitrarily |
| `CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES` | `250000` | hard cap so generated code cannot exhaust memory |
| `CODESEXTANT_WATCH_ENABLED` | on | filesystem watcher for proactive incremental indexing |
| `CODESEXTANT_WATCH_IDLE_TTL_SEC` | `10800` | idle seconds before a quiescent project watcher is detached |
| `CODESEXTANT_WATCH_DEBOUNCE_MS` | `2000` | delay that combines a burst of file events into one dirty-path update |
| `CODESEXTANT_WATCH_RETRY_MAX_SEC` | `60` | maximum exponential backoff after an incremental index is rejected or fails |
| `CODESEXTANT_WATCH_RETRY_JITTER` | `0.2` | random spread applied to watcher retries to prevent synchronized retry bursts |
| `CODESEXTANT_WATCH_RECOVERY_FOLLOWER_CAP` | `8` | maximum first-query recovery followers for one project |
| `CODESEXTANT_HEAVY_GLOBAL_CAP` | `4` | maximum heavy jobs running across all repositories |
| `CODESEXTANT_INTERACTIVE_GLOBAL_RESERVE` | `3` | global slots reserved for interactive graph requests; one slot remains for maintenance |
| `CODESEXTANT_HEAVY_QUEUE_CAP` | `8` | base queued jobs allowed per repository |
| `CODESEXTANT_INTERACTIVE_QUEUE_RESERVE` | `2` | extra queue slots reserved for agent navigation queries |
| `CODESEXTANT_PRIORITY_AGING_SEC` | `30` | wait time before queued work rises one priority level |
| `CODESEXTANT_HEAVY_TIMEOUT_SEC` | `900` | default client and server deadline for batch and maintenance requests |
| `CODESEXTANT_HEAVY_STUCK_SEC` | `1800` | one-shot hard timeout for a native heavy call; `0` disables it |
| `CODESEXTANT_ROUTE_WORKER_PROCESS` | on | isolate production HTTP engine calls so request deadlines can terminate native work |
| `CODESEXTANT_STATUS_DB_TIMEOUT_MS` | `150` | best-effort SQLite budget for the immediate status endpoint |
| `CODESEXTANT_STATUS_GIT_TIMEOUT_SEC` | `0.5` | Git freshness budget when `status?fresh=1` is requested |
| `CODESEXTANT_STATUS_TIMEOUT_SEC` | `2` | client transport deadline for the diagnostic status request |
| `CODESEXTANT_OVERLOAD_RETRY_AFTER_SEC` | `5` | `Retry-After` value returned with an overload response |
| `CODESEXTANT_MAX_BODY_BYTES` | `65536` | maximum JSON request body size |
| `CODESEXTANT_MAX_HANDLER_THREADS` | `64` | maximum concurrent HTTP handlers, including pre-auth connections |
| `CODESEXTANT_PREAUTH_TIMEOUT_SEC` | `5` | socket read timeout before request authentication completes |
| `CODESEXTANT_AUTH_TIME_SKEW_SEC` | `60` | acceptance window for a single-use signed request proof |
| `CODESEXTANT_AUTH_REPLAY_CAP` | `8192` | bounded in-memory nonce replay cache |
| `CODESEXTANT_BROWSER_SESSION_CAP` | `64` | maximum active dashboard sessions held in daemon memory |
| `CODESEXTANT_TS_MORPH_DISABLED` | off | force TS/JS to name matching |
| `CODESEXTANT_NODE` | `node` | Node executable used by the TS/JS bridge; IDE hosts can provide their bundled runtime |
| `CODESEXTANT_TS_MORPH_TIMEOUT` | `30` | ts-morph subprocess timeout, seconds |
| `CODESEXTANT_GIT_FRESHNESS_DISABLED` | off | stop comparing the index against git HEAD |
| `CODESEXTANT_CSRF_GUARD` | on | Origin allowlist for signed native integrations; dashboard writes always require exact same-origin |

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
- Event-driven updates require the daemon to be running. After downtime, the first graph query can return the existing index while one background reconciliation runs. Its `index_lifecycle.stale_possible` field tells callers to verify affected source. `status?fresh=1` remains available for an explicit Git HEAD check.

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
