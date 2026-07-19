"""即時出圖 API — daemon /graph_data 調用。對任意 repo 一條龍出「帶完整代碼 + 佈局 + health」星圖 dict。
鏈：build_repo_graph（抽符號+完整碼+spectral）→ group_in_box_v3.build（連續閘佈局+louvain 社群）→ 回 tidy dict。

⛔ 依賴 scipy/networkx（佈局），故 daemon 端 lazy import 本模組（保持核心引擎輕量）。
"""
import json
import os
import sys

POC = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c"
if POC not in sys.path:
    sys.path.insert(0, POC)


def build_graph_data(project, name="live"):
    """對 project repo 即時出圖，回 v3 tidy 圖 dict（節點帶完整代碼 + 佈局座標 + health + 社群）。

    project：任意 repo 絕對路徑（中文 OK，純內部字串非 argv）。
    name：圖識別名（決定中介檔 graph_{name}_remap.json / graph_{name}_v3_tidy.json）。
    """
    import build_repo_graph
    import group_in_box_v3
    build_repo_graph.build_repo_graph(project, name)   # 寫 graph_{name}_remap.json（節點帶完整 code）
    group_in_box_v3.build(name, "tidy")                # 讀 remap → 連續閘佈局 → 寫 graph_{name}_v3_tidy.json
    tidy = os.path.join(POC, f"graph_{name}_v3_tidy.json")
    with open(tidy, encoding="utf-8") as f:
        g = json.load(f)
    g.setdefault("meta", {})["live_project"] = os.path.abspath(project)
    return g
