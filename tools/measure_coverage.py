"""量測 CodeSextant 在一個 repo 上的「找引用」解析覆蓋率，並誠實標出殘差在哪。

為什麼需要這支
==============
工具在每次查詢回應裡都會附「我可能漏了什麼」，但那是**單次查詢層級**的自述。
使用者真正想知道的是另一個問題：「這個工具在我的語言、我的 repo 上，整體到底
解得動幾成？」——那需要一個離線可重跑、可比較、可被打臉的數字。

量測方法（刻意選一個不會自我美化的定義）
========================================
對每個抽樣符號，用名稱先做一次純文字掃描當作**召回上界**（superset：任何真正的
引用一定會出現在這裡面，但裡面也混著同名雜訊——註解、字串、別的類別的同名方法）。
接著看 CodeSextant 能把其中多少**升級成高信心**（真的解析到定義、不是名字像）。

    解析率 = 高信心引用數 ÷ 名稱級候選數

⛔ 這個定義對工具是不利的（分母含大量本來就不該算的同名雜訊），所以它**不是**
「準確率」。它衡量的是「面對名稱級的一團模糊，工具能斬釘截鐵確認多少」。
選這個定義正是因為它不能靠調整分母灌水——分母是純文字掃描決定的，跟工具無關。

殘差（解不掉的那部分）誠實歸因
==============================
剩下的一定不是零。它由三塊組成，本工具會分開報，不混在一起：
  · same_name_noise  同名雜訊：註解/字串/不同類別的同名成員——**本來就不該算**
  · dynamic          動態解析：反射、字串組出來的名字、DI 容器——靜態分析的本質限制
  · unresolved       工具真的沒解出來——這才是可以改進的部分

⛔ 不做的事：不會為了讓數字好看而縮小分母、不會把 dynamic 併進 same_name_noise、
不會只挑好看的語言報。要嘛全報，要嘛不報。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine, storage  # noqa: E402

# 純文字掃描時要跳過的目錄——這些不是「這個 repo 的碼」
_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules",
              ".mypy_cache", ".pytest_cache", "build", "dist", "target", ".tox"}

_LANG_EXT = {
    "python": (".py",), "typescript": (".ts", ".tsx"), "javascript": (".js", ".jsx"),
    "go": (".go",), "rust": (".rs",), "java": (".java",), "csharp": (".cs",),
    "c": (".c", ".h"), "cpp": (".cpp", ".hpp", ".cc"), "ruby": (".rb",),
    "php": (".php",), "kotlin": (".kt",), "swift": (".swift",),
    "lua": (".lua",), "bash": (".sh",),
}


def _lang_of(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    for lang, exts in _LANG_EXT.items():
        if ext in exts:
            return lang
    return "other"


def name_level_candidates(root: str, name: str) -> int:
    """純文字掃描：這個名字以**完整識別字**在 repo 出現幾次（召回上界）。

    ⛔ 一定要用字界（word boundary）比對，不能用 str.count() 數子字串——否則查 `path`
    會把 `filepath`、`pathlib`、`dispatch` 全算進來，分母瞬間灌成十幾倍，解析率被壓成
    個位數，好工具被自己的量測方法冤枉。2026-07-19 第一版就是這樣寫的，跑出 2.0% 才
    發現不對。**量測方法本身也要先被驗證過**。
    """
    pattern = re.compile(r"\b" + re.escape(name) + r"\b")
    hits = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if _lang_of(os.path.join(dirpath, fn)) == "other":
                continue
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8", errors="ignore") as fh:
                    hits += len(pattern.findall(fh.read()))
            except OSError:
                continue
    return hits


def measure(root: str, *, sample: int, seed: int, timeout_per_symbol: float,
            path_contains: str | None = None) -> dict:
    root = os.path.abspath(root)
    if not storage.db_path_for(root).exists():
        raise SystemExit(f"這個專案還沒被索引：{root}\n先跑 index_project 再來量。")

    with storage.ProjectStore.open(root) as store:
        rows = [dict(r) for r in store.conn.execute(
            "SELECT path,name,kind,line FROM symbols WHERE scope='' AND length(name)>3"
        ).fetchall()]
    # ⚠ 沒有這個過濾的話，量到的多半是「這個 repo 有多少獨立腳本」而不是「工具解得動
    # 多少」——一次性實驗腳本、探針、CLI 入口的頂層函式本來就沒有 repo 內呼叫者，
    # 零高信心是正確答案不是失敗。要跟別的工具比數字，兩邊都得先講清楚量的是哪個範圍。
    if path_contains:
        # ⛔ 必須比對「相對於 root 的路徑」——比絕對路徑會踩到「專案根目錄自己就叫那個名字」
        # 的陷阱：--path-contains codesextant 在 E:\...\CodeSextant\ 底下會命中每一個檔，
        # 過濾等於沒作用，數字卻看起來像有過濾過。
        needle = path_contains.lower().replace("\\", "/")
        rows = [r for r in rows
                if needle in os.path.relpath(r["path"], root).lower().replace("\\", "/")]
    if not rows:
        raise SystemExit("這個範圍內沒有可抽樣的頂層符號。")

    rng = random.Random(seed)          # 固定種子＝任何人重跑都拿到同一組樣本
    picked = rng.sample(rows, min(sample, len(rows)))

    per_lang: dict[str, dict] = {}
    details = []
    for sym in picked:
        lang = _lang_of(sym["path"])
        bucket = per_lang.setdefault(lang, {
            "symbols": 0, "name_candidates": 0, "high_conf": 0, "low_conf": 0,
            "zero_high": 0, "errors": 0, "elapsed_sec": 0.0})
        bucket["symbols"] += 1
        cand = name_level_candidates(root, sym["name"])
        bucket["name_candidates"] += cand

        t0 = time.time()
        try:
            res = engine.find_references(root, sym["name"], def_path=sym["path"])
            hi = len(res.get("high_confidence") or [])
            lo = len(res.get("low_confidence") or [])
        except Exception as exc:                        # noqa: BLE001
            bucket["errors"] += 1
            details.append({"symbol": sym["name"], "error": f"{type(exc).__name__}: {exc}"})
            continue
        finally:
            bucket["elapsed_sec"] += time.time() - t0

        bucket["high_conf"] += hi
        bucket["low_conf"] += lo
        if hi == 0:
            bucket["zero_high"] += 1
        details.append({"symbol": sym["name"], "lang": lang, "path": sym["path"],
                        "name_candidates": cand, "high": hi, "low": lo})

    # 每個符號各自的解析率，再取中位數。
    # ⛔ 不能只報「總高信心 ÷ 總候選」——那個加總會被 `project`、`main` 這種到處都是的
    # 通用參數名主導（單一個 `project` 就貢獻 479 個名稱級命中，其中絕大多數根本是別的
    # 函式的參數、跟這個符號無關）。實測：加總法 4.3%，但對特徵明顯的名字（classify_orphan
    # 12→10、_resolve_openai_call 6→5）其實有八成以上。兩個數字都報，差距本身就是情報。
    by_lang_rates: dict[str, list] = {}
    for d in details:
        if "lang" in d and d["name_candidates"]:
            by_lang_rates.setdefault(d["lang"], []).append(d["high"] / d["name_candidates"])
    for lang, b in per_lang.items():
        cand = b["name_candidates"]
        rates = sorted(by_lang_rates.get(lang, []))
        b["resolve_rate_pooled"] = round(b["high_conf"] / cand, 4) if cand else None
        b["resolve_rate_median"] = (round(rates[len(rates) // 2], 4) if rates else None)
        b["zero_high_rate"] = round(b["zero_high"] / b["symbols"], 4) if b["symbols"] else None
        b["sec_per_symbol"] = round(b["elapsed_sec"] / b["symbols"], 3) if b["symbols"] else None

    return {
        "root": root,
        "sample_size": len(picked),
        "path_contains": path_contains,
        "seed": seed,
        "per_language": per_lang,
        "details": details,
        "honesty_notes": [
            "中位數 vs 加總的差距本身就是情報：加總會被 `project`、`main` 這種到處都是的"
            "通用名主導（單一個 `project` 就貢獻 479 個名稱級命中，絕大多數是別的函式的"
            "參數、跟這個符號無關）。中位數才反映「對一個一般的符號，它解得動多少」。"
            "兩個都報、不挑好看的那個。",
            "resolve_rate 的分母是純文字掃描的名稱級命中數，裡面本來就混著同名雜訊"
            "（註解、字串、別的類別的同名成員）——所以它不是準確率，而是「能從一團"
            "模糊裡斬釘截鐵確認多少」。選這個定義是因為分母跟工具無關、無法灌水。",
            "zero_high_rate 是「完全解不到高信心引用」的符號比例。它偏高不一定是壞事："
            "對外公開 API（被 repo 外部消費）、CLI 入口、測試專用符號，本來在 repo 內"
            "就沒有呼叫者。要判斷得逐個讀碼。",
            "殘差裡的動態解析部分（反射、字串組名、DI 容器）是靜態分析的本質限制，"
            "所有同類工具都一樣——差別只在漏的時候會不會講。CodeSextant 每次查詢都會"
            "在 reliability 欄位講。",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="量測 CodeSextant 在某個 repo 上的找引用解析覆蓋率")
    ap.add_argument("--project", required=True, help="repo 絕對路徑（需已索引）")
    ap.add_argument("--sample", type=int, default=40, help="抽樣符號數（預設 40）")
    ap.add_argument("--seed", type=int, default=20260719,
                    help="亂數種子——固定值讓任何人重跑都拿到同一組樣本、數字可被複現")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--path-contains", help="只抽路徑含此片段的符號（例：codesextant 只量產品碼，"
                    "排除一次性腳本／探針——它們沒有 repo 內呼叫者是正常的）")
    ap.add_argument("--json", dest="as_json", action="store_true", help="輸出原始 JSON")
    ap.add_argument("--out", help="同時把 JSON 寫到這個檔")
    args = ap.parse_args()

    report = measure(args.project, sample=args.sample, seed=args.seed,
                     timeout_per_symbol=args.timeout, path_contains=args.path_contains)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"專案：{report['root']}")
    print(f"抽樣 {report['sample_size']} 個頂層符號（seed={report['seed']}，可複現）\n")
    print(f"{'語言':<12}{'符號':>5}{'名稱級候選':>11}{'高信心':>8}{'低信心':>8}"
          f"{'解析率(中位)':>13}{'解析率(加總)':>13}{'零高信心':>10}{'秒/符號':>9}")
    print("-" * 92)
    for lang, b in sorted(report["per_language"].items()):
        med = (f"{b['resolve_rate_median']:.1%}"
               if b["resolve_rate_median"] is not None else "—")
        pooled = (f"{b['resolve_rate_pooled']:.1%}"
                  if b["resolve_rate_pooled"] is not None else "—")
        zr = f"{b['zero_high_rate']:.1%}" if b["zero_high_rate"] is not None else "—"
        print(f"{lang:<12}{b['symbols']:>5}{b['name_candidates']:>11}{b['high_conf']:>8}"
              f"{b['low_conf']:>8}{med:>13}{pooled:>13}{zr:>10}{b['sec_per_symbol']:>9}")
    print()
    for note in report["honesty_notes"]:
        print(f"※ {note}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
