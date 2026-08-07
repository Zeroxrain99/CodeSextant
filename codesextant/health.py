"""Discipline-to-beauty backend: per-node code health values (D1 bloat + D3 cognitive
complexity + D5 duplication -> health[0,1]; D6 dead code -> dead). Pure numbers, zero
randomness, serializable.

⛔ Contains no visual mapping (saturation/opacity/dark-arc formulas). That's the
presentation layer's job (starmap frontend/PoC); the engine only supplies numbers.
Hard rules: ① a read-only navigation map, where health is a clue, not a verdict, and never
emits a "should delete/should change" decision ② UNKNOWN/N-A dimensions (fingerprint-less
class/variable symbols, cognitive complexity for non-high-confidence languages) are
excluded and the remaining weights are renormalized (never washed up to a perfect score
= guards against vapor) ③ a deterministic pure function. The "balanced" preset weights,
tunable via env (L0 hard rule #6).

The engine (engine.get_health) and the PoC (_poc_graph_c/code_health.py) share this
module's annotate = the single numeric source of truth (no duplicate implementation, no
drift between the two).
"""
import os
from collections import defaultdict

# SSOT §2.3 "balanced" preset weights (D1/D3/D5 in effect; D10 long-parameter-list is
# UNKNOWN in this version). Tunable via env (L0 hard rule #6).
W = {"dup": float(os.environ.get("CODESEXTANT_W_DUP", 0.30)),
     "cog": float(os.environ.get("CODESEXTANT_W_COG", 0.30)),
     "bloat": float(os.environ.get("CODESEXTANT_W_BLOAT", 0.25))}
BLOAT_LO = int(os.environ.get("CODESEXTANT_BLOAT_LO", 80))     # node_count<=80 doesn't count as bloat
BLOAT_HI = int(os.environ.get("CODESEXTANT_BLOAT_HI", 200))    # >=200 gets the full penalty
COG_LO = int(os.environ.get("CODESEXTANT_COG_LO", 8))          # cognitive<=8 doesn't count as complex
COG_HI = int(os.environ.get("CODESEXTANT_COG_HI", 25))         # >=25 gets the full penalty


def _smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def annotate(nodes, fp_by, shape_cnt, dead_keys, key_of):
    """Add 'health'(float[0,1]|None) + 'dead'(bool) to nodes in place; return a coverage
    report + clone_pairs.

    nodes    : list[dict] (written in place)
    fp_by    : {(normcase_path, line): (node_count, shape_hash, cognitive)}; cognitive
               None=UNKNOWN
    shape_cnt: Counter[shape_hash] (determines duplication: >1 means EXACT/RENAMED twins)
    dead_keys: set[(normcase_path, line)] (D6 unwired -> opacity, does not feed the health
               value)
    key_of   : node -> (normcase_path, line) (caller decides how to derive the key from a
               node)
    Returns {n_nodes, n_covered, coverage, n_dead, clone_pairs}. clone_pairs = a star
    connection among same-shape nodes (avoids O(n^2)).
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
            if cog is not None:   # D3: only weighted for high-confidence languages; None=UNKNOWN is excluded and renormalized (never washed to a perfect score)
                pen["cog"] = _smoothstep(COG_LO, COG_HI, cog)
            if shape_cnt[shape] > 1:
                shape_to_idx[shape].append(idx)
        if pen:   # has a valid dimension -> renormalize (UNKNOWN is never washed to a perfect score = C2 vapor guard)
            sw = sum(W[k] for k in pen)
            penalty = min(max(sum(pen[k] * W[k] for k in pen) / sw, 0.0), 1.0)
            n["health"] = round(1.0 - penalty, 4)
            n_cov += 1
        else:     # no fingerprint (class/variable) = UNKNOWN, neutral (the frontend uses a neutral value, not a perfect score, not 0)
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
