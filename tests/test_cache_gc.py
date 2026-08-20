from __future__ import annotations

import json
import time
from pathlib import Path


def _write_project(storage, home: Path, name: str, *, accessed_at: float,
                   db_bytes: int = 256):
    repo = home.parent / name
    repo.mkdir()
    db_file = storage.db_path_for(str(repo))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_file.write_bytes(name.encode("ascii").ljust(db_bytes, b"x"))
    sidecar = Path(f"{db_file}.access.json")
    sidecar.write_text(json.dumps({
        "format": 1,
        "project_key": storage.project_key(str(repo)),
        "repo_path": str(repo.resolve()),
        "accessed_at": accessed_at,
    }), encoding="utf-8")
    return repo, db_file, sidecar


def _project_action(report: dict, project_key: str) -> dict:
    return next(
        action for action in report["projects"]
        if action["project_key"] == project_key
    )


def test_inventory_groups_only_exact_project_artifacts(tmp_path, monkeypatch):
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    repo, db_file, _sidecar = _write_project(
        storage, home, "repo", accessed_at=time.time())
    expected = {
        db_file.name,
        f"{db_file.name}-wal",
        f"{db_file.name}-shm",
        f"{db_file.name}.symbols-v1.json",
        f"{db_file.name}.map-v2.json",
        f"{db_file.name}.access.json",
    }
    for name in expected - {db_file.name, f"{db_file.name}.access.json"}:
        (home / name).write_bytes(b"cache")
    (home / "daemon.token").write_text("secret", encoding="ascii")
    (home / "daemon.log").write_text("log", encoding="utf-8")
    (home / "daemon-8790.instance.lock").write_bytes(b"lock")
    (home / "not-a-project.db").write_bytes(b"unmanaged")
    (home / f"{db_file.name}-journal").write_bytes(b"unmanaged")
    (home / f"{db_file.name}.map-v1.json.tmp").write_bytes(b"unmanaged")

    report = cache_gc.inventory()

    assert report["project_count"] == 1
    project = report["projects"][0]
    assert project["project_key"] == storage.project_key(str(repo))
    assert {artifact["name"] for artifact in project["artifacts"]} == expected
    assert project["repo_state"] == "present"


def test_touch_project_is_throttled_in_process(tmp_path, monkeypatch):
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    monkeypatch.setenv("CODESEXTANT_CACHE_TOUCH_INTERVAL_SEC", "60")
    repo = tmp_path / "repo"
    repo.mkdir()
    db_file = storage.db_path_for(str(repo))
    db_file.parent.mkdir(parents=True)
    db_file.write_bytes(b"db")
    cache_gc._TOUCH_TIMES.clear()

    first = cache_gc.touch_project(str(repo))
    sidecar = Path(f"{db_file}.access.json")
    original = sidecar.read_bytes()
    second = cache_gc.touch_project(str(repo))

    assert first["touched"] is True
    assert second == {
        "project_key": storage.project_key(str(repo)),
        "touched": False,
        "reason": "throttled",
    }
    assert sidecar.read_bytes() == original


def test_prune_removes_only_missing_projects_beyond_grace(
        tmp_path, monkeypatch):
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    monkeypatch.setenv("CODESEXTANT_CACHE_MAX_BYTES", str(1024 * 1024))
    monkeypatch.setenv("CODESEXTANT_CACHE_MISSING_GRACE_DAYS", "30")
    now = time.time()
    old_repo, old_db, _ = _write_project(
        storage, home, "old-missing", accessed_at=now - 31 * 86400)
    recent_repo, recent_db, _ = _write_project(
        storage, home, "recent-missing", accessed_at=now - 29 * 86400)
    old_repo.rmdir()
    recent_repo.rmdir()
    protected = {
        "daemon.token": b"secret",
        "daemon.log": b"log",
        "daemon-8790.instance.lock": b"lock",
    }
    for name, content in protected.items():
        (home / name).write_bytes(content)

    report = cache_gc.prune()

    old_key = storage.project_key(str(old_repo))
    old_action = _project_action(report, old_key)
    assert old_action["reason"] == "missing-repo"
    assert old_action["status"] == "deleted"
    assert not old_db.exists()
    assert recent_db.exists()
    for name, content in protected.items():
        assert (home / name).read_bytes() == content


def test_quota_pruning_uses_lru_order_and_stops_at_target(
        tmp_path, monkeypatch):
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    now = time.time()
    old_repo, old_db, _ = _write_project(
        storage, home, "old", accessed_at=now - 300, db_bytes=512)
    middle_repo, middle_db, _ = _write_project(
        storage, home, "middle", accessed_at=now - 200, db_bytes=512)
    new_repo, new_db, _ = _write_project(
        storage, home, "new", accessed_at=now - 100, db_bytes=512)
    managed = cache_gc.inventory()["managed_bytes"]
    monkeypatch.setenv("CODESEXTANT_CACHE_MAX_BYTES", str(managed - 1))
    monkeypatch.setenv("CODESEXTANT_CACHE_TARGET_RATIO", "0.8")

    report = cache_gc.prune()

    assert report["quota_triggered"] is True
    assert report["projected_after_bytes"] <= report["policy"]["target_bytes"]
    assert report["projects"][0]["project_key"] == storage.project_key(str(old_repo))
    assert report["projects"][0]["reason"] == "quota-lru"
    assert not old_db.exists()
    assert middle_db.exists()
    assert new_db.exists()
    assert storage.project_key(str(middle_repo)) not in report["excluded_project_keys"]
    assert storage.project_key(str(new_repo)) not in report["excluded_project_keys"]


def test_prune_never_removes_excluded_project_keys(tmp_path, monkeypatch):
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    now = time.time()
    old_repo, old_db, _ = _write_project(
        storage, home, "old", accessed_at=now - 200, db_bytes=512)
    new_repo, new_db, _ = _write_project(
        storage, home, "new", accessed_at=now - 100, db_bytes=512)
    managed = cache_gc.inventory()["managed_bytes"]
    monkeypatch.setenv("CODESEXTANT_CACHE_MAX_BYTES", str(managed - 1))
    monkeypatch.setenv("CODESEXTANT_CACHE_TARGET_RATIO", "0.75")
    old_key = storage.project_key(str(old_repo))

    report = cache_gc.prune(exclude_project_keys=(old_key,))

    assert old_db.exists()
    assert not new_db.exists()
    assert report["excluded_project_keys"] == [old_key]
    assert _project_action(
        report, storage.project_key(str(new_repo)))["status"] == "deleted"


def test_dry_run_reports_plan_without_deleting(tmp_path, monkeypatch):
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    monkeypatch.setenv("CODESEXTANT_CACHE_MISSING_GRACE_DAYS", "0")
    repo, db_file, sidecar = _write_project(
        storage, home, "missing", accessed_at=time.time() - 1)
    repo.rmdir()

    report = cache_gc.prune(dry_run=True)

    action = _project_action(report, storage.project_key(str(repo)))
    assert action["status"] == "planned"
    assert report["reclaimed_bytes"] == 0
    assert report["projected_after_bytes"] < report["before_bytes"]
    assert report["after_bytes"] == report["before_bytes"]
    assert db_file.exists()
    assert sidecar.exists()


def test_prune_rejects_targets_outside_codesextant_home(
        tmp_path, monkeypatch):
    from codesextant import cache_gc

    home = tmp_path / "state"
    home.mkdir()
    outside = tmp_path / "outside.db"
    outside.write_bytes(b"must survive")
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    monkeypatch.setenv("CODESEXTANT_CACHE_MAX_BYTES", "1")
    record = cache_gc._ProjectRecord(
        project_key="a" * 40,
        artifacts=(cache_gc._Artifact(outside, outside.name, 12, "db"),),
        total_bytes=12,
        last_access=0.0,
        repo_state="unknown",
        issues=(),
    )
    monkeypatch.setattr(
        cache_gc, "_inventory_records", lambda: ([record], []))

    report = cache_gc.prune()

    assert outside.read_bytes() == b"must survive"
    action = _project_action(report, record.project_key)
    assert action["status"] == "failed"
    assert report["errors"] == [{
        "project_key": record.project_key,
        "artifact": outside.name,
        "operation": "validate",
        "error": "outside-cache-home",
    }]


def test_prune_preserves_groups_with_unverified_metadata(tmp_path, monkeypatch):
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    repo, db_file, sidecar = _write_project(
        storage, home, "repo", accessed_at=time.time())
    sidecar.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("CODESEXTANT_CACHE_MAX_BYTES", "1")

    report = cache_gc.prune()

    action = _project_action(report, storage.project_key(str(repo)))
    assert action["status"] == "skipped"
    assert action["reason"] == "inventory-issues"
    assert report["quota_triggered"] is True
    assert report["quota_satisfied"] is False
    assert db_file.exists()
    assert sidecar.exists()


def test_prune_rechecks_activity_before_unlinking(tmp_path, monkeypatch):
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    repo, db_file, sidecar = _write_project(
        storage, home, "repo", accessed_at=time.time() - 100)
    records, issues = cache_gc._inventory_records()
    assert not issues
    assert not records[0].issues
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["accessed_at"] = time.time()
    payload["activity_marker"] = "changed after inventory"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("CODESEXTANT_CACHE_MAX_BYTES", "1")
    monkeypatch.setattr(
        cache_gc, "_inventory_records", lambda: (records, []))

    report = cache_gc.prune()

    action = _project_action(report, storage.project_key(str(repo)))
    assert action["status"] == "failed"
    assert any(
        error["error"] == "changed-since-inventory"
        for error in report["errors"]
    )
    assert db_file.exists()
    assert sidecar.exists()


def test_policy_defaults_are_bounded_and_deterministic(monkeypatch):
    from codesextant import cache_gc

    for name in (
        "CODESEXTANT_CACHE_MAX_BYTES",
        "CODESEXTANT_CACHE_TARGET_RATIO",
        "CODESEXTANT_CACHE_MISSING_GRACE_DAYS",
        "CODESEXTANT_CACHE_IDLE_GRACE_DAYS",
        "CODESEXTANT_CACHE_TOUCH_INTERVAL_SEC",
        "CODESEXTANT_CACHE_SCRATCH_GRACE_HOURS",
    ):
        monkeypatch.delenv(name, raising=False)

    policy = cache_gc.policy_from_env()

    assert policy.max_bytes == 10 * 1024 ** 3
    assert policy.target_ratio == 0.9
    assert policy.target_bytes == int(10 * 1024 ** 3 * 0.9)
    assert policy.missing_grace_seconds == 30 * 86400
    assert policy.idle_grace_seconds == 14 * 86400
    assert policy.scratch_grace_seconds == 24 * 3600
    assert policy.touch_interval_seconds > 0


def test_invalid_or_extreme_max_bytes_fall_back_to_safe_default(monkeypatch):
    from codesextant import cache_gc

    for value in ("0", "-1", "", "nan", str(2 ** 80)):
        monkeypatch.setenv("CODESEXTANT_CACHE_MAX_BYTES", value)
        assert cache_gc.policy_from_env().max_bytes == 10 * 1024 ** 3


def test_prune_removes_idle_present_projects_beyond_grace(
        tmp_path, monkeypatch):
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    monkeypatch.setenv("CODESEXTANT_CACHE_IDLE_GRACE_DAYS", "14")
    monkeypatch.setenv("CODESEXTANT_CACHE_MAX_BYTES", str(10 * 1024 ** 3))
    now = time.time()
    old_repo, old_db, _ = _write_project(
        storage, home, "old-idle", accessed_at=now - 15 * 86400)
    recent_repo, recent_db, _ = _write_project(
        storage, home, "recent-idle", accessed_at=now - 1 * 86400)

    report = cache_gc.prune()

    old_key = storage.project_key(str(old_repo))
    old_action = _project_action(report, old_key)
    assert old_action["reason"] == "idle-present"
    assert old_action["status"] == "deleted"
    assert not old_db.exists()
    assert recent_db.exists()
    assert recent_repo.exists()


def test_forget_project_deletes_one_group(tmp_path, monkeypatch):
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    now = time.time()
    target_repo, target_db, _ = _write_project(
        storage, home, "forget-me", accessed_at=now)
    keep_repo, keep_db, _ = _write_project(
        storage, home, "keep-me", accessed_at=now)

    result = cache_gc.forget_project(str(target_repo))

    assert result["status"] == "deleted"
    assert result["reason"] == "explicit-forget"
    assert not target_db.exists()
    assert keep_db.exists()
    assert keep_repo.exists()


def test_prune_scratch_removes_old_product_workspaces(tmp_path, monkeypatch):
    from codesextant import cache_gc

    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    old = temp_root / "codesextant-smoke-abc123"
    old.mkdir()
    (old / "wheel.whl").write_bytes(b"x" * 100)
    recent = temp_root / "codesextant-smoke-recent"
    recent.mkdir()
    (recent / "keep.bin").write_bytes(b"y" * 50)
    foreign = temp_root / "other-tool-cache"
    foreign.mkdir()
    (foreign / "data").write_bytes(b"z" * 20)
    now = time.time()
    os_utime = __import__("os").utime
    os_utime(old, (now - 48 * 3600, now - 48 * 3600))
    os_utime(recent, (now - 1 * 3600, now - 1 * 3600))
    monkeypatch.setenv("TEMP", str(temp_root))
    monkeypatch.setenv("TMP", str(temp_root))
    monkeypatch.setenv("TMPDIR", str(temp_root))
    monkeypatch.setenv("CODESEXTANT_CACHE_SCRATCH_GRACE_HOURS", "24")
    monkeypatch.setattr(cache_gc, "_scratch_roots", lambda: [temp_root])

    report = cache_gc.prune_scratch()

    assert not old.exists()
    assert recent.exists()
    assert foreign.exists()
    assert report["reclaimed_bytes"] >= 100
    assert any(item["path"] == str(old) for item in report["deleted"])


def test_scratch_roots_never_resolve_empty_env_to_cwd(tmp_path, monkeypatch):
    from codesextant import cache_gc

    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setenv("TEMP", str(tmp_path / "Temp"))
    monkeypatch.setenv("TMP", str(tmp_path / "Temp"))
    (tmp_path / "Temp").mkdir()
    monkeypatch.setenv("TMPDIR", "")
    monkeypatch.delenv("TMPDIR", raising=False)
    import tempfile
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "Temp"))

    roots = cache_gc._scratch_roots()

    assert roots == [(tmp_path / "Temp").resolve()]
    assert all(".git" not in str(root) for root in roots)


def _write_sqlite_project(storage, home: Path, name: str, *,
                          journal_mode: str = "delete"):
    """Real SQLite database with repo_path metadata but no access sidecar."""
    import sqlite3
    repo = home.parent / name
    repo.mkdir()
    db_file = storage.db_path_for(str(repo))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(f"PRAGMA journal_mode={journal_mode}")
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('repo_path', ?)",
            (str(repo.resolve()),))
        conn.commit()
    finally:
        conn.close()
    return repo, db_file


def test_forget_succeeds_on_wal_group_without_access_sidecar(
        tmp_path, monkeypatch):
    """Reading repo_path during inventory must not touch -shm, or the
    deletion is rejected by our own restat guard (changed-since-inventory)."""
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    repo, db_file = _write_sqlite_project(
        storage, home, "wal-orphan", journal_mode="wal")
    shm = Path(f"{db_file}-shm")
    shm.write_bytes(b"")

    result = cache_gc.forget_project(str(repo))

    assert result["status"] == "deleted", result
    assert not db_file.exists()
    assert not shm.exists()


def test_idle_grace_ignores_shm_and_wal_mtime(tmp_path, monkeypatch):
    """A daemon restart touches -shm on every database it opens; that touch
    is not project activity and must not keep idle groups alive forever."""
    import os

    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    monkeypatch.setenv("CODESEXTANT_CACHE_IDLE_GRACE_DAYS", "14")
    monkeypatch.setenv("CODESEXTANT_CACHE_MAX_BYTES", str(10 * 1024 ** 3))
    repo, db_file = _write_sqlite_project(storage, home, "stale-idle")
    old = time.time() - 20 * 86400
    os.utime(db_file, (old, old))
    shm = Path(f"{db_file}-shm")
    shm.write_bytes(b"")

    report = cache_gc.prune()

    action = _project_action(report, storage.project_key(str(repo)))
    assert action["reason"] == "idle-present"
    assert action["status"] == "deleted", action
    assert not db_file.exists()
