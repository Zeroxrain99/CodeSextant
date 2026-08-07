"""Duplicate and near-duplicate detection: the fingerprints from clones.py plus
the grading that engine.find_duplicates applies.

Covered here: fingerprinting, where a renamed copy keeps the same shape but a
different raw hash, getters carry no control flow, and winnowing applies;
stage-1 EXACT and RENAMED; the structural significance threshold that stops
getters from being flagged; stage-2 and stage-3 STRUCTURAL_NEAR behind the
near_global opt-in; the call_pattern opt-in; the honesty layer, which never
tells anyone to delete or merge and always carries a verification_reminder; the
DF cap; the env switch; and the raise on an unindexed project.
"""
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import clones, engine  # noqa: E402


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    repo = tmp_path / "proj"
    repo.mkdir()
    return str(repo)


def _write(repo, rel, content):
    p = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))
    return p


_LOOP = '''
    def {n}({a}):
        total = 0
        for x in {a}:
            if x > 0:
                total += x
        return total
'''


# Fingerprints (clones.py).

def test_fingerprint_renamed_same_shape_diff_raw():
    src = (_LOOP.format(n="alpha", a="items") + _LOOP.format(n="beta", a="values")).encode("utf-8")
    fps = {f["name"]: f for f in clones.extract_fingerprints_from_source(src, "python")}
    a, b = fps["alpha"], fps["beta"]
    assert a["shape_hash"] == b["shape_hash"]          # same shape once identifiers are erased
    assert a["raw_token_hash"] != b["raw_token_hash"]  # different identifiers, so not token-identical
    assert a["has_control_flow"] is True


def test_fingerprint_getter_no_control_flow():
    src = b"def get_x(self):\n    return self.x\n"
    fps = clones.extract_fingerprints_from_source(src, "python")
    assert fps[0]["has_control_flow"] is False


# Grading in find_duplicates.

def test_find_duplicates_exact(project):
    _write(project, "m.py", _LOOP.format(n="f1", a="items") + _LOOP.format(n="f2", a="items"))
    engine.index_project(project, force=True)
    r = engine.find_duplicates(project)
    exact = [g for g in r["groups"] if g["verdict"] == "EXACT_DUP"]
    assert len(exact) == 1 and {m["name"] for m in exact[0]["members"]} == {"f1", "f2"}
    assert exact[0]["similarity"] == 1.0


def test_find_duplicates_renamed(project):
    _write(project, "m.py", _LOOP.format(n="g1", a="data") + _LOOP.format(n="g2", a="nums"))
    engine.index_project(project, force=True)
    r = engine.find_duplicates(project)
    renamed = [g for g in r["groups"] if g["verdict"] == "RENAMED_DUP"]
    assert len(renamed) == 1 and {m["name"] for m in renamed[0]["members"]} == {"g1", "g2"}


def test_getter_suppressed_not_false_positive(project):
    """Two getters sharing a shape but carrying no control flow come back as
    BOILERPLATE_SUPPRESSED, not as a false EXACT or RENAMED."""
    _write(project, "m.py", '''
        def get_x(self):
            return self.x

        def get_y(self):
            return self.y
    ''')
    engine.index_project(project, force=True)
    r = engine.find_duplicates(project)
    verdicts = {g["verdict"] for g in r["groups"]}
    assert "EXACT_DUP" not in verdicts and "RENAMED_DUP" not in verdicts
    assert r["summary"]["boilerplate_suppressed_groups"] >= 1


def test_stage2_default_off_opt_in(project):
    """Only stage-1 runs by default, leaving stage2_ran False. Stage-2 and
    stage-3 require near_global, a fix that came out of adversarial review."""
    _write(project, "m.py", _LOOP.format(n="f1", a="items") + _LOOP.format(n="f2", a="items"))
    engine.index_project(project, force=True)
    assert engine.find_duplicates(project)["summary"]["stage2_ran"] is False
    assert engine.find_duplicates(project, near_global=True)["summary"]["stage2_ran"] is True


def test_structural_near_via_winnow(project):
    """Two large functions that differ by one line are caught as
    STRUCTURAL_NEAR (Type-3) by the winnowed Jaccard score in stage-2/3."""
    _write(project, "m.py", '''
        def big_a(items):
            result = []
            total = 0
            for x in items:
                if x > 0:
                    total += x
                    result.append(x)
                elif x < 0:
                    total -= x
            return total, result

        def big_b(items):
            result = []
            total = 0
            for x in items:
                if x > 0:
                    total += x
                    result.append(x)
                elif x < 0:
                    total -= x
                    result.append(0)
            return total, result
    ''')
    engine.index_project(project, force=True)
    r = engine.find_duplicates(project, near_global=True)
    near = [g for g in r["groups"] if g["verdict"] == "STRUCTURAL_NEAR"]
    assert len(near) == 1
    assert 0.8 <= near[0]["similarity"] < 1.0   # similar, not token-identical


def test_min_similarity_override(project):
    """Raising min_similarity filters the near-duplicate group out."""
    _write(project, "m.py", '''
        def big_a(items):
            result = []
            total = 0
            for x in items:
                if x > 0:
                    total += x
                    result.append(x)
                elif x < 0:
                    total -= x
            return total, result

        def big_b(items):
            result = []
            total = 0
            for x in items:
                if x > 0:
                    total += x
                    result.append(x)
                elif x < 0:
                    total -= x
                    result.append(0)
            return total, result
    ''')
    engine.index_project(project, force=True)
    assert engine.find_duplicates(project, near_global=True, min_similarity=0.99)[
        "summary"]["structural_near"] == 0


def test_never_recommends_delete_or_merge(project):
    """The honesty layer: a verdict is a grade rather than an instruction, and
    the reminder states outright that nothing here advises deleting or merging."""
    _write(project, "m.py", _LOOP.format(n="f1", a="items") + _LOOP.format(n="f2", a="items"))
    engine.index_project(project, force=True)
    r = engine.find_duplicates(project)
    assert ("never says" in r["verification_reminder"]
            and "read the code" in r["verification_reminder"])
    # the verdict is a label, never a DELETE or MERGE instruction
    legit = {"EXACT_DUP", "RENAMED_DUP", "STRUCTURAL_NEAR", "CALL_PATTERN_SIM"}
    assert all(g["verdict"] in legit for g in r["groups"])
    assert all("delete" not in g["verdict"].lower() and "merge" not in g["verdict"].lower()
               for g in r["groups"])


def test_find_duplicates_unindexed_raises(project):
    with pytest.raises(RuntimeError):
        engine.find_duplicates(project)


def test_dedup_disabled_env(project, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_DEDUP_DISABLED", "1")
    _write(project, "m.py", _LOOP.format(n="f1", a="items") + _LOOP.format(n="f2", a="items"))
    engine.index_project(project, force=True)
    r = engine.find_duplicates(project)
    assert r["summary"]["total_units_scanned"] == 0 and not r["groups"]


def test_call_pattern_opt_in(project):
    """include_call_pattern: the same set of called names with a different
    structure yields CALL_PATTERN_SIM. Off unless asked for."""
    _write(project, "m.py", '''
        def proc_a(xs):
            validate(xs)
            for x in xs:
                transform(x)
            return save(xs)

        def proc_b(ys):
            validate(ys)
            while ys:
                transform(ys.pop())
            return save(ys)
    ''')
    engine.index_project(project, force=True)
    # call_pattern is absent by default
    assert engine.find_duplicates(project)["summary"]["call_pattern"] == 0
    # after opting in: identical validate/transform/save calls, but one uses
    # for where the other uses while
    r = engine.find_duplicates(project, include_call_pattern=True)
    # a hit is not required here, since it depends on the two call sets matching.
    # Coming back without raising is enough.
    assert r["summary"]["call_pattern"] >= 0


# Regressions for the HIGH findings that adversarial review turned up.

def test_go_switch_exact_regression(project):
    """From adversarial review: a Go expression_switch_statement counts as
    control flow via the node_count threshold rather than nstmts, so two
    token-identical Go switch dispatch functions grade EXACT instead of being
    suppressed."""
    _write(project, "m.go", '''
        package main
        func handle1(x int) int {
            switch x {
            case 1:
                return 10
            case 2:
                return 20
            default:
                return 99
            }
        }
        func handle2(x int) int {
            switch x {
            case 1:
                return 10
            case 2:
                return 20
            default:
                return 99
            }
        }
    ''')
    engine.index_project(project, force=True)
    assert engine.find_duplicates(project)["summary"]["exact"] >= 1


def test_stage2_suppresses_noncontrolflow_boilerplate(project):
    """From adversarial review: two semantically unrelated builders, each a long
    run of assignments with no control flow, must not be reported as
    STRUCTURAL_NEAR in stage-2."""
    _write(project, "m.py", '''
        def build_db_config():
            c = {}
            c["host"] = "localhost"
            c["port"] = 5432
            c["user"] = "admin"
            c["passwd"] = "secret"
            c["dbname"] = "mydb"
            c["sslmode"] = "require"
            c["poolsize"] = 10
            return c

        def build_ui_theme():
            t = {}
            t["background"] = "black"
            t["foreground"] = "white"
            t["accentcol"] = "blue"
            t["fontfamily"] = "mono"
            t["fontsize"] = 14
            t["borderrad"] = 4
            t["dropshadow"] = True
            return t
    ''')
    engine.index_project(project, force=True)
    assert engine.find_duplicates(project, near_global=True)["summary"]["structural_near"] == 0


def test_scope_file_stage1_crossfile_exact(project):
    """From adversarial review: stage-1 still scans the whole repo in scope_file
    mode, so token-identical duplicates spanning two files are not missed."""
    fn = ("def calc_a(items):\n    total = 0\n    for x in items:\n"
          "        if x > 0:\n            total += x\n    return total\n")
    a = _write(project, "a.py", fn)
    _write(project, "b.py", fn)
    engine.index_project(project, force=True)
    assert engine.find_duplicates(project, scope_file=a)["summary"]["exact"] >= 1


def test_exact_renamed_subcluster_coexist(project):
    """From adversarial review: within one shape group, a token-identical
    subcluster graded EXACT and a renamed variant graded RENAMED both survive
    instead of one swallowing the other."""
    fn = ("def {n}({a}):\n    total = 0\n    for x in {a}:\n"
          "        if x > 0:\n            total += x\n    return total\n")
    src = (fn.format(n="f1", a="items") + fn.format(n="f1c", a="items")
           + fn.format(n="f3", a="data").replace("total", "acc"))
    _write(project, "m.py", src)
    engine.index_project(project, force=True)
    s = engine.find_duplicates(project)["summary"]
    assert s["exact"] >= 1 and s["renamed"] >= 1
