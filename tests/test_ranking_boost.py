"""競品吸收 queue 4+5：query-aware PageRank（personalization）+ 邊權重符號品質 multipliers。

純算法單元測試（不碰 SQLite/daemon）。
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import ranking  # noqa: E402


def _sym(name, line, path="a.py"):
    return {"path": path, "name": name, "line": line, "end_line": line + 1,
            "scope": "", "kind": "function"}


# ─────────────── queue 5：符號品質係數 ───────────────
class TestSymbolQuality:
    def test_private_underscore_low(self):
        assert ranking._symbol_quality_mult("_helper", 1) < 1.0

    def test_wellnamed_public_high(self):
        assert ranking._symbol_quality_mult("calculate_total", 1) > 1.0

    def test_common_symbol_low(self):
        # 過於常見（>門檻 檔定義）→ 打折，即使 well-named
        assert ranking._symbol_quality_mult("calculate_total", 10) < ranking._symbol_quality_mult("calculate_total", 1)

    def test_short_plain_neutral(self):
        # 短名、非私有、非常見、非 well-named → 1.0
        assert ranking._symbol_quality_mult("run", 1) == 1.0

    def test_env_tunable(self, monkeypatch):
        monkeypatch.setenv("CODESEXTANT_RANK_PRIVATE_MULT", "0.5")
        assert abs(ranking._symbol_quality_mult("_x", 1) - 0.5) < 1e-9


class TestWellNamed:
    def test_snake(self):
        assert ranking._well_named("get_value")

    def test_camel(self):
        assert ranking._well_named("getValue")

    def test_pascal(self):
        assert ranking._well_named("MyClass")

    def test_private_not(self):
        assert not ranking._well_named("_x")

    def test_alllower_noseparator_not(self):
        assert not ranking._well_named("run")


# ─────────────── queue 4：personalization / query-aware ───────────────
class TestPersonalization:
    def test_none_when_no_focus(self):
        assert ranking._build_personalization([_sym("x", 1)], None, None) is None

    def test_focus_symbol_boosted(self):
        syms = [_sym("target", 1), _sym("other", 2)]
        p = ranking._build_personalization(syms, ["target"], None)
        assert p[ranking._symbol_id(syms[0])] > p[ranking._symbol_id(syms[1])]

    def test_focus_file_boosted(self):
        syms = [_sym("a", 1, "hot.py"), _sym("b", 2, "cold.py")]
        p = ranking._build_personalization(syms, None, ["hot.py"])
        assert p[ranking._symbol_id(syms[0])] > p[ranking._symbol_id(syms[1])]


class TestQueryAwarePageRank:
    def test_focus_raises_rank(self):
        # 無引用邊時純 teleport 決定排序——focus 符號 rank 應高於無 focus
        syms = [_sym("alpha", 1), _sym("beta", 3)]
        refs = []
        base = ranking.compute_pagerank(syms, refs)
        focused = ranking.compute_pagerank(
            syms, refs,
            personalization=ranking._build_personalization(syms, ["alpha"], None))
        aid = ranking._symbol_id(syms[0])
        assert focused[aid] > base[aid]

    def test_no_personalization_backward_compat(self):
        # 不傳 personalization＝原靜態行為（分數和 ~1.0、決定性）
        syms = [_sym("a", 1), _sym("b", 3)]
        scores = ranking.compute_pagerank(syms, [])
        assert len(scores) == 2
        assert all(v > 0 for v in scores.values())

    def test_rank_symbols_focus_param(self):
        syms = [_sym("alpha", 1), _sym("beta", 3)]
        ranked = ranking.rank_symbols(syms, [], focus_symbols=["alpha"])
        assert ranked[0]["name"] == "alpha"  # focus 的排最前

    def test_repeated_name_edges_are_aggregated_before_iteration(self):
        """名稱圖的重複 occurrence 只應改權重，不該讓每輪重走五萬筆。"""
        syms = [_sym("caller", 1, "caller.py"), _sym("target", 1, "target.py")]
        edge = {
            "src_path": "caller.py", "src_line": 1,
            "def_path": "target.py", "def_line": 1,
            "confidence": "low",
        }
        started = time.perf_counter()
        scores = ranking.compute_pagerank(
            syms, [edge] * 50_000, max_iter=100, tol=0)
        elapsed = time.perf_counter() - started
        assert scores[ranking._symbol_id(syms[1])] > scores[ranking._symbol_id(syms[0])]
        assert elapsed < 2.0, f"duplicate edges were replayed each iteration ({elapsed:.2f}s)"

    def test_aggregated_multiplicity_matches_expanded_occurrences(self):
        """namegraph 可先折邊，但 multiplicity 必須保持原本 occurrence 權重。"""
        syms = [
            _sym("caller", 1, "caller.py"),
            _sym("target_a", 1, "a.py"),
            _sym("target_b", 1, "b.py"),
        ]
        edge_a = {
            "src_path": "caller.py", "src_line": 1,
            "def_path": "a.py", "def_line": 1, "confidence": "low",
        }
        edge_b = {
            "src_path": "caller.py", "src_line": 1,
            "def_path": "b.py", "def_line": 1, "confidence": "low",
        }
        expanded = ranking.compute_pagerank(syms, [edge_a, edge_a, edge_a, edge_b])
        aggregated = ranking.compute_pagerank(
            syms, [dict(edge_a, multiplicity=3), edge_b])
        assert aggregated == expanded

    def test_sparse_graph_does_not_iterate_every_isolated_node(self):
        """大型索引多數節點無邊時，PageRank 每輪只能走 active graph，不得掃十萬孤點。"""
        syms = [
            _sym("caller", 1, "caller.py"),
            _sym("target", 1, "target.py"),
        ]
        syms.extend(
            _sym(f"isolated_{i}", i + 1, "isolated.py")
            for i in range(100_000)
        )
        edge = {
            "src_path": "caller.py", "src_line": 1,
            "def_path": "target.py", "def_line": 1,
            "confidence": "low",
        }
        started = time.perf_counter()
        scores = ranking.compute_pagerank(syms, [edge], max_iter=100, tol=0)
        elapsed = time.perf_counter() - started
        assert scores[ranking._symbol_id(syms[1])] > scores[ranking._symbol_id(syms[2])]
        assert elapsed < 1.5, f"isolated nodes were revisited every iteration ({elapsed:.2f}s)"

    def test_sparse_math_matches_dense_reference(self):
        """active/inactive 聚合必須與舊 dense 公式一致，含 dangling、focus 與外部入流。"""
        syms = [
            _sym("caller", 1, "caller.py"),
            _sym("a", 1, "a.py"),
            _sym("b", 1, "b.py"),
            _sym("iso", 1, "iso.py"),
        ]
        refs = [
            {"src_path": "caller.py", "src_line": 1,
             "def_path": "a.py", "def_line": 1, "confidence": "high"},
            {"src_path": "caller.py", "src_line": 1,
             "def_path": "b.py", "def_line": 1, "confidence": "high"},
            {"src_path": "a.py", "src_line": 1,
             "def_path": "b.py", "def_line": 1, "confidence": "high"},
            {"src_path": "missing.py", "src_line": 1,
             "def_path": "a.py", "def_line": 1, "confidence": "high"},
        ]
        personalization = {ranking._symbol_id(syms[3]): 11.0}
        actual = ranking.compute_pagerank(
            syms, refs, personalization=personalization, tol=1e-12)

        damping = 0.85
        p = [1 / 14, 1 / 14, 1 / 14, 11 / 14]
        score = list(p)
        transitions = {0: [(1, 0.5), (2, 0.5)], 1: [(2, 1.0)]}
        for _ in range(100):
            new = [(1 - damping) * value for value in p]
            dangling = score[2] + score[3]
            for source, edges in transitions.items():
                for target, portion in edges:
                    new[target] += damping * score[source] * portion
            for i in range(4):
                new[i] += damping * dangling * p[i]
            new[1] += damping / len(refs)  # missing.py → a 的 external inflow
            delta = sum(abs(new[i] - score[i]) for i in range(4))
            score = new
            if delta < 1e-12:
                break

        for i, sym in enumerate(syms):
            assert actual[ranking._symbol_id(sym)] == pytest.approx(score[i], abs=1e-12)
