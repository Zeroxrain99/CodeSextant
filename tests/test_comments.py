"""功能 B 註解管理測試 — comments.py 抽取 + engine 查詢層（覆蓋率/標記索引/精確過濾）。

涵蓋：Python docstring owner_line 對齊／block 逐行 marker 真實行號（FIX-3b）／Rust /// 去重+owner
近似對齊／覆蓋率 JOIN/SKIP_PRIVATE/密度／TODO 索引真實行號+過濾／get_comments 過濾／env 開關／未索引 fail-soft。
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


# ─────────────── 抽取層（extract_comments_from_source） ───────────────

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
    # module doc owner=None；foo doc owner=def foo 行
    assert any(c["owner_line"] is None and c["kind"] == "doc" for c in docs)  # module
    foo_doc = next(c for c in cs if c["is_doc"] and c["owner_line"] is not None)
    assert foo_doc["text"].strip('"').startswith("Foo doc")
    # line comment 抓到
    assert any(c["kind"] == "line" and "inline" in c["text"] for c in cs)


def test_block_comment_marker_real_line():
    """FIX-3b：多行 docstring 內 marker 回真實源碼行（base_line+offset），非起始行。"""
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
    # TODO 在 docstring 第 3 行內容（doc 起始行 + offset），不是 doc["line"]
    assert tags[0]["line"] > doc["line"]


def test_rust_doc_dedup_and_owner_align():
    """Rust /// 巢狀(line_comment 含 doc_comment)只收一筆 + owner 對齊下方符號。"""
    src = textwrap.dedent('''
        /// Doc for add.
        fn add(a: i32, b: i32) -> i32 {
            a + b
        }
    ''').encode("utf-8")
    cs = comments.extract_comments_from_source(src, "rust")
    docs = [c for c in cs if c["is_doc"]]
    assert len(docs) == 1                      # 去重：不重複收 line_comment + doc_comment
    assert docs[0]["owner_line"] is not None   # 緊鄰回填對齊下方 add


# ─────────────── engine 查詢層 ───────────────

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
    # 預設 skip_private=on → _private_helper 不算進分母
    ov = engine.get_comment_overview(project)
    fn = ov["docstring_coverage"]["by_kind"]["function"]
    assert fn["total"] == 1                        # 只算 public_api
    # 關掉 skip_private → 分母含 _private_helper
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
    # 過濾只要 FIXME
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
    """CODESEXTANT_COMMENTS_DISABLED=1 → index 不抽註解、查詢回空。"""
    monkeypatch.setenv("CODESEXTANT_COMMENTS_DISABLED", "1")
    _write(project, "m.py", 'def foo():\n    """doc."""\n    return 1\n')
    engine.index_project(project, force=True)
    assert engine.get_comments(project)["count"] == 0


def test_comment_overview_unindexed(project):
    ov = engine.get_comment_overview(project)
    assert ov.get("indexed") is False and "note" in ov


def test_rust_inner_doc_not_attributed(project):
    """紅隊 L3-MEDIUM：Rust //! 內部文件（文件化 enclosing 模組）不回填下方符號、不灌高覆蓋率。"""
    src = b"//! Module level doc.\nfn helper() {\n    let x = 1;\n}\n"
    inner = [c for c in comments.extract_comments_from_source(src, "rust")
             if c["text"].lstrip().startswith("//!")]
    assert inner and inner[0]["owner_line"] is None


def test_overview_tag_counts_multi_marker(project):
    """紅隊 L3-MEDIUM：overview.tag_counts 逐行掃，多標記 block 不漏算（與 find_comment_tags 一致）。"""
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
