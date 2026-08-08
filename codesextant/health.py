"""Compute deterministic per-symbol code health values.

Health combines bloat, cognitive complexity, and duplication into a value from 0 to 1.
Dead-code evidence is stored separately. Missing dimensions are excluded and the
remaining weights are renormalized, so an unknown value does not become a perfect score.

These values are navigation clues, not recommendations to delete or change code. Visual
properties such as color and opacity belong to the presentation layer. Both the engine
and prototype use ``annotate`` as their numeric implementation.
"""
import os
from collections import defaultdict

# Balanced default weights. Environment variables can override them.
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
    dead_keys: set[(normcase_path, line)] (unwired evidence, excluded from the health
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
            if cog is not None:   # Unsupported complexity values are excluded.
                pen["cog"] = _smoothstep(COG_LO, COG_HI, cog)
            if shape_cnt[shape] > 1:
                shape_to_idx[shape].append(idx)
        if pen:   # Renormalize across the available dimensions.
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
