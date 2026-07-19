"""檢視 graph_cs_v3_tidy.json 的 health/dead 分佈 — 驗證紀律轉美數據真實有對比。"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = r"E:\ai-king\項目資料\CodeSextant\_poc_graph_c\graph_cs_v3_tidy.json"
g = json.load(open(P, encoding="utf-8"))
nodes = g["nodes"]
prod = [n for n in nodes if not n.get("is_test") and n.get("community") != "Ltest"]

buckets = {"UNKNOWN(None)": 0, "爛 [0,0.3)": 0, "中 [0.3,0.7)": 0, "好 [0.7,1]": 0}
for n in prod:
    h = n.get("health")
    if h is None:
        buckets["UNKNOWN(None)"] += 1
    elif h < 0.3:
        buckets["爛 [0,0.3)"] += 1
    elif h < 0.7:
        buckets["中 [0.3,0.7)"] += 1
    else:
        buckets["好 [0.7,1]"] += 1

print(f"生產節點 {len(prod)}（測試帶/孤點不計）health 分佈：")
for k, v in buckets.items():
    print(f"  {k:14} {v:4}  {'█' * (v * 40 // max(1, len(prod)))}")

n_dead = sum(1 for n in prod if n.get("dead"))
print(f"\n未接線(dead) 生產節點：{n_dead}")

scored = sorted([n for n in prod if n.get("health") is not None], key=lambda n: n["health"])
print("\n最褪色（health 最低）前 10（驗證是否真大/重複函數）：")
for n in scored[:10]:
    print(f"  health={n['health']:.3f}  {n.get('kind',''):9} {n['name']:28} {n.get('file','')}")
print("\n最鮮豔（health 最高）前 5：")
for n in scored[-5:]:
    print(f"  health={n['health']:.3f}  {n.get('kind',''):9} {n['name']:28} {n.get('file','')}")
