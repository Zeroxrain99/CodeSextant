"""Read-only store access: the prerequisite for out-of-process query workers.

``ProjectStore.open`` writes on every call (schema script, column migration and
two meta rows, then a commit).  That is correct for the single writer, but it
means a worker process cannot open the same database through a SQLite
``mode=ro`` URI, and it means every cheap read currently takes the write path.

``open_readonly`` gives readers a connection that provably cannot write.
"""
from __future__ import annotations

import sqlite3

import pytest

from codesextant import storage


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "default_db_dir", lambda: tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    with storage.ProjectStore.open(str(repo)) as store:
        store._set_meta("seeded", "yes")
        store.conn.commit()
    return repo


def test_open_readonly_can_read_existing_data(tmp_path, monkeypatch):
    repo = _seed(tmp_path, monkeypatch)
    with storage.ProjectStore.open_readonly(str(repo)) as store:
        row = store.conn.execute(
            "SELECT value FROM meta WHERE key='seeded'").fetchone()
        assert row["value"] == "yes"


def test_open_readonly_refuses_writes(tmp_path, monkeypatch):
    """A worker must not be able to corrupt the index even by mistake."""
    repo = _seed(tmp_path, monkeypatch)
    with storage.ProjectStore.open_readonly(str(repo)) as store:
        with pytest.raises(sqlite3.OperationalError):
            store.conn.execute(
                "INSERT INTO meta(key,value) VALUES('intruder','1')")


def test_open_readonly_does_not_create_a_database(tmp_path, monkeypatch):
    """Opening an unknown project read-only must fail, not silently create."""
    monkeypatch.setattr(storage, "default_db_dir", lambda: tmp_path)
    missing = tmp_path / "never_indexed"
    missing.mkdir()

    with pytest.raises(FileNotFoundError):
        storage.ProjectStore.open_readonly(str(missing))

    assert not storage.db_path_for(str(missing)).exists()


def test_open_readonly_keeps_project_identity(tmp_path, monkeypatch):
    repo = _seed(tmp_path, monkeypatch)
    with storage.ProjectStore.open_readonly(str(repo)) as store:
        assert store.project_key == storage.project_key(str(repo))
        assert store.repo_path == str(repo)
        assert store.read_only is True


def test_open_marks_itself_writable(tmp_path, monkeypatch):
    repo = _seed(tmp_path, monkeypatch)
    with storage.ProjectStore.open(str(repo)) as store:
        assert store.read_only is False


def test_readonly_reads_during_open_write_transaction(tmp_path, monkeypatch):
    """The whole point: a reader stays live while the indexer holds the writer."""
    repo = _seed(tmp_path, monkeypatch)
    with storage.ProjectStore.open(str(repo)) as writer:
        writer.conn.execute("BEGIN IMMEDIATE")
        writer.conn.execute(
            "INSERT INTO meta(key,value) VALUES('mid_write','1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        with storage.ProjectStore.open_readonly(str(repo)) as reader:
            row = reader.conn.execute(
                "SELECT value FROM meta WHERE key='seeded'").fetchone()
            assert row["value"] == "yes"
            # Uncommitted writer data must not be visible to the snapshot read.
            assert reader.conn.execute(
                "SELECT value FROM meta WHERE key='mid_write'").fetchone() is None
        writer.conn.rollback()


def test_project_listing_does_not_apply_write_pragmas(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    project = tmp_path / "project"
    project.mkdir()
    with storage.ProjectStore.open(str(project)):
        pass

    monkeypatch.setattr(
        storage,
        "apply_connection_pragmas",
        lambda _conn: (_ for _ in ()).throw(AssertionError("listing must stay read-only")),
    )

    projects = storage.list_indexed_projects()

    assert len(projects) == 1
    assert "error" not in projects[0]
