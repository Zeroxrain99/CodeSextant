"""namegraph（任務一 map 退化修復）+ find_unwired（功能 A 未接線檢查）測試。

刻意全自包含：每測試建臨時小專案 + 隔離 CODESEXTANT_HOME，可重複、任何機器可跑。

涵蓋：
  - 退化修復驗收（PageRank 脫離均分、被多檔引用的符號 rank 高於孤立符號）。
  - 核心約束：名稱級邊**不落 refs 表**（callgraph/impact/refs 零影響）。
  - env 開關（CODESEXTANT_NAMEGRAPH_DISABLED 退回退化、MAX_FANOUT 防爆）。
  - compute_external_usage body-aware（定義行/遞迴自呼叫不算 external、同檔 helper 不誤報）。
  - find_unwired 各分支（真未接線抓到、helper/跨檔引用不誤報、entrypoint/dunder/method 豁免、
    氾濫名 UNKNOWN_FANOUT、未索引 raise、誠實欄位、JSON 可序列化、跨語言）。
"""
import json
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine, namegraph, storage  # noqa: E402


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """建臨時專案 + 隔離 CODESEXTANT_HOME。回傳專案根路徑（str）。"""
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


def _ranks(m):
    return {s["name"]: s["rank"] for s in m["symbols"]}


def _distinct_ranks(m):
    return len(set(round(s["rank"], 10) for s in m["symbols"]))


# ─────────────── 退化修復驗收（任務一核心） ───────────────

def test_namegraph_fixes_pagerank_degeneration(project):
    """修復前 PageRank 全均分；名稱級邊讓被多檔引用的 hub rank 高於孤立的 lonely。"""
    _write(project, "core.py", "def hub():\n    return 1\n\ndef lonely():\n    return 0\n")
    _write(project, "a.py", "from core import hub\ndef ua():\n    return hub()\n")
    _write(project, "b.py", "from core import hub\ndef ub():\n    return hub()\n")
    _write(project, "c.py", "from core import hub\ndef uc():\n    return hub()\n")
    engine.index_project(project, force=True)
    m = engine.get_map(project, token_budget=2000)
    assert m["edge_sources"]["name_low_edges"] > 0
    assert _distinct_ranks(m) > 1                 # 不再均勻退化
    r = _ranks(m)
    assert r["hub"] > r["lonely"]                 # 被 3 檔引用 > 沒人引用


def test_namegraph_disabled_reverts_to_degeneration(project, monkeypatch):
    """CODESEXTANT_NAMEGRAPH_DISABLED=1 → 不建名稱級邊、退回均分退化。"""
    _write(project, "core.py", "def hub():\n    return 1\n")
    _write(project, "a.py", "from core import hub\ndef ua():\n    return hub()\n")
    engine.index_project(project, force=True)
    monkeypatch.setenv("CODESEXTANT_NAMEGRAPH_DISABLED", "1")
    m = engine.get_map(project, token_budget=2000)
    assert m["edge_sources"]["name_low_edges"] == 0
    assert _distinct_ranks(m) == 1                # 退回退化（全相等）


def test_namegraph_does_not_pollute_refs_table(project):
    """核心約束：名稱級邊 in-memory only、絕不落 refs 表（保護 callgraph/impact/refs）。"""
    _write(project, "core.py", "def hub():\n    return 1\n")
    _write(project, "a.py", "from core import hub\ndef ua():\n    return hub()\n")
    engine.index_project(project, force=True)
    engine.get_map(project, token_budget=2000)    # 觸發建名稱級邊
    with storage.ProjectStore.open(project) as st:
        assert len(st.all_refs()) == 0            # refs 表仍空（名稱級邊不落盤）


def test_get_map_mixes_db_high_and_name_low_edges(project):
    """db 高信心邊（find_references persist）+ 名稱級 low 邊 混合餵 PageRank。"""
    _write(project, "core.py", "def hub():\n    return 1\n")
    _write(project, "a.py", "from core import hub\ndef ua():\n    return hub()\n")
    engine.index_project(project, force=True)
    engine.find_references(project, "hub", persist=True)   # 建 high 邊
    m = engine.get_map(project, token_budget=2000)
    assert m["edge_sources"]["db_high_edges"] > 0
    assert m["edge_sources"]["name_low_edges"] > 0


# ─────────────── namegraph 核心（build_name_edges） ───────────────

def test_build_name_edges_low_confidence_and_skips_undefined(project):
    """名稱級邊全 low 信心；只對「已定義名」建邊（未定義名/內建名不建）。"""
    _write(project, "core.py", "def hub():\n    return 1\n")
    _write(project, "use.py",
           "from core import hub\ndef caller():\n    hub()\n    print('externalname')\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
        indexed = st.all_indexed_files()
    edges, meta = namegraph.build_name_edges(syms, indexed_files=indexed)
    assert edges and all(e["confidence"] == "low" for e in edges)
    assert any(e["symbol_name"] == "hub" for e in edges)
    assert not any(e["symbol_name"] in ("print", "externalname") for e in edges)


def test_build_name_edges_fanout_to_all_same_name_defs(project):
    """同名定義 fan-out：名 X 被引用 → 連到所有定義 X 的檔（compute_pagerank 對接需求）。"""
    _write(project, "a.py", "def shared():\n    return 1\n")
    _write(project, "b.py", "def shared():\n    return 2\n")
    _write(project, "use.py", "def caller():\n    return shared()\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
        indexed = st.all_indexed_files()
    edges, _ = namegraph.build_name_edges(syms, indexed_files=indexed)
    def_paths = {os.path.basename(e["def_path"]) for e in edges if e["symbol_name"] == "shared"}
    assert def_paths == {"a.py", "b.py"}          # fan-out 到兩個同名定義


def test_build_name_edges_respects_max_fanout(project):
    """同名定義數 > max_fanout → 不建該名的邊（防氾濫名笛卡兒積爆邊）。"""
    for i in range(5):
        _write(project, f"d{i}.py", "def dup():\n    return 0\n")
    _write(project, "use.py", "def caller():\n    return dup()\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
        indexed = st.all_indexed_files()
    edges, meta = namegraph.build_name_edges(syms, indexed_files=indexed, max_fanout=3)
    assert not any(e["symbol_name"] == "dup" for e in edges)
    assert meta["skipped_fanout_names"] >= 1


def test_build_name_edges_aggregates_same_line_occurrences(project):
    """同一 caller 行重複名稱折成一邊；multiplicity 保留真實引用次數。"""
    core = _write(project, "core.py", "def hub():\n    return 1\n")
    use = _write(project, "use.py", "def caller():\n    return hub() + hub() + hub()\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
    edges, meta = namegraph.build_name_edges(
        syms, indexed_files=[core, use])
    hub_edges = [e for e in edges if e["symbol_name"] == "hub"]
    assert len(hub_edges) == 1
    assert hub_edges[0]["multiplicity"] == 3
    assert meta["unique_edges"] == 1
    assert meta["total_edges"] == 3


def test_large_map_file_limit_is_adaptive_but_env_can_override(monkeypatch):
    """大型索引預設縮小即時計算工作量；顯式 env 仍是最高權威。"""
    monkeypatch.delenv("CODESEXTANT_NAMEGRAPH_MAX_FILES", raising=False)
    limit, adaptive = namegraph.map_file_limit(570_651)
    assert adaptive is True
    assert 12 <= limit < 40
    monkeypatch.setenv("CODESEXTANT_NAMEGRAPH_MAX_FILES", "123")
    assert namegraph.map_file_limit(570_651) == (123, False)


def test_namegraph_truncation_samples_across_repo_not_only_prefix(tmp_path):
    """檔數超限時做決定性分層取樣，避免大型 monorepo 永遠只看排序前綴。"""
    target = str(tmp_path / "target.py")
    symbols = [{
        "path": target, "name": "hub", "line": 1, "end_line": 1,
        "scope": "", "kind": "function",
    }]
    files = [str(tmp_path / f"part_{i:02d}.py") for i in range(10)]
    visited = []

    def fake_read(path):
        visited.append(path)
        return "hub()\n"

    _edges, meta = namegraph.build_name_edges(
        symbols, indexed_files=files, read_text=fake_read, max_files=3)
    assert meta["total_files"] == 10
    assert meta["scanned_files"] == 3
    assert meta["truncated"] is True
    assert meta["sampling"] == "stratified"
    assert set(visited) != {namegraph._normp(p) for p in files[:3]}


def test_namegraph_unique_edge_budget_stops_growth(project, monkeypatch):
    """惡性 generated code 不得讓單次 map 的 edge dict 無界吃光 RAM。"""
    monkeypatch.setenv("CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES", "2")
    _write(project, "core.py", "def a():\n    return 1\ndef b():\n    return 2\ndef c():\n    return 3\n")
    _write(project, "use.py", "def caller():\n    a()\n    b()\n    c()\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
        indexed = st.all_indexed_files()
    edges, meta = namegraph.build_name_edges(syms, indexed_files=indexed)
    assert len(edges) <= 2
    assert meta["truncated"] is True
    assert "edge_budget" in meta["truncation_reasons"]


def test_get_map_caches_same_revision_and_reindex_invalidates(project, monkeypatch):
    """daemon 長駐時同一 revision 不重算；索引一更新就必須 miss，不能回舊地圖。"""
    _write(project, "core.py", "def hub():\n    return 1\n")
    _write(project, "use.py", "def caller():\n    return hub()\n")
    engine.index_project(project, force=True)
    engine._MAP_CACHE.clear()
    calls = 0
    real_rank = engine.rank_symbols

    def counted_rank(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_rank(*args, **kwargs)

    monkeypatch.setattr(engine, "rank_symbols", counted_rank)
    first = engine.get_map(project, token_budget=120)
    engine._MAP_CACHE.clear()  # 模擬 daemon 重啟：process LRU 消失，disk cache 必須仍可命中
    second = engine.get_map(project, token_budget=120)
    assert calls == 1
    assert first["edge_sources"]["map_cache_hit"] is False
    assert second["edge_sources"]["map_cache_hit"] is True
    assert second["edge_sources"]["map_cache_source"] == "disk"

    _write(project, "core.py", "def hub():\n    return 2\n\ndef added():\n    return 3\n")
    engine.index_project(project, force=True)
    third = engine.get_map(project, token_budget=120)
    assert calls == 2
    assert third["edge_sources"]["map_cache_hit"] is False
    assert third["edge_sources"]["map_cache_source"] == "compute"


def test_symbol_snapshot_roundtrip_and_revision_invalidation(project):
    """JSON snapshot 必須精確 roundtrip；任一重新索引後舊 revision 絕不能被載入。"""
    _write(project, "core.py", "def hub():\n    return 1\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        symbols_before = st.get_symbols()
        revision = st.symbol_revision()
        snapshot = storage.write_symbol_snapshot(
            st.db_file, revision, symbols_before)
        assert snapshot.is_file()
        assert st.load_symbol_snapshot(revision) == symbols_before

    _write(project, "core.py", "def hub():\n    return 2\n\ndef added():\n    return 3\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        assert st.symbol_revision() != revision
        assert st.load_symbol_snapshot(st.symbol_revision()) is None


# ─────────────── compute_external_usage（body-aware） ───────────────

def test_external_usage_body_aware(project):
    """body-aware：定義行 self token + 遞迴自呼叫不算 external；同檔 body 外呼叫算。"""
    _write(project, "m.py", '''
        def helper():
            return 1

        def caller():
            return helper()

        def lonely():
            return 9

        def recur(n):
            return recur(n - 1)
    ''')
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
        indexed = st.all_indexed_files()
    usage, over, _meta = namegraph.compute_external_usage(syms, indexed_files=indexed)
    by_name = {}
    for (p, l, n), c in usage.items():
        by_name.setdefault(n, []).append(c)
    assert max(by_name["helper"]) > 0     # 被同檔 caller 呼叫（body 外）→ 算 external
    assert max(by_name["lonely"]) == 0    # 沒人用 → 0
    assert max(by_name["recur"]) == 0     # 純遞迴自呼叫（body 內）→ 不算 external
    assert over == set()


# ─────────────── find_unwired（功能 A） ───────────────

def test_find_unwired_catches_true_unwired_not_helper(project):
    """真未接線（orphan_func）抓到；同檔 helper（被同檔呼叫）+ 跨檔引用的 caller 不誤報。"""
    _write(project, "m.py", '''
        def helper():
            return 1

        def caller():
            return helper()

        def orphan_func():
            return 99
    ''')
    _write(project, "main.py", "from m import caller\ndef run():\n    return caller()\n")
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    verdicts = {c["name"]: c["verdict"] for c in r["candidates"]}
    assert verdicts.get("orphan_func") == "UNWIRED_CANDIDATE"
    assert "helper" not in verdicts       # 同檔 helper 被同檔 caller 用 → 不誤報
    assert "caller" not in verdicts       # 跨檔被 main 用 → 不誤報


def test_find_unwired_exempts_entrypoint_and_dunder(project):
    """test_ 檔函數 / __all__ 列的 / dunder → 豁免；普通沒人用的 → 候選。"""
    _write(project, "test_x.py", "def test_something():\n    return 1\n")
    _write(project, "app.py", '''
        __all__ = ["public_api"]

        def public_api():
            return 1

        def hidden():
            return 2
    ''')
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    names = {c["name"] for c in r["candidates"]}
    assert "test_something" not in names  # test 檔豁免
    assert "public_api" not in names      # __all__ 豁免
    assert "hidden" in names              # 沒人用、沒豁免 → 候選


def test_find_unwired_skips_methods(project):
    """method/巢狀符號不是頂層未接線候選（只看頂層 referenceable）。"""
    _write(project, "m.py", "class C:\n    def unused_method(self):\n        return 1\n")
    _write(project, "u.py", "from m import C\ndef run():\n    return C()\n")
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    names = {c["name"] for c in r["candidates"]}
    assert "unused_method" not in names


def test_find_unwired_unknown_fanout(project):
    """同名定義過多（>max_fanout）→ UNKNOWN_FANOUT（未建邊不可判、不誤報未接線）。"""
    for i in range(4):
        _write(project, f"d{i}.py", "def dup():\n    return 0\n")
    engine.index_project(project, force=True)
    r = engine.find_unwired(project, max_fanout=2)
    verdicts = {c["verdict"] for c in r["candidates"] if c["name"] == "dup"}
    assert verdicts == {"UNKNOWN_FANOUT"}


def test_find_unwired_unindexed_raises(project):
    """未索引 → RuntimeError（fail-loud）。"""
    with pytest.raises(RuntimeError):
        engine.find_unwired(project)


def test_find_unwired_honest_fields_and_serializable(project):
    """誠實層欄位齊全 + 整個結果可 JSON 序列化（daemon HTTP 要求）。"""
    _write(project, "m.py", "def orphan():\n    return 1\n")
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    assert r.get("verification_reminder")
    assert isinstance(r.get("read_code_advisory"), list) and r["read_code_advisory"]
    assert "summary" in r and "namegraph_meta" in r
    json.dumps(r, ensure_ascii=False, default=str)   # 不可序列化會拋


# ─────────────── 跨語言（namegraph 純 regex、語言無關） ───────────────

def test_namegraph_works_for_typescript(project):
    """名稱級邊純 regex token 化 → 跨語言可用（TS export/import 也能脫離退化）。"""
    _write(project, "core.ts", "export function hub() { return 1; }\n")
    _write(project, "a.ts",
           "import { hub } from './core';\nexport function ua() { return hub(); }\n")
    engine.index_project(project, force=True)
    m = engine.get_map(project, token_budget=2000)
    assert m["edge_sources"]["name_low_edges"] > 0
    r = _ranks(m)
    assert r["hub"] >= r.get("ua", 0)            # 被引用的 hub rank 不低於 ua


# ─────────────── 紅隊 L1-HIGH 回歸：同檔/單模組結構也要脫離均分 ───────────────

def test_intrafile_calls_escape_degeneration_callee_first(project):
    """單檔內被呼叫者『剛好是檔第一符號』也要脫離均分（src_line 映射真 caller、非 file_rep collapse）。"""
    _write(project, "app.py", '''
        def dispatch():
            return 1

        def h1():
            return dispatch()

        def h2():
            return dispatch()

        def h3():
            return dispatch()

        def never_called_dead():
            return 0
    ''')
    engine.index_project(project, force=True)
    m = engine.get_map(project, token_budget=2000)
    assert m["edge_sources"]["name_low_edges"] > 0
    r = _ranks(m)
    # dispatch 是檔第一符號、被 3 個同檔 handler 呼叫 → 必須 > 沒人呼叫的 never_called_dead
    assert r["dispatch"] > r["never_called_dead"]


def test_intrafile_multi_beats_crossfile_single(project):
    """同檔被呼叫多次的符號 rank 應 >= 跨檔被呼叫 1 次的（不去重體現引用次數 + src_line 映射）。"""
    _write(project, "core.py", '''
        def big_internal_api():
            return 1

        def c1():
            return big_internal_api()

        def c2():
            return big_internal_api()

        def c3():
            return big_internal_api()

        def c4():
            return big_internal_api()

        def c5():
            return big_internal_api()
    ''')
    _write(project, "util.py", "def tiny_util():\n    return 2\n")
    _write(project, "use.py", "from util import tiny_util\ndef run():\n    return tiny_util()\n")
    engine.index_project(project, force=True)
    m = engine.get_map(project, token_budget=2000)
    r = _ranks(m)
    assert r["big_internal_api"] >= r["tiny_util"]


# ─────────────── 紅隊 L3 修正：entrypoint 豁免 + variable 降級 ───────────────

def test_find_unwired_exempts_console_scripts(project):
    """pyproject [project.scripts] 指向的 func 豁免（紅隊 L3-HIGH：console_scripts 入口不誤報）。"""
    _write(project, "cli.py", "def cli_main():\n    return run_it()\n\ndef run_it():\n    return 1\n")
    _write(project, "pyproject.toml", '''
        [project]
        name = "demo"
        version = "0.0.1"

        [project.scripts]
        mytool = "cli:cli_main"
    ''')
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    names = {c["name"] for c in r["candidates"]}
    assert "cli_main" not in names              # console_scripts 入口豁免


def test_find_unwired_variable_downgraded(project):
    """module 級變數候選標 low_confidence_kind + reason 提 UNKNOWN（紅隊 L3-MEDIUM）。"""
    _write(project, "config.py", "DEAD_CONST = 42\n")
    _write(project, "u.py", "def run():\n    return 1\n")
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    var_cands = [c for c in r["candidates"] if c["name"] == "DEAD_CONST"]
    assert var_cands and var_cands[0].get("low_confidence_kind") is True
    assert "UNKNOWN" in var_cands[0]["reason"] or "信心更低" in var_cands[0]["reason"]
    assert r["summary"].get("unwired_variable_candidates", 0) >= 1


def test_find_unwired_fastapi_decorator_exempt(project):
    """FastAPI 物件名非 app（@api.get）+ websocket/on_event 變體豁免（紅隊 L3-MEDIUM）。"""
    _write(project, "routes.py", '''
        api = object()

        @api.get("/x")
        def get_x():
            return 1

        @api.websocket("/ws")
        def ws_handler():
            return 2

        @api.on_event("startup")
        def on_start():
            return 3
    ''')
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    names = {c["name"] for c in r["candidates"]}
    assert "get_x" not in names and "ws_handler" not in names and "on_start" not in names
