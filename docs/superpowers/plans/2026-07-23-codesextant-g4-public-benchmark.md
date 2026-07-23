---
tier: 全文
status: revision-5-independent-audit-closure
date: 2026-07-23
scope: CodeSextant G4 public benchmark
---

# CodeSextant G4 Public Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and independently reproduce a pre-registered public benchmark that proves whether the frozen CodeSextant release candidate passes every G4 competitive threshold.

**Architecture:** A Python 3.11 benchmark package owns immutable JSON contracts, deterministic corpus and competitor locks, a separately locked product runtime that mounts rather than rebuilds the ReleaseSubject Linux artifact, a complete operation-by-language capability matrix, independently adjudicated ground truth, capability-aware tool adapters, an exact resource lock, a single core-plus-agent orchestrator that atomically finalizes each run manifest, exact one-sided paired permutation tests with separately Holm-corrected core and no-tool-control agent families, detached reviewer signatures, and evidence-bound reports. Four PowerShell 7.4 scripts prepare the evaluator, run the primary host, run a physically separate independent host from a signed handoff, and finalize from a signed result bundle. Tasks G4.1 through G4.7 plus G4.8A through G4.8D implement and commit only benchmark tooling before the final freeze. The operational runbook runs only after every source-changing G5 hardening/release task has committed and G5 has frozen `release/evidence/release-subject.json`; it emits untracked receipts and release assets bound to that canonical ReleaseSubject digest and never creates a post-freeze commit.

**Tech Stack:** Python 3.11, uv lockfiles, pytest, jsonschema, psutil, Ed25519 signatures through a locked Python dependency, deterministic JSON/JSONL, digest-pinned Linux OCI containers for product/competitor/broker isolation, Git, and Markdown reports.

**Execution granularity:** Every checkbox is one 2–5 minute edit, command, or verification. Bold phase labels group related checkboxes but are not themselves completion claims. When a reference code block spans multiple files, add only the file/function named by the current checkbox, run its focused assertion, then continue.

## Global Constraints

- The daemon repair is already isolated in commit `8bd0dc2`. Complete G0 through G3 before implementing this harness; do not reopen or mix the daemon repair into benchmark commits.
- G0-created tracked `tools/exact_task_commit.ps1` and `tests/release/test_exact_task_commit.py` exist unchanged; this plan sources the former and runs the latter rather than defining a duplicate helper.
- Tasks G4.1 through G4.7 plus G4.8A through G4.8D are source-changing preparation and must finish, pass, and commit before G5 performs its final export/artifact freeze. A development pilot may expose harness defects; every repair is committed and reverified before freeze.
- The scored holdout run and independent rerun start only after all source-changing G5 hardening/tooling is complete and `release/evidence/release-subject.json` exists. They consume the exact artifact named by that ReleaseSubject, not a source-tree build.
- `release/evidence/g4-benchmark.json`, `release/evidence/g4-independent-rerun.json`, raw results, released holdout answers, and generated reports remain outside Git. No `git add`, `git commit`, tag, tracked-file edit, or lock regeneration is permitted after ReleaseSubject freeze.
- Any tracked source, documentation, workflow, lock, benchmark protocol, adapter image, export, or release artifact change invalidates ReleaseSubject and both G4 receipts. Discard the run and return to G5 final freeze; never patch evidence in place.
- Benchmark implementers may read competitor public README files, papers, release notes, and documented command interfaces, but not competitor implementation source.
- All repository and competitor revisions are full 40-character commit SHAs. Floating branches, mutable tags without a resolved SHA, and unpinned OCI tags are invalid.
- `benchmarks/corpus.lock` and `benchmarks/competitors.lock` contain JSON despite their extensionless filenames.
- Corpus source checkouts and competitor installations live under `.benchmark-cache/` and are never committed.
- Development and holdout cases use disjoint repositories. Product tuning must not read holdout answers before the frozen scored run.
- The fixed random seed is `20260723`; each performance case has 3 warm-ups followed by 10 measured repetitions.
- Published performance runs use one declared reference host, identical CPU affinity, memory limit, checkout, timeout, and network policy for every comparable tool.
- Unsupported operations are recorded as `unsupported`; they are never converted to zero and never silently removed from denominators.
- `benchmarks/capabilities.lock.json` is the pre-score authority for every `(tool, operation, language)` tuple. Each tuple is either `required` with a hash-bound successful probe fixture or `unsupported` with hash-bound public-documentation plus negative-probe evidence collected before freeze. Runtime failure never retroactively changes a required tuple to unsupported.
- Coverage and comparable denominators are separate. Coverage reports every preregistered corpus case for every tool, including unsupported/error/timeout rows. Pairwise comparison uses only preregistered pairs supported by both tools, but a build/install/probe/runtime failure on any required competitor remains a gate failure or an inconclusive comparison and always forbids a SOTA claim.
- `benchmarks/product-runtime.lock` is independent of `benchmarks/competitors.lock`. It pins only a generic Linux OCI runtime and the required `x86_64-unknown-linux-gnu` product target; the scored CodeSextant executable is mounted from the exact ReleaseSubject artifact after hash verification. CodeSextant is never built into a benchmark image.
- `benchmarks/competitors.lock` contains exactly the eight runnable external baselines in `competitors.seed.json`; CodeSextant and protocol-only SCIP are not competitor entries.
- `benchmarks/resources.lock.json` is a tracked, reviewed, pre-freeze contract for Linux host/runtime identity, product artifact target, CPU set, RAM, operation deadlines, concurrency, cold/warm cache reset, and power policy. Every run manifest binds its digest and the measured attestation proving conformance.
- A run is not scoreable until one orchestrator has completed core trials and all agent pairs, then atomically written a final manifest that hashes both result trees. A pending, partial, or post-hoc assembled manifest is invalid.
- Every operational script requires PowerShell `>=7.4`, sets `$PSNativeCommandUseErrorActionPreference=$true`, and routes every native executable through one tested `Invoke-Native` wrapper. A nonzero native exit, missing executable, truncated output, or unexpected empty scalar aborts that host's phase; `$LASTEXITCODE` is never inspected after an unwrapped command.
- Reviewer identity is a pseudonymous ID and public signing key from `benchmarks/reviewer-roles.lock`. Primary and independent runs require role-compatible, signature-valid, privacy-safe reviewer/host attestations; a reviewer assigned an implementation role cannot sign the independent rerun.
- Hidden agent evaluators are external bytes committed before either arm runs. Their signed commitment digest binds `tasks.lock`, every evaluator blob/command digest, both run manifests, comparison, and receipts; neither sandbox nor broker can read the hidden bytes.
- Every result binds the canonical ReleaseSubject SHA-256, source/export identities and artifact hashes from that subject, operation schema, corpus lock, competitor lock, ground-truth manifest, runner version, container digest, host fingerprint, seed, and command line by SHA-256.
- High-confidence reference precision must be at least 0.95; cross-language false-miswire rate at most 0.01; impact macro F1 at least 0.75 and at least 0.03 above the best reproduced baseline unless the paired interval is inconclusive; default map noise at most 0.10; forbidden entries in the default top 50 exactly 0; warm-query p95 at most 200 ms; 100-file incremental-refresh p95 at most 2,000 ms.
- Agent success, input tokens, tool calls, and cost each use a 5% non-inferiority margin. At least two of those four measures must show a statistically significant win.
- The 5% agent margin is relative, never percentage points. Endpoint direction, paired unit, relative-margin formula, primary/secondary status, family membership, and Holm family-wise correction are fixed in `benchmarks/analysis-plan.json` before any scored run.
- Agent hypotheses compare `with_codesextant` only with the preregistered `no_tool_control` arm. Those four outcomes form their own Holm family. Aider, Serena, and Codebase Memory MCP are declared `not_evaluated` for agent efficiency; no report or receipt may imply an agent comparison that was not run.
- A collection of ties is not labeled SOTA. A SOTA verdict requires every required baseline to build and run its required matrix pairs, at least one Holm-adjusted statistically significant core win over the strongest reproduced baseline, and no required competitor statistically dominating CodeSextant across an entire comparable language corpus. The only permitted wording is scoped to the exact measured corpus revision, operations, languages, and required-baseline set; no global SOTA claim is allowed.
- Corpus and adapter locks are generated only from reviewed seeds. No task hand-edits a generated lock; a seed change plus deterministic regeneration is the sole update path.
- SCIP is protocol metadata only. It is not scored as a runnable competitor unless this plan is revised to pin each language-specific SCIP indexer, its documented invocation, source commit, OCI image digest, and capability fixtures.
- Map noise and forbidden-top-50 metrics use independently adjudicated source classes only. Product-declared classes are scored separately against ground truth as a confusion matrix and never define their own correctness.
- Agent arms execute in network-disabled sandboxes containing no `.git`, remote, target child object, target patch, target answer, or hidden evaluator material.
- The provider broker is separately isolated and bound by `benchmarks/agent/broker.lock`; its executable/container digest, entrypoint, protocol digest, and captured pricing-evidence bytes are immutable inputs to both arms.
- Provider secrets are referenced by opaque credential handles and resolved only inside the broker supervisor. Workloads, orchestrator records, handoff/result bundles, manifests, and reports receive no secret or secret hash. They bind only a provider-issued nonsecret account/key identifier digest; primary and independent runs must present distinct credential-identity digests.
- The independent rerun is performed by a signature-verified reviewer who did not implement the product, harness, benchmark adapters, ground truth, or evaluator, on a physically distinct host proved by different private host-attestation identity digests. That host must satisfy the same `resources.lock`; otherwise performance reproduction is explicitly nonportable, the overall verdict is at most inconclusive, and no SOTA wording is emitted. Same-host reruns are diagnostic only and cannot issue `g4-independent-rerun.json`.

Before the first source-changing task commit in every fresh implementation shell, run the tracked helper's disposable-repository adversarial suite, then dot-source the same reviewed helper. Every commit block below passes only repository-relative leaf paths; the helper requires an initially empty index, enumerates complete cached and committed `--name-status`, accepts only exact `A`/`M` rows, and rejects deletions, renames, copies, type changes, unmerged rows, duplicates, or extra paths.

```powershell
$exactCommitHelper = Join-Path (Resolve-Path -LiteralPath '.').Path 'tools\exact_task_commit.ps1'
$exactCommitTests = Join-Path (Resolve-Path -LiteralPath '.').Path 'tests\release\test_exact_task_commit.py'
if (-not (Test-Path -LiteralPath $exactCommitHelper -PathType Leaf) -or -not (Test-Path -LiteralPath $exactCommitTests -PathType Leaf)) { throw 'G0 exact-task-commit helper/test prerequisite is missing' }
C:\Python311\python.exe -m pytest $exactCommitTests -q
if ($LASTEXITCODE -ne 0) { throw 'G0 exact-task-commit adversarial prerequisite failed' }
. $exactCommitHelper
if (-not (Get-Command Invoke-ExactTaskCommit -CommandType Function -ErrorAction SilentlyContinue)) { throw 'tracked exact-task-commit helper did not load' }
```

---

## File Structure

- `benchmarks/pyproject.toml`: isolated benchmark-only dependencies and executable entry points.
- `benchmarks/uv.lock`: exact benchmark dependency resolution.
- `benchmarks/model.py`: typed request, response, run-record, and scorecard structures.
- `benchmarks/contracts.py`: JSON-schema loading, validation, canonical JSON, and SHA-256 helpers.
- `benchmarks/schema/*.schema.json`: transport-independent benchmark contracts.
- `benchmarks/gates.json`: machine-readable G4 thresholds copied from the approved design.
- `benchmarks/analysis-plan.json`: preregistered endpoint direction, pairing unit, relative margins, Holm families, required baselines, and scoped-claim rules.
- `benchmarks/protocol.md`: frozen experimental protocol and exclusion rules.
- `benchmarks/corpus.seed.json`: reviewed repository identities and dev/holdout assignment.
- `benchmarks/corpus.lock`: resolved corpus commits, archive hashes, license evidence, and exclusions.
- `benchmarks/competitors.seed.json`: reviewed comparison set, documentation URLs, adapter/image recipes, and declared capabilities; SCIP is recorded separately as protocol-only metadata.
- `benchmarks/competitors.lock`: deterministically generated commits, licenses, documented entry points, and OCI digests; never hand-edited.
- `benchmarks/capabilities.seed.json`: exhaustive reviewed Cartesian `(tool, operation, language)` declarations; no wildcard rows.
- `benchmarks/capabilities.lock.json`: generated required/unsupported matrix with documentation and per-pair probe-fixture hashes.
- `benchmarks/images/image-digests.json`: canonical runnable-competitor OCI digest input used to regenerate `competitors.lock`.
- `benchmarks/images/product-runtime/Dockerfile`: generic artifact-free Linux runtime image.
- `benchmarks/product-runtime.lock`: product runtime OCI digest, Dockerfile/lock digests, executable mount contract, and required ReleaseSubject target.
- `benchmarks/pin_locks.py`: deterministic resolver that produces both lockfiles.
- `benchmarks/corpus.py`: clean materialization and integrity verification.
- `benchmarks/ground_truth/README.md`: adjudication rules and sampling policy.
- `benchmarks/ground_truth/dev/*.jsonl`: visible development labels.
- `benchmarks/ground_truth/holdout-manifest.json`: pre-score hashes and counts, without holdout answers.
- `benchmarks/ground_truth/state.json`: immutable tracked declaration that the holdout is sealed and answers are not tracked.
- `release/staging/g4/holdout/release-manifest.json`: ignored post-freeze proof that independently verified holdout bytes were released without changing tracked state.
- `benchmarks/adjudication.py`: case validation, reviewer agreement, count checks, sealing, and release.
- `benchmarks/adapters/base.py`: capability-aware adapter protocol and subprocess envelope.
- `benchmarks/adapters/*.py`: one normalizer per comparison tool.
- `benchmarks/adapter_fixtures/{codesextant,codegraph,codebase-memory-mcp,code-review-graph,serena,codegraphcontext,codanna,tree-sitter-analyzer,aider}/*.json`: captured documented outputs used by conformance tests.
- `benchmarks/runner.py`: deterministic scheduling and raw-record persistence.
- `benchmarks/resources.py`: deadline, CPU affinity, process-tree RSS, and termination accounting.
- `benchmarks/resources.lock.json`: exact reviewed Linux OCI/host/resource/cache/power contract.
- `benchmarks/reviewer-roles.seed.json`: reviewed pseudonymous role/public-key assignments and conflict exclusions.
- `benchmarks/reviewer-roles.lock`: deterministic reviewer-role lock.
- `benchmarks/reviewers.py`: signature verification and privacy-safe host/reviewer attestations.
- `benchmarks/manifest.py`: pending-result binding and atomic final run-manifest generation.
- `benchmarks/metrics/*.py`: classification, impact, map, search, performance, reliability, and agent metrics.
- `benchmarks/stats.py`: paired bootstrap confidence and non-inferiority intervals.
- `benchmarks/score.py`: G4 threshold evaluation.
- `benchmarks/agent/*.py`: paired agent-task execution and provider contract.
- `benchmarks/agent/sandbox.py`: Git-free, target-answer-free, network-disabled arm materialization.
- `benchmarks/agent/credential.py`: opaque handle parsing and nonsecret provider account/key identity digest; only the broker supervisor resolves a handle.
- `benchmarks/agent/credential-handle.schema.json`: closed provider/resolver/account/key/handle input contract; never a persistent result contract.
- `benchmarks/agent/evaluator-commitment.schema.json`: external hidden-evaluator commitment contract.
- `benchmarks/agent/evaluator-verification.schema.json`: custodian-signed pre-run-nonce verification receipt with a root-relative evaluator slot.
- `benchmarks/agent/broker.lock`: provider-broker image/executable/entrypoint/protocol lock.
- `benchmarks/agent/pricing-evidence/*`: exact immutable official pricing evidence bytes referenced by `pricing.lock`.
- `benchmarks/orchestrate.py`: sole scored-run entry point; core then agent then atomic manifest finalization.
- `benchmarks/handoff.py`: deterministic signed primary-handoff and independent-result bundle creation/verification.
- `benchmarks/report.py`: deterministic Markdown, JSON, and raw-result bundle generation.
- `benchmarks/independent_verify.py`: reviewer-side manifest and score comparison.
- `tests/benchmarks/*.py`: benchmark unit, contract, adversarial, and integration tests.
- `release/staging/g4/BENCHMARKS.md`: generated untracked public summary.
- `release/staging/g4/raw-results.tar.gz`: deterministic primary-plus-independent raw evidence archive.
- `release/staging/g4/holdout-ground-truth.tar.gz`: deterministic archive of the released committed-answer bytes.
- `release/staging/g4/g4-public-assets.json`: deterministic ancillary-asset manifest that G7 hashes, verifies, and uploads while the destination is still private; it is not a gate receipt or part of the G5 product artifact manifest.
- `release/g4/Invoke-Native.ps1`: PowerShell 7.4 fail-closed native-command wrapper dot-sourced by all G4 scripts.
- `release/g4/prepare-evaluator.ps1`: holdout-custodian-only pre-score evaluator commitment and verification receipt.
- `release/g4/run-primary.ps1`: primary-host execution and signed portable review-handoff producer.
- `release/g4/run-independent.ps1`: independent-host handoff verifier, execution, and signed result-bundle producer.
- `release/g4/finalize.ps1`: coordinator-side independent-result verifier, comparison, receipts, report, and G7 handoff.

### Task G4.1: Pre-register Contracts and Release Thresholds

**Files:**
- Create: `benchmarks/__init__.py`
- Create: `benchmarks/pyproject.toml`
- Create: `benchmarks/model.py`
- Create: `benchmarks/contracts.py`
- Create: `benchmarks/schema/request.schema.json`
- Create: `benchmarks/schema/response.schema.json`
- Create: `benchmarks/schema/run-record.schema.json`
- Create: `benchmarks/schema/ground-truth.schema.json`
- Create: `benchmarks/schema/scorecard.schema.json`
- Create: `benchmarks/schema/capability-matrix.schema.json`
- Create: `benchmarks/schema/analysis-plan.schema.json`
- Create: `benchmarks/schema/product-runtime.schema.json`
- Create: `benchmarks/schema/resources-lock.schema.json`
- Create: `benchmarks/schema/run-manifest.schema.json`
- Create: `benchmarks/schema/reviewer-roles.schema.json`
- Create: `benchmarks/schema/reviewer-attestation.schema.json`
- Create: `benchmarks/schema/detached-signature.schema.json`
- Create: `benchmarks/schema/g4-review-handoff.schema.json`
- Create: `benchmarks/schema/g4-independent-result.schema.json`
- Create: `benchmarks/schema/g4-benchmark-receipt.schema.json`
- Create: `benchmarks/schema/g4-independent-receipt.schema.json`
- Create: `benchmarks/gates.json`
- Create: `benchmarks/analysis-plan.json`
- Create: `benchmarks/protocol.md`
- Create: `tests/benchmarks/test_contracts.py`
- Generate: `benchmarks/uv.lock`

**Interfaces:**
- Produces: `BenchmarkRequest.to_dict() -> dict[str, object]`
- Produces: `BenchmarkResponse.to_dict() -> dict[str, object]`
- Produces: `RunRecord.to_dict() -> dict[str, object]`
- Produces: `validate_document(schema_name: str, value: object) -> None`
- Produces: `canonical_sha256(value: object) -> str`
- Produces: typed, schema-valid preregistration in `benchmarks/analysis-plan.json`.
- Consumed by: every later G4 task.

**Phase 1: Write failing contract tests**

- [ ] **Step 1.1 (2–5 min): Add contract-test imports and the request fixture**
- [ ] **Step 1.2 (2–5 min): Add the valid request/response/run-record assertion**
- [ ] **Step 1.3 (2–5 min): Add the explicit unsupported-response assertion**
- [ ] **Step 1.4 (2–5 min): Add the full-commit rejection assertion**
- [ ] **Step 1.5 (2–5 min): Add the canonical-hash assertion**
- [ ] **Step 1.6 (2–5 min): Add the exact schema-inventory assertion**
- [ ] **Step 1.7 (2–5 min): Add analysis-plan family/null/tie assertions**
- [ ] **Step 1.8 (2–5 min): Add both closed G4 receipt-schema assertions**

Create `tests/benchmarks/test_contracts.py`:

```python
import json
from pathlib import Path

import pytest

from benchmarks.contracts import canonical_sha256, load_schema, validate_document
from benchmarks.model import BenchmarkRequest, BenchmarkResponse, RunRecord


def request() -> BenchmarkRequest:
    return BenchmarkRequest(
        schema_version=1,
        run_id="run-001",
        tool="codesextant",
        tool_version="1.0.0",
        task="references",
        repo_id="flask-holdout",
        repo_path="/corpus/flask",
        query={"symbol": "Flask", "definition_path": "src/flask/app.py"},
        deadline_ms=30_000,
        config={"scope": "product"},
    )


def test_valid_documents_pass_all_contracts():
    req = request()
    resp = BenchmarkResponse(
        schema_version=1,
        status="ok",
        results=[{"path": "src/flask/app.py", "line": 12, "symbol": "Flask"}],
        coverage={"supported": True, "fraction": 1.0, "reason": None},
        warnings=[],
        error=None,
    )
    record = RunRecord(
        schema_version=1,
        request=req,
        response=resp,
        elapsed_ns=25_000,
        peak_rss_bytes=16_777_216,
        exit_code=0,
        timed_out=False,
        stdout_sha256="a" * 64,
        stderr_sha256="b" * 64,
    )
    validate_document("request", req.to_dict())
    validate_document("response", resp.to_dict())
    validate_document("run-record", record.to_dict())


def test_unsupported_is_explicit_not_an_empty_success():
    value = BenchmarkResponse(
        schema_version=1,
        status="unsupported",
        results=[],
        coverage={"supported": False, "fraction": 0.0, "reason": "operation unavailable"},
        warnings=[],
        error=None,
    ).to_dict()
    validate_document("response", value)
    value["status"] = "ok"
    with pytest.raises(Exception):
        validate_document("response", value)


def test_contract_rejects_floating_or_short_revisions():
    case = {
        "schema_version": 1,
        "case_id": "refs-001",
        "task": "references",
        "repo_id": "flask-holdout",
        "base_commit": "main",
        "split": "holdout",
        "query": {"symbol": "Flask"},
        "expected": {"locations": []},
        "ambiguity": "clear",
        "evidence": [],
        "adjudicators": ["reviewer-a", "reviewer-b"],
        "resolution": "agreement",
    }
    with pytest.raises(Exception):
        validate_document("ground-truth", case)


def test_canonical_hash_is_key_order_independent():
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def test_every_declared_schema_exists():
    root = Path(__file__).parents[2] / "benchmarks" / "schema"
    assert {p.name for p in root.glob("*.schema.json")} == {
        "analysis-plan.schema.json",
        "capability-matrix.schema.json",
        "detached-signature.schema.json",
        "g4-benchmark-receipt.schema.json",
        "g4-independent-receipt.schema.json",
        "g4-independent-result.schema.json",
        "g4-review-handoff.schema.json",
        "ground-truth.schema.json",
        "product-runtime.schema.json",
        "request.schema.json",
        "resources-lock.schema.json",
        "response.schema.json",
        "reviewer-attestation.schema.json",
        "reviewer-roles.schema.json",
        "run-record.schema.json",
        "run-manifest.schema.json",
        "scorecard.schema.json",
    }


def test_analysis_plan_preregisters_direction_pairing_relative_margin_and_holm():
    root = Path(__file__).parents[2]
    plan = json.loads((root / "benchmarks" / "analysis-plan.json").read_text(encoding="utf-8"))
    validate_document("analysis-plan", plan)
    assert plan["multiplicity_families"] == {
        "core_required_baselines": {"method": "holm", "familywise_alpha": 0.05},
        "agent_no_tool_control": {"method": "holm", "familywise_alpha": 0.05},
    }
    assert plan["agent_noninferiority"]["margin_kind"] == "relative"
    assert plan["agent_noninferiority"]["margin"] == 0.05
    assert plan["agent_noninferiority"]["control"] == "no_tool_control"
    assert plan["permutation_test"] == {
        "alternative": "greater",
        "null": "within-pair labels are exchangeable and directional win probability is 0.5",
        "statistic": "directional_nonzero_pair_wins",
        "ties": "reported and excluded from permutation denominator",
        "raw_p_value": "sum(comb(n,k) for k in range(wins,n+1)) / 2**n",
        "seed": 20260723,
        "rng_used": False,
    }
    assert {endpoint["direction"] for endpoint in plan["primary_endpoints"]} <= {
        "higher_is_better", "lower_is_better"
    }
    assert all(endpoint["paired_unit"] for endpoint in plan["primary_endpoints"])
    assert plan["sota_scope"]["required_baselines"] == [
        "aider", "code-review-graph", "codebase-memory-mcp", "codanna",
        "codegraph", "codegraphcontext", "serena", "tree-sitter-analyzer",
    ]


@pytest.mark.parametrize("name", ["g4-benchmark-receipt", "g4-independent-receipt"])
def test_g4_receipt_payload_schemas_are_closed_and_typed(name):
    schema = load_schema(name)
    assert schema["additionalProperties"] is False
    assert {
        "signed_statement", "signed_statement_sha256", "signing_key_id",
        "signing_public_key_sha256", "signature_algorithm", "signature",
    } <= set(schema["required"])
    with pytest.raises(Exception):
        validate_document(name, {"unexpected": True})
```

**Phase 2: Observe RED**

- [ ] **Step 2.1 (2–5 min): Run the focused contract test once and record the missing-module failure**

Run:

```powershell
python -m pytest tests/benchmarks/test_contracts.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'benchmarks.contracts'`.

**Phase 3: Add the benchmark package and typed models**

- [ ] **Step 3.1 (2–5 min): Add `benchmarks/pyproject.toml` with exact pins**
- [ ] **Step 3.2 (2–5 min): Add empty `benchmarks/__init__.py`**
- [ ] **Step 3.3 (2–5 min): Add `BenchmarkRequest` and `TaskKind`**
- [ ] **Step 3.4 (2–5 min): Add `BenchmarkResponse` and `RunStatus`**
- [ ] **Step 3.5 (2–5 min): Add `RunRecord` serialization**
- [ ] **Step 3.6 (2–5 min): Add canonical bytes/hash helpers**
- [ ] **Step 3.7 (2–5 min): Add schema loading/validation helpers**

Create `benchmarks/pyproject.toml`:

```toml
[project]
name = "codesextant-benchmarks"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = [
  "cryptography==45.0.5",
  "jsonschema==4.25.0",
  "psutil==7.0.0",
  "pytest==8.4.1",
]

[tool.uv]
package = false
```

Create an empty `benchmarks/__init__.py`, then create `benchmarks/model.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

TaskKind = Literal[
    "symbols", "references", "miswires", "impact", "navigation", "map",
    "cold_index", "incremental_index", "warm_query", "agent", "reliability",
]
RunStatus = Literal["ok", "unsupported", "error", "timeout"]


@dataclass(frozen=True)
class BenchmarkRequest:
    schema_version: int
    run_id: str
    tool: str
    tool_version: str
    task: TaskKind
    repo_id: str
    repo_path: str
    query: dict[str, object]
    deadline_ms: int
    config: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkResponse:
    schema_version: int
    status: RunStatus
    results: list[dict[str, object]]
    coverage: dict[str, object]
    warnings: list[str]
    error: dict[str, object] | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RunRecord:
    schema_version: int
    request: BenchmarkRequest
    response: BenchmarkResponse
    elapsed_ns: int
    peak_rss_bytes: int
    exit_code: int
    timed_out: bool
    stdout_sha256: str
    stderr_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

Create `benchmarks/contracts.py`:

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema

_SCHEMA_DIR = Path(__file__).with_name("schema")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_schema(schema_name: str) -> dict[str, object]:
    path = _SCHEMA_DIR / f"{schema_name}.schema.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_document(schema_name: str, value: object) -> None:
    jsonschema.Draft202012Validator(load_schema(schema_name)).validate(value)
```

**Phase 4: Add exact JSON contracts and thresholds**

- [ ] **Step 4.1 (2–5 min): Add request and response schemas**
- [ ] **Step 4.2 (2–5 min): Add run-record and ground-truth schemas**
- [ ] **Step 4.3 (2–5 min): Add scorecard schema**
- [ ] **Step 4.4 (2–5 min): Add capability-matrix and analysis-plan schemas**
- [ ] **Step 4.5 (2–5 min): Add product-runtime and resources-lock schemas**
- [ ] **Step 4.6 (2–5 min): Add run-manifest schema**
- [ ] **Step 4.7 (2–5 min): Add reviewer-role and attestation schemas**
- [ ] **Step 4.8 (2–5 min): Add detached-signature schema**
- [ ] **Step 4.9 (2–5 min): Add review-handoff and independent-result schemas**
- [ ] **Step 4.10 (2–5 min): Add both G4 receipt payload schemas**
- [ ] **Step 4.11 (2–5 min): Add exact `gates.json` values**
- [ ] **Step 4.12 (2–5 min): Add exact `analysis-plan.json` families and tests**
- [ ] **Step 4.13 (2–5 min): Add protocol sections from frozen machine contracts**

Each schema uses Draft 2020-12, `additionalProperties: false`, and the following required invariants:

- request: every field in `BenchmarkRequest`; `deadline_ms >= 1`.
- response: every field in `BenchmarkResponse`; an `ok` response requires `coverage.supported=true`; an `unsupported` response requires `coverage.supported=false` and a non-empty reason.
- run-record: every field in `RunRecord`; both digest fields match `^[0-9a-f]{64}$`.
- ground-truth: full 40-character `base_commit`, split `dev|holdout`, ambiguity `clear|ambiguous|excluded`, at least two unique adjudicators.
- scorecard: commit and all input hashes, per-repository metrics, confidence intervals, threshold verdicts, and overall verdict `pass|fail|inconclusive`.
- capability matrix: one unique row for every tool/operation/language tuple, disposition `required|unsupported`, and evidence hashes; wildcard tools, operations, or languages are forbidden.
- analysis plan: exact required baselines, endpoint direction/unit/formula/family, relative margins, Holm parameters, and SOTA claim template.
- product runtime: artifact-free Linux runtime digest, extraction/mount contract, and exact ReleaseSubject target.
- resources lock: Linux-only host/runtime identity, exact artifact target, CPU/RAM/time/concurrency/cache/power fields, and lowercase SHA-256 digests.
- run manifest: `state="final"`, ReleaseSubject-selected artifact identity, every lock digest, two result-tree digests, evaluator/reviewer attestations, and canonical self-digest.
- reviewer roles: unique pseudonymous reviewer IDs, Ed25519 public keys, roles, and mutually exclusive conflict roles.
- reviewer attestation: reviewer ID/role, run ID, privacy-safe host fields, process nonce, resources-lock digest, statement digest, Ed25519 signature, and no free-form identity fields.
- detached signature: a closed object containing `signed_statement`, canonical `signed_statement_sha256`, `signing_key_id`, `signing_public_key_sha256`, `signature_algorithm="Ed25519"`, and canonical-base64 `signature`; the signature fields are never part of the signed statement.
- review handoff: exact ReleaseSubject/input/selected-artifact/environment/evaluator hashes, primary final manifest/result hashes, privacy-safe primary attestation, credential-identity digest, allowlisted bundle members, and detached primary signature.
- independent result: handoff digest, independent final manifest/result/score hashes, host/resource equivalence, credential-identity digest, no-tool agent family results, required-baseline ledger, and detached independent signature.
- G4 primary receipt payload: selected product target/artifact/runtime, final core/agent manifest hashes, coverage/comparable denominators, required-baseline ledger, endpoint/Holm results, resources/evaluator/reviewer/broker/pricing evidence hashes, scoped claim, and signer/signature.
- G4 independent receipt payload: both final manifests/result trees/scorecards/attestations, host-equivalence mode, resource portability verdict, evaluator commitment, signed comparison, required-baseline/Holm reproduction, and signer/signature.

The two G4 receipt payload schemas are the exact paths referenced by the later G5 registry rows: `benchmarks/schema/g4-benchmark-receipt.schema.json` and `benchmarks/schema/g4-independent-receipt.schema.json`. Task G4.1 tests their closed typed contracts independently; Task G4.8C (which starts only after the G5 registry exists) loads the real registry, asserts those paths exactly, and invokes the registry validator with `--gate G4 --require-payload-schemas`. A missing G4 schema, a receipt envelope without `payload`, or any payload field not admitted by its schema is RED; an unrelated later-gate schema is outside this validation scope.

Create `benchmarks/gates.json` exactly as:

```json
{
  "schema_version": 1,
  "reference_precision_min": 0.95,
  "cross_language_false_miswire_max": 0.01,
  "impact_macro_f1_min": 0.75,
  "impact_delta_over_best_min": 0.03,
  "map_noise_rate_max": 0.10,
  "map_top50_forbidden_max": 0,
  "warm_query_p95_ms_max": 200.0,
  "incremental_100_files_p95_ms_max": 2000.0,
  "agent_noninferiority_margin_relative": 0.05,
  "agent_significant_wins_min": 2,
  "database_corruption_max": 0,
  "duplicate_daemon_max": 0,
  "performance_warmups": 3,
  "performance_repetitions": 10,
  "random_seed": 20260723,
  "confidence_level": 0.95,
  "familywise_alpha": 0.05,
  "multiplicity_method": "holm"
}
```

Create `benchmarks/analysis-plan.json` before any scored observation. It contains explicit core endpoint rows for reference precision (`higher_is_better`, paired by repository), cross-language false-miswire rate (`lower_is_better`, repository), impact macro F1 (`higher_is_better`, repository), map nDCG/noise (`higher_is_better`/`lower_is_better`, repository), warm-query p95 and incremental-refresh p95 (`lower_is_better`, case/repetition block). Each core row declares its exact required-baseline hypotheses. Those raw p-values form `core_required_baselines`, one Holm family at family-wise alpha 0.05.

The four agent endpoints are a separate universe: success (`higher_is_better`) and input tokens/tool calls/cost (`lower_is_better`), each paired by agent task, compare only `with_codesextant` against `no_tool_control`. Their four raw p-values form the separate `agent_no_tool_control` Holm family at 0.05. `codebase-memory-mcp`, `serena`, and `aider` are recorded as workload-capable but `not_evaluated` in this agent experiment; they produce no hypothesis, denominator, win, or comparative prose. Adding a competitor agent arm requires a new preregistration and freeze.

For every endpoint, the analysis plan freezes metric function, unit, aggregation, direction, null, tie rule, superiority boundary, confidence method, and Holm family. Significance uses the exact one-sided paired sign-permutation test: transform each paired difference so positive favors CodeSextant; count directional wins among nonzero pairs; under the sharp null, within-pair arm labels are exchangeable and win probability is 0.5; ties are reported and excluded from both win count and permutation denominator; if all pairs tie, raw p-value is 1.0; otherwise `p_raw = sum(comb(n,k), k=wins..n) / 2**n`. This enumerated/binomial-tail value is exact, not Monte Carlo, so `seed=20260723` is recorded for pair construction/scheduling but `rng_used=false` for the p-value. Any randomized or two-sided substitute is invalid.

`agent_noninferiority` defines the relative formulas exactly against only `no_tool_control`: success is non-inferior only when `CodeSextant / control >= 0.95`; a lower-is-better outcome is non-inferior only when `CodeSextant / control <= 1.05`; a zero denominator is never silently continuity-corrected and is `inconclusive` unless both paired values are exactly zero, which is a tie. Hard safety/reliability thresholds are deterministic gates, not selectively excluded from multiplicity.

The plan lists all eight required baselines in canonical sorted order and defines `sota_scope` as the exact `corpus.lock` digest plus the intersection rows of `capabilities.lock.json`. A SOTA label is invalid if any required baseline is absent, fails build/install/probe/runtime on a required pair, any Holm-adjusted primary comparison is unavailable, or the report omits the measured corpus/operation/language qualifier.

Write `benchmarks/protocol.md` with these fixed sections: scope, comparison set, corpus splits, task definitions, exhaustive capability matrix, coverage versus comparable denominators, exclusions, warm-up/repetition rules, exact resource/cache rules, randomization, ground-truth adjudication, endpoint directions and paired units, exact one-sided paired sign-permutation null/raw-p/tie rule, relative non-inferiority formulas, separate core-required-baseline and agent-no-tool-control Holm families, unrun workload-capable competitor disclosure, required-baseline failure policy, failure retention, holdout secrecy, invalidation, signed reviewer independence, and independent-rerun procedure. Copy every numeric value from `gates.json` and every analysis choice from `analysis-plan.json`; do not restate a different value.

**Phase 5: Lock and verify**

- [ ] **Step 5.1 (2–5 min): Generate `benchmarks/uv.lock` once**
- [ ] **Step 5.2 (2–5 min): Sync the frozen benchmark environment once**
- [ ] **Step 5.3 (2–5 min): Run the contract test with frozen/no-sync execution**
- [ ] **Step 5.4 (2–5 min): Run whitespace validation**

Run:

```powershell
uv lock --project benchmarks
uv sync --project benchmarks --frozen
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_contracts.py -q
```

Expected: all contract/preregistration tests pass and `benchmarks/uv.lock` exists.

**Phase 6: Commit the contract boundary**

- [ ] **Step 6.1 (2–5 min): Stage only G4.1 files and inspect the staged list**
- [ ] **Step 6.2 (2–5 min): Commit the verified contract boundary**

```powershell
$expectedStaged = @('benchmarks/__init__.py','benchmarks/pyproject.toml','benchmarks/uv.lock','benchmarks/model.py','benchmarks/contracts.py','benchmarks/schema/request.schema.json','benchmarks/schema/response.schema.json','benchmarks/schema/run-record.schema.json','benchmarks/schema/ground-truth.schema.json','benchmarks/schema/scorecard.schema.json','benchmarks/schema/capability-matrix.schema.json','benchmarks/schema/analysis-plan.schema.json','benchmarks/schema/product-runtime.schema.json','benchmarks/schema/resources-lock.schema.json','benchmarks/schema/run-manifest.schema.json','benchmarks/schema/reviewer-roles.schema.json','benchmarks/schema/reviewer-attestation.schema.json','benchmarks/schema/detached-signature.schema.json','benchmarks/schema/g4-review-handoff.schema.json','benchmarks/schema/g4-independent-result.schema.json','benchmarks/schema/g4-benchmark-receipt.schema.json','benchmarks/schema/g4-independent-receipt.schema.json','benchmarks/gates.json','benchmarks/analysis-plan.json','benchmarks/protocol.md','tests/benchmarks/test_contracts.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'bench: preregister benchmark contracts'
```

### Task G4.2: Pin Corpus and Competitor Revisions

**Files:**
- Modify: `.gitignore`
- Create: `benchmarks/corpus.seed.json`
- Create: `benchmarks/competitors.seed.json`
- Create: `benchmarks/capabilities.seed.json`
- Create: `benchmarks/pin_locks.py`
- Create: `benchmarks/corpus.py`
- Generate: `benchmarks/corpus.lock`
- Generate: `benchmarks/competitors.lock`
- Create: `tests/benchmarks/test_locks.py`
- Create: `tests/benchmarks/test_corpus.py`

**Interfaces:**
- Consumes: `canonical_sha256(value)` from Task G4.1.
- Produces: `verify_pinned_commit(url: str, commit: str) -> str`.
- Produces: `pin_all(corpus_seed: Path, competitor_seed: Path) -> tuple[dict, dict]`.
- Produces: `materialize_corpus(lock_path: Path, cache_dir: Path) -> list[CheckoutReceipt]`.
- Produces: immutable corpus and competitor locks consumed by Tasks G4.3 through G4.7 and G4.8A through G4.8D.
- Produces: the exhaustive reviewed capability seed consumed and evidence-locked by Task G4.4.

**Phase 1: Write failing lock/materialization tests**

- [ ] **Step 1.1 (2–5 min): Add full-commit and immutable-URL lock assertions**
- [ ] **Step 1.2 (2–5 min): Add disjoint dev/holdout repository assertions**
- [ ] **Step 1.3 (2–5 min): Add deterministic regeneration assertions**
- [ ] **Step 1.4 (2–5 min): Add clean materialization/hash assertions**
- [ ] **Step 1.5 (2–5 min): Add exactly-eight competitor assertions**
- [ ] **Step 1.6 (2–5 min): Add product-runtime separation assertions**
- [ ] **Step 1.7 (2–5 min): Add exhaustive capability-matrix assertions**

Create tests that use local temporary Git repositories, never live network:

```python
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from benchmarks.corpus import LockError, materialize_corpus, validate_lock


def make_repo(root: Path) -> tuple[Path, str]:
    repo = root / "origin"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Bench"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "bench@example.invalid"], check=True)
    (repo / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (repo / "main.py").write_text("def answer(): return 42\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    return repo, sha


def test_lock_rejects_floating_revision(tmp_path):
    lock = {"schema_version": 1, "repositories": [{
        "id": "fixture", "url": "file:///fixture", "commit": "main",
        "license_spdx": "MIT", "split": "dev", "languages": ["python"],
        "license_path": "LICENSE", "license_sha256": "a" * 64,
        "exclusions": [".git/**"],
    }]}
    with pytest.raises(LockError, match="40-character"):
        validate_lock(lock)


def test_materialize_checks_commit_and_license_hash(tmp_path):
    repo, sha = make_repo(tmp_path)
    license_hash = hashlib.sha256((repo / "LICENSE").read_bytes()).hexdigest()
    lock_path = tmp_path / "corpus.lock"
    lock_path.write_text(json.dumps({"schema_version": 1, "repositories": [{
        "id": "fixture", "url": repo.as_uri(), "commit": sha,
        "license_spdx": "MIT", "split": "dev", "languages": ["python"],
        "license_path": "LICENSE", "license_sha256": license_hash,
        "exclusions": [".git/**"],
    }]}), encoding="utf-8")
    receipts = materialize_corpus(lock_path, tmp_path / "cache")
    assert receipts[0].commit == sha
    assert receipts[0].license_sha256 == license_hash

    data = json.loads(lock_path.read_text(encoding="utf-8"))
    data["repositories"][0]["license_sha256"] = "0" * 64
    lock_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(LockError, match="license hash"):
        materialize_corpus(lock_path, tmp_path / "cache-2")


def test_competitor_seed_contains_exactly_eight_external_baselines(repo_root):
    seed = json.loads((repo_root / "benchmarks/competitors.seed.json").read_text(encoding="utf-8"))
    assert {tool["id"] for tool in seed["tools"]} == {
        "aider", "code-review-graph", "codebase-memory-mcp", "codanna",
        "codegraph", "codegraphcontext", "serena", "tree-sitter-analyzer",
    }
    assert "codesextant" not in {tool["id"] for tool in seed["tools"]}


def test_capability_seed_is_a_complete_cartesian_matrix(repo_root):
    corpus = json.loads((repo_root / "benchmarks/corpus.seed.json").read_text(encoding="utf-8"))
    competitors = json.loads((repo_root / "benchmarks/competitors.seed.json").read_text(encoding="utf-8"))
    matrix = json.loads((repo_root / "benchmarks/capabilities.seed.json").read_text(encoding="utf-8"))
    languages = sorted({language for item in corpus["repositories"] for language in item["languages"]})
    tools = ["codesextant", *sorted(item["id"] for item in competitors["tools"])]
    operations = matrix["operations"]
    rows = {(row["tool"], row["operation"], row["language"]) for row in matrix["pairs"]}
    assert rows == {(tool, operation, language) for tool in tools for operation in operations for language in languages}
    assert len(rows) == len(matrix["pairs"])
    assert all(row["disposition"] in {"required", "unsupported"} for row in matrix["pairs"])
```

**Phase 2: Observe RED**

- [ ] **Step 2.1 (2–5 min): Run lock/corpus tests once and record missing-module failure**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_locks.py tests/benchmarks/test_corpus.py -q
```

Expected: collection fails because `benchmarks.corpus` does not exist.

**Phase 3: Add reviewed seeds**

- [ ] **Step 3.1 (2–5 min): Add the corpus seed with disjoint split declarations**
- [ ] **Step 3.2 (2–5 min): Add the eight external competitor seed rows**
- [ ] **Step 3.3 (2–5 min): Add SCIP protocol-only metadata**
- [ ] **Step 3.4 (2–5 min): Add the exhaustive capability seed rows**
- [ ] **Step 3.5 (2–5 min): Review every seed URL/license/commit evidence field**

Create `benchmarks/corpus.seed.json` with these exact repository assignments:

```json
{
  "schema_version": 1,
  "repositories": [
    {"id":"requests-dev","url":"https://github.com/psf/requests.git","commit":"69f84847045bef7a849cc994a26fe7ba8a169e95","split":"dev","license_spdx":"Apache-2.0","license_path":"LICENSE","languages":["python"],"exclusions":[".git/**","docs/**","tests/**","vendor/**","build/**","dist/**"]},
    {"id":"fastify-dev","url":"https://github.com/fastify/fastify.git","commit":"ada0623dce9ed776306f2ccaa095b8ee01a492ba","split":"dev","license_spdx":"MIT","license_path":"LICENSE","languages":["javascript"],"exclusions":[".git/**","docs/**","test/**","node_modules/**","build/**","dist/**"]},
    {"id":"ripgrep-dev","url":"https://github.com/BurntSushi/ripgrep.git","commit":"8372866810a1f2a647d11d7780984d4402a5c1e9","split":"dev","license_spdx":"MIT OR Unlicense","license_path":"COPYING","languages":["rust"],"exclusions":[".git/**","doc/**","tests/**","target/**"]},
    {"id":"cobra-dev","url":"https://github.com/spf13/cobra.git","commit":"adbc8813901bba65827259daa8e22ff94ec1f30e","split":"dev","license_spdx":"Apache-2.0","license_path":"LICENSE.txt","languages":["go"],"exclusions":[".git/**","site/**","tests/**","vendor/**"]},
    {"id":"gson-dev","url":"https://github.com/google/gson.git","commit":"57e95370d89a29be98331350beb68c7d7fa3dffe","split":"dev","license_spdx":"Apache-2.0","license_path":"LICENSE","languages":["java"],"exclusions":[".git/**","gson/src/test/**","target/**"]},
    {"id":"libexpat-dev","url":"https://github.com/libexpat/libexpat.git","commit":"7d93af0965eee44fde42d9e9ec8761ae2894e8e8","split":"dev","license_spdx":"MIT","license_path":"COPYING","languages":["c"],"exclusions":[".git/**","doc/**","tests/**","build/**"]},
    {"id":"flask-holdout","url":"https://github.com/pallets/flask.git","commit":"36e4a824f340fdee7ed50937ba8e7f6bc7d17f81","split":"holdout","license_spdx":"BSD-3-Clause","license_path":"LICENSE.txt","languages":["python"],"exclusions":[".git/**","docs/**","tests/**","build/**","dist/**"]},
    {"id":"vitest-holdout","url":"https://github.com/vitest-dev/vitest.git","commit":"66d95af84b77b59ce84ef30492768d4c25e886ee","split":"holdout","license_spdx":"MIT","license_path":"LICENSE","languages":["typescript"],"exclusions":[".git/**","docs/**","test/**","node_modules/**","dist/**"]},
    {"id":"fd-holdout","url":"https://github.com/sharkdp/fd.git","commit":"eead1886cddbe825198d9ac02617635d2240cfaa","split":"holdout","license_spdx":"MIT OR Apache-2.0","license_path":"LICENSE-MIT","languages":["rust"],"exclusions":[".git/**","doc/**","tests/**","target/**"]},
    {"id":"fzf-holdout","url":"https://github.com/junegunn/fzf.git","commit":"235a726fae89bec3ac6d3e7facd2716d78bb625d","split":"holdout","license_spdx":"MIT","license_path":"LICENSE","languages":["go"],"exclusions":[".git/**","doc/**","test/**","vendor/**"]},
    {"id":"okhttp-holdout","url":"https://github.com/square/okhttp.git","commit":"2ff0781bd6d775ee1a2f286d3b2d80f9c5a9a34a","split":"holdout","license_spdx":"Apache-2.0","license_path":"LICENSE.txt","languages":["java","kotlin"],"exclusions":[".git/**","docs/**","samples/**","src/test/**","build/**"]},
    {"id":"fmt-holdout","url":"https://github.com/fmtlib/fmt.git","commit":"4e5ff510f8234a6e85b86a9e2c96f3a07d2af16b","split":"holdout","license_spdx":"MIT","license_path":"LICENSE","languages":["cpp"],"exclusions":[".git/**","doc/**","test/**","support/**","build/**"]}
  ]
}
```

Create `benchmarks/competitors.seed.json`:

```json
{
  "schema_version": 1,
  "tools": [
    {"id":"codegraph","url":"https://github.com/colbymchenry/codegraph.git","commit":"572d22bfbe82602080e457bec655f72e3314f9ef","documentation_path":"README.md","license_spdx":"MIT","license_path":"LICENSE","adapter_module":"benchmarks.adapters.codegraph","image_recipe":"benchmarks/images/codegraph/Dockerfile","capabilities":["symbols","references","navigation","map","cold_index","incremental_index","warm_query"],"workload_capabilities":[]},
    {"id":"codebase-memory-mcp","url":"https://github.com/DeusData/codebase-memory-mcp.git","commit":"5e7d3eb77e355179d07ff5236bd5bcda4448b81c","documentation_path":"README.md","license_spdx":"MIT","license_path":"LICENSE","adapter_module":"benchmarks.adapters.codebase_memory_mcp","image_recipe":"benchmarks/images/codebase-memory-mcp/Dockerfile","capabilities":["symbols","references","navigation","map","cold_index","incremental_index","warm_query"],"workload_capabilities":["agent"]},
    {"id":"code-review-graph","url":"https://github.com/tirth8205/code-review-graph.git","commit":"6ce25b4e53f9df397f5136e86a59e17c02a610fe","documentation_path":"README.md","license_spdx":"MIT","license_path":"LICENSE","adapter_module":"benchmarks.adapters.code_review_graph","image_recipe":"benchmarks/images/code-review-graph/Dockerfile","capabilities":["references","impact","navigation","map","cold_index","warm_query"],"workload_capabilities":[]},
    {"id":"serena","url":"https://github.com/oraios/serena.git","commit":"ac256f36309dd01153389eb3828ae08d2ab9d705","documentation_path":"README.md","license_spdx":"MIT","license_path":"LICENSE","adapter_module":"benchmarks.adapters.serena","image_recipe":"benchmarks/images/serena/Dockerfile","capabilities":["symbols","references","navigation","warm_query"],"workload_capabilities":["agent"]},
    {"id":"codegraphcontext","url":"https://github.com/CodeGraphContext/CodeGraphContext.git","commit":"8bd1a8f7214a3bdb2788106a6949c60dd83dd5be","documentation_path":"README.md","license_spdx":"MIT","license_path":"LICENSE","adapter_module":"benchmarks.adapters.codegraphcontext","image_recipe":"benchmarks/images/codegraphcontext/Dockerfile","capabilities":["symbols","references","navigation","map","cold_index","warm_query"],"workload_capabilities":[]},
    {"id":"codanna","url":"https://github.com/bartolli/codanna.git","commit":"291668ed767ee4d84d954378a81bb1d2246f9b86","documentation_path":"README.md","license_spdx":"Apache-2.0","license_path":"LICENSE","adapter_module":"benchmarks.adapters.codanna","image_recipe":"benchmarks/images/codanna/Dockerfile","capabilities":["symbols","references","navigation","cold_index","incremental_index","warm_query"],"workload_capabilities":[]},
    {"id":"tree-sitter-analyzer","url":"https://github.com/aimasteracc/tree-sitter-analyzer.git","commit":"ebee728dbf3c05e9096bffc817363dfeceefe0f9","documentation_path":"README.md","license_spdx":"MIT","license_path":"LICENSE","adapter_module":"benchmarks.adapters.tree_sitter_analyzer","image_recipe":"benchmarks/images/tree-sitter-analyzer/Dockerfile","capabilities":["symbols","references","miswires","cold_index","warm_query"],"workload_capabilities":[]},
    {"id":"aider","url":"https://github.com/Aider-AI/aider.git","commit":"5dc9490bb35f9729ef2c95d00a19ccd30c26339c","documentation_path":"README.md","license_spdx":"Apache-2.0","license_path":"LICENSE.txt","adapter_module":"benchmarks.adapters.aider","image_recipe":"benchmarks/images/aider/Dockerfile","capabilities":["map"],"workload_capabilities":["agent"]}
  ],
  "protocols": [
    {"id":"scip","url":"https://github.com/scip-code/scip.git","commit":"44d39fcfc95486d066a796e2cec8c7ec5d429aae","documentation_path":"README.md","license_spdx":"Apache-2.0","license_path":"LICENSE","role":"protocol_only","runnable":false,"capabilities":[]}
  ]
}
```

Create `benchmarks/capabilities.seed.json` as the reviewed preregistration authority. It must explicitly enumerate the complete Cartesian product of:

- tools: `codesextant` plus the eight `tools` entries above;
- operations: `symbols`, `references`, `miswires`, `impact`, `navigation`, `map`, `cold_index`, `incremental_index`, and `warm_query`; and
- every language token present in `corpus.seed.json` (`c`, `cpp`, `go`, `java`, `javascript`, `kotlin`, `python`, `rust`, and `typescript`).

There are no wildcard/default rows. Each pair contains `tool`, `operation`, `language`, `disposition` (`required` or `unsupported`), a commit-bound documentation URL and section anchor, and a non-empty rationale. `required` means the public interface claims the pair and therefore requires a successful fixture/probe in Task G4.4 and a successful scored execution later. `unsupported` is allowed only when public documentation and a negative probe collected before freeze both establish absence; Task G4.4 replaces its unbound evidence placeholders with hashes in the generated lock. Tool-level `capabilities` in `competitors.seed.json` are only a human-readable projection and must equal the union of that tool's required language-matrix operations; they never override a pair row. `workload_capabilities` contains only the separately tested `agent` capability. Reliability is a product/runtime experiment, not a competitor language pair.

Append `.benchmark-cache/` and `benchmarks/results/` to `.gitignore`.

**Phase 4: Implement lock resolution and materialization**

- [ ] **Step 4.1 (2–5 min): Implement canonical corpus revision resolution**
- [ ] **Step 4.2 (2–5 min): Implement archive/hash/license evidence locking**
- [ ] **Step 4.3 (2–5 min): Implement competitor lock generation**
- [ ] **Step 4.4 (2–5 min): Implement product-runtime lock generation**
- [ ] **Step 4.5 (2–5 min): Implement exhaustive capability lock generation**
- [ ] **Step 4.6 (2–5 min): Implement clean corpus materialization**
- [ ] **Step 4.7 (2–5 min): Implement deterministic lock `--check` mode**

`pin_locks.py` must copy the seed's exact 40-hex commit into the generated lock; it never resolves `HEAD`, a branch, or a tag. It initializes `.benchmark-cache/pin/{repository_id}`, fetches only the declared commit, checks out that detached commit, verifies every declared documentation/license path exists there, hashes those files, counts files and nonblank source lines after exclusions, and writes canonical sorted JSON. `corpus.py` validates every field before fetching and verifies checkout HEAD and license SHA after materialization. A missing/floating commit or declared path is a hard `LockError`; it is never replaced by a newly resolved revision or guessed filename. Updating a revision requires an explicit reviewed seed edit followed by deterministic regeneration; generated locks are never hand-edited. The commit values above and their root documentation/license paths were captured from the official GitHub repositories on `2026-07-23`; normal generation never refreshes them implicitly.

Use this immutable receipt type:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckoutReceipt:
    repo_id: str
    commit: str
    checkout: str
    license_sha256: str
    file_count: int
    source_lines: int
    scored_tree_sha256: str
```

`materialize_corpus` builds a second read-only scored view from `git ls-tree`, containing only regular files accepted by the lock's exclusion rules. It rejects symlinks that resolve outside the checkout and records a canonical hash of every scored relative path plus content SHA-256. Every tool receives this identical scored view, so tool-specific ignore behavior cannot change the benchmark corpus.

The competitor lock records each tool's `id`, `url`, seed-pinned `commit`, commit-bound documentation/license URLs and SHA-256 values, adapter module, image recipe, declared capabilities, and `image_digest` (`null` until Task G4.4). Its separate `protocols` array records SCIP with `role="protocol_only"`, `runnable=false`, and no capabilities. `pin_locks.py` is the only writer of `competitors.lock`; Task G4.4 supplies a canonical image-digest input and regenerates the lock rather than editing it.

**Phase 5: Generate and verify locks**

- [ ] **Step 5.1 (2–5 min): Generate corpus/competitor/product locks**
- [ ] **Step 5.2 (2–5 min): Generate capability lock from reviewed seed/probes**
- [ ] **Step 5.3 (2–5 min): Re-run generation into scratch outputs and compare bytes**
- [ ] **Step 5.4 (2–5 min): Run all lock `--check` commands**
- [ ] **Step 5.5 (2–5 min): Run focused lock/corpus GREEN tests**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m benchmarks.pin_locks
Get-FileHash -Algorithm SHA256 benchmarks/corpus.lock,benchmarks/competitors.lock
uv run --frozen --no-sync --project benchmarks python -m benchmarks.pin_locks --check
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_locks.py tests/benchmarks/test_corpus.py -q
```

Expected: `--check` prints `locks are current`, tests pass, and a second generation produces no Git diff.

**Phase 6: Commit immutable inputs**

- [ ] **Step 6.1 (2–5 min): Stage only G4.2 seed/lock/resolver files and inspect them**
- [ ] **Step 6.2 (2–5 min): Commit immutable input locks**

```powershell
$expectedStaged = @('.gitignore','benchmarks/corpus.seed.json','benchmarks/competitors.seed.json','benchmarks/capabilities.seed.json','benchmarks/pin_locks.py','benchmarks/corpus.py','benchmarks/corpus.lock','benchmarks/competitors.lock','tests/benchmarks/test_locks.py','tests/benchmarks/test_corpus.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'bench: pin corpus and competitor revisions'
```

### Task G4.3: Build Independently Adjudicated Ground Truth

**Files:**
- Create: `benchmarks/ground_truth/README.md`
- Create: `benchmarks/ground_truth/state.json`
- Create: `benchmarks/ground_truth/dev/symbols.jsonl`
- Create: `benchmarks/ground_truth/dev/references.jsonl`
- Create: `benchmarks/ground_truth/dev/miswires.jsonl`
- Create: `benchmarks/ground_truth/dev/impact.jsonl`
- Create: `benchmarks/ground_truth/dev/navigation.jsonl`
- Create: `benchmarks/ground_truth/dev/map.jsonl`
- Create: `benchmarks/ground_truth/holdout-manifest.json`
- Create: `benchmarks/adjudication.py`
- Create: `tests/benchmarks/test_adjudication.py`

**Interfaces:**
- Consumes: ground-truth schema from Task G4.1 and corpus lock from Task G4.2.
- Produces: `load_cases(path: Path) -> list[dict[str, object]]`.
- Produces: `verify_adjudication(root: Path, corpus_lock: Path) -> AdjudicationSummary`.
- Produces: `seal_holdout(external_dir: Path, manifest_path: Path) -> dict[str, object]`.
- Produces after independent verification only: `release_holdout(*, subject_path: Path, external_dir: Path, output_dir: Path, scorecard_path: Path, primary_receipt_path: Path, independent_receipt_path: Path, reviewer_id: str) -> dict[str, object]`.

**Phase 1: Write failing adjudication tests**

- [ ] **Step 1.1 (2–5 min): Add schema/count/unique-case assertions**
- [ ] **Step 1.2 (2–5 min): Add two-reviewer agreement assertions**
- [ ] **Step 1.3 (2–5 min): Add ambiguity/exclusion assertions**
- [ ] **Step 1.4 (2–5 min): Add source-class independence assertions**
- [ ] **Step 1.5 (2–5 min): Add sealed-holdout state assertions**
- [ ] **Step 1.6 (2–5 min): Add release-after-two-receipts assertions**

```python
import json
from pathlib import Path

import pytest

from benchmarks.adjudication import AdjudicationError, verify_case, verify_sealed_state


def valid_case() -> dict:
    return {
        "schema_version": 1,
        "case_id": "requests-dev-references-0001",
        "task": "references",
        "repo_id": "requests-dev",
        "base_commit": "a" * 40,
        "split": "dev",
        "query": {"symbol": "Session", "definition_path": "src/requests/sessions.py"},
        "expected": {"locations": [{"path": "src/requests/api.py", "line": 20}]},
        "ambiguity": "clear",
        "evidence": [{"path": "src/requests/api.py", "line_start": 20, "line_end": 20, "blob_sha256": "b" * 64}],
        "adjudicators": ["reviewer-a", "reviewer-b"],
        "resolution": "agreement",
    }


def test_two_distinct_adjudicators_are_required():
    case = valid_case()
    case["adjudicators"] = ["reviewer-a", "reviewer-a"]
    with pytest.raises(AdjudicationError, match="distinct"):
        verify_case(case)


def test_ambiguous_case_cannot_be_forced_into_binary_expected():
    case = valid_case()
    case["ambiguity"] = "ambiguous"
    with pytest.raises(AdjudicationError, match="ambiguous"):
        verify_case(case)


def test_sealed_state_rejects_tracked_holdout_answers(tmp_path):
    root = tmp_path / "ground_truth"
    (root / "holdout").mkdir(parents=True)
    (root / "state.json").write_text(
        json.dumps({"schema_version": 1, "state": "sealed"}), encoding="utf-8")
    (root / "holdout" / "answers.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(AdjudicationError, match="sealed"):
        verify_sealed_state(root)
```

**Phase 2: Observe RED**

- [ ] **Step 2.1 (2–5 min): Run adjudication tests once and record missing-module failure**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_adjudication.py -q
```

Expected: collection fails because `benchmarks.adjudication` does not exist.

**Phase 3: Implement adjudication and sealing**

- [ ] **Step 3.1 (2–5 min): Implement one-case schema/content validation**
- [ ] **Step 3.2 (2–5 min): Implement reviewer agreement resolution**
- [ ] **Step 3.3 (2–5 min): Implement source-class ground-truth separation**
- [ ] **Step 3.4 (2–5 min): Implement deterministic manifest hashing**
- [ ] **Step 3.5 (2–5 min): Implement sealed `state.json` checks**
- [ ] **Step 3.6 (2–5 min): Implement two-receipt-gated holdout release**

`verify_case` validates the JSON schema, requires two unique reviewer IDs, checks repo/commit/split against `corpus.lock`, and requires `expected={"excluded_reason":"adjudicators marked the case ambiguous"}` when ambiguity is `ambiguous` or `excluded`. `seal_holdout` hashes every external JSONL file, counts cases by task/language/repository, and writes only those hashes and counts to `holdout-manifest.json`.

Create `state.json` initially as:

```json
{"schema_version":1,"state":"sealed","answers_tracked":false}
```

`verify_sealed_state` fails if a tracked `holdout/` directory exists while state is `sealed`. The tracked `state.json` never changes after the source freeze. The keyword-only `release_holdout` signature above is also registered in the CLI parser conformance test in Task G4.8D. It first verifies the external files against the precommitted manifest, both signed G4 receipts, reviewer role, and same ReleaseSubject, copies them byte-for-byte to an ignored confined output directory, and writes an adjacent deterministic `release-manifest.json` with `state="released"`. Any missing primary/independent receipt, mismatched scorecard, unknown reviewer flag, or extra positional path fails before copying.

**Phase 4: Document policy and curate visible labels**

- [ ] **Step 4.1 (2–5 min): Write reviewer/resolution policy**
- [ ] **Step 4.2 (2–5 min): Write ambiguity/exclusion policy**
- [ ] **Step 4.3 (2–5 min): Curate and validate the `requests-dev` label batch**
- [ ] **Step 4.4 (2–5 min): Curate and validate the `fastify-dev` label batch**
- [ ] **Step 4.5 (2–5 min): Curate and validate the `ripgrep-dev` label batch**
- [ ] **Step 4.6 (2–5 min): Curate and validate the `cobra-dev` label batch**
- [ ] **Step 4.7 (2–5 min): Curate and validate the `gson-dev` label batch**
- [ ] **Step 4.8 (2–5 min): Curate and validate the `libexpat-dev` label batch**

`ground_truth/README.md` must prescribe stratified sampling by repository, symbol kind, file size, and name collision; exact line/blob evidence; no source snippets; two blind labels before reconciliation; third-reviewer resolution; and these minimum release counts:

- 500 clear reference edges per precision-adapter language.
- 500 clear same-name/cross-language miswire cases total.
- 200 clear impact cases.
- 100 clear navigation questions.
- 50 independently ranked repository-map judgments.

Reference cases identify one exact definition and all in-repository reference locations at the pinned commit. Miswire cases deliberately pair identical names from different scopes, files, or languages. Impact cases index the parent of a non-merge bug-fix commit, use one changed product file as the query anchor, and treat the other changed product files as expected; commits touching more than 20% of product files or containing only formatting/generated changes are excluded. Navigation questions have a single evidence-backed definition/file answer. Map judgments assign relevance 0 through 3 and one source class from `product|test|fixture|generated|vendored|tool|proof_of_concept`.

Curate development labels only from `*-dev` repositories. A separate reviewer checkout curates holdout JSONL files outside this worktree and provides only the sealed manifest until operational runbook R5.

**Phase 5: Seal and verify**

- [ ] **Step 5.1 (2–5 min): Validate every visible development-label file**
- [ ] **Step 5.2 (2–5 min): Generate the holdout manifest from external bytes**
- [ ] **Step 5.3 (2–5 min): Verify sealed state contains no answer bytes/paths**
- [ ] **Step 5.4 (2–5 min): Run focused adjudication GREEN tests**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m benchmarks.adjudication verify-dev
uv run --frozen --no-sync --project benchmarks python -m benchmarks.adjudication seal-holdout --external-dir $env:CODESEXTANT_HOLDOUT_DIR
uv run --frozen --no-sync --project benchmarks python -m benchmarks.adjudication verify-state
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_adjudication.py -q
```

Expected: development counts are printed, holdout state is `sealed`, no holdout answer file is tracked, and tests pass.

**Phase 6: Commit adjudication inputs**

- [ ] **Step 6.1 (2–5 min): Stage policy, visible labels, manifest, state, tests, and inspect**
- [ ] **Step 6.2 (2–5 min): Commit adjudication inputs**

```powershell
$expectedStaged = @('benchmarks/ground_truth/README.md','benchmarks/ground_truth/state.json','benchmarks/ground_truth/dev/symbols.jsonl','benchmarks/ground_truth/dev/references.jsonl','benchmarks/ground_truth/dev/miswires.jsonl','benchmarks/ground_truth/dev/impact.jsonl','benchmarks/ground_truth/dev/navigation.jsonl','benchmarks/ground_truth/dev/map.jsonl','benchmarks/ground_truth/holdout-manifest.json','benchmarks/adjudication.py','tests/benchmarks/test_adjudication.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'bench: freeze independently adjudicated ground truth'
```

### Task G4.4: Implement Capability-Aware Tool Adapters

**Files:**
- Create: `benchmarks/adapters/__init__.py`
- Create: `benchmarks/adapters/base.py`
- Create: `benchmarks/adapters/codesextant.py`
- Create: `benchmarks/adapters/codegraph.py`
- Create: `benchmarks/adapters/codebase_memory_mcp.py`
- Create: `benchmarks/adapters/code_review_graph.py`
- Create: `benchmarks/adapters/serena.py`
- Create: `benchmarks/adapters/codegraphcontext.py`
- Create: `benchmarks/adapters/codanna.py`
- Create: `benchmarks/adapters/tree_sitter_analyzer.py`
- Create: `benchmarks/adapters/aider.py`
- Create: `benchmarks/adapters/build_images.py`
- Create: `benchmarks/adapters/verify.py`
- Create: `benchmarks/adapter_fixtures/{codesextant,codegraph,codebase-memory-mcp,code-review-graph,serena,codegraphcontext,codanna,tree-sitter-analyzer,aider}/probe.json`
- Generate: `benchmarks/adapter_fixtures/{codesextant,codegraph,codebase-memory-mcp,code-review-graph,serena,codegraphcontext,codanna,tree-sitter-analyzer,aider}/capability-pairs.jsonl`; each file contains one canonical row for every operation/language pair of that exact tool, including negative evidence for predeclared unsupported rows.
- Create: `benchmarks/images/{codegraph,codebase-memory-mcp,code-review-graph,serena,codegraphcontext,codanna,tree-sitter-analyzer,aider}/Dockerfile`
- Create: `benchmarks/images/product-runtime/Dockerfile`
- Generate: `benchmarks/images/image-digests.json`
- Generate: `benchmarks/capabilities.lock.json`
- Generate: `benchmarks/product-runtime.lock`
- Regenerate mechanically: `benchmarks/competitors.lock`
- Create: `tests/benchmarks/test_adapter_contract.py`

**Interfaces:**
- Consumes: `BenchmarkRequest`, `BenchmarkResponse`, competitor lock, capability seed, and the G5 ReleaseSubject artifact contract.
- Produces: `ToolAdapter.probe(context: ProbeContext) -> ProbeResult` for the real pinned installation/artifact and `ToolAdapter.probe_fixture() -> ProbeResult` for prefreeze normalization fixtures only.
- Produces: `ToolAdapter.run(request: BenchmarkRequest) -> BenchmarkResponse`.
- Produces: `load_adapter(tool_id: str) -> ToolAdapter`.
- Produces: canonical `benchmarks/images/image-digests.json` for exactly eight external competitors; `pin_locks.py` consumes it and deterministically regenerates `competitors.lock` with pinned OCI digests.
- Produces: `benchmarks/capabilities.lock.json`, whose every pair binds exactly one fixture digest plus documentation evidence.
- Produces: `benchmarks/product-runtime.lock`, which binds the artifact-free runtime image and exact ReleaseSubject target `x86_64-unknown-linux-gnu` independently of competitor images.

**Phase 1: Write adapter conformance RED tests**

- [ ] **Step 1.1 (2–5 min): Add adapter request/response envelope assertions**
- [ ] **Step 1.2 (2–5 min): Add timeout/error/unsupported normalization assertions**
- [ ] **Step 1.3 (2–5 min): Add exact contract-commit/document digest assertions**
- [ ] **Step 1.4 (2–5 min): Add exhaustive required/unsupported pair assertions**
- [ ] **Step 1.5 (2–5 min): Add product-runtime artifact-mount assertions**
- [ ] **Step 1.6 (2–5 min): Add fixture hash and negative-probe assertions**
- [ ] **Step 1.7 (2–5 min): Add real-probe rejection of `fixture_only=true`**

```python
import json

import pytest

from benchmarks.adapters.base import AdapterError, ProbeContext, load_adapter
from benchmarks.model import BenchmarkRequest

TOOLS = [
    "codesextant", "codegraph", "codebase-memory-mcp", "code-review-graph",
    "serena", "codegraphcontext", "codanna", "tree-sitter-analyzer", "aider",
]
PRODUCT = "codesextant"
COMPETITORS = sorted(set(TOOLS) - {PRODUCT})


@pytest.fixture
def adapter_probe_context(repo_root):
    lock = json.loads((repo_root / "benchmarks/competitors.lock").read_text(encoding="utf-8"))
    item = next(row for row in lock["tools"] if row["id"] == "codegraph")
    return ProbeContext(
        tool_id="codegraph",
        contract_commit=item["commit"],
        documentation_sha256=item["documentation_sha256"],
        image_digest=item["image_digest"],
        selected_artifact_path=None,
        selected_artifact_sha256=None,
    )


def request(task: str) -> BenchmarkRequest:
    return BenchmarkRequest(
        schema_version=1, run_id="adapter-test", tool="fixture", tool_version="pinned",
        task=task, repo_id="fixture", repo_path="/repo",
        query={"symbol": "answer"}, deadline_ms=1_000, config={"scope": "product"},
    )


@pytest.mark.parametrize("tool_id", TOOLS)
def test_every_adapter_has_a_pinned_probe_fixture(tool_id):
    adapter = load_adapter(tool_id)
    probe = adapter.probe_fixture()
    assert probe.tool_id == tool_id
    assert len(probe.contract_commit) == 40
    assert probe.image_digest.startswith("sha256:")
    assert len(probe.documentation_sha256) == 64
    assert probe.fixture_only is True


def test_real_probe_is_never_satisfied_by_fixture(adapter_probe_context):
    adapter = load_adapter(adapter_probe_context.tool_id)
    probe = adapter.probe(adapter_probe_context)
    assert probe.fixture_only is False
    assert probe.contract_commit == adapter_probe_context.contract_commit
    assert probe.documentation_sha256 == adapter_probe_context.documentation_sha256


def test_competitor_images_and_product_runtime_are_disjoint(repo_root):
    competitors = json.loads((repo_root / "benchmarks/competitors.lock").read_text(encoding="utf-8"))
    images = json.loads((repo_root / "benchmarks/images/image-digests.json").read_text(encoding="utf-8"))
    runtime = json.loads((repo_root / "benchmarks/product-runtime.lock").read_text(encoding="utf-8"))
    assert {item["id"] for item in competitors["tools"]} == set(COMPETITORS)
    assert set(images["images"]) == set(COMPETITORS)
    assert "codesextant" not in images["images"]
    assert runtime["artifact_target"] == "x86_64-unknown-linux-gnu"
    assert runtime["contains_product_bytes"] is False


def test_every_matrix_pair_has_matching_hash_bound_probe(repo_root):
    seed = json.loads((repo_root / "benchmarks/capabilities.seed.json").read_text(encoding="utf-8"))
    lock = json.loads((repo_root / "benchmarks/capabilities.lock.json").read_text(encoding="utf-8"))
    assert {(r["tool"], r["operation"], r["language"]) for r in lock["pairs"]} == {
        (r["tool"], r["operation"], r["language"]) for r in seed["pairs"]
    }
    for row in lock["pairs"]:
        assert row["fixture_sha256"] and len(row["fixture_sha256"]) == 64
        assert row["documentation_sha256"] and len(row["documentation_sha256"]) == 64
        if row["disposition"] == "required":
            assert row["probe_status"] == "ok"
        else:
            assert row["probe_status"] == "unsupported"
            assert row["negative_probe_sha256"] and row["unsupported_reason"]


@pytest.mark.parametrize("tool_id", TOOLS[1:])
def test_unsupported_capability_is_explicit(tool_id):
    adapter = load_adapter(tool_id)
    response = adapter.run_fixture(request("reliability"))
    assert response.status == "unsupported"
    assert response.coverage["supported"] is False
    assert response.coverage["reason"]


def test_malformed_tool_output_is_an_error_not_empty_success():
    adapter = load_adapter("codesextant")
    with pytest.raises(AdapterError, match="invalid output"):
        adapter.normalize(b"not-json", request("references"))


def test_scip_is_protocol_only_and_never_loads_as_an_adapter():
    with pytest.raises(AdapterError, match="protocol-only"):
        load_adapter("scip")
```

The same module creates a schema-valid ReleaseSubject fixture with one `x86_64-unknown-linux-gnu` artifact, writes exact fixture bytes, and builds a CodeSextant `ProbeContext` from the canonical subject digest plus verified artifact path/SHA. The real CodeSextant probe test asserts `fixture_only is False`, `contract_commit == subject["source_commit"]`, and `selected_artifact_sha256 == subject["artifacts"][0]["sha256"]`; substituting `probe_fixture()`, a source-tree binary, another target, or changed artifact bytes must fail before readiness.

The same test module reads every `benchmarks/images/*/Dockerfile`, requires each `FROM` reference to contain `@sha256:`, rejects floating system/language package inputs, and validates that `image-digests.json` and regenerated `competitors.lock` contain exactly the eight tool IDs declared in `competitors.seed.json` with no extra or missing runnable tool. Each competitor image record repeats the seed-pinned source commit and hashes its Dockerfile plus dependency locks. The separate product-runtime test rejects any CodeSextant archive, binary, wheel, source tree, or commit embedded in the generic runtime image.

**Phase 2: Observe RED**

- [ ] **Step 2.1 (2–5 min): Run adapter contract tests once and record missing-module failure**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_adapter_contract.py -q
```

Expected: collection fails because `benchmarks.adapters.base` does not exist.

**Phase 3: Implement the common adapter envelope**

- [ ] **Step 3.1 (2–5 min): Add `ProbeResult` with exact `contract_commit` semantics**
- [ ] **Step 3.2 (2–5 min): Add normalized subprocess result types**
- [ ] **Step 3.3 (2–5 min): Add timeout/process cleanup behavior**
- [ ] **Step 3.4 (2–5 min): Add required-versus-unsupported validation**
- [ ] **Step 3.5 (2–5 min): Add ReleaseSubject artifact selection/mount verification**

Create `base.py` with:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from benchmarks.contracts import validate_document
from benchmarks.model import BenchmarkRequest, BenchmarkResponse


class AdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProbeContext:
    tool_id: str
    contract_commit: str
    documentation_sha256: str
    image_digest: str
    selected_artifact_path: Path | None
    selected_artifact_sha256: str | None


@dataclass(frozen=True)
class ProbeResult:
    tool_id: str
    contract_commit: str
    documentation_sha256: str
    image_digest: str
    selected_artifact_sha256: str | None
    capabilities: frozenset[str]
    documented_entrypoint: list[str]
    fixture_only: bool


class ToolAdapter(Protocol):
    tool_id: str
    capabilities: frozenset[str]

    def probe(self, context: ProbeContext) -> ProbeResult:
        raise NotImplementedError

    def probe_fixture(self) -> ProbeResult:
        raise NotImplementedError

    def run_fixture(self, request: BenchmarkRequest) -> BenchmarkResponse:
        raise NotImplementedError

    def run(self, request: BenchmarkRequest) -> BenchmarkResponse:
        raise NotImplementedError

    def normalize(self, raw: bytes, request: BenchmarkRequest) -> BenchmarkResponse:
        raise NotImplementedError


def unsupported(task: str) -> BenchmarkResponse:
    return BenchmarkResponse(
        schema_version=1,
        status="unsupported",
        results=[],
        coverage={"supported": False, "fraction": 0.0, "reason": f"{task} unavailable"},
        warnings=[],
        error=None,
    )


def decode_json(raw: bytes) -> object:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterError(f"invalid output: {exc}") from exc
```

`load_adapter` uses a fixed registry from tool ID to class; it does not import by user-controlled module name.

`ProbeResult.contract_commit` has one narrow meaning: the full 40-hex Git commit whose public documented command/operation contract was actually probed. `ProbeContext` is constructed only from verified locks plus ReleaseSubject; adapters may not choose these values. For an external baseline, real `probe(context)` executes the digest-pinned image, returns `fixture_only=false`, and its `contract_commit`/`documentation_sha256` must equal that tool's `competitors.seed.json` commit and commit-bound documentation bytes; this is not a claim that product implementers inspected or derived from competitor source. For scored CodeSextant, real `probe(context)` must return `fixture_only=false`, `contract_commit=ReleaseSubject.source_commit`, and `selected_artifact_sha256` equal to the verified selected ReleaseSubject artifact it executed. `probe_fixture()` always returns `fixture_only=true` and may test normalization only; `benchmarks.adapters.verify` and `orchestrate run` reject it for post-freeze readiness. `source_commit`, image build commit, documentation commit, and ReleaseSubject commit must not be conflated or inferred from one another.

**Phase 4: Implement each public-contract adapter**

- [ ] **Step 4.1 (2–5 min): Implement CodeSextant adapter normalization**
- [ ] **Step 4.2 (2–5 min): Implement CodeGraph adapter normalization**
- [ ] **Step 4.3 (2–5 min): Implement Codebase Memory MCP adapter normalization**
- [ ] **Step 4.4 (2–5 min): Implement Code Review Graph adapter normalization**
- [ ] **Step 4.5 (2–5 min): Implement Serena adapter normalization**
- [ ] **Step 4.6 (2–5 min): Implement CodeGraphContext adapter normalization**
- [ ] **Step 4.7 (2–5 min): Implement Codanna adapter normalization**
- [ ] **Step 4.8 (2–5 min): Implement Tree-sitter Analyzer adapter normalization**
- [ ] **Step 4.9 (2–5 min): Implement Aider map adapter normalization**
- [ ] **Step 4.10 (2–5 min): Capture/hash the CodeSextant fixture set**
- [ ] **Step 4.11 (2–5 min): Capture/hash the CodeGraph fixture set**
- [ ] **Step 4.12 (2–5 min): Capture/hash the Codebase Memory MCP fixture set**
- [ ] **Step 4.13 (2–5 min): Capture/hash the Code Review Graph fixture set**
- [ ] **Step 4.14 (2–5 min): Capture/hash the Serena fixture set**
- [ ] **Step 4.15 (2–5 min): Capture/hash the CodeGraphContext fixture set**
- [ ] **Step 4.16 (2–5 min): Capture/hash the Codanna fixture set**
- [ ] **Step 4.17 (2–5 min): Capture/hash the Tree-sitter Analyzer fixture set**
- [ ] **Step 4.18 (2–5 min): Capture/hash the Aider fixture set**

For each tool:

1. Read the exact commit-bound public documentation URL already generated in `competitors.lock`; do not inspect competitor implementation source.
2. Build an OCI image from the commit already pinned in `competitors.lock` without resolving a remote branch and without reading or reusing its implementation in CodeSextant.
3. Capture `--help` or MCP tool-list output as `probe.json`, including the exact `contract_commit`, documentation SHA-256, binary/image digest, command argv hash, exit code, and normalized capability response.
4. Execute and capture one documented operation for every exact `required` operation/language pair in `capabilities.seed.json`; one operation-level fixture is never reused as proof for another language.
5. For every `unsupported` pair, capture both the commit-bound documentation bytes and an actual negative probe whose normalized result is `unsupported`; a build/runtime error is not unsupported evidence.
6. Normalize paths to slash-separated corpus-relative paths and lines to one-based integers.
7. Preserve confidence/provenance when the tool provides them; otherwise set `warnings=["tool does not expose confidence"]`.
8. Return explicit `unsupported`, `timeout`, or `error`; never fabricate an empty success and never rewrite a required row after observing failure.
9. Record each external competitor image digest, seed-pinned source commit, Dockerfile SHA-256, and dependency-lock SHA-256 in canonical `benchmarks/images/image-digests.json`; every image value must match `^sha256:[0-9a-f]{64}$`. Regenerate `competitors.lock` only through `pin_locks.py --image-digests benchmarks/images/image-digests.json`.
10. Generate `capabilities.lock.json` from the reviewed seed plus the exact fixture/document hashes. Its generator refuses a missing/extra tuple, duplicate tuple, wildcard, required pair without successful probe, unsupported pair without a genuine normalized unsupported probe, or any changed seed disposition.

Every base image uses a digest-pinned `FROM`. OS packages come from a dated snapshot and are version-pinned; language packages use a committed frozen lock/checksum; download URLs include a verified SHA-256; build scripts forbid mutable installer pipes and timestamps. `build_images.py` uses `SOURCE_DATE_EPOCH=0`, BuildKit's OCI timestamp rewrite, and disabled auto-provenance/SBOM metadata, performs two clean builds, and refuses to record a digest unless both OCI outputs are byte-identical. A tool whose documented installation cannot meet this rule is marked non-runnable before scoring rather than receiving a mutable image.

Build `benchmarks/images/product-runtime/Dockerfile` as a generic `linux/amd64` runtime with no product bytes. `product-runtime.lock` records its OCI manifest digest, platform, Dockerfile/dependency-lock digests, `artifact_target="x86_64-unknown-linux-gnu"`, archive extraction rule, read-only mount point `/opt/codesextant-release`, executable relative paths, and `contains_product_bytes=false`. The CodeSextant adapter accepts a verified artifact record selected from `ReleaseSubject.artifacts` by that exact target, checks filename and SHA-256, extracts it into an ephemeral directory, then mounts the result read-only into the generic runtime. The run manifest binds the product-runtime-lock digest, runtime image digest, selected target, filename, and artifact SHA-256. A source checkout, `cargo run`, locally built wheel, or product baked into an OCI layer is a hard error.

The Aider, Serena, and Codebase Memory MCP workload-level `agent` declarations remain in the agent protocol while their language matrices include only documented query operations. SCIP has no adapter, image, fixture, or scored capability because the SCIP repository defines the protocol and consumers; adding SCIP later requires separately pinned language indexers and a reviewed plan revision. The coarse language-capability projections in `competitors.lock` must exactly match the required pair union in `capabilities.lock.json`; `workload_capabilities` is validated independently by the agent harness.

**Phase 5: Build and verify adapters**

- [ ] **Step 5.1 (2–5 min): Build/pin competitor images and product runtime**
- [ ] **Step 5.2 (2–5 min): Regenerate capability evidence hashes**
- [ ] **Step 5.3 (2–5 min): Run adapter verification against all locks**
- [ ] **Step 5.4 (2–5 min): Run focused adapter GREEN tests**
- [ ] **Step 5.5 (2–5 min): Re-run image/lock checks without mutation**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m benchmarks.adapters.build_images --competitor-lock benchmarks/competitors.lock --competitor-out benchmarks/images/image-digests.json --product-runtime benchmarks/images/product-runtime/Dockerfile --product-target x86_64-unknown-linux-gnu --product-out benchmarks/product-runtime.lock
uv run --frozen --no-sync --project benchmarks python -m benchmarks.pin_locks --image-digests benchmarks/images/image-digests.json
uv run --frozen --no-sync --project benchmarks python -m benchmarks.adapters.verify --competitor-lock benchmarks/competitors.lock --capability-seed benchmarks/capabilities.seed.json --capability-out benchmarks/capabilities.lock.json --image-digests benchmarks/images/image-digests.json --product-runtime-lock benchmarks/product-runtime.lock
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_adapter_contract.py -q
uv run --frozen --no-sync --project benchmarks python -m benchmarks.adapters.build_images --competitor-lock benchmarks/competitors.lock --check-competitors benchmarks/images/image-digests.json --check-product benchmarks/product-runtime.lock
uv run --frozen --no-sync --project benchmarks python -m benchmarks.pin_locks --image-digests benchmarks/images/image-digests.json --check
uv run --frozen --no-sync --project benchmarks python -m benchmarks.adapters.verify --competitor-lock benchmarks/competitors.lock --capability-seed benchmarks/capabilities.seed.json --check-capabilities benchmarks/capabilities.lock.json --image-digests benchmarks/images/image-digests.json --product-runtime-lock benchmarks/product-runtime.lock
```

Expected: all nine adapters have probe fixtures; exactly eight external competitor images have full source SHAs and OCI digests; the product adapter uses only the independent artifact-free runtime lock; every required/unsupported pair has the correct hash-bound evidence; SCIP remains protocol-only with zero capabilities; conformance tests pass; and all generated lock checks are clean.

**Phase 6: Commit adapters**

- [ ] **Step 6.1 (2–5 min): Stage only adapter/image/fixture/lock files and inspect**
- [ ] **Step 6.2 (2–5 min): Commit adapter conformance work**

```powershell
$expectedStaged = @('benchmarks/adapters/__init__.py','benchmarks/adapters/base.py','benchmarks/adapters/codesextant.py','benchmarks/adapters/codegraph.py','benchmarks/adapters/codebase_memory_mcp.py','benchmarks/adapters/code_review_graph.py','benchmarks/adapters/serena.py','benchmarks/adapters/codegraphcontext.py','benchmarks/adapters/codanna.py','benchmarks/adapters/tree_sitter_analyzer.py','benchmarks/adapters/aider.py','benchmarks/adapters/build_images.py','benchmarks/adapters/verify.py','benchmarks/adapter_fixtures/codesextant/probe.json','benchmarks/adapter_fixtures/codegraph/probe.json','benchmarks/adapter_fixtures/codebase-memory-mcp/probe.json','benchmarks/adapter_fixtures/code-review-graph/probe.json','benchmarks/adapter_fixtures/serena/probe.json','benchmarks/adapter_fixtures/codegraphcontext/probe.json','benchmarks/adapter_fixtures/codanna/probe.json','benchmarks/adapter_fixtures/tree-sitter-analyzer/probe.json','benchmarks/adapter_fixtures/aider/probe.json','benchmarks/adapter_fixtures/codesextant/capability-pairs.jsonl','benchmarks/adapter_fixtures/codegraph/capability-pairs.jsonl','benchmarks/adapter_fixtures/codebase-memory-mcp/capability-pairs.jsonl','benchmarks/adapter_fixtures/code-review-graph/capability-pairs.jsonl','benchmarks/adapter_fixtures/serena/capability-pairs.jsonl','benchmarks/adapter_fixtures/codegraphcontext/capability-pairs.jsonl','benchmarks/adapter_fixtures/codanna/capability-pairs.jsonl','benchmarks/adapter_fixtures/tree-sitter-analyzer/capability-pairs.jsonl','benchmarks/adapter_fixtures/aider/capability-pairs.jsonl','benchmarks/images/codegraph/Dockerfile','benchmarks/images/codebase-memory-mcp/Dockerfile','benchmarks/images/code-review-graph/Dockerfile','benchmarks/images/serena/Dockerfile','benchmarks/images/codegraphcontext/Dockerfile','benchmarks/images/codanna/Dockerfile','benchmarks/images/tree-sitter-analyzer/Dockerfile','benchmarks/images/aider/Dockerfile','benchmarks/images/product-runtime/Dockerfile','benchmarks/images/image-digests.json','benchmarks/product-runtime.lock','benchmarks/capabilities.lock.json','benchmarks/competitors.lock','tests/benchmarks/test_adapter_contract.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'bench: normalize pinned competitor adapters'
```

### Task G4.5: Add the Deterministic Resource-Controlled Runner

**Files:**
- Create: `benchmarks/resources.py`
- Create: `benchmarks/resources.seed.json`
- Generate: `benchmarks/resources.lock.json`
- Create: `benchmarks/reviewer-roles.seed.json`
- Generate: `benchmarks/reviewer-roles.lock`
- Create: `benchmarks/reviewers.py`
- Create: `benchmarks/manifest.py`
- Create: `benchmarks/runner.py`
- Create: `benchmarks/reliability.py`
- Create: `benchmarks/reliability-cases.json`
- Create: `tests/benchmarks/fixtures/mock_adapter.py`
- Create: `tests/benchmarks/test_resources.py`
- Create: `tests/benchmarks/test_runner.py`
- Create: `tests/benchmarks/test_manifest.py`
- Create: `tests/benchmarks/test_reviewers.py`
- Create: `tests/benchmarks/test_reliability_runner.py`

**Interfaces:**
- Consumes: contracts, locks, ground-truth case IDs, capability matrix, product runtime lock, and adapters from Tasks G4.1 through G4.4.
- Produces: `ResourcePolicy(deadline_ms: int, cpu_ids: Sequence[int], memory_bytes: int)`.
- Produces: `run_monitored(command: list[str], cwd: Path, env: dict[str, str], policy: ResourcePolicy) -> ProcessObservation`.
- Produces: `schedule(case_ids: list[str], tool_ids: list[str], seed: int) -> list[ScheduledCase]`.
- Produces: `run_case(case: ScheduledCase, context: RunContext) -> RunRecord`.
- Produces: `run_reliability_case(case: dict[str, object], adapter: ToolAdapter) -> ReliabilityObservation`.
- Produces: `capture_host() -> dict[str, object]` with no hostname, username, serial number, MAC address, or absolute home path.
- Produces: `validate_resources(lock: Path, host_attestation: Path) -> ResourceValidation`.
- Produces: `sign_reviewer_attestation(reviewer_id: str, role: str, statement: dict[str, object], private_key: Path) -> dict[str, object]` and `verify_reviewer_attestation(attestation: dict[str, object], roles_lock: Path, resources_lock: Path) -> VerifiedReviewerAttestation`.
- Defines: frozen `VerifiedReviewerAttestation(reviewer_id: str, role: str, run_id: str, process_nonce: str, host_identity_sha256: str, resources_lock_sha256: str, statement_sha256: str, signing_key_id: str)`.
- Produces: append-only core `raw-records.jsonl` and `core-results.json`; core execution never writes the final run manifest.
- Produces: `finalize_run_manifest(*, subject_path: Path, core_results: Path, agent_results: Path, evaluator_commitment: Path, resources_lock: Path, capability_lock: Path, reviewer_attestation: Path, output: Path) -> str`, which atomically creates the only scoreable `run-manifest.json` after both result trees exist.

**Phase 1: Write resource/scheduling/manifest RED tests**

- [ ] **Step 1.1 (2–5 min): Add resource-lock schema/host mismatch assertions**
- [ ] **Step 1.2 (2–5 min): Add process-tree RSS/timeout assertions**
- [ ] **Step 1.3 (2–5 min): Add deterministic schedule assertions**
- [ ] **Step 1.4 (2–5 min): Add append-only run-record assertions**
- [ ] **Step 1.5 (2–5 min): Add atomic final-manifest assertions**
- [ ] **Step 1.6 (2–5 min): Add reviewer-role conflict/signature assertions**
- [ ] **Step 1.7 (2–5 min): Add distinct-host/resource-portability assertions**
- [ ] **Step 1.8 (2–5 min): Add reliability-runner assertions**

Create `tests/benchmarks/test_runner.py`:

```python
import json
from pathlib import Path

from benchmarks.runner import append_record, schedule


def test_schedule_is_deterministic_and_interleaves_tools():
    first = schedule(["case-a", "case-b", "case-c"], ["codesextant", "serena"], 20260723)
    second = schedule(["case-a", "case-b", "case-c"], ["codesextant", "serena"], 20260723)
    assert first == second
    assert {(item.case_id, item.tool_id) for item in first} == {
        (case, tool)
        for case in ("case-a", "case-b", "case-c")
        for tool in ("codesextant", "serena")
    }
    assert [item.tool_id for item in first] != ["codesextant"] * 3 + ["serena"] * 3


def test_append_record_keeps_errors_and_timeouts(tmp_path):
    output = tmp_path / "raw-records.jsonl"
    append_record(output, {
        "schema_version": 1,
        "request": {"run_id": "x"},
        "response": {"status": "timeout"},
        "elapsed_ns": 1_000_000,
    })
    append_record(output, {
        "schema_version": 1,
        "request": {"run_id": "y"},
        "response": {"status": "error"},
        "elapsed_ns": 2_000_000,
    })
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["response"]["status"] for row in rows] == ["timeout", "error"]
```

Create `tests/benchmarks/test_resources.py`:

```python
import sys
from pathlib import Path

from benchmarks.resources import ResourcePolicy, run_monitored


def test_timeout_terminates_the_process_tree_and_keeps_output(tmp_path):
    child = tmp_path / "slow.py"
    child.write_text(
        "import subprocess,sys,time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "print('started', flush=True)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    result = run_monitored(
        [sys.executable, str(child)],
        cwd=tmp_path,
        env={},
        policy=ResourcePolicy(deadline_ms=200, cpu_ids=(), memory_bytes=256 * 1024 * 1024),
    )
    assert result.timed_out is True
    assert result.stdout.splitlines() == [b"started"]
    assert result.elapsed_ns >= 200_000_000
    assert result.peak_rss_bytes > 0
```

Create `tests/benchmarks/test_manifest.py`:

```python
import pytest

from benchmarks.manifest import (
    finalize_run_manifest,
    finalize_run_manifest_fixture,
    verify_run_manifest,
)


def test_manifest_binds_every_scored_input():
    manifest = finalize_run_manifest_fixture(
        run_id="g4-fixture",
        release_subject_sha256="0" * 64,
        product_commit="a" * 40,
        product_artifact_sha256="9" * 64,
        protocol_sha256="b" * 64,
        corpus_lock_sha256="c" * 64,
        competitor_lock_sha256="d" * 64,
        adapter_images_sha256="8" * 64,
        ground_truth_sha256="e" * 64,
        runner_sha256="f" * 64,
        agent_tasks_sha256="1" * 64,
        agent_model_sha256="2" * 64,
        agent_pricing_sha256="3" * 64,
        capability_lock_sha256="4" * 64,
        product_runtime_lock_sha256="5" * 64,
        product_artifact_target="x86_64-unknown-linux-gnu",
        resources_lock_sha256="6" * 64,
        core_results_sha256="7" * 64,
        agent_results_sha256="8" * 64,
        evaluator_commitment_sha256="9" * 64,
        reviewer_attestation_sha256="0" * 64,
        host={"cpu_model": "fixture", "logical_cpus": 4, "ram_bytes": 8_000_000_000, "os": "fixture"},
        seed=20260723,
        warmups=3,
        repetitions=10,
        state="final",
    )
    verify_run_manifest(manifest)
    manifest["seed"] = 7
    try:
        verify_run_manifest(manifest)
    except ValueError as exc:
        assert "manifest digest" in str(exc)
    else:
        raise AssertionError("a changed manifest must fail verification")


def test_manifest_cannot_finalize_without_both_result_trees(finalize_inputs):
    finalize_inputs.agent_results.unlink()
    with pytest.raises(ValueError, match="agent results"):
        finalize_run_manifest(**finalize_inputs.kwargs())


def test_scoring_rejects_pending_or_nonatomic_manifest(tmp_path, valid_manifest):
    valid_manifest["state"] = "pending"
    with pytest.raises(ValueError, match="final manifest"):
        verify_run_manifest(valid_manifest)
```

`finalize_run_manifest` reads and schema-validates `release/evidence/release-subject.json`; it selects exactly one artifact whose target equals `product-runtime.lock.artifact_target`, then rejects any filename/hash/version/source/export mismatch. It hashes `benchmarks/images/image-digests.json` separately from `competitors.lock`, binds `capabilities.lock.json`, `product-runtime.lock`, `resources.lock.json`, reviewer attestation, evaluator commitment, core result tree, agent result tree, and every task/model/broker/pricing lock. It records the absolute executable actually invoked only after replacing machine paths with `$ARTIFACT`, `$CACHE`, or `$BROKER` markers. It writes a complete canonical temporary file, fsyncs it, verifies all cross-hashes and `state="final"`, then atomically replaces `run-manifest.json`; no pending filename is accepted by scoring.

Create `tests/benchmarks/test_reviewers.py` and add exact RED cases:

```python
def test_independent_signer_cannot_hold_implementation_or_adjudication_role(roles_lock, signer):
    signer.assign("reviewer-independent", {"independent_operator", "adapter_implementer"})
    with pytest.raises(ReviewerError, match="conflicting role"):
        signer.attest("reviewer-independent", "independent_operator", {})


def test_attestation_signature_and_privacy_are_fail_closed(valid_attestation, public_key):
    verify_reviewer_attestation(valid_attestation, public_key)
    valid_attestation["statement"]["hostname"] = "private-host"
    with pytest.raises(ReviewerError, match="forbidden host field"):
        verify_reviewer_attestation(valid_attestation, public_key)


def test_different_host_must_match_resources_or_performance_is_inconclusive(
    resources_lock, independently_signed_host
):
    independently_signed_host["statement"]["logical_cpus"] -= 1
    result = validate_resources(resources_lock, independently_signed_host)
    assert result.performance_reproducible is False
    assert result.maximum_verdict == "inconclusive"


def test_same_host_cannot_issue_independent_receipt(primary_host, independent_host):
    independent_host["private_host_identity_sha256"] = primary_host["private_host_identity_sha256"]
    with pytest.raises(ReviewerError, match="physically distinct host"):
        verify_independent_hosts(primary_host, independent_host)
```

Create `tests/benchmarks/test_reliability_runner.py`:

```python
from benchmarks.reliability import assess_reliability


def test_duplicate_daemon_and_corruption_are_hard_failures():
    result = assess_reliability([
        {"event": "daemon_snapshot", "live_pids": [101, 102]},
        {"event": "store_check", "integrity": "corrupt"},
    ])
    assert result.duplicate_daemon_count == 1
    assert result.database_corruption_count == 1
    assert result.passed is False


def test_one_daemon_clean_store_and_bounded_recovery_pass():
    result = assess_reliability([
        {"event": "daemon_snapshot", "live_pids": [101]},
        {"event": "store_check", "integrity": "ok"},
        {"event": "recovered", "elapsed_ms": 850, "automatic_restarts": 1},
    ])
    assert result.duplicate_daemon_count == 0
    assert result.database_corruption_count == 0
    assert result.passed is True
```

**Phase 2: Observe RED**

- [ ] **Step 2.1 (2–5 min): Run resource/runner/manifest/reviewer tests once and record RED**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_resources.py tests/benchmarks/test_runner.py tests/benchmarks/test_manifest.py tests/benchmarks/test_reviewers.py -q
```

Expected: collection fails because `benchmarks.resources`, `benchmarks.runner`, `benchmarks.manifest`, and `benchmarks.reviewers` do not exist.

**Phase 3: Implement resource accounting**

- [ ] **Step 3.1 (2–5 min): Add monotonic elapsed-time capture**
- [ ] **Step 3.2 (2–5 min): Add process-tree peak RSS sampling**
- [ ] **Step 3.3 (2–5 min): Add timeout termination of the full process tree**
- [ ] **Step 3.4 (2–5 min): Add CPU-affinity/concurrency enforcement**
- [ ] **Step 3.5 (2–5 min): Add cold/warm cache reset verification**
- [ ] **Step 3.6 (2–5 min): Add Linux host/runtime/power-policy verification**

Create these exact public structures in `resources.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourcePolicy:
    deadline_ms: int
    cpu_ids: Sequence[int]
    memory_bytes: int


@dataclass(frozen=True)
class ProcessObservation:
    stdout: bytes
    stderr: bytes
    exit_code: int
    elapsed_ns: int
    peak_rss_bytes: int
    timed_out: bool
```

`run_monitored` starts a new process group, applies CPU affinity through psutil when `cpu_ids` is non-empty, polls the complete descendant tree every 10 ms, sums resident memory without double-counting PIDs, and records the maximum. At deadline it terminates descendants before the parent, waits 2 seconds, kills survivors, and still returns captured stdout/stderr. Memory over `memory_bytes` uses the same termination path and returns exit code `137`; deadline returns `124`.

Published runs invoke adapters inside their pinned OCI image with corpus mounted read-only, output mounted write-only, `--network none`, a fixed `--cpuset-cpus`, and a fixed `--memory`. Local process accounting supplements rather than replaces the OCI limits.

`benchmarks/resources.seed.json` contains reviewed inputs for one dedicated Linux reference host; `python -m benchmarks.resources pin` is the only writer of canonical `resources.lock.json`. The lock has no placeholders and records all of:

- `platform="linux/amd64"`, exact CPU model/microcode, physical/logical CPU counts, kernel, RAM bytes, and minimum free-disk bytes;
- OCI engine/runtime names, versions, API versions, resolved executable SHA-256 values, and `runc`/containerd component digests;
- `product_artifact_target="x86_64-unknown-linux-gnu"`, equal to `product-runtime.lock.artifact_target`;
- exact CPU IDs, `memory_bytes`, `pids_limit`, `concurrency=1`, per-operation deadline milliseconds, 3 warmups, 10 measured repetitions, and seed `20260723`;
- power governor `performance`, AC-power requirement, turbo policy, and permitted temperature range;
- cold policy: stop/remove the prior container, destroy the tool index volume, run the hash-bound privileged cache-reset helper (`sync` then Linux `drop_caches=3`), and verify empty index plus a bounded page-cache reading before launch;
- warm policy: reuse the same live process/index and perform no cache reset between warm-query repetitions; and
- incremental policy: restore the same hash-bound pristine base index before each repetition, then apply the same committed 100-file change set.

The lock's verifier rejects Windows/macOS hosts, a different product target, runtime drift, an unavailable cache reset, CPU overlap with unrelated processes, insufficient RAM/disk, non-performance power state, unexpected concurrency, or an unhashable executable. A primary run cannot start until the host passes exactly. The independent script requires a different private host-attestation identity digest. An exact resource-lock match permits full performance reproduction; a distinct but nonmatching host may rerun correctness only, marks every performance endpoint `nonportable`, caps the overall verdict at `inconclusive`, and prevents all SOTA wording. A same-host run is retained only as private diagnostic evidence and cannot satisfy the independent receipt.

**Phase 4: Implement scheduling and records**

- [ ] **Step 4.1 (2–5 min): Add fixed-seed case ordering**
- [ ] **Step 4.2 (2–5 min): Add three warm-ups/ten measured repetitions**
- [ ] **Step 4.3 (2–5 min): Add append-only canonical JSONL writes**
- [ ] **Step 4.4 (2–5 min): Add required failure ledger persistence**
- [ ] **Step 4.5 (2–5 min): Add core-result tree sealing**
- [ ] **Step 4.6 (2–5 min): Add agent-result tree sealing**

Add:

```python
from dataclasses import dataclass
import json
import os
import random
from pathlib import Path


@dataclass(frozen=True)
class ScheduledCase:
    case_id: str
    tool_id: str


def schedule(case_ids: list[str], tool_ids: list[str], seed: int) -> list[ScheduledCase]:
    items = [ScheduledCase(case, tool) for case in sorted(case_ids) for tool in sorted(tool_ids)]
    random.Random(seed).shuffle(items)
    return items


def append_record(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
```

`run_case` performs declared warm-ups without writing score records, performs exactly 10 measured repetitions for performance tasks, validates every request/response/run record, hashes raw stdout/stderr into sidecar files, and appends errors/timeouts like any other observation. It never retries a failed scored case. It emits only a canonical `core-results.json` tree digest; it cannot create `run-manifest.json`. Required-pair status comes only from `capabilities.lock.json`. A required competitor error/timeout stays an error/timeout in the coverage denominator and sets `required_baseline_failure=true`; it is never rewritten to unsupported or removed from the comparable inventory.

Create `benchmarks/reliability-cases.json` with five deterministic cases: 32 simultaneous daemon starts, 16 concurrent read clients, process termination 250 ms into indexing, cancellation at a 100 ms deadline, and restart after a corrupt-store fixture. `run_reliability_case` records every observed PID, SQLite integrity result, recovery time, automatic restart count, and retry count. The passing CodeSextant result requires one live daemon, zero corrupt stores, no more than one automatic restart and one request retry, and a stable diagnostic error for the deliberately corrupt fixture. Competitors without a daemon or writable graph store report those cases as explicit `unsupported`.

**Phase 5: Implement attestations/manifests**

- [ ] **Step 5.1 (2–5 min): Add reviewer-role lock generation/check**
- [ ] **Step 5.2 (2–5 min): Add privacy-safe host attestation fields**
- [ ] **Step 5.3 (2–5 min): Add Ed25519 attestation signing/verification**
- [ ] **Step 5.4 (2–5 min): Add distinct host/process/reviewer checks**
- [ ] **Step 5.5 (2–5 min): Add final manifest input/result digests**
- [ ] **Step 5.6 (2–5 min): Add atomic final-manifest rename**

`capture_host` records only CPU model/microcode, physical/logical CPU count, total RAM, operating system/version, kernel, container runtime/version/digests, power-policy label, cache-reset receipt, and benchmark toolchain versions. It must not call hostname, domain, user-profile, serial-number, MAC-address, cloud-instance-metadata, or email APIs. Tests monkeypatch each forbidden source with sentinels and fail if any sentinel enters structured output or its canonical serialization.

`reviewer-roles.seed.json` assigns pseudonymous IDs to `protocol_reviewer`, `holdout_custodian`, `primary_operator`, `independent_operator`, and `evidence_reviewer`, records Ed25519 public keys and explicit conflicts with `product_implementer`, `harness_implementer`, `adapter_implementer`, `adjudicator`, and `evaluator_author`. The deterministic lock hashes the seed and analysis plan. Private keys remain external. `benchmarks.reviewers attest` accepts mandatory `--reviewer-id`, verifies the requested role and conflicts, creates a privacy-safe host statement plus unpredictable process nonce, signs canonical bytes, and writes only after self-verification. The independent operator must differ from all implementation/adjudication/evaluator IDs and from the primary operator. Comparison receipts bind both signed attestation digests.

`finalize_run_manifest` also requires SHA-256 values for `tasks.lock`, `model.lock`, `broker.lock`, `pricing.lock` and its evidence bytes, evaluator commitment, capability lock, resources lock, product runtime lock, core results, and agent results. It adds `state="final"` and its own `manifest_sha256` over all other fields; `verify_run_manifest` recalculates and compares it. Scoring accepts only the final canonical filename written atomically by the orchestrator.

**Phase 6: Verify runner**

- [ ] **Step 6.1 (2–5 min): Pin and verify resources lock**
- [ ] **Step 6.2 (2–5 min): Pin and verify reviewer roles lock**
- [ ] **Step 6.3 (2–5 min): Run focused runner GREEN tests**
- [ ] **Step 6.4 (2–5 min): Run the local fixture core once**
- [ ] **Step 6.5 (2–5 min): Inspect final fixture manifest/tree hashes**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m benchmarks.resources pin --seed benchmarks/resources.seed.json --product-runtime-lock benchmarks/product-runtime.lock --out benchmarks/resources.lock.json
uv run --frozen --no-sync --project benchmarks python -m benchmarks.resources verify-lock --lock benchmarks/resources.lock.json --product-runtime-lock benchmarks/product-runtime.lock
uv run --frozen --no-sync --project benchmarks python -m benchmarks.reviewers pin --seed benchmarks/reviewer-roles.seed.json --analysis-plan benchmarks/analysis-plan.json --out benchmarks/reviewer-roles.lock
uv run --frozen --no-sync --project benchmarks python -m benchmarks.reviewers verify-lock --lock benchmarks/reviewer-roles.lock
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_resources.py tests/benchmarks/test_runner.py tests/benchmarks/test_manifest.py tests/benchmarks/test_reviewers.py tests/benchmarks/test_reliability_runner.py -q
uv run --frozen --no-sync --project benchmarks python -m benchmarks.runner fixture-core --resources-lock benchmarks/resources.lock.json --capability-lock benchmarks/capabilities.lock.json --out .benchmark-cache/fixture-run
```

Expected: tests pass; both reviewed locks verify deterministically; the fixture run contains `core-results.json`, `raw-records.jsonl`, and stdout/stderr sidecars but no final `run-manifest.json`; at least one intentional timeout remains in `raw-records.jsonl`. Unit finalization succeeds only when fixture core and agent result trees plus valid signed reviewer/evaluator/resource inputs are all supplied.

**Phase 7: Commit runner**

- [ ] **Step 7.1 (2–5 min): Stage only runner/resource/reviewer files and inspect**
- [ ] **Step 7.2 (2–5 min): Commit runner without result claims**

```powershell
$expectedStaged = @('benchmarks/resources.py','benchmarks/resources.seed.json','benchmarks/resources.lock.json','benchmarks/reviewer-roles.seed.json','benchmarks/reviewer-roles.lock','benchmarks/reviewers.py','benchmarks/manifest.py','benchmarks/runner.py','benchmarks/reliability.py','benchmarks/reliability-cases.json','tests/benchmarks/fixtures/mock_adapter.py','tests/benchmarks/test_resources.py','tests/benchmarks/test_runner.py','tests/benchmarks/test_manifest.py','tests/benchmarks/test_reviewers.py','tests/benchmarks/test_reliability_runner.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'bench: add deterministic resource-controlled runner'
```

### Task G4.6: Implement Metrics, Confidence Intervals, and G4 Verdicts

**Files:**
- Create: `benchmarks/metrics/__init__.py`
- Create: `benchmarks/metrics/classification.py`
- Create: `benchmarks/metrics/impact.py`
- Create: `benchmarks/metrics/map_quality.py`
- Create: `benchmarks/metrics/navigation.py`
- Create: `benchmarks/metrics/performance.py`
- Create: `benchmarks/metrics/reliability.py`
- Create: `benchmarks/stats.py`
- Create: `benchmarks/score.py`
- Create: `tests/benchmarks/test_metrics.py`
- Create: `tests/benchmarks/test_stats.py`
- Create: `tests/benchmarks/test_g4_gate.py`
- Create: `tests/benchmarks/fixtures/final-run/{run-manifest.json,core-results.json,agent/results.json,raw-records.jsonl}`

**Interfaces:**
- Consumes: validated `RunRecord` rows and released or externally supplied ground truth.
- Produces: `precision_recall_f1(expected: set[str], predicted: set[str]) -> ClassificationScore`.
- Produces: `ndcg_at(relevances: list[float], k: int) -> float`.
- Produces: `map_source_metrics(predicted: list[dict], adjudicated: dict[str, str], k: int) -> MapSourceScore` using only adjudicated classes for noise/forbidden verdicts and returning a product-vs-ground-truth confusion matrix.
- Produces: `nearest_rank_percentile(values: list[float], quantile: float) -> float`.
- Produces: `paired_bootstrap(deltas: list[float], seed: int, samples: int = 10000) -> ConfidenceInterval`.
- Produces: `paired_sign_permutation(directional_deltas: Sequence[float], *, alternative: Literal["greater"] = "greater") -> ExactPermutationResult` with exact rational raw p-value and explicit ties.
- Produces: `holm_adjust(p_values: Mapping[str, float], alpha: float) -> Mapping[str, AdjustedHypothesis]`.
- Produces: `evaluate_relative_noninferiority(code_values: Sequence[float], baseline_values: Sequence[float], *, direction: str, margin: float = 0.05) -> ConfidenceInterval` using the exact preregistered ratio formula.
- Produces: `score_run(run_dir: Path, ground_truth_dir: Path) -> dict[str, object]`.
- Produces: `evaluate_g4(scorecard: dict[str, object], gates: dict[str, object]) -> Literal["pass", "fail", "inconclusive"]`.

**Phase 1: Write exact-value metric RED tests**

- [ ] **Step 1.1 (2–5 min): Add reference precision exact-value cases**
- [ ] **Step 1.2 (2–5 min): Add false-miswire exact-value cases**
- [ ] **Step 1.3 (2–5 min): Add impact macro-F1 exact-value cases**
- [ ] **Step 1.4 (2–5 min): Add map noise/top-50 exact-value cases**
- [ ] **Step 1.5 (2–5 min): Add latency/refresh percentile cases**
- [ ] **Step 1.6 (2–5 min): Add agent relative non-inferiority cases**
- [ ] **Step 1.7 (2–5 min): Add exact sign-permutation/tie cases**
- [ ] **Step 1.8 (2–5 min): Add separate Holm-family cases**
- [ ] **Step 1.9 (2–5 min): Add fail/inconclusive/SOTA gate cases**

```python
import pytest

from benchmarks.metrics.classification import precision_recall_f1
from benchmarks.metrics.map_quality import map_source_metrics, ndcg_at
from benchmarks.metrics.performance import nearest_rank_percentile
from benchmarks.stats import (
    evaluate_relative_noninferiority,
    holm_adjust,
    paired_bootstrap,
    paired_sign_permutation,
)


def test_precision_recall_f1_known_sets():
    score = precision_recall_f1({"b", "c"}, {"a", "b"})
    assert score.precision == 0.5
    assert score.recall == 0.5
    assert score.f1 == 0.5


def test_empty_expected_and_prediction_is_not_fabricated_perfect():
    score = precision_recall_f1(set(), set())
    assert score.scorable is False


def test_map_metrics_known_order():
    assert ndcg_at([3.0, 2.0, 0.0], 3) == 1.0


def test_map_noise_uses_independent_labels_not_product_claims():
    predicted = [
        {"symbol_id": "a", "source_class": "product"},
        {"symbol_id": "b", "source_class": "product"},
        {"symbol_id": "c", "source_class": "tool"},
    ]
    adjudicated = {"a": "product", "b": "test", "c": "product"}
    score = map_source_metrics(predicted, adjudicated, k=3)
    assert score.noise_rate == 1 / 3
    assert score.forbidden_count == 1
    assert score.confusion["product"]["test"] == 1
    assert score.confusion["tool"]["product"] == 1


def test_map_noise_rejects_missing_independent_label():
    predicted = [{"symbol_id": "missing", "source_class": "product"}]
    with pytest.raises(ValueError, match="missing adjudicated source class"):
        map_source_metrics(predicted, {}, k=1)


def test_nearest_rank_percentile():
    assert nearest_rank_percentile(list(range(1, 101)), 0.95) == 95


def test_paired_bootstrap_is_seeded_and_reports_direction():
    first = paired_bootstrap([0.2, 0.1, 0.3, 0.2], seed=20260723, samples=10_000)
    second = paired_bootstrap([0.2, 0.1, 0.3, 0.2], seed=20260723, samples=10_000)
    assert first == second
    assert first.low > 0


def test_agent_margin_is_relative_and_directional():
    success = evaluate_relative_noninferiority([0.76, 0.80], [0.80, 0.80], direction="higher_is_better")
    cost = evaluate_relative_noninferiority([1.04, 1.05], [1.00, 1.00], direction="lower_is_better")
    assert success.boundary == 0.95
    assert cost.boundary == 1.05


def test_core_holm_covers_every_primary_endpoint_by_required_baseline(analysis_plan):
    hypotheses = required_core_hypotheses(analysis_plan)
    adjusted = holm_adjust({name: 0.01 for name in hypotheses}, alpha=0.05)
    assert set(adjusted) == set(hypotheses)


def test_agent_family_is_exactly_four_codesextant_vs_no_tool_hypotheses(analysis_plan):
    assert agent_hypotheses(analysis_plan) == {
        "agent.success.with_codesextant_vs_no_tool_control",
        "agent.input_tokens.with_codesextant_vs_no_tool_control",
        "agent.tool_calls.with_codesextant_vs_no_tool_control",
        "agent.cost.with_codesextant_vs_no_tool_control",
    }


def test_missing_required_core_baseline_is_not_dropped_from_family(analysis_plan):
    p_values = complete_core_fixture_p_values(analysis_plan)
    p_values.pop(next(iter(p_values)))
    with pytest.raises(ValueError, match="required hypothesis missing"):
        holm_core_family(analysis_plan, p_values)


def test_exact_one_sided_p_value_null_and_ties():
    all_wins = paired_sign_permutation([1.0, 2.0, 3.0])
    assert all_wins.raw_p_numerator == 1
    assert all_wins.raw_p_denominator == 8
    assert all_wins.raw_p_value == 0.125
    mixed = paired_sign_permutation([1.0, -4.0, 0.0])
    assert mixed.wins == 1 and mixed.nonzero_pairs == 2 and mixed.ties == 1
    assert mixed.raw_p_value == 0.75
    assert mixed.null == "within-pair labels are exchangeable and directional win probability is 0.5"
    assert mixed.alternative == "greater"
    assert mixed.rng_used is False
    tied = paired_sign_permutation([0.0, 0.0])
    assert tied.ties == 2 and tied.nonzero_pairs == 0
    assert tied.raw_p_numerator == 1 and tied.raw_p_denominator == 1
    assert tied.raw_p_value == 1.0
    assert tied.seed == 20260723 and tied.rng_used is False
```

Create `tests/benchmarks/test_g4_gate.py` with a fully passing synthetic scorecard, then mutate one field at a time. Verify precision `0.9499`, miswire `0.0101`, one forbidden top-50 entry, warm p95 `200.1`, only one agent win, any corruption, and any duplicate daemon each yield `fail`. Verify all ties with no significant win yield `inconclusive`, not `pass`. For each of the eight required baselines independently, mutate build/install/probe/runtime status on one required matrix row and assert the overall result is `fail` for product/harness-invalidating failures or `inconclusive` for a baseline-only unavailable comparison, and in both cases `sota=false`. Verify that omitting a baseline, capability row, coverage denominator, comparable denominator, direction, paired unit, relative-margin calculation, raw p-value, or Holm-adjusted result is fail-closed. Verify any SOTA text lacking exact corpus-lock digest, operation list, language list, and required-baseline list is rejected.

**Phase 2: Observe RED**

- [ ] **Step 2.1 (2–5 min): Run metric/stat/gate tests once and record RED**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_metrics.py tests/benchmarks/test_stats.py tests/benchmarks/test_g4_gate.py -q
```

Expected: collection fails because the metrics and statistics modules do not exist.

**Phase 3: Implement classification/ranking metrics**

- [ ] **Step 3.1 (2–5 min): Implement reference precision**
- [ ] **Step 3.2 (2–5 min): Implement cross-language false-miswire rate**
- [ ] **Step 3.3 (2–5 min): Implement impact macro F1**
- [ ] **Step 3.4 (2–5 min): Implement default-map noise**
- [ ] **Step 3.5 (2–5 min): Implement forbidden top-50 count**
- [ ] **Step 3.6 (2–5 min): Implement latency/refresh percentiles**
- [ ] **Step 3.7 (2–5 min): Implement product-class confusion matrix**

Use immutable score records:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ClassificationScore:
    precision: float | None
    recall: float | None
    f1: float | None
    true_positive: int
    false_positive: int
    false_negative: int
    scorable: bool


def precision_recall_f1(expected: set[str], predicted: set[str]) -> ClassificationScore:
    tp = len(expected & predicted)
    fp = len(predicted - expected)
    fn = len(expected - predicted)
    if not expected and not predicted:
        return ClassificationScore(None, None, None, 0, 0, 0, False)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return ClassificationScore(precision, recall, f1, tp, fp, fn, True)
```

`ndcg_at` uses gain `2**relevance - 1`, log-base-2 discount, and the ideal sorted relevance list. `map_source_metrics` joins each returned `symbol_id` to independently adjudicated map ground truth. Ground-truth classes `test`, `fixture`, `generated`, `vendored`, `tool`, and `proof_of_concept` count as noise; the same labels define the top-50 forbidden count. Missing/duplicate labels make the run unverifiable. Product-declared source class is never an answer key: it is used only to emit a complete predicted-class-by-ground-truth-class confusion matrix.

**Phase 4: Implement preregistered paired statistics**

- [ ] **Step 4.1 (2–5 min): Implement directional delta normalization**
- [ ] **Step 4.2 (2–5 min): Count/report exact-zero ties before exclusion**
- [ ] **Step 4.3 (2–5 min): Implement exact upper-binomial raw p-value**
- [ ] **Step 4.4 (2–5 min): Serialize null/alternative/pairs/ties/seed/rng flag**
- [ ] **Step 4.5 (2–5 min): Implement core-family Holm correction**
- [ ] **Step 4.6 (2–5 min): Implement four-hypothesis no-tool Holm correction**
- [ ] **Step 4.7 (2–5 min): Reject missing/duplicate/cross-family hypotheses**

`paired_bootstrap` remains a descriptive confidence-interval calculation: it resamples paired deltas with replacement 10,000 times using `random.Random(20260723)`, calculates the mean for each sample, and returns percentile bounds at 2.5% and 97.5%. It is never the raw significance p-value. Repository-level macro metrics resample repositories, not individual edges, to prevent a large repository dominating the interval. Performance pairs the same case/repetition block and uses nearest-rank percentiles while reporting all raw repetitions. Agent metrics pair the two arms of the same task.

Implement every primary endpoint from `analysis-plan.json` without inferred defaults. Higher-is-better effects use `CodeSextant / comparator`; lower-is-better effects also use that ratio but reverse the acceptance inequality. The relative 5% agent non-inferiority boundaries are exactly 0.95 for success and 1.05 for tokens/tool calls/cost, always versus `no_tool_control`. Zero-denominator handling follows the preregistration.

`paired_sign_permutation` transforms lower-is-better deltas before testing, drops exact-zero ties only after counting/reporting them, computes the exact upper binomial tail using integer combinations, and returns numerator/denominator plus a float. The null, `alternative="greater"`, tie count, pair count, and `rng_used=false` are serialized with every raw p-value; `seed=20260723` is serialized as the schedule seed, not falsely described as p-value randomness. `holm_adjust` runs independently over (a) the complete named core endpoint-by-required-baseline family and (b) exactly four agent CodeSextant-vs-no-tool-control hypotheses. It emits family ID, raw exact p-value, adjusted p-value, rank, family size, decision, direction, and paired unit. Missing/duplicate/cross-family hypotheses invalidate the scorecard; secondary analyses and unrun workload-capable competitors cannot create an agent or SOTA claim.

Use:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ConfidenceInterval:
    estimate: float
    low: float
    high: float
    level: float = 0.95
```

**Phase 5: Implement the G4 evaluator**

- [ ] **Step 5.1 (2–5 min): Require final manifest/tree digests**
- [ ] **Step 5.2 (2–5 min): Emit coverage and comparable denominators separately**
- [ ] **Step 5.3 (2–5 min): Emit required-baseline failure ledger**
- [ ] **Step 5.4 (2–5 min): Emit `not_evaluated` workload competitor rows**
- [ ] **Step 5.5 (2–5 min): Apply every hard threshold/failure rule**
- [ ] **Step 5.6 (2–5 min): Gate scoped SOTA template on core significance only**

`evaluate_g4` reads thresholds only from `gates.json`. It returns:

- `fail` if any hard threshold is red, the product artifact/runtime/resources/evaluator/reviewer contract is invalid, a CodeSextant required pair fails, a required tuple is missing without preregistered unsupported evidence, or reliability reports corruption/duplicate daemon.
- `inconclusive` if a required external baseline cannot build/install/probe/run a required pair, an independent host cannot reproduce the locked performance environment, a required paired interval crosses its preregistered boundary, or all core differences are ties. `inconclusive` always means `sota=false`.
- `pass` only when every hard condition is green, all eight required baselines executed every required core pair, coverage and comparable denominators are complete and separate, agent non-inferiority holds against `no_tool_control` in all four dimensions, at least two of those four agent hypotheses win after the separate agent Holm correction, no core competitor dominates an entire comparable language corpus, and at least one core endpoint beats the strongest reproduced baseline after the separate core Holm correction.

`score_run` refuses a missing/non-final manifest or any result-tree digest mismatch, then writes a schema-valid `scorecard.json` and a per-repository table. The scorecard includes the complete capability inventory, coverage denominator, comparable denominator, required-baseline failure ledger, endpoint direction/paired unit, exact raw permutation fields, separately Holm-adjusted core and agent families, `not_evaluated` rows for workload-capable competitor agent arms, map source-class confusion matrix, and independent-label digest. It never reads tool labels, product-declared classes, runtime availability, or Markdown marketing names to choose an averaging rule. Its optional claim field can only render the analysis-plan template scoped to the exact corpus lock, operation/language intersection, and eight required core baselines; agent prose is limited to CodeSextant versus no-tool control.

**Phase 6: Verify metrics and fixture score**

- [ ] **Step 6.1 (2–5 min): Run focused metric/stat/gate GREEN tests**
- [ ] **Step 6.2 (2–5 min): Score the final fixture run**
- [ ] **Step 6.3 (2–5 min): Validate fixture scorecard schema/families**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_metrics.py tests/benchmarks/test_stats.py tests/benchmarks/test_g4_gate.py -q
uv run --frozen --no-sync --project benchmarks python -m benchmarks.score --manifest tests/benchmarks/fixtures/final-run/run-manifest.json --run tests/benchmarks/fixtures/final-run --ground-truth tests/benchmarks/fixtures/ground_truth --analysis-plan benchmarks/analysis-plan.json --out .benchmark-cache/fixture-scorecard.json
```

Expected: tests pass; fixture scoring returns `fail` because its intentional timeout is retained.

**Phase 7: Commit metrics**

- [ ] **Step 7.1 (2–5 min): Stage only metrics/stats/score/tests and inspect**
- [ ] **Step 7.2 (2–5 min): Commit metrics without measured result files**

```powershell
$expectedStaged = @('benchmarks/metrics/__init__.py','benchmarks/metrics/classification.py','benchmarks/metrics/impact.py','benchmarks/metrics/map_quality.py','benchmarks/metrics/navigation.py','benchmarks/metrics/performance.py','benchmarks/metrics/reliability.py','benchmarks/stats.py','benchmarks/score.py','tests/benchmarks/fixtures/final-run/run-manifest.json','tests/benchmarks/fixtures/final-run/core-results.json','tests/benchmarks/fixtures/final-run/agent/results.json','tests/benchmarks/fixtures/final-run/raw-records.jsonl','tests/benchmarks/test_metrics.py','tests/benchmarks/test_stats.py','tests/benchmarks/test_g4_gate.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'bench: enforce preregistered competitive thresholds'
```

### Task G4.7: Add Paired Agent-Efficiency Experiments

**Files:**
- Create: `benchmarks/agent/__init__.py`
- Create: `benchmarks/agent/model.py`
- Create: `benchmarks/agent/provider_contract.py`
- Create: `benchmarks/agent/credential.py`
- Create: `benchmarks/agent/build_tasks.py`
- Generate: `benchmarks/agent/tasks.lock`
- Generate: `benchmarks/agent/model.lock`
- Create: `benchmarks/agent/pricing.lock`
- Create: `benchmarks/agent/pricing-evidence/provider-pricing.json`
- Create: `benchmarks/agent/broker/Dockerfile`
- Create: `benchmarks/agent/broker-lock.schema.json`
- Create: `benchmarks/agent/credential-handle.schema.json`
- Create: `benchmarks/agent/pricing-lock.schema.json`
- Generate: `benchmarks/agent/broker.lock`
- Create: `benchmarks/agent/evaluator-commitment.schema.json`
- Create: `benchmarks/agent/evaluator-verification.schema.json`
- Create: `benchmarks/agent/evaluator.py`
- Create: `benchmarks/agent/sandbox.py`
- Create: `benchmarks/agent/driver.py`
- Create: `benchmarks/agent/evaluate.py`
- Create: `tests/benchmarks/fixtures/mock_provider.py`
- Create: `tests/benchmarks/fixtures/mock-credential-handle.json`
- Create: `tests/benchmarks/fixtures/evaluator-commitment.json`
- Create: `tests/benchmarks/test_agent_tasks.py`
- Create: `tests/benchmarks/test_agent_driver.py`
- Create: `tests/benchmarks/test_agent_sandbox.py`
- Create: `tests/benchmarks/test_agent_network_isolation.py`
- Create: `tests/benchmarks/test_evaluator_commitment.py`
- Create: `tests/benchmarks/test_agent_redaction.py`
- Create: `tests/benchmarks/test_credential_isolation.py`

**Interfaces:**
- Consumes: holdout corpus commits, CodeSextant adapter, run manifests, and statistical functions.
- Produces: `AgentTask(task_id, repo_id, base_commit, instruction, evaluator_slot, public_smoke_command, timeout_ms)`; hidden acceptance commands/bytes live only in the external commitment.
- Produces: broker stdin request with model ID, immutable config hash, opaque workspace handle, instruction, allowed tools, and output handle; no host repository path is exposed.
- Produces: provider stdout response with exit status, input/output tokens, tool-call list, elapsed time, and a confined transcript artifact handle plus SHA-256; no host path is serialized.
- Produces: `run_pair(task: AgentTask, broker: LockedProviderBroker, credential_handle: CredentialHandle, seed: int) -> PairedAgentResult`; no free-form provider command or raw key is accepted.
- Produces: `materialize_agent_sandbox(base_tree: Path, destination: Path) -> SandboxReceipt` with no Git metadata, remote, target object, answer, evaluator, or network path.
- Produces: `commit_evaluator(*, tasks_lock: Path, hidden_root: Path, custodian_attestation: Path, signing_key_path: Path, commitment_output: Path, verification_output: Path) -> VerifiedEvaluatorPath` and `verify_evaluator_commitment(*, commitment_path: Path, verification_path: Path, tasks_lock: Path, hidden_root: Path, reviewer_roles_lock: Path) -> VerifiedEvaluatorPath`.
- Produces: `evaluate_patch(checkout: Path, evaluator_commitment: Path, hidden_root: Path, task_id: str, timeout_ms: int) -> bool`, with command/blob bytes resolved only after both arms have exited.
- Consumes: `benchmarks/agent/broker.lock`, whose OCI/executable/entrypoint/protocol hashes replace any free-form provider command.
- Consumes: one opaque `CredentialHandle`; only the broker supervisor may resolve it, while persisted records contain only `credential_identity_sha256 = SHA256(provider_id || "\0" || account_id || "\0" || key_id)` over provider-issued nonsecret identifiers.
- Defines: frozen `CredentialHandle(provider_id: str, account_id: str, key_id: str, resolver_kind: str, opaque_handle: str)`; frozen `LockedProviderBroker(lock_path: Path, image_digest: str, executable_sha256: str, protocol_sha256: str)`; frozen `SandboxReceipt(root: Path, input_tree_sha256: str, network_mode: Literal["none"], remote_urls: Sequence[str], target_object_count: int, hidden_evaluator_paths: Sequence[str], git_environment_exposed: bool)`; frozen `VerifiedEvaluatorPath(commitment_path: Path, verification_path: Path, commitment_sha256: str, verified_tree_sha256: str, evaluator_slot: str, verified_before_run_nonce: bool)`; frozen `AgentArmResult(arm: Literal["with_codesextant", "no_tool_control"], success: bool, input_tokens: int, output_tokens: int, tool_calls: int, cost: Decimal, transcript_sha256: str)`; and frozen `PairedAgentResult(task_id: str, first_arm: str, second_arm: str, treatment: AgentArmResult, control: AgentArmResult, evaluator_receipt_sha256: str)`.

**Phase 1: Write agent-harness RED tests**

- [ ] **Step 1.1 (2–5 min): Add immutable task/base-commit assertions**
- [ ] **Step 1.2 (2–5 min): Add balanced pair-order assertions**
- [ ] **Step 1.3 (2–5 min): Add transcript/path/credential redaction assertions**
- [ ] **Step 1.4 (2–5 min): Add malicious Git/target-answer sandbox assertions**
- [ ] **Step 1.5 (2–5 min): Add network-none OCI integration assertions**
- [ ] **Step 1.6 (2–5 min): Add evaluator commitment/verification-order assertions**
- [ ] **Step 1.7 (2–5 min): Add broker/provider contract assertions**
- [ ] **Step 1.8 (2–5 min): Add credential sentinel and identity-digest assertions**

```python
from benchmarks.agent.driver import paired_order, redact_record
from benchmarks.agent.model import AgentTask


def task() -> AgentTask:
    return AgentTask(
        task_id="flask-001",
        repo_id="flask-holdout",
        base_commit="a" * 40,
        instruction="Fix the failing route registration behavior described by the test.",
        evaluator_slot="flask-001",
        public_smoke_command=["python", "-m", "pytest", "-q"],
        timeout_ms=900_000,
    )


def test_pair_order_is_balanced_and_deterministic():
    first = [paired_order(f"task-{i}", 20260723) for i in range(20)]
    second = [paired_order(f"task-{i}", 20260723) for i in range(20)]
    assert first == second
    assert first.count(("with_codesextant", "no_tool_control")) == 10
    assert first.count(("no_tool_control", "with_codesextant")) == 10


def test_redaction_removes_credentials_and_absolute_home():
    value = {
        "env": {"ANTHROPIC_API_KEY": "secret-value"},
        "transcript": "read C:/Users/person/private.py with token secret-value",
    }
    cleaned = redact_record(value, secrets=["secret-value"], home="C:/Users/person")
    rendered = str(cleaned)
    assert "secret-value" not in rendered
    assert "C:/Users/person" not in rendered


def test_task_validation_is_external_not_model_self_report():
    assert task().evaluator_slot == "flask-001"
    assert task().public_smoke_command == ["python", "-m", "pytest", "-q"]
    assert not hasattr(task(), "hidden_validation_command")
```

`test_agent_tasks.py` creates a temporary two-commit repository, runs `build_tasks`, and asserts every task uses the parent commit as `base_commit`, contains only a public smoke command plus opaque evaluator slot, omits hidden validation commands, target patch, child/target commit SHA, and answer-derived text, and has a full base commit SHA.

Create `tests/benchmarks/test_agent_sandbox.py` from an intentionally malicious source fixture, not a clean toy directory:

```python
from pathlib import Path

from benchmarks.agent.sandbox import materialize_agent_sandbox


def test_agent_sandbox_has_no_git_target_answer_or_network(tmp_path: Path):
    base = tmp_path / "base"
    (base / ".git/objects/aa").mkdir(parents=True)
    (base / ".git/refs/heads").mkdir(parents=True)
    (base / ".git/config").write_text(
        "[remote \"origin\"]\nurl=https://example.invalid/private.git\n", encoding="utf-8"
    )
    (base / ".git/refs/heads/target").write_text("b" * 40 + "\n", encoding="ascii")
    (base / ".git/objects/aa/target-object").write_bytes(b"target child object")
    (base / "app.py").write_text("def value(): return 1\n", encoding="utf-8")
    (base / "target.patch").write_text("the hidden answer", encoding="utf-8")
    (base / "hidden-evaluator").mkdir()
    (base / "hidden-evaluator/answer.json").write_text('{"answer": 2}', encoding="utf-8")
    receipt = materialize_agent_sandbox(base, tmp_path / "sandbox")
    assert not any(path.name == ".git" for path in receipt.root.rglob("*"))
    assert receipt.network_mode == "none"
    assert receipt.remote_urls == ()
    assert receipt.target_object_count == 0
    assert receipt.hidden_evaluator_paths == ()
    assert receipt.git_environment_exposed is False
    assert not (receipt.root / "target.patch").exists()
```

The test also seeds alternate Git directories via `.git` file indirection, packed refs, worktree metadata, reflogs, object alternates, remote URLs in config files, child/tree/blob IDs, filenames from the target patch, evaluator/answer paths, and mining caches. It asserts the exported file allowlist and content scan remove or reject every sentinel rather than merely deleting a top-level `.git` directory.

Create `tests/benchmarks/test_agent_network_isolation.py` as a mandatory OCI integration test. It starts a controlled TCP listener on the host, launches the exact locked workload sandbox with `--network none`, and runs a probe that attempts DNS, the host listener, a public IP, and the provider endpoint. The probe must return a normalized blocked result for all four, the host listener must observe zero connections, and the container's route table must contain only loopback. A missing OCI runtime skips nothing: it fails adapter readiness and therefore prevents G4 scoring.

Create `tests/benchmarks/test_evaluator_commitment.py` with an external hidden evaluator tree containing a test, expected answer, and validation command. Assert the canonical commitment binds the `tasks.lock` digest, every task ID, evaluator relative path/blob SHA-256, normalized command SHA-256, evaluator image digest, custodian reviewer-attestation digest/signature, and aggregate commitment digest while revealing no test/answer bytes. `commit_evaluator` must atomically write both the signed commitment and `evaluator-verification.json`, whose root-relative evaluator slot (never an absolute host path), commitment SHA-256, verified tree SHA-256, custodian ID/key, verification command digest, and `verified_before_run_nonce=true` are consumed by both host scripts. Each script resolves that slot beneath its own authorized evaluator root and rehashes the local bytes. Mutating one hidden byte, task lock, command, signature, verification slot/receipt, or creation order must fail. Assert neither `materialize_agent_sandbox` nor the provider-broker request receives the hidden root or commitment's private slot. A run start timestamp/nonce created before the custodian verification is a hard error.

**Phase 2: Observe RED**

- [ ] **Step 2.1 (2–5 min): Run all agent-harness tests once and record missing modules/fixtures**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_agent_tasks.py tests/benchmarks/test_agent_driver.py tests/benchmarks/test_agent_sandbox.py tests/benchmarks/test_agent_network_isolation.py tests/benchmarks/test_evaluator_commitment.py tests/benchmarks/test_agent_redaction.py tests/benchmarks/test_credential_isolation.py -q
```

Expected: collection fails because `benchmarks.agent.driver`, `benchmarks.agent.model`, `benchmarks.agent.credential`, and `benchmarks.agent.evaluator` do not exist and the two complete credential/evaluator fixtures are not yet consumable. This is the required RED observation.

**Phase 3: Implement tasks/provider/evaluator contracts**

- [ ] **Step 3.1 (2–5 min): Add immutable `AgentTask` model**
- [ ] **Step 3.2 (2–5 min): Add deterministic parent-commit task mining**
- [ ] **Step 3.3 (2–5 min): Strip target/evaluator/remote/mining metadata from task lock**
- [ ] **Step 3.4 (2–5 min): Add broker request/response schemas**
- [ ] **Step 3.5 (2–5 min): Add immutable broker/model lock verification**
- [ ] **Step 3.6 (2–5 min): Add opaque credential-handle parsing**
- [ ] **Step 3.7 (2–5 min): Add broker-only secret resolution**
- [ ] **Step 3.8 (2–5 min): Add nonsecret credential identity digest**
- [ ] **Step 3.9 (2–5 min): Add evaluator commitment generation**
- [ ] **Step 3.10 (2–5 min): Add pre-nonce evaluator verification receipt**

Create:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentTask:
    task_id: str
    repo_id: str
    base_commit: str
    instruction: str
    evaluator_slot: str
    public_smoke_command: list[str]
    timeout_ms: int
```

`build_tasks.py` deterministically mines bug-fix commits from a preparation-only clone, uses the parent as the working base, retains only commits whose hidden focused evaluator fails on the parent and passes on the child, removes issue text that reveals the patch, and emits canonical JSON. Before writing `tasks.lock`, it removes hidden validation commands, evaluator bytes, child commit IDs, target tree/blob IDs, diff-derived text, remote URLs, and mining-cache paths; then it deletes the preparation clone. Curate and independently review 30 tasks across at least six repositories, with Python and TypeScript represented. `tasks.lock` stores only the base commit, neutral instruction, opaque evaluator slot, public smoke-command metadata, and input-tree SHA-256; it never stores a hidden command, target diff, expected patch, child SHA, evaluator digest, or answer hash. The independently held evaluator tree is committed separately through `commit_evaluator` after `tasks.lock` freezes.

`provider_contract.py` invokes only the broker entrypoint from `broker.lock`; it accepts no command string or raw API key from CLI/environment and does not import a vendor SDK into the workload. `broker.lock` contains provider ID, `linux/amd64` OCI image manifest digest, image-recipe/dependency-lock digests, absolute in-container executable path and executable SHA-256, argv array, provider-contract schema digest, allowed egress host/port, and `repository_mount=false`. The broker image is built twice reproducibly and its executable is rehashed inside the launched container before every run.

`credential.py` accepts an opaque credential handle from the host secret manager. A broker supervisor resolves the handle directly into the broker container environment without returning the secret to Python, stdout/stderr, the workload, or the caller. `credential-handle.schema.json` exposes only provider ID, nonsecret provider-issued account ID, nonsecret provider-issued key ID, resolver kind, and opaque handle; persisted data replaces those identifiers with `credential_identity_sha256 = SHA256(provider_id || "\0" || account_id || "\0" || key_id)`. It never hashes the secret value. Primary and independent runs must use different credential-identity digests, and comparison rejects equality before interpreting agent results. The broker receives no host/repository path, repository bytes, evaluator path/bytes, target objects, or answer. The provider must report an immutable model snapshot ID and token counts from its own machine-readable usage response; a mutable alias or missing usage makes the pair `unscorable`, not zero. `model.lock` binds the snapshot ID, system-prompt SHA-256, temperature, maximum output tokens, tool schema SHA-256, broker-lock SHA-256, and probe evidence.

`tests/benchmarks/test_credential_isolation.py` installs a fake resolver returning sentinel `sk-live-never-persist`, then instruments the orchestrator, workload container argv/env, broker request/response, logs, transcripts, run manifest, handoff/result bundle, report, and receipts. The sentinel and its SHA-256 must appear only in the broker container's ephemeral environment snapshot held by the test harness; every persistent surface and workload observation must lack both. A second test supplies the same nonsecret account/key IDs under two different opaque handle strings and proves identity digests collide as intended and independent comparison rejects them; different key IDs must produce distinct digests.

**Phase 4: Implement paired execution**

- [ ] **Step 4.1 (2–5 min): Export one Git-free base tree**
- [ ] **Step 4.2 (2–5 min): Reject alternate Git/target/evaluator sentinels**
- [ ] **Step 4.3 (2–5 min): Launch network-none workload sandbox**
- [ ] **Step 4.4 (2–5 min): Launch isolated provider broker without repository mount**
- [ ] **Step 4.5 (2–5 min): Mount CodeSextant only in the treatment arm**
- [ ] **Step 4.6 (2–5 min): Keep the control explicitly `no_tool_control`**
- [ ] **Step 4.7 (2–5 min): Record workload competitors as `not_evaluated`**
- [ ] **Step 4.8 (2–5 min): Evaluate only after both provider arms exit**
- [ ] **Step 4.9 (2–5 min): Persist redacted paired usage/result records**

`run_pair` materializes two plain source-tree exports at the same base commit through `materialize_agent_sandbox`; neither contains `.git`, objects, refs, remotes, target answers, hidden evaluator files, commitment private locators, or mining metadata. Every filesystem and tool action runs inside the pinned OCI workload sandbox with `--network none`, an explicit empty proxy configuration, a read-only task-input mount, and one writable work mount. The separately pinned provider broker may reach only its locked model API endpoint; only its supervisor receives the opaque credential handle and only its container receives the resolved provider key. It receives no repository mount/path/bytes, target object, evaluator material, or host filesystem. It exchanges only versioned provider-contract messages plus bounded tool observations. Both arms receive the same model snapshot, parameters, system-prompt hash, neutral instruction, timeout, broker lock, and allowed non-CodeSextant tools. One workload sandbox receives the verified Linux CodeSextant artifact selected from ReleaseSubject and mounted through `product-runtime.lock`; the other is explicitly named `no_tool_control` and receives no code-navigation competitor. Pair order uses the fixed balanced schedule. Only after both provider arms exit does a separate evaluator namespace verify the signed commitment, mount the hidden evaluator bytes, run its committed command, and record exit code/digests; the model's own success statement and public smoke command cannot mark a task successful. Workload-capable competitors are recorded as `not_evaluated`, never silently treated as control arms.

`pricing.lock` records provider/model snapshot, effective UTC date, input/output/cache prices, currency, billing unit, official pricing URL, exact `pricing-evidence/provider-pricing.json` size/SHA-256, and decoded response-body size/SHA-256. That evidence file stores the immutable raw official response body as base64 plus content type and capture metadata without credentials; its schema requires canonical base64 and reproduces the exact original bytes. Verification decodes and rereads those bytes, matches both sizes/hashes, and recomputes cost from token usage; a URL/hash without retained evidence bytes is invalid. Lock the broker, model, pricing, and evidence bytes before the scored run.

`evaluator-commitment.schema.json` requires format version, tasks-lock SHA-256, evaluator image digest, sorted per-task slot/blob/path/command digests, aggregate tree digest, custodian reviewer-attestation digest, detached Ed25519 signature, and canonical commitment digest. It prohibits evaluator content, answer text, absolute paths, remote URLs, credentials, and nondeterministic timestamps. `evaluator-verification.schema.json` is a private runtime receipt that may contain only a root-relative evaluator slot plus hashes/identity/ordering proof; public outputs retain only its digest. Before either provider call, the holdout custodian—not the product/operator—runs `release/g4/prepare-evaluator.ps1`, which invokes `commit_evaluator`, immediately reopens and verifies every committed byte, and produces the verification-file path consumed by both signed host bundles. Both primary and independent manifests bind the same commitment and verification-receipt digests; each host resolves the slot under its own authorized root, and evaluator bytes are mounted only after both arms for that task have exited.

**Phase 5: Generate agent locks**

- [ ] **Step 5.1 (2–5 min): Generate the 30-task lock**
- [ ] **Step 5.2 (2–5 min): Recheck the task lock deterministically**
- [ ] **Step 5.3 (2–5 min): Pin/rebuild the broker lock**
- [ ] **Step 5.4 (2–5 min): Pin immutable model snapshot/config**
- [ ] **Step 5.5 (2–5 min): Verify retained pricing evidence bytes**
- [ ] **Step 5.6 (2–5 min): Verify broker executable/protocol digests**

Run:

```powershell
uv run --frozen --no-sync --project benchmarks python -m benchmarks.agent.build_tasks --corpus benchmarks/corpus.lock --out benchmarks/agent/tasks.lock --seed 20260723 --count 30
uv run --frozen --no-sync --project benchmarks python -m benchmarks.agent.build_tasks --check benchmarks/agent/tasks.lock
uv run --frozen --no-sync --project benchmarks python -m benchmarks.agent.provider_contract pin-broker --recipe benchmarks/agent/broker/Dockerfile --out benchmarks/agent/broker.lock
uv run --frozen --no-sync --project benchmarks python -m benchmarks.agent.provider_contract pin-model --broker-lock benchmarks/agent/broker.lock --out benchmarks/agent/model.lock
uv run --frozen --no-sync --project benchmarks python -m benchmarks.agent.provider_contract verify-pricing --lock benchmarks/agent/pricing.lock --evidence-root benchmarks/agent/pricing-evidence
uv run --frozen --no-sync --project benchmarks python -m benchmarks.agent.provider_contract verify-broker --lock benchmarks/agent/broker.lock
```

Expected: 30 independently validated tasks across at least six repositories, no target/evaluator content, an immutable model snapshot/config hash, a reproducibly built and executable-hash-verified broker, and retained pricing evidence bytes matching the lock's exact size/hash.

**Phase 6: Verify paired harness**

- [ ] **Step 6.1 (2–5 min): Run all focused agent GREEN tests**
- [ ] **Step 6.2 (2–5 min): Run one mocked no-tool-control pair fixture**
- [ ] **Step 6.3 (2–5 min): Inspect sandbox/broker/evaluator/credential receipts**

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_agent_tasks.py tests/benchmarks/test_agent_driver.py tests/benchmarks/test_agent_sandbox.py tests/benchmarks/test_agent_network_isolation.py tests/benchmarks/test_evaluator_commitment.py tests/benchmarks/test_agent_redaction.py tests/benchmarks/test_credential_isolation.py -q
uv run --frozen --no-sync --project benchmarks python -m benchmarks.agent.driver fixture --broker-lock benchmarks/agent/broker.lock --credential-handle tests/benchmarks/fixtures/mock-credential-handle.json --evaluator-commitment tests/benchmarks/fixtures/evaluator-commitment.json --out .benchmark-cache/agent-fixture
```

Expected: tests pass; the real locked OCI isolation test proves all outbound workload connections fail; fixture output contains two network-disabled, Git-free paired arms with identical config hashes, hidden-evaluator results, usage, tool calls, and redacted transcripts. The agent hypothesis universe contains only `with_codesextant` versus `no_tool_control`; workload-capable competitors remain explicit `not_evaluated` rows. The sandbox receipt reports zero target objects and zero hidden evaluator paths; the broker receipt proves no repository/evaluator mount and exact executable digest. Primary and independent fixture identities use distinct provider-issued account/key digests, while the secret and its SHA-256 occur on no persistent surface.

**Phase 7: Commit agent harness**

- [ ] **Step 7.1 (2–5 min): Stage only agent source/fixtures/tests and inspect**
- [ ] **Step 7.2 (2–5 min): Commit before any paid/scored trial**

```powershell
$expectedStaged = @('benchmarks/agent/__init__.py','benchmarks/agent/model.py','benchmarks/agent/provider_contract.py','benchmarks/agent/credential.py','benchmarks/agent/build_tasks.py','benchmarks/agent/tasks.lock','benchmarks/agent/model.lock','benchmarks/agent/pricing.lock','benchmarks/agent/pricing-evidence/provider-pricing.json','benchmarks/agent/broker/Dockerfile','benchmarks/agent/broker-lock.schema.json','benchmarks/agent/credential-handle.schema.json','benchmarks/agent/pricing-lock.schema.json','benchmarks/agent/broker.lock','benchmarks/agent/evaluator-commitment.schema.json','benchmarks/agent/evaluator-verification.schema.json','benchmarks/agent/evaluator.py','benchmarks/agent/sandbox.py','benchmarks/agent/driver.py','benchmarks/agent/evaluate.py','tests/benchmarks/fixtures/mock_provider.py','tests/benchmarks/fixtures/mock-credential-handle.json','tests/benchmarks/fixtures/evaluator-commitment.json','tests/benchmarks/test_agent_tasks.py','tests/benchmarks/test_agent_driver.py','tests/benchmarks/test_agent_sandbox.py','tests/benchmarks/test_agent_network_isolation.py','tests/benchmarks/test_evaluator_commitment.py','tests/benchmarks/test_agent_redaction.py','tests/benchmarks/test_credential_isolation.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'bench: add paired agent-efficiency harness'
```

### Task G4.8A: Add Cross-Platform Path Confinement and the Native Boundary

This starts the final source-changing G4 sequence after G5 has committed the shared ReleaseSubject schema, gate-status schema, receipt registry, and canonical `subject_digest`. Each checkbox below is one independently checkable 2–5 minute action.

**Files:**
- Create: `benchmarks/paths.py`
- Create: `release/g4/Invoke-Native.ps1`
- Create: `tests/benchmarks/test_path_confinement.py`
- Create: `tests/benchmarks/test_native_wrapper.py`

**Interfaces:**
- Produces: `resolve_confined_existing(path: Path, *, allowed_roots: Sequence[Path]) -> Path`.
- Produces: `resolve_confined_output(path: Path, *, allowed_roots: Sequence[Path]) -> Path`.
- Produces: typed `path-roots.json` with separate repository, asset, holdout, evaluator, signing-key, cache, staging, and evidence roots.
- Produces: PowerShell `Invoke-Native -FilePath string -ArgumentList string[] -AllowEmptyStdout` as the only native-process boundary used by G4 drivers.

**Phase 1: Add path confinement RED tests**

- [ ] **Step 1.1 (2–5 min): Add relative/parent/sibling-prefix attacks**
- [ ] **Step 1.2 (2–5 min): Add Windows junction/case attacks**
- [ ] **Step 1.3 (2–5 min): Add Linux symlink/case attacks**
- [ ] **Step 1.4 (2–5 min): Add missing-input/output-parent attacks**
- [ ] **Step 1.5 (2–5 min): Add OS-reported temporary-root assertions**

In `test_path_confinement.py`, add cases for relative paths, `..`, Windows junction/Linux symlink escape, non-existing input, output-parent symlink, case variants, and sibling-prefix confusion (`allowed` versus `allowed-evil`). Windows assertions use component-wise ordinal-ignore-case semantics; Linux assertions use component-wise ordinal case-sensitive semantics. Test temporary roots with `[IO.Path]::GetTempPath()`/`tempfile.gettempdir()` and never assume `$env:TEMP` exists.

**Phase 2: Add native-wrapper RED tests**

- [ ] **Step 2.1 (2–5 min): Add 7.4/PSNative/AST assertions**
- [ ] **Step 2.2 (2–5 min): Add exit-17 stdout/stderr assertion**
- [ ] **Step 2.3 (2–5 min): Add downstream-sentinel noncreation assertion**
- [ ] **Step 2.4 (2–5 min): Add missing-executable assertion**
- [ ] **Step 2.5 (2–5 min): Add unexpected-empty-stdout assertion**

In `test_native_wrapper.py`, parse `Invoke-Native.ps1` with the PowerShell AST, require `#requires -Version 7.4`, `$PSNativeCommandUseErrorActionPreference = $true`, redirected stdout/stderr, and `ProcessStartInfo.ArgumentList`. Execute a fixture program that writes both streams and exits `17`; assert the wrapper throws with exit code/stderr and does not create a downstream sentinel. Add missing-executable and unexpected-empty-stdout cases.

- [ ] **Step 3 (2–5 min): Observe the focused RED state**

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_path_confinement.py tests/benchmarks/test_native_wrapper.py -q
```

Expected: collection fails because `benchmarks.paths` and `release/g4/Invoke-Native.ps1` do not exist.

**Phase 4: Implement component-aware path resolution**

- [ ] **Step 4.1 (2–5 min): Implement existing-input resolution**
- [ ] **Step 4.2 (2–5 min): Implement confined-output-parent resolution**
- [ ] **Step 4.3 (2–5 min): Implement Windows component comparison**
- [ ] **Step 4.4 (2–5 min): Implement Linux component comparison**
- [ ] **Step 4.5 (2–5 min): Implement broad-root rejection**
- [ ] **Step 4.6 (2–5 min): Implement POSIX archive-member confinement**

`paths.py` resolves existing inputs before comparison, requires an existing resolved parent for outputs, resolves junctions/symlinks, compares complete path components under the target platform's case rule, rejects a broad drive/temporary root, and performs a second POSIX member-name confinement check for archives. Public output stores markers/digests, never absolute roots.

**Phase 5: Implement the exact fail-closed native wrapper**

- [ ] **Step 5.1 (2–5 min): Add 7.4/strict/native preference preamble**
- [ ] **Step 5.2 (2–5 min): Add typed filepath/argv/stdout policy parameters**
- [ ] **Step 5.3 (2–5 min): Add ProcessStartInfo argument-list/redirection setup**
- [ ] **Step 5.4 (2–5 min): Add missing-start typed failure**
- [ ] **Step 5.5 (2–5 min): Add async stdout/stderr capture**
- [ ] **Step 5.6 (2–5 min): Add nonzero-exit typed failure**
- [ ] **Step 5.7 (2–5 min): Add unexpected-empty-output typed failure**
- [ ] **Step 5.8 (2–5 min): Return the exact success object**

Create `release/g4/Invoke-Native.ps1` with this shared implementation; tests may add typed error properties but may not weaken behavior:

```powershell
#requires -Version 7.4
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

function Invoke-Native {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)][string]$FilePath,
    [Parameter()][string[]]$ArgumentList = @(),
    [Parameter()][switch]$AllowEmptyStdout
  )

  $start = [Diagnostics.ProcessStartInfo]::new()
  $start.FileName = $FilePath
  $start.UseShellExecute = $false
  $start.RedirectStandardOutput = $true
  $start.RedirectStandardError = $true
  foreach ($argument in $ArgumentList) { [void]$start.ArgumentList.Add($argument) }
  $process = [Diagnostics.Process]::new()
  $process.StartInfo = $start
  try {
    if (-not $process.Start()) { throw "process returned false from Start()" }
  } catch {
    $failure = [InvalidOperationException]::new("native process did not start: $FilePath", $_.Exception)
    $failure.Data['ExitCode'] = $null
    $failure.Data['Stdout'] = ''
    $failure.Data['Stderr'] = $_.Exception.Message
    throw $failure
  }
  $stdoutTask = $process.StandardOutput.ReadToEndAsync()
  $stderrTask = $process.StandardError.ReadToEndAsync()
  $process.WaitForExit()
  $stdout = $stdoutTask.GetAwaiter().GetResult()
  $stderr = $stderrTask.GetAwaiter().GetResult()
  if ($process.ExitCode -ne 0) {
    $failure = [InvalidOperationException]::new("native command failed exit=$($process.ExitCode) file=$FilePath")
    $failure.Data['ExitCode'] = $process.ExitCode
    $failure.Data['Stdout'] = $stdout
    $failure.Data['Stderr'] = $stderr
    throw $failure
  }
  if ((-not $AllowEmptyStdout) -and [string]::IsNullOrWhiteSpace($stdout)) {
    $failure = [InvalidOperationException]::new("native command returned empty stdout: $FilePath")
    $failure.Data['ExitCode'] = 0
    $failure.Data['Stdout'] = $stdout
    $failure.Data['Stderr'] = $stderr
    throw $failure
  }
  [pscustomobject]@{ ExitCode = 0; Stdout = $stdout; Stderr = $stderr }
}
```

Every driver catches only to persist a private diagnostic object from the typed exception data, runs the same credential/path/identity redactor used by benchmark records, atomically writes that diagnostic, and immediately rethrows. It never continues to the next phase. Tests require both stdout and stderr sentinels to survive when nonsecret and require credential sentinels plus their SHA-256 to be absent.

- [ ] **Step 6 (2–5 min): Run the focused GREEN tests**

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_path_confinement.py tests/benchmarks/test_native_wrapper.py -q
git diff --check
```

Expected: both test files pass on the available platform; platform-parametrized pure-path cases prove both Windows and Linux comparison rules.

- [ ] **Step 7 (2–5 min): Commit only path/native boundary files**

```powershell
$expectedStaged = @('benchmarks/paths.py','release/g4/Invoke-Native.ps1','tests/benchmarks/test_path_confinement.py','tests/benchmarks/test_native_wrapper.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'bench: add confined paths and native boundary'
```

### Task G4.8B: Add Detached-Signed Cross-Host Bundles

**Files:**
- Create: `benchmarks/handoff.py`
- Create: `tests/benchmarks/test_handoff.py`
- Create: `tests/benchmarks/test_detached_signatures.py`
- Create: `tests/benchmarks/fixtures/g4-benchmark-receipt-payload.json`
- Create: `tests/benchmarks/fixtures/g4-independent-receipt-payload.json`
- Create: `tests/benchmarks/fixtures/g4-review-handoff.json`
- Create: `tests/benchmarks/fixtures/g4-independent-result.json`

**Interfaces:**
- Produces: `emit_review_handoff(*, subject_path: Path, artifact_manifest_path: Path, selected_artifact_path: Path, source_bundle_path: Path, wheelhouse_path: Path, primary_run_path: Path, reviewer_attestation_path: Path, credential_identity_sha256: str, signing_key_path: Path, output: Path) -> SignedBundle` and `verify_review_handoff(*, bundle_path: Path, reviewer_roles_lock: Path, extraction_root: Path) -> VerifiedHandoff`.
- Produces: `emit_independent_result(*, verified_handoff: VerifiedHandoff, independent_run_path: Path, comparison_path: Path, independent_receipt_attestation_path: Path, reviewer_attestation_path: Path, credential_identity_sha256: str, signing_key_path: Path, output: Path) -> SignedBundle` and `verify_independent_result(*, bundle_path: Path, verified_handoff: VerifiedHandoff, reviewer_roles_lock: Path, extraction_root: Path) -> VerifiedIndependentResult`; the transported attestation is an input to the later registered candidate producer, never `g4-independent-rerun.json`.
- Produces: shared canonical detached-signature verification for both receipt schemas and both transport schemas.
- Defines: frozen `SignedBundle(path: Path, archive_sha256: str, signed_statement_sha256: str)`; frozen `VerifiedHandoff(extraction_root: Path, primary_projection_root: Path, subject_sha256: str, primary_private_tree_sha256: str, member_hashes: dict[str, str], primary_host_identity_sha256: str, primary_credential_identity_sha256: str)`; and frozen `VerifiedIndependentResult(extraction_root: Path, subject_sha256: str, handoff_sha256: str, member_hashes: dict[str, str], independent_host_identity_sha256: str, independent_credential_identity_sha256: str)`.

**Phase 1: Write complete registered domain-candidate payload fixtures**

- [ ] **Step 1.1 (2–5 min): Write/validate the complete primary domain-candidate payload fixture**
- [ ] **Step 1.2 (2–5 min): Write/validate the complete independent domain-candidate payload fixture**

Make `g4-benchmark-receipt-payload.json` and `g4-independent-receipt-payload.json` complete, schema-valid closed domain objects. Each contains `signed_statement`, `signed_statement_sha256`, `signing_key_id`, `signing_public_key_sha256`, `signature_algorithm` equal to `Ed25519`, and canonical-base64 `signature`; no signature field appears inside `signed_statement`. Neither fixture contains generic dependency/material/sealer maps, a final receipt pathname, or a producer-selected output field; product-frozen `gate-candidate.schema.json` wraps this domain payload only for the inherited-handle producer boundary.

**Phase 2: Write complete transport fixtures**

- [ ] **Step 2.1 (2–5 min): Write/validate the complete review handoff fixture**
- [ ] **Step 2.2 (2–5 min): Write/validate the complete independent result fixture**

Make `g4-review-handoff.json` and `g4-independent-result.json` complete and schema-valid with deterministic member manifests, ReleaseSubject/artifact/lock/evaluator hashes, privacy-safe reviewer/host identity, credential-identity digest, and the same six detached fields.

**Phase 3: Add detached-signature mutation tests**

- [ ] **Step 3.1 (2–5 min): Add nested signed-statement byte mutation**
- [ ] **Step 3.2 (2–5 min): Add signed-statement SHA mutation**
- [ ] **Step 3.3 (2–5 min): Add signing-key ID mutation**
- [ ] **Step 3.4 (2–5 min): Add public-key SHA mutation/substitution**
- [ ] **Step 3.5 (2–5 min): Add signature-algorithm mutation**
- [ ] **Step 3.6 (2–5 min): Add signature-byte mutation**
- [ ] **Step 3.7 (2–5 min): Add primary/independent signature-swap mutation**
- [ ] **Step 3.8 (2–5 min): Run every mutation against schema plus crypto checks**

Parameterize all four fixtures. Mutate one nested byte in `signed_statement`, then separately mutate `signed_statement_sha256`, `signing_key_id`, `signing_public_key_sha256`, `signature_algorithm`, and `signature`; substitute a different registered public key; then move a signature between primary and independent schemas. Assert combined schema and cryptographic verification reject every mutation. For the two receipt fixtures specifically, require both their named payload schema and detached verification to run.

**Phase 4: Add separate-host archive attacks**

- [ ] **Step 4.1 (2–5 min): Add unrelated-root/drive host fixtures**
- [ ] **Step 4.2 (2–5 min): Add absolute/symlink/path-escape attacks**
- [ ] **Step 4.3 (2–5 min): Add duplicate/order/missing/extra-member attacks**
- [ ] **Step 4.4 (2–5 min): Add member-hash/copied-output attacks**
- [ ] **Step 4.5 (2–5 min): Add equal-host/equal-credential identity attacks**

Create primary and independent fixture trees with no shared parent, drive, environment path, or checkout. Assert rejection of absolute original-host paths, symlinks, duplicate/member-order tricks, missing or extra members, member hash drift, copied primary output, equal host identity, and equal credential identity.

- [ ] **Step 5 (2–5 min): Observe handoff/signature RED**

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_handoff.py tests/benchmarks/test_detached_signatures.py -q
```

Expected: collection fails because `benchmarks.handoff` does not exist.

**Phase 6: Implement canonical detached signing**

- [ ] **Step 6.1 (2–5 min): Canonicalize/hash only `signed_statement`**
- [ ] **Step 6.2 (2–5 min): Add Ed25519 signing with locked key identity**
- [ ] **Step 6.3 (2–5 min): Add schema/key/hash/signature verification**
- [ ] **Step 6.4 (2–5 min): Add reopen/reverify/atomic-rename transport output**

Canonicalize only `signed_statement`, hash those exact UTF-8 bytes, sign the exact bytes with Ed25519, resolve key ID/public-key hash through `reviewer-roles.lock`, serialize all six fields, reopen, schema-validate, and cryptographically reverify before atomic rename of a transport object. Signing-key paths and private bytes never enter a bundle. This transport helper never receives either registered G4 basename; registered domain candidates are written later only to the generic sealer's inherited exclusive handle.

**Phase 7: Implement the primary handoff**

- [ ] **Step 7.1 (2–5 min): Create exact-commit source Git bundle**
- [ ] **Step 7.2 (2–5 min): Create signed wheelhouse manifest/archive**
- [ ] **Step 7.3 (2–5 min): Create privacy-safe primary result projection**
- [ ] **Step 7.4 (2–5 min): Create freeze snapshot and driver ledger projections**
- [ ] **Step 7.5 (2–5 min): Create non-self-referential member manifest**
- [ ] **Step 7.6 (2–5 min): Sign/package/reopen the handoff archive**

`g4-review-handoff.tar.gz` is the sole signed primary transport and contains exactly `handoff.json`, `source.bundle`, `release-subject.json`, `artifact-manifest.json`, the selected Linux artifact, tracked benchmark locks/schemas/scripts, `benchmark-wheelhouse.tar.zst`, `wheelhouse-manifest.json`, `pre-run-freeze-snapshot.json`, privacy-safe `driver-operation-ledger.json`, `primary-public-projection/`, the primary private result-tree SHA-256, and `member-manifest.json`. `primary-public-projection/` contains the final manifest, scorecard, public-safe core/agent JSONL records, per-repository metrics, redacted transcripts, and private-sidecar hashes required by independent comparison and final reporting; no second primary transport exists. `source.bundle` advertises only the exact ReleaseSubject commit and its reachable tree, not branches or tags. `member-manifest.json` lists every payload member except `handoff.json` and itself; `handoff.json.signed_statement` binds the manifest SHA-256, eliminating self-hash cycles while authenticating every payload byte. The snapshot binds source commit/tree, `refs/tags` digest, artifact hashes, and artifact-manifest hash. The ledger stores phase/verb/argv digest/exit code only, never raw argv. Holdout/evaluator plaintext, credentials, private logs, and absolute paths are forbidden.

**Phase 8: Implement handoff verification**

- [ ] **Step 8.1 (2–5 min): Verify handoff schema/registered key/signature**
- [ ] **Step 8.2 (2–5 min): Verify member allowlist/order/hash set**
- [ ] **Step 8.3 (2–5 min): Reject absolute/symlink/duplicate/escape members**
- [ ] **Step 8.4 (2–5 min): Extract beneath host-local temporary root**
- [ ] **Step 8.5 (2–5 min): Verify source/artifact/evaluator commitments**

Verify the detached primary signature, registered key, source bundle commit/tree, every member hash and allowlist before extraction. Extract into `[IO.Path]::GetTempPath()`/`tempfile.gettempdir()`, verify separately supplied holdout/evaluator bytes against signed commitments, and never dereference a primary-host path.

**Phase 9: Implement the independent result**

- [ ] **Step 9.1 (2–5 min): Project final independent core/agent outputs**
- [ ] **Step 9.2 (2–5 min): Add signed comparison and independent receipt-attestation inputs**
- [ ] **Step 9.3 (2–5 min): Create non-self-referential result member manifest**
- [ ] **Step 9.4 (2–5 min): Bind handoff/evaluator/identity/statistical hashes**
- [ ] **Step 9.5 (2–5 min): Sign/package/reopen the result archive**

`g4-independent-result.tar.gz` contains exactly `independent-result.json`, `independent-comparison.json`, `independent-receipt-attestation.json`, final manifest, scorecard, public-safe core/agent projections, reviewer/host attestation, and `member-manifest.json`. It never contains the registered final `g4-independent-rerun.json`. The manifest lists every payload member except `independent-result.json` and itself; the result statement binds the manifest SHA-256, handoff hash, different host and credential identity digests, evaluator verification digest, and exact permutation/Holm reproduction. The signed independent receipt attestation binds the same payload-member hashes but never the result envelope or final archive hash, so no statement hashes itself directly or transitively; after return, the product-frozen registered producer verifies this attestation and emits its domain candidate through the sealer-owned inherited handle.

- [ ] **Step 10 (2–5 min): Run handoff/signature GREEN**

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_handoff.py tests/benchmarks/test_detached_signatures.py -q
git diff --check
```

- [ ] **Step 11 (2–5 min): Commit only signed-bundle files**

```powershell
$expectedStaged = @('benchmarks/handoff.py','tests/benchmarks/test_handoff.py','tests/benchmarks/test_detached_signatures.py','tests/benchmarks/fixtures/g4-benchmark-receipt-payload.json','tests/benchmarks/fixtures/g4-independent-receipt-payload.json','tests/benchmarks/fixtures/g4-review-handoff.json','tests/benchmarks/fixtures/g4-independent-result.json')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'bench: add signed cross-host evidence bundles'
```

### Task G4.8C: Add the Sole Orchestrator, Reports, and Receipts

**Dependencies:** G0 exact-task-commit helper/tests. This source-changing pre-freeze task defines the exact future registry/launch-interface constants and candidate-handle behavior without requiring G5's not-yet-frozen runtime registry; after these producer bytes are committed, G5 registers their actual digests and the post-freeze runbook performs authoritative product-frozen integration.

**Files:**
- Create: `benchmarks/orchestrate.py`
- Create: `benchmarks/report.py`
- Create: `benchmarks/independent_verify.py`
- Create: `tests/benchmarks/test_orchestrate.py`
- Create: `tests/benchmarks/test_report.py`
- Create: `tests/benchmarks/test_independent_verify.py`

**Interfaces:**
- Produces: `orchestrate_run(config: OrchestratorConfig) -> Path`, the only scored entry point.
- Produces: `bundle_raw_results(primary_run: Path, independent_run: Path, output: Path) -> str` and `bundle_directory(source_dir: Path, output: Path) -> str`.
- Produces: `build_report(*, subject_path: Path, run_dir: Path, scorecard_path: Path, archive_path: Path, comparison_path: Path, reviewer_id: str, output: Path) -> None`.
- Produces: `emit_primary_receipt(*, subject_path: Path, run_dir: Path, scorecard_path: Path, report_path: Path, archive_path: Path, comparison_path: Path, reviewer_attestation_path: Path, reviewer_id: str, signing_key_path: Path, candidate_handle: BinaryIO) -> None`; the handle is inherited from `release_gate.py produce-and-seal`, never selected by a path argument.
- Produces: `compare_independent(*, subject_path: Path, primary_scorecard: Path, primary_manifest: Path, primary_agent: Path, primary_attestation: Path, rerun_scorecard: Path, rerun_manifest: Path, rerun_agent: Path, rerun_attestation: Path, resources_lock: Path, evaluator_commitment: Path, reviewer_id: str, signing_key_path: Path, output: Path) -> dict[str, object]`.
- Produces: `emit_independent_receipt(*, subject_path: Path, verified_independent_result: Path, comparison_path: Path, reviewer_attestation_path: Path, candidate_handle: BinaryIO) -> None`; it verifies the physically distinct reviewer's transported signature and writes only the domain candidate to the inherited handle, with no local signing key or output pathname.
- Produces: `release_holdout(*, subject_path: Path, external_dir: Path, output_dir: Path, scorecard_path: Path, primary_receipt_path: Path, independent_receipt_path: Path, reviewer_id: str) -> dict[str, object]`.
- Produces: `emit_public_assets_manifest(subject_path: Path, product_artifact_manifest: Path, assets: Sequence[PublicAsset], output: Path) -> None`.
- Defines: frozen `PublicAsset(role: str, source_path: str, destination_filename: str, media_type: str, size_bytes: int, sha256: str, privacy_audit: Literal["pass"])`; and frozen `OrchestratorConfig(path_roots: Path, subject_path: Path, artifact_manifest_path: Path, selected_artifact_path: Path, corpus_lock: Path, competitor_lock: Path, capability_lock: Path, image_digests: Path, product_runtime_lock: Path, resources_lock: Path, reviewer_roles_lock: Path, reviewer_attestation: Path, tasks_lock: Path, model_lock: Path, broker_lock: Path, pricing_lock: Path, pricing_evidence_root: Path, evaluator_commitment: Path, evaluator_verification: Path, evaluator_root: Path, holdout_dir: Path, credential_handle: CredentialHandle, reviewer_id: str, run_id: str, split: Literal["holdout"], output_root: Path)`; neither type admits a free-form command, raw credential, or host path in public serialization.

**Phase 1: Add orchestrator failpoint tests**

- [ ] **Step 1.1 (2–5 min): Add ReleaseSubject/artifact/lock preflight failures**
- [ ] **Step 1.2 (2–5 min): Add evaluator-order/identity/signature failures**
- [ ] **Step 1.3 (2–5 min): Add core-phase failpoint and no-manifest assertion**
- [ ] **Step 1.4 (2–5 min): Add agent-phase failpoint and no-manifest assertion**
- [ ] **Step 1.5 (2–5 min): Add missing-pair/result-tree mutation failures**
- [ ] **Step 1.6 (2–5 min): Add exactly-once atomic finalization assertion**

Assert no `run-manifest.json` exists after any core/agent failure, missing required pair, selected-artifact mismatch, evaluator verification created after the run nonce, duplicate credential identity, or bad reviewer/resource/evaluator signature. Assert exactly one atomic finalization after both sealed result-tree digests exist.

**Phase 2: Add deterministic archive/report tests**

- [ ] **Step 2.1 (2–5 min): Add sorted-member and metadata assertions**
- [ ] **Step 2.2 (2–5 min): Add byte-identical tar/gzip assertion**
- [ ] **Step 2.3 (2–5 min): Add symlink/path/duplicate-member rejection**
- [ ] **Step 2.4 (2–5 min): Add missing/changed archive rejection**
- [ ] **Step 2.5 (2–5 min): Add partial-run/free-form-claim rejection**

Assert byte-identical repeated archives with sorted POSIX members, uid/gid `0`, empty uname/gname, modes `0644`/`0755`, mtime `0`, gzip filename empty and mtime `0`; reject symlinks, path escape, missing archive, changed archive, partial run, and unregistered free-form claims.

**Phase 3: Add privacy-adversarial report tests**

- [ ] **Step 3.1 (2–5 min): Add credential/home/user/host/email sentinels**
- [ ] **Step 3.2 (2–5 min): Add remote/cloud/MAC/transcript sentinels**
- [ ] **Step 3.3 (2–5 min): Add slash-normalized/JSON/URL encodings**
- [ ] **Step 3.4 (2–5 min): Add base64/nested JSONL/archive encodings**
- [ ] **Step 3.5 (2–5 min): Assert rejection leaves no partial output**

Inject API-key, Windows/Linux home, username, hostname, email, credentialed remote URL, cloud instance ID, MAC address, unredacted transcript, and raw-provider-request markers into every structured string and nested JSONL/archive field. Test raw, slash-normalized, JSON-escaped, URL-encoded, and base64 forms; failure leaves no partial public output.

**Phase 4: Add independent-comparison tests**

- [ ] **Step 4.1 (2–5 min): Add subject/artifact/protocol lock mismatch cases**
- [ ] **Step 4.2 (2–5 min): Add result/evaluator/correctness mismatch cases**
- [ ] **Step 4.3 (2–5 min): Add required core/no-tool pair omission cases**
- [ ] **Step 4.4 (2–5 min): Add reviewer/host/process/credential equality cases**
- [ ] **Step 4.5 (2–5 min): Add nonportable-resource inconclusive case**
- [ ] **Step 4.6 (2–5 min): Add same-host receipt rejection**

Assert the two runs bind the same ReleaseSubject/artifact and all protocol/corpus/competitor/capability/image/product-runtime/resource/holdout/runner/task/model/broker/pricing/evaluator hashes; rerun all core and `no_tool_control` pairs; require different host, reviewer, process nonce, and credential identity; cap resource mismatch at `inconclusive`; reject every same-host receipt.

**Phase 5: Add receipt and gate-scoped registry tests**

- [ ] **Step 5.1 (2–5 min): Assert both exact G4 payload-schema paths**
- [ ] **Step 5.2 (2–5 min): Add typed receipt field mutation cases**
- [ ] **Step 5.3 (2–5 min): Spy on `--gate G4` schema selection**
- [ ] **Step 5.4 (2–5 min): Prove later-gate schemas are untouched**
- [ ] **Step 5.5 (2–5 min): Require inherited-exclusive-handle transport for both G4 launch specs**
- [ ] **Step 5.6 (2–5 min): Reject final `--out`, registered path, delete, replace, rename, stdout candidate, or second writer**

Declare one exact G4 registry/launch contract constant in the tests: the two rows name `benchmarks/schema/g4-benchmark-receipt.schema.json` and `benchmarks/schema/g4-independent-receipt.schema.json`, resolve only `benchmarks.report emit-primary` and `benchmarks.independent_verify emit-receipt`, and set `candidate_transport=inherited_exclusive_handle`. The source tests validate synthetic documents built from that constant against the closed schemas and export the same expected tuples for G5's later real-registry equality test; they do not require or create a pre-freeze runtime registry. Static and process tests require that both domain producers can write only one gate-candidate to the inherited exclusive handle and cannot name, create, delete, replace, rename, or print either registered final receipt. The post-freeze finalizer then proves the product-frozen real registry/launch policy equals this contract before either producer starts.

- [ ] **Step 6 (2–5 min): Observe orchestrator/report RED**

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_orchestrate.py tests/benchmarks/test_report.py tests/benchmarks/test_independent_verify.py -q
```

Expected: collection fails because `benchmarks.orchestrate`, `benchmarks.report`, and `benchmarks.independent_verify` do not exist.

**Phase 7: Implement atomic core-plus-agent orchestration**

- [ ] **Step 7.1 (2–5 min): Validate ReleaseSubject artifact/runtime inputs**
- [ ] **Step 7.2 (2–5 min): Validate all benchmark/reviewer/evaluator locks**
- [ ] **Step 7.3 (2–5 min): Create the run nonce after preflight**
- [ ] **Step 7.4 (2–5 min): Run and seal the complete core matrix**
- [ ] **Step 7.5 (2–5 min): Run and seal all no-tool-control pairs**
- [ ] **Step 7.6 (2–5 min): Validate the required-baseline failure ledger**
- [ ] **Step 7.7 (2–5 min): Atomically finalize once or leave no manifest**

`orchestrate run` validates the ReleaseSubject-selected `x86_64-unknown-linux-gnu` artifact and every corpus/competitor/capability/image/product-runtime/resource/task/model/broker/pricing/evaluator/reviewer lock/signature before creating the run nonce. It runs the complete core matrix, seals `core-results.json`, runs only `with_codesextant` versus `no_tool_control`, seals `agent/results.json`, checks the required-baseline ledger, then atomically calls final-manifest creation exactly once. A failure retains private diagnostics but no final manifest.

**Phase 8: Implement family-scoped report rendering**

- [ ] **Step 8.1 (2–5 min): Render exact raw p-value/null/pair/tie metadata**
- [ ] **Step 8.2 (2–5 min): Render core-family Holm results**
- [ ] **Step 8.3 (2–5 min): Render four no-tool-control Holm results**
- [ ] **Step 8.4 (2–5 min): Render workload competitors as `not_evaluated`**
- [ ] **Step 8.5 (2–5 min): Enforce scoped core-only SOTA template**

`build_report` consumes only a final scorecard. It renders exact one-sided paired sign-permutation raw p-values with null, alternative, wins, nonzero denominator, total pairs, reported/excluded ties, `seed=20260723`, and `rng_used=false`. It renders Holm adjustments separately for `core_required_baselines` and exactly four `agent_no_tool_control` hypotheses. Aider, Serena, and Codebase Memory MCP appear as workload-capable `not_evaluated` agent rows with no denominator, win, comparative prose, or inferred hypothesis.

**Phase 9: Implement deterministic public-safe archives**

- [ ] **Step 9.1 (2–5 min): Project primary allowlisted public records**
- [ ] **Step 9.2 (2–5 min): Project independent allowlisted public records**
- [ ] **Step 9.3 (2–5 min): Normalize roots and run privacy audit**
- [ ] **Step 9.4 (2–5 min): Emit canonical tar members/metadata**
- [ ] **Step 9.5 (2–5 min): Emit canonical gzip wrapper and final SHA**
- [ ] **Step 9.6 (2–5 min): Apply identical rules to released holdout**

`bundle_raw_results` projects allowlisted manifests, JSONL observations, scorecards, per-repository metrics, hashes of private sidecars, agent results, and redacted transcripts under fixed `primary/` and `independent/` prefixes. It excludes credentials, raw provider requests, private sidecar bytes, environments, and non-allowlisted files; normalizes root markers; runs the privacy audit before packing; and applies the canonical tar/gzip metadata tested in Step 2. `bundle_directory` applies the same rules to released holdout bytes.

**Phase 10: Implement strict independent comparison**

- [ ] **Step 10.1 (2–5 min): Compare subject/artifact/lock digests**
- [ ] **Step 10.2 (2–5 min): Compare result trees/pair sets/correctness digests**
- [ ] **Step 10.3 (2–5 min): Verify reviewer/signature/identity separation**
- [ ] **Step 10.4 (2–5 min): Recompute statistical families**
- [ ] **Step 10.5 (2–5 min): Apply resource portability verdict**
- [ ] **Step 10.6 (2–5 min): Emit signed comparison atomically**

`compare_independent` rejects any ReleaseSubject/artifact/lock/result/ground-truth/evaluator mismatch, required pair omission, invalid signature, same reviewer/host/process/credential identity, nonmatching correctness digest, or copied result. A physically distinct host that misses `resources.lock` may record correctness-only evidence but forces performance `nonportable`, overall `inconclusive`, and no SOTA wording; it cannot issue the independent pass receipt.

**Phase 11: Implement handle-only registered domain-candidate emitters**

- [ ] **Step 11.1 (2–5 min): Build primary signed domain candidate**
- [ ] **Step 11.2 (2–5 min): Write/reopen payload-schema-verify primary candidate through inherited handle**
- [ ] **Step 11.3 (2–5 min): Verify independent transported attestation without cycles**
- [ ] **Step 11.4 (2–5 min): Write/reopen payload-schema-verify independent candidate through inherited handle**
- [ ] **Step 11.5 (2–5 min): Assert exact producer IDs, inherited handle, and zero final-path operations**

`emit_primary_receipt` is the registered `benchmarks.report emit-primary` domain producer; `emit_independent_receipt` is the registered `benchmarks.independent_verify emit-receipt` domain producer. Each receives only the anonymous/delete-on-close inherited exclusive candidate handle retained by product-frozen `release_gate.py produce-and-seal`, places claims only in `payload.signed_statement`, writes the other detached domain fields beside it, flushes/reopens through that same handle, cryptographically and payload-schema verifies the candidate bytes, and returns without any final output pathname. The independent producer runs on the coordinator only after it verifies the physically distinct host's signed result bundle and `independent-receipt-attestation.json`; it accepts no local independent signing key. Neither producer accepts `--out`, a registered basename, path-like candidate argument, delete/replace/rename control, stdout candidate, or a second writer. Only the generic sealer adds dependency/material maps and `sealed_by`, validates the exact G4 registry/launch-policy row, and atomically create-new writes `g4-benchmark.json` or `g4-independent-rerun.json`. The independent statement binds the primary handoff hash, non-envelope independent payload-member hashes, both final manifests/result trees/scorecards, `no_tool_control` pairs, exact permutation/Holm reproduction, distinct identities, comparison, commands, and tool versions; it does not bind the result envelope, member manifest, or final archive hash.

**Phase 12: Implement staged public assets**

- [ ] **Step 12.1 (2–5 min): Gate holdout release on both pass receipts**
- [ ] **Step 12.2 (2–5 min): Byte-match released holdout to commitment**
- [ ] **Step 12.3 (2–5 min): Validate exact six ancillary asset inputs**
- [ ] **Step 12.4 (2–5 min): Privacy-audit and hash each asset**
- [ ] **Step 12.5 (2–5 min): Emit canonical non-self-listed manifest**

`release_holdout` requires both valid pass receipts and byte-matches the pre-score commitment. `emit_public_assets_manifest` accepts exactly `BENCHMARKS.md`, `raw-results.tar.gz`, `holdout-ground-truth.tar.gz`, `independent-comparison.json`, `g4-benchmark.json`, and `g4-independent-rerun.json`. It emits canonical sorted JSON fields `format_version`, `subject_sha256`, `artifact_manifest_sha256`, and `assets`; each asset has role, repository-relative source path, unique destination filename, media type, size, SHA-256, and `privacy_audit="pass"`. `g4-public-assets.json` is not self-listed and never mutates the frozen G5 artifact manifest.

- [ ] **Step 13 (2–5 min): Run orchestrator/report GREEN**

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_orchestrate.py tests/benchmarks/test_report.py tests/benchmarks/test_independent_verify.py -q
git diff --check
```

Expected: tests pass; the synthetic closed registry/launch documents validate only the two G4 rows/specs and both typed payload schemas, and a later-gate schema can be absent. Authoritative real-registry equality is intentionally deferred until G5 has frozen actual producer digests.

- [ ] **Step 14 (2–5 min): Commit only orchestrator/report source and tests**

```powershell
$expectedStaged = @('benchmarks/orchestrate.py','benchmarks/report.py','benchmarks/independent_verify.py','tests/benchmarks/test_orchestrate.py','tests/benchmarks/test_report.py','tests/benchmarks/test_independent_verify.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'bench: add deterministic G4 evidence producers'
```

### Task G4.8D: Wire and Verify the Four Operational Drivers

This is the last source-changing G4 task. Complete and commit it before G5 creates the final ReleaseSubject. It must not execute the scored holdout or emit a final receipt during development.

**Files:**
- Modify: `.gitignore`
- Create: `release/g4/prepare-evaluator.ps1`
- Create: `release/g4/run-primary.ps1`
- Create: `release/g4/run-independent.ps1`
- Create: `release/g4/finalize.ps1`
- Create: `tests/benchmarks/test_cli_contracts.py`
- Create: `tests/benchmarks/test_powershell_drivers.py`

**Interfaces:**
- `prepare-evaluator.ps1` atomically emits detached-signed evaluator commitment and verification paths before any run nonce.
- `run-primary.ps1` emits the one JSON path `review_handoff` for detached-signed `g4-review-handoff.tar.gz`; that handoff contains the allowlisted primary result projection and private tree digest, and no second primary bundle is defined or accepted.
- `run-independent.ps1` consumes only the verified portable handoff plus independent secure roots/credential handle and emits a detached-signed independent result bundle containing an external receipt attestation but no registered final receipt.
- `finalize.ps1` accepts `Finalize`, `VerifyForG7`, or `VerifyFreeze`; each mode is read/write constrained by its contract and returns machine-readable JSON. `Finalize` is the only coordinator path that asks product-frozen `tools/release_gate.py produce-and-seal` to create the two registered G4 receipts; `VerifyForG7` uses `check-receipt` for both.
- Only these four drivers may invoke scored/evidence CLIs; every native executable is invoked through the tested `Invoke-Native` function.

**Phase 1: Add exact CLI parser contracts**

- [ ] **Step 1.1 (2–5 min): Assert evaluator commit/verify flags**
- [ ] **Step 1.2 (2–5 min): Assert orchestrate/score flags**
- [ ] **Step 1.3 (2–5 min): Assert handoff/result emit/verify flags**
- [ ] **Step 1.4 (2–5 min): Assert comparison/candidate and generic-sealer flags**
- [ ] **Step 1.5 (2–5 min): Assert holdout/archive/report/assets flags**
- [ ] **Step 1.6 (2–5 min): Assert domain/registry/gate flags**
- [ ] **Step 1.7 (2–5 min): Reject positional paths/unknown/ignored flags**
- [ ] **Step 1.8 (2–5 min): Require `--path-roots` on path-bearing scored CLIs**

Parse each real module parser and assert the exact flags used by the four drivers for evaluator commit/verify, orchestrate run, handoff/result emit/verify, score, independent comparison/attestation, holdout release, archive/report/public-assets emission, `report verify-domain`, and product-frozen gate `validate-registry`/`validate-launch-policy`/`produce-and-seal`/`check-receipt`/`check`. Reject positional path aliases, unknown flags, ignored extras, domain-producer `--out`/final-path/delete/replace/rename options, and any path-bearing scored call without `--path-roots`.

**Phase 2: Add four-driver AST policy tests**

- [ ] **Step 2.1 (2–5 min): Parse/assert `prepare-evaluator.ps1` policy**
- [ ] **Step 2.2 (2–5 min): Parse/assert `run-primary.ps1` policy**
- [ ] **Step 2.3 (2–5 min): Parse/assert `run-independent.ps1` policy**
- [ ] **Step 2.4 (2–5 min): Parse/assert `finalize.ps1` policy**
- [ ] **Step 2.5 (2–5 min): Parse/assert `Invoke-Native.ps1` policy**
- [ ] **Step 2.6 (2–5 min): Reject every direct native call outside wrapper**
- [ ] **Step 2.7 (2–5 min): Require exact two-receipt generic-sealer dispatch and complete VerificationContext**

Parse all four scripts plus `Invoke-Native.ps1`. Require `#requires -Version 7.4`, `$PSNativeCommandUseErrorActionPreference = $true`, one resolved dot-source of `Invoke-Native.ps1`, and `Get-Command` resolution. Reject direct invocation of `git`, `uv`, `python`, `pwsh`, `cosign`, or any native executable outside the wrapper. For `finalize.ps1`, assert exact basename equality `{g4-benchmark.json,g4-independent-rerun.json}`; absent→`produce-and-seal`, existing→`check-receipt`; both receive the same explicit subject/product-source/public-export/evidence/release-assets/index/bundle/signing/bootstrap/registry/launch-policy arguments; `VerifyForG7` calls `check-receipt` for both plus gate `check`; and no code path opens either final basename for write, copies it, deletes it, replaces it, renames it, accepts a final path override, or launches a domain producer directly.

**Phase 3: Add native failure-path tests**

- [ ] **Step 3.1 (2–5 min): Add custodian-driver exit-17 case**
- [ ] **Step 3.2 (2–5 min): Add primary-driver exit-17 case**
- [ ] **Step 3.3 (2–5 min): Add independent-driver exit-17 case**
- [ ] **Step 3.4 (2–5 min): Add finalizer exit-17 case**
- [ ] **Step 3.5 (2–5 min): Assert redacted diagnostic and no next sentinel**
- [ ] **Step 3.6 (2–5 min): Add malformed/truncated JSON stdout cases**
- [ ] **Step 3.7 (2–5 min): Add unexpected-empty scalar cases**

For each driver phase, inject the fake native program that writes stdout/stderr and exits `17`. Assert immediate termination, preserved private diagnostic receipt, and absence of the next phase's sentinel. Add malformed/truncated JSON stdout and unexpected-empty scalar cases.

**Phase 4: Add frozen-environment argv tests**

- [ ] **Step 4.1 (2–5 min): Require frozen/no-sync on every `uv run`**
- [ ] **Step 4.2 (2–5 min): Allow frozen/offline sync only before independent nonce**
- [ ] **Step 4.3 (2–5 min): Reject post-nonce sync/network resolution**
- [ ] **Step 4.4 (2–5 min): Reject implicit environment creation**

Assert every `uv run` argv has `--frozen` and `--no-sync`. Assert the independent driver alone may call `uv sync --frozen --offline`, only before it creates the run nonce; all scored/evidence phases reject sync, network resolution, or implicit environment creation.

**Phase 5: Add physically separate-host integration fixtures**

- [ ] **Step 5.1 (2–5 min): Create unrelated primary/independent roots**
- [ ] **Step 5.2 (2–5 min): Add distinct host/reviewer/process/credential fixtures**
- [ ] **Step 5.3 (2–5 min): Run signed handoff fixture round trip**
- [ ] **Step 5.4 (2–5 min): Run signed result fixture return trip**
- [ ] **Step 5.5 (2–5 min): Reject transferred absolute paths**
- [ ] **Step 5.6 (2–5 min): Reject same-host receipt-attestation/candidate/pass/SOTA output**

Run the primary and independent fixtures under unrelated root trees and synthetic host identities. Assert the signed handoff/result round trip succeeds only with distinct host/reviewer/process/credential identities and no transferred absolute path. A same-host diagnostic may write private diagnostics but cannot produce the independent receipt attestation, registered candidate, final receipt, or a pass/SOTA verdict.

- [ ] **Step 6 (2–5 min): Observe driver RED**

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_cli_contracts.py tests/benchmarks/test_powershell_drivers.py -q
```

Expected: collection fails because the four operational drivers do not exist.

**Phase 7: Implement the custodian driver**

- [ ] **Step 7.1 (2–5 min): Add the typed parameter block and 7.4/native bootstrap**
- [ ] **Step 7.2 (2–5 min): Resolve evaluator/output/signing roots under their allowlists**
- [ ] **Step 7.3 (2–5 min): Invoke `commit-evaluator` through `Invoke-Native`**
- [ ] **Step 7.4 (2–5 min): Reopen and verify commitment/signature/tree hashes**
- [ ] **Step 7.5 (2–5 min): Enforce verification before any run nonce**
- [ ] **Step 7.6 (2–5 min): Emit exact two-property JSON or a redacted diagnostic**

`prepare-evaluator.ps1` resolves confined evaluator/signing roots, invokes `commit_evaluator`, reopens and verifies the commitment and `evaluator-verification.json`, requires `verified_before_run_nonce=true`, and prints only their JSON paths. It never receives a provider handle and never copies evaluator plaintext into a transport/public bundle.

**Phase 8: Implement the primary driver**

- [ ] **Step 8.1 (2–5 min): Add typed parameters and the 7.4/native bootstrap**
- [ ] **Step 8.2 (2–5 min): Reject nonempty tracked/staged status**
- [ ] **Step 8.3 (2–5 min): Snapshot commit/tree/tag/artifact/manifest digests**
- [ ] **Step 8.4 (2–5 min): Verify ReleaseSubject-selected artifact/runtime**
- [ ] **Step 8.5 (2–5 min): Verify corpus/capability/resource/reviewer locks**
- [ ] **Step 8.6 (2–5 min): Verify pre-nonce evaluator commitment/receipt**
- [ ] **Step 8.7 (2–5 min): Validate opaque broker handle and identity digest**
- [ ] **Step 8.8 (2–5 min): Invoke the sole orchestrator with frozen/no-sync argv**
- [ ] **Step 8.9 (2–5 min): Score only the atomically final run manifest**
- [ ] **Step 8.10 (2–5 min): Build the primary public-safe result projection**
- [ ] **Step 8.11 (2–5 min): Emit and reverify the signed review handoff**
- [ ] **Step 8.12 (2–5 min): Emit one-property success JSON or redacted diagnostic**

`run-primary.ps1` verifies clean tracked state, frozen ReleaseSubject/artifact bytes, locks, resource/reviewer attestations, pre-score evaluator verification, and the opaque primary credential handle. It runs the one orchestrator with `uv run --frozen --no-sync`, scores final output, emits the sole signed review handoff containing the primary public-safe projection/private tree digest, and prints only `{"review_handoff":"absolute-local-path"}`. Broker resolution is the only place allowed to see provider secret bytes.

**Phase 9: Implement the independent driver**

- [ ] **Step 9.1 (2–5 min): Add typed parameters and the 7.4/native bootstrap**
- [ ] **Step 9.2 (2–5 min): Verify handoff schema, key, signature, and manifest hash**
- [ ] **Step 9.3 (2–5 min): Verify every allowlisted member before extraction**
- [ ] **Step 9.4 (2–5 min): Extract below the OS-reported temporary root**
- [ ] **Step 9.5 (2–5 min): Clone only the signed commit from `source.bundle`**
- [ ] **Step 9.6 (2–5 min): Prove checkout tree and import path**
- [ ] **Step 9.7 (2–5 min): Verify local holdout/evaluator bytes against commitments**
- [ ] **Step 9.8 (2–5 min): Verify distinct host/reviewer/process/credential identities**
- [ ] **Step 9.9 (2–5 min): Provision from signed wheelhouse with frozen/offline sync**
- [ ] **Step 9.10 (2–5 min): Create the run nonce and disable all later sync/network resolution**
- [ ] **Step 9.11 (2–5 min): Invoke the sole orchestrator with frozen/no-sync argv**
- [ ] **Step 9.12 (2–5 min): Score only the independent final manifest**
- [ ] **Step 9.13 (2–5 min): Compare primary projection with independent results**
- [ ] **Step 9.14 (2–5 min): Emit and reverify the signed independent receipt attestation**
- [ ] **Step 9.15 (2–5 min): Emit and reverify the signed independent result bundle**
- [ ] **Step 9.16 (2–5 min): Emit one-property success JSON or redacted diagnostic**

`run-independent.ps1` verifies the handoff signature/member manifest before extraction, creates a clone from `source.bundle` below `[IO.Path]::GetTempPath()`, proves source commit/tree and `benchmarks.__file__`, verifies independent holdout/evaluator inputs, host/resource/reviewer identity, and a distinct credential-identity digest. Before the nonce it provisions only from the signed wheelhouse with `uv sync --frozen --offline`; after the nonce it uses only `uv run --frozen --no-sync`. It runs, scores, compares, emits the signed independent receipt attestation plus result bundle, and prints only the result-bundle path. It never invokes a registered receipt producer and never creates `g4-independent-rerun.json`.

**Phase 10: Implement finalization mode**

- [ ] **Step 10.1 (2–5 min): Add exact `Finalize` parameter/allowed-output contract**
- [ ] **Step 10.2 (2–5 min): Verify/extract the review handoff locally**
- [ ] **Step 10.3 (2–5 min): Verify/extract the independent result locally**
- [ ] **Step 10.4 (2–5 min): Recheck subject/artifact/lock/identity equality**
- [ ] **Step 10.5 (2–5 min): Recompute raw p-values and both Holm families**
- [ ] **Step 10.6 (2–5 min): Verify independent comparison before archive creation**
- [ ] **Step 10.7 (2–5 min): Build deterministic raw archive before report creation**
- [ ] **Step 10.8 (2–5 min): Build the scoped report from verified structures**
- [ ] **Step 10.9 (2–5 min): Use product-frozen `produce-and-seal`/`check-receipt` for the primary receipt**
- [ ] **Step 10.10 (2–5 min): Use product-frozen `produce-and-seal`/`check-receipt` for the independent receipt**
- [ ] **Step 10.11 (2–5 min): Release holdout only after both pass receipts**
- [ ] **Step 10.12 (2–5 min): Build holdout archive and privacy-audit all assets**
- [ ] **Step 10.13 (2–5 min): Emit/reverify `g4-public-assets.json`**
- [ ] **Step 10.14 (2–5 min): Emit exact finalization JSON or redacted diagnostic**

`finalize.ps1 -Mode Finalize` verifies both bundles/signatures/member hashes without dereferencing independent paths, confirms separate Holm families and exact raw p-value metadata, and builds comparison before archive and archive before registered receipts. It requires `$ReleasePython` to equal the absolute hash-locked interpreter previously returned by product-frozen `tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python`; an ambient Python or benchmark environment cannot execute the generic sealer. It constructs one closed `$gateContext` from explicit `--subject`, `--product-source-root`, `--public-export-root`, `--evidence-dir`, `--release-assets-root`, `--release-index`, `--release-index-bundle`, `--signing-policy`, `--verifier-bootstrap`, `--registry`, and `--launch-policy` values supplied by authenticated parameters; none defaults to CWD, environment inference, another authority, or a receipt path. For each exact basename `g4-benchmark.json` and `g4-independent-rerun.json`, absent state invokes the product-frozen `tools/release_gate.py produce-and-seal --gate G4 --receipt <basename> @gateContext -- <explicit domain inputs>` and existing state invokes `check-receipt` with the same context. No driver copies, deletes, replaces, or renames a registered receipt. Only after both generic-sealer receipts check successfully does finalization release committed holdout bytes, run the privacy audit, and emit the seven staged artifacts from R4.

The finalizer implements that dispatch literally through `Invoke-Native`; `$primaryProducerArgs` and `$independentProducerArgs` are closed arrays built from the typed parameters named in Task G4.8C, never caller-supplied free-form argv:

```powershell
$releaseGatePath = Join-Path $ProductSourceRoot 'tools\release_gate.py'
$gateContext = @(
  '--subject', (Join-Path $EvidenceRoot 'release-subject.json'),
  '--product-source-root', $ProductSourceRoot,
  '--public-export-root', $PublicExportRoot,
  '--evidence-dir', $EvidenceRoot,
  '--release-assets-root', $ReleaseAssetRoot,
  '--release-index', $ReleaseIndex,
  '--release-index-bundle', $ReleaseIndexBundle,
  '--signing-policy', $SigningPolicy,
  '--verifier-bootstrap', $VerifierBootstrap,
  '--registry', $ReceiptRegistry,
  '--launch-policy', $ProducerLaunchPolicy
)
$gateBase = @($releaseGatePath)
function Invoke-G4RegisteredReceipt {
  param([Parameter(Mandatory)][ValidateSet('g4-benchmark.json','g4-independent-rerun.json')][string]$Receipt,
        [Parameter(Mandatory)][string[]]$ProducerArgs)
  $finalPath = Join-Path $EvidenceRoot $Receipt
  if (Test-Path -LiteralPath $finalPath -PathType Leaf) {
    Invoke-Native -FilePath $ReleasePython -ArgumentList ($gateBase + @('check-receipt','--gate','G4','--receipt',$Receipt) + $gateContext) | Out-Null
    return
  }
  Invoke-Native -FilePath $ReleasePython -ArgumentList ($gateBase + @('produce-and-seal','--gate','G4','--receipt',$Receipt) + $gateContext + @('--') + $ProducerArgs) | Out-Null
  Invoke-Native -FilePath $ReleasePython -ArgumentList ($gateBase + @('check-receipt','--gate','G4','--receipt',$Receipt) + $gateContext) | Out-Null
}
Invoke-G4RegisteredReceipt -Receipt 'g4-benchmark.json' -ProducerArgs $primaryProducerArgs
Invoke-G4RegisteredReceipt -Receipt 'g4-independent-rerun.json' -ProducerArgs $independentProducerArgs
```

**Phase 11: Implement G7 verification mode**

- [ ] **Step 11.1 (2–5 min): Add the read-only `VerifyForG7` mode contract**
- [ ] **Step 11.2 (2–5 min): Invoke `report verify-domain` frozen/no-sync**
- [ ] **Step 11.3 (2–5 min): Invoke gate-scoped payload registry validation**
- [ ] **Step 11.4 (2–5 min): Invoke the G4 gate check**
- [ ] **Step 11.5 (2–5 min): Rehash staged manifest/assets and emit verification JSON**

`finalize.ps1 -Mode VerifyForG7` invokes through `Invoke-Native`: `uv run --frozen --no-sync --project benchmarks python -m benchmarks.report verify-domain`; product-frozen `tools/release_gate.py validate-registry --gate G4 --require-payload-schemas`; `validate-launch-policy --gate G4 --require-entrypoint-digests`; exact `check-receipt --gate G4 --receipt g4-benchmark.json`; exact `check-receipt --gate G4 --receipt g4-independent-rerun.json`; and `check --gate G4`. Every gate command receives the same explicit closed VerificationContext roots and policy/index arguments described in Finalize. It rehashes both receipts and all staged assets and validates no unrelated later-gate schema.

**Phase 12: Implement freeze verification mode**

- [ ] **Step 12.1 (2–5 min): Add the read-only `VerifyFreeze` mode contract**
- [ ] **Step 12.2 (2–5 min): Compare commit/tree/tag snapshot digests**
- [ ] **Step 12.3 (2–5 min): Compare artifact/manifest snapshot digests**
- [ ] **Step 12.4 (2–5 min): Require empty tracked/staged status**
- [ ] **Step 12.5 (2–5 min): Verify output ignore/receipt policy**
- [ ] **Step 12.6 (2–5 min): Reject forbidden driver-ledger verbs**
- [ ] **Step 12.7 (2–5 min): Emit read-only freeze-verification JSON**

`finalize.ps1 -Mode VerifyFreeze` compares current source commit/tree, `refs/tags` digest, ReleaseSubject artifact hashes, and artifact-manifest hash with the signed pre-run snapshot in the verified review handoff; requires empty tracked/staged status; verifies post-freeze outputs are ignored or registered receipts; and checks the append-only four-driver operation ledger contains no commit/tag/rebuild/upload/visibility verb. It proves the controlled G4 workflow did not perform those operations and performs no repair.

- [ ] **Step 13 (2–5 min): Add the exact ignore policy**

Add these patterns before the final freeze:

```gitignore
release/staging/g4/
benchmarks/ground_truth/holdout/
```

G5 owns `release/evidence/.gitignore`, including exactly the two G4 receipts. Raw runs remain below the existing ignored `.benchmark-cache/`; no report, scorecard, archive, released holdout, or receipt is tracked.

- [ ] **Step 14 (2–5 min): Run focused driver GREEN**

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks/test_cli_contracts.py tests/benchmarks/test_powershell_drivers.py tests/benchmarks/test_path_confinement.py tests/benchmarks/test_handoff.py tests/benchmarks/test_detached_signatures.py -q
```

Expected: PowerShell AST/parser/exit-17 tests pass; every documented driver invocation matches its Python parser; distinct-host handoff/result fixtures pass; same-host, reused credential, malformed signature, nonzero native exit, unpinned run, or non-gate-scoped validation fails.

- [ ] **Step 15 (2–5 min): Run a development-only fixture pilot**

```powershell
uv run --frozen --no-sync --project benchmarks python -m benchmarks.orchestrate fixture --resources-lock benchmarks/resources.lock.json --capability-lock benchmarks/capabilities.lock.json --product-runtime-lock benchmarks/product-runtime.lock --broker-lock benchmarks/agent/broker.lock --credential-handle tests/benchmarks/fixtures/mock-credential-handle.json --evaluator-commitment tests/benchmarks/fixtures/evaluator-commitment.json --out .benchmark-cache/g4-evidence-pilot
uv run --frozen --no-sync --project benchmarks python -m benchmarks.report bundle --primary .benchmark-cache/g4-evidence-pilot --independent .benchmark-cache/g4-evidence-pilot --out .benchmark-cache/g4-evidence-pilot.tar.gz
```

Expected: the fixture final manifest appears only after core and `no_tool_control` results; repeated fixture bundling is byte-identical; fixture mode refuses final receipt emission because no frozen ReleaseSubject is supplied.

- [ ] **Step 16 (2–5 min): Run the full pre-freeze G4 regression**

```powershell
uv run --frozen --no-sync --project benchmarks python -m pytest tests/benchmarks -q
git diff --check
```

Expected: every command exits `0`; if the pilot exposes a harness defect, fix and recommit before G5 freezes the ReleaseSubject. This pilot exercises candidate-side contracts only and requires no runtime registry. No scored holdout, final receipt, report, or release claim is created.

- [ ] **Step 17 (2–5 min): Commit only drivers/tests/ignore policy**

```powershell
$expectedStaged = @('.gitignore','release/g4/prepare-evaluator.ps1','release/g4/run-primary.ps1','release/g4/run-independent.ps1','release/g4/finalize.ps1','tests/benchmarks/test_cli_contracts.py','tests/benchmarks/test_powershell_drivers.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'bench: wire fail-closed G4 operational drivers'
```

Expected: this final G4 source commit contains only source, tests, and ignore policy. It contains no benchmark result, receipt, report, raw archive, holdout plaintext, credential material, or release claim.

## G4 Operational Runbook: Post-Freeze Scoring and Evidence (No Commit)

This runbook is an external operation, not an implementation task and not a TDD cycle. Run it only after Tasks G4.1 through G4.7 and G4.8A through G4.8D are committed, every source-changing G5 task is complete, G5 has built and verified the final artifacts, and G5 has frozen `release/evidence/release-subject.json`. From that freeze onward, G4 may create only ignored runtime data, staging assets, and the two registered receipts. Do not edit a tracked file, commit, tag, rebuild an artifact, upload, or change repository visibility.

Post-freeze operators invoke exactly four committed drivers: `prepare-evaluator.ps1`, `run-primary.ps1`, `run-independent.ps1`, and `finalize.ps1`. Every driver requires PowerShell 7.4 or newer, repeats `$PSNativeCommandUseErrorActionPreference = $true`, dot-sources `Invoke-Native.ps1`, and routes every native process through `Invoke-Native`; exit code, stderr, and required stdout are fail-closed. The driver contracts, not ad hoc shell commands, are the executable authority.

### R0: Custodian commits and verifies the hidden evaluator before scoring

The custodian runs this on a custodian-controlled host before either operator receives a run nonce. The custodian may read the hidden evaluator and its signing key; primary and independent operators receive only the signed commitment, signed verification object, and separately authorized evaluator input on their own host. The verification path is produced before scoring and is immutable thereafter.

```powershell
#requires -Version 7.4
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

$repoRoot = (Resolve-Path -LiteralPath '.').Path
. (Join-Path $repoRoot 'release/g4/Invoke-Native.ps1')
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
$result = Invoke-Native -FilePath $pwsh -ArgumentList @(
  '-NoLogo', '-NoProfile', '-File', (Join-Path $repoRoot 'release/g4/prepare-evaluator.ps1'),
  '-RepositoryRoot', $repoRoot,
  '-EvaluatorAllowedRoot', $env:CODESEXTANT_EVALUATOR_ALLOWED_ROOT,
  '-EvaluatorDirectory', $env:CODESEXTANT_EVALUATOR_DIR,
  '-CustodianReviewerId', $env:CODESEXTANT_CUSTODIAN_REVIEWER_ID,
  '-CustodianSigningKey', $env:CODESEXTANT_CUSTODIAN_SIGNING_KEY
)
$prepared = $result.Stdout | ConvertFrom-Json
$commitmentPath = [string]$prepared.evaluator_commitment
$verificationPath = [string]$prepared.evaluator_verification
if ([string]::IsNullOrWhiteSpace($commitmentPath) -or [string]::IsNullOrWhiteSpace($verificationPath)) {
  throw 'prepare-evaluator returned incomplete JSON'
}
$env:CODESEXTANT_EVALUATOR_COMMITMENT = (Resolve-Path -LiteralPath $commitmentPath).Path
$env:CODESEXTANT_EVALUATOR_VERIFICATION = (Resolve-Path -LiteralPath $verificationPath).Path
```

Expected: the driver exits `0` and returns absolute paths to schema-valid, detached-signed commitment and verification objects. The verification binds evaluator tree digest, evaluator command digest, tasks/reviewer-role locks, custodian identity/key digest, and `verified_before_run_nonce=true`. A missing file, wrong signature, mutable evaluator path, or attempt to generate verification after scoring aborts before either operator can start.

### R1: Produce the primary result and signed cross-host review handoff

Run on the locked reference host. Provider credentials are passed only as an opaque broker handle. The driver may persist the nonsecret identity digest `SHA256(provider_id || "\0" || account_id || "\0" || key_id)` but never the credential, a credential hash, or broker-resolved secret bytes.

```powershell
#requires -Version 7.4
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

$repoRoot = (Resolve-Path -LiteralPath '.').Path
. (Join-Path $repoRoot 'release/g4/Invoke-Native.ps1')
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
$result = Invoke-Native -FilePath $pwsh -ArgumentList @(
  '-NoLogo', '-NoProfile', '-File', (Join-Path $repoRoot 'release/g4/run-primary.ps1'),
  '-RepositoryRoot', $repoRoot,
  '-ReleaseAssetAllowedRoot', $env:CODESEXTANT_RELEASE_ASSET_ALLOWED_ROOT,
  '-ReleaseAssetRoot', $env:CODESEXTANT_RELEASE_ASSET_ROOT,
  '-HoldoutAllowedRoot', $env:CODESEXTANT_HOLDOUT_ALLOWED_ROOT,
  '-HoldoutDirectory', $env:CODESEXTANT_HOLDOUT_DIR,
  '-EvaluatorAllowedRoot', $env:CODESEXTANT_EVALUATOR_ALLOWED_ROOT,
  '-EvaluatorCommitment', $env:CODESEXTANT_EVALUATOR_COMMITMENT,
  '-EvaluatorVerification', $env:CODESEXTANT_EVALUATOR_VERIFICATION,
  '-ProviderCredentialHandle', $env:CODESEXTANT_PRIMARY_PROVIDER_CREDENTIAL_HANDLE,
  '-ReviewerId', $env:CODESEXTANT_PRIMARY_REVIEWER_ID,
  '-SigningKey', $env:CODESEXTANT_PRIMARY_SIGNING_KEY
)
$primary = $result.Stdout | ConvertFrom-Json
$handoffPath = [string]$primary.review_handoff
if ([string]::IsNullOrWhiteSpace($handoffPath)) { throw 'run-primary returned incomplete JSON' }
$env:CODESEXTANT_REVIEW_HANDOFF = (Resolve-Path -LiteralPath $handoffPath).Path
```

Expected: the driver exits `0`; verifies the frozen ReleaseSubject, artifact bytes, all locks, pre-score evaluator verification, and clean tracked tree; snapshots source commit/tree, `refs/tags`, artifacts, and manifest; runs core then the `no_tool_control` agent family; and emits only detached-signed `g4-review-handoff.tar.gz`. The handoff contains the signed source Git bundle, exact Linux artifact and manifest, allowlisted locks/scripts/wheelhouse, evaluator commitment/verification digests, privacy-safe driver ledger, freeze snapshot, primary public-safe result projection, and private result-tree digest. It contains no holdout plaintext, evaluator plaintext, provider secret, signing key, username, hostname, email, raw argv, or original-host absolute path.

### R2: Transfer only the signed handoff to a physically distinct host

Transfer the bytes named by `$env:CODESEXTANT_REVIEW_HANDOFF` through the approved private channel, then set `CODESEXTANT_REVIEW_HANDOFF` on the independent host to that host's new local received-file path. Supply the independent host with its own custodian-authorized holdout and evaluator roots plus local copies of the same signed commitment/verification objects through separate authenticated channels. Do not transfer primary or custodian signing keys, broker secrets, environment files, raw provider requests, or a primary-host path.

The independent host must be a physically distinct machine whose signed host identity differs from the primary host and whose measured resources satisfy `resources.lock.json`. A same-host rerun is diagnostic only: it cannot emit `g4-independent-rerun.json`, cannot satisfy G4, and cannot support a SOTA claim. Absolute path strings are never compared across operating systems; verification compares canonical bundle member names and signed content/host/environment digests. Primary and independent `credential_identity_sha256` values must also differ.

### R3: Verify and rerun on the physically distinct independent host

The independent operator starts from a custodian-verified bootstrap copy of the four drivers, not the primary checkout. The driver verifies the detached handoff signature and every member hash before extracting. It then creates a clean checkout from `source.bundle` below the operating system's real temporary root, proves `benchmarks.__file__` is below that checkout, and uses no original-host path.

```powershell
#requires -Version 7.4
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

$bootstrapRoot = (Resolve-Path -LiteralPath $env:CODESEXTANT_INDEPENDENT_BOOTSTRAP_ROOT).Path
. (Join-Path $bootstrapRoot 'release/g4/Invoke-Native.ps1')
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$result = Invoke-Native -FilePath $pwsh -ArgumentList @(
  '-NoLogo', '-NoProfile', '-File', (Join-Path $bootstrapRoot 'release/g4/run-independent.ps1'),
  '-BootstrapRoot', $bootstrapRoot,
  '-TemporaryRoot', $tempRoot,
  '-ReviewHandoff', $env:CODESEXTANT_REVIEW_HANDOFF,
  '-HoldoutAllowedRoot', $env:CODESEXTANT_INDEPENDENT_HOLDOUT_ALLOWED_ROOT,
  '-HoldoutDirectory', $env:CODESEXTANT_INDEPENDENT_HOLDOUT_DIR,
  '-EvaluatorAllowedRoot', $env:CODESEXTANT_INDEPENDENT_EVALUATOR_ALLOWED_ROOT,
  '-EvaluatorDirectory', $env:CODESEXTANT_INDEPENDENT_EVALUATOR_DIR,
  '-EvaluatorCommitment', $env:CODESEXTANT_EVALUATOR_COMMITMENT,
  '-EvaluatorVerification', $env:CODESEXTANT_EVALUATOR_VERIFICATION,
  '-ProviderCredentialHandle', $env:CODESEXTANT_INDEPENDENT_PROVIDER_CREDENTIAL_HANDLE,
  '-ReviewerId', $env:CODESEXTANT_INDEPENDENT_REVIEWER_ID,
  '-SigningKey', $env:CODESEXTANT_INDEPENDENT_SIGNING_KEY,
  '-OutputRoot', $env:CODESEXTANT_INDEPENDENT_OUTPUT_ROOT
)
$independent = $result.Stdout | ConvertFrom-Json
$resultBundlePath = [string]$independent.independent_result_bundle
if ([string]::IsNullOrWhiteSpace($resultBundlePath)) { throw 'run-independent returned incomplete JSON' }
$env:CODESEXTANT_INDEPENDENT_RESULT_BUNDLE = (Resolve-Path -LiteralPath $resultBundlePath).Path
```

Expected: before the run nonce, the driver installs only the signed wheelhouse with `uv sync --frozen --offline`; after the nonce, every Python invocation is `uv run --frozen --no-sync`. It verifies the source commit/tree/import location, artifact and lock digests, evaluator verification, independent host/resource identity, and independent broker identity. It reruns core and the `no_tool_control` agent family and emits only a detached-signed `g4-independent-result.tar.gz`; no shared directory, absolute primary path, mutable dependency resolution, same-host receipt, or copied primary output is accepted.

### R4: Return the signed result bundle and finalize on the coordinator host

Return only the bytes named by `$env:CODESEXTANT_INDEPENDENT_RESULT_BUNDLE` through the approved private channel, then set `CODESEXTANT_INDEPENDENT_RESULT_BUNDLE` on the coordinator host to the new local received-file path. The coordinator verifies both detached signatures, registered key identities, member manifests, distinct host/credential identities, evaluator verification order, and ReleaseSubject/artifact/lock equality before reading result content. It never dereferences an independent-host absolute path.

```powershell
#requires -Version 7.4
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

$repoRoot = (Resolve-Path -LiteralPath '.').Path
. (Join-Path $repoRoot 'release/g4/Invoke-Native.ps1')
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
$releaseBootstrap = Invoke-Native -FilePath 'C:\Python311\python.exe' -ArgumentList @((Join-Path $repoRoot 'tools/bootstrap_release_python.py'),'ensure','--lock',(Join-Path $repoRoot 'requirements/release.lock'),'--print-python')
$releasePythonPath = $releaseBootstrap.Stdout.Trim()
if ([string]::IsNullOrWhiteSpace($releasePythonPath) -or -not (Test-Path -LiteralPath $releasePythonPath -PathType Leaf)) { throw 'hash-locked release Python bootstrap returned no executable' }
$result = Invoke-Native -FilePath $pwsh -ArgumentList @(
  '-NoLogo', '-NoProfile', '-File', (Join-Path $repoRoot 'release/g4/finalize.ps1'),
  '-Mode', 'Finalize',
  '-RepositoryRoot', $repoRoot,
  '-ReviewHandoff', $env:CODESEXTANT_REVIEW_HANDOFF,
  '-IndependentResultBundle', $env:CODESEXTANT_INDEPENDENT_RESULT_BUNDLE,
  '-ProductSourceRoot', $repoRoot,
  '-PublicExportRoot', $env:CODESEXTANT_PUBLIC_EXPORT_ROOT,
  '-ReleasePython', $releasePythonPath,
  '-ReleaseAssetRoot', $env:CODESEXTANT_RELEASE_ASSET_ROOT,
  '-ReleaseIndex', $env:CODESEXTANT_RELEASE_INDEX,
  '-ReleaseIndexBundle', $env:CODESEXTANT_RELEASE_INDEX_BUNDLE,
  '-SigningPolicy', (Join-Path $repoRoot 'release/signing-policy.json'),
  '-VerifierBootstrap', (Join-Path $repoRoot 'release/verifier-bootstrap.json'),
  '-ReceiptRegistry', (Join-Path $repoRoot 'release/evidence/receipt-registry.json'),
  '-ProducerLaunchPolicy', (Join-Path $repoRoot 'release/evidence/producer-launch-policy.json'),
  '-HoldoutDirectory', $env:CODESEXTANT_HOLDOUT_DIR,
  '-EvaluatorCommitment', $env:CODESEXTANT_EVALUATOR_COMMITMENT,
  '-EvaluatorVerification', $env:CODESEXTANT_EVALUATOR_VERIFICATION,
  '-StagingRoot', (Join-Path $repoRoot 'release/staging/g4'),
  '-EvidenceRoot', (Join-Path $repoRoot 'release/evidence'),
  '-PrimaryReviewerId', $env:CODESEXTANT_PRIMARY_REVIEWER_ID,
  '-PrimarySigningKey', $env:CODESEXTANT_PRIMARY_SIGNING_KEY
)
$finalized = $result.Stdout | ConvertFrom-Json
$publicAssetsPath = [string]$finalized.public_assets_manifest
if ([string]::IsNullOrWhiteSpace($publicAssetsPath)) { throw 'finalize returned incomplete JSON' }
$env:CODESEXTANT_G4_PUBLIC_ASSETS = (Resolve-Path -LiteralPath $publicAssetsPath).Path
```

Expected: signed comparison finishes before deterministic archive construction; archive construction finishes before report and generic-sealer receipt emission. Core hypotheses use their own Holm family; the agent family contains only paired `no_tool_control` comparisons and has its own Holm adjustment. Codebase Memory MCP, Serena, and Aider are reported as `not_evaluated` for agent workloads, never as defeated. Exact one-sided paired sign-permutation raw p-values, tie counts/exclusion, null, and seed metadata are reproduced byte-for-byte. Product-frozen `release_gate.py produce-and-seal` alone emits exactly `g4-benchmark.json` and `g4-independent-rerun.json`; finalization also emits `BENCHMARKS.md`, `raw-results.tar.gz`, `holdout-ground-truth.tar.gz`, `independent-comparison.json`, and `g4-public-assets.json`, and every public byte passes the privacy audit.

### R5: Re-verify the G4 domain at the G7 handoff boundary

G7 must not trust an earlier console success or only re-hash the staged manifest. Immediately before accepting the G4 asset set, invoke the same committed finalizer in verification-only mode:

```powershell
#requires -Version 7.4
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

$repoRoot = (Resolve-Path -LiteralPath '.').Path
. (Join-Path $repoRoot 'release/g4/Invoke-Native.ps1')
$releaseBootstrap = Invoke-Native -FilePath 'C:\Python311\python.exe' -ArgumentList @((Join-Path $repoRoot 'tools/bootstrap_release_python.py'),'ensure','--lock',(Join-Path $repoRoot 'requirements/release.lock'),'--print-python')
$releasePythonPath = $releaseBootstrap.Stdout.Trim()
if ([string]::IsNullOrWhiteSpace($releasePythonPath) -or -not (Test-Path -LiteralPath $releasePythonPath -PathType Leaf)) { throw 'hash-locked release Python bootstrap returned no executable' }
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
Invoke-Native -FilePath $pwsh -ArgumentList @(
  '-NoLogo', '-NoProfile', '-File', (Join-Path $repoRoot 'release/g4/finalize.ps1'),
  '-Mode', 'VerifyForG7',
  '-RepositoryRoot', $repoRoot,
  '-PublicAssetsManifest', $env:CODESEXTANT_G4_PUBLIC_ASSETS,
  '-ProductSourceRoot', $repoRoot,
  '-PublicExportRoot', $env:CODESEXTANT_PUBLIC_EXPORT_ROOT,
  '-ReleasePython', $releasePythonPath,
  '-EvidenceRoot', (Join-Path $repoRoot 'release/evidence'),
  '-ReleaseAssetRoot', $env:CODESEXTANT_RELEASE_ASSET_ROOT,
  '-ReleaseIndex', $env:CODESEXTANT_RELEASE_INDEX,
  '-ReleaseIndexBundle', $env:CODESEXTANT_RELEASE_INDEX_BUNDLE,
  '-SigningPolicy', (Join-Path $repoRoot 'release/signing-policy.json'),
  '-VerifierBootstrap', (Join-Path $repoRoot 'release/verifier-bootstrap.json'),
  '-ReceiptRegistry', (Join-Path $repoRoot 'release/evidence/receipt-registry.json'),
  '-ProducerLaunchPolicy', (Join-Path $repoRoot 'release/evidence/producer-launch-policy.json')
)
```

`VerifyForG7` reruns, through `Invoke-Native`, `uv run --frozen --no-sync --project benchmarks python -m benchmarks.report verify-domain`, product-frozen `tools/release_gate.py validate-registry` and `validate-launch-policy`, exact `check-receipt` for both registered G4 basenames, and `check --gate G4`, all with the explicit subject/product-source/public-export/evidence/release-assets/index/bundle/signing/bootstrap/registry/launch-policy context shown above. It verifies both payload schemas and detached signatures, the same ReleaseSubject, all seven staged paths/hashes, and the privacy audit. It does not validate or require unrelated later-gate schemas. Only exit `0` hands the manifest and its six listed ancillary assets to G7; any mismatch stops publication.

### R6: Prove the freeze was not disturbed and stop without a commit

```powershell
#requires -Version 7.4
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

$repoRoot = (Resolve-Path -LiteralPath '.').Path
. (Join-Path $repoRoot 'release/g4/Invoke-Native.ps1')
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
Invoke-Native -FilePath $pwsh -ArgumentList @(
  '-NoLogo', '-NoProfile', '-File', (Join-Path $repoRoot 'release/g4/finalize.ps1'),
  '-Mode', 'VerifyFreeze',
  '-RepositoryRoot', $repoRoot,
  '-PublicAssetsManifest', $env:CODESEXTANT_G4_PUBLIC_ASSETS,
  '-EvidenceRoot', (Join-Path $repoRoot 'release/evidence')
)
```

Expected: every native process is fail-closed; source commit/tree, `refs/tags` digest, artifact hashes, and artifact-manifest hash equal the signed pre-run snapshot; tracked and staged status are empty; every runtime/staging/evidence output is covered by the preregistered ignore/receipt policy; and the G4 driver ledger contains no tag, commit, artifact rebuild, upload, visibility, or publication operation. Stop here. A source, schema, script, lock, evaluator, artifact, or receipt repair requires a new G5 freeze and a complete rerun from R0; a failed run remains private diagnosis and is never relabeled as pass.
