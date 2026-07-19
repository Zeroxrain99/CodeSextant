"""Phase A v3：用「per-社群 modularity 貢獻」連續驅動美的程度，取代硬 Q 門控（用戶要求）。
每個社群對 modularity 的貢獻 q_c = 內部邊比例 - 期望 → beauty∈[0,1] 連續：
  beauty 高(真社群,內聚>期望)→ 中心推遠球面 + 群內排緊 → 美；
  beauty 低/負(假社群/孤點/打亂)→ 留中心 + 鬆散 → 自然糊掉醜。
⛔ 無閾值、無開關，好醜是演算法自然輸出。確定性(louvain seed42 + eigh + canon)。
用法: python group_in_box_v3.py <name> <tidy|spiral>"""
import json
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402

POC = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c"
sys.path.insert(0, POC)
from group_in_box_v2 import _spectral_unit, _supergraph_centers  # noqa: E402

R_GLOBAL = 1700.0
GOLDEN_ANGLE = 2.39996322972865332
BETA_TIDY = 0.4


def per_comm_modularity(G, comms):
    """每社群對 modularity 的貢獻 q_c = e_in/m - (deg_sum/2m)^2（高=真社群、低/負=假社群）。"""
    m = G.number_of_edges()
    out = []
    for c in comms:
        sub = G.subgraph(c)
        e_in = sub.number_of_edges()
        deg_sum = sum(d for _, d in G.degree(c))
        out.append(e_in / m - (deg_sum / (2 * m)) ** 2 if m else 0.0)
    return np.array(out, dtype=float)


def build(name, center_mode="tidy", beta=None):
    b = BETA_TIDY if beta is None else beta   # tidy blend 權重（可調，預設讀模組常數）
    g = json.load(open(POC + f"\\graph_{name}_remap.json", encoding="utf-8"))
    nodes = g["nodes"]
    N = len(nodes)
    # ── 代碼地圖分離測試：測試 fixture 不參與生產架構的社群/modularity 計算 ──
    # （前驗：含測試 Q 0.479、排除 Q 0.521，top hub 10/11 是測試 fixture 污染）
    prod = [i for i, n in enumerate(nodes) if not n.get("is_test", False)]
    test_nodes = [i for i, n in enumerate(nodes) if n.get("is_test", False)]
    prodset = set(prod)
    G = nx.Graph()
    G.add_nodes_from(prod)
    G.add_edges_from((e["source"], e["target"]) for e in g["edges"]
                     if e["source"] in prodset and e["target"] in prodset)
    comms = sorted(nx.community.louvain_communities(G, seed=42), key=len, reverse=True)
    C = len(comms)

    cs, SG = _supergraph_centers(G, comms)
    order = np.argsort(-np.linalg.norm(cs, axis=1))
    rank = np.empty(C, int)
    rank[order] = np.arange(C)

    # ── per-社群 beauty（連續，無門控）──
    qc = per_comm_modularity(G, comms)
    Q_REF = 0.03
    beauty = np.clip(qc / Q_REF, 0.0, 1.0)        # per-社群連續：社群內聚→該社群美的程度（細部）

    Qg = float(nx.community.modularity(G, comms))  # 整圖模組化（看全局，不被假社群局部正 qc 騙）

    def _smoothstep(e0, e1, x):
        t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
        return t * t * (3 - 2 * t)
    # ★整圖連續閘（取代二元門控）：平滑 smoothstep 非 0.35 斷崖。Q<0.20→strength≈0 全糊醜、
    # Q>0.45→1 全分離美、中間平滑過渡（0.34 vs 0.36 幾乎一樣）。整圖 strength × per-社群 beauty 雙連續。
    strength = _smoothstep(0.20, 0.45, Qg)

    coords = np.zeros((N, 3))
    centers = np.zeros((C, 3))
    for ci in range(C):
        k = int(rank[ci])
        y = 1 - 2 * (k + 0.5) / C if C > 1 else 0.0
        rad = np.sqrt(max(0.0, 1 - y * y))
        if center_mode == "tidy":
            phi = k * GOLDEN_ANGLE
            fib = np.array([np.cos(phi) * rad, y, np.sin(phi) * rad])
            d = cs[ci]
            struct = d / (np.linalg.norm(d) + 1e-9)
            direction = (1 - b) * struct + b * fib
        else:  # spiral 左旋
            phi = -k * GOLDEN_ANGLE
            direction = np.array([np.cos(phi) * rad, y, np.sin(phi) * rad])
        direction = direction / (np.linalg.norm(direction) + 1e-9)
        # ★連續半徑：beauty 高→推遠球面(0.95R)、beauty 低→留中心(0.12R)→爛社群自然擠中心糊
        R_ci = R_GLOBAL * strength * (0.12 + 0.83 * beauty[ci])   # 整圖 strength(連續閘) × per-社群 beauty
        centers[ci] = direction * R_ci

    for ci in range(C):
        members = sorted(comms[ci])
        loc = _spectral_unit(G, members, dim=3) if len(members) >= 2 else np.zeros((len(members), 3))
        # ★連續群內緊度：beauty 高→緊(看得出結構)、beauty 低→鬆散糊
        r_local = (55 + 16 * np.sqrt(len(members))) * (0.35 + 0.65 * beauty[ci])
        for kk, gi in enumerate(members):
            coords[gi] = centers[ci] + loc[kk] * r_local
            nodes[gi]["community"] = f"L{ci:02d}"

    # ── 測試帶：測試節點不入生產社群，依 rank 收最外圈一圈（與生產架構物理分離、一眼辨）──
    if test_nodes:
        T = max(1, len(test_nodes))
        ts = sorted(test_nodes, key=lambda gi: -(nodes[gi].get("rank", 0.0)))
        for kk, gi in enumerate(ts):
            ang = -kk / T * 2 * np.pi          # 左旋一圈，與 spiral 手性一致
            coords[gi] = [np.cos(ang) * R_GLOBAL * 1.45,
                          (kk / T - 0.5) * R_GLOBAL * 0.30,
                          np.sin(ang) * R_GLOBAL * 1.45]
            nodes[gi]["community"] = "Ltest"

    assert np.isfinite(coords).all(), "NaN/Inf"
    Q = Qg
    for i, nd in enumerate(nodes):
        nd["x"], nd["y"], nd["z"] = float(coords[i, 0]), float(coords[i, 1]), float(coords[i, 2])
    g.setdefault("meta", {})["layout"] = {
        "algo": "gib_continuous_beauty", "dim": 3, "community_algo": "louvain",
        "communities": C, "center_mode": center_mode, "modularity_Q": round(Q, 4),
        "gate": "none_continuous_per_community", "chirality": "left",
        "chirality_rationale": "aesthetic_fingerprint_choice_not_physics", "twist_max": 0.0,
        "n_prod": len(prod), "n_test": len(test_nodes), "test_separated": bool(test_nodes),
        "beta_tidy": round(b, 3),
    }
    # β 非預設時輸出名加後綴（sweep 不覆蓋正式版 graph_{name}_v3_{mode}.json）
    suffix = "" if beta is None else f"_b{int(round(b * 100)):03d}"
    out = POC + f"\\graph_{name}_v3_{center_mode}{suffix}.json"
    json.dump(g, open(out, "w", encoding="utf-8"), ensure_ascii=False)

    # 驗收
    import random
    random.seed(0)
    by = defaultdict(list)
    for i, nd in enumerate(nodes):
        by[nd["community"]].append(i)

    def apd(ps):
        return float(np.median([np.linalg.norm(coords[a] - coords[b]) for a, b in ps])) if ps else float("nan")
    intra = []
    for comm, idxs in by.items():
        if comm == "Ltest" or len(idxs) < 2:   # 測試帶不算生產分團指標
            continue
        for _ in range(min(300, len(idxs) * 3)):
            u, v = random.sample(idxs, 2)   # 用 u,v 不用 a,b：避免覆蓋 β 變數 b（變數收斂）
            intra.append((u, v))
    ratio = apd(intra) / apd([(random.randrange(N), random.randrange(N)) for _ in range(8000)])
    print(f"{name}/{center_mode}: C={C} Q={Q:.3f} strength={strength:.2f} beta={b:.2f} | "
          f"prod={len(prod)} test={len(test_nodes)}(外圈帶) | "
          f"高beauty社群(>0.5)={int((beauty > 0.5).sum())} | d_in/d_all={ratio:.3f}"
          f"({'分團美' if ratio < 0.3 else ('中等' if ratio < 0.6 else '糊醜')}) -> {out}")
    return {"name": name, "C": C, "Q": Q, "strength": strength, "beta": b,
            "ratio": ratio, "high_beauty": int((beauty > 0.5).sum()), "out": out}


if __name__ == "__main__":
    nm = sys.argv[1] if len(sys.argv) > 1 else "cs"
    md = sys.argv[2] if len(sys.argv) > 2 else "tidy"
    build(nm, md)
