# Getting started

CodeSextant has a command-line interface and a browser dashboard. Both use the same local index.

## Install

CodeSextant is tested on CPython 3.10 through 3.13.

```bash
python -m pip install codesextant
```

On Windows, the Python launcher is also fine:

```powershell
py -3.13 -m pip install codesextant
```

## Start the dashboard

Open a terminal in the project you want to inspect, then run:

```bash
codesextant gui .
```

This command does three things:

1. It creates the first index if the project has not been indexed.
2. It starts the shared local daemon, or reuses the existing one.
3. It opens a single-use local session URL, then redirects to `http://127.0.0.1:8790/`.

The local API signs each request with HMAC using a secret stored under `~/.codesextant`. The secret itself is never sent over HTTP. The browser receives only a bounded in-memory dashboard session, stored in the current tab's `sessionStorage` rather than a cookie or persistent browser storage.

The initial index may take time in a large repository. CodeSextant respects Git's standard ignore rules, including `.gitignore` and `.git/info/exclude`. Generated files and dependency directories should be ignored in the repository rather than indexed.

## Use the dashboard

The service card shows whether the daemon is running, its process ID, port, database directory, and log file.

Each indexed project has three actions:

- **Reindex** updates changed files and removes files that were deleted or became ignored.
- **Map** returns the highest-ranked symbols within the selected token budget.
- **References** finds callers for a symbol name. Check the confidence label before treating a result as confirmed.

The dashboard is a compact control panel. It is not the WebGPU star map prototype shown in the README.

## Run without opening a browser

For a remote shell, CI runner, or another headless environment:

```bash
codesextant gui . --no-browser
```

The command prints the dashboard URL. The CLI remains available without a browser:

```bash
codesextant index .
codesextant map . --budget 1500
codesextant references . SYMBOL --def-path path/to/file.py
```

## Control the daemon

The daemon is shared by local CodeSextant clients, listens only on the loopback interface, and authenticates every route.

```bash
python -m codesextant.daemon ping
python -m codesextant.daemon ensure
python -m codesextant.daemon stop
```

Set `CODESEXTANT_PORT` before starting the daemon if port 8790 is already in use.

Indexes survive daemon exits and machine restarts. A new agent session reconnects to the existing project database and attaches a watcher only for that project. Existing graph data can answer immediately while one background reconciliation applies changes made during downtime. Responses expose `index_lifecycle.stale_possible` when source verification is still required. CodeSextant does not rebuild every historical project.

The daemon exits after three idle hours by default. A missing daemon is started by the next client request, which retries once. On Windows, repository clones include `tools/register_windows_startup.ps1` for an optional one-shot login check. A normal PyPI installation does not need startup registration.

Interactive graph requests use a short deadline and reserved capacity. Treat CodeSextant as an accelerator, not a gate: after one timeout, HTTP 503 or 504, authentication or upgrade warning, or missing index, continue with focused AST queries, `rg`, and direct source reads. Do not resend the same failed heavy query in the same task.

`status` is a bounded diagnostic endpoint. It still returns HTTP 200 with `service_load` and `background_recoveries` when SQLite is temporarily locked. In that case, `partial=true` and `index_status_error="database-busy"` identify the unavailable index details.

## Before changing a file

```bash
codesextant preflight . path/to/file.py --symbol name_you_are_about_to_add
```

Three sections, one call. `ALREADY EXISTS` compares the name you intend to use against every indexed definition, so a second implementation is caught before it is written; omit `--symbol` and this section is skipped, since it is the only check that has to happen before the code exists. `CO-CHANGE` reports what version-control history says changes together with this file, which is where obligations that appear nowhere in the source live. `BLAST RADIUS` lists files with resolved references into the target, and under-reports until `references` has run against the symbols involved.

With `--symbol`, co-change also narrows to that one definition where history supports it: changing `daemon.py` anywhere brings its reliability test 70% of the time, while changing `serve` has brought it every time. Those rules are mined from the diffs of the one file you asked about, not the whole repository, which is the difference between twenty milliseconds and a minute. Attribution comes from the definition name Git puts in each hunk header, so a change that falls outside every definition — a module-level constant, an import block — is left to file scope rather than credited to the function above it.

Co-change needs a Git worktree; without one that section is empty and the other two still answer. Rules are re-mined when HEAD moves and cached in between. The thresholds are tunable with `CODESEXTANT_COCHANGE_MIN_SUPPORT`, `CODESEXTANT_COCHANGE_MIN_CONFIDENCE` and `CODESEXTANT_COCHANGE_MAX_COMMIT_FILES`; the last one decides how large a commit may be before it is discarded as a sweeping change that would couple everything to everything.

## Local data and cleanup

CodeSextant stores one SQLite database per absolute project path. The database contains paths, symbols, references, hashes, and extracted comments or docstrings. It does not store full source files and is not encrypted. Access follows the permissions on `~/.codesextant`, so processes running as the same OS user or identities allowed by that directory ACL can read it.

Indexing extracts what navigation needs: symbols and references. The analyses layered on top of them — clone fingerprints for `duplicates`, comment extraction for `comments` and `health` — are computed the first time you ask for them, then kept up to date per file as source changes. This keeps the index small and quick to build for the common case of navigating code; the trade is that the first `codesextant duplicates` run on a project does the fingerprinting work, and later runs are immediate.

Run `codesextant cache` to inspect managed index usage without exposing repository paths. At a quiescent daemon shutdown, caches for repositories missing beyond 30 days are removed. If managed indexes exceed 10 GiB, older inactive cache groups are removed until usage reaches 90 percent of that quota. Projects used by the current daemon are excluded. OS-locked project leases also make cleanup skip a group that is open in another CLI or process. Credentials, logs, locks, and unknown files are never deletion candidates. These limits can be changed with the `CODESEXTANT_CACHE_*` environment variables documented in the README.

To remove all indexes, browser sessions, and the local API token, stop the daemon and delete `~/.codesextant`. CodeSextant does not upload the index or send telemetry.

## Connect it to an agent over MCP

```bash
claude mcp add codesextant -- codesextant mcp
```

For any client that reads an `mcpServers` block — Codex, Cursor, Claude Desktop — the equivalent entry is `{"command": "codesextant", "args": ["mcp"]}`.

The agent then calls `preflight(file="path/to/file.py", symbol="name")` as a tool, rather than importing a client and writing the error handling around it. That difference decides whether the index gets consulted at all: an agent weighing fifteen lines of setup against one `rg` call picks `rg`, and then rebuilds something that already existed.

Eight tools are exposed and no more — `preflight`, `code_map`, `find_references`, `impact`, `symbols`, `find_duplicates`, `index`, `status` — because every tool description is context the agent carries on every turn.

Calls go through the same shared daemon the CLI uses, so several agents on one machine share one index and one process. If the daemon will not start, the same query runs inside the MCP server and the answer says so rather than failing; `--no-daemon` makes that the default. A project that has never been indexed is indexed on the first call, and the answer says that too.

## Install the agent skill

```bash
codesextant install-skill
```

The installer detects Codex, Claude Code, and the open Agent Skills directory. Use `--target` to select a skill root explicitly.

## Troubleshooting

If the `codesextant` command is not on `PATH`, use the module form:

```bash
python -m codesextant gui .
```

If the browser does not open, use the printed single-use URL before it expires, or run the command again. Check daemon health with:

```bash
python -m codesextant.daemon ping
```

High-confidence TypeScript and JavaScript reference resolution needs Node 20 or newer
and the `ts_bridge` directory from the GitHub repository. PyPI installations fall back
to low-confidence name matching for those languages and label the results accordingly.
