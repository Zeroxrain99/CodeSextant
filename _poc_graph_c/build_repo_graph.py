"""對任意 repo 跑 CodeSextant index + 確定性 spectral 佈局 → 產 pure/remap 兩版 graph json。
複用 export_graph.export_real 的符號/引用邏輯（ROOT 參數化）+ poc_spectral 的 spectral 計算。
- CLI:  python build_repo_graph.py <ROOT> <name>
- 函數: build_repo_graph(ROOT, NAME)  ← daemon /graph_data（graph_api）即時出圖調用
interpreter 必用 C:/Python311（有 scipy）。"""
import copy
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

CS = r"E:\ai-king\項目資料\CodeSextant"
POC = CS + r"\_poc_graph_c"
sys.path.insert(0, CS)
sys.path.insert(0, POC)

import code_health  # noqa: E402  紀律轉美：per-node health（D1腫脹/D5重複）+ dead（D6未接線）
from poc_spectral import _density_remap, _report, _rescale, attach, compute_layout  # noqa: E402
from test_classifier import is_test_path  # noqa: E402  代碼地圖分離測試：單一判定中樞

from codesextant import engine, namegraph, storage  # noqa: E402
from codesextant.ranking import _norm, _symbol_id, rank_symbols  # noqa: E402

_fc: dict = {}
def read_snippet(path, line, end_line, max_lines=600):
    """讀符號真實代碼片段（給星圖節點點開顯示）。複用 export_graph.export_real 邏輯，
    修 v3 tidy 圖無 code 欄位的退化。max_lines=600＝「所有代碼基本都在裡面」（user 要求），
    超大函數才截斷（按需完整碼留 daemon /symbol_code 後續做）。"""
    if not path:
        return ""
    try:
        if path not in _fc:
            with open(path, encoding="utf-8", errors="replace") as fh:
                _fc[path] = fh.read().split("\n")
        ls = _fc[path]
        a = max(0, int(line or 1) - 1)
        b = min(len(ls), int(end_line or line or 1))
        b = min(b, a + max_lines)
        return "\n".join(x[:400] for x in ls[a:b])
    except Exception:
        return ""


def git_churn(root):
    """git log 一次算每檔「變更頻率(churn)」+「最後修改 unix 時間」。
    回 {normcase 絕對路徑: {"churn": n, "last_mod": ts}}；非 git repo / git 失敗 → {}。
    P1：hotspot = 認知複雜度 × churn（CodeScene 招牌「複雜又常改才真痛」）。
    ⚠ git log 路徑相對 git repo top，故先 rev-parse 拿 top 再組絕對路徑對齊節點。"""
    import subprocess
    flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW（user 被黑窗干擾教訓 pit6-2）
    try:
        top = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=15, creationflags=flags)
        if top.returncode != 0 or not top.stdout.strip():
            return {}
        git_root = top.stdout.strip()
        out = subprocess.run(["git", "-C", root, "log", "--format=__T__%at", "--name-only"],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=90, creationflags=flags)
        if out.returncode != 0:
            return {}
    except Exception:
        return {}
    res = {}
    cur_ts = 0
    for ln in out.stdout.splitlines():
        if ln.startswith("__T__"):
            try:
                cur_ts = int(ln[5:])
            except ValueError:
                cur_ts = 0
        elif ln.strip():
            ap = os.path.normcase(os.path.join(git_root, ln.strip().replace("/", os.sep)))
            e = res.setdefault(ap, {"churn": 0, "last_mod": cur_ts})  # log 新→舊，first seen=最新
            e["churn"] += 1
    return res


def build_repo_graph(ROOT, NAME):
    """對 ROOT repo 出圖：index + 抽符號（帶完整代碼）+ 引用邊 + health + spectral 佈局。
    寫 graph_{NAME}_pure.json / graph_{NAME}_remap.json（remap 給 group_in_box_v3 佈局）。
    回 g_remap dict。"""
    print(f"[{NAME}] index {ROOT} ...", flush=True)
    engine.index_project(ROOT, force=True)  # force 全量：確保 fingerprints/comments 重建（增量會 skip 未變檔致指紋表空）
    with storage.ProjectStore.open(ROOT) as store:
        symbols = store.get_symbols()
        db_refs = store.all_refs()
        name_edges, _meta = namegraph.build_name_edges(symbols, indexed_files=store.all_indexed_files())
        # P1：認知複雜度（fingerprints）給 hotspot = 複雜度 × git churn
        cog_by = {}
        for r in store.conn.execute(
                "SELECT path,line,cognitive FROM fingerprints WHERE cognitive IS NOT NULL"):
            cog_by[(_norm(r["path"]), int(r["line"]))] = int(r["cognitive"])
    refs = db_refs + name_edges
    churn_map = git_churn(ROOT)   # P1：每檔變更頻率 + 最後修改時間（非 git repo → {}）
    ranked = rank_symbols(symbols, refs)
    rank_by_id = {_symbol_id(s): s["rank"] for s in ranked}

    by_pos, by_body, id_to_idx = {}, {}, {}
    for i, s in enumerate(symbols):
        sid = _symbol_id(s)
        id_to_idx[sid] = i
        p = s.get("path")
        if not p:
            continue
        npth = _norm(p)
        by_pos[(npth, s["line"])] = sid
        by_body.setdefault(npth, []).append((s["line"], int(s.get("end_line", s["line"]) or s["line"]), sid))
    for lst in by_body.values():
        lst.sort()

    def src_node(sp, sl):
        npth = _norm(sp) if sp else ""
        if sl and npth in by_body:
            best = None
            for (ln, el, sid) in by_body[npth]:
                if ln > sl:
                    break
                if ln <= sl <= el:
                    best = sid
            if best:
                return best
        if npth in by_body and by_body[npth]:
            return by_body[npth][0][2]
        return None

    def community_of(path):
        rel = os.path.relpath(path, ROOT) if path else ""
        d = os.path.dirname(rel)
        return d or "(root)"

    nodes = []
    for i, s in enumerate(symbols):
        sid = _symbol_id(s)
        rel = os.path.relpath(s["path"], ROOT) if s.get("path") else ""
        _cog = cog_by.get((_norm(s["path"]), int(s.get("line", 0) or 0))) if s.get("path") else None
        _cinfo = churn_map.get(os.path.normcase(os.path.abspath(s["path"])), {}) if s.get("path") else {}
        _ch = _cinfo.get("churn", 0)
        nodes.append({
            "i": i, "name": s["name"], "kind": s.get("kind", ""),
            "file": rel,
            "community": community_of(s.get("path")),
            "rank": round(rank_by_id.get(sid, 0.0), 6),
            "line": int(s.get("line", 0) or 0),
            "is_test": is_test_path(rel),   # 代碼地圖分離測試：標記，佈局/Q 計算時排除
            "code": read_snippet(s.get("path"), s.get("line"), s.get("end_line")),  # 完整代碼在裡面
            "cognitive": _cog,              # P1：認知複雜度（None=UNKNOWN）
            "churn": _ch,                   # P1：git 變更頻率
            "last_mod": _cinfo.get("last_mod", 0),  # P1：最後修改 unix 時間
            "hotspot": (_cog or 0) * _ch,   # P1：raw hotspot（複雜度×churn）；下方正規化 0-1
        })
    n_test = sum(1 for n in nodes if n["is_test"])

    # ── 紀律轉美：per-node health（D1 腫脹 + D5 重複）+ dead（D6 未接線）──
    health_cov = code_health.compute(ROOT, nodes)
    clone_edges = health_cov.get("clone_pairs", [])
    print(f"[{NAME}] health 覆蓋 {health_cov['coverage'] * 100:.0f}% "
          f"({health_cov['n_covered']}/{health_cov['n_nodes']}) · 未接線 {health_cov['n_dead']} · "
          f"重複碼弧 {len(clone_edges)}", flush=True)

    edges, seen = [], set()
    for e in refs:
        dp, dl = e.get("def_path"), e.get("def_line")
        if dp is None or dl is None:
            continue
        tgt = by_pos.get((_norm(dp), dl))
        if not tgt:
            continue
        src = src_node(e.get("src_path"), e.get("src_line"))
        if not src or src == tgt:
            continue
        k = (src, tgt)
        if k in seen:
            continue
        seen.add(k)
        edges.append({"source": id_to_idx[src], "target": id_to_idx[tgt]})

    N = len(nodes)
    C = len({n["community"] for n in nodes})
    print(f"[{NAME}] {N} nodes ({n_test} 測試/{N - n_test} 生產) / {len(edges)} edges / {C} communities(目錄)", flush=True)

    coords, comps, iso = compute_layout(N, edges, dim=3)
    print(f"[{NAME}] 分量={comps} 非主團={iso}", flush=True)

    _maxhot = max((n["hotspot"] for n in nodes), default=0) or 1
    for n in nodes:
        n["hotspot"] = round(n["hotspot"] / _maxhot, 4)   # P1：正規化 0-1 給前端 hotspot 著色（相對排序）
    n_hot = sum(1 for n in nodes if n["hotspot"] > 0)
    print(f"[{NAME}] git churn: {len(churn_map)} 檔有歷史 · hotspot>0 節點 {n_hot}", flush=True)
    base = {"nodes": nodes, "edges": edges, "clone_edges": clone_edges,
            "meta": {"source": f"{NAME} symbols", "n_nodes": N, "n_edges": len(edges),
                     "n_test": n_test, "n_clone_edges": len(clone_edges),
                     "root": os.path.abspath(ROOT)}}  # P2：絕對根路徑（前端組 vscode:// 跳 IDE）
    g_pure = attach(copy.deepcopy(base), coords, f"spectral_{NAME}_pure", comps)
    json.dump(g_pure, open(f"{POC}\\graph_{NAME}_pure.json", "w", encoding="utf-8"), ensure_ascii=False)
    coords_remap = _rescale(_density_remap(coords), 1700.0)
    g_remap = attach(copy.deepcopy(base), coords_remap, f"spectral_{NAME}_remap", comps)
    json.dump(g_remap, open(f"{POC}\\graph_{NAME}_remap.json", "w", encoding="utf-8"), ensure_ascii=False)
    _report("pure ", coords)
    _report("remap", coords_remap)
    print(f"OK -> graph_{NAME}_pure.json / graph_{NAME}_remap.json", flush=True)
    return g_remap


if __name__ == "__main__":
    _ROOT = sys.argv[1] if len(sys.argv) > 1 else r"E:\ai-king\projects\sancio\src"
    _NAME = sys.argv[2] if len(sys.argv) > 2 else "sancio"
    build_repo_graph(_ROOT, _NAME)
