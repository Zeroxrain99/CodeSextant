"""給既有 graph json 的每個 node 補 is_test 標記（代碼地圖分離測試的舊圖遷移工具）。
新圖由 build_repo_graph 直接帶 is_test；本工具只為已存在、缺欄位的舊圖補上。
用法: python patch_istest.py <in.json> <out.json>"""
import json
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c")
from test_classifier import is_test_path  # noqa: E402

src = sys.argv[1] if len(sys.argv) > 1 else r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c\graph_real.json"
dst = sys.argv[2] if len(sys.argv) > 2 else r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c\graph_cs_remap.json"

g = json.load(open(src, encoding="utf-8"))
nodes = g["nodes"]
n_test = 0
top_dirs = Counter()
for n in nodes:
    f = n.get("file", "")
    n["is_test"] = is_test_path(f)
    if n["is_test"]:
        n_test += 1
    seg = f.replace("\\", "/").split("/")[0] if f else "(root)"
    top_dirs[seg] += 1
g.setdefault("meta", {})["n_test"] = n_test

json.dump(g, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
print(f"{src}\n  -> {dst}")
print(f"  {len(nodes)} 節點：{n_test} 測試 / {len(nodes) - n_test} 生產")
print("  頂層目錄分布：")
for d, c in top_dirs.most_common(10):
    print(f"    {c:5}  {d}")
