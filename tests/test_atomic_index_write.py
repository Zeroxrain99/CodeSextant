"""One source file must become visible as one coherent index revision."""

from __future__ import annotations

import sqlite3

import pytest


def _symbol(name: str, line: int) -> dict:
    return {
        "kind": "function",
        "name": name,
        "line": line,
        "end_line": line + 1,
        "scope": "",
    }


def _comment(text: str, line: int) -> dict:
    return {
        "line": line,
        "end_line": line,
        "kind": "line",
        "is_doc": False,
        "tag": None,
        "scope": "",
        "owner_line": None,
        "text": text,
    }


def _fingerprint(name: str, line: int, shape_hash: str) -> dict:
    return {
        "name": name,
        "kind": "function",
        "line": line,
        "end_line": line + 1,
        "scope": "",
        "shape_hash": shape_hash,
        "raw_token_hash": f"raw-{shape_hash}",
        "call_hash": f"call-{shape_hash}",
        "node_count": 12,
        "nstmts": 3,
        "has_control_flow": True,
        "cognitive": 2,
    }


def _seed_old_revision(store, path: str) -> None:
    store.store_file_symbols(path, "old-hash", [_symbol("old", 1)], indexed_at=1.0)
    store.store_file_comments(path, [_comment("old comment", 2)])
    store.store_file_fingerprints(
        path,
        [_fingerprint("old", 1, "old-shape")],
        [{"line": 1, "fp_value": 101}],
    )
    store.replace_refs_for(
        path,
        [{
            "src_path": path,
            "src_line": 2,
            "symbol_name": "target",
            "def_path": "target.py",
            "def_line": 1,
            "confidence": "high",
        }],
    )
    store.replace_refs_for(
        "caller.py",
        [
            {
                "src_path": "caller.py",
                "src_line": 3,
                "symbol_name": "old",
                "def_path": path,
                "def_line": 1,
                "confidence": "high",
            },
            {
                "src_path": "caller.py",
                "src_line": 4,
                "symbol_name": "unrelated",
                "def_path": "other.py",
                "def_line": 1,
                "confidence": "low",
            },
        ],
    )


def _file_revision(store, path: str) -> dict:
    tables = {
        "files": ("path,content_hash,indexed_at", "path=?"),
        "symbols": ("path,kind,name,line,end_line,scope", "path=?"),
        "comments": (
            "path,line,end_line,kind,is_doc,tag,scope,owner_line,text",
            "path=?",
        ),
        "fingerprints": (
            "path,name,kind,line,end_line,scope,shape_hash,raw_token_hash,"
            "call_hash,node_count,nstmts,has_control_flow,cognitive",
            "path=?",
        ),
        "fingerprint_index": ("path,line,fp_value", "path=?"),
    }
    result = {}
    for table, (columns, predicate) in tables.items():
        rows = store.conn.execute(
            f"SELECT {columns} FROM {table} WHERE {predicate} ORDER BY rowid",
            (path,),
        ).fetchall()
        result[table] = [tuple(row) for row in rows]
    result["refs"] = [
        tuple(row)
        for row in store.conn.execute(
            "SELECT src_path,src_line,symbol_name,def_path,def_line,confidence "
            "FROM refs ORDER BY src_path,src_line"
        ).fetchall()
    ]
    return result


def _replace_with_new_revision(store, path: str) -> None:
    store.store_file_index(
        path,
        "new-hash",
        [_symbol("new", 10)],
        indexed_at=2.0,
        comments=[_comment("new comment", 11)],
        fingerprints=[_fingerprint("new", 10, "new-shape")],
        winnow_index=[{"line": 10, "fp_value": 202}],
    )


def test_atomic_file_index_rolls_back_every_table_on_mid_write_failure(
        tmp_path, monkeypatch):
    from codesextant import storage

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    path = str(tmp_path / "module.py")
    with storage.ProjectStore.open(str(tmp_path)) as store:
        _seed_old_revision(store, path)
        before = _file_revision(store, path)
        store.conn.execute(
            "CREATE TRIGGER fail_new_comment BEFORE INSERT ON comments "
            "WHEN NEW.text='new comment' BEGIN "
            "SELECT RAISE(ABORT, 'injected mid-write failure'); END"
        )
        store.conn.commit()

        with pytest.raises(sqlite3.IntegrityError, match="injected mid-write failure"):
            _replace_with_new_revision(store, path)

        assert _file_revision(store, path) == before
        assert store.needs_reindex(path, "new-hash") is True
        assert store.needs_reindex(path, "old-hash") is False


def test_atomic_file_index_replaces_all_auxiliary_rows_together(
        tmp_path, monkeypatch):
    from codesextant import storage

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    path = str(tmp_path / "module.py")
    with storage.ProjectStore.open(str(tmp_path)) as store:
        _seed_old_revision(store, path)

        _replace_with_new_revision(store, path)

        revision = _file_revision(store, path)
        assert revision["files"] == [(path, "new-hash", 2.0)]
        assert [row[2] for row in revision["symbols"]] == ["new"]
        assert [row[-1] for row in revision["comments"]] == ["new comment"]
        assert [row[6] for row in revision["fingerprints"]] == ["new-shape"]
        assert revision["fingerprint_index"] == [(path, 10, 202)]
        assert revision["refs"] == [
            ("caller.py", 4, "unrelated", "other.py", 1, "low")
        ]
        assert store.needs_reindex(path, "new-hash") is False


def test_auxiliary_extraction_failure_keeps_core_index_tolerant(
        tmp_path, monkeypatch):
    from codesextant import engine, storage

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    repo = tmp_path / "repo"
    repo.mkdir()
    source_path = repo / "module.py"
    source_path.write_text("def current():\n    return True\n", encoding="utf-8")
    path = str(source_path)
    with storage.ProjectStore.open(str(repo)) as store:
        _seed_old_revision(store, path)

    def fail_extraction(*_args, **_kwargs):
        raise RuntimeError("optional extractor failed")

    monkeypatch.setattr(engine.comments, "comments_enabled", lambda: True)
    monkeypatch.setattr(
        engine.comments, "extract_comments_from_source", fail_extraction)
    monkeypatch.setattr(engine.clones, "dedup_enabled", lambda: True)
    monkeypatch.setattr(
        engine.clones, "extract_fingerprints_from_source", fail_extraction)

    result = engine.index_project(str(repo), force=True)

    assert result["indexed"] == 1
    assert result["errors"] == 0
    with storage.ProjectStore.open(str(repo)) as store:
        revision = _file_revision(store, path)
        assert [row[2] for row in revision["symbols"]] == ["current"]
        assert revision["comments"] == []
        assert revision["fingerprints"] == []
        assert revision["fingerprint_index"] == []
