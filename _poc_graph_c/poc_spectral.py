"""Phase0 PoC：對 real 圖跑確定性 spectral 3D 佈局，落兩版座標(pure / remap)。
紅藍CBUA SSOT《結構決定形狀_確定性佈局演算法_2026-06-22》§2.1-2.5。
interpreter 必用 C:/Python311（有 scipy/numpy/networkx）。
real 主分量只 570 節點 → 直接 dense np.linalg.eigh（確定性、無 lobpcg 收斂問題）；
萬級 synth 才需 lobpcg，Phase1 再處理。"""
import copy
import hashlib
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402

BASE = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c"
SRC = BASE + r"\graph_real.json"
OUT_PURE = BASE + r"\graph_spectral_pure.json"
OUT_REMAP = BASE + r"\graph_spectral_remap.json"
TARGET_R = 1700.0


def _canonicalize(vecs, deg):
    """符號確定性：每軸用度加權偏度定號（同輸入同輸出，去 ± 歧義）。"""
    out = vecs.copy()
    for ax in range(out.shape[1]):
        col = out[:, ax]
        if np.sum(deg * (col ** 3)) < 0:
            out[:, ax] = -col
    return out


def _spectral_main(G, main_idx, dim=3):
    """主連通分量 spectral：座標＝Laplacian 第 λ1..λdim 特徵向量（丟 λ0≈0）。"""
    relabel = {gi: k for k, gi in enumerate(main_idx)}
    Gr = nx.relabel_nodes(G.subgraph(main_idx), relabel)
    n = Gr.number_of_nodes()
    A = nx.to_numpy_array(Gr, nodelist=range(n))
    deg = A.sum(axis=1)
    L = np.diag(deg) - A
    vals, vecs = np.linalg.eigh(L)          # 對稱→升序，LAPACK 確定性
    vecs = vecs[:, 1:dim + 1]               # 主分量連通→唯一 λ0，丟它取結構軸
    return _canonicalize(vecs, deg)


def _place_islands(coords, small_comps, R):
    """孤立/小分量：hash(node.i) 確定性散到外圈球殼（不塌原點重疊）。"""
    for c in small_comps:
        for gi in sorted(c):
            h = int(hashlib.md5(str(gi).encode()).hexdigest()[:8], 16)
            phi = (h % 10000) / 10000 * 2 * np.pi
            y = ((h >> 16) % 10000) / 10000 * 2 - 1
            rad = np.sqrt(max(0.0, 1 - y * y))
            coords[gi] = [np.cos(phi) * rad * R, y * R, np.sin(phi) * rad * R]


def _rescale(coords, target):
    """p95 縮放（非 max，防單一離群把整體壓扁）。"""
    r = np.linalg.norm(coords, axis=1)
    p95 = np.percentile(r, 95) or 1.0
    return coords * (target / p95)


def _density_remap(coords):
    """穿梭飽滿版：z 軸 sqrt(振幅)平衡抗薄餅 + 徑向 rank 重映射（純函數零 RNG）。"""
    c = coords.copy()
    for ax in range(3):
        amp = np.std(c[:, ax]) or 1.0
        c[:, ax] = c[:, ax] / np.sqrt(amp)
    r = np.linalg.norm(c, axis=1)
    order = np.argsort(r)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(len(r))
    target_r = (ranks + 1) / len(r)         # 均勻 0..1
    scale = target_r / (r + 1e-9)
    return c * scale[:, None]


def compute_layout(n_nodes, edges, dim=3):
    G = nx.Graph()
    G.add_nodes_from(range(n_nodes))
    G.add_edges_from((e["source"], e["target"]) for e in edges)
    coords = np.zeros((n_nodes, dim))
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    main_idx = sorted(comps[0])
    coords[main_idx] = _spectral_main(G, main_idx, dim)
    _place_islands(coords, comps[1:], R=1.0)        # 島先單位球，下面統一 rescale
    coords = _rescale(coords, TARGET_R)
    iso_mask = np.ones(n_nodes, bool)
    iso_mask[main_idx] = False
    coords[iso_mask] *= 1.35                          # 島推到主團外圈
    assert np.isfinite(coords).all(), "NaN/Inf in coords"
    return coords, len(comps), int(iso_mask.sum())


def attach(graph, coords, algo, comp_count):
    for i, nd in enumerate(graph["nodes"]):
        nd["x"], nd["y"], nd["z"] = float(coords[i, 0]), float(coords[i, 1]), float(coords[i, 2])
    graph.setdefault("meta", {})["layout"] = {"algo": algo, "dim": 3, "v0": "deg_norm", "components": comp_count}
    return graph


def _report(tag, cc):
    r = np.linalg.norm(cc, axis=1)
    amp = [np.std(cc[:, a]) for a in range(3)]
    zratio = amp[2] / max(amp[0], amp[1], 1e-9)
    print(f"{tag}: r[min/p50/p95/max]={r.min():.0f}/{np.percentile(r,50):.0f}/"
          f"{np.percentile(r,95):.0f}/{r.max():.0f} | z/xy振幅比={zratio:.2f}")


def main():
    g = json.load(open(SRC, encoding="utf-8"))
    n = len(g["nodes"])
    coords, comps, iso = compute_layout(n, g["edges"], dim=3)
    print(f"compute_layout: N={n} 分量={comps} 孤立={iso}")

    g_pure = attach(copy.deepcopy(g), coords, "spectral_eigh_pure", comps)
    json.dump(g_pure, open(OUT_PURE, "w", encoding="utf-8"), ensure_ascii=False)

    coords_remap = _rescale(_density_remap(coords), TARGET_R)
    g_remap = attach(copy.deepcopy(g), coords_remap, "spectral_eigh_remap", comps)
    json.dump(g_remap, open(OUT_REMAP, "w", encoding="utf-8"), ensure_ascii=False)

    _report("pure ", coords)
    _report("remap", coords_remap)
    print(f"OK -> {OUT_PURE}")
    print(f"   -> {OUT_REMAP}")


if __name__ == "__main__":
    main()
