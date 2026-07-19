"""序3 死碼線索層測試 — 紅藍 CBUA 最佳解的安全閘回歸。

核心要守的不變式（紅隊定調）：
  - 紅隊 B2：真解析引擎不可用時，⛔ 不可有任何 LIKELY_UNUSED（否則把無引擎的專案每個
    export 標可刪＝災難）→ 全 UNKNOWN_NO_RESOLVER。
  - 假陽性回歸（2026-06-19 序3 實跑 daemon.py SERVICE_NAME）：jedi 二段式定位不到的 module
    級變數，high=0 不代表真沒引用 → 必須 UNKNOWN_UNRESOLVED、⛔ 不可 LIKELY_UNUSED。
  - 無 linter（ruff/eslint）→ UNKNOWN_NO_LINTER（誠實），⛔ 不退化成自造 AST 假陽性。
  - entrypoint（pages/test_/裝飾器/__all__）→ PUBLIC_API、永不進刪除候選。
  - 只有「真解析 + 定位到定義 + high=0」才敢給 LIKELY_UNUSED🟡。

全自包含、可重複（照 test_hardening.py 風格：CODESEXTANT_HOME 隔離庫）。
"""
import os
import shutil
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import deadcode, engine  # noqa: E402


@pytest.fixture()
def db_home(tmp_path, monkeypatch):
    """隔離庫目錄，避免污染真實 ~/.codesextant。"""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))


def _write(root, rel, content):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


def _by_name(result):
    return {o["name"]: o["verdict"] for o in result["orphans"]}


# ─────────────── classify_orphan 純單元（最快、最直接守不變式）───────────────
class TestClassifyOrphan:
    def test_entry_always_public(self):
        v = deadcode.classify_orphan({"engine": "jedi", "definition": None},
                                     is_entry=True, entry_reason="route")
        assert v["verdict"] == "PUBLIC_API"

    def test_no_engine_unknown_no_resolver(self):
        # 安全閘①：無真解析引擎 → 不判可刪
        v = deadcode.classify_orphan({}, is_entry=False, entry_reason=None)
        assert v["verdict"] == "UNKNOWN_NO_RESOLVER"

    def test_name_match_engine_unknown(self):
        v = deadcode.classify_orphan({"engine": "name-match", "high_confidence": []},
                                     is_entry=False, entry_reason=None)
        assert v["verdict"] == "UNKNOWN_NO_RESOLVER"

    def test_error_unknown_unresolved(self):
        # 安全閘②：真解析了但 error（沒定位到定義）→ UNKNOWN，不是 LIKELY_UNUSED
        v = deadcode.classify_orphan({"engine": "jedi", "error": "找不到 def/class 定義行"},
                                     is_entry=False, entry_reason=None)
        assert v["verdict"] == "UNKNOWN_UNRESOLVED"

    def test_no_definition_unknown_unresolved(self):
        v = deadcode.classify_orphan(
            {"engine": "jedi", "definition": None, "high_confidence": []},
            is_entry=False, entry_reason=None)
        assert v["verdict"] == "UNKNOWN_UNRESOLVED"

    def test_high_confidence_keep(self):
        v = deadcode.classify_orphan(
            {"engine": "jedi", "definition": {"path": "x", "line": 1},
             "high_confidence": [{"src_path": "y", "line": 2}]},
            is_entry=False, entry_reason=None)
        assert v["verdict"] == "KEEP"

    def test_zero_high_with_def_likely_unused(self):
        # 只有「真解析 + 有定義 + high=0」才敢 LIKELY_UNUSED
        v = deadcode.classify_orphan(
            {"engine": "jedi", "definition": {"path": "x", "line": 1}, "high_confidence": []},
            is_entry=False, entry_reason=None)
        assert v["verdict"] == "LIKELY_UNUSED"


# ─────────────── is_entrypoint 純單元 ───────────────
class TestIsEntrypoint:
    def test_pages_route(self):
        ok, _ = deadcode.is_entrypoint("E:/x/pages/index.tsx")
        assert ok

    def test_app_router(self):
        ok, _ = deadcode.is_entrypoint("E:/x/app/users/route.ts")
        assert ok

    def test_test_file(self):
        ok, _ = deadcode.is_entrypoint("E:/x/test_foo.py")
        assert ok

    def test_main_module(self):
        ok, _ = deadcode.is_entrypoint("E:/x/pkg/__main__.py")
        assert ok

    def test_decorator(self):
        src = "@app.route('/x')\ndef handler():\n    pass\n"
        ok, _ = deadcode.is_entrypoint("E:/x/api.py", symbol_name="handler", source=src)
        assert ok

    def test_pytest_fixture_decorator(self):
        src = "@pytest.fixture\ndef client():\n    pass\n"
        ok, _ = deadcode.is_entrypoint("E:/x/conftest_like.py", symbol_name="client", source=src)
        assert ok

    def test_dunder_all(self):
        src = "__all__ = ['pub', 'other']\ndef pub():\n    pass\n"
        ok, _ = deadcode.is_entrypoint("E:/x/mod.py", symbol_name="pub", source=src)
        assert ok

    def test_plain_helper_not_entry(self):
        ok, _ = deadcode.is_entrypoint("E:/x/util.py", symbol_name="helper",
                                       source="def helper():\n    pass\n")
        assert not ok

    def test_extra_env(self, monkeypatch):
        monkeypatch.setenv("CODESEXTANT_DEADCODE_ENTRYPOINT_EXTRA", "myroutes")
        ok, reason = deadcode.is_entrypoint("E:/x/myroutes/h.py")
        assert ok and "使用者指定" in reason


# ─────────────── unused-import（ruff）───────────────
class TestUnusedImport:
    def test_ruff_catches_unused(self, tmp_path, db_home):
        if shutil.which("ruff") is None:
            pytest.skip("ruff 未裝，跳過真值測試")
        f = _write(tmp_path, "mod.py", """
            import os
            import sys

            def f():
                return sys.path
        """)
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        ui = r["unused_imports"]
        assert ui["available"] is True
        codes = [x["code"] for x in ui["findings"]]
        assert "F401" in codes  # os 未使用

    def test_linter_off_switch(self, tmp_path, db_home, monkeypatch):
        monkeypatch.setenv("CODESEXTANT_DEADCODE_LINTER", "off")
        f = _write(tmp_path, "mod.py", "import os\n")
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        assert r["unused_imports"]["available"] is False

    def test_no_linter_unknown_not_fabricated(self, tmp_path, db_home, monkeypatch):
        # ruff 不在 PATH → UNKNOWN_NO_LINTER（誠實），⛔ 不假裝掃乾淨、不自造 AST
        monkeypatch.setattr(deadcode.shutil, "which", lambda name: None)
        f = _write(tmp_path, "mod.py", "import os\n")
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        ui = r["unused_imports"]
        assert ui["available"] is False
        assert ui.get("verdict") == "UNKNOWN_NO_LINTER"


# ─────────────── orphan 分級（Python jedi 真解析）───────────────
class TestOrphanPython:
    def test_real_orphan_likely_unused(self, tmp_path, db_home):
        # 驗收(d)：真死 function（零引用）→ LIKELY_UNUSED；被呼叫的 → KEEP
        f = _write(tmp_path, "mod.py", """
            def used():
                return 1

            def dead_orphan():
                return 2

            def caller():
                return used()
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        by = _by_name(r)
        assert by["dead_orphan"] == "LIKELY_UNUSED"
        assert by["used"] == "KEEP"

    def test_module_var_unknown_not_likely(self, tmp_path, db_home):
        # 假陽性回歸（序3 daemon.py SERVICE_NAME）：module 級變數 → UNKNOWN_UNRESOLVED
        f = _write(tmp_path, "consts.py", """
            SERVICE = "x"

            def reader():
                return SERVICE
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        by = _by_name(r)
        assert by["SERVICE"] == "UNKNOWN_UNRESOLVED"
        assert by["SERVICE"] != "LIKELY_UNUSED"

    def test_entrypoint_decorator_public_api(self, tmp_path, db_home):
        # 驗收(c)：帶 @app.route → PUBLIC_API（即使靜態零引用也不進刪除候選）
        f = _write(tmp_path, "api.py", """
            app = object()

            @app.route("/x")
            def handler():
                return 1
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        by = _by_name(r)
        assert by["handler"] == "PUBLIC_API"

    def test_entrypoint_filename_public_api(self, tmp_path, db_home):
        # 驗收(c)：test_*.py 的符號 → PUBLIC_API
        f = _write(tmp_path, "test_thing.py", """
            def test_something():
                assert True
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        by = _by_name(r)
        assert by["test_something"] == "PUBLIC_API"

    def test_dunder_all_public_api(self, tmp_path, db_home):
        f = _write(tmp_path, "pkg.py", """
            __all__ = ["exported"]

            def exported():
                return 1
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        by = _by_name(r)
        assert by["exported"] == "PUBLIC_API"


# ─────────────── 紅隊 B2：無真解析引擎 → 零 LIKELY_UNUSED（最關鍵安全閘）───────────────
class TestB2SafetyGate:
    def test_ts_without_tsmorph_no_likely_unused(self, tmp_path, db_home, monkeypatch):
        # 紅隊 B2 核心：ts-morph 不可用時，TS 檔 orphan 必須全 UNKNOWN_NO_RESOLVER，
        # ⛔ 不可有任何 LIKELY_UNUSED（否則把無引擎的 TS 專案每個 export 標可刪＝災難）。
        monkeypatch.setenv("CODESEXTANT_TS_MORPH_DISABLED", "1")  # 強制 ts-morph 不可用
        f = _write(tmp_path, "mod.ts", """
            export function deadFn() { return 1; }
            export const X = 2;
            export class Thing {}
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        verdicts = [o["verdict"] for o in r["orphans"]]
        assert verdicts, "應有頂層符號被分級"
        assert "LIKELY_UNUSED" not in verdicts, verdicts
        assert all(v == "UNKNOWN_NO_RESOLVER" for v in verdicts), verdicts

    def test_resolver_available_python_always(self):
        ok, _ = deadcode.resolver_available("python")
        assert ok

    def test_resolver_available_unknown_lang(self):
        ok, reason = deadcode.resolver_available("rust")
        assert not ok and reason

    def test_resolver_available_ts_respects_switch(self, monkeypatch):
        monkeypatch.setenv("CODESEXTANT_TS_MORPH_DISABLED", "1")
        ok, _ = deadcode.resolver_available("typescript")
        assert not ok


# ─────────────── find_deadcode 整體契約 ───────────────
class TestFindDeadcodeContract:
    def test_has_verification_reminder(self, tmp_path, db_home):
        f = _write(tmp_path, "mod.py", "def f():\n    return 1\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        assert "verification_reminder" in r and r["verification_reminder"]
        assert "build" in r["verification_reminder"]

    def test_no_scope_file_skips_orphan(self, tmp_path, db_home):
        _write(tmp_path, "mod.py", "import os\ndef f():\n    return 1\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path))  # 不給 scope_file
        assert r["orphans"] == []
        assert r["scope_file"] is None

    def test_bad_path_raises(self, db_home):
        with pytest.raises(NotADirectoryError):
            engine.find_deadcode("E:/__no_such_dir_codesextant__")


# ─────────────── 序4+5：TS 真解析 / barrel re-export / batch（需 node+ts-morph）───────────────
class TestSeq4Seq5TsMorph:
    @pytest.fixture(autouse=True)
    def _need_tsmorph(self):
        from codesextant import references
        if not references.ts_morph_available():
            pytest.skip("node/ts-morph 不可用，跳過 TS 真解析測試")

    def test_reexport_only(self, tmp_path, db_home):
        # 序4：符號只被 barrel re-export（無真消費）→ REEXPORT_ONLY、⛔ 不誤判 LIKELY_UNUSED
        _write(tmp_path, "foo.ts", "export function onlyReexported() { return 1; }\n")
        _write(tmp_path, "barrel.ts", "export { onlyReexported } from './foo';\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=str(tmp_path / "foo.ts"))
        assert _by_name(r)["onlyReexported"] == "REEXPORT_ONLY"

    def test_real_consumer_keep(self, tmp_path, db_home):
        # 真被 import 消費 → KEEP（即使也被 re-export）
        _write(tmp_path, "bar.ts", "export function reallyUsed() { return 2; }\n")
        _write(tmp_path, "consumer.ts",
               "import { reallyUsed } from './bar';\n"
               "export function c() { return reallyUsed(); }\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=str(tmp_path / "bar.ts"))
        assert _by_name(r)["reallyUsed"] == "KEEP"

    def test_true_orphan_ts_likely_unused(self, tmp_path, db_home):
        # TS 真死（export 了、沒人 import、沒 re-export）→ LIKELY_UNUSED
        _write(tmp_path, "dead.ts", "export function deadTs() { return 3; }\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=str(tmp_path / "dead.ts"))
        assert _by_name(r)["deadTs"] == "LIKELY_UNUSED"

    def test_batch_matches_single(self, tmp_path, db_home):
        # 序5：batch 一次查多符號的結果，與逐符號單查一致（同一引用數）
        from codesextant import references
        _write(tmp_path, "m.ts",
               "export function a() { return 1; }\n"
               "export function b() { return a(); }\n")
        root, deffile = str(tmp_path), str(tmp_path / "m.ts")
        batch = references.ts_morph_references_batch(root, deffile, ["a", "b"])
        single_a = references.ts_morph_references(root, "a", def_path=deffile)
        assert batch is not None and single_a is not None
        assert len(batch["a"]["high_confidence"]) == len(single_a["high_confidence"])
        assert batch["a"]["high_confidence"], "a 被 b 呼叫，應有高信心引用"

    def test_batch_unknown_when_disabled(self, tmp_path, db_home, monkeypatch):
        # ts-morph 關閉時 batch 回 None（呼叫端據此走 UNKNOWN，不假裝有結果）
        from codesextant import references
        monkeypatch.setenv("CODESEXTANT_TS_MORPH_DISABLED", "1")
        _write(tmp_path, "m.ts", "export function a() { return 1; }\n")
        assert references.ts_morph_references_batch(
            str(tmp_path), str(tmp_path / "m.ts"), ["a"]) is None


# ─────────────── 序6：自我邊界感知（reliability 自評 + read_code_advisory 盲區攤開）───────────────
class TestSeq6Boundary:
    def test_refs_reliability_present(self, tmp_path, db_home):
        _write(tmp_path, "m.py", "def used():\n    return 1\n\n\ndef caller():\n    return used()\n")
        engine.index_project(str(tmp_path))
        r = engine.find_references(str(tmp_path), "used", src_root=str(tmp_path))
        assert "reliability" in r
        assert r["reliability"].get("level") in ("high", "medium", "low")
        assert r["reliability"].get("advice")

    def test_reliability_name_match_low(self):
        # name-match 引擎（無真解析）→ low，務必讀碼
        rel = engine._refs_reliability(
            {"engine": "name-match", "definition": {"path": "x"}, "high_confidence": [{"x": 1}]})
        assert rel["level"] == "low"

    def test_reliability_no_def_low(self):
        rel = engine._refs_reliability(
            {"engine": "jedi", "definition": None, "high_confidence": [], "low_confidence": []})
        assert rel["level"] == "low"

    def test_reliability_zero_refs_medium(self):
        # 真解析零引用 → medium（可能動態/反射呼叫看不到，讀碼確認）
        rel = engine._refs_reliability(
            {"engine": "jedi", "definition": {"path": "x"},
             "high_confidence": [], "low_confidence": []})
        assert rel["level"] == "medium"

    def test_reliability_high(self):
        rel = engine._refs_reliability(
            {"engine": "jedi", "definition": {"path": "x"},
             "high_confidence": [{"a": 1}, {"b": 2}], "low_confidence": []})
        assert rel["level"] == "high"

    def test_deadcode_advisory_present_and_nonempty(self, tmp_path, db_home):
        f = _write(tmp_path, "m.py", "def a():\n    return 1\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        assert isinstance(r.get("read_code_advisory"), list) and r["read_code_advisory"]

    def test_advisory_flags_unknown(self):
        notes = deadcode.read_code_advisory(
            {"available": True},
            [{"verdict": "UNKNOWN_UNRESOLVED"}, {"verdict": "UNKNOWN_NO_RESOLVER"}])
        assert any("判不出" in n for n in notes)

    def test_advisory_flags_likely_unused(self):
        notes = deadcode.read_code_advisory({"available": True}, [{"verdict": "LIKELY_UNUSED"}])
        assert any("線索非定論" in n for n in notes)

    def test_advisory_flags_no_linter(self):
        notes = deadcode.read_code_advisory({"available": False, "reason": "無 ruff"}, [])
        assert any("無法判定" in n for n in notes)

    def test_advisory_flags_reexport(self):
        notes = deadcode.read_code_advisory({"available": True}, [{"verdict": "REEXPORT_ONLY"}])
        assert any("re-export" in n for n in notes)
