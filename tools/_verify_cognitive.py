"""驗證 D3 認知複雜度落盤 + 外部 ground truth 對照 canary。

用法：C:/Python311/python.exe tools/_verify_cognitive.py [repo路徑]
index（force 全量）→ 查 fingerprints 表 cognitive 分佈 + top 複雜函數（人眼判合理性）。
不帶參數 = index CodeSextant 自己（純 Python，所有 function 應有 cognitive 值）。
"""
import os
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8")
CS = r"E:\ai-king\項目資料\CodeSextant"
sys.path.insert(0, CS)
from codesextant import engine, storage  # noqa: E402

ROOT = sys.argv[1] if len(sys.argv) > 1 else CS
print(f"index {ROOT} (force) ...", flush=True)
engine.index_project(ROOT, force=True)

with storage.ProjectStore.open(ROOT) as store:
    rows = store.conn.execute(
        "SELECT path,name,line,node_count,cognitive FROM fingerprints").fetchall()

total = len(rows)
have = [r for r in rows if r["cognitive"] is not None]
null = total - len(have)
print(f"\nfingerprints={total} / cognitive 有值={len(have)} / NULL(UNKNOWN)={null}")

if have:
    cogs = [r["cognitive"] for r in have]
    print(f"cognitive: max={max(cogs)} mean={statistics.mean(cogs):.1f} "
          f"median={statistics.median(cogs)} zero={sum(1 for c in cogs if c == 0)}")
    print("\ntop 12 複雜函數（人眼判：該有真巢狀控制流）:")
    for r in sorted(have, key=lambda r: r["cognitive"], reverse=True)[:12]:
        rel = os.path.relpath(r["path"], ROOT)
        print(f"  cog={r['cognitive']:>3}  nc={r['node_count']:>4}  {r['name']:<28} {rel}:{r['line']}")
else:
    print("⚠ 零 cognitive 落盤——落盤鏈或語言判定有問題")

# ── D3 → health 整合驗證（證明 cognitive 真進 health 復合、非只落盤）──
sys.path.insert(0, os.path.join(CS, "_poc_graph_c"))
import code_health  # noqa: E402

with storage.ProjectStore.open(ROOT) as store:
    syms = store.get_symbols()
nodes = [{"name": s["name"], "file": os.path.relpath(s["path"], ROOT), "line": s["line"]}
         for s in syms if s.get("path")]
cov = code_health.compute(ROOT, nodes)
print(f"\nhealth 覆蓋 {cov['coverage'] * 100:.0f}% ({cov['n_covered']}/{cov['n_nodes']}) "
      f"· 未接線 {cov['n_dead']} · 重複弧 {len(cov['clone_pairs'])}")
graded = [n for n in nodes if n.get("health") is not None]
print("health 最低 10（D1腫脹/D3複雜度/D5重複 驅動褪色）:")
for n in sorted(graded, key=lambda n: n["health"])[:10]:
    print(f"  health={n['health']:.3f}  {n['name']:<28} {n['file']}:{n['line']}")
