"""紀律轉美後端：per-node 代碼健康度數值（D1 腫脹 + D3 認知複雜度 + D5 重複 → health[0,1]；
D6 死碼 → dead）。純數值、零隨機、可序列化。

⛔ 不含視覺映射（飽和度/透明度/暗弧公式）＝那是展示層（星圖前端/PoC）的事，引擎只給數值。
鐵律：①唯讀導航圖，health 是線索非定論、絕不出「應刪/應改」決策 ②UNKNOWN/N-A 維度（無指紋的
class/變數、非高信心語言的 cognitive）剔除並對剩餘權重 renormalize（不洗成滿分＝防 vapor）
③確定性純函數。preset「平衡」權重，env 可調（L0 鐵律 #6）。

引擎（engine.get_health）與 PoC（_poc_graph_c/code_health.py）共用本模組的 annotate
＝單一數值真相源（不重複實作、避免兩處漂移）。
"""
import os
from collections import defaultdict

# SSOT §2.3 preset「平衡」權重（D1/D3/D5 有效；D10 長參數此版 UNKNOWN）。env 可調（L0 鐵律 #6）。
W = {"dup": float(os.environ.get("CODESEXTANT_W_DUP", 0.30)),
     "cog": float(os.environ.get("CODESEXTANT_W_COG", 0.30)),
     "bloat": float(os.environ.get("CODESEXTANT_W_BLOAT", 0.25))}
BLOAT_LO = int(os.environ.get("CODESEXTANT_BLOAT_LO", 80))     # node_count≤80 不算腫脹
BLOAT_HI = int(os.environ.get("CODESEXTANT_BLOAT_HI", 200))    # ≥200 滿扣
COG_LO = int(os.environ.get("CODESEXTANT_COG_LO", 8))          # cognitive≤8 不算複雜
COG_HI = int(os.environ.get("CODESEXTANT_COG_HI", 25))         # ≥25 滿扣


def _smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def annotate(nodes, fp_by, shape_cnt, dead_keys, key_of):
    """就地對 nodes 加 'health'(float[0,1]|None) + 'dead'(bool)；回覆蓋率報告 + clone_pairs。

    nodes    : list[dict]（就地寫入）
    fp_by    : {(normcase_path, line): (node_count, shape_hash, cognitive)}；cognitive None=UNKNOWN
    shape_cnt: Counter[shape_hash]（判重複：>1 即 EXACT/RENAMED 孿生）
    dead_keys: set[(normcase_path, line)]（D6 未接線 → 透明度，不進 health 數值）
    key_of   : node → (normcase_path, line)（caller 自定如何從 node 取鍵）
    回 {n_nodes, n_covered, coverage, n_dead, clone_pairs}。clone_pairs=同 shape star 連接（避 O(n²)）。
    """
    shape_to_idx = defaultdict(list)
    n_cov = 0
    for idx, n in enumerate(nodes):
        key = key_of(n)
        pen = {}
        fp = fp_by.get(key)
        if fp:
            node_count, shape, cog = fp
            pen["bloat"] = _smoothstep(BLOAT_LO, BLOAT_HI, node_count)
            pen["dup"] = 1.0 if shape_cnt[shape] > 1 else 0.0
            if cog is not None:   # D3：高信心語言才計權；None=UNKNOWN 剔除 renormalize（不洗滿分）
                pen["cog"] = _smoothstep(COG_LO, COG_HI, cog)
            if shape_cnt[shape] > 1:
                shape_to_idx[shape].append(idx)
        if pen:   # 有有效維度 → renormalize（UNKNOWN 不洗滿分＝C2 防 vapor）
            sw = sum(W[k] for k in pen)
            penalty = min(max(sum(pen[k] * W[k] for k in pen) / sw, 0.0), 1.0)
            n["health"] = round(1.0 - penalty, 4)
            n_cov += 1
        else:     # 無指紋（class/變數）= UNKNOWN 中性（前端走中性值、非滿分非 0）
            n["health"] = None
        n["dead"] = key in dead_keys

    clone_pairs = []
    for _shape, idxs in shape_to_idx.items():
        idxs.sort()
        for j in idxs[1:]:
            clone_pairs.append([idxs[0], j])

    n_dead = sum(1 for n in nodes if n.get("dead"))
    return {"n_nodes": len(nodes), "n_covered": n_cov,
            "coverage": round(n_cov / max(1, len(nodes)), 3),
            "n_dead": n_dead, "clone_pairs": clone_pairs}
