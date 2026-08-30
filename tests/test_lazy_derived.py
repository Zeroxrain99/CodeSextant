"""Clone fingerprints and comments are computed when something asks for them.

Indexing extracts the symbols and references needed to navigate code. The optional
analyses used to be extracted for every file in the same pass, which cost more than
twice the index CPU and seven times its storage for data the navigation path never
reads. These tests pin the contract that replaced it: nothing derived at index time,
correct results on first use, no repeated work after that, and per-file invalidation
when source changes.
"""
from __future__ import annotations

import os
import textwrap

import pytest

from codesextant import engine, storage


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "proj"
    root.mkdir()
    return root


def _write(root, rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return str(path)


def _counts(root):
    with storage.ProjectStore.open_readonly(str(root)) as store:
        def n(table):
            return store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return {t: n(t) for t in
                ("symbols", "fingerprints", "fingerprint_index", "comments",
                 "derived_state")}


def _duplicated_pair(root):
    for name in ("alpha", "beta"):
        _write(root, f"{name}.py", f"""
            # a leading comment for {name}
            def {name}_process(items):
                total = 0
                for item in items:
                    if item > 0:
                        total += item
                    else:
                        total -= item
                return total
            """)


def test_indexing_derives_nothing_optional(repo):
    _duplicated_pair(repo)
    engine.index_project(str(repo), force=True)
    counts = _counts(repo)
    assert counts["symbols"] > 0, "navigation data is still indexed eagerly"
    assert counts["fingerprints"] == 0
    assert counts["fingerprint_index"] == 0
    assert counts["comments"] == 0
    assert counts["derived_state"] == 0


def test_find_duplicates_materializes_and_still_finds_the_duplicate(repo):
    _duplicated_pair(repo)
    engine.index_project(str(repo), force=True)

    result = engine.find_duplicates(str(repo))

    assert result["groups"], "the duplicate pair must still be reported"
    assert _counts(repo)["fingerprints"] > 0
    files = {os.path.basename(m["path"])
             for group in result["groups"] for m in group["members"]}
    assert {"alpha.py", "beta.py"} <= files


def test_a_second_query_does_no_further_derivation(repo):
    _duplicated_pair(repo)
    engine.index_project(str(repo), force=True)
    engine.find_duplicates(str(repo))

    again = engine._materialize_derived(str(repo), "fingerprints")
    assert again["computed"] == 0, "already-current files must not be recomputed"


def test_editing_one_file_invalidates_only_that_file(repo):
    _duplicated_pair(repo)
    engine.index_project(str(repo), force=True)
    engine.find_duplicates(str(repo))

    _write(repo, "alpha.py", """
        def alpha_process(items):
            return sum(items)
        """)
    engine.index_project(str(repo))

    pending = engine._materialize_derived(str(repo), "fingerprints")
    assert pending["computed"] == 1, "only the edited file should be re-derived"


def test_comments_are_derived_on_demand(repo):
    _write(repo, "mod.py", """
        # TODO: a marker worth finding
        def documented():
            \"\"\"A docstring.\"\"\"
            return 1
        """)
    engine.index_project(str(repo), force=True)
    assert _counts(repo)["comments"] == 0

    found = engine.find_comment_tags(str(repo), tags=["TODO"])

    assert found["count_by_tag"].get("TODO") == 1
    assert _counts(repo)["comments"] > 0


def test_scoped_comment_query_derives_only_the_file_it_reads(repo):
    _write(repo, "one.py", "# TODO: first\ndef one():\n    return 1\n")
    _write(repo, "two.py", "# TODO: second\ndef two():\n    return 2\n")
    engine.index_project(str(repo), force=True)

    engine.get_comments(str(repo), file=str(repo / "one.py"))

    with storage.ProjectStore.open_readonly(str(repo)) as store:
        derived = {os.path.basename(r["path"]) for r in store.conn.execute(
            "SELECT path FROM derived_state WHERE kind='comments'")}
    assert derived == {"one.py"}, "a file-scoped read must not derive the whole project"


def test_stale_derived_rows_never_survive_a_content_change(repo):
    _write(repo, "mod.py", "# TODO: original marker\ndef mod():\n    return 1\n")
    engine.index_project(str(repo), force=True)
    assert engine.find_comment_tags(str(repo))["count_by_tag"].get("TODO") == 1

    _write(repo, "mod.py", "def mod():\n    return 2\n")
    engine.index_project(str(repo))

    assert engine.find_comment_tags(str(repo))["count_by_tag"].get("TODO") is None


def test_disabling_an_analysis_keeps_materialization_a_no_op(repo, monkeypatch):
    _duplicated_pair(repo)
    engine.index_project(str(repo), force=True)
    monkeypatch.setenv("CODESEXTANT_DEDUP_DISABLED", "1")

    result = engine._materialize_derived(str(repo), "fingerprints")

    assert result["computed"] == 0
    assert _counts(repo)["fingerprints"] == 0


def test_a_file_changed_since_indexing_is_not_derived_from(repo):
    """Deriving from content the index does not describe would disagree with the symbols."""
    path = _write(repo, "mod.py", "def mod():\n    return 1\n")
    engine.index_project(str(repo), force=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("def mod():\n    return 999\n")

    result = engine._materialize_derived(str(repo), "fingerprints")

    assert result["computed"] == 0
    assert result["pending"] == 1


def test_interactive_routes_never_pay_for_derivation(repo):
    """An agent navigating code must not be billed for an analysis it did not ask for."""
    from codesextant import daemon

    _duplicated_pair(repo)
    engine.index_project(str(repo), force=True)

    engine.get_map(str(repo), token_budget=2000)
    engine.get_symbols(str(repo))
    engine.find_references(str(repo), "alpha_process")

    counts = _counts(repo)
    assert counts["fingerprints"] == 0
    assert counts["comments"] == 0
    assert counts["derived_state"] == 0

    # And the routes that do derive are not on the interactive lane, so they queue
    # behind reindex rather than ahead of a navigation query.
    deriving = {"/find_duplicates", "/get_health", "/get_comments",
                "/comment_tags", "/comment_overview"}
    assert deriving.isdisjoint(daemon._INTERACTIVE_HEAVY_PATHS)
    assert deriving <= daemon._HEAVY_PATHS
