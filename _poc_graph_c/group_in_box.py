"""group-in-a-box 混合佈局：Louvain 模組強制排球面（漂亮分離團塊）+ 群內 spectral（結構決定個體）+ 確定性。
解「純 spectral 中心密核不分離」。用法: python group_in_box.py <name>"""
import hashlib
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402

POC = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c"
R_GLOBAL = 1700.0


def _hash_unit(gi):
    h = int(hashlib.md5(str(gi).encode()).hexdigest()[:8], 16)
    return np.array([(h % 1000) / 1000 - 0.5,
                     ((h >> 10) % 1000) / 1000 - 0.5,
                     ((h >> 20) % 1000) / 1000 - 0.5])


def _local_spectral(Gr, members):
    """社群子圖群內 spectral，正規化到單位尺度。不連通/太小則 hash 散。"""
    n = len(members)
    out = np.zeros((n, 3))
    relabel = {gi: k for k, gi in enumerate(members)}
    H = nx.relabel_nodes(Gr, relabel)
    comps = sorted(nx.connected_components(H), key=len, reverse=True)
    main = sorted(comps[0])
    if len(main) >= 4:
        A = nx.to_numpy_array(H.subgraph(main), nodelist=main)
        deg = A.sum(1)
        L = np.diag(deg) - A
        vals, vecs = np.linalg.eigh(L)
        v = vecs[:, 1:4]
        if v.shape[1] < 3:
            v = np.pad(v, ((0, 0), (0, 3 - v.shape[1])))
        v = v / (np.abs(v).max() + 1e-9)        # 正規化到單位
        for k, mi in enumerate(main):
            out[mi] = v[k]
    else:
        for mi in main:
            out[mi] = _hash_unit(members[mi]) * 0.6
    for comp in comps[1:]:                        # 群內其餘分量 hash 散
        for mi in comp:
            out[mi] = _hash_unit(members[mi]) * 0.8
    return out


def build(name):
    src = POC + f"\\graph_{name}_remap.json"
    g = json.load(open(src, encoding="utf-8"))
    nodes = g["nodes"]
    N = len(nodes)
    G = nx.Graph()
    G.add_nodes_from(range(N))
    G.add_edges_from((e["source"], e["target"]) for e in g["edges"])

    comms = nx.community.louvain_communities(G, seed=42)
    comms = sorted(comms, key=len, reverse=True)   # 確定性順序（大社群優先）
    C = len(comms)
    coords = np.zeros((N, 3))
    for ci, comm in enumerate(comms):
        members = sorted(comm)
        # 社群中心：黃金螺旋球面（純 index 排，確定性）
        y = 1 - (ci / max(1, C - 1)) * 1.8 if C > 1 else 0.0
        rad = np.sqrt(max(0.0, 1 - y * y))
        phi = ci * 2.399963
        center = np.array([np.cos(phi) * rad, y * 0.8, np.sin(phi) * rad]) * R_GLOBAL
        # 群內半徑 << 群間距（確保團塊分離）
        r_local = 55 + 16 * np.sqrt(len(members))
        loc = _local_spectral(G.subgraph(members), members)
        for k, gi in enumerate(members):
            coords[gi] = center + loc[k] * r_local
        for gi in members:
            nodes[gi]["community"] = f"L{ci:02d}"

    assert np.isfinite(coords).all()
    for i, nd in enumerate(nodes):
        nd["x"], nd["y"], nd["z"] = float(coords[i, 0]), float(coords[i, 1]), float(coords[i, 2])
    g.setdefault("meta", {})["layout"] = {"algo": "group_in_box_spectral", "dim": 3,
                                          "community_algo": "louvain", "communities": C}
    out = POC + f"\\graph_{name}_gib.json"
    json.dump(g, open(out, "w", encoding="utf-8"), ensure_ascii=False)

    # 團塊指標
    import random
    random.seed(0)
    from collections import defaultdict
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
    print(f"{name}: C={C} d_in/d_all={ratio:.3f} → {'團塊強' if ratio < 0.5 else ('有團塊' if ratio < 0.8 else '弱')} -> {out}")


for n in (sys.argv[1:] or ["cs", "sancio"]):
    build(n)
