"""Core engine tests for codesextant.

Deliberately self-contained. Every test builds a small throwaway project and
points CODESEXTANT_HOME at a temporary database directory, so nothing depends
on the state of an outside repo and the suite runs anywhere, repeatedly.

Covered: symbol extraction; incremental indexing, meaning cache hits, only
reindexing a file that changed, and dropping a file that was deleted;
reference precision from jedi when two symbols share a name; PageRank; and
JSON-serializable return values from the public API.
"""
import json
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import codesextant  # noqa: E402
from codesextant import engine, references, storage  # noqa: E402
from codesextant.ranking import rank_symbols  # noqa: E402
from codesextant.symbols import extract_symbols_from_source  # noqa: E402


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """Create a throwaway Python project with an isolated CODESEXTANT_HOME and
    return the project root."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    repo = tmp_path / "proj"
    repo.mkdir()
    return repo


def _write(repo, rel, content):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


# Symbol extraction.

def test_extract_symbols_kinds_and_scope():
    src = textwrap.dedent('''
        TOP_VAR = 1

        def top_func(x):
            return x

        class MyClass:
            def method_a(self):
                inner = 2   # a local, which must not be collected as a symbol
                return inner
    ''').encode("utf-8")
    syms = extract_symbols_from_source(src)
    kinds = {(s["kind"], s["name"], s["scope"]) for s in syms}
    assert ("variable", "TOP_VAR", "") in kinds
    assert ("function", "top_func", "") in kinds
    assert ("class", "MyClass", "") in kinds
    # a method carries its owning class as scope
    assert ("function", "method_a", "MyClass") in kinds
    # inner never shows up, since only module-level variables are collected
    assert not any(s["name"] == "inner" for s in syms)


def test_extract_symbols_rejects_str():
    with pytest.raises(TypeError):
        extract_symbols_from_source("def f(): pass")  # a str is passed on purpose, and must fail loudly


# Incremental indexing.

def test_index_incremental_cache_hit(project):
    _write(project, "a.py", "def fa(): return 1\n")
    _write(project, "b.py", "def fb(): return 2\n")

    r1 = codesextant.index_project(str(project))
    assert r1["indexed"] == 2 and r1["skipped"] == 0

    # nothing changed, so every file is a cache hit
    r2 = codesextant.index_project(str(project))
    assert r2["indexed"] == 0 and r2["skipped"] == 2

    # only a.py changed, so only one file is reindexed
    _write(project, "a.py", "def fa(): return 1\ndef fa2(): return 11\n")
    r3 = codesextant.index_project(str(project))
    assert r3["indexed"] == 1, f"one edited file should reindex 1, got {r3['indexed']}"
    assert r3["skipped"] == 1


def test_index_remove_deleted_file(project):
    pa = _write(project, "a.py", "def fa(): return 1\n")
    _write(project, "b.py", "def fb(): return 2\n")
    codesextant.index_project(str(project))

    os.remove(pa)
    r = codesextant.index_project(str(project))
    assert r["removed"] == 1
    syms = codesextant.get_symbols(str(project))
    assert all("a.py" not in s["path"] for s in syms["symbols"])


def test_index_paths_updates_only_dirty_files_without_repo_scan(project, monkeypatch):
    pa = _write(project, "a.py", "def original(): return 1\n")
    _write(project, "b.py", "def untouched(): return 2\n")
    codesextant.index_project(str(project))

    _write(project, "a.py", "def replacement(): return 3\n")
    monkeypatch.setattr(
        engine,
        "_iter_source_files",
        lambda _root: (_ for _ in ()).throw(AssertionError("targeted update scanned repo")),
    )

    result = engine.index_paths(str(project), [pa])

    assert result["indexed"] == 1
    assert result["skipped"] == 0
    symbols = codesextant.get_symbols(str(project))["symbols"]
    names = {symbol["name"] for symbol in symbols}
    assert "replacement" in names
    assert "original" not in names
    assert "untouched" in names


def test_index_paths_removes_deleted_file_without_repo_scan(project, monkeypatch):
    pa = _write(project, "a.py", "def removed_symbol(): return 1\n")
    _write(project, "b.py", "def stays(): return 2\n")
    codesextant.index_project(str(project))
    os.remove(pa)
    monkeypatch.setattr(
        engine,
        "_iter_source_files",
        lambda _root: (_ for _ in ()).throw(AssertionError("targeted delete scanned repo")),
    )

    result = engine.index_paths(str(project), [pa])

    assert result["removed"] == 1
    names = {symbol["name"] for symbol in codesextant.get_symbols(str(project))["symbols"]}
    assert names == {"stays"}


def test_index_paths_invalidates_reference_edges_touching_changed_file(project):
    definition = _write(project, "definition.py", "def target(): return 1\n")
    caller = _write(project, "caller.py", "from definition import target\ntarget()\n")
    codesextant.index_project(str(project))
    with storage.ProjectStore.open(str(project)) as store:
        store.replace_refs_for(caller, [{
            "src_path": caller,
            "src_line": 2,
            "symbol_name": "target",
            "def_path": definition,
            "def_line": 1,
            "confidence": "high",
        }])
        assert store.stats()["refs"] == 1

    _write(project, "definition.py", "def replacement(): return 2\n")
    engine.index_paths(str(project), [definition])

    with storage.ProjectStore.open(str(project)) as store:
        assert store.stats()["refs"] == 0


def test_index_paths_directory_delete_counts_each_file_once(project, monkeypatch):
    first = _write(project, "package/a.py", "def first(): return 1\n")
    _write(project, "package/b.py", "def second(): return 2\n")
    codesextant.index_project(str(project))
    import shutil
    shutil.rmtree(project / "package")
    monkeypatch.setattr(
        engine,
        "_iter_source_files",
        lambda _root: (_ for _ in ()).throw(AssertionError("targeted delete scanned repo")),
    )

    result = engine.index_paths(str(project), [project / "package", first])

    assert result["removed"] == 2
    assert codesextant.get_symbols(str(project))["symbols"] == []


def test_project_isolation(tmp_path, monkeypatch):
    """Two projects at different paths get different project_keys and therefore
    separate databases, so their symbols never mix."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    p1 = tmp_path / "proj1"; p1.mkdir()
    p2 = tmp_path / "proj2"; p2.mkdir()
    (p1 / "x.py").write_text("def only_in_p1(): pass\n", encoding="utf-8")
    (p2 / "y.py").write_text("def only_in_p2(): pass\n", encoding="utf-8")
    codesextant.index_project(str(p1))
    codesextant.index_project(str(p2))
    assert storage.project_key(str(p1)) != storage.project_key(str(p2))
    s1 = codesextant.get_symbols(str(p1))
    names1 = {s["name"] for s in s1["symbols"]}
    assert "only_in_p1" in names1 and "only_in_p2" not in names1


# Reference precision from jedi, which is the heart of the tool.

def test_find_references_disambiguates_same_name(project):
    """With two symbols sharing a name, jedi beats name matching outright.

    Two functions are called `helper`: lib_a.helper is the target and
    lib_b.helper is the decoy. One caller imports lib_a.helper explicitly and
    calls it. Name matching treats both files as references, while jedi only
    accepts the call site that resolves to lib_a.helper.
    """
    _write(project, "lib_a.py", "def helper(x):\n    return x + 1\n")
    _write(project, "lib_b.py", "def helper(y):\n    return y - 1\n")  # the same-name decoy
    _write(project, "caller.py", textwrap.dedent('''
        from lib_a import helper
        def run():
            return helper(10)
    '''))
    codesextant.index_project(str(project))

    lib_a = str(project / "lib_a.py")
    res = codesextant.find_references(str(project), "helper", def_path=lib_a,
                                  src_root=str(project))
    # name matching sweeps in every file containing helper: lib_a, lib_b, caller
    assert res["name_match_file_count"] >= 3
    # jedi accepts only the call in caller.py that points at lib_a.helper
    hc_files = {os.path.basename(h["src_path"]) for h in res["high_confidence"]}
    assert "caller.py" in hc_files, f"jedi should catch the real call in caller.py, got {hc_files}"
    # nothing from lib_b belongs in high confidence, since that is a different helper
    assert "lib_b.py" not in hc_files
    # fewer high-confidence hits than raw name matches is the proof of precision
    assert len(res["high_confidence"]) < res["name_match_hit_count"]


def test_find_references_missing_definition_is_loud(project):
    _write(project, "a.py", "x = 1\n")
    codesextant.index_project(str(project))
    res = codesextant.find_references(str(project), "does_not_exist_symbol",
                                  src_root=str(project))
    # with no definition found, the result says so instead of inventing references
    assert res["definition"] is None
    assert "error" in res
    assert res["high_confidence"] == []


# PageRank.

def test_pagerank_ranks_referenced_symbol_higher():
    symbols = [
        {"path": "a.py", "name": "popular", "scope": "", "line": 1, "end_line": 2, "kind": "function"},
        {"path": "b.py", "name": "caller_b", "scope": "", "line": 1, "end_line": 2, "kind": "function"},
        {"path": "c.py", "name": "caller_c", "scope": "", "line": 1, "end_line": 2, "kind": "function"},
        {"path": "d.py", "name": "lonely", "scope": "", "line": 1, "end_line": 2, "kind": "function"},
    ]
    refs = [
        {"src_path": "b.py", "src_line": 1, "symbol_name": "popular",
         "def_path": "a.py", "def_line": 1, "confidence": "high"},
        {"src_path": "c.py", "src_line": 1, "symbol_name": "popular",
         "def_path": "a.py", "def_line": 1, "confidence": "high"},
    ]
    ranked = rank_symbols(symbols, refs)
    assert ranked[0]["name"] == "popular", "the most referenced symbol should rank first"
    lonely = next(s for s in ranked if s["name"] == "lonely")
    assert ranked[0]["rank"] > lonely["rank"]


def test_pagerank_empty():
    assert rank_symbols([], []) == []


# The public API must return JSON-serializable data, since the daemon ships it over HTTP.

def test_all_api_returns_json_serializable(project):
    _write(project, "a.py", "def fa():\n    return 1\n")
    _write(project, "caller.py", "from a import fa\ndef use():\n    return fa()\n")
    codesextant.index_project(str(project))

    outputs = [
        codesextant.index_project(str(project)),
        codesextant.get_symbols(str(project)),
        codesextant.get_symbols(str(project), file=str(project / "a.py")),
        codesextant.find_references(str(project), "fa", src_root=str(project)),
        codesextant.get_map(str(project), token_budget=500),
        codesextant.status(str(project)),
    ]
    for o in outputs:
        # surviving json.dumps means the HTTP daemon can serialize it as is
        json.dumps(o, ensure_ascii=False, default=str)


def test_get_map_requires_index(project):
    # get_map on an unindexed project has to fail loudly
    with pytest.raises(RuntimeError):
        codesextant.get_map(str(project))


def test_status_unindexed(project):
    r = codesextant.status(str(project))
    assert r["indexed"] is False
    assert "project_key" in r


# Listing every project, and the HTML panel.

def test_list_projects_lists_all_indexed(tmp_path, monkeypatch):
    """list_projects walks the database directory and reports every indexed
    project with its statistics. This is what feeds the panel overview."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    p1 = tmp_path / "alpha"; p1.mkdir()
    p2 = tmp_path / "beta"; p2.mkdir()
    (p1 / "a.py").write_text("def fa(): return 1\ndef fb(): return 2\n", encoding="utf-8")
    (p2 / "b.py").write_text("def fc(): return 3\n", encoding="utf-8")
    codesextant.index_project(str(p1))
    codesextant.index_project(str(p2))

    r = codesextant.list_projects()
    assert r["count"] == 2
    by_path = {p["repo_path"]: p for p in r["projects"]}
    assert os.path.abspath(str(p1)) in by_path
    assert os.path.abspath(str(p2)) in by_path
    alpha = by_path[os.path.abspath(str(p1))]
    assert alpha["indexed_files"] == 1 and alpha["symbols"] == 2
    assert alpha["path_exists"] is True
    # the result goes straight out over HTTP /projects, so it must serialize
    json.dumps(r, ensure_ascii=False, default=str)


def test_list_projects_flags_missing_path(tmp_path, monkeypatch):
    """When a project folder is moved or deleted, its database survives, so the
    listing marks path_exists=False and the panel can flag it."""
    import shutil
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    repo = tmp_path / "gone"; repo.mkdir()
    (repo / "x.py").write_text("def gx(): return 1\n", encoding="utf-8")
    codesextant.index_project(str(repo))
    shutil.rmtree(repo)

    r = codesextant.list_projects()
    assert r["count"] == 1
    assert r["projects"][0]["path_exists"] is False


def test_list_projects_empty(tmp_path, monkeypatch):
    """A missing database directory means nothing was ever indexed, so the
    listing returns count=0 without raising."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_nope"))
    r = codesextant.list_projects()
    assert r["count"] == 0 and r["projects"] == []


def test_render_panel_self_contained():
    """The panel is one self-contained HTML document. It pulls nothing from a
    CDN, so it opens offline, and the endpoints its script calls are real."""
    import re

    from codesextant import panel
    html = panel.render_panel()
    assert html.startswith("<!DOCTYPE html>")
    assert "CodeSextant" in html and "Indexed projects" in html and "Service status" in html
    # the panel's script really does call these daemon endpoints
    for ep in ("/health", "/projects", "/get_map", "/reindex", "/find_references"):
        assert ep in html, f"the panel should call {ep}"
    # self-contained means no script or link points at an http(s) CDN
    externals = re.findall(r'(?:src|href)\s*=\s*["\']https?://', html)
    assert externals == [], f"the panel must not depend on a CDN, found {externals}"


# Cross-language symbol extraction, and the fallback path for finding references.

def test_language_for_file():
    from codesextant import symbols
    assert symbols.language_for_file("a.py") == "python"
    assert symbols.language_for_file("a.ts") == "typescript"
    assert symbols.language_for_file("a.tsx") == "tsx"
    assert symbols.language_for_file("a.js") == "javascript"
    assert symbols.language_for_file("a.go") == "go"
    assert symbols.language_for_file("a.rs") == "rust"
    assert symbols.language_for_file("a.unknown") is None


def test_extract_symbols_typescript():
    src = textwrap.dedent('''
        export function topFunc(x) { return x; }
        export class MyClass {
          methodA() {}
        }
        interface IThing { x: number; }
        type Alias = string;
        enum Color { Red, Green }
        const arrow = (y) => y * 2;
    ''').encode("utf-8")
    syms = extract_symbols_from_source(src, "typescript")
    kinds = {(s["kind"], s["name"]) for s in syms}
    assert ("function", "topFunc") in kinds
    assert ("class", "MyClass") in kinds
    assert ("method", "methodA") in kinds
    assert ("interface", "IThing") in kinds
    assert ("type", "Alias") in kinds
    assert ("enum", "Color") in kinds
    assert ("variable", "arrow") in kinds   # a top-level arrow const is collected as a variable
    # a method carries its class as scope, which keeps same-named methods apart
    method_a = next(s for s in syms if s["name"] == "methodA")
    assert method_a["scope"] == "MyClass"


def test_extract_symbols_go_and_rust():
    go_src = textwrap.dedent('''
        package main
        var Gv = 1
        func TopFunc(x int) int { return x }
        type MyStruct struct { X int }
        func (m MyStruct) Method() {}
    ''').encode("utf-8")
    gk = {(s["kind"], s["name"]) for s in extract_symbols_from_source(go_src, "go")}
    assert ("function", "TopFunc") in gk
    assert ("type", "MyStruct") in gk
    assert ("method", "Method") in gk
    assert ("variable", "Gv") in gk

    rust_src = textwrap.dedent('''
        const C: i32 = 1;
        fn top_fn(x: i32) -> i32 { x }
        struct MyStruct { x: i32 }
        enum E { A, B }
        trait T { fn m(&self); }
    ''').encode("utf-8")
    rk = {(s["kind"], s["name"]) for s in extract_symbols_from_source(rust_src, "rust")}
    assert ("function", "top_fn") in rk
    assert ("struct", "MyStruct") in rk
    assert ("enum", "E") in rk
    assert ("trait", "T") in rk
    assert ("variable", "C") in rk


def test_extract_symbols_unsupported_lang_is_loud():
    with pytest.raises(ValueError):
        extract_symbols_from_source(b"whatever", "cobol")


def test_index_multilang_project(tmp_path, monkeypatch):
    """A mixed project: one indexing pass collects Python, TS and Go symbols
    together, because _iter_source_files accepts all three extensions."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    repo = tmp_path / "multi"; repo.mkdir()
    (repo / "a.py").write_text("def py_fn(): pass\n", encoding="utf-8")
    (repo / "b.ts").write_text("export function tsFn(){}\nexport class TsCls{}\n", encoding="utf-8")
    (repo / "c.go").write_text("package main\nfunc GoFn() {}\n", encoding="utf-8")
    (repo / "ignore.txt").write_text("not source\n", encoding="utf-8")  # unsupported extension, skipped
    r = codesextant.index_project(str(repo))
    assert r["indexed"] == 3, f"only the 3 source files should be indexed, got {r['indexed']}"
    names = {s["name"] for s in codesextant.get_symbols(str(repo))["symbols"]}
    assert {"py_fn", "tsFn", "TsCls", "GoFn"} <= names


def test_find_references_ts_fallback_when_ts_morph_unavailable(tmp_path, monkeypatch):
    """Without ts-morph, finding TS references falls back to name matching. High
    confidence comes back empty, a note explains why, and language is set."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    # force ts-morph off so the fallback path is exercised whether or not node
    # happens to be installed here
    monkeypatch.setattr("codesextant.references.ts_morph_available", lambda: False)
    repo = tmp_path / "ts"; repo.mkdir()
    (repo / "lib.ts").write_text("export function helper(x){ return x; }\n", encoding="utf-8")
    (repo / "caller.ts").write_text("import { helper } from './lib';\nhelper(1);\n", encoding="utf-8")
    codesextant.index_project(str(repo))
    res = codesextant.find_references(str(repo), "helper", src_root=str(repo))
    assert res["language"] == "typescript"
    assert res["high_confidence"] == []          # name matching never claims high confidence
    assert "note" in res
    assert res["name_match_hit_count"] >= 1       # it still catches the call in caller.ts
    json.dumps(res, ensure_ascii=False, default=str)


def test_find_references_ts_morph_high_confidence(tmp_path, monkeypatch):
    """With ts-morph available, TS reference lookup returns high confidence hits
    and drops the same-name decoy, which name matching cannot do.

    Needs node with ts_bridge installed via npm. Without them the test skips,
    since a missing Node is an environment gap rather than a failure.
    """
    if not references.ts_morph_available():
        pytest.skip("ts-morph bridge unavailable: no node, or ts_bridge not npm installed")
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    repo = tmp_path / "ts"; repo.mkdir()
    _write(repo, "lib_a.ts", "export function helper(x: number) { return x + 1; }\n")
    _write(repo, "lib_b.ts", "export function helper(y: number) { return y - 1; }\n")  # the decoy
    _write(repo, "caller.ts",
           "import { helper } from './lib_a';\nexport function run() { return helper(10); }\n")
    codesextant.index_project(str(repo))
    res = codesextant.find_references(str(repo), "helper",
                                 def_path=str(repo / "lib_a.ts"), src_root=str(repo))
    assert res.get("engine") == "ts-morph"
    assert res["language"] == "typescript"
    hc_files = {os.path.basename(h["src_path"]) for h in res["high_confidence"]}
    assert "caller.ts" in hc_files            # real resolution finds the call in caller.ts
    assert "lib_b.ts" not in hc_files          # and rejects the lib_b decoy, which name matching cannot
    json.dumps(res, ensure_ascii=False, default=str)


def test_ts_morph_malformed_output_does_not_crash(monkeypatch):
    """Regression: when the mjs bridge returns a malformed high_confidence entry
    with no src_path, the caller skips it rather than raising KeyError."""
    monkeypatch.setattr(references, "ts_morph_available", lambda: True)

    class _FakeProc:
        returncode = 0
        stdout = (b'{"high_confidence":[{"line":5},{"src_path":"a.ts","line":3}],'
                  b'"definition":{"path":"x.ts","line":1}}')  # first entry is malformed: no src_path
        stderr = b""

    monkeypatch.setattr(references.subprocess, "run", lambda *a, **k: _FakeProc())
    res = references.ts_morph_references("/root", "foo", def_path="/root/x.ts")
    assert res is not None                       # a valid entry exists, so this returns normally
    assert len(res["high_confidence"]) == 1      # the malformed entry is skipped, the good one kept
    assert res["high_confidence"][0]["src_path"].endswith("a.ts")


def test_ts_morph_disabled_by_env(monkeypatch):
    """The feature is switchable: CODESEXTANT_TS_MORPH_DISABLED=1 turns ts-morph
    off and routes the lookup through the fallback."""
    monkeypatch.setenv("CODESEXTANT_TS_MORPH_DISABLED", "1")
    assert references.ts_morph_available() is False


def test_c5_review_fixes_abstract_impl_destructure():
    """Regressions for three table and walk bugs found in adversarial review.
    The node types below were confirmed by running _probe2 against the grammars."""
    # bug 2: TS abstract classes and abstract methods are no longer missed, and
    # they land on the right class scope
    ts = textwrap.dedent('''
        abstract class AbsFoo {
          abstract am(): void;
          concreteM() {}
        }
    ''').encode("utf-8")
    tk = {(s["kind"], s["name"], s["scope"]) for s in extract_symbols_from_source(ts, "typescript")}
    assert ("class", "AbsFoo", "") in tk
    assert ("method", "am", "AbsFoo") in tk
    assert ("method", "concreteM", "AbsFoo") in tk

    # bug 3: destructuring no longer emits junk names like "{a, b}" or "[c, d]",
    # while ordinary top-level consts are still collected
    de = b"const {a, b} = obj;\nconst [c, d] = arr;\nconst plain = 1;\n"
    names = {s["name"] for s in extract_symbols_from_source(de, "typescript")}
    assert "plain" in names
    assert not any(("{" in n or "[" in n) for n in names), f"destructuring junk names leaked: {names}"

    # bug 1: a method inside a Rust impl takes the target type as its scope, so
    # it is never confused with a global function of the same name
    rs = textwrap.dedent('''
        fn method() {}
        impl MyStruct {
          fn method(&self) {}
        }
    ''').encode("utf-8")
    scopes = {(s["name"], s["scope"]) for s in extract_symbols_from_source(rs, "rust")
              if s["name"] == "method"}
    assert ("method", "") in scopes            # a global method has an empty scope
    assert ("method", "MyStruct") in scopes    # one inside the impl scopes to MyStruct
