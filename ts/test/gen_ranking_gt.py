"""Generate the ground truth for the ranking.ts golden tests, using the frozen Python
codesextant/ranking.py.

Writes ts/test/fixtures/expected_ranking.json: every case holds its input (symbols/refs/opts) plus the
expected output the Python version computed (ranked_names / scores). The TypeScript side reads it
back, feeds ranking.ts the same input and compares, which proves the port matches Python.

Note: codesextant/ is put on sys.path and `import ranking` is done directly, bypassing
codesextant.__init__ so it does not drag in tree-sitter/jedi.
Note: paths are relative strings such as "a.py". by_pos matching only cares that the strings agree,
symbol_id uses the raw path, and the scores keys agree across languages, so none of it depends on cwd.
"""
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO, "codesextant"))
import ranking  # noqa: E402  (pure algorithm module, imports only os, never triggers the package __init__)


def sym(name, line, path="a.py", end_line=None, scope="", kind="function"):
    return {"path": path, "name": name, "line": line,
            "end_line": end_line if end_line is not None else line + 1,
            "scope": scope, "kind": kind}


def ref(src_path, src_line, name, def_path=None, def_line=None, confidence="high"):
    return {"src_path": src_path, "src_line": src_line, "symbol_name": name,
            "def_path": def_path, "def_line": def_line, "confidence": confidence}


out = {"wellnamed": [], "quality": [], "personalization": [], "pagerank": []}

# ── wellNamed (pure function) ──
for nm in ["get_value", "getValue", "MyClass", "_x", "run", "calculate_total", "HTTP", "a", "_private_long"]:
    out["wellnamed"].append({"name": nm, "result": ranking._well_named(nm)})

# ── symbol quality multiplier (pure function; covers the private, well-named and common rules plus a neutral case) ──
for nm, dfn in [("_helper", 1), ("calculate_total", 1), ("calculate_total", 10), ("run", 1),
                ("getValue", 1), ("x", 1), ("MyLongClassName", 1), ("MyLongClassName", 6),
                ("_x", 8)]:
    out["quality"].append({"name": nm, "defines": dfn,
                           "mult": ranking._symbol_quality_mult(nm, dfn)})

# ── personalization (pure function) ──
def pers_case(symbols, fs, ff):
    p = ranking._build_personalization(symbols, fs, ff)
    return {"symbols": symbols, "focus_symbols": fs, "focus_files": ff,
            "result": None if p is None else p}

out["personalization"].append(pers_case([sym("x", 1)], None, None))            # no focus → None
out["personalization"].append(pers_case([sym("target", 1), sym("other", 2)], ["target"], None))
out["personalization"].append(pers_case([sym("a", 1, "hot.py"), sym("b", 2, "cold.py")], None, ["hot.py"]))

# ── pagerank (computePagerank scores + rankSymbols ordering) ──
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

# 1. linear chain a→b→c (score flows along the reference direction toward the referenced end, so c is highest)
out["pagerank"].append(pr_case(
    "linear chain",
    [sym("a", 1, "a.py", 5), sym("b", 1, "b.py", 5), sym("c", 1, "c.py", 5)],
    [ref("b.py", 3, "c", "c.py", 1), ref("a.py", 3, "b", "b.py", 1)]))

# 2. no reference edges (pure teleport, evenly split)
out["pagerank"].append(pr_case("no edges", [sym("a", 1), sym("b", 3)], []))

# 3. focus personalization (the focused symbol's rank rises)
out["pagerank"].append(pr_case(
    "focus alpha", [sym("alpha", 1), sym("beta", 3)], [], focus_symbols=["alpha"]))

# 4. hub convergence (x and y both reference h → h is highest, and x/y are symmetric so they tie)
out["pagerank"].append(pr_case(
    "hub converge",
    [sym("h", 1, "hub.py", 5), sym("x", 1, "x.py", 5), sym("y", 1, "y.py", 5)],
    [ref("x.py", 3, "h", "hub.py", 1), ref("y.py", 3, "h", "hub.py", 1)]))

# 5. external inflow (the ref's src matches no symbol node → counted as evenly-shared external inflow)
out["pagerank"].append(pr_case(
    "external inflow",
    [sym("t", 1, "t.py", 5)],
    [ref("nowhere.py", 1, "t", "t.py", 1)]))

# 6. innermost caller within one file (src_line 4 falls inside inner(3-5) → the caller is inner, not outer or file_rep)
out["pagerank"].append(pr_case(
    "same file inner caller",
    [sym("outer", 1, "f.py", 10), sym("inner", 3, "f.py", 5), sym("g", 1, "g.py", 2)],
    [ref("f.py", 4, "g", "g.py", 1)]))

# 7. the quality factor reaching PageRank (calculate_total is well-named, ×10 → it outranks x, which is referenced just as often)
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
