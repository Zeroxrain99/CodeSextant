"""Deadline enforcement for CPU-bound SQLite status queries."""
from __future__ import annotations

import sqlite3
import time
from urllib.parse import urlencode, urlparse

import pytest


def _install_slow_symbols_view(store, *, row_count: int = 10_000_000) -> None:
    """Replace the empty symbols table with a deterministic CPU-bound view."""
    assert isinstance(row_count, int) and row_count > 0
    store.conn.execute("DROP TABLE symbols")
    store.conn.execute(
        "CREATE VIEW symbols AS "
        "WITH RECURSIVE sequence(value) AS ("
        "SELECT 1 UNION ALL SELECT value + 1 FROM sequence "
        f"WHERE value < {row_count}"
        ") "
        "SELECT '' AS path, '' AS kind, '' AS name, value AS line, "
        "value AS end_line, '' AS scope FROM sequence"
    )
    store.conn.commit()


def test_status_interrupts_cpu_bound_stats_within_database_budget(
        tmp_path, monkeypatch):
    from codesextant import daemon, storage

    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("CODESEXTANT_STATUS_DB_TIMEOUT_MS", "20")
    with storage.ProjectStore.open(str(project)) as store:
        _install_slow_symbols_view(store)

    started = time.monotonic()
    code, result = daemon._ep_status(urlparse(
        "/status?" + urlencode({"project": str(project)})), None)
    elapsed = time.monotonic() - started

    assert code == 200
    assert elapsed < 0.5
    assert result["partial"] is True
    assert result["index_status_error"] == "unavailable"
    assert "service_load" in result
    assert "background_recoveries" in result


def test_stats_clears_progress_handler_after_interruption(tmp_path, monkeypatch):
    from codesextant import storage

    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    with storage.ProjectStore.open(str(project)) as store:
        _install_slow_symbols_view(store)

    with storage.ProjectStore.open_readonly(str(project)) as store:
        with pytest.raises(sqlite3.OperationalError, match="interrupt"):
            store.stats(deadline=time.monotonic() + 0.02)

        row = store.conn.execute(
            "WITH RECURSIVE sequence(value) AS ("
            "SELECT 1 UNION ALL SELECT value + 1 FROM sequence WHERE value < 10000"
            ") SELECT SUM(value) FROM sequence"
        ).fetchone()

    assert row[0] == 50_005_000
