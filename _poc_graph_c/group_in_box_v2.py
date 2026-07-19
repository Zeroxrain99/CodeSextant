"""Phase A：自然有序美學裝盒佈局 v2（紅藍CBUA最佳解收口 §B 落地）。
FATAL-3：社群中心改「超節點 spectral」(反映社群間真實引用關聯，非純大小排名 ci)。
拍板1：center_mode='tidy'(預設,超節點spectral投球面均勻不旋) | 'spiral'(黃金角左旋螺旋,順序由結構排)。
M4：群內+超圖 spectral 都套 _canonicalize 定號。M8：equal-area y 去不對稱拉伸。
FATAL-5：size<4 收 singleton 帶(rank 序排外圈,不 hash 噪聲散)。手性 Phase B(opt-in,本版不做)。
用法: python group_in_box_v2.py <name> <tidy|spiral>"""
import hashlib
import json
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402

POC = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c"
sys.path.insert(0, POC)
from poc_spectral import _canonicalize  # noqa: E402  M4 定號（度加權偏度）

R_GLOBAL = 1700.0
GOLDEN_ANGLE = 2.39996322972865332
BETA_TIDY = 0.4   # tidy blend：Fibonacci 均勻化權重（低=結構主導→只有模組化好的才均勻漂亮、爛結構仍擠/亂，不美化爛代碼）
MIN_Q = 0.35      # Q 門控閾值：modularity < 此值 = 無真實模組化 → ⛔不裝盒、退全域 spectral（不美化爛代碼）


def _hash_unit(gi):
    h = int(hashlib.md5(str(gi).encode()).hexdigest()[:8], 16)
    return np.array([(h % 1000) / 1000 - 0.5, ((h >> 10) % 1000) / 1000 - 0.5, ((h >> 20) % 1000) / 1000 - 0.5])


def _spectral_unit(G, members, dim=3):
    """子圖 spectral 單位座標（群內 or 超圖共用）。M4 定號。不連通/太小 hash 散。"""
    n = len(members)
    out = np.zeros((n, dim))
    relabel = {gi: k for k, gi in enumerate(members)}
    H = nx.relabel_nodes(G.subgraph(members), relabel)
    comps = sorted(nx.connected_components(H), key=len, reverse=True)
    main = sorted(comps[0])
    if len(main) >= dim + 1:
        A = nx.to_numpy_array(H.subgraph(main), nodelist=main)
        deg = A.sum(1)
        L = np.diag(deg) - A
        vals, vecs = np.linalg.eigh(L)
        v = vecs[:, 1:dim + 1]
        v = _canonicalize(v, deg)              # M4：定號（同 BLAS 內可重現）
        v = v / (np.abs(v).max() + 1e-9)
        for k, mi in enumerate(main):
            out[mi] = v[k]
    else:
        for mi in main:
            out[mi] = _hash_unit(members[mi]) * 0.6
    for comp in comps[1:]:
        for mi in comp:
            out[mi] = _hash_unit(members[mi]) * 0.8
    return out


def _supergraph_centers(G, comms):
    """FATAL-3：社群縮超節點、超圖跑 spectral → 反映社群間真實引用關聯的中心基底。"""
    C = len(comms)
    node2c = {n: ci for ci, m in enumerate(comms) for n in m}
    SG = nx.Graph()
    SG.add_nodes_from(range(C))
    for u, v in G.edges():
        cu, cv = node2c[u], node2c[v]
        if cu != cv:
            if SG.has_edge(cu, cv):
                SG[cu][cv]['weight'] += 1
            else:
                SG.add_edge(cu, cv, weight=1)
    cs = _spectral_unit(SG, list(range(C)), dim=3)   # C×3 單位尺度
    return cs, SG


def build(name, center_mode="tidy"):
    g = json.load(open(POC + f"\\graph_{name}_remap.json", encoding="utf-8"))
    nodes = g["nodes"]
    N = len(nodes)
    G = nx.Graph()
    G.add_nodes_from(range(N))
    G.add_edges_from((e["source"], e["target"]) for e in g["edges"])
    comms = sorted(nx.community.louvain_communities(G, seed=42), key=len, reverse=True)
    C = len(comms)

    cs, SG = _supergraph_centers(G, comms)            # 超節點 spectral 中心基底
    order = np.argsort(-np.linalg.norm(cs, axis=1))   # 結構徑向序（確定性）
    rank = np.empty(C, int)
    rank[order] = np.arange(C)

    # ── Q 門控（用戶鐵律：只有真模組化才美，爛結構不准被裝盒機制強行美化）──
    Q = float(nx.community.modularity(G, comms))   # 模組化強度：高=社群真實分離=該美；低=糾纏/隨機=不該美
    coords = np.zeros((N, 3))
    centers = None
    if Q < MIN_Q:
        # 模組結構太弱（無統一母版 / 無模組化 / 糾纏）→ ⛔不裝盒、退全域 spectral
        # → 誠實呈現「中心密核 / 糾纏」真實醜樣，不被裝盒機制排成漂亮團塊（不美化爛代碼）
        from poc_spectral import compute_layout
        coords, _, _ = compute_layout(N, g["edges"], dim=3)
        for ci in range(C):
            for gi in comms[ci]:
                nodes[gi]["community"] = f"L{ci:02d}"
        big, small, aesthetic = [], [], "low_modularity_no_box"
    else:
        # 模組化夠強 → 裝盒 + blend 美學
        centers = np.zeros((C, 3))
        for ci in range(C):
            k = int(rank[ci])
            y = 1 - 2 * (k + 0.5) / C if C > 1 else 0.0       # equal-area（M8 去不對稱拉伸）
            rad = np.sqrt(max(0.0, 1 - y * y))
            if center_mode == "tidy":
                # blend：結構方向(超節點 spectral) 主導 + Fibonacci 均勻化(輕推 β=0.4)。
                # 模組化好→中心本就分散→均勻漂亮；爛→中心本就擠→Fibonacci 救不動→仍擠。
                phi = k * GOLDEN_ANGLE                         # tidy 不左旋
                fib = np.array([np.cos(phi) * rad, y, np.sin(phi) * rad])
                d = cs[ci]
                struct = d / (np.linalg.norm(d) + 1e-9)        # 超節點 spectral 方向
                blended = (1 - BETA_TIDY) * struct + BETA_TIDY * fib
                centers[ci] = blended / (np.linalg.norm(blended) + 1e-9) * R_GLOBAL
            else:  # spiral：黃金角左旋螺旋，順序由結構 spectral 徑向序決定
                phi = -k * GOLDEN_ANGLE                         # 左旋（chirality_sign=-1）
                centers[ci] = np.array([np.cos(phi) * rad, y, np.sin(phi) * rad]) * R_GLOBAL
        big = [ci for ci in range(C) if len(comms[ci]) >= 4]
        for ci in big:
            members = sorted(comms[ci])
            loc = _spectral_unit(G, members, dim=3)
            r_local = 55 + 16 * np.sqrt(len(members))
            for kk, gi in enumerate(members):
                coords[gi] = centers[ci] + loc[kk] * r_local
            for gi in members:
                nodes[gi]["community"] = f"L{ci:02d}"
        # FATAL-5：size<4 收 singleton 帶（rank 序排外圈一圈、左旋、不 hash 噪聲散）
        small = sorted([gi for ci in range(C) if len(comms[ci]) < 4 for gi in comms[ci]],
                       key=lambda gi: -(nodes[gi].get("rank", 0.0)))
        M = max(1, len(small))
        for kk, gi in enumerate(small):
            ang = -kk / M * 2 * np.pi                          # 左旋一圈
            coords[gi] = [np.cos(ang) * R_GLOBAL * 1.28, (kk / M - 0.5) * R_GLOBAL * 0.25, np.sin(ang) * R_GLOBAL * 1.28]
            nodes[gi]["community"] = "Lsingleton"
        aesthetic = "full"

    assert np.isfinite(coords).all(), "NaN/Inf in coords"
    for i, nd in enumerate(nodes):
        nd["x"], nd["y"], nd["z"] = float(coords[i, 0]), float(coords[i, 1]), float(coords[i, 2])
    g.setdefault("meta", {})["layout"] = {
        "algo": "gib_super_spectral", "dim": 3, "community_algo": "louvain",
        "communities": C, "supergraph_spectral": True, "center_mode": center_mode,
        "modularity_Q": round(Q, 4), "min_q_gate": MIN_Q, "aesthetic": aesthetic, "beta_tidy": BETA_TIDY,
        "chirality": "left", "chirality_rationale": "aesthetic_fingerprint_choice_not_physics",
        "twist_max": 0.0,
    }
    out = POC + f"\\graph_{name}_v2_{center_mode}.json"
    json.dump(g, open(out, "w", encoding="utf-8"), ensure_ascii=False)

    # ── 驗收 ──
    import random
    random.seed(0)
    by = defaultdict(list)
    for i, nd in enumerate(nodes):
        by[nd["community"]].append(i)

    def apd(ps):
        return float(np.median([np.linalg.norm(coords[a] - coords[b]) for a, b in ps])) if ps else float("nan")
    intra = []
    for idxs in by.values():
        if len(idxs) < 2:
            continue
        for _ in range(min(300, len(idxs) * 3)):
            a, b = random.sample(idxs, 2)
            intra.append((a, b))
    allp = [(random.randrange(N), random.randrange(N)) for _ in range(8000)]
    ratio = apd(intra) / apd(allp)

    # FATAL-3 修復指標：社群間中心距離 vs 引用數 correlation（負=引用多→中心近=關聯反映；low_q 無 centers 故 nan）
    if aesthetic == "full" and centers is not None and SG.number_of_edges() > 2:
        dists = [float(np.linalg.norm(centers[cu] - centers[cv])) for cu, cv, _ in SG.edges(data=True)]
        weights = [d["weight"] for _, _, d in SG.edges(data=True)]
        corr = float(np.corrcoef(dists, weights)[0, 1])
    else:
        corr = float("nan")
    beauty = "模組化夠→裝盒美" if Q >= MIN_Q else "結構太弱→退全域spectral(不美化)"
    print(f"{name}/{center_mode}: C={C} Q={Q:.3f}({beauty}) | aesthetic={aesthetic} | "
          f"真盒={len(big)} singleton={len(small)} | d_in/d_all={ratio:.3f} | 中心距×引用 corr={corr:+.3f} -> {out}")


if __name__ == "__main__":
    nm = sys.argv[1] if len(sys.argv) > 1 else "cs"
    mode = sys.argv[2] if len(sys.argv) > 2 else "tidy"
    build(nm, mode)
