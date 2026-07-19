"""紀律轉美鐵證：CodeSextant 星圖按 health 著色（無 bloom、matplotlib 清楚看品質維度）。
左＝社群著色（看結構）｜右＝health 著色（看 clean-code 品質：紅=爛/綠=好/灰=UNKNOWN/黑圈=未接線）。
證明同一張確定性佈局可疊加「品質」維度——結構好的團塊裡，重複碼/腫脹函數會被標出來。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
import matplotlib  # noqa: E402
import numpy as np  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

P = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c\graph_cs_v3_tidy.json"
g = json.load(open(P, encoding="utf-8"))
nodes = g["nodes"]
coords = np.array([[n["x"], n["y"], n["z"]] for n in nodes], dtype=float)

# 左：社群著色
comm = [n["community"] for n in nodes]
uniq = sorted(set(comm))
c2i = {c: i for i, c in enumerate(uniq)}
cmap20 = plt.cm.tab20


def comm_color(c):
    if c == "Ltest":
        return (0.30, 0.32, 0.38, 0.30)
    if c == "Lsingleton":
        return (0.5, 0.5, 0.55, 0.4)
    return cmap20(c2i[c] % 20)


# 右：health 著色（RdYlGn：紅爛→綠好），UNKNOWN 灰、測試帶/孤點不評
rdylgn = plt.cm.RdYlGn


def health_color(n):
    if n.get("community") in ("Ltest", "Lsingleton"):
        return (0.28, 0.30, 0.35, 0.22)
    h = n.get("health")
    if h is None:
        return (0.5, 0.5, 0.52, 0.5)          # UNKNOWN 中性灰
    return rdylgn(h)                            # 0 紅 → 1 綠


fig = plt.figure(figsize=(22, 11), facecolor="#0a0e16")
for sp, (title, colf) in enumerate([
    ("community (structure)", lambda n, c: comm_color(c)),
    ("health + clone arcs (red line=duplicate twins / black ring=dead)", lambda n, c: health_color(n)),
], 1):
    ax = fig.add_subplot(1, 2, sp, projection="3d", facecolor="#0a0e16")
    colors = [colf(n, n["community"]) for n in nodes]
    # 未接線(dead) 加黑圈標記
    edge = ["#000000" if n.get("dead") else "none" for n in nodes]
    lw = [1.2 if n.get("dead") else 0 for n in nodes]
    ax.scatter(coords[:, 0], coords[:, 1], coords[:, 2], c=colors, s=14,
               alpha=0.9, edgecolors=edge, linewidths=lw)
    if sp == 2:  # health panel 疊「重複碼暗弧」：孿生函數連暗紅線（跨團塊＝複製貼上散各處）
        for e in g.get("clone_edges", []):
            a, b = e[0], e[1]
            ax.plot([coords[a, 0], coords[b, 0]], [coords[a, 1], coords[b, 1]],
                    [coords[a, 2], coords[b, 2]], color=(0.85, 0.16, 0.18), alpha=0.40, linewidth=0.7)
    ax.view_init(elev=22, azim=35)
    ax.set_axis_off()
    ax.set_title(title, color="#cfe8ff", fontsize=13)
out = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c\plot_cs_health.png"
plt.savefig(out, dpi=80, facecolor="#0a0e16", bbox_inches="tight")
plt.close()
n_dead = sum(1 for n in nodes if n.get("dead"))
print(f"saved {out}  (dead={n_dead} 加黑圈)")
