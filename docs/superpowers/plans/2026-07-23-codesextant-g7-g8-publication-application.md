---
tier: 全文
status: revision-9-shared-exact-task-commit-closure
date: 2026-07-23
scope: CodeSextant G7-G8 publication and application
---

# CodeSextant G7-G8 Publication and Claude OSS Application Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Publish exactly one fully verified CodeSextant release under Zeroxrain99 and only then submit a factual, publicly evidenced Claude for Open Source application.

**Architecture:** Two fail-closed transaction-like workflows separate preparation from external effects. G7 refreshes security evidence against the immutable export, builds an immutable publication-plan payload plus a separate authorization receipt, validates G0-G6 evidence and identity, then promotes the already verified private staging export to public and re-verifies from the public Internet. G8 builds its application exclusively from public URLs/API facts, receives an independent signed review of every typed evidence-use edge, and requires a final user authorization before form submission.

**Tech Stack:** Python 3.11, Git/GitHub CLI and API, Chrome connector for logged-in identity/form actions, JSON Schema 2020-12, pytest, pinned cosign with Sigstore/Rekor bundles, OpenSSF Scorecard, official Anthropic Claude for Open Source terms and form.

## Global Constraints

- No GitHub public repository, public release, announcement, or application submission occurs until G0-G6 all pass for the exact ReleaseSubject digest.
- A registry-owned publication-security refresh must finish no more than 24 hours before the G7 transaction starts and must bind the same ReleaseSubject, export, artifacts, runtime closure, SBOM, pre-public SAST, and independent security review. A new high/critical advisory, vulnerable dependency, runtime supersession, or announced pending security release blocks publication and requires rebuild/refreeze plus G4-G6 reruns; stale G5 evidence is never grandfathered through the 168-hour dogfood window.
- Current browser evidence identifies the logged-in account as Zeroxrain99. Current gh CLI evidence identifies aiking931931, so CLI publication is blocked until gh api user returns Zeroxrain99.
- Google linkage is not inferable from the public GitHub API. Immediately before G7, verify the intended email through the logged-in account settings or obtain an explicit user confirmation tied to the publication-plan payload.
- The destination is owner Zeroxrain99, repository CodeSextant, default branch main, visibility public.
- Publication authorization hashes an immutable publication-plan payload containing ReleaseSubject digest, source/export identities, artifact hashes, derived version/tag, owner/repository, and public visibility. Authorization is stored beside the payload, never inside the payload it hashes.
- The private staging repository from G5 contains the exact allowlist export and draft release. G7 promotes that reviewed state; it never rebuilds from a different checkout.
- Any mismatch during promotion or public verification fails closed. Do not repair public state piecemeal from an unreviewed commit.
- No claim says approval is guaranteed. The application may only say submitted and awaiting Anthropic discretionary review after a confirmed submission receipt.
- Eligibility and form fields are re-verified against current official Anthropic pages immediately before submission because terms may change.
- The validator must prove one official eligibility track: Maintainer Track with its current quantitative threshold, or Ecosystem Impact Track with concrete independently owned downstream use showing that the ecosystem meaningfully depends on CodeSextant. A project-authored explanation or URL alone is not eligibility. It also records every current general eligibility attestation from the official terms; it never infers age, location/sanctions, natural-person status, GitHub good standing, family/household relationship, duplicate-application state, or Anthropic employment from GitHub.
- Application receipts and private email evidence never enter the public export.
- External actions are sequential: identity -> immutable authorization -> promotion -> public verification -> application evidence -> factual review -> application authorization -> submission.
- All product, G7 publication, **G8 trust-bootstrap**, and G8 context-initializer tooling is committed before G5 final freeze. Tasks 2-3 private G8 tooling are implemented only after the product `ReleaseSubject` freezes, in standalone local Git repository `E:\ai-king\private\CodeSextant-application` with no remote and a Git root distinct from CodeSextant; they are never committed into the product source tree/commit or public export. Before any private module is imported or executed, the product-frozen bootstrap creates and verifies a content-addressed, clean product execution root from the public ReleaseSubject and its policy-rooted Sigstore bundles. The locked Python, external-review engine, generic external-review schemas, release-gate implementation, and G8 initializer are thereafter loaded only from that product execution root. The private repository may add files only below the declared private namespaces; it may not modify or delete any pre-existing product path. Its exact private Git commit/tree, exhaustive additive closure, and official-terms snapshot are frozen separately as `ApplicationToolSubject`. If terms or private G8 tooling later change, update and independently review only that private repository, mint a new application subject, and rerun G8 without altering or invalidating the already-published product/G7 chain.
- Every source-code task follows RED -> GREEN -> refactor and uses the exact commit message shown. External identity, promotion, verification, and form steps live in runbooks and are not mislabeled as implementation tasks.

G0 Task 1 owns the sole tracked exact-task commit helper and its disposable-repository contract test at `tools/exact_task_commit.ps1` and `tests/release/test_exact_task_commit.py`; G7/G8 must extend and consume that SSOT, never fork or inline it. Task 1 adds an explicit `-RepositoryRoot` mode while preserving existing current-repository callers. The helper resolves and proves one absolute Git root, runs every Git operation with `git -C <root>`, requires an initially empty index and a duplicate-free list of existing leaf paths, and stages only that list. It parses both the cached diff and resulting `HEAD^..HEAD` diff with `--name-status --find-renames --find-copies --find-copies-harder`, accepting only single-path `A`/`M` records with case-sensitive exact set equality; captures cached blob IDs and modes; runs `git -C <root> -c core.hooksPath=NUL commit --no-verify`; then proves the resulting raw blob/mode closure is identical and the index is empty. Deletes, renames, copies, type changes, duplicate manifests, pre-staged extras, commit-hook/index mutation, or cached-versus-HEAD drift fail closed. The tracked test runs before Task 1's product commit and, from the authenticated product execution root, before each private Task 2/3 commit. Private commits pass `-RepositoryRoot $privateRoot`; this commit mechanism does not relax the remote-free, additive-only namespace boundary, which is checked immediately before the helper touches the index and again after its commit.

---

### Task 1: Build a side-effect-free GitHub publication preflight

**Files:**
- Modify (G0 exact-commit SSOT; add explicit repository-root mode, no duplicate helper): tools/exact_task_commit.ps1
- Modify/Test (G0 disposable-repository contract; run the complete matrix in explicit-root mode): tests/release/test_exact_task_commit.py
- Create: release/github.json
- Consume (G5 SSOT): release/github-controls.schema.json
- Consume (G5 SSOT): release/github-controls.json
- Consume (G5 trust root): release/signing-policy.json
- Consume (G5 trust root): release/verifier-bootstrap.json
- Consume (pre-F1 committed Authenticode authority): release/g8-authenticode-signing-policy.json
- Consume (G6 trust root): release/g8-seed-install-receipt.schema.json
- Consume (G6 non-authoritative byte-identical gate mirror): release/evidence/g8-seed-install.json
- Consume (G6 fixed installed signed authority): `%ProgramData%\CodeSextant\Trust\G8\g8-seed-install.json`
- Consume (G6 sole verifier): tools/install_g8_seed.py
- Consume (G6 fixed native bootstrap): `%ProgramData%\CodeSextant\Trust\G8\codesextant-g8-seed-static-verify.exe`
- Modify (G5 closed review scope before final freeze): release/security-review-scope.json
- Create: release/github-identity.schema.json
- Create: release/publication-plan.schema.json
- Create: release/publication-authorization.schema.json
- Create: release/publication-start.schema.json
- Create: release/publication-mutation-journal.schema.json
- Create: release/publication-result.schema.json
- Create: release/publication-tombstone.schema.json
- Create: release/g8-product-execution-root.schema.json
- Create: release/g8-node-context.schema.json
- Create: release/g8_node_host.mjs
- Create: release/g8_node_bootstrap.mjs
- Create: release/evidence/publication-security-refresh.schema.json
- Create: release/evidence/github-publication.schema.json
- Create: release/evidence/public-smoke.schema.json
- Modify: release/evidence/receipt-registry.json
- Modify (actual G7 producer/runtime hashes; no private G8 specs): release/evidence/producer-launch-policy.json
- Create: tools/github_preflight.py
- Create: tools/github_publish.py
- Create: tools/github_public_verify.py
- Create: tools/publication_security_refresh.py
- Create: tools/application_repo_bootstrap.py
- Create: tools/render_publication_runbook.py
- Create: release/Bootstrap-CodeSextantG8ProductExec.ps1
- Create: release/Initialize-CodeSextantG7.ps1
- Create: release/Initialize-CodeSextantG8.ps1
- Create (pre-freeze generated, tracked, Authenticode-signed, complete inline pre-exec definitions): release/Invoke-CodeSextantPublication.ps1
- Create: tests/release/test_github_preflight.py
- Create: tests/release/test_github_publish.py
- Create: tests/release/test_github_public_verify.py
- Create: tests/release/test_publication_security_refresh.py
- Create: tests/release/test_application_repo_bootstrap.py
- Create: tests/release/test_g7_fresh_shell.py
- Create: tests/release/test_g8_trusted_bootstrap.py
- Create: tests/release/test_transaction_entry_routing.py
- Create: tests/release/test_publication_application_runbook_static.py

**Step 1: Write RED tests**

First extend `tests/release/test_exact_task_commit.py`. Parameterize its complete real-Git matrix over both the existing current-repository invocation and an explicit `-RepositoryRoot` invocation launched from a foreign working directory. Both modes must cover `A`/`M` success; real `D`/`R`/`C`/`T` rejection using `--find-renames --find-copies --find-copies-harder`; duplicate and pre-staged-extra rejection; leaf-only manifests; hook/index-mutation isolation; cached-versus-resulting-HEAD blob/mode equality; exact resulting `HEAD^..HEAD` name-status closure; and an empty post-commit index. Also reject a relative root, non-root subdirectory, nonexistent root, and a root that resolves to a different repository.

~~~python
def test_exact_task_commit_is_cwd_independent_with_explicit_repository_root(
    real_repo, foreign_cwd
) -> None:
    write(real_repo / "declared.txt", "declared")
    result = invoke_exact_commit(
        real_repo,
        ["declared.txt"],
        "test: explicit repository root",
        cwd=foreign_cwd,
        repository_root=real_repo,
    )
    assert result.returncode == 0
    assert committed_name_status(real_repo, find_renames=True, find_copies=True) == [
        "A\tdeclared.txt"
    ]
    assert committed_raw_blob_and_mode(real_repo) == captured_cached_blob_and_mode(result)
    assert cached_name_status(real_repo) == []
~~~

~~~python
EXPECTED = {
    "owner": "Zeroxrain99",
    "repository": "CodeSextant",
    "default_branch": "main",
    "visibility": "public",
    "license_spdx": "Apache-2.0",
}


def test_preflight_rejects_any_red_or_wrong_subject_gate(valid_plan) -> None:
    valid_plan["gates"]["G6"]["subject_sha256"] = "0" * 64
    assert preflight(valid_plan, VALID_AUTHORIZATION, VALID_SUBJECT, VALID_CONTROLS, VALID_SECURITY_REFRESH).status == "fail"


def test_preflight_rejects_wrong_destination(valid_plan) -> None:
    valid_plan["destination"]["owner"] = "aiking931931"
    assert preflight(valid_plan, VALID_AUTHORIZATION, VALID_SUBJECT, VALID_CONTROLS, VALID_SECURITY_REFRESH).status == "fail"


def test_preflight_rejects_non_apache_product_license(valid_plan) -> None:
    valid_plan["destination"]["license_spdx"] = "BSD-3-Clause"
    assert preflight(valid_plan, VALID_AUTHORIZATION, VALID_SUBJECT, VALID_CONTROLS, VALID_SECURITY_REFRESH).status == "fail"


def test_preflight_has_no_network_side_effect(monkeypatch, valid_plan) -> None:
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert preflight(valid_plan, VALID_AUTHORIZATION, VALID_SUBJECT, VALID_CONTROLS, VALID_SECURITY_REFRESH).status == "pass"


def test_authorization_hashes_payload_not_an_envelope(valid_plan) -> None:
    digest = publication_plan_digest(valid_plan)
    authorization = sign_user_authorization_fixture(digest)
    assert verify_authorization(valid_plan, authorization).status == "pass"
    assert "authorization" not in valid_plan


def test_public_verify_uses_only_declared_product_and_evidence_assets(
    valid_subject, artifact_manifest, valid_plan
) -> None:
    artifact_manifest["release_assets"].append({"path": "extra.bin", "sha256": "0" * 64})
    assert public_verify(valid_subject, artifact_manifest, valid_plan).status == "fail"


def test_publication_plan_binds_every_g4_g6_public_evidence_asset(valid_plan) -> None:
    valid_plan["public_evidence_assets"].pop()
    assert preflight(valid_plan, VALID_AUTHORIZATION, VALID_SUBJECT, VALID_CONTROLS, VALID_SECURITY_REFRESH).status == "fail"


def test_plan_binds_signed_release_index_and_pinned_verifier_bootstrap(valid_plan) -> None:
    assert valid_plan["release_index_sha256"] == VALID_SUBJECT.release_index_sha256
    assert re.fullmatch(r"[0-9a-f]{64}", valid_plan["verifier_bootstrap_sha256"])
    valid_plan["verifier_bootstrap_sha256"] = "0" * 64
    assert preflight(valid_plan, VALID_AUTHORIZATION, VALID_SUBJECT, VALID_CONTROLS, VALID_SECURITY_REFRESH).status == "fail"


def test_plan_start_result_and_receipt_bind_installed_g8_seed(
    valid_publication_chain, installed_g8_seed
) -> None:
    expected = sha256_file(installed_g8_seed)
    for link in ("plan", "start", "result", "github_publication"):
        assert domain_payload(valid_publication_chain[link])["g8_seed_verifier_sha256"] == expected
        assert domain_payload(valid_publication_chain[link])["g8_seed_install_receipt_sha256"] == canonical_sha256(
            valid_publication_chain["g8_seed_install"]
        )
    domain_payload(valid_publication_chain["github_publication"])["g8_seed_verifier_sha256"] = "0" * 64
    assert verify_g7_chain(valid_publication_chain, installed_g8_seed=installed_g8_seed).status == "fail"


def test_publication_plan_binds_the_verified_google_linked_identity(valid_plan) -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", valid_plan["github_identity_sha256"])
    authorization = sign_user_authorization_fixture(publication_plan_digest(valid_plan))
    valid_plan["github_identity_sha256"] = "0" * 64
    assert verify_authorization(valid_plan, authorization).status == "fail"


def test_plan_binds_github_controls_and_fresh_security_refresh(valid_plan) -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", valid_plan["github_controls_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", valid_plan["publication_security_refresh_sha256"])
    authorization = sign_user_authorization_fixture(publication_plan_digest(valid_plan))
    valid_plan["github_controls_sha256"] = "0" * 64
    assert verify_authorization(valid_plan, authorization).status == "fail"


def test_security_refresh_rejects_stale_or_changed_release_closure(valid_refresh) -> None:
    assert verify_security_refresh(valid_refresh, now=valid_refresh.completed_at_utc + timedelta(hours=24)).status == "pass"
    assert verify_security_refresh(valid_refresh, now=valid_refresh.completed_at_utc + timedelta(hours=24, microseconds=1)).status == "fail"
    valid_refresh["sbom_sha256"] = "0" * 64
    assert verify_security_refresh(valid_refresh).status == "fail"


@pytest.mark.parametrize(
    "bound_digest",
    [
        "artifacts_receipt_sha256",
        "security_receipt_sha256",
        "security_review_receipt_sha256",
        "runtime_policy_sha256",
        "check_policy_sha256",
        "github_controls_sha256",
        "signing_policy_sha256",
        "verifier_bootstrap_sha256",
    ],
)
def test_security_refresh_verifier_recomputes_every_generation_input(valid_refresh, bound_digest) -> None:
    original_inputs = refresh_verification_inputs(valid_refresh)
    original_inputs[bound_digest] = tampered_input_for(bound_digest)
    assert verify_security_refresh(valid_refresh, **original_inputs).status == "fail"


@pytest.mark.parametrize(
    "blocking_fact",
    ["new_high_advisory", "new_critical_advisory", "vulnerable_dependency", "runtime_superseded", "pending_security_release"],
)
def test_security_refresh_blocks_new_security_facts(valid_refresh, blocking_fact) -> None:
    valid_refresh["observations"][blocking_fact] = True
    assert verify_security_refresh(valid_refresh).status == "fail"


def test_plan_requires_post_publish_failure_compensation(valid_plan) -> None:
    assert valid_plan["compensation"] == {
        "release_to_draft": True,
        "delete_only_run_uploaded_evidence_assets": True,
        "visibility_to_private": True,
        "restore_description_and_topics": True,
        "restore_security_settings": True,
        "restore_rulesets_and_branch_protections": True,
        "verify_prior_private_state": True,
    }
    valid_plan["compensation"]["visibility_to_private"] = False
    assert preflight(valid_plan, VALID_AUTHORIZATION, VALID_SUBJECT, VALID_CONTROLS, VALID_SECURITY_REFRESH).status == "fail"


def test_plan_and_authorization_acknowledge_irreversible_public_disclosure(valid_plan) -> None:
    assert valid_plan["residual_risk"]["public_bytes_may_be_cloned_cached_or_forked"] is True
    assert valid_plan["residual_risk"]["compensation_cannot_restore_confidentiality"] is True
    assert valid_plan["residual_risk"]["public_audit_and_check_history_may_persist"] is True
    authorization = sign_user_authorization_fixture(publication_plan_digest(valid_plan))
    authorization["acknowledged_irreversible_disclosure"] = False
    assert verify_authorization(valid_plan, authorization).status == "fail"


def test_g7_rejects_stale_or_tombstoned_transaction(valid_receipts, valid_plan) -> None:
    valid_receipts.public_smoke["payload"]["transaction_id"] = str(uuid.uuid4())
    assert verify_g7(valid_receipts, valid_plan).status == "fail"
    valid_receipts.public_smoke["payload"]["transaction_id"] = valid_plan["transaction_id"]
    write_tombstone(valid_plan["transaction_id"])
    assert verify_g7(valid_receipts, valid_plan).status == "fail"


def test_authorization_expiry_limits_start_not_completion(valid_plan, authorization) -> None:
    start = begin_transaction(valid_plan, authorization, now=authorization.expires_at_utc)
    assert verify_started_transaction(start, valid_plan, authorization, now=utc_now() + timedelta(days=1)).status == "pass"
    assert begin_transaction(valid_plan, authorization, now=authorization.expires_at_utc + timedelta(microseconds=1)).status == "fail"
    assert compensate(start, authorization, now=utc_now() + timedelta(days=30)).authorized is True


def test_publication_result_is_identity_bound_and_not_caller_asserted(valid_result) -> None:
    assert verify_transaction_result(valid_result).status == "pass"
    valid_result["repository_id"] = valid_result["repository_id"] + 1
    assert build_publication_receipt(valid_result).status == "fail"


@pytest.mark.parametrize(
    "failed_after",
    [
        "evidence_asset_upload",
        "metadata",
        "security_settings",
        "ruleset_or_branch_protection",
        "visibility",
        "public_check_dispatch",
        "release_publish",
        "preliminary_public_verify",
        "transaction_result_persist",
    ],
)
def test_every_publication_failure_restores_full_snapshot_and_tombstones_first(
    publication_fixture, failed_after
) -> None:
    result = inject_failure(publication_fixture, failed_after=failed_after)
    assert result.events.index("tombstone_written") < result.events.index("compensation_started")
    assert result.final_control_plane_sha256 == result.start.prior_control_plane_sha256
    expected_delta = derive_authorized_asset_delta(
        prior=result.start.prior_release_asset_snapshot,
        current=result.pre_compensation_release_asset_snapshot,
        authorized=result.plan.public_evidence_assets,
    )
    assert result.mutation_journal.run_owned_evidence_asset_ids == expected_delta.asset_ids
    assert result.deleted_asset_ids == expected_delta.asset_ids
    assert set(result.deleted_asset_ids).isdisjoint(result.start.prior_release_asset_ids)
    assert result.preexisting_product_assets_unchanged
    assert verify_g7(result.quarantined_receipts, result.plan).status == "fail"


@pytest.mark.parametrize("death_after", ["start", "asset_api_success", "visibility", "release_publish"])
def test_process_death_recovers_from_start_and_journal_without_deleting_prior_assets(
    publication_fixture, death_after
) -> None:
    killed = kill_process_after(publication_fixture, death_after)
    recovered = recover_started_publication(killed.transaction_root)
    assert recovered.events[0] == "tombstone_written"
    assert recovered.redispatched_mutations == 0
    assert set(recovered.deleted_asset_ids).isdisjoint(killed.start.prior_release_asset_ids)
    assert recovered.final_control_plane_sha256 == killed.start.prior_control_plane_sha256


def test_plan_uses_pre_public_sast_as_the_confidentiality_gate(valid_plan) -> None:
    assert set(valid_plan["checks"]["private_capable"]) == {
        "python",
        "typescript",
        "rust",
        "contracts",
        "secret-scan",
        "dependency-audit",
        "license",
        "pre-public-sast",
    }
    assert set(valid_plan["checks"]["public_corroboration"]) == {"codeql", "scorecard"}
    assert valid_plan["checks"]["public_corroboration_is_not_pre_public_evidence"] is True
    assert valid_plan["checks"]["future_pull_request_safeguards"] == ["dependency-review"]


def test_plan_and_live_state_are_bound_to_one_github_controls_policy(valid_plan, controls) -> None:
    assert valid_plan["github_controls_sha256"] == canonical_sha256(controls)
    controls["actions_permissions"]["allowed_actions"] = "all"
    assert preflight(
        valid_plan,
        VALID_AUTHORIZATION,
        VALID_SUBJECT,
        controls=controls,
        security_refresh=VALID_SECURITY_REFRESH,
    ).status == "fail"


def test_blank_pwsh_reconstructs_the_complete_g7_context_and_recovers_without_promote(
    started_publication_fixture,
) -> None:
    result = invoke_g7_recovery_in_blank_pwsh(
        started_publication_fixture,
        inherited_environment=minimal_process_environment(),
    )
    assert result.initializer == "Initialize-G7Context"
    assert result.inherited_path_variables == ()
    assert result.authoritative_root == started_publication_fixture.authoritative_root
    assert result.locked_release_python_verified is True
    assert result.installed_g8_seed_rehashed_against_plan_start_result_and_receipt is True
    assert result.all_authority_paths_are_absolute_and_initializer_owned is True
    assert result.competing_literal_authority_paths == ()
    assert {
        "product_source_root",
        "public_export_root",
        "public_clone_root",
        "release_assets_root",
        "evidence_root",
        "g7_publication_receipt",
        "g7_public_smoke_receipt",
    } <= set(result.explicit_recovery_inputs)
    assert result.recover_calls == 1
    assert result.promote_calls == 0


def test_g5_independent_security_review_scope_covers_all_g7_and_bootstrap_tooling(
    g5_security_review_scope,
) -> None:
    assert {
        "github_preflight",
        "github_publish_transaction_and_recovery",
        "github_public_verify",
        "publication_security_refresh",
        "g7_context_initializer",
        "g7_g8_dependency_free_preexec_runbook",
        "g8_acl_installed_seed_verifier",
        "g8_product_execution_root_bootstrap",
        "g8_product_node_host_wrapper",
        "g8_context_initializer_node_bundle_and_product_node_bootstrap",
        "private_application_repo_bootstrap",
    } <= set(g5_security_review_scope["review_only_material_ids"])


def test_private_application_repo_bootstrap_is_exact_remote_free_and_fail_closed(
    frozen_public_fixture, tmp_path
) -> None:
    destination = tmp_path / "CodeSextant-application"
    result = bootstrap_application_repo(
        public_repo=frozen_public_fixture.public_repo,
        destination=destination,
        product_subject=frozen_public_fixture.subject,
        publication_receipt=frozen_public_fixture.publication_receipt,
        public_smoke_receipt=frozen_public_fixture.public_smoke_receipt,
    )
    assert result.base_commit == frozen_public_fixture.subject.export_commit
    assert result.base_tree_sha256 == frozen_public_fixture.subject.export_tree_sha256
    assert result.branch == "application-private"
    assert result.remotes == ()
    assert result.imported_receipts_are_ignored_and_reverified
    assert bootstrap_application_repo(
        public_repo=frozen_public_fixture.public_repo,
        destination=destination,
        product_subject=frozen_public_fixture.subject,
    ).status == "fail"


def test_g8_product_execution_root_is_content_addressed_sigstore_verified_and_clean(
    frozen_public_fixture, tmp_path
) -> None:
    result = prepare_product_execution_root(
        public_repo=frozen_public_fixture.public_repo,
        product_subject=frozen_public_fixture.subject,
        signing_policy=frozen_public_fixture.signing_policy,
        verifier_bootstrap=frozen_public_fixture.verifier_bootstrap,
        destination_parent=tmp_path,
    )
    assert result.root.name == frozen_public_fixture.subject.sha256
    assert result.release_subject_sha256 == frozen_public_fixture.subject.sha256
    assert result.release_index_sigstore_verified is True
    assert result.root_commit == frozen_public_fixture.subject.export_commit
    assert result.root_tree_sha256 == frozen_public_fixture.subject.export_tree_sha256
    assert result.head_index_worktree_clean is True
    assert result.nonignored_untracked == ()
    assert result.external_review_engine.is_relative_to(result.root)
    assert result.generic_review_schemas_are_relative_to(result.root)
    assert result.locked_python.is_relative_to(result.root)
    assert result.seed_install_receipt_sha256 == frozen_public_fixture.seed_install_receipt.sha256
    assert result.g7_publication_receipt_sha256 == frozen_public_fixture.publication_receipt.sha256
    assert result.g7_public_smoke_receipt_sha256 == frozen_public_fixture.public_smoke_receipt.sha256
    assert result.node_host.is_relative_to(result.root)
    assert result.node_host_sha256 == sha256_file(result.node_host)
    assert verify_product_execution_root(result.receipt, result.root).status == "pass"


def test_g8_seed_verifier_is_authenticated_before_any_product_tree_code_executes(
    g6_seed_install_fixture, g7_authenticated_chain, tmp_path
) -> None:
    trace = prepare_product_root_from_acl_seed(g6_seed_install_fixture, g7_authenticated_chain, tmp_path)
    assert trace.events[:4] == (
        "verify_g6_seed_install_receipt_and_live_acl",
        "verify_signed_release_index",
        "materialize_content_addressed_product_root",
        "verify_fixed_g7_publication_and_public_smoke_chain",
    )
    assert trace.product_tree_processes_before_root == ()
    tamper_one_byte(g6_seed_install_fixture.installed_seed)
    failed = prepare_product_root_from_acl_seed(g6_seed_install_fixture, g7_authenticated_chain, tmp_path / "tampered")
    assert failed.status == "fail"
    assert failed.product_tree_processes_before_root == ()


def test_g6_seed_receipt_and_purpose_verified_g7_chain_are_joint_authority(
    valid_g7_chain, g6_seed_install_fixture
) -> None:
    assert valid_g7_chain["github_publication"]["payload"]["g8_seed_verifier_sha256"] == sha256_file(
        g6_seed_install_fixture.installed_seed
    )
    result = verify_installed_seed_and_g7_chain(
        seed_install_receipt=g6_seed_install_fixture.receipt,
        installed_seed=g6_seed_install_fixture.installed_seed,
        g7_chain=valid_g7_chain,
    )
    assert result.status == "pass"
    assert result.seed_install_receipt_recomputed is True
    assert result.g7_purpose_verifier_passed is True


def test_forged_g7_receipt_and_matching_environment_hash_cannot_self_authenticate(
    valid_g7_chain, g6_seed_install_fixture
) -> None:
    forged = forge_publication_receipt_and_rehash(valid_g7_chain["github_publication"])
    environment = {
        "CODESEXTANT_G7_PUBLICATION_RECEIPT": str(forged.path),
        "CODESEXTANT_G7_PUBLICATION_RECEIPT_SHA256": sha256_file(forged.path),
        "CODESEXTANT_G8_SEED_VERIFIER": str(g6_seed_install_fixture.installed_seed),
    }
    assert verify_installed_seed_and_g7_chain(
        seed_install_receipt=g6_seed_install_fixture.receipt,
        installed_seed=g6_seed_install_fixture.installed_seed,
        g7_chain=valid_g7_chain,
        environment=environment,
    ).status == "fail"


def test_fresh_shell_verifies_root_and_initializer_before_dot_source(
    g6_seed_install_fixture, valid_product_execution_root
) -> None:
    trace = invoke_g8_fresh_shell_prelude(
        seed_install=g6_seed_install_fixture,
        product_root=valid_product_execution_root.root,
        product_root_receipt=valid_product_execution_root.receipt,
        empty_environment=True,
    )
    assert trace.events[:5] == (
        "winverifytrust_static_verifier_and_pin_leaf_certificate",
        "verify_static_verifier_and_seed_trustedinstaller_exact_acl",
        "execute_static_verifier_and_verify_signed_seed_install_receipt",
        "verify_complete_product_execution_root",
        "dot_source_verified_g8_initializer",
    )
    tamper_one_byte(valid_product_execution_root.root / "release/Initialize-CodeSextantG8.ps1")
    failed = invoke_g8_fresh_shell_prelude(
        seed_install=g6_seed_install_fixture,
        product_root=valid_product_execution_root.root,
        product_root_receipt=valid_product_execution_root.receipt,
        empty_environment=True,
    )
    assert failed.status == "fail"
    assert failed.dot_sourced_files == ()


def test_g7_blank_shell_uses_acl_seed_before_dot_sourcing_initializer(
    g6_seed_install_fixture, frozen_g7_root
) -> None:
    trace = invoke_g7_fresh_shell_prelude(
        seed_install_receipt=g6_seed_install_fixture.receipt,
        frozen_root=frozen_g7_root,
        inherited_environment=forged_receipt_and_hash_environment(),
    )
    assert trace.events[:4] == (
        "winverifytrust_static_verifier_and_pin_leaf_certificate",
        "verify_static_verifier_trustedinstaller_owner_protected_exact_dacl_and_parent_no_reparse",
        "execute_fixed_g6_native_static_verifier",
        "verify_signed_g6_receipt_live_seed_static_sha_exact_acl_and_parent_no_reparse",
    )
    assert trace.events[4:6] == (
        "verify_g7_initializer_and_complete_frozen_closure",
        "dot_source_authenticated_g7_initializer",
    )
    assert trace.dot_sourced_files == (frozen_g7_root / "release/Initialize-CodeSextantG7.ps1",)
    tamper_one_byte(frozen_g7_root / "release/Initialize-CodeSextantG7.ps1")
    failed = invoke_g7_fresh_shell_prelude(
        seed_install_receipt=g6_seed_install_fixture.receipt,
        frozen_root=frozen_g7_root,
        inherited_environment=minimal_process_environment(),
    )
    assert failed.status == "fail"
    assert failed.dot_sourced_files == ()
    assert "G7-INITIALIZER-CANARY" not in failed.executed_canaries


@pytest.mark.parametrize(
    "forgery",
    [
        "static_verifier_unsigned",
        "static_verifier_wrong_authenticode_leaf",
        "static_verifier_owner_not_trustedinstaller",
        "static_verifier_extra_allow_ace",
        "static_verifier_inherited_ace",
        "seed_owner_not_trustedinstaller",
        "seed_extra_allow_ace",
        "seed_inherited_ace",
        "parent_reparse",
        "matching_forged_receipt_hash",
    ],
)
def test_g7_static_bootstrap_blocks_acl_and_receipt_forgery_before_seed_execution(
    g6_seed_install_fixture, frozen_g7_root, forgery
) -> None:
    forged = mutate_seed_trust_fixture(g6_seed_install_fixture, forgery)
    trace = invoke_g7_fresh_shell_prelude(
        seed_install_receipt=forged.receipt,
        frozen_root=frozen_g7_root,
        inherited_environment=forged.environment,
    )
    assert trace.status == "fail"
    assert trace.static_verifier_processes == ()
    assert trace.seed_processes == ()
    assert trace.dot_sourced_files == ()
    assert trace.executed_canaries == ()


def test_generated_preexec_runbook_defines_trust_primitives_before_call_and_has_no_placeholder(
    generated_publication_runbook, g8_authenticode_signing_policy, g6_signed_asset_manifest
) -> None:
    source = generated_publication_runbook.read_text(encoding="utf-8")
    assert source.index("function Assert-PinnedAuthenticodeWinTrust") < source.index(
        "Assert-PinnedAuthenticodeWinTrust -LiteralPath"
    )
    assert source.index("function Assert-CodeSextantFixedTrustAcl") < source.index(
        "Assert-CodeSextantFixedTrustAcl -LiteralPath"
    )
    assert not imports_or_dot_sources_project_code_before_static_verifier(source)
    assert not contains_placeholder_or_environment_pin(source)
    assert extract_embedded_leaf_cert_der_sha256(source) == g8_authenticode_signing_policy.leaf_cert_der_sha256
    assert g6_signed_asset_manifest.static_verifier_leaf_cert_der_sha256 == g8_authenticode_signing_policy.leaf_cert_der_sha256
    assert len(extract_embedded_leaf_cert_der_sha256(source)) == 64
    assert set(g6_signed_asset_manifest.roles) == {
        "g8_seed_verifier", "g8_seed_static_verifier", "g8_seed_installer",
        "g6_context_preflight", "g6_runbook_launcher",
    }
    assert "g7_g8_preexec_runbook" not in g6_signed_asset_manifest.roles
    assert authenticode_verify(generated_publication_runbook).leaf_cert_der_sha256 == extract_embedded_leaf_cert_der_sha256(source)


def test_authenticode_policy_schema_object_is_shared_by_all_consumers(real_authenticode_policy_json) -> None:
    policy = load_authenticode_policy(real_authenticode_policy_json)
    assert set(policy) >= {"leaf_cert_der_sha256", "rfc3161_timestamp_url", "timestamp_policy"}
    assert "leaf_der_sha256" not in policy
    assert "timestamp_url" not in policy
    for consumer in (runbook_renderer, runbook_signer, native_runbook_launcher, wintrust_verifier, g6_asset_manifest_verifier):
        observed = consumer.load_policy(real_authenticode_policy_json)
        assert observed.leaf_cert_der_sha256 == policy["leaf_cert_der_sha256"]
        assert observed.rfc3161_timestamp_url == policy["rfc3161_timestamp_url"]
        assert observed.timestamp_policy == policy["timestamp_policy"]


@pytest.mark.parametrize(
    "action",
    ["publication-g7", "publication-g8", "bootstrap-private", "resume-private-development"],
)
def test_wrong_but_trusted_publication_runbook_signer_executes_zero_runbook_code(
    installed_g6_runbook_launcher, generated_publication_runbook, action
) -> None:
    forged = resign_with_other_os_trusted_publisher(generated_publication_runbook)
    trace = installed_g6_runbook_launcher.run_fixed(
        runbook=forged,
        action=action,
        require_subject=True,
    )
    assert trace.winverifytrust_status == "trusted"
    assert trace.leaf_pin_status == "mismatch"
    assert trace.runbook_process_created is False
    assert trace.runbook_code_execution_count == 0
    assert trace.dot_sourced_files == ()


def test_public_g7_launch_policy_has_actual_closed_specs_and_no_private_g8_rows(
    public_receipt_registry, public_launch_policy, verification_authorities
) -> None:
    g7_rows = public_receipt_registry["G7"]
    assert {row["filename"] for row in g7_rows} == {
        "publication-security-refresh.json", "github-publication.json", "public-smoke.json",
    }
    assert set(public_receipt_registry) == {f"G{i}" for i in range(8)}
    public_rows = [row for gate in sorted(public_receipt_registry) for row in public_receipt_registry[gate]]
    assert len(public_rows) == 20
    assert len({row["filename"] for row in public_rows}) == 20
    assert set(public_launch_policy["launch_specs"]) == {row["launch_spec_id"] for row in public_rows}
    for row in g7_rows:
        assert set(row) == {
            "filename", "producer_id", "launch_spec_id", "schema", "payload_schema",
            "depends_on", "material_edges",
        }
        spec = public_launch_policy["launch_specs"][row["launch_spec_id"]]
        assert spec["producer_id"] == row["producer_id"]
        assert spec["entrypoint_sha256"] == sha256_file(
            verification_authorities.resolve(spec["authority_id"], spec["entrypoint"])
        )
        assert spec["runtime"]["sha256"] == sha256_file(
            verification_authorities.resolve(spec["runtime"]["authority_id"], spec["runtime"]["path"])
        )
        assert spec["candidate_transport"] == "inherited_exclusive_handle"
    assert not any(spec_id.startswith("g8_") for spec_id in public_launch_policy["launch_specs"])


def test_only_atomic_generic_launcher_writes_registered_g7_g8_receipts(publication_runbook) -> None:
    registered = {
        "publication-security-refresh.json",
        "github-publication.json",
        "public-smoke.json",
        "claude-oss-application-tool-review.json",
        "claude-oss-terms.json",
        "claude-oss-packet.json",
        "claude-oss-review.json",
        "claude-oss-authorization.json",
        "claude-oss-submission.json",
    }
    for filename in registered:
        flow = publication_runbook.receipt_flow(filename)
        assert flow.public_candidate_paths == ()
        assert flow.commands == ("tools/release_gate.py produce-and-seal",)
        assert flow.final_writer == "tools/release_gate.py produce-and-seal"
        assert flow.inherited_candidate_transport == "inherited_exclusive_handle"
        assert flow.produce_and_seal_precedes_every_consumer is True
        assert flow.verification_context_has_explicit_authenticated_roots is True


@pytest.mark.parametrize(
    "authority_id",
    ["product_source", "public_export", "public_clone", "private_application", "evidence", "release_assets"],
)
def test_produce_and_seal_and_check_reject_decoy_swapped_or_escaping_authority_roots(
    valid_verification_context, registered_receipt_request, authority_id, tmp_path
) -> None:
    forged = decoy_context_with_same_relative_path_and_matching_candidate_digest(
        valid_verification_context, authority_id, tmp_path
    )
    assert release_gate_produce_and_seal(registered_receipt_request, context=forged).status == "fail"
    assert release_gate_check(context=forged).status == "fail"
    assert forged.executed_materials == ()


def test_public_clone_authority_cannot_alias_or_swap_with_public_export(valid_verification_context) -> None:
    aliased = replace(valid_verification_context, public_clone_root=valid_verification_context.public_export_root)
    assert release_gate_check(context=aliased).status == "fail"
    swapped = replace(
        valid_verification_context,
        public_clone_root=valid_verification_context.public_export_root,
        public_export_root=valid_verification_context.public_clone_root,
    )
    assert release_gate_check(context=swapped).status == "fail"


def test_g8_registry_paths_equal_generated_evidence_ssot(g8_registry_extension, generated_private_evidence_paths) -> None:
    declared = {
        edge["path"]
        for row in g8_registry_extension["G8"]
        for edge in row["material_edges"]
        if edge["kind"] == "evidence_file"
    }
    expected = {
        "g8-product-execution-root.json",
        "claude-oss-application-form-contract.json",
        "claude-oss-application-tool-findings.json",
        "claude-oss-application-tool-review-input.json",
        "claude-oss-application-tool-review-request.json",
        "claude-oss-application-tool-scan.json",
        "claude-oss-application-tool-subject.json",
        "claude-oss-browser-confirmation-source.json",
        "claude-oss-confirmation.json",
        "claude-oss-confirmation-runtime.json",
        "claude-oss-evidence-authority-responses/manifest.json",
        "claude-oss-evidence-input.json",
        "claude-oss-evidence-input-request.json",
        "claude-oss-evidence-refresh.json",
        "claude-oss-pre-click.json",
        "claude-oss-pre-submit-form.json",
        "claude-oss-pre-submit-runtime.json",
        "claude-oss-review-input.json",
        "claude-oss-review-request.json",
        "claude-oss-submission-start.json",
        "claude-oss-target-profile.json",
        "claude-oss-terms-source.json",
        "claude-oss-user-confirmation.json",
    }
    assert declared
    assert declared == expected
    expected_generated = {f"release/evidence/{path}" for path in expected}
    assert expected_generated == (generated_private_evidence_paths & expected_generated)
    assert not any(path.startswith("release/evidence/") for path in declared)
    stale_private_evidence_prefix = "application/claude-for-oss/" + "evidence/"
    assert not any(path.startswith(stale_private_evidence_prefix) for path in declared)
    assert all(edge["authority_id"] in CLOSED_VERIFICATION_AUTHORITY_IDS for row in g8_registry_extension["G8"] for edge in row["material_edges"])


def test_private_g8_launch_specs_are_closed_digest_bound_and_registry_referenced(
    g8_registry_extension, g8_launch_policy_extension, application_tool_subject,
    verification_authorities,
) -> None:
    expected_keys = {
        "producer_id", "authority_id", "entrypoint", "entrypoint_sha256", "runtime",
        "argv_prefix", "candidate_transport", "signer_mode",
    }
    expected_specs = {
        "g8_application_tool_review_v1": ("g8_application_tool_review", "product_source", "tools/external_security_review.py", ["receipt-and-verify"], "none"),
        "g8_terms_v1": ("g8_terms", "private_application", "application/claude-for-oss/refresh_terms.py", ["seal"], "none"),
        "g8_packet_v1": ("g8_packet", "private_application", "application/claude-for-oss/build_packet.py", [], "none"),
        "g8_claim_review_v1": ("g8_claim_review", "private_application", "application/claude-for-oss/review_packet.py", ["emit"], "os_credential_ed25519"),
        "g8_authorization_v1": ("g8_authorization", "private_application", "application/claude-for-oss/authorize_packet.py", ["authorize"], "external_attestation_only"),
        "g8_submission_v1": ("g8_submission", "private_application", "application/claude-for-oss/record_submission.py", ["receipt"], "none"),
    }
    for row in g8_registry_extension["G8"]:
        assert set(row) == {
            "filename", "producer_id", "launch_spec_id", "schema", "payload_schema",
            "depends_on", "material_edges",
        }
        spec = g8_launch_policy_extension["launch_specs"][row["launch_spec_id"]]
        expected = expected_specs[row["launch_spec_id"]]
        assert row["producer_id"] == spec["producer_id"]
        assert (spec["producer_id"], spec["authority_id"], spec["entrypoint"], spec["argv_prefix"], spec["signer_mode"]) == expected
        assert set(spec) == expected_keys or set(spec) == expected_keys | {"role_launcher"}
        assert spec["candidate_transport"] == "inherited_exclusive_handle"
        assert spec["entrypoint_sha256"] == sha256_file(
            verification_authorities.resolve(spec["authority_id"], spec["entrypoint"])
        )
        assert set(spec["runtime"]) == {"authority_id", "path", "version", "sha256"}
        assert spec["runtime"]["sha256"] == sha256_file(
            verification_authorities.resolve(spec["runtime"]["authority_id"], spec["runtime"]["path"])
        )
        if spec["authority_id"] == "private_application":
            assert application_tool_subject.binds(spec["entrypoint"], spec["entrypoint_sha256"])
        assert isinstance(spec["argv_prefix"], list) and all(isinstance(v, str) for v in spec["argv_prefix"])
        assert spec["signer_mode"] in {"none", "os_credential_ed25519", "external_attestation_only"}
        assert ("role_launcher" in spec) is (spec["signer_mode"] == "os_credential_ed25519")
        if "role_launcher" in spec:
            assert set(spec["role_launcher"]) == {
                "authority_id", "path", "sha256", "role", "credential_name",
                "allowed_key_env", "forbidden_key_env", "role_registry_path",
                "role_registry_sha256", "implementation_actors_path",
                "implementation_actors_sha256", "signing_env_registry_path",
                "signing_env_registry_sha256", "reserved_key_env_pattern",
            }
    assert set(g8_launch_policy_extension["launch_specs"]) == set(expected_specs)


def test_each_g8_registered_receipt_has_closed_producer_input_manifest(
    g8_registry_extension, evidence_authority
) -> None:
    for row in g8_registry_extension["G8"]:
        edges = [edge for edge in row["material_edges"] if edge["material_id"] == "producer_inputs"]
        assert len(edges) == 1
        edge = edges[0]
        assert edge["kind"] == "input_manifest"
        assert edge["authority_id"] == "evidence"
        assert edge["path"] == f"inputs/{Path(row['filename']).stem}.inputs.json"
        assert edge["sha256_pointer"] == "/material_digests/producer_inputs"
        assert edge["canonicalization"] == "jcs"
        assert edge["required_roles"]
        manifest = load_jcs(evidence_authority / edge["path"])
        assert [entry["role"] for entry in manifest["entries"]] == edge["required_roles"]
        assert all(set(entry) in (
            {"role", "kind", "authority_id", "path", "sha256", "canonicalization"},
            {"role", "kind", "authority_id", "path", "size", "sha256", "canonicalization"},
        ) for entry in manifest["entries"])
        assert recursively_rehash_manifest(manifest).status == "pass"


def test_f1_is_public_only_and_private_merge_is_post_application_subject(
    validation_chronology, g8_registry_extension
) -> None:
    assert validation_chronology.f1.required_gates == tuple(f"G{i}" for i in range(8))
    assert validation_chronology.f1.registry_extensions == ()
    assert validation_chronology.f1.launch_policy_extensions == ()
    assert validation_chronology.g8.application_tool_subject_created_before_merge is True
    assert validation_chronology.g8.extensions_generated_after_application_tool_subject is True
    assert validation_chronology.g8.generated_extensions_are_subject_members is False
    assert validation_chronology.g8.every_receipt_binds_both_extension_digests is True
    assert validation_chronology.g8.release_gate_authority == "authenticated_product_root"
    assert validation_chronology.g8.validate_registry_argv.has("--registry-extension")
    assert not validation_chronology.g8.validate_registry_argv.has("--launch-policy-extension")
    assert validation_chronology.g8.validate_launch_policy_argv.has_all(
        "--registry-extension", "--launch-policy-extension",
        "--require-entrypoint-digests", "--require-all-signer-policies",
    )
    review_inputs = next(
        edge for edge in g8_registry_extension["G8"][0]["material_edges"]
        if edge["material_id"] == "producer_inputs"
    )
    assert {
        "public_receipt_registry", "public_producer_launch_policy",
        "global_signing_environment_registry",
        "private_receipt_registry_extension", "private_producer_launch_policy_extension",
        "merged_registry_launch_policy_closure",
    } <= set(review_inputs["required_roles"])


def test_blank_shell_private_development_resume_rebuilds_locked_context_without_mutation(
    installed_g6_runbook_launcher, existing_private_development_fixture
) -> None:
    trace = run_in_blank_pwsh(
        installed_g6_runbook_launcher,
        action="resume-private-development",
        fixture=existing_private_development_fixture,
        inherited_environment={},
    )
    assert trace.status == "pass"
    assert trace.runbook_authenticated_before_process is True
    assert trace.product_execution_root_verified is True
    assert trace.private_overlay_audited is True
    assert trace.release_python == existing_private_development_fixture.locked_release_python
    assert trace.returned_paths_are_absolute is True
    assert trace.created_paths == ()
    assert trace.modified_paths == ()
    assert trace.deleted_paths == ()
    assert trace.git_mutations == ()


def test_g8_signing_environment_inventory_is_exact_and_forbidden_sets_are_derived(
    global_signing_environment_registry, product_release_subject,
    private_role_inventory, g8_launch_policy_extension,
) -> None:
    g8_allowed_names = {
        "CODESEXTANT_APPLICATION_REVIEWER_SIGNING_KEY",
        "CODESEXTANT_APPLICATION_TOOL_REVIEW_REQUESTER_SIGNING_KEY",
        "CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_SIGNING_KEY",
    }
    global_known = {row["key_env"] for row in global_signing_environment_registry["roles"]}
    assert global_signing_environment_registry.raw_sha256 == product_release_subject.material_sha256(
        "global_signing_environment_registry"
    )
    assert g8_allowed_names <= global_known
    expected_allowed = {
        "application_tool_review_requester": {"CODESEXTANT_APPLICATION_TOOL_REVIEW_REQUESTER_SIGNING_KEY"},
        "independent_tool_security_reviewer": {"CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_SIGNING_KEY"},
        "claim_signer": {"CODESEXTANT_APPLICATION_REVIEWER_SIGNING_KEY"},
        "tool_review_verifier": set(),
        "claim_verifier": set(),
        "receipt_verifier": set(),
    }
    assert set(private_role_inventory) == set(expected_allowed)
    assert set().union(*expected_allowed.values()) == g8_allowed_names
    for role, allowed in expected_allowed.items():
        assert set(private_role_inventory[role]["allowed_key_env"]) == allowed
        assert set(private_role_inventory[role]["forbidden_key_env"]) == global_known - allowed
    claim_launcher = g8_launch_policy_extension["launch_specs"]["g8_claim_review_v1"]["role_launcher"]
    assert claim_launcher["allowed_key_env"] == next(iter(expected_allowed["claim_signer"]))
    assert set(claim_launcher["forbidden_key_env"]) == global_known - expected_allowed["claim_signer"]
    assert claim_launcher["signing_env_registry_path"] == "release/signing-environment-registry.json"
    assert claim_launcher["signing_env_registry_sha256"] == global_signing_environment_registry.raw_sha256
    assert claim_launcher["reserved_key_env_pattern"] == global_signing_environment_registry["reserved_pattern"]
    assert invoke_review_role_with_environment(
        role="claim_signer",
        environment={"CODESEXTANT_UNREGISTERED_SIGNING_KEY": "canary"},
    ).status == "fail"


def test_product_frozen_node_host_loads_only_authenticated_absolute_bootstrap(
    valid_node_context, tmp_path
) -> None:
    ambient = {"codeSextantG8ProductBootstrap": malicious_canary("AMBIENT-GLOBAL-CANARY")}
    result = run_product_node_host(
        host_module=PRODUCT_NODE_HOST,
        bootstrap_module=PRODUCT_NODE_BOOTSTRAP.resolve(),
        bootstrap_sha256=sha256_file(PRODUCT_NODE_BOOTSTRAP),
        node_context=valid_node_context,
        ambient_globals=ambient,
    )
    assert result.status == "pass"
    assert result.bootstrap_import_path == PRODUCT_NODE_BOOTSTRAP.resolve()
    assert result.namespace_is_frozen is True
    assert result.ambient_globals_consumed == ()
    assert "AMBIENT-GLOBAL-CANARY" not in result.executed_canaries
    assert run_product_node_host(
        host_module=PRODUCT_NODE_HOST,
        bootstrap_module=relative_or_tampered_bootstrap(tmp_path),
        bootstrap_sha256=sha256_file(PRODUCT_NODE_BOOTSTRAP),
        node_context=valid_node_context,
        ambient_globals=ambient,
    ).status == "fail"


def test_product_execution_root_receipt_binds_verifier_schema_commit_tree_and_python(
    valid_product_execution_root
) -> None:
    receipt = valid_product_execution_root.receipt
    assert receipt.bootstrap_verifier_sha256 == sha256_file(PRODUCT_BOOTSTRAP_VERIFIER)
    assert receipt.receipt_schema_sha256 == sha256_file(PRODUCT_EXECUTION_ROOT_SCHEMA)
    assert receipt.root_commit == PRODUCT_SUBJECT.export_commit
    assert receipt.root_tree_sha256 == PRODUCT_SUBJECT.export_tree_sha256
    assert receipt.release_index_sha256 == PRODUCT_SUBJECT.release_index_sha256
    assert receipt.release_python_lock_sha256 == sha256_file(RELEASE_LOCK)
    tamper_one_byte(valid_product_execution_root.root / "tools/external_security_review.py")
    assert verify_product_execution_root(receipt, valid_product_execution_root.root).status == "fail"


def test_private_overlay_is_additive_only_and_product_paths_are_byte_identical(
    valid_private_application_repo, product_subject
) -> None:
    assert audit_private_overlay(
        valid_private_application_repo,
        product_subject,
        allowed_additions=("application/claude-for-oss/**", "tests/application/**"),
    ).status == "pass"
    for mutation in (
        modify_existing_product_path(),
        delete_existing_product_path(),
        add_outside_private_namespaces(),
        stage_without_commit(),
        add_nonignored_untracked(),
    ):
        repo = valid_private_application_repo.clone_fixture()
        mutation.apply(repo)
        assert audit_private_overlay(repo, product_subject).status == "fail"


def test_private_code_is_never_loaded_before_product_bootstrap_and_overlay_audit(
    g8_blank_shell_trace,
) -> None:
    assert g8_blank_shell_trace.events[:3] == (
        "verify_product_execution_root",
        "audit_private_overlay",
        "emit_canonical_absolute_context_bundle",
    )
    assert g8_blank_shell_trace.first_private_import_index > g8_blank_shell_trace.events.index(
        "audit_private_overlay"
    )
    assert g8_blank_shell_trace.g8_initializer_path.is_relative_to(
        g8_blank_shell_trace.product_execution_root
    )
    assert g8_blank_shell_trace.private_initializer_imports == ()


@pytest.mark.parametrize("workflow", ["G7", "G8"])
def test_prelude_routes_transaction_state_before_any_cleanup_or_producer(
    workflow, started_transaction_fixture
) -> None:
    trace = invoke_blank_shell_prelude(workflow, started_transaction_fixture)
    assert trace.events[0] == "classify_transaction_state"
    assert trace.mode == "recovery_only"
    assert trace.deleted_paths == ()
    assert trace.forward_producer_calls == 0
    assert trace.external_effect_redispatches == 0


@pytest.mark.parametrize("failure", ["crash_before_generic_gate", "tampered", "missing_input", "wrong_rerun"])
def test_recovery_complete_requires_same_full_verifier_and_generic_registry_gate(
    complete_transaction_fixture, failure
) -> None:
    recovered = recover_fixture(complete_transaction_fixture, inject=failure)
    assert recovered.full_chain_verifier_calls == 1
    assert recovered.generic_registry_gate_calls == 1
    if complete_transaction_fixture.workflow == "G8":
        assert {
            "product_execution_root_receipt",
            "g7_publication_receipt",
            "g7_public_smoke_receipt",
            "evidence_input_request",
            "evidence_authority_response_root",
            "evidence_authority_response_manifest",
            "evidence_input",
        } <= set(recovered.full_chain_explicit_input_names)
        assert recovered.generic_registry_gate_executable_is_product_root_absolute is True
    if failure == "crash_before_generic_gate":
        assert recovered.status == "complete"
    else:
        assert recovered.status in {"tombstoned", "compensated"}
        assert recovered.forward_producer_calls == 0


def test_runbook_ast_has_no_cleanup_before_state_route_and_reaudits_every_effect_entry(
    parsed_plan_runbooks,
) -> None:
    for workflow in (parsed_plan_runbooks.g7, parsed_plan_runbooks.g8):
        assert workflow.preexec_events[:3] == (
            "winverifytrust_and_pin_static_verifier",
            "verify_programdata_trustedinstaller_acl_and_no_reparse",
            "execute_authenticated_static_verifier",
        )
        assert workflow.first_transaction_operation == "classify_transaction_state"
        assert workflow.cleanup_before_state_route == ()
        assert workflow.producer_cleanup_without_no_start_guard == ()
        assert workflow.external_effect_or_recovery_entries
        assert all(entry.reverifies_clean_trust_closure for entry in workflow.external_effect_or_recovery_entries)
    assert parsed_plan_runbooks.g7.operational_relative_executable_or_schema_paths == ()
    assert parsed_plan_runbooks.g8.operational_relative_executable_or_schema_paths == ()
    assert parsed_plan_runbooks.g7.dot_source_before_acl_seed_authentication == ()
    assert parsed_plan_runbooks.g8.stage_entry_trust_assertions == {
        "G8.1", "G8.2", "G8.3", "G8.4", "G8.5", "G8.6"
    }
    assert parsed_plan_runbooks.g8.post_interaction_trust_assertions_are_complete is True
    assert parsed_plan_runbooks.g8.start_to_click_events[-2:] == (
        "assert_trust_closure",
        "atomic_verify_and_click",
    )
~~~

release/github.json contains:

~~~json
{
  "owner": "Zeroxrain99",
  "repository": "CodeSextant",
  "default_branch": "main",
  "visibility": "public",
  "description": "Local-first code intelligence for AI agents: precise references, impact analysis, repository maps, and reproducible benchmarks.",
  "topics": [
    "code-intelligence",
    "static-analysis",
    "mcp",
    "tree-sitter",
    "rust",
    "developer-tools",
    "code-graph",
    "ai-agents",
    "impact-analysis"
  ],
  "license_spdx": "Apache-2.0"
}
~~~

**Step 2: Run RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_exact_task_commit.py tests/release/test_github_preflight.py tests/release/test_github_publish.py tests/release/test_github_public_verify.py tests/release/test_publication_security_refresh.py tests/release/test_application_repo_bootstrap.py tests/release/test_g7_fresh_shell.py tests/release/test_g8_trusted_bootstrap.py tests/release/test_transaction_entry_routing.py tests/release/test_publication_application_runbook_static.py -q
if ($LASTEXITCODE -eq 0) { throw 'Task 1 RED suite unexpectedly passed before the explicit-repository-root and G7/G8 implementations exist' }
~~~

Expected: FAIL because tools.github_preflight and tools.publication_security_refresh do not exist.

**Step 3: Implement immutable publication-plan validation**

~~~python
@dataclass(frozen=True)
class PublicationPlan:
    transaction_id: UUID
    subject_sha256: str
    github_identity_sha256: str
    check_policy_sha256: str
    github_controls_sha256: str
    publication_security_refresh_sha256: str
    release_index_sha256: str
    verifier_bootstrap_sha256: str
    g8_seed_verifier_sha256: str
    source_commit: str
    export_commit: str
    release_tag: str
    artifacts: tuple[ArtifactIdentity, ...]
    public_evidence_assets: tuple[AssetIdentity, ...]
    gates: Mapping[str, GateReceiptIdentity]
    destination: GitHubDestination
    compensation: PublicationCompensation
    residual_risk: PublicationResidualRisk


def publication_plan_digest(plan: Mapping[str, object]) -> str:
    """SHA-256 canonical plan JSON; authorization is never part of this payload."""


def preflight(
    plan: Mapping[str, object],
    authorization: Mapping[str, object],
    subject: Mapping[str, object],
    controls: Mapping[str, object],
    security_refresh: Mapping[str, object],
) -> CheckResult:
    """Validate ReleaseSubject, G0-G6, controls, fresh security evidence, destination, and authorization without mutation."""
~~~

tools/publication_security_refresh.py owns the G7 domain producer selected by `producer_id=publication_security_refresh` and `launch_spec_id=publication_security_refresh_v1`. It re-fetches the official Python, Node.js, RustSec, PyPA, npm, GitHub Advisory Database, Semgrep-ruleset, and selected runtime-vendor security channels named by the frozen G5 policy; reruns every locked dependency audit and pre-public SAST command against the exact `$exportRoot`; verifies the signed independent-security-review statement; and binds ReleaseSubject, export commit/tree, artifact manifest, runtime support closure, SBOM, G5 security receipt, independent review, scanner/ruleset/lock digests, feed response hashes, timestamps, and observed version/supersession facts. Its schema has no caller-supplied `pass` shortcut. It emits PASS only through the inherited exclusive handle when the rerun is clean, every upstream response is authenticated HTTPS from the allowlisted official host, no high/critical or unreviewed security finding exists, no dependency/runtime is superseded for security, and no pending security release is announced. The producer performs no GitHub mutation. The typed registry row has exactly `filename`, `producer_id`, `launch_spec_id`, `schema`, `payload_schema`, `depends_on`, and `material_edges`; command strings and omitted edge arrays are invalid. Task 1 phase-generates the public producer launch policy through `G7_FINAL` from actual final entrypoint/runtime bytes and exact registry rows before tests/staging; F1 later enforces `FINAL_PRE_FREEZE` exact public closure. Private G8 specs remain absent and later live only in the ApplicationToolSubject-bound extension.

tools/github_publish.py owns idempotent `record-identity`, `verify-identity`, `collect-public-evidence`, `plan`, `show-authorization-request`, `record-authorization`, `promote`, compensating `rollback`, and the domain receipt operation selected only by its G7 launch spec. Before `plan`, the G6-owned absolute `install_g8_seed.py verify` path validates the fixed signed authority `%ProgramData%\CodeSextant\Trust\G8\g8-seed-install.json`, schema, ReleaseSubject, authenticated static-verifier and seed assets, installed paths, Authenticode leaf pin, live file IDs, exact TrustedInstaller owner/DACL, and no-follow/no-reparse state. The `release/evidence/g8-seed-install.json` copy is only a byte-identical, digest-bound gate mirror and can never select a path, digest, or executable. Plan/start/result/`github-publication` bind the authoritative `g8_seed_install_receipt_sha256`, independently recomputed static-verifier SHA-256, and independently recomputed `g8_seed_verifier_sha256`; neither a mirror/caller receipt nor matching caller hashes can substitute. Identity, controls, fresh security, signed-index, verifier-bootstrap, transaction, repository, and irreversible-compensation contracts remain closed and subject-bound. `promote` writes start before mutation, carries the same seed receipt/live-asset digests through result, and never accepts caller pass fields. The handle-only domain producer re-runs the G6 verifier and re-hashes all three before the atomic generic final write. `github_public_verify.py` validates public metadata, exact controls, product/evidence asset set, Sigstore bundles, clean-clone lifecycle, transaction timing, and the complete plan/start/result/publication chain; public smoke digest-binds the registered publication receipt. A missing/extra asset, stale refresh, wrong fixed receipt/live verifier/seed, dirty export, wrong signer, subject mismatch, or failed public corroboration is fatal. Third-party assets retain their original licenses and notices.

`publication-start` contains only the immutable prior asset/control-plane snapshot, including every pre-existing release asset ID/name/hash; it can never contain IDs allocated by later mutations. `publication-mutation-journal` is an ignored, schema-valid, hash-chained append-only transaction log. After each successful authorized API mutation it records the operation, response hash, and any newly allocated ID before the next mutation. `publication-result` binds the journal's final digest and repeats the observed run-owned IDs. On process restart, an existing start without a valid result or tombstone enters recovery instead of promotion: recovery writes the tombstone first, performs no new forward mutation, and reconciles any crash gap by deriving `(current assets - prior asset snapshot) intersect exact authorized evidence names and hashes`. Only that derived set may be deleted; a prior asset ID is never deletable even if its name collides. The same start/journal authority compensates failures in preliminary public verification and atomic result persistence.

`release/Initialize-CodeSextantG7.ps1` defines the idempotent `Initialize-G7Context` function used by every operational G7 shell, including recovery, but it is never the first trusted executable. Before F1, G5 commits and independently reviews `release/g8-authenticode-signing-policy.json`, containing the concrete leaf-certificate raw-DER SHA-256, exact issuer, code-signing EKU, timestamp authority/policy, and whole-chain revocation requirements; it is an immutable ReleaseSubject input, not an F4 output. `tools/render_publication_runbook.py` reads that precommitted policy and deterministically renders the unsigned body of tracked `release/Invoke-CodeSextantPublication.ps1`, expanding complete dependency-free inline definitions of `Assert-PinnedAuthenticodeWinTrust` and `Assert-CodeSextantFixedTrustAcl` before their first call and embedding the concrete 64-hex pin as a literal. The renderer rejects placeholders, imports, dot-sources, dynamic code/downloads, file/env/receipt/argument pin sources, or a pin unequal to the pre-F1 policy. Task 1 renders twice and byte-compares the unsigned bodies, signs the tracked file with the policy-authorized leaf/timestamp service, verifies WinTrust/pin/timestamp, strips only the Authenticode signature block, and requires the recovered body digest to equal the deterministic unsigned-body digest. Signed bytes themselves are not claimed deterministic.

Build-time proof is not launch authority. The exact G6 trust set now has five roles: `g8_seed_verifier`, `g8_seed_static_verifier`, `g8_seed_installer`, `g6_context_preflight`, and `g6_runbook_launcher`. F5 installs the dependency-closed native launcher at `%ProgramData%\CodeSextant\Trust\G6\codesextant-g6-runbook-launcher.exe`, with its file ID/hash and embedded pre-F1 leaf-DER pin bound by the machine-signed monotonic G6 authority and with exact TrustedInstaller/protected ACL/no-reparse state. That already-authenticated native launcher—not `pwsh`, the tracked runbook, or a source-tree helper—is the first project executable for every G7/G8 publication operation. Its closed `run-fixed` operation opens `release/Invoke-CodeSextantPublication.ps1` without following reparses, performs OS WinVerifyTrust with whole-chain revocation and the required RFC3161 timestamp, constant-time matches the actual signer leaf DER against its compiled literal pin, verifies exact ReleaseSubject path/file-ID/raw-byte identity, and only then creates `pwsh -NoProfile -File` over the same revalidated file identity. A generally trusted but wrong publisher is fatal before process creation. No direct `-File`, dot-source, or shell invocation of the publication runbook is permitted. The signed tracked runbook remains separately review-/ReleaseSubject-bound source, not a sixth G6 asset.

Only after that external self-authentication do the generated runbook regions below execute their inline checks as defense in depth. Their prelude authenticates the fixed native bootstrap `%ProgramData%\CodeSextant\Trust\G8\codesextant-g8-seed-static-verify.exe`; with its embedded precommitted installer public key and no dynamic dependency, that verifier validates the domain-separated JCS signature on the fixed G6 receipt, ReleaseSubject/release-index/two-asset digests, live static-verifier and seed SHA-256, owner, exact allow ACE identities/rights, protected DACL, and every parent no-reparse. Only then may the verified fixed seed authenticate the frozen product closure and return the sole canonical G7 initializer path for dot-source. The initializer returns one immutable context containing canonical absolute paths and expected digests for every operational executable/schema. CWD, ambient PATH, runbook literals, and environment receipt/digest pairs have no authority. Tests use launcher/runbook/static-verifier/seed/initializer canaries plus wrong-but-trusted runbook signer, owner rewrite, extra/inherited ACE, parent reparse, same-file-ID race, and matching-forged-receipt/hash fixtures to prove zero runbook or downstream code executes before its preceding trust check passes.

`tools/application_repo_bootstrap.py`, `release/Bootstrap-CodeSextantG8ProductExec.ps1`, `release/g8-product-execution-root.schema.json`, `release/Initialize-CodeSextantG8.ps1`, `release/g8_node_host.mjs`, and `release/g8_node_bootstrap.mjs` are frozen in the product/G7 closure. G6 builds, Authenticode-signs, stages, installs, receipts, and tests the static native verifier as a second immutable release asset, then installs the static verifier, seed, and signed install receipt only under `%ProgramData%\CodeSextant\Trust\G8\`; every use revalidates the fixed receipt plus live bytes, Authenticode pin, file IDs, exact TrustedInstaller ownership/DACL, and no-follow parent closure. No user-profile-writable directory is a trust root. The seed bootstraps the content-addressed product root solely from ReleaseSubject and the policy-verified signed release index, never from a caller-supplied G7 receipt/hash. After the root exists and its complete closure is independently verified, the product-frozen G7 chain verifier authenticates the fixed publication/public-smoke receipt paths against plan/start/result, live public state, and each other. The canonical product-root receipt records the seed-install receipt/live-seed/static-verifier digests plus fixed G7 publication/public-smoke paths and digests, root commit/tree/full closure, clean-state observations, release lock, and locked Python. Every later shell recomputes the complete closure before returning the sole authenticated G8 initializer path. All product executables, schemas, Node host/bootstrap modules, and locked Python resolve only as absolute descendants of that root; private code cannot supply them.

`bootstrap-private` clones only the authenticated product execution root into a new remote-free `application-private` repository. `audit-private-overlay` compares the product base to private `HEAD` by Git object identity and path status, requires every pre-existing product path to be byte-identical and present, and permits only `A` records below `application/claude-for-oss/**` and `tests/application/**`. It requires the expected branch, no remotes, exact base ancestry, clean HEAD/tree/index/worktree, no staged/unstaged changes, and zero nonignored untracked paths. Generated evidence is ignored by the already-frozen product policy or local `.git/info/exclude`; Task 2 never modifies `.gitignore` or any other product path. Every G8 stage and every external-effect/recovery entry reruns both `verify-product-exec` and `audit-private-overlay` before loading private code.

The product-frozen `release/Initialize-CodeSextantG8.ps1`, not a private initializer, owns `Initialize-G8Context`; it is dot-sourced only after the ACL seed authenticates the product root, fixed G7 publication/public-smoke chain, and initializer bytes. The initializer re-verifies the product-root receipt, audits the additive private overlay, classifies transaction state, and only for `prepare` emits a create-new JCS-canonical absolute-path context bundle. The bundle binds product root/commit/tree/receipt, fixed G7 publication/public-smoke paths and digests, private root/commit/tree, both subjects, every executable/schema/evidence authority, product Node-host and Node-bootstrap paths/digests, private bridge digest, and allowed namespaces. The product-frozen Node host is loaded by the locked connector through an authenticated absolute-path-plus-SHA-256 primitive, rejects ambient same-name globals, re-hashes the absolute bootstrap before import, seals its namespace, verifies the bundle and product/private closure, and only then permits private-bridge import. No private initializer, CWD, ambient PATH/global, unverified bundle field, or runbook literal is a trust root.

Before G5 final freeze, Task 1 also extends the already closed `release/security-review-scope.json` with every G7 publication/recovery/initializer/bootstrap material ID above, including the pre-F1 Authenticode policy, deterministic runbook renderer, generated signed publication runbook and embedded literal, installed G6 native runbook-launcher binding/negative tests, fixed static-verifier role/asset contract, content-addressed G8 product-root bootstrap and receipt schema, product-frozen G8 initializer/context bundle, product Node host/bootstrap and pre-import verifier, private-overlay confinement, atomic generic producer/sealer plus VerificationContext/launch-policy changes, and transaction-state router. The normal G5 signed request/input/findings flow must therefore independently review the exact final bytes and generated-equals-source relation of these tools. A frozen G5 security review that omits any new G7/G8 trust-bootstrap file is stale and cannot satisfy publication-security refresh.

Generate, sign, and verify the tracked runbook and refresh the public G7 launch policy before any GREEN test or staging command. The unsigned body—not the RFC3161 timestamped signed bytes—is the deterministic object:

~~~powershell
$ErrorActionPreference = 'Stop'
$authenticodePolicyPath = 'release/g8-authenticode-signing-policy.json'
$runbookPath = 'release/Invoke-CodeSextantPublication.ps1'
$renderA = Join-Path $env:TEMP ("codesextant-publication-runbook-a-" + [guid]::NewGuid().ToString('N') + '.ps1')
$renderB = Join-Path $env:TEMP ("codesextant-publication-runbook-b-" + [guid]::NewGuid().ToString('N') + '.ps1')
& C:\Python311\python.exe tools/render_publication_runbook.py render-unsigned --authenticode-policy $authenticodePolicyPath --source-root . --out $renderA
if ($LASTEXITCODE -ne 0) { throw 'first deterministic publication-runbook render failed' }
& C:\Python311\python.exe tools/render_publication_runbook.py render-unsigned --authenticode-policy $authenticodePolicyPath --source-root . --out $renderB
if ($LASTEXITCODE -ne 0) { throw 'second deterministic publication-runbook render failed' }
$bodyA = (Get-FileHash -LiteralPath $renderA -Algorithm SHA256).Hash.ToLowerInvariant()
$bodyB = (Get-FileHash -LiteralPath $renderB -Algorithm SHA256).Hash.ToLowerInvariant()
if ($bodyA -cne $bodyB) { throw 'publication-runbook unsigned render is nondeterministic' }
Copy-Item -LiteralPath $renderA -Destination $runbookPath -Force
$authenticodePolicy = Get-Content -Raw -Encoding UTF8 -LiteralPath $authenticodePolicyPath | ConvertFrom-Json
$signingCert = @(Get-ChildItem Cert:\CurrentUser\My,Cert:\LocalMachine\My | Where-Object {
  $sha256 = [Security.Cryptography.SHA256]::Create()
  try { $derSha256 = ([BitConverter]::ToString($sha256.ComputeHash($_.RawData))).Replace('-','').ToLowerInvariant() }
  finally { $sha256.Dispose() }
  $derSha256 -ceq [string]$authenticodePolicy.leaf_cert_der_sha256
})
if ($signingCert.Count -ne 1 -or -not $signingCert[0].HasPrivateKey) { throw 'exact pre-F1 Authenticode signing certificate/private key is unavailable or ambiguous' }
$signature = Set-AuthenticodeSignature -FilePath $runbookPath -Certificate $signingCert[0] -TimestampServer ([string]$authenticodePolicy.rfc3161_timestamp_url) -HashAlgorithm SHA256
if ($signature.Status -ne 'Valid') { throw "publication runbook Authenticode signing failed: $($signature.StatusMessage)" }
& C:\Python311\python.exe tools/render_publication_runbook.py verify-signed --signed $runbookPath --expected-unsigned $renderA --expected-unsigned-sha256 $bodyA --authenticode-policy $authenticodePolicyPath --require-wintrust --require-rfc3161-timestamp --require-strip-signature-body-equality --forbid-placeholder --forbid-project-import-before-static-verifier
if ($LASTEXITCODE -ne 0) { throw 'signed publication runbook failed WinTrust/pin/timestamp or unsigned-body equality verification' }
$releasePython = & C:\Python311\python.exe tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$releasePython)) { throw 'locked release Python bootstrap failed before launch-policy sync' }
& $releasePython tools/generate_producer_launch_policy.py sync --through-phase G7_FINAL --registry release/evidence/receipt-registry.json --out release/evidence/producer-launch-policy.json
if ($LASTEXITCODE -ne 0) { throw 'phase-generated public launch policy sync through G7_FINAL failed' }
& $releasePython tools/generate_producer_launch_policy.py check --through-phase G7_FINAL --registry release/evidence/receipt-registry.json --policy release/evidence/producer-launch-policy.json --schema release/evidence/producer-launch-policy.schema.json --require-exact-phase-closure --forbid-private-g8-specs
if ($LASTEXITCODE -ne 0) { throw 'G7_FINAL public launch policy is incomplete, stale, or contains private G8 specs' }
Remove-Item -LiteralPath $renderA,$renderB -Force
~~~

The later F1 Final Pre-Freeze owner must run the exact closure check below; a G7-only check is not a substitute for that final chronology gate. Every producer-owning phase stages the same public policy file after its own sync, while private G8 specs remain solely in the ApplicationToolSubject-bound extension.

~~~powershell
& $releasePython tools/generate_producer_launch_policy.py check --through-phase FINAL_PRE_FREEZE --registry release/evidence/receipt-registry.json --policy release/evidence/producer-launch-policy.json --schema release/evidence/producer-launch-policy.schema.json --require-exact-public-closure --forbid-private-g8-specs
if ($LASTEXITCODE -ne 0) { throw 'FINAL_PRE_FREEZE public producer launch policy closure is stale or incomplete' }
~~~

**Step 4: Run GREEN**

Set `CODESEXTANT_CHROME_BROWSER_CLIENT` to the exact `scripts/browser-client.mjs` selected by the active `control-chrome` skill, never to a guessed newest cache directory. On the verified 2026-07-23 workstation that path is `C:\Users\zerox\.codex\plugins\cache\openai-bundled\chrome\26.707.71524\scripts\browser-client.mjs`; if the active skill moves or updates before implementation, regenerate the lock, independently review the new private application commit, and mint a new `ApplicationToolSubject` rather than silently retaining this snapshot.

~~~powershell
$releasePython = & C:\Python311\python.exe tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$releasePython)) { throw 'locked release Python bootstrap failed' }
& $releasePython -m pytest tests/release/test_exact_task_commit.py tests/release/test_github_preflight.py tests/release/test_github_publish.py tests/release/test_github_public_verify.py tests/release/test_publication_security_refresh.py tests/release/test_application_repo_bootstrap.py tests/release/test_g7_fresh_shell.py tests/release/test_g8_trusted_bootstrap.py tests/release/test_transaction_entry_routing.py tests/release/test_publication_application_runbook_static.py -q
if ($LASTEXITCODE -ne 0) { throw 'G7 and product-frozen G8 bootstrap tests failed' }
~~~

Expected: all tests pass. The live preflight is intentionally deferred to G7.2 because the final immutable authorization receipt does not exist during implementation.

**Step 5: Commit**

~~~powershell
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($repoRoot)) { throw 'unable to resolve product repository root' }
$exactTaskCommitPath = Join-Path $repoRoot 'tools\exact_task_commit.ps1'
$exactTaskCommitTestPath = Join-Path $repoRoot 'tests\release\test_exact_task_commit.py'
if (-not (Test-Path -LiteralPath $exactTaskCommitPath -PathType Leaf) -or -not (Test-Path -LiteralPath $exactTaskCommitTestPath -PathType Leaf)) { throw 'G0 exact-task helper/test SSOT is missing' }
. $exactTaskCommitPath
C:\Python311\python.exe -m pytest $exactTaskCommitTestPath -q
if ($LASTEXITCODE -ne 0) { throw 'tracked exact-task commit contract failed before Task 1 commit' }
$expectedStaged = @('release/Bootstrap-CodeSextantG8ProductExec.ps1','release/Initialize-CodeSextantG7.ps1','release/Initialize-CodeSextantG8.ps1','release/Invoke-CodeSextantPublication.ps1','release/evidence/github-publication.schema.json','release/evidence/public-smoke.schema.json','release/evidence/publication-security-refresh.schema.json','release/evidence/producer-launch-policy.json','release/evidence/receipt-registry.json','release/g8-node-context.schema.json','release/g8-product-execution-root.schema.json','release/g8_node_host.mjs','release/g8_node_bootstrap.mjs','release/github-identity.schema.json','release/github.json','release/publication-authorization.schema.json','release/publication-mutation-journal.schema.json','release/publication-plan.schema.json','release/publication-result.schema.json','release/publication-start.schema.json','release/publication-tombstone.schema.json','release/security-review-scope.json','tests/release/test_application_repo_bootstrap.py','tests/release/test_exact_task_commit.py','tests/release/test_g7_fresh_shell.py','tests/release/test_g8_trusted_bootstrap.py','tests/release/test_github_preflight.py','tests/release/test_github_public_verify.py','tests/release/test_github_publish.py','tests/release/test_publication_application_runbook_static.py','tests/release/test_publication_security_refresh.py','tests/release/test_transaction_entry_routing.py','tools/application_repo_bootstrap.py','tools/exact_task_commit.ps1','tools/github_preflight.py','tools/github_public_verify.py','tools/github_publish.py','tools/publication_security_refresh.py','tools/render_publication_runbook.py') | Sort-Object
Invoke-ExactTaskCommit -RepositoryRoot $repoRoot -ExpectedPaths $expectedStaged -Message 'release: add fail-closed GitHub publication preflight'
~~~

### Task 2: Build the typed Claude for Open Source packet and receipt producers

**Execution boundary:** This specification appears before the runbook for readability, but Task 2 and Task 3 execute only after the product freezes and G7 succeeds. First create the independently verified, content-addressed product execution root; then use only its absolute locked-Python and product-frozen bootstrap to clone the exact authenticated product commit into `E:\ai-king\private\CodeSextant-application`, remove every remote, and create local branch `application-private`. Additions are permitted only below `application/claude-for-oss/` and `tests/application/`; no pre-existing product path may be modified or deleted. All private G8 code below resolves there, while the locked Python, external-review engine, generic schemas, release gate, bootstrap, and G8 initializer always resolve under the separate product execution root. The new application files exist only in the later private commit and therefore are not members of the older product `source_commit/source_tree_sha256`. `ApplicationToolSubject` binds the distinct additive private commit/tree plus its exhaustive manifest and the verified product-execution-root receipt. Copy ignored product/G7 receipts into this private evidence directory only after re-verifying their digests and live public chain; they are runtime inputs, never committed.

The private-development entry is executable and fail-closed. On the first run after G7 it uses the closed native-launcher action `bootstrap-private`, which refuses an existing destination instead of merging with unknown state. Every later fresh shell uses the distinct non-mutating `resume-private-development` action; that action reauthenticates the product execution root, remote-free additive private repository, branch/ancestry/path confinement, and locked Python before returning the same absolute context, and can never create, repair, clean, stage, or import anything:

~~~powershell
$productExecParent = 'E:\ai-king\private\CodeSextant-g8-product-exec'
$destination = 'E:\ai-king\private\CodeSextant-application'
$frozenProductRootLocator = 'E:\ai-king\項目資料\CodeSextant'
$g6RunbookLauncher = Join-Path $env:ProgramData 'CodeSextant\Trust\G6\codesextant-g6-runbook-launcher.exe'
$publicationRunbook = Join-Path $frozenProductRootLocator 'release\Invoke-CodeSextantPublication.ps1'
if (-not (Test-Path -LiteralPath $g6RunbookLauncher -PathType Leaf)) { throw 'fixed protected G6 runbook launcher is missing' }
if (Test-Path -LiteralPath $destination -PathType Container) {
  $bootstrapJson = & $g6RunbookLauncher run-fixed --runbook $publicationRunbook --action resume-private-development --expected-root $frozenProductRootLocator --require-subject --product-exec-parent $productExecParent --private-destination $destination --public-repo Zeroxrain99/CodeSextant --format json
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$bootstrapJson)) { throw 'non-mutating authenticated private-development resume failed closed' }
} else {
  $bootstrapJson = & $g6RunbookLauncher run-fixed --runbook $publicationRunbook --action bootstrap-private --expected-root $frozenProductRootLocator --require-subject --product-exec-parent $productExecParent --private-destination $destination --public-repo Zeroxrain99/CodeSextant --format json
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$bootstrapJson)) { throw 'authenticated publication runbook private bootstrap failed closed' }
}
$privateDevelopment = $bootstrapJson | ConvertFrom-Json
$productExecRoot = [string]$privateDevelopment.product_execution_root
$productExecReceiptPath = [string]$privateDevelopment.product_execution_receipt
$privateRoot = [string]$privateDevelopment.private_root
$releasePython = [string]$privateDevelopment.release_python
$productOverlayTool = [string]$privateDevelopment.product_overlay_tool
foreach($absolutePath in @($productExecRoot,$productExecReceiptPath,$privateRoot,$releasePython,$productOverlayTool)) {
  if (-not [IO.Path]::IsPathFullyQualified($absolutePath)) { throw 'bootstrap-private returned a non-absolute development authority path' }
}
if ($privateRoot -cne $destination) { throw 'bootstrap-private returned an unexpected private root' }
function Assert-CodeSextantPrivateDevelopmentBoundary {
  & $releasePython $productOverlayTool verify-product-exec --product-execution-root $productExecRoot --product-execution-receipt $productExecReceiptPath
  if ($LASTEXITCODE -ne 0) { throw 'product execution root verification failed before private development step' }
  & $releasePython $productOverlayTool audit-private-overlay --product-execution-root $productExecRoot --product-execution-receipt $productExecReceiptPath --repo $privateRoot --required-branch application-private --require-no-remotes --allow-declared-working-additions --reject-modified-or-deleted-product-path --allowed-addition 'application/claude-for-oss/**' --allowed-addition 'tests/application/**'
  if ($LASTEXITCODE -ne 0) { throw 'private overlay audit failed before private development step' }
}
function Enter-CodeSextantPrivateDevelopmentCheckpoint {
  $resumeJson = & $g6RunbookLauncher run-fixed --runbook $publicationRunbook --action resume-private-development --expected-root $frozenProductRootLocator --require-subject --product-exec-parent $productExecParent --private-destination $destination --public-repo Zeroxrain99/CodeSextant --format json
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace([string]$resumeJson)) { throw 'native authenticated private-development checkpoint resume failed' }
  $resumed = $resumeJson | ConvertFrom-Json
  if ([string]$resumed.product_execution_root -cne $productExecRoot -or [string]$resumed.product_execution_receipt -cne $productExecReceiptPath -or [string]$resumed.private_root -cne $privateRoot -or [string]$resumed.release_python -cne $releasePython -or [string]$resumed.product_overlay_tool -cne $productOverlayTool) { throw 'resumed private-development authority context differs from the authenticated bootstrap context' }
  Assert-CodeSextantPrivateDevelopmentBoundary
}
~~~

The one-shot bootstrap re-fetches the live public commit/release, verifies ReleaseSubject and signed index, materializes one clean content-addressed product root, and then runs the product-frozen purpose verifier over fixed G7 publication/public-smoke paths before it creates the private repository. The bootstrap output may expose those already-authenticated absolute paths, but no caller supplies their expected hashes. `CODESEXTANT_G7_PUBLICATION_RECEIPT*` and `CODESEXTANT_G8_SEED_VERIFIER*` are ignored; even a forged receipt paired with its matching environment hash fails the G6 seed-receipt, public-state, plan/start/result, and public-smoke cross-checks. After materialization, the installed seed re-verifies the root and returns the authenticated initializer before dot-source. A blank-shell fixture proves receipt/seed/ACL/initializer drift, Sigstore/base mismatch, product-path mutation, namespace escape, remaining remote, dirty state, or existing destination blocks before private code loads.

**Files:**

- Create, keep private and exclude from public export: application/claude-for-oss/application-tool-manifest.json
- Create, keep private and exclude from public export: application/claude-for-oss/application-tool-subject.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/application_tool_subject.py
- Create, keep private and exclude from public export: application/claude-for-oss/schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/terms.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/attestations.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/target-profile-request.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/target-profile.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/confirmation.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/authorization.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/submission-start.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/confirmation-runtime.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/browser-confirmation-source.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/submission-confirmation.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/submission-tombstone.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/submission.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/evidence-input.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/evidence-input-request.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/evidence-authority-response.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/evidence-refresh.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/application-form-contract.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/form-capture-policy.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/form-capture-policy.json
- Create, keep private and exclude from public export: application/claude-for-oss/browser-client-lock.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/browser-client-lock.json
- Create, keep private and exclude from public export: application/claude-for-oss/chrome_form_bridge.mjs
- Create, keep private and exclude from public export: application/claude-for-oss/pre-submit-runtime.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/pre-submit-form.schema.json
- Create, keep private and exclude from public export: application/claude-for-oss/pre-click.schema.json
- Create, keep private and include in `ApplicationToolSubject`: application/claude-for-oss/private-trust-extension.schema.json
- Create, keep private and include in `ApplicationToolSubject`: application/claude-for-oss/generate_private_trust_extensions.py
- Generate only after `ApplicationToolSubject` exists; keep ignored and exclude from subject membership: application/claude-for-oss/receipt-registry-extension.json
- Generate only after `ApplicationToolSubject` exists; keep ignored and exclude from subject membership: application/claude-for-oss/producer-launch-policy-extension.json
- Create, keep private and exclude from public export: application/claude-for-oss/build_packet.py
- Create, keep private and exclude from public export: application/claude-for-oss/evidence_input.py
- Create, keep private and exclude from public export: application/claude-for-oss/verify_packet.py
- Create, keep private and exclude from public export: application/claude-for-oss/refresh_terms.py
- Create, keep private and exclude from public export: application/claude-for-oss/authorize_packet.py
- Create, keep private and exclude from public export: application/claude-for-oss/record_submission.py
- Create, keep private and exclude from public export: tests/application/test_claude_oss_packet.py
- Create, keep private and exclude from public export: tests/application/test_claude_oss_receipts.py
- Create, keep private and exclude from public export: tests/application/test_claude_oss_application_subject.py
- Create, keep private and exclude from public export: tests/application/test_claude_oss_evidence.py
- Create, keep private and exclude from public export: tests/application/test_claude_oss_pre_submit.py
- Create, keep private and exclude from public export: tests/application/test_chrome_form_bridge.py
- Create, keep private and exclude from public export: tests/application/test_g8_fresh_shell.py

**Step 1: Write RED tests**

~~~python
def test_packet_rejects_wrong_account_or_stale_activity(valid_packet) -> None:
    valid_packet["payload"]["github"]["login"] = "aiking931931"
    assert verify_packet(valid_packet).status == "fail"
    valid_packet["payload"]["github"]["login"] = "Zeroxrain99"
    valid_packet["payload"]["github"]["latest_public_activity_utc"] = utc_now() - timedelta(days=91)
    assert verify_packet(valid_packet).status == "fail"


def test_application_tool_subject_binds_exact_private_commit_tree_and_product_base(
    private_application_repo, product_subject
) -> None:
    subject = create_application_tool_subject(private_application_repo, product_subject)
    assert subject.application_commit == private_application_repo.head_commit
    assert subject.application_tree_sha256 == private_application_repo.head_tree_sha256
    assert subject.product_export_base_commit == product_subject.export_commit
    assert verify_application_tool_subject(subject, private_application_repo, product_subject).status == "pass"
    private_application_repo.add_remote("origin", "https://github.com/example/example.git")
    assert verify_application_tool_subject(subject, private_application_repo, product_subject).status == "fail"
    private_application_repo.remove_remote("origin")
    private_application_repo.rebase_onto(unrelated_commit())
    assert verify_application_tool_subject(subject, private_application_repo, product_subject).status == "fail"


def test_application_tool_subject_binds_verified_product_execution_root(
    private_application_repo, product_execution_root
) -> None:
    subject = create_application_tool_subject(
        private_application_repo,
        PRODUCT_SUBJECT,
        product_execution_root.receipt,
    )
    assert subject.product_execution_root_receipt_sha256 == canonical_sha256(
        product_execution_root.receipt
    )
    assert subject.product_execution_root_commit == PRODUCT_SUBJECT.export_commit
    assert subject.product_execution_root_tree_sha256 == PRODUCT_SUBJECT.export_tree_sha256
    subject["product_execution_root_tree_sha256"] = "0" * 64
    assert verify_application_tool_subject(
        subject, private_application_repo, PRODUCT_SUBJECT, product_execution_root.receipt
    ).status == "fail"


def test_private_trust_extensions_are_post_subject_outputs_not_subject_members(
    private_application_repo, product_execution_root, global_signing_environment_registry
) -> None:
    subject = create_application_tool_subject(
        private_application_repo, PRODUCT_SUBJECT, product_execution_root.receipt
    )
    generated_paths = {
        "application/claude-for-oss/receipt-registry-extension.json",
        "application/claude-for-oss/producer-launch-policy-extension.json",
    }
    assert generated_paths.isdisjoint(subject.manifest_paths)
    extensions = generate_private_trust_extensions(
        application_tool_subject=subject,
        private_application_repo=private_application_repo,
        signing_environment_registry=global_signing_environment_registry,
    )
    assert extensions.application_tool_subject_sha256 == canonical_sha256(subject)
    assert verify_generated_private_trust_extensions(
        extensions, subject, private_application_repo, PRODUCT_SUBJECT
    ).status == "pass"
    mutate_subject_digest(extensions.registry_extension)
    assert verify_generated_private_trust_extensions(
        extensions, subject, private_application_repo, PRODUCT_SUBJECT
    ).status == "fail"


def test_every_claim_has_a_public_url_and_digest(valid_packet) -> None:
    claim = valid_packet["payload"]["claims"][0]
    evidence_id = evidence_uses_for(valid_packet, "claim", claim["claim_id"])[0]["evidence_id"]
    evidence_row(valid_packet, evidence_id)["citation_url"] = ""
    assert verify_packet(valid_packet).status == "fail"


def test_typed_evidence_graph_is_complete_reachable_and_unique(valid_packet) -> None:
    graph = build_evidence_graph(valid_packet)
    assert graph.consumer_kinds == {
        "claim", "track", "criterion", "downstream_dependency", "project", "github"
    }
    assert graph.dangling_uses == ()
    assert graph.orphan_evidence_rows == ()
    assert graph.duplicate_uses == ()
    assert graph.uncovered_required_consumers == ()
    duplicate = copy.deepcopy(valid_packet["payload"]["evidence_uses"][0])
    valid_packet["payload"]["evidence_uses"].append(duplicate)
    assert verify_packet(valid_packet).status == "fail"


def test_evidence_graph_rejects_dangling_consumer_evidence_and_orphan_rows(valid_packet) -> None:
    valid_packet["payload"]["evidence_uses"][0]["consumer_id"] = "unknown-consumer"
    assert verify_packet(valid_packet).status == "fail"
    valid_packet = valid_packet_fixture()
    valid_packet["payload"]["evidence_uses"][0]["evidence_id"] = "ev_" + "0" * 64
    assert verify_packet(valid_packet).status == "fail"
    valid_packet = valid_packet_fixture()
    valid_packet["payload"]["evidence_table"].append(valid_evidence_record("github_git_object"))
    assert verify_packet(valid_packet).status == "fail"


def test_packet_rejects_guarantee_language(valid_packet) -> None:
    valid_packet["payload"]["qualification_text"] += " Approval is guaranteed."
    assert verify_packet(valid_packet).status == "fail"


def test_packet_has_two_distinct_live_form_values_and_no_legacy_alias(valid_packet) -> None:
    payload = valid_packet["payload"]
    assert "application_text" not in payload
    assert payload["planned_use_text"] != payload["qualification_text"]
    assert payload["first_name"].strip()
    assert payload["last_name"].strip()
    assert payload["message__oss"]["state"] in {"explicit_empty", "explicit_value"}
    assert payload["message__oss"]["value"] == (
        "" if payload["message__oss"]["state"] == "explicit_empty" else payload["message__oss"]["value"].strip()
    )
    payload["qualification_text"] = payload["planned_use_text"]
    assert verify_packet(valid_packet).status == "fail"


def test_name_and_optional_message_are_explicit_user_values_not_github_inference(valid_packet) -> None:
    profile = valid_packet["payload"]["target_profile"]
    assert profile["field_confirmations"] == {
        "github_account": True,
        "email": True,
        "first_name": True,
        "last_name": True,
        "message__oss": True,
    }
    assert profile["value_sources"]["first_name"] == "explicit_user_input"
    assert profile["value_sources"]["last_name"] == "explicit_user_input"
    assert profile["value_sources"]["message__oss"] == "explicit_user_input"
    assert valid_packet["payload"]["first_name"] == profile["first_name"]
    assert valid_packet["payload"]["last_name"] == profile["last_name"]
    assert valid_packet["payload"]["message__oss"] == profile["message__oss"]
    profile["value_sources"]["first_name"] = "github_profile"
    assert verify_packet(valid_packet).status == "fail"


def test_packet_requires_apache_2_and_official_osi_evidence(valid_packet) -> None:
    project = valid_packet["payload"]["project"]
    github = valid_packet["payload"]["github"]
    assert project["license_spdx"] == "Apache-2.0"
    project_uses = evidence_uses_for(valid_packet, "project", project["project_id"])
    assert any(evidence_row(valid_packet, row["evidence_id"])["kind"] == "osi_license" for row in project_uses)
    assert not any(key.endswith("_evidence_url") for key in project)
    assert not any(key.endswith("_evidence_url") for key in github)
    project["license_spdx"] = "LicenseRef-Proprietary"
    assert verify_packet(valid_packet).status == "fail"


def test_packet_requires_exactly_one_current_official_track(valid_packet) -> None:
    valid_packet["payload"]["eligibility"].pop("track")
    assert verify_packet(valid_packet).status == "fail"


def test_ecosystem_impact_track_requires_independent_downstream_dependency(valid_packet) -> None:
    valid_packet["payload"]["eligibility"]["track"] = {
        "kind": "ecosystem_impact",
        "track_id": "track_ecosystem_impact",
        "explanation": "CodeSextant is useful",
        "downstream_dependencies": [],
    }
    assert verify_packet(valid_packet).status == "fail"


def test_human_eligibility_is_never_inferred(valid_packet) -> None:
    valid_packet["payload"]["eligibility"]["attestations"]["adult_or_age_of_majority"] = None
    assert verify_packet(valid_packet).status == "fail"


@pytest.mark.parametrize(
    "attestation_id",
    [
        "github_account_at_least_two_years_and_in_good_standing",
        "not_anthropic_personnel_contractor_agent_program_operator_or_immediate_family_or_household",
        "no_active_benefit_and_no_duplicate_or_pending_application",
    ],
)
def test_current_nonpublic_eligibility_is_explicitly_attested(valid_packet, attestation_id) -> None:
    valid_packet["payload"]["eligibility"]["attestations"][attestation_id] = None
    assert verify_packet(valid_packet).status == "fail"


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/Zeroxrain99/CodeSextant/blob/main/README.md",
        "https://github.com/Zeroxrain99/CodeSextant/tree/main",
        "https://github.com/Zeroxrain99/CodeSextant/releases/latest",
    ],
)
def test_packet_rejects_mutable_evidence_urls(valid_packet, url) -> None:
    evidence_id = valid_packet["payload"]["evidence_uses"][0]["evidence_id"]
    evidence_row(valid_packet, evidence_id)["citation_url"] = url
    assert verify_packet(valid_packet).status == "fail"


@pytest.mark.parametrize(
    "kind",
    [
        "github_git_object",
        "github_release_asset",
        "registry_metric_snapshot",
        "openssf_report",
        "official_roster",
        "osi_license",
        "anthropic_terms",
    ],
)
def test_closed_evidence_union_represents_every_official_route(kind) -> None:
    row = valid_evidence_record(kind)
    assert verify_evidence_record(row, OFFICIAL_AUTHORITY_POLICY).status == "pass"


def test_evidence_rejects_arbitrary_authority_or_self_authored_metric(valid_packet) -> None:
    row = valid_packet["payload"]["evidence_table"][0]
    row["authority_url"] = "https://example.invalid/my-number.json"
    assert verify_packet(valid_packet).status == "fail"


def test_attestation_recorder_rejects_omitted_unknown_or_implicit_answers(
    valid_attestation_request,
) -> None:
    answers = explicit_answers_for(valid_attestation_request)
    answers.pop(next(iter(answers)))
    assert record_attestations(valid_attestation_request, answers).status == "fail"
    answers = explicit_answers_for(valid_attestation_request) | {"unknown_field": True}
    assert record_attestations(valid_attestation_request, answers).status == "fail"


def test_attestations_bind_current_terms_questions_and_both_subjects(valid_attestations) -> None:
    valid_attestations["terms_sha256"] = "0" * 64
    assert verify_attestations(valid_attestations).status == "fail"
    valid_attestations = valid_attestations_fixture()
    valid_attestations["application_tool_subject_sha256"] = "0" * 64
    assert verify_attestations(valid_attestations).status == "fail"


def test_target_profile_requires_explicit_confirmation_for_every_form_value(valid_target_request) -> None:
    profile = record_target_profile(
        valid_target_request,
        confirmed_account="Zeroxrain99",
        confirmed_email="zeroxrain99@gmail.com",
        confirmed_first_name="User supplied first name",
        confirmed_last_name="User supplied last name",
        confirmed_message__oss={"state": "explicit_empty", "value": ""},
        confirm_each_field=True,
        confirmed_by="user",
    )
    assert verify_target_profile(profile, valid_target_request).status == "pass"
    profile["target_email"] = "different@example.com"
    assert verify_target_profile(profile, valid_target_request).status == "fail"


@pytest.mark.parametrize(
    "field",
    ["github_account", "email", "first_name", "last_name", "message__oss"],
)
def test_target_profile_rejects_any_unconfirmed_or_inferred_field(valid_target_profile, field) -> None:
    valid_target_profile["field_confirmations"][field] = False
    assert verify_target_profile(valid_target_profile).status == "fail"
    valid_target_profile = valid_target_profile_fixture()
    valid_target_profile["value_sources"][field] = "github_profile"
    assert verify_target_profile(valid_target_profile).status == "fail"


def test_submission_must_start_inside_authorization_ttl_and_ambiguous_click_is_terminal(
    valid_authorization,
) -> None:
    start = begin_submission(valid_authorization, now=valid_authorization.expires_at_utc)
    assert start.status == "pass"
    assert begin_submission(
        valid_authorization,
        now=valid_authorization.expires_at_utc + timedelta(microseconds=1),
    ).status == "fail"
    tombstone = mark_submission_ambiguous(start)
    assert can_retry_submission(start, tombstone) is False


def test_submission_start_requires_fresh_unchanged_official_terms(valid_authorization, terms) -> None:
    assert begin_submission(valid_authorization, terms, live_terms=terms, max_age_minutes=15).status == "pass"
    changed = copy.deepcopy(terms)
    changed["content_sha256"] = "0" * 64
    assert begin_submission(valid_authorization, terms, live_terms=changed, max_age_minutes=15).status == "fail"
    terms["fetched_at_utc"] = utc_now() - timedelta(minutes=16)
    assert begin_submission(valid_authorization, terms, live_terms=terms, max_age_minutes=15).status == "fail"


def test_submission_start_requires_exact_pre_submit_and_refetched_immutable_evidence(
    valid_authorization, valid_pre_submit, valid_evidence_refresh
) -> None:
    start = begin_submission(valid_authorization, pre_submit=valid_pre_submit, evidence_refresh=valid_evidence_refresh)
    assert start.pre_submit_form_sha256 == canonical_sha256(valid_pre_submit)
    assert start.evidence_refresh_sha256 == canonical_sha256(valid_evidence_refresh)
    valid_evidence_refresh["rows"][0]["observed_sha256"] = "0" * 64
    assert begin_submission(valid_authorization, pre_submit=valid_pre_submit, evidence_refresh=valid_evidence_refresh).status == "fail"


@pytest.mark.parametrize(
    "failing_phase",
    [
        "connector_capture",
        "post_click_resume",
        "record_browser_source",
        "capture_confirmation",
        "submission_receipt",
        "verify_chain",
        "gate",
    ],
)
def test_every_post_click_failure_tombstones_first_and_quarantines_partial_receipts(
    started_submission, failing_phase, tmp_path
) -> None:
    result = complete_after_click(started_submission, fail_at=failing_phase, root=tmp_path)
    assert result.status == "ambiguous"
    assert result.events.index("tombstone_atomically_written") < result.events.index("partial_receipts_quarantined")
    assert result.tombstone.submission_start_sha256 == canonical_sha256(started_submission)
    assert result.tombstone.authorization_sha256 == started_submission.authorization_sha256
    assert result.retry_allowed is False
    assert not (tmp_path / "claude-oss-submission.json").exists()


def test_fresh_shell_existing_start_without_verified_positive_chain_tombstones_without_redispatch(
    started_submission, tmp_path
) -> None:
    recovered = recover_existing_submission(started_submission.root, empty_process_environment())
    assert recovered.events[0] == "tombstone_atomically_written"
    assert recovered.partial_receipts_quarantined is True
    assert recovered.connector_submit_clicks == 0
    assert recovered.retry_allowed is False


def test_recovery_can_report_complete_only_via_the_full_g8_verifier(complete_evidence_root) -> None:
    recovered = recover_existing_submission(complete_evidence_root, empty_process_environment())
    assert recovered.status == "complete"
    assert recovered.full_verify_g8_chain_calls == 1
    remove_required_input(complete_evidence_root, "claude-oss-evidence-refresh.json")
    recovered = recover_existing_submission(complete_evidence_root, empty_process_environment())
    assert recovered.status == "tombstoned"
    assert recovered.events[0] == "tombstone_atomically_written"


def test_blank_pwsh_initializes_all_g8_paths_and_recovers_without_click(
    started_submission,
) -> None:
    result = invoke_g8_recovery_in_blank_pwsh(
        started_submission,
        inherited_environment=minimal_process_environment(),
    )
    assert result.events[:5] == (
        "winverifytrust_static_verifier_and_pin_leaf_certificate",
        "verify_static_verifier_and_seed_trustedinstaller_exact_acl",
        "verify_signed_fixed_seed_install_receipt",
        "verify_complete_product_execution_root",
        "dot_source_verified_g8_initializer",
    )
    assert result.initializer == "Initialize-G8Context"
    assert result.inherited_path_variables == ()
    assert result.authoritative_root == Path(r"E:\ai-king\private\CodeSextant-application")
    assert result.branch == "application-private"
    assert result.remotes == ()
    assert result.locked_release_python_verified is True
    assert result.all_authority_paths_are_absolute_and_initializer_owned is True
    assert result.competing_literal_authority_paths == ()
    assert {
        "product_execution_root_receipt",
        "g7_publication_receipt",
        "g7_public_smoke_receipt",
        "product_source_root",
        "public_export_root",
        "public_clone_root",
        "private_application_root",
        "release_assets_root",
        "evidence_root",
        "confirmation_runtime",
        "browser_source",
    } <= set(result.explicit_recovery_inputs)
    assert result.recover_existing_calls == 1
    assert result.connector_submit_clicks == 0


def test_product_frozen_initializer_emits_canonical_absolute_node_context(
    valid_g8_context,
) -> None:
    bundle = emit_node_context(valid_g8_context)
    assert bundle == jcs_round_trip(bundle)
    assert all(Path(value).is_absolute() for value in bundle["authority_paths"].values())
    assert {
        "refresh_terms_tool", "application_tool_subject_tool", "evidence_input_tool",
        "build_packet_tool", "verify_packet_tool", "review_packet_tool",
        "authorize_packet_tool", "record_submission_tool", "release_gate_tool",
        "evidence_directory", "registry_extension", "product_node_host_module",
        "product_node_bootstrap_module", "product_source_root", "public_export_root",
        "public_clone_root", "private_application_root", "release_assets_root",
        "g7_publication_receipt", "g7_public_smoke_receipt",
    } <= set(bundle["authority_paths"])
    assert bundle["product_execution_root"] == str(valid_g8_context.product_execution_root)
    assert bundle["private_root"] == str(valid_g8_context.private_root)
    assert bundle["product_execution_root_receipt_sha256"] == canonical_sha256(
        valid_g8_context.product_execution_root_receipt
    )
    assert bundle["application_tool_subject_sha256"] == canonical_sha256(
        valid_g8_context.application_tool_subject
    )
    assert bundle["product_node_bootstrap_sha256"] == sha256_file(
        valid_g8_context.product_node_bootstrap_module
    )
    assert bundle["private_bridge_sha256"] == valid_g8_context.application_tool_subject.chrome_form_bridge_sha256
    assert bundle["allowed_private_namespaces"] == [
        "application/claude-for-oss/",
        "tests/application/",
    ]


def test_node_bridge_is_cwd_independent_and_confined_to_context_bundle(
    valid_node_context_bundle, tmp_path
) -> None:
    result = invoke_bridge_from_cwd(
        tmp_path,
        context_bundle=valid_node_context_bundle,
        operation="capture_only",
    )
    assert result.status == "pass"
    assert result.private_root == valid_node_context_bundle["private_root"]
    assert result.application_tool_subject_sha256 == valid_node_context_bundle[
        "application_tool_subject_sha256"
    ]
    escaped = copy.deepcopy(valid_node_context_bundle)
    escaped["authority_paths"]["packet"] = str(tmp_path / "outside.json")
    assert invoke_bridge_from_cwd(tmp_path, context_bundle=escaped).status == "blocked"


def test_product_bootstrap_verifies_bundle_and_private_bridge_before_import(
    valid_node_context_bundle, tmp_path
) -> None:
    canary = tmp_path / "bridge-import-canary"
    tampered = copy.deepcopy(valid_node_context_bundle)
    tampered["bridge_module_url"] = malicious_module_url_that_writes(canary)
    result = invoke_product_node_bootstrap(
        bundle_path=write_jcs_bundle(tmp_path / "g8-node-context.json", tampered),
        cwd=tmp_path,
    )
    assert result.status == "blocked"
    assert result.private_module_imports == ()
    assert not canary.exists()


def test_node_host_injects_only_absolute_bundle_path_not_unverified_bundle_object(
    valid_node_context_bundle_path,
) -> None:
    invocation = build_node_host_invocation(valid_node_context_bundle_path)
    assert invocation.injected_values == {
        "codeSextantG8NodeContextBundlePath": str(valid_node_context_bundle_path)
    }
    assert Path(invocation.injected_values["codeSextantG8NodeContextBundlePath"]).is_absolute()
    assert "codeSextantG8NodeContextBundle" not in invocation.injected_values
    assert invocation.preloaded_module == "seed_authenticated_product_node_bootstrap"
    assert invocation.private_module_imports_before_bundle_verification == ()


def test_runbook_javascript_has_no_literal_authority_paths_and_remove_item_is_context_owned(
    parsed_plan_runbooks,
) -> None:
    assert parsed_plan_runbooks.g8.javascript_authority_path_literals == ()
    assert parsed_plan_runbooks.g8.node_calls_use_only_context_bundle is True
    assert parsed_plan_runbooks.g8.private_bridge_imports_before_product_bootstrap_verify == ()
    assert parsed_plan_runbooks.g8.remove_item_nonvariable_arguments == ()


def test_confirmation_capture_rejects_navigation_or_http_success_without_positive_result(valid_source) -> None:
    valid_source["positive_server_rendered_confirmation"] = False
    assert capture_confirmation(valid_source).status == "fail"


def test_submission_raw_evidence_and_quarantine_are_gitignored(repo_root: Path) -> None:
    for relative in (
        "release/evidence/claude-oss-application-tool-scan.json",
        "release/evidence/claude-oss-application-tool-review-request.json",
        "release/evidence/claude-oss-application-tool-review-input.json",
        "release/evidence/claude-oss-application-tool-findings.json",
        "release/evidence/claude-oss-application-tool-review.json",
        "release/evidence/claude-oss-application-form-contract.json",
        "release/evidence/claude-oss-pre-submit-runtime.json",
        "release/evidence/claude-oss-pre-click.json",
        "release/evidence/claude-oss-confirmation-runtime.json",
        "release/evidence/claude-oss-submission-quarantine/sample/partial.json",
    ):
        assert is_git_ignored(repo_root / relative)


def test_form_capture_never_persists_opaque_token_or_raw_dom(runtime_form_fixture) -> None:
    runtime_form_fixture.add_hidden("verification_token", "CANARY-SECRET")
    receipt = sanitize_runtime_form(runtime_form_fixture, FORM_CAPTURE_POLICY)
    serialized = canonical_json(receipt)
    assert "CANARY-SECRET" not in serialized
    assert "outerHTML" not in serialized
    assert receipt.opaque_sensitive_fields == [
        {"semantic_class": "verification_token", "present": True, "session_bound": True}
    ]


def test_confirmation_capture_never_persists_page_bytes_or_secrets(confirmation_runtime_fixture) -> None:
    confirmation_runtime_fixture.inject_unclassified("raw_html", "<input value='CANARY-SECRET'>")
    assert sanitize_confirmation_runtime(confirmation_runtime_fixture).status == "fail"
    confirmation_runtime_fixture = valid_confirmation_runtime_fixture()
    source = sanitize_confirmation_runtime(confirmation_runtime_fixture)
    serialized = canonical_json(source)
    assert "CANARY-SECRET" not in serialized
    assert set(source.payload) <= {
        "result_url", "positive_server_rendered_confirmation", "reference_id",
        "success_text_sha256", "page_instance_nonce", "session_nonce", "captured_at_utc",
    }


def test_hashed_chrome_bridge_uses_cdp_for_one_atomic_verify_and_click(
    fake_chrome_tab, application_tool_subject
) -> None:
    result = run_chrome_bridge_fixture(
        fake_chrome_tab,
        application_tool_subject=application_tool_subject,
        operation="verify_and_click",
    )
    assert fake_chrome_tab.cdp_methods == ["Runtime.evaluate"]
    assert fake_chrome_tab.playwright_mutations == []
    assert result.click_issued is True
    assert result.bridge_source_sha256 == application_tool_subject.chrome_form_bridge_sha256
    assert set(result) <= PRE_CLICK_SCHEMA_PROPERTIES


def test_bridge_uses_the_verified_real_connector_interface_not_missing_capability_docs(
    chrome_bridge_source,
) -> None:
    assert 'tab.capabilities.get("cdp")' in chrome_bridge_source
    assert 'cdp.send("Runtime.evaluate"' in chrome_bridge_source
    assert "cdp.documentation" not in chrome_bridge_source
    assert "playwright.evaluate" not in mutation_primitives(chrome_bridge_source)


def test_chrome_bridge_fails_closed_without_locked_client_cdp_or_exact_same_page(
    fake_chrome_tab, application_tool_subject
) -> None:
    fake_chrome_tab.capabilities.remove("cdp")
    assert run_chrome_bridge_fixture(fake_chrome_tab, application_tool_subject).status == "blocked"
    fake_chrome_tab = valid_fake_chrome_tab()
    fake_chrome_tab.browser_client_sha256 = "0" * 64
    assert run_chrome_bridge_fixture(fake_chrome_tab, application_tool_subject).status == "blocked"
    fake_chrome_tab = valid_fake_chrome_tab()
    fake_chrome_tab.page_instance_nonce = "changed"
    assert run_chrome_bridge_fixture(fake_chrome_tab, application_tool_subject).clicks == 0


def test_subject_bound_form_contract_selects_only_the_official_post_form(dual_form_snapshot) -> None:
    contract = derive_application_form_contract(
        dual_form_snapshot,
        application_tool_subject=APPLICATION_TOOL_SUBJECT,
        policy=FORM_CAPTURE_POLICY,
    )
    assert contract.source_snapshot_sha256 == canonical_sha256(dual_form_snapshot)
    assert contract.application_tool_subject_sha256 == APPLICATION_TOOL_SUBJECT.sha256
    assert contract.document_form_count == 2
    assert contract.canonical_action_origin == "https://forms.hsforms.com"
    assert contract.canonical_action_path == CURRENT_OFFICIAL_ACTION_PATH
    assert contract.allowed_action_path_pattern == FORM_CAPTURE_POLICY.official_action_path_pattern
    assert contract.allowed_action_path_pattern.startswith("^")
    assert contract.allowed_action_path_pattern.endswith("$")
    assert re.fullmatch(contract.allowed_action_path_pattern, contract.canonical_action_path)
    assert contract.method == "POST"
    assert contract.complete_field_set == CURRENT_OFFICIAL_APPLICATION_FIELDS
    assert contract.unique_submit.form_scoped is True
    assert contract.unique_submit.initially_disabled is True
    assert re.fullmatch(r"[0-9a-f]{64}", contract.unique_submit.submit_identity_sha256)
    assert contract.initial_enabled_form_scoped_submit_count == 0
    assert contract.non_target_forms == ({"method": "GET", "selectable": False},)


@pytest.mark.parametrize(
    "mutation",
    [
        "action_origin", "action_path", "method_get", "form_identity", "remove_field",
        "add_field", "rename_field", "duplicate_field", "disable_required_field",
        "submit_outside_form", "duplicate_submit", "submit_identity", "initially_enabled_submit",
    ],
)
def test_form_contract_or_live_mutation_blocks_capture_and_click(dual_form_snapshot, mutation) -> None:
    contract = derive_application_form_contract(dual_form_snapshot, APPLICATION_TOOL_SUBJECT, FORM_CAPTURE_POLICY)
    live_document = mutate_target_form(copy.deepcopy(dual_form_snapshot), mutation)
    assert capture_pre_submit(live_document, AUTHORIZED_PACKET, contract, FORM_CAPTURE_POLICY).status == "fail"
    assert verify_and_click(live_document, AUTHORIZED_PACKET, contract).clicks == 0


@pytest.mark.parametrize(
    "method,action",
    [
        ("GET", CURRENT_OFFICIAL_ACTION),
        ("POST", "https://example.invalid/forms/official-looking"),
        ("POST", "https://forms.hsforms.com/outside-the-allowlisted-path"),
    ],
)
def test_get_form_and_action_decoys_are_never_selectable_or_clickable(
    dual_form_snapshot, method, action
) -> None:
    decoy_id = dual_form_snapshot.add_decoy_form(
        method=method,
        action=action,
        fields=CURRENT_OFFICIAL_APPLICATION_FIELDS,
        enabled_submit=True,
    )
    contract = derive_application_form_contract(
        dual_form_snapshot, APPLICATION_TOOL_SUBJECT, FORM_CAPTURE_POLICY
    )
    assert contract.document_form_count == 3
    result = select_application_form(dual_form_snapshot, contract, FORM_CAPTURE_POLICY)
    assert result.status == "pass"
    assert result.selected_form_identity_sha256 == contract.form_identity_sha256
    assert result.form(decoy_id).selectable is False
    assert result.form(decoy_id).clicks == 0


def test_second_contract_matching_post_form_blocks_as_ambiguous(dual_form_snapshot) -> None:
    contract = derive_application_form_contract(
        dual_form_snapshot, APPLICATION_TOOL_SUBJECT, FORM_CAPTURE_POLICY
    )
    dual_form_snapshot.clone_target_form_preserving_contract_identity()
    result = select_application_form(dual_form_snapshot, contract, FORM_CAPTURE_POLICY)
    assert result.status == "fail"
    assert result.reason == "matching_form_count_not_one"
    assert result.clicks == 0


def test_initially_disabled_submit_must_become_same_enabled_descendant_after_stable_readiness(
    dual_form_snapshot, authorized_packet
) -> None:
    contract = derive_application_form_contract(
        dual_form_snapshot, APPLICATION_TOOL_SUBJECT, FORM_CAPTURE_POLICY
    )
    assert contract.unique_submit.initially_disabled is True
    live = fill_authorized_values(copy.deepcopy(dual_form_snapshot), authorized_packet)
    live.enable_submit(contract.unique_submit.submit_identity_sha256)
    readiness = await_bounded_form_readiness(
        live,
        contract,
        timeout_ms=5_000,
        poll_interval_ms=100,
        stable_sample_count=3,
    )
    assert readiness.status == "pass"
    assert readiness.samples == 3
    assert readiness.submit_identity_sha256 == contract.unique_submit.submit_identity_sha256
    assert readiness.enabled_form_scoped_submit_count == 1
    assert capture_pre_submit(live, authorized_packet, contract, FORM_CAPTURE_POLICY).status == "pass"


@pytest.mark.parametrize("mutation", ["never_enabled", "identity_changed", "census_churn", "two_enabled"])
def test_form_readiness_fails_closed_on_timeout_or_unstable_census(
    dual_form_snapshot, authorized_packet, mutation
) -> None:
    contract = derive_application_form_contract(
        dual_form_snapshot, APPLICATION_TOOL_SUBJECT, FORM_CAPTURE_POLICY
    )
    live = mutate_readiness_fixture(dual_form_snapshot, authorized_packet, mutation)
    readiness = await_bounded_form_readiness(
        live, contract, timeout_ms=500, poll_interval_ms=50, stable_sample_count=3
    )
    assert readiness.status == "fail"
    assert readiness.clicks == 0


def test_atomic_click_reverifies_same_submit_identity_enabled_and_stable_census(
    ready_runtime_form, valid_form_contract
) -> None:
    pre_submit = capture_pre_submit(
        ready_runtime_form, AUTHORIZED_PACKET, valid_form_contract, FORM_CAPTURE_POLICY
    )
    result = verify_and_click(ready_runtime_form, AUTHORIZED_PACKET, valid_form_contract, pre_submit)
    assert result.clicks == 1
    assert result.submit_identity_sha256 == valid_form_contract.unique_submit.submit_identity_sha256
    ready_runtime_form.replace_submit_with_identical_label()
    assert verify_and_click(
        ready_runtime_form, AUTHORIZED_PACKET, valid_form_contract, pre_submit
    ).clicks == 0


def test_dynamic_action_query_is_not_a_trust_root(source_snapshot_with_dynamic_action_query) -> None:
    contract = derive_application_form_contract(
        source_snapshot_with_dynamic_action_query,
        APPLICATION_TOOL_SUBJECT,
        FORM_CAPTURE_POLICY,
    )
    assert contract.canonical_action_origin == "https://forms.hsforms.com"
    assert "?" not in contract.canonical_action_path
    assert "#" not in contract.canonical_action_path
    assert not hasattr(contract, "query_token")
    assert contract.source_snapshot_sha256 == canonical_sha256(source_snapshot_with_dynamic_action_query)
    live = source_snapshot_with_dynamic_action_query.with_rotated_action_query_token()
    assert select_application_form(live, contract, FORM_CAPTURE_POLICY).status == "pass"


def test_form_capture_classifies_dynamic_fields_and_compares_complete_authorized_values(
    valid_runtime_form, valid_form_contract
) -> None:
    result = capture_pre_submit(
        valid_runtime_form,
        AUTHORIZED_PACKET,
        valid_form_contract,
        FORM_CAPTURE_POLICY,
    )
    assert result.user_authorized_values == expected_authorized_form_values(AUTHORIZED_PACKET)
    assert set(result.user_authorized_values) >= {
        "first_name", "last_name", "message__oss", "planned_use_text", "qualification_text"
    }
    assert result.application_form_contract_sha256 == canonical_sha256(valid_form_contract)
    assert result.form_identity_sha256 == valid_form_contract.form_identity_sha256
    assert result.complete_live_field_set_sha256 == valid_form_contract.complete_field_set_sha256
    assert result.oauth_server_derived.github_handle == "Zeroxrain99"
    assert result.oauth_server_derived.repository == "Zeroxrain99/CodeSextant"
    assert result.opaque_sensitive_fields_have_no_values
    valid_runtime_form.add_hidden("unknown_dynamic_field", "x")
    assert capture_pre_submit(
        valid_runtime_form, AUTHORIZED_PACKET, valid_form_contract, FORM_CAPTURE_POLICY
    ).status == "fail"


def test_record_evidence_input_is_deterministic_complete_and_create_new(
    valid_evidence_request, complete_authority_response_root, tmp_path
) -> None:
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    first = record_evidence_input(
        request=valid_evidence_request,
        authority_response_root=complete_authority_response_root,
        product_subject=PRODUCT_SUBJECT,
        application_tool_subject=APPLICATION_TOOL_SUBJECT,
        application_tool_review=APPLICATION_TOOL_REVIEW,
        terms=TERMS,
        form_contract=FORM_CONTRACT,
        out=out_a,
        create_new=True,
    )
    second = record_evidence_input(
        request=valid_evidence_request,
        authority_response_root=complete_authority_response_root,
        product_subject=PRODUCT_SUBJECT,
        application_tool_subject=APPLICATION_TOOL_SUBJECT,
        application_tool_review=APPLICATION_TOOL_REVIEW,
        terms=TERMS,
        form_contract=FORM_CONTRACT,
        out=out_b,
        create_new=True,
    )
    assert first.canonical_bytes == second.canonical_bytes
    assert first.authority_response_manifest_sha256 == hash_complete_response_root(
        complete_authority_response_root
    )
    assert first.product_release_subject_sha256 == PRODUCT_SUBJECT.sha256
    assert first.application_tool_subject_sha256 == APPLICATION_TOOL_SUBJECT.sha256
    assert first.application_tool_review_sha256 == canonical_sha256(APPLICATION_TOOL_REVIEW)
    assert first.terms_sha256 == canonical_sha256(TERMS)
    assert first.application_form_contract_sha256 == canonical_sha256(FORM_CONTRACT)
    assert record_evidence_input(
        request=valid_evidence_request,
        authority_response_root=complete_authority_response_root,
        out=out_a,
        create_new=True,
    ).status == "fail"


def test_verify_evidence_input_rehashes_full_authority_responses_and_all_bindings(
    valid_evidence_input, complete_authority_response_root
) -> None:
    assert verify_evidence_input(
        valid_evidence_input,
        authority_response_root=complete_authority_response_root,
        product_subject=PRODUCT_SUBJECT,
        application_tool_subject=APPLICATION_TOOL_SUBJECT,
        application_tool_review=APPLICATION_TOOL_REVIEW,
        terms=TERMS,
        form_contract=FORM_CONTRACT,
    ).status == "pass"
    tamper_one_byte(next(iter_full_authority_response_bodies(complete_authority_response_root)))
    assert verify_evidence_input(
        valid_evidence_input,
        authority_response_root=complete_authority_response_root,
    ).status == "fail"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_response",
        "extra_response",
        "redirected_response",
        "mutable_response",
        "duplicate_response",
        "stale_response",
        "partial_manifest",
        "request_query_mismatch",
    ],
)
def test_authority_response_root_must_exactly_match_request_and_be_complete(
    valid_evidence_request, complete_authority_response_root, mutation
) -> None:
    mutated = mutate_authority_response_root(
        complete_authority_response_root,
        mutation,
    )
    assert verify_authority_response_root(
        request=valid_evidence_request,
        authority_response_root=mutated,
        require_exact_query_set=True,
        require_atomic_complete_manifest=True,
    ).status == "fail"


def test_evidence_stale_cleanup_is_owned_and_rejected_after_submission_start(
    valid_g8_context, started_submission
) -> None:
    assert cleanup_evidence_producer_outputs(valid_g8_context, transaction_state="prepare").status == "pass"
    before = snapshot_paths(valid_g8_context.evidence_producer_owned_paths)
    assert cleanup_evidence_producer_outputs(
        valid_g8_context, transaction_state=started_submission
    ).status == "fail"
    assert snapshot_paths(valid_g8_context.evidence_producer_owned_paths) == before


def test_submission_authorization_requires_exact_user_confirmation(
    product_subject, application_tool_subject, packet, terms, review, valid_confirmation
) -> None:
    authorization = authorize(product_subject, application_tool_subject, packet, terms, review, valid_confirmation)
    assert authorization.confirmation_sha256 == canonical_sha256(valid_confirmation)
    assert authorization.authorized_form_values == {
        "first_name": packet["payload"]["first_name"],
        "last_name": packet["payload"]["last_name"],
        "message__oss": packet["payload"]["message__oss"],
        "planned_use_text": packet["payload"]["planned_use_text"],
        "qualification_text": packet["payload"]["qualification_text"],
    }
    assert authorization.application_form_contract_sha256 == packet["payload"][
        "application_form_contract_sha256"
    ]
    assert authorization.acknowledgements == {
        "benefit_is_six_months_under_current_terms": True,
        "paid_plan_may_resume_or_continue_after_benefit": True,
        "enabled_overages_may_be_charged": True,
        "discretionary_and_current_terms_govern": True,
    }
    valid_confirmation["packet_sha256"] = "0" * 64
    assert authorize(product_subject, application_tool_subject, packet, terms, review, valid_confirmation).status == "fail"


@pytest.mark.parametrize("field", [
    "first_name", "last_name", "message__oss", "planned_use_text", "qualification_text"
])
@pytest.mark.parametrize("link", [
    "target_profile", "packet", "user_confirmation", "authorization", "pre_submit_runtime",
    "pre_submit_form", "pre_click", "submission",
])
def test_packet_authorization_runtime_and_final_verifier_bind_every_form_value(
    valid_g8_chain, field, link
) -> None:
    mutate_authorized_form_value(valid_g8_chain[link], field)
    assert verify_g8_chain(valid_g8_chain).status == "fail"


def test_only_authorize_launch_spec_is_the_g8_receipt_producer(
    receipt_registry, producer_launch_policy
) -> None:
    row = receipt_registry.row("G8", "claude-oss-authorization.json")
    assert row.producer_id == "g8_authorization"
    assert row.launch_spec_id == "g8_authorization_v1"
    spec = producer_launch_policy.spec(row.launch_spec_id)
    assert spec.producer_id == row.producer_id
    assert spec.entrypoint == "application/claude-for-oss/authorize_packet.py"
    assert spec.argv_prefix == ["authorize"]


def test_only_product_frozen_external_verifier_produces_tool_review_receipt(
    receipt_registry, producer_launch_policy,
) -> None:
    row = receipt_registry.row("G8", "claude-oss-application-tool-review.json")
    assert row.producer_id == "g8_application_tool_review"
    assert row.launch_spec_id == "g8_application_tool_review_v1"
    spec = producer_launch_policy.spec(row.launch_spec_id)
    assert spec.producer_id == row.producer_id
    assert spec.entrypoint == "tools/external_security_review.py"
    assert spec.argv_prefix == ["receipt-and-verify"]


def test_private_registry_extension_cannot_override_or_escape_public_authority() -> None:
    assert validate_merged_registry(PRIVATE_G8_EXTENSION).status == "pass"
    assert validate_merged_registry(extension_with_public_override()).status == "fail"
    assert validate_merged_registry(extension_with_parent_path()).status == "fail"


def test_current_official_fixture_preserves_every_published_route(official_terms) -> None:
    assert official_terms.maintainer_thresholds == {
        "dependent_repositories": 500,
        "dependent_packages": 100,
        "combined_monthly_downloads": 200_000,
        "external_merged_pull_requests_12_months": 100,
        "unique_external_contributors_12_months": 20,
        "openssf_criticality": Decimal("0.4"),
    }
    assert official_terms.has_core_contributor_route
    assert official_terms.has_ecosystem_impact_route
    assert official_terms.required_attestations >= {
        "github_account_at_least_two_years_and_in_good_standing",
        "not_anthropic_personnel_contractor_agent_program_operator_or_immediate_family_or_household",
        "no_active_benefit_and_no_duplicate_or_pending_application",
    }
    assert {field.semantic_name for field in official_terms.application_fields} >= {
        "first_name",
        "last_name",
        "message__oss",
        "planned_use_text",
        "qualification_text",
    }
    assert official_terms.field("message__oss").required is False
    assert official_terms.application_form_contract.canonical_action_origin == "https://forms.hsforms.com"
    assert official_terms.application_form_contract.document_form_count == 2
~~~

schema.json defines one nested shape shared by fixtures, dataclasses, serializers, and validators. Each registry `claude-oss-*.json` output uses the public `gate-status.schema.json` envelope bound to product `subject_sha256`; its typed G8 domain object under `payload` mandatorily binds `product_release_subject_sha256`, `application_tool_subject_sha256`, and the independently verified `application_tool_review_sha256`. `release_gate.py check --secondary-subject --required-receipt` validates the latter two without changing the public G0-G7 envelope schema. The immutable private source manifest includes the extension generator and its closed schema, but excludes both generated extension outputs. Only after `ApplicationToolSubject` freezes that source closure does the subject-bound generator emit ignored `application/claude-for-oss/receipt-registry-extension.json` and `producer-launch-policy-extension.json`; each embeds the exact application-subject digest and generator/schema digests and is authenticated through the `private_application` authority. Structural merge validation always rejects duplicate gates, filenames, producer IDs, or launch-spec IDs; public-row overrides; absolute, parent-traversing, or symlink-escaping declared paths; a wrong/missing application-subject binding; and any extension gate other than G8, but deliberately permits a confined later-task schema path that is not created yet. Development-time tests use synthetic subject-bound generator outputs; authoritative generation plus merged registry/launch-policy/schema/digest validation runs only in G8.1 after `ApplicationToolSubject` exists, using product-root `release_gate.py` plus authenticated public/product, private-source, and evidence roots. F1 validates public G0-G7 only and never requires a private path or G8 extension. The public G0-G7 registry remains independently complete inside the public export. `planned_use_text` and `qualification_text` are separate values, each capped at 500 English words as a private concision ceiling and each also constrained by its exact current live form limit; no combined `application_text` alias is accepted.

~~~json
{
  "G8": [
    {
      "filename": "claude-oss-application-tool-review.json", "producer_id": "g8_application_tool_review", "launch_spec_id": "g8_application_tool_review_v1", "schema": "release/evidence/gate-status.schema.json", "payload_schema": "release/external-review-receipt.schema.json",
      "depends_on": [
        {"gate": "G7", "filename": "github-publication.json", "receipt_sha256_pointer": "/dependency_receipts/github-publication.json"},
        {"gate": "G7", "filename": "public-smoke.json", "receipt_sha256_pointer": "/dependency_receipts/public-smoke.json"}
      ],
      "material_edges": [
        {"material_id": "producer_inputs", "kind": "input_manifest", "authority_id": "evidence", "path": "inputs/claude-oss-application-tool-review.inputs.json", "sha256_pointer": "/material_digests/producer_inputs", "canonicalization": "jcs", "required_roles": ["product_subject", "g7_publication", "g7_public_smoke", "product_execution_root", "application_tool_subject", "application_tool_manifest", "global_signing_environment_registry", "public_receipt_registry", "public_producer_launch_policy", "private_receipt_registry_extension", "private_producer_launch_policy_extension", "merged_registry_launch_policy_closure", "tool_review_scope", "tool_scan", "tool_review_request", "tool_review_input", "tool_findings", "reviewer_roles", "implementation_actors"]},
        {"material_id": "release_subject", "kind": "release_subject", "authority_id": "subject", "sha256_pointer": "/material_digests/release_subject", "canonicalization": "jcs"},
        {"material_id": "product_execution_root_receipt", "kind": "evidence_file", "authority_id": "evidence", "path": "g8-product-execution-root.json", "sha256_pointer": "/material_digests/product_execution_root_receipt", "canonicalization": "raw_bytes"},
        {"material_id": "application_tool_subject", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-application-tool-subject.json", "sha256_pointer": "/material_digests/application_tool_subject", "canonicalization": "raw_bytes"},
        {"material_id": "application_tool_scan", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-application-tool-scan.json", "sha256_pointer": "/material_digests/application_tool_scan", "canonicalization": "raw_bytes"},
        {"material_id": "application_tool_review_request", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-application-tool-review-request.json", "sha256_pointer": "/material_digests/application_tool_review_request", "canonicalization": "raw_bytes"},
        {"material_id": "application_tool_review_input", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-application-tool-review-input.json", "sha256_pointer": "/material_digests/application_tool_review_input", "canonicalization": "raw_bytes"},
        {"material_id": "application_tool_findings", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-application-tool-findings.json", "sha256_pointer": "/material_digests/application_tool_findings", "canonicalization": "raw_bytes"}
      ]
    },
    {
      "filename": "claude-oss-terms.json", "producer_id": "g8_terms", "launch_spec_id": "g8_terms_v1", "schema": "release/evidence/gate-status.schema.json", "payload_schema": "application/claude-for-oss/terms.schema.json",
      "depends_on": [{"gate": "G8", "filename": "claude-oss-application-tool-review.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-application-tool-review.json"}],
      "material_edges": [
        {"material_id": "producer_inputs", "kind": "input_manifest", "authority_id": "evidence", "path": "inputs/claude-oss-terms.inputs.json", "sha256_pointer": "/material_digests/producer_inputs", "canonicalization": "jcs", "required_roles": ["product_subject", "application_tool_subject", "application_tool_review", "terms_source", "application_form_contract"]},
        {"material_id": "release_subject", "kind": "release_subject", "authority_id": "subject", "sha256_pointer": "/material_digests/release_subject", "canonicalization": "jcs"},
        {"material_id": "application_tool_subject", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-application-tool-subject.json", "sha256_pointer": "/material_digests/application_tool_subject", "canonicalization": "raw_bytes"},
        {"material_id": "application_form_contract", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-application-form-contract.json", "sha256_pointer": "/material_digests/application_form_contract", "canonicalization": "raw_bytes"},
        {"material_id": "terms_source", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-terms-source.json", "sha256_pointer": "/material_digests/terms_source", "canonicalization": "raw_bytes"}
      ]
    },
    {
      "filename": "claude-oss-packet.json", "producer_id": "g8_packet", "launch_spec_id": "g8_packet_v1", "schema": "release/evidence/gate-status.schema.json", "payload_schema": "application/claude-for-oss/schema.json",
      "depends_on": [
        {"gate": "G7", "filename": "github-publication.json", "receipt_sha256_pointer": "/dependency_receipts/github-publication.json"},
        {"gate": "G7", "filename": "public-smoke.json", "receipt_sha256_pointer": "/dependency_receipts/public-smoke.json"},
        {"gate": "G8", "filename": "claude-oss-application-tool-review.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-application-tool-review.json"},
        {"gate": "G8", "filename": "claude-oss-terms.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-terms.json"}
      ],
      "material_edges": [
        {"material_id": "producer_inputs", "kind": "input_manifest", "authority_id": "evidence", "path": "inputs/claude-oss-packet.inputs.json", "sha256_pointer": "/material_digests/producer_inputs", "canonicalization": "jcs", "required_roles": ["product_subject", "application_tool_subject", "application_tool_review", "terms", "application_form_contract", "attestations", "target_profile", "evidence_input_request", "evidence_authority_response_manifest", "evidence_input"]},
        {"material_id": "release_subject", "kind": "release_subject", "authority_id": "subject", "sha256_pointer": "/material_digests/release_subject", "canonicalization": "jcs"},
        {"material_id": "product_execution_root_receipt", "kind": "evidence_file", "authority_id": "evidence", "path": "g8-product-execution-root.json", "sha256_pointer": "/material_digests/product_execution_root_receipt", "canonicalization": "raw_bytes"},
        {"material_id": "application_tool_subject", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-application-tool-subject.json", "sha256_pointer": "/material_digests/application_tool_subject", "canonicalization": "raw_bytes"},
        {"material_id": "evidence_input_request", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-evidence-input-request.json", "sha256_pointer": "/material_digests/evidence_input_request", "canonicalization": "raw_bytes"},
        {"material_id": "evidence_authority_response_manifest", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-evidence-authority-responses/manifest.json", "sha256_pointer": "/material_digests/evidence_authority_response_manifest", "canonicalization": "raw_bytes"},
        {"material_id": "evidence_input", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-evidence-input.json", "sha256_pointer": "/material_digests/evidence_input", "canonicalization": "raw_bytes"},
        {"material_id": "target_profile", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-target-profile.json", "sha256_pointer": "/material_digests/target_profile", "canonicalization": "raw_bytes"}
      ]
    },
    {
      "filename": "claude-oss-review.json", "producer_id": "g8_claim_review", "launch_spec_id": "g8_claim_review_v1", "schema": "release/evidence/gate-status.schema.json", "payload_schema": "application/claude-for-oss/review.schema.json",
      "depends_on": [
        {"gate": "G8", "filename": "claude-oss-application-tool-review.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-application-tool-review.json"},
        {"gate": "G8", "filename": "claude-oss-terms.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-terms.json"},
        {"gate": "G8", "filename": "claude-oss-packet.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-packet.json"}
      ],
      "material_edges": [
        {"material_id": "producer_inputs", "kind": "input_manifest", "authority_id": "evidence", "path": "inputs/claude-oss-review.inputs.json", "sha256_pointer": "/material_digests/producer_inputs", "canonicalization": "jcs", "required_roles": ["product_subject", "application_tool_subject", "application_tool_review", "terms", "packet", "review_request", "review_input", "reviewer_roles", "tool_reviewer_roles", "implementation_actors"]},
        {"material_id": "evidence_input_request", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-evidence-input-request.json", "sha256_pointer": "/material_digests/evidence_input_request", "canonicalization": "raw_bytes"},
        {"material_id": "evidence_authority_response_manifest", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-evidence-authority-responses/manifest.json", "sha256_pointer": "/material_digests/evidence_authority_response_manifest", "canonicalization": "raw_bytes"},
        {"material_id": "evidence_input", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-evidence-input.json", "sha256_pointer": "/material_digests/evidence_input", "canonicalization": "raw_bytes"},
        {"material_id": "claim_review_request", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-review-request.json", "sha256_pointer": "/material_digests/claim_review_request", "canonicalization": "raw_bytes"},
        {"material_id": "claim_review_input", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-review-input.json", "sha256_pointer": "/material_digests/claim_review_input", "canonicalization": "raw_bytes"}
      ]
    },
    {
      "filename": "claude-oss-authorization.json", "producer_id": "g8_authorization", "launch_spec_id": "g8_authorization_v1", "schema": "release/evidence/gate-status.schema.json", "payload_schema": "application/claude-for-oss/authorization.schema.json",
      "depends_on": [
        {"gate": "G8", "filename": "claude-oss-application-tool-review.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-application-tool-review.json"},
        {"gate": "G8", "filename": "claude-oss-terms.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-terms.json"},
        {"gate": "G8", "filename": "claude-oss-packet.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-packet.json"},
        {"gate": "G8", "filename": "claude-oss-review.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-review.json"}
      ],
      "material_edges": [
        {"material_id": "producer_inputs", "kind": "input_manifest", "authority_id": "evidence", "path": "inputs/claude-oss-authorization.inputs.json", "sha256_pointer": "/material_digests/producer_inputs", "canonicalization": "jcs", "required_roles": ["product_subject", "application_tool_subject", "application_tool_review", "terms", "packet", "review", "target_profile", "user_confirmation", "application_form_contract"]},
        {"material_id": "target_profile", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-target-profile.json", "sha256_pointer": "/material_digests/target_profile", "canonicalization": "raw_bytes"},
        {"material_id": "user_confirmation", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-user-confirmation.json", "sha256_pointer": "/material_digests/user_confirmation", "canonicalization": "raw_bytes"},
        {"material_id": "application_form_contract", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-application-form-contract.json", "sha256_pointer": "/material_digests/application_form_contract", "canonicalization": "raw_bytes"}
      ]
    },
    {
      "filename": "claude-oss-submission.json", "producer_id": "g8_submission", "launch_spec_id": "g8_submission_v1", "schema": "release/evidence/gate-status.schema.json", "payload_schema": "application/claude-for-oss/submission.schema.json",
      "depends_on": [
        {"gate": "G7", "filename": "github-publication.json", "receipt_sha256_pointer": "/dependency_receipts/github-publication.json"},
        {"gate": "G7", "filename": "public-smoke.json", "receipt_sha256_pointer": "/dependency_receipts/public-smoke.json"},
        {"gate": "G8", "filename": "claude-oss-application-tool-review.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-application-tool-review.json"},
        {"gate": "G8", "filename": "claude-oss-terms.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-terms.json"},
        {"gate": "G8", "filename": "claude-oss-packet.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-packet.json"},
        {"gate": "G8", "filename": "claude-oss-review.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-review.json"},
        {"gate": "G8", "filename": "claude-oss-authorization.json", "receipt_sha256_pointer": "/dependency_receipts/claude-oss-authorization.json"}
      ],
      "material_edges": [
        {"material_id": "producer_inputs", "kind": "input_manifest", "authority_id": "evidence", "path": "inputs/claude-oss-submission.inputs.json", "sha256_pointer": "/material_digests/producer_inputs", "canonicalization": "jcs", "required_roles": ["product_subject", "product_execution_root", "g7_publication", "g7_public_smoke", "application_tool_subject", "application_tool_review", "application_form_contract", "terms", "target_profile", "evidence_input_request", "evidence_authority_response_manifest", "evidence_input", "packet", "review", "authorization", "evidence_refresh", "pre_submit_runtime", "pre_submit_form", "pre_click", "submission_start", "confirmation_runtime", "browser_source", "submission_confirmation"]},
        {"material_id": "release_subject", "kind": "release_subject", "authority_id": "subject", "sha256_pointer": "/material_digests/release_subject", "canonicalization": "jcs"},
        {"material_id": "product_execution_root_receipt", "kind": "evidence_file", "authority_id": "evidence", "path": "g8-product-execution-root.json", "sha256_pointer": "/material_digests/product_execution_root_receipt", "canonicalization": "raw_bytes"},
        {"material_id": "application_tool_subject", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-application-tool-subject.json", "sha256_pointer": "/material_digests/application_tool_subject", "canonicalization": "raw_bytes"},
        {"material_id": "evidence_input_request", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-evidence-input-request.json", "sha256_pointer": "/material_digests/evidence_input_request", "canonicalization": "raw_bytes"},
        {"material_id": "evidence_authority_response_manifest", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-evidence-authority-responses/manifest.json", "sha256_pointer": "/material_digests/evidence_authority_response_manifest", "canonicalization": "raw_bytes"},
        {"material_id": "evidence_input", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-evidence-input.json", "sha256_pointer": "/material_digests/evidence_input", "canonicalization": "raw_bytes"},
        {"material_id": "evidence_refresh", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-evidence-refresh.json", "sha256_pointer": "/material_digests/evidence_refresh", "canonicalization": "raw_bytes"},
        {"material_id": "pre_submit_runtime", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-pre-submit-runtime.json", "sha256_pointer": "/material_digests/pre_submit_runtime", "canonicalization": "raw_bytes"},
        {"material_id": "pre_submit_form", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-pre-submit-form.json", "sha256_pointer": "/material_digests/pre_submit_form", "canonicalization": "raw_bytes"},
        {"material_id": "pre_click", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-pre-click.json", "sha256_pointer": "/material_digests/pre_click", "canonicalization": "raw_bytes"},
        {"material_id": "submission_start", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-submission-start.json", "sha256_pointer": "/material_digests/submission_start", "canonicalization": "raw_bytes"},
        {"material_id": "confirmation_runtime", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-confirmation-runtime.json", "sha256_pointer": "/material_digests/confirmation_runtime", "canonicalization": "raw_bytes"},
        {"material_id": "browser_source", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-browser-confirmation-source.json", "sha256_pointer": "/material_digests/browser_source", "canonicalization": "raw_bytes"},
        {"material_id": "submission_confirmation", "kind": "evidence_file", "authority_id": "evidence", "path": "claude-oss-confirmation.json", "sha256_pointer": "/material_digests/submission_confirmation", "canonicalization": "raw_bytes"}
      ]
    }
  ]
}
~~~

Every registry-owned G8 receipt has exact-key top-level `dependency_receipts` and `material_digests` maps in addition to the public envelope fields; undeclared, missing, duplicate, or extra keys fail. There is no public candidate pathname or standalone sealer API. Product-frozen `release_gate.py produce-and-seal` is the sole registered final writer: it authenticates the generated extension pair through the subject-bound `private_application` authority by closed schema, exact `ApplicationToolSubject` digest, generator/schema digest, and merged-closure digest; separately authenticates every private entrypoint/runtime/role file through that same authority; records both extension SHA-256 values in `sealed_by` for every G8 receipt; creates an inherited anonymous/delete-on-close exclusive candidate handle; launches the exact digest-bound producer without a shell or executable/runtime/output override; retains and validates that handle; computes both generic maps; and atomically create-new writes the registered basename. `check-receipt` independently re-hashes those same extension bytes and verifies one existing registered receipt without writing; `check` verifies the complete gate. The public launch-policy schema extension branch requires each private launch spec to have exactly `producer_id`, `authority_id`, `entrypoint`, `entrypoint_sha256`, closed `runtime`, string-array `argv_prefix`, `candidate_transport=inherited_exclusive_handle`, `signer_mode`, and only when needed the exact closed `role_launcher` object. Private specs cannot override public IDs/specs; their generated policy rows bind the already-frozen subject rather than becoming members of it.

Every row also has exactly one `producer_inputs` material edge of kind `input_manifest`. Its authority-relative path is `inputs/<receipt-stem>.inputs.json`, canonicalization is JCS, pointer is `/material_digests/producer_inputs`, and ordered `required_roles` is nonempty. The sealer creates/verifies the manifest from every dynamic producer argument; each entry is exactly `{role,kind:file|tree|closure_manifest,authority_id,path,size?,sha256,canonicalization}`, and trees/closure manifests are recursively rehashed before process start and again before final write. No receipt, producer, or caller may invent or omit an input role. The application-tool-review input manifest additionally binds the authenticated public registry/policy, both post-subject generated extension files, and `merged_registry_launch_policy_closure`: a recursively hashed closure-manifest view of every referenced payload/launch schema and actual entrypoint/runtime digest after both product-root validators pass. Only the extension generator and closed schema are members of `application-tool-manifest.json` and therefore `ApplicationToolSubject`; the generated extension outputs are ignored private-application files, bind that subject digest, and are re-hashed into every later receipt. This two-stage closure prevents both a subject/extension digest cycle and substitution of an unvalidated merge result. The closed authority IDs are `subject`, `product_source`, `public_export`, `public_clone`, `private_application`, `evidence`, and `release_assets`, and every material edge names exactly one. Evidence paths are relative to the authenticated evidence authority and therefore never repeat `release/evidence/`. Each command supplies the applicable authenticated absolute roots explicitly: no CWD, environment variable, receipt path, caller digest, or free-form material root is authority. Source/export/clone roots authenticate independently; aliasing `$publicCloneRoot` to `$publicExportRoot`, swapping roots, same-relative-path decoys, symlink/reparse escape, dirty closure, or forged matching digests fail before producer start.

The six private launch specs are closed as follows: `g8_application_tool_review_v1` launches product-frozen `tools/external_security_review.py` with prefix `receipt-and-verify` and signer mode `none` because it verifies already-signed request/reviewer ledgers; `g8_terms_v1` launches private `refresh_terms.py seal` with `none`; `g8_packet_v1` launches private `build_packet.py` with `none`; `g8_claim_review_v1` launches private `review_packet.py emit` with `os_credential_ed25519` and the exact product-frozen role launcher/`claim_signer` credential policy; `g8_authorization_v1` launches private `authorize_packet.py authorize` with `external_attestation_only`; and `g8_submission_v1` launches private `record_submission.py receipt` with `none` over already authenticated browser evidence. Every private Python spec copies the complete concrete locked-runtime identity from the authenticated public producer-launch policy, changes only the entrypoint authority/path/digest and fixed prefix, and is regenerated from actual ApplicationToolSubject bytes; descriptive digest strings, PATH runtimes, shell commands, and credential overrides are schema-invalid.

**Step 2: Run RED**

~~~powershell
Enter-CodeSextantPrivateDevelopmentCheckpoint
& $releasePython -m pytest (Join-Path $privateRoot 'tests\application\test_claude_oss_application_subject.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_packet.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_evidence.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_pre_submit.py') (Join-Path $privateRoot 'tests\application\test_chrome_form_bridge.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_receipts.py') -q
~~~

Expected: FAIL because the application modules and two-stage subject-bound extension generator do not exist. Product-root authoritative merge validation is intentionally deferred to G8.1, after a real `ApplicationToolSubject` exists; these tests use a synthetic subject fixture only to red-test generation and schema rules.

**Step 3: Implement public evidence collection**

~~~python
@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    kind: Literal[
        "github_git_object",
        "github_release_asset",
        "registry_metric_snapshot",
        "openssf_report",
        "official_roster",
        "osi_license",
        "anthropic_terms",
    ]
    citation_url: str
    authority_url: str
    authority: str
    resolved_object_id: str
    content_sha256: str
    observed_at_utc: datetime
    parsed_facts: Mapping[str, str | int | Decimal]
    refresh_mode: Literal["immutable_ref", "refetch_and_compare_facts"]


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str


@dataclass(frozen=True)
class EvidenceUse:
    consumer_kind: Literal[
        "claim", "track", "criterion", "downstream_dependency", "project", "github"
    ]
    consumer_id: str
    evidence_id: str


@dataclass(frozen=True)
class ExplicitOptionalText:
    state: Literal["explicit_empty", "explicit_value"]
    value: str


@dataclass(frozen=True)
class TargetProfile:
    target_github_account: str
    target_email: str
    first_name: str
    last_name: str
    message__oss: ExplicitOptionalText
    field_confirmations: Mapping[str, bool]
    value_sources: Mapping[str, Literal["explicit_user_input"]]


@dataclass(frozen=True)
class FormCensusEntry:
    form_identity_sha256: str
    method: str
    canonical_action_origin: str
    canonical_action_path: str
    complete_field_set_sha256: str
    enabled_form_scoped_submit_count: int
    selectable: bool


@dataclass(frozen=True)
class SubmitContract:
    submit_identity_sha256: str
    form_scoped: Literal[True]
    initially_disabled: Literal[True]


@dataclass(frozen=True)
class ApplicationFormContract:
    application_tool_subject_sha256: str
    source_snapshot_sha256: str
    document_form_count: int
    form_census: tuple[FormCensusEntry, ...]
    form_identity_sha256: str
    canonical_action_origin: Literal["https://forms.hsforms.com"]
    canonical_action_path: str
    allowed_action_path_pattern: str
    method: Literal["POST"]
    complete_field_set: tuple[FormFieldContract, ...]
    complete_field_set_sha256: str
    unique_submit: SubmitContract
    initial_enabled_form_scoped_submit_count: Literal[0]


@dataclass(frozen=True)
class GitHubEvidence:
    github_id: str
    login: str
    account_created_at_utc: datetime
    latest_public_activity_utc: datetime
    maintainer_repository: str


@dataclass(frozen=True)
class ProjectEvidence:
    project_id: str
    license_spdx: str
    license_file_sha256: str


@dataclass(frozen=True)
class QuantitativeCriterion:
    criterion_id: str
    criterion: str
    observed_value: Decimal
    required_value: Decimal


@dataclass(frozen=True)
class CoreContributorCriterion:
    criterion_id: str
    project: str
    listed_role: str


@dataclass(frozen=True)
class MaintainerTrack:
    kind: Literal["maintainer"]
    track_id: str
    criterion: QuantitativeCriterion | CoreContributorCriterion


@dataclass(frozen=True)
class DownstreamDependency:
    dependency_id: str
    independent_owner: str
    project: str
    immutable_revision: str
    dependency_mechanism: str


@dataclass(frozen=True)
class EcosystemImpactTrack:
    kind: Literal["ecosystem_impact"]
    track_id: str
    explanation: str
    downstream_dependencies: tuple[DownstreamDependency, ...]


@dataclass(frozen=True)
class Eligibility:
    track: MaintainerTrack | EcosystemImpactTrack
    attestations: Mapping[str, bool]
    terms_sha256: str


@dataclass(frozen=True)
class ApplicationPacket:
    author: str
    product_release_subject_sha256: str
    application_tool_subject_sha256: str
    application_tool_review_sha256: str
    application_form_contract_sha256: str
    target_profile: TargetProfile
    first_name: str
    last_name: str
    message__oss: ExplicitOptionalText
    github: GitHubEvidence
    project: ProjectEvidence
    eligibility: Eligibility
    claims: tuple[Claim, ...]
    evidence_table: tuple[EvidenceRecord, ...]
    evidence_uses: tuple[EvidenceUse, ...]
    planned_use_text: str
    qualification_text: str


def build_packet(
    public_repo: str,
    product_subject: ReleaseSubject,
    application_tool_subject: ApplicationToolSubject,
    terms: TermsSnapshot,
) -> ApplicationPacket:
    """Use only public GitHub/API URLs and verified G7 release evidence."""
~~~

`application-tool-manifest.json` is the private allowlist for the additive G8 scripts, schemas, tests, reviewer policy, lock inputs, and the private-trust extension generator/schema. It explicitly excludes the two subject-bound extension JSON outputs, which do not exist until after subject creation. `application_tool_subject.py` hashes that immutable source closure, the verified product-execution-root receipt, the unsealed official-terms source snapshot, implementation/reviewer authorities, and proofs that neither the frozen public-export tree nor the live public commit contains `application/`, `tests/application/`, internal `docs/superpowers/plans/` or `docs/superpowers/specs/`, private identities, browser captures, or G8 evidence. `browser-client-lock.json` records the explicitly selected active Chrome connector package/version, canonical `browser-client.mjs` path relative to its trusted plugin root, file SHA-256, required backend `extension`, and required tab capability/method `cdp`/`Runtime.evaluate`; it does not rely on `cdp.documentation()` or a capability-document file because the verified installed connector exposes no such stable document. Subject creation and verification re-hash the exact client source and reject an unset/out-of-root, missing, moved, or changed active client, while harmless inactive cache versions are ignored. The bridge integration test uses the real interface contract—`await tab.capabilities.get("cdp")` followed by `cdp.send("Runtime.evaluate", params, options)`—and separately confirms the live advertised capability. The private `chrome_form_bridge.mjs` digest plus the product-frozen initializer, node-context schema, and product Node-bootstrap/pre-import-verifier digests are carried by every runtime/pre-click/confirmation or recovery receipt. A connector or private bridge change creates a new `ApplicationToolSubject`; a product initializer, product Node bootstrap, external verifier, generic schema, or product-execution bootstrap change is a product change and requires rebuild/refreeze plus G4-G7. The tool emits the private subject without mutating `ReleaseSubject`; the next stage alone generates the two extensions against that immutable digest.

The product-frozen `release/Initialize-CodeSextantG8.ps1` defines idempotent `Initialize-G8Context`. The ACL-installed seed verifies its exact bytes and the complete content-addressed product execution root before dot-source. The initializer enables all three UTF-8 channels, requires `pwsh >= 7.4` strict/fail-fast behavior, re-verifies the product-root receipt, reruns the additive-only private-overlay audit, requires branch `application-private`, zero remotes, clean HEAD/index/worktree and no nonignored untracked path, then classifies transaction state before any cleanup or private import. It obtains the hash-locked Python, generic schemas, external-review engine, release gate, product Node bootstrap, and bootstrap only from the verified product root. In prepare mode it returns immutable absolute paths for every private executable; every product executable; every schema/policy; both subjects and product-root receipt; application-tool security review; evidence-input request/authority-response root and manifest/input; form contract; terms; attestations; target profile; packet; claim review; confirmation/authorization; refresh/runtime/pre-click/start/confirmation/submission/tombstone/quarantine; role/actor policies; browser lock/installed root; and exact product/private roots. It also atomically emits the JCS-canonical node-context bundle. No operational command resolves an executable, schema, registry, or evidence directory through current working directory. The initializer never creates, deletes, or overwrites transaction evidence.

`terms.schema.json` records both official source URLs, fetch timestamps, content digests, the current Maintainer Track criteria/thresholds, the Ecosystem Impact Track wording, benefit/discretion and six-month/billing/overage language, exact live form field IDs/labels/order/required flags/limits, and the full current general-eligibility field list. It also binds one schema-valid `application-form-contract` derived from the raw source snapshot and the exact `ApplicationToolSubject`: the full document form census (currently two forms), the one selected official POST form, canonical action origin exactly `https://forms.hsforms.com`, a strict allowlisted action-path pattern and matched canonical path, method, stable form-identity digest, full ordered normalized field set, and exactly one submit descendant scoped to that form. That submit identity is static and initially disabled; bounded readiness after filling must enable the same descendant without changing its identity or the form census. Query and fragment bytes are stripped before comparison and never become trust values; when the live action carries a mutable query token, the contract trusts only the raw-source snapshot digest plus the strict origin/path allowlist. Every non-target form, including the current GET form and any decoy, remains in the census but is unselectable. The parser has golden dual-form HTML fixtures covering GitHub good standing, immediate-family/household exclusion, one-active/no-duplicate requirements, action-query churn, decoys, and every form/field/submit mutation, and fails closed when mandatory official sections disappear; it never silently reuses an old terms snapshot.

The track is a discriminated union backed by one canonical `evidence_table` and one canonical sorted `evidence_uses` relation. Every claim, selected track, criterion, downstream dependency, project, and GitHub object has a stable consumer ID and carries no inline evidence ID or URL. `EvidenceUse(consumer_kind, consumer_id, evidence_id)` is the only link from those consumers to evidence, with the closed kinds `claim`, `track`, `criterion`, `downstream_dependency`, `project`, and `github`. Validation requires every required consumer to have at least one use, every evidence row to be reachable from at least one use, and exact absence of dangling consumer IDs, dangling evidence IDs, duplicate use triples, orphan rows, or unknown consumer kinds. `GitHubEvidence` and `ProjectEvidence` reject every `*_evidence_url`; all citation and authority URLs live only in `EvidenceRecord`. Every evidence row has a stable content-derived ID and one closed source kind. `github_git_object` and `github_release_asset` require a full commit/tag-object or versioned asset identity. `registry_metric_snapshot` permits only the pinned official npm/PyPI/crates/deps.dev endpoint plus an immutable public snapshot/citation and records package identity, observation window, parsed dependent/download facts, response digest, and UTC. `openssf_report` binds repository plus commit and report digest. `official_roster` binds the named foundation/language-project authority, roster revision/observation and immutable snapshot. `osi_license` and `anthropic_terms` permit only their official allowlisted hosts and exact content digests. `citation_url` is immutable; where the authority exposes a current metric/roster rather than an immutable URL, `authority_url` is separately allowlisted and must be re-fetched at submission time with the same-or-still-qualifying parsed facts. Default-branch URLs, `latest`, search pages, unpinned dashboards, arbitrary hosts, and self-authored metric assertions are rejected.

A Maintainer Track packet must name a quantitative criterion from the current official snapshot and meet its exact threshold using the applicable registry/OpenSSF evidence rows, or prove a currently recognized core-contributor role using an official-roster row. An Ecosystem Impact Track must identify at least one independently owned public project/package at a full immutable revision that imports, invokes, packages, or operationally depends on CodeSextant, plus a concrete adoption/dependent signal and mechanism. A self-authored explanation, planned integration, star count without dependency, or CodeSextant's own repository never satisfies it. An independent application reviewer must sign a separate exact track verdict `PROVEN`; `NOT_PROVEN` blocks. The validator also requires account age at least two years and good standing, public OSS activity within 90 days, owner/maintainer evidence, exact product license `Apache-2.0` plus public LICENSE digest and OSI evidence, an accessible public release, and immutable benchmark/security/provenance citations. The pre-G7 planning snapshot has zero public repositories; after G7, CodeSextant itself may satisfy recent activity but cannot by itself prove any Maintainer threshold or downstream dependence. The live evaluator—not a stale repo count—must return `ELIGIBILITY_TRACK_UNPROVEN` until one official track is genuinely proven.

General eligibility explicitly includes user-attested natural-person status, adult or age-of-majority status, eligible residence/location, sanctions/export-control eligibility, GitHub account age of at least two years **and good standing**, recent public OSS activity, no Anthropic employee/contractor/agent/program-operator **or immediate-family/household** relationship, and no active benefit or duplicate/pending application. `refresh_terms.py` may add newly required official fields; any missing, false, or unknown attestation fails closed. No GitHub field substitutes for a human attestation. `authorize_packet.py show-attestation-request` derives and displays every question ID and verbatim statement from the current schema-valid terms receipt, plus both subject and terms digests. `record-attestations` accepts exactly one explicit `--answer <id>=true|false` for every displayed ID, rejects omitted, duplicate, or unknown IDs, and writes a canonical `attestations.schema.json` document containing the exact question text/digest, answers, both subject/terms digests, `attested_by=user`, and UTC timestamp. It never defaults, infers, or copies answers from GitHub. The same tool's `show-target-profile-request` displays and requests separate confirmation of all five target values—GitHub account, email, `first_name`, `last_name`, and `message__oss`—plus both subject/terms digests; only a subsequent explicit `record-target-profile` command can produce the ignored schema-valid target profile. First/last name and the optional message must come from explicit user input, never a GitHub profile. `message__oss` is always present as either `{state: explicit_empty, value: ""}` or `{state: explicit_value, value: <confirmed text>}`. It rejects omitted, inferred, mismatched, stale, or generic confirmation and stores no credential/token. All later packet construction, authorization display, confirmation, authorization, pre-submit capture, click, receipt, and chain-verification commands consume that exact profile digest and bind all five values plus the form-contract digest. The validator prohibits `guaranteed`, `approved`, `entitled`, `promised six months`, and any benchmark claim unsupported by immutable published evidence.

`confirmation.schema.json` is the separate short-lived user decision: it binds both subjects, the independent application-tool security review, packet, terms, signed all-use-edge/track review, target-profile/account/email/first/last/message, the application-form-contract digest, distinct planned-use and qualification values, every evidence-table and evidence-use digest, action, issue/expiry times, and `authorized_by=user`. It also requires four explicit booleans covering the six-month benefit, paid-plan billing resumption/continuation, enabled overage charges, and then-current discretionary terms. It is created only by `authorize_packet.py record-confirmation` after `show-request` displays the immutable request. `authorization.schema.json` additionally binds that confirmation, tool review, target-profile, form-contract, and every exact authorized form-value digest and revalidates every input.

Submission ordering is fixed to prevent token leakage and time-of-check/time-of-use drift: first `refresh-evidence` re-fetches terms and every type-specific evidence authority; then the locked `chrome_form_bridge.mjs` uses the claimed existing Chrome tab and the sealed application-form contract to select exactly one matching official POST form inside the document. Selection is form-scoped: the live action must match canonical origin `https://forms.hsforms.com` and the allowlisted path, the stable form identity and full ordered field set must match, and exactly one static submit descendant must belong to that selected form. The submit may be initially disabled. After the bridge fills the selected form, it performs a bounded readiness wait with a stable form/field/submit census and requires that the same submit identity becomes enabled; replacement, duplication, timeout, or census drift fails closed. The current non-target GET form and any injected or live decoy are never candidates. The bridge then extracts a structured runtime-property snapshot (`input.value`, `textarea.value`, selections, labels, constraints, OAuth/server metadata) directly in page context. It never serializes `outerHTML` or raw DOM. `form-capture-policy.json` classifies fields into `user_authorized`, `oauth_server_derived`, `opaque_sensitive`, and narrowly allowlisted `analytics_ignored`. Only user-authorized values compare one-to-one with the packet; OAuth/server-derived handle/email/repository metadata are independently checked against the authorized target; opaque verification/CSRF/anti-automation fields record only semantic class, presence, and session-bound boolean—never value, digest, HTML, screenshot, log, or quarantine bytes. Any unclassified dynamic field fails closed.

`capture-pre-submit` validates that sanitized runtime snapshot and binds page-instance nonce, application-form-contract/form-identity/full-field-set/static-submit digests, form/runtime schema, bridge/client digests, all five user-confirmed target values plus distinct planned-use/qualification digests, server-derived identity digest, opaque-field-presence classes, evidence-refresh digest, and capture UTC. Before `start`, the bridge must prove the current tab advertises the locked `cdp` capability and that the same contract-bound submit identity became enabled after bounded readiness without census drift. `start` performs no long network work: it accepts only a fresh evidence refresh and a same-page, same-form-contract capture, validates authorization TTL, and writes one transaction with a 60-second `click_deadline_utc`. Chrome submission is allowed only through the manifest-bound bridge's single CDP `Runtime.evaluate` expression. In one synchronous page task it re-selects the exact contract-bound form, re-reads and canonicalizes the complete field set and non-sensitive runtime properties, requires the page/session/form/field/value/static-submit digests to equal the bound capture, proves the same submit remains enabled, checks the deadline, clicks that descendant once, and returns only a sanitized `pre-click` receipt. The ordinary connector `playwright.evaluate` is read-only and is explicitly forbidden as the submit primitive. If full CDP is unavailable, client/source/contract hashes drift, the expression throws, the tab/form/field set or submit identity/enabled state changes, candidate or submit count is not exactly one, or the sanitized result is absent, G8 remains blocked or becomes tombstoned according to whether `start` exists; no manual click occurs. `confirmation-runtime.schema.json` describes the connector's sanitized positive server-rendered result/reference-ID runtime snapshot, and `browser-confirmation-source.schema.json` describes the locally validated receipt derived from it; neither permits raw DOM, token bytes, or screenshots. Final confirmation binds start/authorization/form-contract/runtime/pre-submit/pre-click/evidence-refresh and all exact user-confirmed values. Any post-click uncertainty is ambiguous. Tombstoning first quarantines only the allowlisted sanitized receipts; it tolerates absent files, refuses paths outside the allowlist, forbids automatic retry, and requires explicit human disposition.

**Step 4: Run GREEN**

~~~powershell
$ErrorActionPreference = 'Stop'
Enter-CodeSextantPrivateDevelopmentCheckpoint
$chromePluginRoot = Join-Path $env:USERPROFILE '.codex\plugins\cache\openai-bundled\chrome'
$activeChromeClient = $env:CODESEXTANT_CHROME_BROWSER_CLIENT
if ([string]::IsNullOrWhiteSpace($activeChromeClient) -or -not (Test-Path -LiteralPath $activeChromeClient -PathType Leaf)) { throw 'set CODESEXTANT_CHROME_BROWSER_CLIENT to the active control-chrome skill browser-client.mjs path' }
& $releasePython (Join-Path $privateRoot 'application\claude-for-oss\application_tool_subject.py') lock-browser-client --client $activeChromeClient --trusted-root $chromePluginRoot --required-backend extension --required-capability cdp --required-method Runtime.evaluate --out (Join-Path $privateRoot 'application\claude-for-oss\browser-client-lock.json')
if ($LASTEXITCODE -ne 0) { throw 'unable to lock one exact installed Chrome connector client source and live CDP contract' }
& $releasePython -m pytest (Join-Path $privateRoot 'tests\application\test_claude_oss_application_subject.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_packet.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_evidence.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_pre_submit.py') (Join-Path $privateRoot 'tests\application\test_chrome_form_bridge.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_receipts.py') (Join-Path $privateRoot 'tests\application\test_g8_fresh_shell.py') -q
if ($LASTEXITCODE -ne 0) { throw 'private packet, evidence, browser, and fresh-shell tests failed' }
~~~

Expected: all tests pass. Live receipt generation is intentionally deferred to the G8 runbook because it requires a verified public release, a current official terms fetch, and explicit human attestations.

**Step 5: Commit tooling in the private source repository only**

~~~powershell
Enter-CodeSextantPrivateDevelopmentCheckpoint
$exactTaskCommitPath = Join-Path $productExecRoot 'tools\exact_task_commit.ps1'
$exactTaskCommitTestPath = Join-Path $productExecRoot 'tests\release\test_exact_task_commit.py'
if (-not (Test-Path -LiteralPath $exactTaskCommitPath -PathType Leaf) -or -not (Test-Path -LiteralPath $exactTaskCommitTestPath -PathType Leaf)) { throw 'authenticated product exact-task helper/test is missing' }
. $exactTaskCommitPath
Push-Location -LiteralPath $productExecRoot
try {
  & $releasePython -m pytest $exactTaskCommitTestPath -q
  if ($LASTEXITCODE -ne 0) { throw 'authenticated exact-task commit contract failed before private Task 2 commit' }
} finally {
  Pop-Location
}
$expectedStaged = @(& $releasePython (Join-Path $privateRoot 'application\claude-for-oss\application_tool_subject.py') manifest-paths --manifest (Join-Path $privateRoot 'application\claude-for-oss\application-tool-manifest.json') --partition packet-tooling) | Sort-Object
if ($LASTEXITCODE -ne 0 -or $expectedStaged.Count -eq 0) { throw 'Task 2 manifest partition enumeration failed' }
Invoke-ExactTaskCommit -RepositoryRoot $privateRoot -ExpectedPaths $expectedStaged -Message 'tools: build verifiable Claude OSS application packet'
Enter-CodeSextantPrivateDevelopmentCheckpoint
~~~

The G5 public-export allowlist must prove `application/`, `tests/application/`, `docs/superpowers/plans/`, and `docs/superpowers/specs/` are absent from the public repository and all reachable public history.

### Task 3: Implement independent typed evidence-use and track review validation

**Files:**

- Modify, keep private: application/claude-for-oss/application-tool-manifest.json
- Create, keep private: application/claude-for-oss/APPLICATION_TOOL_THREAT_MODEL.md
- Create, keep private: application/claude-for-oss/application-tool-review-scope.schema.json
- Create, keep private: application/claude-for-oss/application-tool-review-scope.json
- Create, keep private: application/claude-for-oss/application-tool-scan-policy.schema.json
- Create, keep private: application/claude-for-oss/application-tool-scan-policy.json
- Create, keep private: application/claude-for-oss/application-tool-reviewer-roles.json
- Create, keep private: application/claude-for-oss/review.schema.json
- Create, keep private: application/claude-for-oss/review-input.schema.json
- Create, keep private: application/claude-for-oss/reviewer-roles.json
- Create, keep private: application/claude-for-oss/review_packet.py
- Create, keep private and exclude from public export: tests/application/test_application_tool_security_review.py
- Create, keep private and exclude from public export: tests/application/test_claude_oss_review.py

**Step 1: Write RED tests**

~~~python
def test_review_requires_exactly_one_row_per_typed_evidence_use(valid_packet, valid_review) -> None:
    assert set(review_edges(valid_review)) == set(evidence_use_edges(valid_packet))
    valid_review["signed_statement"]["evidence_reviews"].pop()
    assert verify_review(valid_packet, valid_review).status == "fail"


def test_review_input_recorder_rejects_missing_duplicate_or_unknown_edges(valid_review_request) -> None:
    verdicts = explicit_verdicts_for(valid_review_request)
    verdicts.pop(next(iter(verdicts)))
    assert record_review_input(valid_review_request, verdicts).status == "fail"
    assert record_review_input(
        valid_review_request,
        explicit_verdicts_for(valid_review_request)
        | {("claim", "unknown-claim", "ev_" + "0" * 64): "supported"},
    ).status == "fail"


@pytest.mark.parametrize(
    "consumer_kind",
    ["claim", "track", "criterion", "downstream_dependency", "project", "github"],
)
def test_review_requires_explicit_signed_verdict_for_every_consumer_kind(
    valid_packet, valid_review, consumer_kind
) -> None:
    edge = next(edge for edge in evidence_use_edges(valid_packet) if edge[0] == consumer_kind)
    remove_signed_review_row(valid_review, edge)
    assert verify_review(valid_packet, valid_review).status == "fail"


def test_review_rejects_author_as_reviewer(valid_packet, valid_review) -> None:
    valid_review["payload"]["reviewer"] = valid_packet["payload"]["author"]
    assert verify_review(valid_packet, valid_review).status == "fail"


def test_review_rejects_changed_evidence_digest(valid_packet, valid_review) -> None:
    valid_packet["payload"]["evidence_table"][0]["content_sha256"] = "0" * 64
    assert verify_review(valid_packet, valid_review).status == "fail"


def test_review_must_sign_the_selected_track_as_proven(valid_packet, valid_review) -> None:
    not_proven = resign_review(
        valid_review,
        track_verdict="NOT_PROVEN",
        signing_key=VALID_INDEPENDENT_REVIEWER_KEY,
    )
    assert verify_detached_signature(not_proven, REVIEWER_ROLES).status == "pass"
    assert verify_review(valid_packet, not_proven).status == "fail"


def test_review_requires_valid_detached_signature_and_precommitted_role(valid_packet, valid_review) -> None:
    assert verify_review(valid_packet, valid_review, REVIEWER_ROLES, IMPLEMENTATION_ACTORS).status == "pass"
    valid_review["signature"] = "A" + valid_review["signature"][1:]
    assert verify_review(valid_packet, valid_review, REVIEWER_ROLES, IMPLEMENTATION_ACTORS).status == "fail"


def test_review_signer_cannot_be_packet_or_tooling_implementation_actor(valid_packet, valid_review) -> None:
    valid_review["signed_statement"]["reviewer_id"] = IMPLEMENTATION_ACTOR_ID
    assert verify_review(valid_packet, valid_review, REVIEWER_ROLES, IMPLEMENTATION_ACTORS).status == "fail"


def test_claim_review_signer_and_verifier_use_fresh_separate_key_environments() -> None:
    signer = launch_claim_review_role_probe(role="signer", polluted_parent_environment=True)
    verifier = launch_claim_review_role_probe(role="verifier", polluted_parent_environment=True)
    assert signer.fresh_process is True
    assert signer.visible_signing_keys == {"CODESEXTANT_APPLICATION_REVIEWER_SIGNING_KEY"}
    assert verifier.fresh_process is True
    assert verifier.visible_signing_keys == set()
    assert "CODESEXTANT_APPLICATION_REVIEWER_SIGNING_KEY" not in verifier.environment_names


def test_claim_review_verifier_rejects_parent_key_inheritance(valid_review_chain) -> None:
    result = verify_claim_review_in_fresh_role(
        valid_review_chain,
        polluted_parent_environment=True,
    )
    assert result.status == "pass"
    assert result.signing_key_environment_names == ()


def test_application_tool_security_review_binds_the_entire_private_attack_surface(
    valid_application_tool_security_review,
) -> None:
    statement = valid_application_tool_security_review["signed_statement"]
    assert statement["application_commit"] == APPLICATION_TOOL_SUBJECT.application_commit
    assert statement["application_tree_sha256"] == APPLICATION_TOOL_SUBJECT.application_tree_sha256
    assert statement["manifest_closure_sha256"] == APPLICATION_TOOL_SUBJECT.manifest_closure_sha256
    assert set(statement["reviewed_material_ids"]) == {
        "chrome_bridge_source",
        "cdp_runtime_evaluate_expression",
        "browser_client_lock",
        "form_contract_schema",
        "form_capture_policy_and_schema",
        "all_packet_and_receipt_schemas",
        "g8_initializer_and_blank_shell_recovery",
        "submission_tombstone_and_quarantine",
        "application_tool_threat_model",
        "public_exclusion_proof",
        "terms_source_and_derived_form_contract",
        "pinned_sast_and_dependency_scan",
    }
    remove_reviewed_material(valid_application_tool_security_review, "g8_initializer_and_blank_shell_recovery")
    assert verify_application_tool_security_review(valid_application_tool_security_review).status == "fail"


def test_tool_security_reviewer_is_distinct_from_implementers_and_claim_reviewer(
    valid_application_tool_security_review,
) -> None:
    tool_reviewer = valid_application_tool_security_review["signed_statement"]["reviewer_id"]
    claim_reviewer = VALID_CLAIM_REVIEW["signed_statement"]["reviewer_id"]
    assert tool_reviewer != claim_reviewer
    assert tool_reviewer not in IMPLEMENTATION_ACTORS
    assert tool_reviewer_key_id() != claim_reviewer_key_id()
    reuse_claim_reviewer_identity_and_key(valid_application_tool_security_review)
    assert verify_application_tool_security_review(valid_application_tool_security_review).status == "fail"


@pytest.mark.parametrize(
    ("role", "visible_key", "forbidden_key"),
    [
        ("requester", "CODESEXTANT_APPLICATION_TOOL_REVIEW_REQUESTER_SIGNING_KEY", "CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_SIGNING_KEY"),
        ("reviewer", "CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_SIGNING_KEY", "CODESEXTANT_APPLICATION_TOOL_REVIEW_REQUESTER_SIGNING_KEY"),
    ],
)
def test_tool_review_role_launcher_uses_fresh_mutually_exclusive_key_environments(
    role, visible_key, forbidden_key
) -> None:
    child = launch_review_role_probe(role=role, polluted_parent_environment=True)
    assert child.fresh_process is True
    assert child.visible_signing_keys == {visible_key}
    assert forbidden_key not in child.environment_names


def test_tool_review_receipt_process_is_keyless_and_binds_product_verifier_closure(
    valid_application_tool_review_chain,
) -> None:
    child = launch_review_role_probe(role="verifier", polluted_parent_environment=True)
    assert child.visible_signing_keys == set()
    receipt = valid_application_tool_review_chain["receipt"]
    assert receipt["product_execution_root_receipt_sha256"] == PRODUCT_EXECUTION_ROOT_RECEIPT_SHA256
    assert receipt["external_review_engine_sha256"] == EXTERNAL_REVIEW_ENGINE_SHA256
    assert receipt["external_review_schema_set_sha256"] == EXTERNAL_REVIEW_SCHEMA_SET_SHA256
    assert verify_application_tool_review_chain(valid_application_tool_review_chain).status == "pass"
    receipt["external_review_engine_sha256"] = "0" * 64
    assert verify_application_tool_review_chain(valid_application_tool_review_chain).status == "fail"


@pytest.mark.parametrize("severity", ["high", "critical"])
def test_open_high_or_critical_application_tool_finding_blocks_g8(
    valid_application_tool_review_chain, severity
) -> None:
    add_signed_tool_finding(valid_application_tool_review_chain, severity=severity, status="open")
    assert verify_application_tool_review_chain(valid_application_tool_review_chain).status == "fail"


def test_zero_application_tool_findings_requires_explicit_signed_scope_complete(
    valid_application_tool_review_chain,
) -> None:
    findings = valid_application_tool_review_chain["findings"]["signed_statement"]
    assert findings["findings"] == []
    assert findings["verdict"] == "no_findings"
    assert findings["scope_complete"] is True
    findings["scope_complete"] = False
    assert verify_application_tool_review_chain(valid_application_tool_review_chain).status == "fail"


@pytest.mark.parametrize(
    "downstream_link",
    [
        "terms", "attestations", "target_profile", "evidence_input_request",
        "evidence_authority_response_manifest", "evidence_input", "packet", "review_request",
        "review_input", "review", "user_confirmation", "authorization",
        "evidence_refresh", "pre_submit_runtime", "pre_submit_form", "submission_start",
        "pre_click", "confirmation_runtime", "browser_source", "submission_confirmation", "submission",
    ],
)
def test_every_later_g8_link_binds_application_tool_security_review(
    valid_g8_chain, downstream_link
) -> None:
    assert valid_g8_chain[downstream_link]["application_tool_review_sha256"] == canonical_sha256(
        valid_g8_chain["application_tool_security_review"]
    )
    valid_g8_chain[downstream_link]["application_tool_review_sha256"] = "0" * 64
    assert verify_g8_chain(valid_g8_chain).status == "fail"


@pytest.mark.parametrize(
    "link",
    [
        "product_execution_root_receipt",
        "g7_publication_receipt",
        "g7_public_smoke_receipt",
        "application_tool_subject",
        "application_tool_security_review",
        "terms",
        "application_form_contract",
        "attestations",
        "target_profile",
        "evidence_input_request",
        "evidence_authority_response_manifest",
        "evidence_input",
        "packet",
        "review_request",
        "review_input",
        "review",
        "user_confirmation",
        "authorization",
        "pre_submit_runtime",
        "pre_submit_form",
        "evidence_refresh",
        "submission_start",
        "pre_click",
        "confirmation_runtime",
        "browser_source",
        "submission_confirmation",
        "submission",
    ],
)
def test_g8_chain_rejects_every_mutated_link(valid_g8_chain, link) -> None:
    mutate_canonical_digest(valid_g8_chain[link])
    assert verify_g8_chain(
        valid_g8_chain,
        reviewer_roles=REVIEWER_ROLES,
        implementation_actors=IMPLEMENTATION_ACTORS,
    ).status == "fail"


def test_g8_chain_rejects_any_matching_submission_tombstone(valid_g8_chain) -> None:
    valid_g8_chain["submission_tombstone"] = tombstone_for(valid_g8_chain["submission_start"])
    assert verify_g8_chain(valid_g8_chain).status == "fail"


def test_confirmation_may_arrive_after_ttl_only_when_start_was_timely(valid_g8_chain) -> None:
    valid_g8_chain["submission_start"]["started_at_utc"] = valid_g8_chain["authorization"]["expires_at_utc"]
    valid_g8_chain["submission_confirmation"]["captured_at_utc"] = plus_minutes(
        valid_g8_chain["authorization"]["expires_at_utc"], 2
    )
    assert verify_g8_chain(valid_g8_chain).status == "pass"
    valid_g8_chain["submission_start"]["started_at_utc"] = plus_microseconds(
        valid_g8_chain["authorization"]["expires_at_utc"], 1
    )
    assert verify_g8_chain(valid_g8_chain).status == "fail"
~~~

**Step 2: Run RED**

~~~powershell
Enter-CodeSextantPrivateDevelopmentCheckpoint
& $releasePython -m pytest (Join-Path $privateRoot 'tests\application\test_application_tool_security_review.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_review.py') -q
~~~

Expected: FAIL because the application-tool review scope/roles and review_packet.py do not exist. A synthetic post-subject extension fixture is exercised inside the tests; no authoritative extension file is emitted before G8.1.

**Step 3: Implement the review schema and verifier**

For every canonical `(consumer_kind, consumer_id, evidence_id)` use edge, the signed receipt contains exactly one row validated by this schema fragment:

~~~json
{
  "type": "object",
  "required": ["consumer_kind", "consumer_id", "evidence_id", "evidence_record_sha256", "verdict", "reviewed_at_utc"],
  "properties": {
    "consumer_kind": {"enum": ["claim", "track", "criterion", "downstream_dependency", "project", "github"]},
    "consumer_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9._-]{2,127}$"},
    "evidence_id": {"type": "string", "pattern": "^ev_[0-9a-f]{64}$"},
    "evidence_record_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "verdict": {"enum": ["supported", "unsupported", "misleading"]},
    "reviewed_at_utc": {"type": "string", "format": "date-time"}
  },
  "additionalProperties": false
}
~~~

Before any claim review, `application-tool-review-scope.json` is the closed security-review authority for the private tooling. Its schema requires the exact private commit/tree and exhaustive manifest; bridge source and the single CDP expression; locked connector client; form contract/capture policies and every schema; initializer plus blank-shell recovery; transaction/tombstone/quarantine code; threat model; public-exclusion proof; raw terms/form-contract material; and the product-frozen external scan result. `APPLICATION_TOOL_THREAT_MODEL.md` uses STRIDE assets/boundaries/threats/controls/residual risks and maps every item to a scope ID. `application-tool-scan-policy.json` pins the public `tools/external_security_review.py`, its generic schemas, SAST/rule/dependency locks, zero-dependency Node bridge assertion, and exact commands. No private script may emit its own passing scan or review receipt.

`application-tool-reviewer-roles.json` precommits requester and `independent_tool_security_reviewer` UUIDs/key IDs/public keys. The sole signing-environment SSOT is product-frozen `release/signing-environment-registry.json` plus its schema; the private G8 extension never defines a competing registry. `ApplicationToolSubject`, the application-tool-review input manifest, both reviewer inventories, and the post-subject generated G8 launch-policy extension digest-bind that authenticated product registry. G8's allowed-name subset is exactly `CODESEXTANT_APPLICATION_REVIEWER_SIGNING_KEY`, `CODESEXTANT_APPLICATION_TOOL_REVIEW_REQUESTER_SIGNING_KEY`, and `CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_SIGNING_KEY`; role IDs are `application_tool_review_requester`, `independent_tool_security_reviewer`, `claim_signer`, `tool_review_verifier`, `claim_verifier`, and `receipt_verifier`. Each role has zero or one allowed key, and its forbidden set is generated as `global_known - allowed` across the complete G4-G8 product registry, never hand-maintained. `Invoke-CodeSextantG8ReviewRole` scans the parent and proposed child environment for the reserved pattern `^CODESEXTANT_[A-Z0-9_]*SIGNING_KEY$`; it rejects every match except the role's single registry-authorized allowed name, rejects an unregistered matching name even if absent from the known set, and gives keyless roles none. The claim launch spec uses the G5 schema's singular `role_launcher.allowed_key_env`, exact `forbidden_key_env` set, authenticated signing-registry path/digest, and exact reserved pattern generated from that same global registry; G6 clean-runner and private G8 tests require exact equality. The frozen external verifier also loads claim `reviewer-roles.json` and the universal implementation-actor roster and rejects any identity or key overlap across requester, tool-security reviewer, claim reviewer, and implementers. Its signed request/input/findings protocol binds every scope material and the exact scan digest. Empty findings are valid only as a signed `no_findings` with `scope_complete=true`; open high/critical findings block. The authenticated `g8_application_tool_review_v1` launch spec selects `tools/external_security_review.py receipt-and-verify`; private code cannot select or replace it. Product-frozen `release_gate.py produce-and-seal` alone supplies its inherited exclusive candidate handle and create-new writes registry-owned `claude-oss-application-tool-review.json`, recomputing both subjects, both generated extension digests, input manifest, dependencies, and material edges from the explicit VerificationContext. The registered receipt is a mandatory digest input to terms and every later G8 payload/receipt.

`review_packet.py show-review-request` creates a canonical request from the exact product subject, application-tool subject, application-tool security review, packet, terms, selected track, canonical evidence table, and canonical sorted `evidence_uses`. It displays each evidence row once and every typed use edge that relies on it, including claim, track, criterion, downstream-dependency, project, and GitHub consumers. After the reviewer supplies one explicit verdict per `(consumer_kind, consumer_id, evidence_id)` use edge **and** an explicit selected-track verdict covering its exact evidence-use closure, `record-review-input` writes a schema-valid ignored object binding request, both subjects, application-tool review, packet, terms, reviewer ID, verdicts, notes digests, and UTC; it rejects missing, duplicate, dangling, unknown, or uncovered consumer/evidence IDs and never defaults a verdict. The final review payload uses a detached Ed25519 structure: `signed_statement`, `statement_sha256`, `signer_key_id`, and `signature`. The signature covers only JCS-canonical UTF-8 bytes of `signed_statement` under `codesextant-claude-oss-review-v1\0`. The statement contains both subject/tool-review/packet/terms/review-request/review-input digests, canonical evidence-table and evidence-use digests, exact `track_claim_sha256`, track evidence-use closure, `track_verdict` (`PROVEN|NOT_PROVEN`), reviewer ID/role/process/tool-model identity, reviewer-role and universal implementation-actor-roster digests, and exactly one row for every canonical typed use edge. `reviewer-roles.json` precommits independent application reviewer UUIDs/key IDs/public keys; the existing `provenance/implementation-actors.json` remains the single authority for packet/tooling/product authors. Neither contains private key material, and verification rejects any overlap or unrecognized signer before considering verdicts. Allowed use-edge verdicts are supported, unsupported, and misleading. The verifier passes only when the detached signature is valid, every use edge is explicitly signed `supported`, every evidence row is reachable and passes its type-specific authority/canonicalization rules, and the selected official track is independently signed `PROVEN`. Unsupported/misleading use edges or a structurally valid, correctly re-signed `NOT_PROVEN` receipt fail by policy and require a new packet/review; a test that merely corrupts a signature is insufficient.

**Step 4: Run GREEN**

~~~powershell
$ErrorActionPreference = 'Stop'
Enter-CodeSextantPrivateDevelopmentCheckpoint
& $releasePython -m pytest (Join-Path $privateRoot 'tests\application\test_application_tool_security_review.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_review.py') -q
if ($LASTEXITCODE -ne 0) { throw 'signed application review tests failed' }
~~~

Expected: tests pass.

**Step 5: Commit**

~~~powershell
Enter-CodeSextantPrivateDevelopmentCheckpoint
$exactTaskCommitPath = Join-Path $productExecRoot 'tools\exact_task_commit.ps1'
$exactTaskCommitTestPath = Join-Path $productExecRoot 'tests\release\test_exact_task_commit.py'
if (-not (Test-Path -LiteralPath $exactTaskCommitPath -PathType Leaf) -or -not (Test-Path -LiteralPath $exactTaskCommitTestPath -PathType Leaf)) { throw 'authenticated product exact-task helper/test is missing' }
. $exactTaskCommitPath
Push-Location -LiteralPath $productExecRoot
try {
  & $releasePython -m pytest $exactTaskCommitTestPath -q
  if ($LASTEXITCODE -ne 0) { throw 'authenticated exact-task commit contract failed before private Task 3 commit' }
} finally {
  Pop-Location
}
$expectedStaged = @(& $releasePython (Join-Path $privateRoot 'application\claude-for-oss\application_tool_subject.py') manifest-paths --manifest (Join-Path $privateRoot 'application\claude-for-oss\application-tool-manifest.json') --partition independent-review) | Sort-Object
if ($LASTEXITCODE -ne 0 -or $expectedStaged.Count -eq 0) { throw 'Task 3 manifest partition enumeration failed' }
Invoke-ExactTaskCommit -RepositoryRoot $privateRoot -ExpectedPaths $expectedStaged -Message 'test: require signed review for every evidence use'
Enter-CodeSextantPrivateDevelopmentCheckpoint
~~~

## G7 Publication Runbook

This is an external, post-freeze operation, not a TDD task and not a source commit. Run it after Task 1 and all product source-changing work are committed, the ReleaseSubject is frozen, and G0-G6 are independently green for that exact subject digest. Tasks 2-3 are deliberately not a prerequisite: they run later in their distinct private application repository and cannot alter this product transaction.

Run G7.1-G7.4 in one launcher-owned `pwsh` 7.4-or-newer process. The only permitted operator entry is the protected native launch below; never invoke, dot-source, or paste a region of `Invoke-CodeSextantPublication.ps1` directly. `run-fixed` accepts only the closed `publication-g7` action, authenticates the runbook before its first statement as specified above, passes the expected root/subject through a closed argument contract, and preserves the child exit code:

~~~powershell
$g7Root = 'E:\ai-king\項目資料\CodeSextant'
$publicationRunbook = Join-Path $g7Root 'release\Invoke-CodeSextantPublication.ps1'
$g6RunbookLauncher = Join-Path $env:ProgramData 'CodeSextant\Trust\G6\codesextant-g6-runbook-launcher.exe'
if (-not (Test-Path -LiteralPath $g6RunbookLauncher -PathType Leaf)) { throw 'fixed protected G6 runbook launcher is missing' }
& $g6RunbookLauncher run-fixed --runbook $publicationRunbook --action publication-g7 --expected-root $g7Root --require-subject
if ($LASTEXITCODE -ne 0) { throw 'native launcher or publication G7 run failed closed' }
~~~

The following block is a generated region inside that externally authenticated runbook, not a standalone operator prelude. It reconstructs every path and executable from the tracked initializer and makes every unhandled nonzero native exit terminal; captured stdout is separately checked for exact shape. Before executing the fixed native verifier, it embeds a minimal inline Win32 `WinVerifyTrust` wrapper and the concrete 64-lowercase-hex Authenticode leaf-certificate SHA-256 frozen during G5; it imports no project code and reads no pin from a file, environment variable, receipt, or argument. The wrapper uses `WTD_REVOKE_WHOLECHAIN`, `WTD_CHOICE_FILE`, `WTD_STATEACTION_VERIFY`, requires status zero, hashes the returned signer leaf's raw DER, compares constant-time with the literal, and always calls `WTD_STATEACTION_CLOSE`. It then uses only OS ACL APIs to require the fixed verifier, seed, and every parent be non-reparse; owner exactly `NT SERVICE\TrustedInstaller`; protected, non-inherited DACL exactly `NT AUTHORITY\SYSTEM` and `BUILTIN\Administrators` FullControl plus the invoking ordinary-user SID ReadAndExecute/Synchronize; and no write/delete/rename/WRITE_DAC permission for that user. Only then may the static verifier execute. The initializer classifies transaction state before any cleanup or producer. An existing start enters recovery-only mode, reruns the same full public verifier plus generic G7 registry gate with the complete explicit VerificationContext and fixed G7 publication/public-smoke inputs, and can never fall through to G7.1; a tombstone/quarantine is terminal. Only a verified `prepare` state may remove a side-effect-free producer's own stale output.

~~~powershell
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
& chcp.com 65001 *> $null
$g7RootLocator = 'E:\ai-king\項目資料\CodeSextant'
$trustRoot = Join-Path $env:ProgramData 'CodeSextant\Trust\G8'
$staticSeedVerifier = Join-Path $trustRoot 'codesextant-g8-seed-static-verify.exe'
$seedVerifier = Join-Path $trustRoot 'Bootstrap-CodeSextantG8ProductExec.ps1'
$seedInstallReceiptLocator = Join-Path $trustRoot 'g8-seed-install.json'
if (-not (Test-Path -LiteralPath $staticSeedVerifier -PathType Leaf)) { throw 'fixed G6 native static seed verifier is missing' }
Assert-PinnedAuthenticodeWinTrust -LiteralPath $staticSeedVerifier
Assert-CodeSextantFixedTrustAcl -LiteralPath $trustRoot,$staticSeedVerifier,$seedVerifier,$seedInstallReceiptLocator -Owner 'NT SERVICE\TrustedInstaller' -SystemAndAdministratorsFullControl -InvokingUserReadExecuteSynchronize -ProtectedDacl -NoInheritedOrExtraAce -NoParentReparse
$verifiedSeedPath = [string](& $staticSeedVerifier verify --receipt $seedInstallReceiptLocator --subject (Join-Path $g7RootLocator 'release\evidence\release-subject.json') --print-verified-seed-path)
if ($LASTEXITCODE -ne 0 -or $verifiedSeedPath -cne $seedVerifier) { throw 'static verifier rejected signed receipt, live hashes, exact owner/ACE/DACL, or parent no-reparse closure' }
$initializerPath = [string](& $seedVerifier -VerifyG7Initializer -ExpectedRootLocator $g7RootLocator -SeedInstallReceiptLocator $seedInstallReceiptLocator -PrintAuthenticatedG7Initializer)
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($initializerPath) -or -not (Test-Path -LiteralPath $initializerPath -PathType Leaf)) { throw 'ACL seed rejected G6 receipt, frozen closure, or G7 initializer' }
. $initializerPath
$g7 = Initialize-G7Context -ExpectedRootLocator $g7RootLocator -AuthenticatedInitializerPath $initializerPath
$releasePython = $g7.ReleasePython
$ghExecutablePath = $g7.GhExecutablePath
$releaseGatePath = $g7.ReleaseGatePath
$publicExportToolPath = $g7.PublicExportToolPath
$publicationSecurityRefreshToolPath = $g7.PublicationSecurityRefreshToolPath
$githubPublishToolPath = $g7.GitHubPublishToolPath
$githubPreflightToolPath = $g7.GitHubPreflightToolPath
$githubPublicVerifyToolPath = $g7.GitHubPublicVerifyToolPath
$seedInstallVerifierToolPath = $g7.SeedInstallVerifierToolPath
$seedInstallReceiptPath = $g7.SeedInstallReceiptPath
$seedInstallReceiptSchemaPath = $g7.SeedInstallReceiptSchemaPath
if ($seedInstallReceiptPath -cne $seedInstallReceiptLocator) { throw 'G7 context did not return the fixed ProgramData seed-install receipt authority' }
$subjectPath = $g7.SubjectPath
$evidenceDir = $g7.EvidenceDirectory
$productSourceRoot = $g7.ProductSourceRoot
$releaseAssetsRoot = $g7.ReleaseAssetsRoot
$releaseIndexPath = $g7.ReleaseIndexPath
$releaseIndexBundlePath = $g7.ReleaseIndexBundlePath
$identityPath = $g7.IdentityPath
$identitySchemaPath = $g7.IdentitySchemaPath
$githubConfigPath = $g7.GitHubConfigPath
$planPath = $g7.PlanPath
$authorizationPath = $g7.AuthorizationPath
$publicEvidencePath = $g7.PublicEvidencePath
$securityRefreshPath = $g7.SecurityRefreshPath
$artifactsReceiptPath = $g7.ArtifactsReceiptPath
$securityReceiptPath = $g7.SecurityReceiptPath
$securityReviewReceiptPath = $g7.SecurityReviewReceiptPath
$runtimePolicyPath = $g7.RuntimePolicyPath
$checkPolicyPath = $g7.CheckPolicyPath
$githubControlsPath = $g7.GitHubControlsPath
$g4PublicAssetsPath = $g7.G4PublicAssetsPath
$g6PublicAssetsPath = $g7.G6PublicAssetsPath
$verifierBootstrapPath = $g7.VerifierBootstrapPath
$g8SeedVerifierPath = $g7.G8SeedVerifierPath
$signingPolicyPath = $g7.SigningPolicyPath
$publicationReceiptPath = $g7.PublicationReceiptPath
$publicSmokePath = $g7.PublicSmokePath
$transactionStartPath = $g7.TransactionStartPath
$transactionJournalPath = $g7.TransactionJournalPath
$transactionResultPath = $g7.TransactionResultPath
$transactionTombstonePath = $g7.TransactionTombstonePath
$transactionFailurePath = $g7.TransactionFailurePath
$transactionQuarantinePath = $g7.TransactionQuarantinePath
$repo = $g7.Repository
& $releasePython $seedInstallVerifierToolPath verify --receipt $seedInstallReceiptPath --receipt-schema $seedInstallReceiptSchemaPath --subject $subjectPath --signing-policy $signingPolicyPath --verifier-bootstrap $verifierBootstrapPath
if ($LASTEXITCODE -ne 0) { throw 'G6 seed-install receipt, fixed path, live seed, or ACL verification failed' }
switch ($g7.TransactionMode) {
  'recovery_only' {
    $recovery = Invoke-CodeSextantG7Recovery -Context $g7 -RequirePurposeBuiltVerifier -RequireGenericRegistryGate
    if ($recovery.Status -eq 'complete') { throw 'existing G7 transaction is fully verified; report only and never promote again' }
    throw 'existing G7 transaction was compensated/tombstoned or remains unresolved; forward producers are forbidden'
  }
  'terminal' { throw 'terminal G7 tombstone/quarantine state exists; explicit human disposition is required' }
  'prepare' { }
  default { throw "invalid G7 transaction mode: $($g7.TransactionMode)" }
}
~~~

### G7.1 Verify identity without changing public state

~~~powershell
$ghLogin = [string](& $ghExecutablePath api user --jq .login)
if ($ghLogin.Trim() -cne 'Zeroxrain99') { throw "wrong GitHub CLI identity: $ghLogin" }
$exportRoot = Join-Path $env:TEMP ("codesextant-g7-export-" + [guid]::NewGuid().ToString('N'))
& $ghExecutablePath repo clone $repo $exportRoot -- --branch main --single-branch
& $releasePython $publicExportToolPath assert-authoritative-root --subject $subjectPath --repo $exportRoot
if ($LASTEXITCODE -ne 0) { throw 'fresh public clone does not match ReleaseSubject' }
foreach ($gate in 'G0','G1','G2','G3','G4','G5','G6') {
  & $releasePython $releaseGatePath check --gate $gate --subject $subjectPath --evidence-dir $evidenceDir --product-source-root $productSourceRoot --public-export-root $exportRoot --release-assets-root $releaseAssetsRoot --release-index $releaseIndexPath --release-index-bundle $releaseIndexBundlePath --signing-policy $signingPolicyPath --verifier-bootstrap $verifierBootstrapPath
  if ($LASTEXITCODE -ne 0) { throw "frozen gate $gate failed" }
}
if (Test-Path -LiteralPath $securityRefreshPath -PathType Leaf) {
  & $releasePython $releaseGatePath check-receipt --gate G7 --receipt publication-security-refresh.json --subject $subjectPath --evidence-dir $evidenceDir --product-source-root $productSourceRoot --public-export-root $exportRoot --release-assets-root $releaseAssetsRoot --release-index $releaseIndexPath --release-index-bundle $releaseIndexBundlePath --signing-policy $signingPolicyPath --verifier-bootstrap $verifierBootstrapPath
  if ($LASTEXITCODE -ne 0) { throw 'existing publication-security-refresh receipt is invalid; do not delete or reseal it—tombstone the run and rebuild/refreeze' }
} else {
  & $releasePython $releaseGatePath produce-and-seal --gate G7 --receipt publication-security-refresh.json --subject $subjectPath --evidence-dir $evidenceDir --product-source-root $productSourceRoot --public-export-root $exportRoot --release-assets-root $releaseAssetsRoot --release-index $releaseIndexPath --release-index-bundle $releaseIndexBundlePath --signing-policy $signingPolicyPath --verifier-bootstrap $verifierBootstrapPath -- --export $exportRoot --artifacts-receipt $artifactsReceiptPath --security-receipt $securityReceiptPath --security-review-receipt $securityReviewReceiptPath --runtime-policy $runtimePolicyPath --check-policy $checkPolicyPath --github-controls $githubControlsPath --max-age-hours 24
  if ($LASTEXITCODE -ne 0) { throw 'atomic publication-security-refresh producer/sealer failed; receipt remains absent and publication is blocked' }
}
& $releasePython $publicationSecurityRefreshToolPath verify-receipt --subject $subjectPath --export $exportRoot --receipt $securityRefreshPath --artifacts-receipt $artifactsReceiptPath --security-receipt $securityReceiptPath --security-review-receipt $securityReviewReceiptPath --runtime-policy $runtimePolicyPath --check-policy $checkPolicyPath --github-controls $githubControlsPath --signing-policy $signingPolicyPath --verifier-bootstrap $verifierBootstrapPath --max-age-hours 24
if ($LASTEXITCODE -ne 0) { throw 'publication security refresh verification failed' }
~~~

Expected: `gh api user --jq .login` prints exactly `Zeroxrain99`; all seven frozen gates exit 0; a clean temporary clone exactly matches the ReleaseSubject export; and the refresh receipt is no more than 24 hours old and binds the same export, artifacts, SBOM/runtime closure, G5 security receipt, signed independent review, controls, scanner locks, and official advisory-feed responses. The current known CLI identity is `aiking931931`, so publication remains blocked until the user completes GitHub device/browser login or `gh auth switch` for Zeroxrain99. As of the planning snapshot, Node.js has officially announced a pending security release for the pinned line; the refresh must return nonzero and publication must remain blocked until the applicable fixed runtime is pinned, the product is rebuilt/refrozen, and G4-G6 are rerun. Do not waive or age out that hold.

Verify the intended Google-linked GitHub identity immediately before authorization. Use the Chrome connector only if it can operate in the existing logged-in session without Windows desktop automation or focus theft. Record only account handle, boolean email match, evidence method, and UTC timestamp in untracked `release/evidence/github-identity.json`. Expected handle is Zeroxrain99 and intended email is zeroxrain99@gmail.com. If the connector is blocked, give the user the exact two fields to confirm and wait for that confirmation; never drive Windows UI.

~~~powershell
Remove-Item -LiteralPath $identityPath -Force -ErrorAction SilentlyContinue
& $releasePython $githubPublishToolPath record-identity --handle Zeroxrain99 --intended-email-match true --evidence-method confirmed --out $identityPath
& $releasePython $githubPublishToolPath verify-identity --identity $identityPath --schema $identitySchemaPath
~~~

Expected: exit 0 and a canonical identity SHA-256; this exact digest is bound into the publication plan and therefore into the later authorization.

### G7.2 Build and authorize the immutable publication plan

~~~powershell
Remove-Item -LiteralPath $publicEvidencePath,$planPath -Force -ErrorAction SilentlyContinue
& $releasePython $githubPublishToolPath collect-public-evidence --subject $subjectPath --manifest $g4PublicAssetsPath --manifest $g6PublicAssetsPath --out $publicEvidencePath
& $releasePython $githubPublishToolPath plan --subject $subjectPath --config $githubConfigPath --controls $githubControlsPath --security-refresh $securityRefreshPath --verifier-bootstrap $verifierBootstrapPath --g8-seed-install-receipt $seedInstallReceiptPath --g8-seed-verifier $g8SeedVerifierPath --evidence-dir $evidenceDir --identity $identityPath --public-evidence $publicEvidencePath --out $planPath
& $releasePython $githubPublishToolPath show-authorization-request --plan $planPath
~~~

The plan contains one UUIDv4 `transaction_id`, the ReleaseSubject digest, canonical `github_identity_sha256`, `check_policy_sha256`, `github_controls_sha256`, `publication_security_refresh_sha256`, `release_index_sha256`, `verifier_bootstrap_sha256`, `g8_seed_verifier_sha256`, source and export commit/tree identities, exact product artifact names/hashes (including the signed release index and bundle), the SHA-256 of both G4/G6 public-asset manifests, every privacy-audited public evidence asset and hash, G0-G6 receipt hashes, owner/repository, derived version/tag, requested public visibility, and the exact post-publish compensation. It proves the full `private_capable` set—including pinned Semgrep CE, cargo clippy, Ruff security, dependency audits, custom taint/path tests—and signed independent review already passed against the private exact export. CodeQL and Scorecard are labeled only `public_corroboration`; they are not represented as evidence that was green before disclosure. Dependency-review is a future pull-request safeguard rather than a fabricated initial run. Its single transaction explicitly covers private evidence-asset upload, remote hash verification, visibility change, exact controls-policy application, public-corroboration dispatch/wait, draft-release publication, immediate fresh-process public verification, and—if any later phase fails—release back to draft, deletion of only evidence assets uploaded by this run, visibility back to private, and verification of the prior GitHub control-plane state. The plan and display also state the non-reversible residual risk: once public, bytes may already have been cloned, cached, indexed, or forked, and compensation cannot restore prior confidentiality. Present its canonical SHA-256, transaction ID, refreshed-security/index/bootstrap/seed/control digests, residual-risk warning, and full external effects to the user. A prior generic “好了” is not publication authorization because it does not bind this payload.

The publication-plan schema additionally requires `g8_seed_install_receipt_sha256` beside `g8_seed_verifier_sha256`; both appear unchanged in start/result/publication/public-smoke, and every producer recomputes the signed G6 receipt, fixed native bootstrap, live seed bytes, exact ACL, and parent no-reparse state before accepting them.

After explicit authorization, the context-owned absolute GitHub-publish tool writes a separate untracked receipt satisfying:

~~~json
{
  "action": "publish_github_release",
  "transaction_id": "UUIDv4 copied exactly from the immutable plan",
  "publication_plan_sha256": "64 lowercase hexadecimal characters",
  "owner": "Zeroxrain99",
  "repository": "CodeSextant",
  "visibility": "public",
  "acknowledged_irreversible_disclosure": true,
  "authorized_at_utc": "RFC 3339 timestamp",
  "expires_at_utc": "RFC 3339 timestamp no more than 30 minutes later",
  "authorized_by": "user"
}
~~~

The JSON Schema implements the descriptive value constraints above as `const`, `pattern`, and `format` rules. Authorization is never inserted into the plan it hashes. The recorder refuses unless the user explicitly acknowledged that rollback cannot revoke copies already cloned, cached, indexed, or forked. Any source, export, artifact, receipt, destination, transaction ID, or tag change invalidates authorization and requires a newly generated plan and a new explicit authorization.

~~~powershell
Remove-Item -LiteralPath $authorizationPath -Force -ErrorAction SilentlyContinue
& $releasePython $githubPublishToolPath record-authorization --plan $planPath --acknowledge-irreversible-disclosure --authorized-by user --expires-minutes 30 --out $authorizationPath
& $releasePython $githubPreflightToolPath --plan $planPath --authorization $authorizationPath --subject $subjectPath --controls $githubControlsPath --security-refresh $securityRefreshPath --verifier-bootstrap $verifierBootstrapPath --g8-seed-install-receipt $seedInstallReceiptPath --g8-seed-verifier $g8SeedVerifierPath --max-security-age-hours 24
~~~

Expected: exit 0 and no network mutation.

### G7.3 Promote the exact private staging repository

~~~powershell
$subject = Get-Content -Raw -Encoding UTF8 $subjectPath | ConvertFrom-Json
$publicationPlan = Get-Content -Raw -Encoding UTF8 $planPath | ConvertFrom-Json
$tag = $subject.release_tag
& $ghExecutablePath repo view $repo --json nameWithOwner,visibility,defaultBranchRef
& $ghExecutablePath run list --repo $repo --branch main --limit 20
& $ghExecutablePath release view $tag --repo $repo --json isDraft,tagName,targetCommitish,assets
if ((Test-Path -LiteralPath $transactionStartPath) -or (Test-Path -LiteralPath $transactionJournalPath) -or (Test-Path -LiteralPath $transactionResultPath) -or (Test-Path -LiteralPath $transactionTombstonePath)) { throw 'existing publication transaction state must be resumed or compensated; never overwrite or retry it' }
& $releasePython $githubPublishToolPath promote --plan $planPath --authorization $authorizationPath --subject $subjectPath --controls $githubControlsPath --security-refresh $securityRefreshPath --verifier-bootstrap $verifierBootstrapPath --g8-seed-install-receipt $seedInstallReceiptPath --g8-seed-verifier $g8SeedVerifierPath --start-out $transactionStartPath --mutation-journal-out $transactionJournalPath --result-out $transactionResultPath --tombstone $transactionTombstonePath --quarantine-dir $transactionQuarantinePath --failure-out $transactionFailurePath
if ($LASTEXITCODE -ne 0) { throw 'publication promotion failed or compensated; do not enter G7.4 in this process' }
~~~

After any process/session interruption, do not rerun `promote` or jump directly to G7.4. Open a blank `pwsh -NoProfile` and execute only the complete initializer prelude above. Its recovery-only branch invokes `github_publish.py recover` with every context-owned absolute path, then requires the same purpose-built public-chain verifier and generic G7 registry gate before it can report `complete`; the prelude terminates either way and never falls through to a producer. If the existing result and both gates do not fully validate, recovery atomically tombstones first, performs no forward mutation, reconstructs the authorized asset delta from live-minus-prior names/hashes plus the journal, compensates, and terminates the transaction permanently. It never redispatches a check, upload, visibility change, or release publication. `tests/release/test_g7_fresh_shell.py` spawns an actual blank `pwsh -NoProfile` with no inherited runbook variables and proves completed, crash-before-gate, interrupted, tampered, and missing-input paths use the locked Python, run both gates, and issue zero `promote` calls.

Before mutation, the tool requires the exact G5 private staging repository `Zeroxrain99/CodeSextant`, default branch `main`, the authorized export commit, every pre-public release-blocking workflow green, the fresh publication-security receipt still within 24 hours, the derived annotated tag object pointing exactly to that export commit, one matching draft release, the signed release index plus its Sigstore bundle, and every exact pinned-cosign-verified product bundle. It recomputes `release/github-controls.json` and rejects any digest mismatch or unavailable required control. It atomically creates the transaction-start record and rejects a first mutation unless that record's `started_at_utc` is within authorization TTL and the security-refresh age limit. The annotated Git tag is an identity pointer, not a separately claimed signed artifact; authenticity is provided by the hash-bound ReleaseSubject, GitHub API tag-object verification, and Sigstore/Rekor bundles whose certificate identity/issuer are fixed in the tracked signing policy. While the repository is still private, it uploads only the authorized G4/G6 public evidence assets, re-downloads them, and verifies every hash. It applies every control that GitHub permits while private and records exact API reads after writes: description/topics, vulnerability reporting, secret scanning and push protection, Dependabot settings, least-privilege Actions permissions, bypass-free main ruleset, branch protection, and required checks. A required control that the account cannot apply is a blocker, not an optional warning. It then changes visibility to public while the release remains draft, applies the remaining policy controls, and runs CodeQL and Scorecard only as post-visibility corroboration. Their run IDs/results are recorded and any unexpected failure or finding triggers compensation and a security disposition, but they are never represented as pre-public evidence; the all-green-before-disclosure claim rests on the pinned pre-public SAST/audit matrix and signed independent review. Dependency-review remains a configured future pull-request safeguard rather than a fabricated initial run. Only after corroboration and exact controls pass does it publish the draft release. `promote` does not report success merely after publication: it immediately launches its preliminary public verifier in a fresh child process and keeps the transaction open until that process passes, then atomically writes only the immutable transaction-result record. The authenticated G7 launch specs select `tools/github_publish.py receipt` and `tools/github_public_verify.py receipt`; those domain producers receive only the inherited exclusive candidate handle from product-frozen `release_gate.py produce-and-seal`, which is the sole final writer of registry-owned `github-publication.json` and `public-smoke.json`. Any failure at any point, including corroboration, preliminary post-publish public smoke, asset, release-index signature, Sigstore, clean-clone, controls, or Scorecard verification, triggers the authorized compensation.

Promotion mutates only the explicitly authorized control-plane fields recorded in the transaction snapshot: description/topics, supported security settings, rulesets/branch protections, visibility, this run's evidence assets, and the existing draft-release state. No rebuild, force push, second repository, history copy, or tag recreation is allowed. Internally the final two publication mutations are equivalent to:

~~~powershell
& $ghExecutablePath repo edit $repo --visibility public --accept-visibility-change-consequences
& $ghExecutablePath release edit $tag --repo $repo --draft=false
~~~

On failure after any mutation, the state machine first atomically writes a transaction tombstone and quarantines only allowlisted non-registered partial/intermediate evidence. A registered `publication-security-refresh.json`, `github-publication.json`, or `public-smoke.json` is immutable create-new evidence: rollback never deletes, moves, overwrites, invalidates, or reseals it. The tombstone and transaction ID make any failed/compensated chain unusable, while `check-receipt` preserves its audit bytes. Compensation then changes this run's release back to its prior draft state, deletes only G4/G6 evidence assets uploaded by this transaction (never pre-existing product artifacts), restores description/topics, vulnerability/Dependabot/security settings, rulesets/branch protections, workflow configuration, and visibility from the hash-bound start snapshot, and verifies the exact prior repository ID/export/tag/release/product-asset/control-plane state. It writes a private failed-transaction receipt with every API response hash and returns nonzero. It explicitly does not claim to revoke public clones, caches, indexes, forks, audit events, or completed check-run history. If compensation itself fails, the tombstone remains authoritative and the tool halts for explicit human disposition; it does not leave a reusable success receipt, upload, rebuild, or rewrite anything else.

The G7 publication receipt records the subject, publication-plan, authorization, publication-security-refresh, GitHub-controls, signed-release-index, pinned-verifier-bootstrap, canonical `g8_seed_install_receipt_sha256`, and independently re-hashed live `g8_seed_verifier_sha256`; transaction ID/start digest; API response hashes; public repository/release URLs; actor and UTC time; source/export identities; tag object and target; exact settings/ruleset/branch-protection/Actions-permission hashes; pre-public release-blocking receipt IDs and post-visibility corroboration run IDs; product/evidence asset IDs, sizes and hashes; release-index bundle identity; and cosign bundle/certificate/Rekor identities. `public-smoke.json` digest-binds this exact publication receipt, and the purpose-built verifier recomputes both before either is usable by G8.

For asset compensation, the start record is prior-state authority and contains no run-owned future IDs. The journal/result are observation authorities for IDs allocated after upload. Before deletion, rollback re-downloads the current release asset inventory and accepts an ID only when it is absent from the prior snapshot and its exact name plus SHA-256 appears in the authorized public-evidence set; it rejects every prior ID and every ambiguous name/hash. The transaction result and final receipt bind the mutation-journal digest.

### G7.4 Reverify the public release in a fresh deterministic process

One purpose-built fresh verifier process owns the fresh clone, release download, exact asset-union check, SHA-256 checks, policy-rooted pinned-cosign verification, clean-clone build/tests, documented quickstart smoke, and atomic receipt write. This is deterministic process isolation, not a claim of an independent human reviewer. The receipt binds verifier executable/lock digests and a fresh process nonce. The entire verifier plus final cross-receipt gate is inside one compensated transaction; every nonzero native exit becomes an exception, and no raw `exit` bypasses compensation:

~~~powershell
try {
  $publicationPlan = Get-Content -Raw -Encoding UTF8 $planPath | ConvertFrom-Json
  $sessionRoot = Join-Path $env:TEMP ("codesextant-public-smoke-" + [guid]::NewGuid().ToString('N'))
  if (Test-Path -LiteralPath $publicationReceiptPath -PathType Leaf) {
    & $releasePython $releaseGatePath check-receipt --gate G7 --receipt github-publication.json --subject $subjectPath --evidence-dir $evidenceDir --product-source-root $productSourceRoot --public-export-root $exportRoot --release-assets-root $releaseAssetsRoot --release-index $releaseIndexPath --release-index-bundle $releaseIndexBundlePath --signing-policy $signingPolicyPath --verifier-bootstrap $verifierBootstrapPath
    if ($LASTEXITCODE -ne 0) { throw 'existing github-publication receipt is invalid; never delete or reseal it' }
  } else {
    & $releasePython $releaseGatePath produce-and-seal --gate G7 --receipt github-publication.json --subject $subjectPath --evidence-dir $evidenceDir --product-source-root $productSourceRoot --public-export-root $exportRoot --release-assets-root $releaseAssetsRoot --release-index $releaseIndexPath --release-index-bundle $releaseIndexBundlePath --signing-policy $signingPolicyPath --verifier-bootstrap $verifierBootstrapPath -- --plan $planPath --authorization $authorizationPath --transaction-start $transactionStartPath --mutation-journal $transactionJournalPath --controls $githubControlsPath --security-refresh $securityRefreshPath --g8-seed-install-receipt $seedInstallReceiptPath --g8-seed-verifier $g8SeedVerifierPath --transaction-result $transactionResultPath
    if ($LASTEXITCODE -ne 0) { throw 'atomic github-publication producer/sealer failed' }
  }
  & $releasePython $githubPublicVerifyToolPath prepare-clean-clone --repo $repo --subject $subjectPath --fresh-root $sessionRoot --signing-policy $signingPolicyPath --verifier-bootstrap $verifierBootstrapPath
  if ($LASTEXITCODE -ne 0) { throw 'independent public clean-clone preparation failed' }
  if ((Resolve-Path -LiteralPath $sessionRoot).Path -ceq (Resolve-Path -LiteralPath $exportRoot).Path) { throw 'public_clone and public_export authorities must be distinct roots' }
  if (Test-Path -LiteralPath $publicSmokePath -PathType Leaf) {
    & $releasePython $releaseGatePath check-receipt --gate G7 --receipt public-smoke.json --subject $subjectPath --evidence-dir $evidenceDir --product-source-root $productSourceRoot --public-export-root $exportRoot --public-clone-root $sessionRoot --release-assets-root $releaseAssetsRoot --release-index $releaseIndexPath --release-index-bundle $releaseIndexBundlePath --signing-policy $signingPolicyPath --verifier-bootstrap $verifierBootstrapPath
    if ($LASTEXITCODE -ne 0) { throw 'existing public-smoke receipt is invalid; never delete or reseal it' }
  } else {
    & $releasePython $releaseGatePath produce-and-seal --gate G7 --receipt public-smoke.json --subject $subjectPath --evidence-dir $evidenceDir --product-source-root $productSourceRoot --public-export-root $exportRoot --public-clone-root $sessionRoot --release-assets-root $releaseAssetsRoot --release-index $releaseIndexPath --release-index-bundle $releaseIndexBundlePath --signing-policy $signingPolicyPath --verifier-bootstrap $verifierBootstrapPath -- --repo $repo --plan $planPath --authorization $authorizationPath --controls $githubControlsPath --security-refresh $securityRefreshPath --transaction-start $transactionStartPath --publication-receipt $publicationReceiptPath --fresh-root $sessionRoot --g8-seed-install-receipt $seedInstallReceiptPath --g8-seed-verifier $g8SeedVerifierPath
    if ($LASTEXITCODE -ne 0) { throw 'atomic public-smoke producer/sealer failed' }
  }
  & $releasePython $githubPublicVerifyToolPath verify-g7-chain --subject $subjectPath --plan $planPath --authorization $authorizationPath --controls $githubControlsPath --security-refresh $securityRefreshPath --verifier-bootstrap $verifierBootstrapPath --g8-seed-install-receipt $seedInstallReceiptPath --g8-seed-verifier $g8SeedVerifierPath --transaction-start $transactionStartPath --publication-receipt $publicationReceiptPath --smoke-receipt $publicSmokePath --tombstone $transactionTombstonePath
  if ($LASTEXITCODE -ne 0) { throw "G7 cross-receipt verification failed with exit $LASTEXITCODE" }
  & $releasePython $releaseGatePath check --gate G7 --subject $subjectPath --evidence-dir $evidenceDir --product-source-root $productSourceRoot --public-export-root $exportRoot --public-clone-root $sessionRoot --release-assets-root $releaseAssetsRoot --release-index $releaseIndexPath --release-index-bundle $releaseIndexBundlePath --signing-policy $signingPolicyPath --verifier-bootstrap $verifierBootstrapPath
  if ($LASTEXITCODE -ne 0) { throw "G7 registry gate failed with exit $LASTEXITCODE" }
} catch {
  $originalFailure = $_
  & $releasePython $githubPublishToolPath rollback --plan $planPath --authorization $authorizationPath --transaction-start $transactionStartPath --mutation-journal $transactionJournalPath --subject $subjectPath --controls $githubControlsPath --security-refresh $securityRefreshPath --verifier-bootstrap $verifierBootstrapPath --g8-seed-install-receipt $seedInstallReceiptPath --failed-phase independent-public-verify-or-final-gate --preserve-registered-receipt $publicationReceiptPath --preserve-registered-receipt $publicSmokePath --tombstone $transactionTombstonePath --quarantine-dir $transactionQuarantinePath --out $transactionFailurePath
  if ($LASTEXITCODE -ne 0) { throw "G7 failed and compensation could not restore GitHub control-plane state; tombstone remains authoritative. Original failure: $originalFailure" }
  throw "G7 failed; GitHub control-plane compensation completed but public copies may persist. Original failure: $originalFailure"
}
~~~

Expected: PUBLIC, Apache-2.0 recognized, main, exact topics, exact `release/github-controls.json` state, matching tag/export commit, the exact product-plus-evidence asset union with no extras, the signed release index and its policy-rooted Sigstore bundle verified first through the hash-pinned verifier bootstrap, all other exact hashes/bundles enumerated only by that authenticated index, clean-clone build/tests, and the complete documented quickstart smoke: cryptographically verified install, doctor, index fixture, CLI map/refs, MCP initialize/tools/list/tools/call, authenticated HTTP query, cryptographically verified update, rollback, failed-update auto-rollback, and uninstall. The verifier also records the publication-plan, authorization, security-refresh, controls, release-index, verifier-bootstrap, and installed-G8-seed digests; transaction ID/start digest; ruleset/check/security-setting state; and public CodeQL/Scorecard corroboration results with their post-visibility timing explicitly labeled. G7 exits 0 only when the acyclic chain verifies in order: `publication-security-refresh` binds the ReleaseSubject/export/artifact/SBOM/runtime/SAST/review closure; the immutable publication plan binds that refresh and seed digest; authorization binds the plan; transaction start binds plan+authorization+refresh+controls+seed; and `github-publication` plus `public-smoke` bind that start, re-hashed seed, and every upstream digest. The refresh was within 24 hours when the transaction started, no matching tombstone exists, and the purpose-built DAG validator plus generic registry gate pass. The refresh never contains the not-yet-created plan or authorization digest. No source or documentation commit follows this runbook.

## G8 Claude for Open Source Submission Runbook

This is an external, post-G7 operation, not a source commit. G7 must already be green for the immutable product `ReleaseSubject`. G8 additionally creates a private `ApplicationToolSubject` for the exact application scripts, schemas, official-terms snapshot, and exclusion proof used here, then requires a distinct independent signed application-tool security review before producing any later application receipt. Every later G8 receipt binds both subject digests and that tool-review digest.

The two subjects have deliberately different invalidation boundaries:

- A product/source/artifact change invalidates `ReleaseSubject` and requires G4-G7 again before G8.
- A current-terms, private application script, private schema, form-field, or application-review-policy change invalidates only `ApplicationToolSubject` and every derived G8 receipt. Update and independently review the private G8 tooling, create a new `ApplicationToolSubject`, then restart G8.1; the already-published immutable product subject and G7 receipts remain valid.
- `application/claude-for-oss/`, its tests, raw browser captures, credentials, attestations, and all G8 private evidence are excluded from the public export and are not members of `ReleaseSubject`. `application_tool_subject.py` proves both the G7 export tree and the exact public GitHub commit omit them. A missing or failed exclusion proof is fatal.

**Current truthful state: G8 is BLOCKED.** The pre-G7 snapshot exposes zero public repositories; after G7 the account will contain CodeSextant, so that count is not a durable blocker. The durable verified gaps are that no current Maintainer threshold/core-contributor route is proven and no independently verifiable downstream project meaningfully depends on CodeSextant. Account age or CodeSextant's own publication alone proves neither track. Do not build an approvable packet, request authorization, or submit until the live evaluator proves one current official track; return `ELIGIBILITY_TRACK_UNPROVEN`, never reinterpret explanation as adoption.

Run G8.1-G8.6 in one launcher-owned `pwsh` 7.4-or-newer process. Every fresh-shell, restart, or recovery entry repeats this one external command; direct `pwsh -File`, dot-source, or pasted execution of the generated body is forbidden. `CODESEXTANT_G8_PRODUCT_EXEC_ROOT` and `CODESEXTANT_G8_PRIVATE_ROOT` remain locators only and gain no authority by being inherited. The launcher authenticates the exact product-root runbook before its first statement, permits only the closed `publication-g8` action, and preserves the child exit code:

~~~powershell
$productExecRootLocator = [string]$env:CODESEXTANT_G8_PRODUCT_EXEC_ROOT
if ([string]::IsNullOrWhiteSpace($productExecRootLocator) -or -not [IO.Path]::IsPathFullyQualified($productExecRootLocator)) { throw 'set CODESEXTANT_G8_PRODUCT_EXEC_ROOT to the verified content-addressed product root' }
$publicationRunbook = Join-Path $productExecRootLocator 'release\Invoke-CodeSextantPublication.ps1'
$g6RunbookLauncher = Join-Path $env:ProgramData 'CodeSextant\Trust\G6\codesextant-g6-runbook-launcher.exe'
if (-not (Test-Path -LiteralPath $g6RunbookLauncher -PathType Leaf)) { throw 'fixed protected G6 runbook launcher is missing' }
& $g6RunbookLauncher run-fixed --runbook $publicationRunbook --action publication-g8 --expected-root $productExecRootLocator --require-subject
if ($LASTEXITCODE -ne 0) { throw 'native launcher or publication G8/recovery run failed closed' }
~~~

The following block is generated body inside that authenticated child and must never be run manually. The same literal-pin inline WinVerifyTrust and exact TrustedInstaller/protected-DACL/no-reparse checks from G7 then run as defense in depth before the fixed static verifier, seed, or any product/private executable. The static verifier and signed G6 seed-install receipt authenticate the seed; the product-root receipt authenticates the complete ReleaseSubject/Sigstore root, fixed G7 publication/public-smoke paths and digests, locked Python, Node host/bootstrap, and initializer before dot-source. No environment receipt path/hash pair is accepted. The initializer audits clean product/private state and additive overlay, classifies transaction state before cleanup/producer/private import, reconstructs every authority as a canonical absolute path, and emits one create-new JCS context bundle. Recovery/terminal state cannot fall through, and every stage or human/connector return re-audits trust closure.

~~~powershell
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
& chcp.com 65001 *> $null
$productExecRoot = [string]$env:CODESEXTANT_G8_PRODUCT_EXEC_ROOT
if ([string]::IsNullOrWhiteSpace($productExecRoot) -or -not [IO.Path]::IsPathFullyQualified($productExecRoot)) { throw 'set CODESEXTANT_G8_PRODUCT_EXEC_ROOT to the exact content-addressed root printed by bootstrap-private' }
$productExecRoot = (Resolve-Path -LiteralPath $productExecRoot).Path
$productExecReceiptPath = Join-Path $productExecRoot 'release\evidence\g8-product-execution-root.json'
$trustRoot = Join-Path $env:ProgramData 'CodeSextant\Trust\G8'
$staticSeedVerifier = Join-Path $trustRoot 'codesextant-g8-seed-static-verify.exe'
$seedVerifier = Join-Path $trustRoot 'Bootstrap-CodeSextantG8ProductExec.ps1'
$seedInstallReceiptLocator = Join-Path $trustRoot 'g8-seed-install.json'
Assert-PinnedAuthenticodeWinTrust -LiteralPath $staticSeedVerifier
Assert-CodeSextantFixedTrustAcl -LiteralPath $trustRoot,$staticSeedVerifier,$seedVerifier,$seedInstallReceiptLocator -Owner 'NT SERVICE\TrustedInstaller' -SystemAndAdministratorsFullControl -InvokingUserReadExecuteSynchronize -ProtectedDacl -NoInheritedOrExtraAce -NoParentReparse
$verifiedSeedPath = [string](& $staticSeedVerifier verify --receipt $seedInstallReceiptLocator --subject (Join-Path $productExecRoot 'release\evidence\release-subject.json') --print-verified-seed-path)
if ($LASTEXITCODE -ne 0 -or $verifiedSeedPath -cne $seedVerifier) { throw 'native static verifier rejected signed seed receipt/live hashes/exact ACL closure' }
$g8Root = [string]$env:CODESEXTANT_G8_PRIVATE_ROOT
if ([string]::IsNullOrWhiteSpace($g8Root) -or -not [IO.Path]::IsPathFullyQualified($g8Root)) { throw 'set CODESEXTANT_G8_PRIVATE_ROOT to the exact private overlay root printed by bootstrap-private' }
$g8Root = (Resolve-Path -LiteralPath $g8Root).Path
$initializerPath = [string](& $seedVerifier -VerifyProductExec -ProductExecutionRoot $productExecRoot -ProductExecutionReceipt $productExecReceiptPath -SeedInstallReceiptLocator $seedInstallReceiptLocator -VerifyFixedG7Chain -PrintAuthenticatedInitializer)
if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($initializerPath) -or -not (Test-Path -LiteralPath $initializerPath -PathType Leaf)) { throw 'seed rejected product root or initializer before dot-source' }
. $initializerPath
$g8 = Initialize-G8Context -ProductExecutionRoot $productExecRoot -ProductExecutionReceipt $productExecReceiptPath -PrivateRoot $g8Root -EmitNodeContext
switch ($g8.TransactionMode) {
  'recovery_only' {
    $recovery = Invoke-CodeSextantG8Recovery -Context $g8 -RequirePurposeBuiltVerifier -RequireGenericRegistryGate
    if ($recovery.Status -eq 'complete') { throw 'existing G8 transaction is fully verified; report only and never click again' }
    throw 'existing G8 transaction was tombstoned or remains unresolved; forward producers are forbidden'
  }
  'terminal' { throw 'terminal G8 tombstone/quarantine state exists; explicit human disposition is required' }
  'prepare' { }
  default { throw "invalid G8 transaction mode: $($g8.TransactionMode)" }
}
$releasePython = $g8.ReleasePython
$nodeContextBundlePath = $g8.NodeContextBundlePath
$productNodeHostModulePath = $g8.ProductNodeHostModulePath
$productNodeHostModuleSha256 = $g8.ProductNodeHostModuleSha256
$productNodeBootstrapModulePath = $g8.ProductNodeBootstrapModulePath
$productNodeBootstrapModuleSha256 = $g8.ProductNodeBootstrapModuleSha256
$privateRoot = $g8.PrivateRoot
$refreshTermsToolPath = $g8.RefreshTermsToolPath
$applicationToolSubjectToolPath = $g8.ApplicationToolSubjectToolPath
$privateTrustExtensionGeneratorPath = $g8.PrivateTrustExtensionGeneratorPath
$privateTrustExtensionSchemaPath = $g8.PrivateTrustExtensionSchemaPath
$evidenceInputToolPath = $g8.EvidenceInputToolPath
$buildPacketToolPath = $g8.BuildPacketToolPath
$verifyPacketToolPath = $g8.VerifyPacketToolPath
$reviewPacketToolPath = $g8.ReviewPacketToolPath
$authorizePacketToolPath = $g8.AuthorizePacketToolPath
$recordSubmissionToolPath = $g8.RecordSubmissionToolPath
$releaseGatePath = $g8.ReleaseGatePath
$installedBrowserRootPath = $g8.InstalledBrowserRootPath
$productSubjectPath = $g8.ProductSubjectPath
$productSourceRoot = $g8.ProductSourceRoot
$publicExportRoot = $g8.PublicExportRoot
$publicCloneRoot = $g8.PublicCloneRoot
$privateApplicationRoot = $g8.PrivateApplicationRoot
$releaseAssetsRoot = $g8.ReleaseAssetsRoot
$releaseIndexPath = $g8.ReleaseIndexPath
$releaseIndexBundlePath = $g8.ReleaseIndexBundlePath
$signingPolicyPath = $g8.SigningPolicyPath
$verifierBootstrapPath = $g8.VerifierBootstrapPath
$applicationToolSubjectPath = $g8.ApplicationToolSubjectPath
$applicationToolScanPath = $g8.ApplicationToolScanPath
$applicationToolReviewRequestPath = $g8.ApplicationToolReviewRequestPath
$applicationToolReviewInputPath = $g8.ApplicationToolReviewInputPath
$applicationToolFindingsPath = $g8.ApplicationToolFindingsPath
$applicationToolReviewPath = $g8.ApplicationToolReviewPath
$applicationToolManifestPath = $g8.ApplicationToolManifestPath
$applicationToolReviewScopePath = $g8.ApplicationToolReviewScopePath
$applicationToolScanPolicyPath = $g8.ApplicationToolScanPolicyPath
$applicationToolThreatModelPath = $g8.ApplicationToolThreatModelPath
$applicationToolReviewerRolesPath = $g8.ApplicationToolReviewerRolesPath
$globalSigningEnvironmentRegistryPath = $g8.GlobalSigningEnvironmentRegistryPath
$claimReviewerRolesPath = $g8.ClaimReviewerRolesPath
$implementationActorsPath = $g8.ImplementationActorsPath
$browserClientLockPath = $g8.BrowserClientLockPath
$formCapturePolicyPath = $g8.FormCapturePolicyPath
$applicationFormContractSchemaPath = $g8.ApplicationFormContractSchemaPath
$preSubmitRuntimeSchemaPath = $g8.PreSubmitRuntimeSchemaPath
$preSubmitFormSchemaPath = $g8.PreSubmitFormSchemaPath
$preClickSchemaPath = $g8.PreClickSchemaPath
$confirmationRuntimeSchemaPath = $g8.ConfirmationRuntimeSchemaPath
$browserConfirmationSourceSchemaPath = $g8.BrowserConfirmationSourceSchemaPath
$externalReviewEnginePath = $g8.ExternalReviewEnginePath
$externalReviewScanSchemaPath = $g8.ExternalReviewScanSchemaPath
$g7PublicationReceiptPath = $g8.G7PublicationReceiptPath
$g7PublicSmokePath = $g8.G7PublicSmokePath
$applicationFormContract = $g8.ApplicationFormContractPath
$termsSourcePath = $g8.TermsSourcePath
$termsPath = $g8.TermsPath
$attestationRequestPath = $g8.AttestationRequestPath
$attestationsPath = $g8.AttestationsPath
$targetProfileRequestPath = $g8.TargetProfileRequestPath
$targetProfilePath = $g8.TargetProfilePath
$evidenceInputPath = $g8.EvidenceInputPath
$evidenceInputRequestPath = $g8.EvidenceInputRequestPath
$evidenceAuthorityResponseRoot = $g8.EvidenceAuthorityResponseRoot
$evidenceAuthorityResponseManifestPath = $g8.EvidenceAuthorityResponseManifestPath
$packetPath = $g8.PacketPath
$claimReviewRequestPath = $g8.ClaimReviewRequestPath
$claimReviewInputPath = $g8.ClaimReviewInputPath
$claimReviewPath = $g8.ClaimReviewPath
$userConfirmationPath = $g8.UserConfirmationPath
$applicationAuthorizationPath = $g8.AuthorizationPath
$evidenceRefresh = $g8.EvidenceRefreshPath
$preSubmitRuntime = $g8.PreSubmitRuntimePath
$preSubmitForm = $g8.PreSubmitFormPath
$preClick = $g8.PreClickPath
$confirmationRuntime = $g8.ConfirmationRuntimePath
$browserConfirmationSourcePath = $g8.BrowserConfirmationSourcePath
$submissionConfirmationPath = $g8.SubmissionConfirmationPath
$submissionStart = $g8.SubmissionStartPath
$submissionTombstone = $g8.SubmissionTombstonePath
$submissionQuarantine = $g8.SubmissionQuarantinePath
$submissionPath = $g8.SubmissionPath
$registryExtensionPath = $g8.RegistryExtensionPath
$launchPolicyExtensionPath = $g8.LaunchPolicyExtensionPath
$publicReceiptRegistryPath = $g8.PublicReceiptRegistryPath
$publicReceiptSchemaPath = $g8.PublicReceiptSchemaPath
$publicLaunchPolicyPath = $g8.PublicLaunchPolicyPath
$publicLaunchPolicySchemaPath = $g8.PublicLaunchPolicySchemaPath
$g8EvidenceDirectory = $g8.EvidenceDirectory
if ((Resolve-Path -LiteralPath $publicExportRoot).Path -ceq (Resolve-Path -LiteralPath $publicCloneRoot).Path) { throw 'G8 public_export and public_clone authorities must be independently rooted' }
$g8VerificationContextArgs = @(
  '--product-source-root',$productSourceRoot,
  '--public-export-root',$publicExportRoot,
  '--public-clone-root',$publicCloneRoot,
  '--private-application-root',$privateApplicationRoot,
  '--release-assets-root',$releaseAssetsRoot,
  '--release-index',$releaseIndexPath,
  '--release-index-bundle',$releaseIndexBundlePath,
  '--signing-policy',$signingPolicyPath,
  '--verifier-bootstrap',$verifierBootstrapPath
)
function Assert-CodeSextantG8MergedRegistryAndLaunchPolicy {
  if (-not (Test-Path -LiteralPath $applicationToolSubjectPath -PathType Leaf)) { throw 'ApplicationToolSubject must exist before authoritative private G8 merge validation' }
  if (-not (Test-Path -LiteralPath $registryExtensionPath -PathType Leaf) -or -not (Test-Path -LiteralPath $launchPolicyExtensionPath -PathType Leaf)) { throw 'post-subject generated private trust extensions are missing' }
  & $releasePython $privateTrustExtensionGeneratorPath verify --application-tool-subject $applicationToolSubjectPath --application-manifest $applicationToolManifestPath --private-application-root $privateApplicationRoot --global-signing-environment-registry $globalSigningEnvironmentRegistryPath --public-registry $publicReceiptRegistryPath --public-launch-policy $publicLaunchPolicyPath --schema $privateTrustExtensionSchemaPath --registry $registryExtensionPath --launch-policy $launchPolicyExtensionPath
  if ($LASTEXITCODE -ne 0) { throw 'generated private trust extensions do not bind the frozen application subject or generator/schema closure' }
  & $releasePython $releaseGatePath validate-registry --registry $publicReceiptRegistryPath --registry-extension $registryExtensionPath --receipt-schema $publicReceiptSchemaPath --subject $productSubjectPath --secondary-subject $applicationToolSubjectPath @g8VerificationContextArgs --require-payload-schemas
  if ($LASTEXITCODE -ne 0) { throw 'authenticated public plus private G8 registry/schema merge validation failed' }
  & $releasePython $releaseGatePath validate-launch-policy --registry $publicReceiptRegistryPath --registry-extension $registryExtensionPath --launch-policy $publicLaunchPolicyPath --launch-policy-schema $publicLaunchPolicySchemaPath --launch-policy-extension $launchPolicyExtensionPath --subject $productSubjectPath --secondary-subject $applicationToolSubjectPath @g8VerificationContextArgs --require-entrypoint-digests --require-all-signer-policies --require-exact-merged-closure
  if ($LASTEXITCODE -ne 0) { throw 'authenticated public plus private G8 launch-policy digest/signer merge validation failed' }
}
function Invoke-CodeSextantG8RegisteredReceipt {
  param(
    [Parameter(Mandatory=$true)][string]$Receipt,
    [Parameter(Mandatory=$true)][string]$FinalPath,
    [string[]]$ProducerArgs = @()
  )
  Assert-CodeSextantG8MergedRegistryAndLaunchPolicy
  $reviewRequirementArgs = if ($Receipt -ceq 'claude-oss-application-tool-review.json') { @() } else { @('--required-receipt',$applicationToolReviewPath) }
  if (Test-Path -LiteralPath $FinalPath -PathType Leaf) {
    & $releasePython $releaseGatePath check-receipt --gate G8 --receipt $Receipt --registry-extension $registryExtensionPath --launch-policy-extension $launchPolicyExtensionPath --subject $productSubjectPath --secondary-subject $applicationToolSubjectPath --evidence-dir $g8EvidenceDirectory @reviewRequirementArgs @g8VerificationContextArgs
    if ($LASTEXITCODE -ne 0) { throw "existing registered receipt $Receipt is invalid; never delete or reseal it" }
    return
  }
  & $releasePython $releaseGatePath produce-and-seal --gate G8 --receipt $Receipt --registry-extension $registryExtensionPath --launch-policy-extension $launchPolicyExtensionPath --subject $productSubjectPath --secondary-subject $applicationToolSubjectPath --evidence-dir $g8EvidenceDirectory @reviewRequirementArgs @g8VerificationContextArgs -- @ProducerArgs
  if ($LASTEXITCODE -ne 0) { throw "atomic authenticated producer/sealer failed for $Receipt" }
}
~~~

**Private G8 implementation contract:** `application/claude-for-oss/application-tool-manifest.json` is the only immutable source-ownership/closure SSOT; do not maintain a second hand-written path list here. Tasks 2-3 create/update that manifest in the isolated private application repository. `application_tool_subject.py audit-closure` statically enumerates every private import, CLI input path in G8.1-G8.6, schema `$ref`, reviewer/implementation authority, lock/bootstrap/config file, extension generator/schema, and test, then requires exact set equality with the manifest: no missing, extra, duplicate, symlink-escaping, mutable, or unhashable member. It also requires the generated extension output paths to be absent from subject membership. The tests explicitly cover target-profile request/profile, confirmation, application-form-contract schema/derivation, dual-form and decoy selection, form-capture policy/runtime/pre-submit/pre-click, Chrome bridge/browser-client lock, G8 initializer and blank-shell recovery, browser-confirmation source, submission confirmation/tombstone, post-subject extension generation/binding, separate tool-security/claim reviewer roles and keys, closed tool-review scope, pinned external scan, and every packet/receipt/review test.

All immutable source closure remains outside the product public export. Any source-closure change creates a new private Git commit/tree and `ApplicationToolSubject`; generated private-application outputs, including both subject-bound extensions, are never manifest members and cannot feed back into the subject digest.

`ApplicationPacket` uses two distinct fields, never a combined `application_text` alias:

~~~python
@dataclass(frozen=True)
class ApplicationPacket:
    product_release_subject_sha256: str
    application_tool_subject_sha256: str
    application_tool_review_sha256: str
    application_form_contract_sha256: str
    repository: str
    target_profile: TargetProfile
    first_name: str
    last_name: str
    message__oss: ExplicitOptionalText
    target_track: Literal["maintainer", "ecosystem_impact"]
    track_claim: TrackClaim
    planned_use_text: str
    qualification_text: str
    evidence_table: tuple[EvidenceRecord, ...]
    evidence_uses: tuple[EvidenceUse, ...]
~~~

`first_name`, `last_name`, and `message__oss` are copied only from the exact user-confirmed target profile. They are never derived from GitHub; the optional message is still explicit as either empty or a confirmed value. `planned_use_text` and `qualification_text` each bind its own live field ID, label, required flag, and size constraints from the official form snapshot. Each is independently capped at 500 English words as a private safety ceiling and must also satisfy any stricter live word/character limit. A producer or verifier rejects a missing or inferred target field, a joined value, values copied between fields, a deprecated `application_text` member, or a live-schema/form-contract mismatch. Packet, review, confirmation, authorization, pre-submit runtime, pre-submit form, pre-click, submission receipt, and final verifier bind the same application-form-contract digest and exact five user-authorized values.

**Generated private files:**

For the six registry-owned entries in the list below—application-tool-review, terms, packet, review, authorization, and submission—the domain producer never receives or writes a final/candidate pathname. Product-frozen `release_gate.py produce-and-seal` authenticates the structured launch spec and input manifest, passes one inherited anonymous exclusive handle, reads the candidate through its retained handle, and atomically create-new writes the fixed final path. Existing finals are verified only with `check-receipt`; they are never deleted, moved, invalidated, overwritten, or resealed. Non-registry intermediate evidence remains owned by its named producer and alone may be quarantined on failure.

- `release/evidence/g8-product-execution-root.json` (verified imported product-root receipt; never private-produced)
- `release/evidence/claude-oss-terms-source.json`
- `release/evidence/inputs/claude-oss-application-tool-review.inputs.json`
- `release/evidence/inputs/claude-oss-terms.inputs.json`
- `release/evidence/inputs/claude-oss-packet.inputs.json`
- `release/evidence/inputs/claude-oss-review.inputs.json`
- `release/evidence/inputs/claude-oss-authorization.inputs.json`
- `release/evidence/inputs/claude-oss-submission.inputs.json`
- `release/evidence/claude-oss-application-tool-subject.json`
- `release/evidence/claude-oss-application-tool-scan.json`
- `release/evidence/claude-oss-application-tool-review-request.json`
- `release/evidence/claude-oss-application-tool-review-input.json`
- `release/evidence/claude-oss-application-tool-findings.json`
- `release/evidence/claude-oss-application-tool-review.json`
- `release/evidence/claude-oss-application-form-contract.json`
- `release/evidence/claude-oss-terms.json`
- `release/evidence/claude-oss-attestation-request.json`
- `release/evidence/claude-oss-attestations.json`
- `release/evidence/claude-oss-target-profile-request.json`
- `release/evidence/claude-oss-target-profile.json`
- `release/evidence/claude-oss-evidence-input-request.json`
- `release/evidence/claude-oss-evidence-authority-responses/` with a complete manifest and immutable response objects
- `release/evidence/claude-oss-evidence-input.json`
- `release/evidence/claude-oss-evidence-refresh.json`
- `release/evidence/claude-oss-packet.json`
- `release/evidence/claude-oss-review-request.json`
- `release/evidence/claude-oss-review-input.json`
- `release/evidence/claude-oss-review.json`
- `release/evidence/claude-oss-user-confirmation.json`
- `release/evidence/claude-oss-authorization.json`
- `release/evidence/claude-oss-pre-submit-runtime.json` (sanitized structured runtime properties; no opaque values)
- `release/evidence/claude-oss-pre-submit-form.json`
- `release/evidence/claude-oss-pre-click.json`
- `release/evidence/claude-oss-confirmation-runtime.json` (sanitized positive result only; validated by `confirmation-runtime.schema.json`)
- `release/evidence/claude-oss-browser-confirmation-source.json`
- `release/evidence/claude-oss-confirmation.json`
- `release/evidence/claude-oss-submission-start.json`
- `release/evidence/claude-oss-submission-tombstone.json` on an ambiguous outcome
- `release/evidence/claude-oss-submission-quarantine/` on an ambiguous outcome
- `release/evidence/claude-oss-submission.json`

Before operational use, the private tooling test suite must prove: the public export contains none of the private paths; changing one application byte changes only `ApplicationToolSubject`; changing one product byte changes `ReleaseSubject`; branch/default-branch/latest URLs are rejected; evidence digest drift is rejected; every typed evidence use is reachable, unique, and explicitly reviewed; the tool-security reviewer/key is distinct from every implementer and claim reviewer; every tool-review scope material and pinned scan digest is bound; every later G8 link binds the tool-review digest; the two application prose fields cannot be merged; every user-confirmed value and live field is present exactly once; the current dual-form document selects only the contract-bound official POST form; GET/wrong-origin/wrong-path decoys are never selectable; action, method, form identity, field-set, and submit mutations block capture/click; mismatched OAuth identity/email is rejected; a success receipt without the tool-review/form-contract/pre-submit digests is rejected; and the six-month/billing/overage acknowledgements are mandatory.

~~~powershell
& $releasePython -m pytest (Join-Path $privateRoot 'tests\application\test_claude_oss_application_subject.py') (Join-Path $privateRoot 'tests\application\test_application_tool_security_review.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_packet.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_evidence.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_review.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_pre_submit.py') (Join-Path $privateRoot 'tests\application\test_chrome_form_bridge.py') (Join-Path $privateRoot 'tests\application\test_claude_oss_receipts.py') (Join-Path $privateRoot 'tests\application\test_g8_fresh_shell.py') -q
if ($LASTEXITCODE -ne 0) { throw 'private G8 tooling tests are not green' }
~~~

### G8.1 Refresh requirements, create ApplicationToolSubject, and independently review the tooling

Use only the current official Anthropic sources:

- https://claude.com/contact-sales/claude-for-oss
- https://www.anthropic.com/claude-for-oss-terms

Fetch an unsealed source snapshot first, then create the private tool subject over immutable private code/tooling plus the extension generator/schema, explicitly excluding generated extensions. Next generate the two subject-bound extension outputs as ignored `private_application` files, validate their embedded subject/generator/schema digests and exact merged closure, and bind both extension digests into the application-tool review and every later G8 receipt. Derive the subject-bound application-form contract only after that subject exists, from the exact raw source snapshot, strict form policy, and subject digest; run and independently sign the closed tool-security review; only then seal terms with the contract and review. This avoids a digest cycle: `ApplicationToolSubject` never contains an extension whose bytes depend on that subject; the generated extensions point one way to the frozen subject; the contract binds snapshot plus subject; the tool review binds subject+extensions+contract+scan; and the sealed terms receipt binds both subjects, extensions, contract, and tool-review digest.

~~~powershell
Assert-CodeSextantG8TrustClosure -Context $g8
Assert-CodeSextantG8BrowserClient -Context $g8 -InstalledRoot $installedBrowserRootPath
if (Test-Path -LiteralPath $applicationToolReviewPath -PathType Leaf) {
  Invoke-CodeSextantG8RegisteredReceipt -Receipt 'claude-oss-application-tool-review.json' -FinalPath $applicationToolReviewPath
} else {
Remove-Item -LiteralPath $termsSourcePath,$applicationToolSubjectPath,$registryExtensionPath,$launchPolicyExtensionPath,$applicationFormContract,$applicationToolScanPath,$applicationToolReviewRequestPath,$applicationToolReviewInputPath,$applicationToolFindingsPath -Force -ErrorAction SilentlyContinue
& $releasePython $refreshTermsToolPath fetch --source https://claude.com/contact-sales/claude-for-oss --source https://www.anthropic.com/claude-for-oss-terms --out $termsSourcePath
if ($LASTEXITCODE -ne 0) { throw 'official Anthropic terms fetch failed' }
& $releasePython $applicationToolSubjectToolPath create --application-repo $privateRoot --application-commit HEAD --manifest $applicationToolManifestPath --browser-client-lock $browserClientLockPath --installed-browser-root $installedBrowserRootPath --global-signing-environment-registry $globalSigningEnvironmentRegistryPath --terms-source $termsSourcePath --product-subject $productSubjectPath --g7-publication-receipt $g7PublicationReceiptPath --public-smoke-receipt $g7PublicSmokePath --external-review-engine $externalReviewEnginePath --public-repo Zeroxrain99/CodeSextant --out $applicationToolSubjectPath
if ($LASTEXITCODE -ne 0) { throw 'application tool subject or private-export exclusion proof failed' }
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath
& $releasePython $privateTrustExtensionGeneratorPath generate --application-tool-subject $applicationToolSubjectPath --application-manifest $applicationToolManifestPath --private-application-root $privateApplicationRoot --global-signing-environment-registry $globalSigningEnvironmentRegistryPath --public-registry $publicReceiptRegistryPath --public-launch-policy $publicLaunchPolicyPath --schema $privateTrustExtensionSchemaPath --registry-out $registryExtensionPath --launch-policy-out $launchPolicyExtensionPath
if ($LASTEXITCODE -ne 0) { throw 'post-subject private trust-extension generation or subject binding failed' }
Assert-CodeSextantG8MergedRegistryAndLaunchPolicy
& $releasePython $refreshTermsToolPath derive-form-contract --source-snapshot $termsSourcePath --application-tool-subject $applicationToolSubjectPath --policy $formCapturePolicyPath --schema $applicationFormContractSchemaPath --out $applicationFormContract
if ($LASTEXITCODE -ne 0) { throw 'official application form contract derivation failed: expected one contract-matching POST form inside the complete form census' }
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath
& $releasePython $externalReviewEnginePath scan --primary-subject $productSubjectPath --secondary-subject $applicationToolSubjectPath --manifest $applicationToolManifestPath --scope $applicationToolReviewScopePath --scan-policy $applicationToolScanPolicyPath --schema $externalReviewScanSchemaPath --out $applicationToolScanPath
if ($LASTEXITCODE -ne 0) { throw 'pinned offline application-tool SAST/dependency scan failed' }
$toolReviewRequesterId = $env:CODESEXTANT_APPLICATION_TOOL_REVIEW_REQUESTER_ID
$toolReviewReviewerId = $env:CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_ID
$toolReviewReviewerProcess = $env:CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_PROCESS_SHA256
if (-not $toolReviewRequesterId -or -not $toolReviewReviewerId -or $toolReviewRequesterId -eq $toolReviewReviewerId -or $toolReviewReviewerProcess -notmatch '^[0-9a-f]{64}$') { throw 'distinct precommitted application-tool review requester/reviewer identities and reviewer process digest are required' }
$requestArgs = @($externalReviewEnginePath,'request','--primary-subject',$productSubjectPath,'--secondary-subject',$applicationToolSubjectPath,'--manifest',$applicationToolManifestPath,'--scope',$applicationToolReviewScopePath,'--scan',$applicationToolScanPath,'--terms-source',$termsSourcePath,'--form-contract',$applicationFormContract,'--threat-model',$applicationToolThreatModelPath,'--reviewer-roles',$applicationToolReviewerRolesPath,'--forbid-reviewer-roles',$claimReviewerRolesPath,'--implementation-actors',$implementationActorsPath,'--requester-id',$toolReviewRequesterId,'--signing-key-env','CODESEXTANT_APPLICATION_TOOL_REVIEW_REQUESTER_SIGNING_KEY','--out',$applicationToolReviewRequestPath)
Invoke-CodeSextantG8ReviewRole -Context $g8 -Role application_tool_review_requester -CredentialName 'codesextant/g8/tool-review-requester' -Command $requestArgs -SigningEnvironmentRegistry $globalSigningEnvironmentRegistryPath -AllowedSigningKey CODESEXTANT_APPLICATION_TOOL_REVIEW_REQUESTER_SIGNING_KEY
if ($LASTEXITCODE -ne 0) { throw 'fresh requester process failed to create the closed security-review request' }
$reviewArgs = @($externalReviewEnginePath,'record-input-and-findings','--request',$applicationToolReviewRequestPath,'--reviewer-id',$toolReviewReviewerId,'--reviewer-process-sha256',$toolReviewReviewerProcess,'--reviewer-roles',$applicationToolReviewerRolesPath,'--forbid-reviewer-roles',$claimReviewerRolesPath,'--implementation-actors',$implementationActorsPath,'--signing-key-env','CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_SIGNING_KEY','--interactive','--input-out',$applicationToolReviewInputPath,'--findings-out',$applicationToolFindingsPath)
Invoke-CodeSextantG8ReviewRole -Context $g8 -Role independent_tool_security_reviewer -CredentialName 'codesextant/g8/tool-review-reviewer' -Command $reviewArgs -SigningEnvironmentRegistry $globalSigningEnvironmentRegistryPath -AllowedSigningKey CODESEXTANT_APPLICATION_TOOL_SECURITY_REVIEWER_SIGNING_KEY
if ($LASTEXITCODE -ne 0) { throw 'fresh independent reviewer process failed to record a complete signed input and findings ledger' }
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath
$receiptArgs = @('--manifest',$applicationToolManifestPath,'--global-signing-environment-registry',$globalSigningEnvironmentRegistryPath,'--scope',$applicationToolReviewScopePath,'--scan',$applicationToolScanPath,'--request',$applicationToolReviewRequestPath,'--review-input',$applicationToolReviewInputPath,'--findings',$applicationToolFindingsPath,'--reviewer-roles',$applicationToolReviewerRolesPath,'--forbid-reviewer-roles',$claimReviewerRolesPath,'--implementation-actors',$implementationActorsPath,'--product-execution-root-receipt',$g8.ProductExecutionRootReceiptPath,'--verifier-sha256',$g8.ExternalReviewEngineSha256,'--schema-set-sha256',$g8.ExternalReviewSchemaSetSha256)
Invoke-CodeSextantG8RegisteredReceipt -Receipt 'claude-oss-application-tool-review.json' -FinalPath $applicationToolReviewPath -ProducerArgs $receiptArgs
}
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
$termsArgs = @('--source-snapshot',$termsSourcePath,'--application-form-contract',$applicationFormContract,'--application-tool-review',$applicationToolReviewPath)
Invoke-CodeSextantG8RegisteredReceipt -Receipt 'claude-oss-terms.json' -FinalPath $termsPath -ProducerArgs $termsArgs
~~~

The raw and sealed snapshots record URL, `fetched_at_utc`, response/content hash, eligibility tracks and thresholds, every general-eligibility statement, benefit length, billing/overage/discretion language, and the current form field IDs, labels, order, required flags, and word/character limits. The derived contract additionally records the full document form census (currently two forms), one selected POST form, canonical action origin exactly `https://forms.hsforms.com`, strict allowlisted action-path pattern plus concrete matched path, query/fragment-free action, method, stable form-identity digest, full ordered normalized field set, and exactly one static form-descendant submit identity. That descendant is allowed to be initially disabled and must become enabled only after filling, within a bounded readiness window and without replacement or census drift. The GET form remains enumerated but unselectable. Dynamic action query tokens are never persisted or hardcoded; only the source-snapshot digest and strict origin/path allowlist are trust inputs. The golden parser assertions include the current immediate-family/household restriction, GitHub good-standing requirement, one-active-benefit/no-duplicate-application rule, dual-form selection, decoys, disabled-to-enabled readiness, and field/form/submit mutations.

Requester, reviewer, and receipt verification run in three mutually exclusive fresh processes. The requester process receives only the requester key, the reviewer process receives only the reviewer key, and the receipt/verifier process receives neither; the product-frozen launcher starts from a closed environment allowlist, reads each key from a role-specific OS credential reference inside its child, rejects ambient or inherited signing-key variables, and clears the child environment on exit. The reviewer receives the immutable request/material closure, not a caller-authored summary, and signs either typed findings or an explicit scope-complete `no_findings`. The claim reviewer in G8.3 is a different identity and key and uses the same separation shape: a fresh signer child alone sees its role credential, then a different fresh keyless child verifies the detached review. Tests reject key co-residency, parent-to-child inheritance, requester/reviewer identity overlap, any signing key visible to either verifier, or a receipt that omits the product-root receipt plus verifier/schema/root digests. The sealed terms receipt is the first downstream object permitted after this review and binds `application_tool_review_sha256`; a changed subject, contract, scanner result, review scope, reviewer policy, finding ledger, product execution root, verifier, or schema set requires a new tool review before any later G8 command.

If the official content changed but remains representable, create a new `ApplicationToolSubject` and continue with the new data. If private code or schemas cannot represent it, stop, update and independently review only the private G8 tool closure, then restart G8.1. Do not invalidate or rebuild the immutable product merely because application terms or private tooling changed. If the product itself must change, stop and return to G4.

### G8.2 Collect every attestation and prove one official track

Generate a schema-bound request containing every current non-public eligibility statement verbatim. The current request is expected to cover at least: natural person; age of majority; eligible location; sanctions/export eligibility; GitHub account age of at least two years **and good standing**; public OSS activity in the required recent window; not an Anthropic employee, contractor, agent, program operator, or their immediate-family/household member; and no active Claude-for-OSS benefit or duplicate/pending application. The source-derived request is authoritative, so any added official statement also becomes mandatory.

~~~powershell
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
Remove-Item -LiteralPath $attestationRequestPath,$attestationsPath -Force -ErrorAction SilentlyContinue
& $releasePython $authorizePacketToolPath show-attestation-request --product-subject $productSubjectPath --application-tool-subject $applicationToolSubjectPath --application-tool-review $applicationToolReviewPath --terms $termsPath --out $attestationRequestPath
if ($LASTEXITCODE -ne 0) { throw 'eligibility attestation request generation failed' }
~~~

The user must answer every displayed ID explicitly. The following IDs are illustrative current expectations; pass exactly the source-derived IDs printed by the command and never silently reuse this example after a terms change:

~~~powershell
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
Remove-Item -LiteralPath $attestationsPath -Force -ErrorAction SilentlyContinue
& $releasePython $authorizePacketToolPath record-attestations --request $attestationRequestPath --application-tool-review $applicationToolReviewPath --answer natural_person=true --answer adult_or_age_of_majority=true --answer eligible_residence_or_location=true --answer sanctions_and_export_control_eligible=true --answer github_account_at_least_two_years_and_in_good_standing=true --answer recent_public_open_source_activity=true --answer not_anthropic_personnel_contractor_agent_program_operator_or_immediate_family_or_household=true --answer no_active_benefit_and_no_duplicate_or_pending_application=true --attested-by user --out $attestationsPath
if ($LASTEXITCODE -ne 0) { throw 'one or more current eligibility attestations are missing or false' }
~~~

`record-attestations` accepts only explicit booleans, requires exactly one answer per current question, and rejects omitted, duplicate, unknown, stale, or generic earlier approvals. It records exact question text/digest, answer, timestamp, terms digest, both subject digests, and the application-tool-review digest. Public API facts may corroborate account age and activity, but cannot silently substitute for the user's good-standing, relationship, or duplicate-application attestations.

Display and separately confirm every destination/form identity value. The request may prefill only the already specified account and email. It must collect `first_name`, `last_name`, and the optional `message__oss` interactively from the user; it must never query or copy a GitHub display name. The optional message prompt requires the user to choose explicit empty or explicit value, so omission is impossible:

~~~powershell
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
Remove-Item -LiteralPath $targetProfileRequestPath,$targetProfilePath -Force -ErrorAction SilentlyContinue
& $releasePython $authorizePacketToolPath show-target-profile-request --product-subject $productSubjectPath --application-tool-subject $applicationToolSubjectPath --application-tool-review $applicationToolReviewPath --terms $termsPath --application-form-contract $applicationFormContract --target-account Zeroxrain99 --target-email zeroxrain99@gmail.com --interactive-user-values --out $targetProfileRequestPath
if ($LASTEXITCODE -ne 0) { throw 'target profile request generation failed' }
~~~

Only after the user explicitly confirms each displayed field—account, email, first name, last name, and optional-message state/value—one by one:

~~~powershell
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
& $releasePython $authorizePacketToolPath record-target-profile --request $targetProfileRequestPath --application-tool-review $applicationToolReviewPath --interactive-confirm-each-field --confirmed-by user --out $targetProfilePath
if ($LASTEXITCODE -ne 0) { throw 'target account/email/first-name/last-name/optional-message confirmation failed' }
~~~

Create `claude-oss-evidence-input.json` only through the deterministic `evidence_input.py` producer. `show-request` first freezes both subjects, current terms, application-tool review, application-form contract, target profile, every required consumer, and the exact authority query contract. In create-new mode, `record-authority-responses` fetches each allowlisted authority into a new response root and atomically writes a complete manifest; missing, extra, redirected, mutable, duplicate, stale, or partially written responses are fatal. `record-evidence-input` accepts only that request plus the complete authority-response root and writes one canonical deduplicated `evidence_table` plus one canonical sorted `evidence_uses`; claims, selected track, criteria, downstream dependencies, project, and GitHub objects carry only their stable consumer IDs and no inline evidence ID or URL. Each `EvidenceUse` is exactly `(consumer_kind, consumer_id, evidence_id)` with a closed consumer kind. Every required consumer must be covered, every evidence row must be reachable, and dangling consumer/evidence IDs, duplicate triples, orphan rows, unknown kinds, or any `*_evidence_url` in GitHub/project payloads are fatal. Each evidence row uses the closed kind union defined in Task 2 and records immutable `citation_url`, allowlisted `authority_url`, resolved identity, response/content SHA-256, parsed facts, observation UTC, and type-specific refresh mode. Git rows require full objects/assets. Registry metrics, OpenSSF results, and official rosters require an immutable public snapshot citation plus the exact official live query that submission-start must re-fetch. OSI and Anthropic sources use only their official hosts. Reject default-branch URLs (`main`, `master`, `/tree/<branch>`, `/blob/<branch>`), `releases/latest`, search pages, arbitrary dashboards/hosts, duplicate/dangling IDs, and unpinned prose.

For `ecosystem_impact`, a qualifying claim requires concrete downstream use: at least one independently owned public project/package at an immutable revision that imports, invokes, packages, or operationally depends on CodeSextant, plus evidence explaining the dependency mechanism and actual adoption/dependent signal. A CodeSextant-authored description, a planned integration, account age, stars without dependency, or the upstream repository by itself is not downstream dependence. For `maintainer`, enforce the exact live quantitative/current criteria from the terms receipt. No fallback track is inferred.

~~~powershell
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
if ($g8.TransactionMode -ne 'prepare' -or (Test-Path -LiteralPath $submissionStart)) { throw 'evidence inputs may be created or cleaned only before transaction start' }
if (Test-Path -LiteralPath $packetPath -PathType Leaf) {
  Invoke-CodeSextantG8RegisteredReceipt -Receipt 'claude-oss-packet.json' -FinalPath $packetPath
} else {
Remove-Item -LiteralPath $evidenceInputRequestPath,$evidenceInputPath -Force -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $evidenceAuthorityResponseRoot) { Remove-Item -LiteralPath $evidenceAuthorityResponseRoot -Recurse -Force }
& $releasePython $evidenceInputToolPath show-request --product-subject $productSubjectPath --application-tool-subject $applicationToolSubjectPath --application-tool-review $applicationToolReviewPath --application-form-contract $applicationFormContract --terms $termsPath --target-profile $targetProfilePath --out $evidenceInputRequestPath
if ($LASTEXITCODE -ne 0) { throw 'deterministic evidence-input request generation failed' }
& $releasePython $evidenceInputToolPath record-authority-responses --request $evidenceInputRequestPath --create-new-root $evidenceAuthorityResponseRoot --manifest-out $evidenceAuthorityResponseManifestPath --interactive
if ($LASTEXITCODE -ne 0) { throw 'complete create-new authority-response capture failed' }
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
& $releasePython $evidenceInputToolPath record-evidence-input --request $evidenceInputRequestPath --authority-response-root $evidenceAuthorityResponseRoot --authority-response-manifest $evidenceAuthorityResponseManifestPath --create-new $evidenceInputPath
if ($LASTEXITCODE -ne 0) { throw 'canonical evidence-input production failed' }
& $releasePython $evidenceInputToolPath verify-evidence-input --request $evidenceInputRequestPath --authority-response-root $evidenceAuthorityResponseRoot --authority-response-manifest $evidenceAuthorityResponseManifestPath --evidence-input $evidenceInputPath --product-subject $productSubjectPath --application-tool-subject $applicationToolSubjectPath --application-tool-review $applicationToolReviewPath --application-form-contract $applicationFormContract --terms $termsPath
if ($LASTEXITCODE -ne 0) { throw 'evidence-input request, authority-response manifest, subject, terms, review, or form-contract binding failed' }
$packetArgs = @('--repo','Zeroxrain99/CodeSextant','--application-tool-review',$applicationToolReviewPath,'--application-form-contract',$applicationFormContract,'--terms',$termsPath,'--attestations',$attestationsPath,'--target-profile',$targetProfilePath,'--evidence-input-request',$evidenceInputRequestPath,'--evidence-authority-response-root',$evidenceAuthorityResponseRoot,'--evidence-authority-response-manifest',$evidenceAuthorityResponseManifestPath,'--evidence-input',$evidenceInputPath)
Invoke-CodeSextantG8RegisteredReceipt -Receipt 'claude-oss-packet.json' -FinalPath $packetPath -ProducerArgs $packetArgs
}
& $releasePython $verifyPacketToolPath verify-packet --packet $packetPath --product-subject $productSubjectPath --application-tool-subject $applicationToolSubjectPath --application-tool-review $applicationToolReviewPath --application-form-contract $applicationFormContract --terms $termsPath --attestations $attestationsPath --target-profile $targetProfilePath --evidence-input-request $evidenceInputRequestPath --evidence-authority-response-root $evidenceAuthorityResponseRoot --evidence-authority-response-manifest $evidenceAuthorityResponseManifestPath --evidence-input $evidenceInputPath
if ($LASTEXITCODE -ne 0) { throw 'packet verification failed or eligibility track remains unproven' }
~~~

Expected from the pre-G7 planning snapshot: `Zeroxrain99` exposes zero public repositories. At actual G8 time G7 will have made CodeSextant public and may satisfy recent-activity evidence, so do not use the stale repository count as the blocker. The live evaluator must still return `ELIGIBILITY_TRACK_UNPROVEN` until a current Maintainer threshold/core-contributor route or genuine independent downstream dependence is proven. Never manufacture repositories, stars, contributors, dependents, downloads, PRs, usage, or criticality.

### G8.3 Obtain an independent track and typed evidence-use review

The reviewer did not author the product, application tooling, packet, evidence, or claims and is precommitted under the independent application-reviewer role with no overlap in the universal implementation-actor roster. The signed review must display every evidence row and cover every canonical typed `EvidenceUse` edge—claim, track, criterion, downstream dependency, project, and GitHub—with one explicit signed verdict per `(consumer_kind, consumer_id, evidence_id)`. It must also contain an explicit `track_claim` verdict with the exact selected track, criterion IDs, evidence-use closure, and one of `PROVEN` or `NOT_PROVEN`. Empty review input, an uncovered/orphan/dangling/duplicate use, unsupported prose, and a missing use-edge or track verdict are invalid. `NOT_PROVEN` is terminal for this packet and cannot be overridden by the operator or user authorization.

After the interactive review input returns, re-audit the complete trust closure. The product-frozen role launcher starts a fresh signer child from a closed environment allowlist; that child alone reads the claim-review signing key from its role-specific OS credential. A second fresh keyless verifier child receives no signing credential or inherited signing-key variable:

~~~powershell
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
$applicationReviewerId = $env:CODESEXTANT_APPLICATION_REVIEWER_ID
$applicationReviewerProcess = $env:CODESEXTANT_APPLICATION_REVIEWER_PROCESS_SHA256
if (-not $applicationReviewerId -or $applicationReviewerProcess -notmatch '^[0-9a-f]{64}$') { throw 'independent application reviewer identity/process evidence is required' }
if ($env:CODESEXTANT_APPLICATION_REVIEWER_SIGNING_KEY) { throw 'ambient claim-review signing key is forbidden; the fresh signer child reads its role credential directly' }
if (Test-Path -LiteralPath $claimReviewPath -PathType Leaf) {
  Invoke-CodeSextantG8RegisteredReceipt -Receipt 'claude-oss-review.json' -FinalPath $claimReviewPath
} else {
Remove-Item -LiteralPath $claimReviewRequestPath,$claimReviewInputPath -Force -ErrorAction SilentlyContinue
& $releasePython $reviewPacketToolPath show-review-request --packet $packetPath --product-subject $productSubjectPath --application-tool-subject $applicationToolSubjectPath --application-tool-review $applicationToolReviewPath --terms $termsPath --out $claimReviewRequestPath
if ($LASTEXITCODE -ne 0) { throw 'application review request generation failed' }
& $releasePython $reviewPacketToolPath record-review-input --request $claimReviewRequestPath --application-tool-review $applicationToolReviewPath --reviewer-id $applicationReviewerId --require-track-verdict --interactive --out $claimReviewInputPath
if ($LASTEXITCODE -ne 0) { throw 'explicit every-use-edge and track review input recording failed' }
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
$claimSignArgs = @('--packet',$packetPath,'--application-tool-review',$applicationToolReviewPath,'--terms',$termsPath,'--review-request',$claimReviewRequestPath,'--review-input',$claimReviewInputPath,'--reviewer-id',$applicationReviewerId,'--reviewer-process-sha256',$applicationReviewerProcess,'--reviewer-roles',$claimReviewerRolesPath,'--tool-reviewer-roles',$applicationToolReviewerRolesPath,'--implementation-actors',$implementationActorsPath)
Invoke-CodeSextantG8RegisteredReceipt -Receipt 'claude-oss-review.json' -FinalPath $claimReviewPath -ProducerArgs $claimSignArgs
}
$claimVerifyArgs = @($reviewPacketToolPath,'verify','--packet',$packetPath,'--product-subject',$productSubjectPath,'--application-tool-subject',$applicationToolSubjectPath,'--application-tool-review',$applicationToolReviewPath,'--terms',$termsPath,'--review-request',$claimReviewRequestPath,'--review-input',$claimReviewInputPath,'--review',$claimReviewPath,'--reviewer-roles',$claimReviewerRolesPath,'--tool-reviewer-roles',$applicationToolReviewerRolesPath,'--implementation-actors',$implementationActorsPath,'--require-track-verdict','PROVEN')
Invoke-CodeSextantG8ReviewRole -Context $g8 -Role claim_verifier -Command $claimVerifyArgs -SigningEnvironmentRegistry $globalSigningEnvironmentRegistryPath
if ($LASTEXITCODE -ne 0) { throw 'fresh keyless claim-review verifier rejected signature, separation, typed-use edges, or track verdict' }
~~~

Any unsupported/misleading evidence-use edge, changed evidence/use byte, or `NOT_PROVEN` verdict requires a newly generated packet and completely fresh independent review. Never edit a review into `PROVEN`.

### G8.4 Obtain submission-specific authorization and billing acknowledgement

Present first name, last name, the optional-message state/value, both distinct application prose fields, every immutable evidence URL/digest and typed use edge, selected track and signed verdict, target account/email, application-form-contract digest and selected form identity, both subject digests, independent application-tool-review digest/verdict, packet SHA-256, and the current terms summary. The confirmation request also displays the current benefit/billing effects and requires separate explicit acknowledgements that: the benefit lasts six months under the then-current terms; any paid subscription may resume or continue billing after the benefit unless cancelled as the then-current terms specify; usage above included limits may incur overage charges where enabled; and acceptance/continued availability is discretionary and governed by the terms current at submission. An acknowledgement is not consent to unspecified future text: any terms, form-contract, or tool-review digest change invalidates the request.

~~~powershell
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
& $releasePython $authorizePacketToolPath show-request --product-subject $productSubjectPath --application-tool-subject $applicationToolSubjectPath --application-tool-review $applicationToolReviewPath --application-form-contract $applicationFormContract --packet $packetPath --terms $termsPath --review $claimReviewPath --target-profile $targetProfilePath
if ($LASTEXITCODE -ne 0) { throw 'submission authorization request generation failed' }
~~~

Only after the user explicitly authorizes that exact display and answers every acknowledgement `true`:

~~~powershell
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
if (Test-Path -LiteralPath $applicationAuthorizationPath -PathType Leaf) {
  Invoke-CodeSextantG8RegisteredReceipt -Receipt 'claude-oss-authorization.json' -FinalPath $applicationAuthorizationPath
} else {
Remove-Item -LiteralPath $userConfirmationPath -Force -ErrorAction SilentlyContinue
& $releasePython $authorizePacketToolPath record-confirmation --product-subject $productSubjectPath --application-tool-subject $applicationToolSubjectPath --application-tool-review $applicationToolReviewPath --application-form-contract $applicationFormContract --packet $packetPath --terms $termsPath --review $claimReviewPath --target-profile $targetProfilePath --ack benefit_is_six_months_under_current_terms=true --ack paid_plan_may_resume_or_continue_after_benefit=true --ack enabled_overages_may_be_charged=true --ack discretionary_and_current_terms_govern=true --authorized-by user --expires-minutes 30 --out $userConfirmationPath
if ($LASTEXITCODE -ne 0) { throw 'explicit application and billing confirmation failed' }
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
$authorizationArgs = @('--application-tool-review',$applicationToolReviewPath,'--application-form-contract',$applicationFormContract,'--packet',$packetPath,'--terms',$termsPath,'--review',$claimReviewPath,'--target-profile',$targetProfilePath,'--user-confirmation',$userConfirmationPath)
Invoke-CodeSextantG8RegisteredReceipt -Receipt 'claude-oss-authorization.json' -FinalPath $applicationAuthorizationPath -ProducerArgs $authorizationArgs
}
~~~

The authorization binds both subjects; the independent application-tool-review digest; the application-form-contract/form-identity/full-field-set digests; user-confirmed first name, last name, and explicit optional-message state/value; distinct `planned_use_text` and `qualification_text`; every immutable evidence row and typed-use digest; signed `PROVEN` track verdict; all four acknowledgements; exact target account `Zeroxrain99`; exact target email `zeroxrain99@gmail.com`; and a 30-minute expiry. A generic earlier approval cannot satisfy it.

### G8.5 Refresh evidence, capture a sanitized same-page snapshot, then submit once

Use the Chrome connector in the existing logged-in session without Windows desktop automation or focus theft. First re-fetch both official requirement pages and every evidence-table authority according to its type-specific refresh rule. Re-derive the live form census from the refreshed page and require exact equality with the sealed application-form contract: selected POST form identity, canonical action origin/path allowlist, method, full field set, and one static form-descendant submit identity. That submit may initially be disabled. After filling, perform a bounded readiness wait and require the same descendant to become enabled while the form, field, and submit census remains stable. A changed query token alone is ignored after query stripping, but source structure, path, form, field, submit identity, replacement, duplication, or readiness timeout is fatal. Reject any terms/form-contract digest change, mutable citation, redirect to a branch/default-branch/latest resource, object/asset change, registry/OpenSSF/roster fact that no longer meets the selected track, or content-digest drift. Only after that refresh passes, fill the selected official form from the authorized packet but do not click.

From the same tab, document, and contract-selected form, Chrome emits only `claude-oss-pre-submit-runtime.json`: structured runtime `.value`/selection/label/constraint facts after applying `form-capture-policy.json`. The complete live field census must equal the contract; user-authorized fields—first name, last name, explicit optional message, planned-use text, and qualification text—must equal the packet, target profile, confirmation, and authorization exactly. OAuth/server-derived GitHub handle, verified email, selected repository ID/name, and account/repository metadata are independently checked against the target and live public subject. Opaque verification/CSRF fields remain inside Chrome; the snapshot records presence/class only and must not contain their value or digest. Analytics fields are accepted only when explicitly classified by the current policy. Raw DOM/HTML and unredacted screenshots are forbidden, and a canary-secret test scans every output/quarantine byte.

`capture-pre-submit` binds both subjects, the application-tool security review, authorization/packet/terms/evidence-refresh/application-form-contract digests, page-instance/session nonce, form identity and complete field-set digests, every exact user-authorized runtime value, verified server-derived metadata, opaque-presence classes, and UTC. `start` performs no network request; it requires the review, refresh, and capture to be fresh, same-session, same-form, and unchanged, then writes `click_deadline_utc` no more than 60 seconds later. Chrome may submit only with the atomic form-scoped page-context `verify-and-click` primitive described below.

~~~powershell
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
function Stop-CodeSextantSubmission {
  param(
    [Parameter(Mandatory=$true)][string]$Reason,
    [object]$OriginalFailure = $null
  )
  try {
    & $releasePython $recordSubmissionToolPath tombstone --application-tool-review $applicationToolReviewPath --submission-start $submissionStart --authorization $applicationAuthorizationPath --reason $Reason --invalidate $evidenceRefresh --invalidate $preSubmitRuntime --invalidate $preSubmitForm --invalidate $preClick --invalidate $confirmationRuntime --invalidate $browserConfirmationSourcePath --invalidate $submissionConfirmationPath --preserve-registered-receipt $submissionPath --quarantine-dir $submissionQuarantine --out $submissionTombstone
  } catch {
    throw "submission is ambiguous and tombstone/quarantine failed; do not retry. Original failure: $OriginalFailure; tombstone failure: $_"
  }
  throw "submission is tombstoned and cannot be retried automatically. Reason: $Reason; original failure: $OriginalFailure"
}
if ($g8.TransactionMode -ne 'prepare') { throw 'the initializer owns recovery and terminal routing; this stage accepts only a fresh prepare state' }
if ((Test-Path -LiteralPath $submissionStart) -or (Test-Path -LiteralPath $submissionTombstone) -or (Test-Path -LiteralPath $submissionQuarantine)) { throw 'unexpected transaction evidence after prepare routing; stop without cleanup or click' }
Remove-Item -LiteralPath $evidenceRefresh,$preSubmitRuntime,$preSubmitForm,$preClick,$confirmationRuntime,$browserConfirmationSourcePath,$submissionConfirmationPath -Force -ErrorAction SilentlyContinue
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
& $releasePython $recordSubmissionToolPath refresh-evidence --product-subject $productSubjectPath --application-tool-subject $applicationToolSubjectPath --application-tool-review $applicationToolReviewPath --application-form-contract $applicationFormContract --terms $termsPath --refresh-source https://claude.com/contact-sales/claude-for-oss --refresh-source https://www.anthropic.com/claude-for-oss-terms --packet $packetPath --max-age-minutes 5 --out $evidenceRefresh
if ($LASTEXITCODE -ne 0) { throw 'official terms or evidence refresh failed; rebuild/review/reauthorize before opening the form' }
~~~

In the connected Chrome runtime, the locked connector host first loads the product-frozen `g8_node_host.mjs` through its authenticated absolute-path-plus-expected-SHA-256 primitive. The host wrapper rejects any ambient `codeSextantG8ProductBootstrap`, bridge, context, or tab global; accepts the bootstrap only as the canonical absolute path and digest from the seed-authenticated context; reads and hashes it before `pathToFileURL` import; freezes the returned namespace; and passes only the absolute create-new JCS context path. The bootstrap verifies the bundle, product-root receipt, fixed G7 receipts, private root, ApplicationToolSubject, manifest confinement, and bridge digest before private import. A tampered path/global can never execute. Only the resulting lexical bridge/context/tab values select and fill the one contract-bound official form. The same disabled-to-enabled readiness, full-census stability, privacy, and no-second-click rules remain mandatory.

~~~javascript
const productHost = await connectorHost.importVerifiedProductModule({
  absolutePath: productNodeHostModulePath,
  expectedSha256: productNodeHostModuleSha256,
  rejectAmbientNames: [
    "codeSextantG8ProductBootstrap", "codeSextantChromeBridge",
    "codeSextantG8Context", "codeSextantFormTab",
  ],
});
const activated = await productHost.activate({
  productBootstrapAbsolutePath: productNodeBootstrapModulePath,
  productBootstrapExpectedSha256: productNodeBootstrapModuleSha256,
  nodeContextBundleAbsolutePath: nodeContextBundlePath,
  browser: chrome,
});
const { bridge, context } = Object.freeze(activated);
const formTab = await bridge.claimOfficialFormTab({context, browser: chrome});
await bridge.fillAndCapturePreSubmit({context, tab: formTab});
~~~

~~~powershell
if (-not (Test-Path -LiteralPath $preSubmitRuntime -PathType Leaf)) { throw 'Chrome must now fill the same official form and emit a fresh sanitized runtime snapshot; raw DOM/screenshots are forbidden' }
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
& $releasePython $recordSubmissionToolPath capture-pre-submit --product-subject $productSubjectPath --application-tool-subject $applicationToolSubjectPath --application-tool-review $applicationToolReviewPath --application-form-contract $applicationFormContract --terms $termsPath --packet $packetPath --authorization $applicationAuthorizationPath --target-profile $targetProfilePath --evidence-refresh $evidenceRefresh --runtime-snapshot $preSubmitRuntime --runtime-schema $preSubmitRuntimeSchemaPath --capture-policy $formCapturePolicyPath --schema $preSubmitFormSchemaPath --out $preSubmitForm
if ($LASTEXITCODE -ne 0) { throw 'OAuth identity, email, live schema, or exact filled-value pre-submit verification failed; do not click' }
Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
& $releasePython $recordSubmissionToolPath start --product-subject $productSubjectPath --application-tool-subject $applicationToolSubjectPath --application-tool-review $applicationToolReviewPath --application-form-contract $applicationFormContract --terms $termsPath --packet $packetPath --evidence-refresh $evidenceRefresh --pre-submit-runtime $preSubmitRuntime --pre-submit-form $preSubmitForm --target-profile $targetProfilePath --review $claimReviewPath --authorization $applicationAuthorizationPath --click-deadline-seconds 60 --out $submissionStart
if ($LASTEXITCODE -ne 0) { throw 'terms/evidence/pre-submit transaction start rejected; rebuild, review, and reauthorize before any click' }
try {
  Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
} catch {
  Stop-CodeSextantSubmission -Reason post_start_trust_closure_changed -OriginalFailure $_
}
~~~

Only after `start` exits zero and one final `Assert-CodeSextantG8TrustClosure` check may the same locked bridge invoke one atomic `verify-and-click` action in the same page context. It uses exactly one CDP `Runtime.evaluate` call whose manifest-bound expression re-selects the exact contract-bound form, re-captures the complete classified field set and non-sensitive runtime values, proves the static submit identity is unchanged and now enabled, compares the form/field/value digests and page/session nonce to `$preSubmitForm`, verifies `click_deadline_utc`, clicks that unique descendant exactly once only on equality, and atomically writes sanitized `$preClick` with create-new semantics; it never returns token values. A document-wide submit selector is forbidden. If CDP is absent, the module/client/contract digest changes, the tab/document/form/field set changes, the deadline elapses, the form-scoped submit identity/count/enabled state changes, or the sanitized result is absent, invoke `Stop-CodeSextantSubmission` as ambiguous and never click/retry manually. The start—not later confirmation time—must fall inside the 30-minute authorization TTL.

~~~javascript
await bridge.verifyAndClickOnce({context, tab: formTab});
~~~

### G8.6 Verify the positive result and close G8

The terminal helper first atomically writes the exact tool-review/start/authorization/evidence-refresh/runtime/pre-submit/pre-click-bound tombstone and only then quarantines allowlisted partial evidence. If the shell or connector disappears after the click, the next entry reruns the seed-authenticated product-frozen `Initialize-G8Context` prelude in a blank shell. Transaction state is classified immediately: an existing start can route only to initializer-owned recovery, which first invokes the same purpose-built `verify-g8-chain` implementation with the complete explicit input set shown below—including product-root receipt, scan/request/input/findings/tool-review ledgers, evidence-input request, exact authority-response root and manifest, canonical evidence input, packet/review/authorization, and every runtime/submission link—and then requires the product-root absolute generic receipt-registry gate. Only when both exit zero may recovery return `complete`; it terminates without exposing any form/click continuation. A missing input, absent pre-click, incomplete confirmation, purpose-built verification failure, generic registry failure, or request/authority-response/evidence-input mismatch atomically writes the tombstone first and returns `tombstoned`; it has no weaker recovery verifier and never discovers evidence through receipt-controlled paths. `tests/application/test_g8_fresh_shell.py` proves an actual `pwsh -NoProfile` with no inherited variables reconstructs the locked Python and every absolute path, routes recovery exactly once before private imports, invokes both verifiers with the same explicit closure, and issues zero connector clicks.

~~~powershell
try {
  Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
} catch {
  Stop-CodeSextantSubmission -Reason post_click_stage_entry_trust_closure_changed -OriginalFailure $_
}
~~~

Before interpreting the result, require the sanitized `$preClick` returned by the same atomic `verify-and-click` operation. `verify-pre-click` independently validates its schema, page/session nonce, application-tool-review, application-form-contract/form-identity/full-field-set and exact authorized-value digests, click deadline, start digest, and exact equality to the bound runtime/pre-submit receipts. Absence or mismatch is ambiguous and must tombstone. For a clearly positive server-rendered result, Chrome writes only `$confirmationRuntime`: a schema-bounded runtime snapshot containing the official result URL, a positive server-rendered status/reference ID or success text, page/session nonce, and capture UTC. It must contain no raw DOM/HTML, screenshot, token, cookie, header, local-storage value, or arbitrary page bytes. The final source, confirmation, submission receipt, and verifier all bind the tool review, form contract, target profile, exact first/last/message/planned-use/qualification values, evidence refresh, sanitized runtime/pre-submit, pre-click, start, and authorization; a success page without those links is invalid.

The same locked bridge performs one bounded, targeted post-navigation observation and writes only the sanitized confirmation runtime. It requires the current tab's server-rendered URL/origin and a source-derived positive result contract from the current official form snapshot. A generic HTTP 2xx, navigation alone, client-authored text, timeout, connector interruption, or unexpected page is not positive evidence and must enter the tombstone path.

~~~javascript
await bridge.capturePositiveConfirmation({context, tab: formTab});
~~~

~~~powershell
try {
  Assert-CodeSextantG8TrustClosure -Context $g8 -SecondarySubject $applicationToolSubjectPath -ReviewReceipt $applicationToolReviewPath
  if (-not (Test-Path -LiteralPath $preClick -PathType Leaf)) { throw 'atomic verify-and-click did not return a sanitized pre-click receipt' }
  & $releasePython $recordSubmissionToolPath verify-pre-click --application-tool-review $applicationToolReviewPath --application-form-contract $applicationFormContract --submission-start $submissionStart --evidence-refresh $evidenceRefresh --pre-submit-runtime $preSubmitRuntime --pre-submit-form $preSubmitForm --pre-click $preClick --schema $preClickSchemaPath
  if ($LASTEXITCODE -ne 0) { throw 'atomic pre-click receipt does not match the same page/session, bound values, or click deadline' }
  if (-not (Test-Path -LiteralPath $confirmationRuntime -PathType Leaf)) { throw 'Chrome did not emit a sanitized positive confirmation runtime snapshot' }
  & $releasePython $recordSubmissionToolPath record-browser-source --application-tool-review $applicationToolReviewPath --application-form-contract $applicationFormContract --submission-start $submissionStart --pre-click $preClick --runtime-snapshot $confirmationRuntime --runtime-schema $confirmationRuntimeSchemaPath --schema $browserConfirmationSourceSchemaPath --out $browserConfirmationSourcePath
  if ($LASTEXITCODE -ne 0) { throw 'positive browser source capture failed' }
  & $releasePython $recordSubmissionToolPath capture-confirmation --application-tool-review $applicationToolReviewPath --application-form-contract $applicationFormContract --submission-start $submissionStart --evidence-refresh $evidenceRefresh --pre-submit-runtime $preSubmitRuntime --pre-submit-form $preSubmitForm --pre-click $preClick --authorization $applicationAuthorizationPath --source $browserConfirmationSourcePath --out $submissionConfirmationPath
  if ($LASTEXITCODE -ne 0) { throw 'positive confirmation capture failed' }
  $submissionArgs = @('--product-execution-root-receipt',$g8.ProductExecutionRootReceiptPath,'--g7-publication-receipt',$g7PublicationReceiptPath,'--g7-public-smoke-receipt',$g7PublicSmokePath,'--application-tool-review',$applicationToolReviewPath,'--application-form-contract',$applicationFormContract,'--terms',$termsPath,'--target-profile',$targetProfilePath,'--evidence-input-request',$evidenceInputRequestPath,'--evidence-authority-response-root',$evidenceAuthorityResponseRoot,'--evidence-authority-response-manifest',$evidenceAuthorityResponseManifestPath,'--evidence-input',$evidenceInputPath,'--packet',$packetPath,'--review',$claimReviewPath,'--authorization',$applicationAuthorizationPath,'--evidence-refresh',$evidenceRefresh,'--pre-submit-runtime',$preSubmitRuntime,'--pre-submit-form',$preSubmitForm,'--pre-click',$preClick,'--submission-start',$submissionStart,'--confirmation-runtime',$confirmationRuntime,'--browser-source',$browserConfirmationSourcePath,'--confirmation',$submissionConfirmationPath)
  Invoke-CodeSextantG8RegisteredReceipt -Receipt 'claude-oss-submission.json' -FinalPath $submissionPath -ProducerArgs $submissionArgs
  & $releasePython $verifyPacketToolPath verify-g8-chain --product-subject $productSubjectPath --product-execution-root-receipt $g8.ProductExecutionRootReceiptPath --g7-publication-receipt $g7PublicationReceiptPath --g7-public-smoke-receipt $g7PublicSmokePath --application-tool-subject $applicationToolSubjectPath --application-tool-manifest $applicationToolManifestPath --application-tool-review-scope $applicationToolReviewScopePath --application-tool-scan-policy $applicationToolScanPolicyPath --application-tool-threat-model $applicationToolThreatModelPath --terms-source $termsSourcePath --application-tool-scan $applicationToolScanPath --application-tool-review-request $applicationToolReviewRequestPath --application-tool-review-input $applicationToolReviewInputPath --application-tool-findings $applicationToolFindingsPath --application-tool-review $applicationToolReviewPath --application-tool-reviewer-roles $applicationToolReviewerRolesPath --application-form-contract $applicationFormContract --terms $termsPath --attestations $attestationsPath --target-profile $targetProfilePath --evidence-input-request $evidenceInputRequestPath --evidence-authority-response-root $evidenceAuthorityResponseRoot --evidence-authority-response-manifest $evidenceAuthorityResponseManifestPath --evidence-input $evidenceInputPath --packet $packetPath --review-request $claimReviewRequestPath --review-input $claimReviewInputPath --review $claimReviewPath --reviewer-roles $claimReviewerRolesPath --implementation-actors $implementationActorsPath --user-confirmation $userConfirmationPath --authorization $applicationAuthorizationPath --evidence-refresh $evidenceRefresh --pre-submit-runtime $preSubmitRuntime --pre-submit-form $preSubmitForm --pre-click $preClick --submission-start $submissionStart --confirmation-runtime $confirmationRuntime --browser-source $browserConfirmationSourcePath --submission-confirmation $submissionConfirmationPath --submission-tombstone-if-present $submissionTombstone --submission $submissionPath
  if ($LASTEXITCODE -ne 0) { throw 'purpose-built G8 chain verification failed' }
  & $releasePython $releaseGatePath check --gate G8 --registry-extension $registryExtensionPath --launch-policy-extension $launchPolicyExtensionPath --subject $productSubjectPath --secondary-subject $applicationToolSubjectPath --required-receipt $applicationToolReviewPath --evidence-dir $g8EvidenceDirectory @g8VerificationContextArgs
  if ($LASTEXITCODE -ne 0) { throw 'dual-subject plus independent-tool-review G8 registry gate failed' }
} catch {
  Stop-CodeSextantSubmission -Reason post_click_evidence_or_gate_failure -OriginalFailure $_
}
~~~

If Chrome cannot prove whether the click succeeded, do not execute the positive branch. Tombstone first; no automatic second submission is allowed:

~~~powershell
Stop-CodeSextantSubmission -Reason ambiguous_connector_outcome
~~~

Expected: exit 0 only when the verifier recomputes every canonical digest and producer identity across immutable product subject + authenticated product-execution-root receipt + private application-tool/raw-source/form-contract subject -> product-frozen pinned SAST/dependency scan -> distinct independent signed tool-security request/input/findings and scope-complete review -> sealed terms -> exact eligibility attestations and five-field target profile -> deterministic evidence-input request + exact complete create-new authority-response root/manifest + canonical evidence input -> reachable evidence table/use graph and one proven official track -> user-confirmed first name, last name, explicit optional-message state/value, separate planned-use and qualification values -> a different independent reviewer’s fresh-signer/keyless-verifier signed verdict on every typed evidence-use edge plus track verdict -> explicit benefit/billing acknowledgements -> short-lived authorization -> freshly re-fetched terms/evidence and re-derived identical form contract -> sanitized OAuth/email/complete-live-field runtime and pre-submit receipts -> atomic same-page, same-form pre-click receipt -> timely one-shot form-scoped submit -> sanitized positive captured confirmation -> submission receipt. It requires exact account `Zeroxrain99`, exact email `zeroxrain99@gmail.com`, exact equality of first/last/message/planned-use/qualification across target profile, packet, authorization, runtime, pre-submit, pre-click, receipt, and final verifier, every downstream object’s exact `application_tool_review_sha256`, every evidence-request/authority-manifest/evidence-input and form-contract/refresh/runtime/pre-submit/pre-click digest in the success chain, and no matching tombstone.

After confirmed submission, report only: submitted and awaiting Anthropic discretionary review. Do not state that six months of Claude Max are approved until Anthropic confirms it.
