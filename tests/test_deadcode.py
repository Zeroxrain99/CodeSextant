"""Dead-code clue layer: regression tests for the safety gates.

The invariants these tests hold, several of them settled during adversarial review:
  - When no real resolver engine is available, nothing may come back as LIKELY_UNUSED.
    Every orphan falls back to UNKNOWN_NO_RESOLVER. Without that gate, a project with
    no engine would see every export marked deletable.
  - False-positive regression (found on a real run against daemon.py's SERVICE_NAME):
    a module-level variable that jedi's two-stage lookup cannot locate must be
    UNKNOWN_UNRESOLVED, never LIKELY_UNUSED. high=0 does not prove nobody references it.
  - No linter (ruff or eslint) means UNKNOWN_NO_LINTER, which is the honest answer. The
    scanner does not fall back to a hand-rolled AST pass that invents false positives.
  - Entrypoints (pages, test_ files, decorators, __all__) are PUBLIC_API and never enter
    the deletion candidate list.
  - LIKELY_UNUSED needs all three: real resolution, a located definition, and high=0.

Self-contained and repeatable, following the style of test_hardening.py: CODESEXTANT_HOME
is redirected to a temporary database per test.
"""
import os
import shutil
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import deadcode, engine  # noqa: E402


@pytest.fixture()
def db_home(tmp_path, monkeypatch):
    """Redirect the database directory so tests never touch the real ~/.codesextant."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))


def _write(root, rel, content):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


def _by_name(result):
    return {o["name"]: o["verdict"] for o in result["orphans"]}


# ---- classify_orphan, pure unit tests: the fastest guard on the invariants ----
class TestClassifyOrphan:
    def test_entry_always_public(self):
        v = deadcode.classify_orphan({"engine": "jedi", "definition": None},
                                     is_entry=True, entry_reason="route")
        assert v["verdict"] == "PUBLIC_API"

    def test_no_engine_unknown_no_resolver(self):
        # Safety gate 1: no real resolver, so deletability is not judged.
        v = deadcode.classify_orphan({}, is_entry=False, entry_reason=None)
        assert v["verdict"] == "UNKNOWN_NO_RESOLVER"

    def test_name_match_engine_unknown(self):
        v = deadcode.classify_orphan({"engine": "name-match", "high_confidence": []},
                                     is_entry=False, entry_reason=None)
        assert v["verdict"] == "UNKNOWN_NO_RESOLVER"

    def test_error_unknown_unresolved(self):
        # Safety gate 2: resolution ran but errored (no definition located), so the
        # verdict is UNKNOWN, not LIKELY_UNUSED.
        v = deadcode.classify_orphan({"engine": "jedi", "error": "no def/class definition line found"},
                                     is_entry=False, entry_reason=None)
        assert v["verdict"] == "UNKNOWN_UNRESOLVED"

    def test_no_definition_unknown_unresolved(self):
        v = deadcode.classify_orphan(
            {"engine": "jedi", "definition": None, "high_confidence": []},
            is_entry=False, entry_reason=None)
        assert v["verdict"] == "UNKNOWN_UNRESOLVED"

    def test_high_confidence_keep(self):
        v = deadcode.classify_orphan(
            {"engine": "jedi", "definition": {"path": "x", "line": 1},
             "high_confidence": [{"src_path": "y", "line": 2}]},
            is_entry=False, entry_reason=None)
        assert v["verdict"] == "KEEP"

    def test_zero_high_with_def_likely_unused(self):
        # LIKELY_UNUSED only when all three hold: real resolution, a definition, high=0.
        v = deadcode.classify_orphan(
            {"engine": "jedi", "definition": {"path": "x", "line": 1}, "high_confidence": []},
            is_entry=False, entry_reason=None)
        assert v["verdict"] == "LIKELY_UNUSED"


# ---- is_entrypoint, pure unit tests ----
class TestIsEntrypoint:
    def test_pages_route(self):
        ok, _ = deadcode.is_entrypoint("E:/x/pages/index.tsx")
        assert ok

    def test_app_router(self):
        ok, _ = deadcode.is_entrypoint("E:/x/app/users/route.ts")
        assert ok

    def test_test_file(self):
        ok, _ = deadcode.is_entrypoint("E:/x/test_foo.py")
        assert ok

    def test_main_module(self):
        ok, _ = deadcode.is_entrypoint("E:/x/pkg/__main__.py")
        assert ok

    def test_decorator(self):
        src = "@app.route('/x')\ndef handler():\n    pass\n"
        ok, _ = deadcode.is_entrypoint("E:/x/api.py", symbol_name="handler", source=src)
        assert ok

    def test_pytest_fixture_decorator(self):
        src = "@pytest.fixture\ndef client():\n    pass\n"
        ok, _ = deadcode.is_entrypoint("E:/x/conftest_like.py", symbol_name="client", source=src)
        assert ok

    def test_dunder_all(self):
        src = "__all__ = ['pub', 'other']\ndef pub():\n    pass\n"
        ok, _ = deadcode.is_entrypoint("E:/x/mod.py", symbol_name="pub", source=src)
        assert ok

    def test_plain_helper_not_entry(self):
        ok, _ = deadcode.is_entrypoint("E:/x/util.py", symbol_name="helper",
                                       source="def helper():\n    pass\n")
        assert not ok

    def test_extra_env(self, monkeypatch):
        monkeypatch.setenv("CODESEXTANT_DEADCODE_ENTRYPOINT_EXTRA", "myroutes")
        ok, reason = deadcode.is_entrypoint("E:/x/myroutes/h.py")
        assert ok and "user-specified" in reason


# ---- unused imports, via ruff ----
class TestUnusedImport:
    def test_ruff_catches_unused(self, tmp_path, db_home):
        if shutil.which("ruff") is None:
            pytest.skip("ruff is not installed, skipping the ground-truth test")
        f = _write(tmp_path, "mod.py", """
            import os
            import sys

            def f():
                return sys.path
        """)
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        ui = r["unused_imports"]
        assert ui["available"] is True
        codes = [x["code"] for x in ui["findings"]]
        assert "F401" in codes  # os is imported but never used

    def test_linter_off_switch(self, tmp_path, db_home, monkeypatch):
        monkeypatch.setenv("CODESEXTANT_DEADCODE_LINTER", "off")
        f = _write(tmp_path, "mod.py", "import os\n")
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        assert r["unused_imports"]["available"] is False

    def test_no_linter_unknown_not_fabricated(self, tmp_path, db_home, monkeypatch):
        # ruff missing from PATH gives UNKNOWN_NO_LINTER, the honest answer. It must not
        # pretend the scan came back clean, nor fall back to a hand-rolled AST pass.
        monkeypatch.setattr(deadcode.shutil, "which", lambda name: None)
        f = _write(tmp_path, "mod.py", "import os\n")
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        ui = r["unused_imports"]
        assert ui["available"] is False
        assert ui.get("verdict") == "UNKNOWN_NO_LINTER"


# ---- orphan grading, with jedi doing the real Python resolution ----
class TestOrphanPython:
    def test_real_orphan_likely_unused(self, tmp_path, db_home):
        # A genuinely dead function (zero references) grades LIKELY_UNUSED; a called one KEEP.
        f = _write(tmp_path, "mod.py", """
            def used():
                return 1

            def dead_orphan():
                return 2

            def caller():
                return used()
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        by = _by_name(r)
        assert by["dead_orphan"] == "LIKELY_UNUSED"
        assert by["used"] == "KEEP"

    def test_module_var_unknown_not_likely(self, tmp_path, db_home):
        # False-positive regression (daemon.py SERVICE_NAME): a module-level variable
        # grades UNKNOWN_UNRESOLVED.
        f = _write(tmp_path, "consts.py", """
            SERVICE = "x"

            def reader():
                return SERVICE
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        by = _by_name(r)
        assert by["SERVICE"] == "UNKNOWN_UNRESOLVED"
        assert by["SERVICE"] != "LIKELY_UNUSED"

    def test_entrypoint_decorator_public_api(self, tmp_path, db_home):
        # An @app.route decorator makes it PUBLIC_API. Zero static references still does
        # not put it in the deletion candidate list.
        f = _write(tmp_path, "api.py", """
            app = object()

            @app.route("/x")
            def handler():
                return 1
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        by = _by_name(r)
        assert by["handler"] == "PUBLIC_API"

    def test_entrypoint_filename_public_api(self, tmp_path, db_home):
        # Symbols inside test_*.py grade PUBLIC_API.
        f = _write(tmp_path, "test_thing.py", """
            def test_something():
                assert True
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        by = _by_name(r)
        assert by["test_something"] == "PUBLIC_API"

    def test_dunder_all_public_api(self, tmp_path, db_home):
        f = _write(tmp_path, "pkg.py", """
            __all__ = ["exported"]

            def exported():
                return 1
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        by = _by_name(r)
        assert by["exported"] == "PUBLIC_API"


# ---- the most important safety gate: no real resolver means zero LIKELY_UNUSED ----
class TestB2SafetyGate:
    def test_ts_without_tsmorph_no_likely_unused(self, tmp_path, db_home, monkeypatch):
        # When ts-morph is unavailable, every orphan in a TS file must come back
        # UNKNOWN_NO_RESOLVER. A single LIKELY_UNUSED here would mark every export of an
        # engine-less TS project as deletable.
        monkeypatch.setenv("CODESEXTANT_TS_MORPH_DISABLED", "1")  # force ts-morph off
        f = _write(tmp_path, "mod.ts", """
            export function deadFn() { return 1; }
            export const X = 2;
            export class Thing {}
        """)
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        verdicts = [o["verdict"] for o in r["orphans"]]
        assert verdicts, "expected top-level symbols to be graded"
        assert "LIKELY_UNUSED" not in verdicts, verdicts
        assert all(v == "UNKNOWN_NO_RESOLVER" for v in verdicts), verdicts

    def test_resolver_available_python_always(self):
        ok, _ = deadcode.resolver_available("python")
        assert ok

    def test_resolver_available_unknown_lang(self):
        ok, reason = deadcode.resolver_available("rust")
        assert not ok and reason

    def test_resolver_available_ts_respects_switch(self, monkeypatch):
        monkeypatch.setenv("CODESEXTANT_TS_MORPH_DISABLED", "1")
        ok, _ = deadcode.resolver_available("typescript")
        assert not ok


# ---- the overall find_deadcode contract ----
class TestFindDeadcodeContract:
    def test_has_verification_reminder(self, tmp_path, db_home):
        f = _write(tmp_path, "mod.py", "def f():\n    return 1\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        assert "verification_reminder" in r and r["verification_reminder"]
        assert "build" in r["verification_reminder"]

    def test_no_scope_file_skips_orphan(self, tmp_path, db_home):
        _write(tmp_path, "mod.py", "import os\ndef f():\n    return 1\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path))  # no scope_file given
        assert r["orphans"] == []
        assert r["scope_file"] is None

    def test_bad_path_raises(self, db_home):
        with pytest.raises(NotADirectoryError):
            engine.find_deadcode("E:/__no_such_dir_codesextant__")


# ---- real TS resolution, barrel re-exports and batch queries (needs node + ts-morph) ----
class TestSeq4Seq5TsMorph:
    @pytest.fixture(autouse=True)
    def _need_tsmorph(self):
        from codesextant import references
        if not references.ts_morph_available():
            pytest.skip("node/ts-morph unavailable, skipping the real TS resolution tests")

    def test_reexport_only(self, tmp_path, db_home):
        # A symbol only re-exported through a barrel, with no real consumer, grades
        # REEXPORT_ONLY rather than being misjudged as LIKELY_UNUSED.
        _write(tmp_path, "foo.ts", "export function onlyReexported() { return 1; }\n")
        _write(tmp_path, "barrel.ts", "export { onlyReexported } from './foo';\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=str(tmp_path / "foo.ts"))
        assert _by_name(r)["onlyReexported"] == "REEXPORT_ONLY"

    def test_real_consumer_keep(self, tmp_path, db_home):
        # Actually imported and consumed grades KEEP, even when it is also re-exported.
        _write(tmp_path, "bar.ts", "export function reallyUsed() { return 2; }\n")
        _write(tmp_path, "consumer.ts",
               "import { reallyUsed } from './bar';\n"
               "export function c() { return reallyUsed(); }\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=str(tmp_path / "bar.ts"))
        assert _by_name(r)["reallyUsed"] == "KEEP"

    def test_true_orphan_ts_likely_unused(self, tmp_path, db_home):
        # Genuinely dead TS: exported, nobody imports it, nobody re-exports it.
        _write(tmp_path, "dead.ts", "export function deadTs() { return 3; }\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=str(tmp_path / "dead.ts"))
        assert _by_name(r)["deadTs"] == "LIKELY_UNUSED"

    def test_batch_matches_single(self, tmp_path, db_home):
        # Querying several symbols in one batch gives the same reference counts as
        # querying them one at a time.
        from codesextant import references
        _write(tmp_path, "m.ts",
               "export function a() { return 1; }\n"
               "export function b() { return a(); }\n")
        root, deffile = str(tmp_path), str(tmp_path / "m.ts")
        batch = references.ts_morph_references_batch(root, deffile, ["a", "b"])
        single_a = references.ts_morph_references(root, "a", def_path=deffile)
        assert batch is not None and single_a is not None
        assert len(batch["a"]["high_confidence"]) == len(single_a["high_confidence"])
        assert batch["a"]["high_confidence"], "b calls a, so a needs a high-confidence reference"

    def test_batch_unknown_when_disabled(self, tmp_path, db_home, monkeypatch):
        # With ts-morph off the batch call returns None, which the caller turns into
        # UNKNOWN instead of pretending it got an answer.
        from codesextant import references
        monkeypatch.setenv("CODESEXTANT_TS_MORPH_DISABLED", "1")
        _write(tmp_path, "m.ts", "export function a() { return 1; }\n")
        assert references.ts_morph_references_batch(
            str(tmp_path), str(tmp_path / "m.ts"), ["a"]) is None


# ---- knowing its own limits: the reliability rating and the blind-spot advisory ----
class TestSeq6Boundary:
    def test_refs_reliability_present(self, tmp_path, db_home):
        _write(tmp_path, "m.py", "def used():\n    return 1\n\n\ndef caller():\n    return used()\n")
        engine.index_project(str(tmp_path))
        r = engine.find_references(str(tmp_path), "used", src_root=str(tmp_path))
        assert "reliability" in r
        assert r["reliability"].get("level") in ("high", "medium", "low")
        assert r["reliability"].get("advice")

    def test_reliability_name_match_low(self):
        # The name-match engine does no real resolution, so reliability is low and you
        # have to read the code.
        rel = engine._refs_reliability(
            {"engine": "name-match", "definition": {"path": "x"}, "high_confidence": [{"x": 1}]})
        assert rel["level"] == "low"

    def test_reliability_no_def_low(self):
        rel = engine._refs_reliability(
            {"engine": "jedi", "definition": None, "high_confidence": [], "low_confidence": []})
        assert rel["level"] == "low"

    def test_reliability_zero_refs_medium(self):
        # Real resolution with zero references is medium: dynamic or reflective calls are
        # invisible to it, so confirm by reading the code.
        rel = engine._refs_reliability(
            {"engine": "jedi", "definition": {"path": "x"},
             "high_confidence": [], "low_confidence": []})
        assert rel["level"] == "medium"

    def test_reliability_high(self):
        rel = engine._refs_reliability(
            {"engine": "jedi", "definition": {"path": "x"},
             "high_confidence": [{"a": 1}, {"b": 2}], "low_confidence": []})
        assert rel["level"] == "high"

    def test_deadcode_advisory_present_and_nonempty(self, tmp_path, db_home):
        f = _write(tmp_path, "m.py", "def a():\n    return 1\n")
        engine.index_project(str(tmp_path))
        r = engine.find_deadcode(str(tmp_path), scope_file=f)
        assert isinstance(r.get("read_code_advisory"), list) and r["read_code_advisory"]

    def test_advisory_flags_unknown(self):
        notes = deadcode.read_code_advisory(
            {"available": True},
            [{"verdict": "UNKNOWN_UNRESOLVED"}, {"verdict": "UNKNOWN_NO_RESOLVER"}])
        assert any("cannot decide" in n for n in notes)

    def test_advisory_flags_likely_unused(self):
        notes = deadcode.read_code_advisory({"available": True}, [{"verdict": "LIKELY_UNUSED"}])
        assert any("a clue, not a verdict" in n for n in notes)

    def test_advisory_flags_no_linter(self):
        notes = deadcode.read_code_advisory({"available": False, "reason": "no ruff"}, [])
        assert any("could not be determined" in n for n in notes)

    def test_advisory_flags_reexport(self):
        notes = deadcode.read_code_advisory({"available": True}, [{"verdict": "REEXPORT_ONLY"}])
        assert any("re-export" in n for n in notes)
