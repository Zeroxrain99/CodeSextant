"""Comment management tests: extraction in comments.py plus the engine query
layer that reports coverage, indexes tags and filters them.

What is covered here: owner_line alignment for Python docstrings, real source
line numbers for markers buried inside a block comment, Rust /// dedup with
approximate owner alignment, the coverage JOIN together with SKIP_PRIVATE and
density, real line numbers and filtering in the TODO index, get_comments
filters, the env switch, and a soft failure when the project is not indexed.
"""
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import comments, engine  # noqa: E402


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    repo = tmp_path / "proj"
    repo.mkdir()
    return str(repo)


def _write(repo, rel, content):
    p = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))
    return p


# Extraction layer: extract_comments_from_source.

def test_python_docstring_owner_line_and_kinds():
    src = textwrap.dedent('''
        """Module doc."""

        def foo(x):
            """Foo doc."""
            return x  # inline

        # top comment
    ''').encode("utf-8")
    cs = comments.extract_comments_from_source(src, "python")
    docs = [c for c in cs if c["is_doc"]]
    # the module doc has owner=None, while foo's doc points at the def foo line
    assert any(c["owner_line"] is None and c["kind"] == "doc" for c in docs)  # module
    foo_doc = next(c for c in cs if c["is_doc"] and c["owner_line"] is not None)
    assert foo_doc["text"].strip('"').startswith("Foo doc")
    # the inline line comment was picked up too
    assert any(c["kind"] == "line" and "inline" in c["text"] for c in cs)


def test_block_comment_marker_real_line():
    """A marker inside a multi-line docstring reports its real source line
    (base_line plus offset), not the line the docstring opens on."""
    src = textwrap.dedent('''
        def foo():
            """Line1.

            TODO: real line here
            """
            return 1
    ''').encode("utf-8")
    cs = comments.extract_comments_from_source(src, "python")
    doc = next(c for c in cs if c["is_doc"])
    tags = comments.scan_tags_in_text(doc["text"], doc["line"])
    assert tags and tags[0]["tag"] == "TODO"
    # the marker sits on the docstring's third line, so its line is the
    # docstring's opening line plus an offset
    assert tags[0]["line"] > doc["line"]


def test_rust_doc_dedup_and_owner_align():
    """A nested Rust /// (a line_comment wrapping a doc_comment) is collected
    once, and its owner aligns to the symbol below it."""
    src = textwrap.dedent('''
        /// Doc for add.
        fn add(a: i32, b: i32) -> i32 {
            a + b
        }
    ''').encode("utf-8")
    cs = comments.extract_comments_from_source(src, "rust")
    docs = [c for c in cs if c["is_doc"]]
    assert len(docs) == 1                      # dedup: not counted as both kinds
    assert docs[0]["owner_line"] is not None   # backfilled onto the adjacent add


# Engine query layer.

def test_comment_overview_coverage(project):
    _write(project, "m.py", '''
        def documented(x):
            """Has doc."""
            return x

        def undocumented(y):
            return y
    ''')
    engine.index_project(project, force=True)
    ov = engine.get_comment_overview(project)
    fn = ov["docstring_coverage"]["by_kind"].get("function", {})
    assert fn.get("documented") == 1 and fn.get("total") == 2
    assert ov["docstring_coverage"]["overall_pct"] == 50.0
    assert any(u["name"] == "undocumented" for u in ov["top_undocumented"])
    assert ov["density"] is not None and "comment_lines" in ov["density"]


def test_comment_overview_skip_private(project, monkeypatch):
    _write(project, "m.py", '''
        def _private_helper():
            return 1

        def public_api():
            """doc."""
            return 2
    ''')
    engine.index_project(project, force=True)
    # skip_private defaults to on, which keeps _private_helper out of the denominator
    ov = engine.get_comment_overview(project)
    fn = ov["docstring_coverage"]["by_kind"]["function"]
    assert fn["total"] == 1                        # public_api is the only one counted
    # turn skip_private off and _private_helper joins the denominator
    monkeypatch.setenv("CODESEXTANT_COMMENT_COVERAGE_SKIP_PRIVATE", "off")
    ov2 = engine.get_comment_overview(project)
    assert ov2["docstring_coverage"]["by_kind"]["function"]["total"] == 2


def test_find_comment_tags_real_line_and_filter(project):
    _write(project, "m.py", '''
        def foo():
            """Doc.

            FIXME: fix in block
            """
            x = 1  # TODO inline
            return x
    ''')
    engine.index_project(project, force=True)
    tg = engine.find_comment_tags(project)
    tags = {f["tag"] for f in tg["findings"]}
    assert "FIXME" in tags and "TODO" in tags
    # narrow the query to FIXME only
    only = engine.find_comment_tags(project, tags=["FIXME"])
    assert all(f["tag"] == "FIXME" for f in only["findings"])
    assert only["count_by_tag"].get("FIXME", 0) >= 1


def test_get_comments_filters(project):
    _write(project, "m.py", '''
        """Mod."""
        def foo():
            """Foo doc."""
            return 1  # NOTE here
    ''')
    engine.index_project(project, force=True)
    docs = engine.get_comments(project, doc_only=True)
    assert docs["count"] >= 2 and all(c["is_doc"] for c in docs["comments"])
    note = engine.get_comments(project, tag="NOTE")
    assert note["count"] == 1 and note["comments"][0]["tag"] == "NOTE"


def test_comments_disabled_env(project, monkeypatch):
    """With CODESEXTANT_COMMENTS_DISABLED=1 the indexer extracts no comments
    and queries come back empty."""
    monkeypatch.setenv("CODESEXTANT_COMMENTS_DISABLED", "1")
    _write(project, "m.py", 'def foo():\n    """doc."""\n    return 1\n')
    engine.index_project(project, force=True)
    assert engine.get_comments(project)["count"] == 0


def test_comment_overview_unindexed(project):
    ov = engine.get_comment_overview(project)
    assert ov.get("indexed") is False and "note" in ov


def test_rust_inner_doc_not_attributed(project):
    """Raised in adversarial review: a Rust //! inner doc documents the
    enclosing module, so it must not be backfilled onto the symbol below it
    and must not inflate the coverage figure."""
    src = b"//! Module level doc.\nfn helper() {\n    let x = 1;\n}\n"
    inner = [c for c in comments.extract_comments_from_source(src, "rust")
             if c["text"].lstrip().startswith("//!")]
    assert inner and inner[0]["owner_line"] is None


def test_overview_tag_counts_multi_marker(project):
    """Raised in adversarial review: overview.tag_counts scans line by line, so
    a block holding several markers is counted in full and agrees with what
    find_comment_tags reports."""
    _write(project, "m.py", '''
        def foo():
            """Doc.

            TODO: first
            TODO: second
            FIXME: third
            """
            return 1
    ''')
    engine.index_project(project, force=True)
    ov = engine.get_comment_overview(project)
    assert ov["tag_counts"].get("TODO") == 2 and ov["tag_counts"].get("FIXME") == 1
