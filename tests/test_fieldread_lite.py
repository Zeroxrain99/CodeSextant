"""FieldRead-lite 輸出壓縮層測試（借 user 自創 FieldRead 精髓的 MIT 零依賴版）。

驗證：full/under-budget 不壓、over-budget 按 priority 分配 + 麵包屑、min_keep 保護重要分區、
總量不超 budget、原順序維持、render 麵包屑文字。純函數、零依賴、零 SQLite。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import fieldread_lite as fl  # noqa: E402


def _sec(name, items, priority=1, min_keep=0):
    return fl.Section(name=name, label=name, items=list(items),
                      priority=priority, min_keep=min_keep)


class TestCompress:
    def test_full_no_compress(self):
        out = fl.compress([_sec("a", range(100))], budget=10, full=True)
        assert out[0].shown == list(range(100)) and out[0].elided == 0

    def test_under_budget_no_compress(self):
        out = fl.compress([_sec("a", [1, 2, 3])], budget=10)
        assert out[0].shown == [1, 2, 3] and out[0].elided == 0

    def test_over_budget_compresses_with_elided(self):
        out = fl.compress([_sec("a", range(20))], budget=5)
        assert len(out[0].shown) == 5
        assert out[0].elided == 15
        assert out[0].total == 20

    def test_budget_respected_across_sections(self):
        out = fl.compress([_sec("a", range(20)), _sec("b", range(20))], budget=10)
        assert sum(len(c.shown) for c in out) <= 10

    def test_high_priority_keeps_more(self):
        out = fl.compress([_sec("hi", range(20), priority=10),
                           _sec("lo", range(20), priority=1)], budget=11)
        by = {c.name: len(c.shown) for c in out}
        assert by["hi"] > by["lo"], by

    def test_min_keep_protects_important(self):
        # crit 雖低 priority，但 min_keep=3 → 至少留 3，不被高 priority 擠掉
        out = fl.compress([_sec("hi", range(50), priority=10),
                           _sec("crit", range(10), priority=1, min_keep=3)], budget=10)
        by = {c.name: len(c.shown) for c in out}
        assert by["crit"] >= 3, by

    def test_order_preserved(self):
        out = fl.compress([_sec("a", [1]), _sec("b", [2]), _sec("c", [3])], budget=2)
        assert [c.name for c in out] == ["a", "b", "c"]

    def test_empty_section(self):
        out = fl.compress([_sec("a", []), _sec("b", range(10))], budget=3)
        assert out[0].total == 0 and out[0].shown == []

    def test_budget_zero_only_min_keep(self):
        out = fl.compress([_sec("a", range(10), min_keep=2)], budget=0)
        assert len(out[0].shown) == 2 and out[0].elided == 8

    def test_shown_is_prefix(self):
        # 壓縮保留的是前綴（呼叫端已先排好序：重要的在前）
        out = fl.compress([_sec("a", range(20))], budget=5)
        assert out[0].shown == [0, 1, 2, 3, 4]


class TestRender:
    def test_breadcrumb_text(self):
        lines = fl.render([fl.Section("callers", "被呼叫鏈", list(range(20)))], budget=5)
        joined = "\n".join(lines)
        assert "省略" in joined and "--full" in joined

    def test_full_no_breadcrumb(self):
        lines = fl.render([fl.Section("a", "A", [1, 2, 3])], budget=2, full=True)
        assert "省略" not in "\n".join(lines)

    def test_empty_section_skipped(self):
        assert fl.render([fl.Section("a", "A", [])], budget=5) == []

    def test_item_fmt_applied(self):
        lines = fl.render([fl.Section("a", "A", [{"n": 1}])], budget=5,
                          item_fmt=lambda x: f"item-{x['n']}")
        assert any("item-1" in ln for ln in lines)
