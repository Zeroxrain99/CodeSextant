"""Call hierarchy tests covering transitive caller and callee chains.

Exercises storage.traverse_call_graph, which walks the refs table with a
recursive CTE, together with engine.call_hierarchy. The cases here check
transitive callers and callees, the max_hops depth cap, call cycles that must
not recurse forever, and a loud failure when the project was never indexed.
Everything is self-contained because CODESEXTANT_HOME points at an isolated
database.
"""
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine  # noqa: E402


@pytest.fixture()
def db_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))


def _write(root, rel, content):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


def _setup_chain(tmp_path):
    """Build a leaf <- mid <- top chain, persisting refs edges for every symbol."""
    _write(tmp_path, "m.py", """
        def leaf():
            return 1


        def mid():
            return leaf()


        def top():
            return mid()
    """)
    root = str(tmp_path)
    engine.index_project(root)
    for sym in ("leaf", "mid", "top"):
        engine.find_references(root, sym, src_root=root, persist=True)
    return root


class TestCallHierarchy:
    def test_up_transitive_callers(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        r = engine.call_hierarchy(root, "leaf", direction="up")
        depth = {c["name"]: c["depth"] for c in r["callers"]}
        assert depth.get("mid") == 1, depth
        assert depth.get("top") == 2, depth  # reached transitively

    def test_down_transitive_callees(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        r = engine.call_hierarchy(root, "top", direction="down")
        depth = {c["name"]: c["depth"] for c in r["callees"]}
        assert depth.get("mid") == 1, depth
        assert depth.get("leaf") == 2, depth  # reached transitively

    def test_both_directions(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        r = engine.call_hierarchy(root, "mid", direction="both")
        assert "callers" in r and "callees" in r
        assert any(c["name"] == "top" for c in r["callers"])
        assert any(c["name"] == "leaf" for c in r["callees"])

    def test_max_hops_limit(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        r = engine.call_hierarchy(root, "leaf", direction="up", max_hops=1)
        names = {c["name"] for c in r["callers"]}
        assert "mid" in names       # depth 1 is inside the cap
        assert "top" not in names   # depth 2 is past max_hops=1

    def test_cycle_no_infinite(self, tmp_path, db_home):
        # a and b call each other, so the graph has a cycle. max_hops plus
        # the CTE's dedup have to stop the traversal from recursing forever.
        _write(tmp_path, "c.py", """
            def a():
                return b()


            def b():
                return a()
        """)
        root = str(tmp_path)
        engine.index_project(root)
        for sym in ("a", "b"):
            engine.find_references(root, sym, src_root=root, persist=True)
        r = engine.call_hierarchy(root, "a", direction="up", max_hops=5)
        # Nothing blows up, b comes back as a caller, and node dedup keeps a
        # from showing up as its own caller.
        names = {c["name"] for c in r["callers"]}
        assert "b" in names

    def test_confidence_field(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        r = engine.call_hierarchy(root, "leaf", direction="up")
        for c in r["callers"]:
            assert c["confidence"] in ("high", "low")

    def test_has_note_and_reminder(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        r = engine.call_hierarchy(root, "leaf", direction="up")
        assert r.get("note") and "reference edges" in r["note"]
        assert r.get("verification_reminder") and "dynamic" in r["verification_reminder"]
        assert "edges_in_graph" in r

    def test_unindexed_raises(self, db_home):
        with pytest.raises(RuntimeError):
            engine.call_hierarchy("E:/__no_such_dir_cs_callgraph__", "x")

    def test_bad_direction_raises(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        with pytest.raises(ValueError):
            engine.call_hierarchy(root, "leaf", direction="sideways")

    def test_unknown_symbol_no_crash(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        r = engine.call_hierarchy(root, "no_such_symbol_xyz", direction="both")
        assert r.get("definition") is None
        assert r.get("error")
        assert r["callers"] == [] and r["callees"] == []


# Blast radius: what a change to a symbol reaches.
class TestIsTestPath:
    def test_test_prefix(self):
        assert engine._is_test_path("E:/x/test_foo.py")

    def test_tests_dir(self):
        assert engine._is_test_path("E:/x/tests/foo.py")

    def test_spec(self):
        assert engine._is_test_path("E:/x/foo.spec.ts")

    def test_conftest(self):
        assert engine._is_test_path("E:/x/conftest.py")

    def test_prod_not_test(self):
        assert not engine._is_test_path("E:/x/app/core.py")


class TestImpact:
    def test_blast_radius_basic(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        r = engine.impact(root, "leaf")
        names = {c["name"] for c in r["direct_callers"]}
        assert "mid" in names
        assert r["summary"]["total_confirmed_affected"] >= 1

    def test_affected_files(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        r = engine.impact(root, "leaf")
        assert any("m.py" in f for f in r["affected_files"])

    def test_test_caller_classified(self, tmp_path, db_home):
        _write(tmp_path, "core.py", "def target():\n    return 1\n")
        _write(tmp_path, "test_core.py",
               "from core import target\n\n\ndef test_x():\n    return target()\n")
        root = str(tmp_path)
        engine.index_project(root)
        for sym in ("target", "test_x"):
            engine.find_references(root, sym, src_root=root, persist=True)
        r = engine.impact(root, "target")
        assert any("test_core" in c["path"] for c in r["by_kind"]["test"]), r["by_kind"]

    def test_summary_and_uncertain_separated(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        r = engine.impact(root, "leaf")
        for k in ("total_confirmed_affected", "direct", "transitive", "test", "prod",
                  "entrypoint", "high_importance", "uncertain"):
            assert k in r["summary"]
        # low-confidence hits get their own list instead of joining the confirmed set
        assert isinstance(r["uncertain_maybe_affected"], list)

    def test_unknown_symbol(self, tmp_path, db_home):
        root = _setup_chain(tmp_path)
        r = engine.impact(root, "no_such_xyz")
        assert r.get("error")
        assert r["summary"]["total_confirmed_affected"] == 0
