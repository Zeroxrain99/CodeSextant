"""代碼健康度（PoC 薄 wrapper）— 委派 codesextant.health 數值核心 + PoC nodes/key 對齊。

數值邏輯（D1 腫脹 / D3 認知複雜度 / D5 重複 → health、D6 未接線 → dead、權重/renormalize/
clone_pairs）已固化進正式引擎 `codesextant.health`（單一數值真相源、引擎 get_health 與本 PoC 共用、
避免兩處漂移）。本檔只負責 PoC 特有的三件事：① 從 fingerprints 表撈指紋 ② find_unwired 取
dead_keys ③ 把 build_repo_graph 的「佈局 node（含相對 file + line）」對齊到指紋鍵。

⛔ 視覺映射（飽和度/透明度/暗弧）在前端 graph-common.js，非本檔。
"""
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
CS = r"E:\ai-king\項目資料\CodeSextant"
sys.path.insert(0, CS)
from codesextant import engine, storage  # noqa: E402
from codesextant import health as _health


def compute(root, nodes):
    """對 nodes（含相對 file + line）就地加 health[0,1]|None + dead(bool)。回覆蓋率報告 + clone_pairs。"""
    root = os.path.abspath(root)
    with storage.ProjectStore.open(root) as store:
        fps = store.conn.execute(
            "SELECT path,line,node_count,shape_hash,cognitive FROM fingerprints").fetchall()
    shape_cnt = Counter(r[3] for r in fps)
    # value=(node_count, shape_hash, cognitive)；cognitive None=UNKNOWN（非高信心語言/無 body）
    fp_by = {(os.path.normcase(r[0]), int(r[1])): (int(r[2] or 0), r[3], r[4]) for r in fps}
    # D6 未接線（線索→dead）；失敗不炸 health（fail-soft）
    try:
        uw = engine.find_unwired(root)
        dead_keys = {(os.path.normcase(os.path.abspath(c["path"])), int(c["line"]))
                     for c in uw.get("candidates", []) if c.get("verdict") == "UNWIRED_CANDIDATE"}
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ find_unwired 失敗（D6 跳過）：{e}")
        dead_keys = set()
    # 數值核心委派 codesextant.health（引擎/PoC 單一真相源）
    return _health.annotate(
        nodes, fp_by, shape_cnt, dead_keys,
        key_of=lambda n: (os.path.normcase(os.path.join(root, n.get("file", ""))),
                          int(n.get("line", 0))))
