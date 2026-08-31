"""A file the repository points at has to be in the repository.

This exists because it happened. ``.gitignore`` carries ``docs/*`` with a deliberate
allowlist under it -- "internal planning docs stay on disk but are not published" -- and
three files were written into ``docs/`` over a session without being added to that list.
Every ``git add -A`` reported success and silently dropped them. On disk the tree was
complete and every link resolved; in the repository, ``HANDOFF.md`` named a roadmap that
was not there, ``experiments/README.md`` linked a write-up that was not there, and
``release.yml`` tested for release notes it would never find and would have published
ninety-three commits of generated changelog instead.

Nothing failed. That is the whole problem, and it is the failure this project is about:
a guard set for a good reason, forgotten, and then quietly costing more than it saved.
The fix is not to remember the allowlist. It is this test.

The rule is one sentence: **if a tracked file names a path under ``docs/``, that path is
tracked too.** Adding a published doc means adding one ``!`` line to ``.gitignore``;
forgetting to means a red test rather than a broken link discovered by a reader.
"""
from __future__ import annotations

import os
import re
import subprocess

import pytest

try:  # 3.11+ has it in the stdlib; 3.10 is the floor and `tomli` is declared for it.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on the 3.10 CI job
    import tomli as tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where a reference to a doc realistically appears: prose that links it, and the release
# workflow that reads one. Widening this to every file type would sweep in the
# experiments' own scratch paths and turn a sharp test into a noisy one.
SEARCHED = (".md", ".yml", ".yaml")

# ``docs/`` followed by a path. Trailing punctuation is stripped afterwards rather than
# excluded here, because a link at the end of a sentence is the common case.
_REFERENCE = re.compile(r"(?<![\w./-])docs/[\w./-]+")


def _tracked() -> set[str]:
    done = subprocess.run(["git", "-C", ROOT, "ls-files"],
                          capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        pytest.skip("not a git checkout, so there is nothing to be missing from it")
    return set(done.stdout.split())


def test_every_doc_the_repository_points_at_is_in_the_repository():
    tracked = _tracked()
    searched = sorted(path for path in tracked if path.endswith(SEARCHED))
    assert searched, "no tracked prose to check, which would make this test a no-op"

    missing: dict[str, set[str]] = {}
    for path in searched:
        try:
            with open(os.path.join(ROOT, path), encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            continue
        for found in _REFERENCE.findall(text):
            target = found.rstrip(".,;:)`\"'")
            if target in tracked or target.rstrip("/") + "/" in {
                    t.rsplit("/", 1)[0] + "/" for t in tracked}:
                continue
            # A directory is satisfied by anything tracked inside it.
            if any(t.startswith(target.rstrip("/") + "/") for t in tracked):
                continue
            missing.setdefault(target, set()).add(path)

    assert not missing, (
        "these paths are referenced by tracked files but are not themselves tracked, "
        "so anyone cloning this repository gets a broken link or a workflow that "
        "silently takes its fallback branch:\n"
        + "\n".join(f"  {target}  <- {', '.join(sorted(sources))}"
                    for target, sources in sorted(missing.items()))
        + "\n\n.gitignore carries `docs/*` on purpose. Publishing a doc means adding a "
          "`!docs/<name>` line under it; this test is what says you forgot.")


def test_the_release_notes_the_workflow_reads_are_present_for_this_version():
    """The workflow tests for ``docs/release-notes/<tag>.md`` and falls back to a
    generated changelog when it is absent. A fallback that is never exercised locally is
    a fallback nobody notices taking over -- for a release spanning ninety-three commits
    it publishes the commit list instead of the notes somebody wrote."""
    tracked = _tracked()
    workflow = os.path.join(ROOT, ".github", "workflows", "release.yml")
    if not os.path.isfile(workflow):
        pytest.skip("no release workflow to hold to this")
    with open(workflow, encoding="utf-8") as handle:
        if "docs/release-notes/" not in handle.read():
            pytest.skip("the workflow no longer reads written notes")

    try:
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as handle:
            version = tomllib.load(handle)["project"]["version"]
    except (OSError, KeyError):  # pragma: no cover - a broken pyproject fails elsewhere
        pytest.skip("no packaged version to look for notes about")

    expected = f"docs/release-notes/v{version}.md"
    assert expected in tracked, (
        f"pyproject packages {version} and the release workflow would look for "
        f"{expected}, which is not in the repository. The release would publish a "
        "generated commit list in place of written notes.")
