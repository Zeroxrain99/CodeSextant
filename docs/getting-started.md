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
3. It opens `http://127.0.0.1:8790/` in the default browser.

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

The daemon is shared by local CodeSextant clients and listens only on the loopback interface.

```bash
python -m codesextant.daemon ping
python -m codesextant.daemon ensure
python -m codesextant.daemon stop
```

Set `CODESEXTANT_PORT` before starting the daemon if port 8790 is already in use.

On Windows, repository clones include `tools/register_windows_startup.ps1` for optional startup registration. A normal PyPI installation does not need startup registration because `codesextant gui` and agent clients start the daemon when required.

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

If the browser does not open, visit the printed URL or run with `--no-browser`. Check daemon health with:

```bash
python -m codesextant.daemon ping
```

High-confidence TypeScript and JavaScript reference resolution needs Node 20 or newer
and the `ts_bridge` directory from the GitHub repository. PyPI installations fall back
to low-confidence name matching for those languages and label the results accordingly.
