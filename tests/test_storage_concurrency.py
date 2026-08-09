"""Concurrency contract for the per-project SQLite store.

Multiple agents share one CodeSextant daemon, and the roadmap adds read-only
worker processes on top of that.  Both need the store to be opened in a mode
where a writer does not lock every reader out, and where a momentarily busy
database backs off instead of raising immediately.

These tests pin the contract, not the implementation detail of any one caller.
"""
from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from codesextant import storage


def _pragma(conn: sqlite3.Connection, name: str):
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


def test_store_opens_in_wal_mode(tmp_path, monkeypatch):
    """WAL lets readers keep reading while a writer is mid-transaction."""
    monkeypatch.setattr(storage, "default_db_dir", lambda: tmp_path)
    monkeypatch.setenv("CODESEXTANT_SQLITE_UNSAFE_WAL", "1")
    repo = tmp_path / "repo"
    repo.mkdir()

    with storage.ProjectStore.open(str(repo)) as store:
        assert str(_pragma(store.conn, "journal_mode")).lower() == "wal"


def test_store_sets_busy_timeout(tmp_path, monkeypatch):
    """A busy database must back off, not raise 'database is locked' at once."""
    monkeypatch.setattr(storage, "default_db_dir", lambda: tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()

    with storage.ProjectStore.open(str(repo)) as store:
        assert int(_pragma(store.conn, "busy_timeout")) >= 1000


def test_reader_not_blocked_by_open_write_transaction(tmp_path, monkeypatch):
    """The real multi-agent scenario: one indexer writing, others querying.

    A second connection must complete a read while the first still holds an
    uncommitted write transaction.  Under the default rollback journal this
    degrades into lock contention; under WAL the reader sees the last
    committed snapshot immediately.
    """
    monkeypatch.setattr(storage, "default_db_dir", lambda: tmp_path)
    monkeypatch.setenv("CODESEXTANT_SQLITE_UNSAFE_WAL", "1")
    repo = tmp_path / "repo"
    repo.mkdir()

    with storage.ProjectStore.open(str(repo)) as writer:
        db_file = writer.db_file
        writer.conn.execute("BEGIN IMMEDIATE")
        writer.conn.execute(
            "INSERT INTO meta(key,value) VALUES('concurrency_probe','1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value")

        read_ok: list[bool] = []
        read_err: list[BaseException] = []

        def _read():
            try:
                conn = sqlite3.connect(str(db_file), timeout=3.0)
                try:
                    conn.execute("SELECT count(*) FROM meta").fetchone()
                    read_ok.append(True)
                finally:
                    conn.close()
            except BaseException as exc:  # noqa: BLE001 - surfaced via assert
                read_err.append(exc)

        t = threading.Thread(target=_read)
        started = time.monotonic()
        t.start()
        t.join(timeout=5.0)
        elapsed = time.monotonic() - started

        writer.conn.rollback()

    assert not t.is_alive(), "reader thread never finished; writer locked it out"
    assert not read_err, f"reader failed while a write transaction was open: {read_err}"
    assert read_ok == [True]
    assert elapsed < 2.0, (
        f"reader waited {elapsed:.2f}s behind an open write transaction; "
        "expected an immediate WAL snapshot read")


def test_wal_mode_survives_reopen(tmp_path, monkeypatch):
    """Journal mode is persistent, so reopening must not silently regress."""
    monkeypatch.setattr(storage, "default_db_dir", lambda: tmp_path)
    monkeypatch.setenv("CODESEXTANT_SQLITE_UNSAFE_WAL", "1")
    repo = tmp_path / "repo"
    repo.mkdir()

    with storage.ProjectStore.open(str(repo)):
        pass
    with storage.ProjectStore.open(str(repo)) as store:
        assert str(_pragma(store.conn, "journal_mode")).lower() == "wal"


@pytest.mark.parametrize("env_value,expected", [("2500", 2500), ("bogus", 5000)])
def test_busy_timeout_is_configurable(tmp_path, monkeypatch, env_value, expected):
    """Per L0 rule 6 every new behaviour needs a switch and a tunable value."""
    monkeypatch.setattr(storage, "default_db_dir", lambda: tmp_path)
    monkeypatch.setenv("CODESEXTANT_SQLITE_BUSY_TIMEOUT_MS", env_value)
    repo = tmp_path / "repo"
    repo.mkdir()

    with storage.ProjectStore.open(str(repo)) as store:
        assert int(_pragma(store.conn, "busy_timeout")) == expected


def test_wal_can_be_disabled_by_switch(tmp_path, monkeypatch):
    """Escape hatch: operators must be able to fall back to the old journal."""
    monkeypatch.setattr(storage, "default_db_dir", lambda: tmp_path)
    monkeypatch.setenv("CODESEXTANT_SQLITE_WAL", "0")
    repo = tmp_path / "repo"
    repo.mkdir()

    with storage.ProjectStore.open(str(repo)) as store:
        assert str(_pragma(store.conn, "journal_mode")).lower() != "wal"


@pytest.mark.parametrize(
    "version,expected",
    [
        ((3, 44, 5), False),
        ((3, 44, 6), True),
        ((3, 45, 1), False),
        ((3, 49, 9), False),
        ((3, 50, 6), False),
        ((3, 50, 7), True),
        ((3, 51, 2), False),
        ((3, 51, 3), True),
        ((3, 52, 0), True),
    ],
)
def test_wal_safety_gate_matches_fixed_sqlite_releases(version, expected):
    assert storage.sqlite_wal_is_safe(version) is expected


def test_affected_sqlite_defaults_to_rollback_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "default_db_dir", lambda: tmp_path)
    monkeypatch.setattr(storage.sqlite3, "sqlite_version_info", (3, 45, 1))
    monkeypatch.delenv("CODESEXTANT_SQLITE_WAL", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()

    monkeypatch.setenv("CODESEXTANT_SQLITE_UNSAFE_WAL", "1")
    with storage.ProjectStore.open(str(repo)) as store:
        assert str(_pragma(store.conn, "journal_mode")).lower() == "wal"

    monkeypatch.delenv("CODESEXTANT_SQLITE_UNSAFE_WAL")
    with storage.ProjectStore.open(str(repo)) as store:
        assert str(_pragma(store.conn, "journal_mode")).lower() != "wal"


def test_sqlite_runtime_status_reports_effective_wal_policy(monkeypatch):
    monkeypatch.setattr(storage.sqlite3, "sqlite_version", "3.45.1")
    monkeypatch.setattr(storage.sqlite3, "sqlite_version_info", (3, 45, 1))
    monkeypatch.delenv("CODESEXTANT_SQLITE_UNSAFE_WAL", raising=False)

    status = storage.sqlite_runtime_status()

    assert status == {
        "version": "3.45.1",
        "wal_safe": False,
        "unsafe_wal_override": False,
        "wal_requested": True,
        "wal_allowed": False,
    }
