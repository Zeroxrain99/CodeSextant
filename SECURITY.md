# Security Policy

## Reporting a vulnerability

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/Zeroxrain99/CodeSextant/security/advisories/new)
rather than opening a public issue.

Expect an initial response within a week.

## Threat model

CodeSextant runs entirely on your machine. It makes no network calls, requires
no API keys, and sends nothing anywhere. The main exposure is therefore local:

- **The daemon listens on `127.0.0.1:8790`.** Any process on the machine that
  can reach loopback can query indexed projects, which means it can read symbol
  names, file paths and line numbers from any repo you have indexed. It cannot
  read file contents through the API.
- **`POST` endpoints are Origin-checked** (`CODESEXTANT_CSRF_GUARD`, on by
  default) so that a page in your browser cannot drive the local daemon. Turning
  that off is supported but means any website you visit can reach the API.
- **Indexes live in `~/.codesextant/`** as SQLite databases with normal user
  permissions. They contain symbol names and paths, not source text.
- **`ts_bridge/` runs Node** as a subprocess when resolving TypeScript. It
  parses your project files, so treat it with the same trust you give any tool
  that opens the repo.

Reports that reduce to "someone with full access to your user account can read
your files" are out of scope; a process at that privilege level can read the
repos directly.
