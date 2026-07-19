"""功能 C PoC 圖資料匯出 — 站在 CodeSextant 既有 get_map/namegraph/rank_symbols 肩上。

產兩份 JSON 給 PoC-A(cosmos.gl) 與 PoC-B(three.js WebGPU/TSL) 共用、公平對照：
  graph_real.json  ＝ CodeSextant 自己的真實符號圖（誠實展示工具真實輸出）
  graph_synth.json ＝ 合成萬級圖（~10000 節點 + 多社群），展示「數以萬計 + 亂中有序 + 效能」

node = {i, name, kind, file, community, rank}；edge = {source, target}（都用整數 index）。
"""
import json
import os
import random
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # E:\ai-king\項目資料\CodeSextant
sys.path.insert(0, ROOT)

from codesextant import engine, namegraph, storage
from codesextant.ranking import _norm, _symbol_id, rank_symbols

random.seed(42)  # 可重現


def export_real():
    print("[real] index_project ...")
    engine.index_project(ROOT)
    with storage.ProjectStore.open(ROOT) as store:
        symbols = store.get_symbols()
        db_refs = store.all_refs()
        name_edges, meta = namegraph.build_name_edges(
            symbols, indexed_files=store.all_indexed_files())
    refs = db_refs + name_edges
    ranked = rank_symbols(symbols, refs)  # 全部、不 top_n
    rank_by_id = {_symbol_id(s): s["rank"] for s in ranked}

    by_pos, by_body = {}, {}
    id_to_idx = {}
    for i, s in enumerate(symbols):
        sid = _symbol_id(s)
        id_to_idx[sid] = i
        p = s.get("path")
        if not p:
            continue
        np = _norm(p)
        by_pos[(np, s["line"])] = sid
        by_body.setdefault(np, []).append(
            (s["line"], int(s.get("end_line", s["line"]) or s["line"]), sid))
    for lst in by_body.values():
        lst.sort()

    def src_node(sp, sl):
        np = _norm(sp) if sp else ""
        if sl and np in by_body:
            best = None
            for (ln, el, sid) in by_body[np]:
                if ln > sl:
                    break
                if ln <= sl <= el:
                    best = sid
            if best:
                return best
        if np in by_body and by_body[np]:
            return by_body[np][0][2]
        return None

    def community_of(path):
        # 用「相對目錄」當社群（Louvain 是正式版；PoC 用目錄分群已足夠展示亂中有序）
        rel = os.path.relpath(path, ROOT) if path else ""
        d = os.path.dirname(rel)
        return d or "(root)"

    _fc = {}
    def read_snippet(path, line, end_line, max_lines=34):
        """讀符號真實代碼片段（給 v2 節點點開顯示）。"""
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
            return "\n".join(x[:240] for x in ls[a:b])
        except Exception:
            return ""

    nodes = []
    for i, s in enumerate(symbols):
        sid = _symbol_id(s)
        nodes.append({
            "i": i,
            "name": s["name"],
            "kind": s.get("kind", ""),
            "file": os.path.relpath(s["path"], ROOT) if s.get("path") else "",
            "community": community_of(s.get("path")),
            "rank": round(rank_by_id.get(sid, 0.0), 6),
            "line": int(s.get("line", 0) or 0),
            "code": read_snippet(s.get("path"), s.get("line"), s.get("end_line")),
        })

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
        key = (src, tgt)
        if key in seen:
            continue
        seen.add(key)
        edges.append({"source": id_to_idx[src], "target": id_to_idx[tgt]})

    out = {"nodes": nodes, "edges": edges,
           "meta": {"source": "CodeSextant real symbols", "n_nodes": len(nodes),
                    "n_edges": len(edges), "db_high_edges": len(db_refs),
                    "name_low_edges": len(name_edges)}}
    path = os.path.join(HERE, "graph_real.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[real] {len(nodes)} nodes / {len(edges)} edges -> {path}")
    return out


def export_synth(n_communities=42, per_comm_min=120, per_comm_max=380,
                 intra_density=0.018, inter_edges=2200):
    """合成萬級「亂中有序」圖：n_communities 個社群、群內密、群間疏。
    rank 用節點度數近似（前端當大小）。"""
    print("[synth] generating ...")
    nodes, edges = [], []
    comm_ranges = []  # (community_idx, start_node_idx, count)
    idx = 0
    KINDS = ["function", "class", "method", "variable", "interface", "type"]
    for c in range(n_communities):
        cnt = random.randint(per_comm_min, per_comm_max)
        start = idx
        for k in range(cnt):
            nodes.append({
                "i": idx, "name": f"sym_{c}_{k}",
                "kind": random.choice(KINDS),
                "file": f"module_{c}/file_{k % 12}.ts",
                "community": f"module_{c}",
                "rank": 0.0,
            })
            idx += 1
        comm_ranges.append((c, start, cnt))
    n = idx

    deg = [0] * n
    eseen = set()

    def add_edge(a, b):
        if a == b:
            return
        key = (a, b) if a < b else (b, a)
        if key in eseen:
            return
        eseen.add(key)
        edges.append({"source": a, "target": b})
        deg[a] += 1
        deg[b] += 1

    # 群內密集連
    for (_c, start, cnt) in comm_ranges:
        end = start + cnt
        target_edges = int(cnt * cnt * intra_density / 2)
        for _ in range(target_edges):
            a = random.randint(start, end - 1)
            b = random.randint(start, end - 1)
            add_edge(a, b)
    # 群間稀疏連（製造「亂中有序」的跨群少量橋）
    for _ in range(inter_edges):
        a = random.randint(0, n - 1)
        b = random.randint(0, n - 1)
        add_edge(a, b)

    # rank = 度數歸一化（近似 PageRank 的視覺效果：度高＝大）
    maxd = max(deg) or 1
    for i in range(n):
        nodes[i]["rank"] = round(deg[i] / maxd, 6)

    out = {"nodes": nodes, "edges": edges,
           "meta": {"source": "synthetic communities", "n_nodes": n,
                    "n_edges": len(edges), "n_communities": n_communities}}
    path = os.path.join(HERE, "graph_synth.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[synth] {n} nodes / {len(edges)} edges / {n_communities} communities -> {path}")
    return out


if __name__ == "__main__":
    export_real()
    export_synth()
    print("DONE")
