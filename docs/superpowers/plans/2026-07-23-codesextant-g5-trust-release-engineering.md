---
tier: 全文
status: revision-7-shared-exact-commit-and-closed-role-launch
date: 2026-07-23
scope: CodeSextant G5 trust and release engineering
---

# CodeSextant G5 Trust and Release Engineering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Make the release candidate independently auditable for provenance, private-data exclusion, security, licensing, reproducible dependencies, and signed cross-platform artifacts before anything becomes public.

**Architecture:** A fail-closed evidence gate binds every registry gate receipt to one immutable ReleaseSubject: product version/tag, private source commit/tree, allowlist export commit/tree, artifact-manifest hash, signed release-index hash, and artifact hashes. Pre-freeze SAST/runner/staging records instead bind the exact export and staging payload, then become hash-bound inputs to subject-bound G5 receipts. Evidence stays outside Git, so writing it cannot mutate the thing being verified. All source-changing security and release work finishes before the final export, artifacts, benchmark, and dogfood runs.

**Tech Stack:** Python 3.11, JSON Schema 2020-12, TOML, Rust cargo-deny/cargo-audit, SPDX or CycloneDX SBOM, in-toto/SLSA provenance, GitHub Actions with SHA-pinned actions, pytest, Ruff, gitleaks, REUSE.

## Global Constraints

- G5 provenance and policy tooling can start after commit 8bd0dc2; runtime hardening starts only after the G2 native kernel and G3 protocol/daemon foundations exist.
- Product-runtime and public documentation must contain no AI King private skill dependency, personal absolute path, secret, private email, internal handoff, proof-of-concept runtime route, generated stress output, or local database.
- The words in source comments are not the provenance decision. The Aider-related comments in codesextant/ranking.py and codesextant/namegraph.py stay blocked until an independent reviewer records one of: independent idea, licensed derivation, or clean-room rewrite required.
- No competitor implementation source may be shown to a product implementer. A provenance reviewer may inspect it in an isolated checkout and returns only a hash-bound conclusion signed by the reviewer-owned Ed25519 role key. The later workflow Sigstore bundle separately proves repository/workflow/time identity; it is never misrepresented as the reviewer's signature.
- Public export is allowlist-based and happens in a disposable clone. Never rewrite the private repository history in place.
- Missing, stale, wrong-subject, or unverifiable evidence is red. Gate exit codes are fixed: 0 pass, 1 fail, 2 unverifiable.
- Release artifacts are built from the allowlist export commit, not from an unreviewed private-tree checkout.
- Registry-authoritative product-quality, license, SAST, packaging, and installer conclusions are evaluated against that exact allowlist export. Private-source runs are diagnostics only and can never satisfy a public-release receipt.
- Cross-platform claims require real Windows, Linux, and macOS runner receipts. Static workflow inspection is not runtime evidence.
- Native claims require the exact tracked runner-policy entry, fresh availability proof, target-native attestation, and clean ephemeral teardown. A mutable runner label, fallback label, emulation, or persistent dirty host is never authoritative.
- The private staging repository is the final destination Zeroxrain99/CodeSextant with visibility private. Creating it is an external side effect and requires authorization for that exact private destination; G7 later changes only its visibility after a second, immutable publication authorization.
- Tasks 1 through 8 are source-changing preparation and all commit before final freeze. The Final Freeze runbook recreates the export from the final clean source commit, builds artifacts, writes ReleaseSubject, emits every G0-G3 and G5 receipt, and validates the candidate-only registry/launcher contract for deferred G4. G4 and G6 run only after that freeze.
- ReleaseSubject and every raw receipt under release/evidence are gitignored private evidence. Public benchmark/dogfood summaries become immutable G7 release assets, not post-freeze commits.
- `artifact-manifest.json` and ReleaseSubject cover only the immutable product release set created in F4/F5. Post-freeze G4/G6 public evidence is staged only in ignored runtime paths. Already-committed G7 tooling combines `release/staging/g4/g4-public-assets.json` and `release/assets/g6-public-assets.json` into ignored `release/evidence/public-evidence-assets.json`, hashes that exact ancillary set into the publication-plan authorization payload, uploads it while the repository is still PRIVATE only after exact authorization, and never edits the product manifest or ReleaseSubject.
- Any tracked source, lock, workflow, documentation, export, or artifact change invalidates ReleaseSubject and all downstream benchmark, security, artifact, dogfood, and publication evidence.
- Every task follows RED -> GREEN -> refactor, stages only the listed files, and uses the exact commit message shown.

G0 Task 1 creates the sole tracked exact-commit implementation at `tools/exact_task_commit.ps1` and its executable disposable-repository contract test at `tests/release/test_exact_task_commit.py`. G5 owns no duplicate. Every Step 5 block below independently resolves the repository root, dot-sources that tracked helper, and runs the same tracked disposable-repository test before touching the real index. The helper accepts leaf paths only, stages exactly that closed set, rejects pre-staged or caller-added paths and every status except A/M, validates the patch, commits, and proves the resulting commit changed the same set. A task with conditional finding fixes must enumerate each changed leaf path explicitly; directory names and globs are forbidden.

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
$exactTaskCommitPath = Join-Path $repoRoot 'tools\exact_task_commit.ps1'
if (-not (Test-Path -LiteralPath $exactTaskCommitPath -PathType Leaf)) { throw 'tracked exact-task commit helper is missing; complete G0 Task 1 first' }
. $exactTaskCommitPath
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
~~~

---

### Task 1: Build the immutable ReleaseSubject and cross-gate receipt registry

**Files:**

- Create: release/evidence/.gitignore
- Create: release/evidence/release-subject.schema.json
- Create: release/evidence/gate-status.schema.json
- Create: release/evidence/gate-candidate.schema.json
- Create: release/evidence/receipt-registry.schema.json
- Create: release/evidence/material-input-manifest.schema.json
- Create: release/evidence/producer-launch-policy.schema.json
- Create: release/evidence/producer-launch-policy.json
- Create: release/evidence/receipt-registry.json
- Create: release/signing-environment-registry.schema.json
- Create: release/signing-environment-registry.json
- Create: release/evidence/README.md
- Create: requirements/release.lock
- Create: tools/bootstrap_release_python.py
- Create: tools/release_gate.py
- Create: tools/generate_producer_launch_policy.py
- Create: tools/review_role_runner.py
- Create: tests/release/test_release_gate.py
- Create: tests/release/test_release_python.py
- Create: tests/release/test_review_role_runner.py

**Step 1: Write the failing tests**

~~~python
from pathlib import Path

from tools.release_gate import GateResult, check_gate, subject_digest


def test_missing_receipt_is_unverifiable(tmp_path: Path, valid_subject: Path) -> None:
    assert check_gate("G5", valid_subject, tmp_path) is GateResult.UNVERIFIABLE


def test_receipt_for_another_subject_fails(
    tmp_path: Path, valid_subject: Path, valid_receipt: dict
) -> None:
    valid_receipt["subject_sha256"] = "b" * 64
    write_receipt(tmp_path / "provenance.json", valid_receipt)
    assert check_gate("G5", valid_subject, tmp_path) is GateResult.FAIL


def test_public_registry_names_one_unique_producer_for_every_g0_to_g7_receipt() -> None:
    registry = load_registry()
    assert set(registry) == {f"G{i}" for i in range(8)}
    rows = [row for gate in registry.values() for row in gate]
    assert len({row["filename"] for row in rows}) == len(rows)
    assert len({row["producer_id"] for row in rows}) == len(rows)
    assert len({row["launch_spec_id"] for row in rows}) == len(rows)
    assert all(row["producer_id"] and row["launch_spec_id"] and row["schema"] for row in rows)
    assert all(
        row.get("payload_schema")
        for gate in ("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7")
        for row in registry[gate]
    )


def test_security_review_registry_producer_matches_the_only_runbook_writer() -> None:
    row = next(
        row for row in load_registry()["G5"] if row["filename"] == "security-review.json"
    )
    assert row["producer_id"] == "g5_security_review"
    assert final_freeze_candidate_producers("security-review.json") == {row["producer_id"]}
    assert final_freeze_registered_path_writers("security-review.json") == {"tools/release_gate.py produce-and-seal"}


def test_private_registry_extension_cannot_override_public_rows(tmp_path: Path) -> None:
    extension = write_registry_extension(tmp_path, gate="G7", filename="public-smoke.json")
    assert validate_registry(load_registry(), extension=extension).status == "fail"


def test_typed_dependency_and_material_edges_rehash_actual_bytes(
    tmp_path: Path, valid_subject: Path, valid_receipts: Path
) -> None:
    extension = write_registry_extension(
        tmp_path,
        gate="G8",
        filename="application-submission.json",
        depends_on=[{
            "gate": "G7",
            "filename": "public-smoke.json",
            "receipt_sha256_pointer": "/dependency_receipts/public-smoke.json",
        }],
        material_edges=[{
            "material_id": "application_tool_subject",
            "kind": "repository_file",
            "authority_id": "private_application",
            "path": "application/claude-for-oss/application-tool-subject.json",
            "sha256_pointer": "/material_digests/application_tool_subject",
            "canonicalization": "raw_bytes",
        }],
    )
    context = authenticated_verification_context(tmp_path)
    assert check_gate(
        "G8", valid_subject, valid_receipts,
        registry_extension=extension,
        verification_context=context,
    ) is GateResult.PASS
    mutate_one_byte(valid_receipts / "public-smoke.json")
    assert check_gate(
        "G8", valid_subject, valid_receipts,
        registry_extension=extension,
        verification_context=context,
    ) is GateResult.FAIL
    restore_fixture_then_mutate_one_byte(
        context.private_application.root / "application/claude-for-oss/application-tool-subject.json"
    )
    assert check_gate(
        "G8", valid_subject, valid_receipts,
        registry_extension=extension,
        verification_context=context,
    ) is GateResult.FAIL


def test_verification_context_rejects_unbound_or_ambiguous_root_authority(
    complete_public_receipt_fixture,
) -> None:
    for context in (
        swap_product_source_and_public_export_roots(complete_public_receipt_fixture),
        same_relative_path_decoy_root(complete_public_receipt_fixture),
        cwd_decoy_context(complete_public_receipt_fixture),
        receipt_controlled_root_context(complete_public_receipt_fixture),
        symlink_or_reparse_root_context(complete_public_receipt_fixture),
    ):
        assert check_all_public_gates(
            complete_public_receipt_fixture, verification_context=context
        ).status == "fail"


def test_only_authenticated_generic_sealer_launches_producers_and_writes_receipts(repo_root: Path) -> None:
    invocations = authoritative_runbook_receipt_invocations(repo_root)
    assert all(call.command == "tools/release_gate.py produce-and-seal" for call in invocations)
    assert all(call.final_writer == "tools/release_gate.py produce-and-seal" for call in invocations)
    assert no_nonsealer_write_path_reaches_registered_filename(repo_root)


def test_f5_uses_candidate_producers_for_exact_g0_g1_g2_g3_g5_closure(repo_root: Path) -> None:
    invocations = final_freeze_registered_receipt_invocations(repo_root)
    expected = set(registry_filenames_for_gates("G0", "G1", "G2", "G3", "G5"))
    assert {call.receipt for call in invocations} == expected
    assert all(call.interface == "inherited_exclusive_candidate_handle" for call in invocations)
    assert all("--out" not in call.producer_argv for call in invocations)


def test_f5_validates_deferred_g4_candidate_interface_without_producing_it(repo_root: Path) -> None:
    rows = registry_rows_for_gate("G4")
    assert {row["filename"] for row in rows} == {
        "g4-benchmark.json", "g4-independent-rerun.json"
    }
    assert all(load_launch_spec(row["launch_spec_id"])["candidate_transport"] == "inherited_exclusive_handle" for row in rows)
    assert final_freeze_deferred_gate_contract(repo_root, "G4") == "validated_absent"
    assert not set(final_freeze_produced_receipts(repo_root)) & {row["filename"] for row in rows}


def test_sealer_computes_closed_top_level_edge_maps_from_real_bytes(valid_candidate) -> None:
    valid_candidate["dependency_receipts"] = {"forged.json": "0" * 64}
    assert internally_seal_authenticated_child_output(valid_candidate).status == "fail"
    valid_candidate.pop("dependency_receipts")
    sealed = internally_seal_authenticated_child_output(valid_candidate)
    assert set(sealed) == REQUIRED_GATE_ENVELOPE_KEYS
    assert sealed["dependency_receipts"] == recompute_expected_dependency_map()
    assert sealed["material_digests"] == recompute_expected_material_map()


def test_handmade_candidate_or_producer_string_spoof_cannot_be_sealed(tmp_path: Path) -> None:
    handmade = tmp_path / "candidate.json"
    handmade.write_bytes(schema_valid_pass_candidate_bytes())
    assert cli("seal", "--candidate", handmade).status == "invalid_cli"
    assert produce_and_seal(producer_override="other.exe --producer tools/verify_g0.py").status == "fail"


def test_candidate_transport_is_process_bound_and_toctou_safe(authenticated_context) -> None:
    trace = produce_and_seal_with_trace(authenticated_context)
    assert trace.producer_executable_sha256 == trace.registry_authenticated_producer_sha256
    assert trace.candidate_transport == "inherited-exclusive-handle"
    assert trace.candidate_path_exposed_to_caller is False
    attempt_replace_candidate_between_child_exit_and_seal(trace)
    assert trace.final_status == "fail"


def test_existing_registered_receipt_is_read_only_reverified_not_resealed(valid_receipt) -> None:
    before = valid_receipt.path.read_bytes()
    assert cli("check-receipt", "--gate", valid_receipt.gate, "--receipt", valid_receipt.path.name).status == "pass"
    assert valid_receipt.path.read_bytes() == before
    assert cli("produce-and-seal", "--receipt", valid_receipt.path.name).status == "fail"


def test_launch_policy_is_closed_complete_and_path_independent(repo_root: Path) -> None:
    policy = load_producer_launch_policy(repo_root)
    rows = index_registry_rows(load_registry())
    assert set(policy["launch_specs"]) == {row["launch_spec_id"] for row in rows.values()}
    assert all(spec["authority_id"] in CLOSED_AUTHORITY_IDS for spec in policy["launch_specs"].values())
    assert all(is_confined_canonical_path(spec["entrypoint"]) for spec in policy["launch_specs"].values())
    assert all(spec["runtime"]["sha256"] and spec["entrypoint_sha256"] for spec in policy["launch_specs"].values())


def test_launch_policy_generation_is_phase_aware_and_never_hashes_future_files(repo_root: Path) -> None:
    task1 = generate_launch_policy(repo_root, through_phase="G5_TASK1")
    assert set(task1["launch_specs"]) == launch_specs_whose_entrypoints_exist_at_g5_task1(repo_root)
    assert not set(task1["launch_specs"]) & launch_specs_owned_by_later_g6_g7_tasks()
    final = generate_launch_policy(repo_root, through_phase="FINAL_PRE_FREEZE")
    assert set(final["launch_specs"]) == all_public_registry_launch_spec_ids()
    assert all(spec["entrypoint_sha256"] == sha256_file(resolve_spec_entrypoint(spec)) for spec in final["launch_specs"].values())


CURRENT_SIGNING_KEY_ENVS = {
    "CODESEXTANT_PRIMARY_SIGNING_KEY",
    "CODESEXTANT_INDEPENDENT_SIGNING_KEY",
    "CODESEXTANT_CUSTODIAN_SIGNING_KEY",
    "CODESEXTANT_PROVENANCE_REVIEWER_SIGNING_KEY",
    "CODESEXTANT_SECURITY_REQUESTER_SIGNING_KEY",
    "CODESEXTANT_SECURITY_REVIEWER_SIGNING_KEY",
    "CODESEXTANT_FIRST_USER_SIGNING_KEY",
    "CODESEXTANT_DOGFOOD_ANCHOR_SIGNING_KEY",
    "CODESEXTANT_APPLICATION_REVIEWER_SIGNING_KEY",
    "CODESEXTANT_APPLICATION_TOOL_REVIEW_REQUESTER_SIGNING_KEY",
    "CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_SIGNING_KEY",
}


def test_global_signing_environment_inventory_and_every_role_launch_spec_are_exact() -> None:
    inventory = load_signing_environment_registry()
    assert inventory["reserved_pattern"] == r"^CODESEXTANT_[A-Z0-9_]*SIGNING_KEY$"
    assert {row["key_env"] for row in inventory["roles"]} == CURRENT_SIGNING_KEY_ENVS
    assert len({row["role_id"] for row in inventory["roles"]}) == len(inventory["roles"])
    assert len({row["credential_name"] for row in inventory["roles"]}) == len(inventory["roles"])
    for spec in every_realized_public_role_launch_spec():
        launcher = spec["role_launcher"]
        allowed = launcher["allowed_key_env"]
        assert allowed in CURRENT_SIGNING_KEY_ENVS
        assert set(launcher["forbidden_key_env"]) == CURRENT_SIGNING_KEY_ENVS - {allowed}
        assert launcher["signing_env_registry_path"] == "release/signing-environment-registry.json"
        assert launcher["signing_env_registry_sha256"] == sha256_file(
            "release/signing-environment-registry.json"
        )
        assert launcher["reserved_key_env_pattern"] == inventory["reserved_pattern"]


def test_security_launch_spec_owns_exact_role_credential_and_key_environment() -> None:
    spec = load_launch_spec("g5_security")
    launcher = spec["role_launcher"]
    assert launcher["authority_id"] == "product_source"
    assert launcher["path"] == "tools/review_role_runner.py"
    assert launcher["sha256"] == sha256_file("tools/review_role_runner.py")
    assert launcher["role"] == "reviewer"
    assert launcher["credential_name"] == "codesextant/g5/security-reviewer"
    assert launcher["allowed_key_env"] == "CODESEXTANT_SECURITY_REVIEWER_SIGNING_KEY"
    assert set(launcher["forbidden_key_env"]) == CURRENT_SIGNING_KEY_ENVS - {
        launcher["allowed_key_env"]
    }


@pytest.mark.parametrize("attack", [
    shell_quoting_injection,
    same_name_path_shadow,
    alternate_interpreter,
    cargo_package_replacement,
    unsigned_role_launcher,
    wrong_role_or_credential,
])
def test_sealer_rejects_launch_identity_or_signer_policy_substitution(attack) -> None:
    assert produce_and_seal_under_attack(attack).status == "fail"


def test_registry_edges_reject_cycles_unknown_dependencies_and_unconfined_materials() -> None:
    for invalid in (
        cyclic_dependency_extension(),
        unknown_receipt_dependency_extension(),
        traversal_material_extension(),
        missing_digest_pointer_extension(),
    ):
        assert validate_registry(load_registry(), extension=invalid).status == "fail"


EXPECTED_PUBLIC_DEPENDENCY_GRAPH = {
    "g0-workspace.json": (),
    "g1.json": ("g0-workspace.json",),
    "g2-map-quality.json": ("g0-workspace.json", "g1.json"),
    "g3-contracts.json": ("g1.json", "g2-map-quality.json"),
    "g3-lifecycle.json": ("g3-contracts.json",),
    "g3-reliability.json": ("g3-contracts.json", "g3-lifecycle.json"),
    "g4-benchmark.json": ("g2-map-quality.json", "g3-contracts.json", "g3-lifecycle.json", "g3-reliability.json"),
    "g4-independent-rerun.json": ("g4-benchmark.json",),
    "provenance.json": ("g0-workspace.json", "g1.json", "g2-map-quality.json", "g3-contracts.json", "g3-lifecycle.json", "g3-reliability.json"),
    "public-export.json": ("provenance.json",),
    "license.json": ("public-export.json",),
    "security.json": ("license.json", "g3-lifecycle.json", "g3-reliability.json"),
    "security-review.json": ("security.json",),
    "artifacts.json": ("security-review.json", "g3-lifecycle.json"),
    "first-user.json": ("artifacts.json",),
    "dogfood-summary.json": ("first-user.json", "g4-independent-rerun.json"),
    "issues.json": ("dogfood-summary.json",),
    "publication-security-refresh.json": ("security.json", "security-review.json", "artifacts.json", "issues.json", "g4-independent-rerun.json"),
    "github-publication.json": ("g0-workspace.json", "g1.json", "g2-map-quality.json", "g3-contracts.json", "g3-lifecycle.json", "g3-reliability.json", "g4-benchmark.json", "g4-independent-rerun.json", "provenance.json", "public-export.json", "license.json", "security.json", "security-review.json", "artifacts.json", "first-user.json", "dogfood-summary.json", "issues.json", "publication-security-refresh.json"),
    "public-smoke.json": ("publication-security-refresh.json", "github-publication.json"),
}

EXPECTED_PUBLIC_MATERIAL_GRAPH = {
    "g0-workspace.json": ("release_subject", "producer_inputs"),
    "g1.json": ("oracle_manifest", "producer_inputs"),
    "g2-map-quality.json": ("expert_expectations", "producer_inputs"),
    "g3-contracts.json": ("operations_registry", "producer_inputs"),
    "g3-lifecycle.json": ("native_lifecycle_matrix", "producer_inputs"),
    "g3-reliability.json": ("producer_inputs",),
    "g4-benchmark.json": ("benchmark_protocol", "producer_inputs"),
    "g4-independent-rerun.json": ("benchmark_reviewer_roles", "producer_inputs"),
    "provenance.json": ("prior_art_review", "producer_inputs"),
    "public-export.json": ("public_export_config", "producer_inputs"),
    "license.json": ("product_license", "producer_inputs"),
    "security.json": ("security_review_scope", "producer_inputs"),
    "security-review.json": ("security_findings", "producer_inputs"),
    "artifacts.json": ("artifact_manifest", "producer_inputs"),
    "first-user.json": ("first_user_runner_bundle", "producer_inputs"),
    "dogfood-summary.json": ("dogfood_policy", "producer_inputs"),
    "issues.json": ("dogfood_issue_ledger", "producer_inputs"),
    "publication-security-refresh.json": ("sast_lock", "producer_inputs"),
    "github-publication.json": ("g8_seed_install_receipt", "producer_inputs"),
    "public-smoke.json": ("release_index", "producer_inputs"),
}

EXPECTED_INPUT_MANIFEST_ROLES = {
    "g0-workspace.json": ("subject", "public_export_tree"),
    "g1.json": ("subject", "public_export_tree", "oracle_manifest"),
    "g2-map-quality.json": ("subject", "public_export_tree", "expert_expectations"),
    "g3-contracts.json": ("subject", "public_export_tree", "operations_registry"),
    "g3-lifecycle.json": ("subject", "release_index", "release_index_bundle", "artifact_manifest", "asset_closure", "lifecycle_matrix", "lifecycle_fragment_closure", "signing_policy", "verifier_bootstrap"),
    "g3-reliability.json": ("subject", "public_export_tree", "reliability_result_closure"),
    "g4-benchmark.json": ("subject", "benchmark_protocol", "analysis_plan", "uv_lock", "competitors_lock", "image_digests", "resources", "product_runtime", "reviewer_roles", "result_closure"),
    "g4-independent-rerun.json": ("subject", "handoff", "reviewer_roles", "implementation_actors", "rerun_result_closure"),
    "provenance.json": ("subject", "artifact_manifest", "asset_closure", "prior_art_review", "reviewer_roles", "implementation_actors", "source_manifest"),
    "public-export.json": ("subject", "public_export_config", "product_source_tree", "public_export_tree", "excluded_path_audit"),
    "license.json": ("subject", "public_export_tree", "product_license", "third_party_notices", "license_report"),
    "security.json": ("subject", "product_source_tree", "public_export_tree", "artifact_manifest", "asset_closure", "security_scope", "reviewer_roles", "implementation_actors", "tool_lock", "sast_input_closure"),
    "security-review.json": ("request", "input", "findings", "scope", "reviewer_roles", "implementation_actors"),
    "artifacts.json": ("release_index", "release_index_bundle", "artifact_manifest", "asset_closure", "signing_policy", "verifier_bootstrap"),
    "first-user.json": ("runner_receipt", "runner_bundle", "scenario", "runner_roles", "implementation_actors", "artifact_manifest", "asset_closure", "release_python_lock"),
    "dogfood-summary.json": ("policy", "plan", "transparency_plan", "transparency_authorization", "workstream_bindings", "installation_receipt", "event_log", "anchor_closure", "issue_ledger"),
    "issues.json": ("issue_ledger", "plan"),
    "publication-security-refresh.json": ("artifact_manifest", "asset_closure", "runtime_security_closure", "sbom_closure", "sast_lock", "sast_rules", "scanner_lock", "signed_review", "advisory_feed_closure"),
    "github-publication.json": ("publication_plan", "authorization", "start_receipt", "journal", "result_receipt", "github_controls", "security_refresh", "g8_seed_install_receipt", "public_evidence_closure"),
    "public-smoke.json": ("publication_receipt", "github_controls", "security_refresh", "g8_seed_install_receipt", "signing_policy", "verifier_bootstrap", "release_index", "release_index_bundle", "artifact_manifest", "asset_closure", "public_evidence_closure"),
}


def test_public_registry_declares_the_complete_g0_to_g7_graph() -> None:
    rows = index_registry_rows(load_registry())
    assert set(rows) == set(EXPECTED_PUBLIC_DEPENDENCY_GRAPH) == set(EXPECTED_PUBLIC_MATERIAL_GRAPH)
    assert all("depends_on" in row and "material_edges" in row for row in rows.values())
    assert dependency_filename_graph(rows) == EXPECTED_PUBLIC_DEPENDENCY_GRAPH
    assert material_id_graph(rows) == EXPECTED_PUBLIC_MATERIAL_GRAPH
    assert input_manifest_role_graph(rows) == EXPECTED_INPUT_MANIFEST_ROLES
    assert topological_sort(rows) == tuple(topological_sort(rows))


def test_every_public_dependency_and_material_edge_rehashes_real_bytes(
    complete_public_receipt_fixture
) -> None:
    assert check_all_public_gates(complete_public_receipt_fixture).status == "pass"
    for receipt, dependency in every_declared_public_dependency():
        mutated = complete_public_receipt_fixture.copy()
        mutate_one_byte(mutated.evidence_dir / dependency)
        assert check_receipt(receipt, mutated).status == "fail"
    for receipt, material in every_declared_public_material():
        mutated = complete_public_receipt_fixture.copy()
        mutate_one_byte(resolve_authoritative_material(mutated, material))
        assert check_receipt(receipt, mutated).status == "fail"
    for receipt, manifest_entry in every_recursive_input_manifest_entry():
        mutated = complete_public_receipt_fixture.copy()
        mutate_one_byte(resolve_manifest_entry_from_authenticated_authority(mutated, manifest_entry))
        assert check_receipt(receipt, mutated).status == "fail"


def test_input_manifest_is_verifier_owned_closed_and_not_a_receipt_summary(valid_candidate) -> None:
    manifest = build_input_manifest_from_producer_argv_and_context(valid_candidate)
    assert tuple(entry["role"] for entry in manifest["entries"]) == EXPECTED_INPUT_MANIFEST_ROLES[valid_candidate.filename]
    assert all(entry["authority_id"] in CLOSED_AUTHORITY_IDS for entry in manifest["entries"])
    assert recursively_rehash_manifest_entries(manifest).status == "pass"
    forge_self_consistent_summary_without_changing_real_input(manifest)
    assert recursively_rehash_manifest_entries(manifest).status == "fail"


def test_subject_digest_is_canonical(valid_subject_dict: dict) -> None:
    reordered = dict(reversed(list(valid_subject_dict.items())))
    assert subject_digest(valid_subject_dict) == subject_digest(reordered)


def test_subject_requires_the_signed_release_index_digest(valid_subject_dict: dict) -> None:
    assert validate_release_subject(valid_subject_dict).status == "pass"
    valid_subject_dict.pop("release_index_sha256")
    assert validate_release_subject(valid_subject_dict).status == "fail"


def test_release_python_lock_is_fully_hashed_and_pins_ed25519_runtime(repo_root: Path) -> None:
    lock = parse_hashed_requirements(repo_root / "requirements/release.lock")
    assert lock["cryptography"].version == "45.0.5"
    assert all(dependency.hashes for dependency in lock.values())


def test_release_python_bootstrap_refuses_ambient_or_wrong_lock(tmp_path: Path) -> None:
    assert bootstrap_release_python(tmp_path, lock="requirements/release.lock").digest_addressed
    assert bootstrap_release_python(tmp_path, lock="requirements/test.lock").status == "fail"
~~~

release-subject.schema.json requires:

~~~json
{
  "format_version": 1,
  "product_version": "semver read from codesextant._version.__version__",
  "release_tag": "the exact string v plus product_version",
  "frozen_at_utc": "RFC 3339 UTC timestamp written once by freeze_release_subject.py",
  "source_commit": "40 lowercase hexadecimal characters",
  "source_tree_sha256": "64 lowercase hexadecimal characters",
  "export_commit": "40 lowercase hexadecimal characters",
  "export_tree_sha256": "64 lowercase hexadecimal characters",
  "artifact_manifest_sha256": "64 lowercase hexadecimal characters",
  "release_index_sha256": "64 lowercase hexadecimal characters for the separately signed non-recursive distribution index",
  "artifacts": [
    {"target": "Rust target triple", "filename": "basename only", "sha256": "64 lowercase hexadecimal characters"}
  ]
}
~~~

The schema implements those descriptions as const/format/pattern constraints; it does not accept descriptive example strings. `frozen_at_utc` is generated exactly once during the atomic ReleaseSubject write, is covered by the canonical subject digest, and is the time authority for post-freeze receipt freshness. `gate-candidate.schema.json` is the closed pre-seal envelope accepted from a domain producer and expressly forbids `dependency_receipts`, `material_digests`, and `sealed_by`. `gate-status.schema.json` is the sole final envelope and requires gate, subject_sha256, producer_id, launch_spec_id, issued_at_utc, reviewer, tools with versions/digests, artifacts with SHA-256, checks, status, domain `payload`, the two closed top-level generic maps `dependency_receipts` and `material_digests`, and `sealed_by`; no domain payload schema repeats those maps. `receipt-registry.schema.json` is a closed public schema for the G0-G7 registry and every allowed private extension row. Every row declares a closed producer_id/launch_spec_id, domain `payload_schema`, typed `depends_on`, and `material_edges`; neither array is optional or inferred. A `depends_on` row contains exactly gate, registered filename, and an RFC 6901 pointer under top-level `/dependency_receipts`. A `material_edges` row contains exactly material_id, kind (`release_subject`, `repository_file`, `evidence_file`, `release_asset`, or `input_manifest`), closed `authority_id` (`subject`, `product_source`, `public_export`, `public_clone`, `private_application`, `evidence`, or `release_assets`), confined normalized relative path when applicable, an RFC 6901 pointer under top-level `/material_digests`, canonicalization (`raw_bytes` or `jcs`), and—only for `input_manifest`—an exact ordered nonempty `required_roles` array. Kind/authority combinations are closed: release_subject/subject, repository_file/product_source|public_export|public_clone|private_application, evidence_file|input_manifest/evidence, and release_asset/release_assets. The schema rejects command-like producer strings, absolute/traversal/aliased paths, duplicate material IDs or roles, unknown keys, malformed/wrong-level pointers, and unregistered dependencies.

`material-input-manifest.schema.json` is a closed verifier-owned recursive manifest. Every entry has exactly role, kind (`file`, `tree`, or `closure_manifest`), one closed authority_id, confined path, size when applicable, SHA-256, and canonicalization. A `closure_manifest` is recursively parsed and every member is re-resolved and re-hashed; nesting depth/member count/total bytes are bounded and cycles, aliases, links, duplicate roles/paths, missing/extra required roles, or summaries without the actual members fail. The generic sealer derives this manifest from the producer's parsed CLI inputs plus `VerificationContext`, never from receipt payload fields, writes it create-new below the fixed evidence authority, re-opens it, recursively re-hashes every entry, and only then binds its JCS digest. This is the permitted compact representation of every direct non-receipt producer input; it is not a producer-authored pass summary.

`release_gate.py produce-and-seal` is the single generic producer launcher and final-envelope writer for G0-G8; there is deliberately no public `seal --candidate` or producer-executable override. From the authenticated registry row and `VerificationContext` it resolves the exact producer/optional role-launcher entrypoint beneath an authenticated authority, checks its raw-byte digest and complete interpreter/binary launch identity before spawn, creates an anonymous or delete-on-close exclusive handle unavailable by pathname to the caller, and passes only that inherited handle to the child as its candidate sink. The sealer retains the handle, waits for the exact child PID/process identity, rechecks the producer file identity/digest, reads candidate bytes from the retained handle before close, and rejects link count/file-ID/size drift or any second writer. A handmade file, self-declared producer string, alternate executable with the same basename, stdout/path injection, or candidate replacement cannot enter the seal path.

`release/evidence/producer-launch-policy.json` and its closed schema are the public launch SSOT, but they are intentionally phase-generated rather than pretending Task 1 can hash future files. Task 1 creates the schema, generator, and a base policy containing only launch specs whose entrypoints/runtime/role files exist at that commit; structural registry validation permits unresolved later `launch_spec_id` references only while `phase != FINAL_PRE_FREEZE`. Each later producer-owning task runs `tools/generate_producer_launch_policy.py sync --through-phase <phase>`, stages the same public policy with its actual source/runtime/launcher/role hashes, and tests exact add/update closure. G6 tasks add and exact-stage G6 specs after their files exist; G7 does the same for G7. F1 regenerates `--through-phase FINAL_PRE_FREEZE --check`, requires every public registry launch_spec exactly once, and rejects missing/stale/future/extra specs. Private G8 is never inserted into the public file: it is additive only through authenticated `producer-launch-policy-extension.json`.

Every registry row carries a closed `producer_id` label and `launch_spec_id`; command-like producer strings are forbidden. Every realized launch spec fixes authority_id, canonical entrypoint path and raw SHA-256, runtime/toolchain authority/path/version/digest, argv prefix as a JSON string array, candidate-handle interface, and optional role-launcher policy. A role-launcher policy fixes its own authority/path/digest, exact role, OS credential name, single allowed key environment, authenticated signing-environment-registry path/digest, the reserved environment-name pattern, the complete forbidden set mechanically derived as every registered key environment except the one allowed, role registry/actor roster digests, and whether the domain output contains an external attestation instead of a local signer. Signed G4-G8 rows all declare one of these closed signer modes; `none` is valid only for deterministic keyless verification of already-signed inputs. `produce-and-seal` uses CreateProcess/exec argv arrays directly without a shell, resolves no PATH entry, and for Cargo verifies pinned cargo plus package ID/source tree. Quoting, PATH shadow, package replacement, role/credential/key-env drift, or unregistered launcher fails before child start.

`release/signing-environment-registry.json` and its closed schema are the cross-plan signing-environment SSOT. The registry fixes `reserved_pattern` to `^CODESEXTANT_[A-Z0-9_]*SIGNING_KEY$` and contains unique role_id/credential_name/key_env rows for the current primary, independent, custodian, provenance reviewer, security requester/reviewer, first-user, dogfood anchor, application reviewer, application-tool review requester, and application-tool security reviewer roles. Its exact key environments are `CODESEXTANT_PRIMARY_SIGNING_KEY`, `CODESEXTANT_INDEPENDENT_SIGNING_KEY`, `CODESEXTANT_CUSTODIAN_SIGNING_KEY`, `CODESEXTANT_PROVENANCE_REVIEWER_SIGNING_KEY`, `CODESEXTANT_SECURITY_REQUESTER_SIGNING_KEY`, `CODESEXTANT_SECURITY_REVIEWER_SIGNING_KEY`, `CODESEXTANT_FIRST_USER_SIGNING_KEY`, `CODESEXTANT_DOGFOOD_ANCHOR_SIGNING_KEY`, `CODESEXTANT_APPLICATION_REVIEWER_SIGNING_KEY`, `CODESEXTANT_APPLICATION_TOOL_REVIEW_REQUESTER_SIGNING_KEY`, and `CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_SIGNING_KEY`. The generator and sealer reject a launch spec unless its forbidden list is exact set equality with registry minus allowed. Independently, the role runner enumerates every process environment key and rejects any reserved-pattern match other than the one allowed, even when a future role name is not yet in the inventory; the inventory provides auditable completeness, while the runtime pattern closes forward-compatibility leakage.

The normative security launch entry is:

~~~json
{"g5_security":{"producer_id":"g5_security","authority_id":"product_source","entrypoint":"tools/security_receipt.py","entrypoint_sha256":"64 lowercase hex of reviewed bytes","runtime":{"authority_id":"product_source","path":"requirements/release.lock","version":"CPython 3.11 digest-addressed environment","sha256":"64 lowercase hex"},"argv_prefix":["receipt"],"candidate_transport":"inherited_exclusive_handle","signer_mode":"os_credential_ed25519","role_launcher":{"authority_id":"product_source","path":"tools/review_role_runner.py","sha256":"64 lowercase hex","role":"reviewer","credential_name":"codesextant/g5/security-reviewer","allowed_key_env":"CODESEXTANT_SECURITY_REVIEWER_SIGNING_KEY","forbidden_key_env":["CODESEXTANT_APPLICATION_REVIEWER_SIGNING_KEY","CODESEXTANT_APPLICATION_TOOL_REVIEW_REQUESTER_SIGNING_KEY","CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_SIGNING_KEY","CODESEXTANT_CUSTODIAN_SIGNING_KEY","CODESEXTANT_DOGFOOD_ANCHOR_SIGNING_KEY","CODESEXTANT_FIRST_USER_SIGNING_KEY","CODESEXTANT_INDEPENDENT_SIGNING_KEY","CODESEXTANT_PRIMARY_SIGNING_KEY","CODESEXTANT_PROVENANCE_REVIEWER_SIGNING_KEY","CODESEXTANT_SECURITY_REQUESTER_SIGNING_KEY"],"signing_env_registry_path":"release/signing-environment-registry.json","signing_env_registry_sha256":"64 lowercase hex","reserved_key_env_pattern":"^CODESEXTANT_[A-Z0-9_]*SIGNING_KEY$","role_registry_path":"release/security-reviewer-roles.json","role_registry_sha256":"64 lowercase hex","implementation_actors_path":"provenance/implementation-actors.json","implementation_actors_sha256":"64 lowercase hex"}}}
~~~

The public policy contains corresponding exact entries for all 20 public receipts only; each authenticated private extension contains only its mutually referenced private rows/specs. G4 primary/independent, G5 provenance/security/review, G6 external-first-user verifier/dogfood anchors, G7 publication authorization/result, and later G8 application requester/reviewer declare explicit signer/attestation modes and role policies; a generic inherited credential is never allowed. Values shown as digest descriptions above are generated from actual reviewed bytes before commit. Public values must be 64 lowercase hexadecimal characters and are rechecked at F1; private values are generated and validated only after ApplicationToolSubject authenticates the private root.

For immutable evidence, the exact read-only API is `release_gate.py check-receipt --gate <gate> --receipt <registered-basename> <VerificationContext flags>`; it accepts no path and resolves the basename only under authenticated evidence authority. `check --gate` verifies every row in a gate. Runbooks use absent -> `produce-and-seal`, existing -> `check-receipt`; `produce-and-seal` fails if the final path exists. `validate-deferred-gate-interface` authenticates an exact named gate/receipt set, proves every launch spec is exclusive-handle candidate-only, and proves registered finals are absent without launching a producer; F5 uses it for the later G4 pair. Domain arguments after `--` may be empty only when the launch spec fixed prefix plus authenticated context completely determine every required input; otherwise every dynamic input is explicit and enters the verifier-owned input manifest.

The internal candidate validates against `gate-candidate.schema.json`, contains only domain envelope/payload, and cannot contain generic maps. The sealer builds/verifies the input manifest, DAG, and both maps, records subject/producer/launcher/policy digests plus child identity in `sealed_by`, and atomically create-new writes the registry filename. Static tests reject direct registered output, missing `produce-and-seal`, second final writer, or gate/receipt/producer mismatch. `producer_id` records authenticated domain-candidate provenance; final-path writer is always `release_gate.py produce-and-seal`.

`VerificationContext` is a typed immutable object, not a caller-free map. It contains independently authenticated authorities for subject, product source, public export, public clone, private application, evidence, and release assets. It is built only from explicit CLI flags: `--subject`, `--product-source-root`, `--public-export-root`, `--public-clone-root`, `--private-application-root`, `--evidence-dir`, `--release-assets-root`, `--release-index`, `--release-index-bundle`, `--signing-policy`, and `--verifier-bootstrap`. No authority defaults to CWD, environment, a receipt path, or another authority with the same relative layout. Before resolving any material, subject is canonicalized; product_source/public_export/public_clone each independently prove the exact ReleaseSubject commit/tree plus clean index/worktree, no nonignored untracked file, confined tracked closure, and no symlink/reparse component; private_application proves the exact signed G8 application-tool subject and clean private closure; evidence must equal the fixed directory derived from the subject path and have no link/reparse component; release_assets independently verifies the signed release index/bundle/policy/bootstrap, exact subject `release_index_sha256`, and closed asset set. A swapped authority, same-relative-path decoy root, CWD decoy, receipt-controlled path, symlink/reparse root, mismatched commit/tree, dirty closure, or unavailable required authority fails before the first path resolution.

Before returning PASS `release_gate.py` builds the complete acyclic dependency DAG, requires every upstream receipt to be registry-valid and bound to the same ReleaseSubject, reads its actual canonical bytes, recomputes SHA-256, and compares that value to the top-level pointer. It then resolves and recursively re-hashes each material only through its declared authenticated authority. A filename, schema-valid pass field, producer-controlled generic map, receipt-controlled path, caller-supplied digest, or manifest summary is never evidence. Private registry extensions use this identical public implementation/schema and may add new gates/edges but cannot override a public row or authority. Cycles, missing/extra edges, an unavailable authority, digest drift, or a dependency that is only UNVERIFIABLE makes the dependent gate fail closed. The initial structural registry check validates closed pointers/authorities/paths/roles but does not require later-plan payload schemas to exist; `--require-payload-schemas` is mandatory only in final pre-freeze verification after every later-plan schema is committed.

`receipt-registry.json` is deliberately the public G0-G7 authority and contains no path into excluded private `application/`. After ApplicationToolSubject has authenticated the private root, G8 bootstrap creates `application/claude-for-oss/receipt-registry-extension.json` and the separate `application/claude-for-oss/producer-launch-policy-extension.json`, then invokes the product-root `release_gate.py` to validate the merged public-plus-private registry and launch policy through that authenticated `private_application` authority. Earlier F1 validates only the exact public G0-G7 closure and cannot reference these future private files. Later G8 calls pass both `--registry-extension` and `--launch-policy-extension`; extensions may add only mutually referenced private G8 rows/specs, cannot override public IDs/specs, and every private entrypoint/runtime/role-launcher digest and merged-validation result is ApplicationToolSubject/input-manifest bound.

receipt-registry.json is the only public G0-G7 receipt-name authority:

~~~json
{
  "G0": [
    {"filename":"g0-workspace.json","producer_id":"g0_workspace","launch_spec_id":"g0_workspace","schema":"gate-status.schema.json","payload_schema":"release/evidence/g0-workspace.schema.json","depends_on":[],"material_edges":[{"material_id":"release_subject","kind":"release_subject","authority_id":"subject","sha256_pointer":"/material_digests/release_subject","canonicalization":"jcs"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/g0-workspace.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","public_export_tree"]}]}
  ],
  "G1": [
    {"filename":"g1.json","producer_id":"g1_foundation","launch_spec_id":"g1_foundation","schema":"gate-status.schema.json","payload_schema":"release/evidence/g1-foundation.schema.json","depends_on":[{"gate":"G0","filename":"g0-workspace.json","receipt_sha256_pointer":"/dependency_receipts/g0-workspace.json"}],"material_edges":[{"material_id":"oracle_manifest","kind":"repository_file","authority_id":"public_export","path":"tests/fixtures/oracle-manifest.json","sha256_pointer":"/material_digests/oracle_manifest","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/g1.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","public_export_tree","oracle_manifest"]}]}
  ],
  "G2": [
    {"filename":"g2-map-quality.json","producer_id":"g2_map_quality","launch_spec_id":"g2_map_quality","schema":"gate-status.schema.json","payload_schema":"release/evidence/g2-map-quality.schema.json","depends_on":[{"gate":"G0","filename":"g0-workspace.json","receipt_sha256_pointer":"/dependency_receipts/g0-workspace.json"},{"gate":"G1","filename":"g1.json","receipt_sha256_pointer":"/dependency_receipts/g1.json"}],"material_edges":[{"material_id":"expert_expectations","kind":"repository_file","authority_id":"public_export","path":"tests/fixtures/map_gate_expectations.json","sha256_pointer":"/material_digests/expert_expectations","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/g2-map-quality.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","public_export_tree","expert_expectations"]}]}
  ],
  "G3": [
    {"filename":"g3-contracts.json","producer_id":"g3_contracts","launch_spec_id":"g3_contracts","schema":"gate-status.schema.json","payload_schema":"release/evidence/g3-contracts.schema.json","depends_on":[{"gate":"G1","filename":"g1.json","receipt_sha256_pointer":"/dependency_receipts/g1.json"},{"gate":"G2","filename":"g2-map-quality.json","receipt_sha256_pointer":"/dependency_receipts/g2-map-quality.json"}],"material_edges":[{"material_id":"operations_registry","kind":"repository_file","authority_id":"public_export","path":"spec/operations.yaml","sha256_pointer":"/material_digests/operations_registry","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/g3-contracts.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","public_export_tree","operations_registry"]}]},
    {"filename":"g3-lifecycle.json","producer_id":"g3_lifecycle","launch_spec_id":"g3_lifecycle","schema":"gate-status.schema.json","payload_schema":"release/lifecycle-receipt.schema.json","depends_on":[{"gate":"G3","filename":"g3-contracts.json","receipt_sha256_pointer":"/dependency_receipts/g3-contracts.json"}],"material_edges":[{"material_id":"native_lifecycle_matrix","kind":"release_asset","authority_id":"release_assets","path":"native-lifecycle-matrix.json","sha256_pointer":"/material_digests/native_lifecycle_matrix","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/g3-lifecycle.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","release_index","release_index_bundle","artifact_manifest","asset_closure","lifecycle_matrix","lifecycle_fragment_closure","signing_policy","verifier_bootstrap"]}]},
    {"filename":"g3-reliability.json","producer_id":"g3_reliability","launch_spec_id":"g3_reliability","schema":"gate-status.schema.json","payload_schema":"release/evidence/g3-reliability.schema.json","depends_on":[{"gate":"G3","filename":"g3-contracts.json","receipt_sha256_pointer":"/dependency_receipts/g3-contracts.json"},{"gate":"G3","filename":"g3-lifecycle.json","receipt_sha256_pointer":"/dependency_receipts/g3-lifecycle.json"}],"material_edges":[{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/g3-reliability.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","public_export_tree","reliability_result_closure"]}]}
  ],
  "G4": [
    {"filename":"g4-benchmark.json","producer_id":"g4_benchmark","launch_spec_id":"g4_benchmark","schema":"gate-status.schema.json","payload_schema":"benchmarks/schema/g4-benchmark-receipt.schema.json","depends_on":[{"gate":"G2","filename":"g2-map-quality.json","receipt_sha256_pointer":"/dependency_receipts/g2-map-quality.json"},{"gate":"G3","filename":"g3-contracts.json","receipt_sha256_pointer":"/dependency_receipts/g3-contracts.json"},{"gate":"G3","filename":"g3-lifecycle.json","receipt_sha256_pointer":"/dependency_receipts/g3-lifecycle.json"},{"gate":"G3","filename":"g3-reliability.json","receipt_sha256_pointer":"/dependency_receipts/g3-reliability.json"}],"material_edges":[{"material_id":"benchmark_protocol","kind":"repository_file","authority_id":"public_export","path":"benchmarks/protocol.md","sha256_pointer":"/material_digests/benchmark_protocol","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/g4-benchmark.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","benchmark_protocol","analysis_plan","uv_lock","competitors_lock","image_digests","resources","product_runtime","reviewer_roles","result_closure"]}]},
    {"filename":"g4-independent-rerun.json","producer_id":"g4_independent","launch_spec_id":"g4_independent","schema":"gate-status.schema.json","payload_schema":"benchmarks/schema/g4-independent-receipt.schema.json","depends_on":[{"gate":"G4","filename":"g4-benchmark.json","receipt_sha256_pointer":"/dependency_receipts/g4-benchmark.json"}],"material_edges":[{"material_id":"benchmark_reviewer_roles","kind":"repository_file","authority_id":"public_export","path":"benchmarks/reviewer-roles.lock","sha256_pointer":"/material_digests/benchmark_reviewer_roles","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/g4-independent-rerun.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","handoff","reviewer_roles","implementation_actors","rerun_result_closure"]}]}
  ],
  "G5": [
    {"filename":"provenance.json","producer_id":"g5_provenance","launch_spec_id":"g5_provenance","schema":"gate-status.schema.json","payload_schema":"provenance/receipt.schema.json","depends_on":[{"gate":"G0","filename":"g0-workspace.json","receipt_sha256_pointer":"/dependency_receipts/g0-workspace.json"},{"gate":"G1","filename":"g1.json","receipt_sha256_pointer":"/dependency_receipts/g1.json"},{"gate":"G2","filename":"g2-map-quality.json","receipt_sha256_pointer":"/dependency_receipts/g2-map-quality.json"},{"gate":"G3","filename":"g3-contracts.json","receipt_sha256_pointer":"/dependency_receipts/g3-contracts.json"},{"gate":"G3","filename":"g3-lifecycle.json","receipt_sha256_pointer":"/dependency_receipts/g3-lifecycle.json"},{"gate":"G3","filename":"g3-reliability.json","receipt_sha256_pointer":"/dependency_receipts/g3-reliability.json"}],"material_edges":[{"material_id":"prior_art_review","kind":"repository_file","authority_id":"public_export","path":"provenance/reviews/prior-art-review.json","sha256_pointer":"/material_digests/prior_art_review","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/provenance.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","artifact_manifest","asset_closure","prior_art_review","reviewer_roles","implementation_actors","source_manifest"]}]},
    {"filename":"public-export.json","producer_id":"g5_public_export","launch_spec_id":"g5_public_export","schema":"gate-status.schema.json","payload_schema":"release/evidence/public-export.schema.json","depends_on":[{"gate":"G5","filename":"provenance.json","receipt_sha256_pointer":"/dependency_receipts/provenance.json"}],"material_edges":[{"material_id":"public_export_config","kind":"repository_file","authority_id":"product_source","path":"release/public-export.toml","sha256_pointer":"/material_digests/public_export_config","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/public-export.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","public_export_config","product_source_tree","public_export_tree","excluded_path_audit"]}]},
    {"filename":"license.json","producer_id":"g5_license","launch_spec_id":"g5_license","schema":"gate-status.schema.json","payload_schema":"release/evidence/license.schema.json","depends_on":[{"gate":"G5","filename":"public-export.json","receipt_sha256_pointer":"/dependency_receipts/public-export.json"}],"material_edges":[{"material_id":"product_license","kind":"repository_file","authority_id":"public_export","path":"LICENSE","sha256_pointer":"/material_digests/product_license","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/license.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","public_export_tree","product_license","third_party_notices","license_report"]}]},
    {"filename":"security.json","producer_id":"g5_security","launch_spec_id":"g5_security","schema":"gate-status.schema.json","payload_schema":"release/evidence/security.schema.json","depends_on":[{"gate":"G5","filename":"license.json","receipt_sha256_pointer":"/dependency_receipts/license.json"},{"gate":"G3","filename":"g3-lifecycle.json","receipt_sha256_pointer":"/dependency_receipts/g3-lifecycle.json"},{"gate":"G3","filename":"g3-reliability.json","receipt_sha256_pointer":"/dependency_receipts/g3-reliability.json"}],"material_edges":[{"material_id":"security_review_scope","kind":"repository_file","authority_id":"product_source","path":"release/security-review-scope.json","sha256_pointer":"/material_digests/security_review_scope","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/security.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["subject","product_source_tree","public_export_tree","artifact_manifest","asset_closure","security_scope","reviewer_roles","implementation_actors","tool_lock","sast_input_closure"]}]},
    {"filename":"security-review.json","producer_id":"g5_security_review","launch_spec_id":"g5_security_review","schema":"gate-status.schema.json","payload_schema":"release/evidence/security-review-receipt.schema.json","depends_on":[{"gate":"G5","filename":"security.json","receipt_sha256_pointer":"/dependency_receipts/security.json"}],"material_edges":[{"material_id":"security_findings","kind":"evidence_file","authority_id":"evidence","path":"security-findings.json","sha256_pointer":"/material_digests/security_findings","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/security-review.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["request","input","findings","scope","reviewer_roles","implementation_actors"]}]},
    {"filename":"artifacts.json","producer_id":"g5_artifacts","launch_spec_id":"g5_artifacts","schema":"gate-status.schema.json","payload_schema":"release/evidence/artifacts.schema.json","depends_on":[{"gate":"G5","filename":"security-review.json","receipt_sha256_pointer":"/dependency_receipts/security-review.json"},{"gate":"G3","filename":"g3-lifecycle.json","receipt_sha256_pointer":"/dependency_receipts/g3-lifecycle.json"}],"material_edges":[{"material_id":"artifact_manifest","kind":"release_asset","authority_id":"release_assets","path":"artifact-manifest.json","sha256_pointer":"/material_digests/artifact_manifest","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/artifacts.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["release_index","release_index_bundle","artifact_manifest","asset_closure","signing_policy","verifier_bootstrap"]}]}
  ],
  "G6": [
    {"filename":"first-user.json","producer_id":"g6_first_user","launch_spec_id":"g6_first_user","schema":"gate-status.schema.json","payload_schema":"release/evidence/first-user.schema.json","depends_on":[{"gate":"G5","filename":"artifacts.json","receipt_sha256_pointer":"/dependency_receipts/artifacts.json"}],"material_edges":[{"material_id":"first_user_runner_bundle","kind":"evidence_file","authority_id":"evidence","path":"first-user-runner-bundle/first-user-runner-bundle.json","sha256_pointer":"/material_digests/first_user_runner_bundle","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/first-user.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["runner_receipt","runner_bundle","scenario","runner_roles","implementation_actors","artifact_manifest","asset_closure","release_python_lock"]}]},
    {"filename":"dogfood-summary.json","producer_id":"g6_dogfood_summary","launch_spec_id":"g6_dogfood_summary","schema":"gate-status.schema.json","payload_schema":"release/evidence/dogfood-summary.schema.json","depends_on":[{"gate":"G6","filename":"first-user.json","receipt_sha256_pointer":"/dependency_receipts/first-user.json"},{"gate":"G4","filename":"g4-independent-rerun.json","receipt_sha256_pointer":"/dependency_receipts/g4-independent-rerun.json"}],"material_edges":[{"material_id":"dogfood_policy","kind":"repository_file","authority_id":"product_source","path":"dogfood/policy.json","sha256_pointer":"/material_digests/dogfood_policy","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/dogfood-summary.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["policy","plan","transparency_plan","transparency_authorization","workstream_bindings","installation_receipt","event_log","anchor_closure","issue_ledger"]}]},
    {"filename":"issues.json","producer_id":"g6_issues","launch_spec_id":"g6_issues","schema":"gate-status.schema.json","payload_schema":"release/evidence/issues.schema.json","depends_on":[{"gate":"G6","filename":"dogfood-summary.json","receipt_sha256_pointer":"/dependency_receipts/dogfood-summary.json"}],"material_edges":[{"material_id":"dogfood_issue_ledger","kind":"evidence_file","authority_id":"evidence","path":"dogfood-issues.json","sha256_pointer":"/material_digests/dogfood_issue_ledger","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/issues.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["issue_ledger","plan"]}]}
  ],
  "G7": [
    {"filename":"publication-security-refresh.json","producer_id":"g7_security_refresh","launch_spec_id":"g7_security_refresh","schema":"gate-status.schema.json","payload_schema":"release/evidence/publication-security-refresh.schema.json","depends_on":[{"gate":"G5","filename":"security.json","receipt_sha256_pointer":"/dependency_receipts/security.json"},{"gate":"G5","filename":"security-review.json","receipt_sha256_pointer":"/dependency_receipts/security-review.json"},{"gate":"G5","filename":"artifacts.json","receipt_sha256_pointer":"/dependency_receipts/artifacts.json"},{"gate":"G6","filename":"issues.json","receipt_sha256_pointer":"/dependency_receipts/issues.json"},{"gate":"G4","filename":"g4-independent-rerun.json","receipt_sha256_pointer":"/dependency_receipts/g4-independent-rerun.json"}],"material_edges":[{"material_id":"sast_lock","kind":"repository_file","authority_id":"public_export","path":"requirements/sast.lock","sha256_pointer":"/material_digests/sast_lock","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/publication-security-refresh.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["artifact_manifest","asset_closure","runtime_security_closure","sbom_closure","sast_lock","sast_rules","scanner_lock","signed_review","advisory_feed_closure"]}]},
    {"filename":"github-publication.json","producer_id":"g7_github_publication","launch_spec_id":"g7_github_publication","schema":"gate-status.schema.json","payload_schema":"release/evidence/github-publication.schema.json","depends_on":[{"gate":"G0","filename":"g0-workspace.json","receipt_sha256_pointer":"/dependency_receipts/g0-workspace.json"},{"gate":"G1","filename":"g1.json","receipt_sha256_pointer":"/dependency_receipts/g1.json"},{"gate":"G2","filename":"g2-map-quality.json","receipt_sha256_pointer":"/dependency_receipts/g2-map-quality.json"},{"gate":"G3","filename":"g3-contracts.json","receipt_sha256_pointer":"/dependency_receipts/g3-contracts.json"},{"gate":"G3","filename":"g3-lifecycle.json","receipt_sha256_pointer":"/dependency_receipts/g3-lifecycle.json"},{"gate":"G3","filename":"g3-reliability.json","receipt_sha256_pointer":"/dependency_receipts/g3-reliability.json"},{"gate":"G4","filename":"g4-benchmark.json","receipt_sha256_pointer":"/dependency_receipts/g4-benchmark.json"},{"gate":"G4","filename":"g4-independent-rerun.json","receipt_sha256_pointer":"/dependency_receipts/g4-independent-rerun.json"},{"gate":"G5","filename":"provenance.json","receipt_sha256_pointer":"/dependency_receipts/provenance.json"},{"gate":"G5","filename":"public-export.json","receipt_sha256_pointer":"/dependency_receipts/public-export.json"},{"gate":"G5","filename":"license.json","receipt_sha256_pointer":"/dependency_receipts/license.json"},{"gate":"G5","filename":"security.json","receipt_sha256_pointer":"/dependency_receipts/security.json"},{"gate":"G5","filename":"security-review.json","receipt_sha256_pointer":"/dependency_receipts/security-review.json"},{"gate":"G5","filename":"artifacts.json","receipt_sha256_pointer":"/dependency_receipts/artifacts.json"},{"gate":"G6","filename":"first-user.json","receipt_sha256_pointer":"/dependency_receipts/first-user.json"},{"gate":"G6","filename":"dogfood-summary.json","receipt_sha256_pointer":"/dependency_receipts/dogfood-summary.json"},{"gate":"G6","filename":"issues.json","receipt_sha256_pointer":"/dependency_receipts/issues.json"},{"gate":"G7","filename":"publication-security-refresh.json","receipt_sha256_pointer":"/dependency_receipts/publication-security-refresh.json"}],"material_edges":[{"material_id":"g8_seed_install_receipt","kind":"evidence_file","authority_id":"evidence","path":"g8-seed-install.json","sha256_pointer":"/material_digests/g8_seed_install_receipt","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/github-publication.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["publication_plan","authorization","start_receipt","journal","result_receipt","github_controls","security_refresh","g8_seed_install_receipt","public_evidence_closure"]}]},
    {"filename":"public-smoke.json","producer_id":"g7_public_smoke","launch_spec_id":"g7_public_smoke","schema":"gate-status.schema.json","payload_schema":"release/evidence/public-smoke.schema.json","depends_on":[{"gate":"G7","filename":"publication-security-refresh.json","receipt_sha256_pointer":"/dependency_receipts/publication-security-refresh.json"},{"gate":"G7","filename":"github-publication.json","receipt_sha256_pointer":"/dependency_receipts/github-publication.json"}],"material_edges":[{"material_id":"release_index","kind":"release_asset","authority_id":"release_assets","path":"release-index.json","sha256_pointer":"/material_digests/release_index","canonicalization":"raw_bytes"},{"material_id":"producer_inputs","kind":"input_manifest","authority_id":"evidence","path":"inputs/public-smoke.inputs.json","sha256_pointer":"/material_digests/producer_inputs","canonicalization":"jcs","required_roles":["publication_receipt","github_controls","security_refresh","g8_seed_install_receipt","signing_policy","verifier_bootstrap","release_index","release_index_bundle","artifact_manifest","asset_closure","public_evidence_closure"]}]}
  ]
}
~~~

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_release_gate.py -q
C:\Python311\python.exe -m pytest tests/release/test_release_python.py -q
C:\Python311\python.exe -m pytest tests/release/test_review_role_runner.py -q
~~~

Expected: collection fails because tools.release_gate, tools.bootstrap_release_python, and the authenticated tools.review_role_runner do not exist.

**Step 3: Implement the minimum gate**

~~~python
class GateResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNVERIFIABLE = "unverifiable"


def subject_digest(subject: Mapping[str, object]) -> str:
    payload = json.dumps(subject, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def check_gate(
    gate: str,
    subject_path: Path,
    evidence_dir: Path,
    *,
    registry_extension: Path | None = None,
    verification_context: VerificationContext,
) -> GateResult:
    """Validate subject-bound receipts and recompute every declared dependency/material edge."""
~~~

release/evidence/.gitignore ignores release-subject.json, all gate receipts, verifier-owned input manifests, `pre-public-sast.json`, `runner-availability.json`, `runner-attestations/`, `first-user-runner-bundle/`, `g8-seed-install.json`, the three full security-review ledgers, `public-evidence-assets.json`, JSONL event logs, downloaded DOM/screenshots, and authorization/submission data while retaining schemas, README.md, receipt-registry.schema.json, and receipt-registry.json. The root `.gitignore` ignores G4 staging under `release/staging/g4/` and G6 staged assets under `release/assets/`. The verifier rejects a receipt, review ledger, runner record, ancillary evidence manifest, or staged runtime asset that Git reports as tracked.

`requirements/release.lock` is created before any signed-review task and is the single hashed Python dependency closure for provenance, security, G6 first-user, and private application-review Ed25519 producers/verifiers. It pins `cryptography==45.0.5` plus every transitive wheel/sdist hash needed on supported Python 3.11 hosts. `tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python` installs with `pip --require-hashes` into an ignored digest-addressed environment, verifies the interpreter/module versions, and returns its absolute Python path. Those cryptographic tools refuse ambient Python and record the lock/interpreter digests; G4 remains governed by its own frozen `uv.lock` environment.

`tools/review_role_runner.py` is already available and tested in Task 1, before any Task 2 signature is created. Its minimum authenticated role-launch contract validates the signed-environment registry and exact role/credential/allowed-key tuple, derives the forbidden environment set as registry-minus-allowed, rejects any caller-provided set that is not exactly equal, starts a fresh closed-environment child, obtains the one named OS credential only inside that child, rejects every other actual environment name matching the registry's reserved pattern (including names added by future registry versions), and supports a separate keyless verifier mode. Later Task 5 extends policy fixtures, not the credential boundary.

**Step 4: Run GREEN**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_release_gate.py -q
C:\Python311\python.exe -m pytest tests/release/test_release_python.py -q
C:\Python311\python.exe -m pytest tests/release/test_review_role_runner.py -q
C:\Python311\python.exe tools/bootstrap_release_python.py verify-lock --lock requirements/release.lock
C:\Python311\python.exe tools/release_gate.py validate-registry --registry release/evidence/receipt-registry.json --registry-schema release/evidence/receipt-registry.schema.json --subject-schema release/evidence/release-subject.schema.json --receipt-schema release/evidence/gate-status.schema.json
C:\Python311\python.exe tools/generate_producer_launch_policy.py sync --through-phase G5_TASK1 --registry release/evidence/receipt-registry.json --out release/evidence/producer-launch-policy.json
C:\Python311\python.exe tools/generate_producer_launch_policy.py check --through-phase G5_TASK1 --registry release/evidence/receipt-registry.json --policy release/evidence/producer-launch-policy.json --schema release/evidence/producer-launch-policy.schema.json
C:\Python311\python.exe tools/release_gate.py validate-signing-env-registry --registry release/signing-environment-registry.json --schema release/signing-environment-registry.schema.json --launch-policy release/evidence/producer-launch-policy.json --require-exact-forbidden-closure
~~~

Expected: tests and registry/schema validation exit 0. No live ReleaseSubject or gate receipt is created during this implementation task; F5 performs that external evidence run.

**Step 5: Commit**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('release/evidence/.gitignore','release/evidence/release-subject.schema.json','release/evidence/gate-candidate.schema.json','release/evidence/gate-status.schema.json','release/evidence/receipt-registry.schema.json','release/evidence/material-input-manifest.schema.json','release/evidence/producer-launch-policy.schema.json','release/evidence/producer-launch-policy.json','release/evidence/receipt-registry.json','release/signing-environment-registry.schema.json','release/signing-environment-registry.json','release/evidence/README.md','requirements/release.lock','tools/bootstrap_release_python.py','tools/release_gate.py','tools/generate_producer_launch_policy.py','tools/review_role_runner.py','tests/release/test_release_gate.py','tests/release/test_release_python.py','tests/release/test_review_role_runner.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'release: define immutable subject and receipt registry'
~~~

### Task 2: Establish the source-provenance ledger and isolated review protocol

**Files:**

- Create: provenance/prior-art-ledger.json
- Create: provenance/source-policy.json
- Create: provenance/implementation-actors.json
- Create: provenance/review.schema.json
- Create: provenance/reviewer-roles.json
- Generate then track: provenance/reviews/prior-art-review.json
- Create: provenance/review-policy.md
- Create: provenance/receipt.schema.json
- Create: tools/provenance_review.py
- Create: tools/provenance_audit.py
- Create: tests/release/test_provenance.py
- Create: PROVENANCE.md
- Create: THIRD_PARTY_NOTICES.md

**Step 1: Write the failing provenance tests**

~~~python
def test_unresolved_copy_language_blocks_release(repo_root: Path) -> None:
    findings = audit_source(repo_root, load_ledger(repo_root))
    assert not [f for f in findings if f.code == "UNRESOLVED_DERIVATION"]


def test_every_shipped_source_is_covered_once_by_authorship_policy(repo_root: Path) -> None:
    policy = SourcePolicy.load(repo_root / "provenance/source-policy.json")
    coverage = policy.cover(shipped_source_paths(repo_root))
    assert coverage.uncovered == ()
    assert coverage.multiply_covered == ()


def test_review_conclusion_is_hash_bound(review: ReviewReceipt) -> None:
    assert all(len(item.product_sha256) == 64 for item in review.items)
    assert all(sha256_file(item.product_path) == item.product_sha256 for item in review.items)


def test_review_is_independent_and_ledger_binds_its_digest(review, ledger) -> None:
    assert review.reviewer_id not in review.implementation_actor_ids
    assert len(review.reviewer_process_digest) == 64
    assert verify_reviewer_signature(review, load_reviewer_roles()).status == "pass"
    assert ledger.review_receipt_sha256 == canonical_sha256(review)


def test_release_receipt_requires_sigstore_bundle_for_review(review, release_assets) -> None:
    asset = release_assets.by_kind("provenance_review")
    assert asset.sha256 == sha256_file(review.path)
    assert asset.sigstore_required is True
    assert asset.signature_bundle_filename


def test_provenance_signer_is_fresh_child_only_and_verifier_is_keyless() -> None:
    inventory = load_signing_environment_registry()
    registered = {row["key_env"] for row in inventory["roles"]}
    allowed = "CODESEXTANT_PROVENANCE_REVIEWER_SIGNING_KEY"
    launch = build_role_launch(role="independent_provenance_reviewer", allowed=allowed)
    assert set(launch.forbidden_key_env) == registered - {allowed}
    assert launch_with_parent_env({allowed: "must-not-be-here"}, launch).status == "fail"
    signer = launch_with_parent_env({}, launch)
    assert signer.parent_visible_signing_keys == set()
    assert signer.child_visible_signing_keys == {allowed}
    verifier = launch_keyless_verifier(polluted_parent_environment=False)
    assert verifier.visible_signing_keys == set()
    assert verifier.environment_names.isdisjoint(registered)
~~~

The first RED run must identify codesextant/namegraph.py and codesextant/ranking.py as unresolved. The ledger contains entries for Aider repository map, MOSS winnowing, PageRank, Sonar Cognitive Complexity, tree-sitter, Jedi, ts-morph, and SQLite WAL.

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_provenance.py -q
~~~

Expected: FAIL because the ledger and audit module are absent; once skeleton files exist, FAIL with UNRESOLVED_DERIVATION for the two Aider comments.

**Step 3: Implement the audit model**

~~~python
class ProvenanceDisposition(str, Enum):
    INDEPENDENT_IDEA = "independent_idea"
    LICENSED_DERIVATION = "licensed_derivation"
    CLEAN_ROOM_REWRITE_REQUIRED = "clean_room_rewrite_required"


@dataclass(frozen=True)
class ReviewItem:
    product_path: str
    product_sha256: str
    prior_art_url: str
    prior_art_commit: str
    source_sha256: str
    disposition: ProvenanceDisposition
    rationale: str


@dataclass(frozen=True)
class ReviewReceipt:
    schema_version: int
    reviewer_id: str
    reviewer_key_id: str
    reviewer_role: Literal["independent_provenance_reviewer"]
    reviewer_process_digest: str
    implementation_actor_ids: tuple[str, ...]
    product_manifest_sha256: str
    prior_art_manifest_sha256: str
    issued_at_utc: datetime
    items: tuple[ReviewItem, ...]
    conclusion: Literal["pass", "rewrite_required", "license_action_required"]
    signature_ed25519: str


def audit_source(repo_root: Path, ledger: PriorArtLedger) -> list[Finding]:
    """Block unrecorded shipped files, unresolved derivation language, and stale review hashes."""
~~~

provenance/source-policy.json contains non-overlapping shipped-path rules, authorship class, owner, and required review disposition; it does not snapshot a path list that becomes stale when later G5/G6 files are added. Every full test/F1 run expands the rules against the live tracked tree and fails on an uncovered or multiply covered shipped path. The final enumerated source manifest is generated from the frozen source/export trees under `release/evidence/source-manifest.json`, outside Git.

The independent reviewer works from an isolated competitor checkout and compares tokens/AST structure where technically possible. `provenance/reviewer-roles.json` precommits reviewer IDs, roles, and Ed25519 public keys; private keys never enter the repository, argv, logs, or product implementer context. `tools/provenance_review.py emit` hashes the complete product input manifest and isolated prior-art manifest, requires reviewer identity/process digest and implementation actor roster, rejects overlap, signs the canonical payload with the reviewer-owned key, and emits schema-valid bytes. The product implementer receives only this receipt. `provenance_audit.py bind-review` first verifies the reviewer signature/role/separation, then writes only its digest into the ledger; all later audits repeat that verification. If the disposition is licensed_derivation, THIRD_PARTY_NOTICES.md and LICENSES entries are mandatory. If clean_room_rewrite_required, a fresh implementer receives only behavior tests and the abstract interface.

The reviewer-owned Ed25519 signature proves authorship under the precommitted role policy. During the authorized private artifact workflow, pinned cosign additionally keyless-signs this exact blob through GitHub OIDC/Rekor to prove workflow/time inclusion. Its bundle and certificate identity become typed `provenance_review`/`signature_bundle` release assets. The final G5 provenance receipt verifies both layers and the exact receipt digest before passing.

PROVENANCE.md must state that the current Git history begins 2026-07-19 and cannot by itself prove earlier independent authorship. Earlier internal design files and SHA receipts are supporting evidence, not third-party timestamp proof.

**Step 4: Run GREEN and record the independent decision**

Run:

~~~powershell
$reviewerId = $env:CODESEXTANT_PROVENANCE_REVIEWER_ID
$reviewerProcessDigest = $env:CODESEXTANT_PROVENANCE_REVIEWER_PROCESS_SHA256
if (-not $reviewerId -or $reviewerProcessDigest -notmatch '^[0-9a-f]{64}$') { throw 'independent reviewer identity/process evidence is required' }
$releasePython = & C:\Python311\python.exe tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python
if ($LASTEXITCODE -ne 0) { throw 'locked release Python bootstrap failed' }
$signingEnvRegistryPath = 'release/signing-environment-registry.json'
$signingEnvRegistry = Get-Content -Raw -Encoding UTF8 -LiteralPath $signingEnvRegistryPath | ConvertFrom-Json
$allowedKeyEnv = 'CODESEXTANT_PROVENANCE_REVIEWER_SIGNING_KEY'
$registeredKeyEnvs = @($signingEnvRegistry.roles | ForEach-Object { [string]$_.key_env })
$uniqueRegisteredKeyEnvs = @($registeredKeyEnvs | Sort-Object -Unique)
if ($registeredKeyEnvs.Count -ne $uniqueRegisteredKeyEnvs.Count -or $allowedKeyEnv -notin $registeredKeyEnvs) { throw 'invalid signing-environment registry closure' }
$ambientReserved = @(Get-ChildItem Env: | Where-Object { $_.Name -match [string]$signingEnvRegistry.reserved_pattern })
if ($ambientReserved.Count -ne 0) { throw "signing keys must not exist in the parent shell: $($ambientReserved.Name -join ',')" }
$forbiddenKeyEnvs = @($registeredKeyEnvs | Where-Object { $_ -cne $allowedKeyEnv } | Sort-Object -CaseSensitive)
$signerLaunch = @('run','--role','independent_provenance_reviewer','--credential-name','codesextant/g5/provenance-reviewer','--allowed-key-env',$allowedKeyEnv,'--signing-env-registry',$signingEnvRegistryPath,'--reserved-key-env-pattern',[string]$signingEnvRegistry.reserved_pattern)
foreach ($name in $forbiddenKeyEnvs) { $signerLaunch += @('--forbidden-key-env',$name) }
& $releasePython tools/review_role_runner.py @signerLaunch -- $releasePython tools/provenance_review.py emit --root . --ledger provenance/prior-art-ledger.json --reviewer-id $reviewerId --reviewer-process-digest $reviewerProcessDigest --reviewer-roles provenance/reviewer-roles.json --signing-key-env $allowedKeyEnv --implementation-actors provenance/implementation-actors.json --out provenance/reviews/prior-art-review.json
if ($LASTEXITCODE -ne 0) { throw 'fresh provenance reviewer child failed' }
& $releasePython tools/review_role_runner.py run-keyless --signing-env-registry $signingEnvRegistryPath --reserved-key-env-pattern ([string]$signingEnvRegistry.reserved_pattern) -- $releasePython tools/provenance_review.py verify --review provenance/reviews/prior-art-review.json --schema provenance/review.schema.json --reviewer-roles provenance/reviewer-roles.json --implementation-actors provenance/implementation-actors.json
if ($LASTEXITCODE -ne 0) { throw 'separate keyless provenance verifier failed' }
& $releasePython tools/provenance_audit.py bind-review --ledger provenance/prior-art-ledger.json --review provenance/reviews/prior-art-review.json
if ($LASTEXITCODE -ne 0) { throw 'provenance review binding failed' }
& $releasePython tools/provenance_audit.py scan --root . --ledger provenance/prior-art-ledger.json
if ($LASTEXITCODE -ne 0) { throw 'provenance scan failed' }
& $releasePython -m pytest tests/release/test_provenance.py -q
if ($LASTEXITCODE -ne 0) { throw 'provenance tests failed' }
~~~

Expected: both exit 0 only after every unresolved item has a hash-bound reviewer disposition and any required rewrite/license work is complete.

**Step 5: Commit**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('provenance/prior-art-ledger.json','provenance/source-policy.json','provenance/implementation-actors.json','provenance/review.schema.json','provenance/reviewer-roles.json','provenance/review-policy.md','provenance/receipt.schema.json','provenance/reviews/prior-art-review.json','PROVENANCE.md','THIRD_PARTY_NOTICES.md','tools/provenance_review.py','tools/provenance_audit.py','tests/release/test_provenance.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'docs: establish auditable source provenance'
~~~

### Task 3: Build and audit the allowlist public export

**Files:**

- Create: release/public-export.toml
- Create: release/public-author-map.toml
- Create: release/private-patterns.toml
- Create: release/evidence/public-export.schema.json
- Create: tools/public_export.py
- Modify: tools/check_map_quality.py
- Create: tests/release/test_public_export.py
- Create: tests/release/private_history_fixture.py

**Step 1: Write RED tests**

~~~python
def test_prepare_export_contains_only_allowlisted_paths(tmp_path: Path) -> None:
    receipt = prepare_export(REPO, tmp_path / "export", CONFIG)
    assert set(receipt.exported_paths) == set(receipt.allowlisted_paths)


def test_private_application_tooling_is_never_exported(tmp_path: Path) -> None:
    receipt = prepare_export(REPO, tmp_path / "export", CONFIG)
    normalized = tuple(path.replace("\\", "/") for path in receipt.exported_paths)
    assert not any(path.startswith("application/claude-for-oss/") for path in normalized)
    assert not any(path.startswith("tests/application/") for path in normalized)
    assert not any(path.startswith("docs/superpowers/plans/") for path in normalized)
    assert not any(path.startswith("docs/superpowers/specs/") for path in normalized)


@pytest.mark.parametrize(
    "needle",
    [
        "_poc_graph_c",
        "交接_CodeSextant.md",
        "E:\\\\ai-king",
        "C:\\\\Users\\\\zerox",
        "coverage_report.json",
        "tools/stress_out.txt",
        "zeroxrain99@gmail.com",
    ],
)
def test_audit_export_scans_every_commit(tmp_path: Path, needle: str) -> None:
    repo = history_fixture_with_secret(tmp_path, needle)
    assert any(f.code == "PRIVATE_HISTORY_MATCH" for f in audit_export(repo))


def test_authoritative_g2_receipt_is_export_bound_not_private_source_bound(
    frozen_subject, source_repo: Path, export_repo: Path
) -> None:
    expectations = export_repo / "tests/fixtures/map_gate_expectations.json"
    receipt = emit_map_quality_receipt(
        repo=export_repo,
        expectations=expectations,
        subject=frozen_subject,
    )
    mutate_excluded_private_source_only(source_repo)
    assert verify_map_quality_receipt(receipt, frozen_subject, export_repo).status == "pass"
    mutate_tracked_export_file(export_repo)
    assert verify_map_quality_receipt(receipt, frozen_subject, export_repo).status == "fail"


def test_authoritative_receipt_rejects_private_source_as_export_root(
    frozen_subject, source_repo: Path
) -> None:
    assert emit_map_quality_receipt(
        repo=source_repo,
        expectations=source_repo / "tests/fixtures/map_gate_expectations.json",
        subject=frozen_subject,
    ).status == "fail"


def test_g2_receipt_rejects_expectations_outside_the_same_authoritative_export(
    frozen_subject, export_repo: Path, private_source_repo: Path
) -> None:
    assert emit_map_quality_receipt(
        repo=export_repo,
        expectations=private_source_repo / "tests/fixtures/map_gate_expectations.json",
        subject=frozen_subject,
    ).status == "fail"


def test_final_freeze_receipt_argv_binds_g0_and_g2_to_the_same_export() -> None:
    commands = final_freeze_receipt_argv()
    assert commands["G0"] == (
        "C:/Python311/python.exe", "tools/verify_g0.py", "receipt",
        "--subject", "$subject", "--export-root", "$exportRoot",
        "--out", "release/evidence/g0-workspace.json",
    )
    assert commands["G2"] == (
        "C:/Python311/python.exe", "tools/check_map_quality.py", "receipt",
        "--repo", "$exportRoot", "--scope", "product", "--budget", "12000",
        "--min-results", "50", "--required-class", "first_party_source",
        "--expectations", "$exportRoot/tests/fixtures/map_gate_expectations.json",
        "--subject", "$subject", "--out", "release/evidence/g2-map-quality.json",
    )
~~~

`tests/release/private_history_fixture.py` creates the multi-commit repository under `tmp_path` at test time, configures a local test author, commits the denied value in an old revision, removes it in the tip, and returns the repository path. Do not track a nested `.git` directory or gitlink as a fixture; a fresh clone of CodeSextant must be able to generate the same history locally.

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_public_export.py -q
~~~

Expected: FAIL because tools.public_export does not exist.

**Step 3: Implement the export contract**

~~~python
@dataclass(frozen=True)
class ExportReceipt:
    source_commit: str
    source_tree_sha256: str
    export_commit: str
    export_tree_sha256: str
    config_sha256: str
    exported_paths: tuple[str, ...]
    allowlisted_paths: tuple[str, ...]
    history_commits_scanned: int
    findings: tuple[Finding, ...]


def prepare_export(source_repo: Path, dest: Path, config: Path) -> ExportReceipt:
    """Create a disposable clone, retain allowlisted paths/history, then audit all commits."""


def audit_export(repo: Path) -> list[Finding]:
    """Scan every reachable commit plus the worktree for secrets, paths, emails, and denied files."""
~~~

The allowlist includes product crates/packages, tests required to reproduce product and benchmark claims, deliberately authored public docs, benchmark protocol/locks/results, governance, install/release tooling, and licenses. "Public docs" is an explicit path allowlist, never the whole `docs/` tree. It excludes all internal `docs/superpowers/plans/` and `docs/superpowers/specs/` artifacts because those may contain private paths, account/email targeting, unreleased architecture, review identities, and application operations. It also explicitly excludes the entire `application/claude-for-oss/` and `tests/application/` trees, release/evidence raw receipts containing private identifiers, internal handoffs, _poc_graph_c, coverage/stress output, cache/database files, and AI King-only tools. The real-tree dry run scans the resulting export's entire reachable history and worktree for every denied value; a plan/spec path or private identifier is a hard failure even if the tip later deletes it.

Author mapping is explicit and deterministic. The tool never invokes filter-repo against the source path and refuses when destination is not empty. `tools/public_export.py assert-authoritative-root` recomputes the candidate repository commit and allowlist tree SHA-256 and requires both to equal `ReleaseSubject.export_commit` and `ReleaseSubject.export_tree_sha256`; it also rejects the subject's private `source_commit`/`source_tree_sha256` pair when those identities differ. `tools/verify_g0.py receipt` and `tools/check_map_quality.py receipt` must call that guard before executing and both require the same explicit authoritative export root. G0 records the complete allowlist export/classification closure. G2 additionally requires `--expectations <export-root>/tests/fixtures/map_gate_expectations.json`, resolves it beneath that same no-link authoritative root, rejects a private-source/outside/aliased fixture even when its bytes match, recomputes its path and digest from the export inventory, and records the normalized export root plus reviewed expectation/tree digests under its domain payload. A source-only diagnostic may still run before freeze, but it has `authority=diagnostic`, cannot use the registry filename, and cannot be wrapped as G2 evidence. The source-only/export-mutation tests prove that changing excluded private files does not affect an already frozen exported conclusion while changing any shipped export byte or the exported expectation fixture invalidates it.

**Step 4: Run GREEN and a real-tree dry run**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_public_export.py -q
$dest = Join-Path $env:TEMP ("codesextant-public-export-test-" + [Guid]::NewGuid().ToString("N"))
$dryReceipt = Join-Path $env:TEMP ("codesextant-public-export-receipt-" + [Guid]::NewGuid().ToString("N") + ".json")
C:\Python311\python.exe tools/public_export.py prepare --source . --dest $dest --config release/public-export.toml --diagnostic-receipt $dryReceipt
C:\Python311\python.exe tools/public_export.py audit --repo $dest
~~~

Expected: all commands exit 0 and the diagnostic receipt names the current source/export commits plus deterministic allowlist tree SHA-256 values. It is not the registry-named G5 receipt and is deleted with the disposable export. `release/evidence/public-export.json` is emitted only after ReleaseSubject freezes in F5.

**Step 5: Commit**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('release/public-export.toml','release/public-author-map.toml','release/private-patterns.toml','release/evidence/public-export.schema.json','tools/public_export.py','tools/check_map_quality.py','tests/release/test_public_export.py','tests/release/private_history_fixture.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'release: add allowlist-based public export'
~~~

### Task 4: Lock dependencies and enforce license policy

**Dependencies:** G0/G1 workspace manifest, G2/G3 product-license task, and native-kernel Task 6 (both compiled sidecar manifests and locks must already exist).

**Files:**

- Modify: .gitignore
- Create: release/toolchain.lock
- Create: tools/bootstrap_release_tools.py
- Create: tests/release/test_release_toolchain.py
- Create: requirements/runtime.lock
- Create: requirements/test.lock
- Modify: ts/package.json
- Modify: ts_bridge/.gitignore
- Modify: ts_bridge/package.json
- Track: ts_bridge/package-lock.json
- Create: deny.toml
- Create: REUSE.toml
- Create: LICENSES/Apache-2.0.txt
- Create: release/evidence/license.schema.json
- Create: tools/license_audit.py
- Create: tests/release/test_license_policy.py

**Step 1: Write RED tests**

~~~python
def test_every_ecosystem_has_a_reproducible_lock(repo_root: Path) -> None:
    assert (repo_root / "Cargo.lock").is_file()
    for lock in (
        repo_root / "requirements/runtime.lock",
        repo_root / "requirements/test.lock",
        repo_root / "sidecars/python/requirements.lock",
    ):
        assert requirements_are_fully_hashed(lock)
    for lock in (
        repo_root / "ts/package-lock.json",
        repo_root / "ts_bridge/package-lock.json",
        repo_root / "sidecars/typescript/package-lock.json",
    ):
        assert read_npm_lock_version(lock) == 3
        assert npm_lock_has_exact_versions_and_integrities(lock)
    assert not is_git_ignored(repo_root / "ts_bridge/package-lock.json")


def test_release_crypto_dependency_is_exactly_locked_with_hashes(repo_root: Path) -> None:
    lock = parse_hashed_requirements(repo_root / "requirements/release.lock")
    assert lock["cryptography"].version == "45.0.5"
    assert lock["cryptography"].hashes
    assert all(dep.hashes for dep in transitive_closure(lock, "cryptography"))


def test_dependency_license_allowlist_is_complete(repo_root: Path) -> None:
    result = audit_licenses(repo_root)
    assert result.unknown == ()
    assert result.incompatible == ()


def test_authoritative_license_receipt_binds_exact_shipped_export(
    frozen_subject, source_repo: Path, export_repo: Path
) -> None:
    receipt = emit_license_receipt(root=export_repo, subject=frozen_subject)
    mutate_excluded_private_source_only(source_repo)
    assert verify_license_receipt(receipt, frozen_subject, export_repo).status == "pass"
    mutate_exported_license_or_lock(export_repo)
    assert verify_license_receipt(receipt, frozen_subject, export_repo).status == "fail"


def test_license_receipt_rejects_source_checkout_even_if_local_audit_passes(
    frozen_subject, source_repo: Path
) -> None:
    assert audit_licenses(source_repo).status == "pass"
    assert emit_license_receipt(root=source_repo, subject=frozen_subject).status == "fail"


def test_product_license_is_apache_2_everywhere(repo_root: Path) -> None:
    expected = "Apache-2.0"
    assert read_pyproject_license(repo_root) == expected
    assert read_pyproject_classifier(repo_root) == "License :: OSI Approved :: Apache Software License"
    assert read_cargo_workspace_license(repo_root) == expected
    assert read_package_license(repo_root / "ts/package.json") == expected
    assert read_package_license(repo_root / "ts_bridge/package.json") == expected
    assert read_package_license(repo_root / "sidecars/typescript/package.json") == expected
    assert (repo_root / "LICENSE").read_bytes() == (repo_root / "LICENSES/Apache-2.0.txt").read_bytes()
    assert read_reuse_default_license(repo_root) == expected
    assert notice_identifies_codesextant(repo_root / "NOTICE")


def test_release_tools_are_exact_and_checksummed(tool_lock: ToolLock) -> None:
    assert tool_lock.versions == {
        "actionlint": "1.7.12",
        "cargo-audit": "0.22.2",
        "cargo-deny": "0.20.2",
        "cyclonedx-bom": "7.3.0",
        "cosign": "3.1.2",
        "gitleaks": "8.30.1",
        "reuse": "6.2.0",
        "syft": "1.49.0",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", asset.sha256) for asset in tool_lock.assets)
~~~

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_release_toolchain.py tests/release/test_license_policy.py -q
~~~

Expected: FAIL because the tool/dependency locks and policy are absent and ts_bridge/package-lock.json is ignored.

**Step 3: Implement deterministic locks and policy**

release/toolchain.lock pins the eight versions asserted above, each distribution kind and executable entry point, and every Windows/Linux/macOS download by immutable official URL and SHA-256. The pin command downloads official checksum/signature metadata, verifies it, computes the actual asset digest, and writes canonical sorted JSON; verify refuses a mutable latest URL, a missing platform, a missing entry point, or a digest mismatch. Tools install only under gitignored .release-tools/.

Generate runtime/test Python locks from exact hashes for Python 3.10-3.13 supported wheels/sdists, while preserving the earlier `requirements/release.lock` as the sole release-cryptography authority. This task revalidates that its `cryptography==45.0.5` transitive closure remains fully hashed but does not create a competing lock or bootstrap. npm lockfiles use lockfileVersion 3. deny.toml denies unmaintained/yanked advisories and non-approved licenses, with any exception containing package, version, reason, owner, and expiry date. The already-created top-level `LICENSE`, `NOTICE`, `pyproject.toml`, and Cargo workspace metadata remain the product-license authority from the pre-freeze contract task. The native plan already creates `sidecars/typescript/package.json` as `Apache-2.0`; this task sets the remaining `ts` and `ts_bridge` manifests and then requires all three Node package manifests to agree. Store the unmodified canonical license text at `LICENSES/Apache-2.0.txt`; require byte-identical canonical text at the top-level `LICENSE`; and make REUSE.toml map product-owned shipped files to SPDX `Apache-2.0` unless a narrower third-party notice applies. Do not alter dependency, vendored, fixture, grammar, corpus, or competitor licenses.

~~~python
@dataclass(frozen=True)
class LicenseAudit:
    ecosystems: tuple[EcosystemReport, ...]
    unknown: tuple[Dependency, ...]
    incompatible: tuple[Dependency, ...]
    notices_sha256: str


def audit_licenses(repo_root: Path) -> LicenseAudit:
    """Reconcile Rust, Python, and Node dependency locks with SPDX policy."""
~~~

`tools/license_audit.py check` remains a useful private-source diagnostic. In contrast, `receipt` invokes the same authoritative-export guard as G2, recomputes every shipped manifest/lock/license byte from the exact `$exportRoot`, binds `ReleaseSubject.export_commit` and `export_tree_sha256`, and refuses a private checkout or caller-supplied audit result. A source-only mutation outside the allowlist cannot change the exported receipt; any export mutation, including a synchronized mutation to package metadata plus license files, invalidates the tree binding before license conclusions are considered.

**Step 4: Run GREEN**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_release_toolchain.py tests/release/test_license_policy.py -q
C:\Python311\python.exe tools/bootstrap_release_tools.py verify --lock release/toolchain.lock
$toolBin = & C:\Python311\python.exe tools/bootstrap_release_tools.py ensure --lock release/toolchain.lock --print-bin
$releasePython = & C:\Python311\python.exe tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python
$releasePythonVersion = & $releasePython -c "import cryptography; print(cryptography.__version__)"
if ($releasePythonVersion -ne '45.0.5') { throw 'release cryptography environment is not the locked version' }
$env:PATH = "$toolBin;$env:PATH"
cargo deny check
reuse lint
cargo audit
C:\Python311\python.exe tools/license_audit.py check --root .
npm --prefix ts ci --ignore-scripts
npm --prefix ts_bridge ci --ignore-scripts
npm --prefix sidecars/typescript ci --ignore-scripts
~~~

Expected: every command exits 0; no unknown or incompatible license remains.

**Step 5: Commit**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('.gitignore','release/toolchain.lock','tools/bootstrap_release_tools.py','tests/release/test_release_toolchain.py','requirements/runtime.lock','requirements/test.lock','ts/package.json','ts_bridge/.gitignore','ts_bridge/package.json','ts_bridge/package-lock.json','deny.toml','REUSE.toml','LICENSES/Apache-2.0.txt','release/evidence/license.schema.json','tools/license_audit.py','tests/release/test_license_policy.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'security: lock dependencies and enforce license policy'
~~~

### Task 5: Codify the threat model and adversarial security tests

**Files:**

- Create: SECURITY.md
- Create: THREAT_MODEL.md
- Create: SUPPORT.md
- Create: docs/privacy.md
- Modify: release/public-export.toml
- Create: tests/security/test_paths.py
- Create: tests/security/test_symlinks.py
- Create: tests/security/test_origin_auth.py
- Create: tests/security/test_parser_limits.py
- Create: tests/security/test_log_redaction.py
- Create: tests/security/test_corrupt_store.py
- Create: crates/codesextant-core/tests/path_security.rs
- Modify: crates/codesextant-parser/tests/parser_limits.rs
- Create: crates/codesextant-store/tests/corrupt_store.rs
- Create: crates/codesextant-daemon/tests/log_redaction.rs
- Create: release/evidence/security.schema.json
- Create: release/evidence/security-review-receipt.schema.json
- Create: release/security-reviewer-roles.json
- Create: release/security-review-scope.schema.json
- Create: release/security-review-scope.json
- Create: release/security-review-request.schema.json
- Create: release/security-review-input.schema.json
- Create: release/security-findings.schema.json
- Create: release/external-review-request.schema.json
- Create: release/external-review-input.schema.json
- Create: release/external-review-findings.schema.json
- Create: release/external-review-receipt.schema.json
- Create: release/external-review-scan.schema.json
- Create: tools/security_receipt.py
- Create: tools/security_review.py
- Create: tools/external_security_review.py
- Modify: tools/review_role_runner.py
- Create: tests/release/test_security_receipt.py
- Create: tests/release/test_security_review.py
- Create: tests/release/test_external_security_review.py
- Modify: tests/release/test_review_role_runner.py
- Generated private evidence, never committed: release/evidence/security-review-request.json
- Generated private evidence, never committed: release/evidence/security-review-input.json
- Generated private evidence, never committed: release/evidence/security-findings.json
- Modify only as findings require: crates/codesextant-core/, crates/codesextant-parser/, crates/codesextant-store/, crates/codesextant-daemon/

**Step 1: Write adversarial RED tests**

Tests cover:

- repository paths that escape through dot-dot, junctions, and symlinks;
- a repository symlink retargeted between classification and read;
- parser inputs exceeding configured file bytes, parse time, nesting, and node count;
- logs/errors containing bearer tokens, source snippets, home directories, or repository absolute paths;
- corrupt/truncated/future-version SQLite files;
- HTTP Origin null, hostile Host, DNS rebinding, missing/wrong bearer, and heavy GET;
- insecure StateRoot/DB-WAL-SHM/spill/snapshot ACLs and link swaps;
- hostile sidecar environment/preload, analyzer-snapshot escape, uninterruptible resolver, and orphan recovery;
- bounded MCP/HTTP pre-parser, stdout writer, daemon instance/PID reuse, writer fencing, and cancel-vs-commit races;
- telemetry disabled and no outbound socket path by default.

~~~python
def test_error_and_log_redaction() -> None:
    secret = "Bearer test-secret-token"
    path = r"C:\Users\zerox\private\repo"
    rendered = render_error_for_log(InternalError(f"{secret} at {path}"))
    assert secret not in rendered
    assert path not in rendered
    assert "[REDACTED_TOKEN]" in rendered
    assert "$REPO" in rendered


EXPECTED_SECURITY_CHECKS = {
    "gitleaks_source_history",
    "gitleaks_export_history",
    "python_dependency_audit",
    "rust_advisory_audit",
    "rust_deny_policy",
    "node_dependency_audit_ts",
    "node_dependency_audit_bridge",
    "node_dependency_audit_sidecar",
    "reuse_lint",
    "license_audit",
    "python_adversarial_suite",
    "rust_path_security",
    "rust_parser_limits",
    "rust_corrupt_store",
    "rust_http_policy",
    "rust_log_redaction",
    "rust_state_root_security",
    "rust_sidecar_isolation",
    "rust_transport_limits",
    "rust_daemon_instance",
    "rust_writer_linearization",
}


def test_security_receipt_is_non_vacuous_current_and_complete(valid_security_payload) -> None:
    assert {row["id"] for row in valid_security_payload["checks"]} == EXPECTED_SECURITY_CHECKS
    assert all(row["exit_code"] == 0 for row in valid_security_payload["checks"])
    assert all(row["executed_test_count"] > 0 for row in valid_security_payload["test_suites"])
    assert all(row["skipped"] == 0 and row["xfailed"] == 0 for row in valid_security_payload["test_suites"])
    assert valid_security_payload["started_at_utc"] >= valid_security_payload["subject_frozen_at_utc"]
    assert valid_security_payload["source_tree_sha256"] == VALID_SUBJECT.source_tree_sha256
    assert valid_security_payload["export_tree_sha256"] == VALID_SUBJECT.export_tree_sha256


def test_security_receipt_rejects_missing_tool_digest_or_same_reviewer(valid_security_payload) -> None:
    valid_security_payload["tools"]["gitleaks"]["sha256"] = ""
    assert verify_security_payload(valid_security_payload).status == "fail"
    valid_security_payload["reviewer"]["implemented_security_controls"] = True
    assert verify_security_payload(valid_security_payload).status == "fail"


def test_security_receipt_requires_valid_reviewer_signature_and_role(valid_security_receipt) -> None:
    assert verify_security_receipt(
        valid_security_receipt,
        roles="release/security-reviewer-roles.json",
        actors="provenance/implementation-actors.json",
    ).status == "pass"
    valid_security_receipt["signature"] = "A" + valid_security_receipt["signature"][1:]
    assert verify_security_receipt(valid_security_receipt).status == "fail"


def test_security_reviewer_cannot_be_an_implementation_actor(valid_security_receipt) -> None:
    valid_security_receipt["signed_statement"]["reviewer_id"] = IMPLEMENTER_ACTOR_ID
    assert verify_security_receipt(valid_security_receipt).status == "fail"


def test_review_request_is_signed_closed_and_binds_every_review_input(valid_review_request) -> None:
    assert verify_review_request(valid_review_request).status == "pass"
    statement = valid_review_request["signed_statement"]
    assert statement["release_subject_sha256"] == VALID_SUBJECT_SHA256
    assert statement["source_tree_sha256"] == VALID_SUBJECT.source_tree_sha256
    assert statement["export_tree_sha256"] == VALID_SUBJECT.export_tree_sha256
    assert statement["artifact_manifest_sha256"] == VALID_SUBJECT.artifact_manifest_sha256
    assert statement["release_index_sha256"] == VALID_SUBJECT.release_index_sha256
    assert set(statement["sboms"]) == EXPECTED_SBOM_IDENTITIES
    assert set(statement["assets"]) == EXPECTED_THREAT_MODEL_ASSETS
    assert set(statement["controls"]) == EXPECTED_THREAT_MODEL_CONTROLS
    assert set(statement["claims"]) == EXPECTED_SECURITY_CLAIMS
    assert set(statement["automated_inputs"]) == EXPECTED_SECURITY_CHECKS | EXPECTED_REVIEW_ONLY_INPUTS
    valid_review_request["signature"] = tamper(valid_review_request["signature"])
    assert verify_review_request(valid_review_request).status == "fail"


def test_product_security_review_covers_the_frozen_external_review_engine(
    valid_review_request,
) -> None:
    assert {
        "external_review_engine_source",
        "external_review_request_schema",
        "external_review_input_schema",
        "external_review_findings_schema",
        "external_review_receipt_schema",
        "external_review_scan_schema",
        "external_review_engine_tests",
    } <= set(valid_review_request["signed_statement"]["automated_inputs"])


def test_signed_scope_binds_the_complete_g8_seed_install_and_preexec_closure(
    valid_review_request,
) -> None:
    required = {
        "signing_environment_registry_schema": "release/signing-environment-registry.schema.json",
        "signing_environment_registry": "release/signing-environment-registry.json",
        "g8_seed_installer": "tools/install_g8_seed.py",
        "g8_seed_install_receipt_schema": "release/g8-seed-install-receipt.schema.json",
        "g8_seed_install_tombstone_schema": "release/g8-seed-install-tombstone.schema.json",
        "g6_release_authority_schema": "release/g6-release-authority.schema.json",
        "g6_release_authority_tombstone_schema": "release/g6-release-authority-tombstone.schema.json",
        "g6_release_migration_schema": "release/g6-release-migration.schema.json",
        "g6_release_migration_signing_policy_schema": "release/g6-release-migration-signing-policy.schema.json",
        "g6_release_migration_signing_policy": "release/g6-release-migration-signing-policy.json",
        "g6_release_migration_key_provisioner": "tools/provision_g6_release_migration_key.ps1",
        "g8_seed_installer_signing_policy": "release/g8-seed-installer-signing-policy.json",
        "g8_authenticode_signing_policy": "release/g8-authenticode-signing-policy.json",
        "g8_authenticode_signing_policy_schema": "release/g8-authenticode-signing-policy.schema.json",
        "g8_seed_machine_key_provisioner": "tools/provision_g8_seed_machine_key.ps1",
        "g8_authenticode_trust_provisioner": "tools/provision_g8_authenticode_trust.ps1",
        "g8_seed_static_verifier_source": "release/g8-seed-static-verifier.rs",
        "g8_seed_standalone_installer_build_spec": "release/g8-seed-installer.spec",
        "g6_context_preflight_source": "release/g6-context-preflight.rs",
        "g6_runbook_launcher_source": "release/g6-runbook-launcher.rs",
        "g6_signed_runbook": "release/Run-CodeSextantG6.ps1",
        "g6_runbook_renderer": "tools/render_g6_runbook.py",
        "g8_seed_acl_no_reparse_negative_tests": "tests/release/test_g8_seed_install.py",
        "g8_seed_static_verifier_tests": "tests/release/test_g8_seed_static_verifier.py",
        "g6_context_preflight_tests": "tests/release/test_g6_context_preflight.py",
        "g6_runbook_bootstrap_tests": "tests/release/test_g6_runbook_bootstrap.py",
    }
    materials = index_scope_materials(valid_review_request["signed_statement"])
    assert {material_id: materials[material_id]["path"] for material_id in required} == required
    assert all(materials[material_id]["sha256"] == sha256_file(path) for material_id, path in required.items())


def test_review_input_requires_independent_actor_and_exact_material_closure(valid_review_input) -> None:
    assert verify_review_input(valid_review_input).status == "pass"
    valid_review_input["signed_statement"]["reviewer_id"] = IMPLEMENTER_ACTOR_ID
    assert verify_review_input(valid_review_input).status == "fail"
    valid_review_input["signed_statement"]["material_digests"].pop()
    assert verify_review_input(valid_review_input).status == "fail"


def test_findings_ledger_requires_typed_complete_entries(valid_findings_ledger) -> None:
    finding = valid_findings_ledger["signed_statement"]["findings"][0]
    assert set(finding) >= {
        "finding_id", "severity", "status", "evidence_sha256", "resolution_sha256"
    }
    finding.pop("resolution_sha256")
    assert verify_findings(valid_findings_ledger).status == "fail"


def test_zero_findings_requires_signed_explicit_scope_complete_verdict(
    zero_findings_ledger,
) -> None:
    statement = zero_findings_ledger["signed_statement"]
    assert statement["findings"] == []
    assert statement["verdict"] == "no_findings"
    assert statement["scope_complete"] is True
    assert statement["reviewed_scope_sha256"] == VALID_REVIEW_REQUEST_SCOPE_SHA256
    assert verify_findings(zero_findings_ledger).status == "pass"
    statement["scope_complete"] = False
    assert verify_findings(zero_findings_ledger).status == "fail"


@pytest.mark.parametrize("severity", ["high", "critical"])
def test_open_high_or_critical_finding_blocks_release(valid_findings_ledger, severity) -> None:
    finding = valid_findings_ledger["signed_statement"]["findings"][0]
    finding.update(severity=severity, status="open")
    assert emit_security_review_receipt(valid_findings_ledger).status == "fail"


def test_public_security_review_receipt_is_privacy_safe(valid_review_receipt) -> None:
    payload = valid_review_receipt["payload"]
    assert set(payload) == {
        "request_sha256", "input_sha256", "findings_sha256", "scope_sha256",
        "reviewer_id", "finding_counts_by_severity_and_status", "verdict", "status",
    }
    assert not contains_absolute_path_email_secret_or_source_text(payload)


def test_external_review_engine_binds_secondary_subject_manifest_and_closed_scope(
    valid_external_review_chain,
) -> None:
    assert verify_external_review(valid_external_review_chain).status == "pass"
    valid_external_review_chain.request["signed_statement"]["secondary_subject_sha256"] = "0" * 64
    assert verify_external_review(valid_external_review_chain).status == "fail"
    valid_external_review_chain = fresh_valid_external_review_chain()
    valid_external_review_chain.request["signed_statement"]["manifest_closure_sha256"] = "0" * 64
    assert verify_external_review(valid_external_review_chain).status == "fail"
    valid_external_review_chain = fresh_valid_external_review_chain()
    valid_external_review_chain.request["signed_statement"]["review_scope_sha256"] = "0" * 64
    assert verify_external_review(valid_external_review_chain).status == "fail"


def test_external_scan_is_manifest_bound_pinned_offline_and_non_vacuous(
    valid_external_scan,
) -> None:
    assert verify_external_scan(valid_external_scan).status == "pass"
    assert valid_external_scan["network_access_during_scan"] is False
    assert valid_external_scan["executed_file_count"] > 0
    assert all(row["tool_sha256"] for row in valid_external_scan["checks"])
    valid_external_scan["manifest_closure_sha256"] = "0" * 64
    assert verify_external_scan(valid_external_scan).status == "fail"


def test_external_review_engine_requires_distinct_independent_reviewer_and_key(
    valid_external_review_chain,
) -> None:
    statement = valid_external_review_chain.input["signed_statement"]
    statement["reviewer_id"] = IMPLEMENTER_ACTOR_ID
    assert verify_external_review(valid_external_review_chain).status == "fail"
    valid_external_review_chain = fresh_valid_external_review_chain()
    valid_external_review_chain.roles["independent_tool_security_reviewer"]["key_id"] = (
        valid_external_review_chain.roles["independent_claim_reviewer"]["key_id"]
    )
    assert verify_external_review(valid_external_review_chain).status == "fail"


@pytest.mark.parametrize(
    ("role", "visible"),
    [
        ("requester", "CODESEXTANT_SECURITY_REQUESTER_SIGNING_KEY"),
        ("reviewer", "CODESEXTANT_SECURITY_REVIEWER_SIGNING_KEY"),
    ],
)
def test_review_role_runner_starts_fresh_process_with_exactly_one_role_key(
    role, visible
) -> None:
    inventory = load_signing_environment_registry()
    known = {row["key_env"] for row in inventory["roles"]}
    launch = build_role_launch(role=role, allowed=visible)
    assert set(launch.forbidden_key_env) == known - {visible}
    child = run_role_probe(role=role, launch=launch, polluted_parent_environment=False)
    assert child.is_fresh_process
    assert child.visible_signing_keys == {visible}
    assert child.environment_names.isdisjoint(known - {visible})


def test_review_role_runner_rejects_nonexact_forbidden_set_and_future_reserved_env() -> None:
    inventory = load_signing_environment_registry()
    allowed = "CODESEXTANT_SECURITY_REQUESTER_SIGNING_KEY"
    exact = {row["key_env"] for row in inventory["roles"]} - {allowed}
    assert run_role_probe(forbidden_key_env=exact - {next(iter(exact))}).status == "fail"
    assert run_role_probe(forbidden_key_env=exact | {"NOT_RESERVED"}).status == "fail"
    assert run_role_probe(
        forbidden_key_env=exact,
        parent_environment={"CODESEXTANT_FUTURE_ROLE_SIGNING_KEY": "must-not-leak"},
    ).status == "fail"


def test_final_freeze_security_launches_derive_global_forbidden_closure() -> None:
    inventory = load_signing_environment_registry()
    known = {row["key_env"] for row in inventory["roles"]}
    launches = parse_final_freeze_security_role_launches()
    assert {launch.role for launch in launches} == {"requester", "reviewer"}
    for launch in launches:
        assert set(launch.forbidden_key_env) == known - {launch.allowed_key_env}
        assert launch.reserved_key_env_pattern == inventory["reserved_pattern"]
    assert final_freeze_rejects_parent_environment(
        {"CODESEXTANT_FUTURE_ROLE_SIGNING_KEY": "must-not-leak"}
    )


def test_review_receipt_verifier_process_has_no_signing_keys() -> None:
    child = run_role_probe(role="verifier", polluted_parent_environment=True)
    assert child.visible_signing_keys == set()
    assert child.environment_names.isdisjoint(ALL_REVIEW_SIGNING_KEY_NAMES)


@pytest.mark.parametrize("severity", ["high", "critical"])
def test_external_review_engine_blocks_open_high_or_critical(
    valid_external_review_chain, severity
) -> None:
    valid_external_review_chain.findings["signed_statement"]["findings"][0].update(
        severity=severity, status="open"
    )
    assert verify_external_review(valid_external_review_chain).status == "fail"


def test_external_review_zero_findings_is_explicit_signed_and_scope_complete(
    valid_external_review_chain,
) -> None:
    findings = valid_external_review_chain.findings["signed_statement"]
    findings.update(findings=[], verdict="no_findings", scope_complete=True)
    resign_external_findings(valid_external_review_chain)
    assert verify_external_review(valid_external_review_chain).status == "pass"
    findings["scope_complete"] = False
    assert verify_external_review(valid_external_review_chain).status == "fail"


def test_external_review_engine_is_in_the_public_export_allowlist(repo_root: Path) -> None:
    policy = load_public_export_policy(repo_root / "release/public-export.toml")
    assert {
        "tools/external_security_review.py",
        "release/external-review-request.schema.json",
        "release/external-review-input.schema.json",
        "release/external-review-findings.schema.json",
        "release/external-review-receipt.schema.json",
        "release/external-review-scan.schema.json",
        "tools/review_role_runner.py",
        "tests/release/test_external_security_review.py",
        "tests/release/test_review_role_runner.py",
    } <= set(policy.explicit_release_tool_paths)
    assert release_subject_tool_digests(policy).keys() >= {
        "tools/external_security_review.py",
        "tools/review_role_runner.py",
        "tests/release/test_external_security_review.py",
        "tests/release/test_review_role_runner.py",
    }


def test_only_the_frozen_external_engine_writes_the_entire_review_chain() -> None:
    assert external_review_chain_producers() == {
        "scan": "tools/external_security_review.py scan",
        "request": "tools/external_security_review.py request",
        "review_input": "tools/external_security_review.py record-input",
        "findings": "tools/external_security_review.py record-findings",
        "receipt": "tools/external_security_review.py receipt",
    }
    assert private_secondary_subject_writer_overrides() == ()
~~~

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/security -q
C:\Python311\python.exe -m pytest tests/release/test_security_receipt.py tests/release/test_security_review.py tests/release/test_external_security_review.py tests/release/test_review_role_runner.py -q
cargo test --locked -p codesextant-core --test path_security
cargo test --locked -p codesextant-parser --test parser_limits
cargo test --locked -p codesextant-store --test corrupt_store
cargo test --locked -p codesextant-store --test state_root_security --test multiprocess_publish
cargo test --locked -p codesextant-core --test analyzer_snapshot --test semantic_sidecars
cargo test --locked -p codesextant-mcp --test concurrent_stdio --test request_id_lifecycle
cargo test --locked -p codesextant-daemon --test http_policy --test log_redaction --test transport_limits --test instance_lifecycle
~~~

Expected: at least one named target fails for unimplemented limits/redaction and any open HTTP or path behavior; every named test binary reports a non-zero test count.

**Step 3: Implement the documented controls**

THREAT_MODEL.md uses assets, trust boundaries, attacker capabilities, threats, controls, residual risk, owner, and verification test. SECURITY.md provides a private vulnerability-reporting channel without promising response times the maintainer cannot meet. docs/privacy.md states local-only, no telemetry by default, no source upload, exact local files/ports, and deletion/uninstall behavior.

Every limit is a named configuration field with a conservative default and stable error code. No hidden network fallback is allowed.

`security.schema.json` defines a non-vacuous detached-signature domain payload: canonical `signed_statement`, `statement_sha256`, `signer_key_id`, and Ed25519 `signature`. The signed statement contains exact ReleaseSubject/source/export identities, start/end UTC, evidence-collector process identity, reviewer-role and implementation-actor-roster digests, tool-lock SHA-256, every executable version+binary digest, the exact 21-check matrix above, command/exit/stdout/stderr hashes, test collected/executed/skipped/xfail counts, vulnerability counts by severity, and final status. The signature covers only RFC 8785/JCS canonical UTF-8 bytes of `signed_statement` under a fixed `codesextant-security-automation-v1\0` domain separator, avoiding signature self-reference. This `security.json` receipt proves the automated matrix only; it is a mandatory input to, and can never substitute for, the separately registered `security-review.json` independent-review receipt.

`release/security-review-scope.json` is the closed review-scope authority. Its schema requires every asset/control/claim/check plus the complete pre-freeze G6-G8 trust closure. That closure includes the seed installer/receipt/tombstone/authority schemas; machine-key provisioning and signing policy; Authenticode policy plus schema; static verifier source/tests; standalone installer build spec and WinTrust/install negative tests; G6 native context-preflight source/tests; G6 initializer/portable runner; and all G7/G8 bootstrap/overlay/router files/tests. Every review-only material row carries exact repository-relative path and raw-byte SHA-256; names without digests are invalid. `validate-scope` rejects missing, extra, duplicate, stale-digest, or unbound IDs, and no caller can narrow scope. Changing any afterward invalidates review and forces G5-G6 again.

The same closed scope also names the frozen generic external-review engine, its five schemas, the fresh-process role launcher, `tests/release/test_external_security_review.py`, and `tests/release/test_review_role_runner.py` as mandatory review-only materials. `tools/external_security_review.py` and `tools/review_role_runner.py` are therefore committed, scanned, and independently reviewed before the product/G7 freeze. The external engine is the sole writer and verifier for the later private G8 application-tool `scan`, `request`, `review-input`, `findings`, and security-review receipt; the role launcher is the sole path by which requester/reviewer signing credentials enter mutually exclusive child processes. Private application code may supply only the manifest-bound reviewed materials and may not create, replace, patch, or bypass any ledger producer or launcher. The public-export allowlist includes the engine, launcher, schemas, and tests as release tooling. Their exact source and schema digests are included in the product ReleaseSubject and later in `ApplicationToolSubject`; any change after freeze requires a product rebuild and G4-G6 rerun rather than a private hot patch.

The review protocol uses three immutable JCS-canonical ledgers plus one privacy-safe receipt. `request` is signed by a precommitted security-review-requester role and binds the exact ReleaseSubject, source/export commits and trees, artifact manifest, signed release index, every archive/SBOM/provenance/bundle digest, every claim/asset/control ID, and every scan/test output ID plus content digest. `input` is signed by the independent reviewer and records the request digest, review process/tool/environment digests, every material actually inspected, and exact scope acknowledgement. `findings` is signed separately by that reviewer and records a stable finding ID, severity (`info|low|medium|high|critical`), status (`open|resolved|accepted_residual`), evidence SHA-256, and resolution-record SHA-256 for every finding. Empty findings are valid only when the signed statement says `verdict=no_findings`, `scope_complete=true`, and repeats the exact request scope digest. A nonempty ledger says `verdict=findings_recorded`; any omitted material, unknown status/severity, duplicate ID, unsigned mutation, or open high/critical item prevents receipt creation. Accepted low/medium residuals require owner, rationale, and expiry in the resolution record.

`release/security-reviewer-roles.json` precommits distinct requester and independent-reviewer UUIDs, roles, key IDs, and Ed25519 public keys. The existing universal `provenance/implementation-actors.json` remains the single actor authority for provenance, security, G6, and application review; no narrower duplicate roster may omit an implementer. Both authorities are hashed into every signed statement, contain no private/seed/signing-key material, and verifiers reject requester/reviewer identity equality, reviewer/implementation-actor overlap, and signing-key reuse across those roles. `tools/review_role_runner.py` is the sole role launcher: it starts a fresh process from a closed environment allowlist, schema-validates and digest-checks `release/signing-environment-registry.json`, derives the exact forbidden set as every registered key environment except the role's one allowed value, rejects any caller/launch-spec set that differs, and enumerates the actual environment to reject every other name matching the closed reserved pattern even when a future name is not registered yet. Only then may it obtain one role-specific key from an OS credential reference inside that child; it clears the child environment on exit. A requester child can see only the requester key, a reviewer child only the reviewer key, and a receipt/verifier child neither; private keys never enter argv, logs, receipts, the parent environment, or any other role process.

`tools/security_receipt.py receipt` itself creates an isolated checkout/export and executes the automated matrix; it cannot accept caller-supplied pass rows or reuse an earlier result. Python dependency audit runs the exact hashed runtime/test/sidecar locks with the audit package pinned inside `requirements/test.lock`; all three npm audits use committed lockfileVersion-3 locks. Network-backed advisory databases record retrieval UTC and content digest and fail closed when unavailable or stale. Any missing check, bad signature/key/role, zero-test suite, skip/xfail, unknown/high/critical automated finding, tool digest mismatch, reviewer overlap, or source/export/subject mismatch prevents receipt creation.

The automated receipt is produced in a fresh reviewer process. After it exists, a separate fresh requester process invokes `tools/security_review.py request`; then a new reviewer process with no implementation role invokes the atomic `record-input-and-findings` flow. Finally a keyless fresh verifier invokes `receipt-and-verify`, which verifies all three detached signatures, exact scope/material closure, actor separation, finding disposition, and the absence of both signing keys before emitting and re-verifying `security-review.json`. That receipt contains only actor IDs, canonical digests, aggregate finding counts, verdict, and status—never source excerpts, absolute paths, email, credentials, or private review notes—so it is safe to publish as release evidence. F5 independently runs both receipt verifiers before the generic gate. Tests reject key co-residency, parent-to-child inheritance, verifier key visibility, role overlap, or separate commands that could mutate input between reviewer acknowledgements.

`tools/external_security_review.py` applies the same detached Ed25519/JCS rules to a later secondary subject without trusting code from that subject. Its `scan` subcommand reads only the subject's exhaustive manifest, runs the product-frozen offline SAST rules and exact dependency locks in an isolated process, forbids network, requires every declared file/check to execute, and emits the generic schema-bound scan with tool/rule/command/output hashes and zero caller-supplied result rows. Its signed review request must bind: primary ReleaseSubject digest; secondary-subject digest and commit/tree identities; exhaustive manifest-closure digest; fixed review-scope digest; implementation-actor and role-policy digests; every declared source/schema/policy/recovery/threat-model/public-exclusion proof; and that exact pinned SAST/dependency-scan digest. Reviewer input and findings are signed by a precommitted `independent_tool_security_reviewer`; the verifier rejects overlap with any implementation actor, requester, or `independent_claim_reviewer`, and rejects reviewer-key reuse. Zero findings requires signed `no_findings` plus `scope_complete=true`; any omitted material or open high/critical finding blocks. The emitted privacy-safe receipt contains only subject/scope/request/input/findings/reviewer digests, aggregate counts, verdict, and status. It never executes or imports the reviewed private code and accepts no caller-supplied pass flag.

**Step 4: Run GREEN**

~~~powershell
C:\Python311\python.exe -m pytest tests/security -q
cargo test --locked --workspace
C:\Python311\python.exe -m pytest tests/test_hardening.py tests/test_daemon_routing.py -q
C:\Python311\python.exe -m pytest tests/release/test_security_receipt.py -q
C:\Python311\python.exe -m pytest tests/release/test_security_review.py -q
C:\Python311\python.exe -m pytest tests/release/test_external_security_review.py tests/release/test_review_role_runner.py -q
C:\Python311\python.exe tools/security_receipt.py check --source . --tool-lock release/toolchain.lock
C:\Python311\python.exe tools/security_review.py validate-scope --scope release/security-review-scope.json --threat-model THREAT_MODEL.md
~~~

Expected: all pass, every named test suite has nonzero collected/executed counts, and no test is xfail/skip on the host platform when it covers portable logic. This local check emits no gate receipt; F5 performs the independent subject-bound rerun.

**Step 5: Commit**

~~~powershell
$task5FindingFixPaths = @(
  # Add every implementation leaf changed to resolve a recorded finding. Never put a directory here.
)
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('SECURITY.md','THREAT_MODEL.md','SUPPORT.md','docs/privacy.md','release/public-export.toml','tests/security/test_paths.py','tests/security/test_symlinks.py','tests/security/test_origin_auth.py','tests/security/test_parser_limits.py','tests/security/test_log_redaction.py','tests/security/test_corrupt_store.py','crates/codesextant-core/tests/path_security.rs','crates/codesextant-parser/tests/parser_limits.rs','crates/codesextant-store/tests/corrupt_store.rs','crates/codesextant-daemon/tests/log_redaction.rs','release/evidence/security.schema.json','release/evidence/security-review-receipt.schema.json','release/security-reviewer-roles.json','release/security-review-scope.schema.json','release/security-review-scope.json','release/security-review-request.schema.json','release/security-review-input.schema.json','release/security-findings.schema.json','release/external-review-request.schema.json','release/external-review-input.schema.json','release/external-review-findings.schema.json','release/external-review-receipt.schema.json','release/external-review-scan.schema.json','tools/security_receipt.py','tools/security_review.py','tools/external_security_review.py','tools/review_role_runner.py','tests/release/test_security_receipt.py','tests/release/test_security_review.py','tests/release/test_external_security_review.py','tests/release/test_review_role_runner.py') + $task5FindingFixPaths
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'security: codify threat model and adversarial controls'
~~~

### Task 6: Add SHA-pinned CI and security policy

**Files:**

- Create: .github/workflows/ci.yml
- Create: .github/workflows/contracts.yml
- Create: .github/workflows/security.yml
- Create: .github/workflows/pre-public-sast.yml
- Create: .github/workflows/dependency-review.yml
- Create: .github/workflows/scorecard.yml
- Create: .github/dependabot.yml
- Create: .github/CODEOWNERS
- Create: release/check-policy.json
- Create: release/pre-public-sast.schema.json
- Create: release/github-controls.schema.json
- Create: release/github-controls.json
- Create: requirements/sast.lock
- Create: security/semgrep-rules.yml
- Create: security/ruff-security.toml
- Create: tools/verify_actions_pinned.py
- Create: tools/pre_public_sast.py
- Create: tools/github_controls.py
- Create: tests/release/test_workflow_policy.py
- Create: tests/release/test_pre_public_sast.py
- Create: tests/release/test_github_controls.py

**Step 1: Write RED tests**

~~~python
ACTION_REF = re.compile(r"^[0-9a-f]{40}$")


def test_all_actions_are_commit_pinned(repo_root: Path) -> None:
    for use in workflow_uses(repo_root / ".github/workflows"):
        assert ACTION_REF.fullmatch(use.ref), use


def test_checks_are_partitioned_by_private_repository_feasibility(repo_root: Path) -> None:
    policy = load_check_policy(repo_root / "release/check-policy.json")
    assert policy.private_capable == {
        "python",
        "typescript",
        "rust",
        "contracts",
        "secret-scan",
        "dependency-audit",
        "license",
        "pre-public-sast",
    }
    assert policy.public_corroboration == {
        "codeql",
        "scorecard",
    }
    assert policy.future_pull_request_safeguards == {"dependency-review"}
    assert not hasattr(policy, "public_only")
    assert policy.private_capable | policy.public_corroboration | policy.future_pull_request_safeguards <= workflow_jobs(repo_root)


def test_pre_public_sast_is_pinned_offline_and_export_bound(
    frozen_subject, export_repo: Path
) -> None:
    report = run_pre_public_sast(
        root=export_repo,
        subject=frozen_subject,
        dependency_lock="requirements/sast.lock",
        semgrep_rules="security/semgrep-rules.yml",
        ruff_config="security/ruff-security.toml",
    )
    assert report.authority == "release_export"
    assert report.export_commit == frozen_subject.export_commit
    assert report.export_tree_sha256 == frozen_subject.export_tree_sha256
    assert set(report.check_ids) == {
        "semgrep_ce_python_typescript",
        "ruff_security_rules",
        "rust_clippy_deny_warnings",
        "custom_taint_and_path_tests",
        "python_dependency_audit",
        "rust_advisory_audit",
        "rust_deny_policy",
        "node_dependency_audits",
    }
    assert all(row.exit_code == 0 for row in report.checks)
    assert report.finding_counts == {
        "info": 0, "low": 0, "medium": 0, "high": 0, "critical": 0
    }
    assert report.network_access_during_scan is False


def test_pre_public_sast_rejects_mutable_registry_rules_or_private_source(
    frozen_subject, source_repo: Path, export_repo: Path
) -> None:
    assert run_pre_public_sast(export_repo, frozen_subject, semgrep_rules="p/security").status == "fail"
    assert run_pre_public_sast(source_repo, frozen_subject).status == "fail"


def test_github_controls_are_closed_and_exact(repo_root: Path) -> None:
    controls = load_github_controls(repo_root / "release/github-controls.json")
    assert controls.repository == "Zeroxrain99/CodeSextant"
    assert controls.default_branch == "main"
    assert controls.ruleset.enforcement == "active"
    assert controls.ruleset.bypass_actors == []
    assert set(controls.ruleset.required_status_checks) == (
        load_check_policy(repo_root / "release/check-policy.json").private_capable
        | {"native-artifact-matrix"}
    )
    assert controls.secret_scanning.enabled is True
    assert controls.secret_scanning.push_protection is True
    assert controls.dependabot == {
        "alerts": True,
        "security_updates": True,
        "version_updates": True,
    }
    assert controls.actions.default_workflow_permissions == "read"
    assert controls.actions.can_approve_pull_requests is False
    assert controls.actions.allowed_actions == "selected"


def test_github_controls_reject_wildcard_check_bypass_or_actions(valid_controls) -> None:
    valid_controls["ruleset"]["bypass_actors"] = [{"actor": "RepositoryRole:admin"}]
    assert validate_github_controls(valid_controls).status == "fail"
    valid_controls["ruleset"]["required_status_checks"] = ["*"]
    assert validate_github_controls(valid_controls).status == "fail"
    valid_controls["actions"]["allowed_action_patterns"] = ["*"]
    assert validate_github_controls(valid_controls).status == "fail"
~~~

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_workflow_policy.py tests/release/test_pre_public_sast.py tests/release/test_github_controls.py -q
~~~

Expected: FAIL because .github workflows do not exist.

**Step 3: Implement workflows**

All uses entries are pinned to verified 40-character upstream commit SHAs and carry a trailing comment with human-readable release tag. Workflow permissions default to `contents: read`. Permission elevation is job-local: cosign signing gets only `id-token: write`; the post-visibility Scorecard corroboration job gets `id-token: write` plus `security-events: write`; CodeQL SARIF upload gets only `security-events: write`; and the release job alone gets `contents: write`. Pull-request and dependency-review jobs never receive OIDC, write permissions, or repository secrets while executing untrusted checkout code.

`release/check-policy.json` is the single check-phase authority. `private_capable` contains local/CI Rust/Python/TypeScript/contracts, pinned gitleaks, dependency audits, license policy, and `pre-public-sast`; all of these plus the separately enumerated native artifact matrix must pass against the exact allowlist export while staging remains private. `public_corroboration` contains CodeQL and OpenSSF Scorecard because a personal Free/Pro private repository cannot execute the required GitHub code-scanning service. G7 may run them only after visibility changes and must describe them as corroboration: they are never evidence that confidentiality was preserved or that the release was all-green before source exposure. An unexpected public corroboration finding triggers fail-closed release withholding/incident compensation, not a retroactive claim that it was a pre-public gate. `dependency-review` is configured and tested as a future pull-request safeguard, not claimed as a successful initial-release run. No plan attempts to bypass a GitHub feature entitlement or makes the repository public early.

`requirements/sast.lock` fully pins Semgrep Community Edition, Ruff, and every transitive Python dependency with hashes for the supported release host. Tool licenses and exact source/distribution digests are recorded and checked by license policy; no Pro rule, proprietary registry pack, telemetry, or remote rule URL is accepted. `security/semgrep-rules.yml` contains only project-owned Apache-2.0 local Python/TypeScript rules and its canonical digest is policy-bound. Ruff runs the pinned flake8-bandit-compatible `S` rules under `security/ruff-security.toml`; Rust uses the pinned toolchain's `cargo clippy --locked --workspace --all-targets -- -D warnings`; custom taint/path tests exercise access-scope, origin, log-redaction, sidecar-environment, and archive/install traversal boundaries. Dependency audits are rerun from the exact committed locks. `tools/pre_public_sast.py` disables Semgrep metrics/version checks, forbids network during the scan, records executable/rule/config/command/output hashes, requires every check to execute, requires zero findings at every severity (no inline ignore, waiver, or accepted-residual escape hatch in this automated gate), rejects an unavailable/stale advisory source, and calls the authoritative-export guard before emitting its schema-valid report. It cannot accept caller-supplied result rows or a Semgrep registry identifier.

`release/github-controls.json`, validated by `release/github-controls.schema.json`, is the tracked SSOT consumed by G5 staging and G7 publication. It fixes repository/default branch, one named active ruleset, exact required check contexts from `check-policy.json`, no bypass actors, branch deletion/force-push prohibition, signed-tag/review requirements where applicable, secret scanning and push protection, Dependabot alerts/security updates/version updates, and Actions selected-action/default-permission policy. It distinguishes controls that can be applied while the personal repository is private from controls that become available at public visibility, but never silently drops a desired public control. Values are closed—no wildcard actor/check/action pattern, caller-added exception, mutable `latest`, or best-effort mode. `tools/github_controls.py schema-check` validates the cross-file equality and emits the canonical policy SHA-256 for staging/publication plans; live G7 apply/verify receipts must bind that same digest and the concrete GitHub-returned ruleset/config IDs.

CodeQL scans only languages officially supported by the selected action. Rust uses cargo clippy, cargo audit, and cargo deny; the documentation does not claim CodeQL covers Rust.

**Step 4: Run GREEN**

~~~powershell
$toolBin = & C:\Python311\python.exe tools/bootstrap_release_tools.py ensure --lock release/toolchain.lock --print-bin
$env:PATH = "$toolBin;$env:PATH"
C:\Python311\python.exe tools/verify_actions_pinned.py .github/workflows
C:\Python311\python.exe tools/pre_public_sast.py verify-lock --lock requirements/sast.lock --rules security/semgrep-rules.yml --ruff-config security/ruff-security.toml
C:\Python311\python.exe tools/github_controls.py schema-check --controls release/github-controls.json --schema release/github-controls.schema.json --check-policy release/check-policy.json
C:\Python311\python.exe -m pytest tests/release/test_workflow_policy.py -q
C:\Python311\python.exe -m pytest tests/release/test_pre_public_sast.py tests/release/test_github_controls.py -q
$workflowFiles = Get-ChildItem -LiteralPath .github/workflows -Filter '*.yml' -File | ForEach-Object FullName
foreach ($workflowFile in $workflowFiles) { actionlint -- $workflowFile; if ($LASTEXITCODE -ne 0) { throw "actionlint failed for $workflowFile with exit $LASTEXITCODE" } }
cargo run --locked -q -p xtask -- contracts check
~~~

Expected: all exit 0 and generated contract files remain clean under `cargo run --locked -q -p xtask -- contracts check`.

**Step 5: Commit**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('.github/workflows/ci.yml','.github/workflows/contracts.yml','.github/workflows/security.yml','.github/workflows/pre-public-sast.yml','.github/workflows/dependency-review.yml','.github/workflows/scorecard.yml','.github/dependabot.yml','.github/CODEOWNERS','release/check-policy.json','release/pre-public-sast.schema.json','release/github-controls.schema.json','release/github-controls.json','requirements/sast.lock','security/semgrep-rules.yml','security/ruff-security.toml','tools/verify_actions_pinned.py','tools/pre_public_sast.py','tools/github_controls.py','tests/release/test_workflow_policy.py','tests/release/test_pre_public_sast.py','tests/release/test_github_controls.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'ci: add pinned security and dependency workflows'
~~~

### Task 7: Build checksummed, SBOM-attached, attestable artifacts

**Dependencies:** Native-kernel Task 11 and its exact five-component layout, `release/native-lifecycle-contract.json`/schema, `release/run_native_lifecycle.py`, and previous-artifact requirement; G5 Tasks 1-6.

**Files:**

- Modify: release/targets.toml
- Create: release/signing-policy.schema.json
- Create: release/signing-policy.json
- Create: release/verifier-bootstrap.schema.json
- Create: release/verifier-bootstrap.json
- Create: release/release-index.schema.json
- Create: release/private-check-evidence.schema.json
- Create: release/runner-policy.schema.json
- Create: release/runner-policy.json
- Create: release/runner-availability.schema.json
- Create: release/runner-attestation.schema.json
- Create: release/artifact-fragment.schema.json
- Create: release/artifact-manifest.schema.json
- Create: release/evidence/artifacts.schema.json
- Create: release/native-lifecycle-fragment.schema.json
- Create: release/lifecycle-receipt.schema.json
- Create: release/runtime-security-baseline.schema.json
- Create: release/runtime-security-policy.json
- Create: release/build.py
- Create: release/package.py
- Create: release/provenance.py
- Create: tools/release_index.py
- Create: tools/runner_authority.py
- Create: tools/runtime_security_baseline.py
- Modify: tools/sync_version.py
- Create: install/install.ps1
- Create: install/uninstall.ps1
- Create: install/install.sh
- Create: install/update.ps1
- Create: install/update.sh
- Create: install/uninstall.sh
- Create: .github/workflows/artifact-smoke.yml
- Create: tests/release/test_artifact_manifest.py
- Create: tests/release/test_install_scripts.py
- Create: tests/release/test_lifecycle_matrix.py
- Create: tests/release/test_runtime_security_baseline.py
- Create: tests/release/test_release_index.py
- Create: tests/release/test_runner_authority.py
- Generated private evidence, never committed: release/evidence/runner-availability.json
- Generated per-job evidence, never committed: release/evidence/runner-attestations/

**Step 1: Write RED tests**

~~~python
EXPECTED_TARGETS = {
    "x86_64-pc-windows-msvc",
    "x86_64-unknown-linux-gnu",
    "aarch64-unknown-linux-gnu",
    "x86_64-apple-darwin",
    "aarch64-apple-darwin",
}


def test_manifest_covers_every_target(manifest: ArtifactManifest) -> None:
    assert {a.target for a in manifest.artifacts} == EXPECTED_TARGETS
    for artifact in manifest.artifacts:
        assert len(artifact.sha256) == 64
        assert artifact.sbom.format in {"spdx-json", "cyclonedx-json"}
        assert artifact.provenance.predicate_type.startswith("https://slsa.dev/provenance/")


def test_single_target_fragment_is_identity_bound(fragment: ArtifactFragment) -> None:
    assert fragment.artifact.target == fragment.target
    assert fragment.build_identity.export_commit == fragment.artifact.export_commit
    assert fragment.build_identity.export_tree_sha256 == fragment.artifact.export_tree_sha256
    assert fragment.build_identity.source_commit == fragment.artifact.source_commit
    assert fragment.build_identity.source_tree_sha256 == fragment.artifact.source_tree_sha256


def test_aggregate_rejects_missing_target_or_mixed_identity(valid_fragments) -> None:
    assert aggregate_fragments(valid_fragments[:-1]).status == "fail"
    valid_fragments[-1]["build_identity"]["source_commit"] = "0" * 40
    assert aggregate_fragments(valid_fragments).status == "fail"


def test_diagnostic_fragment_can_never_enter_a_release_manifest(valid_fragments) -> None:
    valid_fragments[0]["build_identity"]["authority"] = "diagnostic"
    assert aggregate_fragments(valid_fragments).status == "fail"


def test_release_assets_are_explicit_complete_and_unique(manifest: ArtifactManifest) -> None:
    assert manifest.manifest_identity.filename == "artifact-manifest.json"
    assert len(manifest.manifest_identity.canonical_payload_sha256) == 64
    names = [asset.filename for asset in manifest.release_assets]
    assert len(names) == len(set(names))
    assert "SHA256SUMS" in names
    assert {asset.kind for asset in manifest.release_assets} == {
        "archive",
        "checksums",
        "sbom",
        "provenance",
        "signature_bundle",
        "license_report",
        "check_evidence",
        "lifecycle_receipt",
        "provenance_review",
    }
    assert {artifact.filename for artifact in manifest.artifacts} <= set(names)
    for artifact in manifest.artifacts:
        assert artifact.sbom.path in names
        assert artifact.provenance.path in names
        assert artifact.provenance.signature_bundle_path in names
    assert all(len(asset.sha256) == 64 for asset in manifest.release_assets)
    assert all(isinstance(asset.sigstore_required, bool) for asset in manifest.release_assets)
    policy = load_signing_policy("release/signing-policy.json")
    for asset in manifest.release_assets:
        if asset.sigstore_required:
            assert asset.sigstore_bundle_filename
            assert asset.certificate_identity == policy.certificate_identity
            assert asset.certificate_oidc_issuer == policy.certificate_oidc_issuer


def test_signer_trust_root_is_exact_and_not_artifact_selected(signing_policy) -> None:
    assert signing_policy == {
        "schema_version": 1,
        "repository": "Zeroxrain99/CodeSextant",
        "workflow_ref": "Zeroxrain99/CodeSextant/.github/workflows/artifact-smoke.yml@refs/heads/main",
        "certificate_identity": "https://github.com/Zeroxrain99/CodeSextant/.github/workflows/artifact-smoke.yml@refs/heads/main",
        "certificate_oidc_issuer": "https://token.actions.githubusercontent.com",
    }
    assert verify_release_asset(asset_with_identity(".*"), signing_policy).status == "fail"
    assert verify_release_asset(asset_with_identity(signing_policy["certificate_identity"]), signing_policy).status == "pass"


def test_signed_release_index_is_the_non_recursive_distribution_authority(
    release_index, release_index_bundle, manifest, signing_policy
) -> None:
    assert release_index.repository == "Zeroxrain99/CodeSextant"
    assert release_index.release_tag == f"v{release_index.product_version}"
    assert release_index.artifact_manifest_sha256 == sha256_file(manifest.path)
    assert set(release_index.assets) == {
        manifest.filename,
        *(asset.filename for asset in manifest.release_assets),
    }
    assert release_index.signature_bundle_filename == "release-index.sigstore.json"
    assert "release-index.json" not in {row.filename for row in release_index.assets}
    assert "release-index.sigstore.json" not in {row.filename for row in release_index.assets}
    assert verify_release_index(
        release_index,
        release_index_bundle,
        signing_policy=signing_policy,
    ).status == "pass"


def test_distribution_asset_set_includes_signed_index_and_bundle(
    release_index, manifest
) -> None:
    assert distribution_asset_names(release_index, manifest) == {
        "release-index.json",
        "release-index.sigstore.json",
        "artifact-manifest.json",
        *(asset.filename for asset in manifest.release_assets),
    }


def test_installer_rejects_coordinated_payload_manifest_checksum_and_index_tamper(
    signed_distribution,
) -> None:
    mutate_archive(signed_distribution)
    rewrite_component_manifest_to_match(signed_distribution)
    rewrite_sha256sums_to_match(signed_distribution)
    rewrite_release_index_to_match(signed_distribution)
    assert install_verify(signed_distribution).status == "fail"
    assert install_verify(signed_distribution).reason == "release_index_signature_invalid"


def test_install_update_and_rollback_never_accept_unsigned_or_wrong_identity_index(
    signed_distribution,
) -> None:
    for operation in (install_release, update_release, rollback_release):
        assert operation(without_bundle(signed_distribution)).status == "fail"
        assert operation(bundle_from_other_workflow(signed_distribution)).status == "fail"


def test_verifier_bootstrap_is_immutable_and_matches_installer_constants(
    verifier_bootstrap,
) -> None:
    assert verifier_bootstrap.cosign_version == "3.1.2"
    assert all(is_immutable_official_url(row.url) for row in verifier_bootstrap.assets)
    assert all(re.fullmatch(r"[0-9a-f]{64}", row.sha256) for row in verifier_bootstrap.assets)
    assert installer_embedded_bootstrap() == verifier_bootstrap


def test_runner_policy_is_exact_native_and_fail_closed(runner_policy) -> None:
    assert set(runner_policy.targets) == EXPECTED_TARGETS
    for target, authority in runner_policy.targets.items():
        assert set(authority.observations) == {"oldest_supported", "current"}
        for observation in authority.observations.values():
            assert observation.labels and all("latest" not in x for x in observation.labels)
            assert observation.os_name and observation.os_build
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", observation.image_digest)
            assert observation.architecture == target_architecture(target)
            assert observation.owner == "Zeroxrain99"
            assert validate_closed_attestation_trust(observation.attestation_trust).status == "pass"
            assert observation.ephemeral is True
            assert observation.clean_teardown_required is True
            assert observation.allow_fallback is False
            assert observation.allow_emulation is False
    assert runner_policy.targets["x86_64-pc-windows-msvc"].observations[
        "oldest_supported"
    ].os_build == "10.0.19045"
    for target in ("x86_64-apple-darwin", "aarch64-apple-darwin"):
        assert runner_policy.targets[target].observations["oldest_supported"].os_version == "13.5"


def test_authoritative_fragment_requires_available_attested_runner_and_teardown(
    valid_fragment, valid_runner_availability, valid_runner_attestation
) -> None:
    assert validate_runner_authority(
        valid_fragment, valid_runner_availability, valid_runner_attestation
    ).status == "pass"
    valid_runner_attestation["emulated"] = True
    assert validate_runner_authority(
        valid_fragment, valid_runner_availability, valid_runner_attestation
    ).status == "fail"
    valid_runner_attestation["emulated"] = False
    valid_runner_attestation["ephemeral_teardown"]["status"] = "dirty_or_persistent"
    assert validate_runner_authority(
        valid_fragment, valid_runner_availability, valid_runner_attestation
    ).status == "fail"


def test_workflow_runner_matrix_exactly_consumes_tracked_policy(repo_root: Path) -> None:
    policy = load_runner_policy(repo_root / "release/runner-policy.json")
    workflow = load_workflow(repo_root / ".github/workflows/artifact-smoke.yml")
    assert workflow_runner_matrix(workflow) == policy.static_workflow_matrix
    assert workflow_bound_policy_sha256(workflow) == canonical_sha256(policy)


def test_every_native_target_proves_full_lifecycle(lifecycle: LifecycleReceipt) -> None:
    contract = load_native_lifecycle_contract("release/native-lifecycle-contract.json")
    assert {run.target for run in lifecycle.runs} == EXPECTED_TARGETS
    for run in lifecycle.runs:
        assert run.native_phase_ids == contract.phase_ids
        assert run.release_extension_phase_ids == [
            "prerelease_artifact_verified",
            "rollback_to_prerelease",
            "doctor_after_manual_rollback",
            "update_final_after_manual_rollback",
            "failed_update_auto_rollback",
            "doctor_after_failed_update_auto_rollback",
        ]
        assert all(phase.exit_code == 0 for phase in run.native_receipts)
        assert all(phase.exit_code == 0 for phase in run.release_extension_receipts)
        failed_update = run.receipt("failed_update_auto_rollback")
        assert failed_update.attempted_update_exit_code != 0
        assert failed_update.rollback_exit_code == 0
        assert failed_update.after_rollback_version == lifecycle.final_version
        assert failed_update.corrupt_payload_sha256 not in lifecycle.release_artifact_sha256s


def test_fragment_binds_exact_verified_five_component_layout(fragment: ArtifactFragment) -> None:
    assert fragment.component_manifest_sha256 == sha256_file(fragment.component_manifest_path)
    assert {component.logical_name for component in fragment.components} == {
        "codesextant",
        "codesextant-mcp",
        "codesextantd",
        "codesextant-jedi-sidecar",
        "codesextant-ts-morph-sidecar",
    }
    assert all(component.sha256 and component.license_refs for component in fragment.components)
    component_manifest = load_component_manifest(fragment.component_manifest_path)
    physical_files = walk_regular_files_without_following_links(fragment.component_root) - {fragment.component_manifest_path}
    assert {row.path for row in component_manifest.installed_files} == physical_files
    assert component_manifest.installed_files_root_sha256 == merkle_root(component_manifest.installed_files)
    assert all(row.sha256 and row.size_bytes >= 0 and row.license_refs for row in component_manifest.installed_files)
    assert any(row.kind == "runtime_support" and row.owner == "codesextant-jedi-sidecar" for row in component_manifest.installed_files)
    assert fragment.component_verification.status == "pass"


@pytest.mark.parametrize("support_kind", ["dll", "pyd", "python_archive", "package_data"])
def test_fragment_rejects_tampered_or_unmanifested_jedi_onedir_support_file(
    verified_component_layout,
    support_kind,
) -> None:
    mutate_one_support_file(verified_component_layout, support_kind)
    assert verify_components(verified_component_layout).status == "fail"
    assert build_fragment(verified_component_layout).status == "fail"


def test_every_product_version_surface_uses_the_python_projection(
    manifest: ArtifactManifest,
    release_index,
    release_subject,
) -> None:
    from codesextant._version import __version__

    assert manifest.product_version == __version__
    assert release_subject.product_version == __version__
    assert release_subject.release_tag == f"v{__version__}"
    assert release_index.product_version == __version__
    assert release_index.release_tag == f"v{__version__}"
    for artifact in manifest.artifacts:
        assert artifact.product_version == __version__
        component_manifest = load_component_manifest(artifact)
        assert component_manifest.product_version == __version__
        for name in ("codesextant", "codesextant-mcp", "codesextantd"):
            assert run_installed_version(artifact, name) == f"CodeSextant {__version__}"
    assert no_product_surface_uses_cargo_pkg_version()
~~~

`test_runtime_security_baseline.py` requires one fresh target-native baseline fragment per target. Each fragment binds the verified component-manifest/SBOM/provenance identities and actual packaged CPython/sys.version/SOABI/OpenSSL/SQLite/Jedi/parso/PyInstaller plus the TypeScript launcher/private-Node path, Node/V8/OpenSSL/ts-morph/TypeScript/esbuild versions and executable/component digests. It records observation UTC and content digests for official release/security feeds. Tests reject an unavailable/stale feed, manifest/runtime mismatch, host-runtime fallback, a pin superseded by an upstream security release, an officially announced pending security release for the pinned supported line, an applicable unwaived high/critical advisory, a diagnostic fragment, or a baseline older than the policy window at ReleaseSubject freeze. A pending security release places publication on hold until the release is available, its applicability is known, and the reviewed toolchain pin/baseline is refreshed; an embargoed announcement cannot be waived as "not affected" without authoritative upstream evidence. A normal newer non-security feature release alone does not silently change pins; it opens a reviewed pin decision.

The target matrix tests also parse `release/targets.toml` and require the actual binary/runtime ABI inspection receipts: Windows 10 22H2 build 19045/UCRT/import allowlist, Linux maximum GLIBC_2.28 on native x86_64/aarch64 baseline images, and macOS 13.5 `minos` on both architectures for every Rust, PyInstaller, and private Node executable. Every target runs lifecycle on the oldest-supported and current OS and binds both receipts. A missing/mismatched ABI or lifecycle observation is red even when compilation succeeds.

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_artifact_manifest.py tests/release/test_install_scripts.py tests/release/test_lifecycle_matrix.py tests/release/test_runtime_security_baseline.py tests/release/test_release_index.py tests/release/test_runner_authority.py -q
~~~

Expected: FAIL because release tooling and manifests are absent.

**Step 3: Implement the artifact contract**

~~~python
@dataclass(frozen=True)
class SbomRecord:
    path: str
    format: Literal["spdx-json", "cyclonedx-json"]
    sha256: str


@dataclass(frozen=True)
class ProvenanceRecord:
    path: str
    predicate_type: str
    sha256: str
    signature_bundle_path: str
    signature_bundle_sha256: str


@dataclass(frozen=True)
class ReleaseAssetRecord:
    filename: str
    kind: Literal[
        "archive", "checksums", "sbom", "provenance", "signature_bundle",
        "license_report", "check_evidence", "lifecycle_receipt", "provenance_review",
    ]
    sha256: str
    size_bytes: int
    media_type: str
    target: str | None
    sigstore_required: bool
    sigstore_bundle_filename: str | None
    certificate_identity: str | None
    certificate_oidc_issuer: str | None
    provenance_predicate_type: str | None


@dataclass(frozen=True)
class ManifestIdentity:
    filename: Literal["artifact-manifest.json"]
    canonical_payload_sha256: str
    final_file_sha256_source: Literal["ReleaseSubject.artifact_manifest_sha256"]


@dataclass(frozen=True)
class BuildIdentity:
    authority: Literal["diagnostic", "authorized_staging_payload"]
    staging_payload_sha256: str
    source_commit: str
    source_tree_sha256: str
    export_commit: str
    export_tree_sha256: str


@dataclass(frozen=True)
class ArtifactRecord:
    target: str
    filename: str
    sha256: str
    size_bytes: int
    product_version: str
    source_commit: str
    source_tree_sha256: str
    export_commit: str
    export_tree_sha256: str
    sbom: SbomRecord
    provenance: ProvenanceRecord


@dataclass(frozen=True)
class ArtifactManifest:
    schema_version: int
    source_commit: str
    source_tree_sha256: str
    export_commit: str
    export_tree_sha256: str
    artifacts: tuple[ArtifactRecord, ...]
    release_assets: tuple[ReleaseAssetRecord, ...]
    manifest_identity: ManifestIdentity


@dataclass(frozen=True)
class InstalledFileRecord:
    path: str
    kind: Literal["entrypoint", "runtime_support", "package_data", "license"]
    owner: str
    sha256: str
    size_bytes: int
    target: str
    version: str
    license_refs: tuple[str, ...]


@dataclass(frozen=True)
class ArtifactFragment:
    schema_version: int
    target: str
    build_identity: BuildIdentity
    component_manifest_path: str
    component_manifest_sha256: str
    installed_files_root_sha256: str
    installed_file_rows: tuple[InstalledFileRecord, ...]
    components: tuple[ComponentRecord, ...]
    component_verification_path: str
    component_verification_sha256: str
    component_verification: ComponentVerification
    artifact: ArtifactRecord
    target_assets: tuple[ReleaseAssetRecord, ...]


def build_target(
    target: Target,
    *,
    export_root: Path,
    component_root: Path,
    component_verification_path: Path,
    out_dir: Path,
    build_identity: BuildIdentity,
) -> ArtifactFragment:
    """Recompute identities, require a verified five-component layout, and archive one target."""
~~~

Each native runner writes exactly one `artifact-fragment.schema.json` document and target-local assets; a fragment is not a release manifest and `verify-fragment` requires exactly one expected target. The fragment binds the complete `component-manifest.json` digest, its sorted `installed_files` Merkle/root, and every file-row hash/size/license—not only the five entrypoint hashes—so the PyInstaller onedir runtime/Jedi/parso support closure is cryptographically covered. `release/package.py aggregate` accepts exactly the five target fragments, rejects duplicate/missing targets, mixed identity, incomplete physical-file closure, or any `authority=diagnostic` fragment, then atomically emits the sole final `artifact-manifest.json`. Packaging produces one archive per target plus SHA256SUMS, SPDX/CycloneDX SBOM, dependency license report, the signed native lifecycle matrix, the canonical provenance-review receipt, in-toto provenance, and cosign/Sigstore bundles.

`release/signing-policy.json` is the pre-freeze trust root: exact owner/repository, workflow ref, certificate identity, and OIDC issuer; it forbids regex/wildcard identities. `artifact-manifest.release_assets` is the exhaustive product-asset allowlist: every entry has expected SHA-256 and `sigstore_required`; required entries must echo the exact policy identity/issuer and name the exact bundle filename plus optional provenance predicate type. The artifact or manifest can never choose a broader accepted signer. The private workflow uses pinned `cosign sign-blob --yes --bundle` with GitHub OIDC and public Rekor; F4 aggregation, F5, and G7 compare every product, lifecycle-fragment, lifecycle-matrix, provenance bundle, and top-level release-index bundle to the tracked policy and invoke `cosign verify-blob --certificate-identity <exact-policy-value> --certificate-oidc-issuer <exact-policy-value>` rather than a free regex. It never relies on GitHub Artifact Attestations, which are not available to ordinary private personal repositories.

`artifact-manifest.json` avoids recursive self-hashing through `manifest_identity`: its canonical payload digest excludes only that digest field. Its product assets include a signed `private-check-evidence.json` whose schema closes over every private-capable workflow job/test/scan command, conclusion, exit/output digest, export identity, workflow run/job identity, and check-policy/GitHub-controls/SAST-policy digest; a missing or zero-execution job is red. After that manifest and all product assets are final, `tools/release_index.py create` emits the non-recursive top-level `release-index.json`, which binds the exact repository/tag/version, signing-policy digest, artifact-manifest final SHA-256, and every product asset filename/hash/size/media type. The signed index names `release-index.sigstore.json` but deliberately lists neither itself nor its bundle as an indexed asset; the bundle signs the final index bytes and ReleaseSubject stores both `artifact_manifest_sha256` and `release_index_sha256`. Thus the complete distribution set is exactly `{release-index.json, release-index.sigstore.json, artifact-manifest.json} + artifact-manifest.release_assets` without a hash cycle. F4, F5, and G7 reject missing or extra release assets and verify the index bundle first, then use only the verified index to locate and hash the manifest and product assets.

`release/verifier-bootstrap.json` pins cosign 3.1.2 official per-platform immutable URLs and SHA-256 values, and the installer generators embed those exact constants plus the exact signing identity/issuer/workflow. Install/update scripts fetch a tag-immutable index and bundle over HTTPS, download cosign only from the pinned URL, verify the verifier digest before execution, then verify the index bundle before trusting any URL, manifest, checksum, archive, update, or rollback metadata. There is no PATH-cosign, checksum-only, unsigned-cache, caller-identity, or best-effort fallback. A coordinated rewrite of archive, component manifest, SHA256SUMS, and release index still fails because the old bundle cannot authenticate changed index bytes; a bundle from another owner/repository/workflow/issuer also fails. The verified index then anchors complete component-closure verification before atomic replacement, one stored prior signed index+bundle for rollback, `codesextant doctor`, and automatic rollback if doctor fails. Update and rollback repeat signature/identity verification for both candidate and retained prior distributions. Uninstall removes every manifested installed file plus binaries/service metadata but requires an explicit `--purge-data` to remove local indexes.

`tools/runtime_security_baseline.py` reads actual packaged self-test facts and component digests, then checks the official release/security/advisory sources enumerated by `release/runtime-security-policy.json`. Policy fixes the source URLs/types, applicable component mapping, maximum observation age (24 hours at final subject freeze), severity rule, a fail-closed `pending_security_release` state, and no wildcard waiver. The tool fails closed on network/signature/content-digest/staleness failure, a declared-vs-packaged mismatch, a pin superseded by a security release, an officially announced pending security release for the pinned line, or applicable unwaived high/critical advisory. An embargoed/pending security-release hold is not waivable without authoritative upstream non-applicability evidence; once published, updating or retaining the pin requires a reviewed source/toolchain change and a complete rebuild. Any ordinary advisory exception is a tracked package+version+advisory+reason+owner+expiry entry reviewed before source freeze; the artifact cannot supply it. Each target fragment embeds the schema-valid baseline receipt and its digest. SBOM, component manifest, provenance predicate, lifecycle fragment, final artifact manifest, and ReleaseSubject all bind that same receipt. F4 reruns it immediately before signing; F5 verifies source content digests, signature identities where available, exact component mapping, pending-security-release state, and 24-hour freshness without rewriting evidence.

`release/targets.toml` remains the ABI/support authority shared with native Task 11. `release/runner-policy.json` is the separate execution-authority SSOT. For every target and both `oldest_supported` and `current` observations it fixes a concrete non-`latest` label tuple, OS name/version/build, immutable VM/container image digest, architecture, owner, provider/resource ID, closed attestation trust root (controller key ID plus Ed25519 public key, or exact GitHub OIDC issuer plus non-wildcard identity), ephemeral provisioning mode, and clean-teardown requirement. Windows x86_64 oldest is exactly Windows 10 22H2 build 10.0.19045; both macOS architectures oldest are exactly macOS 13.5; Linux baseline images are native-architecture digest pins with glibc 2.28. Oldest Windows/macOS observations use provisioned ephemeral self-hosted machines because GitHub-hosted labels do not provide those exact floors. A GitHub-hosted runner is permitted only when its API-reported image version, OS build, architecture, and image digest exactly match a committed policy row; otherwise that row must use an exact ephemeral self-hosted image. Current observations are also exact policy entries—never mutable `*-latest`. Every entry sets `allow_fallback=false` and `allow_emulation=false`; diagnostic emulation is a separate non-authoritative class that cannot enter a fragment.

`tools/runner_authority.py availability` performs a read-only preflight against the policy's exact provider/controller resource IDs before staging authorization and writes a short-lived signed `runner-availability.schema.json` receipt with policy digest, capacity, image digest, labels, architecture, probe UTC, and attester identity. Missing capacity, stale inventory, wrong image/label/build/arch, unattested controller, or unavailable exact oldest/current observation blocks F3; there is no substitute runner. After the private repository exists, each build job verifies its GitHub runner registration/labels and measured OS/image/architecture against that availability receipt, records clean initial disk/worktree/process state, and writes a signed `runner-attestation.schema.json` receipt. Finalization proves the one-job ephemeral machine was destroyed and its repository token/material erased; a persistent/dirty/unknown teardown is red. The workflow's static runs-on/matrix entries are mechanically equal to the tracked policy, and every job binds `runner_policy_sha256`; workflow input cannot select a label. `release/build.py` and `verify_components.py` consume `targets.toml` plus these runner records. Fragment aggregation rejects a target without matching ABI, runner availability/attestation/teardown, and both oldest/current native lifecycle observations. SBOM/provenance record the policy/attestation and ABI-inspection digests.

The F3 staging payload is the source/export identity authority. Before authorization, staging preflight recomputes both source and export commits/tree SHA-256 values. After authorization, `staging_prepare.py execute` passes `staging_payload_sha256`, `source_commit`, `source_tree_sha256`, `export_commit`, and `export_tree_sha256` as required immutable `workflow_dispatch` inputs. `artifact-smoke.yml` rejects missing inputs and checks the checked-out commit plus recomputed export tree before invoking `release/build.py` with all five values. The private source tree is not available on the rewritten export runner, so its identity is accepted only as an external parameter whose value is bound to the separately authorized staging payload; provenance records that distinction instead of claiming the runner observed the private tree. Every fragment, provenance predicate, final manifest, and ReleaseSubject repeats the same identities.

For each target, `artifact-smoke.yml` executes the native Task 11 pipeline without reinterpretation on the exact policy-selected target-native runner, with every source/script path rooted in the checked-out allowlist export and every generated object rooted in a fresh runner-temporary build directory outside both the immutable export and the final component layout: one locked Cargo build for `codesextant-cli`, `codesextant-mcp`, and `codesextant-daemon`, plus one locked Cargo build of the existing core package's `codesextant-ts` launcher binary; Python 3.11 invokes `<export>/sidecars/build.py --orchestrator-only --toolchain-lock <export>/sidecars/toolchain.lock.json --ts-launcher <target-native-launcher>`, which must provision/verify target-native CPython 3.14.6 and invoke that interpreter's `python -m PyInstaller`, and must assemble the verified private Node 24.18.0 onedir runtime plus bundle without PATH fallback; `<export>/install/component_layout.py assemble`; `<export>/release/verify_components.py`; ABI inspection; and the runtime-security-baseline receipt. Before any build it verifies the signed availability receipt plus measured runner identity; after upload it requires the signed clean-teardown record. Only that verified directory may be passed as `component_root` to `<export>/release/build.py`. The verifier writes receipts beside the layout under `<temp>/receipts/`, never inside the layout that is archived. `release/build.py` receives them separately, revalidates them, and the fragment schema binds their paths/SHA-256, runner-policy/availability/attestation/teardown digests, exact `component-manifest.json`, packaged CPython sys.version/SOABI/OpenSSL/SQLite and launcher/private-Node path plus Node/V8/OpenSSL facts, all five logical component entrypoint hashes/sizes/versions/targets/license refs, ABI/security baseline, the `installed_files` root, and every physical installed-file path/hash/size/license row including the private Node executable/support closure. The component manifest is deliberately outside its own `installed_files` table to avoid recursive self-hashing; physical-set equality excludes only that exact normalized manifest path, while the fragment independently binds its final bytes. Missing/extra component or physical file, an installed-file closure mismatch, wrong/unavailable/persistent runner, absent teardown, emulation/fallback, an orchestrator 3.11 embedded as runtime, a generated receipt embedded in the install tree, host/PATH runtime fallback, private-source build input, an experimental SEA artifact, or a Rust-only archive fails before signing.

Every F4 native job, on its own operating system and architecture, validates `release/native-lifecycle-contract.json` and invokes the exact `<export>/release/run_native_lifecycle.py` runner against that target's final and same-target previous/prerelease artifacts. It emits one `native-lifecycle-fragment.schema.json` document containing the target, staging/source/export identities, workflow run/job identity, runner OS/architecture, final and previous artifact hashes, all 19 native phase IDs in canonical order, and the separate G5 rollback/failed-update extension phases above. The job signs that canonical fragment with the pinned cosign/OIDC identity and emits its bundle; it cannot substitute static workflow inspection or foreign-target emulation for native execution.

The F4 aggregation job accepts exactly five target-distinct lifecycle fragments and their Sigstore bundles, verifies their configured workflow identity/OIDC issuer plus shared immutable identities, rejects duplicates/missing targets/emulation/diagnostic authority, and emits a canonical `native-lifecycle-matrix.json` release asset with all five fragment digests and embedded phase results. The matrix and its bundle are part of the exhaustive artifact manifest. F5 `release/package.py lifecycle-receipt` never executes a foreign binary: it verifies the matrix, all five signed fragments/bundles, exact contract digest/order/target identities, required previous-artifact evidence, and G5 extension phases, then wraps that verified result in the G3 gate envelope. `release/evidence/gate-status.schema.json` validates the outer gate envelope, while `release/lifecycle-receipt.schema.json` validates only the typed lifecycle domain object under `payload`; the registry-driven validator must apply both schemas. Missing, merged, renamed, skipped, generic `cli`/`mcp`/`http`, unsigned, wrong-runner, or absent previous-artifact evidence is red.

release/package.py lifecycle-pair copies the clean final export to an isolated temporary tree, derives a test-only `{product_version}-rc.1`, builds the complete three-binary/two-sidecar component layout for that previous artifact, verifies all five hashes/licenses, and leaves the final export untouched. artifact-smoke.yml supplies the same-target previous artifact to the native runner and uses prerelease/final layouts for the exact native plus G5 extension phases above. The failed-update case supplies a separately hashed corrupted full-layout payload, requires the update command itself to fail, proves automatic rollback, and proves the post-rollback version/components remain the previously healthy final layout. The prerelease and corrupted payload are test-only inputs: they are named in the lifecycle receipt but excluded from ReleaseSubject and the final draft release assets. Linux aarch64 may use emulation for diagnostics, but G3/G5 cannot pass without a native receipt.

**Step 4: Run local GREEN**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_artifact_manifest.py tests/release/test_install_scripts.py tests/release/test_lifecycle_matrix.py tests/release/test_runtime_security_baseline.py tests/release/test_release_index.py tests/release/test_runner_authority.py -q
C:\Python311\python.exe tools/release_index.py schema-check --schema release/release-index.schema.json --signing-policy release/signing-policy.json --verifier-bootstrap release/verifier-bootstrap.json
C:\Python311\python.exe tools/runner_authority.py schema-check --policy release/runner-policy.json --policy-schema release/runner-policy.schema.json --availability-schema release/runner-availability.schema.json --attestation-schema release/runner-attestation.schema.json --targets release/targets.toml --workflow .github/workflows/artifact-smoke.yml
$localExport = Join-Path $env:TEMP ("codesextant-export-" + [Guid]::NewGuid().ToString("N"))
$buildRoot = Join-Path $env:TEMP ("codesextant-build-" + [Guid]::NewGuid().ToString("N"))
$dryIdentity = Join-Path $env:TEMP ("codesextant-build-identity-" + [Guid]::NewGuid().ToString("N") + ".json")
C:\Python311\python.exe tools/public_export.py prepare --source . --dest $localExport --config release/public-export.toml --diagnostic-receipt $dryIdentity
$identity = Get-Content -Raw -Encoding UTF8 -LiteralPath $dryIdentity | ConvertFrom-Json
$cargoTarget = Join-Path $buildRoot 'cargo-target'
$sidecarRoot = Join-Path $buildRoot 'sidecars\x86_64-pc-windows-msvc'
$componentRoot = Join-Path $buildRoot 'installed-layout\x86_64-pc-windows-msvc'
$componentReceipt = Join-Path $buildRoot 'receipts\component-verification.json'
$fragment = Join-Path $buildRoot 'fragments\x86_64-pc-windows-msvc.json'
New-Item -ItemType Directory -Force -Path (Split-Path $componentReceipt),(Split-Path $fragment) | Out-Null
cargo build --locked --manifest-path (Join-Path $localExport 'Cargo.toml') --target-dir $cargoTarget --release -p codesextant-cli -p codesextant-mcp -p codesextant-daemon
cargo build --locked --manifest-path (Join-Path $localExport 'Cargo.toml') --target-dir $cargoTarget --release -p codesextant-core --bin codesextant-ts
C:\Python311\python.exe (Join-Path $localExport 'sidecars\build.py') --orchestrator-only --toolchain-lock (Join-Path $localExport 'sidecars\toolchain.lock.json') --source-root $localExport --target x86_64-pc-windows-msvc --ts-launcher (Join-Path $cargoTarget 'release\codesextant-ts.exe') --out $sidecarRoot
C:\Python311\python.exe (Join-Path $localExport 'install\component_layout.py') assemble --source-root $localExport --target x86_64-pc-windows-msvc --bin-root (Join-Path $cargoTarget 'release') --sidecar-root $sidecarRoot --out $componentRoot
C:\Python311\python.exe (Join-Path $localExport 'release\verify_components.py') --root $componentRoot --receipt $componentReceipt
C:\Python311\python.exe (Join-Path $localExport 'release\build.py') --target x86_64-pc-windows-msvc --export-root $localExport --component-root $componentRoot --component-verification $componentReceipt --identity-authority diagnostic --staging-payload-sha256 ('0' * 64) --source-commit $identity.source_commit --source-tree-sha256 $identity.source_tree_sha256 --export-commit $identity.export_commit --export-tree-sha256 $identity.export_tree_sha256 --out-fragment $fragment
C:\Python311\python.exe (Join-Path $localExport 'release\package.py') verify-fragment --fragment $fragment --asset-root $buildRoot
~~~

Expected: tests and the local single-target Windows fragment verification exit 0. It does not create or claim a final artifact manifest. Native cross-platform fragments are produced and aggregated later by F4/F5.

**Step 5: Commit**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('release/targets.toml','release/signing-policy.schema.json','release/signing-policy.json','release/verifier-bootstrap.schema.json','release/verifier-bootstrap.json','release/release-index.schema.json','release/private-check-evidence.schema.json','release/runner-policy.schema.json','release/runner-policy.json','release/runner-availability.schema.json','release/runner-attestation.schema.json','release/artifact-fragment.schema.json','release/artifact-manifest.schema.json','release/evidence/artifacts.schema.json','release/native-lifecycle-fragment.schema.json','release/lifecycle-receipt.schema.json','release/runtime-security-baseline.schema.json','release/runtime-security-policy.json','release/build.py','release/package.py','release/provenance.py','tools/release_index.py','tools/runner_authority.py','tools/runtime_security_baseline.py','tools/sync_version.py','install/install.ps1','install/uninstall.ps1','install/install.sh','install/update.ps1','install/update.sh','install/uninstall.sh','.github/workflows/artifact-smoke.yml','tests/release/test_artifact_manifest.py','tests/release/test_install_scripts.py','tests/release/test_lifecycle_matrix.py','tests/release/test_runtime_security_baseline.py','tests/release/test_release_index.py','tests/release/test_runner_authority.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'release: build signed cross-platform artifact matrix'
~~~

### Task 8: Implement final-freeze and private-staging orchestration

**Files:**

- Modify: .gitignore
- Create: release/staging-policy.json
- Create: release/staging.schema.json
- Create: release/staging-authorization.schema.json
- Create: release/staging-probe.schema.json
- Create: release/public-transparency-log-disclosure.schema.json
- Create: tools/staging_preflight.py
- Create: tools/staging_prepare.py
- Create: tools/freeze_release_subject.py
- Create: tests/release/test_staging_preflight.py
- Create: tests/release/test_release_subject_freeze.py
- Generated private config, never exported or committed: release/staging.json
- Generated private authorization, never exported or committed: release/staging-authorization.json

**Step 1: Write RED tests**

~~~python
def test_preflight_requires_the_exact_final_repository_private(valid_config) -> None:
    valid_config["owner"] = "aiking931931"
    assert staging_preflight(valid_config, VALID_AUTHORIZATION).status == "fail"
    valid_config["owner"] = "Zeroxrain99"
    valid_config["repository"] = "CodeSextant-staging"
    assert staging_preflight(valid_config, VALID_AUTHORIZATION).status == "fail"
    valid_config["repository"] = "CodeSextant"
    valid_config["visibility"] = "public"
    assert staging_preflight(valid_config, VALID_AUTHORIZATION).status == "fail"


def test_release_subject_rejects_source_export_or_artifact_mismatch(
    clean_source, clean_export, artifact_manifest, signed_release_index
) -> None:
    artifact_manifest["source_commit"] = "0" * 40
    assert freeze_subject(
        clean_source, clean_export, artifact_manifest, signed_release_index
    ).status == "fail"


def test_release_subject_rejects_unsigned_or_mismatched_release_index(
    clean_source, clean_export, artifact_manifest, signed_release_index
) -> None:
    signed_release_index["artifact_manifest_sha256"] = "0" * 64
    assert freeze_subject(
        clean_source, clean_export, artifact_manifest, signed_release_index
    ).status == "fail"


def test_preflight_is_network_free(monkeypatch, valid_config) -> None:
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert staging_preflight(valid_config, VALID_AUTHORIZATION).status == "pass"


def test_authorization_is_separate_and_binds_exact_staging_payload(valid_plan) -> None:
    authorization = authorize_fixture(canonical_sha256(valid_plan))
    assert "authorization" not in valid_plan
    assert verify_staging_authorization(valid_plan, authorization).status == "pass"
    valid_plan["rollback_new_private_repository_on_failure"] = False
    assert verify_staging_authorization(valid_plan, authorization).status == "fail"


def test_staging_plan_binds_security_controls_sast_and_runner_authority(valid_plan) -> None:
    assert valid_plan["check_policy_sha256"] == sha256_file("release/check-policy.json")
    assert valid_plan["github_controls_sha256"] == sha256_file("release/github-controls.json")
    assert valid_plan["runner_policy_sha256"] == sha256_file("release/runner-policy.json")
    assert valid_plan["verifier_bootstrap_sha256"] == sha256_file(
        "release/verifier-bootstrap.json"
    )
    assert valid_plan["pre_public_sast_sha256"] == sha256_file(
        "release/evidence/pre-public-sast.json"
    )
    assert valid_plan["runner_availability_sha256"] == sha256_file(
        "release/evidence/runner-availability.json"
    )
    assert verify_staging_plan(valid_plan).status == "pass"
    valid_plan["github_controls_sha256"] = "0" * 64
    assert verify_staging_plan(valid_plan).status == "fail"


def test_staging_authorization_requires_exact_irreversible_rekor_disclosure(valid_plan) -> None:
    disclosure = valid_plan["public_transparency_log_disclosure"]
    assert disclosure["provider"] == "sigstore_rekor"
    assert disclosure["irreversible"] is True
    assert disclosure["repository"] == "Zeroxrain99/CodeSextant"
    assert disclosure["workflow_ref"] == ".github/workflows/artifact-smoke.yml"
    assert set(disclosure["statement_categories"]) == {
        "product_artifact",
        "release_index",
        "native_lifecycle_fragment",
        "native_lifecycle_matrix",
        "provenance_review",
    }
    assert {"release-index.json", "release-index.sigstore.json"} <= set(
        disclosure["asset_names"]
    )
    authorization = authorize_fixture(
        canonical_sha256(valid_plan),
        acknowledged_public_transparency_log=True,
    )
    assert verify_staging_authorization(valid_plan, authorization).status == "pass"
    authorization["acknowledged_public_transparency_log"] = False
    assert verify_staging_authorization(valid_plan, authorization).status == "fail"


def test_rekor_disclosure_forbids_unplanned_statement_or_asset_scope(valid_plan) -> None:
    valid_plan["public_transparency_log_disclosure"]["asset_names"].append("unplanned.bin")
    assert verify_staging_plan(valid_plan).status == "fail"


def test_compensation_never_claims_rekor_records_were_erased(failed_run) -> None:
    result = compensate_private_staging(failed_run)
    assert result.github_repository_state == "absent"
    assert result.public_transparency_log_state == "authorized_records_remain"


def test_existing_destination_is_not_a_fresh_staging_repo(valid_probe) -> None:
    valid_probe["exists"] = True
    valid_probe["repository_id"] = 123
    assert validate_destination_probe(valid_probe).status == "fail"


def test_compensation_can_delete_only_the_repo_created_by_this_run(created_repo, run_state) -> None:
    run_state.created_repository_id = created_repo.id
    assert rollback_allowed(created_repo, run_state) is True
    run_state.created_repository_id = created_repo.id + 1
    assert rollback_allowed(created_repo, run_state) is False


@pytest.mark.parametrize(
    "field,mutated",
    [
        ("visibility", "PUBLIC"),
        ("owner", "NotZeroxrain99"),
        ("repository", "NotCodeSextant"),
        ("creation_transaction_id", "other-transaction"),
        ("destination_probe_sha256", "0" * 64),
        ("staging_payload_sha256", "1" * 64),
        ("authorization_sha256", "2" * 64),
        ("created_repository_id", 999999),
    ],
)
def test_compensation_refuses_any_destructive_authority_mismatch(
    created_repo, run_state, field, mutated
) -> None:
    candidate = copy.deepcopy(run_state)
    setattr(candidate, field, mutated)
    assert rollback_allowed(created_repo, candidate) is False
    assert delete_repository_if_authorized(created_repo, candidate).status == "fail_closed"


def test_private_generated_files_are_gitignored(repo_root: Path) -> None:
    assert is_git_ignored(repo_root / "release/staging.json")
    assert is_git_ignored(repo_root / "release/staging-authorization.json")
    assert is_git_ignored(repo_root / "release/evidence/staging-probe.json")
    assert is_git_ignored(repo_root / "release/evidence/public-evidence-assets.json")
    assert is_git_ignored(repo_root / "release/evidence/pre-public-sast.json")
    assert is_git_ignored(repo_root / "release/evidence/runner-availability.json")
    assert is_git_ignored(repo_root / "release/evidence/runner-attestations/example.json")
    assert is_git_ignored(repo_root / "release/evidence/security-review-request.json")
    assert is_git_ignored(repo_root / "release/evidence/security-review-input.json")
    assert is_git_ignored(repo_root / "release/evidence/security-findings.json")
    assert is_git_ignored(repo_root / "release/staging/g4/g4-public-assets.json")
    assert is_git_ignored(repo_root / "release/assets/g6-public-assets.json")
    assert is_git_ignored(repo_root / "release/assets/dogfood-deadbeefcafe-report.md")
~~~

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_staging_preflight.py tests/release/test_release_subject_freeze.py -q
~~~

Expected: collection fails because staging_preflight and freeze_release_subject do not exist.

**Step 3: Implement the no-side-effect planners**

release/staging-policy.json is the G5-owned destination authority: owner Zeroxrain99, repository CodeSextant, visibility private, default branch main, `require_absent=true`, one derived tag, one draft release, `check_policy_sha256`, `github_controls_sha256`, `runner_policy_sha256`, `verifier_bootstrap_sha256`, only the `private_capable` required checks plus native artifact matrix, and `rollback_new_private_repository_on_failure=true`. The generated staging plan additionally binds the fresh exact-export `pre_public_sast_sha256` and signed `runner_availability_sha256`. It explicitly does not require CodeQL, Scorecard, or dependency-review in private staging: the first two are public corroboration, while all legal pre-public SAST gates are already mandatory. It also contains a closed `public_transparency_log_disclosure` validated by release/public-transparency-log-disclosure.schema.json: provider `sigstore_rekor`; exact repository, workflow ref, signing-policy digest, release tag, and exhaustive asset names including the top-level signed release index/bundle; statement categories `product_artifact`, `release_index`, `native_lifecycle_fragment`, `native_lifecycle_matrix`, and `provenance_review`; the public certificate/statement/hash metadata fields; and `irreversible=true`. The disclosure forbids wildcard or caller-added asset/statement scope and explicitly excludes secrets, credentials, private paths, raw source, prompts, and user email. release/staging.schema.json binds that disclosure and policy to exact source/export tree identities, expected checks, GitHub controls, runner authority/availability, pre-public SAST, and verifier bootstrap. release/staging-authorization.schema.json defines a separate short-lived receipt whose `staging_payload_sha256` hashes only the immutable staging payload, including the narrowly scoped rollback and disclosure; it requires `acknowledged_public_transparency_log=true`. Authorization is never embedded in the payload it hashes. release/staging-probe.schema.json records the read-only GitHub lookup, actor, UTC time, requested owner/repository, and `exists`; a fresh run requires `exists=false`.

tools/staging_prepare.py has `probe`, `plan`, `show-authorization-request`, `record-authorization`, and `execute` subcommands. `probe` is read-only and fails if the exact destination already exists; it never deletes, renames, or reuses a repository. `plan` is network-free and emits exact one-shot GitHub operations from the policy plus a fresh probe, schema-valid pre-public SAST report, and signed runner-availability receipt; it rejects a source-root report, stale/unavailable runner, digest mismatch, or any omitted private blocker. `show-authorization-request` prints the canonical payload digest and every external effect, including that Sigstore/Rekor publication is public, append-only, independently discoverable, and not erased by repository rollback. Only after the user explicitly authorizes that displayed digest and supplies `--acknowledge-public-transparency-log` may `record-authorization` write the separate schema-valid receipt; it cannot modify the plan. `execute` refuses unless gh api user returns Zeroxrain99, all policy/evidence/authorization payload and disclosure digests match, authorization is unexpired, the runner availability and destination probe are still fresh, and a second existence check still returns not found. It records the newly created GitHub repository ID before any later mutation. On a later F4 failure it may delete only that same still-private repository ID, created by this run, when the immutable authorization includes the rollback; it never deletes a pre-existing, mismatched, or public repository. A successful compensation may prove the GitHub repository is absent, but its receipt must say `public_transparency_log_state=authorized_records_remain`; Rekor entries cannot be rolled back. A failed compensation stops for user intervention instead of reusing dirty state. `tools/staging_preflight.py schema-check` validates tracked policy and all four schemas plus the cross-file GitHub/runner/check/verifier policies without requiring generated runtime identities or authorization. `tools/freeze_release_subject.py` derives product_version from codesextant._version.__version__, derives release_tag as v plus that value, independently verifies clean source/export trees, artifact manifest, release-index Sigstore bundle against the tracked signing/bootstrap policies, and exact distribution asset closure, captures one UTC `frozen_at_utc` immediately before atomic replace, and writes canonical release/evidence/release-subject.json with that timestamp covered by the subject digest.

**Step 4: Run GREEN**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_staging_preflight.py tests/release/test_release_subject_freeze.py -q
C:\Python311\python.exe tools/staging_preflight.py schema-check --schema release/staging.schema.json --authorization-schema release/staging-authorization.schema.json --probe-schema release/staging-probe.schema.json --transparency-disclosure-schema release/public-transparency-log-disclosure.schema.json --policy release/staging-policy.json --check-policy release/check-policy.json --github-controls release/github-controls.json --runner-policy release/runner-policy.json --verifier-bootstrap release/verifier-bootstrap.json
~~~

Expected: tests and schema/policy checks exit 0. The live authorized preflight is deliberately deferred to F3 after final source/export/artifact identities exist.

**Step 5: Commit all source-side orchestration before freeze**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('.gitignore','release/staging-policy.json','release/staging.schema.json','release/staging-authorization.schema.json','release/staging-probe.schema.json','release/public-transparency-log-disclosure.schema.json','tools/staging_preflight.py','tools/staging_prepare.py','tools/freeze_release_subject.py','tests/release/test_staging_preflight.py','tests/release/test_release_subject_freeze.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'release: orchestrate immutable private staging'
~~~

## Final Freeze and Private Staging Runbook

This runbook is an external execution phase, not an implementation task. It begins only after Tasks 1 through 8, all G0-G3/native-kernel work, all benchmark harness code, all G6 documentation/verification tooling, and G7 Task 1's complete product-frozen publication/G8 trust-bootstrap closure are committed. That last prerequisite includes the G7 transaction initializer, ACL-installed G8 seed verifier, content-addressed product-root bootstrap and receipt schema, product-frozen G8 initializer/node-context schema, additive private-overlay bootstrap, transaction router, and all associated tests. `release/security-review-scope.json` must already name and digest-bind this exact closed set. From Step F1 onward, any tracked change invalidates the run and restarts F1; adding a missing G7/G8 trust-bootstrap file after freeze is forbidden and forces a new G5 review/freeze.

Run F1-F5 in one `pwsh` 7.4-or-newer session. Run this fail-fast prelude first and repeat it after any shell restart. `$PSNativeCommandUseErrorActionPreference` converts every unhandled nonzero native exit into a terminating error; every command that captures stdout must additionally reject missing or malformed output. The only intentionally allowed nonzero status is the pre-authorization `2` in F3, handled locally with native-error promotion temporarily disabled.

~~~powershell
if ($PSVersionTable.PSVersion -lt [Version]'7.4') { throw 'pwsh 7.4 or newer is required for fail-fast native command handling' }
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
~~~

### F1: Verify and freeze the clean source

~~~powershell
C:\Python311\python.exe -m pytest -q
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace
cargo run --locked -q -p xtask -- contracts check
C:\Python311\python.exe tools/release_gate.py validate-registry --registry release/evidence/receipt-registry.json --registry-schema release/evidence/receipt-registry.schema.json --subject-schema release/evidence/release-subject.schema.json --receipt-schema release/evidence/gate-status.schema.json --require-payload-schemas
C:\Python311\python.exe tools/generate_producer_launch_policy.py check --through-phase FINAL_PRE_FREEZE --registry release/evidence/receipt-registry.json --policy release/evidence/producer-launch-policy.json --schema release/evidence/producer-launch-policy.schema.json --require-exact-public-closure
C:\Python311\python.exe tools/release_gate.py validate-launch-policy --registry release/evidence/receipt-registry.json --launch-policy release/evidence/producer-launch-policy.json --launch-policy-schema release/evidence/producer-launch-policy.schema.json --require-entrypoint-digests --require-all-signer-policies
C:\Python311\python.exe tools/release_gate.py validate-signing-env-registry --registry release/signing-environment-registry.json --schema release/signing-environment-registry.schema.json --launch-policy release/evidence/producer-launch-policy.json --require-exact-forbidden-closure
C:\Python311\python.exe tools/sync_version.py --check --phase binaries
C:\Python311\python.exe tools/bootstrap_release_tools.py verify --lock release/toolchain.lock
$toolBin = & C:\Python311\python.exe tools/bootstrap_release_tools.py ensure --lock release/toolchain.lock --print-bin
$toolBin = [string]$toolBin
if ([string]::IsNullOrWhiteSpace($toolBin) -or -not (Test-Path -LiteralPath $toolBin -PathType Container)) { throw 'locked release tool directory was not produced' }
$releasePython = & C:\Python311\python.exe tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python
$releasePython = [string]$releasePython
if ([string]::IsNullOrWhiteSpace($releasePython) -or -not (Test-Path -LiteralPath $releasePython -PathType Leaf)) { throw 'locked release Python bootstrap did not return an executable' }
$releasePythonVersion = & $releasePython -c "import cryptography; print(cryptography.__version__)"
if ($LASTEXITCODE -ne 0 -or $releasePythonVersion -ne '45.0.5') { throw 'locked release Python cryptography verification failed' }
& $releasePython tools/security_review.py validate-scope --scope release/security-review-scope.json --threat-model THREAT_MODEL.md --require-material-digests --require-material-id signing_environment_registry_schema --require-material-id signing_environment_registry --require-material-id g8_seed_installer --require-material-id g8_seed_install_receipt_schema --require-material-id g8_seed_install_tombstone_schema --require-material-id g6_release_authority_schema --require-material-id g6_release_authority_tombstone_schema --require-material-id g6_release_migration_schema --require-material-id g6_release_migration_signing_policy_schema --require-material-id g6_release_migration_signing_policy --require-material-id g6_release_migration_key_provisioner --require-material-id g8_seed_installer_signing_policy --require-material-id g8_authenticode_signing_policy --require-material-id g8_authenticode_signing_policy_schema --require-material-id g8_seed_machine_key_provisioner --require-material-id g8_authenticode_trust_provisioner --require-material-id g8_seed_static_verifier_source --require-material-id g8_seed_standalone_installer_build_spec --require-material-id g6_context_preflight_source --require-material-id g6_runbook_launcher_source --require-material-id g6_signed_runbook --require-material-id g6_runbook_renderer --require-material-id g8_seed_acl_no_reparse_negative_tests --require-material-id g8_seed_static_verifier_tests --require-material-id g6_context_preflight_tests --require-material-id g6_runbook_bootstrap_tests --require-material-id g7_context_initializer --require-material-id g8_acl_installed_seed_verifier --require-material-id g8_product_execution_root_bootstrap --require-material-id g8_context_initializer_and_node_bundle --require-material-id private_application_repo_bootstrap
if ($LASTEXITCODE -ne 0) { throw 'final G5 scope does not digest-bind the complete pre-freeze G7/G8 trust-bootstrap closure' }
& pwsh -NoProfile -File tools/provision_g8_seed_machine_key.ps1 -VerifyExisting -Policy release/g8-seed-installer-signing-policy.json
if ($LASTEXITCODE -ne 0) { throw 'pre-provisioned nonexportable G8 machine receipt key does not match committed public policy' }
& pwsh -NoProfile -File tools/provision_g8_authenticode_trust.ps1 -VerifyExisting -Policy release/g8-authenticode-signing-policy.json -AssertPublicOnly -NoPrivateOutput
if ($LASTEXITCODE -ne 0) { throw 'LocalMachine TrustedPublisher leaf does not match committed Authenticode policy' }
& pwsh -NoProfile -File tools/provision_g6_release_migration_key.ps1 -VerifyExisting -Policy release/g6-release-migration-signing-policy.json -AssertDistinctFromPolicy release/g8-seed-installer-signing-policy.json -NoPrivateOutput
if ($LASTEXITCODE -ne 0) { throw 'pre-provisioned G6 migration key does not match the committed distinct policy' }
C:\Python311\python.exe tools/verify_actions_pinned.py .github/workflows
C:\Python311\python.exe tools/pre_public_sast.py verify-lock --lock requirements/sast.lock --rules security/semgrep-rules.yml --ruff-config security/ruff-security.toml
C:\Python311\python.exe tools/github_controls.py schema-check --controls release/github-controls.json --schema release/github-controls.schema.json --check-policy release/check-policy.json
C:\Python311\python.exe tools/runner_authority.py schema-check --policy release/runner-policy.json --policy-schema release/runner-policy.schema.json --availability-schema release/runner-availability.schema.json --attestation-schema release/runner-attestation.schema.json --targets release/targets.toml --workflow .github/workflows/artifact-smoke.yml
C:\Python311\python.exe tools/release_index.py schema-check --schema release/release-index.schema.json --signing-policy release/signing-policy.json --verifier-bootstrap release/verifier-bootstrap.json
$actionlint = Join-Path $toolBin 'actionlint.exe'
$workflowFiles = Get-ChildItem -LiteralPath .github/workflows -Filter '*.yml' -File | ForEach-Object FullName
foreach ($workflowFile in $workflowFiles) { & $actionlint -- $workflowFile }
C:\Python311\python.exe tools/license_audit.py check --root .
C:\Python311\python.exe tools/check_public_docs.py --root .
git diff --check
$sourceStatus = @(git status --porcelain)
if ($sourceStatus.Count -ne 0) { throw "source tree is not clean: $($sourceStatus -join '; ')" }
~~~

Expected: every command exits 0, every final workflow (including the later artifact-smoke and dogfood-anchor workflows) passes both the SHA-pin policy and the pinned actionlint executable, and status is empty. The source-root license call here is explicitly diagnostic; it cannot become the G5 license receipt. Record source_commit and source_tree_sha256 without editing the tree.

### F2: Recreate and audit the final allowlist export

~~~powershell
$exportRoot = Join-Path $env:TEMP ("codesextant-final-export-" + [Guid]::NewGuid().ToString("N"))
C:\Python311\python.exe tools/public_export.py prepare --source . --dest $exportRoot --config release/public-export.toml
git -C $exportRoot branch -M main
C:\Python311\python.exe tools/public_export.py audit --repo $exportRoot
C:\Python311\python.exe tools/check_map_quality.py check --repo $exportRoot --scope product --budget 12000 --min-results 50 --required-class first_party_source --expectations (Join-Path $exportRoot 'tests\fixtures\map_gate_expectations.json')
C:\Python311\python.exe tools/license_audit.py check --root $exportRoot
C:\Python311\python.exe tools/pre_public_sast.py run --root $exportRoot --dependency-lock (Join-Path $exportRoot 'requirements\sast.lock') --semgrep-rules (Join-Path $exportRoot 'security\semgrep-rules.yml') --ruff-config (Join-Path $exportRoot 'security\ruff-security.toml') --out release/evidence/pre-public-sast.json
C:\Python311\python.exe tools/runner_authority.py availability --policy release/runner-policy.json --out release/evidence/runner-availability.json --max-age-minutes 30
$exportStatus = @(git -C $exportRoot status --porcelain)
if ($exportStatus.Count -ne 0) { throw "export tree is not clean: $($exportStatus -join '; ')" }
~~~

Expected: audit, exported quality/license diagnostics, authoritative pre-public SAST, and signed exact-runner availability all exit 0; export status is empty and its commit/tree identities are recorded. The SAST report binds this export and every required private check; the availability receipt proves all ten oldest/current native observations have exact capacity with immutable images. Never reuse an earlier temporary export or runner receipt.

### F3: Build the private-staging payload and obtain authorization

~~~powershell
C:\Python311\python.exe tools/staging_prepare.py probe --policy release/staging-policy.json --out release/evidence/staging-probe.json
C:\Python311\python.exe tools/staging_prepare.py plan --source . --export $exportRoot --policy release/staging-policy.json --destination-probe release/evidence/staging-probe.json --pre-public-sast release/evidence/pre-public-sast.json --runner-availability release/evidence/runner-availability.json --out release/staging.json
C:\Python311\python.exe tools/staging_prepare.py show-authorization-request --plan release/staging.json
$oldNativePreference = $PSNativeCommandUseErrorActionPreference
try {
  $PSNativeCommandUseErrorActionPreference = $false
  & C:\Python311\python.exe tools/staging_preflight.py --config release/staging.json --authorization release/staging-authorization.json
  $preAuthorizationExit = $LASTEXITCODE
} finally {
  $PSNativeCommandUseErrorActionPreference = $oldNativePreference
}
if ($preAuthorizationExit -ne 2) { throw "pre-authorization check must exit exactly 2, got $preAuthorizationExit" }
~~~

Expected before authorization: the probe proves `Zeroxrain99/CodeSextant` does not exist and preflight exits 2 only for missing authorization. If the repository exists, stop without mutation; deleting or reusing it requires a new, explicit destructive-operation plan outside this runbook. Present the payload digest, Zeroxrain99/CodeSextant, PRIVATE visibility, main branch, derived version/tag, planned draft release, narrowly scoped rollback of a repository created by this run, and the complete `public_transparency_log_disclosure`: exact artifact/lifecycle/provenance statement scope, exact workflow/signing identity, the public certificate/hash metadata, and the fact that Rekor records are irreversible even if staging is rolled back. After the user authorizes that exact displayed payload and explicitly acknowledges the public transparency log, record it and rerun preflight:

~~~powershell
C:\Python311\python.exe tools/staging_prepare.py record-authorization --plan release/staging.json --acknowledge-public-transparency-log --authorized-by user --expires-minutes 30 --out release/staging-authorization.json
C:\Python311\python.exe tools/staging_preflight.py --config release/staging.json --authorization release/staging-authorization.json
~~~

Expected: preflight exits 0. This authorization permits only the disclosed append-only Rekor entries while the GitHub repository remains private; it does not authorize public repository visibility or deletion of any pre-existing repository.

### F4: Create the exact private destination and run the native matrix

First verify gh api user --jq .login prints Zeroxrain99. Then tools/staging_prepare.py execute performs one fresh transaction:

~~~powershell
gh api user --jq .login
C:\Python311\python.exe tools/staging_prepare.py execute --plan release/staging.json --authorization release/staging-authorization.json
~~~

1. re-check that Zeroxrain99/CodeSextant is absent, then create that exact repository as PRIVATE; if it appeared since the probe, abort without mutation;
2. push the export commit as refs/heads/main and set main as default;
3. apply and verify the private-feasible phase of the hash-bound `release/github-controls.json`, then run and require the complete hash-bound `private_capable` check set—including pre-public SAST—plus the native artifact matrix; every build command and script is rooted in the checked-out allowlist export, while cargo targets, sidecars, component layouts, verification receipts, lifecycle fragments, and archives go to fresh runner-temporary directories outside both the export and the exact install layout; CodeQL/Scorecard are later public corroboration and dependency-review is a future PR safeguard, so none may substitute for a private blocker;
4. create the derived annotated tag on the export commit;
5. create one draft release for that tag;
6. trigger the pinned artifact-smoke workflow;
7. wait for every exact policy-authorized native target, including native Linux aarch64, to verify runner availability/identity, build its exact five-component layout, write the component/ABI/runtime-security/runner attestations outside that layout, execute lifecycle on both oldest-supported and current OS natively, prove clean ephemeral teardown, and emit one identity-bound lifecycle fragment plus pinned-cosign bundle;
8. verify and aggregate exactly five target-distinct lifecycle fragments and fresh runtime-security/ABI/runner receipts into signed matrices; build `release/g8-seed-static-verifier.rs`, `release/g6-context-preflight.rs`, and `release/g6-runbook-launcher.rs` with the pinned Windows Rust toolchain, and build reviewed `tools/install_g8_seed.py` through `release/g8-seed-installer.spec`, yielding four executables. Authenticode-sign all four with the pre-F1 policy certificate, run required WinVerifyTrust revocation/timestamp/pin checks, and require the committed signer identity. Create the final artifact manifest with exactly five product-frozen trust assets: `g8_seed_verifier`/`Bootstrap-CodeSextantG8ProductExec.ps1`, `g8_seed_static_verifier`/`codesextant-g8-seed-static-verify.exe`, `g8_seed_installer`/`codesextant-g8-seed-installer.exe`, `g6_context_preflight`/`codesextant-g6-context-preflight.exe`, and `g6_runbook_launcher`/`codesextant-g6-runbook-launcher.exe`. Generate/sign the release index from that closure and attach all five; reject missing/extra/duplicate role-name pairs, unpinned signatures, or bytes not derived from reviewed inputs.

No visibility change occurs.

If steps 2 through 8 fail, execute the authorized compensation only after matching the recorded repository ID and confirming visibility is still PRIVATE. A successful compensation returns the GitHub repository to the absent state so F3 can create a new probe/authorization, but its signed receipt must preserve `public_transparency_log_state=authorized_records_remain` because append-only Rekor entries cannot be deleted. Without a successful GitHub compensation, stop and do not retry or reuse the partial repository.

### F5: Freeze ReleaseSubject, emit G0-G3 and G5 receipts, and validate deferred G4

Download the draft assets to a new empty directory and verify the signed index before trusting paths/checksums. `release/package.py verify` enforces the exact distribution and exactly five typed trust role/name pairs listed in F4, proves the script equals reviewed export bytes, proves all four executables derive from reviewed source/spec closures, and checks each against the pre-F1 Authenticode leaf/issuer/revocation/timestamp policy. Missing/extra/sixth trust assets fail. ReleaseSubject, artifact receipt, G6 authority, and seed-install receipt bind the five role/name/digest rows. These are the only G6/G7 preflight/install/launcher inputs.

~~~powershell
$staging = Get-Content -Raw -Encoding UTF8 -LiteralPath release/staging.json | ConvertFrom-Json
$assetRoot = Join-Path $env:TEMP ("codesextant-final-assets-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $assetRoot | Out-Null
gh release download $staging.release_tag --repo Zeroxrain99/CodeSextant --dir $assetRoot
$releaseIndex = Join-Path $assetRoot 'release-index.json'
$releaseIndexBundle = Join-Path $assetRoot 'release-index.sigstore.json'
$artifactManifest = Join-Path $assetRoot 'artifact-manifest.json'
C:\Python311\python.exe tools/release_index.py verify --index $releaseIndex --bundle $releaseIndexBundle --asset-root $assetRoot --signing-policy release/signing-policy.json --verifier-bootstrap release/verifier-bootstrap.json
C:\Python311\python.exe release/package.py verify --release-index $releaseIndex --release-index-bundle $releaseIndexBundle --manifest $artifactManifest --asset-root $assetRoot --signing-policy release/signing-policy.json --verifier-bootstrap release/verifier-bootstrap.json
C:\Python311\python.exe tools/runtime_security_baseline.py verify-matrix --manifest $artifactManifest --asset-root $assetRoot --policy release/runtime-security-policy.json --max-age-hours 24
C:\Python311\python.exe tools/freeze_release_subject.py --source . --export $exportRoot --artifact-manifest $artifactManifest --release-index $releaseIndex --release-index-bundle $releaseIndexBundle --asset-root $assetRoot --signing-policy release/signing-policy.json --verifier-bootstrap release/verifier-bootstrap.json --out release/evidence/release-subject.json
$subject = 'release/evidence/release-subject.json'
C:\Python311\python.exe tools/runtime_security_baseline.py verify-matrix --manifest $artifactManifest --asset-root $assetRoot --policy release/runtime-security-policy.json --subject $subject --max-age-hours 24
C:\Python311\python.exe tools/sync_version.py --check --phase final --subject $subject --artifact-manifest $artifactManifest --release-index $releaseIndex --asset-root $assetRoot
$gateContext = @('--subject',$subject,'--product-source-root',(Get-Location).Path,'--public-export-root',$exportRoot,'--evidence-dir',(Join-Path (Get-Location).Path 'release\evidence'),'--release-assets-root',$assetRoot,'--release-index',$releaseIndex,'--release-index-bundle',$releaseIndexBundle,'--signing-policy',(Join-Path (Get-Location).Path 'release\signing-policy.json'),'--verifier-bootstrap',(Join-Path (Get-Location).Path 'release\verifier-bootstrap.json'),'--registry',(Join-Path (Get-Location).Path 'release\evidence\receipt-registry.json'),'--launch-policy',(Join-Path (Get-Location).Path 'release\evidence\producer-launch-policy.json'))
function Invoke-SealedGateProducer {
  param([Parameter(Mandatory)][string]$Gate,[Parameter(Mandatory)][string]$Receipt,[string[]]$ProducerArgs=@())
  & $releasePython tools/release_gate.py produce-and-seal --gate $Gate --receipt $Receipt @gateContext -- @ProducerArgs
  if ($LASTEXITCODE -ne 0) { throw "authenticated producer/sealer failed for $Receipt" }
}
& $releasePython tools/release_gate.py validate-deferred-gate-interface --gate G4 --receipt g4-benchmark.json --receipt g4-independent-rerun.json @gateContext --require-final-absent --require-candidate-only
if ($LASTEXITCODE -ne 0) { throw 'deferred G4 registry/launch contract is not closed or a G4 final receipt already exists' }
Invoke-SealedGateProducer G0 'g0-workspace.json' @('--export-root',$exportRoot)
Invoke-SealedGateProducer G1 'g1.json'
Invoke-SealedGateProducer G2 'g2-map-quality.json' @('--repo',$exportRoot,'--scope','product','--budget','12000','--min-results','50','--required-class','first_party_source','--expectations',(Join-Path $exportRoot 'tests\fixtures\map_gate_expectations.json'))
Invoke-SealedGateProducer G3 'g3-contracts.json'
Invoke-SealedGateProducer G3 'g3-lifecycle.json' @('--manifest',$artifactManifest,'--asset-root',$assetRoot,'--signing-policy','release/signing-policy.json','--verify-only')
Invoke-SealedGateProducer G3 'g3-reliability.json'
Invoke-SealedGateProducer G5 'provenance.json' @('--artifact-manifest',$artifactManifest,'--asset-root',$assetRoot,'--manifest-out','release/evidence/source-manifest.json')
Invoke-SealedGateProducer G5 'public-export.json' @('--repo',$exportRoot)
Invoke-SealedGateProducer G5 'license.json' @('--root',$exportRoot)
$securityReviewerId = $env:CODESEXTANT_SECURITY_REVIEWER_ID
$securityReviewerProcess = $env:CODESEXTANT_SECURITY_REVIEWER_PROCESS_SHA256
$securityRequesterId = $env:CODESEXTANT_SECURITY_REQUESTER_ID
$securityFindingsDraft = $env:CODESEXTANT_SECURITY_FINDINGS_DRAFT
if (-not $securityReviewerId -or $securityReviewerProcess -notmatch '^[0-9a-f]{64}$') { throw 'independent security reviewer identity/process evidence is required' }
if (-not $securityRequesterId -or $securityRequesterId -eq $securityReviewerId) { throw 'distinct security review requester identity is required' }
$signingEnvRegistryPath = 'release/signing-environment-registry.json'
$signingEnvRegistry = Get-Content -Raw -Encoding UTF8 -LiteralPath $signingEnvRegistryPath | ConvertFrom-Json
$registeredKeyEnvs = @($signingEnvRegistry.roles | ForEach-Object { [string]$_.key_env })
$uniqueRegisteredKeyEnvs = @($registeredKeyEnvs | Sort-Object -Unique)
if ($registeredKeyEnvs.Count -eq 0 -or $registeredKeyEnvs.Count -ne $uniqueRegisteredKeyEnvs.Count) { throw 'invalid signing-environment registry closure' }
$reservedKeyEnvPattern = [string]$signingEnvRegistry.reserved_pattern
if ($reservedKeyEnvPattern -ne '^CODESEXTANT_[A-Z0-9_]*SIGNING_KEY$') { throw 'unexpected reserved signing-key environment pattern' }
$ambientReserved = @(Get-ChildItem Env: | Where-Object { $_.Name -match $reservedKeyEnvPattern })
if ($ambientReserved.Count -ne 0) { throw "reserved signing keys must not exist in the parent shell: $($ambientReserved.Name -join ',')" }
function New-ReviewRoleLaunchArguments {
  param([Parameter(Mandatory)][string]$Role,[Parameter(Mandatory)][string]$CredentialName,[Parameter(Mandatory)][string]$AllowedKeyEnv)
  if ($AllowedKeyEnv -notin $registeredKeyEnvs) { throw "unregistered allowed signing-key environment: $AllowedKeyEnv" }
  $forbidden = @($registeredKeyEnvs | Where-Object { $_ -cne $AllowedKeyEnv } | Sort-Object -CaseSensitive)
  if ($forbidden.Count -ne ($registeredKeyEnvs.Count - 1)) { throw 'forbidden signing-key closure is not registry-minus-allowed' }
  $launchArguments = @('run','--role',$Role,'--credential-name',$CredentialName,'--allowed-key-env',$AllowedKeyEnv,'--signing-env-registry',$signingEnvRegistryPath,'--reserved-key-env-pattern',$reservedKeyEnvPattern)
  foreach ($name in $forbidden) { $launchArguments += @('--forbidden-key-env',$name) }
  return $launchArguments
}
$requesterRoleArgs = @(New-ReviewRoleLaunchArguments -Role requester -CredentialName 'codesextant/g5/security-requester' -AllowedKeyEnv 'CODESEXTANT_SECURITY_REQUESTER_SIGNING_KEY')
$reviewerRoleArgs = @(New-ReviewRoleLaunchArguments -Role reviewer -CredentialName 'codesextant/g5/security-reviewer' -AllowedKeyEnv 'CODESEXTANT_SECURITY_REVIEWER_SIGNING_KEY')
if ([string]::IsNullOrWhiteSpace($securityFindingsDraft) -or -not (Test-Path -LiteralPath $securityFindingsDraft -PathType Leaf)) { throw 'independent reviewer findings draft is required; never synthesize a no-findings verdict' }
Invoke-SealedGateProducer G5 'security.json' @('--source','.', '--export',$exportRoot,'--artifact-manifest',$artifactManifest,'--asset-root',$assetRoot,'--tool-lock','release/toolchain.lock','--reviewer-id',$securityReviewerId,'--reviewer-process-sha256',$securityReviewerProcess,'--reviewer-roles','release/security-reviewer-roles.json','--implementation-actors','provenance/implementation-actors.json')
& $releasePython tools/review_role_runner.py @requesterRoleArgs -- $releasePython tools/security_review.py request --subject $subject --source . --export $exportRoot --release-index $releaseIndex --artifact-manifest $artifactManifest --asset-root $assetRoot --security-automation release/evidence/security.json --pre-public-sast release/evidence/pre-public-sast.json --runner-availability release/evidence/runner-availability.json --scope release/security-review-scope.json --requester-id $securityRequesterId --reviewer-roles release/security-reviewer-roles.json --implementation-actors provenance/implementation-actors.json --signing-key-env CODESEXTANT_SECURITY_REQUESTER_SIGNING_KEY --out release/evidence/security-review-request.json
if ($LASTEXITCODE -ne 0) { throw 'fresh requester process failed to produce the signed review request' }
& $releasePython tools/review_role_runner.py @reviewerRoleArgs -- $releasePython tools/security_review.py record-input-and-findings --request release/evidence/security-review-request.json --draft $securityFindingsDraft --reviewer-id $securityReviewerId --reviewer-process-sha256 $securityReviewerProcess --reviewer-roles release/security-reviewer-roles.json --implementation-actors provenance/implementation-actors.json --signing-key-env CODESEXTANT_SECURITY_REVIEWER_SIGNING_KEY --input-out release/evidence/security-review-input.json --findings-out release/evidence/security-findings.json
if ($LASTEXITCODE -ne 0) { throw 'fresh reviewer process failed to record the complete signed input and findings ledgers' }
Invoke-SealedGateProducer G5 'security-review.json' @('--request','release/evidence/security-review-request.json','--input','release/evidence/security-review-input.json','--findings','release/evidence/security-findings.json','--reviewer-roles','release/security-reviewer-roles.json','--implementation-actors','provenance/implementation-actors.json')
Invoke-SealedGateProducer G5 'artifacts.json' @('--release-index',$releaseIndex,'--release-index-bundle',$releaseIndexBundle,'--manifest',$artifactManifest,'--asset-root',$assetRoot,'--signing-policy','release/signing-policy.json','--verifier-bootstrap','release/verifier-bootstrap.json')
~~~

Each registered G0-G3/G5 domain producer returns only an internal candidate through the exclusive handle; `produce-and-seal` validates it and is the only writer of the registered final receipt. The two registered G4 rows remain absent and candidate-only until the later G4 run. Then:

~~~powershell
foreach ($gate in 'G0','G1','G2','G3','G5') {
  & $releasePython tools/release_gate.py check --gate $gate @gateContext
  if ($LASTEXITCODE -ne 0) { throw "final registry gate $gate failed" }
}
$g6Preflight = Join-Path $assetRoot 'codesextant-g6-context-preflight.exe'
& $releasePython tools/release_index.py verify-authenticode-role --index $releaseIndex --asset-root $assetRoot --role g6_context_preflight --expected-name codesextant-g6-context-preflight.exe --policy release/g8-authenticode-signing-policy.json
if ($LASTEXITCODE -ne 0) { throw 'G6 context preflight release asset is not index/pin authenticated' }
$g6RunbookLauncherAsset = Join-Path $assetRoot 'codesextant-g6-runbook-launcher.exe'
& $releasePython tools/release_index.py verify-authenticode-role --index $releaseIndex --asset-root $assetRoot --role g6_runbook_launcher --expected-name codesextant-g6-runbook-launcher.exe --policy release/g8-authenticode-signing-policy.json
if ($LASTEXITCODE -ne 0) { throw 'G6 runbook launcher release asset is not index/pin authenticated' }
$trustStateJson = & $g6Preflight g6-trust-state --launcher-asset $g6RunbookLauncherAsset --subject $subject --release-index $releaseIndex --release-index-bundle $releaseIndexBundle --format json
if ($LASTEXITCODE -ne 0) { throw 'could not classify atomic G6 launcher/authority state' }
$trustState = $trustStateJson | ConvertFrom-Json
$subjectSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $subject).Hash.ToLowerInvariant()
$trustArgs = switch ($trustState.state) {
  'absent' { @('bootstrap-g6-trust','--create-new','--launcher-asset',$g6RunbookLauncherAsset,'--subject',$subject,'--release-index',$releaseIndex,'--release-index-bundle',$releaseIndexBundle) }
  'complete_same_subject' { @('verify-g6-trust','--subject-sha256',$subjectSha256,'--launcher-asset',$g6RunbookLauncherAsset) }
  'current_older_subject' { @('bootstrap-g6-trust','--advance-monotonic','--expected-prior-sha256',$trustState.authority_sha256,'--expected-generation',[string]$trustState.generation,'--launcher-asset',$g6RunbookLauncherAsset,'--subject',$subject,'--release-index',$releaseIndex,'--release-index-bundle',$releaseIndexBundle) }
  'recoverable_launcher_orphan' { @('recover-g6-trust','--complete-authority-only','--launcher-asset',$g6RunbookLauncherAsset,'--subject',$subject,'--release-index',$releaseIndex,'--release-index-bundle',$releaseIndexBundle) }
  'terminal_tombstone' { throw 'G6 anti-rollback authority is terminal; administrator remediation required' }
  default { throw "ambiguous G6 launcher/authority state: $($trustState.state)" }
}
$trustProcess = Start-Process -FilePath $g6Preflight -Verb RunAs -Wait -PassThru -ArgumentList $trustArgs
if ($trustProcess.ExitCode -ne 0) { throw 'atomic protected-launcher/current-authority transaction failed; prior valid authority or terminal tombstone governs recovery' }
~~~

Expected: every produced G0-G3/G5 gate exits 0, both deferred G4 rows validate as absent candidate-only contracts, and no producer accepts a direct registered `--out` path. Only then does the signed native preflight create or monotonically advance the fixed TrustedInstaller-owned machine-signed G6 authority. It never rolls back or deletes a prior authority; ambiguous failure leaves the prior current record or terminal tombstone and blocks G6. No evidence/report is committed. G4/G6 run against this exact subject and draft artifact set.
