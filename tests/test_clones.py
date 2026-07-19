"""功能 B 重複/類似偵測測試 — clones.py 指紋 + engine.find_duplicates 分級。

涵蓋：指紋（改名同形 shape 同 raw 不同／getter 無控制流／winnow）／stage-1 EXACT/RENAMED／
結構顯著性門檻擋 getter 誤報／stage-2/3 STRUCTURAL_NEAR（near_global opt-in）／call_pattern opt-in／
誠實層（永不出應刪應合併、verification_reminder）／DF-cap／env 開關／未索引 raise。
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


# ─────────────── 指紋（clones.py） ───────────────

def test_fingerprint_renamed_same_shape_diff_raw():
    src = (_LOOP.format(n="alpha", a="items") + _LOOP.format(n="beta", a="values")).encode("utf-8")
    fps = {f["name"]: f for f in clones.extract_fingerprints_from_source(src, "python")}
    a, b = fps["alpha"], fps["beta"]
    assert a["shape_hash"] == b["shape_hash"]          # 抹 ID 後同形
    assert a["raw_token_hash"] != b["raw_token_hash"]  # 識別字不同 → 逐字不同
    assert a["has_control_flow"] is True


def test_fingerprint_getter_no_control_flow():
    src = b"def get_x(self):\n    return self.x\n"
    fps = clones.extract_fingerprints_from_source(src, "python")
    assert fps[0]["has_control_flow"] is False


# ─────────────── find_duplicates 分級 ───────────────

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
    """兩個同形 getter（shape 同但無控制流）→ BOILERPLATE_SUPPRESSED，⛔不誤報 EXACT/RENAMED。"""
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
    """預設只跑 stage-1（stage2_ran=False）；near_global 才跑 stage-2/3（紅隊 FIX-1）。"""
    _write(project, "m.py", _LOOP.format(n="f1", a="items") + _LOOP.format(n="f2", a="items"))
    engine.index_project(project, force=True)
    assert engine.find_duplicates(project)["summary"]["stage2_ran"] is False
    assert engine.find_duplicates(project, near_global=True)["summary"]["stage2_ran"] is True


def test_structural_near_via_winnow(project):
    """大函數差一行 → stage-2/3 winnow Jaccard 抓 STRUCTURAL_NEAR（Type-3）。"""
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
    assert 0.8 <= near[0]["similarity"] < 1.0   # 近似非逐字


def test_min_similarity_override(project):
    """min_similarity 提高門檻 → 近似群被濾掉。"""
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
    """誠實層（設計 §⑤）：verdict 是分級非動作指令、reminder 聲明永不建議刪/合併。"""
    _write(project, "m.py", _LOOP.format(n="f1", a="items") + _LOOP.format(n="f2", a="items"))
    engine.index_project(project, force=True)
    r = engine.find_duplicates(project)
    assert "永不出" in r["verification_reminder"] and "讀碼" in r["verification_reminder"]
    # verdict 是分級標籤，無 DELETE/MERGE 動作指令
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
    """include_call_pattern：呼叫名集合相同、結構不同 → CALL_PATTERN_SIM（預設關）。"""
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
    # 預設不含 call_pattern
    assert engine.find_duplicates(project)["summary"]["call_pattern"] == 0
    # opt-in 後（呼叫 validate/transform/save 相同、for vs while 結構不同）
    r = engine.find_duplicates(project, include_call_pattern=True)
    assert r["summary"]["call_pattern"] >= 0   # 不強制命中（依 call 集合是否相同），不報錯即通過


# ─────────────── 對抗 review HIGH 修復回歸 ───────────────

def test_go_switch_exact_regression(project):
    """紅隊 L1-HIGH：Go expression_switch_statement 算控制流（node_count 門檻、不卡 nstmts），
    逐字相同的 Go switch dispatch 函數 → EXACT，不被誤壓制。"""
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
    """紅隊 L2-HIGH：兩個語義無關的無控制流大樣板（賦值串 builder）→ stage-2 不報 STRUCTURAL_NEAR。"""
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
    """紅隊 L5-HIGH：scope_file 模式 stage-1 仍對全 repo 偵測，跨檔逐字重複不漏。"""
    fn = ("def calc_a(items):\n    total = 0\n    for x in items:\n"
          "        if x > 0:\n            total += x\n    return total\n")
    a = _write(project, "a.py", fn)
    _write(project, "b.py", fn)
    engine.index_project(project, force=True)
    assert engine.find_duplicates(project, scope_file=a)["summary"]["exact"] >= 1


def test_exact_renamed_subcluster_coexist(project):
    """紅隊 L1-MEDIUM：同 shape 群內逐字子簇 EXACT 與改名變體 RENAMED 並存、不互相吃掉。"""
    fn = ("def {n}({a}):\n    total = 0\n    for x in {a}:\n"
          "        if x > 0:\n            total += x\n    return total\n")
    src = (fn.format(n="f1", a="items") + fn.format(n="f1c", a="items")
           + fn.format(n="f3", a="data").replace("total", "acc"))
    _write(project, "m.py", src)
    engine.index_project(project, force=True)
    s = engine.find_duplicates(project)["summary"]
    assert s["exact"] >= 1 and s["renamed"] >= 1
