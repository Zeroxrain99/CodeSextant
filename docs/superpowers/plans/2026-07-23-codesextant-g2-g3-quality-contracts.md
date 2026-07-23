---
tier: 全文
status: ready-for-execution
date: 2026-07-23
scope: CodeSextant G2-G3 quality and public contracts
---

# CodeSextant G2/G3 Quality Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Make repository maps explainable and non-vacuous, then expose every supported CodeSextant operation through one typed Rust service contract whose enabled CLI, MCP, and HTTP transports agree on payloads, warnings, confidence, and transport-applicable errors.

**Architecture:** Python remains the reviewed behavior oracle during migration. G2 first changes Python map behavior, commits those source changes, and then freezes a new manifest/golden set in a separate evidence-only commit. G3 extends the G1 Rust workspace before any protocol code is added. spec/operations.yaml is the operation authority; generated Rust and OpenAPI artifacts feed thin transports around one QueryService. Native discovery, parsing, incremental storage, semantic sidecars, and operation bodies are implemented by the companion native-kernel plan, then this plan closes transport parity and emits release-subject-bound receipts.

**Tech Stack:** Python 3.11, pytest, Hypothesis, Ruff, Rust 1.96.0 edition 2024, Cargo, Tokio, Axum, Clap, generated typed MCP JSON-RPC, serde, serde_json, schemars, jsonschema, rusqlite-compatible SQLite contracts, JSON Schema 2020-12, PowerShell.

## Dependencies and execution interlock

- Execute the G0/G1 foundation plan through its clean source and frozen-oracle commits first.
- Execute Tasks 1 through 3 here; Task 3 is the last oracle-bound Python/product source commit and creates the immutable operation/lifecycle registry.
- Execute native-kernel Task 1 next so deterministic fixtures and every Python public-operation adapter exist before the base oracle freeze.
- Execute Task 4 here as the separate reviewed base manifest/golden-only commit. Native parity must consume that new manifest and no later task may edit a bound Python/product/adapter/corpus/generator path.
- Execute Tasks 5 through 9 here to establish quality gates, the complete Rust workspace, generated contracts, envelopes, and transport shells.
- Execute native-kernel Tasks 2 through 12.
- Return to Tasks 10 and 11 here for success/error transport parity, the post-freeze mutation scan, and reliability verification; then use the final receipt Runbook.
- G5 Task 1 later supplies release/evidence/release-subject.json, the closed gate-candidate/final schemas, authenticated producer launch policy, inherited-exclusive-handle transport, and the sole final writer `release_gate.py produce-and-seal`. G5 Task 7 supplies F4 target-native lifecycle execution, five identity-bound signed fragments, their exact-five signed matrix, and the F5 verification-only lifecycle candidate. Domain producers implemented here emit candidates only; they never receive a registered receipt path.

## Global constraints

- Do not publish, push to a public repository, submit an application, or claim G2/G3 complete while any gate is absent.
- Do not copy competitor source. Behavior contracts, published documentation, papers, and clean-room fixtures are allowed inputs.
- Use C:\Python311\python.exe for local Python commands.
- Dot-source the single tracked G0 SSOT `tools/exact_task_commit.ps1` and use `Invoke-ExactTaskCommit` for every implementation commit. Do not define a second helper. The helper requires exact case-sensitive A/M-only cached and committed path/status/blob/mode closure and rejects D/R/C/T, duplicates, extras, hooks, and index mutation.
- CI verifies oracle bytes but never regenerates them.
- spec/operations.yaml is the only operation list. No transport may keep a second list of names, routes, costs, side effects, confidence policy, or errors.
- Every operation implementation lives behind QueryService. CLI, MCP, and HTTP may parse, authenticate, dispatch, cancel, and render; they may not execute graph queries independently.
- Every self-map and final quality run uses a newly created CODESEXTANT_HOME and a forced index. Reusing a developer database is a gate failure.
- A zero-result map cannot pass. Missing result classes, incomplete evidence, non-finite rank values, or rank/evidence disagreement cannot pass.
- An error is tested only on transports named by applicable_transports and enabled for the operation. A transport-specific error must not be fabricated on unrelated transports.
- Final receipts live under release/evidence, remain outside Git, bind the canonical SHA-256 of release/evidence/release-subject.json, and are create-new written only by G5's authenticated generic sealer after it verifies exact entrypoint/runtime/argv/handle identity.
- Every Cargo-manifest edit has one controlled lockfile-update window: after the complete manifest set is written, run `cargo generate-lockfile` once, inspect the complete `Cargo.lock` package/checksum diff, and then run all metadata/build/test/clippy commands with `--locked`. This is the only unlocked Cargo command; missing lock drift, duplicate runtime authorities, an unpinned package, or an unexpected package/checksum change is red.

## Operation inventory

The public inventory is exactly these 18 IDs:

| ID | CLI | MCP | HTTP | Side effect | Cost |
|---|---|---|---|---|---|
| service_health | health | disabled | GET /health, auth none | none | cheap |
| doctor | doctor | disabled | disabled | none | cheap |
| status | status | codesextant_status | POST /v1/query/status | none | cheap |
| index | index | codesextant_index | POST /v1/mutate/index | write_index | heavy |
| symbols | symbols | codesextant_symbols | POST /v1/query/symbols | none | standard |
| references | refs | codesextant_references | POST /v1/query/references | none | standard |
| call_graph | calls | codesextant_call_graph | POST /v1/query/call-graph | none | standard |
| map | map | codesextant_map | POST /v1/query/map | none | heavy |
| impact | impact | codesextant_impact | POST /v1/query/impact | none | heavy |
| dead_code | dead-code | codesextant_dead_code | POST /v1/query/dead-code | none | heavy |
| unwired | unwired | codesextant_unwired | POST /v1/query/unwired | none | heavy |
| duplicates | duplicates | codesextant_duplicates | POST /v1/query/duplicates | none | heavy |
| comment_overview | comments-overview | codesextant_comment_overview | POST /v1/query/comments/overview | none | standard |
| comment_tags | comment-tags | codesextant_comment_tags | POST /v1/query/comments/tags | none | standard |
| comments | comments | codesextant_comments | POST /v1/query/comments | none | standard |
| ai_usage | ai-usage | codesextant_ai_usage | POST /v1/query/ai-usage | none | standard |
| code_health | code-health | codesextant_code_health | POST /v1/query/code-health | none | heavy |
| discipline_evaluate | discipline | codesextant_discipline_evaluate | POST /v1/query/discipline | none | heavy |

`status` is cheap only for its metadata-only default. The immutable registry's input-dependent cost override classifies `verify_fresh=true` as heavy before queue admission; no adapter or operation body may decide this independently.

---

### Task 1: Classify every indexed path and make map scope explicit

**Files:**
- Create: codesextant/source_class.py
- Create: codesextant/schema_v5.sql
- Create: codesextant/migrations.py
- Modify: codesextant/engine.py
- Modify: codesextant/storage.py
- Modify: codesextant/__main__.py
- Test: tests/test_source_class.py
- Test: tests/test_map_scope.py
- Test: tests/test_schema_v5_migration.py
- Test: tests/test_schema_v5_rollback.py
- Test: tests/parity/test_schema_v5_python_rust.py
- Create: tests/parity/fixtures/schema_v5/seed_v4.sql
- Create: tests/parity/fixtures/schema_v5/expected_v5.json
- Create: tests/fixtures/map_scope/src/public_api.py
- Create: tests/fixtures/map_scope/tests/test_public_api.py
- Create: tests/fixtures/map_scope/examples/demo.py
- Create: tests/fixtures/map_scope/generated/client.py
- Create: tests/fixtures/map_scope/vendor/dependency.py
- Create: tests/fixtures/map_scope/_poc_graph_c/probe.py
- Create: tests/fixtures/map_scope/a.py

**Interfaces:**
- Consumes: normalized repository-relative path, repository ignore rules, file metadata, and extracted public symbol evidence.
- Produces: shared schema version 5, migrate_v4_to_v5(), SourceClass, ClassificationEvidence, classify_path(), MapScope, and get_map(scope=product|tests|all).

- [ ] **Step 1: Write failing classification and scope tests**

~~~python
from codesextant.source_class import SourceClass, classify_path


def test_known_classes_are_explicit_and_stable():
    assert {item.value for item in SourceClass} == {
        "first_party_source",
        "public_test",
        "fixture",
        "example",
        "generated",
        "vendored",
        "cache",
        "build_output",
        "prototype",
        "private_project",
        "unknown",
    }


def test_one_letter_file_needs_semantic_public_evidence():
    hidden = classify_path("a.py", public_symbols=frozenset())
    exported = classify_path("x.py", public_symbols=frozenset({"x.public_api"}))
    assert hidden.source_class is SourceClass.UNKNOWN
    assert hidden.public_api_evidence is False
    assert exported.source_class is SourceClass.FIRST_PARTY_SOURCE
    assert exported.public_api_evidence is True
~~~

tests/test_map_scope.py indexes tests/fixtures/map_scope into a temporary home and asserts:

- product includes src/public_api.py;
- product excludes tests, fixtures, examples, generated, vendored, cache, build output, prototype, private-project paths, and unproven a.py;
- tests includes public_test and fixture only;
- all returns every indexed class except ignored cache/build artifacts;
- every returned row contains source_class, classification_rule_id, and public_api_evidence;
- unknown scope exits with the stable INVALID_ARGUMENT error.

tests/test_schema_v5_migration.py opens a copied schema-v4 database with representative files/symbols/refs, runs the v5 migration once, and requires source_class, classification_rule_id, and public_api_evidence columns plus schema_version 5. Existing rows receive deterministic conservative defaults unknown, legacy_unclassified, and false. A second migration is byte/row-idempotent.

tests/test_schema_v5_rollback.py injects failure after each ALTER/copy/index stage and proves the transaction rolls back to readable schema v4 with unchanged user rows and user_version. This is transactional rollback testing, not a supported destructive downgrade command.

tests/parity/test_schema_v5_python_rust.py is green in this task: it builds a temporary v4 database from seed_v4.sql, applies the shared Python v5 migration, and compares every canonical row/column/index/classification field with expected_v5.json. These frozen fixtures are the cross-language parity contract. Native Task 5 migration_parity.rs independently loads the same seed and expected JSON, applies v5 then v6 through Rust, and proves lossless v5-to-v6 parity; this Python file is never edited after the base oracle freeze.

- [ ] **Step 2: Run the tests and observe red**

~~~powershell
$env:CODESEXTANT_HOME = Join-Path $env:TEMP ("codesextant-classify-red-" + [guid]::NewGuid())
C:\Python311\python.exe -m pytest tests/test_source_class.py tests/test_map_scope.py tests/test_schema_v5_migration.py tests/test_schema_v5_rollback.py tests/parity/test_schema_v5_python_rust.py -q
~~~

Expected: FAIL because schema v5, SourceClass, MapScope, and the persisted scope fields do not exist.

- [ ] **Step 3: Implement one ordered classifier**

codesextant/source_class.py defines immutable ClassificationEvidence with source_class, rule_id, public_api_evidence, and normalized_path. Rules run in this exact precedence:

1. ignored cache and build output;
2. vendored dependency roots;
3. generated markers and generated roots;
4. private-project roots named by config;
5. prototype and experiment roots, including _poc_graph_c;
6. fixtures;
7. public tests;
8. examples;
9. configured first-party roots;
10. semantic public-symbol evidence;
11. unknown.

Path length, alphabetical order, and filename popularity are not evidence. A one-letter filename is first-party only when it is below a configured first-party root or has an extracted public symbol.

schema_v5.sql is the shared Python/Rust schema authority for G2. migrations.py upgrades v4 to v5 in one immediate transaction, validates table/column/index shape, writes schema_version only at commit, and refuses unknown future versions without mutation. storage.py loads the versioned shared resource and persists source_class, classification_rule_id, and public_api_evidence in the file row. engine.get_map accepts scope with default product and filters before ranking. codesextant/__main__.py exposes --scope product|tests|all and serializes scope in response metadata.

- [ ] **Step 4: Run focused and regression tests**

~~~powershell
$env:CODESEXTANT_HOME = Join-Path $env:TEMP ("codesextant-classify-green-" + [guid]::NewGuid())
C:\Python311\python.exe -m pytest tests/test_source_class.py tests/test_map_scope.py tests/test_schema_v5_migration.py tests/test_schema_v5_rollback.py tests/parity/test_schema_v5_python_rust.py tests/test_codemap.py tests/test_daemon_routing.py -q
C:\Python311\python.exe -m ruff check codesextant tests
~~~

Expected: all commands exit 0.

- [ ] **Step 5: Commit only source behavior**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('codesextant/source_class.py','codesextant/schema_v5.sql','codesextant/migrations.py','codesextant/engine.py','codesextant/storage.py','codesextant/__main__.py','tests/test_source_class.py','tests/test_map_scope.py','tests/test_schema_v5_migration.py','tests/test_schema_v5_rollback.py','tests/parity/test_schema_v5_python_rust.py','tests/parity/fixtures/schema_v5/seed_v4.sql','tests/parity/fixtures/schema_v5/expected_v5.json','tests/fixtures/map_scope/src/public_api.py','tests/fixtures/map_scope/tests/test_public_api.py','tests/fixtures/map_scope/examples/demo.py','tests/fixtures/map_scope/generated/client.py','tests/fixtures/map_scope/vendor/dependency.py','tests/fixtures/map_scope/_poc_graph_c/probe.py','tests/fixtures/map_scope/a.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(map): persist source classes in schema v5'
~~~

Do not generate or stage oracle manifest/golden files in this commit.

---

### Task 2: Emit deterministic explainable ranking from the existing graph pass

**Dependencies:** Task 1.

**Files:**
- Modify: codesextant/ranking.py
- Modify: codesextant/engine.py
- Test: tests/test_map_ranking.py
- Test: tests/property/test_map_ranking_properties.py
- Create: tests/fixtures/map_ranking/src/api.py
- Create: tests/fixtures/map_ranking/src/service.py
- Create: tests/fixtures/map_ranking/src/internal.py

**Interfaces:**
- Consumes: filtered product graph, incoming/outgoing edges, public API evidence, test affinity, and normalized path priority.
- Produces: ScoreEvidence and deterministic rank_map_nodes().

- [ ] **Step 1: Write failing evidence tests**

ScoreEvidence has exactly these JSON fields:

~~~json
{
  "formula_version": 1,
  "weighted_pagerank": 0.0,
  "fan_in": 0,
  "fan_out": 0,
  "public_api_evidence": false,
  "test_affinity": 0.0,
  "path_priority": 0.0,
  "total_score": 0.0
}
~~~

Tests require finite numeric values, stable ordering by total_score descending then normalized path ascending, and exact row.rank == row.score_evidence.weighted_pagerank. Reindexing the same corpus in two fresh homes must yield byte-identical canonical map JSON after removing request_id and duration_ms.

Property tests generate small directed graphs and assert no NaN/Infinity, every rank is non-negative, ties use normalized path, and no excluded source class enters the ranking pass.

- [ ] **Step 2: Run the tests and observe red**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_map_ranking.py tests/property/test_map_ranking_properties.py -q
~~~

Expected: FAIL because ranking evidence is absent.

- [ ] **Step 3: Implement one deterministic formula**

Use a fixed damping factor of 0.85, fixed convergence tolerance 1e-12, and maximum 100 iterations. Sort nodes and adjacency lists before iteration. weighted_pagerank is the converged PageRank value rounded only at canonical JSON serialization. total_score is:

~~~text
weighted_pagerank
+ min(fan_in, 50) * 0.002
+ min(fan_out, 50) * 0.001
+ 0.05 when public_api_evidence is true
+ test_affinity * 0.02
+ path_priority * 0.01
~~~

The public row rank remains weighted_pagerank for backwards compatibility; total_score controls ordering. Every component is emitted, and formula_version is 1.

- [ ] **Step 4: Run focused, property, and deterministic replay tests**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_map_ranking.py tests/property/test_map_ranking_properties.py tests/test_map_scope.py -q
C:\Python311\python.exe -m ruff check codesextant tests
~~~

Expected: all commands exit 0.

- [ ] **Step 5: Commit only source behavior**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('codesextant/ranking.py','codesextant/engine.py','tests/test_map_ranking.py','tests/property/test_map_ranking_properties.py','tests/fixtures/map_ranking/src/api.py','tests/fixtures/map_ranking/src/service.py','tests/fixtures/map_ranking/src/internal.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(map): emit deterministic score evidence'
~~~

Do not generate or stage oracle manifest/golden files in this commit.

---

### Task 3: Finalize all oracle-bound Python runtime and registry sources

**Dependencies:** Tasks 1 and 2.

**Files:**
- Modify: codesextant/daemon.py
- Modify: codesextant/__main__.py
- Modify: codesextant/panel.py
- Modify: pyproject.toml
- Create: requirements-dev.lock
- Modify: Cargo.toml
- Modify: LICENSE
- Create: NOTICE
- Modify: README.md
- Create: spec/operations.yaml
- Create: spec/operations.schema.json
- Test: tests/test_public_runtime_boundary.py
- Test: tests/test_operation_registry_source.py
- Test: tests/test_product_license.py

**Interfaces:**
- Consumes: the exact 18-operation inventory above and the private runtime literal denylist.
- Produces: the final oracle-bound Python source tree, the immutable operations/error/lifecycle registry input, and zero private runtime routes.

- [ ] **Step 1: Write failing runtime-boundary and registry tests**

tests/test_public_runtime_boundary.py imports the Python CLI/daemon/panel modules and asserts they expose no home-directory skill lookup, handoff integration, POC graph import/route/asset, private operation, or hard-coded private path. It also fixed-string scans codesextant, pyproject.toml, and README.md for .claude, handoff-tick, _poc_graph_c, E:\ai-king, and C:\Users\zerox.

tests/test_operation_registry_source.py validates operations.yaml against operations.schema.json and requires:

- exactly the 18 operation IDs in the inventory;
- nested transports only;
- the global ErrorSpec fields origin_layer, applicable_transports, retryable, and mappings;
- no mapping outside applicable_transports and no missing applicable mapping;
- lifecycle_commands as the sole serve/start/stop/restart command registry;
- every PORT_CONFLICT consumer derived from lifecycle_commands rather than an operation row or a second hard-coded set.

tests/test_product_license.py requires the product LICENSE to be the unmodified Apache License 2.0 text, pyproject.toml project.license to be Apache-2.0, the classifier list to contain exactly one `License :: OSI Approved :: Apache Software License` and no MIT/proprietary/other product-license classifier, root Cargo.toml workspace.package.license to be Apache-2.0, and NOTICE to identify CodeSextant without relicensing third-party/fixture material. It does not rewrite or assert a different license for dependencies, vendored fixtures, grammar crates, Jedi, ts-morph, or retained private test inputs.

- [ ] **Step 2: Run red**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_public_runtime_boundary.py tests/test_operation_registry_source.py tests/test_product_license.py -q
~~~

Expected: FAIL because private Python runtime paths remain and the immutable registry files do not exist.

- [ ] **Step 3: Remove private Python runtime paths permanently**

Delete home-directory skill lookup, handoff adapters, POC graph imports/routes/assets, hard-coded private paths, and panel links for private operations. The public panel renders only registry-backed public operations. AI King-only integration remains outside the CodeSextant repository. Do not relocate any denied route into another codesextant module.

- [ ] **Step 4: Author the immutable nested registry and lifecycle-command SSOT**

operations.yaml contains schema_version 1, the exact 18 operation rows, the global error table specified in Task 7, the generated execution/transport limits authority, and this exact lifecycle command registry:

~~~yaml
lifecycle_commands:
  - id: daemon_serve
    executable: codesextantd
    argv: [serve]
    transport: cli
    errors: [PORT_CONFLICT]
  - id: daemon_start
    executable: codesextant
    argv: [daemon, start]
    transport: cli
    errors: [PORT_CONFLICT]
  - id: daemon_stop
    executable: codesextant
    argv: [daemon, stop]
    transport: cli
    errors: [DAEMON_INSTANCE_MISMATCH]
  - id: daemon_restart
    executable: codesextant
    argv: [daemon, restart]
    transport: cli
    errors: [PORT_CONFLICT, DAEMON_INSTANCE_MISMATCH]
~~~

PORT_CONFLICT includes applicable_transports: [cli], mappings.cli.exit_code: 73, origin_layer: daemon, and applies_to_lifecycle_commands: [daemon_serve, daemon_start, daemon_restart]. DAEMON_INSTANCE_MISMATCH is CLI-only, non-retryable, exit 76, and applies only to daemon_stop/daemon_restart. No operation row declares either lifecycle-only error. Generated CLI help, daemon dispatch, schema validation, lifecycle tests, and error parity later consume this same lifecycle_commands node; no lifecycle phase may use literal argv.

The registry also contains exact per-cost-class `default_timeout_ms`, `max_timeout_ms`, and `queue_wait_ms`, plus generated transport limits for MCP line/JSON/string/collection/response bytes and HTTP connection/header/body/JSON/string/collection/response/keep-alive/idle budgets. Status declares a generated cost override: `verify_fresh=true` is heavy before admission; default status remains cheap. Schema rejects absent/unbounded/nonpositive/overflow limits, a queue wait above the default timeout, overlapping cost overrides, or a transport implementation constant outside the registry projection.

~~~yaml
execution_limits:
  cheap:    {default_timeout_ms: 2000,  max_timeout_ms: 10000,  queue_wait_ms: 100}
  standard: {default_timeout_ms: 10000, max_timeout_ms: 60000,  queue_wait_ms: 1000}
  heavy:    {default_timeout_ms: 60000, max_timeout_ms: 300000, queue_wait_ms: 5000}
transport_limits:
  json: {max_depth: 64, max_string_bytes: 1048576, max_collection_items: 10000}
  mcp: {max_line_bytes: 4194304, max_response_bytes: 8388608, writer_queue: 64}
  http: {max_connections: 128, max_header_count: 64, max_header_bytes: 32768,
         max_body_bytes: 4194304, max_response_bytes: 8388608,
         header_idle_ms: 5000, body_idle_ms: 30000,
         max_keepalive_requests: 100, max_connection_lifetime_ms: 300000}
~~~

operations.schema.json rejects top-level flat transport fields, duplicate command IDs/argv pairs, a lifecycle error absent from the global error table, an error-to-command reference absent from lifecycle_commands, or serve/start literals outside the registry projection tests. Pin PyYAML 6.0.2 and jsonschema 4.25.0 in the development dependency lock used by the validator; production runtime does not parse YAML.

Replace only the CodeSextant product license with Apache-2.0, set pyproject.toml project.license and root Cargo.toml workspace.package.license to Apache-2.0, replace the stale `License :: OSI Approved :: MIT License` classifier with exactly one `License :: OSI Approved :: Apache Software License`, and add NOTICE. This task is the product-license metadata authority: later Cargo workspace tasks may add members/dependencies but may not choose or change the product license. Downstream G5 is verification-only for pyproject/Cargo/LICENSE/NOTICE and may only project this authority into Node package manifests, REUSE metadata, and LICENSES/Apache-2.0.txt; it may not re-decide or edit the frozen Python metadata. Preserve every third-party and fixture license verbatim.

- [ ] **Step 5: Run green and the complete bound Python suite**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_public_runtime_boundary.py tests/test_operation_registry_source.py tests/test_product_license.py tests/test_source_class.py tests/test_map_scope.py tests/test_map_ranking.py tests/test_schema_v5_migration.py tests/test_schema_v5_rollback.py tests/parity/test_schema_v5_python_rust.py -q
C:\Python311\python.exe -m ruff check codesextant tests tools
~~~

Expected: all commands exit 0.

- [ ] **Step 6: Commit the last oracle-bound Python source change**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('codesextant/daemon.py','codesextant/__main__.py','codesextant/panel.py','pyproject.toml','requirements-dev.lock','Cargo.toml','LICENSE','NOTICE','README.md','spec/operations.yaml','spec/operations.schema.json','tests/test_public_runtime_boundary.py','tests/test_operation_registry_source.py','tests/test_product_license.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'refactor(runtime): freeze public Python and command contracts'
~~~

This is the last commit allowed to modify codesextant Python product source before the G2 base oracle evidence commit. Native Task 1 now adds the deterministic oracle adapters and fixtures; after Task 4 freezes the refreshed base oracle, no task may modify any bound Python/product/adapter/corpus/generator path.

---

### Task 4: Refresh the reviewed oracle after all G2 Python changes

**Dependencies:** Tasks 1 through 3 and native-kernel Task 1 committed; worktree clean.

**Files:**
- Modify: tests/fixtures/oracle-manifest.json
- Modify: tests/parity/golden/python-engine-v1.json
- Modify: tests/parity/golden/python-store-v1.json only when the store wire output changed

**Interfaces:**
- Consumes: the clean source commit containing Tasks 1 through 3 plus native Task 1 adapters/fixtures and tools/oracle_snapshot.py from G1.
- Produces: a separately reviewed evidence commit whose oracle.source_commit names the complete G2 Python/adapter/fixture source commit.

- [ ] **Step 1: Prove the old oracle is stale without rewriting it**

~~~powershell
git status --porcelain
$oracleSourceCommit = git rev-parse HEAD
C:\Python311\python.exe tools/oracle_snapshot.py --verify
~~~

Expected: status is empty; verification exits 1 because Python source digest and reviewed behavior changed. The command must not modify any golden.

- [ ] **Step 2: Generate twice from the exact clean source commit**

~~~powershell
if (git status --porcelain) { throw "oracle source commit is dirty" }
$oracleSourceCommit = git rev-parse HEAD
$runA = Join-Path 'C:\Temp' ("codesextant-oracle-g2-a-" + [guid]::NewGuid())
$runB = Join-Path 'C:\Temp' ("codesextant-oracle-g2-b-" + [guid]::NewGuid())
try {
    C:\Python311\python.exe tools/oracle_snapshot.py --oracle-commit $oracleSourceCommit --write --output-root $runA
    C:\Python311\python.exe tools/oracle_snapshot.py --oracle-commit $oracleSourceCommit --write --output-root $runB
    git diff --no-index --exit-code -- $runA $runB
    if ($LASTEXITCODE -ne 0) { throw "independent G2 oracle outputs differ" }
    Copy-Item -LiteralPath (Join-Path $runA 'tests\fixtures\oracle-manifest.json') -Destination tests\fixtures\oracle-manifest.json
    Copy-Item -LiteralPath (Join-Path $runA 'tests\parity\golden\python-engine-v1.json') -Destination tests\parity\golden\python-engine-v1.json
    Copy-Item -LiteralPath (Join-Path $runA 'tests\parity\golden\python-store-v1.json') -Destination tests\parity\golden\python-store-v1.json
} finally {
    Remove-Item -LiteralPath $runA,$runB -Recurse -Force -ErrorAction SilentlyContinue
}
~~~

Expected: the two independent output trees are byte-for-byte identical. Only the manifest and affected golden JSON files are copied. The format_version 3 manifest records oracle.source_commit equal to $oracleSourceCommit; the exact tracked commit tree and environment lock; the exact historical bound-path rows against which current HEAD is checked; the executed child-process module paths and hashes loaded exclusively from that materialized commit; and complete product, parity source, harness/adapter, corpus, generator, version, and golden hashes.

- [ ] **Step 3: Review semantic differences**

~~~powershell
git diff -- tests/fixtures/oracle-manifest.json tests/parity/golden/python-engine-v1.json tests/parity/golden/python-store-v1.json
C:\Python311\python.exe tools/oracle_snapshot.py --verify-output-root . --expected-source-commit $oracleSourceCommit --precommit
C:\Python311\python.exe -m pytest tests/test_oracle_harness.py tests/test_map_scope.py tests/test_map_ranking.py tests/test_public_operation_oracle_harness.py -q
~~~

Expected: differences are limited to schema-v5 classification, scope/ranking, finalized public runtime/registry behavior, adapter/fixture closure, and their hashes. Precommit verification recomputes every bound tree and defers only the evidence-parent check.

- [ ] **Step 4: Commit only reviewed evidence**

~~~powershell
$sourceCommit = git rev-parse HEAD
. .\tools\exact_task_commit.ps1
$expectedStaged = @('tests/fixtures/oracle-manifest.json','tests/parity/golden/python-engine-v1.json')
& git diff --quiet -- tests/parity/golden/python-store-v1.json
if ($LASTEXITCODE -eq 1) { $expectedStaged += 'tests/parity/golden/python-store-v1.json' }
elseif ($LASTEXITCODE -ne 0) { throw 'unable to classify optional store-golden drift' }
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'test: refresh oracle for scoped explainable map'
~~~

~~~powershell
C:\Python311\python.exe tools/oracle_snapshot.py --verify
C:\Python311\python.exe -m pytest tests/test_oracle_manifest.py -q
~~~

Expected: the latest manifest commit has first parent $sourceCommit, changes only the evidence files, and full recomputation passes. All Rust parity work reads this refreshed manifest and fails if it names an older commit.

---

### Task 5: Build a non-vacuous isolated self-map gate and G2 candidate producer

**Dependencies:** Task 4.

**Files:**
- Create: tools/check_map_quality.py
- Create: release/evidence/g2-map-quality.schema.json
- Create: tests/test_map_quality_gate.py
- Create: tests/fixtures/map_gate_expectations.json

**Interfaces:**
- Consumes: a clean repository, product scope, a forced fresh index, the refreshed oracle manifest, the reviewed expert map/navigation expectations, final ReleaseSubject plus authoritative G5 export root, and an inherited exclusive candidate handle.
- Produces: `evaluate_map()`, `evaluate_adjudicated_map()`, `fresh_self_map()`, and `check|candidate`; `PRODUCER_ID="g2_map_quality"`, `LAUNCH_SPEC_ID="g2_map_quality"`, and `ENTRYPOINT_RELATIVE_PATH="tools/check_map_quality.py"`. It never receives or writes `release/evidence/g2-map-quality.json`.

- [ ] **Step 1: Write failing anti-vacuity tests**

Tests must independently reject:

- a reused CODESEXTANT_HOME;
- zero returned rows;
- fewer rows than min_results;
- an unknown source_class;
- product results containing generated, vendored, cache, build_output, prototype, private_project, fixture, example, or unknown;
- a one-letter path without public_api_evidence;
- missing formula_version, weighted_pagerank, fan_in, fan_out, public_api_evidence, test_affinity, path_priority, or total_score;
- bool values in numeric fields;
- NaN or Infinity;
- abs(row.rank - row.score_evidence.weighted_pagerank) greater than 1e-12;
- missing required class first_party_source;
- source commit or tree digest different from the forced index metadata;
- a candidate computed against a ReleaseSubject/export authority other than those passed by the authenticated G5 context;
- domain fields outside `payload`, a missing payload, candidate generic fields reserved for the sealer, or payload bytes that fail `g2-map-quality.schema.json`;
- a missing/extra/stale expert expectation, expectation digest drift, nDCG@10 below the reviewed threshold, a fixed navigation answer with wrong symbol/path/evidence, or a fixture marked expert-reviewed without reviewer ID and review commit;
- candidate mode pointed at the private source checkout, a caller-authored export summary, an export commit/tree unequal to the ReleaseSubject, or an authoritative export whose complete allowlist inventory changes after indexing;
- `--out`, a path-valued/stdout candidate sink, a missing/non-inherited handle, multiple writes, or any attempt to create the registered filename. Tests launch the CLI in a fresh subprocess with a controlled inheritable handle and assert one bounded JCS candidate is written to that handle only.

- [ ] **Step 2: Run the tests and observe red**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_map_quality_gate.py -q
~~~

Expected: collection FAIL because tools.check_map_quality does not exist.

- [ ] **Step 3: Implement forced isolation and exact evaluation**

fresh_self_map() always creates TemporaryDirectory(prefix="codesextant-map-gate-"), sets CODESEXTANT_HOME inside it while preserving/restoring the caller's prior environment in a `try/finally`, asserts that no project database existed before indexing, invokes index_project(repo, force=True), and then invokes get_map(repo, scope="product", token_budget=budget). It records the indexed Git commit and a deterministic tracked-source tree digest. It never accepts a caller-provided persistent home.

evaluate_map() receives min_results and required_classes. It validates the exact known-class enum, complete evidence object, finite non-bool numeric fields, rank equality tolerance 1e-12, allowed product classes, one-letter semantic evidence, and source/index identity. min_results must be at least 1; the release self-map command uses 50.

`tests/fixtures/map_gate_expectations.json` is a reviewed, immutable expert fixture rather than an unused sample. It contains `schema_version`, `review_commit`, nonempty `reviewer_ids`, fixed repository/tree digest, ordered expected core concepts with relevance grades, fixed navigation questions with exact symbol/path/evidence answers, `minimum_ndcg_at_10`, and `minimum_navigation_success_rate`. `evaluate_adjudicated_map()` validates exact-key equality, recomputes the fixture/tree digest, calculates nDCG@10, checks every navigation answer against the same published index revision, and fails on ambiguity, missing evidence, an unknown expectation, or a threshold miss. The candidate payload binds the complete expectation SHA-256, reviewer IDs, review commit, nDCG@10, navigation numerator/denominator, and threshold values.

Development `check --repo .` is explicitly `authority=diagnostic`. Final `candidate` requires the G5 F5 `$exportRoot`, first invokes `tools/public_export.py assert-authoritative-root --subject <subject> --repo <repo>` and `tools/public_export.py audit --repo <repo>`, snapshots the exact export commit/tree and complete allowlist inventory before indexing, and rechecks them after evaluation. A private checkout, symlink/reparse alias, dirty export, inventory drift, subject mismatch, missing inherited handle, or handle reuse exits 2 without emitting bytes.

The candidate contains exactly `issued_at_utc`, reviewer, tools, artifacts, checks, status, and these G2-specific fields under `payload`:

~~~text
source_commit
source_tree_sha256
export_commit
export_tree_sha256
allowlist_inventory_sha256
fresh_home = true
scope = product
min_results
result_count
observed_classes
formula_version
expert_expectations_sha256
expert_review_commit
expert_reviewer_ids
ndcg_at_10
navigation_passed
navigation_total
commands with argv, exit_code, stdout_sha256, stderr_sha256, started_at_utc, duration_ms
~~~

It JCS-serializes once to the inherited handle only after every check passes. It never writes a pathname or any generic final-envelope field (`gate`, `subject_sha256`, `producer_id`, `launch_spec_id`, dependency/material maps, or `sealed_by`). G5 later authenticates the exact entrypoint bytes and digest-addressed release-Python runtime from `requirements/release.lock`; its launch spec fixes argv prefix `candidate` and `candidate_transport=inherited_exclusive_handle`.

- [ ] **Step 4: Run focused and live self-map checks**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_map_quality_gate.py tests/test_map_scope.py tests/test_map_ranking.py -q
C:\Python311\python.exe tools/check_map_quality.py check --repo . --scope product --budget 12000 --min-results 50 --required-class first_party_source
~~~

Expected: tests pass; the live source-tree diagnostic exits 0, reports `authority=diagnostic`, fresh_home=true, at least 50 rows, only allowed product classes, the reviewed nDCG@10 threshold, and every fixed navigation answer. It cannot write `release/evidence/g2-map-quality.json`.

- [ ] **Step 5: Commit the gate without a final receipt**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('tools/check_map_quality.py','release/evidence/g2-map-quality.schema.json','tests/test_map_quality_gate.py','tests/fixtures/map_gate_expectations.json')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'ci(map): reject vacuous or stale quality evidence'
~~~

release/evidence/g2-map-quality.json is not created until the final runbook invokes G5's generic producer/sealer after release-subject freeze.

---

### Task 6: Bootstrap the complete G3 Rust workspace before contract code

**Dependencies:** G1 Task 8 and this plan Task 5.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Create: crates/codesextant-protocol/Cargo.toml
- Create: crates/codesextant-protocol/src/lib.rs
- Create: crates/codesextant-cli/Cargo.toml
- Create: crates/codesextant-cli/src/lib.rs
- Create: crates/codesextant-cli/src/main.rs
- Create: crates/codesextant-mcp/Cargo.toml
- Create: crates/codesextant-mcp/src/lib.rs
- Create: crates/codesextant-mcp/src/main.rs
- Create: crates/codesextant-daemon/Cargo.toml
- Create: crates/codesextant-daemon/src/lib.rs
- Create: crates/codesextant-daemon/src/main.rs
- Create: crates/codesextant-sidecar-protocol/Cargo.toml
- Create: crates/codesextant-sidecar-protocol/src/lib.rs
- Create: crates/codesextant-parser/Cargo.toml
- Create: crates/codesextant-parser/src/lib.rs
- Create: xtask/Cargo.toml
- Create: xtask/src/main.rs
- Create: tools/check_workspace.py
- Test: tests/test_rust_workspace.py

**Interfaces:**
- Consumes: G1 root workspace with codesextant-core and codesextant-store.
- Produces: one Cargo workspace containing core, store, protocol, parser, cli, mcp, daemon, sidecar-protocol, and xtask.

- [ ] **Step 1: Add an exact-member test and observe red**

`tests/test_rust_workspace.py` runs `cargo metadata --locked --format-version 1 --no-deps` to require this exact workspace package set:

~~~text
codesextant-core
codesextant-store
codesextant-protocol
codesextant-cli
codesextant-mcp
codesextant-daemon
codesextant-sidecar-protocol
codesextant-parser
xtask
~~~

The same test imports `codesextant._version.__version__`, reads `codesextant_core::PRODUCT_VERSION` through a tiny test binary, rejects `CARGO_PKG_VERSION` in all product-facing entry points, and requires each of `codesextant --version`, `codesextant-mcp --version`, and `codesextantd --version` to print exactly `CodeSextant 0.16.0` to stdout with no internal Cargo 0.1.0 version. It separately runs full `cargo metadata --locked --format-version 1` (without `--no-deps`) and `cargo tree --locked -e normal -d` to prove the resolved graph contains exactly one `windows-sys` version, 0.61.2, and later exactly one runtime `tree-sitter`. The root Cargo.toml declaration—not the transitive resolved feature union—must have exactly `Win32_Foundation`, `Win32_Globalization`, `Win32_Security`, `Win32_Security_Authorization`, `Win32_Storage_FileSystem`, `Win32_System_JobObjects`, `Win32_System_Memory`, `Win32_System_SystemInformation`, and `Win32_System_Threading`, matching the G1/native authority; Tokio may legitimately activate additional `windows-sys` features transitively. The test rejects crate-local versions/features and direct use outside the target-specific owning core/daemon manifests.

Root Cargo.toml must use this exact members array:

~~~toml
members = [
  "crates/codesextant-core",
  "crates/codesextant-store",
  "crates/codesextant-protocol",
  "crates/codesextant-parser",
  "crates/codesextant-cli",
  "crates/codesextant-mcp",
  "crates/codesextant-daemon",
  "crates/codesextant-sidecar-protocol",
  "xtask",
]
~~~

~~~powershell
C:\Python311\python.exe -m pytest tests/test_rust_workspace.py -q
~~~

Expected: FAIL because the G1 workspace contains only core and store.

- [ ] **Step 2: Prove Cargo itself fails on missing declared members**

Replace the root Cargo.toml members array with the exact nine package paths listed above before creating the seven new manifests, then run:

~~~powershell
cargo metadata --locked --format-version 1 --no-deps
cargo metadata --locked --format-version 1
~~~

Expected: exit nonzero naming the first missing Cargo.toml. This is the required workspace-bootstrap red state; do not commit it.

- [ ] **Step 3: Create every manifest and real bootstrap entry point**

Use workspace.package edition 2024, rust-version 1.96, license = "Apache-2.0", version inherited from the root, and exact workspace dependency pins serde = 1.0.229 with derive/std, serde_json = 1.0.151 with std and preserve_order disabled, thiserror = 2.0.19 with std, schemars = 1.0.4 with derive/std, clap = 4.5.41 with std/derive/env/help/usage/error-context, tokio = 1.48.0 with rt-multi-thread/macros/process/io-util/io-std/sync/time/signal/fs/net, axum = 0.8.4 with http1/json/tokio, tower = 0.5.2 with util/timeout/limit, getrandom = 0.3.3 with std, subtle = 2.6.1, hex = 0.4.3 with std, and tempfile = 3.27.0. Every requirement is an exact = pin under workspace.dependencies, every product crate uses dependency.workspace = true and license.workspace = true, and no crate adds local features. `default-features = false` is explicit for every row; the listed standard-library features are explicit rather than relying on unrelated transitive feature unification. The explicit Clap feature set preserves generated help, usage, and error context despite disabled defaults. Tokio 1.48.0 is the minimum reviewed exact pin whose Windows dependency can resolve through the single workspace `windows-sys = 0.61.2` authority; explicit `io-std` is required for the async MCP stdin/stdout transport. `tests/test_rust_workspace.py` asserts each exact root feature set as well as the single resolved Windows runtime version. codesextant-daemon declares getrandom, subtle, and hex at bootstrap so Task 9 can generate a 256-bit token, encode it, and compare it in constant time without another dependency edit. Cargo.lock is committed; every Cargo build/test/clippy/run/check/metadata invocation uses --locked, including candidate-producing cargo run. Cargo fmt, cargo deny, and cargo audit keep their native syntax because those subcommands do not accept Cargo's lockfile flag. The external G5 producer launch policy authenticates the exact canonical package/subcommand identity for `cargo run --locked -q -p xtask -- contracts candidate`; callers cannot substitute a Cargo binary, package source, argv prefix, or stdout/path sink.

After all nine manifests and exact dependency rows exist, run the sole controlled unlocked command and immediately prove it is stable:

~~~powershell
cargo generate-lockfile
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath Cargo.lock -PathType Leaf)) { throw 'controlled G3 Cargo.lock generation failed' }
$lockStatus = @(git status --short -- Cargo.lock)
if ($lockStatus.Count -ne 1) { throw "unexpected lockfile state: $($lockStatus -join '; ')" }
cargo metadata --locked --format-version 1 | Out-Null
cargo tree --locked -e normal -d
~~~

Expected: the lockfile changes exactly once, all direct packages resolve to the exact pins, there is one `windows-sys` 0.61.2, and no command after this block changes `Cargo.lock`.

protocol, parser, and sidecar-protocol are libraries; xtask is a binary. The multi-binary product layout is authoritative: codesextant-cli declares [[bin]] name = "codesextant"; codesextant-mcp declares [[bin]] name = "codesextant-mcp"; codesextant-daemon declares [[bin]] name = "codesextantd". Installer, artifact manifest, lifecycle registry, and uninstaller must use those names.

The three product binaries implement `--version` only through the generated `codesextant_core::PRODUCT_VERSION` projection from `codesextant/_version.py`; `env!("CARGO_PKG_VERSION")` and crate metadata are forbidden for product-facing version output. They return a stable nonzero usage error for unknown arguments and do not advertise operation support until generated contracts exist in Task 7. xtask exposes workspace-check, which reads cargo metadata and rejects missing or extra members.

- [ ] **Step 4: Prove Cargo metadata and package smoke are green**

~~~powershell
cargo metadata --locked --format-version 1 --no-deps
C:\Python311\python.exe tools/check_workspace.py
C:\Python311\python.exe -m pytest tests/test_rust_workspace.py -q
C:\Python311\python.exe tools/sync_version.py --check --phase binaries
cargo check --locked --workspace --all-targets
cargo run --locked -q -p codesextant-cli --bin codesextant -- --version
cargo run --locked -q -p codesextant-mcp --bin codesextant-mcp -- --version
cargo run --locked -q -p codesextant-daemon --bin codesextantd -- --version
cargo run --locked -q -p xtask -- workspace-check
~~~

Expected: all commands exit 0, metadata contains the exact nine packages, and all product-facing version surfaces report 0.16.0 even though Cargo's internal ABI/package version remains 0.1.0.

- [ ] **Step 5: Commit the complete workspace**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-protocol/Cargo.toml','crates/codesextant-protocol/src/lib.rs','crates/codesextant-cli/Cargo.toml','crates/codesextant-cli/src/lib.rs','crates/codesextant-cli/src/main.rs','crates/codesextant-mcp/Cargo.toml','crates/codesextant-mcp/src/lib.rs','crates/codesextant-mcp/src/main.rs','crates/codesextant-daemon/Cargo.toml','crates/codesextant-daemon/src/lib.rs','crates/codesextant-daemon/src/main.rs','crates/codesextant-sidecar-protocol/Cargo.toml','crates/codesextant-sidecar-protocol/src/lib.rs','crates/codesextant-parser/Cargo.toml','crates/codesextant-parser/src/lib.rs','xtask/Cargo.toml','xtask/src/main.rs','tools/check_workspace.py','tests/test_rust_workspace.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'build(rust): bootstrap complete product workspace'
~~~

No later plan may create an undeclared product crate outside this workspace authority.

---

### Task 7: Generate every public contract from immutable operations.yaml

**Dependencies:** Task 6.

**Files:**
- Verify without modification: spec/operations.yaml
- Verify without modification: spec/operations.schema.json
- Create: spec/openapi.yaml
- Create: spec/transport-limits.json
- Create: docs/reference/operations.md
- Create: release/evidence/g3-contracts.schema.json
- Create: xtask/src/contracts.rs
- Modify: xtask/src/main.rs
- Create: crates/codesextant-protocol/src/generated/operations.rs
- Create: crates/codesextant-protocol/src/generated/transport_limits.rs
- Create: crates/codesextant-protocol/src/generated/lifecycle_commands.rs
- Create: crates/codesextant-cli/src/generated/operations.rs
- Create: crates/codesextant-cli/src/generated/lifecycle_commands.rs
- Create: crates/codesextant-mcp/src/generated/operations.rs
- Create: crates/codesextant-daemon/src/generated/operations.rs
- Create: crates/codesextant-daemon/src/generated/lifecycle_commands.rs
- Test: xtask/tests/contracts.rs
- Test: tests/test_operations_contract.py

**Interfaces:**
- Consumes: the already committed immutable 18-row operation/error/lifecycle registry from Task 3.
- Produces: OperationId, OperationSpec, TransportSet, ErrorSpec, LifecycleCommandSpec, generated typed request validators, timeout/cost/transport-limit tables, command/tool/route/lifecycle tables, OpenAPI, documentation, and the canonical `cargo run --locked -q -p xtask -- contracts candidate` producer with producer/launch ID `g3_contracts`.

- [ ] **Step 1: Write failing schema and drift tests**

Tests require operation transports to be nested:

~~~yaml
transports:
  cli:
    enabled: true
    name: map
  mcp:
    enabled: true
    name: codesextant_map
  http:
    enabled: true
    method: POST
    path: /v1/query/map
    auth: bearer
~~~

No top-level cli, mcp, http, cli_name, mcp_name, route, or method field is accepted. Enabled transports require all fields applicable to that transport; disabled transports contain only enabled: false.

Error entries require:

~~~yaml
- code: INVALID_ARGUMENT
  origin_layer: protocol
  applicable_transports: [cli, mcp, http]
  retryable: false
  mappings:
    cli: {exit_code: 2}
    mcp: {code: -32602}
    http: {status: 400}
~~~

Schema validation rejects a mapping not named in applicable_transports, a missing mapping for an applicable transport, an unknown origin_layer, duplicate operation/transport names/routes, heavy GET, stateful GET, unauthenticated non-health HTTP, an operation error code absent from the global error list, or a PORT_CONFLICT command not derived from lifecycle_commands.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
cargo test --locked -p xtask --test contracts
C:\Python311\python.exe -m pytest tests/test_operations_contract.py -q
~~~

Expected: Python source validation passes for the immutable registry; Rust tests FAIL because the generator and generated projections do not exist.

- [ ] **Step 3: Validate the immutable registry before generation**

Do not edit operations.yaml or operations.schema.json. Verify that every operation includes id, summary, cost, side_effect, input_schema, output_schema, warnings, errors, confidence_semantics, and nested transports; validate the exact inventory and the Task 3 lifecycle_commands node.

Define these global errors:

| Code | Origin | Applicable transports | CLI | MCP tools/call | HTTP |
|---|---|---|---:|---:|---:|
| INVALID_ARGUMENT | protocol | cli,mcp,http | 2 | CallToolResult isError | 400 |
| PROJECT_NOT_INDEXED | core | cli,mcp,http | 4 | CallToolResult isError | 404 |
| INDEX_STALE | core | cli,mcp,http | 5 | CallToolResult isError | 409 |
| RESOURCE_LIMIT | core | cli,mcp,http | 75 | CallToolResult isError | 413 |
| NOT_FOUND | core | cli,mcp,http | 4 | CallToolResult isError | 404 |
| PROJECT_ID_COLLISION | store | cli,mcp,http | 74 | CallToolResult isError | 409 |
| ACCESS_DENIED | protocol | cli,mcp,http | 77 | CallToolResult isError | 403 |
| AUTH_REQUIRED | transport | http | absent | absent | 401 |
| AUTH_FAILED | transport | http | absent | absent | 403 |
| METHOD_NOT_ALLOWED | transport | http | absent | absent | 405 |
| DEADLINE_EXCEEDED | core | cli,mcp,http | 124 | CallToolResult isError | 504 |
| CANCELLED | protocol | mcp,http | absent | CallToolResult isError | 499 |
| QUEUE_FULL | daemon | mcp,http | absent | CallToolResult isError | 429 |
| SIDECAR_UNAVAILABLE | sidecar | cli,mcp,http | 69 | CallToolResult isError | 503 |
| RESOLVER_UNAVAILABLE | sidecar | cli,mcp,http | 69 | CallToolResult isError | 503 |
| PORT_CONFLICT | daemon | cli | 73 | absent | absent |
| DATABASE_CORRUPT | store | cli,mcp,http | 74 | CallToolResult isError | 500 |
| DATABASE_VERSION_UNSUPPORTED | store | cli,mcp,http | 78 | CallToolResult isError | 426 |
| UPGRADE_REQUIRED | store | cli,mcp,http | 78 | CallToolResult isError | 409 |
| DAEMON_INSTANCE_MISMATCH | daemon | cli | 76 | absent | absent |
| INTERNAL | core | cli,mcp,http | 70 | CallToolResult isError | 500 |

PORT_CONFLICT applies only to generated daemon_serve/daemon_start/daemon_restart and DAEMON_INSTANCE_MISMATCH only to daemon_stop/daemon_restart. Generated CLI/daemon dispatch and error tests import LIFECYCLE_COMMAND_SPECS; no literal serve/start/stop/restart set or second command registry is permitted. RESOURCE_LIMIT is the only public mapping for internal byte/node/depth/query-match/capture/fact/repository-memory/disk/output bounds; internal PARSER_LIMIT never escapes QueryService. PROJECT_ID_COLLISION covers an exact stored-root/key/strong-ID mismatch without mutation. DATABASE_VERSION_UNSUPPORTED covers a valid future schema; malformed/negative structure remains DATABASE_CORRUPT. UPGRADE_REQUIRED covers a valid older schema that a read-only operation cannot safely serve and only writer-authorized index may migrate. AUTH_REQUIRED, AUTH_FAILED, and METHOD_NOT_ALLOWED are HTTP-only. CANCELLED and QUEUE_FULL are not fabricated as CLI query envelopes. For a valid `tools/call`, every operation success is a schema-valid MCP `CallToolResult` whose `structuredContent` matches the generated `outputSchema`, and every listed domain/tool-execution failure is a `CallToolResult` with `isError:true` plus the canonical error semantics. JSON-RPC errors are reserved for malformed JSON-RPC, unknown method/tool, invalid protocol-level params, unsupported lifecycle/version, or an exceptional failure outside the tool-execution boundary. Parity compares the canonical payload/error after unwrapping each transport; it never requires CLI/HTTP envelopes and MCP wire shapes to be byte-identical.

For every input schema, the generator emits a typed request with `deny_unknown_fields` plus one `validate()` method covering finite numeric range, UTF-8/string/cursor byte length, collection count, nesting, enums, and cross-field/mutual-exclusion rules. The schema rejects any unconstrained request field. Duplicate JSON object keys are rejected by the shared bounded decoder before Serde. Generated property tests exercise exact boundaries and compare JSON Schema/OpenAPI/MCP schema with Rust validation; schemars is generation metadata, never the runtime validator.

`cargo run --locked -q -p xtask -- contracts candidate` requires the authenticated subject/context arguments and inherited exclusive candidate handle; it rejects `--out`, stdout/path sinks, and a missing/non-inherited/reused handle. It runs schema validation, semantic validation, exact workspace-member validation, regeneration byte comparison, and enabled-surface comparison, then writes exactly one closed JCS gate-candidate to that handle. Contract-specific registry/spec/workspace/surface/generated-artifact identities live only under `payload` and validate against `release/evidence/g3-contracts.schema.json`; generic final-envelope fields are forbidden. `xtask` exports the closed launch identity `producer_id=g3_contracts`, `launch_spec_id=g3_contracts`, package `xtask`, subcommand argv prefix `["contracts","candidate"]`, and source/package closure used by G5 to authenticate pinned Cargo path/version/digest, package ID, and source-tree digest before spawn. Controlled-handle Rust integration tests prove no final path is accepted or written.

- [ ] **Step 4: Generate and byte-check every artifact**

~~~powershell
cargo run --locked -q -p xtask -- contracts generate
cargo run --locked -q -p xtask -- contracts check
cargo test --locked -p xtask --test contracts
C:\Python311\python.exe -m pytest tests/test_operations_contract.py -q
git diff --exit-code -- spec/openapi.yaml spec/transport-limits.json docs/reference/operations.md crates/codesextant-protocol/src/generated/operations.rs crates/codesextant-protocol/src/generated/transport_limits.rs crates/codesextant-protocol/src/generated/lifecycle_commands.rs crates/codesextant-cli/src/generated/operations.rs crates/codesextant-cli/src/generated/lifecycle_commands.rs crates/codesextant-mcp/src/generated/operations.rs crates/codesextant-daemon/src/generated/operations.rs crates/codesextant-daemon/src/generated/lifecycle_commands.rs
~~~

Expected: generator and check exit 0; generated files are byte-identical to a temporary regeneration.

- [ ] **Step 5: Commit the contract authority**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('spec/openapi.yaml','spec/transport-limits.json','docs/reference/operations.md','release/evidence/g3-contracts.schema.json','xtask/src/contracts.rs','xtask/src/main.rs','xtask/tests/contracts.rs','tests/test_operations_contract.py','crates/codesextant-protocol/src/generated/operations.rs','crates/codesextant-protocol/src/generated/transport_limits.rs','crates/codesextant-protocol/src/generated/lifecycle_commands.rs','crates/codesextant-cli/src/generated/operations.rs','crates/codesextant-cli/src/generated/lifecycle_commands.rs','crates/codesextant-mcp/src/generated/operations.rs','crates/codesextant-daemon/src/generated/operations.rs','crates/codesextant-daemon/src/generated/lifecycle_commands.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(protocol): define nested operation and error contracts'
~~~

---

### Task 8: Define canonical envelopes and one QueryService boundary

**Dependencies:** Task 7.

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-core/Cargo.toml
- Create: crates/codesextant-protocol/src/envelope.rs
- Create: crates/codesextant-protocol/src/error.rs
- Create: crates/codesextant-protocol/src/request.rs
- Create: crates/codesextant-protocol/src/access_scope.rs
- Modify: crates/codesextant-protocol/src/lib.rs
- Create: crates/codesextant-core/src/query_service.rs
- Modify: crates/codesextant-core/src/lib.rs
- Test: crates/codesextant-protocol/tests/envelope_contract.rs
- Test: crates/codesextant-protocol/tests/request_validation.rs
- Test: crates/codesextant-core/tests/query_service_contract.rs
- Test: crates/codesextant-core/tests/access_scope_contract.rs
- Test: crates/codesextant-core/tests/deadline_contract.rs

**Interfaces:**
- Produces: OperationRequest, OperationPayload, SuccessEnvelope, ErrorEnvelope, Warning, Confidence, unforgeable AccessScope, RequestContext, QueryService, CancellationToken, and Clock.

- [ ] **Step 1: Write failing serialization and exhaustiveness tests**

SuccessEnvelope contains schema_version, operation, request_id, data, warnings, confidence, index_revision, and duration_ms. ErrorEnvelope contains schema_version, operation, request_id, error with code/message/details/retryable/origin_layer, warnings, and duration_ms. Confidence is high, medium, low, or unknown and always includes reason_codes. Generated typed requests use `deny_unknown_fields` and expose one non-optional `validate()` implementation derived from the registry schema; direct QueryService callers cannot bypass it.

Tests canonicalize request_id and duration_ms only. They do not remove warnings, confidence, index_revision, error origin, or payload fields. `request_validation.rs` property/boundary tests all 18 variants for duplicate/unknown fields, min-1/min/max/max+1, NaN/infinity/overflow, oversized strings/cursors/lists/nesting, enum values, and mutually exclusive/cross-field rules; failures are INVALID_ARGUMENT before queue/store/sidecar invocation. Access-scope tests place a sentinel secret outside the authorized roots and attempt direct absolute paths, parent traversal, relative aliases, POSIX symlinks, Windows junctions/reparse points, config/tsconfig extends, imports, semantic-sidecar resolution, and a swap/race between validation and open. All 18 operation variants must return ACCESS_DENIED before reading any out-of-scope byte; error details/logs reveal neither the sentinel nor its path.

`tests/test_rust_workspace.py` also starts red here by requiring the acyclic package edge `codesextant-core -> codesextant-protocol`, forbidding the reverse edge, and rejecting any second service/envelope type authority. Task 6 must not predeclare an unused speculative edge; this task owns the manifest change and controlled `Cargo.lock` refresh.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
cargo test --locked -p codesextant-protocol
cargo test --locked -p codesextant-core --test query_service_contract
cargo test --locked -p codesextant-core --test access_scope_contract
~~~

Expected: FAIL because envelopes and QueryService do not exist.

- [ ] **Step 3: Implement the typed boundary**

Generated OperationRequest and OperationPayload enums have one variant for every registry ID. QueryService exposes:

~~~rust
pub async fn execute(
    &self,
    request: OperationRequest,
    context: RequestContext,
) -> Result<SuccessEnvelope<OperationPayload>, ErrorEnvelope>;
~~~

RequestContext carries request_id, one monotonic absolute deadline, cancellation token, caller transport, authenticated local principal, and an unforgeable frozen `AccessScope` capability created only by a transport bootstrap. Transport parses an optional finite positive client budget, rejects malformed/zero/negative/overflow, selects the generated cost class (including status verify_fresh override), and computes once `deadline = monotonic_now + min(client_budget_or_default, server_max)`; queue wait consumes that same budget and is capped by generated queue_wait_ms. QueryService revalidates/clamps policy for direct callers, calls the generated request `validate()` before queue/service work, and never resets timeouts. Omitted/huge/overflow/already-expired cases have exact CLI/MCP/HTTP parity. QueryService validates every repository/config/import/tsconfig/sidecar path through AccessScope before discovery or resolution and owns dispatch, confidence/warning normalization, index revision, and timing. Canonical path and file identity are rechecked at open/use time; POSIX no-follow/openat-style traversal and Windows handle/reparse-point checks reject symlink, junction, mount, hardlink escape, and TOCTOU replacement. A request may select within the frozen scope but can never widen it. QueryService accepts injected Clock and request ID generator for deterministic tests.

Root `Cargo.toml` adds `codesextant-protocol = { path = "crates/codesextant-protocol" }` under `workspace.dependencies`; `crates/codesextant-core/Cargo.toml` consumes it only with `codesextant-protocol.workspace = true`. The protocol crate remains independent of core. Run the controlled lockfile-update block from Global constraints, then require locked metadata to show the single directed edge and no cycle before compiling QueryService.

- [ ] **Step 4: Run protocol and core tests**

~~~powershell
cargo test --locked -p codesextant-protocol
cargo test --locked -p codesextant-core --test query_service_contract
cargo test --locked -p codesextant-core --test access_scope_contract
cargo test --locked -p codesextant-core --test deadline_contract
cargo clippy --locked -p codesextant-protocol -p codesextant-core --all-targets -- -D warnings
~~~

Expected: all commands exit 0.

- [ ] **Step 5: Commit the shared boundary**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-core/Cargo.toml','crates/codesextant-protocol/src/envelope.rs','crates/codesextant-protocol/src/error.rs','crates/codesextant-protocol/src/request.rs','crates/codesextant-protocol/src/access_scope.rs','crates/codesextant-protocol/src/lib.rs','crates/codesextant-protocol/tests/envelope_contract.rs','crates/codesextant-protocol/tests/request_validation.rs','crates/codesextant-core/src/query_service.rs','crates/codesextant-core/src/lib.rs','crates/codesextant-core/tests/query_service_contract.rs','crates/codesextant-core/tests/access_scope_contract.rs','crates/codesextant-core/tests/deadline_contract.rs','tests/test_rust_workspace.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(core): add canonical query service envelopes'
~~~

---

### Task 9: Generate thin CLI, MCP, and authenticated HTTP adapters

**Dependencies:** Task 8.

**Files:**
- Modify: crates/codesextant-cli/src/lib.rs
- Modify: crates/codesextant-cli/src/main.rs
- Modify: crates/codesextant-mcp/src/lib.rs
- Modify: crates/codesextant-mcp/src/main.rs
- Create: crates/codesextant-mcp/src/bounded_json.rs
- Create: crates/codesextant-mcp/src/stdout_writer.rs
- Modify: crates/codesextant-daemon/src/lib.rs
- Modify: crates/codesextant-daemon/src/main.rs
- Create: crates/codesextant-daemon/src/token_file.rs
- Create: crates/codesextant-daemon/src/instance.rs
- Create: crates/codesextant-daemon/src/transport_limits.rs
- Create: crates/codesextant-cli/tests/generated_commands.rs
- Create: crates/codesextant-mcp/tests/generated_tools.rs
- Create: crates/codesextant-mcp/tests/stdio_integrity.rs
- Create: crates/codesextant-mcp/tests/concurrent_stdio.rs
- Create: crates/codesextant-mcp/tests/request_id_lifecycle.rs
- Create: spec/mcp-compatibility.json
- Create: tests/mcp/package.json
- Create: tests/mcp/package-lock.json
- Create: tests/mcp/conformance.mjs
- Create: spec/access-scope.schema.json
- Create: docs/security/access-scope.md
- Create: tests/security/test_transport_access_scope.py
- Create: crates/codesextant-daemon/tests/http_policy.rs
- Create: crates/codesextant-daemon/tests/token_file_security.rs
- Create: crates/codesextant-daemon/tests/instance_lifecycle.rs
- Create: crates/codesextant-daemon/tests/transport_limits.rs
- Create: tests/parity/test_surface_sets.py

**Interfaces:**
- Consumes: generated operation tables, QueryService, and the tracked MCP compatibility authority.
- Produces: generated Clap/lifecycle commands, spec-conformant bounded MCP initialize/ping/cancellation/tools list/call over newline-delimited stdio, a single bounded stdout writer, numeric-loopback-only Axum routes, authenticated daemon instance records, bearer-token middleware, and /v1/meta/operations.

`stdio_integrity.rs` treats MCP stdout as an exclusive protocol channel: a client must parse every byte as the declared JSON-RPC framing with zero prefix, suffix, log, panic, or diagnostic bytes during startup, INFO/WARN/ERROR emission, invalid request, cancellation, semantic-sidecar crash, and an injected panic. All responses/notifications go through one bounded writer task: producers pre-serialize under the generated response-byte cap and enqueue one frame; the writer performs one complete `write_all(message + LF)` per item, applies deadline/backpressure, and drains or deterministically fails on shutdown. `concurrent_stdio.rs` drives 100 concurrent large success/error/cancel/panic responses with injected short writes, permits response reordering, and requires every byte to parse with no interleaving/loss/duplicate ID. Diagnostics remain only on bounded redacted stderr.

The MCP request-ID table compares exact JSON-RPC type+value, rejects duplicate live numeric/string/null IDs as protocol errors, removes an ID only at its terminal response/cancellation state, quarantines late results from cancelled process generations, and keeps client IDs separate from internal sidecar IDs. Reuse after terminal cancellation is accepted only as a new generation. Tests cover numeric/string/null duplicates, cancel+reuse, blocked stdout/backpressure, and exactly one response for every accepted ID.

`spec/mcp-compatibility.json` is the compatibility authority: preferred/supported protocol version `2025-11-25`, explicit fallback `2025-06-18`, UTF-8 newline-delimited stdio with exactly one JSON-RPC message per line and no embedded newline, and server capability `tools`. Tests require initialize to be the first non-ping request, exact protocol-version negotiation, client capabilities/clientInfo validation, result protocolVersion/capabilities/serverInfo, rejection of unsupported versions, `notifications/initialized` before operation, ping before/after initialization, `notifications/cancelled`, and schema-valid `tools/list`, `tools/call`, and JSON-RPC errors. Every generated tool declares inputSchema/outputSchema and read-only/destructive annotations derived from operations.yaml; success and domain/tool failures validate as `CallToolResult`, while unknown tool/malformed protocol requests alone validate as JSON-RPC errors. `tests/mcp/package-lock.json` pins the external official `@modelcontextprotocol/sdk = 1.29.0` client and `zod = 4.4.3` with integrity hashes; the conformance process launches the built Rust server as a black box and may not import CodeSextant protocol code.

- [ ] **Step 1: Write failing surface and policy tests**

test_surface_sets.py reads operations.yaml and compares enabled IDs against:

- codesextant --list-operations --json;
- MCP initialize followed by tools/list;
- authenticated GET /v1/meta/operations.

Generated-command tests execute the root command and every registry-backed public/lifecycle subcommand with `--help`, require exit 0 with nonempty help and usage sections, compare the advertised command set exactly to the enabled CLI registry projection, and reject every private producer/maintenance command. HTTP policy is a G3 invariant, not a default: parse and bind only numeric addresses in 127.0.0.0/8 or ::1, then verify the actual bound socket; reject 0.0.0.0, ::, interface IPs, hostnames/DNS ambiguity, forwarded-address overrides, and IPv6 dual-stack wildcard before token/endpoint publication. Remote bind is deferred to a separate TLS/mTLS design. `http_policy.rs` starts red with an exact Host/Origin matrix: canonical numeric loopback Host plus absent Origin is allowed; the explicitly configured exact local UI origin may be allowed; foreign, `null`, malformed, multiple, userinfo-bearing, DNS/hostname, wildcard, suffix-confusable, or scheme/port-mismatched Origin is rejected before body admission; `Access-Control-Allow-Origin: *` is forbidden; preflight is denied unless its exact origin/method/header tuple is allowlisted; `Sec-Fetch-Site: cross-site` is rejected; and arbitrary/hostname/forwarded Host values, including a DNS-rebinding Host resolving to loopback, are rejected. Tests prove rejection for authenticated and unauthenticated requests and zero operation/queue invocation. Tests also require a random 256-bit token file with platform-proven owner-only permissions, constant-time bearer comparison, no token in argv/logs/errors, auth none only for GET /health, 401 for missing auth, 403 for invalid auth, 405 for wrong method, and no heavy/stateful GET route. `token_file_security.rs` requires atomic secure creation and fail-closed validation under the shared StateRoot: POSIX uses no-follow semantics and exact mode 0600; Windows rejects reparse points, requires the security-descriptor owner SID to equal the current process-user SID, disables DACL inheritance, and permits only that SID with no inherited or unexpected allow ACE. Tests mutate each condition and require daemon startup, token reload, and `doctor` to fail rather than merely warn. No chmod/read-only-bit approximation may satisfy the Windows case.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
cargo test --locked -p codesextant-cli --test generated_commands
cargo test --locked -p codesextant-mcp --test generated_tools
cargo test --locked -p codesextant-mcp --test stdio_integrity
cargo test --locked -p codesextant-mcp --test concurrent_stdio
cargo test --locked -p codesextant-mcp --test request_id_lifecycle
node tests/mcp/conformance.mjs --server target/debug/codesextant-mcp --authority spec/mcp-compatibility.json
cargo test --locked -p codesextant-daemon --test http_policy
cargo test --locked -p codesextant-daemon --test token_file_security
cargo test --locked -p codesextant-daemon --test instance_lifecycle
cargo test --locked -p codesextant-daemon --test transport_limits
C:\Python311\python.exe -m pytest tests/parity/test_surface_sets.py -q
C:\Python311\python.exe -m pytest tests/security/test_transport_access_scope.py -q
~~~

Expected: FAIL because generated adapters are not wired.

- [ ] **Step 3: Implement generated adapters with no operation logic**

All pre-scheduler parsing is bounded by generated `transport_limits.rs`. MCP uses an incremental line decoder that rejects cap+1/missing-newline input before growing beyond the line cap, a duplicate-key/depth/string/collection-limited JSON decoder, and bounded output/token budgets. On violation it emits the stable protocol error when safe, otherwise closes deterministically without admitting work. HTTP applies an accept-time connection semaphore, max header count/bytes, header/body idle deadlines, bounded keep-alive request count/lifetime, Content-Length plus streaming body cap before JSON extraction, duplicate-key/depth/string/collection limits, and response cap. Bearer authentication runs after bounded headers but before body buffering; unauthorized oversized bodies are not read. Tests cover cap-1/cap/cap+1, declared-small streamed-large body, deep/duplicate JSON, oversized strings/lists, missing newline, slowloris, many partial headers/bodies, unauthenticated oversized bodies, and bounded FD/task/RSS/queue counts plus healthy-client latency.

Each adapter maps transport input to OperationRequest, builds RequestContext, calls QueryService.execute exactly once, then maps the canonical envelope using the generated error mapping for that transport. The MCP binary implements the tracked initialize/initialized state machine and version/capability negotiation, serializes each UTF-8 JSON-RPC message to one newline-terminated line without embedded newlines, reserves stdout exclusively for those messages, and installs tracing, panic, sidecar, and validation diagnostics on a bounded redacting stderr writer before any request is accepted; no default formatter may target stdout. The HTTP router derives every route/method/auth rule from OperationSpec. Before authentication/body parsing it canonicalizes and validates the actual socket, Host, Origin, preflight tuple, and Fetch Metadata against one immutable local-origin policy; it emits no permissive wildcard CORS header and never trusts DNS resolution or forwarded headers. /v1/meta/operations returns the registry projection; it is not a second list.

Transport bootstrap is the sole AccessScope minting boundary. CLI requires an explicit repository/root argument and grants exactly that canonical root for that invocation. MCP requires one or more startup `--root` values or an owner-only validated scope file, freezes them before initialize, advertises only the corresponding roots capability behavior, and rejects any request/client-roots message that attempts expansion. HTTP loads roots only at daemon startup from an owner-only scope file protected by the same POSIX mode/Windows owner-SID+DACL validator as the token, freezes the scope, and exposes no route/request field that can expand it. `docs/security/access-scope.md` documents these defaults without claiming sandboxing beyond the verified roots. The transport E2E suite runs all 18 operations against direct/traversal/link/config/import/race escapes and proves zero out-of-scope bytes reach stdout, HTTP, MCP, logs, errors, DB, or sidecar cache.

`token_file.rs` is the only token-file creator/loader. It creates a fresh 256-bit value without ever placing it in argv, a child environment, logs, or errors. On POSIX it opens with owner-only mode 0600 and no symlink following, then rechecks owner/type/mode before every read. On Windows it applies the protected security descriptor to the temporary file at creation time (no insecure inherited-ACL window), sets and verifies the descriptor owner SID as the current process-user SID, protects the DACL from inheritance, grants only that same SID, rejects reparse points and any inherited/unexpected allow ACE, and rechecks owner/type/owner-SID/DACL before every read. Atomic replacement applies the same checks to the parent and replacement file. Daemon startup and reload abort if validation cannot be proven. The registry-backed `doctor` operation calls the same validator and reports a red machine-readable result; it never weakens policy or prints the token/path contents.

`instance.rs` owns daemon start/serve/stop/restart state beneath the validated owner-only no-follow StateRoot runtime directory. Start acquires an exclusive cross-process instance lock before any bootstrap mutation; concurrent starts have one winner. Only after token creation, numeric-loopback socket bind, authenticated control endpoint, and readiness probe all succeed does it fsync/atomically publish an instance record binding a random nonce, PID, OS process creation/start identity, executable file identity+SHA-256, actual endpoint, token-generation digest, boot identity, and readiness time. Crash injection at every bootstrap stage leaves no usable ready record.

Generated daemon_stop first validates the record/lock and sends authenticated graceful control carrying the exact nonce/generation. A kill fallback is permitted only after immediately revalidating PID+creation time+boot identity+executable file identity/digest+nonce against the live process; any mismatch or PID reuse returns DAEMON_INSTANCE_MISMATCH and quarantines/removes only stale metadata, never signals that process. daemon_restart is registry-composed stop→start under the same lock and preserves these rules. Tests cover start→stop→start, restart, concurrent starts, crash at every stage, stale record targeting a live unrelated reused PID, executable replacement, runtime-directory link/reparse swap, and cleanup/recovery on Windows and POSIX.

The daemon manifest consumes the existing target-specific `windows-sys.workspace = true` authority; it does not add a version or feature list. The required security/memory/file APIs are already in the single root feature union and `tests/test_rust_workspace.py` guards that union.

MCP cancellation maps JSON-RPC cancellation to the shared token. HTTP disconnect and deadline headers cancel the same token. CLI Ctrl+C cancels local work and exits 130 without inventing a CANCELLED envelope because CANCELLED does not apply to CLI.

- [ ] **Step 4: Run adapter and contract tests**

~~~powershell
cargo test --locked -p codesextant-cli
cargo test --locked -p codesextant-mcp
cargo test --locked -p codesextant-daemon
cargo test --locked -p codesextant-daemon --test token_file_security
C:\Python311\python.exe -m pytest tests/parity/test_surface_sets.py tests/test_operations_contract.py -q
C:\Python311\python.exe -m pytest tests/security/test_transport_access_scope.py -q
cargo run --locked -q -p xtask -- contracts check
~~~

Expected: all commands exit 0.

- [ ] **Step 5: Commit thin transports**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('crates/codesextant-cli/src/lib.rs','crates/codesextant-cli/src/main.rs','crates/codesextant-cli/tests/generated_commands.rs','crates/codesextant-mcp/src/lib.rs','crates/codesextant-mcp/src/main.rs','crates/codesextant-mcp/src/bounded_json.rs','crates/codesextant-mcp/src/stdout_writer.rs','crates/codesextant-mcp/tests/generated_tools.rs','crates/codesextant-mcp/tests/stdio_integrity.rs','crates/codesextant-mcp/tests/concurrent_stdio.rs','crates/codesextant-mcp/tests/request_id_lifecycle.rs','crates/codesextant-daemon/src/lib.rs','crates/codesextant-daemon/src/main.rs','crates/codesextant-daemon/src/token_file.rs','crates/codesextant-daemon/src/instance.rs','crates/codesextant-daemon/src/transport_limits.rs','crates/codesextant-daemon/tests/http_policy.rs','crates/codesextant-daemon/tests/token_file_security.rs','crates/codesextant-daemon/tests/instance_lifecycle.rs','crates/codesextant-daemon/tests/transport_limits.rs','spec/mcp-compatibility.json','spec/access-scope.schema.json','docs/security/access-scope.md','tests/mcp/package.json','tests/mcp/package-lock.json','tests/mcp/conformance.mjs','tests/parity/test_surface_sets.py','tests/security/test_transport_access_scope.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat(transports): generate thin adapters from operation contracts'
~~~

At this checkpoint, execute the complete native-kernel-adapters plan. Do not claim transport parity until its operation bodies and sidecars are green.

---

### Task 10: Prove every public operation and applicable error on enabled transports

**Dependencies:** Task 9 and native-kernel Tasks 2 through 12.

**Files:**
- Create: tests/parity/operation_cases.yaml
- Create: tests/parity/test_transport_parity.py
- Create: tests/parity/normalize.py
- Create: tests/parity/runners.py
- Verify without modification: tests/parity/fixtures/repository

**Interfaces:**
- Consumes: operations.yaml, refreshed Python oracle, native QueryService, and all enabled transports.
- Produces: one named success case per operation and a fail-closed transport parity matrix.

- [ ] **Step 1: Write the exact case inventory**

operation_cases.yaml contains one success case for each of the 18 IDs and no other IDs. Each case names input, expected warning/confidence rules, enabled transports from operations.yaml, and canonicalization fields. service_health runs CLI and HTTP only. doctor runs CLI only. Every other operation runs CLI, MCP, and HTTP.

- [ ] **Step 2: Write the failing completeness test**

The test rejects missing/extra case IDs, an enabled transport without a runner, a disabled transport named by a case, or any canonicalization beyond request_id, duration_ms, absolute temporary paths, and transport framing. Semantic payload fields cannot be ignored.

~~~powershell
C:\Python311\python.exe -m pytest tests/parity/test_transport_parity.py -q
~~~

Expected: FAIL until all case files and runners exist.

- [ ] **Step 3: Implement isolated runners**

For every case, copy the fixture repository into a new temporary directory, create a new CODESEXTANT_HOME, disable watchers, use a fixed clock and request IDs, force index where the case requires it, then invoke:

- the built CLI binary and parse stdout JSON;
- the built MCP binary over the tracked newline-delimited MCP stdio transport, rejecting any stdout byte outside valid frames while capturing bounded redacted stderr separately; the isolated official-SDK client performs initialize, `notifications/initialized`, ping, tools/list, and tools/call before the custom parity runner is allowed to compare payloads;
- the daemon on a random loopback port with a fresh token and HTTP client.

Compare every enabled transport to QueryService output. Compare all 18 semantic payloads to tests/parity/golden/python-public-operations-v1.json from the native plan. The test asserts that public-operation-oracle-manifest.json names its clean adapter commit, binds the SHA-256 of the refreshed G2 oracle-manifest.json, and that the G2 manifest names the G2 source commit immediately preceding its reviewed evidence commit.

- [ ] **Step 4: Run every operation**

~~~powershell
cargo build --locked --workspace
C:\Python311\python.exe -m pytest tests/parity/test_transport_parity.py -q
~~~

Expected: 18 operation cases pass with the exact enabled-transport matrix and no skipped/xfail cases.

- [ ] **Step 5: Commit operation parity**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('tests/parity/operation_cases.yaml','tests/parity/test_transport_parity.py','tests/parity/normalize.py','tests/parity/runners.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'test(parity): cover every enabled public operation'
~~~

---

#### Task 10B: Prove errors only where origin and transport applicability permit

**Dependencies:** Task 10 success phase.

**Files:**
- Create: tests/parity/error_cases.yaml
- Create: tests/parity/test_error_parity.py
- Create: crates/codesextant-protocol/tests/error_matrix.rs
- Verify without modification: spec/operations.yaml lifecycle_commands

**Interfaces:**
- Consumes: ErrorSpec.origin_layer, applicable_transports, mappings, and each operation's declared errors.
- Produces: exact applicable error cases without impossible three-transport requirements.

- [ ] **Step 1: Write the failing matrix validator**

For every global error, error_cases.yaml names a deterministic trigger, origin layer, applicable transport subset, and eligible operation or lifecycle command. The validator rejects:

- a case transport absent from applicable_transports;
- an applicable transport with no mapping;
- a mapping for an inapplicable transport;
- an operation that does not declare the error;
- an MCP domain/tool-execution case encoded as a JSON-RPC error instead of `CallToolResult { isError:true }`;
- a malformed/unknown MCP protocol case encoded as a successful or domain-error CallToolResult;
- an attempt to send PORT_CONFLICT through MCP/HTTP;
- an attempt to send AUTH_REQUIRED, AUTH_FAILED, or METHOD_NOT_ALLOWED through CLI/MCP;
- an attempt to require CLI CANCELLED or QUEUE_FULL envelope parity.
- a literal serve/start/stop/restart command list in the test instead of generated lifecycle_commands cases.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
cargo test --locked -p codesextant-protocol --test error_matrix
C:\Python311\python.exe -m pytest tests/parity/test_error_parity.py -q
~~~

Expected: FAIL because deterministic error fixtures are missing.

- [ ] **Step 3: Add exact triggers and assertions**

Use invalid schema input; unindexed project; stale revision; byte/node/depth/query-match/capture/fact/repository-memory/disk/output RESOURCE_LIMIT cases with zero publication; missing symbol; injected two-root legacy project-key collision with byte-identical state; missing/invalid bearer; wrong HTTP method; expired deadline; MCP cancellation; saturated daemon queue; killed semantic sidecar; strict resolver request with sidecar disabled; occupied loopback port; stale/reused-PID daemon instance; corrupt/negative/malformed copied SQLite databases; valid future schema; valid older schema through a read-only operation; and an injected panic boundary. PORT_CONFLICT and DAEMON_INSTANCE_MISMATCH cases are parameterized exclusively from generated LIFECYCLE_COMMAND_SPECS, so daemon_serve/start/stop/restart stay in the single operations.yaml lifecycle registry. Internal PARSER_LIMIT and PublishConflict are asserted never to appear at CLI/MCP/HTTP.

For each applicable transport, assert stable code/mapping, retryable, origin_layer, warnings, and redacted details after transport-specific unwrapping. MCP cases separately validate success `structuredContent` against outputSchema, domain/tool failures as `CallToolResult {isError:true}`, and malformed/unknown protocol cases as the specified JSON-RPC error. For inapplicable transports, assert no generated mapping and no required E2E case.

- [ ] **Step 4: Run scoped error parity**

~~~powershell
cargo test --locked -p codesextant-protocol --test error_matrix
C:\Python311\python.exe -m pytest tests/parity/test_error_parity.py -q
~~~

Expected: all declared cases pass; no test synthesizes an unsupported transport path.

- [ ] **Step 5: Commit error parity**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('tests/parity/error_cases.yaml','tests/parity/test_error_parity.py','crates/codesextant-protocol/tests/error_matrix.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'test(parity): scope errors by origin and transport'
~~~

---

### Task 11: Verify the frozen Python boundary and add the G3 reliability producer

**Dependencies:** Task 10 including its error-parity phase.

**Files:**
- Create: tools/check_oracle_freeze.py
- Create: tools/verify_g3.py
- Create: release/evidence/g3-reliability.schema.json
- Create: tests/test_no_private_routes.py
- Create: tests/test_oracle_freeze_guard.py
- Create: tests/test_g3_gate.py

**Interfaces:**
- Consumes: base/public oracle manifests, their evidence commits, public operation registry, native reliability tests, sidecar lifecycle tests, and exact private literal list.
- Produces: a fail-closed post-freeze mutation proof plus `check|candidate`; `PRODUCER_ID="g3_reliability"`, `LAUNCH_SPEC_ID="g3_reliability"`, and `ENTRYPOINT_RELATIVE_PATH="tools/verify_g3.py"`. Candidate mode writes only to the inherited exclusive handle and never receives `release/evidence/g3-reliability.json`.

- [ ] **Step 1: Write failing private-route and producer tests**

tests/test_no_private_routes.py asserts no public Python/Rust/UI runtime imports or opens:

- .claude;
- handoff-tick;
- _poc_graph_c;
- E:\ai-king;
- C:\Users\zerox.

tests/test_oracle_freeze_guard.py creates a temporary Git history where a bound Python/adapter/corpus/generator file changes and is later restored byte-for-byte; the guard must still fail because post-freeze history touched a bound path. It also rejects a stale base/public manifest tree hash or invalid source/evidence parent.

tests/test_g3_gate.py requires commands covering oracle freeze history, workspace metadata, product-license consistency, contracts drift, Rust fmt/clippy/tests, Python parity, isolated map quality, deadlines, cancellation, bounded queue saturation, sidecar crash/restart, database crash recovery, exact native lifecycle contract/schema/runner unit coverage, and exact literal scanning. It also requires reliability-specific command/count/identity fields to live only under a payload valid against `release/evidence/g3-reliability.schema.json`; rejects every generic final field and `--out`; and launches a fresh child with a controlled inherited handle to prove exactly one candidate write and no registered-path write. This development reliability gate proves the runner and contract are ready; it does not launch foreign release artifacts or substitute local execution for the five signed F4 target-native lifecycle fragments.

- [ ] **Step 2: Run tests and observe red**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_no_private_routes.py tests/test_oracle_freeze_guard.py tests/test_g3_gate.py -q
~~~

Expected: the private-route assertion is already green from Task 3; collection FAILS because check_oracle_freeze.py and verify_g3.py are absent.

- [ ] **Step 3: Implement the post-freeze mutation guard**

tools/check_oracle_freeze.py imports the exact bound-path selectors from tools/oracle_snapshot.py and tools/public_operation_oracle.py, fully verifies both manifests, resolves each latest evidence commit, and inspects every commit after that evidence commit. It fails if git log reports any touch to codesextant Python/schema product files, pyproject.toml, requirements-dev.lock, ts_bridge source/lock, canonical.py, cases.py, public oracle adapters, harness tests, oracle corpora/fixture repository, or either oracle generator. A later byte-identical revert remains a failure. It prints the offending commit/path pairs and writes nothing.

- [ ] **Step 4: Implement the fail-closed reliability producer**

tools/verify_g3.py runs:

~~~text
cargo metadata --locked --format-version 1 --no-deps
cargo run --locked -q -p xtask -- contracts check
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace
C:\Python311\python.exe tools/verify_native_kernel.py check
C:\Python311\python.exe tools/check_oracle_freeze.py
Python tests for product license, surface, operation, error, lifecycle, and private routes
tools/check_map_quality.py check with fresh home and min-results 50
git diff --check
exact fixed-string private scan
~~~

The exact fixed-string PowerShell scan is:

~~~powershell
$hits = rg -n -F -e '.claude' -e 'handoff-tick' -e '_poc_graph_c' -e 'E:\ai-king' -e 'C:\Users\zerox' codesextant crates spec README.md docs/reference
if ($LASTEXITCODE -eq 0) { $hits; throw "private literal leaked into public runtime" }
if ($LASTEXITCODE -ne 1) { throw "rg failed" }
~~~

Do not use doubled-backslash regex patterns for literal Windows paths.

The candidate mode accepts authenticated subject/context arguments but no output path, records every command with argv/exit/stdout/stderr hashes and timing under the typed payload, validates `g3-reliability.schema.json`, and JCS-writes the closed candidate once to the inherited handle only when all commands pass. G5 authenticates the exact entrypoint bytes and digest-addressed release-Python runtime before launch and supplies the final subject/producer/launch/dependency/material/sealer fields itself.

- [ ] **Step 5: Run the development G3 gate**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_no_private_routes.py tests/test_oracle_freeze_guard.py tests/test_g3_gate.py -q
C:\Python311\python.exe tools/check_oracle_freeze.py
C:\Python311\python.exe tools/verify_g3.py check
~~~

Expected: all commands exit 0 and no release receipt is written.

- [ ] **Step 6: Commit verifier-only changes**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('tools/check_oracle_freeze.py','tools/verify_g3.py','release/evidence/g3-reliability.schema.json','tests/test_no_private_routes.py','tests/test_oracle_freeze_guard.py','tests/test_g3_gate.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'ci(g3): enforce frozen Python and reliability gates'
~~~

---

## G2/G3 Final Receipt Runbook

This is a post-freeze evidence operation, not a TDD implementation task and not a
source commit. Run it only after Tasks 1-11, the companion native-kernel plan, and
the named G5 prerequisites are complete. It runs in the same G5 F5 session that owns
the already-audited authoritative `$exportRoot`; a private source checkout is never
eligible for the registry-named G2 receipt.

**Dependencies:** Tasks 1 through 11; G5 Task 1 receipt schemas; G5 Task 7 F4 target-native lifecycle execution, five signed fragments, and signed matrix; final release subject frozen and clean for F5 verification-only aggregation.

**Generated evidence outside Git (create-new by G5 generic sealer only):**
- Seal: release/evidence/g2-map-quality.json
- Seal: release/evidence/g3-contracts.json
- Seal: release/evidence/g3-lifecycle.json
- Seal: release/evidence/g3-reliability.json

**Interfaces:**
- Consumes: release/evidence/release-subject.json, authenticated G5 `VerificationContext`, exact registry/launch-policy rows, the exact frozen source/artifact digests, the signed native-lifecycle-matrix.json with its Sigstore bundle, exactly five target-distinct signed lifecycle fragments with their Sigstore bundles, and one launcher-owned exclusive candidate handle per producer.
- Produces: four pass receipts bound to one subject_sha256, each final-written only by `release_gate.py produce-and-seal` after authenticating the exact producer entrypoint/runtime/argv/handle contract.

The command lines below are the sole final-receipt authority and execute inside the G5 F5 session, which owns `$artifactManifest`, `$assetRoot`, typed context, registry, launch policy, anonymous handles, and final create-new writes. Domain-producer arguments follow `--`; callers cannot choose an executable, candidate path, final path, producer label, runtime, or handle. G5 F5 documentation/tests must execute these exact subcommands, option names, and variables.

Run the whole receipt sequence in the same `pwsh` 7.4-or-newer session as G5 F5, after its fail-fast prelude. If invoked for isolated verification, run the same prelude first:

~~~powershell
if ($PSVersionTable.PSVersion -lt [Version]'7.4') { throw 'pwsh 7.4 or newer is required for fail-fast native command handling' }
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
~~~

- [ ] **Step 1: Reject pre-freeze or dirty execution**

~~~powershell
$sourceStatus = @(git status --porcelain)
if ($LASTEXITCODE -ne 0 -or $sourceStatus.Count -ne 0) { throw "source tree is not clean: $($sourceStatus -join '; ')" }
if (-not (Test-Path variable:artifactManifest) -or -not (Test-Path -LiteralPath $artifactManifest -PathType Leaf)) { throw 'G5 F5 artifactManifest is required' }
if (-not (Test-Path variable:assetRoot) -or -not (Test-Path -LiteralPath $assetRoot -PathType Container)) { throw 'G5 F5 assetRoot is required' }
if (-not (Test-Path variable:exportRoot) -or -not (Test-Path -LiteralPath $exportRoot -PathType Container)) { throw 'G5 F5 authoritative exportRoot is required' }
$releasePython = & C:\Python311\python.exe tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python
if ($LASTEXITCODE -ne 0) { throw 'locked release Python bootstrap failed' }
& $releasePython tools/release_gate.py subject-check --subject release/evidence/release-subject.json
& $releasePython tools/public_export.py assert-authoritative-root --subject release/evidence/release-subject.json --repo $exportRoot
& $releasePython tools/public_export.py audit --repo $exportRoot
& $releasePython tools/sync_version.py --check --phase final --subject release/evidence/release-subject.json --artifact-manifest $artifactManifest --asset-root $assetRoot
$gateContext = @('--subject','release/evidence/release-subject.json','--product-source-root',(Get-Location).Path,'--public-export-root',$exportRoot,'--evidence-dir',(Join-Path (Get-Location).Path 'release\evidence'),'--release-assets-root',$assetRoot,'--registry',(Join-Path (Get-Location).Path 'release\evidence\receipt-registry.json'),'--launch-policy',(Join-Path (Get-Location).Path 'release\evidence\producer-launch-policy.json'))
~~~

Expected: source status is clean and subject-check confirms private source commit/tree, public export commit/tree, artifact-manifest hash, and artifact hashes. If any source or artifact changed after freeze, stop, recreate the subject, and rerun every receipt.

- [ ] **Step 2: Emit the G2 map-quality receipt**

~~~powershell
& $releasePython tools/release_gate.py produce-and-seal --gate G2 --receipt g2-map-quality.json @gateContext -- --repo $exportRoot --scope product --budget 12000 --min-results 50 --required-class first_party_source --expectations (Join-Path $exportRoot 'tests\fixtures\map_gate_expectations.json')
if ($LASTEXITCODE -ne 0) { throw 'authenticated G2 candidate producer/sealer failed' }
~~~

Expected: exit 0; receipt reports authoritative export commit/tree/inventory equal to the ReleaseSubject, fresh_home=true, nonempty result count at least 50, known/allowed classes, complete evidence, rank agreement, reviewed expectation digest, passing nDCG@10/navigation thresholds, and matching release subject.

- [ ] **Step 3: Emit the G3 contracts receipt**

~~~powershell
& $releasePython tools/release_gate.py produce-and-seal --gate G3 --receipt g3-contracts.json @gateContext
if ($LASTEXITCODE -ne 0) { throw 'authenticated G3 contracts candidate producer/sealer failed' }
~~~

Expected: exit 0 after schema validation, generated-artifact byte comparison, exact workspace membership, and surface-set agreement.

- [ ] **Step 4: Verify signed native lifecycle evidence and emit the packaged lifecycle receipt**

~~~powershell
& $releasePython tools/release_gate.py produce-and-seal --gate G3 --receipt g3-lifecycle.json @gateContext -- --manifest $artifactManifest --asset-root $assetRoot --signing-policy release/signing-policy.json --verify-only
if ($LASTEXITCODE -ne 0) { throw 'authenticated G3 lifecycle candidate producer/sealer failed' }
~~~

Expected: exit 0 only when the authenticated `g3_lifecycle` launch spec selects the exact `release/package.py` entrypoint, pinned release Python, argv prefix `lifecycle-candidate`, and inherited-handle transport. Its `--verify-only` domain operation validates release/native-lifecycle-contract.json against its schema; verifies the signed native-lifecycle-matrix.json and its Sigstore bundle plus exactly five target-distinct lifecycle fragments and their Sigstore bundles; matches configured workflow identity/OIDC issuer, target, runner OS/architecture, staging/source/export identity, final and same-target previous/prerelease artifact hashes, contract digest, exact packaged runtime/ABI facts, and canonical phase order; and confirms one passing item for every exact ordered native phase plus the G5 rollback/failed-update extension phases. It emits only a closed candidate to the inherited handle; the generic sealer constructs the G3 final envelope. F5 must not invoke release/run_native_lifecycle.py, launch any packaged binary, rewrite a fragment/matrix, or expose a final/candidate path to the domain producer.

- [ ] **Step 5: Emit reliability and validate the gate**

~~~powershell
& $releasePython tools/release_gate.py produce-and-seal --gate G3 --receipt g3-reliability.json @gateContext
if ($LASTEXITCODE -ne 0) { throw 'authenticated G3 reliability candidate producer/sealer failed' }
& $releasePython tools/release_gate.py check --gate G2 @gateContext
& $releasePython tools/release_gate.py check --gate G3 @gateContext
~~~

Expected: all commands exit 0; each receipt has status pass and the same subject_sha256. The registry and launch policy report one closed producer/launch identity per filename, every child receives one anonymous inherited handle, and only `release_gate.py` creates a registered final path.

## G2/G3 completion evidence

Completion requires:

- the G2 Python behavior source commit followed by a distinct reviewed oracle manifest/golden commit;
- exact nine-package Cargo workspace metadata;
- no generated contract drift;
- all 18 operation success cases on their enabled transports;
- every error case only on its applicable transports;
- fresh non-vacuous self-map evidence with complete numeric agreement;
- deadline, cancellation, bounded queue, sidecar crash, and store crash tests;
- no private runtime literals or routes;
- exactly five target-native identity-bound signed lifecycle fragments and their verified signed native-lifecycle-matrix.json, with no local foreign-binary execution during F5;
- g2-map-quality.json, g3-contracts.json, g3-lifecycle.json, and g3-reliability.json bound to the same final ReleaseSubject.

This evidence authorizes only progression to later release gates. It does not authorize public publication or application submission.
