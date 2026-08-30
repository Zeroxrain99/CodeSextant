"""Reference persistence must remain correct across concurrent index work."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor


def _write(path, source: str) -> str:
    path.write_text(source, encoding="utf-8")
    return str(path)


def _resolved(symbol: str, definition: str, caller: str) -> dict:
    line = 2 if symbol == "alpha" else 3
    return {
        "symbol": symbol,
        "definition": {"path": definition, "line": 1, "column": 0},
        "high_confidence": [{
            "src_path": caller,
            "line": line,
            "column": 0,
            "confidence": "high",
        }],
        "low_confidence": [],
        "engine": "jedi",
        "truncated": False,
    }


def test_concurrent_symbol_writes_in_one_source_preserve_both_edges(
        tmp_path, monkeypatch):
    from codesextant import engine, storage

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    repo = tmp_path / "repo"
    repo.mkdir()
    alpha = _write(repo / "alpha.py", "def alpha():\n    return 1\n")
    beta = _write(repo / "beta.py", "def beta():\n    return 2\n")
    caller = _write(
        repo / "caller.py",
        "from alpha import alpha\nalpha()\nbeta()\n",
    )
    engine.index_project(str(repo))

    def resolve(_root, symbol, def_path=None, **_kwargs):
        return _resolved(symbol, str(def_path), caller)

    monkeypatch.setattr(engine.references, "find_references", resolve)

    # Force the old read, merge, replace sequence to let both writers read the
    # same empty snapshot before either replaces the source file's whole edge set.
    read_barrier = threading.Barrier(2)
    original_all_refs = storage.ProjectStore.all_refs

    def interleaved_all_refs(store):
        rows = original_all_refs(store)
        read_barrier.wait(timeout=5)
        return rows

    monkeypatch.setattr(storage.ProjectStore, "all_refs", interleaved_all_refs)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                engine.find_references,
                str(repo),
                symbol,
                def_path=definition,
            )
            for symbol, definition in (("alpha", alpha), ("beta", beta))
        ]
        for future in futures:
            future.result(timeout=10)

    with storage.ProjectStore.open_readonly(str(repo)) as store:
        rows = store.conn.execute(
            "SELECT symbol_name FROM refs WHERE src_path=? ORDER BY symbol_name",
            (caller,),
        ).fetchall()
    assert [row["symbol_name"] for row in rows] == ["alpha", "beta"]


def test_reindex_overlap_cannot_persist_a_stale_reference_edge(
        tmp_path, monkeypatch):
    from codesextant import engine, storage

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    repo = tmp_path / "repo"
    repo.mkdir()
    definition = _write(repo / "target.py", "def target():\n    return 1\n")
    caller = _write(
        repo / "caller.py",
        "from target import target\ntarget()\n",
    )
    engine.index_project(str(repo))

    resolution_started = threading.Event()
    allow_resolution = threading.Event()

    def stale_resolution(_root, symbol, def_path=None, **_kwargs):
        resolution_started.set()
        assert allow_resolution.wait(timeout=10)
        return _resolved(symbol, str(def_path), caller)

    monkeypatch.setattr(engine.references, "find_references", stale_resolution)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            engine.find_references,
            str(repo),
            "target",
            def_path=definition,
        )
        assert resolution_started.wait(timeout=5)
        _write(repo / "target.py", "def replacement():\n    return 2\n")
        update = engine.index_paths(str(repo), [definition])
        assert update["indexed"] == 1
        allow_resolution.set()
        pending.result(timeout=10)

    with storage.ProjectStore.open_readonly(str(repo)) as store:
        rows = store.conn.execute(
            "SELECT symbol_name,def_path FROM refs ORDER BY symbol_name"
        ).fetchall()
    assert rows == []


def test_failed_index_transaction_does_not_advance_generation(
        tmp_path, monkeypatch):
    from codesextant import engine, storage

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    repo = tmp_path / "repo"
    repo.mkdir()
    source = _write(repo / "module.py", "def original():\n    return 1\n")
    engine.index_project(str(repo))

    with storage.ProjectStore.open(str(repo)) as store:
        generation = store.index_generation()
        store.conn.execute(
            "CREATE TRIGGER fail_replacement BEFORE INSERT ON symbols "
            "WHEN NEW.name='replacement' BEGIN "
            "SELECT RAISE(ABORT, 'injected generation failure'); END"
        )
        store.conn.commit()

    _write(repo / "module.py", "def replacement():\n    return 2\n")
    failed = engine.index_paths(str(repo), [source])
    assert failed["errors"] == 1
    with storage.ProjectStore.open(str(repo)) as store:
        assert store.index_generation() == generation
        assert [row["name"] for row in store.get_symbols(source)] == ["original"]
        store.conn.execute("DROP TRIGGER fail_replacement")
        store.conn.commit()

    succeeded = engine.index_paths(str(repo), [source])
    assert succeeded["indexed"] == 1
    with storage.ProjectStore.open_readonly(str(repo)) as store:
        assert store.index_generation() == generation + 1
        assert [row["name"] for row in store.get_symbols(source)] == ["replacement"]


def test_a_locked_index_does_not_discard_a_resolved_answer(tmp_path, monkeypatch):
    """A busy index costs the caller its cached edges, never its result.

    A concurrent reindex holding the write lock is routine on a shared daemon. The
    references are fully resolved before persistence is attempted, so failing the whole
    query -- as a 500, over an optimization -- charged the caller everything to save a
    lookup they can simply redo.
    """
    import sqlite3

    from codesextant import engine, storage

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    repo = tmp_path / "repo"
    repo.mkdir()
    definition = _write(repo / "alpha.py", "def alpha():\n    return 1\n")
    caller = _write(repo / "caller.py", "from alpha import alpha\nalpha()\n")
    engine.index_project(str(repo))

    monkeypatch.setattr(
        engine.references, "find_references",
        lambda _root, symbol, def_path=None, **_kw: _resolved(
            symbol, str(def_path), caller))

    def locked(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(storage.ProjectStore, "replace_refs_for_symbol", locked)

    result = engine.find_references(str(repo), "alpha", def_path=definition)

    assert result["high_confidence"], "the resolved references must survive"
    assert result["references_persisted"] is False, "and say they were not cached"


def test_successful_persistence_is_reported(tmp_path, monkeypatch):
    from codesextant import engine

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    repo = tmp_path / "repo"
    repo.mkdir()
    definition = _write(repo / "alpha.py", "def alpha():\n    return 1\n")
    caller = _write(repo / "caller.py", "from alpha import alpha\nalpha()\n")
    engine.index_project(str(repo))

    monkeypatch.setattr(
        engine.references, "find_references",
        lambda _root, symbol, def_path=None, **_kw: _resolved(
            symbol, str(def_path), caller))

    result = engine.find_references(str(repo), "alpha", def_path=definition)

    assert result["references_persisted"] is True
