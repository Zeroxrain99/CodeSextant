"""外部 ground truth 對照 canary — 認知複雜度（D3）能否拉開不同品質的真實 repo。

跑法：C:\\Python311\\python.exe tools\\cog_canary.py
       （PowerShell 先 [Console]::OutputEncoding = [System.Text.Encoding]::UTF8）

輸出每個 repo 的認知複雜度分布（n/中位數/平均/p90/max/>15 佔比）+ 最難讀熱點 top6。
用途：health 改進 / walker 改動後重跑，看分布是否合理、熱點是否人眼可複核。
⛔ 唯讀導航圖：cog 高=「值得讀碼複核」訊號，非「應改」決策。

2026-06-23 首跑結果（見 docs/認知複雜度_白皮書對齊與學術效度_查證評估_2026-06-23.md §八）：
  CodeSextant 自己 n=267 mean=8.41 max=335（複雜度 walker 自己最高=指標誠實不偏袒）
  concinno         n=4848 mean=4.80 max=78（大但拆得細、平均反而低=反直覺真實發現）
"""
import json
import os
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8")
PKG = os.environ.get("CODESEXTANT_PKG_ROOT", r"E:\ai-king\項目資料\CodeSextant")
os.environ["CODESEXTANT_PKG_ROOT"] = PKG
sys.path.insert(0, PKG)
from codesextant import engine, storage  # noqa: E402


def cog_rows(repo: str):
    engine.index_project(repo, force=True)
    abs_path = os.path.abspath(repo)
    with storage.ProjectStore.open(abs_path) as store:
        rows = store.conn.execute(
            "SELECT path,line,cognitive FROM fingerprints WHERE cognitive IS NOT NULL"
        ).fetchall()
    return [(r["path"], int(r["line"]), int(r["cognitive"])) for r in rows]


def summarize(label: str, rows):
    vals = [c for _, _, c in rows]
    if not vals:
        print(f"{label}: 無 cognitive 資料")
        return None
    vs = sorted(vals)
    n = len(vs)
    p90 = vs[min(n - 1, int(n * 0.9))]
    over15 = sum(1 for v in vals if v > 15)
    print(f"\n=== {label} ===")
    print(f"函數數 n={n}  max={max(vals)}  mean={statistics.mean(vals):.2f}  "
          f"median={statistics.median(vals)}  p90={p90}")
    print(f">15(SonarSource 預設閾值): {over15} ({over15 / n * 100:.1f}%)")
    print("最難讀熱點 top6（線索非決策、刪改前讀碼）:")
    for p, l, c in sorted(rows, key=lambda x: -x[2])[:6]:
        parent = os.path.basename(os.path.dirname(p))
        print(f"   cog={c:3d}  ...{os.sep}{parent}{os.sep}{os.path.basename(p)}:{l}")
    return {"n": n, "max": max(vals), "mean": round(statistics.mean(vals), 2),
            "median": statistics.median(vals), "p90": p90,
            "over15_pct": round(over15 / n * 100, 1)}


def main():
    repos = [
        ("CodeSextant 自己 (剛對抗 review·模組化)", PKG + r"\codesextant"),
        ("concinno (大型多年累積)", r"E:\ai-king\projects\concinno\src\concinno"),
    ]
    res = {}
    for label, repo in repos:
        if not os.path.isdir(repo):
            print(f"{label}: 跳過（路徑不存在 {repo}）")
            continue
        try:
            res[label] = summarize(label, cog_rows(repo))
        except Exception as e:  # noqa: BLE001
            import traceback
            print(f"\n{label}: 失敗 {e}")
            traceback.print_exc()
    print("\n----RESULT JSON----")
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
