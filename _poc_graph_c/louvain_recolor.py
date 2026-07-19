"""用 Louvain（吃引用關係分群，和 spectral 同源）取代目錄分群，看團塊是否對齊浮現。
重寫 node.community = Louvain id（前端配色依此）→ 產 graph_<name>_louvain.json + 算 d_in/d_all。"""
import json
import random
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402

random.seed(0)
POC = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c"


def run(name, src):
    g = json.load(open(POC + "\\" + src, encoding="utf-8"))
    nodes = g["nodes"]
    N = len(nodes)
    G = nx.Graph()
    G.add_nodes_from(range(N))
    G.add_edges_from((e["source"], e["target"]) for e in g["edges"])
    comms = nx.community.louvain_communities(G, seed=42)
    node2c = {}
    for ci, c in enumerate(comms):
        for n in c:
            node2c[n] = ci
    for i, nd in enumerate(nodes):
        nd["community"] = f"L{node2c.get(i, -1):02d}"

    coords = np.array([[n["x"], n["y"], n["z"]] for n in nodes], dtype=float)
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
    d_in, d_all = apd(intra), apd(allp)
    ratio = d_in / d_all if d_all else float("nan")
    verdict = "團塊強" if ratio < 0.5 else ("有團塊" if ratio < 0.8 else "幾乎無團塊")
    print(f"{name:10} Louvain社群={len(comms):3} d_in={d_in:7.0f} d_all={d_all:7.0f} "
          f"d_in/d_all={ratio:.3f}  → {verdict}")

    g.setdefault("meta", {})["layout"]["community_algo"] = "louvain"
    json.dump(g, open(POC + f"\\graph_{name}_louvain.json", "w", encoding="utf-8"), ensure_ascii=False)


run("sancio", "graph_sancio_remap.json")
run("cs", "graph_spectral_remap.json")
