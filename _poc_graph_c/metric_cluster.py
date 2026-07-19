"""客觀團塊指標：同目錄社群的節點在 spectral 空間是否聚集。
d_in/d_all << 1 = 同社群明顯更近 = spectral 真把同模組佈一起（結構決定形狀成立）；
≈1 = 沒佈出團塊。紅藍 Phase0 量化驗收標準。"""
import json
import random
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
import numpy as np  # noqa: E402

random.seed(0)
POC = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c"


def metric(path):
    g = json.load(open(path, encoding="utf-8"))
    nodes = g["nodes"]
    if "x" not in nodes[0]:
        return None
    coords = np.array([[n["x"], n["y"], n["z"]] for n in nodes], dtype=float)
    comm = [n.get("community", "") for n in nodes]
    N = len(nodes)
    by = defaultdict(list)
    for i, c in enumerate(comm):
        by[c].append(i)

    def apd(pairs):
        if not pairs:
            return float("nan")
        d = [np.linalg.norm(coords[a] - coords[b]) for a, b in pairs]
        return float(np.median(d))   # 中位數抗離群

    intra = []
    for idxs in by.values():
        if len(idxs) < 2:
            continue
        for _ in range(min(300, len(idxs) * 3)):
            a, b = random.sample(idxs, 2)
            intra.append((a, b))
    allp = [(random.randrange(N), random.randrange(N)) for _ in range(8000)]
    d_in, d_all = apd(intra), apd(allp)
    return N, len(by), d_in, d_all, d_in / d_all if d_all else float("nan")


for f in ["graph_spectral_pure.json", "graph_spectral_remap.json",
          "graph_sancio_pure.json", "graph_sancio_remap.json"]:
    try:
        r = metric(POC + "\\" + f)
        if r is None:
            print(f"{f:30} (無座標)")
        else:
            N, C, d_in, d_all, ratio = r
            verdict = "團塊強" if ratio < 0.5 else ("有團塊" if ratio < 0.8 else "幾乎無團塊")
            print(f"{f:30} N={N:5} 社群={C:3} d_in={d_in:7.0f} d_all={d_all:7.0f} "
                  f"d_in/d_all={ratio:.3f}  → {verdict}")
    except Exception as e:
        print(f"{f}: {e}")
