"""codesextant C1 引擎測試。

刻意全自包含：每個測試建一個臨時小專案 + 臨時庫目錄（CODESEXTANT_HOME），
不依賴任何外部 repo 的特定狀態，所以可重複、可在任何機器跑。

涵蓋：抽符號 / 增量(cache hit + 改檔只重算 + 刪檔移除) / jedi 找引用精度
（同名符號）/ PageRank / 對外 API 回傳可序列化。
"""
import json
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import codesextant  # noqa: E402
from codesextant import references, storage  # noqa: E402
from codesextant.ranking import rank_symbols  # noqa: E402
from codesextant.symbols import extract_symbols_from_source  # noqa: E402


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """建一個臨時 Python 專案 + 隔離的 CODESEXTANT_HOME。回傳專案根路徑。"""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    repo = tmp_path / "proj"
    repo.mkdir()
    return repo


def _write(repo, rel, content):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


# ─────────────── 抽符號 ───────────────

def test_extract_symbols_kinds_and_scope():
    src = textwrap.dedent('''
        TOP_VAR = 1

        def top_func(x):
            return x

        class MyClass:
            def method_a(self):
                inner = 2   # 區域變數不該被當符號
                return inner
    ''').encode("utf-8")
    syms = extract_symbols_from_source(src)
    kinds = {(s["kind"], s["name"], s["scope"]) for s in syms}
    assert ("variable", "TOP_VAR", "") in kinds
    assert ("function", "top_func", "") in kinds
    assert ("class", "MyClass", "") in kinds
    # method 應標出所屬 class 為 scope
    assert ("function", "method_a", "MyClass") in kinds
    # 區域變數 inner 不該出現（只收模組層級變數）
    assert not any(s["name"] == "inner" for s in syms)


def test_extract_symbols_rejects_str():
    with pytest.raises(TypeError):
        extract_symbols_from_source("def f(): pass")  # 故意傳 str，應 fail-loud


# ─────────────── 增量 ───────────────

def test_index_incremental_cache_hit(project):
    _write(project, "a.py", "def fa(): return 1\n")
    _write(project, "b.py", "def fb(): return 2\n")

    r1 = codesextant.index_project(str(project))
    assert r1["indexed"] == 2 and r1["skipped"] == 0

    # 沒改任何檔 → 全 cache hit
    r2 = codesextant.index_project(str(project))
    assert r2["indexed"] == 0 and r2["skipped"] == 2

    # 只改 a.py → 只重算 1 檔
    _write(project, "a.py", "def fa(): return 1\ndef fa2(): return 11\n")
    r3 = codesextant.index_project(str(project))
    assert r3["indexed"] == 1, f"改一檔應只重算 1，實際 {r3['indexed']}"
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


def test_project_isolation(tmp_path, monkeypatch):
    """兩個不同路徑的專案 → 不同 project_key → 不同庫 → 不混線。"""
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


# ─────────────── jedi 找引用精度（命脈） ───────────────

def test_find_references_disambiguates_same_name(project):
    """核心：同名符號 jedi 完勝名稱比對。

    建兩個同名 `helper`：lib_a.helper（目標）與 lib_b.helper（干擾）。
    一個 caller 明確 import lib_a.helper 並呼叫。
    名稱比對會把兩個檔都當引用；jedi 只認 lib_a.helper 的呼叫點。
    """
    _write(project, "lib_a.py", "def helper(x):\n    return x + 1\n")
    _write(project, "lib_b.py", "def helper(y):\n    return y - 1\n")  # 同名干擾
    _write(project, "caller.py", textwrap.dedent('''
        from lib_a import helper
        def run():
            return helper(10)
    '''))
    codesextant.index_project(str(project))

    lib_a = str(project / "lib_a.py")
    res = codesextant.find_references(str(project), "helper", def_path=lib_a,
                                  src_root=str(project))
    # 名稱比對會框到含 helper 的多個檔（lib_a, lib_b, caller）
    assert res["name_match_file_count"] >= 3
    # jedi 高信心引用只認 caller.py 裡指向 lib_a.helper 的呼叫
    hc_files = {os.path.basename(h["src_path"]) for h in res["high_confidence"]}
    assert "caller.py" in hc_files, f"jedi 應抓到 caller.py 的真呼叫，實際 {hc_files}"
    # lib_b.helper 的定義/任何 lib_b 內的東西不該進高信心（它是別的 helper）
    assert "lib_b.py" not in hc_files
    # 高信心數 < 名稱比對總命中數（精度提升的鐵證）
    assert len(res["high_confidence"]) < res["name_match_hit_count"]


def test_find_references_missing_definition_is_loud(project):
    _write(project, "a.py", "x = 1\n")
    codesextant.index_project(str(project))
    res = codesextant.find_references(str(project), "does_not_exist_symbol",
                                  src_root=str(project))
    # 查無定義應誠實回 error，不假裝有引用
    assert res["definition"] is None
    assert "error" in res
    assert res["high_confidence"] == []


# ─────────────── PageRank ───────────────

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
    assert ranked[0]["name"] == "popular", "被引用最多的應排第一"
    lonely = next(s for s in ranked if s["name"] == "lonely")
    assert ranked[0]["rank"] > lonely["rank"]


def test_pagerank_empty():
    assert rank_symbols([], []) == []


# ─────────────── 對外 API 可序列化（給 C2 daemon） ───────────────

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
        # 能 json.dumps 不報錯 = 可被 HTTP daemon 直接序列化
        json.dumps(o, ensure_ascii=False, default=str)


def test_get_map_requires_index(project):
    # 沒索引就 get_map 應 fail-loud
    with pytest.raises(RuntimeError):
        codesextant.get_map(str(project))


def test_status_unindexed(project):
    r = codesextant.status(str(project))
    assert r["indexed"] is False
    assert "project_key" in r


# ─────────────── C4：列所有專案 + 中文面板 ───────────────

def test_list_projects_lists_all_indexed(tmp_path, monkeypatch):
    """list_projects 掃庫目錄、列出每個已索引專案 + 統計（面板總覽資料源）。"""
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
    # 回傳要可序列化（直接給 HTTP /projects）
    json.dumps(r, ensure_ascii=False, default=str)


def test_list_projects_flags_missing_path(tmp_path, monkeypatch):
    """專案資料夾被搬走/刪掉後，庫還在 → list 標 path_exists=False（面板標紅用）。"""
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
    """庫目錄不存在（沒索引過任何專案）→ count=0、不報錯。"""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_nope"))
    r = codesextant.list_projects()
    assert r["count"] == 0 and r["projects"] == []


def test_render_panel_self_contained():
    """面板＝自包含中文 HTML，無外部 CDN 依賴（離線可開），且真打既有端點。"""
    import re

    from codesextant import panel
    html = panel.render_panel()
    assert html.startswith("<!DOCTYPE html>")
    assert "CodeSextant" in html and "已索引專案" in html and "服務狀態" in html
    # 面板 JS 確實呼叫這些 daemon 端點
    for ep in ("/health", "/projects", "/get_map", "/reindex", "/find_references"):
        assert ep in html, f"面板應呼叫 {ep}"
    # 自包含鐵則：沒有任何 http(s):// 的外連 script/link（CDN）
    externals = re.findall(r'(?:src|href)\s*=\s*["\']https?://', html)
    assert externals == [], f"面板不該有外部 CDN 依賴，發現 {externals}"


# ─────────────── C5：跨語言抽符號 + 找引用退化 ───────────────

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
    assert ("variable", "arrow") in kinds   # 頂層 const（arrow）收為 variable
    # method 標出所屬 class scope（同名 method 可分辨）
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
    """跨語言專案：一次 index 同時收 Python + TS + Go 符號（_iter_source_files 多副檔名）。"""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    repo = tmp_path / "multi"; repo.mkdir()
    (repo / "a.py").write_text("def py_fn(): pass\n", encoding="utf-8")
    (repo / "b.ts").write_text("export function tsFn(){}\nexport class TsCls{}\n", encoding="utf-8")
    (repo / "c.go").write_text("package main\nfunc GoFn() {}\n", encoding="utf-8")
    (repo / "ignore.txt").write_text("not source\n", encoding="utf-8")  # 不支援副檔名應跳過
    r = codesextant.index_project(str(repo))
    assert r["indexed"] == 3, f"應只索引 3 個原始碼檔，實際 {r['indexed']}"
    names = {s["name"] for s in codesextant.get_symbols(str(repo))["symbols"]}
    assert {"py_fn", "tsFn", "TsCls", "GoFn"} <= names


def test_find_references_ts_fallback_when_ts_morph_unavailable(tmp_path, monkeypatch):
    """ts-morph 不可用時，TS 找引用 fallback 成 C5a 名稱比對（high 空、附 note、標 language）。"""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    # 強制 ts-morph 不可用，測純 fallback 路徑（不靠環境有沒有 node）
    monkeypatch.setattr("codesextant.references.ts_morph_available", lambda: False)
    repo = tmp_path / "ts"; repo.mkdir()
    (repo / "lib.ts").write_text("export function helper(x){ return x; }\n", encoding="utf-8")
    (repo / "caller.ts").write_text("import { helper } from './lib';\nhelper(1);\n", encoding="utf-8")
    codesextant.index_project(str(repo))
    res = codesextant.find_references(str(repo), "helper", src_root=str(repo))
    assert res["language"] == "typescript"
    assert res["high_confidence"] == []          # fallback 名稱比對不給高信心（誠實）
    assert "note" in res
    assert res["name_match_hit_count"] >= 1       # 名稱比對至少框到 caller.ts 的呼叫
    json.dumps(res, ensure_ascii=False, default=str)


def test_find_references_ts_morph_high_confidence(tmp_path, monkeypatch):
    """C5b：ts-morph 可用時，TS 找引用給高信心、排除同名干擾（勝過名稱比對）。

    需 node + ts_bridge 已 npm install；不可用則 skip（環境缺 Node 不算測試失敗）。
    """
    if not references.ts_morph_available():
        pytest.skip("ts-morph 橋不可用（無 node 或未 npm install ts_bridge）")
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    repo = tmp_path / "ts"; repo.mkdir()
    _write(repo, "lib_a.ts", "export function helper(x: number) { return x + 1; }\n")
    _write(repo, "lib_b.ts", "export function helper(y: number) { return y - 1; }\n")  # 同名干擾
    _write(repo, "caller.ts",
           "import { helper } from './lib_a';\nexport function run() { return helper(10); }\n")
    codesextant.index_project(str(repo))
    res = codesextant.find_references(str(repo), "helper",
                                 def_path=str(repo / "lib_a.ts"), src_root=str(repo))
    assert res.get("engine") == "ts-morph"
    assert res["language"] == "typescript"
    hc_files = {os.path.basename(h["src_path"]) for h in res["high_confidence"]}
    assert "caller.ts" in hc_files            # 真解析抓到 caller.ts 的呼叫
    assert "lib_b.ts" not in hc_files          # 排除 lib_b 同名干擾（勝過名稱比對的鐵證）
    json.dumps(res, ensure_ascii=False, default=str)


def test_ts_morph_malformed_output_does_not_crash(monkeypatch):
    """M1 回歸：mjs 回畸形 high_confidence（缺 src_path）時不拋 KeyError（永不爆契約）。"""
    monkeypatch.setattr(references, "ts_morph_available", lambda: True)

    class _FakeProc:
        returncode = 0
        stdout = (b'{"high_confidence":[{"line":5},{"src_path":"a.ts","line":3}],'
                  b'"definition":{"path":"x.ts","line":1}}')  # 第一個元素缺 src_path（畸形）
        stderr = b""

    monkeypatch.setattr(references.subprocess, "run", lambda *a, **k: _FakeProc())
    res = references.ts_morph_references("/root", "foo", def_path="/root/x.ts")
    assert res is not None                       # 不拋、不回 None（有合法元素）
    assert len(res["high_confidence"]) == 1      # 畸形元素跳過、合法保留
    assert res["high_confidence"][0]["src_path"].endswith("a.ts")


def test_ts_morph_disabled_by_env(monkeypatch):
    """開關（L0 鐵律 #6）：env CODESEXTANT_TS_MORPH_DISABLED=1 → ts-morph 停用、走 fallback。"""
    monkeypatch.setenv("CODESEXTANT_TS_MORPH_DISABLED", "1")
    assert references.ts_morph_available() is False


def test_c5_review_fixes_abstract_impl_destructure():
    """對抗性 review 抓出的 3 個 table/walk bug，修後回歸測試（_probe2 坐實節點型別）。"""
    # 問題 2：TS abstract class / abstract method 不再漏抓，且掛對 class scope
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

    # 問題 3：解構賦值不再吐 "{a, b}" / "[c, d]" 垃圾符號名，但正常頂層 const 仍收
    de = b"const {a, b} = obj;\nconst [c, d] = arr;\nconst plain = 1;\n"
    names = {s["name"] for s in extract_symbols_from_source(de, "typescript")}
    assert "plain" in names
    assert not any(("{" in n or "[" in n) for n in names), f"不該有解構垃圾名：{names}"

    # 問題 1：Rust impl 內方法 scope 掛到目標型別，不與全域同名函數混淆
    rs = textwrap.dedent('''
        fn method() {}
        impl MyStruct {
          fn method(&self) {}
        }
    ''').encode("utf-8")
    scopes = {(s["name"], s["scope"]) for s in extract_symbols_from_source(rs, "rust")
              if s["name"] == "method"}
    assert ("method", "") in scopes            # 全域 method：scope 空
    assert ("method", "MyStruct") in scopes    # impl 內 method：scope=MyStruct
