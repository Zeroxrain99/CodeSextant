"""queue 7 接線整合測試 — wrapper 三 formatter（map/callgraph/impact）走 FieldRead-lite 壓縮。

驗收施工圖步驟5：壓縮顯示有麵包屑 + --full 拿完整 + 重要分區（high_importance）min_keep 全留。
從絕對路徑載入 skills 目錄下的 wrapper 模組（純函數、不起 daemon）；fieldread_lite 經
package root（下方 sys.path）解析。
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_WRAPPER = r"C:\Users\zerox\.claude\skills\codesextant\scripts\codesextant_query.py"


def _load_wrapper():
    spec = importlib.util.spec_from_file_location("cs_wrapper_under_test", _WRAPPER)
    mod = importlib.util.module_from_spec(spec)
    # wrapper 內 `from codesextant import fieldread_lite` 靠上面 sys.path 的 package root
    mod._ensure_importable = lambda: ""  # 避免覆寫 sys.path（測試已自備）
    spec.loader.exec_module(mod)
    return mod


W = _load_wrapper()


# ── 假資料工廠 ──
def _sym(i):
    return {"name": f"sym{i}", "kind": "func", "path": f"a/b{i}.py", "line": i, "rank": 0.5}


def _node(name, depth=1, conf="high"):
    return {"name": name, "path": f"x/{name}.py", "line": 10, "depth": depth, "confidence": conf}


class TestMap:
    def _r(self, n):
        return {"symbols": [_sym(i) for i in range(n)], "token_budget": 2000,
                "approx_tokens": 100, "count": n, "note": None}

    def test_compress_breadcrumb(self):
        out = W._fmt_map(self._r(30), budget=5, full=False)
        assert "省略" in out and "--full" in out
        # 只顯示 5 個符號行（序號 1..5），第 6 個不該出現
        assert "  6. " not in out

    def test_full_no_compress(self):
        out = W._fmt_map(self._r(30), budget=5, full=True)
        assert "省略" not in out
        assert "30." in out  # 第 30 個有印

    def test_under_budget_no_breadcrumb(self):
        out = W._fmt_map(self._r(3), budget=40, full=False)
        assert "省略" not in out


class TestCallgraph:
    def _r(self):
        callers = [_node(f"up{i}", depth=1, conf=("high" if i < 3 else "low")) for i in range(20)]
        return {"symbol": "target", "direction": "up", "max_hops": 5,
                "callers": callers, "definition": {"path": "t.py"},
                "candidate_definitions": [], "note": None, "verification_reminder": None}

    def test_compress_breadcrumb(self):
        out = W._fmt_callgraph(self._r(), budget=5, full=False)
        assert "省略" in out and "--full" in out

    def test_full_complete(self):
        out = W._fmt_callgraph(self._r(), budget=5, full=True)
        assert "省略" not in out
        assert "up19" in out  # 全部都在

    def test_high_confidence_first(self):
        # budget 小 → 保前綴；前綴是高信心（up0/up1/up2 conf=high 排最前）
        out = W._fmt_callgraph(self._r(), budget=4, full=False)
        assert "up0" in out and "up1" in out


class TestImpact:
    def _r(self, n_hi=8, n_test=20):
        return {
            "symbol": "core", "definition": {"path": "c.py"},
            "summary": {"total_confirmed_affected": n_hi + n_test, "direct": 5,
                        "transitive": n_hi + n_test - 5, "prod": 3, "test": n_test, "entrypoint": 2},
            "by_kind": {"entrypoint": [_node(f"e{i}") for i in range(2)],
                        "prod": [_node(f"p{i}") for i in range(3)],
                        "test": [_node(f"t{i}") for i in range(n_test)]},
            "high_importance_affected": [_node(f"H{i}") for i in range(n_hi)],
            "uncertain_maybe_affected": [_node(f"u{i}") for i in range(10)],
            "affected_files": [f"f{i}.py" for i in range(20)],
            "note": None, "verification_reminder": None,
        }

    def test_high_importance_min_keep_all(self):
        # budget=2 遠小於 high(8)，但 high min_keep 全留 → 8 個都印（最該看的不被擠掉）
        out = W._fmt_impact(self._r(n_hi=8), budget=2, full=False)
        for i in range(8):
            assert f"H{i}" in out, f"H{i} 應全留（min_keep）但不在輸出"

    def test_low_priority_elided(self):
        # test 分區低 priority → budget 緊時多被省成麵包屑
        out = W._fmt_impact(self._r(n_hi=8, n_test=20), budget=2, full=False)
        assert "省略" in out

    def test_full_complete(self):
        out = W._fmt_impact(self._r(n_hi=8, n_test=20), budget=2, full=True)
        assert "省略" not in out
        assert "t19" in out and "u9" in out  # test/uncertain 全在

    def test_affected_files_truncate(self):
        out = W._fmt_impact(self._r(), budget=40, full=False)
        assert "其餘" in out  # 20 檔 > 15 → 截斷提示
        out_full = W._fmt_impact(self._r(), budget=40, full=True)
        assert "f19.py" in out_full
