"""生成 ranking.ts 黃金測試 ground truth（用凍結的 Python 版 codesextant/ranking.py）。

輸出 ts/test/fixtures/expected_ranking.json：每個 case 含 input(symbols/refs/opts) + Python 版算出的
expected(ranked_names / scores)。TS 端讀回、餵同樣 input 給 ranking.ts、比對 → 證明 TS 平移與 Python 一致。

⚠ 直接把 codesextant/ 目錄加 sys.path 後 `import ranking`（不經 codesextant.__init__，避開它拖 tree-sitter/jedi）。
⚠ 路徑用相對字串（"a.py"）：by_pos 配對只看字串一致、symbol_id 用 raw path、scores key 跨語言一致，與 cwd 無關。
"""
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO, "codesextant"))
import ranking  # noqa: E402  （純算法模組、只 import os，不觸發 package __init__）


def sym(name, line, path="a.py", end_line=None, scope="", kind="function"):
    return {"path": path, "name": name, "line": line,
            "end_line": end_line if end_line is not None else line + 1,
            "scope": scope, "kind": kind}


def ref(src_path, src_line, name, def_path=None, def_line=None, confidence="high"):
    return {"src_path": src_path, "src_line": src_line, "symbol_name": name,
            "def_path": def_path, "def_line": def_line, "confidence": confidence}


out = {"wellnamed": [], "quality": [], "personalization": [], "pagerank": []}

# ── wellNamed（純函數）──
for nm in ["get_value", "getValue", "MyClass", "_x", "run", "calculate_total", "HTTP", "a", "_private_long"]:
    out["wellnamed"].append({"name": nm, "result": ranking._well_named(nm)})

# ── symbol quality multiplier（純函數；含私有/well-named/common 三條 + 中性）──
for nm, dfn in [("_helper", 1), ("calculate_total", 1), ("calculate_total", 10), ("run", 1),
                ("getValue", 1), ("x", 1), ("MyLongClassName", 1), ("MyLongClassName", 6),
                ("_x", 8)]:
    out["quality"].append({"name": nm, "defines": dfn,
                           "mult": ranking._symbol_quality_mult(nm, dfn)})

# ── personalization（純函數）──
def pers_case(symbols, fs, ff):
    p = ranking._build_personalization(symbols, fs, ff)
    return {"symbols": symbols, "focus_symbols": fs, "focus_files": ff,
            "result": None if p is None else p}

out["personalization"].append(pers_case([sym("x", 1)], None, None))            # 無 focus → None
out["personalization"].append(pers_case([sym("target", 1), sym("other", 2)], ["target"], None))
out["personalization"].append(pers_case([sym("a", 1, "hot.py"), sym("b", 2, "cold.py")], None, ["hot.py"]))

# ── pagerank（computePagerank scores + rankSymbols 順序）──
def pr_case(label, symbols, refs, focus_symbols=None, focus_files=None):
    pers = ranking._build_personalization(symbols, focus_symbols, focus_files)
    scores = ranking.compute_pagerank(symbols, refs, personalization=pers)
    ranked = ranking.rank_symbols(symbols, refs, focus_symbols=focus_symbols, focus_files=focus_files)
    opts = {}
    if focus_symbols is not None:
        opts["focus_symbols"] = focus_symbols
    if focus_files is not None:
        opts["focus_files"] = focus_files
    return {"label": label, "symbols": symbols, "refs": refs, "opts": opts,
            "ranked_names": [s["name"] for s in ranked], "scores": scores}

# 1. 線性鏈 a→b→c（分數沿引用方向流向被引用端，c 最高）
out["pagerank"].append(pr_case(
    "linear chain",
    [sym("a", 1, "a.py", 5), sym("b", 1, "b.py", 5), sym("c", 1, "c.py", 5)],
    [ref("b.py", 3, "c", "c.py", 1), ref("a.py", 3, "b", "b.py", 1)]))

# 2. 無引用邊（純 teleport 均分）
out["pagerank"].append(pr_case("no edges", [sym("a", 1), sym("b", 3)], []))

# 3. focus personalization（focus 符號 rank 升）
out["pagerank"].append(pr_case(
    "focus alpha", [sym("alpha", 1), sym("beta", 3)], [], focus_symbols=["alpha"]))

# 4. hub 匯聚（x,y 都引用 h → h 最高，x/y 對稱同 rank）
out["pagerank"].append(pr_case(
    "hub converge",
    [sym("h", 1, "hub.py", 5), sym("x", 1, "x.py", 5), sym("y", 1, "y.py", 5)],
    [ref("x.py", 3, "h", "hub.py", 1), ref("y.py", 3, "h", "hub.py", 1)]))

# 5. external inflow（ref 的 src 對不到任何符號節點 → 外部入流均攤）
out["pagerank"].append(pr_case(
    "external inflow",
    [sym("t", 1, "t.py", 5)],
    [ref("nowhere.py", 1, "t", "t.py", 1)]))

# 6. 同檔最內層 caller（src_line 4 落在 inner(3-5) 內 → caller 是 inner 非 outer 或 file_rep）
out["pagerank"].append(pr_case(
    "same file inner caller",
    [sym("outer", 1, "f.py", 10), sym("inner", 3, "f.py", 5), sym("g", 1, "g.py", 2)],
    [ref("f.py", 4, "g", "g.py", 1)]))

# 7. quality 係數進 PageRank（calculate_total well-named ×10 → rank 高於同樣被引用一次的 x）
out["pagerank"].append(pr_case(
    "quality weight in pagerank",
    [sym("caller_a", 1, "a.py", 5), sym("caller_b", 1, "b.py", 5),
     sym("calculate_total", 1, "good.py", 5), sym("x", 1, "bad.py", 5)],
    [ref("a.py", 3, "calculate_total", "good.py", 1), ref("b.py", 3, "x", "bad.py", 1)]))

_dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "expected_ranking.json")
with open(_dst, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("wrote", _dst)
print("cases: wellnamed=%d quality=%d personalization=%d pagerank=%d" % (
    len(out["wellnamed"]), len(out["quality"]), len(out["personalization"]), len(out["pagerank"])))
