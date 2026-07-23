---
tier: 全文
status: revision-5-shared-exact-commit-prerequisite
date: 2026-07-23
scope: CodeSextant G6 release-candidate validation
---

# CodeSextant G6 Release Candidate Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Make the release candidate understandable to a new user and prove that one unchanged artifact survives real use in two workstreams for a full week with zero product-defect fallback.

**Architecture:** Documentation is executable: public claims and commands are generated from the operation registry, quick-start steps run in a clean environment, and every acceptance/dogfood event is a privacy-safe receipt bound to one immutable ReleaseSubject. The first-user run is signed by a pre-authorized independent runner's external Ed25519 key and verified against a committed role registry plus the implementation-actor roster. A hash chain plus independently verifiable Sigstore/Rekor anchors proves elapsed time and observed chain heads; a fail-closed summarizer invalidates G6 when time, activity, workstream, issue, subject, signature, role-separation, or hash requirements are missing.

**Tech Stack:** Markdown, Python 3.11, JSON Schema 2020-12, pytest, locked cryptography 45.0.5 Ed25519 support, release artifacts from G5, CLI/MCP/HTTP smoke clients, Git commit and SHA-256 receipts.

## Global Constraints

- G6 external evidence begins only after G4 and G5 are green for the same canonical ReleaseSubject SHA-256.
- README and all public documents default to English; README.zh-TW.md is maintained as a translation.
- Documentation may claim only capabilities and measurements emitted by the operation registry, support matrix, and current G4 benchmark receipt.
- No local absolute path, user email, private host, private skill, secret, stale hard-coded test count, or unsupported SOTA claim may appear in the public export.
- First-user verification must be performed by a person or agent whose UUID, independent-first-user role, key ID, and Ed25519 public key were committed in release/first-user-runner-roles.json before Final Freeze, who is absent from provenance/implementation-actors.json, and who uses a clean machine/profile with no source checkout on PATH. The private signing key remains external and may enter only through the named process environment variable; it may never enter Git, argv, logs, receipts, captured child environments, or release assets.
- Both the external first-user-run.json and canonical G6 first-user.json receipt payload require the verified runner key_id and Ed25519 signature; a boolean independence assertion without signature/role/actor-roster verification is never sufficient.
- Dogfood records contain no source, prompt, token, personal path, repository name, or secret. Workstreams are opaque random IDs.
- The seven-day window is measured between two Sigstore/Rekor-verified CI time anchors for the same ReleaseSubject, not by the local OS clock or event timestamps. It requires at least 168 hours, at least five UTC calendar days with activity, and at least 20 successful real query sessions per workstream.
- Both workstreams use the exact same artifact SHA-256. Any product or artifact change resets first-user and dogfood evidence.
- product_defect fallback count, open P0, and open P1 must all be zero. Missing reason fields are invalid, not silently classified as non-product.
- All four implementation tasks commit before the G5 Final Freeze. After ReleaseSubject freezes, no tracked source, documentation, policy, schema, or generated report is committed; any such change invalidates the subject and restarts G5 F1.
- Raw G6 evidence, the generated subject-bound dogfood plan, anchor requests/bundles, and redacted aggregate assets stay outside Git. G6 only stages and hashes public-safe evidence under ignored `release/assets/`; it performs no upload. G7 combines the G4/G6 asset manifests into ignored `release/evidence/public-evidence-assets.json`, hashes that exact set into the publication-plan authorization payload, uploads it while the repository is still PRIVATE only after exact authorization, verifies it, and only then changes visibility.
- Every task follows RED -> GREEN -> refactor and uses the exact commit message shown.

G0 Task 1 owns the sole tracked exact-commit implementation at `tools/exact_task_commit.ps1` and its executable disposable-repository contract test at `tests/release/test_exact_task_commit.py`; G6 owns no duplicate. Before the first G6 task and before every Step 5 block, resolve the repository root, dot-source that tracked helper, and run the same tracked test. The test exercises A/M success, index D/R/C/T rejection, duplicate/extra paths, and commit-hook index mutation entirely inside temporary repositories.

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

### Task 1: Replace internal documentation with executable public documentation

**Files:**

- Rewrite: README.md
- Create: README.zh-TW.md
- Create: ARCHITECTURE.md
- Create: CHANGELOG.md
- Create: CONTRIBUTING.md
- Create: CODE_OF_CONDUCT.md
- Create: docs/quickstart.md
- Create: docs/cli.md
- Create: docs/mcp.md
- Create: docs/http.md
- Create: docs/troubleshooting.md
- Create: docs/release-policy.md
- Create: docs/release-notes.md
- Create: docs/known-limitations.md
- Create: docs/support-matrix.json
- Create: .github/ISSUE_TEMPLATE/bug.yml
- Create: .github/ISSUE_TEMPLATE/feature.yml
- Create: .github/pull_request_template.md
- Create: tools/check_public_docs.py
- Create: tools/render_quickstart.py
- Create: tests/docs/test_public_docs.py

**Step 1: Write RED tests**

~~~python
DENIED_PATTERNS = (
    r"[A-Za-z]:\\",
    r"/Users/",
    r"/home/[^/]+/",
    "zeroxrain99@gmail.com",
    "337 passed",
    "抄 aider",
)


def test_public_docs_have_no_private_or_stale_claims(public_docs: list[Path]) -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in public_docs)
    for pattern in DENIED_PATTERNS:
        assert re.search(pattern, text, re.IGNORECASE) is None


def test_documented_operations_equal_registry() -> None:
    assert documented_operation_ids() == enabled_operation_ids("cli", "mcp", "http")


def test_claimed_languages_equal_support_matrix() -> None:
    assert readme_languages() == support_matrix_languages()


def test_public_docs_identify_the_product_license_exactly(repo_root: Path) -> None:
    assert read_readme_license_badge(repo_root / "README.md") == "Apache-2.0"
    assert read_readme_license_target(repo_root / "README.md") == "LICENSE"
    assert read_readme_license_target(repo_root / "README.zh-TW.md") == "LICENSE"


def test_benchmark_link_is_bound_to_the_version_authority(repo_root: Path) -> None:
    version = read_product_version(repo_root / "codesextant/_version.py")
    assert readme_benchmark_url(repo_root / "README.md") == (
        f"https://github.com/Zeroxrain99/CodeSextant/releases/download/v{version}/BENCHMARKS.md"
    )


def test_quickstart_is_exactly_rendered_from_operation_registry(repo_root: Path) -> None:
    rendered = render_quickstart(repo_root / "spec/operations.yaml")
    assert rendered == extract_generated_block(repo_root / "docs/quickstart.md")
    assert all_cli_arguments_exist_in_registry(rendered, repo_root / "spec/operations.yaml")
~~~

The tracked docs checker rejects every numeric or comparative performance claim in README/public docs; those pre-freeze files may contain only a stable release-asset link. Measured claims, run ID, ReleaseSubject/artifact/commit hashes, scope, and limitations live only in the post-freeze generated `BENCHMARKS.md` release asset. It also rejects claims containing 100%, zero false positives, guaranteed SOTA, or guaranteed Claude eligibility.

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/docs/test_public_docs.py -q
~~~

Expected: FAIL because the new files are absent and README.md contains a local E drive path and stale 337-passed text.

**Step 3: Write the documentation**

README.md contains, in order:

1. one-sentence product definition;
2. honest status and support matrix;
3. 60-second artifact install;
4. index and one map/reference query;
5. MCP setup;
6. a tag-bound link rendered from the version SSOT as `https://github.com/Zeroxrain99/CodeSextant/releases/download/v{product_version}/BENCHMARKS.md`, with no pre-freeze run ID or performance number;
7. privacy/security statement;
8. architecture, contributing, support, and an `Apache-2.0` badge/link to the
   top-level `LICENSE` (with the zh-TW README linking to the same authority).

docs/quickstart.md is generated from spec/operations.yaml by tools/render_quickstart.py and then edited only in generated-safe prose regions. The generated smoke block runs released artifacts with registry-defined names and fields:

~~~powershell
codesextant doctor --json
codesextant index --repository .
codesextant map --repository . --scope product --token-budget 2000 --json
codesextant refs --repository . --symbol get_map --def-path codesextant/engine.py --json
~~~

`tools/render_quickstart.py` derives command names, kebab-case flags, required fields, defaults, and JSON support from `spec/operations.yaml`; the literal block above is an expected generated snapshot, not a second authority. Generation fails if an example supplies an unknown flag, omits a required registry field, or refers to a disabled CLI operation.

docs/mcp.md includes the exact JSON client configuration generated from spec/operations.yaml. docs/http.md documents bearer-token location/permissions, Origin/Host policy, POST-only heavy routes, and curl examples that never print the token into shell history. docs/known-limitations.md separates precision adapters from name-level adapters and explicitly accepts launch disadvantages in community and language breadth.

**Step 4: Run GREEN**

~~~powershell
C:\Python311\python.exe tools/check_public_docs.py --root .
C:\Python311\python.exe tools/render_quickstart.py --check
C:\Python311\python.exe -m pytest tests/docs/test_public_docs.py -q
cargo run --locked -q -p xtask -- contracts check
~~~

Expected: all exit 0 and the generated operation/reference docs have no diff.

**Step 5: Commit**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('README.md','README.zh-TW.md','ARCHITECTURE.md','CHANGELOG.md','CONTRIBUTING.md','CODE_OF_CONDUCT.md','docs/quickstart.md','docs/cli.md','docs/mcp.md','docs/http.md','docs/troubleshooting.md','docs/release-policy.md','docs/release-notes.md','docs/known-limitations.md','docs/support-matrix.json','.github/ISSUE_TEMPLATE/bug.yml','.github/ISSUE_TEMPLATE/feature.yml','.github/pull_request_template.md','tools/check_public_docs.py','tools/render_quickstart.py','tests/docs/test_public_docs.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'docs: ship executable public documentation'
~~~

### Task 2: Make the clean-artifact quick start machine-verifiable

**Files:**

- Create: release/evidence/first-user.schema.json
- Create: release/first-user-run.schema.json
- Create: release/first-user-runner-bundle.schema.json
- Create: release/first-user-scenario.json
- Create: release/first-user-runner-roles.json
- Create: release/g8-seed-install-receipt.schema.json
- Create: release/g8-seed-install-tombstone.schema.json
- Create: release/g6-release-authority.schema.json
- Create: release/g6-release-authority-tombstone.schema.json
- Create: release/g6-release-migration.schema.json
- Create: release/g6-release-migration-signing-policy.schema.json
- Create: release/g6-release-migration-signing-policy.json
- Create: release/g8-seed-installer-signing-policy.schema.json
- Create: release/g8-seed-installer-signing-policy.json
- Create: release/g8-authenticode-signing-policy.schema.json
- Create: release/g8-authenticode-signing-policy.json
- Create: release/g8-seed-static-verifier.rs
- Create: release/g8-seed-installer.spec
- Create: release/g6-context-preflight.rs
- Create: release/g6-runbook-launcher.rs
- Create: tools/run_first_user.py
- Create: tools/verify_first_user.py
- Create: tools/install_g8_seed.py
- Create: tools/provision_g8_seed_machine_key.ps1
- Create: tools/provision_g8_authenticode_trust.ps1
- Create: tools/provision_g6_release_migration_key.ps1
- Create: tests/release/test_first_user_verifier.py
- Create: tests/release/test_g8_seed_install.py
- Create: tests/release/test_g8_seed_static_verifier.py
- Create: tests/release/test_g6_context_preflight.py
- Verify without modification: provenance/implementation-actors.json
- Verify without modification and include in the portable bundle: tools/review_role_runner.py
- Verify without modification and include in the portable bundle: release/signing-environment-registry.schema.json
- Verify without modification and include in the portable bundle: release/signing-environment-registry.json

**Step 1: Write RED tests**

~~~python
def test_author_or_dirty_environment_is_rejected(valid_receipt, verification_inputs) -> None:
    valid_receipt["independence"]["implemented_quickstart"] = True
    assert verify_first_user(runner_receipt=valid_receipt, **verification_inputs).status == "fail"
    valid_receipt["independence"]["implemented_quickstart"] = False
    valid_receipt["environment"]["source_checkout_on_path"] = True
    assert verify_first_user(runner_receipt=valid_receipt, **verification_inputs).status == "fail"


def test_every_quickstart_phase_has_exit_zero_and_hash(valid_receipt, verification_inputs) -> None:
    valid_receipt["steps"][2]["exit_code"] = 1
    assert verify_first_user(runner_receipt=valid_receipt, **verification_inputs).status == "fail"


def test_gate_receipt_requires_an_external_runner_input(subject, scenario, tmp_path) -> None:
    missing = tmp_path / "first-user-run.json"
    assert emit_receipt(subject, scenario, missing).status == "fail"


def test_unknown_key_or_invalid_signature_is_rejected(
    valid_receipt, runner_roles, verification_inputs
) -> None:
    inputs = {**verification_inputs, "runner_roles": runner_roles}
    valid_receipt["key_id"] = "unregistered-key"
    assert verify_first_user(runner_receipt=valid_receipt, **inputs).status == "fail"
    valid_receipt["key_id"] = runner_roles["allowed_runners"][0]["key_id"]
    valid_receipt["signature"] = "A" * 86
    assert verify_first_user(runner_receipt=valid_receipt, **inputs).status == "fail"


def test_role_registry_rejects_private_material_and_actor_overlap(
    runner_roles, implementation_actors
) -> None:
    runner_roles["allowed_runners"][0]["private_key"] = "forbidden"
    assert validate_runner_roles(runner_roles, implementation_actors).status == "fail"
    runner_roles["allowed_runners"][0].pop("private_key")
    implementation_actors["actors"].append(
        {"actor_id": runner_roles["allowed_runners"][0]["runner_id"]}
    )
    runner_roles["implementation_actors_sha256"] = canonical_sha256(implementation_actors)
    assert validate_runner_roles(runner_roles, implementation_actors).status == "fail"


def test_signature_binds_subject_scenario_and_artifact(signed_receipt, verification_inputs) -> None:
    for field in ("subject_sha256", "scenario_sha256", "artifact_manifest_sha256", "artifact_sha256"):
        tampered = copy.deepcopy(signed_receipt)
        tampered[field] = "0" * 64
        assert verify_first_user(runner_receipt=tampered, **verification_inputs).status == "fail"


def test_runner_must_not_be_an_implementation_actor(
    signed_receipt, runner_roles, implementation_actors, verification_inputs
) -> None:
    implementation_actors["actors"].append({"actor_id": signed_receipt["runner_id"]})
    resigned = sign_fixture(signed_receipt)
    inputs = {
        **verification_inputs,
        "runner_roles": runner_roles,
        "implementation_actors": implementation_actors,
    }
    assert verify_first_user(runner_receipt=resigned, **inputs).status == "fail"


def test_gate_receipt_preserves_verified_runner_attestation(valid_gate_receipt) -> None:
    attestation = valid_gate_receipt["payload"]["runner_attestation"]
    assert set(attestation) == {
        "runner_id", "runner_role", "key_id", "signature",
        "signed_runner_receipt_sha256", "runner_bundle_manifest_sha256",
        "runner_roles_sha256",
        "implementation_actors_sha256", "release_python_lock_sha256",
        "release_python_executable_sha256",
    }


def test_gate_receipt_reverification_rejects_replacement(
    valid_gate_receipt, signed_receipt, verification_inputs
) -> None:
    valid_gate_receipt["payload"]["runner_attestation"]["key_id"] = "substituted"
    assert verify_gate_receipt(
        gate_receipt=valid_gate_receipt,
        runner_receipt=signed_receipt,
        **verification_inputs,
    ).status == "fail"


@pytest.mark.parametrize("field", ["release_python_lock_sha256", "release_python_executable_sha256"])
def test_gate_receipt_rejects_release_python_identity_tamper(
    valid_gate_receipt, signed_receipt, verification_inputs, field
) -> None:
    valid_gate_receipt["payload"]["runner_attestation"][field] = "0" * 64
    assert verify_gate_receipt(
        gate_receipt=valid_gate_receipt,
        runner_receipt=signed_receipt,
        **verification_inputs,
    ).status == "fail"


def test_portable_runner_bundle_works_in_an_arbitrary_clean_root_without_git(
    frozen_runner_bundle, tmp_path: Path
) -> None:
    clean_root = tmp_path / "clean-profile" / "runner-bundle"
    copy_bundle(frozen_runner_bundle, clean_root)
    result = invoke_external_runner_in_blank_pwsh(clean_root, inherited_path="")
    assert result.cwd == clean_root
    assert result.git_root is None
    assert result.loaded_codesextant_source_checkout is False
    assert result.used_exact_root_initializer is False
    assert result.locked_release_python_verified is True
    assert result.ambient_python_calls_after_bootstrap == 0


def test_local_verifier_rejects_runner_bundle_manifest_or_member_tamper(
    signed_receipt, runner_bundle_manifest, verification_inputs
) -> None:
    runner_bundle_manifest["members"][0]["sha256"] = "0" * 64
    assert verify_first_user(
        runner_receipt=signed_receipt,
        runner_bundle_manifest=runner_bundle_manifest,
        **verification_inputs,
    ).status == "fail"


def test_private_key_is_not_serialized_logged_or_forwarded(
    monkeypatch, valid_private_seed_base64url, mocked_children, tmp_path
) -> None:
    monkeypatch.setenv("CODESEXTANT_FIRST_USER_SIGNING_KEY", valid_private_seed_base64url)
    receipt = run_signed_fixture(
        signing_key_env="CODESEXTANT_FIRST_USER_SIGNING_KEY",
        children=mocked_children,
        out=tmp_path / "first-user-run.json",
    )
    assert valid_private_seed_base64url.encode() not in receipt.path.read_bytes()
    assert all("CODESEXTANT_FIRST_USER_SIGNING_KEY" not in child.env for child in mocked_children)
    assert all(valid_private_seed_base64url not in child.argv_log for child in mocked_children)


def test_first_user_key_is_injected_only_after_locked_bootstrap(
    portable_bundle, os_credential, valid_private_seed_base64url
) -> None:
    trace = invoke_portable_runner_with_role_launcher(
        portable_bundle,
        credential=os_credential,
        inherited_environment={"CODESEXTANT_FIRST_USER_SIGNING_KEY": None},
    )
    assert trace.locked_bootstrap_completed_before_role_launch is True
    assert trace.signing_key_first_visible_to == "tools/run_first_user.py"
    assert all(
        "CODESEXTANT_FIRST_USER_SIGNING_KEY" not in child.env
        and valid_private_seed_base64url not in child.argv
        and valid_private_seed_base64url not in child.stdin
        for child in trace.bootstrap_and_pip_children
    )


def test_foreign_role_signing_environment_is_closed_and_fails_before_runner(portable_bundle) -> None:
    inventory = load_signing_environment_registry(portable_bundle)
    known = {row["key_env"] for row in inventory["roles"]}
    allowed = "CODESEXTANT_FIRST_USER_SIGNING_KEY"
    forbidden = known - {allowed}
    assert inventory["reserved_pattern"] == r"^CODESEXTANT_[A-Z0-9_]*SIGNING_KEY$"
    assert forbidden == all_known_signing_key_envs() - {allowed}
    for foreign_env in forbidden:
        trace = invoke_portable_runner(
            portable_bundle,
            inherited_environment={foreign_env: "foreign-secret"},
        )
        assert trace.status == "fail"
        assert trace.run_first_user_started is False
    clean = invoke_portable_runner(portable_bundle)
    assert all(
        all(env not in child.env for env in known)
        for child in clean.parent_bootstrap_pip_runner_and_product_children
    )
    future = invoke_portable_runner(
        portable_bundle,
        inherited_environment={"CODESEXTANT_FUTURE_ROTATION_SIGNING_KEY": "future-secret"},
    )
    assert future.status == "fail"
    assert future.run_first_user_started is False


def test_public_first_user_statement_is_privacy_safe_and_independently_verifiable(
    valid_gate_receipt, runner_roles
) -> None:
    public = valid_gate_receipt["payload"]["public_verification"]
    assert set(public) == {
        "signature_domain", "signature_algorithm", "key_id",
        "statement", "signature",
    }
    assert set(public["statement"]) == {
        "format_version", "subject_sha256", "scenario_sha256",
        "artifact_manifest_sha256", "artifact_sha256",
        "runner_bundle_manifest_sha256", "release_python_lock_sha256",
        "release_python_executable_sha256", "runner_role", "key_id",
        "required_phases_sha256", "phase_evidence_sha256",
        "uninstall_proof_sha256", "clean_environment", "status",
    }
    assert verify_public_first_user_statement(public, runner_roles).status == "pass"
    raw = canonical_json(public)
    assert not contains_path_url_identity_environment_log_or_timestamp(raw)
    public["statement"]["artifact_sha256"] = "0" * 64
    assert verify_public_first_user_statement(public, runner_roles).status == "fail"


def test_g8_seed_installer_uses_only_the_verified_release_asset(
    verified_subject, verified_release_index, verified_asset_root
) -> None:
    result = install_g8_seed(
        subject=verified_subject,
        release_index=verified_release_index,
        asset_root=verified_asset_root,
        create_new=True,
    )
    assert result.source_asset_roles == {
        "g8_seed_verifier": "Bootstrap-CodeSextantG8ProductExec.ps1",
        "g8_seed_static_verifier": "codesextant-g8-seed-static-verify.exe",
    }
    assert result.source_asset_sha256s == result.installed_sha256s
    assert result.installed_path == fixed_g8_seed_path()
    assert result.static_verifier_path == fixed_g8_static_verifier_path()
    assert result.owner_sid == trusted_installer_sid()
    assert result.dacl_protected is True
    assert result.exact_aces == expected_system_admin_fullcontrol_and_invoking_user_rx()
    assert result.inherited_aces == ()
    assert result.unexpected_allow_aces == ()
    assert result.no_reparse_components is True


def test_g8_seed_receipt_or_acl_tamper_fails_closed(installed_g8_seed) -> None:
    assert verify_g8_seed_install(installed_g8_seed.receipt).status == "pass"
    tamper_one_byte(installed_g8_seed.path)
    assert verify_g8_seed_install(installed_g8_seed.receipt).status == "fail"
    restore_bytes_then_add_inherited_ace(installed_g8_seed.path)
    assert verify_g8_seed_install(installed_g8_seed.receipt).status == "fail"
    replace_parent_with_reparse_point(installed_g8_seed.path)
    assert verify_g8_seed_install(installed_g8_seed.receipt).status == "fail"


@pytest.mark.parametrize("tamper", [
    grant_everyone_full_control,
    grant_invoking_user_modify,
    grant_invoking_user_delete_or_write_dac,
    rewrite_owner_to_invoking_user,
    add_inherited_or_unexpected_ace,
])
def test_g8_seed_exact_owner_and_acl_fail_closed(installed_g8_seed, tamper) -> None:
    tamper(installed_g8_seed.trust_root)
    assert static_verify_fixed_install().status == "fail"


@pytest.mark.parametrize("attack", [
    forge_self_consistent_unsigned_release_index,
    duplicate_seed_role,
    omit_static_or_script_seed_role,
    rename_seed_basename,
    substitute_source_tree_bytes,
    substitute_same_relative_export_path,
    request_destination_override,
    precreate_destination_or_receipt,
])
def test_g8_seed_installer_rejects_untrusted_source_or_ambiguous_state(attack) -> None:
    assert invoke_attacked_install(attack).status == "fail"
    assert fixed_trust_root_was_not_mutated()


@pytest.mark.parametrize("argv", [
    ["install", "--destination", r"C:\decoy"],
    ["verify", "--receipt", r"C:\decoy.json"],
    ["state-fixed", "--path", r"C:\decoy"],
    ["export-evidence", "--create-new", "--evidence-file", r"C:\decoy.json"],
    ["export-evidence", "--overwrite", "--evidence-dir", r"C:\decoy"],
])
def test_g8_seed_closed_cli_rejects_path_or_overwrite_authority(argv) -> None:
    assert invoke_installer_cli(argv).status == "invalid_cli"


@pytest.mark.parametrize("failure", [
    fail_secure_temp_create,
    fail_temp_acl,
    fail_temp_flush,
    fail_atomic_rename,
    parent_rename_reparse_race_between_handle_checks,
])
def test_g8_seed_install_temp_or_race_failure_leaves_no_usable_partial(failure) -> None:
    result = invoke_install_with_fault(failure)
    assert result.status == "fail"
    assert static_verify_fixed_install().status != "pass"


@pytest.mark.parametrize("kill_point", ALL_INSTALL_KILL_POINTS)
def test_g8_seed_install_crash_is_recoverable_or_terminal(kill_point) -> None:
    crash_install_at(kill_point)
    result = recover_orphan_create_receipt_only()
    if complete_fixed_seed_and_static_bytes_exist():
        assert result.status == "pass"
        assert result.did_not_rewrite_installed_bytes is True
        assert static_verify_fixed_install().status == "pass"
    else:
        assert result.status == "terminal_manual_intervention"
        assert signed_tombstone_exists()


def test_orphan_recovery_rehashes_live_bytes_acl_and_signed_index() -> None:
    orphan = create_seed_rename_succeeded_receipt_not_created_state()
    assert recover_orphan_create_receipt_only(orphan).status == "pass"
    for tamper in (tamper_one_live_byte, rewrite_owner_to_invoking_user, add_parent_reparse, swap_signed_index):
        state = create_seed_rename_succeeded_receipt_not_created_state()
        tamper(state)
        assert recover_orphan_create_receipt_only(state).status == "terminal_manual_intervention"


def test_terminal_tombstone_is_fixed_signed_and_blocks_all_execution(terminal_orphan) -> None:
    tombstone = recover_orphan_create_receipt_only(terminal_orphan).tombstone
    assert tombstone.path == fixed_g8_tombstone_path()
    assert tombstone.signature_domain == "codesextant:g8-seed-tombstone:v1"
    assert tombstone.reason_code in CLOSED_TERMINAL_REASON_CODES
    assert tombstone.subject_sha256 == VALID_SUBJECT_SHA256
    assert tombstone.live_file_observations_sha256 == hash_live_fixed_path_observations()
    assert verify_tombstone_fixed().status == "pass"
    assert static_verify_fixed_install().status == "terminal_manual_intervention"
    assert install_g8_seed(create_new=True).status == "terminal_manual_intervention"
    tamper_one_byte(tombstone.path)
    assert verify_tombstone_fixed().status == "fail"


def test_g6_release_authority_is_machine_signed_monotonic_and_rollback_safe() -> None:
    first = authorize_release(create_new=True, subject=SUBJECT_A, generation=1)
    assert first.path == fixed_g6_release_authority_path()
    assert first.signature_domain == "codesextant:g6-release-authority:v1"
    assert first.migration_signing_policy_sha256 == sha256_file(
        "release/g6-release-migration-signing-policy.json"
    )
    assert first.migration_signer_key_id == load_migration_signing_policy()["key_id"]
    assert verify_fixed_release_authority(first).status == "pass"
    assert authorize_release(create_new=True, subject=SUBJECT_B).status == "fail"
    second = authorize_release(
        advance_monotonic=True, subject=SUBJECT_B,
        expected_prior_sha256=sha256_file(first.path), expected_generation=1,
    )
    assert second.generation == 2
    assert second.prior_authority_sha256 == sha256_bytes(first.canonical_bytes)
    assert attempt_authorize_older_subject_or_generation().status == "fail"


def test_g6_authority_advance_requires_release_order_and_git_ancestry() -> None:
    assert advance_authority(PRIOR, NEW_DESCENDANT_HIGHER_SEMVER_LATER_REKOR).status == "pass"
    for candidate in (LOWER_OR_EQUAL_SEMVER, NON_DESCENDANT_COMMIT, OLDER_OR_EQUAL_REKOR_TIME, REUSED_RELEASE_INDEX):
        assert advance_authority(PRIOR, candidate).status == "fail"


def test_non_descendant_release_requires_separately_signed_migration() -> None:
    migration = signed_release_migration(
        prior=PRIOR, successor=NEW_NON_DESCENDANT,
        reason_code="repository_history_migration",
        user_authorization_digest=VALID_EXPLICIT_AUTHORIZATION_SHA256,
    )
    assert verify_release_migration(migration).status == "pass"
    assert migration.migration_signing_policy_sha256 == sha256_file(
        "release/g6-release-migration-signing-policy.json"
    )
    assert migration.admin_signer_key_id == load_migration_signing_policy()["key_id"]
    assert migration.admin_signer_key_id != migration.release_receipt_key_id
    tamper(migration, "user_authorization_digest")
    assert verify_release_migration(migration).status == "fail"


def test_migration_key_policy_is_distinct_admin_only_and_nonexportable() -> None:
    migration_key = verify_existing_migration_key()
    receipt_key = verify_existing_machine_receipt_key()
    assert migration_key.key_id == load_migration_signing_policy()["key_id"]
    assert migration_key.key_id != receipt_key.key_id
    assert migration_key.public_spki_sha256 != receipt_key.public_spki_sha256
    assert migration_key.export_policy == "nonexportable"
    assert migration_key.users == {trusted_installer_sid(), builtin_administrators_sid()}
    assert system_service_installer_sid() not in migration_key.users
    assert invoking_user_sid() not in migration_key.users


def test_g6_authority_terminal_tombstone_is_fixed_signed_and_preflight_blocking(authority_failure) -> None:
    tombstone = fail_authority_advance_ambiguously(authority_failure)
    assert tombstone.path == Path(os.environ["ProgramData"]) / "CodeSextant/Trust/G6/g6-release-authority.tombstone.json"
    assert tombstone.signature_domain == "codesextant:g6-release-authority-tombstone:v1"
    assert tombstone.terminal_manual_intervention is True
    assert tombstone.reason_code in CLOSED_G6_AUTHORITY_TERMINAL_REASONS
    assert verify_fixed_g6_authority_tombstone().status == "pass"
    assert invoke_rendered_g6_runbook().status == "terminal_manual_intervention"
    tamper_one_byte(tombstone.path)
    assert verify_fixed_g6_authority_tombstone().status == "fail"


@pytest.mark.parametrize("kill_point", ALL_G6_AUTHORITY_UPDATE_KILL_POINTS)
def test_g6_authority_update_kill_points_preserve_prior_or_signed_terminal(kill_point) -> None:
    result = crash_authority_update_at(kill_point)
    assert result in {"prior_authority_still_current", "signed_terminal_tombstone"}
    assert not unsigned_or_ambiguous_current_authority_exists()


def test_launcher_rename_before_authority_is_only_recoverable_or_terminal() -> None:
    crash_after_protected_launcher_rename_before_authority_create()
    state = classify_atomic_g6_trust_state()
    assert state == "recoverable_launcher_orphan"
    recovered = recover_g6_trust_complete_authority_only()
    assert recovered.did_not_rewrite_launcher is True
    assert verify_launcher_and_authority_transaction().status == "pass"
    corrupt_launcher_or_acl_before_recovery()
    assert recover_g6_trust_complete_authority_only().status == "terminal_tombstone"


def test_static_verifier_is_authenticode_pinned_before_execution(installed_g8_seed) -> None:
    preflight = winverifytrust_preflight(installed_g8_seed.static_verifier)
    assert preflight.chain_status == "trusted"
    assert preflight.leaf_cert_sha256 == FROZEN_G8_AUTHENTICODE_LEAF_SHA256
    assert invoke_only_after_preflight(preflight).status == "pass"
    replace_signature_with_other_trusted_leaf(installed_g8_seed.static_verifier)
    assert invoke_only_after_preflight(winverifytrust_preflight(installed_g8_seed.static_verifier)).status == "fail"


def test_all_g8_native_release_assets_match_pre_f1_authenticode_policy(signed_g8_assets) -> None:
    policy = load_tracked_g8_authenticode_policy()
    assert policy["leaf_cert_der_sha256"] == FROZEN_G8_AUTHENTICODE_LEAF_SHA256
    for asset in signed_g8_assets:
        result = winverifytrust(asset, revocation=policy["revocation_mode"], timestamp=policy["timestamp_policy"])
        assert result.status == "trusted"
        assert result.leaf_cert_der_sha256 == policy["leaf_cert_der_sha256"]
        assert result.issuer == policy["issuer"]


def test_authenticode_schema_is_the_single_leaf_and_timestamp_contract(repo_root: Path) -> None:
    schema = load_json(repo_root / "release/g8-authenticode-signing-policy.schema.json")
    policy = validate_and_load_authenticode_policy(
        repo_root / "release/g8-authenticode-signing-policy.json", schema
    )
    assert {"leaf_cert_der_sha256", "rfc3161_timestamp_url", "timestamp_policy"} <= set(
        schema["required"]
    )
    assert not set(policy) & {
        "leaf_der_sha256", "leaf_sha256", "timestamp_url", "timestamp_server",
    }
    assert policy["timestamp_policy"] == {
        "kind": "rfc3161",
        "require_trusted_timestamp": True,
        "require_exactly_one_countersignature": True,
        "revocation_mode": "whole_chain",
    }
    assert load_authenticode_policy_for_runbook_renderer() == policy
    assert load_authenticode_policy_for_release_signer() == policy
    assert all_authenticode_consumers_use_schema_field(
        "leaf_cert_der_sha256", consumers=("G5", "G6")
    )


def test_product_trust_asset_roles_and_names_are_exactly_five(candidate_trust_assets) -> None:
    assert {(a.role, a.name) for a in candidate_trust_assets} == {
        ("g8_seed_verifier", "Bootstrap-CodeSextantG8ProductExec.ps1"),
        ("g8_seed_static_verifier", "codesextant-g8-seed-static-verify.exe"),
        ("g8_seed_installer", "codesextant-g8-seed-installer.exe"),
        ("g6_context_preflight", "codesextant-g6-context-preflight.exe"),
        ("g6_runbook_launcher", "codesextant-g6-runbook-launcher.exe"),
    }
    assert len(candidate_trust_assets) == 5


def test_wrong_but_trusted_runbook_signer_executes_zero_runbook_code(installed_g6_launcher) -> None:
    replace_runbook_signature_with_other_trusted_publisher()
    trace = installed_g6_launcher.launch_fixed_runbook()
    assert trace.status == "fail"
    assert trace.runbook_process_created is False
    assert trace.runbook_code_execution_count == 0


def test_authenticode_trusted_publisher_pin_is_public_only_and_distinct_from_receipt_key() -> None:
    trust = verify_existing_authenticode_trust()
    receipt_key = verify_existing_machine_receipt_key()
    assert trust.store == r"Cert:\LocalMachine\TrustedPublisher"
    assert trust.has_private_key is False
    assert sha256(trust.certificate.raw_der) == load_tracked_g8_authenticode_policy()["leaf_cert_der_sha256"]
    assert trust.certificate.thumbprint == load_tracked_g8_authenticode_policy()["certificate_thumbprint"]
    assert trust.cert_store_writers == {system_sid(), builtin_administrators_sid()}
    assert receipt_key.store == r"Cert:\LocalMachine\My"
    assert receipt_key.has_private_key is True
    assert receipt_key.public_spki_sha256 != sha256(trust.certificate.public_key_spki_der)


def test_trusted_publisher_verify_existing_rejects_missing_duplicate_or_replacement() -> None:
    for attack in (remove_trusted_publisher_cert, duplicate_policy_oid_cert, replace_with_same_subject_other_leaf):
        state = provisioned_trust_fixture()
        attack(state)
        assert verify_existing_authenticode_trust(state).status == "fail"


def test_machine_receipt_key_is_nonexportable_system_owned_and_publicly_pinned(machine_key) -> None:
    assert machine_key.store == r"Cert:\LocalMachine\My"
    assert machine_key.provider == "Microsoft Software Key Storage Provider"
    assert machine_key.export_policy == "nonexportable"
    assert machine_key.private_key_owner_sid == trusted_installer_sid()
    assert machine_key.private_key_readers == {system_sid(), builtin_administrators_sid()}
    assert invoking_user_sid() not in machine_key.private_key_readers
    assert machine_key.key_id == tracked_installer_signing_policy()["key_id"]
    assert sha256(machine_key.public_spki_der) == tracked_installer_signing_policy()["public_spki_sha256"]


def test_machine_key_provision_and_rotation_are_create_new_and_subject_invalidating() -> None:
    first = provision_machine_key(create_new=True, policy_out="release/g8-seed-installer-signing-policy.json")
    assert first.status == "pass"
    assert first.exported_private_key_bytes == 0
    assert verify_existing_machine_key(policy=first.policy).status == "pass"
    assert provision_machine_key(create_new=True).status == "fail"
    assert provision_machine_key(overwrite=True).status == "invalid_cli"
    assert rotate_machine_key().requires_new_policy_commit_and_restart_g5 is True


def test_installer_requires_elevated_high_integrity_token(machine_key) -> None:
    assert invoke_install_as_ordinary_user(machine_key).status == "fail"
    assert invoke_install_elevated(machine_key).signer_key_id == tracked_installer_signing_policy()["key_id"]


def test_admin_provision_commands_exit_cleanly_without_private_output(admin_provision_trace) -> None:
    assert admin_provision_trace.create_new_exit_code == 0
    assert admin_provision_trace.verify_existing_exit_code == 0
    assert admin_provision_trace.ordinary_user_nonuse_proof is True
    assert admin_provision_trace.private_key_export_attempt == "denied"
    assert not contains_private_key_seed_pfx_or_secret(admin_provision_trace.stdout + admin_provision_trace.stderr)
~~~

The external-run schema requires ReleaseSubject SHA-256, scenario SHA-256, artifact-manifest SHA-256, selected artifact SHA-256, runner-bundle manifest SHA-256, runner UUID, runner role, key_id, signature_algorithm exactly Ed25519, signature, release-Python lock/interpreter digests, independence assertion, OS/architecture, clean-environment evidence, artifact URL, source/export commit, start/end UTC, every command, exit code, redacted stdout/stderr hash, ambiguity notes, final uninstall proof, and a separately domain-signed privacy-safe public statement. The top-level signature and public-statement signature are unpadded base64url for exactly 64 signature bytes. The gate-receipt schema wraps the verified result in the registry's canonical gate-status envelope and requires `payload.runner_attestation` with exactly runner_id, runner_role, key_id, signature, signed_runner_receipt_sha256, runner_bundle_manifest_sha256, runner_roles_sha256, implementation_actors_sha256, release_python_lock_sha256, and release_python_executable_sha256. It separately requires `payload.public_verification` containing the exact reconstructible statement, `codesextant:first-user-public:v1` domain, Ed25519 signature, and key_id. The statement contains only subject/scenario/artifact/bundle/runtime hashes, role/key ID, required-phase/evidence/uninstall hashes, clean-environment boolean, and pass status; paths, URLs, runner UUID, source/export identities, environment names/values, command/log bytes, timestamps, and ambiguity text are forbidden. Anyone can reconstruct the signed bytes as the public domain prefix plus canonical JSON and verify them against the committed public runner-role key without access to private `first-user-run.json`. A missing, unsigned, hand-edited, ambient/wrong interpreter, unknown-key, wrong-role, wrong-subject, wrong-scenario, wrong-bundle, wrong-manifest, wrong-artifact, actor-overlapping, noncanonical, privacy-unsafe, or independently unverifiable external input fails closed.

release/first-user-runner-roles.json is the pre-freeze public role authority. It contains schema_version 1, algorithm Ed25519, implementation_actors_sha256, and allowed_runners. Every allowed_runners entry contains one UUID runner_id, globally unique key_id, role exactly independent_first_user_runner, and public_key_ed25519_base64url as unpadded base64url encoding exactly 32 public-key bytes. key_id is deterministically `ed25519-` plus the first 16 lowercase hexadecimal characters of SHA-256(public_key_bytes), and every loader recomputes it. Duplicate UUIDs/keys, an implementation actor, any role other than independent_first_user_runner, or any field matching private, secret, seed, or signing_key is invalid. Before Task 2 GREEN, the designated independent runner supplies the real UUID and public key out of band; the implementation commit may not contain a sample/dummy credential. Only the public key is committed. Key rotation or role changes after Final Freeze invalidate ReleaseSubject and restart G5 F1.

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_first_user_verifier.py -q
~~~

Expected: FAIL because tools.verify_first_user does not exist.

**Step 3: Implement the verifier**

~~~python
@dataclass(frozen=True)
class VerificationResult:
    status: Literal["pass", "fail", "unverifiable"]
    findings: tuple[str, ...]


@dataclass(frozen=True)
class RunnerRole:
    runner_id: UUID
    key_id: str
    role: Literal["independent_first_user_runner"]
    public_key_ed25519_base64url: str


SIGNATURE_DOMAIN = b"codesextant:first-user-run:v1\0"


def signed_runner_bytes(receipt: Mapping[str, object]) -> bytes:
    unsigned = dict(receipt)
    unsigned.pop("signature")
    return SIGNATURE_DOMAIN + canonical_json(unsigned)


REQUIRED_PHASES = (
    "download",
    "checksum",
    "install",
    "doctor",
    "index",
    "cli_query",
    "mcp_initialize",
    "mcp_query",
    "http_query",
    "uninstall",
)


def verify_first_user(
    *,
    subject: Mapping[str, object],
    scenario: Mapping[str, object],
    runner_receipt: Mapping[str, object],
    runner_roles: Mapping[str, object],
    implementation_actors: Mapping[str, object],
    artifact_manifest: Mapping[str, object],
    asset_root: Path,
) -> VerificationResult:
    """Validate signature, role separation, clean environment, artifact identity, and phases."""
~~~

canonical_json serializes UTF-8 with sorted keys, separators=(",", ":"), ensure_ascii=False, rejects duplicate keys and non-finite numbers, and appends no newline. The runner signs SIGNATURE_DOMAIN plus canonical_json of the complete external receipt with only signature removed. runner_id, runner_role, key_id, signature_algorithm, subject_sha256, scenario_sha256, artifact_manifest_sha256, selected artifact SHA-256, environment evidence, every step, and uninstall proof are therefore signed. The final file bytes must equal canonical_json of the signed object plus one LF; the verifier rejects alternate/noncanonical encodings before trust decisions.

release/first-user-scenario.json is generated from the same registry-backed quick-start model and records operation ID plus canonical argv for every CLI/MCP/HTTP phase. It also binds runner_roles_sha256 and implementation_actors_sha256 so role policy or actor-roster drift invalidates the scenario. `tools/verify_first_user.py prepare-runner-bundle` is the sole producer of a create-new portable runner directory after ReleaseSubject freezes. From the exact verified product root it copies only the subject, scenario, public role/actor registries, operation registry, required schemas, `requirements/release.lock`, the release-Python bootstrap, the already-reviewed generic `tools/review_role_runner.py` credential launcher, the first-user runner, and the exact verified platform artifact/manifest closure. It writes a canonical `release/first-user-runner-bundle.schema.json` manifest binding the subject, export commit/tree, release-index and artifact-manifest digests, every relative member path/size/SHA-256, and intended runner platform; it rejects an existing destination, symlink/reparse member, source package, `.git`, absolute path, or extra file.

`tools/run_first_user.py` is the non-author clean-environment runner. It is intentionally portable and never calls `Initialize-G6Context`, assumes `E:\ai-king\...`, requires a Git repository, or imports a source checkout. In an arbitrary clean directory it validates the complete runner-bundle manifest and member closure—including the global signing-environment registry/schema—validates its UUID/role, and accepts the 32-byte Ed25519 private seed only in the environment variable named by `--signing-key-env` after the digest-addressed release-Python bootstrap has completed. The parent clean-runner shell and every bootstrap/pip child must reject or omit every environment name matching the registry's reserved pattern. Only the reviewed role launcher may obtain `codesextant/g6/first-user` from the OS credential store and inject it into the fresh `run_first_user.py` child; before spawn it schema-validates the inventory, derives forbidden as all registered names minus the single allowed name, requires exact equality with the launch spec, and independently enumerates the live child environment to reject any other `^CODESEXTANT_[A-Z0-9_]*SIGNING_KEY$` name, including future unregistered roles. The allowed key never enters the parent environment. The runner derives its public key, requires an exact match to the UUID's unique roles entry, removes the variable before starting any artifact child, and excludes it from bounded diagnostic metadata. Using only the bundle's locked release Python and exact platform artifact, it verifies the artifact before install, executes every scenario phase, signs the complete canonical private receipt including `runner_bundle_manifest_sha256`, separately signs the closed privacy-safe public statement under `codesextant:first-user-public:v1`, self-verifies both, and atomically emits only `release/first-user-run.schema.json`; it cannot emit the G6 gate receipt. The secret value is never accepted as argv, stdin, file option, serialized field, or log data.

`tools/verify_first_user.py receipt` is the sole registry producer for `first-user.json`. It consumes the external runner file and returned runner-bundle manifest plus ReleaseSubject, scenario, roles, implementation-actor roster, artifact manifest, and asset root from a freshly initialized local product root. It validates canonical bytes and schemas; recomputes the bundle/member, subject/scenario/roles/actor-roster/manifest/artifact hashes; verifies both Ed25519 signatures against the key_id and UUID role entry; rejects a runner UUID present anywhere in the implementation actor roster; revalidates every phase/argv/hash and clean-environment/uninstall assertion; then emits the canonical gate-status envelope with the exact signed runner attestation and exact reconstructible privacy-safe `payload.public_verification`. The verifier rejects any scenario argv that no longer validates against `spec/operations.yaml`, any public-statement field outside the closed allowlist, and any public statement that cannot be reconstructed and verified independently from `first-user.json` plus the committed role registry. It never accepts the receipt's self-declared `implemented_quickstart=false` as proof of separation. Its `verify-receipt` subcommand later revalidates canonical first-user.json against the immutable signed runner receipt, returned bundle manifest, current subject/scenario/roles/actor roster, and their hashes without rewriting either file; this closes the gap where a schema-valid gate receipt could be substituted after R2.

`tools/install_g8_seed.py` is the source for the sole signed standalone G6/G7 installer/verifier; no runbook copy command or second installer is permitted. Its closed CLI is: mutating elevated `install --create-new` and `recover-orphan --create-receipt-only`; read-only `verify`, `verify-tombstone`, and `state-fixed --format json`; plus `export-evidence --create-new|--verify-existing --evidence-dir <authenticated context evidence authority>`. `state-fixed` only classifies absent, complete, orphan_assets_without_receipt, or terminal_tombstone from fixed no-follow handles and returns no trusted digest. `export-evidence` accepts only the authenticated subject-derived evidence directory, fixed basename `g8-seed-install.json`, and byte-copies/reopens/compares the already verified ProgramData receipt; it cannot create/repair authority. Every mode rejects a destination/file/receipt/digest/role/basename/owner/ACL/pin override and unknown option. On Windows all authoritative paths are compile/policy-fixed beneath `%ProgramData%\CodeSextant\Trust\G8\`: `Bootstrap-CodeSextantG8ProductExec.ps1`, `codesextant-g8-seed-static-verify.exe`, and installed signed `g8-seed-install.json`. `%LOCALAPPDATA%`, source/export tree, CWD, environment, or caller path is never install authority.

Before mutation, `install` validates ReleaseSubject and independently verifies its exact `release_index_sha256` plus Sigstore bundle through frozen signing/bootstrap policies. It requires exactly one member with role/name `g8_seed_verifier`/`Bootstrap-CodeSextantG8ProductExec.ps1` and exactly one with role/name `g8_seed_static_verifier`/`codesextant-g8-seed-static-verify.exe`; missing, duplicate, renamed, extra-role, source-tree fallback, a merely self-consistent forged index, or any byte not re-hashed from the signed release-asset directory is red. The static executable is a product-frozen Rust/native build whose Authenticode leaf-certificate SHA-256 is a pre-freeze literal in both signed release metadata and G7's subject-authenticated minimal WinVerifyTrust prelude.

`release/g8-seed-installer-signing-policy.json` plus its closed schema are the machine-receipt signing authority. Provisioning is explicitly two phase and completes before the Task 2 commit: an administrator runs `tools/provision_g8_seed_machine_key.ps1 -CreateNew -PolicyOut release/g8-seed-installer-signing-policy.json`; it refuses any existing key/name/policy, creates a fresh nonexportable ECDSA P-256 CNG key in `Cert:\LocalMachine\My`, sets private-key owner TrustedInstaller and read/use access only for SYSTEM/Administrators, exports only the public SPKI/certificate, derives deterministic key_id/thumbprint, and atomically creates the policy. The policy fixes `ECDSA_P256_SHA256`, signature domain `codesextant:g8-seed-install:v1`, public SPKI bytes/SHA-256, certificate thumbprint, store/provider/key name, nonexportable flag, and exact private-key owner/read ACL; that generated public-only policy is then committed, compiled into the static verifier, and included in G5 signed review scope.

From F1 onward only `tools/provision_g8_seed_machine_key.ps1 -VerifyExisting -Policy release/g8-seed-installer-signing-policy.json` is allowed: it never creates/imports/repairs, rechecks the exact existing key/public SPKI/provider/nonexportability/ACL, proves the invoking ordinary user cannot open/export/sign, and fails on absence/drift. Rotation has no in-place mode: an administrator must provision a new key under a new name, regenerate/commit policy and static verifier, and restart G5; old-key deletion is a separately authorized post-migration operation. `install` has no create/import path, requires a high-integrity elevated token, opens the exact existing key by policy key_id, rechecks provider/export/ACL/public SPKI, and signs without exporting key material. The machine public key is compiled into the static verifier and included in the signed release index, so replacing executable plus receipt with ordinary-user material fails before seed execution.

Authenticode trust is a distinct public-only authority. `release/g8-authenticode-signing-policy.schema.json` is the field-name SSOT: the leaf pin is only `leaf_cert_der_sha256`, the timestamp endpoint is only `rfc3161_timestamp_url`, and the closed structured `timestamp_policy` requires RFC3161, one trusted countersignature, and whole-chain revocation; aliases such as `leaf_der_sha256`, `timestamp_url`, or `timestamp_server` are invalid. The renderer and release-signing path both schema-validate and load the same typed policy object, and cross-plan tests require every G5/G6/G7 consumer to use those schema names. Before F1 an administrator runs `tools/provision_g8_authenticode_trust.ps1 -InstallPublicCert -Policy release/g8-authenticode-signing-policy.json`, which imports exactly the policy's leaf DER into `Cert:\LocalMachine\TrustedPublisher`, requires no private key, fixes the private CodeSextant policy OID, and leaves store mutation to SYSTEM/Administrators. It rejects an existing different/duplicate OID certificate. Every later shell runs `-VerifyExisting`; it requires exactly one certificate whose raw DER SHA-256/thumbprint/issuer/EKU/policy OID equal the committed policy and proves no private key is present. The Authenticode signing private key remains only on the release signer; it is never installed on the G6 user machine. This TrustedPublisher certificate is deliberately different from the nonexportable ECDSA receipt key in `LocalMachine\My`; schemas/tests reject equal SPKI/key IDs or conflated store/provider roles.

The elevated installer opens `%ProgramData%` and every new/existing child using no-follow handles, records volume/file IDs, and creates the full chain owner-exact `NT SERVICE\TrustedInstaller` with a protected non-inherited DACL containing exactly SYSTEM and BUILTIN\Administrators FullControl plus the invoking ordinary user's read/execute rights—never write, append, delete, delete-child, rename, take-ownership, or WRITE_DAC. It rejects Everyone/Users writes, current-user Modify, inherited/extra ACEs, owner drift, alternate data streams, hardlinks, and every symlink/junction/reparse component. It writes each asset through a same-directory secured temporary handle, flushes bytes/metadata, atomically create-new renames, then reopens the root-to-leaf chain without following reparses and rechecks file IDs, owner/DACL, size, hash, and parent identities. A concurrent parent rename/reparse race, temp/flush/ACL/rename failure, existing receipt, or pre-existing non-orphan destination fails without overwrite.

`recover-orphan --create-receipt-only` handles only the crash window in which both fixed asset renames completed but the signed installed receipt did not. It never rewrites either asset. It re-verifies the signed release index/bundle from an explicit authenticated release-assets authority, re-hashes both fixed live files, re-opens and validates the complete no-reparse handle chain, exact TrustedInstaller owner/DACL/file IDs, exact Authenticode leaf, and absence of any existing receipt/tombstone; only exact equality may create-new and sign the receipt. Any incomplete/mismatched/ambiguous state atomically creates the fixed `%ProgramData%\CodeSextant\Trust\G8\g8-seed-install.tombstone.json` and requires manual elevated remediation.

`release/g8-seed-install-tombstone.schema.json` is closed and the tombstone is machine-signed under distinct domain `codesextant:g8-seed-tombstone:v1`. It binds subject/index/bundle, machine signer key_id/algorithm/signature, one closed terminal reason code, attempted operation UUID/time, the canonical hash of live observations for every fixed path (existence, file ID, owner/DACL, size/hash/reparse state), and `terminal_manual_intervention=true`; it contains no executable path override. `verify-tombstone` verifies the fixed file only. Installer, recovery, static verifier, G7 prelude, and every downstream consumer check tombstone first and return the terminal state without repair or execution. Only an explicit separately reviewed administrator-remediation runbook may remove it; normal install/recovery has no removal option. Kill-point tests cover every step before/after each temp write, flush, rename, tombstone sign/create, and receipt sign/create so no crash wedges a silently reusable state.

`release/g6-release-authority.schema.json` closes the anti-rollback anchor at `%ProgramData%\CodeSextant\Trust\G6\g6-release-authority.json`. Under domain `codesextant:g6-release-authority:v1` it binds monotonically increasing generation, prior-authority SHA-256 (null only at generation 1), subject canonical SHA-256, source/export commit/tree, release tag/version, repository ID, release-index/bundle SHA-256 and integrated time, Authenticode policy SHA-256, the exact `release/g6-release-migration-signing-policy.json` SHA-256 and its migration signer key_id, machine receipt key_id/algorithm/signature, issued UTC, exact TrustedInstaller owner/protected ACL, and status current. The signed standalone context-preflight executable exposes elevated create/advance operations using only the pre-provisioned key/fixed path, writes append-only history before atomic current-pointer replacement, and rejects generation gaps, subject rollback, mismatched prior bytes, a migration-policy/key mismatch, or same generation/different subject.

Normal monotonic advance is mechanically ordered by all three conditions: the new semantic version is strictly greater under SemVer precedence; `git merge-base --is-ancestor <prior source_commit> <new source_commit>` succeeds in the authenticated source repository and the export commit is derived from that successor; and the new signed release-index Rekor integrated time is strictly later than the prior authority while its digest/tag have never appeared in history. Failure of any condition is rollback, not an alternate ordering heuristic.

`release/g6-release-migration.schema.json` is the sole non-descendant exception. It binds prior/new authority and subject/index identities, old/new repositories/commits, closed migration reason, evidence manifest, explicit user authorization payload digest, monotonically later transparency time, the exact migration-signing-policy SHA-256, the policy's migration signer key_id, and two distinct signatures. `release/g6-release-migration-signing-policy.json` plus schema fix a separate nonexportable administrator CNG key, public SPKI SHA-256, provider/key name, algorithm, and signature domain `codesextant:g6-release-migration:v1`; `tools/provision_g6_release_migration_key.ps1 -CreateNew|-VerifyExisting` gives use only to TrustedInstaller/Administrators, excludes the installer service and ordinary user, and refuses the receipt-key SPKI/key_id. `authorize-release --advance-migration` re-hashes that committed policy, requires the normal machine receipt signature plus an offline administrator migration signature by exactly its key_id and exact authorization, and records migration plus policy digests in history. Missing/expired authorization, policy/key drift, same signer, arbitrary reason, lower/equal SemVer, or older/equal index time fails. No force flag bypasses ancestry.

`release/g6-release-authority-tombstone.schema.json` closes the only terminal marker at `%ProgramData%\CodeSextant\Trust\G6\g6-release-authority.tombstone.json`. Under distinct domain `codesextant:g6-release-authority-tombstone:v1` it binds attempted/prior generation and authority digest, attempted subject/index/tag, the fixed launcher source/install hashes and live file ID, closed reason code, operation UUID, complete live path/owner/DACL/hash observations, machine signer key_id/algorithm/signature, UTC, and `terminal_manual_intervention=true`. Launcher installation plus authority creation/advance is one native transaction under this marker. A launcher-rename-before-authority crash is recoverable only when signed index, fixed launcher bytes/file ID/ACL/no-reparse, subject, and absent authority all reverify; `recover-g6-trust --complete-authority-only` never rewrites the launcher. Any mismatch creates the terminal marker. `verify-authority-tombstone` accepts only fixed path and recompares live descriptors. The protected launcher/runbook checks it before download hints; valid or invalid tombstone fails before network/runbook execution. Kill tests cover launcher temp/flush/rename, history/current authority writes, tombstone writes, and verification; every crash leaves prior authority, exact recoverable orphan, or signed terminal state.

`release/g8-seed-static-verifier.rs` builds `codesextant-g8-seed-static-verify.exe`, a dependency-closed native pre-exec verifier that accepts only `verify-fixed`. It is invoked only after the subject-authenticated G7 prelude calls WinVerifyTrust with whole-chain revocation, obtains the signer leaf DER from provider state, and constant-time matches the frozen SHA-256 literal; another generally trusted certificate is insufficient. The native verifier then opens the fixed ProgramData component chain by handle, verifies exact owner/DACL/no-reparse/file IDs, validates the installed receipt's machine signature against the compiled public key, binds receipt subject/index/asset hashes, and re-hashes the live script and its own file. It returns a verified open script handle/identity to the launcher, which rechecks that identity immediately before execution; attacker-controlled replacement executable/receipt/script bytes therefore fail before any verifier-controlled seed code runs.

`release/g6-context-preflight.rs` builds the separate dependency-closed, Authenticode-signed release asset `codesextant-g6-context-preflight.exe` with typed role `g6_context_preflight`. The G6 runbook downloads it with the fixed release-index bundle into a new directory, uses the OS WinVerifyTrust API plus the pre-F1 literal leaf pin before execution, and then invokes only `verify-and-export`. The native preflight independently verifies the release index/bundle/policy/bootstrap and ReleaseSubject; binds source HEAD/tree/clean tracked closure/no nonignored untracked/no-reparse; verifies initializer, release gate, lock/bootstrap, and every allowed tool digest; and creates a read-only content-addressed export. It returns the absolute initializer and authority roots from that export. It neither installs the G8 seed nor elevates. Thus mutable checkout Python/PowerShell is never the first verifier.

`release/g8-seed-installer.spec` creates the standalone `codesextant-g8-seed-installer.exe` release asset from reviewed `tools/install_g8_seed.py` plus its closed schemas/policies. F4 builds it in the allowlist export with the locked packaging toolchain, signs it with the same pre-F1 Authenticode policy, and indexes it under unique role `g8_seed_installer`. G6 verifies the signed release index, then WinVerifyTrust+leaf pin on this exact executable before `Start-Process -Verb RunAs`; it never elevates checkout Python, a source-tree script, or an unindexed executable.

`release/g8-seed-install-receipt.schema.json` is closed and binds ReleaseSubject SHA-256, source/export commit/tree, release-index/bundle SHA-256, all exact trust asset roles/names/sizes/SHA-256 values including standalone installer/context preflight, static/installer Authenticode leaf/issuer/timestamp-policy digest, installer build-spec/static-source/context-source/schema/machine-signing-policy digests, three fixed installed paths, installed sizes/SHA-256/file IDs, owner SID, exact ACE SID/mask rows and SDDL SHA-256 for every component, protected/empty-inherited/no-reparse properties, installer signer key ID/algorithm/signature, installation UTC, and pass. `verify` recomputes every field from authenticated subject/assets/live handles. G7 consumes fixed signed receipt plus byte-identical ignored mirror, passes WinVerifyTrust pin gate, and runs `verify-fixed` before publication planning.

Before committing Task 2, run the one-time administrator provisioning and verify it from both privilege levels:

~~~powershell
$createReceiptKey = Start-Process pwsh -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile','-File','tools/provision_g8_seed_machine_key.ps1','-CreateNew','-PolicyOut','release/g8-seed-installer-signing-policy.json','-NoPrivateOutput')
if ($createReceiptKey.ExitCode -ne 0) { throw 'G8 receipt CNG key provisioning failed' }
$installPublisher = Start-Process pwsh -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile','-File','tools/provision_g8_authenticode_trust.ps1','-InstallPublicCert','-Policy','release/g8-authenticode-signing-policy.json','-NoPrivateOutput')
if ($installPublisher.ExitCode -ne 0) { throw 'CodeSextant TrustedPublisher public certificate installation failed' }
$createMigrationKey = Start-Process pwsh -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile','-File','tools/provision_g6_release_migration_key.ps1','-CreateNew','-PolicyOut','release/g6-release-migration-signing-policy.json','-NoPrivateOutput')
if ($createMigrationKey.ExitCode -ne 0) { throw 'separate G6 migration key provisioning failed' }
$verifyReceiptKey = Start-Process pwsh -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile','-File','tools/provision_g8_seed_machine_key.ps1','-VerifyExisting','-Policy','release/g8-seed-installer-signing-policy.json','-AssertNonExportable','-AssertOrdinaryUserCannotUse','-NoPrivateOutput')
$verifyPublisher = Start-Process pwsh -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile','-File','tools/provision_g8_authenticode_trust.ps1','-VerifyExisting','-Policy','release/g8-authenticode-signing-policy.json','-AssertPublicOnly','-NoPrivateOutput')
$verifyMigrationKey = Start-Process pwsh -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile','-File','tools/provision_g6_release_migration_key.ps1','-VerifyExisting','-Policy','release/g6-release-migration-signing-policy.json','-AssertDistinctFromPolicy','release/g8-seed-installer-signing-policy.json','-NoPrivateOutput')
if ($verifyReceiptKey.ExitCode -ne 0 -or $verifyPublisher.ExitCode -ne 0 -or $verifyMigrationKey.ExitCode -ne 0) { throw 'pre-freeze machine trust VerifyExisting failed' }
& pwsh -NoProfile -File tools/provision_g8_seed_machine_key.ps1 -ProveOrdinaryUserCannotUse -Policy release/g8-seed-installer-signing-policy.json -NoPrivateOutput
if ($LASTEXITCODE -ne 0) { throw 'ordinary-user receipt-key non-use proof failed' }
~~~

`-NoPrivateOutput` is schema/test enforced: stdout may contain only status, key_id, public SPKI/certificate digests, and ACL SIDs; stderr is empty on success. PFX/private blobs, seeds, signatures over caller data, provider handles, or secret paths are forbidden. A second `-CreateNew`, overwrite/import mode, missing high-integrity token, or ordinary-user signing attempt exits nonzero without repair.

**Step 4: Run local GREEN**

~~~powershell
$releasePython = & C:\Python311\python.exe tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python
if ($LASTEXITCODE -ne 0) { throw 'locked release Python bootstrap failed' }
& $releasePython -m pytest tests/release/test_first_user_verifier.py tests/release/test_g8_seed_install.py tests/release/test_g8_seed_static_verifier.py tests/release/test_g6_context_preflight.py -q
if ($LASTEXITCODE -ne 0) { throw 'first-user verifier tests failed' }
& $releasePython tools/verify_first_user.py schema-check --scenario release/first-user-scenario.json --runner-roles release/first-user-runner-roles.json --implementation-actors provenance/implementation-actors.json --release-python-lock requirements/release.lock
if ($LASTEXITCODE -ne 0) { throw 'first-user schemas/roles/release-Python check failed' }
& $releasePython tools/install_g8_seed.py schema-check --receipt-schema release/g8-seed-install-receipt.schema.json --tombstone-schema release/g8-seed-install-tombstone.schema.json --g6-authority-schema release/g6-release-authority.schema.json --g6-authority-tombstone-schema release/g6-release-authority-tombstone.schema.json --g6-release-migration-schema release/g6-release-migration.schema.json --g6-release-migration-signing-policy release/g6-release-migration-signing-policy.json --g6-release-migration-signing-policy-schema release/g6-release-migration-signing-policy.schema.json --installer-signing-policy release/g8-seed-installer-signing-policy.json --installer-signing-policy-schema release/g8-seed-installer-signing-policy.schema.json --signing-policy release/signing-policy.json --verifier-bootstrap release/verifier-bootstrap.json
if ($LASTEXITCODE -ne 0) { throw 'G8 seed installer schema/policy check failed' }
& $releasePython tools/generate_producer_launch_policy.py sync --through-phase G6_TASK2 --registry release/evidence/receipt-registry.json --out release/evidence/producer-launch-policy.json
& $releasePython tools/generate_producer_launch_policy.py check --through-phase G6_TASK2 --registry release/evidence/receipt-registry.json --policy release/evidence/producer-launch-policy.json --schema release/evidence/producer-launch-policy.schema.json
if ($LASTEXITCODE -ne 0) { throw 'G6 Task2 launch specs are missing or stale' }
$toolBin = & C:\Python311\python.exe tools/bootstrap_release_tools.py ensure --lock release/toolchain.lock --print-bin
$lockedRustc = Join-Path $toolBin 'rustc.exe'
& $lockedRustc --edition 2024 -D warnings release/g8-seed-static-verifier.rs -o $env:TEMP\codesextant-g8-seed-static-verify.exe
& $lockedRustc --edition 2024 -D warnings release/g6-context-preflight.rs -o $env:TEMP\codesextant-g6-context-preflight.exe
& $lockedRustc --edition 2024 -D warnings release/g6-runbook-launcher.rs -o $env:TEMP\codesextant-g6-runbook-launcher.exe
if ($LASTEXITCODE -ne 0) { throw 'locked Rust build of G6/G8 native trust executables failed' }
& $releasePython -m PyInstaller --clean --noconfirm release/g8-seed-installer.spec
if ($LASTEXITCODE -ne 0) { throw 'deterministic standalone G8 installer package failed' }
& $releasePython tools/install_g8_seed.py package-smoke --spec release/g8-seed-installer.spec --installer dist/codesextant-g8-seed-installer.exe --static-verifier $env:TEMP\codesextant-g8-seed-static-verify.exe --context-preflight $env:TEMP\codesextant-g6-context-preflight.exe --runbook-launcher $env:TEMP\codesextant-g6-runbook-launcher.exe --seed-script release/Bootstrap-CodeSextantG8ProductExec.ps1 --expect-role-name g8_seed_verifier=Bootstrap-CodeSextantG8ProductExec.ps1 --expect-role-name g8_seed_static_verifier=codesextant-g8-seed-static-verify.exe --expect-role-name g8_seed_installer=codesextant-g8-seed-installer.exe --expect-role-name g6_context_preflight=codesextant-g6-context-preflight.exe --expect-role-name g6_runbook_launcher=codesextant-g6-runbook-launcher.exe --reject-extra
if ($LASTEXITCODE -ne 0) { throw 'trust asset package smoke/cardinality failed' }
~~~

Expected: tests plus scenario/role/actor schema and separation validation pass. The roles file contains a real externally supplied runner UUID/public key, no private-key field, and an implementation_actors_sha256 equal to the canonical tracked roster. The independent clean-runner validation is deliberately deferred to R2 after Final Freeze; this implementation task neither creates nor validates release evidence.

**Step 5: Commit**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('release/evidence/first-user.schema.json','release/first-user-run.schema.json','release/first-user-runner-bundle.schema.json','release/first-user-scenario.json','release/first-user-runner-roles.json','release/g8-seed-install-receipt.schema.json','release/g8-seed-install-tombstone.schema.json','release/g6-release-authority.schema.json','release/g6-release-authority-tombstone.schema.json','release/g6-release-migration.schema.json','release/g6-release-migration-signing-policy.schema.json','release/g6-release-migration-signing-policy.json','release/g8-seed-installer-signing-policy.schema.json','release/g8-seed-installer-signing-policy.json','release/g8-authenticode-signing-policy.schema.json','release/g8-authenticode-signing-policy.json','release/g8-seed-static-verifier.rs','release/g8-seed-installer.spec','release/g6-context-preflight.rs','release/g6-runbook-launcher.rs','release/evidence/producer-launch-policy.json','tools/run_first_user.py','tools/verify_first_user.py','tools/install_g8_seed.py','tools/provision_g8_seed_machine_key.ps1','tools/provision_g8_authenticode_trust.ps1','tools/provision_g6_release_migration_key.ps1','tests/release/test_first_user_verifier.py','tests/release/test_g8_seed_install.py','tests/release/test_g8_seed_static_verifier.py','tests/release/test_g6_context_preflight.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'test: verify independent first-user quick start'
~~~

### Task 3: Add a privacy-safe dogfood event recorder

**Files:**

- Create: dogfood/schema.json
- Create: dogfood/execution.schema.json
- Create: dogfood/plan.schema.json
- Create: dogfood/workstream-bindings.schema.json
- Create: dogfood/workstream-intent.schema.json
- Create: dogfood/window-state.schema.json
- Create: dogfood/policy.json
- Create: dogfood/privacy.md
- Create: dogfood/issues.schema.json
- Create: dogfood/time-anchor.schema.json
- Create: dogfood/transparency-plan.schema.json
- Create: dogfood/transparency-authorization.schema.json
- Create: dogfood/anchor-dispatch-start.schema.json
- Create: dogfood/anchor-dispatch-tombstone.schema.json
- Create: release/dogfood-signing-policy.schema.json
- Create: release/dogfood-signing-policy.json
- Create: release/Initialize-CodeSextantG6.ps1
- Generate, Authenticode-sign, then track: release/Run-CodeSextantG6.ps1
- Modify: release/security-review-scope.json
- Create: .github/workflows/dogfood-anchor.yml
- Create: tools/dogfood.py
- Create: tools/dogfood_anchor.py
- Create: tools/render_g6_runbook.py
- Create: tests/release/test_dogfood_evidence.py
- Create: tests/release/test_dogfood_anchor.py
- Create: tests/release/test_g6_fresh_shell.py
- Create: tests/release/test_g6_runbook_bootstrap.py
- Generated private evidence after freeze, never committed: release/evidence/dogfood-plan.json
- Generated private bindings/secret after freeze, never committed or published: release/evidence/dogfood-workstream-bindings.json
- Generated owner-only pending intent/state after freeze, never committed or published: release/evidence/dogfood-workstream-intent.json and release/evidence/dogfood-window-state.json
- Generated private transparency plan/authorization after freeze, never committed: release/evidence/dogfood-transparency-plan.json and release/evidence/dogfood-transparency-authorization.json
- Generated private one-shot dispatch state, never committed: release/evidence/dogfood-anchor-dispatch/

**Step 1: Write RED tests**

~~~python
def test_event_rejects_private_data(valid_event) -> None:
    for leaked in (
        r"E:\ai-king",
        r"C:\Users\zerox",
        "sk-test-secret",
        "def proprietary_function():",
    ):
        candidate = dict(valid_event, note=leaked)
        assert validate_event(candidate).status == "fail"


@pytest.mark.parametrize(
    ("schema_path", "fixture_name"),
    [
        ("dogfood/schema.json", "valid_event"),
        ("dogfood/execution.schema.json", "valid_execution"),
        ("dogfood/time-anchor.schema.json", "valid_anchor"),
    ],
)
def test_event_execution_and_verified_anchor_use_the_tracked_authoritative_schemas(
    request, repo_root, schema_path, fixture_name
) -> None:
    document = request.getfixturevalue(fixture_name)
    assert validate_against_schema(document, repo_root / schema_path).status == "pass"
    assert runtime_schema_path_for(type(document)) == schema_path
    assert validate_against_schema(add_unknown_property(document), repo_root / schema_path).status == "fail"


def test_blank_pwsh_rehydrates_g6_with_the_locked_interpreter_and_exact_root(
    frozen_g6_fixture,
) -> None:
    result = invoke_g6_resume_in_blank_pwsh(
        frozen_g6_fixture,
        inherited_environment=minimal_process_environment(),
    )
    assert result.initializer == "Initialize-G6Context"
    assert result.inherited_path_variables == ()
    assert result.authoritative_root == Path(r"E:\ai-king\項目資料\CodeSextant")
    assert result.locked_release_python_verified is True
    assert result.ambient_python_calls_after_bootstrap == 0
    assert result.subject_path == result.authoritative_root / "release/evidence/release-subject.json"
    assert result.subject_check_calls == 1
    assert result.resume_window_calls == 1


def test_g6_preflight_authenticates_checkout_before_any_project_code_executes(frozen_g6_fixture) -> None:
    trace = invoke_g6_resume_in_blank_pwsh(frozen_g6_fixture)
    assert trace.first_project_code_execution == "verified-content-addressed-export/release/Initialize-CodeSextantG6.ps1"
    assert trace.pre_exec_checks == (
        "pinned_authenticode_policy", "release_subject_schema_and_digest",
        "head_equals_subject_source_commit", "source_tree_equals_subject",
        "tracked_closure", "clean_index_worktree", "no_nonignored_untracked",
        "initializer_digest", "release_gate_digest", "bootstrap_digest",
    )


@pytest.mark.parametrize("tamper", [
    tamper_worktree_initializer,
    tamper_release_gate_tool,
    replace_initializer_with_same_relative_path_decoy,
    add_nonignored_untracked_python_shadow,
])
def test_g6_preflight_tamper_has_zero_project_code_execution(frozen_g6_fixture, tamper) -> None:
    tamper(frozen_g6_fixture)
    trace = invoke_g6_resume_in_blank_pwsh(frozen_g6_fixture)
    assert trace.status == "fail"
    assert trace.project_code_execution_count == 0


def test_rendered_g6_runbook_defines_dependency_free_wintrust_before_first_call(repo_root: Path) -> None:
    runbook = repo_root / "release/Run-CodeSextantG6.ps1"
    text = runbook.read_text(encoding="utf-8")
    definition = text.index("function Assert-AuthenticodeWinTrustWholeChain")
    first_call = text.index("Assert-AuthenticodeWinTrustWholeChain -LiteralPath")
    assert definition < first_call
    assert "WinVerifyTrust" in text and "WTD_REVOKE_WHOLECHAIN" in text
    assert "WTD_REVOCATION_CHECK_CHAIN_EXCLUDE_ROOT" in text
    assert "CryptQueryObject" in text and "RFC3161" in text
    assert not contains_import_dot_source_add_type_from_file_or_network(text)
    assert not contains_placeholder_or_unresolved_template_token(text)
    assert verify_authenticode_signature_and_policy(runbook).status == "pass"


def test_g6_runbook_renderer_is_deterministic_and_binds_real_authenticode_policy(repo_root: Path) -> None:
    rendered = render_g6_runbook(repo_root / "release/g8-authenticode-signing-policy.json")
    tracked_unsigned_body = strip_authenticode_signature(repo_root / "release/Run-CodeSextantG6.ps1")
    assert rendered == tracked_unsigned_body
    assert concrete_leaf_der_sha256(rendered) == load_authenticode_policy()["leaf_cert_der_sha256"]


def test_r4_crash_after_summary_before_issues_forward_recovers_without_rewrite(g6_window) -> None:
    crash_after_registered_write(g6_window, "dogfood-summary.json")
    before = sha256_file(g6_window.evidence / "dogfood-summary.json")
    resumed = run_r4(g6_window)
    assert resumed.status == "pass"
    assert sha256_file(g6_window.evidence / "dogfood-summary.json") == before
    assert (g6_window.evidence / "issues.json").is_file()


def test_r4_reverse_partial_issues_without_summary_is_terminal(g6_window) -> None:
    create_schema_valid_issues_without_summary(g6_window)
    resumed = run_r4(g6_window)
    assert resumed.status == "terminal"
    assert not (g6_window.evidence / "dogfood-summary.json").exists()


def test_g5_independent_security_scope_covers_g6_initializer(
    g5_security_review_scope,
) -> None:
    assert {
        "g6_context_initializer_and_cross_day_resume",
        "g6_portable_first_user_runner_bundle",
    } <= set(g5_security_review_scope["review_only_material_ids"])


def test_record_rejects_a_bare_asserted_outcome(valid_event, tmp_path) -> None:
    assert record_event(event=valid_event, execution_receipt=None, out=tmp_path / "events.jsonl").status == "fail"


def test_execution_receipt_binds_the_real_binary_and_response(valid_execution, artifact) -> None:
    assert valid_execution.binary_sha256 == artifact.installed_binary_sha256
    assert valid_execution.exit_code == 0
    assert valid_execution.response_schema_valid is True
    valid_execution.response_sha256 = "0" * 64
    assert verify_execution_receipt(valid_execution, artifact).status == "fail"


def test_failure_or_product_defect_requires_a_linked_issue(failed_execution, issues) -> None:
    failed_execution.issue_id = None
    assert event_from_execution(failed_execution, issues).status == "fail"


def test_event_is_bound_to_rc_and_known_workstream(valid_event) -> None:
    valid_event["artifact_sha256"] = "0" * 64
    assert validate_event(valid_event).status == "fail"


def test_two_workstream_ids_must_bind_two_distinct_real_repository_commitments(valid_plan) -> None:
    valid_plan["workstreams"][1]["repository_commitment"] = valid_plan["workstreams"][0]["repository_commitment"]
    assert validate_plan(valid_plan).status == "fail"


def test_two_clones_of_same_repository_identity_are_not_two_workstreams(tmp_path) -> None:
    first, second = clone_same_repository_to_two_paths(tmp_path)
    result = create_plan(workstream_roots=[first, second])
    assert result.status == "fail"


def test_vacuous_or_reused_workstream_activity_is_rejected(valid_execution) -> None:
    valid_execution["indexed_file_count"] = 0
    assert event_from_execution(valid_execution).status == "fail"
    valid_execution["indexed_file_count"] = 42
    valid_execution["query_result_count"] = 0
    assert event_from_execution(valid_execution).status == "fail"


def test_rewriting_an_old_event_breaks_the_hash_chain(valid_chain) -> None:
    valid_chain[2]["operation"] = "status"
    assert validate_chain(valid_chain).status == "fail"


def test_daily_anchor_must_bind_the_observed_chain_head(valid_chain, valid_anchor) -> None:
    valid_anchor["statement"]["chain_head_sha256"] = "0" * 64
    assert verify_anchor(valid_anchor, valid_chain).status == "fail"


def test_start_anchor_rejects_a_literal_instead_of_the_subject_genesis(subject) -> None:
    request = start_anchor_request(subject, chain_head="genesis")
    assert validate_anchor_request(request, subject).status == "fail"
    assert genesis_chain_head(subject.sha256) != "genesis"


def test_tracked_policy_contains_no_future_subject_or_anchor(policy) -> None:
    assert "subject_sha256" not in policy
    assert "artifact_sha256" not in policy
    assert "start_anchor_sha256" not in policy


@pytest.mark.parametrize("kind", ["intent", "bindings", "window_state"])
def test_private_workstream_state_requires_platform_owner_only_protection(tmp_path, kind) -> None:
    private_file = create_private_workstream_file(kind, tmp_path / f"{kind}.json")
    assert private_file.is_symlink_or_reparse_point is False
    if os.name == "nt":
        assert private_file.security_descriptor.owner_sid == current_user_sid()
        assert private_file.dacl.inheritance_protected is True
        assert private_file.dacl.allowed_sids == {current_user_sid()}
        assert private_file.dacl.denied_or_unexpected_aces == set()
    else:
        assert stat.S_IMODE(private_file.path.stat().st_mode) == 0o600
    assert validate_private_workstream_file(kind, private_file.path).status == "pass"


def test_anchor_transparency_plan_authorizes_exactly_seven_one_shot_slots(subject) -> None:
    plan = create_transparency_plan(subject, signing_policy=SIGNING_POLICY)
    assert [slot.kind for slot in plan.slots] == [
        "start", "daily", "daily", "daily", "daily", "daily", "end"
    ]
    assert len({slot.slot_id for slot in plan.slots}) == 7
    assert plan.public_transparency_log_disclosure.irreversible is True
    assert dispatch_without_authorization(plan, slot_id=plan.slots[0].slot_id).status == "fail"


def test_anchor_dispatch_rejects_wrong_subject_workflow_policy_or_slot(valid_anchor_authorization) -> None:
    for field in ("subject_sha256", "repository", "workflow_ref", "signing_policy_sha256"):
        candidate = copy.deepcopy(valid_anchor_authorization)
        candidate[field] = wrong_value_for(field)
        assert authorize_anchor_dispatch(candidate).status == "fail"
    assert dispatch_anchor(valid_anchor_authorization, slot_id=uuid4()).status == "fail"


@pytest.mark.parametrize("mutation", ["slot_id", "kind", "ordinal", "order", "replace", "remove", "append"])
def test_authorization_binds_exact_ordered_seven_slot_digest(valid_anchor_plan, mutation) -> None:
    authorization = authorize_anchor_plan(valid_anchor_plan)
    assert authorization.ordered_slots_sha256 == canonical_sha256(valid_anchor_plan.slots)
    tampered = mutate_plan_slots(copy.deepcopy(valid_anchor_plan), mutation)
    assert validate_anchor_authorization(tampered, authorization).status == "fail"
    assert dispatch_anchor(authorization, plan=tampered, slot_id=tampered.slots[0].slot_id).status == "fail"


def test_ambiguous_anchor_dispatch_tombstones_slot_and_forbids_retry(valid_anchor_dispatch) -> None:
    start = persist_dispatch_start(valid_anchor_dispatch)
    tombstone = mark_anchor_dispatch_ambiguous(start)
    assert can_retry_anchor_slot(start.slot_id, tombstone) is False
    assert dispatch_anchor(valid_anchor_dispatch, slot_id=start.slot_id).status == "fail"


def test_anchor_reset_never_claims_public_rekor_records_were_erased(valid_anchor_plan) -> None:
    reset = reset_dogfood_window(valid_anchor_plan)
    assert reset.public_transparency_log_state == "authorized_records_remain"


def test_fresh_shell_resumes_after_start_and_daily_without_overwriting_authority(
    authorized_window,
) -> None:
    start = dispatch_slot(authorized_window, "start")
    original_authority = digests_of(
        authorized_window.transparency_plan,
        authorized_window.authorization,
        start,
    )
    resumed = resume_window_from_disk(authorized_window.root, empty_process_environment())
    assert resumed.remaining_slot_kinds == ["daily"] * 5 + ["end"]
    dispatch_slot(resumed, "daily", ordinal=1)
    resumed_again = resume_window_from_disk(authorized_window.root, empty_process_environment())
    assert resumed_again.remaining_slot_kinds == ["daily"] * 4 + ["end"]
    assert digests_of(
        resumed_again.transparency_plan,
        resumed_again.authorization,
        start,
    ) == original_authority
    assert overwrite_or_delete_authority(resumed_again).status == "fail"


@pytest.mark.parametrize(
    "kill_after",
    [
        "authorization_persisted",
        "workstream_intent_persisted",
        "dispatch_start_persisted",
        "workflow_dispatched",
        "rekor_confirmation_observed",
        "start_anchor_downloaded",
        "bindings_temp_fsynced",
        "plan_temp_fsynced",
        "issues_temp_fsynced",
        "window_state_committed",
        "install_receipt_committed",
    ],
)
def test_start_bootstrap_kill_recovery_never_redispatches_or_strands_window(kill_after, window_fixture) -> None:
    killed = dispatch_with_kill_injection(window_fixture, slot_kind="start", kill_after=kill_after)
    resumed = resume_window_from_disk(killed.root, empty_process_environment())
    assert resumed.status in {"authorized_no_start", "active"}
    assert resumed.remote_dispatch_count <= 1
    assert resumed.transparency_plan_sha256 == killed.transparency_plan_sha256
    assert resumed.authorization_sha256 == killed.authorization_sha256
    assert resumed.slot_id == killed.slot_id
    if killed.public_write_may_have_occurred:
        assert resumed.used_nonce_recovery is True
        assert resumed.remote_dispatch_count == 1


@pytest.mark.parametrize("slot_kind", ["daily", "end"])
@pytest.mark.parametrize(
    "kill_after",
    ["dispatch_start_persisted", "workflow_dispatched", "rekor_confirmation_observed", "anchor_downloaded"],
)
def test_cross_day_anchor_kill_recovery_uses_same_nonce_and_never_redispatches(
    active_window,
    slot_kind,
    kill_after,
) -> None:
    killed = dispatch_with_kill_injection(active_window, slot_kind=slot_kind, kill_after=kill_after)
    resumed = resume_window_from_disk(killed.root, empty_process_environment())
    assert resumed.slot_id == killed.slot_id
    assert resumed.request_nonce == killed.request_nonce
    assert resumed.remote_dispatch_count == 1
    assert resumed.used_nonce_recovery is (kill_after != "dispatch_start_persisted")
    assert resumed.retry_of_slot_id is None
    assert resumed.transparency_plan_sha256 == killed.transparency_plan_sha256
    assert resumed.authorization_sha256 == killed.authorization_sha256


def test_anchor_request_and_output_paths_are_derived_only_from_authorized_slot(
    authorized_window,
) -> None:
    slot = authorized_window.transparency_plan.slots[2]
    paths = derive_anchor_paths(authorized_window, slot_id=slot.slot_id)
    assert paths.request.name == f"dogfood-anchor-{slot.slot_id}-request.json"
    assert paths.anchor.name == f"slot-{slot.slot_id}.json"
    assert paths.label_input_accepted is False


@pytest.mark.parametrize("existing", ["request", "anchor", "dispatch_start", "tombstone"])
def test_anchor_dispatch_is_create_new_and_never_deletes_existing_authority(
    active_window, existing
) -> None:
    slot = next_unused_slot(active_window, kind="daily")
    before = persist_existing_authority(active_window, slot, existing)
    result = dispatch_slot(active_window, "daily", ordinal=slot.ordinal)
    assert result.status == "fail"
    assert result.remote_dispatch_count == 0
    assert read_bytes(before.path) == before.bytes
~~~

dogfood/policy.json is tracked before freeze and contains only stable thresholds: exactly two workstreams, required operations, 20 sessions per workstream, every required operation represented in each workstream, at least 20 indexed first-party files and a nonzero query result for result-bearing operations, five independently anchored active days, 168 elapsed hours, and accepted fallback reasons. It contains no future subject, artifact, workstream UUID, repository commitment, or anchor digest. Before the irreversible start dispatch, `prepare-window` takes two distinct real repository roots, resolves each canonical path for routing, captures each normalized repository identity, and atomically persists them in the private pending workstream intent. After the start anchor is verified, `activate-window` consumes that intent and creates two fresh opaque UUIDv4 workstream IDs. Repository identity is `{normalized_origin, initial_commit, initial_tree}`; credentials/query strings are stripped from the canonical remote. For a repository with no remote, the conservative fallback is `{normalized_origin:null, initial_commit, initial_tree}`, so two clones with the same history collide rather than falsely count twice. The tool generates a random 32-byte per-window HMAC key and atomically writes a schema-valid private bindings document to `release/evidence/dogfood-workstream-bindings.json` containing the key, private roots, normalized identities, and route bindings. The pending intent, bindings, and window state all reject symlinks on POSIX and reparse points on Windows. On POSIX they are created/revalidated at mode 0600; on Windows the temporary file receives a protected security descriptor at creation time before any private byte is written, its owner SID must equal the current process-user SID, inheritance is disabled, its DACL grants that same SID only, and every inherited or unexpected allow ACE is rejected. Owner SID and DACL are revalidated before every read in `prepare-window`, `activate-window`, `resume-window`, `run`, `record`, and `validate-workstreams`. Creation fails closed if either platform cannot prove those protections. The plan stores only `HMAC-SHA256(key, "codesextant-dogfood-workstream-identity-v1\\0" || JCS(repository_identity))` for each workstream plus the private-bindings file SHA-256, ReleaseSubject SHA-256, one artifact SHA-256, policy SHA-256, and verified start-anchor digest. The two identity commitments must differ; two paths/clones of the same repository therefore fail. Neither secret, root, normalized identity, UUID, nor commitment enters public assets. Planned end is computed from the start anchor's Rekor `integratedTime` plus 168 hours; local time is not an authority.

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_dogfood_evidence.py tests/release/test_dogfood_anchor.py tests/release/test_g6_fresh_shell.py tests/release/test_g6_runbook_bootstrap.py -q
~~~

Expected: FAIL because tools.dogfood, tools.dogfood_anchor, and the policy/plan schemas do not exist.

**Step 3: Implement append-only event validation**

~~~python
class Outcome(str, Enum):
    SUCCESS = "success"
    FALLBACK = "fallback"
    FAILURE = "failure"


class FallbackReason(str, Enum):
    PRODUCT_DEFECT = "product_defect"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    USER_CHOICE = "user_choice"
    EXTERNAL_OUTAGE = "external_outage"


@dataclass(frozen=True)
class DogfoodEvent:
    event_id: UUID
    occurred_at_utc: datetime
    workstream_id: UUID
    repository_commitment: str
    subject_sha256: str
    artifact_sha256: str
    operation: str
    session_id: UUID
    execution_receipt_sha256: str
    binary_sha256: str
    command_argv_sha256: str
    exit_code: int
    response_sha256: str
    response_schema_sha256: str
    response_schema_valid: bool
    indexed_file_count: int
    query_result_count: int
    duration_monotonic_ms: int
    outcome: Outcome
    fallback_reason: FallbackReason | None
    issue_id: UUID | None
    previous_receipt_sha256: str
    receipt_sha256: str


def genesis_chain_head(subject_sha256: str) -> str:
    payload = f"codesextant-dogfood-genesis-v1:{subject_sha256}".encode("ascii")
    return hashlib.sha256(payload).hexdigest()
~~~

`dogfood/schema.json`, `dogfood/execution.schema.json`, and `dogfood/time-anchor.schema.json` are the tracked authoritative contracts for append-only events, real execution receipts, and verified signed/Rekor anchor receipts. The tools use fixed repository-relative constants for those paths; callers cannot substitute a weaker schema. `schema-check` proves those constants resolve to the exact tracked schemas, tests reject unknown properties and schema drift, `run` validates execution output, `record` validates both execution and event bytes before appending, `dogfood_anchor.py dispatch/recover/verify` validates every downloaded anchor before returning it, and `resume-window`/`summarize` revalidate all three domains from raw evidence rather than receipt assertions.

`release/Initialize-CodeSextantG6.ps1` defines the idempotent `Initialize-G6Context`, but no shell dot-sources working-tree bytes first. A dependency-free inline Windows prelude uses only built-in PowerShell, Git by absolute pinned path, and WinVerifyTrust: it verifies the initializer's Authenticode signature/revocation and leaf DER SHA-256 against the pre-F1 committed `release/g8-authenticode-signing-policy.json` value compiled as a literal into the signed initializer; parses the fixed ReleaseSubject with a closed minimal field check; requires HEAD equals subject source_commit; recomputes the subject source-tree closure; requires clean index/worktree, no nonignored untracked file, no reparse component; and checks committed/raw-byte digests for the initializer, release-Python bootstrap/lock, `release_gate.py`, and every tool the initializer may execute. It then materializes those exact committed blobs into a new digest-addressed, read-only, no-reparse export, re-hashes the closure, and dot-sources only that verified export. Tampered initializer/tool, a same-relative-path decoy, PATH shadow, dirty/untracked closure, or subject/HEAD/tree mismatch exits with zero project-code execution.

`tools/render_g6_runbook.py` deterministically renders `release/Run-CodeSextantG6.ps1` from the concrete pre-F1 Authenticode policy, after which the policy-authorized code-signing certificate signs the tracked file before commit. The runbook contains the full dependency-free P/Invoke implementation of `Assert-AuthenticodeWinTrustWholeChain` before its first call: all WinTrust/Crypt32 structs and constants are literal source, it uses whole-chain revocation and `CryptQueryObject`/signed-message countersigner parsing to require one trusted RFC3161 timestamp, extracts the primary leaf DER, constant-time compares the embedded 64-hex policy digest, and always closes provider state. It imports/dot-sources/downloads no helper and contains no placeholder.

Because AllSigned alone accepts any TrustedPublisher, the trust set is exactly five release assets, not four. `release/g6-runbook-launcher.rs` builds `codesextant-g6-runbook-launcher.exe` with unique role `g6_runbook_launcher`; F4 signs/indexes it and F5 installs it at `%ProgramData%\CodeSextant\Trust\G6\codesextant-g6-runbook-launcher.exe` under TrustedInstaller/protected SYSTEM+Administrators FullControl and ordinary-user RX. The machine-signed G6 authority binds its file ID/hash and embedded policy pin. This protected native launcher is the first project code: it WinVerifyTrusts the tracked runbook with whole-chain revocation/timestamp and exact compiled leaf DER pin, verifies path/file ID/no-reparse, and only then creates `pwsh`. Wrong-but-trusted signer therefore yields zero runbook execution. The tracked runbook itself remains source/subject material rather than a sixth asset.

Only after that bootstrap does `Initialize-G6Context` enable all UTF-8 channels, require `pwsh >= 7.4`, enter fail-fast mode, bootstrap the hashed release Python from the verified export, and construct an immutable context containing authenticated product_source/public_export/evidence/release_assets authorities plus `SubjectPath`; it never treats CWD or inherited variables as authority. Every R1-R4/cross-day shell repeats the dependency-free prelude and context construction before any authority command. The initializer creates, deletes, or repairs no dogfood state. The distinct R2 clean runner never uses this machine-specific initializer: it uses only the create-new portable runner bundle, validates the bundled subject, and independently bootstraps that bundle's locked Python. Tests start real `pwsh -NoProfile` processes for both routes and prove the local route has zero project execution before complete subject/HEAD/tree/closure/tool authentication while the clean-runner route works from an arbitrary non-Git directory; neither route uses ambient Python. Before G5 Final Freeze, the initializer, its Authenticode policy/literal, portable bundle producer/schema, and blank-shell/resume tests are mandatory signed-scope materials; changing any invalidates the G5 review.

`tools/dogfood.py run` is the only event source. It requires the schema-valid private bindings file and actual repository root, re-normalizes repository identity, verifies the private route binding, recomputes the identity HMAC, and rejects unless it equals that workstream's unique plan commitment. It launches the installed CodeSextant binary whose SHA-256 is named by the frozen artifact, derives argv from the operation registry, observes UTC start/end plus monotonic duration, captures exit code, validates the response against the operation response schema, derives nontrivial indexed-file/query-result counts from the response, hashes the redacted argv/stdout/stderr/response/schema, and writes an immutable `dogfood/execution.schema.json` receipt containing only the opaque workstream ID/commitment. It never accepts a caller-supplied outcome or count. `record --execution-receipt ...` revalidates those bytes, commitment, counts, and plan; derives `SUCCESS` only from exit zero plus a schema-valid nonvacuous response; rejects reuse of an execution receipt/session ID; then appends an event under an interprocess lock plus fsync. A failed execution or product-defect fallback requires an existing linked issue created by `issue-record`; raw stdin outcomes and hand-authored events are rejected.

receipt_sha256 is SHA-256 over canonical event JSON without that field and includes previous_receipt_sha256, forming one append-only chain. `tools/dogfood.py genesis-head --subject ...` is the sole CLI projection of `genesis_chain_head(subject_sha256)`; a literal sentinel such as `genesis` is invalid. The event contains only privacy-safe hashes, opaque commitment, counts, and normalized operation identity—never source, prompt, raw output, repository path/identity, or secret. For daily/end anchors, `anchor-request --events ...` validates the complete JSONL and derives event count and chain head itself rather than trusting caller-supplied duplicates.

`issue-init`, `issue-record`, and `issue-resolve` are the only writers of the schema-valid private issue ledger. Every issue mutation is subject/plan-bound, append-audited, and links the triggering execution digest. `issue-record` requires severity, class, and privacy-safe code; `issue-resolve` retains history and resolution evidence rather than deleting a row.

dogfood-anchor.yml is `workflow_dispatch` only; a scheduled cloud job cannot read the private local event chain and is therefore forbidden. Its permissions are exactly `contents: read` and `id-token: write`, it consumes no repository secret, and every third-party action is pinned by full commit SHA. Its required inputs are mode `start|daily|end`, subject SHA-256, event count, chain-head SHA-256, and a random request nonce. It writes canonical JSON, uses GitHub OIDC plus the pinned cosign tool to sign the blob and submit it to Sigstore Rekor, and uploads statement plus bundle as an Actions artifact named by the nonce. `release/dogfood-signing-policy.json` is a distinct pre-freeze trust root with an exact, non-wildcard certificate identity for `.github/workflows/dogfood-anchor.yml`, exact `Zeroxrain99/CodeSextant`, exact OIDC issuer, and schema; it can never reuse the artifact-smoke certificate identity. Tests prove dogfood policy accepts only dogfood-anchor bundles and rejects artifact-smoke bundles, while `release/signing-policy.json` does the inverse.

Before the first dispatch, `tools/dogfood_anchor.py transparency-plan` creates one schema-valid subject-bound plan with exact repository `Zeroxrain99/CodeSextant`, exact workflow ref/commit, exact dogfood-signing-policy digest/certificate identity/OIDC issuer, and exactly seven UUIDv4 one-shot slots in canonical order: one `start`, five `daily`, and one `end`. Its closed `public_transparency_log_disclosure` enumerates the statement/certificate/hash metadata that each slot may publish and states that Sigstore/Rekor is public, append-only, independently discoverable, and irreversible; secrets, paths, repository identities, HMAC commitments, prompts, raw results, and user email are forbidden. `show-authorization-request` displays that entire plan and disclosure. Only a subsequent `record-authorization --acknowledge-public-transparency-log`, explicitly confirmed by the user, may create the separate schema-valid authorization; it binds the exact plan/subject/workflow/dogfood-signing-policy/slot digests, expires no later than ten days after issue, and cannot be inferred from G5 or G7 authorization.

`tools/dogfood_anchor.py dispatch` requires the authorized plan, authorization, and one exact unused slot ID in addition to the derived anchor request. Request and anchor paths are derived solely from that authorized slot ID as `dogfood-anchor-{slot_id}-request.json` and `slot-{slot_id}.json`; a supplied output path must equal that derivation, and no caller label or alternative alias is accepted. Request, dispatch-start, tombstone, and anchor writes are create-new. Any existing member is preserved byte-for-byte and fails before network access; deletion/overwrite is not a recovery mechanism. Before any network call the tool atomically writes an `anchor-dispatch-start` binding the slot, request nonce/hash, subject, plan, and authorization. A confirmed success consumes that slot, locates the run by nonce, downloads the artifact, and verifies certificate identity, workflow path, `workflow_repository == Zeroxrain99/CodeSextant`, `workflow_commit == ReleaseSubject.export_commit`, Rekor inclusion proof/integratedTime, subject digest, event count, chain head, mode, nonce, and slot. An ambiguous network/workflow outcome atomically writes a matching dispatch tombstone, permanently consumes the slot, and forbids automatic retry; continuing requires a freshly displayed and explicitly authorized replacement plan. A clear pre-network validation failure writes no start and leaves the slot unused. Reset/compensation receipts must state that any already-authorized Rekor records remain public. The private `source_commit` is bound only through the signed request's ReleaseSubject digest; the rewritten staging repository can never expose it as the workflow commit. Exactly five daily anchors must bind monotonically increasing observed heads; this prevents local clock changes or a rewritten/backfilled JSONL from manufacturing active days.

**Step 4: Run GREEN**

~~~powershell
$releasePython = & C:\Python311\python.exe tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python
if ($LASTEXITCODE -ne 0) { throw 'locked release Python bootstrap failed' }
& $releasePython tools/render_g6_runbook.py render --authenticode-policy release/g8-authenticode-signing-policy.json --out release/Run-CodeSextantG6.ps1
if ($LASTEXITCODE -ne 0) { throw 'deterministic G6 runbook render failed' }
$authPolicy = Get-Content -Raw -Encoding UTF8 -LiteralPath release/g8-authenticode-signing-policy.json | ConvertFrom-Json
$codeSigningCert = Get-Item -LiteralPath ("Cert:\LocalMachine\My\" + $authPolicy.certificate_thumbprint)
if (-not $codeSigningCert.HasPrivateKey) { throw 'policy-authorized Authenticode signing certificate/private key is unavailable on the release signer' }
$signedRunbook = Set-AuthenticodeSignature -LiteralPath release/Run-CodeSextantG6.ps1 -Certificate $codeSigningCert -HashAlgorithm SHA256 -TimestampServer $authPolicy.rfc3161_timestamp_url -IncludeChain All
if ($signedRunbook.Status -ne 'Valid') { throw 'rendered G6 runbook Authenticode signing failed' }
$winTrust = Get-AuthenticodeSignature -LiteralPath release/Run-CodeSextantG6.ps1
if ($winTrust.Status -ne 'Valid') { throw 'Windows WinVerifyTrust rejected the signed G6 runbook' }
$leafSha256 = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($winTrust.SignerCertificate.RawData)).ToLowerInvariant()
if ($leafSha256 -ne [string]$authPolicy.leaf_cert_der_sha256) { throw 'signed G6 runbook leaf certificate differs from the frozen Authenticode policy' }
& $releasePython tools/render_g6_runbook.py verify-body --authenticode-policy release/g8-authenticode-signing-policy.json --runbook release/Run-CodeSextantG6.ps1 --require-function-before-first-call Assert-AuthenticodeWinTrustWholeChain --require-symbol WinVerifyTrust --require-symbol CryptQueryObject --require-rfc3161 --reject-placeholder
if ($LASTEXITCODE -ne 0) { throw 'signed G6 runbook body is not the deterministic dependency-free WinTrust implementation' }
& $releasePython -m pytest tests/release/test_dogfood_evidence.py tests/release/test_dogfood_anchor.py tests/release/test_g6_fresh_shell.py tests/release/test_g6_runbook_bootstrap.py -q
if ($LASTEXITCODE -ne 0) { throw 'dogfood and G6 runbook bootstrap tests failed' }
& $releasePython tools/dogfood.py validate-policy --policy dogfood/policy.json
~~~

Expected: tests and policy validation pass; summary remains unverifiable before elapsed time and sessions mature.

**Step 5: Commit**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('dogfood/schema.json','dogfood/execution.schema.json','dogfood/plan.schema.json','dogfood/workstream-bindings.schema.json','dogfood/workstream-intent.schema.json','dogfood/window-state.schema.json','dogfood/policy.json','dogfood/privacy.md','dogfood/issues.schema.json','dogfood/time-anchor.schema.json','dogfood/transparency-plan.schema.json','dogfood/transparency-authorization.schema.json','dogfood/anchor-dispatch-start.schema.json','dogfood/anchor-dispatch-tombstone.schema.json','release/dogfood-signing-policy.schema.json','release/dogfood-signing-policy.json','release/Initialize-CodeSextantG6.ps1','release/Run-CodeSextantG6.ps1','release/security-review-scope.json','.github/workflows/dogfood-anchor.yml','tools/dogfood.py','tools/dogfood_anchor.py','tools/render_g6_runbook.py','tests/release/test_dogfood_evidence.py','tests/release/test_dogfood_anchor.py','tests/release/test_g6_fresh_shell.py','tests/release/test_g6_runbook_bootstrap.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'test: add privacy-safe release-candidate dogfood'
~~~

### Task 4: Enforce the non-shortenable seven-day acceptance window

**Files:**

- Modify: tools/dogfood.py
- Modify: tests/release/test_dogfood_evidence.py
- Create: release/evidence/dogfood-summary.schema.json
- Create: release/evidence/issues.schema.json
- Create: docs/dogfood/report.schema.json

**Step 1: Write clock- and hash-adversarial RED tests**

~~~python
def test_167_hours_59_minutes_of_verified_anchors_is_unverifiable(
    complete_events, start_anchor, end_anchor
) -> None:
    end_anchor["rekor"]["integrated_time"] = (
        start_anchor["rekor"]["integrated_time"] + 167 * 3600 + 59 * 60
    )
    assert summarize(complete_events, ISSUES, anchors=ANCHORS).status == "unverifiable"


def test_artifact_hash_change_resets_window(complete_events) -> None:
    complete_events[-1]["artifact_sha256"] = "f" * 64
    result = summarize(complete_events, ISSUES, anchors=ANCHORS)
    assert result.status == "fail"
    assert "ARTIFACT_CHANGED" in result.findings


def test_product_fallback_or_open_severity_blocks(complete_events) -> None:
    complete_events[-1]["outcome"] = "fallback"
    complete_events[-1]["fallback_reason"] = "product_defect"
    assert summarize(complete_events, ISSUES, anchors=ANCHORS).status == "fail"


def test_g6_public_asset_manifest_is_deterministic_subject_bound_and_private_safe(
    public_safe_receipts, privacy_audited_report, subject
) -> None:
    first = emit_public_assets(subject, privacy_audited_report, public_safe_receipts)
    second = emit_public_assets(subject, privacy_audited_report, public_safe_receipts)
    assert first.canonical_bytes == second.canonical_bytes
    assert first.subject_sha256 == subject.sha256
    assert {asset.destination_filename for asset in first.assets} == {
        "dogfood-report.md", "first-user.json", "dogfood-summary.json", "issues.json"
    }
    assert all(len(asset.sha256) == 64 and asset.size_bytes > 0 for asset in first.assets)
    assert not first.contains_raw_events_or_issue_text


def test_public_issue_receipt_is_aggregate_only(private_issue_ledger, subject) -> None:
    receipt = emit_issue_receipt(subject, private_issue_ledger)
    assert receipt.subject_sha256 == subject.sha256
    assert set(receipt.payload) == {"counts_by_severity", "counts_by_code", "counts_by_status", "open_p0", "open_p1"}
    assert not receipt.contains_issue_ids_workstream_ids_or_text


def test_public_dogfood_summary_contains_no_private_workstream_identity(
    private_summary, private_plan, private_bindings
) -> None:
    public_receipt = emit_public_dogfood_summary(private_summary)
    raw = canonical_json(public_receipt)
    for workstream in private_plan["workstreams"]:
        assert workstream["id"].encode() not in raw
        assert workstream["repository_commitment"].encode() not in raw
    assert private_bindings["key_sha256"].encode() not in raw
~~~

Tests also enforce two distinct opaque workstream IDs bound to two distinct real-repository HMAC commitments, every required operation at least once per workstream, nontrivial indexed-file/result counts, at least five independently anchored UTC dates, at least 20 unique `Outcome.SUCCESS` session IDs for each, known operations only, no duplicated event or execution-receipt IDs, a complete receipt chain, start/end plus at least five daily Rekor anchors, zero open P0/P1, zero `FAILURE`, and zero product_defect fallback. A failure or product-defect fallback fails the current subject/window; a product fix changes the artifact and therefore restarts G5 freeze plus the full G6 clock.

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_dogfood_evidence.py tests/release/test_dogfood_anchor.py tests/release/test_g6_fresh_shell.py -q
~~~

Expected: FAIL because summarize and the evidence schemas do not enforce the complete window.

**Step 3: Implement the summarizer**

~~~python
@dataclass(frozen=True)
class DogfoodSummary:
    status: Literal["pass", "fail", "unverifiable"]
    subject_sha256: str
    artifact_sha256: str
    start_utc: datetime
    evaluated_at_utc: datetime
    elapsed_hours: Decimal
    active_days: int
    workstream_count: Literal[2]
    sessions_per_workstream_sorted: tuple[int, int]
    min_sessions_per_workstream: int
    required_operation_success_counts_sorted: Mapping[str, tuple[int, int]]
    product_defect_fallbacks: int
    open_p0: int
    open_p1: int
    event_chain_sha256: str
    start_anchor_sha256: str
    end_anchor_sha256: str
    verified_anchor_count: int
    findings: tuple[str, ...]


def summarize(
    events: Sequence[DogfoodEvent],
    issues: Sequence[Issue],
    *,
    anchors: Sequence[VerifiedAnchor],
) -> DogfoodSummary:
    """Use verified anchor time/heads; fail closed on mixed artifacts, rewritten chains, or issues."""
~~~

The public report generator emits aggregate counts, version, commit, artifact hash, date range, operation/count thresholds, and known limitations. It omits workstream IDs, repository paths/identities, commitments, HMAC-key digest, and raw events. `dogfood/issues.schema.json` remains the private mutable ledger contract. The separate `release/evidence/issues.schema.json` is the canonical gate payload and permits only subject-bound aggregate counts by severity/code/status plus open-P0/P1 totals—no issue IDs, workstream IDs, timestamps, or text. `issue-receipt` is the sole converter. `emit-public-assets` accepts one exact report path, rejects raw event/private-ledger/key/plan paths and unrecognized receipt schemas, and deterministically writes `release/assets/g6-public-assets.json`. The manifest binds the privacy-audited report plus public-safe `first-user.json`, `dogfood-summary.json`, and `issues.json` evidence to the same ReleaseSubject with exact role, destination filename, byte size, SHA-256, and privacy-audit result; it performs no network request.

**Step 4: Run GREEN**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_dogfood_evidence.py tests/release/test_dogfood_anchor.py tests/release/test_g6_fresh_shell.py -q
C:\Python311\python.exe tools/dogfood.py schema-check --policy dogfood/policy.json --event-schema dogfood/schema.json --execution-schema dogfood/execution.schema.json --anchor-schema dogfood/time-anchor.schema.json --plan-schema dogfood/plan.schema.json --workstream-intent-schema dogfood/workstream-intent.schema.json --workstream-bindings-schema dogfood/workstream-bindings.schema.json --window-state-schema dogfood/window-state.schema.json --private-issues-schema dogfood/issues.schema.json --issue-receipt-schema release/evidence/issues.schema.json --summary-schema release/evidence/dogfood-summary.schema.json --transparency-plan-schema dogfood/transparency-plan.schema.json --transparency-authorization-schema dogfood/transparency-authorization.schema.json --anchor-dispatch-start-schema dogfood/anchor-dispatch-start.schema.json --anchor-dispatch-tombstone-schema dogfood/anchor-dispatch-tombstone.schema.json
C:\Python311\python.exe tools/generate_producer_launch_policy.py sync --through-phase G6_FINAL --registry release/evidence/receipt-registry.json --out release/evidence/producer-launch-policy.json
C:\Python311\python.exe tools/generate_producer_launch_policy.py check --through-phase G6_FINAL --registry release/evidence/receipt-registry.json --policy release/evidence/producer-launch-policy.json --schema release/evidence/producer-launch-policy.schema.json
~~~

Expected: tests and schema checks pass. No live summary or asset manifest is generated before ReleaseSubject freezes; the external runbook creates private receipts under `release/evidence` and stages redacted ancillary evidence under ignored `release/assets`.

**Step 5: Commit the verifier before starting the clock**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve repository root' }
Set-Location -LiteralPath $repoRoot
. (Join-Path $repoRoot 'tools\exact_task_commit.ps1')
C:\Python311\python.exe -m pytest (Join-Path $repoRoot 'tests\release\test_exact_task_commit.py') -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed' }
$expectedStaged = @('tools/dogfood.py','tests/release/test_dogfood_evidence.py','release/evidence/dogfood-summary.schema.json','release/evidence/issues.schema.json','release/evidence/producer-launch-policy.json','docs/dogfood/report.schema.json')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'test: enforce seven-day two-workstream acceptance'
~~~

Never commit a live dogfood summary or report after ReleaseSubject freezes. If the artifact changes, discard its anchors/events, freeze a new subject, and begin again.

## G6 External Evidence Runbook

This section runs only after every implementation task above is committed and the G5 Final Freeze runbook has produced ReleaseSubject plus green G0-G5 receipts. It is an operational evidence phase, not an implementation task.

Run every local authority portion of R1-R4 in `pwsh` 7.4 or newer and execute this fail-fast prelude after every fresh local shell. F5 has already created the fixed TrustedInstaller-owned, machine-signed `%ProgramData%\CodeSextant\Trust\G6\g6-release-authority.json`; it binds the one current ReleaseSubject hash, release tag, signed-index hash, public repository ID, machine key_id, and monotonic generation, preventing an internally valid older release from being selected. Reading its release_tag before signature verification is only a download hint: the signed native preflight must verify the anchor signature/current generation and exact subject/index before accepting anything.

`Assert-AuthenticodeWinTrustWholeChain` is included verbatim in the runbook as a dependency-free P/Invoke wrapper around `WinVerifyTrust`: `WTD_CHOICE_FILE`, whole-chain revocation, trusted RFC3161 timestamp, `WTD_STATEACTION_VERIFY`, provider-state leaf extraction, constant-time DER SHA-256 comparison, then `WTD_STATEACTION_CLOSE` in `finally`. Its expected leaf is not a mutable file or placeholder; it is derived from the unique administrator-installed LocalMachine TrustedPublisher certificate carrying the private CodeSextant policy OID, whose exact DER digest is also committed in `g8-authenticode-signing-policy.json` and rechecked by the signed native preflight. The prelude downloads all release assets only after obtaining the fixed anchor hint, WinVerifyTrust-authenticates the native preflight before execution, and then uses its verified content-addressed export. R2's clean signer remains the sole exception and uses only its closed bundle. Registered receipts are immutable create-new; existing receipts are fully reverified and byte-compared, never deleted/re-emitted. Only replaceable reports/ephemeral internal candidate handles may be discarded.

~~~powershell
$g6Root = 'E:\ai-king\項目資料\CodeSextant'
$runbook = Join-Path $g6Root 'release\Run-CodeSextantG6.ps1'
$g6Launcher = Join-Path $env:ProgramData 'CodeSextant\Trust\G6\codesextant-g6-runbook-launcher.exe'
if (-not (Test-Path -LiteralPath $g6Launcher -PathType Leaf)) { throw 'fixed protected G6 runbook launcher is missing' }
$g6Json = & $g6Launcher run-fixed --runbook $runbook --action initialize-verified-context --expected-root $g6Root --require-subject --format json
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$g6Json)) { throw 'pinned native launcher rejected G6 runbook/context' }
$g6 = $g6Json | ConvertFrom-Json
$releasePython = $g6.ReleasePython
$subject = $g6.SubjectPath
$g6AuthorityPath = $g6.ReleaseAuthorityPath
& $releasePython $g6.ReleaseGatePath subject-check --subject $subject
if ($LASTEXITCODE -ne 0) { throw 'initializer-derived ReleaseSubject failed validation' }
$g6GateContext = @('--subject',$subject,'--product-source-root',$g6.ProductSourceRoot,'--public-export-root',$g6.PublicExportRoot,'--evidence-dir',$g6.EvidenceDir,'--release-assets-root',$g6.ReleaseAssetsRoot,'--release-index',$g6.ReleaseIndex,'--release-index-bundle',$g6.ReleaseIndexBundle,'--signing-policy',$g6.SigningPolicy,'--verifier-bootstrap',$g6.VerifierBootstrap,'--registry',$g6.ReceiptRegistry,'--launch-policy',$g6.ProducerLaunchPolicy)
~~~

Generated private evidence:

- release/evidence/first-user-runner-bundle/
- release/evidence/first-user-run.json
- release/evidence/first-user.json
- release/evidence/g8-seed-install.json
- release/evidence/dogfood-plan.json
- release/evidence/dogfood-transparency-plan.json
- release/evidence/dogfood-transparency-authorization.json
- release/evidence/dogfood-anchor-dispatch/
- release/evidence/dogfood-events.jsonl
- release/evidence/dogfood-anchors/
- release/evidence/dogfood-summary.json
- release/evidence/dogfood-issues.json
- release/evidence/issues.json
- release/assets/dogfood-{artifact_sha256[0:12]}-report.md
- release/assets/g6-public-assets.json

### R1: Verify subject and upstream gates

~~~powershell
foreach ($gate in 'G0','G1','G2','G3','G4','G5') {
  & $releasePython $g6.ReleaseGatePath check --gate $gate @g6GateContext
  if ($LASTEXITCODE -ne 0) { throw "upstream registry gate $gate failed" }
}
& $releasePython tools/dogfood.py validate-policy --policy dogfood/policy.json
~~~

Expected: all exit 0. No subject-bound dogfood plan exists yet; it is created only after the verified start anchor in R3.

### R2: Run independent first-user verification

Use a distinct runner identity on a clean machine/profile. R2 is deliberately split into three processes so the machine-specific product initializer never leaks into the clean runner.

First, in a fresh local authority shell after the exact-root prelude, download and verify the draft assets and create one portable, content-closed bundle for the runner's explicit target. The destination must not exist; this producer never repairs or overwrites a prior bundle:

~~~powershell
$staging = Get-Content -Raw -Encoding UTF8 -LiteralPath release/staging.json | ConvertFrom-Json
$firstUserAssets = Join-Path $env:TEMP ("codesextant-first-user-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $firstUserAssets | Out-Null
gh release download $staging.release_tag --repo Zeroxrain99/CodeSextant --dir $firstUserAssets
$firstUserManifest = Join-Path $firstUserAssets 'artifact-manifest.json'
$runnerTarget = $env:CODESEXTANT_FIRST_USER_TARGET
if ([string]::IsNullOrWhiteSpace($runnerTarget)) { throw 'explicit first-user target triple is required' }
$runnerBundleRoot = 'release/evidence/first-user-runner-bundle'
if (Test-Path -LiteralPath $runnerBundleRoot) { throw 'portable runner bundle destination must be create-new' }
& $releasePython tools/verify_first_user.py prepare-runner-bundle --subject $subject --scenario release/first-user-scenario.json --manifest $firstUserManifest --asset-root $firstUserAssets --runner-roles release/first-user-runner-roles.json --implementation-actors provenance/implementation-actors.json --operations spec/operations.yaml --release-python-lock requirements/release.lock --target $runnerTarget --out $runnerBundleRoot
if ($LASTEXITCODE -ne 0) { throw 'portable first-user runner bundle preparation failed' }
$runnerBundleManifest = Join-Path $runnerBundleRoot 'first-user-runner-bundle.json'
& $releasePython tools/verify_first_user.py verify-runner-bundle --subject $subject --bundle-root $runnerBundleRoot --bundle-manifest $runnerBundleManifest --bundle-schema release/first-user-runner-bundle.schema.json
if ($LASTEXITCODE -ne 0) { throw 'portable first-user runner bundle self-verification failed' }
~~~

Transfer exactly that directory to the distinct clean machine/profile. In a new `pwsh -NoProfile` there, set `$portableBundleRoot` to its arbitrary absolute location. It must not be inside a Git worktree and must contain no source package. Provision the 32-byte Ed25519 private seed out of band only into the OS credential entry `codesextant/g6/first-user`, not an environment variable, argv, stdin, or file in the bundle. `CODESEXTANT_BOOTSTRAP_PYTHON` is used exactly once to create the digest-addressed environment while the signing-key environment variable is provably absent; pip and every bootstrap child inherit that absence. Only after bootstrap succeeds does the reviewed role launcher read the OS credential inside a fresh runner child and inject the named variable into that child alone:

~~~powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$portableBundleRoot = [IO.Path]::GetFullPath($portableBundleRoot)
Set-Location -LiteralPath $portableBundleRoot
if (Test-Path -LiteralPath (Join-Path $portableBundleRoot '.git')) { throw 'clean runner bundle must not be a Git checkout' }
$signingKeyEnv = 'CODESEXTANT_FIRST_USER_SIGNING_KEY'
if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($signingKeyEnv, 'Process'))) { throw 'first-user signing key must be absent before locked bootstrap' }
$bootstrapPython = [Environment]::GetEnvironmentVariable('CODESEXTANT_BOOTSTRAP_PYTHON','Process')
if ([string]::IsNullOrWhiteSpace($bootstrapPython) -or -not [IO.Path]::IsPathRooted($bootstrapPython)) { throw 'one absolute bootstrap Python is required on the clean runner' }
$runnerPython = & $bootstrapPython tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$runnerPython) -or -not (Test-Path -LiteralPath $runnerPython -PathType Leaf)) { throw 'clean runner locked Python bootstrap failed' }
[Environment]::SetEnvironmentVariable('CODESEXTANT_BOOTSTRAP_PYTHON',$null,'Process')
if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($signingKeyEnv, 'Process'))) { throw 'bootstrap leaked or injected the first-user signing key' }
$runnerId = $env:CODESEXTANT_FIRST_USER_RUNNER_ID
$parsedRunnerId = [Guid]::Empty
if (-not [Guid]::TryParseExact($runnerId, 'D', [ref]$parsedRunnerId)) { throw 'CODESEXTANT_FIRST_USER_RUNNER_ID must be the allowed canonical UUID in release/first-user-runner-roles.json' }
$runnerRoles = 'release/first-user-runner-roles.json'
$credentialName = 'codesextant/g6/first-user'
$signingEnvRegistryPath = 'release/signing-environment-registry.json'
$signingEnvRegistrySchema = 'release/signing-environment-registry.schema.json'
$signingEnvRegistry = Get-Content -Raw -Encoding UTF8 -LiteralPath $signingEnvRegistryPath | ConvertFrom-Json
$reservedSigningEnvPattern = '^CODESEXTANT_[A-Z0-9_]*SIGNING_KEY$'
if ([string]$signingEnvRegistry.reserved_pattern -cne $reservedSigningEnvPattern) { throw 'portable signing-environment registry has the wrong reserved pattern' }
$knownSigningKeyEnvs = @($signingEnvRegistry.roles | ForEach-Object { [string]$_.key_env } | Sort-Object -Unique)
if ($knownSigningKeyEnvs -notcontains $signingKeyEnv) { throw 'first-user signing environment is absent from the authenticated global registry' }
$forbiddenSigningKeyEnvs = @($knownSigningKeyEnvs | Where-Object { $_ -cne $signingKeyEnv })
$presentReservedSigningEnvs = @([Environment]::GetEnvironmentVariables('Process').Keys | ForEach-Object { [string]$_ } | Where-Object { $_ -cmatch $reservedSigningEnvPattern })
if ($presentReservedSigningEnvs.Count -ne 0) { throw "reserved signing-key environment must be empty before role launch: $($presentReservedSigningEnvs -join ',')" }
$runnerOutputRoot = Join-Path ([IO.Path]::GetTempPath()) ("codesextant-first-user-output-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $runnerOutputRoot | Out-Null
$portableReceipt = Join-Path $runnerOutputRoot 'first-user-run.json'
try {
    $roleArgs = @('run','--role','independent_first_user_runner','--credential-name',$credentialName,'--allowed-key-env',$signingKeyEnv,'--signing-env-registry',$signingEnvRegistryPath,'--signing-env-registry-schema',$signingEnvRegistrySchema,'--reserved-key-env-pattern',$reservedSigningEnvPattern)
    foreach ($name in $forbiddenSigningKeyEnvs) { $roleArgs += @('--forbidden-key-env',$name) }
    & $runnerPython tools/review_role_runner.py @roleArgs -- $runnerPython tools/run_first_user.py --bundle-root $portableBundleRoot --bundle-manifest first-user-runner-bundle.json --runner-roles $runnerRoles --runner-id $runnerId --release-python-lock requirements/release.lock --signing-key-env $signingKeyEnv --out $portableReceipt
    if ($LASTEXITCODE -ne 0) { throw 'signed first-user runner failed' }
} finally {
    $presentReservedSigningEnvs = @([Environment]::GetEnvironmentVariables('Process').Keys | ForEach-Object { [string]$_ } | Where-Object { $_ -cmatch $reservedSigningEnvPattern })
    if ($presentReservedSigningEnvs.Count -ne 0) { throw "role launcher leaked or introduced reserved signing-key environment: $($presentReservedSigningEnvs -join ',')" }
}
~~~

Return only the immutable signed `$portableReceipt` to the local authority machine. In a third fresh local shell, rerun the exact-root prelude, reverify the unchanged local bundle, require both registry outputs to be create-new, copy the returned signed bytes into the ignored evidence path, and invoke the keyless sole registry producer:

~~~powershell
if ((Test-Path -LiteralPath release/evidence/first-user-run.json) -or (Test-Path -LiteralPath release/evidence/first-user.json)) { throw 'first-user evidence already exists; verify or restart the subject, never overwrite it' }
$runnerBundleRoot = 'release/evidence/first-user-runner-bundle'
$runnerBundleManifest = Join-Path $runnerBundleRoot 'first-user-runner-bundle.json'
& $releasePython tools/verify_first_user.py verify-runner-bundle --subject $subject --bundle-root $runnerBundleRoot --bundle-manifest $runnerBundleManifest --bundle-schema release/first-user-runner-bundle.schema.json
if ($LASTEXITCODE -ne 0) { throw 'local runner bundle changed after transfer' }
Copy-Item -LiteralPath $returnedPortableReceipt -Destination release/evidence/first-user-run.json
& $releasePython $g6.ReleaseGatePath produce-and-seal --gate G6 --receipt first-user.json @g6GateContext -- --scenario release/first-user-scenario.json --runner-bundle-root $runnerBundleRoot --runner-bundle-manifest $runnerBundleManifest --runner-roles release/first-user-runner-roles.json --implementation-actors provenance/implementation-actors.json --release-python-lock requirements/release.lock --runner-receipt release/evidence/first-user-run.json
if ($LASTEXITCODE -ne 0) { throw 'first-user gate receipt verification failed' }
~~~

Expected: exit 0. The clean signer ran from an arbitrary non-Git directory, never loaded the exact-root initializer or source checkout, and made no ambient-Python call after the one locked bootstrap. The signing key was absent from the parent, bootstrap, and pip environments and became visible only inside the post-bootstrap `run_first_user.py` child launched from the OS credential. first-user-run.json is canonical and signature-valid for the allowed UUID/key_id/role; its signature binds the exact runner-bundle manifest, subject, scenario, artifact manifest, selected artifact, environment, steps, and uninstall proof. first-user.json preserves that verified key_id/signature and the bundle/signed-run/roles/actor-roster digests, and embeds the separately signed privacy-safe public statement so an independent reader can reconstruct and verify its Ed25519 bytes without the private runner receipt. The runner UUID is absent from the implementation actor roster, and the private seed is absent from the repository, argv, stdin, receipts, logs, release assets, parent/bootstrap/pip environments, and every product child environment.

### R3: Anchor start, create the private plan, anchor five active days, and anchor end

Every cross-day shell rehydrates state from fixed private files; no environment variable is an authority after initial workstream creation. Define this helper after the fail-fast prelude in each fresh shell. It validates schemas, subject/signing identity, authorization, owner-only binding protection, plan/HMAC routes, and one-shot dispatch state before placing roots into script-local variables:

~~~powershell
function Resume-G6Window {
  $script:subject = $g6.SubjectPath
  if ([string]::IsNullOrWhiteSpace([string]$subject) -or -not [IO.Path]::IsPathRooted($subject)) { throw 'G6 SubjectPath must be reconstructed by Initialize-G6Context' }
  $script:transparencyPlan = 'release/evidence/dogfood-transparency-plan.json'
  $script:transparencyAuthorization = 'release/evidence/dogfood-transparency-authorization.json'
  $script:dispatchStateDir = 'release/evidence/dogfood-anchor-dispatch'
  $script:anchorDir = 'release/evidence/dogfood-anchors'
  $script:workstreamIntent = 'release/evidence/dogfood-workstream-intent.json'
  $script:workstreamBindings = 'release/evidence/dogfood-workstream-bindings.json'
  $script:windowState = 'release/evidence/dogfood-window-state.json'
  foreach ($path in @($subject,$transparencyPlan,$transparencyAuthorization)) { if (-not (Test-Path -LiteralPath $path)) { throw "G6 authority input missing: $path" } }
  & $releasePython tools/release_gate.py subject-check --subject $subject
  $resumeJson = & $releasePython tools/dogfood.py resume-window --subject $subject --transparency-plan $transparencyPlan --transparency-authorization $transparencyAuthorization --signing-policy release/dogfood-signing-policy.json --dispatch-state $dispatchStateDir --anchors $anchorDir --workstream-intent $workstreamIntent --workstream-bindings $workstreamBindings --bindings-schema dogfood/workstream-bindings.schema.json --plan release/evidence/dogfood-plan.json --issues release/evidence/dogfood-issues.json --window-state $windowState --recover-existing-dispatch --json
  if ([string]::IsNullOrWhiteSpace([string]$resumeJson)) { throw 'G6 resume returned no phase record' }
  $script:g6Window = $resumeJson | ConvertFrom-Json
  if ($g6Window.phase -notin @('authorized_no_start','start_confirmed_no_workstream_plan','active','complete')) { throw "invalid or ambiguous G6 window phase: $($g6Window.phase)" }
  if ($g6Window.phase -eq 'start_confirmed_no_workstream_plan') {
    $startPlan = Get-Content -Raw -Encoding UTF8 -LiteralPath $transparencyPlan | ConvertFrom-Json
    $startSlot = @($startPlan.slots | Where-Object kind -eq 'start')
    if ($startSlot.Count -ne 1) { throw 'authorized plan must contain exactly one start slot' }
    $startAnchor = Join-Path $anchorDir "slot-$($startSlot[0].slot_id).json"
    & $releasePython tools/dogfood.py activate-window --subject $subject --policy dogfood/policy.json --transparency-plan $transparencyPlan --transparency-authorization $transparencyAuthorization --start-anchor $startAnchor --workstream-intent $workstreamIntent --workstream-bindings-out $workstreamBindings --plan-out release/evidence/dogfood-plan.json --issues-out release/evidence/dogfood-issues.json --window-state $windowState
    $resumeJson = & $releasePython tools/dogfood.py resume-window --subject $subject --transparency-plan $transparencyPlan --transparency-authorization $transparencyAuthorization --signing-policy release/dogfood-signing-policy.json --dispatch-state $dispatchStateDir --anchors $anchorDir --workstream-intent $workstreamIntent --workstream-bindings $workstreamBindings --bindings-schema dogfood/workstream-bindings.schema.json --plan release/evidence/dogfood-plan.json --issues release/evidence/dogfood-issues.json --window-state $windowState --recover-existing-dispatch --json
    if ([string]::IsNullOrWhiteSpace([string]$resumeJson)) { throw 'G6 post-activation resume returned no phase record' }
    $script:g6Window = $resumeJson | ConvertFrom-Json
    if ($g6Window.phase -ne 'active') { throw "G6 activation did not reach active phase: $($g6Window.phase)" }
  }
  $script:transparency = Get-Content -Raw -Encoding UTF8 -LiteralPath $transparencyPlan | ConvertFrom-Json
  if ($g6Window.phase -in @('active','complete')) {
    $bindings = Get-Content -Raw -Encoding UTF8 -LiteralPath $workstreamBindings | ConvertFrom-Json
    if ($bindings.routes.Count -ne 2) { throw 'owner-only workstream bindings must contain exactly two routes' }
    $script:workstreamRootA = [string]$bindings.routes[0].root
    $script:workstreamRootB = [string]$bindings.routes[1].root
    if ([string]::IsNullOrWhiteSpace($workstreamRootA) -or [string]::IsNullOrWhiteSpace($workstreamRootB)) { throw 'validated bindings lack both real workstream roots' }
  }
}
~~~

First create the exact seven-slot transparency plan for the frozen subject and display the irreversible public-log request. This block is side-effect-free with respect to GitHub and Rekor:

~~~powershell
$transparencyPlan = 'release/evidence/dogfood-transparency-plan.json'
$transparencyAuthorization = 'release/evidence/dogfood-transparency-authorization.json'
$dispatchStateDir = 'release/evidence/dogfood-anchor-dispatch'
if ((Test-Path -LiteralPath $transparencyAuthorization) -or (Test-Path -LiteralPath $dispatchStateDir)) { throw 'G6 authority or dispatch state already exists; use Resume-G6Window and never overwrite it' }
if (-not (Test-Path -LiteralPath $transparencyPlan)) {
  & $releasePython tools/dogfood_anchor.py transparency-plan --subject $subject --repo Zeroxrain99/CodeSextant --workflow-ref .github/workflows/dogfood-anchor.yml --signing-policy release/dogfood-signing-policy.json --slot-kind start --slot-kind daily --slot-kind daily --slot-kind daily --slot-kind daily --slot-kind daily --slot-kind end --out $transparencyPlan
}
& $releasePython tools/dogfood_anchor.py validate-plan --subject $subject --plan $transparencyPlan --signing-policy release/dogfood-signing-policy.json
& $releasePython tools/dogfood_anchor.py show-authorization-request --plan $transparencyPlan
~~~

Expected: the displayed digest binds the frozen ReleaseSubject, exact repository/workflow/signing identity, exactly seven UUIDv4 one-shot slots, and the complete public Sigstore/Rekor disclosure. It states that already-written public transparency records cannot be deleted by a reset or compensation. After the user explicitly authorizes that exact display and acknowledges the irreversible public log, record and validate the separate authorization:

~~~powershell
if (Test-Path -LiteralPath $transparencyAuthorization) { throw 'transparency authorization already exists and is immutable' }
& $releasePython tools/dogfood_anchor.py record-authorization --plan $transparencyPlan --acknowledge-public-transparency-log --authorized-by user --expires-days 10 --out $transparencyAuthorization
& $releasePython tools/dogfood_anchor.py validate-authorization --subject $subject --plan $transparencyPlan --authorization $transparencyAuthorization --signing-policy release/dogfood-signing-policy.json
~~~

Only after authorization passes, persist the two real workstream roots/normalized identities in an owner-only pending intent before any network dispatch. `prepare-window` is idempotent only for byte-identical authority/roots; it refuses to overwrite or delete an existing intent, authorization, dispatch record, anchor, bindings, plan, issue ledger, or window state:

~~~powershell
$workstreamRootA = $realWorkstreamRootA
$workstreamRootB = $realWorkstreamRootB
if (-not (Test-Path -LiteralPath release/evidence/dogfood-workstream-intent.json)) {
  if (-not $workstreamRootA -or -not $workstreamRootB) { throw 'two genuine workstream repository roots are required before the first network dispatch' }
  & $releasePython tools/dogfood.py prepare-window --subject $subject --policy dogfood/policy.json --transparency-plan $transparencyPlan --transparency-authorization $transparencyAuthorization --workstream-root $workstreamRootA --workstream-root $workstreamRootB --workstream-intent-out release/evidence/dogfood-workstream-intent.json --window-state-out release/evidence/dogfood-window-state.json --dispatch-state release/evidence/dogfood-anchor-dispatch --anchors release/evidence/dogfood-anchors
}
Resume-G6Window
~~~

`resume-window` is the phase authority: `authorized_no_start` permits the one start dispatch; `start_confirmed_no_workstream_plan` is recovered by the persisted request nonce/start anchor and deterministically completed into bindings/plan/issues without dispatching again; `active` resumes the remaining daily/end slots; `complete` is read-only. If a dispatch-start exists without a local anchor, recovery queries the already-issued workflow nonce and downloads/verifies that same result. It never creates a second workflow dispatch. If the result cannot be proven, it tombstones the slot and stops.

When `$g6Window.phase` is `authorized_no_start`, execute the start transaction exactly once. If it is already `active` after a restart, skip this block and continue; never manually delete state to make it runnable:

~~~powershell
if ($g6Window.phase -eq 'authorized_no_start') {
  $startSlot = @($transparency.slots | Where-Object kind -eq 'start')
  if ($startSlot.Count -ne 1 -or $startSlot[0].slot_id -notmatch '^[0-9a-f-]{36}$') { throw 'authorized plan must contain exactly one canonical start slot' }
  $startSlotId = $startSlot[0].slot_id
  $startDispatchState = Join-Path $dispatchStateDir "$startSlotId-start.json"
  $startDispatchTombstone = Join-Path $dispatchStateDir "$startSlotId-tombstone.json"
  $startRequest = "release/evidence/dogfood-anchor-$startSlotId-request.json"
  $startAnchor = Join-Path $anchorDir "slot-$startSlotId.json"
  foreach ($path in @($startRequest,$startAnchor,$startDispatchState,$startDispatchTombstone)) { if (Test-Path -LiteralPath $path) { throw "start anchor authority already exists; recover without deletion: $path" } }
  $genesisHead = & $releasePython tools/dogfood.py genesis-head --subject $subject
  if ($genesisHead -notmatch '^[0-9a-f]{64}$') { throw 'invalid subject-derived genesis head' }
  & $releasePython tools/dogfood.py anchor-request --subject $subject --transparency-plan $transparencyPlan --slot-id $startSlotId --mode start --event-count 0 --chain-head $genesisHead --out $startRequest
  & $releasePython tools/dogfood_anchor.py dispatch --request $startRequest --transparency-plan $transparencyPlan --authorization $transparencyAuthorization --slot-id $startSlotId --dispatch-start-out $startDispatchState --dispatch-tombstone-out $startDispatchTombstone --out $startAnchor
  Resume-G6Window
}
if ($g6Window.phase -notin @('active','complete')) { throw "G6 bootstrap did not reach a resumable active phase: $($g6Window.phase)" }
~~~

Expected: the start anchor has event_count 0, binds `genesis_chain_head(subject_sha256)`, lives inside the anchor directory consumed by R4, and has a verified Rekor inclusion time. Prepare one checksummed isolated installation of the frozen platform artifact; both workstreams must use this same installation/artifact SHA:

~~~powershell
$staging = Get-Content -Raw -Encoding UTF8 -LiteralPath release/staging.json | ConvertFrom-Json
$dogfoodAssets = Join-Path $env:TEMP ("codesextant-dogfood-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $dogfoodAssets | Out-Null
gh release download $staging.release_tag --repo Zeroxrain99/CodeSextant --dir $dogfoodAssets
$dogfoodManifest = Join-Path $dogfoodAssets 'artifact-manifest.json'
Remove-Item -LiteralPath release/evidence/dogfood-install.json -Force -ErrorAction SilentlyContinue
& $releasePython tools/dogfood.py prepare-install --subject $subject --plan release/evidence/dogfood-plan.json --manifest $dogfoodManifest --asset-root $dogfoodAssets --out release/evidence/dogfood-install.json
~~~

For each genuine CodeSextant query session, use the controlled wrapper and append only its verified execution receipt. The two-entry local mapping below is private; the wrapper recomputes each HMAC commitment and rejects an ID/root mismatch or two aliases of one repository. Repeat with fresh session/execution paths across the required operation mix until each plan-issued workstream has at least 20 successful nonvacuous sessions:

~~~powershell
Resume-G6Window
$dogfoodPlan = Get-Content -Raw -Encoding UTF8 -LiteralPath release/evidence/dogfood-plan.json | ConvertFrom-Json
$workstreams = @(
  @{ id = $dogfoodPlan.workstreams[0].id; root = $workstreamRootA },
  @{ id = $dogfoodPlan.workstreams[1].id; root = $workstreamRootB }
)
$workstream = $workstreams[0]
$sessionId = [Guid]::NewGuid().ToString()
$executionReceipt = "release/evidence/dogfood-execution-$sessionId.json"
Remove-Item -LiteralPath $executionReceipt -Force -ErrorAction SilentlyContinue
$oldNativePreference = $PSNativeCommandUseErrorActionPreference
try {
  $PSNativeCommandUseErrorActionPreference = $false
  & $releasePython tools/dogfood.py run --subject $subject --plan release/evidence/dogfood-plan.json --workstream-bindings $workstreamBindings --install-receipt release/evidence/dogfood-install.json --workstream-id $workstream.id --session-id $sessionId --operation map --repository $workstream.root --out $executionReceipt
  $dogfoodRunExit = $LASTEXITCODE
} finally {
  $PSNativeCommandUseErrorActionPreference = $oldNativePreference
}
if (-not (Test-Path -LiteralPath $executionReceipt -PathType Leaf)) { throw 'dogfood wrapper returned without an execution receipt' }
if ($dogfoodRunExit -eq 0) {
  & $releasePython tools/dogfood.py record --subject $subject --plan release/evidence/dogfood-plan.json --install-receipt release/evidence/dogfood-install.json --execution-receipt $executionReceipt --issues release/evidence/dogfood-issues.json --events release/evidence/dogfood-events.jsonl
} else {
  Write-Warning "dogfood execution failed with exit $dogfoodRunExit; do not record success—classify and execute the failure block below"
}
~~~

If `run` is nonzero, do not write `success`. Create a linked issue from that execution receipt before `record`; after a real fix or disposition, use `issue-resolve` so history remains auditable. A product-defect fix changes the artifact and resets the full freeze/window:

~~~powershell
if ($dogfoodRunExit -eq 0) { throw 'failure branch must run only for a nonzero execution receipt' }
$issueId = & $releasePython tools/dogfood.py issue-record --subject $subject --plan release/evidence/dogfood-plan.json --execution-receipt $executionReceipt --severity P1 --class product_defect --code PRODUCT_EXECUTION_FAILED --issues release/evidence/dogfood-issues.json --print-issue-id
if ($issueId -notmatch '^[0-9a-f-]{36}$') { throw 'issue recorder did not return a canonical issue UUID' }
& $releasePython tools/dogfood.py record --subject $subject --plan release/evidence/dogfood-plan.json --install-receipt release/evidence/dogfood-install.json --execution-receipt $executionReceipt --issues release/evidence/dogfood-issues.json --events release/evidence/dogfood-events.jsonl
throw 'dogfood product defect was recorded; freeze/artifact/window must reset before continuing'
~~~

For a non-product external outage or user-choice fallback, use the matching allowed class/code, record the failure event, and only later call `issue-resolve` with a real resolution-evidence SHA-256. A product defect is never “resolved” inside the old subject: fix the product, freeze a new ReleaseSubject, and restart G6.

On at least five different UTC dates with genuine activity, run the following template once for that date; `anchor-request` derives the observed count/head from the private JSONL:

~~~powershell
Resume-G6Window
$dailyOrdinal = 1 # use each value 1..5 exactly once, on a genuine distinct active UTC date
$dailySlot = @($transparency.slots | Where-Object { $_.kind -eq 'daily' -and $_.ordinal -eq $dailyOrdinal })
if ($dailySlot.Count -ne 1) { throw "authorized plan lacks daily slot $dailyOrdinal" }
$dailySlotId = $dailySlot[0].slot_id
$dailyDispatchState = Join-Path $dispatchStateDir "$dailySlotId-start.json"
$dailyDispatchTombstone = Join-Path $dispatchStateDir "$dailySlotId-tombstone.json"
$dailyRequest = "release/evidence/dogfood-anchor-$dailySlotId-request.json"
$dailyAnchor = Join-Path $anchorDir "slot-$dailySlotId.json"
foreach ($path in @($dailyRequest,$dailyAnchor,$dailyDispatchState,$dailyDispatchTombstone)) { if (Test-Path -LiteralPath $path) { throw "daily anchor authority already exists; recover without deletion: $path" } }
& $releasePython tools/dogfood.py anchor-request --subject $subject --plan release/evidence/dogfood-plan.json --transparency-plan $transparencyPlan --slot-id $dailySlotId --mode daily --events release/evidence/dogfood-events.jsonl --out $dailyRequest
& $releasePython tools/dogfood_anchor.py dispatch --request $dailyRequest --transparency-plan $transparencyPlan --authorization $transparencyAuthorization --slot-id $dailySlotId --dispatch-start-out $dailyDispatchState --dispatch-tombstone-out $dailyDispatchTombstone --out $dailyAnchor
~~~

After verified Rekor integrated time shows at least 168 elapsed hours, create and dispatch the end request from the final validated chain:

~~~powershell
Resume-G6Window
$endSlot = @($transparency.slots | Where-Object kind -eq 'end')
if ($endSlot.Count -ne 1) { throw 'authorized plan must contain exactly one end slot' }
$endSlotId = $endSlot[0].slot_id
$endDispatchState = Join-Path $dispatchStateDir "$endSlotId-start.json"
$endDispatchTombstone = Join-Path $dispatchStateDir "$endSlotId-tombstone.json"
$endRequest = "release/evidence/dogfood-anchor-$endSlotId-request.json"
$endAnchor = Join-Path $anchorDir "slot-$endSlotId.json"
foreach ($path in @($endRequest,$endAnchor,$endDispatchState,$endDispatchTombstone)) { if (Test-Path -LiteralPath $path) { throw "end anchor authority already exists; recover without deletion: $path" } }
& $releasePython tools/dogfood.py anchor-request --subject $subject --plan release/evidence/dogfood-plan.json --transparency-plan $transparencyPlan --slot-id $endSlotId --mode end --events release/evidence/dogfood-events.jsonl --out $endRequest
& $releasePython tools/dogfood_anchor.py dispatch --request $endRequest --transparency-plan $transparencyPlan --authorization $transparencyAuthorization --slot-id $endSlotId --dispatch-start-out $endDispatchState --dispatch-tombstone-out $endDispatchTombstone --out $endAnchor
~~~

Do not synthesize/backdate events, reuse a slot-derived authority path/slot, or retry an ambiguous dispatch. The dispatch tool writes the matching tombstone before returning nonzero on ambiguity; a replacement plan requires a fresh displayed disclosure and explicit user authorization, and every already-written Rekor record remains public. Resolve every P0/P1; any product/export/artifact change invalidates the subject and resets the whole run.

### R4: Reverify G6 in a fresh deterministic process and stage/hash public ancillary assets

~~~powershell
Resume-G6Window
$dogfoodPlan = Get-Content -Raw -Encoding UTF8 -LiteralPath release/evidence/dogfood-plan.json | ConvertFrom-Json
$report = "release/assets/dogfood-$($dogfoodPlan.artifact_sha256.Substring(0,12))-report.md"
Remove-Item -LiteralPath $report,release/assets/g6-public-assets.json -Force -ErrorAction SilentlyContinue
& $releasePython tools/dogfood.py validate-workstreams --subject $subject --plan release/evidence/dogfood-plan.json --workstream-bindings release/evidence/dogfood-workstream-bindings.json --bindings-schema dogfood/workstream-bindings.schema.json --events release/evidence/dogfood-events.jsonl
$summaryExists = Test-Path -LiteralPath release/evidence/dogfood-summary.json -PathType Leaf
$issuesExists = Test-Path -LiteralPath release/evidence/issues.json -PathType Leaf
if ($issuesExists -and -not $summaryExists) { throw 'issues-without-summary is impossible/terminal; never delete or synthesize the prerequisite' }
if (-not $summaryExists) {
  & $releasePython $g6.ReleaseGatePath produce-and-seal --gate G6 --receipt dogfood-summary.json @g6GateContext -- --plan release/evidence/dogfood-plan.json --transparency-plan $transparencyPlan --transparency-authorization $transparencyAuthorization --anchor-dispatch-state $dispatchStateDir --events release/evidence/dogfood-events.jsonl --anchors release/evidence/dogfood-anchors --issues release/evidence/dogfood-issues.json --public-report $report
  if ($LASTEXITCODE -ne 0) { throw 'dogfood summary producer/sealer failed' }
}
if (-not $issuesExists) {
  & $releasePython tools/dogfood.py verify-summary --subject $subject --summary release/evidence/dogfood-summary.json --plan release/evidence/dogfood-plan.json --events release/evidence/dogfood-events.jsonl --anchors release/evidence/dogfood-anchors --private-issues release/evidence/dogfood-issues.json --recompute-report-and-compare $report
  if ($LASTEXITCODE -ne 0) { throw 'sealed summary cannot safely forward-recover missing issues receipt' }
  & $releasePython $g6.ReleaseGatePath produce-and-seal --gate G6 --receipt issues.json @g6GateContext -- --issues release/evidence/dogfood-issues.json
  if ($LASTEXITCODE -ne 0) { throw 'dogfood issues producer/sealer failed' }
} else {
  & $releasePython tools/dogfood.py verify-summary --subject $subject --summary release/evidence/dogfood-summary.json --issues-receipt release/evidence/issues.json --plan release/evidence/dogfood-plan.json --events release/evidence/dogfood-events.jsonl --anchors release/evidence/dogfood-anchors --private-issues release/evidence/dogfood-issues.json --recompute-report-and-compare $report
  if ($LASTEXITCODE -ne 0) { throw 'existing immutable G6 receipts/report are not deterministic-equal' }
}
& $releasePython tools/verify_first_user.py verify-receipt --subject $subject --scenario release/first-user-scenario.json --runner-bundle-root release/evidence/first-user-runner-bundle --runner-bundle-manifest release/evidence/first-user-runner-bundle/first-user-runner-bundle.json --runner-roles release/first-user-runner-roles.json --implementation-actors provenance/implementation-actors.json --release-python-lock requirements/release.lock --runner-receipt release/evidence/first-user-run.json --gate-receipt release/evidence/first-user.json
if ($LASTEXITCODE -ne 0) { throw 'first-user signed receipt replacement check failed' }
& $releasePython $g6.ReleaseGatePath check --gate G6 @g6GateContext
if ($LASTEXITCODE -ne 0) { throw 'complete G6 typed gate failed' }
$seedAssetRoot = $g6.ReleaseAssetsRoot
$seedInstaller = Join-Path $seedAssetRoot 'codesextant-g8-seed-installer.exe'
$installerTrustJson = & $g6Launcher verify-authenticode-fixed-policy --authority $g6AuthorityPath --path $seedInstaller --format json
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$installerTrustJson)) { throw 'standalone G8 installer failed protected-launcher Authenticode pin' }
$seedStateJson = & $seedInstaller state-fixed --authority $g6AuthorityPath --subject $subject --asset-root $seedAssetRoot --format json
if ($LASTEXITCODE -ne 0) { throw 'standalone installer could not classify fixed trust-root state' }
$seedState = $seedStateJson | ConvertFrom-Json
$elevatedArgs = switch ($seedState.state) {
  'absent' { @('install','--create-new') }
  'complete' { @('verify') }
  'orphan_assets_without_receipt' { @('recover-orphan','--create-receipt-only') }
  'terminal_tombstone' { throw 'G8 trust root is terminal; follow administrator remediation, never auto-repair' }
  default { throw "unknown/ambiguous G8 fixed state: $($seedState.state)" }
}
$commonInstallerArgs = @('--authority',$g6AuthorityPath,'--subject',$subject,'--release-index',$g6.ReleaseIndex,'--release-index-bundle',$g6.ReleaseIndexBundle,'--asset-root',$seedAssetRoot)
$elevated = Start-Process -FilePath $seedInstaller -Verb RunAs -Wait -PassThru -ArgumentList @($elevatedArgs + $commonInstallerArgs)
if ($elevated.ExitCode -ne 0) { throw "elevated fixed-path G8 operation failed: $($elevated.ExitCode)" }
& $seedInstaller verify @commonInstallerArgs
if ($LASTEXITCODE -ne 0) { throw 'post-elevation fixed G8 trust-root verification failed' }
$evidenceReceipt = Join-Path $g6.EvidenceDir 'g8-seed-install.json'
$exportMode = if (Test-Path -LiteralPath $evidenceReceipt -PathType Leaf) { '--verify-existing' } else { '--create-new' }
& $seedInstaller export-evidence $exportMode @commonInstallerArgs --evidence-dir $g6.EvidenceDir
if ($LASTEXITCODE -ne 0) { throw 'could not create byte-identical read-only evidence copy of fixed signed install receipt' }
& $releasePython tools/dogfood.py emit-public-assets --subject $subject --report $report --first-user release/evidence/first-user.json --summary release/evidence/dogfood-summary.json --issues release/evidence/issues.json --out release/assets/g6-public-assets.json
~~~

Expected: all exit 0. Existing registered receipts were verified without rewrite; absent ones were created only through authenticated `produce-and-seal`. First-user reverification preserves the exact signature-valid external attestation and privacy-safe public statement. The WinVerifyTrust-pinned standalone installer—not checkout Python—classifies the fixed ProgramData trust root, routes exactly absent/complete/orphan/tombstone, elevates only the signed indexed executable, verifies the machine key plus TrustedInstaller owner/exact ACL/no-reparse chain, and leaves a fixed machine-signed receipt or terminal tombstone. `release/evidence/g8-seed-install.json` is only a byte-identical read-only export; the fixed ProgramData receipt/live handles remain authority. `g6-public-assets.json` lists exactly the privacy-audited report and three public-safe evidence files and contains no private identities/paths/secrets. Do not upload, commit, edit the product manifest, or change visibility. Hand the public manifest plus exported install receipt to G7; G7 must run the native fixed verifier and bind the authoritative installed receipt/live seed closure before publication planning.
