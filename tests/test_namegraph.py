"""Tests for namegraph, which repairs the degenerate map, and for find_unwired,
which looks for symbols nothing wires in.

Deliberately self-contained. Each test builds a small throwaway project with an
isolated CODESEXTANT_HOME, so the suite repeats cleanly on any machine.

Covered:
  - The degeneracy repair: PageRank stops splitting evenly, and a symbol several
    files reference outranks an isolated one.
  - The core constraint: name-level edges never reach the refs table, leaving
    callgraph, impact and refs untouched.
  - The env switches. CODESEXTANT_NAMEGRAPH_DISABLED restores the degenerate
    behaviour, and MAX_FANOUT caps edge growth.
  - compute_external_usage is body-aware: the definition line and recursive
    self-calls are not external usage, and a same-file helper is not misreported.
  - Every find_unwired branch: real unwired symbols are caught; helpers and
    cross-file references are not flagged; entrypoints, dunders and methods are
    exempt; over-common names return UNKNOWN_FANOUT; an unindexed project
    raises; the honesty fields are present; results serialize to JSON; and the
    whole thing works across languages.
"""
import json
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine, namegraph, storage  # noqa: E402


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """Build a throwaway project with an isolated CODESEXTANT_HOME and return
    its root path as a string."""
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


def _ranks(m):
    return {s["name"]: s["rank"] for s in m["symbols"]}


def _distinct_ranks(m):
    return len(set(round(s["rank"], 10) for s in m["symbols"]))


# The degeneracy repair.

def test_namegraph_fixes_pagerank_degeneration(project):
    """Before the fix, PageRank handed every symbol the same score. Name-level
    edges lift hub, which three files reference, above the isolated lonely."""
    _write(project, "core.py", "def hub():\n    return 1\n\ndef lonely():\n    return 0\n")
    _write(project, "a.py", "from core import hub\ndef ua():\n    return hub()\n")
    _write(project, "b.py", "from core import hub\ndef ub():\n    return hub()\n")
    _write(project, "c.py", "from core import hub\ndef uc():\n    return hub()\n")
    engine.index_project(project, force=True)
    m = engine.get_map(project, token_budget=2000)
    assert m["edge_sources"]["name_low_edges"] > 0
    assert _distinct_ranks(m) > 1                 # the flat distribution is gone
    r = _ranks(m)
    assert r["hub"] > r["lonely"]                 # three referencing files beat zero


def test_namegraph_disabled_reverts_to_degeneration(project, monkeypatch):
    """CODESEXTANT_NAMEGRAPH_DISABLED=1 builds no name-level edges, which puts
    PageRank back into its flat, degenerate state."""
    _write(project, "core.py", "def hub():\n    return 1\n")
    _write(project, "a.py", "from core import hub\ndef ua():\n    return hub()\n")
    engine.index_project(project, force=True)
    monkeypatch.setenv("CODESEXTANT_NAMEGRAPH_DISABLED", "1")
    m = engine.get_map(project, token_budget=2000)
    assert m["edge_sources"]["name_low_edges"] == 0
    assert _distinct_ranks(m) == 1                # back to identical scores


def test_namegraph_does_not_pollute_refs_table(project):
    """The core constraint: name-level edges live in memory and never reach the
    refs table, which is what keeps callgraph, impact and refs trustworthy."""
    _write(project, "core.py", "def hub():\n    return 1\n")
    _write(project, "a.py", "from core import hub\ndef ua():\n    return hub()\n")
    engine.index_project(project, force=True)
    engine.get_map(project, token_budget=2000)    # this builds the name-level edges
    with storage.ProjectStore.open(project) as st:
        assert len(st.all_refs()) == 0            # refs stays empty; nothing was persisted


def test_get_map_mixes_db_high_and_name_low_edges(project):
    """PageRank is fed a mix: high-confidence edges persisted by find_references
    alongside low-confidence name-level edges."""
    _write(project, "core.py", "def hub():\n    return 1\n")
    _write(project, "a.py", "from core import hub\ndef ua():\n    return hub()\n")
    engine.index_project(project, force=True)
    engine.find_references(project, "hub", persist=True)   # lays down the high edges
    m = engine.get_map(project, token_budget=2000)
    assert m["edge_sources"]["db_high_edges"] > 0
    assert m["edge_sources"]["name_low_edges"] > 0


# The heart of namegraph: build_name_edges.

def test_build_name_edges_low_confidence_and_skips_undefined(project):
    """Every name-level edge is low confidence, and edges are built only for
    names the project actually defines. Undefined and builtin names get none."""
    _write(project, "core.py", "def hub():\n    return 1\n")
    _write(project, "use.py",
           "from core import hub\ndef caller():\n    hub()\n    print('externalname')\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
        indexed = st.all_indexed_files()
    edges, meta = namegraph.build_name_edges(syms, indexed_files=indexed)
    assert edges and all(e["confidence"] == "low" for e in edges)
    assert any(e["symbol_name"] == "hub" for e in edges)
    assert not any(e["symbol_name"] in ("print", "externalname") for e in edges)


def test_build_name_edges_fanout_to_all_same_name_defs(project):
    """Fan-out across same-name definitions: a reference to X links to every
    file defining X, which is what compute_pagerank expects to receive."""
    _write(project, "a.py", "def shared():\n    return 1\n")
    _write(project, "b.py", "def shared():\n    return 2\n")
    _write(project, "use.py", "def caller():\n    return shared()\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
        indexed = st.all_indexed_files()
    edges, _ = namegraph.build_name_edges(syms, indexed_files=indexed)
    def_paths = {os.path.basename(e["def_path"]) for e in edges if e["symbol_name"] == "shared"}
    assert def_paths == {"a.py", "b.py"}          # fanned out to both definitions


def test_build_name_edges_respects_max_fanout(project):
    """Once a name has more definitions than max_fanout, it gets no edges at
    all. Otherwise a very common name would explode into a cartesian product."""
    for i in range(5):
        _write(project, f"d{i}.py", "def dup():\n    return 0\n")
    _write(project, "use.py", "def caller():\n    return dup()\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
        indexed = st.all_indexed_files()
    edges, meta = namegraph.build_name_edges(syms, indexed_files=indexed, max_fanout=3)
    assert not any(e["symbol_name"] == "dup" for e in edges)
    assert meta["skipped_fanout_names"] >= 1


def test_build_name_edges_aggregates_same_line_occurrences(project):
    """A name repeated on one caller line collapses into a single edge, with
    multiplicity holding the real number of references."""
    core = _write(project, "core.py", "def hub():\n    return 1\n")
    use = _write(project, "use.py", "def caller():\n    return hub() + hub() + hub()\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
    edges, meta = namegraph.build_name_edges(
        syms, indexed_files=[core, use])
    hub_edges = [e for e in edges if e["symbol_name"] == "hub"]
    assert len(hub_edges) == 1
    assert hub_edges[0]["multiplicity"] == 3
    assert meta["unique_edges"] == 1
    assert meta["total_edges"] == 3


def test_large_map_file_limit_is_adaptive_but_env_can_override(monkeypatch):
    """A large index shrinks the work done per request by default, while an
    explicit env setting still wins over whatever the heuristic picked."""
    monkeypatch.delenv("CODESEXTANT_NAMEGRAPH_MAX_FILES", raising=False)
    limit, adaptive = namegraph.map_file_limit(570_651)
    assert adaptive is True
    assert 12 <= limit < 40
    monkeypatch.setenv("CODESEXTANT_NAMEGRAPH_MAX_FILES", "123")
    assert namegraph.map_file_limit(570_651) == (123, False)


def test_namegraph_truncation_samples_across_repo_not_only_prefix(tmp_path):
    """Past the file limit, sampling is stratified and deterministic, so a large
    monorepo does not get judged on whatever sorts to the front every time."""
    target = str(tmp_path / "target.py")
    symbols = [{
        "path": target, "name": "hub", "line": 1, "end_line": 1,
        "scope": "", "kind": "function",
    }]
    files = [str(tmp_path / f"part_{i:02d}.py") for i in range(10)]
    visited = []

    def fake_read(path):
        visited.append(path)
        return "hub()\n"

    _edges, meta = namegraph.build_name_edges(
        symbols, indexed_files=files, read_text=fake_read, max_files=3)
    assert meta["total_files"] == 10
    assert meta["scanned_files"] == 3
    assert meta["truncated"] is True
    assert meta["sampling"] == "stratified"
    assert set(visited) != {namegraph._normp(p) for p in files[:3]}


def test_namegraph_unique_edge_budget_stops_growth(project, monkeypatch):
    """Pathological generated code must not let one map request grow its edge
    dict without bound and eat all available memory."""
    monkeypatch.setenv("CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES", "2")
    _write(project, "core.py",
           "def alpha():\n    return 1\ndef beta():\n    return 2\ndef gamma():\n    return 3\n")
    _write(project, "use.py", "def caller():\n    alpha()\n    beta()\n    gamma()\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
        indexed = st.all_indexed_files()
    edges, meta = namegraph.build_name_edges(syms, indexed_files=indexed)
    assert len(edges) <= 2
    assert meta["truncated"] is True
    assert "edge_budget" in meta["truncation_reasons"]


def test_get_map_caches_same_revision_and_reindex_invalidates(project, monkeypatch):
    """A long-running daemon reuses the result for an unchanged revision. As
    soon as the index moves, the cache misses and never serves the old map."""
    _write(project, "core.py", "def hub():\n    return 1\n")
    _write(project, "use.py", "def caller():\n    return hub()\n")
    engine.index_project(project, force=True)
    engine._MAP_CACHE.clear()
    calls = 0
    real_rank = engine.rank_symbols

    def counted_rank(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_rank(*args, **kwargs)

    monkeypatch.setattr(engine, "rank_symbols", counted_rank)
    first = engine.get_map(project, token_budget=120)
    # simulate a daemon restart: the in-process LRU is gone, so the disk cache
    # is the only thing that can still answer
    engine._MAP_CACHE.clear()
    second = engine.get_map(project, token_budget=120)
    assert calls == 1
    assert first["edge_sources"]["map_cache_hit"] is False
    assert second["edge_sources"]["map_cache_hit"] is True
    assert second["edge_sources"]["map_cache_source"] == "disk"

    _write(project, "core.py", "def hub():\n    return 2\n\ndef added():\n    return 3\n")
    engine.index_project(project, force=True)
    third = engine.get_map(project, token_budget=120)
    assert calls == 2
    assert third["edge_sources"]["map_cache_hit"] is False
    assert third["edge_sources"]["map_cache_source"] == "compute"


def test_symbol_snapshot_roundtrip_and_revision_invalidation(project):
    """A JSON snapshot has to round-trip exactly, and after any reindex the old
    revision must refuse to load."""
    _write(project, "core.py", "def hub():\n    return 1\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        symbols_before = st.get_symbols()
        revision = st.symbol_revision()
        snapshot = storage.write_symbol_snapshot(
            st.db_file, revision, symbols_before)
        assert snapshot.is_file()
        assert st.load_symbol_snapshot(revision) == symbols_before

    _write(project, "core.py", "def hub():\n    return 2\n\ndef added():\n    return 3\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        assert st.symbol_revision() != revision
        assert st.load_symbol_snapshot(st.symbol_revision()) is None


# compute_external_usage, which is body-aware.

def test_external_usage_body_aware(project):
    """The symbol's own token on its definition line and any recursive self-call
    are not external usage. A call from elsewhere in the same file is."""
    _write(project, "m.py", '''
        def helper():
            return 1

        def caller():
            return helper()

        def lonely():
            return 9

        def recur(n):
            return recur(n - 1)
    ''')
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        syms = st.get_symbols()
        indexed = st.all_indexed_files()
    usage, over, _meta = namegraph.compute_external_usage(syms, indexed_files=indexed)
    by_name = {}
    for (p, l, n), c in usage.items():
        by_name.setdefault(n, []).append(c)
    assert max(by_name["helper"]) > 0     # called from outside its body, so external
    assert max(by_name["lonely"]) == 0    # nobody calls it
    assert max(by_name["recur"]) == 0     # only calls itself, from inside its own body
    assert over == set()


# find_unwired.

def test_find_unwired_catches_true_unwired_not_helper(project):
    """orphan_func really is unwired and gets caught. A helper called from its
    own file and a caller referenced from another file both stay clear."""
    _write(project, "m.py", '''
        def helper():
            return 1

        def caller():
            return helper()

        def orphan_func():
            return 99
    ''')
    _write(project, "main.py", "from m import caller\ndef run():\n    return caller()\n")
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    verdicts = {c["name"]: c["verdict"] for c in r["candidates"]}
    assert verdicts.get("orphan_func") == "UNWIRED_CANDIDATE"
    assert "helper" not in verdicts       # used by caller in the same file
    assert "caller" not in verdicts       # used by main across files


def test_find_unwired_exempts_entrypoint_and_dunder(project):
    """Functions in a test_ file, names listed in __all__, and dunders are all
    exempt. An ordinary function nobody uses becomes a candidate."""
    _write(project, "test_x.py", "def test_something():\n    return 1\n")
    _write(project, "app.py", '''
        __all__ = ["public_api"]

        def public_api():
            return 1

        def hidden():
            return 2
    ''')
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    names = {c["name"] for c in r["candidates"]}
    assert "test_something" not in names  # exempt: it lives in a test file
    assert "public_api" not in names      # exempt: listed in __all__
    assert "hidden" in names              # unused and unexempt, so a candidate


def test_find_unwired_skips_methods(project):
    """Methods and nested symbols are not candidates. Only top-level
    referenceable symbols are considered."""
    _write(project, "m.py", "class C:\n    def unused_method(self):\n        return 1\n")
    _write(project, "u.py", "from m import C\ndef run():\n    return C()\n")
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    names = {c["name"] for c in r["candidates"]}
    assert "unused_method" not in names


def test_find_unwired_unknown_fanout(project):
    """Too many definitions share the name, so no edges were built and the
    verdict is UNKNOWN_FANOUT rather than a guess that it is unwired."""
    for i in range(4):
        _write(project, f"d{i}.py", "def dup():\n    return 0\n")
    engine.index_project(project, force=True)
    r = engine.find_unwired(project, max_fanout=2)
    verdicts = {c["verdict"] for c in r["candidates"] if c["name"] == "dup"}
    assert verdicts == {"UNKNOWN_FANOUT"}


def test_find_unwired_unindexed_raises(project):
    """An unindexed project raises RuntimeError instead of failing quietly."""
    with pytest.raises(RuntimeError):
        engine.find_unwired(project)


def test_find_unwired_honest_fields_and_serializable(project):
    """The honesty fields are all present, and the whole result serializes to
    JSON, which the daemon needs in order to return it over HTTP."""
    _write(project, "m.py", "def orphan():\n    return 1\n")
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    assert r.get("verification_reminder")
    assert isinstance(r.get("read_code_advisory"), list) and r["read_code_advisory"]
    assert "summary" in r and "namegraph_meta" in r
    json.dumps(r, ensure_ascii=False, default=str)   # raises if anything is unserializable


# Cross-language behaviour. namegraph is pure regex, so it does not care.

def test_namegraph_works_for_typescript(project):
    """Name-level edges come from plain regex tokenization, so they work in any
    language. TS export and import escape the degenerate ranking too."""
    _write(project, "core.ts", "export function hub() { return 1; }\n")
    _write(project, "a.ts",
           "import { hub } from './core';\nexport function ua() { return hub(); }\n")
    engine.index_project(project, force=True)
    m = engine.get_map(project, token_budget=2000)
    assert m["edge_sources"]["name_low_edges"] > 0
    r = _ranks(m)
    assert r["hub"] >= r.get("ua", 0)            # the referenced hub ranks at least as high as ua


# Regression from adversarial review: single-file and single-module structures
# have to escape the flat ranking as well.

def test_intrafile_calls_escape_degeneration_callee_first(project):
    """A callee that happens to be the first symbol in its file still escapes
    the flat ranking, because src_line maps to the real caller rather than
    collapsing into a file representative."""
    _write(project, "app.py", '''
        def dispatch():
            return 1

        def h1():
            return dispatch()

        def h2():
            return dispatch()

        def h3():
            return dispatch()

        def never_called_dead():
            return 0
    ''')
    engine.index_project(project, force=True)
    m = engine.get_map(project, token_budget=2000)
    assert m["edge_sources"]["name_low_edges"] > 0
    r = _ranks(m)
    # dispatch is the first symbol in the file and three handlers in that same
    # file call it, so it has to outrank never_called_dead
    assert r["dispatch"] > r["never_called_dead"]


def test_intrafile_multi_beats_crossfile_single(project):
    """A symbol called many times within its file ranks at least as high as one
    called once from another file, since call counts are not deduplicated and
    src_line maps each call to its real caller."""
    _write(project, "core.py", '''
        def big_internal_api():
            return 1

        def c1():
            return big_internal_api()

        def c2():
            return big_internal_api()

        def c3():
            return big_internal_api()

        def c4():
            return big_internal_api()

        def c5():
            return big_internal_api()
    ''')
    _write(project, "util.py", "def tiny_util():\n    return 2\n")
    _write(project, "use.py", "from util import tiny_util\ndef run():\n    return tiny_util()\n")
    engine.index_project(project, force=True)
    m = engine.get_map(project, token_budget=2000)
    r = _ranks(m)
    assert r["big_internal_api"] >= r["tiny_util"]


# Fixes from adversarial review: entrypoint exemptions, and downgrading variables.

def test_find_unwired_exempts_console_scripts(project):
    """A function named in pyproject's [project.scripts] is an entrypoint, so it
    is exempt and never reported as unwired."""
    _write(project, "cli.py", "def cli_main():\n    return run_it()\n\ndef run_it():\n    return 1\n")
    _write(project, "pyproject.toml", '''
        [project]
        name = "demo"
        version = "0.0.1"

        [project.scripts]
        mytool = "cli:cli_main"
    ''')
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    names = {c["name"] for c in r["candidates"]}
    assert "cli_main" not in names              # exempt as a console_scripts entrypoint


def test_find_unwired_variable_downgraded(project):
    """A module-level variable candidate is marked low_confidence_kind, and its
    reason says UNKNOWN rather than claiming the variable is deletable."""
    _write(project, "config.py", "DEAD_CONST = 42\n")
    _write(project, "u.py", "def run():\n    return 1\n")
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    var_cands = [c for c in r["candidates"] if c["name"] == "DEAD_CONST"]
    assert var_cands and var_cands[0].get("low_confidence_kind") is True
    assert "UNKNOWN" in var_cands[0]["reason"]
    assert r["summary"].get("unwired_variable_candidates", 0) >= 1


def test_find_unwired_fastapi_decorator_exempt(project):
    """From adversarial review: the FastAPI object is not always called app, so
    a decorator like @api.get counts, and the websocket and on_event variants
    are exempt as well."""
    _write(project, "routes.py", '''
        api = object()

        @api.get("/x")
        def get_x():
            return 1

        @api.websocket("/ws")
        def ws_handler():
            return 2

        @api.on_event("startup")
        def on_start():
            return 3
    ''')
    engine.index_project(project, force=True)
    r = engine.find_unwired(project)
    names = {c["name"] for c in r["candidates"]}
    assert "get_x" not in names and "ws_handler" not in names and "on_start" not in names


# The token budget is a promise, not an estimate.

def test_get_map_payload_stays_within_the_requested_budget(project):
    """approx_tokens used to report the budget while the JSON was about four times it."""
    for i in range(40):
        _write(project, f"mod{i}.py",
               f"def handler_number_{i}():\n    return {i}\n\n"
               f"class ServiceNumber{i}:\n    def run_service(self):\n        return handler_number_{i}()\n")
    engine.index_project(project, force=True)

    for budget in (400, 900, 2500):
        m = engine.get_map(project, token_budget=budget)
        served = len(json.dumps(m, ensure_ascii=False, default=str)) // 4
        assert served <= budget, (
            f"budget={budget} but the caller received about {served} tokens")
        # the reported figure has to describe the same payload, within rounding
        assert abs(m["approx_tokens"] - served) <= 2
        assert m["count"] == len(m["symbols"])


def test_get_map_reports_when_the_budget_truncated_the_list(project):
    for i in range(30):
        _write(project, f"m{i}.py", f"def named_function_{i}():\n    return {i}\n")
    engine.index_project(project, force=True)
    small = engine.get_map(project, token_budget=300)
    large = engine.get_map(project, token_budget=20000)
    assert small["truncated_by_budget"] is True
    assert small["count"] < large["count"]
    assert large["truncated_by_budget"] is False


def test_get_map_returns_a_symbol_even_when_the_envelope_exceeds_the_budget(project):
    _write(project, "only.py", "def the_only_function():\n    return 1\n")
    engine.index_project(project, force=True)
    m = engine.get_map(project, token_budget=1)
    assert m["count"] == 1, "a tiny budget still has to answer what matters most"


# Which definitions may be name-match targets.

def test_short_names_are_not_name_match_targets(project):
    _write(project, "core.py", "def ab():\n    return 1\n\ndef abc():\n    return 2\n")
    _write(project, "use.py", "def caller():\n    return ab() + abc()\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        edges, _meta = namegraph.build_name_edges(
            st.get_symbols(), indexed_files=st.all_indexed_files())
    named = {e["symbol_name"] for e in edges}
    assert "ab" not in named, "a two-character name carries no reference signal"
    assert "abc" in named


def test_function_local_definitions_are_not_name_match_targets(project):
    """A helper nested in a function cannot be referenced by name from anywhere else."""
    _write(project, "helpers.py", """
        def build_tracker():
            class TrackingEvent:
                def notify(self):
                    return 1
            return TrackingEvent()
        """)
    _write(project, "caller.py", """
        def use_it(event):
            return event.notify()
        """)
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        edges, meta = namegraph.build_name_edges(
            st.get_symbols(), indexed_files=st.all_indexed_files())
    assert "notify" not in {e["symbol_name"] for e in edges}
    assert meta["skipped_target_defs"] >= 1


def test_plain_variables_are_not_targets_but_constants_are(project):
    _write(project, "conf.py", "SHARED_LIMIT = 5\nscratchvalue = 7\n")
    _write(project, "use.py", """
        from conf import SHARED_LIMIT, scratchvalue

        def consume():
            return SHARED_LIMIT + scratchvalue
        """)
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        edges, _meta = namegraph.build_name_edges(
            st.get_symbols(), indexed_files=st.all_indexed_files())
    named = {e["symbol_name"] for e in edges}
    assert "SHARED_LIMIT" in named, "a screaming-snake constant is meant to be referenced"
    assert "scratchvalue" not in named


def test_unwired_detection_keeps_the_definitions_ranking_drops(project):
    """The ranking filter must not narrow what find_unwired analyses."""
    _write(project, "conf.py", "scratchvalue = 1\n")
    engine.index_project(project, force=True)
    with storage.ProjectStore.open(project) as st:
        symbols = st.get_symbols()
        edges, _meta = namegraph.build_name_edges(
            symbols, indexed_files=st.all_indexed_files())
        usage, _over, _usage_meta = namegraph.compute_external_usage(symbols)
    assert "scratchvalue" not in {e["symbol_name"] for e in edges}, "ranking drops it"
    assert any(name == "scratchvalue" for (_dp, _dl, name) in usage), (
        "but unwired detection still has to analyse it")


# Test files are not the project's API surface.

def test_test_definitions_do_not_outrank_the_code_under_test(project):
    _write(project, "service.py", """
        def compute_total(rows):
            return sum(rows)
        """)
    _write(project, "runner.py", """
        from service import compute_total

        def report(rows):
            return compute_total(rows)
        """)
    _write(project, "tests/test_service.py", """
        from service import compute_total

        def compute_total_fixture():
            return [1, 2, 3]

        def test_one():
            return compute_total(compute_total_fixture())

        def test_two():
            return compute_total(compute_total_fixture())

        def test_three():
            return compute_total(compute_total_fixture())
        """)
    engine.index_project(project, force=True)
    m = engine.get_map(project, token_budget=20000)
    ranks = {}
    for s in m["symbols"]:
        ranks.setdefault(s["name"], s["rank"])
    assert ranks["compute_total"] > ranks["compute_total_fixture"], (
        "a test fixture must not outrank the production symbol it exercises")


def test_a_test_only_project_is_not_uniformly_demoted(project):
    """The test factor is relative: with nothing but tests, ordering is unchanged."""
    _write(project, "tests/test_a.py", """
        def shared_helper():
            return 1

        def test_alpha():
            return shared_helper()

        def test_beta():
            return shared_helper()
        """)
    engine.index_project(project, force=True)
    m = engine.get_map(project, token_budget=20000)
    ranks = {s["name"]: s["rank"] for s in m["symbols"]}
    assert ranks["shared_helper"] > ranks["test_alpha"]


# A cached map must not outlive the code that produced it.

def test_map_cache_key_changes_with_the_engine_version(project, monkeypatch):
    _write(project, "core.py", "def hub_function():\n    return 1\n")
    engine.index_project(project, force=True)
    first = engine._map_cache_key(project, 2000, 0.85, None, None, True)
    monkeypatch.setattr(engine.storage, "db_path_for", engine.storage.db_path_for)
    import codesextant
    monkeypatch.setattr(codesextant, "__version__", "999.0.0")
    second = engine._map_cache_key(project, 2000, 0.85, None, None, True)
    assert first != second, "an upgrade must not serve a map built by the old ranking"
