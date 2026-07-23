---
tier: 全文
status: ready-for-execution
date: 2026-07-23
scope: CodeSextant G0-G1 foundation
---

# CodeSextant G0-G1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Establish a clean, immutable Python correctness oracle and a Rust core/store vertical slice that proves schema and storage parity without publishing or replacing the known-good Python product.

**Architecture:** Python 0.16.0 remains the production oracle. A reviewed manifest freezes its source, corpus, and golden outputs; Rust introduces only the performance-sensitive domain and SQLite store foundation, consuming the same schema resource and matching the frozen wire behavior. The former TypeScript-primary rewrite is explicitly superseded and retained only as private fixtures or a future JS/TS semantic-adapter input.

**Tech Stack:** Python 3.11, pytest, Ruff, setuptools, SQLite, Rust 1.96.0 edition 2024, Cargo, rusqlite 0.40.1 with bundled SQLite, serde 1.0.229, serde_json 1.0.151, sha1 0.11.0 only for the legacy Python-compatible locator, sha2 0.10.9 for the strong domain-separated storage identity, thiserror 2.0.19, tempfile 3.27.0, retained Vitest/TypeScript fixture suite.

## Global Constraints

- Commit 8bd0dc2 already completes the Windows-safe daemon log rollover repair. Treat it as a precondition; do not re-edit codesextant/daemon.py or tests/test_daemon_reliability.py in this plan.
- No public repository, package, benchmark claim, release, or Claude for Open Source application is allowed during G0-G1 work.
- Do not read or copy competitor implementation source. Public product documentation, papers, issue descriptions, benchmark protocols, and documented interfaces are the clean-room boundary.
- The Python engine remains usable after every task. No task deletes or redirects the production Python entry point.
- Oracle expected output is never regenerated in CI. Every behavior change, including the later G2 map scope/ranking changes, requires a clean source commit followed by a separate reviewed manifest/golden commit. Rust parity must verify and consume the newest reviewed manifest; it may not continue against an older oracle digest.
- Use C:\Python311\python.exe for local Python commands. Bare python currently resolves to a Hermes virtual environment without pytest.
- Use only the tracked SSOT `tools/exact_task_commit.ps1` for implementation commits after its Task 1 bootstrap. It rejects a nonempty pre-existing index; duplicate/undeclared paths; every status other than exact `A`/`M`; rename/copy/type-change inference; cached whitespace errors; commit failure; hook execution; and any cached-versus-HEAD path/status/blob/mode drift. Never use directory-wide staging, stash, reset, or history rewriting.
- All new Markdown artifacts are English and start with tier metadata. Existing zh-TW documentation may receive only the status/supersession banner specified here.
- Rust core/store work covers the G1 vertical slice only. Rust implementations of repository map, impact, duplicates, and the remaining public queries belong to later G2-G3 plans; no skipped or expected-failure test may be used to imply those queries are complete.
- The current Python schema is version 4. The retained TS fixture implementation is version 3 and must not become a schema authority.
- A Cargo manifest change has one controlled lockfile-update window: after writing the complete manifest set, run `cargo generate-lockfile` once, review the complete new `Cargo.lock` package/checksum diff, and then run every metadata/build/test/clippy command with `--locked`. `cargo generate-lockfile` is the only unlocked Cargo command allowed by this plan; a missing, unchanged when dependencies changed, or unexpectedly broadened lock diff is red.
- Every task uses red-green-refactor discipline, ends in a focused commit, and leaves the worktree clean.

## Execution Setup

Run these checks from E:\ai-king\項目資料\CodeSextant after the plan itself has been committed:

~~~powershell
git merge-base --is-ancestor 8bd0dc2 HEAD
git status --porcelain
~~~

Expected: the ancestry command exits 0 and status is empty. Then create the isolated execution worktree:

~~~powershell
git worktree add ".worktrees/codesextant-sota-gate" -b "codex/codesextant-sota-gate"
git -C ".worktrees/codesextant-sota-gate" status --short
~~~

Expected: the new worktree is clean. Run every remaining command from E:\ai-king\項目資料\CodeSextant\.worktrees\codesextant-sota-gate.

---

### Task 1: Make the Python product version authoritative

**Files:**
- Create: tools/exact_task_commit.ps1
- Test: tests/release/test_exact_task_commit.py
- Create: codesextant/_version.py
- Modify: codesextant/__init__.py
- Modify: pyproject.toml
- Create: tools/sync_version.py
- Test: tests/test_version_ssot.py

**Interfaces:**
- Consumes: existing codesextant import surface and daemon._engine_pkg_version().
- Produces: `Invoke-ExactTaskCommit -ExpectedPaths <string[]> -Message <string>` as the sole implementation-commit entrypoint for every later G0-G3 task; codesextant._version.__version__: str, codesextant._version.ENGINE_VERSION: int, and codesextant.__version__ as a compatibility re-export.

- [ ] **Step 1: Write disposable-repository tests for the exact commit SSOT**

Create `tests/release/test_exact_task_commit.py`. Every case creates a real temporary Git repository with a baseline commit and invokes a fresh `pwsh -NoProfile` process that dot-sources the tracked helper. Cover this exact matrix:

~~~python
@pytest.mark.parametrize("change_kind", ["add", "modify"])
def test_exact_task_commit_accepts_only_declared_add_or_modify(real_repo, change_kind):
    expected = apply_change(real_repo, change_kind)
    result = invoke_exact_commit(real_repo, expected, "test: exact closure")
    assert result.returncode == 0
    assert committed_name_status(real_repo) == expected_name_status(real_repo, expected)
    assert cached_name_status(real_repo) == []


@pytest.mark.parametrize("change_kind", ["delete", "rename", "copy", "type_change"])
def test_exact_task_commit_rejects_d_r_c_t_from_real_git_name_status(real_repo, change_kind):
    expected = stage_real_change_kind(real_repo, change_kind)
    before = head_oid(real_repo)
    result = invoke_index_assertion(real_repo, expected)
    assert result.returncode != 0
    assert head_oid(real_repo) == before


def test_exact_task_commit_rejects_duplicate_manifest_and_pre_staged_extra(real_repo):
    write(real_repo / "declared.txt", "declared")
    write(real_repo / "extra.txt", "extra")
    assert invoke_exact_commit(real_repo, ["declared.txt", "declared.txt"], "bad").returncode != 0
    git(real_repo, "add", "--", "extra.txt")
    assert invoke_exact_commit(real_repo, ["declared.txt"], "bad").returncode != 0


def test_exact_task_commit_rejects_directory_wide_manifest(real_repo):
    write(real_repo / "tree" / "a.txt", "a")
    assert invoke_exact_commit(real_repo, ["tree"], "bad").returncode != 0


def test_commit_hook_cannot_mutate_the_index_or_committed_closure(real_repo):
    install_pre_commit_hook_that_stages(real_repo, "unexpected.txt")
    write(real_repo / "declared.txt", "declared")
    result = invoke_exact_commit(real_repo, ["declared.txt"], "test: hook isolated")
    assert result.returncode == 0
    assert not (real_repo / "hook-ran.sentinel").exists()
    assert committed_name_status(real_repo) == ["A\tdeclared.txt"]


def test_cached_blob_or_mode_mutation_never_matches_committed_closure(real_repo):
    write(real_repo / "declared.txt", "before")
    mutation = invoke_test_only_index_mutation_fence(real_repo, ["declared.txt"])
    assert mutation.returncode != 0
    assert "cached-versus-HEAD blob/mode drift" in mutation.stderr
~~~

`stage_real_change_kind(..., "type_change")` uses `git hash-object -w --stdin` plus `git update-index --cacheinfo 120000,<blob>,type-change.txt`, so the test exercises a real Git `T` row without requiring Windows symlink privilege. The fixture sets local test identity, never touches the product repository, and deletes the disposable root on exit. For the mutation test only, `invoke_test_only_index_mutation_fence` copies the helper into that disposable root and injects one index mutation at the marked post-capture test seam; the tracked product helper contains no test switch or environment-controlled branch.

- [ ] **Step 2: Run the helper tests RED**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_exact_task_commit.py -q
~~~

Expected: FAIL because `tools/exact_task_commit.ps1` does not exist.

- [ ] **Step 3: Implement the single tracked exact-commit helper**

Create `tools/exact_task_commit.ps1` with strict mode and exactly two exported functions: `Assert-ExactTaskIndex` and `Invoke-ExactTaskCommit`. The assertion parses `git diff --cached --name-status --find-renames --find-copies --find-copies-harder`, rejects malformed/duplicate rows and every status except single-path `A`/`M`, and requires case-sensitive set equality with the sorted unique manifest. The commit function:

~~~powershell
function Invoke-ExactTaskCommit {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)][string[]]$ExpectedPaths,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Message
  )
  $expected = @($ExpectedPaths | ForEach-Object { $p = $_.Replace('\','/'); if ($p.StartsWith('./',[StringComparison]::Ordinal)) { $p = $p.Substring(2) }; $p } | Sort-Object)
  if ($expected.Count -eq 0 -or (@($expected | Select-Object -Unique)).Count -ne $expected.Count) { throw 'expected path manifest is empty or contains duplicates' }
  if ($expected | Where-Object { [IO.Path]::IsPathRooted($_) -or $_ -match '(^|/)\.\.(/|$)' -or $_ -match "[`r`n`t]" }) { throw 'expected path is absolute, escaping, or unparseable' }
  if ($expected | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) }) { throw 'every expected path must name one existing file; directory-wide or deletion staging is forbidden' }
  $preStaged = @(& git diff --cached --name-status)
  if ($LASTEXITCODE -ne 0) { throw 'unable to inspect the pre-existing index' }
  if ($preStaged.Count -ne 0) { throw 'pre-existing staged changes are forbidden' }
  & git add -- $expected
  if ($LASTEXITCODE -ne 0) { throw 'exact git add failed' }
  $staged = Assert-ExactTaskIndex -ExpectedPaths $expected -ReturnRows
  & git diff --cached --check
  if ($LASTEXITCODE -ne 0) { throw 'cached whitespace check failed' }
  $stagedObjects = Get-ExactIndexObjects -ExpectedPaths $expected

  & git -c core.hooksPath=NUL commit --no-verify -m $Message
  if ($LASTEXITCODE -ne 0) { throw 'git commit failed' }
  $committed = Get-ExactHeadRows
  if (Compare-Object -ReferenceObject $staged -DifferenceObject $committed -CaseSensitive) { throw 'cached-versus-HEAD name-status drift' }
  $headObjects = Get-ExactHeadObjects -ExpectedPaths $expected
  if (Compare-Object -ReferenceObject $stagedObjects -DifferenceObject $headObjects -CaseSensitive) { throw 'cached-versus-HEAD blob/mode drift' }
  $remainingStaged = @(& git diff --cached --name-status)
  if ($LASTEXITCODE -ne 0) { throw 'unable to inspect the post-commit index' }
  if ($remainingStaged.Count -ne 0) { throw 'index mutated during commit' }
}
~~~

The actual file includes the complete definitions of `Get-ExactIndexObjects`, `Get-ExactHeadRows`, and `Get-ExactHeadObjects`: they parse Git's tab-delimited output without `Invoke-Expression`, compare normalized `mode object-id path` rows, require one row per expected path, and check every native exit code. The disposable-only mutation fence is implemented inside the helper test harness by copying the helper to the disposable repository and inserting the mutation callback at its marked test seam; the tracked production helper contains no environment-controlled bypass. `core.hooksPath=NUL` and `--no-verify` are both mandatory defense in depth, and the real hook test proves the configured hook never executes.

- [ ] **Step 4: Run all exact-commit tests against real disposable repositories**

~~~powershell
C:\Python311\python.exe -m pytest tests/release/test_exact_task_commit.py -q
~~~

Expected: PASS for exact A/M commits and PASS for every fail-closed D/R/C/T, duplicate, extra-path, hook, and cached-versus-HEAD mutation assertion. No test changes the product repository's HEAD or index.

- [ ] **Step 5: Write the failing version-authority test**

~~~python
from __future__ import annotations

import tomllib
from pathlib import Path

import codesextant
from codesextant import daemon
from codesextant import _version


def test_python_package_version_has_one_authority():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in data["project"]
    assert data["project"]["dynamic"] == ["version"]
    assert data["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "codesextant._version.__version__",
    }
    assert _version.__version__ == "0.16.0"
    assert _version.ENGINE_VERSION == 1
    assert codesextant.__version__ == _version.__version__
    assert daemon._engine_pkg_version() == _version.__version__


def test_version_projection_tool_rejects_any_mirror_drift(tmp_path):
    fixture = version_fixture(
        tmp_path,
        python_product_version="0.16.0",
        cargo_internal_abi_version="0.1.0",
        rust_product_version="0.15.0",
    )
    assert sync_version.check(fixture, phase="foundation").status == "fail"
    sync_version.project_rust(fixture)
    assert fixture.rust_product_version == "0.16.0"
    assert fixture.cargo_internal_abi_version == "0.1.0"
    assert sync_version.check(fixture, phase="foundation").status == "pass"


def test_final_version_contract_requires_all_product_surfaces(final_version_fixture):
    result = sync_version.check(final_version_fixture, phase="final")
    assert result.checked == {
        "python_authority",
        "setuptools_dynamic_metadata",
        "rust_product_version_projection",
        "codesextant_version_output",
        "codesextant_mcp_version_output",
        "codesextantd_version_output",
        "component_manifest_versions",
        "artifact_manifest_version",
        "installer_version",
        "release_subject_version_and_tag",
    }
    assert result.status == "pass"
~~~

- [ ] **Step 6: Run the test and observe the existing drift**

Run:

~~~powershell
C:\Python311\python.exe -m pytest tests/test_version_ssot.py -q
~~~

Expected: FAIL because codesextant._version does not exist and pyproject.toml still contains project.version = "0.15.0".

- [ ] **Step 7: Add the single version module**

Create codesextant/_version.py:

~~~python
"""CodeSextant product and engine compatibility versions."""

__version__ = "0.16.0"
ENGINE_VERSION = 1
~~~

In codesextant/__init__.py, import these values after the future import and delete the existing long literal assignment:

~~~python
from ._version import ENGINE_VERSION, __version__
~~~

Keep __version__ and ENGINE_VERSION in __all__.

- [ ] **Step 8: Delegate setuptools metadata to the same module**

In pyproject.toml, remove version = "0.15.0", add dynamic = ["version"] under [project], and add:

~~~toml
[tool.setuptools.dynamic]
version = {attr = "codesextant._version.__version__"}
~~~

Create `tools/sync_version.py` in the same commit. It parses `codesextant/_version.py` as the sole editable product-version authority and exposes: `project-rust`, which mechanically writes only `crates/codesextant-core/src/generated/product_version.rs` once the Rust core exists; `--check --phase python`, which verifies setuptools dynamic metadata and the Python import/re-export before Rust exists; `--check --phase foundation`, which additionally requires the exact generated Rust `PRODUCT_VERSION` projection while permitting Cargo workspace/crate versions to remain independent internal ABI versions; `--check --phase binaries`, which additionally executes all three product binaries' `--version`; and `--check --phase final`, which additionally validates every component/artifact/install manifest and installer metadata and checks ReleaseSubject `product_version` plus `release_tag == "v" + product_version`. Missing required phase surfaces, use of `CARGO_PKG_VERSION` for a product-facing value, or any product-version mismatch is red. The tool never edits `_version.py`, manifests, installers, ReleaseSubject, or Cargo package versions; only `project-rust` may update the generated Rust product-version mirror. Its parser is covered by tests and does not use regex replacement across arbitrary files.

- [ ] **Step 9: Run focused and package-build verification**

Run:

~~~powershell
C:\Python311\python.exe -m pytest tests/test_version_ssot.py tests/test_daemon_reliability.py -q
C:\Python311\python.exe tools/sync_version.py --check --phase python
$wheelDir = Join-Path $env:TEMP ("codesextant-wheel-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $wheelDir | Out-Null
C:\Python311\python.exe -m pip wheel --no-deps . -w $wheelDir
Get-ChildItem $wheelDir -Filter "codesextant-0.16.0-*.whl"
C:\Python311\python.exe -m pytest tests/release/test_exact_task_commit.py -q
if ($LASTEXITCODE -ne 0) { throw 'post-implementation exact-task-commit GREEN verification failed' }
~~~

Expected: version and daemon tests PASS, exactly one 0.16.0 wheel is found, and the implemented exact-task-commit helper passes its full disposable-repository matrix immediately before the bootstrap commit.

- [ ] **Step 10: Commit the helper and version authority through the tested SSOT**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('tools/exact_task_commit.ps1','tests/release/test_exact_task_commit.py','codesextant/_version.py','codesextant/__init__.py','pyproject.toml','tools/sync_version.py','tests/test_version_ssot.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'build: establish Python product version authority'
~~~

Expected: one commit whose exact A/M closure is the seven paths above, with no hook execution and an empty index afterward. This is the only bootstrap: every later G0-G3 task dot-sources this same tracked helper; no plan may define a duplicate commit helper.

---

### Task 2: Supersede the TypeScript-primary architecture

**Files:**
- Create: docs/architecture/adr/0001-rust-kernel.md
- Create: docs/architecture/adr/0002-python-oracle.md
- Modify: docs/全TS重寫架構藍圖_2026-06-24.md
- Modify: ts/package.json
- Modify mechanically: ts/package-lock.json
- Test: tests/test_architecture_authority.py

**Interfaces:**
- Consumes: approved SOTA release-gate design and the retained ts test suite.
- Produces: one accepted Rust-kernel authority, one accepted Python-oracle authority, and a machine-private TS fixture package named @codesextant/legacy-ts-fixtures.

- [ ] **Step 1: Write the failing architecture-authority test**

~~~python
from __future__ import annotations

import json
from pathlib import Path


def test_rust_adr_is_the_only_active_kernel_authority():
    rust_adr = Path("docs/architecture/adr/0001-rust-kernel.md").read_text(
        encoding="utf-8"
    )
    oracle_adr = Path("docs/architecture/adr/0002-python-oracle.md").read_text(
        encoding="utf-8"
    )
    old = Path("docs/全TS重寫架構藍圖_2026-06-24.md").read_text(encoding="utf-8")
    package = json.loads(Path("ts/package.json").read_text(encoding="utf-8"))

    assert "status: accepted" in rust_adr.lower()
    assert "supersedes" in rust_adr.lower()
    assert "status: accepted" in oracle_adr.lower()
    assert "status: superseded" in old.lower()
    assert "0001-rust-kernel.md" in old
    assert package["name"] == "@codesextant/legacy-ts-fixtures"
    assert package["version"] == "0.0.0-private"
    assert package["private"] is True
    assert not {"bin", "main", "types", "files"} & package.keys()
~~~

- [ ] **Step 2: Run the test and observe both active authorities**

Run:

~~~powershell
C:\Python311\python.exe -m pytest tests/test_architecture_authority.py -q
~~~

Expected: FAIL because the ADRs do not exist, the old blueprint is not marked superseded, and ts/package.json still presents itself as the codesextant product.

- [ ] **Step 3: Write ADR 0001 with an explicit supersession decision**

Create docs/architecture/adr/0001-rust-kernel.md with:

~~~markdown
---
tier: 全文
status: accepted
date: 2026-07-23
---

# ADR 0001: Rust Kernel

## Context

The production Python engine is correct but its CPU-heavy indexing and query work
sets the concurrency and latency floor. The earlier TypeScript-primary blueprint
optimized distribution before proving the required performance envelope.

## Decision

Rust owns repository identity, discovery, parsing, graph persistence, migrations,
ranking, query hot paths, bounded work, cancellation, and resource accounting.
Python remains the production correctness oracle until reviewed parity is green.
The TypeScript rewrite is not a standalone replacement or release authority.

Retained TypeScript material is limited to JS/TS semantic-adapter candidates,
protocol-conformance fixtures, golden-output fixtures, and experiments explicitly
recorded as discarded. This ADR supersedes
docs/全TS重寫架構藍圖_2026-06-24.md.

## Consequences

CodeSextant has one kernel direction. Rust crate versions are internal ABI
versions; codesextant/_version.py remains the product-version authority.
No known-good Python behavior is removed before external parity tests pass.
~~~

- [ ] **Step 4: Write ADR 0002 with the immutable-oracle protocol**

Create docs/architecture/adr/0002-python-oracle.md with:

~~~markdown
---
tier: 全文
status: accepted
date: 2026-07-23
---

# ADR 0002: Immutable Python Oracle

## Context

Parity is meaningless if expected output changes in the same commit as the
replacement. The Python engine therefore needs a commit-bound, reproducible
behavioral snapshot.

## Decision

tests/fixtures/oracle-manifest.json binds the Python commit, product version,
engine version, schema version, generator version, Python source digest, corpus
digest, and golden-output digests. CI verifies these values but cannot regenerate
them. A source or behavior update is committed first; regenerated manifest and
goldens are reviewed in a separate commit. Intentional differences are named,
tested, and recorded rather than silently accepted.

## Consequences

Rust parity tests consume immutable outputs. A changed Python source digest blocks
the gate until the oracle-update process is deliberately completed. The Python
engine remains available throughout migration.
~~~

- [ ] **Step 5: Disable the old TS package as a product authority**

Add status: superseded to the old blueprint frontmatter and place this sentence immediately below its title:

~~~markdown
> Superseded by [ADR 0001](architecture/adr/0001-rust-kernel.md). This document
> remains only as migration history and a source of reusable TS fixtures.
~~~

Change the package identity to:

~~~json
{
  "name": "@codesextant/legacy-ts-fixtures",
  "version": "0.0.0-private",
  "private": true,
  "description": "Private retained TypeScript parity fixtures and JS/TS adapter experiments."
}
~~~

Preserve type, scripts, dependencies, and devDependencies; remove bin, main, types, and files.

- [ ] **Step 6: Regenerate only lockfile metadata and verify retained fixtures**

~~~powershell
npm --prefix ts install --package-lock-only --ignore-scripts
C:\Python311\python.exe -m pytest tests/test_architecture_authority.py -q
npm --prefix ts test
npm --prefix ts run build
~~~

Expected: Python test PASS; retained Vitest suite and TypeScript build PASS.

- [ ] **Step 7: Commit the authority decision**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('docs/architecture/adr/0001-rust-kernel.md','docs/architecture/adr/0002-python-oracle.md','docs/全TS重寫架構藍圖_2026-06-24.md','ts/package.json','ts/package-lock.json','tests/test_architecture_authority.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'docs: supersede TypeScript-primary architecture'
~~~

---

### Task 3: Extract schema v4 as the Python/Rust shared resource

**Files:**
- Create: codesextant/schema_v4.sql
- Modify: codesextant/storage.py
- Modify: pyproject.toml
- Test: tests/test_schema_resource.py

**Interfaces:**
- Consumes: the exact 8bd0dc2 storage._SCHEMA body, whose UTF-8 SHA-256 is 6051d89c781fd4d4e2944920b6fc86e6c589d6920ce68480dd71fd3cffa80a1b and whose Python string length is 3304.
- Produces: codesextant/storage.py::_load_schema_resource() -> tuple[int, str], SCHEMA_VERSION == 4, and _SCHEMA containing the unchanged SQL body.

- [ ] **Step 1: Write the failing resource-authority test**

~~~python
from __future__ import annotations

import hashlib
from importlib import resources

from codesextant import storage


EXPECTED_BODY_SHA256 = (
    "6051d89c781fd4d4e2944920b6fc86e6c589d6920ce68480dd71fd3cffa80a1b"
)


def test_schema_resource_is_the_authority():
    resource = resources.files("codesextant").joinpath("schema_v4.sql")
    text = resource.read_text(encoding="utf-8")
    header, body = text.split("\n", 1)
    assert header == "-- codesextant-schema-version: 4"
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == EXPECTED_BODY_SHA256
    assert storage.SCHEMA_VERSION == 4
    assert storage._SCHEMA == body
    assert "idx_symbols_map" in body
~~~

- [ ] **Step 2: Run the test and observe the missing resource**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_schema_resource.py -q
~~~

Expected: FAIL with FileNotFoundError for codesextant/schema_v4.sql.

- [ ] **Step 3: Move the exact SQL body without editing it**

Use git show 8bd0dc2:codesextant/storage.py as the source of truth. Move the complete string assigned to _SCHEMA into codesextant/schema_v4.sql, prepend exactly:

~~~sql
-- codesextant-schema-version: 4
~~~

The bytes after the first newline must hash to the value in the test. Do not reformat SQL.

- [ ] **Step 4: Load and validate the resource**

Replace the literal SCHEMA_VERSION and _SCHEMA definitions in storage.py with:

~~~python
import re
from importlib import resources

_SCHEMA_HEADER = re.compile(r"^-- codesextant-schema-version: ([1-9][0-9]*)$")


def _load_schema_resource() -> tuple[int, str]:
    text = resources.files("codesextant").joinpath("schema_v4.sql").read_text(
        encoding="utf-8"
    )
    header, body = text.split("\n", 1)
    match = _SCHEMA_HEADER.fullmatch(header)
    if match is None:
        raise RuntimeError("schema_v4.sql has no valid schema-version header")
    return int(match.group(1)), body


SCHEMA_VERSION, _SCHEMA = _load_schema_resource()
~~~

Add the package-data declaration:

~~~toml
[tool.setuptools.package-data]
codesextant = ["schema_v4.sql"]
~~~

- [ ] **Step 5: Verify behavior and wheel contents**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_schema_resource.py tests/test_storage_readonly.py tests/test_storage_concurrency.py tests/test_codemap.py -q
$wheelDir = Join-Path $env:TEMP ("codesextant-schema-wheel-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $wheelDir | Out-Null
C:\Python311\python.exe -m pip wheel --no-deps . -w $wheelDir
C:\Python311\python.exe -c "import glob,zipfile,sys; p=glob.glob(sys.argv[1]+'/*.whl')[0]; z=zipfile.ZipFile(p); assert 'codesextant/schema_v4.sql' in z.namelist()" $wheelDir
~~~

Expected: tests PASS and the resource exists inside the wheel.

- [ ] **Step 6: Commit the shared schema**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('codesextant/schema_v4.sql','codesextant/storage.py','pyproject.toml','tests/test_schema_resource.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'refactor: make graph schema a shared resource'
~~~

---

### Task 4: Add the immutable Python oracle generator

**Files:**
- Create: tests/parity/__init__.py
- Create: tests/parity/canonical.py
- Create: tests/parity/cases.py
- Create: tests/parity/corpora/python_core/app.py
- Create: tests/parity/corpora/python_core/service.py
- Create: tests/parity/corpora/python_core/models.py
- Create: tests/parity/corpora/python_core/cases/render_case.py
- Create: requirements/oracle.lock
- Create: tools/oracle_environment.py
- Create: tools/oracle_snapshot.py
- Test: tests/test_oracle_harness.py
- Test: tests/test_oracle_manifest.py

**Interfaces:**
- Consumes: all names in codesextant._ENGINE_EXPORTS, ProjectStore, the schema resource, and an isolated CODESEXTANT_HOME.
- Produces: OracleCase, module-level ORACLE_CASES, PUBLIC_ENGINE_OPERATIONS, canonicalize(), tree_sha256() over an explicit tracked-entry closure, run_engine_snapshot(), run_store_snapshot(), write_oracle(), verify_oracle(), and verify_output_root().

- [ ] **Step 1: Add a deterministic corpus**

Create service.py:

~~~python
"""Small deterministic oracle service."""

from models import Message


def format_message(name: str) -> Message:
    return Message(text=f"hello {name}")


def render(name: str) -> str:
    return format_message(name).text


def structurally_same_a(value: int) -> int:
    if value > 0:
        return value + 1
    return 0


def structurally_same_b(number: int) -> int:
    if number > 0:
        return number + 1
    return 0


def disconnected_helper() -> str:
    # FIXME: intentional oracle fixture marker; this is test data.
    return "unused"
~~~

Create models.py:

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    text: str
~~~

Create app.py:

~~~python
from service import render


def main() -> str:
    return render("CodeSextant")


if __name__ == "__main__":
    print(main())
~~~

Create `cases/render_case.py` (fixture source data, deliberately not a pytest collection name):

~~~python
from service import render


def test_render():
    assert render("Ada") == "hello Ada"
~~~

- [ ] **Step 2: Write the failing harness tests**

~~~python
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import codesextant
from tests.parity.canonical import canonicalize
from tests.parity.cases import ORACLE_CASES, PUBLIC_ENGINE_OPERATIONS, run_engine_snapshot
from tools import oracle_snapshot


def test_every_public_engine_operation_has_an_oracle_case():
    names = [case.name for case in ORACLE_CASES]
    assert len(names) == len(set(names))
    assert frozenset(names) == PUBLIC_ENGINE_OPERATIONS == frozenset(codesextant._ENGINE_EXPORTS)


def test_fixture_corpora_are_not_collected_by_pytest():
    roots = [str(path) for path in (
        Path("tests/parity/corpora"), Path("tests/parity/fixtures")
    ) if path.exists()]
    assert roots
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *roots],
        cwd=Path.cwd(), capture_output=True, text=True, check=False,
    )
    assert result.returncode == 5  # no tests collected
    assert "test_render" not in result.stdout


def test_canonicalizer_removes_machine_state(tmp_path):
    corpus = tmp_path / "corpus"
    home = tmp_path / "home"
    corpus.mkdir()
    home.mkdir()
    value = {
        "path": str(corpus / "app.py"),
        "db_file": str(home / "index.db"),
        "elapsed_ms": 9.5,
        "last_indexed_at": 123.0,
    }
    assert canonicalize(value, corpus_root=corpus, home=home) == {
        "path": "$CORPUS/app.py",
        "db_file": "$HOME/index.db",
    }


def test_snapshot_is_byte_stable(tmp_path, monkeypatch):
    corpus = Path("tests/parity/corpora/python_core").resolve()
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "home-a"))
    first = run_engine_snapshot(corpus, tmp_path / "home-a")
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "home-b"))
    second = run_engine_snapshot(corpus, tmp_path / "home-b")
    assert first == second


def test_writer_refuses_ci(monkeypatch, tmp_path):
    monkeypatch.setenv("CI", "true")
    with pytest.raises(SystemExit) as exc:
        oracle_snapshot.write_oracle(
            repo_root=Path.cwd(),
            oracle_commit="8bd0dc2",
            output_root=tmp_path / "new-oracle-output",
        )
    assert exc.value.code == 2
~~~

- [ ] **Step 3: Run the tests and observe missing parity modules**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_oracle_harness.py -q
~~~

Expected: collection FAIL because tests.parity.canonical and tests.parity.cases do not exist.

- [ ] **Step 4: Implement canonical JSON shaping**

Create tests/parity/canonical.py:

~~~python
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

VOLATILE_KEYS = frozenset({"elapsed_ms", "indexed_at", "last_indexed_at"})


def _portable(text: str, source: Path, marker: str) -> str:
    source_text = str(source.resolve())
    normalized = text.replace("\\", "/")
    source_normalized = source_text.replace("\\", "/")
    return normalized.replace(source_normalized, marker)


def canonicalize(value, *, corpus_root: Path, home: Path):
    if isinstance(value, dict):
        if "project_key" in value:
            raise AssertionError(
                "project_key must be asserted byte-for-byte by the identity parity harness "
                "and removed before portable golden serialization"
            )
        return {
            key: canonicalize(item, corpus_root=corpus_root, home=home)
            for key, item in sorted(value.items())
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [
            canonicalize(item, corpus_root=corpus_root, home=home)
            for item in value
        ]
    if isinstance(value, str):
        return _portable(
            _portable(value, corpus_root, "$CORPUS"),
            home,
            "$HOME",
        )
    return value


def canonical_json(value) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def tree_sha256(paths: Iterable[Path], *, root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()
~~~

- [ ] **Step 5: Implement the operation registry and deterministic order**

Create tests/parity/cases.py with this public set:

~~~python
PUBLIC_ENGINE_OPERATIONS = frozenset({
    "index_project",
    "get_symbols",
    "find_references",
    "find_deadcode",
    "find_unwired",
    "find_duplicates",
    "get_comment_overview",
    "find_comment_tags",
    "get_comments",
    "call_hierarchy",
    "impact",
    "get_health",
    "get_map",
    "status",
    "list_projects",
    "find_ai_usage",
})
~~~

Define:

~~~python
@dataclass(frozen=True)
class OracleCase:
    name: str
    run: Callable[[Path], dict]


ORACLE_CASES = (
    OracleCase("index_project", lambda root: engine.index_project(str(root), force=True)),
    OracleCase("get_symbols", lambda root: engine.get_symbols(str(root))),
    OracleCase("find_references", lambda root: engine.find_references(
        str(root), "format_message", def_path=str(root / "service.py"), src_root=str(root))),
    OracleCase("call_hierarchy", lambda root: engine.call_hierarchy(
        str(root), "format_message", direction="both", def_path=str(root / "service.py"),
        src_root=str(root), build_edges=True)),
    OracleCase("impact", lambda root: engine.impact(
        str(root), "format_message", def_path=str(root / "service.py"), src_root=str(root))),
    OracleCase("get_map", lambda root: engine.get_map(str(root), token_budget=2000)),
    OracleCase("status", lambda root: engine.status(str(root), check_freshness=False)),
    OracleCase("list_projects", lambda root: engine.list_projects()),
    OracleCase("find_deadcode", lambda root: engine.find_deadcode(
        str(root), scope_file=str(root / "service.py"), lang="python")),
    OracleCase("find_ai_usage", lambda root: engine.find_ai_usage(str(root))),
    OracleCase("find_unwired", lambda root: engine.find_unwired(str(root))),
    OracleCase("find_duplicates", lambda root: engine.find_duplicates(
        str(root), scope_file=str(root / "service.py"), near_global=False,
        include_call_pattern=False)),
    OracleCase("get_comment_overview", lambda root: engine.get_comment_overview(
        str(root), scope_file=str(root / "service.py"))),
    OracleCase("find_comment_tags", lambda root: engine.find_comment_tags(
        str(root), tags=["FIXME"], scope_file=str(root / "service.py"))),
    OracleCase("get_comments", lambda root: engine.get_comments(
        str(root), file=str(root / "service.py"))),
    OracleCase("get_health", lambda root: engine.get_health(str(root))),
)


def run_engine_snapshot(corpus_root: Path, home: Path) -> dict[str, object]:
    os.environ["CODESEXTANT_HOME"] = str(home)
    names = [case.name for case in ORACLE_CASES]
    if len(names) != len(set(names)) or frozenset(names) != PUBLIC_ENGINE_OPERATIONS:
        raise AssertionError("oracle case registry is incomplete or duplicated")
    raw = {case.name: case.run(corpus_root) for case in ORACLE_CASES}
    return canonicalize(raw, corpus_root=corpus_root, home=home)
~~~

Implement the store transcript with the existing Python API:

~~~python
def run_store_snapshot(corpus_root: Path, home: Path) -> dict[str, object]:
    os.environ["CODESEXTANT_HOME"] = str(home)
    source = str((corpus_root / "service.py").resolve())
    symbols = [
        {
            "path": source,
            "kind": "function",
            "name": "format_message",
            "line": 6,
            "end_line": 7,
            "scope": "",
        },
        {
            "path": source,
            "kind": "function",
            "name": "render",
            "line": 10,
            "end_line": 11,
            "scope": "",
        },
    ]
    edge = {
        "src_path": source,
        "src_line": 11,
        "symbol_name": "format_message",
        "def_path": source,
        "def_line": 6,
        "confidence": "high",
    }
    fingerprints = [{
        "name": "format_message", "kind": "function", "line": 6, "end_line": 7,
        "scope": "模組", "shape_hash": "shape-v1", "raw_token_hash": None,
        "call_hash": "call-v1", "node_count": 3, "nstmts": 1,
        "has_control_flow": False, "cognitive": 0,
    }]
    winnow_index = [{"line": 6, "fp_value": (2**63) - 2}]
    comments = [{
        "line": 5, "end_line": 5, "kind": "line", "is_doc": True,
        "tag": "契約", "scope": "模組", "owner_line": 6, "text": "UTF-8 註解",
    }]
    with storage.ProjectStore.open(str(corpus_root)) as store:
        store.store_file_symbols(source, "content-v1", symbols, 1000.0)
        store.store_file_fingerprints(source, fingerprints, winnow_index)
        store.store_file_comments(source, comments)
        store.replace_refs_for(source, [edge])
        def table(name: str, order: str) -> list[dict]:
            return [dict(row) for row in store.conn.execute(
                f"SELECT * FROM {name} WHERE path=? ORDER BY {order}", (source,)
            ).fetchall()]
        before = {
            "needs_same": store.needs_reindex(source, "content-v1"),
            "needs_changed": store.needs_reindex(source, "content-v2"),
            "symbols": store.get_symbols(),
            "fingerprints": table("fingerprints", "line,name"),
            "winnow_index": table("fingerprint_index", "line,fp_value"),
            "comments": table("comments", "line,end_line,kind"),
            "refs": store.all_refs(),
            "stats": store.stats(),
        }
        store.remove_file(source)
        after = {
            "symbols": store.get_symbols(),
            "fingerprints": table("fingerprints", "line,name"),
            "winnow_index": table("fingerprint_index", "line,fp_value"),
            "comments": table("comments", "line,end_line,kind"),
            "refs": store.all_refs(),
            "stats": store.stats(),
        }
    expected_key = storage.project_key(str(corpus_root))
    for stats in (before["stats"], after["stats"]):
        assert stats.pop("project_key") == expected_key
    return canonicalize(
        {"identity_checked": True, "before": before, "after": after},
        corpus_root=corpus_root,
        home=home,
    )
~~~

`run_engine_snapshot` applies the same rule to every public operation response: before portable serialization it traverses every `project_key`, directly asserts it equals `storage.project_key(str(corpus_root))`, removes it, and adds one top-level `identity_checked=true`. Canonicalization refuses an unasserted identity field; `$PROJECT_KEY` is no longer a scrub token. Cross-language equality itself is proven by the unsanitized Python/Rust vector and existing-DB tests in Task 6.

- [ ] **Step 6: Implement guarded oracle writing**

tools/oracle_snapshot.py must expose:

~~~python
GENERATOR_VERSION = 1


def write_oracle(
    *,
    repo_root: Path,
    oracle_commit: str,
    output_root: Path,
) -> None:
    if os.environ.get("CI"):
        raise SystemExit(2)
    if subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout:
        raise SystemExit(2)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if oracle_commit != head:
        raise SystemExit(2)
    source_root, tracked_entries = materialize_tracked_regular_commit(
        repo_root, oracle_commit
    )
    staging_root = prepare_new_output_staging(repo_root, output_root)
    manifest_path = staging_root / "tests/fixtures/oracle-manifest.json"
    engine_output = staging_root / "tests/parity/golden/python-engine-v1.json"
    store_output = staging_root / "tests/parity/golden/python-store-v1.json"
    engine_value, store_value, execution = run_materialized_oracle_child(
        source_root=source_root,
        lock_path=source_root / "requirements/oracle.lock",
    )

    engine_bytes = canonical_json(engine_value)
    store_bytes = canonical_json(store_value)
    engine_output.parent.mkdir(parents=True, exist_ok=True)
    store_output.parent.mkdir(parents=True, exist_ok=True)
    engine_output.write_bytes(engine_bytes)
    store_output.write_bytes(store_bytes)

    product_paths = select_tracked_regular(tracked_entries, source_root, prefixes=[
        "codesextant/",
    ], exact=[
        "pyproject.toml", "ts_bridge/find_refs.mjs", "ts_bridge/package.json",
        "ts_bridge/package-lock.json", "requirements-dev.lock", "requirements/oracle.lock",
    ])
    parity_source_paths = select_tracked_regular(tracked_entries, source_root, exact=[
        "tests/parity/canonical.py",
        "tests/parity/cases.py",
        "tests/parity/python_public_oracle.py",
        "tests/parity/public_operation_cases.py",
    ])
    harness_adapter_paths = select_tracked_regular(tracked_entries, source_root, exact=[
        "tests/test_oracle_harness.py",
        "tests/test_oracle_manifest.py",
        "tests/test_public_operation_oracle_harness.py",
        "tests/test_public_operation_oracle_manifest.py",
    ])
    corpus_paths = select_tracked_regular(tracked_entries, source_root, prefixes=[
        "tests/parity/corpora/", "tests/parity/fixtures/",
    ])
    generator_paths = select_tracked_regular(tracked_entries, source_root, exact=[
        "tools/oracle_snapshot.py",
        "tools/oracle_environment.py",
        "tools/public_operation_oracle.py",
    ])
    bound_paths = bound_path_manifest(
        product_paths
        + parity_source_paths
        + harness_adapter_paths
        + corpus_paths
        + generator_paths,
        root=source_root,
    )
    environment = execution["environment"]
    manifest = {
        "format_version": 3,
        "oracle": {
            "source_commit": oracle_commit,
            "package_version": execution["package_version"],
            "engine_version": execution["engine_version"],
            "schema_version": execution["schema_version"],
            "generator_version": GENERATOR_VERSION,
            "tracked_commit_tree": tracked_commit_tree_identity(tracked_entries),
            "bound_paths": bound_paths,
            "environment": environment,
            "executed_modules": execution["executed_modules"],
            "product_source_tree_sha256": tree_sha256(product_paths, root=source_root),
            "parity_source_tree_sha256": tree_sha256(
                parity_source_paths, root=source_root
            ),
            "harness_adapter_tree_sha256": tree_sha256(
                harness_adapter_paths, root=source_root
            ),
            "corpus_tree_sha256": tree_sha256(corpus_paths, root=source_root),
            "generator_tree_sha256": tree_sha256(generator_paths, root=source_root),
        },
        "goldens": {
            engine_output.name: {
                "sha256": hashlib.sha256(engine_bytes).hexdigest(),
            },
            store_output.name: {
                "sha256": hashlib.sha256(store_bytes).hexdigest(),
            },
        },
        "intentional_differences": [],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(canonical_json(manifest))
    fsync_tree_and_atomic_publish(staging_root, output_root)


def verify_oracle(repo_root: Path) -> int:
    manifest_path = repo_root / "tests/fixtures/oracle-manifest.json"
    if not manifest_path.is_file():
        return 1
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format_version") != 3:
            return 1
        recomputed = collect_bound_inputs(repo_root, manifest["oracle"]["source_commit"])
        current = collect_current_bound_inputs(repo_root)
        oracle = manifest["oracle"]
        for field in (
            "product_source_tree_sha256",
            "parity_source_tree_sha256",
            "harness_adapter_tree_sha256",
            "corpus_tree_sha256",
            "generator_tree_sha256",
        ):
            if oracle[field] != recomputed[field]:
                return 1
            if oracle[field] != current[field]:
                return 1
        for field in (
            "tracked_commit_tree",
            "bound_paths",
            "environment",
            "executed_modules",
        ):
            if oracle[field] != recomputed[field]:
                return 1
        if not current["bound_paths_clean"] or current["bound_paths"] != oracle["bound_paths"]:
            return 1
        if (
            oracle["package_version"] != current["package_version"]
            or oracle["engine_version"] != current["engine_version"]
            or oracle["schema_version"] != current["schema_version"]
            or oracle["generator_version"] != current["generator_version"]
        ):
            return 1
        if not evidence_commit_has_source_parent(
            repo_root, manifest_path, oracle["source_commit"]
        ):
            return 1
        if set(manifest["goldens"]) != {"python-engine-v1.json", "python-store-v1.json"}:
            return 1
        for name, entry in manifest["goldens"].items():
            path = repo_root / "tests/parity/golden" / name
            if not path.is_file():
                return 1
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                return 1
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
        return 1
    return 0
~~~

`materialize_tracked_regular_commit` reads the declared commit with `git ls-tree -rz --full-tree` plus `git cat-file --batch`, accepts only regular blob modes 100644/100755, rejects symlinks, submodules, duplicate/case-colliding paths, traversal, reparse points, and any extra live-worktree/ignored file, and materializes into a newly created owner-only no-link temporary root. All selectors operate only on that immutable tracked-entry table; there is no `rglob` over the live checkout. `bound_path_manifest` emits the exact sorted repository-relative path, mode, size, and SHA-256 row for the union of every product/parity/harness/corpus/generator input; the verifier reconstructs that historical closure and requires the live current closure to equal it byte-for-byte. `collect_current_bound_inputs` snapshots those current paths into a second owner-only materialization and derives versions through the same fresh `python -I` child, never through already-imported verifier modules. `requirements/oracle.lock` is hash-locked for the Python oracle environment; `tools/oracle_environment.py` verifies the actual executable SHA-256, implementation/version/build/platform/machine, full resolved distribution name/version/file closure, and every lock/toolchain digest.

`run_materialized_oracle_child` always starts a fresh sanitized interpreter with `-I` and executes the materialized commit's own `tools/oracle_snapshot.py --child` entry; the parent is only a commit-materializer/output validator and never calls an already-imported live `engine`, `storage`, `_version`, generator, or case module. Child cwd/import roots contain only the materialized commit and its hash-locked environment, user site/config/environment injection is disabled, and it refuses any executed CodeSextant/oracle module whose resolved path is outside that root. The child returns canonical snapshots plus package/engine/schema versions, environment closure, and every executed module—including generator/cases/canonicalizer/product/storage—repository-relative path/SHA-256; manifest format 3 binds them. A deterministic barrier mutates the live checkout after materialization and proves output/module hashes are unchanged. These facts ensure a clean git status alone cannot mask interpreter, dependency, or live-import drift. `evidence_commit_has_source_parent` resolves the most recent commit touching oracle-manifest.json, requires its first parent to equal oracle.source_commit, and requires that evidence commit to change only oracle-manifest.json and the named golden files.

`prepare_new_output_staging` requires the requested output root not to exist, resolves its existing parent without links/reparse points, rejects the repository itself, any ancestor/descendant of the repository, junction/symlink aliases, and nonempty/precreated roots, then creates an owner-only sibling staging directory. Generation writes only there, fsyncs files/directories, and atomically publishes the complete tree to the requested root. CI, partial writes, link swaps, disk-full, output `.`/repo/nested-repo, and caller-controlled redirection all fail without modifying checkout or leaving a partial final output. Tests cover every rejection and cleanup path.

Import hashlib, json, os, subprocess, sys, tempfile, Path, _version, storage, canonical_json, tree_sha256, run_engine_snapshot, and run_store_snapshot. One command/parser/API contract is the SSOT: `write_oracle(repo_root, oracle_commit, output_root)`, `verify_oracle(repo_root)`, and `verify_output_root(repo_root, output_root, expected_source_commit, precommit)`. The CLI exposes exactly three mutually exclusive modes using those same functions: `--write --oracle-commit COMMIT --output-root NEW_ROOT`; `--verify`; and `--verify-output-root ROOT --expected-source-commit COMMIT [--precommit]`. Parser-contract tests call each function and exact argv form, reject undocumented/mixed flags, and assert no alternate manifest/engine/store path signature exists. `--verify` fully recomputes tracked commit inputs, environment closure, source/harness/corpus/generator hashes, versions, golden hashes, and source/evidence commit relationship. `--verify-output-root` performs the same checks against generated/copy-staged bytes; `--precommit` defers only the evidence-commit-parent assertion. Invoking no mode exits 2 without changing files.

- [ ] **Step 7: Add the manifest validator before evidence exists**

Create tests/test_oracle_manifest.py with two explicit states. Before the initial freeze, it passes only when oracle-manifest.json, python-engine-v1.json, and python-store-v1.json are all absent; any partial set fails. Once all three exist, it requires format_version 3 and exact-key equality at every manifest object; the exact tracked regular-file source-commit closure; freshly recomputed hash-locked interpreter/platform/resolved dependency closure and executed-module paths/hashes; live package/engine/schema/generator versions from the fresh materialized child; resolvable oracle.source_commit; exact recomputation of product source, parity source, harness/adapter, corpus, and generator tree hashes; nonempty representative symbols/refs/fingerprints/fingerprint_index/comments before removal and empty associated tables after removal; golden hashes; the latest evidence commit's first-parent relationship to oracle.source_commit; an evidence-only changed-path set; and no private absolute path. It also computes the same bound-path closure from current HEAD, rejects staged/unstaged/untracked changes under those exact paths/prefixes, and requires current bound path set+hashes equal the manifest while allowing unrelated later Rust/docs commits. Table-driven tamper tests alter/remove/add each `tracked_commit_tree`, `environment`, `executed_modules`, bound-path, version, and golden field and require failure. This lets the source/tooling commit stay green while ensuring Task 5 can commit only generated evidence.

- [ ] **Step 8: Verify the harness without creating checked-in goldens**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_oracle_harness.py -q
~~~

Expected: all harness tests PASS.

- [ ] **Step 9: Commit the generator, corpus, and validator**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('requirements/oracle.lock','tests/parity/__init__.py','tests/parity/canonical.py','tests/parity/cases.py','tests/parity/corpora/python_core/app.py','tests/parity/corpora/python_core/service.py','tests/parity/corpora/python_core/models.py','tests/parity/corpora/python_core/cases/render_case.py','tools/oracle_environment.py','tools/oracle_snapshot.py','tests/test_oracle_harness.py','tests/test_oracle_manifest.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'test: add immutable Python oracle generator'
~~~

Do not generate or stage manifest/golden files in this commit.

---

### Task 5: Freeze the Python oracle in a separate commit

**Files:**
- Create: tests/fixtures/oracle-manifest.json
- Create: tests/parity/golden/python-engine-v1.json
- Create: tests/parity/golden/python-store-v1.json

**Interfaces:**
- Consumes: clean Task 4 commit, codesextant._version, storage.SCHEMA_VERSION, canonical source/corpus/golden hashing.
- Produces: format_version 3 manifest with complete tracked-commit/environment closure hashes, source/evidence commit relationship, and golden hashes.

- [ ] **Step 1: Observe the missing checked-in oracle from a clean commit**

~~~powershell
C:\Python311\python.exe tools/oracle_snapshot.py --verify
~~~

Expected: exit 1 because the manifest and golden JSON files do not exist. The worktree remains clean.

- [ ] **Step 2: Generate twice in independent output roots**

~~~powershell
if (git status --porcelain) { throw "oracle source commit is dirty" }
$oracleCommit = git rev-parse HEAD
$runA = Join-Path 'C:\Temp' ("codesextant-oracle-a-" + [guid]::NewGuid())
$runB = Join-Path 'C:\Temp' ("codesextant-oracle-b-" + [guid]::NewGuid())
try {
    C:\Python311\python.exe tools/oracle_snapshot.py --oracle-commit $oracleCommit --write --output-root $runA
    C:\Python311\python.exe tools/oracle_snapshot.py --oracle-commit $oracleCommit --write --output-root $runB
    git diff --no-index --exit-code -- $runA $runB
    if ($LASTEXITCODE -ne 0) { throw "independent oracle outputs differ" }
    New-Item -ItemType Directory -Force tests\fixtures,tests\parity\golden | Out-Null
    Copy-Item -LiteralPath (Join-Path $runA 'tests\fixtures\oracle-manifest.json') -Destination tests\fixtures\oracle-manifest.json
    Copy-Item -LiteralPath (Join-Path $runA 'tests\parity\golden\python-engine-v1.json') -Destination tests\parity\golden\python-engine-v1.json
    Copy-Item -LiteralPath (Join-Path $runA 'tests\parity\golden\python-store-v1.json') -Destination tests\parity\golden\python-store-v1.json
} finally {
    Remove-Item -LiteralPath $runA,$runB -Recurse -Force -ErrorAction SilentlyContinue
}
~~~

Each invocation creates independent engine/store homes internally. The generator emits actual commit and SHA-256 values; no descriptive digest text is written. The byte-for-byte directory comparison must pass before any evidence is copied into the checkout.

- [ ] **Step 3: Validate copied bytes before commit**

~~~powershell
C:\Python311\python.exe tools/oracle_snapshot.py --verify-output-root . --expected-source-commit $oracleCommit --precommit
C:\Python311\python.exe -m pytest tests/test_oracle_harness.py -q
~~~

Expected: complete bound-input, version, corpus, generator, golden, and privacy validation passes. --precommit checks source_commit equals HEAD and intentionally defers only the evidence-commit-parent assertion.

- [ ] **Step 4: Commit only the frozen evidence**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('tests/fixtures/oracle-manifest.json','tests/parity/golden/python-engine-v1.json','tests/parity/golden/python-store-v1.json')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'test: freeze Python oracle manifest and goldens'
~~~

- [ ] **Step 5: Verify the committed source/evidence relationship**

~~~powershell
C:\Python311\python.exe tools/oracle_snapshot.py --verify
C:\Python311\python.exe -m pytest tests/test_oracle_manifest.py tests/test_oracle_harness.py -q
~~~

Expected: both commands pass; the latest manifest evidence commit has first parent $oracleCommit and changes only the three evidence files.

---

### Task 6: Establish the Rust workspace and core wire contract

**Files:**
- Create: Cargo.toml
- Generate: Cargo.lock
- Create: rust-toolchain.toml
- Create: crates/codesextant-core/Cargo.toml
- Create: crates/codesextant-core/src/lib.rs
- Create: crates/codesextant-core/src/model.rs
- Create: crates/codesextant-core/src/error.rs
- Create: crates/codesextant-core/src/identity.rs
- Generate: crates/codesextant-core/src/generated/product_version.rs
- Create: tools/project_identity_vectors.py
- Test: crates/codesextant-core/tests/wire_contract.rs
- Test: crates/codesextant-core/tests/identity.rs
- Test: tests/test_project_identity_vectors.py

**Interfaces:**
- Consumes: Python snake_case wire fields and the legacy wire `project_key = SHA-1(normalized absolute repository path)` compatibility locator.
- Produces: Confidence, EvidenceLocation, SymbolRecord, RefEdge, RepositoryIdentity with legacy project_key plus strong storage_id, normalize_repo_path(), and repository_identity().

- [ ] **Step 1: Create the failing integration tests**

wire_contract.rs:

~~~rust
use codesextant_core::{Confidence, RefEdge, SymbolRecord};
use serde_json::json;

#[test]
fn python_wire_shape_is_stable() {
    let symbol = SymbolRecord {
        path: "$CORPUS/service.py".into(),
        kind: "function".into(),
        name: "render".into(),
        line: 7,
        end_line: 8,
        scope: String::new(),
    };
    assert_eq!(
        serde_json::to_value(symbol).unwrap(),
        json!({
            "path": "$CORPUS/service.py",
            "kind": "function",
            "name": "render",
            "line": 7,
            "end_line": 8,
            "scope": ""
        })
    );
    assert_eq!(
        serde_json::to_value(Confidence::High).unwrap(),
        json!("high")
    );
}
~~~

`tools/project_identity_vectors.py` is the executable Python 3.11 authority for `os.path.normcase(os.path.abspath(path))`. Given an explicit cwd and JSON input paths, it emits UTF-8 canonical JSON containing input, Python normalized string, its exact UTF-8 bytes as hex, and SHA-1 project key. `identity.rs` invokes that authority and directly asserts Rust normalized UTF-8 bytes and legacy key equal Python for a closed vector matrix: relative and absolute paths; empty/`.`; `repo/.`; `repo/sub/..`; duplicate separators; trailing separators; non-ASCII segments; and, on Windows, forward/back slashes, mixed case, drive-rooted, drive-relative, UNC forms, U+0130, Greek sigma variants, accented characters, and separator/case combinations. Windows normalization uses `LCMapStringEx` invariant lowercase behavior through the exact `Win32_Globalization` authority rather than Rust Unicode lowercase. It also asserts `storage_id = SHA-256("codesextant-project-storage-v1\0" || normalized_utf8_bytes)` against independent vectors. On POSIX it covers the implementation-defined double-leading-slash case and proves case is preserved. The test must not replace, redact, or scrub `project_key` or `storage_id`. Store tests create a legacy Python-keyed DB, open it through each equivalent Rust spelling, and prove the same validated row is used/migrated. A test-only legacy hasher injects a collision between two different normalized roots and proves neither root can read, migrate, overwrite, or alias the other's DB; mismatch is `PROJECT_ID_COLLISION` with a byte-identical directory. Any future identity difference requires an explicit alias migration test; silent divergence is forbidden.

- [ ] **Step 2: Run the tests before the workspace exists**

~~~powershell
cargo test --locked -p codesextant-core
~~~

Expected: FAIL because Cargo.toml and the codesextant-core package do not exist.

- [ ] **Step 3: Create the pinned workspace**

rust-toolchain.toml:

~~~toml
[toolchain]
channel = "1.96.0"
components = ["rustfmt", "clippy"]
profile = "minimal"
~~~

Root Cargo.toml:

~~~toml
[workspace]
members = ["crates/codesextant-core"]
resolver = "3"

[workspace.package]
version = "0.1.0" # internal Rust ABI/package version, not the product version
edition = "2024"
rust-version = "1.96"
license = "Apache-2.0"
publish = false

[workspace.dependencies]
serde = { version = "=1.0.229", features = ["derive"] }
serde_json = "=1.0.151"
sha1 = "=0.11.0"
sha2 = { version = "=0.10.9", default-features = false, features = ["std"] }
thiserror = "=2.0.19"
tempfile = "=3.27.0"
rusqlite = { version = "=0.40.1", default-features = false, features = ["bundled"] }
windows-sys = { version = "=0.61.2", default-features = false, features = ["Win32_Foundation", "Win32_Globalization", "Win32_Security", "Win32_Security_Authorization", "Win32_Storage_FileSystem", "Win32_System_JobObjects", "Win32_System_Memory", "Win32_System_SystemInformation", "Win32_System_Threading"] }
~~~

Task 7 changes `members` to `["crates/codesextant-core", "crates/codesextant-store"]` when the store manifest exists. The G2/G3 contract plan later expands the same authority to the final nine-package workspace.

The root `windows-sys` row is the single workspace version/feature authority. `codesextant-core/Cargo.toml` consumes it only under `[target.'cfg(windows)'.dependencies]` with `windows-sys.workspace = true` for Python-compatible Windows path expansion; it does not repeat a version or feature list. Later daemon DACL/process work consumes the same authority in its own Windows target section. A metadata test rejects any duplicate version, crate-local feature drift, or non-owning direct dependency.

Generate the first lockfile only after the root and core manifests are complete, then prove the locked graph is usable before any green build:

~~~powershell
cargo generate-lockfile
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath Cargo.lock -PathType Leaf)) { throw 'controlled Cargo.lock generation failed' }
$lockStatus = @(git status --short -- Cargo.lock)
if ($lockStatus.Count -ne 1) { throw "Cargo.lock was not the sole generated lock artifact: $($lockStatus -join '; ')" }
cargo metadata --locked --format-version 1 --no-deps | Out-Null
~~~

Expected: `Cargo.lock` is newly generated from the exact `=` pins, metadata exits 0 without modifying it, and review of the complete lockfile shows no unrequested package or duplicate `windows-sys` authority. Every later manifest-changing task repeats this same controlled generation/review before its first `--locked` green command.

Immediately after creating the root manifest/core module, generate and verify the Rust product-version constant from Python. The generated module contains only `pub const PRODUCT_VERSION: &str = "0.16.0";`, is re-exported by codesextant-core, and is the only version source permitted for product-facing Rust output:

~~~powershell
C:\Python311\python.exe tools/sync_version.py project-rust
C:\Python311\python.exe tools/sync_version.py --check --phase foundation
~~~

Expected: `codesextant_core::PRODUCT_VERSION` is exactly 0.16.0 and the tool proves it was generated from `codesextant/_version.py`; Cargo's 0.1.0 workspace/package version remains an internal ABI version and is never exposed by product `--version`, component manifests, installers, artifact manifests, tags, or ReleaseSubject.

- [ ] **Step 4: Implement focused domain types**

model.rs:

~~~rust
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Confidence {
    High,
    Low,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct EvidenceLocation {
    pub path: String,
    pub line: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub column: Option<u32>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct SymbolRecord {
    pub path: String,
    pub kind: String,
    pub name: String,
    pub line: u32,
    pub end_line: u32,
    pub scope: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct RefEdge {
    pub src_path: String,
    pub src_line: u32,
    pub symbol_name: String,
    pub def_path: Option<String>,
    pub def_line: Option<u32>,
    pub confidence: Confidence,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resolver: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub evidence: Option<EvidenceLocation>,
}
~~~

identity.rs exports the public shape below, but the normalizer implementation is a byte-for-byte compatibility port of the Python 3.11 authority rather than a filesystem canonicalizer:

~~~rust
use std::path::{Path, PathBuf};

use sha1::{Digest as Sha1Digest, Sha1};
use sha2::{Digest as Sha2Digest, Sha256};

use crate::CoreError;

pub struct RepositoryIdentity {
    pub canonical_root: PathBuf,
    pub project_key: String,
    pub storage_id: String,
}

pub fn normalize_repo_path(path: &Path) -> Result<String, CoreError> {
    normalize_repo_path_from(path, &std::env::current_dir()?)
}

pub fn normalize_repo_path_from(path: &Path, cwd: &Path) -> Result<String, CoreError> {
    // Lexically match Python 3.11 os.path.abspath(path) followed by normcase().
    // Collapse '.'/'..' and duplicate/trailing separators exactly as Python does;
    // do not resolve symlinks and do not trim Windows trailing dots or spaces.
    // Windows uses GetFullPathNameW-compatible drive/UNC resolution, then '\\'
    // separators and Python-compatible Unicode lowercase. POSIX normcase is a no-op.
    python_311_compatible_normalize(path, cwd)
}

pub fn repository_identity(path: &Path) -> Result<RepositoryIdentity, CoreError> {
    let normalized = normalize_repo_path(path)?;
    let project_key = format!(
        "{:x}",
        <Sha1 as Sha1Digest>::digest(normalized.as_bytes()),
    );
    let storage_id = format!(
        "{:x}",
        <Sha256 as Sha2Digest>::digest(
            [b"codesextant-project-storage-v1\0".as_slice(), normalized.as_bytes()].concat()
        ),
    );
    Ok(RepositoryIdentity {
        canonical_root: PathBuf::from(normalized),
        project_key,
        storage_id,
    })
}
~~~

`std::path::absolute()` alone is explicitly forbidden here because it retains lexical `..` on POSIX; manual trimming of Windows dots/spaces is also forbidden because Python `normcase(abspath())` does neither. Non-UTF-8 input remains fail-closed. The Python-vector test is the acceptance oracle for implementation details, including platform path corner cases and Unicode lowering. CI sets `CODESEXTANT_TEST_PYTHON` to the locked Python 3.11 executable before `cargo test`; the test refuses to skip if it is absent.

error.rs:

~~~rust
use std::path::PathBuf;

use thiserror::Error;

#[derive(Debug, Error)]
pub enum CoreError {
    #[error("repository path is not valid UTF-8: {0:?}")]
    NonUtf8Path(PathBuf),
    #[error("cannot make repository path absolute: {0}")]
    Io(#[from] std::io::Error),
}
~~~

- [ ] **Step 5: Re-export the public core contract**

lib.rs re-exports the generated product version alongside the domain types and identity functions:

~~~rust
mod generated {
    pub mod product_version;
}

pub use generated::product_version::PRODUCT_VERSION;
~~~

The generated file is a checked projection of Python, never hand-edited, and no product-facing code may use `env!("CARGO_PKG_VERSION")`. Continue with the remaining public re-exports:

~~~rust
mod error;
mod identity;
mod model;

pub use error::CoreError;
pub use identity::{RepositoryIdentity, normalize_repo_path, repository_identity};
pub use model::{Confidence, EvidenceLocation, RefEdge, SymbolRecord};
~~~

- [ ] **Step 6: Format, lint, test, and commit**

~~~powershell
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked -p codesextant-core
. .\tools\exact_task_commit.ps1
$expectedStaged = @('Cargo.toml','Cargo.lock','rust-toolchain.toml','crates/codesextant-core/Cargo.toml','crates/codesextant-core/src/lib.rs','crates/codesextant-core/src/model.rs','crates/codesextant-core/src/error.rs','crates/codesextant-core/src/identity.rs','crates/codesextant-core/tests/wire_contract.rs','crates/codesextant-core/tests/identity.rs','tools/project_identity_vectors.py','tests/test_project_identity_vectors.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat: establish Rust core domain contract'
~~~

---

### Task 7: Add the versioned Rust graph-store boundary

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Create: crates/codesextant-store/Cargo.toml
- Create: crates/codesextant-store/src/lib.rs
- Create: crates/codesextant-store/src/config.rs
- Create: crates/codesextant-store/src/error.rs
- Create: crates/codesextant-store/src/state_root.rs
- Create: crates/codesextant-store/src/schema.rs
- Create: crates/codesextant-store/src/store.rs
- Create: crates/codesextant-store/tests/fixtures/schema-v3.sql
- Test: crates/codesextant-store/tests/schema_migration.rs
- Test: crates/codesextant-store/tests/readonly.rs
- Test: crates/codesextant-store/tests/concurrency.rs
- Test: crates/codesextant-store/tests/identity_collision.rs
- Test: crates/codesextant-store/tests/state_root_security.rs

**Interfaces:**
- Consumes: codesextant/schema_v4.sql and codesextant-core::RepositoryIdentity.
- Produces: validated unforgeable StateRoot capability, StoreConfig, StoreError, ProjectStore::open(), ProjectStore::open_readonly(), schema_version(), is_read_only(), db_file(), get_meta(), set_meta(), and close().

- [ ] **Step 1: Write failing schema/open tests**

Use this complete v3 migration test shape; schema-v3.sql contains the v3 schema with meta.schema_version = 3, one files row, one symbols row, and no idx_symbols_map:

~~~rust
use std::fs;

use codesextant_core::repository_identity;
use codesextant_store::{ProjectStore, StoreConfig, StoreError};
use rusqlite::Connection;
use tempfile::tempdir;

#[test]
fn v3_upgrades_to_v4_without_losing_rows() {
    let root = tempdir().unwrap();
    let home = tempdir().unwrap();
    let repo = root.path().join("repo");
    fs::create_dir(&repo).unwrap();
    let identity = repository_identity(&repo).unwrap();
    let db_file = home.path().join(format!("{}.db", identity.project_key));
    let connection = Connection::open(&db_file).unwrap();
    connection
        .execute_batch(include_str!("fixtures/schema-v3.sql"))
        .unwrap();
    drop(connection);

    let store = ProjectStore::open(&repo, &StoreConfig::for_home(home.path())).unwrap();
    assert_eq!(store.schema_version().unwrap(), 4);
    store.close().unwrap();

    let connection = Connection::open(db_file).unwrap();
    let rows: i64 = connection
        .query_row("SELECT COUNT(*) FROM symbols", [], |row| row.get(0))
        .unwrap();
    let index: String = connection
        .query_row(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_symbols_map'",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(rows, 1);
    assert_eq!(index, "idx_symbols_map");
}
~~~

Add v4_reopen_is_idempotent by calling ProjectStore::open(), close(), and open() again against the same home and asserting version 4 both times. Add future_schema_fails_closed by seeding meta.schema_version = 5 and matching StoreError::UnsupportedSchema { found: 5, supported: 4 }. Add a table-driven preflight matrix for missing/malformed/zero/one/two/future schema_version, a claimed v3/v4 database with missing/extra/wrong tables/columns/indexes, and a truly empty file defined as zero application objects. Before any pragma or migration, each existing database is opened with a no-create read-only probe, structurally validated against the exact supported schema, and snapshotted; malformed/corrupt/unsupported states fail with the declared stable error and byte-identical DB/directory with no journal/WAL/SHM. `readonly.rs` asserts that an existing checkpointed DB can be read, `Connection::is_readonly(DatabaseName::Main)` is true, an INSERT returns a rusqlite readonly error through the store API, a missing DB returns StoreError::DatabaseMissing without creating a file, and `is_read_only()` is true. It snapshots directory entries plus every file's bytes/hash, makes the DB and containing directory genuinely read-only using POSIX mode bits or a Windows ACL, then opens, queries, and closes the store and proves the snapshot is byte-identical with no new `-journal`, `-wal`, or `-shm` file. `identity_collision.rs` seeds strong and legacy-locator databases whose stored canonical-root bytes/key/storage-id disagree with the request, plus an injected two-root legacy SHA-1 collision, and requires `StoreError::ProjectIdCollision`/public `PROJECT_ID_COLLISION` without mutation. `concurrency.rs` starts BEGIN IMMEDIATE on a writable rusqlite connection, spawns a reader, requires the reader to finish within two seconds, and verifies it sees only the last committed row.

Build schema-v3.sql mechanically from codesextant/schema_v4.sql: copy the complete SQL body, remove only the CREATE INDEX idx_symbols_map statement, then append:

~~~sql
INSERT INTO meta(key,value) VALUES('schema_version','3');
INSERT INTO files(path,content_hash,indexed_at)
VALUES('$CORPUS/service.py','content-v1',1000.0);
INSERT INTO symbols(path,kind,name,line,end_line,scope)
VALUES('$CORPUS/service.py','function','render',10,11,'');
~~~

- [ ] **Step 2: Run the store tests before implementation**

~~~powershell
cargo test --locked -p codesextant-store --test schema_migration
~~~

Expected: FAIL because codesextant-store is not a workspace package.

- [ ] **Step 3: Add exact dependencies and the store configuration**

`state_root.rs` is the single prerequisite for every database, WAL/SHM, runtime, spill, analyzer-snapshot, token, and cache path. It creates or validates a real directory before any state access and returns an unforgeable `StateRoot` capability. POSIX requires every existing component to be opened no-follow, owned by the effective UID, and the root to be mode 0700 under a restrictive creation mask. Windows requires owner SID equal to the current user, a protected non-inherited DACL granting only that SID and required system authority, no unexpected/inherited ACE, and no reparse component. All descendants are created relative to validated handles, remain below the root, use owner-only permissions, and are revalidated at open/use time; SQLite DB, `-wal`, `-shm`, and temporary files are included. Existing insecure/precreated/link-swapped state fails closed without repair or permission mutation; repair is allowed only through a later explicit reviewed command. `doctor` calls this same validator.

`state_root_security.rs` creates permissive umasks/inherited Windows ACLs, hostile precreated directories/files, symlink/junction/reparse and swap races, WAL/SHM creation, and an other-user read probe where the runner supports it. It requires owner-only state for every created file, rejects insecure existing state before SQLite opens, and proves no outside path or bytes are touched.

crates/codesextant-store/Cargo.toml:

~~~toml
[package]
name = "codesextant-store"
version.workspace = true
edition.workspace = true
rust-version.workspace = true
license.workspace = true
publish.workspace = true

[dependencies]
codesextant-core = { path = "../codesextant-core" }
rusqlite.workspace = true
thiserror.workspace = true

[dev-dependencies]
tempfile.workspace = true
~~~

config.rs:

~~~rust
pub struct StoreConfig {
    pub home: PathBuf,
    pub busy_timeout: Duration,
    pub wal: bool,
    pub synchronous_normal: bool,
}

impl StoreConfig {
    pub fn for_home(home: impl Into<PathBuf>) -> Self {
        Self {
            home: home.into(),
            busy_timeout: Duration::from_millis(5_000),
            wal: true,
            synchronous_normal: true,
        }
    }

    pub fn from_env() -> Result<Self, StoreError>;
}
~~~

- [ ] **Step 4: Parse and apply the shared schema**

schema.rs:

~~~rust
const SCHEMA_SQL: &str =
    include_str!("../../../codesextant/schema_v4.sql");

pub fn bundled_schema_version() -> Result<u32, StoreError> {
    let first = SCHEMA_SQL.lines().next().ok_or(StoreError::InvalidSchemaHeader)?;
    first
        .strip_prefix("-- codesextant-schema-version: ")
        .ok_or(StoreError::InvalidSchemaHeader)?
        .parse()
        .map_err(|_| StoreError::InvalidSchemaHeader)
}
~~~

Before applying any mutable pragma/schema, perform a no-create read-only probe. A database is empty only when it has zero application objects; otherwise validate exact supported v3/v4 table, column, index, and meta structure before reading schema_version. Reject missing/malformed/0/1/2/future versions or structure/version disagreement without mutation. Only a validated v3 or truly empty newly created database may enter the writable configuration/migration transaction; execute the shared schema and set meta.schema_version to 4. The v3 fixture includes all v3 tables and the cognitive column but omits idx_symbols_map.

- [ ] **Step 5: Implement open/read-only behavior**

store.rs exports:

~~~rust
pub struct ProjectStore {
    connection: Connection,
    identity: RepositoryIdentity,
    db_file: PathBuf,
    read_only: bool,
}

impl ProjectStore {
    pub fn open(repo_root: &Path, config: &StoreConfig) -> Result<Self, StoreError>;
    pub fn open_readonly(
        repo_root: &Path,
        config: &StoreConfig,
    ) -> Result<Self, StoreError>;
    pub fn schema_version(&self) -> Result<u32, StoreError>;
    pub fn is_read_only(&self) -> bool;
    pub fn db_file(&self) -> &Path;
    pub fn get_meta(&self, key: &str) -> Result<Option<String>, StoreError>;
    pub fn set_meta(&mut self, key: &str, value: &str) -> Result<(), StoreError>;
    pub fn close(self) -> Result<(), StoreError>;
}
~~~

For rollback compatibility, the physical database filename remains the legacy `project_key` locator in this release; `storage_id` is the strong runtime/storage identity stored inside and validated on every open, never a second parallel filename. Every open first computes requested normalized-root bytes, legacy key, and strong storage ID, then performs a no-create read-only probe that proves stored `repo_path` bytes, `project_key`, and `storage_id` exactly match before any product-row read or writable pragma. Existing pre-storage-id databases may be claimed only after exact root/key validation and a writer-only, journaled metadata migration; no DB/WAL/SHM file is renamed or moved. Any mismatch/collision returns `ProjectIdCollision`/`PROJECT_ID_COLLISION`; it never reads product rows, migrates, creates, journals, or mutates the database. New databases use the legacy physical locator for previous-artifact compatibility but record all three identity fields in their first transaction. Upgrade/rollback tests index with the new binary, then open/read with the designated previous Python artifact and prove one shared state rather than split stores; a future filename migration requires a separate checkpoint/backup/fsync/crash-recovery design.

After identity and exact schema preflight succeeds, writable open sets busy_timeout, WAL when enabled, synchronous=NORMAL when enabled, and applies the allowed schema/migration. Unsupported/future/corrupt/identity-mismatched databases never receive `journal_mode`, `synchronous`, migration, or recovery writes. Read-only open first requires the selected DB file to exist, then calls `Connection::open_with_flags` with `OpenFlags::SQLITE_OPEN_READ_ONLY` rather than ever opening read-write/create; it verifies SQLite reports `DatabaseName::Main` read-only and only then applies `PRAGMA query_only=ON` as defense in depth. It never runs schema migration, WAL-mode changes, or any statement that can create/recover a journal. `readonly.rs` calls `set_meta()` and asserts the resulting `StoreError` wraps SQLite ReadOnly, and its protected-directory fixture proves open/query/close creates or changes no file.

- [ ] **Step 6: Run migration, readonly, and concurrency tests**

~~~powershell
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked -p codesextant-store --test schema_migration
cargo test --locked -p codesextant-store --test readonly
cargo test --locked -p codesextant-store --test concurrency
cargo test --locked -p codesextant-store --test identity_collision
cargo test --locked -p codesextant-store --test state_root_security
~~~

Expected: all tests PASS; no row loss and no future-schema downgrade.

- [ ] **Step 7: Commit the graph-store boundary**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-store/Cargo.toml','crates/codesextant-store/src/lib.rs','crates/codesextant-store/src/config.rs','crates/codesextant-store/src/error.rs','crates/codesextant-store/src/state_root.rs','crates/codesextant-store/src/schema.rs','crates/codesextant-store/src/store.rs','crates/codesextant-store/tests/fixtures/schema-v3.sql','crates/codesextant-store/tests/schema_migration.rs','crates/codesextant-store/tests/readonly.rs','crates/codesextant-store/tests/concurrency.rs','crates/codesextant-store/tests/identity_collision.rs','crates/codesextant-store/tests/state_root_security.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat: add versioned Rust graph store'
~~~

---

### Task 8: Prove Rust store CRUD parity against the Python oracle

**Files:**
- Modify: Cargo.toml
- Modify: Cargo.lock
- Modify: crates/codesextant-core/Cargo.toml
- Modify: crates/codesextant-core/src/model.rs
- Modify: crates/codesextant-core/src/lib.rs
- Modify: crates/codesextant-store/Cargo.toml
- Modify: crates/codesextant-store/src/store.rs
- Test: crates/codesextant-store/tests/python_oracle.rs
- Test: crates/codesextant-store/tests/crud_atomicity.rs

**Interfaces:**
- Consumes: tests/parity/golden/python-store-v1.json and the store/open boundary from Task 7.
- Produces: FileIndexBatch, FingerprintRecord, WinnowEntry, CommentRecord, ProjectStats, needs_reindex(), replace_file_index(), replace_refs_for(), remove_file(), get_symbols(), get_fingerprints(), get_winnow_index(), get_comments(), all_refs(), and stats().

**Dependency closure:** Root Cargo.toml/Cargo.lock remain the only version authority. `codesextant-store` adds `serde_json.workspace = true` alongside `tempfile.workspace = true` under dev-dependencies because its integration tests import both directly. `codesextant-core` declares every crate it imports directly and declares `serde_json.workspace = true` plus `tempfile.workspace = true` for tests; transitive availability is never relied on. Workspace metadata tests reject missing direct declarations or crate-local version/feature drift.

- [ ] **Step 1: Write the failing oracle replay test**

python_oracle.rs uses this top-level test:

~~~rust
#[test]
fn rust_store_matches_the_frozen_python_transcript() {
    let expected: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/parity/golden/python-store-v1.json"
    ))
    .unwrap();
    let root = tempfile::tempdir().unwrap();
    let home = tempfile::tempdir().unwrap();
    let repo = root.path().join("python_core");
    std::fs::create_dir(&repo).unwrap();
    let source = repo.join("service.py");
    std::fs::write(&source, "def format_message(name):\n    return name\n").unwrap();
    let actual = replay_store_transcript(&repo, home.path(), &source).unwrap();
    assert_eq!(actual, expected);
}
~~~

Implement the replay helper with the same literal records:

~~~rust
fn replay_store_transcript(
    repo: &Path,
    home: &Path,
    source: &Path,
) -> Result<serde_json::Value, StoreError> {
    let source_text = source.to_str().unwrap().to_owned();
    let mut store = ProjectStore::open(repo, &StoreConfig::for_home(home))?;
    let batch = FileIndexBatch {
        path: source_text.clone(),
        content_hash: "content-v1".into(),
        indexed_at: 1000.0,
        symbols: vec![
            SymbolRecord {
                path: source_text.clone(),
                kind: "function".into(),
                name: "format_message".into(),
                line: 6,
                end_line: 7,
                scope: String::new(),
            },
            SymbolRecord {
                path: source_text.clone(),
                kind: "function".into(),
                name: "render".into(),
                line: 10,
                end_line: 11,
                scope: String::new(),
            },
        ],
        fingerprints: vec![FingerprintRecord {
            name: Some("format_message".into()),
            kind: Some("function".into()),
            line: Some(6),
            end_line: Some(7),
            scope: Some("模組".into()),
            shape_hash: Some("shape-v1".into()),
            raw_token_hash: None,
            call_hash: Some("call-v1".into()),
            node_count: Some(3),
            nstmts: Some(1),
            has_control_flow: false,
            cognitive: Some(0),
        }],
        winnow_index: vec![WinnowEntry { line: Some(6), fp_value: Some(i64::MAX - 1) }],
        comments: vec![CommentRecord {
            line: 5,
            end_line: 5,
            kind: "line".into(),
            is_doc: true,
            tag: Some("契約".into()),
            scope: "模組".into(),
            owner_line: Some(6),
            text: "UTF-8 註解".into(),
        }],
    };
    store.replace_file_index(&batch)?;
    store.replace_refs_for(
        &source_text,
        &[RefEdge {
            src_path: source_text.clone(),
            src_line: 11,
            symbol_name: "format_message".into(),
            def_path: Some(source_text.clone()),
            def_line: Some(6),
            confidence: Confidence::High,
            resolver: None,
            evidence: None,
        }],
    )?;
    let before = serde_json::json!({
        "needs_same": store.needs_reindex(&source_text, "content-v1")?,
        "needs_changed": store.needs_reindex(&source_text, "content-v2")?,
        "symbols": store.get_symbols(None)?,
        "fingerprints": store.get_fingerprints(&source_text)?,
        "winnow_index": store.get_winnow_index(&source_text)?,
        "comments": store.get_comments(&source_text)?,
        "refs": store.all_refs()?,
        "stats": store.stats()?,
    });
    store.remove_file(&source_text)?;
    let after = serde_json::json!({
        "symbols": store.get_symbols(None)?,
        "fingerprints": store.get_fingerprints(&source_text)?,
        "winnow_index": store.get_winnow_index(&source_text)?,
        "comments": store.get_comments(&source_text)?,
        "refs": store.all_refs()?,
        "stats": store.stats()?,
    });
    let project_key = store.stats()?.project_key;
    let python_identity = python_project_identity(
        std::env::var("CODESEXTANT_TEST_PYTHON")?,
        &repo,
    )?;
    assert_eq!(project_key.as_bytes(), python_identity.project_key.as_bytes());
    assert_eq!(
        repository_identity(&repo)?.canonical_root.to_string_lossy().as_bytes(),
        python_identity.normalized_utf8.as_bytes(),
    );
    let mut value = serde_json::json!({"before": before, "after": after});
    assert_and_remove_project_keys(&mut value, &project_key)?;
    scrub_portable_paths(
        &mut value,
        &repo.to_string_lossy().replace('\\', "/"),
        &home.to_string_lossy().replace('\\', "/"),
    );
    value["identity_checked"] = serde_json::Value::Bool(true);
    Ok(value)
}

fn scrub_portable_paths(value: &mut serde_json::Value, repo: &str, home: &str) {
    match value {
        serde_json::Value::Object(entries) => {
            entries.remove("elapsed_ms");
            entries.remove("indexed_at");
            entries.remove("last_indexed_at");
            assert!(!entries.contains_key("project_key"));
            for item in entries.values_mut() {
                scrub_portable_paths(item, repo, home);
            }
        }
        serde_json::Value::Array(items) => {
            for item in items {
                scrub_portable_paths(item, repo, home);
            }
        }
        serde_json::Value::String(text) => {
            let normalized = text.replace('\\', "/");
            *text = normalized
                .replace(repo, "$CORPUS")
                .replace(home, "$HOME");
        }
        _ => {}
    }
}
~~~

`assert_and_remove_project_keys` recursively requires every key field to equal the already byte-compared Python value before removing it from the machine-portable golden. It fails when no key is present or when any nested key differs. No path scrubber accepts a key argument or can mask identity drift.

Run:

~~~powershell
cargo test --locked -p codesextant-store --test python_oracle
~~~

Expected: compile FAIL because CRUD records and methods do not exist.

- [ ] **Step 2: Add the remaining store records**

Add these serializable records to codesextant-core:

~~~rust
pub struct FingerprintRecord {
    pub name: Option<String>,
    pub kind: Option<String>,
    pub line: Option<u32>,
    pub end_line: Option<u32>,
    pub scope: Option<String>,
    pub shape_hash: Option<String>,
    pub raw_token_hash: Option<String>,
    pub call_hash: Option<String>,
    pub node_count: Option<u32>,
    pub nstmts: Option<u32>,
    pub has_control_flow: bool,
    pub cognitive: Option<u32>,
}

pub struct CommentRecord {
    pub line: u32,
    pub end_line: u32,
    pub kind: String,
    pub is_doc: bool,
    pub tag: Option<String>,
    pub scope: String,
    pub owner_line: Option<u32>,
    pub text: String,
}

pub struct FileIndexBatch {
    pub path: String,
    pub content_hash: String,
    pub indexed_at: f64,
    pub symbols: Vec<SymbolRecord>,
    pub fingerprints: Vec<FingerprintRecord>,
    pub winnow_index: Vec<WinnowEntry>,
    pub comments: Vec<CommentRecord>,
}

pub struct WinnowEntry {
    pub line: Option<u32>,
    pub fp_value: Option<i64>,
}

pub struct ProjectStats {
    pub project_key: String,
    pub repo_path: String,
    pub db_file: String,
    pub indexed_files: u64,
    pub symbols: u64,
    pub refs: u64,
    pub fingerprints: u64,
    pub comments: u64,
    pub last_indexed_at: Option<f64>,
    pub schema_version: u32,
    pub indexed_git_sha: Option<String>,
}
~~~

- [ ] **Step 3: Implement the atomic CRUD contract**

Add:

~~~rust
pub fn needs_reindex(
    &self,
    path: &str,
    content_hash: &str,
) -> Result<bool, StoreError>;

pub fn replace_file_index(
    &mut self,
    batch: &FileIndexBatch,
) -> Result<(), StoreError>;

pub fn replace_refs_for(
    &mut self,
    src_path: &str,
    edges: &[RefEdge],
) -> Result<(), StoreError>;

pub fn remove_file(&mut self, path: &str) -> Result<(), StoreError>;

pub fn get_symbols(
    &self,
    file_path: Option<&str>,
) -> Result<Vec<SymbolRecord>, StoreError>;

pub fn all_refs(&self) -> Result<Vec<RefEdge>, StoreError>;
pub fn get_fingerprints(&self, path: &str) -> Result<Vec<FingerprintRecord>, StoreError>;
pub fn get_winnow_index(&self, path: &str) -> Result<Vec<WinnowEntry>, StoreError>;
pub fn get_comments(&self, path: &str) -> Result<Vec<CommentRecord>, StoreError>;
pub fn stats(&self) -> Result<ProjectStats, StoreError>;
~~~

The Python golden and Rust replay both insert representative nonempty symbols, refs, fingerprints, fingerprint_index, and comments, covering None/bool/int boundary/UTF-8 values, then round-trip, delete, reopen, and compare payloads plus stats. Empty vectors are forbidden in this parity case. replace_file_index uses one rusqlite transaction for files, symbols, fingerprints, fingerprint_index, and comments. Any insertion failure rolls back the entire batch. replace_refs_for is also one transaction. `remove_file` deletes the file and every associated symbols/refs/fingerprints/fingerprint_index/comments row in one transaction. `crud_atomicity.rs` injects failure at each delete/insert stage, reopens, and proves byte/row integrity with either the complete old or complete new state. Preserve Python ordering for every returned table; symbols use path,line and per-file line ordering with deterministic tie-breakers.

Because schema v4 has no resolver/evidence columns, replace_refs_for returns StoreError::UnsupportedProvenance when either optional field is Some; it never drops provenance silently. Add a test for this fail-closed behavior.

- [ ] **Step 4: Test atomic rollback as the approved reliability difference**

Seed a valid batch, close a separate rusqlite connection after installing this trigger, then submit a changed batch:

~~~sql
CREATE TRIGGER force_comment_abort
BEFORE INSERT ON comments
BEGIN
  SELECT RAISE(ABORT, 'forced parity rollback');
END;
~~~

Use store.db_file() to open the setup connection. The changed batch includes one valid CommentRecord, so the trigger aborts after file/symbol/fingerprint work has begun. Assert StoreError, then verify the original content hash and every original table count remain unchanged. This difference does not change successful wire output, so intentional_differences remains [].

- [ ] **Step 5: Run the parity and workspace suite**

~~~powershell
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked -p codesextant-store --test python_oracle
cargo test --locked -p codesextant-store --test crud_atomicity
cargo test --locked --workspace
~~~

Expected: exact Python transcript equality and all Rust tests PASS.

- [ ] **Step 6: Commit storage parity**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('Cargo.toml','Cargo.lock','crates/codesextant-core/Cargo.toml','crates/codesextant-core/src/model.rs','crates/codesextant-core/src/lib.rs','crates/codesextant-store/Cargo.toml','crates/codesextant-store/src/store.rs','crates/codesextant-store/tests/python_oracle.rs','crates/codesextant-store/tests/crud_atomicity.rs')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'feat: prove Rust store parity with Python oracle'
~~~

---

### Task 9: Add a machine-verifiable G1 gate

**Files:**
- Create: tools/verify_g0.py
- Create: tools/verify_g1.py
- Create: release/evidence/g0-workspace.schema.json
- Create: release/evidence/g1-foundation.schema.json
- Test: tests/test_g0_gate.py
- Test: tests/test_g1_gate.py

**Interfaces:**
- Consumes: workspace/version/architecture checks for G0; immutable oracle verifier, Python tests/lint, retained TS fixtures, Rust fmt/clippy/tests, and git cleanliness for G1; the final ReleaseSubject/public-export authorities supplied later by G5; and one inherited exclusive candidate handle supplied only by `tools/release_gate.py produce-and-seal`.
- Produces: `tools/verify_g0.py check|candidate` and `tools/verify_g1.py check|candidate`. Candidate mode emits one closed `gate-candidate` to the inherited handle and never knows or writes `release/evidence/g0-workspace.json` or `release/evidence/g1.json`; G5's authenticated generic sealer is the sole final writer.

- [ ] **Step 1: Write the failing command-contract test**

~~~python
from tools import verify_g0, verify_g1
from tools.verify_g0 import commands as g0_commands
from tools.verify_g1 import commands as g1_commands


def test_g1_gate_contains_every_required_external_check():
    joined = [" ".join(command) for command in g1_commands("C:/Python311/python.exe")]
    assert any("-m pytest" in command for command in joined)
    assert any("-m ruff check" in command for command in joined)
    assert any("npm --prefix ts test" in command for command in joined)
    assert any("npm --prefix ts run build" in command for command in joined)
    assert any("cargo fmt --all -- --check" in command for command in joined)
    assert any("cargo clippy --locked --workspace --all-targets -- -D warnings" in command
               for command in joined)
    assert any("cargo test --locked --workspace" in command for command in joined)
    assert any("git diff --check" in command for command in joined)
    assert any("git status --porcelain" in command for command in joined)


def test_g0_gate_contains_workspace_and_authority_checks():
    joined = [" ".join(command) for command in g0_commands("C:/Python311/python.exe")]
    assert any("test_version_ssot.py" in command for command in joined)
    assert any("test_architecture_authority.py" in command for command in joined)
    assert any("test_schema_resource.py" in command for command in joined)
    assert any("git diff --check" in command for command in joined)


def test_candidate_modes_have_closed_authenticated_launch_identities():
    assert verify_g0.PRODUCER_ID == "g0_workspace"
    assert verify_g0.LAUNCH_SPEC_ID == "g0_workspace"
    assert verify_g0.ENTRYPOINT_RELATIVE_PATH == "tools/verify_g0.py"
    assert verify_g1.PRODUCER_ID == "g1_foundation"
    assert verify_g1.LAUNCH_SPEC_ID == "g1_foundation"
    assert verify_g1.ENTRYPOINT_RELATIVE_PATH == "tools/verify_g1.py"


def test_g0_g1_candidates_put_domain_fields_under_typed_payload(valid_g0, valid_g1):
    assert validate_payload(valid_g0["payload"], "release/evidence/g0-workspace.schema.json")
    assert validate_payload(valid_g1["payload"], "release/evidence/g1-foundation.schema.json")
    assert set(valid_g0) == {"issued_at_utc", "reviewer", "tools", "artifacts", "checks", "status", "payload"}
    assert set(valid_g1) == {"issued_at_utc", "reviewer", "tools", "artifacts", "checks", "status", "payload"}
    for forbidden in ("gate", "subject_sha256", "producer_id", "launch_spec_id", "dependency_receipts", "material_digests", "sealed_by"):
        assert forbidden not in valid_g0 and forbidden not in valid_g1


def test_g0_candidate_requires_authoritative_export_and_controlled_inherited_handle(g0_cli, inherited_candidate_handle, tmp_path):
    missing = g0_cli.candidate_args(subject="release/evidence/release-subject.json")
    assert "--export-root" not in missing
    assert g0_cli.run(missing).returncode == 2

    result = g0_cli.run_candidate(
        subject="release/evidence/release-subject.json",
        export_root=tmp_path / "authoritative-export",
        inherited_handle=inherited_candidate_handle,
    )
    assert result.public_export_guard == "tools/public_export.py assert-authoritative-root"
    assert result.public_export_audit is True
    assert result.payload["export_commit"] == result.subject["export_commit"]
    assert result.payload["export_tree_sha256"] == result.subject["export_tree_sha256"]
    assert result.payload["allowlist_inventory_sha256"]


def test_candidate_cli_has_no_out_or_final_receipt_path(g0_cli, g1_cli, tmp_path):
    for cli in (g0_cli, g1_cli):
        assert cli.run(["candidate", "--out", str(tmp_path / "forged.json")]).returncode == 2
        assert cli.run(["candidate"]).returncode == 2
    assert not (tmp_path / "g0-workspace.json").exists()
    assert not (tmp_path / "g1.json").exists()


def test_candidate_is_written_once_only_to_inherited_exclusive_handle(g0_cli, inherited_candidate_handle):
    result = g0_cli.run_candidate(
        subject="release/evidence/release-subject.json",
        export_root="authoritative-export",
        inherited_handle=inherited_candidate_handle,
    )
    assert result.returncode == 0
    assert inherited_candidate_handle.write_count == 1
    assert inherited_candidate_handle.path_exposed_to_child is False
    assert inherited_candidate_handle.decoded_json["status"] == "pass"
~~~

- [ ] **Step 2: Run the test before creating the verifier**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_g0_gate.py tests/test_g1_gate.py -q
~~~

Expected: collection FAIL because tools.verify_g0 and tools.verify_g1 do not exist.

- [ ] **Step 3: Implement fail-fast command execution**

~~~python
from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone


def commands(python: str) -> list[list[str]]:
    return [
        [python, "tools/sync_version.py", "--check", "--phase", "foundation"],
        [python, "-m", "pytest", "tests/test_project_identity_vectors.py", "-q"],
        [python, "-m", "pytest", "tests/test_oracle_manifest.py", "-q"],
        [python, "-m", "pytest", "-q"],
        [python, "-m", "ruff", "check", "codesextant", "tests", "tools"],
        ["npm", "--prefix", "ts", "test"],
        ["npm", "--prefix", "ts", "run", "build"],
        ["cargo", "fmt", "--all", "--", "--check"],
        ["cargo", "clippy", "--locked", "--workspace", "--all-targets", "--", "-D", "warnings"],
        ["cargo", "test", "--locked", "--workspace"],
        ["git", "diff", "--check"],
        ["git", "status", "--porcelain"],
    ]


def run_checks(python: str) -> tuple[int, list[dict[str, object]]]:
    evidence: list[dict[str, object]] = []
    for command in commands(python):
        started = datetime.now(timezone.utc)
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            capture_output=True,
        )
        exit_code = completed.returncode
        if command[-2:] == ["status", "--porcelain"] and completed.stdout:
            exit_code = 1
        finished = datetime.now(timezone.utc)
        evidence.append({
            "argv": command,
            "exit_code": exit_code,
            "stdout_sha256": hashlib.sha256(
                completed.stdout.encode("utf-8")
            ).hexdigest(),
            "stderr_sha256": hashlib.sha256(
                completed.stderr.encode("utf-8")
            ).hexdigest(),
            "started_at_utc": started.isoformat().replace("+00:00", "Z"),
            "duration_ms": max(
                0, int((finished - started).total_seconds() * 1000)
            ),
        })
        if exit_code != 0:
            return exit_code, evidence
    return 0, evidence
~~~

tools/verify_g0.py uses the same run_checks shape with this exact command set:

~~~python
[
    [python, "tools/sync_version.py", "--check", "--phase", "foundation"],
    [python, "-m", "pytest", "tests/test_version_ssot.py", "-q"],
    [python, "-m", "pytest", "tests/test_architecture_authority.py", "-q"],
    [python, "-m", "pytest", "tests/test_schema_resource.py", "-q"],
    ["git", "merge-base", "--is-ancestor", "8bd0dc2", "HEAD"],
    ["git", "diff", "--check"],
    ["git", "status", "--porcelain"],
]
~~~

Both tools accept only `check` and `candidate`. `check` runs the command set and writes nothing. Before Cargo commands, the verifier sets `CODESEXTANT_TEST_PYTHON` in the child-only environment to the exact Python executable whose digest it records. `candidate` rejects `--out`, stdout transport, a path-valued sink, a dirty source tree, a failed child command, a missing/invalid ReleaseSubject, or a missing/non-inherited candidate handle. The handle number is received only through the launcher's closed child environment, is proven writable and inherited by this exact child, is opened once without path resolution, receives exactly one length-bounded JCS document, is flushed, and is never reopened. Tests construct the same controlled inherited handle in a fresh subprocess; ordinary unit tests cannot name a registry filename.

The candidate contains exactly `issued_at_utc`, `reviewer="automated-local-gate"`, tool identities, artifacts, checks, `status="pass"`, and the typed domain `payload`. It contains no gate, subject digest, producer/launch labels, dependency/material maps, or `sealed_by`; those are recomputed by G5's generic sealer. G0 candidate mode additionally requires `--export-root`, invokes `tools/public_export.py assert-authoritative-root` and `audit`, and binds the authoritative export closure. The final G5 launch-policy generator authenticates the canonical product-source entrypoint path and raw SHA-256, the digest-addressed `requirements/release.lock` Python path/version/digest, argv prefix `candidate`, producer/launch IDs above, and `candidate_transport=inherited_exclusive_handle`. Any entrypoint/runtime/argv/handle drift fails before child start. Missing later G5 tooling or runtime authority exits 2 without writing candidate bytes.

- [ ] **Step 4: Run focused verification**

~~~powershell
C:\Python311\python.exe -m pytest tests/test_g0_gate.py tests/test_g1_gate.py -q
~~~

Expected: PASS.

- [ ] **Step 5: Commit the verifier before running its clean-tree check**

~~~powershell
. .\tools\exact_task_commit.ps1
$expectedStaged = @('tools/verify_g0.py','tools/verify_g1.py','release/evidence/g0-workspace.schema.json','release/evidence/g1-foundation.schema.json','tests/test_g0_gate.py','tests/test_g1_gate.py')
Invoke-ExactTaskCommit -ExpectedPaths $expectedStaged -Message 'ci: enforce immutable oracle and Rust parity gate'
~~~

- [ ] **Step 6: Run the complete G1 gate from the clean commit**

~~~powershell
C:\Python311\python.exe tools/verify_g0.py check
C:\Python311\python.exe tools/verify_g1.py check
~~~

Expected: every child command exits 0 and the final lines are G0 PASS and G1 PASS.

## G0/G1 Final Receipt Runbook

This is a post-freeze evidence operation, not an implementation task or source commit. Do not run it during initial G1 development. Run it in the same G5 F5 session that owns the already-audited `$exportRoot`, after all source-changing G0-G5 tasks are committed, the final allowlist export/artifact manifest exists, and release/evidence/release-subject.json is frozen. G5 F5 tests must use these option names without aliases.

~~~powershell
if ($PSVersionTable.PSVersion -lt [Version]'7.4') { throw 'pwsh 7.4 or newer is required for fail-fast native command handling' }
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
if (-not (Test-Path variable:exportRoot) -or -not (Test-Path -LiteralPath $exportRoot -PathType Container)) { throw 'G5 F5 authoritative exportRoot is required' }
$releasePython = & C:\Python311\python.exe tools/bootstrap_release_python.py ensure --lock requirements/release.lock --print-python
if ($LASTEXITCODE -ne 0) { throw 'locked release Python bootstrap failed' }
$gateContext = @('--subject','release/evidence/release-subject.json','--product-source-root',(Get-Location).Path,'--public-export-root',$exportRoot,'--evidence-dir',(Join-Path (Get-Location).Path 'release\evidence'),'--registry',(Join-Path (Get-Location).Path 'release\evidence\receipt-registry.json'),'--launch-policy',(Join-Path (Get-Location).Path 'release\evidence\producer-launch-policy.json'))
& $releasePython tools/release_gate.py produce-and-seal --gate G0 --receipt g0-workspace.json @gateContext -- --export-root $exportRoot
if ($LASTEXITCODE -ne 0) { throw 'authenticated G0 candidate producer/sealer failed' }
& $releasePython tools/release_gate.py produce-and-seal --gate G1 --receipt g1.json @gateContext
if ($LASTEXITCODE -ne 0) { throw 'authenticated G1 candidate producer/sealer failed' }
& $releasePython tools/release_gate.py check --gate G0 --subject release/evidence/release-subject.json --evidence-dir release/evidence --product-source-root (Get-Location).Path --public-export-root $exportRoot
& $releasePython tools/release_gate.py check --gate G1 --subject release/evidence/release-subject.json --evidence-dir release/evidence --product-source-root (Get-Location).Path --public-export-root $exportRoot
~~~

Expected: all commands exit 0; both receipts have status pass and the same subject_sha256 as the final frozen subject. Any later source/export/artifact change invalidates both receipts and requires a full rerun.

## G1 Completion Evidence

Before claiming G1 complete, record these exact outputs in the execution report without changing the oracle:

~~~powershell
git status --porcelain
git log --oneline 8bd0dc2..HEAD
C:\Python311\python.exe -c "from codesextant import __version__,ENGINE_VERSION; from codesextant.storage import SCHEMA_VERSION; print(__version__,ENGINE_VERSION,SCHEMA_VERSION)"
rustc --version
cargo --version
C:\Python311\python.exe tools/verify_g0.py check
C:\Python311\python.exe tools/verify_g1.py check
~~~

Required development evidence: clean status; focused commits corresponding to Tasks 1-9; product 0.16.0, engine 1, schema 4; Rust 1.96.0; final G0 PASS and G1 PASS.

Required final-freeze evidence, create-new written later only by G5 `release_gate.py produce-and-seal`: release/evidence/g0-workspace.json and release/evidence/g1.json, both status pass and both bound to the same final ReleaseSubject digest. The Task 9 domain producers never receive those paths. This does not authorize publication or submission.
