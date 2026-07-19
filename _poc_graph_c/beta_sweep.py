"""(d) 調 β：BETA_TIDY 從 0(純結構方向) → 1(純 Fibonacci 均勻化) 掃描看均勻度變化。
β 低 = 中心方向忠於超節點 spectral 結構（關聯近的社群靠近，但可能擠）；
β 高 = 中心被推向 Fibonacci 球面均勻分布（漂亮均勻，但犧牲結構保真）。
產 4 檔 graph json + 一張 2x2 對照圖。用法: python beta_sweep.py"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
import matplotlib  # noqa: E402
import numpy as np  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

POC = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c"
sys.path.insert(0, POC)
import group_in_box_v3 as gib  # noqa: E402

BETAS = [0.0, 0.4, 0.7, 1.0]   # 純結構 / 預設 / 偏均勻 / 純均勻


def col(c):
    if c == "Ltest":
        return (0.30, 0.30, 0.34, 0.28)
    if c == "Lsingleton":
        return (0.5, 0.5, 0.55, 0.45)
    cmap = plt.cm.tab20
    return cmap(hash(c) % 20)


results = []
for be in BETAS:
    r = gib.build("cs", "tidy", beta=be)
    results.append(r)

fig = plt.figure(figsize=(20, 16), facecolor="#0a0e16")
for sp, (be, r) in enumerate(zip(BETAS, results), 1):
    g = json.load(open(r["out"], encoding="utf-8"))
    nodes = g["nodes"]
    coords = np.array([[n["x"], n["y"], n["z"]] for n in nodes], dtype=float)
    colors = [col(n["community"]) for n in nodes]
    ax = fig.add_subplot(2, 2, sp, projection="3d", facecolor="#0a0e16")
    ax.scatter(coords[:, 0], coords[:, 1], coords[:, 2], c=colors, s=10, alpha=0.82, edgecolors="none")
    ax.view_init(elev=22, azim=35)
    ax.set_axis_off()
    ax.set_title(f"beta={be:.1f}  Q={r['Q']:.3f}  d_in/d_all={r['ratio']:.3f}",
                 color="#cfe8ff", fontsize=14)
out = POC + r"\plot_cs_beta_sweep.png"
plt.savefig(out, dpi=72, facecolor="#0a0e16", bbox_inches="tight")
plt.close()

print("\n── β sweep 指標（cs，生產 324 / 測試 274 外圈帶）──")
print(f"{'beta':>6} {'Q':>7} {'strength':>9} {'d_in/d_all':>11} {'高beauty社群':>12}")
for r in results:
    print(f"{r['beta']:>6.1f} {r['Q']:>7.3f} {r['strength']:>9.2f} {r['ratio']:>11.3f} {r['high_beauty']:>12}")
print(f"\nsaved {out}")
