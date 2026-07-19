"""matplotlib 3D 散點看 v2 超節點 spectral 中心 tidy vs spiral 團塊（singleton 帶灰色）。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
import matplotlib  # noqa: E402
import numpy as np  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

POC = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c"


def plot(name, mode):
    g = json.load(open(POC + f"\\graph_{name}_v3_{mode}.json", encoding="utf-8"))
    nodes = g["nodes"]
    coords = np.array([[n["x"], n["y"], n["z"]] for n in nodes], dtype=float)
    comm = [n["community"] for n in nodes]
    uniq = sorted(set(comm))
    c2i = {c: i for i, c in enumerate(uniq)}
    cmap = plt.cm.tab20

    def col(c):
        if c == "Ltest":
            return (0.30, 0.30, 0.34, 0.30)    # 測試帶：暗灰、最淡（一眼辨與生產分離）
        if c == "Lsingleton":
            return (0.5, 0.5, 0.55, 0.45)
        return cmap(c2i[c] % 20)
    colors = [col(c) for c in comm]
    n_test = sum(1 for c in comm if c == "Ltest")
    fig = plt.figure(figsize=(20, 10), facecolor="#0a0e16")
    for sp, (az, el) in enumerate([(30, 20), (120, 35)], 1):
        ax = fig.add_subplot(1, 2, sp, projection="3d", facecolor="#0a0e16")
        ax.scatter(coords[:, 0], coords[:, 1], coords[:, 2], c=colors, s=11, alpha=0.82, edgecolors="none")
        ax.view_init(elev=el, azim=az)
        ax.set_axis_off()
        ax.set_title(f"{name} v3 {mode}  (test={n_test} 灰外圈)  view{sp}", color="#cfe8ff")
    out = POC + f"\\plot_{name}_v3_{mode}.png"
    plt.savefig(out, dpi=70, facecolor="#0a0e16", bbox_inches="tight")
    plt.close()
    print("saved", out)


for n, m in [("cs", "tidy")]:
    plot(n, m)
