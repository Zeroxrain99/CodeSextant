# Security Policy

## Reporting a vulnerability

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/Zeroxrain99/CodeSextant/security/advisories/new)
rather than opening a public issue.

Expect an initial response within a week.

## Threat model

CodeSextant runs locally and makes no runtime network calls outside its loopback
daemon. The security boundary is the operating-system identity that owns
`~/.codesextant`:

- **The daemon listens only on `127.0.0.1`.** Loopback alone is not treated as
  authentication. API clients sign the HTTP method, exact request target,
  timestamp, nonce, and body digest with HMAC-SHA256. The long-lived secret
  never crosses HTTP, proofs expire, and each nonce can be used once.
- **Host validation blocks DNS rebinding.** Requests whose `Host` header does
  not identify the daemon's loopback address and port are rejected. No CORS
  access is granted to remote origins.
- **The browser dashboard does not receive the long-lived secret.**
  `codesextant gui` creates a 60-second, single-use bootstrap code. The browser
  exchanges it for a bounded in-memory session stored only in `sessionStorage`
  and sends that session in a custom header. It is not stored in a cookie,
  persistent browser storage, a final URL, or a log.
- **Browser writes require an exact same-origin `Origin`.** Signed native
  clients do not depend on browser Origin headers. Request bodies, pre-auth read
  time, concurrent handlers, heavy queues, and recovery followers are bounded.
- **A network response is never authority to terminate a PID.** Current daemons
  stop through a signed, graceful drain request. Legacy daemons fail closed and
  must be stopped through an independently verified process-management path.
- **Indexes are local cache files, not encrypted vaults.** They contain absolute
  paths, symbol and reference metadata, hashes, fingerprints, and extracted
  comments or docstrings. They do not contain complete source files. POSIX uses
  private directory and token modes. Windows follows the directory DACL so
  explicitly allowed local agent sandbox identities can share the index.
- **Automatic cache cleanup is narrow and quiescent.** It runs only after HTTP
  handlers and recovery work drain. Projects used by that daemon lifetime are
  excluded. Every SQLite or snapshot user also holds an OS-locked per-project
  lease. Cleanup takes that project's gate without waiting and skips any active
  or unverifiable holder, including a separate CLI process. Only exact
  project-key database groups and their known cache companions are candidates;
  credentials, logs, locks, and unknown files are preserved. Every candidate
  is contained and revalidated immediately before deletion, and unverifiable
  groups fail closed.
- **`ts_bridge/` runs Node as a subprocess** when resolving TypeScript. It reads
  project files and should receive the same trust as any local code-analysis
  tool.

A malicious process that can already read files as the owning OS identity, or
an identity explicitly allowed by the storage-directory ACL, can read both the
indexes and the signing secret. That native same-user case is outside the HTTP
authentication boundary.
