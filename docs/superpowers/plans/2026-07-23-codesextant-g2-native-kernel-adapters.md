---
tier: 全文
status: ready-for-execution
date: 2026-07-23
scope: CodeSextant G2 native kernel and semantic adapters
---

# CodeSextant G2 Native Kernel and Semantic Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Replace Python hot paths with a native Rust discovery, parsing, incremental indexing, storage, ranking, and query kernel while retaining reviewed Python behavior as the correctness oracle and shipping persistent Jedi and ts-morph semantic resolvers that require neither Python nor Node on the user's machine.

**Architecture:** The Rust core owns deterministic discovery, graph algorithms, analysis operations, cancellation, and confidence policy. codesextant-parser owns bundled tree-sitter grammars for the existing 16-language indexing surface. codesextant-store implements versioned SQLite transactions and crash recovery behind core traits. Two persistent semantic sidecars use one framed protocol: Jedi is packaged with PyInstaller, while ts-morph is an exhaustive onedir component containing a native Rust launcher, one esbuild bundle, and a private hash-locked official Node runtime. Release artifacts therefore need no preinstalled Python or Node. QueryService calls native components directly; sidecars are used only for high-confidence Python and TS/JS semantic resolution. Every public operation has a named oracle comparison and no implementation is accepted through a generic smoke test alone.

**Tech Stack:** Rust 1.96.0 edition 2024, Tokio, tokio-util, ignore matcher APIs, tree-sitter and pinned grammar crates, blake3, SHA-256, serde, serde_json, thiserror, tracing, SQLite, POSIX rustix and Windows windows-sys directory-handle traversal, Python 3.11 only as the reviewed oracle/build orchestrator, SHA-verified target-native CPython 3.14.6 with Jedi 0.20.0/parso 0.8.7/PyInstaller 6.21.0 as the embedded Python sidecar runtime, and a SHA-verified target-native official Node 24.18.0 onedir runtime with ts-morph 28.0.0, TypeScript 6.0.2, esbuild 0.28.1, and a native Rust launcher for the embedded TypeScript sidecar.

## Preconditions

- Complete G0/G1 foundation.
- G0-created tracked `tools/exact_task_commit.ps1` and `tests/release/test_exact_task_commit.py` exist unchanged; this plan sources the former and runs the latter rather than defining a second commit helper.
- Before Task 1, complete quality-contract Tasks 1 through 3 only. Task 1 supplies deterministic adapters/fixtures before the refreshed base oracle freeze.
- After Task 1, return to quality-contract Task 4 and freeze the refreshed base oracle, then complete quality-contract Tasks 5 through 9.
- Execute Tasks 2 through 12 here only after that base evidence commit, exact nine-package Rust workspace, generated contracts, envelopes, and transport shells exist.
- The worktree is clean at every task boundary.
- The public operation inventory is the 18 IDs in operations.yaml. This plan may not add a nineteenth operation or silently omit one.

## Global constraints

- Python production behavior remains available until all named oracle comparisons pass.
- Oracle writers are never invoked in CI. A new oracle adapter commit and its manifest/golden commit are separate and independently reviewable.
- After the quality-contract Task 4 base freeze, no task may edit a bound Python product, parity adapter, harness, oracle corpus/fixture, or oracle generator path.
- Discovery order, parser output, graph identities, ranking, and serialized query order are deterministic across runs.
- Release binaries never execute python, python3, py, node, npm, npx, pnpm, or bun from PATH.
- Release binaries locate sidecars only from the signed/checksummed installed component manifest next to the main executable.
- CodeSextant product binaries/crates/packages use Apache-2.0 from workspace/package metadata. Third-party parser, sidecar, runtime, dependency, and fixture licenses remain their original licenses and are copied into the component license inventory without alteration.
- A missing or failed semantic resolver lowers confidence or emits the declared resolver error; it never upgrades name matching to high confidence.
- Every request has an absolute parent deadline and cancellation token. Queues are bounded. No retry loop is unbounded.
- Index writes are atomic. Cancellation, parser failure, sidecar failure, or process termination cannot publish a partial revision.
- Every database/WAL/SHM, runtime, spill, analyzer snapshot, token, and cache path is a descendant of the owner-only no-follow StateRoot capability established in G0; native code reuses that validator and never creates state beside a repository or in an inherited-permission temp directory.
- Stage exact files only and use focused commits.

Before the first task commit in every fresh implementation shell, run the tracked helper's disposable-repository adversarial suite, then dot-source the same reviewed helper. Every commit block below passes only repository-relative leaf paths; the helper requires an initially empty index, enumerates complete cached and committed `--name-status`, accepts only exact `A`/`M` rows, and rejects deletions, renames, copies, type changes, unmerged rows, duplicates, or extra paths.

~~~powershell
$exactCommitHelper = Join-Path (Resolve-Path -LiteralPath '.').Path 'tools\exact_task_commit.ps1'
$exactCommitTests = Join-Path (Resolve-Path -LiteralPath '.').Path 'tests\release\test_exact_task_commit.py'
if (-not (Test-Path -LiteralPath $exactCommitHelper -PathType Leaf) -or -not (Test-Path -LiteralPath $exactCommitTests -PathType Leaf)) { throw 'G0 exact-task-commit helper/test prerequisite is missing' }
C:\Python311\python.exe -m pytest $exactCommitTests -q
if ($LASTEXITCODE -ne 0) { throw 'G0 exact-task-commit adversarial prerequisite failed' }
. $exactCommitHelper
if (-not (Get-Command Invoke-ExactTaskCommit -CommandType Function -ErrorAction SilentlyContinue)) { throw 'tracked exact-task-commit helper did not load' }
~~~

## Native ownership map

| Concern | Owner |
|---|---|
| deterministic repository discovery and classification parity | codesextant-core discovery |
| syntax parsing, symbols, comments, complexity primitives, structural fingerprints | codesextant-parser |
| schema migrations, files, symbols, edges, analyses, revisions, recovery | codesextant-store |
| requests, envelopes, errors, sidecar wire types | codesextant-protocol and codesextant-sidecar-protocol |
| graph ranking, reachability, health, policy, confidence | codesextant-core |
| Jedi and ts-morph semantic truth | packaged persistent sidecars |
| process supervision, queue limits, deadlines, cancellation | codesextant-daemon composition |
| CLI, MCP, HTTP framing | transport crates from the quality-contract plan |

## Exact dependency and feature authority

The exact serde, serde_json, thiserror, schemars, clap, tokio, axum, tower, getrandom, subtle, hex, and tempfile pins established by quality-contract Task 6 remain authoritative. The table below is the native dependency authority; its tokio and hex rows restate those same pins and exact feature sets rather than creating second declarations. Every new dependency uses an exact = pin in root workspace.dependencies; every crate uses dependency.workspace = true and enables no additional feature locally. Cargo.lock is staged in every native implementation task, and all Cargo build/test/metadata/run/clippy commands use --locked.

Each task that edits any Cargo manifest has exactly one controlled lockfile-update window after its complete manifest edit and before its first green Cargo command:

~~~powershell
cargo generate-lockfile
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath Cargo.lock -PathType Leaf)) { throw 'controlled native Cargo.lock generation failed' }
$lockStatus = @(git status --short -- Cargo.lock)
if ($lockStatus.Count -ne 1) { throw "unexpected Cargo.lock state: $($lockStatus -join '; ')" }
cargo metadata --locked --format-version 1 | Out-Null
cargo tree --locked -e normal -d
~~~

`cargo generate-lockfile` is the only unlocked Cargo command. The task reviews every changed package/checksum row against the exact authority table, rejects an unpinned or unexpected transitive package, duplicate `windows-sys`/runtime `tree-sitter`, or a lockfile that changes during any later `--locked` command, then stages that exact lock with the manifests.

~~~toml
ignore = { version = "=0.4.23", default-features = false }
blake3 = { version = "=1.8.2", default-features = false, features = ["std"] }
rustix = { version = "=1.1.4", default-features = false, features = ["std", "fs", "process"] }
tokio = { version = "=1.48.0", default-features = false, features = ["rt-multi-thread", "macros", "process", "io-util", "io-std", "sync", "time", "signal", "fs", "net"] }
tokio-util = { version = "=0.7.16", default-features = false, features = ["rt"] }
futures-util = { version = "=0.3.31", default-features = false, features = ["std", "async-await"] }
async-trait = { version = "=0.1.88", default-features = false }
bytes = { version = "=1.10.1", default-features = false, features = ["std"] }
tracing = { version = "=0.1.41", default-features = false, features = ["std", "attributes"] }
tracing-subscriber = { version = "=0.3.19", default-features = false, features = ["fmt", "env-filter", "json", "ansi"] }
dashmap = { version = "=6.1.0", default-features = false }
lru = { version = "=0.14.0", default-features = false }
parking_lot = { version = "=0.12.4", default-features = false }
sha2 = { version = "=0.10.9", default-features = false, features = ["std"] }
hex = { version = "=0.4.3", default-features = false, features = ["std"] }
yaml_serde = { version = "=0.10.4", default-features = false }
rusqlite = { version = "=0.40.1", default-features = false, features = ["bundled", "functions", "limits", "modern_sqlite"] }
tree-sitter = { version = "=0.25.8", default-features = false, features = ["std"] }
tree-sitter-python = { version = "=0.23.6", default-features = false }
tree-sitter-javascript = { version = "=0.23.1", default-features = false }
tree-sitter-typescript = { version = "=0.23.2", default-features = false }
tree-sitter-go = { version = "=0.23.4", default-features = false }
tree-sitter-rust = { version = "=0.23.2", default-features = false }
tree-sitter-c-sharp = { version = "=0.23.1", default-features = false }
tree-sitter-java = { version = "=0.23.5", default-features = false }
tree-sitter-c = { version = "=0.24.1", default-features = false }
tree-sitter-cpp = { version = "=0.23.4", default-features = false }
tree-sitter-kotlin = { package = "tree-sitter-kotlin-ng", version = "=1.1.0", default-features = false }
tree-sitter-swift = { version = "=0.7.1", default-features = false }
tree-sitter-php = { version = "=0.24.2", default-features = false }
tree-sitter-ruby = { version = "=0.23.1", default-features = false }
tree-sitter-bash = { version = "=0.25.0", default-features = false }
tree-sitter-lua = { version = "=0.2.0", default-features = false }
windows-sys = { version = "=0.61.2", default-features = false, features = ["Win32_Foundation", "Win32_Globalization", "Win32_Security", "Win32_Security_Authorization", "Win32_Storage_FileSystem", "Win32_System_JobObjects", "Win32_System_Memory", "Win32_System_SystemInformation", "Win32_System_Threading"] }
proptest = { version = "=1.7.0", default-features = false, features = ["std"] }
~~~

The Kotlin dependency name is a compatibility alias to package `tree-sitter-kotlin-ng` 1.1.0. Parser registration consumes `tree_sitter_kotlin::LANGUAGE` (a `LanguageFn`) via `.into()` against the single workspace `tree-sitter` 0.25.8 runtime; the older fwcd `tree-sitter-kotlin` crate is forbidden because it caps tree-sitter below 0.23 and creates an incompatible second `Language` type. Cargo-metadata tests require exactly one runtime `tree-sitter` version, reject the old package, and verify the Kotlin-ng package/license in lock, SBOM, and dependency-license fixtures.

The embedded/build sidecar pins are CPython 3.14.6, Jedi 0.20.0, parso 0.8.7, PyInstaller 6.21.0, Node 24.18.0 LTS, ts-morph 28.0.0 with its bundled TypeScript 6.0.2 compiler authority, build/dev-only TypeScript 6.0.2, and esbuild 0.28.1. The server never imports a second direct TypeScript runtime. Python requirements.lock includes --require-hashes for every transitive wheel/sdist; package-lock.json lockfileVersion 3 contains exact integrity hashes. `sidecars/toolchain.lock.json` binds the official target-native CPython and Node archive/source URL, target, SHA-256, upstream signature/checksum identity, packaged `sys.version`/SOABI/OpenSSL/SQLite and Node/V8/OpenSSL versions, and security-baseline observation UTC for all five release targets. Python 3.11 may invoke `sidecars/build.py` as an orchestrator only: that script must provision or locate the locked target-native CPython 3.14.6, verify its target/version/digest, create the build environment with that interpreter, install every hash-locked dependency, and invoke that interpreter's `python -m PyInstaller`; PyInstaller may never embed the 3.11 orchestrator. If any exact pin is unavailable, incompatible, digest-mismatched, or superseded by a security release before final freeze, stop and submit a reviewed plan/pin change; do not float a version, silently enable defaults, or ship the stale runtime.

---

### Task 1: Define explicit Python public-operation oracle adapters

**Dependencies:** Complete quality-contract Tasks 1 through 3; do not run quality-contract Task 4 yet.

**Files:**
- Create: tests/parity/python_public_oracle.py
- Create: tests/parity/public_operation_cases.py
- Create: tools/public_operation_oracle.py
- Test: tests/test_public_operation_oracle_harness.py
- Test: tests/test_public_operation_oracle_manifest.py
- Create: tests/parity/fixtures/repository/src/api.py
- Create: tests/parity/fixtures/repository/src/service.py
- Create: tests/parity/fixtures/repository/src/models.py
- Create: tests/parity/fixtures/repository/src/client.ts
- Create: tests/parity/fixtures/repository/tests/test_service.py
- Create: tests/parity/fixtures/repository/policy.yaml
- Create: tests/parity/fixtures/repository/tsconfig.json
- Create: tests/parity/corpora/languages/python.py
- Create: tests/parity/corpora/languages/javascript.js
- Create: tests/parity/corpora/languages/typescript.ts
- Create: tests/parity/corpora/languages/typescript.tsx
- Create: tests/parity/corpora/languages/go.go
- Create: tests/parity/corpora/languages/rust.rs
- Create: tests/parity/corpora/languages/csharp.cs
- Create: tests/parity/corpora/languages/java.java
- Create: tests/parity/corpora/languages/c.c
- Create: tests/parity/corpora/languages/cpp.cpp
- Create: tests/parity/corpora/languages/kotlin.kt
- Create: tests/parity/corpora/languages/swift.swift
- Create: tests/parity/corpora/languages/php.php
- Create: tests/parity/corpora/languages/ruby.rb
- Create: tests/parity/corpora/languages/bash.sh
- Create: tests/parity/corpora/languages/lua.lua

**Interfaces:**
- Consumes: immutable operations.yaml from quality Task 3, Python engine/daemon functions, isolated CODESEXTANT_HOME, fixed clock, and fixed request IDs.
- Produces: the deterministic repository/policy/language corpus before any G2 oracle freeze, PUBLIC_OPERATION_IDS, run_public_operation_case(), run_public_operation_snapshot(), canonical_public_json(), and guarded write/verify commands.

- [ ] **Step 1: Write the failing inventory test**

~~~python
def test_public_oracle_names_every_registry_operation():
    assert PUBLIC_OPERATION_IDS == {
        "service_health",
        "doctor",
        "status",
        "index",
        "symbols",
        "references",
        "call_graph",
        "map",
        "impact",
        "dead_code",
        "unwired",
        "duplicates",
        "comment_overview",
        "comment_tags",
        "comments",
        "ai_usage",
        "code_health",
        "discipline_evaluate",
    }
~~~

The harness test also rejects importing Rust code, calling a Rust binary, reading a developer database, wall-clock timestamps, random request IDs, and normalization of semantic fields. `test_public_oracle_runs_only_the_materialized_locked_child` starts red by placing an importable sentinel module and hostile `PYTHONPATH`/user-site package outside the repository, mutating the live checkout after the source commit is materialized, and requiring both generated runs to ignore those bytes. It asserts every executed CodeSextant/oracle module resolves beneath the owner-only materialized commit root, the interpreter/dependency/environment closure equals `requirements/oracle.lock`, and a live-worktree module, already-imported parent module, or ambient distribution makes generation fail rather than enter the manifest.

The repository fixture has fixed LF bytes, no generated timestamps, Python and TypeScript reference edges, duplicate structures, comments/tags, AI-usage evidence, an unused import, a re-export, and policy boundary values. The corpus closure also includes the frozen schema-v5 seed/expected fixtures created by quality Task 1. tests/test_public_operation_oracle_harness.py hashes the complete tests/parity/fixtures and tests/parity/corpora trees and runs the operation inputs twice from independent copies to prove byte-stable inputs.

- [ ] **Step 2: Run the test and observe red**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_public_operation_oracle_harness.py -q
~~~

Expected: collection FAIL because the public oracle modules do not exist.

- [ ] **Step 3: Implement each adapter explicitly**

public_operation_cases.py declares one callable per operation:

- service_health: Python daemon health projection with fixed process/runtime fields;
- doctor: Python install/config/database/resolver diagnostic projection;
- status: engine.status;
- index: engine.index_project with force true;
- symbols: engine.get_symbols;
- references: engine.find_references;
- call_graph: engine.call_hierarchy;
- map: engine.get_map with product scope and fixed budget;
- impact: engine.impact;
- dead_code: engine.find_deadcode;
- unwired: engine.find_unwired;
- duplicates: engine.find_duplicates;
- comment_overview: engine.get_comment_overview;
- comment_tags: engine.find_comment_tags;
- comments: engine.get_comments;
- ai_usage: engine.find_ai_usage;
- code_health: engine.get_health;
- discipline_evaluate: evaluate the checked-in tests/parity/fixtures/repository/policy.yaml using the Python policy evaluator used by the current discipline route.

Each adapter returns the canonical operation payload, warnings, and confidence inputs without transport framing. service_health, doctor, and discipline_evaluate are defined by explicit deterministic Python adapter functions over the existing daemon/config/store/policy primitives; their field lists and ordering are fixed in this commit before Rust implementation begins. No adapter calls a Rust binary or fills an absent value with a guessed Rust result.

tools/public_operation_oracle.py reuses—not approximates—the complete G1 oracle trust boundary. Write mode refuses CI, requires a clean worktree and `--source-commit` equal to HEAD, verifies `--adapter-source-commit` through Git history, then uses `materialize_tracked_regular_commit` to read only regular blobs from that exact commit into a newly created owner-only no-link root. A fresh sanitized `C:\Python311\python.exe -I` child executes that materialized commit's own `tools/public_operation_oracle.py --child` with `requirements/oracle.lock` and `tools/oracle_environment.py` as the executable/distribution/environment authority; the parent never imports or calls live adapter, product, registry, canonicalizer, or generator modules. The child refuses any executed module outside the materialized root, records every executed path/hash plus executable/platform/resolved-distribution closure, creates independent repository/home instances, and returns only canonical operation data and closure evidence. A deterministic barrier mutates the live checkout after materialization and proves output and executed-module hashes are unchanged. Output uses the G1 `prepare_new_output_staging`/fsync/atomic-publish boundary and rejects CI, existing/nonempty output, repository ancestors/descendants, links/reparse points, partial writes, and caller redirection.

tests/test_public_operation_oracle_manifest.py is committed before evidence. It accepts only two states: both manifest/golden absent, or both present and fully valid. In the present state it requires exactly 18 operation keys; resolvable adapter/generation commits; exact tracked regular-file source closure; recomputed adapter, harness, fixture/corpus, registry, base product, generator, version, and golden hashes; locked executable/platform/resolved-distribution environment closure; executed-module paths/hashes confined to the materialized root; valid commit relationships; and no private absolute path. Table-driven tamper tests alter every environment, executed-module, tracked-entry, source-tree, and golden field and require failure.

- [ ] **Step 4: Run the harness**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_public_operation_oracle_harness.py tests/test_public_operation_oracle_manifest.py -q
C:\Python311\python.exe -m ruff check tests/parity tools/public_operation_oracle.py
~~~

Expected: all tests pass without creating a manifest or golden.

- [ ] **Step 5: Commit oracle adapter source only**

~~~powershell
$expectedStaged = @('tests/parity/python_public_oracle.py','tests/parity/public_operation_cases.py','tools/public_operation_oracle.py','tests/test_public_operation_oracle_harness.py','tests/test_public_operation_oracle_manifest.py','tests/parity/fixtures/repository/src/api.py','tests/parity/fixtures/repository/src/service.py','tests/parity/fixtures/repository/src/models.py','tests/parity/fixtures/repository/src/client.ts','tests/parity/fixtures/repository/tests/test_service.py','tests/parity/fixtures/repository/policy.yaml','tests/parity/fixtures/repository/tsconfig.json','tests/parity/corpora/languages/python.py','tests/parity/corpora/languages/javascript.js','tests/parity/corpora/languages/typescript.ts','tests/parity/corpora/languages/typescript.tsx','tests/parity/corpora/languages/go.go','tests/parity/corpora/languages/rust.rs','tests/parity/corpora/languages/csharp.cs','tests/parity/corpora/languages/java.java','tests/parity/corpora/languages/c.c','tests/parity/corpora/languages/cpp.cpp','tests/parity/corpora/languages/kotlin.kt','tests/parity/corpora/languages/swift.swift','tests/parity/corpora/languages/php.php','tests/parity/corpora/languages/ruby.rb','tests/parity/corpora/languages/bash.sh','tests/parity/corpora/languages/lua.lua')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'test(oracle): define all public operation adapters'
~~~

Do not generate or stage public-operation manifest/golden files in this commit.

Return to quality-contract Task 4 now, then complete quality-contract Tasks 5 through 9. Do not execute Task 2 until the refreshed base oracle evidence commit and those workspace/contract/transport commits all exist.

---

### Task 2: Freeze the public-operation oracle in an evidence-only commit

**Dependencies:** Task 1; quality-contract Task 4 base oracle evidence committed and clean; quality-contract Tasks 5 through 9 complete so the exact workspace/contracts/envelopes/transport shells are the generation commit.

**Files:**
- Create: tests/fixtures/public-operation-oracle-manifest.json
- Create: tests/parity/golden/python-public-operations-v1.json

**Interfaces:**
- Consumes: clean generation commit, Task 1 adapter-source commit, tests/fixtures/oracle-manifest.json, deterministic repository/policy/language corpus, operation registry, generator, materialized-commit versions, and the hash-locked oracle environment.
- Produces: a format-version 2 reviewed public-operation manifest with full tree recomputation and explicit adapter/generation/evidence commit relationships.

- [ ] **Step 1: Observe missing evidence**

~~~powershell
C:\Python311\python.exe tools/public_operation_oracle.py --verify
~~~

Expected: exit 1 and no files created.

- [ ] **Step 2: Generate twice in independent output roots**

~~~powershell
if (git status --porcelain) { throw "public oracle source commit is dirty" }
$generationCommit = git rev-parse HEAD
$adapterCommit = git log -1 --format=%H -- tests/parity/python_public_oracle.py tests/parity/public_operation_cases.py tools/public_operation_oracle.py tests/parity/fixtures tests/parity/corpora
$runA = Join-Path 'C:\Temp' ("codesextant-public-oracle-a-" + [guid]::NewGuid())
$runB = Join-Path 'C:\Temp' ("codesextant-public-oracle-b-" + [guid]::NewGuid())
try {
    C:\Python311\python.exe tools/public_operation_oracle.py --write --source-commit $generationCommit --adapter-source-commit $adapterCommit --output-root $runA
    C:\Python311\python.exe tools/public_operation_oracle.py --write --source-commit $generationCommit --adapter-source-commit $adapterCommit --output-root $runB
    git diff --no-index --exit-code -- $runA $runB
    if ($LASTEXITCODE -ne 0) { throw "independent public oracle outputs differ" }
    Copy-Item -LiteralPath (Join-Path $runA 'tests\fixtures\public-operation-oracle-manifest.json') -Destination tests\fixtures\public-operation-oracle-manifest.json
    Copy-Item -LiteralPath (Join-Path $runA 'tests\parity\golden\python-public-operations-v1.json') -Destination tests\parity\golden\python-public-operations-v1.json
} finally {
    Remove-Item -LiteralPath $runA,$runB -Recurse -Force -ErrorAction SilentlyContinue
}
~~~

Each invocation uses an independent materialized commit, isolated locked child interpreter, repository copy, and CODESEXTANT_HOME directory. The manifest requires format_version 2, adapter_source_commit, generation_source_commit, tracked_commit_tree, bound_paths, environment, executed_modules, adapter_source_tree_sha256, harness_tree_sha256, fixture_corpus_tree_sha256, operations_registry_tree_sha256 over both spec/operations.yaml and spec/operations.schema.json, base_oracle_manifest_sha256, base_product_source_tree_sha256, generator_tree_sha256, package/engine/schema versions, and golden SHA-256. The golden has exactly 18 operation keys.

Verification reconstructs every historical field from the materialized generation commit and separately recomputes the current bound-file closure without importing it. It invokes the base oracle verifier/selectors to recompute the complete Python product, parity-source, harness/adapter, corpus, generator, version, golden, locked environment, and executed-module closure before accepting base_oracle_manifest_sha256 or base_product_source_tree_sha256; it never trusts an embedded base hash alone. Current bound paths must equal the historical path/mode/size/hash table and be free of staged/unstaged/untracked drift. It requires adapter_source_commit to be the last commit touching any adapter/fixture/corpus/generator input, requires it to be an ancestor of generation_source_commit, requires the refreshed base oracle evidence commit to be an ancestor of generation_source_commit, and after evidence commit requires that commit's first parent to equal generation_source_commit and changed paths to be only the public manifest/golden.

- [ ] **Step 3: Review and verify**

~~~powershell
git diff -- tests/fixtures/public-operation-oracle-manifest.json tests/parity/golden/python-public-operations-v1.json
C:\Python311\python.exe tools/public_operation_oracle.py --verify-output-root . --expected-source-commit $generationCommit --precommit
C:\Python311\python.exe -m pytest tests/test_public_operation_oracle_harness.py -q
~~~

Expected: all precommit recomputation passes, no operation is missing, and the base oracle/product source hashes equal the reviewed G2 manifest. Only the evidence-parent assertion is deferred.

- [ ] **Step 4: Commit only evidence**

~~~powershell
$expectedStaged = @('tests/fixtures/public-operation-oracle-manifest.json','tests/parity/golden/python-public-operations-v1.json')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'test(oracle): freeze all public operation outputs'
~~~

~~~powershell
C:\Python311\python.exe tools/public_operation_oracle.py --verify
C:\Python311\python.exe -m pytest tests/test_public_operation_oracle_manifest.py tests/test_public_operation_oracle_harness.py -q
~~~

Expected: full recomputation and adapter/generation/evidence relationships pass. All subsequent parity tasks consume this evidence commit and the G2 base oracle.

---

### Task 3: Implement native deterministic discovery and classification parity

**Dependencies:** Task 2.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-core/Cargo.toml
- Create: crates/codesextant-core/src/discovery.rs
- Create: crates/codesextant-core/src/ignore_policy.rs
- Create: crates/codesextant-core/src/source_class.rs
- Create: crates/codesextant-core/src/path.rs
- Modify: crates/codesextant-core/src/lib.rs
- Test: crates/codesextant-core/tests/discovery_parity.rs
- Test: crates/codesextant-core/tests/discovery_security.rs

**Interfaces:**
- Consumes: AccessScope-authorized repository root, immutable SourceBlob copies of every in-scope .gitignore/.ignore/CodeSextant exclude policy, supported extension table, public symbol hints, and cancellation token.
- Produces: DiscoveryConfig, immutable SourceBlob, DiscoveredFile, SourceClass, ClassificationEvidence, discover_repository(), normalize_relative_path(), and discovery digest.

**Dependency closure:** Root Cargo.toml adds exactly ignore, blake3, and POSIX-target-only rustix from the authority table; codesextant-core/Cargo.toml consumes them with workspace = true and no local feature overrides. The ignore crate is used only to compile already-captured policy lines; it performs no walking or policy-file I/O. Rustix supplies reviewed no-follow/openat-style directory-handle enumeration and reads on POSIX; Windows uses the existing target-specific windows-sys authority for directory-handle enumeration, reparse rejection, and file-identity checks. Cargo.lock is regenerated and staged in this task.

- [ ] **Step 1: Write failing parity and security tests**

discovery_parity.rs runs Python discovery and Rust discovery over the same corpus and compares:

- normalized relative path;
- source class;
- classification rule ID;
- public API evidence;
- file length;
- content BLAKE3;
- deterministic ordinal.

Security tests reject traversal outside root, symlink escape, invalid UTF-8 path loss, device files, sockets, files larger than configured maximum, and cancellation after a fixed file count. Tests include nested .gitignore negation, hidden source, Windows case behavior, Unix case behavior, and a symlink loop. Parent-directory `.gitignore`, symlinked `.gitignore`/`.ignore`, linked-worktree `.git` files that point to an external gitdir, global excludes, and swap-after-policy-load fixtures place unique sentinels outside AccessScope and prove neither walker nor matcher opens or reads them. A symlinked or unstable in-scope policy is a fail-closed discovery error, not silently skipped. State-root tests place CODESEXTANT_HOME, DB/WAL/SHM, runtime, spill, and analyzer-snapshot directories inside the repository through direct, case/Unicode, symlink, junction, and file-ID aliases; state equal to repository is rejected, descendants are unconditionally pruned, user `!` rules cannot reinclude them, and zero state path names/bytes enter discovery digest/facts/output. A many-max-sized-files fixture stalls the parser consumer and asserts the measured in-memory blob high-water/RSS stays below the configured aggregate budget, permits return on cancellation/failure, and the old revision remains published. Deterministic barriers at policy load, open, hash, classification, parse handoff, semantic handoff, and publish replace/truncate/delete/rename or link-swap a source/config/policy; the only valid outcome is the complete old revision or a hash/facts-consistent new revision, never a contaminated fact key or out-of-scope byte.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
cargo test --locked -p codesextant-core --test discovery_parity
cargo test --locked -p codesextant-core --test discovery_security
~~~

Expected: FAIL because native discovery does not exist.

- [ ] **Step 3: Implement one deterministic walker**

Implement one incremental walker rooted in an AccessScope-authorized directory handle; do not use `ignore::WalkBuilder`, `walkdir`, or any path-based recursive enumerator. POSIX enumeration and reads stay relative to retained rustix directory handles; Windows enumeration and reads stay relative to verified directory handles and reject every reparse point. Before descending into each directory, the walker securely probes the known `.gitignore`/`.ignore` candidates through AccessScope, captures stable ones as SourceBlobs, compiles only their in-memory lines through `ignore::gitignore::GitignoreBuilder::add_line` with an explicit in-scope base, pushes that matcher frame, evaluates/prunes sorted child entries, then pops on exit. No ignore API may autonomously discover or open parent, global, repository, or per-directory policy. This preserves nested precedence/negation without ever walking ignored `node_modules`/vendor subtrees merely to discover policy. Root CodeSextant config is parsed from its blob. Parent policy is accepted only when its parent root and policy file were explicitly granted at bootstrap. Before user policy, bootstrap compares canonical handles/file identities for repository and the validated StateRoot; equality is rejected, and every state-root descendant is installed as a highest-precedence non-overridable hard exclusion. The policy blob hashes, hard-exclusion identities, and ordered matcher stack are part of discovery/analysis contracts. Normalize separators to slash for identity while retaining a scope-checked relative locator. Discovery is two-phase and never collects repository-sized bytes in memory: deterministic metadata/path enumeration is followed by a bounded producer/consumer pipeline with a weighted byte semaphore, bounded channel, explicit aggregate in-memory high-water, and a private content-addressed spill area when the semantic closure must outlive a batch. Each source is opened once through the authorized root directory handle with no-follow/reparse rejection and bounded-read into an immutable logical `SourceBlob` (owned bytes or a hash-verified immutable spill handle); content BLAKE3, byte length, classification evidence, tree-sitter parse, semantic snapshot materialization, and later receipt hashing consume that same logical blob and never reopen the live path. Permits are RAII-released on success, cancellation, panic, and parse/store failure. Pre/post open-handle file ID/type/size plus path identity are rechecked; replace/truncate/short-read instability aborts or retries within a fixed bound and can never publish. Sort by normalized relative path before assigning ordinals.

Classification reproduces the Python precedence from G2 Task 1. It must return unknown when evidence is insufficient. Check cancellation before directory expansion, before hashing, and after each file.

The discovery digest is BLAKE3 over the ordered policy-blob path/hash/base tuples plus length-prefixed normalized source path, source class, immutable SourceBlob length, and content hash in ordinal order. IndexReceipt binds every policy and source digest plus any unstable-source retry/error; a bundle is rehashed against its SourceBlob before publish and a contaminated bundle is never published or reusable.

- [ ] **Step 4: Run parity twice**

~~~powershell
cargo test --locked -p codesextant-core --test discovery_parity -- --nocapture
cargo test --locked -p codesextant-core --test discovery_security
cargo test --locked -p codesextant-core --test discovery_parity -- --nocapture
~~~

Expected: both parity runs produce the same digest and all tests pass.

- [ ] **Step 5: Commit native discovery**

~~~powershell
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-core/Cargo.toml','crates/codesextant-core/src/discovery.rs','crates/codesextant-core/src/ignore_policy.rs','crates/codesextant-core/src/source_class.rs','crates/codesextant-core/src/path.rs','crates/codesextant-core/src/lib.rs','crates/codesextant-core/tests/discovery_parity.rs','crates/codesextant-core/tests/discovery_security.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(core): add deterministic native discovery'
~~~

---

### Task 4: Implement the bundled 16-language parser registry

**Dependencies:** Task 3.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-parser/Cargo.toml
- Create: crates/codesextant-parser/src/language.rs
- Create: crates/codesextant-parser/src/registry.rs
- Create: crates/codesextant-parser/src/symbols.rs
- Create: crates/codesextant-parser/src/comments.rs
- Create: crates/codesextant-parser/src/complexity.rs
- Create: crates/codesextant-parser/src/fingerprint.rs
- Modify: crates/codesextant-parser/src/lib.rs
- Test: crates/codesextant-parser/tests/language_registry.rs
- Test: crates/codesextant-parser/tests/python_oracle.rs
- Test: crates/codesextant-parser/tests/parser_limits.rs
- Verify without modification: tests/parity/corpora/languages

**Interfaces:**
- Consumes: bytes, extension, normalized path, parser limits, and cancellation token.
- Produces: LanguageId, ParseOutput, SymbolFact, CommentFact, ComplexityFact, StructuralFingerprint, ParserRegistry, and parse_file().

**Dependency closure:** Root Cargo.toml adds tree-sitter and every listed grammar crate at the exact authority-table versions. codesextant-parser/Cargo.toml consumes only those workspace dependencies plus already-authoritative serde/thiserror; no grammar is optional, dynamically downloaded, or feature-expanded locally. Cargo.lock is regenerated and staged.

- [ ] **Step 1: Write failing exact-language tests**

The registry must expose exactly:

~~~text
Python, JavaScript, TypeScript, TSX, Go, Rust, CSharp, Java,
C, Cpp, Kotlin, Swift, PHP, Ruby, Bash, Lua
~~~

Every language fixture asserts Python-oracle parity for symbol name, kind, start/end line, parent, visibility evidence, comments/tags, supported complexity value or explicit unknown reason, and structural fingerprint. Registry tests reject extension aliases not present in Python SUPPORTED_EXTENSIONS. The Kotlin case specifically constructs the grammar as `tree_sitter_kotlin::LANGUAGE.into()`. A Cargo-metadata/`cargo tree -d` assertion requires exactly one non-dev runtime `tree-sitter` package at 0.25.8, requires package `tree-sitter-kotlin-ng` 1.1.0 under the compatibility alias, and rejects package `tree-sitter-kotlin` entirely.

parser_limits.rs covers maximum bytes, maximum syntax nodes, maximum depth, tree-sitter QueryCursor match/capture limits, per-file symbol/comment/complexity/fingerprint/output-byte caps, invalid bytes, parse timeout/cancellation, malformed source, a stack-adversarial nested fixture, and a small query-capture-explosion fixture. It requires `did_exceed_match_limit()` handling, stable PARSER_LIMIT, zero partial facts/revision publication, and permit cleanup.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
cargo test --locked -p codesextant-parser --test language_registry
cargo test --locked -p codesextant-parser --test python_oracle
cargo test --locked -p codesextant-parser --test parser_limits
~~~

Expected: FAIL because the registry and extractors do not exist.

- [ ] **Step 3: Add pinned grammar crates and registry**

Add tree-sitter plus the grammar crates for the exact 16 languages to workspace dependencies and Cargo.lock. Each LanguageSpec owns extensions, grammar factory, definition queries, comment queries, visibility rules, complexity rules, and fingerprint normalization. Grammar objects are lazily initialized once and never loaded from system paths.

Do not call an external parser executable. The release binary statically links or bundles the grammar libraries selected by Cargo features. Feature set default-languages contains all 16 existing languages; minimal builds are development-only and cannot produce release artifacts.

- [ ] **Step 4: Implement bounded iterative extraction**

Parse bytes once per file. Traverse iteratively, not recursively, with node/depth counters and cancellation checks every 256 nodes. Every QueryCursor receives explicit match/capture limits; `did_exceed_match_limit()` is checked before accepting results. Derive symbols, comments, complexity primitives, and fingerprints from the same tree while enforcing independent fact-count and serialized-output-byte caps. A recoverable syntax error emits ParseWarning and partial facts with confidence reason syntax_recovery; any syntax/query/capture/fact/output hard limit emits stable PARSER_LIMIT, drops the entire file analysis, releases weighted permits, and permits no partial store publication.

- [ ] **Step 5: Run the full parser suite**

~~~powershell
cargo test --locked -p codesextant-parser
cargo clippy --locked -p codesextant-parser --all-targets -- -D warnings
~~~

Expected: all 16 language fixtures and limit tests pass.

- [ ] **Step 6: Commit bundled parsers**

~~~powershell
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-parser/Cargo.toml','crates/codesextant-parser/src/language.rs','crates/codesextant-parser/src/registry.rs','crates/codesextant-parser/src/symbols.rs','crates/codesextant-parser/src/comments.rs','crates/codesextant-parser/src/complexity.rs','crates/codesextant-parser/src/fingerprint.rs','crates/codesextant-parser/src/lib.rs','crates/codesextant-parser/tests/language_registry.rs','crates/codesextant-parser/tests/python_oracle.rs','crates/codesextant-parser/tests/parser_limits.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(parser): bundle native sixteen-language extraction'
~~~

---

### Task 5: Implement atomic incremental indexing and versioned recovery

**Dependencies:** Tasks 3 and 4.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-core/Cargo.toml
- Modify: crates/codesextant-store/Cargo.toml
- Modify: crates/codesextant-core/src/query_service.rs
- Create: crates/codesextant-core/src/index.rs
- Create: crates/codesextant-core/src/store.rs
- Modify: crates/codesextant-core/src/lib.rs
- Create: crates/codesextant-store/migrations/0006_native_revision.sql
- Create: crates/codesextant-store/src/migration.rs
- Create: crates/codesextant-store/src/revision.rs
- Create: crates/codesextant-store/src/recovery.rs
- Modify: crates/codesextant-store/src/schema.rs
- Modify: crates/codesextant-store/src/store.rs
- Modify: crates/codesextant-store/src/lib.rs
- Test: crates/codesextant-store/tests/incremental_index.rs
- Test: crates/codesextant-store/tests/crash_recovery.rs
- Test: crates/codesextant-store/tests/multiprocess_publish.rs
- Test: crates/codesextant-store/tests/migration_parity.rs
- Test: crates/codesextant-store/tests/migration_rollback.rs
- Test: crates/codesextant-store/tests/schema_authority.rs
- Modify: crates/codesextant-store/tests/schema_migration.rs
- Modify: crates/codesextant-store/tests/python_oracle.rs
- Verify without modification: tests/parity/test_schema_v5_python_rust.py

**Interfaces:**
- Consumes: shared Python schema v5, the deterministic immutable SourceBlob discovery stream, ParseOutput, and revision-bound semantic outputs created from those same blobs.
- Produces: native schema version 6, GraphStore trait, AnalysisContract, IndexPlan with `base_published_revision`, IndexRevision, ChangeSet, IndexReceipt, separately keyed path-independent syntax bundles and resolution-context-bound semantic bundles/Merkle snapshot roots, ReaderEpoch, begin_revision(), compare-and-swap publish_revision(), abort_revision(), retire_revisions(), collect_garbage(), recover().

**Dependency closure:** Root Cargo.toml updates the existing rusqlite pin to the exact authority-table feature set bundled/functions/limits/modern_sqlite and adds no alternative SQLite driver. codesextant-store consumes rusqlite from the workspace; codesextant-core consumes only its store trait boundary. Cargo.lock and both crate manifests are staged together.

- [ ] **Step 1: Write failing incremental and crash tests**

incremental_index.rs proves:

- first index parses every supported file;
- unchanged second index parses zero files and preserves revision content digest;
- one edited file reparses one file plus only declared reverse-dependency invalidations;
- deleted and renamed files remove stale symbols/edges;
- source-class change updates map eligibility;
- output is identical between full rebuild and equivalent incremental history.
- 100 unchanged reindexes parse zero files, reuse the exact published revision/root, and keep fact/node/revision row counts plus database page growth within a fixed no-op budget;
- changed revisions write only changed content-addressed fact bundles and O(changed paths * tree depth) snapshot nodes rather than copying every unchanged fact.
- with repository bytes held identical, mutating each parser grammar/query digest, parser-registry schema, discovery/classification/config/policy rule digest, fingerprint parameter digest, semantic-resolver component/protocol/environment-policy digest, or resolution-input digest in turn forces a new revision and reparses or re-resolves exactly the affected language/file set; a second run under that same changed contract is again a zero-write no-op;
- identical source bytes at two normalized paths with different relative-import targets produce one reusable syntax bundle but distinct correct semantic bundles; changing a dependency export, renaming/moving a module, or changing a tsconfig/pyproject alias while leaving the importer bytes unchanged creates a new semantic context key, and incremental output equals a clean full rebuild followed by a zero-write second run.
- unresolved imports persist negative lookup dependencies; missing-to-added/deleted targets, Python `__init__.py`, JS/TS `index` candidates, package exports/types, tsconfig paths, and case-only rename fixtures invalidate unchanged importers, equal a full rebuild, and immediately return to zero-write reuse.

crash_recovery.rs injects termination after discovery, after parsing, during staging writes, before publish, after publish marker, and at every retired-generation GC batch. Reopening must expose either the complete old revision or complete new revision, never a mix. A long-lived ReaderEpoch begun before publish continues to see the old snapshot while a new reader sees the new one; the retired generation remains while that reader is pinned, becomes collectible after release, and is pruned without touching the current published root. A crash during GC always leaves a valid published pointer and every root reachable from it.

Cancel/publish barriers exercise the shared linearization machine `Active -> Cancelled` or `Active -> Committing -> Committed` (with bounded Failed cleanup). Cancellation atomically wins only from Active and then fences/aborts staging. Publish atomically wins Active→Committing before opening its final bounded transaction, rechecks writer epoch/state, and becomes non-cancellable only for that transaction. If commit wins, the response reports the committed revision even if cancellation arrives later; it never returns a false CANCELLED for a committed pointer. Barriers immediately before/after the state CAS and SQL COMMIT prove envelope and pointer always agree.

`multiprocess_publish.rs` launches true child processes, not tasks sharing one connection. Two writers plan from the same `base_published_revision`, then deterministic barriers reverse their publish order. Exactly one pointer compare-and-swap succeeds; the loser receives an internal `PublishConflict` control result, aborts its staging root, and IndexCoordinator rediscover/replans under a fixed attempt budget and the original absolute deadline before it may publish from the new base. `PublishConflict` never crosses QueryService or any transport; retry exhaustion maps to the already-declared public `INDEX_STALE` error. Additional cases kill the lease owner, simulate PID reuse with a different process-start/boot identity, resume a paused old owner after takeover, run concurrent GC, cancel a writer, and prove monotonic current content, permanent fencing, no stale overwrite, no leaked staging root, and bounded lease recovery. The pointer CAS is mandatory even when a lease is held.

migration_parity.rs opens a copied Python schema-v5 database with persisted classification evidence, migrates v5 to native v6 once, verifies every legacy row/identity/classification field, reopens idempotently, and refuses a future schema version without mutation. migration_rollback.rs injects failure after each v6 table/index/copy/publish stage and requires a readable unchanged v5 database.

schema_authority.rs starts red unless `crates/codesextant-store/src/schema.rs` is the sole executable schema-version registry. It requires the bootstrap baseline to report version 5, the current native store to report version 6, a new empty database to finish at version 6, v4 to traverse the historical v4-to-v5 migration and then v5-to-v6, v5 to run only v5-to-v6, and v6 to reopen without mutation. It rejects a future version and malformed/missing version evidence without mutation, and it fails if any creation, open, migration, doctor, or compatibility path still embeds an independent current-version literal of 4 or 5.

Store open mode is explicit. `ReadOnly` performs owner/state/identity/schema validation with SQLite read-only flags and no mutable PRAGMA, migration, journal recovery, WAL creation, or bulk daemon-startup upgrade. On a valid v5 database, project read operations return declared UPGRADE_REQUIRED unless a proven compatibility view satisfies that exact operation; on a valid future version they return DATABASE_VERSION_UNSUPPORTED; malformed versions return DATABASE_CORRUPT. The copied-byte suite invokes every applicable read-only operation plus doctor against v5/future/malformed DBs and proves no DB/WAL/SHM/journal mutation. Only `index` may acquire the writer lease/fencing epoch and enter `WriterMigration` to migrate v5 once. Cancel/failure at each migration stage preserves readable v5; immediate reindex after successful migration is stable.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
cargo test --locked -p codesextant-store --test incremental_index
cargo test --locked -p codesextant-store --test crash_recovery
cargo test --locked -p codesextant-store --test multiprocess_publish
cargo test --locked -p codesextant-store --test migration_parity
cargo test --locked -p codesextant-store --test migration_rollback
cargo test --locked -p codesextant-store --test schema_authority
~~~

Expected: FAIL because native revisions and recovery do not exist.

- [ ] **Step 3: Implement staged revisions**

`crates/codesextant-store/src/schema.rs` is the sole executable schema-version registry. It preserves v4 only as historical input, includes schema_v5.sql as the bootstrap/classification baseline, registers 0006_native_revision.sql as the v5-to-v6 edge, and exports `bootstrap_schema_version() -> 5` plus `current_schema_version() -> 6`. New-database creation, read-only open, writer migration, doctor, compatibility checks, and recovery all consume this registry; none owns an independent current-version literal. 0006_native_revision.sql consumes schema_v5.sql as the shared baseline; version 5 is classification persistence and version 6 adds native revisions without duplicating unchanged facts. The store uses WAL, foreign_keys on, busy_timeout, synchronous full for revision publish, and explicit transactions. A canonical `analysis_contract_sha256` is computed from a schema-versioned JCS document containing the parser registry and every grammar/query byte hash, discovery/classification/config/ignore-policy blob hash, fingerprint algorithm/parameter hash, semantic-resolver component/protocol/environment-policy/launcher-policy/runtime/bundle hash, and analyzer-snapshot format hash. Path-independent syntax analysis is stored in immutable bundles keyed by source-content digest plus the applicable syntax-analyzer contract. Contextual semantic facts are separate immutable bundles keyed by strong project/scope identity, normalized path, source digest, resolver contract, and a deterministic resolution-context digest covering the exact config/alias/module graph and dependency-export closure observed in the revision-bound analyzer snapshot. The context persists positive and negative resolution dependencies: resolved targets plus every unresolved lookup key, searched virtual directory/manifest/alias/package export/types candidate, and case-normalized name attempted. Addition/deletion/rename of a formerly missing target, `__init__`/`index` candidate, exports/types field, tsconfig path, or package metadata invalidates subscribers even when importer bytes are unchanged. Reverse-dependency invalidation must calculate a new context key; it may never reuse an old semantic bundle merely because importer bytes are unchanged. Immutable snapshot/Merkle nodes map normalized paths to the paired syntax/semantic bundle digests and structurally share only context-compatible subtrees. A revision row binds both the global analysis-contract digest and snapshot-root digest and progresses staging to published, retired, or aborted. Facts do not carry a per-revision copy. Readers acquire a ReaderEpoch at request start, bind one published revision/root and its analysis contract inside a SQLite read snapshot, and release the epoch after the response.

IndexPlan compares size and mtime only as hints, BLAKE3 from the immutable SourceBlob as content authority, the stored relevant analyzer-contract digest as syntax authority, and the resolution-context digest as semantic authority. Content hash equality skips parsing only when the applicable syntax digest matches; it skips semantic resolution only when the path/project/scope/resolver/context tuple also matches. Every plan binds `base_published_revision` and the current writer fencing epoch. Returning the existing published revision with zero revision/membership/fact/tree writes requires both the complete repository content root and global `analysis_contract_sha256` to match. A changed contract creates a new revision, reanalyzes only files whose applicable parser/query/classifier/fingerprint/resolver/context inputs changed, and may structurally share unaffected compatible bundles/subtrees. Changed files create/reuse only analyzer-compatible content-addressed bundles and the Merkle path nodes needed for changed/deleted/renamed paths; unchanged compatible subtrees are referenced, never copied. Every staging mutation predicates on current holder+fencing epoch. Publish marks the staged revision and atomically executes `UPDATE project_pointer SET current_revision = ? WHERE current_revision = ? AND writer_epoch = ?` against the bound base/epoch in one transaction, requires exactly one affected row, and otherwise rolls back with internal `PublishConflict`; a stale or fenced plan can never be last-writer-wins.

After publish, the old generation becomes retired. `retire_revisions`/`collect_garbage` retain the current published generation, one rollback generation, and every generation held by an active ReaderEpoch; only unreachable content-addressed nodes/facts are deleted, in bounded transactions. Reader epochs are process-unique and tied to actual live read guards rather than caller assertions. The cross-process writer lease carries a random UUID plus PID, process-start identity, boot identity, heartbeat, bounded expiry, and a monotonically increasing fencing epoch acquired under `BEGIN IMMEDIATE`; ownership and recovery are PID-reuse-safe. Every staging, retirement, and GC transaction predicates on current holder+epoch, so takeover permanently fences an old paused process. The lease never replaces pointer CAS. `recover()` deletes abandoned staging roots, clears only provably stale writer-owned leases, resumes idempotent reachability GC under a current fencing epoch, and validates the published pointer/root before and after every batch. It never guesses that staging or GC is complete and never deletes a root reachable from the published pointer or a live reader.

- [ ] **Step 4: Add cancellation and parser failure atomicity**

IndexCoordinator carries the immutable SourceBlob stream from policy load through discovery, hash, parse, semantic-snapshot materialization, sidecar resolution, staging, and receipt; no phase reopens the live path for content. It checks cancellation and deterministic race barriers between each phase, content-addressed store batches, snapshot-node updates, CAS publish, and GC batches. Any cancellation, deadline, unstable blob/policy/config, parser/sidecar/resource limit, database error, or panic boundary while state is Active atomically transitions to Cancelled, aborts the revision, and returns the declared error. Publish must win the shared Active→Committing CAS, revalidate writer epoch/base, run one bounded non-cancellable SQLite transaction, then return Committed; cancellation after that CAS cannot change the envelope. A CAS/epoch miss yields internal `PublishConflict`; the coordinator aborts, rediscover/replans within the fixed retry/deadline budget, and exposes only declared `INDEX_STALE` if exhausted. A post-publish GC failure leaves the new published revision valid and reports deferred cleanup without rolling the pointer backward. IndexReceipt includes every policy/config/source blob digest, resolution-context digest, writer epoch, files_discovered, files_hashed, files_parsed/resolved/reused/deleted, syntax/semantic facts created/reused, snapshot nodes created/reused, rows/pages before/after, warnings, base/old/new revision, snapshot-root digest, content digest, global `analysis_contract_sha256`, and the changed analyzer-input digests that justified targeted reanalysis.

- [ ] **Step 5: Run store and oracle parity**

~~~powershell
cargo test --locked -p codesextant-store
cargo test --locked -p codesextant-store --test multiprocess_publish
cargo test --locked -p codesextant-store --test schema_authority
cargo test --locked -p codesextant-core --test discovery_parity
C:\Python311\python.exe -m pytest tests/parity/test_schema_v5_python_rust.py -q
cargo clippy --locked -p codesextant-core -p codesextant-store --all-targets -- -D warnings
~~~

Expected: all commands exit 0.

- [ ] **Step 6: Commit the incremental kernel**

~~~powershell
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-core/Cargo.toml','crates/codesextant-store/Cargo.toml','crates/codesextant-core/src/index.rs','crates/codesextant-core/src/store.rs','crates/codesextant-core/src/query_service.rs','crates/codesextant-core/src/lib.rs','crates/codesextant-store/migrations/0006_native_revision.sql','crates/codesextant-store/src/migration.rs','crates/codesextant-store/src/revision.rs','crates/codesextant-store/src/recovery.rs','crates/codesextant-store/src/schema.rs','crates/codesextant-store/src/store.rs','crates/codesextant-store/src/lib.rs','crates/codesextant-store/tests/incremental_index.rs','crates/codesextant-store/tests/crash_recovery.rs','crates/codesextant-store/tests/multiprocess_publish.rs','crates/codesextant-store/tests/migration_parity.rs','crates/codesextant-store/tests/migration_rollback.rs','crates/codesextant-store/tests/schema_authority.rs','crates/codesextant-store/tests/schema_migration.rs','crates/codesextant-store/tests/python_oracle.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(index): add atomic native incremental revisions'
~~~

---

### Task 6: Build one persistent semantic sidecar protocol and two bundled resolvers

**Dependencies:** Task 5.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-core/Cargo.toml
- Modify: crates/codesextant-sidecar-protocol/Cargo.toml
- Create: crates/codesextant-sidecar-protocol/src/frame.rs
- Create: crates/codesextant-sidecar-protocol/src/message.rs
- Create: crates/codesextant-sidecar-protocol/src/handshake.rs
- Modify: crates/codesextant-sidecar-protocol/src/lib.rs
- Create: crates/codesextant-core/src/semantic.rs
- Create: crates/codesextant-core/src/analyzer_snapshot.rs
- Create: crates/codesextant-core/src/resolution_input.rs
- Create: crates/codesextant-core/src/sidecar_manager.rs
- Create: crates/codesextant-core/src/bin/codesextant_ts_launcher.rs
- Modify: crates/codesextant-core/src/lib.rs
- Create: sidecars/python/codesextant_jedi_server.py
- Create: sidecars/python/requirements.lock
- Create: sidecars/python/codesextant-jedi.spec
- Create: sidecars/python/tests/test_server.py
- Create: sidecars/typescript/package.json
- Create: sidecars/typescript/package-lock.json
- Create: sidecars/toolchain.lock.json
- Create: sidecars/typescript/src/server.ts
- Create: sidecars/typescript/src/project-cache.ts
- Create: sidecars/typescript/scripts/build-component.mjs
- Create: sidecars/typescript/launcher-policy.json
- Create: sidecars/typescript/test/server.test.ts
- Create: sidecars/typescript/test/component-build.test.ts
- Create: sidecars/component-manifest.schema.json
- Create: sidecars/environment-policy.json
- Create: sidecars/build.py
- Create: tests/release/run_sidecar_no_runtime.py
- Test: crates/codesextant-sidecar-protocol/tests/framing.rs
- Test: crates/codesextant-core/tests/semantic_sidecars.rs
- Test: crates/codesextant-core/tests/analyzer_snapshot.rs
- Test: crates/codesextant-core/tests/resolution_input.rs

**Interfaces:**
- Consumes: installed component manifest, strong project/scope identity, revision-bound read-only analyzer snapshot built only from immutable SourceBlobs, semantic query, timeout, and cancellation token.
- Produces: AnalyzerSnapshot/virtual-path map, Hello, Ready, ResolveReferences, ResolveDefinitions, AnalyzeImports, Cancel, Ping, Shutdown, SemanticResult, SidecarManager, ResolverConfidence, and persisted semantic bundles consumed only through a pinned ReaderEpoch.

**Dependency closure:** Root Cargo.toml adds exactly tokio-util, futures-util, async-trait, bytes, lru, and sha2 from the authority table while retaining the authoritative tokio and hex pins/features. codesextant-sidecar-protocol consumes bytes, serde, serde_json, thiserror, and tokio; codesextant-core consumes async-trait, futures-util, lru, sha2, hex, tokio, and tokio-util through workspace = true and declares the `codesextant-ts` launcher as a binary target in that existing package, not a tenth workspace package. Python and Node build dependencies use only the exact hash-locked pins listed above; no executable injector is used. `sidecars/toolchain.lock.json` binds the official Node 24.18.0 archive, executable/support-file SHA-256 closure, upstream SHASUMS signature identity, target, and ABI floor for each of the five release targets. The lock and bundle scan reject any runtime TypeScript compiler other than ts-morph/common's 6.0.2 authority. Cargo.lock and both affected crate manifests are staged.

- [ ] **Step 1: Write failing protocol and persistence tests**

The wire protocol is Content-Length framed UTF-8 JSON over stdin/stdout. Protocol version 1 messages have request_id and kind. Hello includes parent version, protocol versions accepted, strong project/scope identity, analyzer-snapshot ID, virtual snapshot root, original-to-virtual path-map digest, analysis-contract digest, and capability request; it never includes or exposes an original repository root. Ready returns sidecar kind, resolver version, protocol version, capabilities, process ID, project cache ID, snapshot ID, sanitized-environment digest, and self-test runtime facts.

Tests cover split headers/bodies, multiple frames in one read, malformed length, maximum 16 MiB frame, invalid JSON, unknown version, out-of-order responses by request ID, cancellation, stderr noise isolation, graceful shutdown, and EOF crash. Analyzer-snapshot tests place sentinel imports/configs outside scope, then race symlink/reparse swaps, tsconfig `extends`, pyproject/sys.path/import changes, rename/delete, and live-repository mutation after the source/config blobs were captured; neither sidecar may open the original repository or sentinel, and every result must bind the snapshot ID plus exact resolution-context digest. Python fixtures cover Python 3.14 syntax plus Final/ClassVar/Self/TypeAlias/generics and prove the server uses `jedi.Project(load_unsafe_extensions=False)` only against the virtual snapshot, with no `Interpreter`, uncontrolled environment, smart-sys-path escape, host-filesystem fallback, or sys.path outside that snapshot. An unchanged-source 0.19.2-to-0.20.0 fixture must change the analyzer contract, perform one controlled re-resolution, then become a stable no-op. TypeScript fixtures cover TypeScript 6 syntax, require the Ready/self-test compilerVersion to equal 6.0.2, and reject a direct server import, second bundled/compiler version, or FileSystemHost/module-resolution access outside the snapshot. Component-build tests reject `npx`/PATH/network resolution, an unlocked/wrong-target Node archive or executable, missing/extra runtime support, launcher/bundle/runtime hash drift, a launcher policy with mutable or unbounded Node flags, caller arguments interpreted as Node flags, host-Node fallback, and a target ABI/minimum-OS mismatch. All five native targets, including macOS x86_64, launch through the packaged `codesextant-ts` binary, prove `process.execPath` is the manifest-listed private Node runtime beneath the component root, report exact Node/V8/OpenSSL/compiler versions, and pass the sidecar self-test under the closed child environment.

Persistence tests send 100 requests to one process and assert the PID and project cache ID stay constant for one immutable snapshot. They then change tsconfig/pyproject inputs through a new authorized SourceBlob snapshot and require an explicit snapshot/cache-key invalidation without spawning per request. A revision-consistency barrier indexes R, mutates/renames/deletes the live repository without reindexing, then calls references and call_graph: responses remain exactly R and open zero live source bytes. Reindexing publishes R+1 and only then exposes the change. Sidecars run during staging/index analysis; public semantic reads after ReaderEpoch acquisition use only the persisted semantic bundles in that pinned revision and never query a live path or sidecar.

- [ ] **Step 2: Run protocol tests and observe red**

~~~powershell
cargo test --locked -p codesextant-sidecar-protocol
C:\Python311\python.exe -m pytest sidecars/python/tests -q
npm --prefix sidecars/typescript test
~~~

Expected: FAIL because protocol and servers do not exist.

- [ ] **Step 3: Implement the Jedi server**

The Python server creates one `jedi.Project(load_unsafe_extensions=False, environment_path=<embedded-locked-runtime>, smart_sys_path=False)` per analyzer-snapshot/cache key and retains source/module caches across requests. Project path and explicit sys_path contain only the private read-only virtual snapshot; original repository paths are absent from argv, environment, cwd, protocol, and Jedi state. Every source/config/dependency in that snapshot was materialized from an AccessScope-opened SourceBlob, with links forbidden and an original-to-virtual path map used only for response remapping. It never calls `jedi.Interpreter`, imports project code, executes unsafe extensions, consults host/user config, or follows environment/import/config paths outside the snapshot. ResolveReferences performs candidate prefilter then Jedi goto confirmation. ResolveDefinitions follows only snapshot-valid imports. AnalyzeImports reports unused imports and re-exports with explicit confidence. It never returns high confidence from text matching.

requirements.lock contains exact hashes for Jedi, parso, PyInstaller, and transitive packages. `sidecars/build.py`, even when launched by the Python 3.11 orchestrator, verifies and launches the target-native CPython 3.14.6 from `sidecars/toolchain.lock.json`, creates its isolated venv, installs with `--require-hashes`, and invokes that interpreter's `python -m PyInstaller`; it refuses target, archive/signature, executable digest, `sys.version`, SOABI, OpenSSL, SQLite, or PyInstaller mismatch. codesextant-jedi.spec produces an onedir component with that 3.14.6 runtime, executable, Jedi/parso data, LICENSE files, and component-manifest.json. A packaged self-test reports `sys.version`, SOABI, OpenSSL, SQLite, Jedi, and parso, and all facts are bound into component metadata, SBOM, provenance, and `analysis_contract_sha256`.

- [ ] **Step 4: Implement the ts-morph server**

The TypeScript server creates one ts-morph Project per analyzer-snapshot/tsconfig cache key and retains it. A controlled FileSystemHost and module-resolution host are rooted only in the private snapshot, reject absolute/original/parent/link escapes, and have no host-filesystem fallthrough; tsconfig `extends`, path aliases, package metadata, and imports resolve only from snapshot bytes. It supports JS, JSX, TS, and TSX source files, findReferences, definitions, unused imports, and re-export evidence. A new snapshot invalidates only affected source/context caches or the project when captured config changes.

esbuild bundles server code and ts-morph dependencies into one CommonJS entry. Committed `launcher-policy.json` fixes the manifest-relative private Node path, bundle path, bounded Node argv, and rule that all protocol/application arguments follow the script separator and can never become Node options. `scripts/build-component.mjs` runs only the SHA-256-verified Node 24.18.0 executable and local `node_modules/.bin/esbuild` from the committed npm-ci lock closure—never `npx`, PATH lookup, or network resolution—then emits a closed sorted fragment for the bundle plus the exact official Node runtime/support/license closure. The Rust `codesextant-ts` launcher validates the component root and relevant manifest rows without following links, rejects caller-supplied runtime paths, clears the inherited environment through the shared policy, and launches only the manifest-relative private Node executable with the fixed argv and bundle; no host Node fallback exists. package-lock.json is committed and npm ci is mandatory. Component metadata, SBOM, provenance, and `analysis_contract_sha256` bind launcher bytes/policy, Node archive/executable/support-file target/version/digests and V8/OpenSSL versions, bundle digest, ts-morph version, actual bundled TypeScript compiler version, esbuild version/integrity, and closed-environment-policy digest. This supported onedir strategy is uniform across all five targets and deliberately avoids Node's experimental SEA path, which is not officially tested on macOS x86_64.

- [ ] **Step 5: Implement Rust supervision and confidence**

`ResolutionInputCollector` is the sole parent-side authority for analyzer inputs. Its versioned candidate/closure table covers project-local Python/JS/TS source and declaration modules plus pyproject.toml, setup.cfg/setup.py, tsconfig/jsconfig and their in-scope extends chain, package.json exports/types/main, and required lock/package metadata. It resolves candidates incrementally from imports through AccessScope directory handles, opens every accepted input once with no-follow/reparse and file-identity recheck into a bounded SourceBlob, and enforces per-file, file-count, depth, and aggregate byte/disk quotas. Outside-root, link, missing, and capped candidates become explicit unresolved/negative lookup records; they never trigger host fallback. The snapshot manifest proves every virtual file path maps to one collected blob hash and every failed virtual open maps to a recorded negative dependency. `resolution_input.rs` tests all candidate kinds, cycles, caps, missing-to-added invalidation, and rejects any sidecar-opened virtual file absent from the collector manifest.

Before launch, IndexCoordinator builds a revision-bound analyzer snapshot solely from the already-open immutable source/config/policy/dependency SourceBlobs. Spill and snapshot data live in an owner-only no-follow per-index directory beneath the validated StateRoot. Its fsync/atomically-published manifest binds strong project/scope ID, writer fencing epoch/holder, creator PID+process-start+boot identity, creation time, snapshot/path-map/blob digests, and strict per-index/global byte quota. Disk-full/quota/link-swap aborts without publication. The private content-addressed no-link tree is verified against the receipt and made read-only before use; no byte is copied from a live path. The snapshot contains only the explicitly captured resolution closure; missing/out-of-scope imports remain unresolved. Snapshot creation and sidecar execution have barriers proving subsequent live swaps cannot affect bytes.

Every running/cache entry holds a snapshot lease/refcount. Teardown stops admission for that snapshot, drains or cancels requests, sends Shutdown with bounded grace, kills and reaps the complete process tree if needed, discards caches/file handles, and only then deletes the materialization. A retained sidecar can never outlive its snapshot. Windows tests keep real open files/Jedi/ts-morph handles across teardown and require reap-before-delete; sharing violations create a quota-counted tombstone retried by recovery. On every normal publish/abort/cancel path the snapshot is retired after persisted semantic bundles/context digests commit. Startup/recover enumerates manifests without following links and quarantines/deletes an orphan only after proving its creator dead or fencing epoch superseded; a live unrelated owner is untouched. Crash injection at spill/snapshot/sidecar/publish, disk-full/quota, and link-swap leaves zero orphan blobs after recovery. Documentation states deletion does not promise forensic SSD secure erase. Retained public revisions need no source-byte store because public semantic reads use persisted bundles.

SidecarManager reads the installed component manifest, verifies component SHA-256 before first launch, spawns with stdin/stdout pipes and hidden-window flags on Windows, performs handshake, multiplexes request IDs, sends cancellation, and captures bounded/redacted stderr. It clears the inherited environment and rebuilds only the reviewed per-platform minimum from `sidecars/environment-policy.json`: controlled private HOME/cache/temp directories, fixed locale/TZ, and required system variables such as Windows SystemRoot. It explicitly strips/rejects NODE_OPTIONS, NODE_PATH, every PYTHON* variable, VIRTUAL_ENV, CONDA*, hostile HOME/config/cache/temp values, and any unlisted variable; sets cwd to the analyzer snapshot; and passes no original repository path. Ready/self-test returns the sanitized environment-policy digest without secrets.

Cancellation is a supervised process state machine, not a cooperative assumption. Every sidecar generation is born in a dedicated POSIX process group controlled through the pinned rustix process APIs or a Windows Job Object configured kill-on-close before untrusted child work begins; failure to establish that containment aborts launch. A queued call cancels locally. For an active synchronous Jedi/ts-morph call, manager sends Cancel and waits only the bounded ACK/completion grace inside the original deadline; because the child event loop may be CPU-blocked, grace expiry kills and reaps the whole contained child process tree, fails every in-flight ID for that generation, quarantines late frames, releases snapshot/queue/byte permits only after reap, and never replays cancelled work. A later request may start one clean process. Synthetic uninterruptible Python and TypeScript resolvers that spawn grandchildren must return the deadline error on time, prove the old PID/process-group or Job Object tree is gone, preserve zero publication, and let the next request succeed.

One process is retained per resolver kind and strong project/scope identity up to a configurable LRU capacity, while all caches are additionally keyed by immutable analyzer-snapshot ID. Idle eviction sends Shutdown then kills/reaps after 2 seconds. Crash/restart is governed by a single-flight rolling circuit breaker keyed by component/resolver/snapshot context with fixed launch-rate/window/backoff caps; component integrity/protocol failures open a component-wide breaker. One hundred concurrent crash requests produce a bounded launch count and deterministic SIDECAR_UNAVAILABLE responses, not a process storm. A crash fails active requests, and only future idempotent staging-time reads whose deadlines remain viable may use a clean restarted process against the same verified snapshot. No active/cancelled work is replayed.

When a sidecar is unavailable and strict_semantic is false, native name candidates may return low confidence with RESOLVER_UNAVAILABLE warning. strict_semantic true returns the declared error.

- [ ] **Step 6: Build components and prove no PATH runtime**

~~~powershell
$originalPath = $env:PATH
try {
    cargo build --locked --release -p codesextant-core --bin codesextant-ts
    C:\Python311\python.exe sidecars/build.py --orchestrator-only --toolchain-lock sidecars/toolchain.lock.json --target x86_64-pc-windows-msvc --ts-launcher target\release\codesextant-ts.exe --out dist\sidecars\x86_64-pc-windows-msvc
    cargo test --locked -p codesextant-sidecar-protocol
    cargo test --locked -p codesextant-core --test semantic_sidecars
    C:\Python311\python.exe tests/release/run_sidecar_no_runtime.py --component-root dist\sidecars\x86_64-pc-windows-msvc --child-path "$env:SystemRoot\System32"
    if ($env:PATH -ne $originalPath) { throw 'parent PATH changed during sidecar test' }
} finally {
    $env:PATH = $originalPath
}
~~~

The build and both cargo tests run with the caller's normal PATH; the 3.11 command is only the build orchestrator and the build receipt proves PyInstaller ran under locked CPython 3.14.6. run_sidecar_no_runtime.py snapshots its own parent PATH and launches only the two packaged sidecar self-test child processes through the same SidecarManager environment builder. Adversarial cases set NODE_OPTIONS=`--require <outside-sentinel>`, NODE_PATH, PYTHONPATH, PYTHONHOME, VIRTUAL_ENV, CONDA_PREFIX, hostile HOME/config/cache/temp directories, preload sentinels, and fake PATH runtimes; the child must neither open/execute/write them nor leak them to output/cache. It asserts python, python3, py, node, npm, npx, pnpm, and bun are not discoverable through PATH; requires Python to report exact packaged 3.14.6/SOABI/OpenSSL/SQLite/Jedi/parso and TypeScript to report the exact manifest-relative private Node executable, launcher-policy digest, Node/V8/OpenSSL/compiler versions, environment-policy digest, and closed-resolution self-test; then proves parent environment/PATH are unchanged. The same assertion runs on all five native release targets in Task 11/G5. The finally block restores the PowerShell PATH even if a command fails. Expected: all commands exit 0.

- [ ] **Step 7: Commit persistent bundled sidecars**

~~~powershell
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-core/Cargo.toml','crates/codesextant-sidecar-protocol/Cargo.toml','crates/codesextant-sidecar-protocol/src/frame.rs','crates/codesextant-sidecar-protocol/src/message.rs','crates/codesextant-sidecar-protocol/src/handshake.rs','crates/codesextant-sidecar-protocol/src/lib.rs','crates/codesextant-sidecar-protocol/tests/framing.rs','crates/codesextant-core/src/semantic.rs','crates/codesextant-core/src/analyzer_snapshot.rs','crates/codesextant-core/src/resolution_input.rs','crates/codesextant-core/src/sidecar_manager.rs','crates/codesextant-core/src/bin/codesextant_ts_launcher.rs','crates/codesextant-core/src/lib.rs','sidecars/python/codesextant_jedi_server.py','sidecars/python/requirements.lock','sidecars/python/codesextant-jedi.spec','sidecars/python/tests/test_server.py','sidecars/typescript/package.json','sidecars/typescript/package-lock.json','sidecars/toolchain.lock.json','sidecars/typescript/src/server.ts','sidecars/typescript/src/project-cache.ts','sidecars/typescript/scripts/build-component.mjs','sidecars/typescript/launcher-policy.json','sidecars/typescript/test/server.test.ts','sidecars/typescript/test/component-build.test.ts','sidecars/component-manifest.schema.json','sidecars/environment-policy.json','sidecars/build.py','tests/release/run_sidecar_no_runtime.py','crates/codesextant-core/tests/semantic_sidecars.rs','crates/codesextant-core/tests/analyzer_snapshot.rs','crates/codesextant-core/tests/resolution_input.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(semantic): bundle persistent Jedi and ts-morph sidecars'
~~~

Do not stage dist outputs.

---

### Task 7: Enforce deadlines, cancellation, bounded queues, and crash containment

**Dependencies:** Task 6.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-core/Cargo.toml
- Modify: crates/codesextant-daemon/Cargo.toml
- Modify: crates/codesextant-cli/Cargo.toml
- Modify: crates/codesextant-mcp/Cargo.toml
- Create: crates/codesextant-core/src/execution.rs
- Create: crates/codesextant-daemon/src/scheduler.rs
- Create: crates/codesextant-daemon/src/shutdown.rs
- Modify: crates/codesextant-daemon/src/lib.rs
- Modify: crates/codesextant-cli/src/lib.rs
- Modify: crates/codesextant-mcp/src/lib.rs
- Test: crates/codesextant-core/tests/cancellation.rs
- Test: crates/codesextant-daemon/tests/bounded_queue.rs
- Test: crates/codesextant-daemon/tests/crash_containment.rs
- Test: crates/codesextant-daemon/tests/cross_process_index.rs
- Test: crates/codesextant-daemon/tests/shutdown.rs

**Interfaces:**
- Consumes: RequestContext deadline/cancellation, operation cost class, and configured limits.
- Produces: ExecutionBudget, OperationScheduler, QueuePermit, PanicBoundary, ShutdownCoordinator.

**Dependency closure:** Root Cargo.toml adds exactly dashmap, parking_lot, tracing, and tracing-subscriber from the authority table; tokio/tokio-util/tower remain on their existing exact pins and features. codesextant-core, codesextant-daemon, codesextant-cli, and codesextant-mcp consume only their needed workspace dependencies with no local features. Cargo.lock and all four crate manifests are staged.

- [ ] **Step 1: Write failing concurrency tests**

Use Tokio paused time and deterministic barriers. Tests require:

- cheap queue capacity 64, standard 32, heavy 4 by default;
- global in-flight cap 64;
- per-project heavy cap 1;
- immediate QUEUE_FULL after queue wait budget expires;
- deadline propagation through discovery, parser, store, ranking, and sidecar request;
- MCP cancellation and HTTP disconnect cancel shared work;
- CLI Ctrl+C cancels and exits 130;
- cancelled index leaves old revision published;
- true-process CLI+CLI and CLI+daemon writers planned from one base are released in reverse order; fencing plus pointer CAS prevents stale overwrite, and crash/cancellation/takeover leaves no staging roots;
- panic in parser/query task becomes INTERNAL and daemon survives;
- killed sidecar follows one-restart policy;
- repeated timeouts against an uncooperative parser and locked SQLite DB never exceed the dedicated blocking-work/thread permit cap, never release a permit before the closure exits, never publish late, and shutdown stays bounded;
- graceful shutdown stops accepting, cancels queued work, waits up to 10 seconds for active atomic sections, flushes WAL, stops sidecars, and removes runtime files.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
cargo test --locked -p codesextant-core --test cancellation
cargo test --locked -p codesextant-daemon --test bounded_queue
cargo test --locked -p codesextant-daemon --test crash_containment
cargo test --locked -p codesextant-daemon --test cross_process_index
cargo test --locked -p codesextant-daemon --test shutdown
~~~

Expected: FAIL because scheduler and shutdown coordination do not exist.

- [ ] **Step 3: Implement monotonic budget propagation**

ExecutionBudget stores one Tokio Instant deadline and child cancellation token. Every layer receives a reference; no layer resets timeout. Blocking parser/store work must first acquire a separate bounded blocking-work semaphore; the permit is moved into the `spawn_blocking` closure and is released only when that closure actually exits, never when the awaiting request times out. Tree-sitter parse/query progress callbacks and extraction checkpoints consult the original monotonic deadline/cancellation token. SQLite installs busy/progress handlers from the same budget and clamps busy_timeout to remaining time. A timed-out blocking task may finish privately while still consuming its permit, but linearization/fencing prevents late publication. Stress tests prove repeated timeouts cannot accumulate unbounded threads/tasks or bypass operation queues.

- [ ] **Step 4: Implement bounded scheduling and panic boundaries**

Use bounded mpsc channels per cost class and semaphores for global/project/blocking-work caps. Discovery/parser pipelines additionally enforce the weighted aggregate SourceBlob byte budget from Task 3; no queue may retain unaccounted repository bytes. Reject on full/expired queue; do not allocate an unbounded pending task. Cross-process index coordination acquires/increments a monotonically increasing writer fencing epoch under `BEGIN IMMEDIATE`; every staging write, pointer CAS publish, retirement, and GC transaction predicates on the current epoch and holder. Lease takeover permanently fences a paused old writer even if its PID later resumes. `cross_process_index.rs` launches real CLI+CLI and CLI+daemon processes and covers reverse publish, old-owner resume after takeover, writer crash, cancellation, concurrent GC, PID reuse, bounded rediscover/replan, monotonic content, and zero leaked staging roots. Wrap each operation future with AssertUnwindSafe/catch_unwind at the service boundary, redact panic payload, abort staging work, and keep daemon accept loop alive. Shutdown waits only the declared grace for blocking closures, fences all writers before returning, and cannot falsely report cleanup while a late task retains publish authority.

- [ ] **Step 5: Run deterministic stress**

~~~powershell
cargo test --locked -p codesextant-core --test cancellation
cargo test --locked -p codesextant-daemon --test bounded_queue -- --nocapture
cargo test --locked -p codesextant-daemon --test crash_containment
cargo test --locked -p codesextant-daemon --test cross_process_index
cargo test --locked -p codesextant-daemon --test shutdown
~~~

Expected: all tests pass; queue counts return to zero; old revision survives every cancelled/crashed write.

- [ ] **Step 6: Commit execution control**

~~~powershell
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-core/Cargo.toml','crates/codesextant-daemon/Cargo.toml','crates/codesextant-cli/Cargo.toml','crates/codesextant-mcp/Cargo.toml','crates/codesextant-core/src/execution.rs','crates/codesextant-core/tests/cancellation.rs','crates/codesextant-daemon/src/scheduler.rs','crates/codesextant-daemon/src/shutdown.rs','crates/codesextant-daemon/src/lib.rs','crates/codesextant-daemon/tests/bounded_queue.rs','crates/codesextant-daemon/tests/crash_containment.rs','crates/codesextant-daemon/tests/cross_process_index.rs','crates/codesextant-daemon/tests/shutdown.rs','crates/codesextant-cli/src/lib.rs','crates/codesextant-mcp/src/lib.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(runtime): bound and cancel every operation'
~~~

---

### Task 8: Implement native service, index, graph, and navigation operations

**Dependencies:** Tasks 5 through 7.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-core/Cargo.toml
- Create: crates/codesextant-core/src/operations/mod.rs
- Create: crates/codesextant-core/src/operations/service_health.rs
- Create: crates/codesextant-core/src/operations/doctor.rs
- Create: crates/codesextant-core/src/operations/status.rs
- Create: crates/codesextant-core/src/operations/index.rs
- Create: crates/codesextant-core/src/operations/symbols.rs
- Create: crates/codesextant-core/src/operations/references.rs
- Create: crates/codesextant-core/src/operations/call_graph.rs
- Create: crates/codesextant-core/src/operations/map.rs
- Create: crates/codesextant-core/src/operations/impact.rs
- Create: crates/codesextant-core/src/ranking.rs
- Create: crates/codesextant-core/src/graph.rs
- Create: crates/codesextant-core/src/cursor.rs
- Modify: crates/codesextant-core/src/query_service.rs
- Test: crates/codesextant-core/tests/operation_service_health.rs
- Test: crates/codesextant-core/tests/operation_doctor.rs
- Test: crates/codesextant-core/tests/operation_status.rs
- Test: crates/codesextant-core/tests/operation_index.rs
- Test: crates/codesextant-core/tests/operation_symbols.rs
- Test: crates/codesextant-core/tests/operation_references.rs
- Test: crates/codesextant-core/tests/operation_call_graph.rs
- Test: crates/codesextant-core/tests/operation_map.rs
- Test: crates/codesextant-core/tests/operation_impact.rs
- Test: crates/codesextant-core/tests/pagination_cursor.rs

**Interfaces:**
- Consumes: operation-specific typed input, GraphStore snapshot, parser/index coordinator, persisted revision-bound semantic bundles, execution budget, and operation registry policy.
- Produces: nine named OperationPayload variants with warnings/confidence/index revision.

**Dependency closure:** This task adds no third-party crate. Root Cargo.toml, Cargo.lock, and codesextant-core/Cargo.toml are still staged so review proves the dependency graph and Apache-2.0 inheritance did not drift while the operation modules were added.

- [ ] **Step 1: Write nine failing oracle tests**

Each test loads its same-named payload from python-public-operations-v1.json and compares semantic output after the allowed canonicalization. No test calls another public operation through CLI/MCP/HTTP; it calls QueryService directly to isolate kernel behavior.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
cargo test --locked -p codesextant-core --test operation_service_health
cargo test --locked -p codesextant-core --test operation_doctor
cargo test --locked -p codesextant-core --test operation_status
cargo test --locked -p codesextant-core --test operation_index
cargo test --locked -p codesextant-core --test operation_symbols
cargo test --locked -p codesextant-core --test operation_references
cargo test --locked -p codesextant-core --test operation_call_graph
cargo test --locked -p codesextant-core --test operation_map
cargo test --locked -p codesextant-core --test operation_impact
~~~

Expected: each named test fails because its operation body is absent.

- [ ] **Step 3: Implement service_health and doctor**

service_health reports version, protocol/schema versions, daemon state, queue depth by cost, database accessibility, index revision, and sidecar ready/degraded state. It does not leak absolute paths or tokens.

doctor checks install component checksums, owner-only token/runtime permissions, writable home, SQLite integrity_check, schema version, parser registry, Jedi handshake, ts-morph handshake, loopback policy, and stale runtime files. Each check has stable ID, pass/warn/fail, remediation, and redacted evidence.

- [ ] **Step 4: Implement status, index, and symbols**

Default status is metadata-only and reports project identity, current revision, file/symbol/edge counts, last complete index, parser warnings, resolver state, and `freshness=unknown|watcher_clean|known_stale` from a bounded watcher/change epoch. It opens and hashes zero repository source files. Optional `verify_fresh=true` is dynamically classified as heavy before queue admission and recomputes the discovery digest through the bounded IndexCoordinator pipeline; it cannot consume a cheap worker. Large-repository tests prove warm default status remains under its ceiling with zero source opens while verified freshness obeys heavy caps/deadlines.

index delegates to the atomic IndexCoordinator and returns IndexReceipt. It never performs transport work.

symbols filters by file/kind/name/visibility, uses stable path/start-line/symbol-ID ordering, and enforces bounded limit/cursor. The cursor is opaque, versioned, and integrity-protected with a keyed BLAKE3 key stored owner-only beneath StateRoot. Its payload binds operation ID, strong project/scope ID, exact published revision+snapshot root, canonical filter/sort/limit digest, and last complete `(path,start_line,symbol_id)` tuple. Validation/signature/project/filter checks happen before opening a snapshot; a valid cursor acquires that exact retained revision even if a newer index exists, and returns INDEX_STALE only if the pinned revision was legitimately retired. Malformed/oversized/tampered/cross-project/filter-or-limit-changed cursors return INVALID_ARGUMENT. Equal-prefix, rename/insert/delete-between-pages, cross-project replay, and tamper tests require concatenated pagination to equal a one-shot result from the pinned revision with no skip/duplicate.

- [ ] **Step 5: Implement references and call_graph**

references pins one published revision and reads deterministic name candidates plus high-confidence Python/JS/TS semantic edges only from that revision's persisted syntax/semantic bundles. Jedi and ts-morph run exclusively during IndexCoordinator staging against the revision-bound analyzer snapshot; a public references/call_graph request never reopens the repository or invokes a sidecar after acquiring ReaderEpoch. Results merge by stable edge identity in request memory and report high/low groups with resolver evidence. The operation never persists an edge, cache entry, or revision; unsupported-language candidates remain explicitly low confidence.

call_graph performs bounded up/down/both traversal over revision-pinned edges with max_depth and max_nodes, cycle markers, deterministic breadth-first ordering, and confidence as the minimum edge confidence along each path.

- [ ] **Step 6: Implement map and impact hot paths**

map filters scope before graph construction, computes weighted PageRank with the exact G2 formula/tolerance/order, emits every ScoreEvidence field, and guarantees rank equals weighted_pagerank within 1e-12.

impact performs reverse reachability from exact symbol/file seeds, deduplicates shortest paths, applies confidence multiplication/minimum policy from operations.yaml, respects max_depth/max_nodes, and reports truncation warnings rather than silently dropping nodes.

- [ ] **Step 7: Run all nine named tests and performance ceilings**

~~~powershell
cargo test --locked -p codesextant-core --test operation_service_health
cargo test --locked -p codesextant-core --test operation_doctor
cargo test --locked -p codesextant-core --test operation_status
cargo test --locked -p codesextant-core --test operation_index
cargo test --locked -p codesextant-core --test operation_symbols
cargo test --locked -p codesextant-core --test operation_references
cargo test --locked -p codesextant-core --test operation_call_graph
cargo test --locked -p codesextant-core --test operation_map
cargo test --locked -p codesextant-core --test operation_impact
~~~

Expected: all nine pass. The fixed medium corpus additionally requires warm status under 20 ms, symbols under 50 ms, map under 250 ms, and impact under 250 ms on the benchmark reference runner; ceilings are regression guards, not public cross-machine claims.

- [ ] **Step 8: Commit nine operation bodies**

~~~powershell
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-core/Cargo.toml','crates/codesextant-core/src/operations/mod.rs','crates/codesextant-core/src/operations/service_health.rs','crates/codesextant-core/src/operations/doctor.rs','crates/codesextant-core/src/operations/status.rs','crates/codesextant-core/src/operations/index.rs','crates/codesextant-core/src/operations/symbols.rs','crates/codesextant-core/src/operations/references.rs','crates/codesextant-core/src/operations/call_graph.rs','crates/codesextant-core/src/operations/map.rs','crates/codesextant-core/src/operations/impact.rs','crates/codesextant-core/src/ranking.rs','crates/codesextant-core/src/graph.rs','crates/codesextant-core/src/cursor.rs','crates/codesextant-core/src/query_service.rs','crates/codesextant-core/tests/operation_service_health.rs','crates/codesextant-core/tests/operation_doctor.rs','crates/codesextant-core/tests/operation_status.rs','crates/codesextant-core/tests/operation_index.rs','crates/codesextant-core/tests/operation_symbols.rs','crates/codesextant-core/tests/operation_references.rs','crates/codesextant-core/tests/operation_call_graph.rs','crates/codesextant-core/tests/operation_map.rs','crates/codesextant-core/tests/operation_impact.rs','crates/codesextant-core/tests/pagination_cursor.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(core): implement native navigation hot paths'
~~~

---

### Task 9: Implement native analysis, comments, health, and discipline operations

**Dependencies:** Task 8.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-core/Cargo.toml
- Create: crates/codesextant-core/src/operations/dead_code.rs
- Create: crates/codesextant-core/src/operations/unwired.rs
- Create: crates/codesextant-core/src/operations/duplicates.rs
- Create: crates/codesextant-core/src/operations/comment_overview.rs
- Create: crates/codesextant-core/src/operations/comment_tags.rs
- Create: crates/codesextant-core/src/operations/comments.rs
- Create: crates/codesextant-core/src/operations/ai_usage.rs
- Create: crates/codesextant-core/src/operations/code_health.rs
- Create: crates/codesextant-core/src/operations/discipline_evaluate.rs
- Create: crates/codesextant-core/src/policy.rs
- Modify: crates/codesextant-core/src/operations/mod.rs
- Modify: crates/codesextant-core/src/query_service.rs
- Test: crates/codesextant-core/tests/operation_dead_code.rs
- Test: crates/codesextant-core/tests/operation_unwired.rs
- Test: crates/codesextant-core/tests/operation_duplicates.rs
- Test: crates/codesextant-core/tests/operation_comment_overview.rs
- Test: crates/codesextant-core/tests/operation_comment_tags.rs
- Test: crates/codesextant-core/tests/operation_comments.rs
- Test: crates/codesextant-core/tests/operation_ai_usage.rs
- Test: crates/codesextant-core/tests/operation_code_health.rs
- Test: crates/codesextant-core/tests/operation_discipline_evaluate.rs
- Test: crates/codesextant-core/tests/operation_read_only_contract.rs

**Interfaces:**
- Produces: the remaining nine named OperationPayload variants.

**Dependency closure:** Root Cargo.toml adds exactly the actively maintained YAML Organization `yaml_serde` pin from the authority table and reuses the Task 6 sha2/hex pins for policy decoding and canonical evidence hashes. `serde_yaml` and `serde_yml` are forbidden from Cargo.toml, Cargo.lock, full cargo metadata, SBOM, and license inventory. codesextant-core/Cargo.toml consumes `yaml_serde`, sha2, and hex with workspace = true and no local features. Cargo.lock and both manifests are staged.

- [ ] **Step 1: Write nine failing oracle tests**

Each named test uses the corresponding golden entry and adversarial fixtures for same-name symbols, re-exports, entrypoints, generated code, duplicated structure with renamed identifiers, comment line endings, false-positive AI terms, unavailable complexity, and policy boundary values. `operation_read_only_contract.rs` derives all 17 `side_effect=none` IDs from operations.yaml, executes each through a read-capability-only QueryService context whose type cannot obtain a writer, and proves DB bytes/rows/current revision plus every persistent sidecar cache/state file are byte-identical before and after. It separately proves `index` is the sole operation receiving the writer capability. Discipline-policy fixtures prove `yaml_serde` parses every supported existing `operations.yaml`/policy document identically to the Python authority, rejects duplicate keys, aliases/anchors beyond configured expansion limits, recursive/deep/oversized documents, type confusion, unknown fields, and non-UTF-8 input, and never coerces an adversarial value into a permissive policy.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
cargo test --locked -p codesextant-core --test operation_dead_code
cargo test --locked -p codesextant-core --test operation_unwired
cargo test --locked -p codesextant-core --test operation_duplicates
cargo test --locked -p codesextant-core --test operation_comment_overview
cargo test --locked -p codesextant-core --test operation_comment_tags
cargo test --locked -p codesextant-core --test operation_comments
cargo test --locked -p codesextant-core --test operation_ai_usage
cargo test --locked -p codesextant-core --test operation_code_health
cargo test --locked -p codesextant-core --test operation_discipline_evaluate
cargo test --locked -p codesextant-core --test operation_read_only_contract
~~~

Expected: each named test fails because its native body is absent.

- [ ] **Step 3: Implement dead_code and unwired conservatively**

dead_code uses semantic unused-import/references for Python and JS/TS. Resolver absence returns unknown_no_resolver, never safe_to_delete. Re-exports, public APIs, tests, scripts, framework entrypoints, reflection patterns, and configured entrypoints are exemptions with evidence.

unwired uses the complete name graph as a low-confidence clue layer, excludes nested/local symbols and explicit entrypoints, and emits candidate evidence without deletion permission.

- [ ] **Step 4: Implement duplicates**

Use parser structural fingerprints, token normalization, winnowing window/hash parameters matching the Python oracle, minimum token/line thresholds, deterministic pair identity, and overlap clustering. Generated/vendored content is excluded before comparison.

- [ ] **Step 5: Implement the three comment operations**

comments returns exact comment/docstring spans and owning symbol. comment_tags filters the stable TODO/FIXME/HACK/XXX registry with true line numbers. comment_overview aggregates density, tag counts, documentation coverage, and excluded-class counts from one revision snapshot. CRLF/LF inputs produce identical logical line values.

- [ ] **Step 6: Implement ai_usage and code_health**

ai_usage ports the checked-in pattern registry into data loaded once, scans only eligible source classes, emits provider/model/API evidence, and preserves dispatch_policy categories without HTML generation.

code_health combines size, cognitive complexity where supported, duplicate membership, churn only when supplied, dead-code confidence, and documentation signals. Unsupported complexity is null with reason, not zero. The formula/version and evidence components match the Python oracle.

- [ ] **Step 7: Implement discipline_evaluate as a pure policy engine**

policy.rs parses the versioned YAML schema, validates unknown metrics/operators as INVALID_ARGUMENT, evaluates threshold and allow/deny rules over typed operation results, and emits pass/warn/fail decisions with rule ID, observed value, threshold, source operation, and evidence location. It performs no shell command and no file mutation.

- [ ] **Step 8: Run all nine named tests**

~~~powershell
cargo test --locked -p codesextant-core --test operation_dead_code
cargo test --locked -p codesextant-core --test operation_unwired
cargo test --locked -p codesextant-core --test operation_duplicates
cargo test --locked -p codesextant-core --test operation_comment_overview
cargo test --locked -p codesextant-core --test operation_comment_tags
cargo test --locked -p codesextant-core --test operation_comments
cargo test --locked -p codesextant-core --test operation_ai_usage
cargo test --locked -p codesextant-core --test operation_code_health
cargo test --locked -p codesextant-core --test operation_discipline_evaluate
~~~

Expected: all nine pass without skip or expected failure.

- [ ] **Step 9: Commit the remaining operation bodies**

~~~powershell
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-core/Cargo.toml','crates/codesextant-core/src/operations/dead_code.rs','crates/codesextant-core/src/operations/unwired.rs','crates/codesextant-core/src/operations/duplicates.rs','crates/codesextant-core/src/operations/comment_overview.rs','crates/codesextant-core/src/operations/comment_tags.rs','crates/codesextant-core/src/operations/comments.rs','crates/codesextant-core/src/operations/ai_usage.rs','crates/codesextant-core/src/operations/code_health.rs','crates/codesextant-core/src/operations/discipline_evaluate.rs','crates/codesextant-core/src/policy.rs','crates/codesextant-core/src/operations/mod.rs','crates/codesextant-core/src/query_service.rs','crates/codesextant-core/tests/operation_dead_code.rs','crates/codesextant-core/tests/operation_unwired.rs','crates/codesextant-core/tests/operation_duplicates.rs','crates/codesextant-core/tests/operation_comment_overview.rs','crates/codesextant-core/tests/operation_comment_tags.rs','crates/codesextant-core/tests/operation_comments.rs','crates/codesextant-core/tests/operation_ai_usage.rs','crates/codesextant-core/tests/operation_code_health.rs','crates/codesextant-core/tests/operation_discipline_evaluate.rs','crates/codesextant-core/tests/operation_read_only_contract.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(core): implement native analysis operations'
~~~

---

### Task 10: Run one-by-one oracle parity for all 18 public operations

**Dependencies:** Tasks 8 and 9.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-core/Cargo.toml
- Create: crates/codesextant-core/tests/public_operation_oracle.rs
- Create: tests/parity/native_operation_cases.yaml
- Create: tests/parity/test_native_operation_oracle.py
- Create: tools/check_native_parity.py

**Interfaces:**
- Consumes: operations.yaml, public-operation oracle manifest/golden, G2 base oracle, fresh homes, fixed corpus/clock/IDs, and native QueryService.
- Produces: 18 individually named comparisons and a complete matrix report.

**Dependency closure:** This task adds no production dependency. Test code uses the already-pinned serde_json/tempfile stack; root Cargo.toml, Cargo.lock, and codesextant-core/Cargo.toml are staged to make that unchanged dependency and license state reviewable.

- [ ] **Step 1: Write the fail-closed inventory check**

native_operation_cases.yaml contains exactly these test IDs:

~~~text
oracle_service_health
oracle_doctor
oracle_status
oracle_index
oracle_symbols
oracle_references
oracle_call_graph
oracle_map
oracle_impact
oracle_dead_code
oracle_unwired
oracle_duplicates
oracle_comment_overview
oracle_comment_tags
oracle_comments
oracle_ai_usage
oracle_code_health
oracle_discipline_evaluate
~~~

The checker rejects a generic all_operations case, missing operation, duplicate operation, skipped/ignored test, xfail, missing golden key, stale manifest hash, or normalization of semantic fields.

- [ ] **Step 2: Run inventory and observe red**

~~~powershell
C:\Python311\python.exe -m pytest tests/parity/test_native_operation_oracle.py -q
cargo test --locked -p codesextant-core --test public_operation_oracle
~~~

Expected: FAIL until all 18 named comparisons are registered.

- [ ] **Step 3: Implement exact comparison rules**

For each operation, create a fresh fixture copy and CODESEXTANT_HOME, run Python adapter and Rust QueryService from equivalent initial state, and compare:

- canonical payload;
- warning codes and evidence;
- confidence level and reason codes;
- index revision content digest;
- stable error when applicable.

Only request_id, duration_ms, absolute temporary root, process ID, random port, and platform path separator may be normalized. Ranking floats use 1e-12 absolute tolerance; every other numeric value is exact.

- [ ] **Step 4: Run every named test with no filter**

~~~powershell
C:\Python311\python.exe tools/check_native_parity.py --manifest tests/fixtures/public-operation-oracle-manifest.json --cases tests/parity/native_operation_cases.yaml
cargo test --locked -p codesextant-core --test public_operation_oracle -- --nocapture
C:\Python311\python.exe -m pytest tests/parity/test_native_operation_oracle.py -q
~~~

Expected: report lists 18/18 pass, zero missing, zero skipped, zero stale, zero unreviewed differences.

- [ ] **Step 5: Commit complete native parity**

~~~powershell
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-core/Cargo.toml','crates/codesextant-core/tests/public_operation_oracle.rs','tests/parity/native_operation_cases.yaml','tests/parity/test_native_operation_oracle.py','tools/check_native_parity.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'test(native): prove all public operations against oracle'
~~~

---

### Task 11: Package sidecars with the product and prove lifecycle without installed runtimes

**Dependencies:** Task 10 and the G0 exact-task-commit helper/tests. This task defines and tests only the G3 lifecycle domain-candidate side of the future generic-sealer boundary; G5 later registers the frozen producer bytes and performs the real `release_gate.py produce-and-seal` integration after all source-changing work is committed.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-core/Cargo.toml
- Modify: crates/codesextant-cli/Cargo.toml
- Modify: crates/codesextant-mcp/Cargo.toml
- Modify: crates/codesextant-daemon/Cargo.toml
- Create: release/targets.toml
- Create: release/verify_components.py
- Create: release/native-lifecycle-contract.schema.json
- Create: release/native-lifecycle-contract.json
- Create: release/run_native_lifecycle.py
- Create: install/component_layout.py
- Modify: sidecars/build.py
- Create: tests/release/test_sidecar_components.py
- Create: tests/release/test_no_runtime_dependency.py
- Create: tests/release/test_native_lifecycle_contract.py
- Create: crates/codesextant-core/tests/component_discovery.rs

**Interfaces:**
- Consumes: per-target codesextant CLI binary, codesextant-mcp binary, codesextantd daemon binary, Jedi component, ts-morph component, product and third-party licenses, and component hashes.
- Produces: one exact multi-binary installed component layout, machine-readable release/native-lifecycle-contract.json, and release/run_native_lifecycle.py invoked without reinterpretation by every G5 F4 target-native job. G5 owns the identity-bound fragment schema, pinned-cosign signing, exact-five aggregation, signed matrix, and F5 verification-only G3 envelope.

**Dependency closure:** G1 already established the single root `windows-sys = 0.61.2` workspace authority with the exact Foundation/Globalization/Security/Security_Authorization/Storage_FileSystem/System_JobObjects/System_Memory/System_SystemInformation/System_Threading feature union. This task consumes that pin and may not re-add, downgrade, or widen it. `codesextant-core` owns target-specific path/component discovery use; `codesextant-daemon` owns target-specific process/token-DACL/job-object use. CLI and MCP call core APIs and do not declare a second direct Windows dependency unless a reviewed compile-time need is added to the same authority. Non-Windows code is cfg-gated. Cargo.lock and every affected manifest are staged. `tests/test_rust_workspace.py`/cargo-metadata validation reject a second windows-sys version, a crate-local version/features table, a missing required root feature, or a direct dependency in a non-owning crate.

- [ ] **Step 1: Write failing component tests**

The installed layout is exact:

~~~text
bin/codesextant
bin/codesextant-mcp
bin/codesextantd
libexec/codesextant/jedi/codesextant-jedi-sidecar
libexec/codesextant/codesextant-ts-morph-sidecar
share/codesextant/component-manifest.json
share/codesextant/licenses/
~~~

The logical entrypoint list is exactly three product binaries plus two sidecars, not a multiplexed executable. The Jedi entry above is the logical path; because Task 6 deliberately uses PyInstaller `onedir`, its physical install root is `libexec/codesextant/jedi/`, with the entrypoint plus the complete deterministic Python runtime/Jedi/parso DLL, `.pyd`, archive, package-data, and support-file closure below it. Windows appends `.exe` to the five entrypoints. Manifest logical names remain codesextant, codesextant-mcp, codesextantd, codesextant-jedi-sidecar, and codesextant-ts-morph-sidecar on every platform.

`component-manifest.json` contains an `entrypoints` table for those exact five logical executables and a closed `installed_files` table enumerating every regular installed file under `bin/`, `libexec/codesextant/`, and `share/codesextant/licenses/`. The manifest file itself is the sole deliberate exclusion from that table, avoiding a recursive self-hash; its final byte SHA-256 is instead bound by the target artifact fragment and ReleaseSubject chain. Every installed-file row binds normalized relative path, kind (`entrypoint|runtime_support|package_data|license`), owning component, SHA-256, size, target, component/product version, and license references. It also contains a canonical Merkle/root digest over the sorted file rows. No support file may be implicit. Symlinks, junctions/reparse points, sockets/devices, path traversal, hardlinks escaping the install root, duplicate normalized/case-folded paths, and any unmanifested or missing file other than that explicitly excluded manifest fail. Tests require the three product binaries and product manifest field to equal the generated `codesextant_core::PRODUCT_VERSION` projection (initially 0.16.0), never Cargo's internal 0.1.0 package version; the two sidecars keep their separately declared component versions. The license directory contains the unchanged Apache-2.0 product text and verbatim third-party/fixture notices; packaging never rewrites those third-party licenses.

Installer and uninstaller tests require exactly these five entrypoints plus the manifest-enumerated support/license closure and the one separately verified `component-manifest.json`, reject missing or extra entrypoints/files, mutate one Jedi `.pyd`, DLL, archive, and data file in turn to prove each is detected before launch, and prove uninstall removes the full manifested closure before removing the manifest last while honoring the declared user-data retention policy. They execute every installed product binary with `--version`, require exact equality to the component manifest and Python product authority, and reject `CARGO_PKG_VERSION` leakage in installer/manifests. Tests also reject a manifest path outside install root, missing hash/license, executable/support-file hash mismatch, user-writable replacement on a protected system install, and fallback to PATH. SidecarManager and `doctor` verify the complete installed-files Merkle/root and each file row before starting Jedi or ts-morph; executable-only verification is forbidden. test_native_lifecycle_contract.py validates the machine-readable contract against its schema and fails if a required phase ID is missing, duplicated, reordered, or replaced by a generic cli/mcp/http smoke phase. It also proves the runner rejects a final or previous artifact whose declared product version or target does not match the frozen subject, the other artifact, and the native runner OS/architecture before launching any executable; Windows-local tests must never execute Linux or macOS binaries.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_sidecar_components.py tests/release/test_no_runtime_dependency.py tests/release/test_native_lifecycle_contract.py -q
cargo test --locked -p codesextant-core --test component_discovery
~~~

Expected: FAIL because component layout and lifecycle contract do not exist.

- [ ] **Step 3: Implement per-target builds**

`release/targets.toml` is the sole OS/architecture/ABI support authority. It names Windows x86_64 with minimum Windows 10 22H2 build 19045 and the reviewed Universal CRT strategy, Linux x86_64/aarch64 with maximum required glibc 2.28, and macOS x86_64/aarch64 with minimum/deployment target 13.5, matching the locked official Node runtime floor. Linux builds run inside digest-pinned glibc-2.28 baseline images on native architecture and `readelf`/`objdump` reject any imported `GLIBC_*` above 2.28; macOS sets `MACOSX_DEPLOYMENT_TARGET=13.5` for Rust and CPython/PyInstaller, verifies every Mach-O slice including the Rust launcher and private Node runtime with `otool`/`vtool`, and rejects any `minos` above 13.5; Windows verifies subsystem/minimum OS, imported DLL allowlist, architecture, and Universal CRT policy with pinned inspection tools. Each target also pins build tools, uses npm ci and hash-locked Python dependencies, strips nondeterministic metadata where supported, and emits one provenance fragment per sidecar. Both the PyInstaller and Node onedir fragments carry complete sorted support-file manifests; assembly rejects a file not covered by its fragment. install/component_layout.py exposes an `assemble` command that consumes the three Cargo product binaries, the `codesextant-ts` launcher, and both sidecar fragments, copies only the exact entrypoints and full declared support closure above, obtains the product version only from the generated core projection, executes all three product `--version` commands, and writes the unified component-manifest.json with the exhaustive file rows/root digest, product/component versions, protocol versions where applicable, target, license entries, build provenance, and ABI baseline. release/verify_components.py walks the physical install tree without following links, requires exact set equality to `installed_files`, recomputes the root plus every hash/size, re-executes the three version commands and both sidecar self-tests on the native target, verifies the target ABI baseline for every executable/support binary, and rejects an extra file/executable or any product-version/ABI mismatch. Installers preflight the host and return an explicit unsupported-platform error before replacement. Every target lifecycle runs once on the oldest-supported OS image/host and once on a current OS; both results are bound into the target fragment, manifest, SBOM/provenance, and support-matrix documentation.

Release packaging fails if either sidecar is absent. There is no lite release that silently omits semantic resolvers. Per-target component verification executes packaged self-tests and requires CPython 3.14.6 plus exact SOABI/OpenSSL/SQLite/Jedi/parso/PyInstaller and Node 24.18.0 plus exact launcher/private-runtime path, V8/OpenSSL/ts-morph/TypeScript/esbuild facts to equal toolchain.lock, component manifest, SBOM, provenance, and analysis contract. Python 3.11 is recorded only as build orchestrator and its presence in the packaged runtime closure is a failure; a PATH/host Node or an experimental SEA artifact is likewise a failure. G5 adds a fresh upstream security-baseline decision before signing; this task exposes all exact runtime facts needed for that gate.

- [ ] **Step 4: Implement exact lifecycle contract**

release/native-lifecycle-contract.json has schema_version 1, required_executables containing the exact five logical names, lifecycle_command_ids [daemon_serve, daemon_start, daemon_stop, daemon_restart], restricted_path_scope installed_artifact_children_only, previous_artifact_required true, and this exact ordered phase_ids array:

~~~json
[
  "install_clean_prefix",
  "child_path_isolation",
  "cli_doctor_sidecars_ready",
  "daemon_serve_health",
  "mcp_initialize_tools_list_call",
  "cli_index_python_typescript_fixture",
  "python_references_high_confidence",
  "typescript_references_high_confidence",
  "daemon_stop_runtime_cleanup",
  "daemon_start_reuse_revision",
  "daemon_restart_reuse_revision",
  "port_conflict_daemon_serve",
  "port_conflict_daemon_start",
  "port_conflict_daemon_restart",
  "daemon_instance_mismatch_stop",
  "daemon_instance_mismatch_restart",
  "upgrade_preserve_schema_and_entrypoints",
  "uninstall_remove_all_five",
  "parent_path_restored"
]
~~~

The contract stores lifecycle command IDs only, never duplicate argv. release/run_native_lifecycle.py first validates that the final and previous/prerelease artifacts have the same declared target and that target matches the native runner OS/architecture; a mismatch fails before any executable launch. It resolves daemon_serve, daemon_start, daemon_stop, and daemon_restart only from generated LIFECYCLE_COMMAND_SPECS, installs the artifact into a clean prefix, snapshots the parent PATH, and passes the OS-system-tools-only PATH only to installed-artifact child processes. It executes every phase in order: direct codesextantd serve/health; MCP initialize, tools/list, and tools/call through the pinned external official SDK/client and compatibility authority; CLI index plus separate high-confidence Python and TypeScript reference assertions; authenticated registry-derived stop/cleanup; CLI daemon start and registry-derived restart with the same published revision and identical analysis contract; every registry-derived PORT_CONFLICT/DAEMON_INSTANCE_MISMATCH case; previous-artifact upgrade/rollback with schema, strong identity, shared legacy physical store, and three-entrypoint preservation; uninstall of all five executables; and parent-PATH restoration even on failure. During upgrade it compares the artifacts' `analysis_contract_sha256`: identical contracts must reuse the revision, while a changed contract must perform one controlled analyzer-appropriate rebuild/new revision and then prove the immediately repeated index is stable zero-write reuse. Cross-contract stale-revision reuse is always a lifecycle failure. The lifecycle fragment binds official SDK version/lock digest, negotiated MCP protocol version, every MCP phase result, and all four lifecycle command spec digests.

Every G5 F4 job runs this same lifecycle runner on the matching native Windows x86_64, Linux x86_64/aarch64, or macOS x86_64/aarch64 host against that target's final and same-target previous/prerelease artifacts. Each job produces one canonical lifecycle fragment binding target, staging/source/export identities, workflow run/job identity, runner OS/architecture, final and previous artifact hashes, the contract digest, all 19 ordered native phase results, and the separate G5 rollback/failed-update extension phases; the job signs that fragment with the pinned cosign/OIDC identity and emits its Sigstore bundle. F4 aggregation verifies configured workflow identities/OIDC issuers and shared immutable identities, accepts exactly five target-distinct signed fragments and bundles, rejects duplicate/missing/emulated/diagnostic evidence, and emits the signed native-lifecycle-matrix.json. Static inspection or foreign-target emulation cannot pass lifecycle.

G5 F5 `release/package.py lifecycle-receipt --verify-only` must never call release/run_native_lifecycle.py or launch a packaged binary. It verifies the contract/schema/digest/order, signed matrix and its bundle, exactly five fragments and their bundles, target and workflow identities, same-target previous-artifact evidence, and extension phases, then emits only the internal G3 lifecycle gate-candidate through the anonymous/delete-on-close inherited exclusive handle supplied by product-frozen `tools/release_gate.py produce-and-seal`. The domain producer accepts no registered final `--out`, final receipt pathname, delete, replace, or rename operation; only the generic sealer may validate the candidate, add generic maps, and atomically create `g3-lifecycle.json`. `tests/release/test_native_lifecycle_contract.py` statically and dynamically rejects any direct final-path writer, path-like candidate argument, stdout candidate, missing inherited handle, or second writer. Missing, merged, renamed, skipped, generic cli/mcp/http, unsigned, wrong-runner, identity-mismatched, or absent previous-artifact evidence fails closed. A Windows-local F5 host therefore verifies Linux/macOS evidence cryptographically and structurally but never executes those foreign binaries.

- [ ] **Step 5: Run a same-target Windows packaged-lifecycle diagnostic**

~~~powershell
$originalPath = $env:PATH
try {
    $previousArtifact = $env:CODESEXTANT_PREVIOUS_ARTIFACT
    if (-not $previousArtifact -or -not (Test-Path -LiteralPath $previousArtifact)) { throw 'CODESEXTANT_PREVIOUS_ARTIFACT must name the designated same-target previous/prerelease artifact' }
    cargo build --locked --release -p codesextant-cli -p codesextant-mcp -p codesextant-daemon
    cargo build --locked --release -p codesextant-core --bin codesextant-ts
    C:\Python311\python.exe sidecars/build.py --orchestrator-only --toolchain-lock sidecars/toolchain.lock.json --target x86_64-pc-windows-msvc --ts-launcher target\release\codesextant-ts.exe --out dist\sidecars\x86_64-pc-windows-msvc
    C:\Python311\python.exe install/component_layout.py assemble --target x86_64-pc-windows-msvc --bin-root target\release --sidecar-root dist\sidecars\x86_64-pc-windows-msvc --out dist\installed-layout\x86_64-pc-windows-msvc
    C:\Python311\python.exe release/verify_components.py --root dist\installed-layout\x86_64-pc-windows-msvc
    cargo test --locked -p codesextant-core --test component_discovery
    $env:CODESEXTANT_TEST_CHILD_PATH = "$env:SystemRoot\System32"
    $env:CODESEXTANT_TEST_ARTIFACT_ROOT = (Resolve-Path dist\installed-layout\x86_64-pc-windows-msvc).Path
    C:\Python311\python.exe -m pytest tests/release/test_sidecar_components.py tests/release/test_no_runtime_dependency.py tests/release/test_native_lifecycle_contract.py -q
    C:\Python311\python.exe release/run_native_lifecycle.py check --contract release/native-lifecycle-contract.json --artifact-root $env:CODESEXTANT_TEST_ARTIFACT_ROOT --previous-artifact $previousArtifact --child-path $env:CODESEXTANT_TEST_CHILD_PATH
    if ($env:PATH -ne $originalPath) { throw 'parent PATH changed during packaged lifecycle test' }
} finally {
    Remove-Item Env:\CODESEXTANT_TEST_CHILD_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:\CODESEXTANT_TEST_ARTIFACT_ROOT -ErrorAction SilentlyContinue
    $env:PATH = $originalPath
}
~~~

The pytest harness passes CODESEXTANT_TEST_CHILD_PATH only as PATH in subprocess environments for the three installed product binaries and their two packaged sidecars; the Python orchestrator and cargo retain the normal parent PATH. The runner must verify both artifacts declare x86_64-pc-windows-msvc before launching them. This is same-target development diagnostics only: it writes no signed lifecycle fragment, native-lifecycle-matrix.json, or G3 receipt and cannot substitute for any F4 job. Never point this Windows-local command at Linux or macOS artifacts. Expected: all commands pass, installed children cannot discover Python or Node, and the parent PATH is restored byte-for-byte.

- [ ] **Step 6: Commit packaging contracts**

~~~powershell
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-core/Cargo.toml','crates/codesextant-cli/Cargo.toml','crates/codesextant-mcp/Cargo.toml','crates/codesextant-daemon/Cargo.toml','release/targets.toml','release/verify_components.py','release/native-lifecycle-contract.schema.json','release/native-lifecycle-contract.json','release/run_native_lifecycle.py','install/component_layout.py','sidecars/build.py','tests/release/test_sidecar_components.py','tests/release/test_no_runtime_dependency.py','tests/release/test_native_lifecycle_contract.py','crates/codesextant-core/tests/component_discovery.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'release: package semantic runtimes with CodeSextant'
~~~

---

### Task 12: Add the native reliability gate consumed by final G3 verification

**Dependencies:** Tasks 1 through 11.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-core/Cargo.toml
- Modify: crates/codesextant-daemon/Cargo.toml
- Create: tools/verify_native_kernel.py
- Create: tests/test_native_kernel_gate.py
- Create: tests/stress/test_native_concurrency.py

**Interfaces:**
- Consumes: workspace, oracle manifests, all named operation tests, sidecar builds, crash/cancellation tests, and lifecycle contract.
- Produces: check command and structured command evidence for tools/verify_g3.py.

**Dependency closure:** Root Cargo.toml adds proptest as the exact dev dependency from the authority table; tracing-subscriber remains on the Task 7 exact pin for captured stress diagnostics. codesextant-core and codesextant-daemon declare only target/dev workspace dependencies required by their tests. Cargo.lock and both manifests are staged.

- [ ] **Step 1: Write the failing command coverage test**

The gate command list must include:

- cargo metadata exact-member check;
- parser registry and parser limits;
- discovery parity/security;
- incremental index, migration, and crash recovery;
- sidecar framing, persistence, checksum, crash, and no-runtime tests;
- cancellation, queue, panic, and shutdown tests;
- all 18 named operation oracle tests;
- complete native parity checker;
- packaged lifecycle contract/runner tests, including fail-closed host/target matching; no release lifecycle receipt production;
- Rust fmt/clippy;
- 1,000 mixed requests over bounded queues with fixed seed and zero leaked tasks/processes.

- [ ] **Step 2: Run test and observe red**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_native_kernel_gate.py -q
~~~

Expected: collection FAIL because tools.verify_native_kernel does not exist.

- [ ] **Step 3: Implement fail-fast execution and structured evidence**

Every child command is invoked without a shell, with timeout, bounded captured output, redaction, start time, duration, exit code, stdout SHA-256, and stderr SHA-256. A timeout kills the process tree and returns DEADLINE_EXCEEDED. The check mode writes no receipt. The evidence mode returns a JSON object to tools/verify_g3.py; it is not a second g3-reliability producer.

- [ ] **Step 4: Run the full native gate**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_native_kernel_gate.py tests/stress/test_native_concurrency.py -q
C:\Python311\python.exe tools/verify_native_kernel.py check
~~~

Expected: all commands exit 0; 18/18 operations pass; stress reports queue capacity never exceeded, zero partial revisions, zero leaked sidecars, and zero unreaped child processes.

- [ ] **Step 5: Commit the native gate**

~~~powershell
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-core/Cargo.toml','crates/codesextant-daemon/Cargo.toml','tools/verify_native_kernel.py','tests/test_native_kernel_gate.py','tests/stress/test_native_concurrency.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'ci(native): enforce kernel and sidecar reliability'
~~~

## Native completion handoff

Return to Task 10 of the G2/G3 quality-contract plan only after:

- the public-operation oracle source and evidence are separate commits;
- native discovery matches Python classification and inventory;
- all 16 existing parser languages are bundled and bounded;
- incremental revisions survive cancellation and injected crashes;
- Jedi and ts-morph stay persistent and run from bundled components without PATH runtimes;
- deadlines and cancellation reach every layer;
- bounded queues and one-restart sidecar policy pass deterministic tests;
- each of the 18 operation IDs has an individually named oracle pass;
- the packaged lifecycle contract and runner are green, including foreign-target refusal; the five signed native executions and matrix remain G5 F4 responsibilities;
- tools/verify_native_kernel.py check exits 0.

This plan does not authorize publication or application submission.
