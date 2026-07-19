"""反例：把 sancio 的邊 degree-preserving 隨機打亂（破壞模組結構、保每節點度數），
證明『美=真實模組化』——打亂後 modularity Q 應暴跌、blend 佈局應變醜（不被演算法強行美化）。
確定性 seed=42。產 graph_sanshuf_remap.json 供 group_in_box_v2.py sanshuf tidy 用。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
import networkx as nx  # noqa: E402

POC = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c"
g = json.load(open(POC + r"\graph_sancio_remap.json", encoding="utf-8"))
N = len(g["nodes"])
G = nx.Graph()
G.add_nodes_from(range(N))
G.add_edges_from((e["source"], e["target"]) for e in g["edges"])
E0 = G.number_of_edges()

# 原圖模組化（Louvain）
comms0 = nx.community.louvain_communities(G, seed=42)
Q0 = nx.community.modularity(G, comms0)

# degree-preserving double edge swap：保每節點度數、徹底打散誰連誰（破壞模組邊界）
nx.double_edge_swap(G, nswap=E0 * 6, max_tries=E0 * 60, seed=42)
comms1 = nx.community.louvain_communities(G, seed=42)
Q1 = nx.community.modularity(G, comms1)

g["edges"] = [{"source": int(u), "target": int(v)} for u, v in G.edges()]
json.dump(g, open(POC + r"\graph_sanshuf_remap.json", "w", encoding="utf-8"), ensure_ascii=False)
print(f"原 sancio: E={E0} Louvain社群={len(comms0)} Q={Q0:.3f}")
print(f"打亂後   : E={G.number_of_edges()} Louvain社群={len(comms1)} Q={Q1:.3f}")
print(f"Q 變化: {Q0:.3f} -> {Q1:.3f} (降 {100*(Q0-Q1)/Q0:.0f}%)  ＝ 模組結構被破壞")
