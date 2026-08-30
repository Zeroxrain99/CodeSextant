from __future__ import annotations

import multiprocessing
import os
import time
from pathlib import Path

import pytest


def _hold_project_store(home: str, repo: str, ready, release) -> None:
    os.environ["CODESEXTANT_HOME"] = home
    from codesextant import storage

    with storage.ProjectStore.open(repo):
        ready.wait(timeout=10)
        release.wait(timeout=10)


def _crash_with_project_store(home: str, repo: str, ready) -> None:
    os.environ["CODESEXTANT_HOME"] = home
    from codesextant import storage

    store = storage.ProjectStore.open(repo)
    ready.wait(timeout=10)
    assert store.conn is not None
    os._exit(0)


def _create_index(home: Path, repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))
    from codesextant import storage

    with storage.ProjectStore.open(str(repo)) as store:
        store.store_file_index("sample.py", "digest", [], time.time())


def _quota_forces_prune(home: Path, monkeypatch) -> None:
    from codesextant import cache_gc

    managed = cache_gc.inventory()["managed_bytes"]
    assert managed > 1
    monkeypatch.setenv("CODESEXTANT_CACHE_MAX_BYTES", str(managed - 1))
    monkeypatch.setenv("CODESEXTANT_CACHE_TARGET_RATIO", "0.5")


def _write_orphaned_holder(
        root: Path, project_key: str, serial: int) -> Path:
    marker = root / (
        f"{project_key}.holder.{10_000 + serial}.{20_000 + serial}."
        f"{serial:032x}.lock"
    )
    marker.write_bytes(b"\0")
    return marker


def test_multiple_shared_leases_block_exclusive_until_all_close(
        tmp_path: Path) -> None:
    from codesextant import cache_lease

    project_key = "a" * 40
    first = cache_lease.acquire_shared(project_key, home=tmp_path)
    second = cache_lease.acquire_shared(project_key, home=tmp_path)
    try:
        assert cache_lease.try_acquire_exclusive(
            project_key, home=tmp_path) is None
        first.close()
        assert cache_lease.try_acquire_exclusive(
            project_key, home=tmp_path) is None
        second.close()
        exclusive = cache_lease.try_acquire_exclusive(
            project_key, home=tmp_path)
        assert exclusive is not None
        exclusive.close()
    finally:
        first.close()
        second.close()


def test_shared_acquire_reaps_repeated_crashed_and_timed_out_holders(
        tmp_path: Path) -> None:
    from codesextant import cache_lease

    project_key = "9" * 40
    root = cache_lease.lease_root(tmp_path)
    active = cache_lease.acquire_shared(project_key, home=tmp_path)
    try:
        for round_index in range(32):
            crashed = _write_orphaned_holder(
                root, project_key, round_index * 2)
            timed_out = _write_orphaned_holder(
                root, project_key, round_index * 2 + 1)

            newcomer = cache_lease.acquire_shared(project_key, home=tmp_path)
            try:
                assert set(root.glob(f"{project_key}.holder.*.lock")) == {
                    active.marker,
                    newcomer.marker,
                }
                assert active.marker.exists()
                assert not crashed.exists()
                assert not timed_out.exists()
            finally:
                newcomer.close()
    finally:
        active.close()


def test_project_store_in_other_process_blocks_prune(
        tmp_path: Path, monkeypatch) -> None:
    from codesextant import cache_gc, storage

    home = tmp_path / "state"
    repo = tmp_path / "repo"
    repo.mkdir()
    _create_index(home, repo, monkeypatch)
    _quota_forces_prune(home, monkeypatch)

    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Barrier(3)
    release = ctx.Event()
    processes = [
        ctx.Process(
            target=_hold_project_store,
            args=(str(home), str(repo), ready, release),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    try:
        ready.wait(timeout=10)
        report = cache_gc.prune()
        action = next(
            item for item in report["projects"]
            if item["project_key"] == storage.project_key(str(repo))
        )
        assert action["status"] == "skipped"
        assert action["reason"] == "active-project-lease"
        assert storage.db_path_for(str(repo)).exists()
    finally:
        release.set()
        for process in processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
    assert [process.exitcode for process in processes] == [0, 0]

    report = cache_gc.prune()
    action = next(
        item for item in report["projects"]
        if item["project_key"] == storage.project_key(str(repo))
    )
    assert action["status"] == "deleted"
    assert not storage.db_path_for(str(repo)).exists()


def test_crashed_project_store_marker_is_reaped_before_prune(
        tmp_path: Path, monkeypatch) -> None:
    from codesextant import cache_gc, cache_lease, storage

    home = tmp_path / "state"
    repo = tmp_path / "repo"
    repo.mkdir()
    _create_index(home, repo, monkeypatch)
    _quota_forces_prune(home, monkeypatch)

    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Barrier(2)
    process = ctx.Process(
        target=_crash_with_project_store,
        args=(str(home), str(repo), ready),
    )
    process.start()
    ready.wait(timeout=10)
    process.join(timeout=10)
    assert process.exitcode == 0
    assert list(cache_lease.lease_root(home).glob("*.holder.*.lock"))

    report = cache_gc.prune()

    action = next(
        item for item in report["projects"]
        if item["project_key"] == storage.project_key(str(repo))
    )
    assert action["status"] == "deleted"
    assert not list(cache_lease.lease_root(home).glob("*.holder.*.lock"))


def test_unknown_project_lease_marker_fails_closed(
        tmp_path: Path, monkeypatch) -> None:
    from codesextant import cache_gc, cache_lease, storage

    home = tmp_path / "state"
    repo = tmp_path / "repo"
    repo.mkdir()
    _create_index(home, repo, monkeypatch)
    _quota_forces_prune(home, monkeypatch)
    project_key = storage.project_key(str(repo))
    root = cache_lease.lease_root(home)
    root.mkdir(parents=True, exist_ok=True)
    unknown = root / f"{project_key}.holder.future.lock"
    unknown.write_bytes(b"\0")
    stale = _write_orphaned_holder(root, project_key, 71)

    with pytest.raises(cache_lease.LeaseUnsafeError):
        cache_lease.acquire_shared(project_key, home=home)
    assert unknown.exists()
    assert stale.exists()

    report = cache_gc.prune()

    action = next(
        item for item in report["projects"]
        if item["project_key"] == project_key
    )
    assert action["status"] == "failed"
    assert action["reason"] == "unsafe-project-lease"
    assert storage.db_path_for(str(repo)).exists()


def test_hardlinked_holder_marker_fails_closed(
        tmp_path: Path) -> None:
    from codesextant import cache_lease

    project_key = "b" * 40
    root = cache_lease.lease_root(tmp_path)
    root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.lock"
    outside.write_bytes(b"\0")
    marker = root / (
        f"{project_key}.holder.123.456."
        f"{'c' * 32}.lock"
    )
    try:
        os.link(outside, marker)
    except OSError as exc:
        pytest.skip(f"hard links unavailable: {exc}")

    with pytest.raises(cache_lease.LeaseUnsafeError):
        cache_lease.acquire_shared(project_key, home=tmp_path)
    with pytest.raises(cache_lease.LeaseUnsafeError):
        cache_lease.try_acquire_exclusive(project_key, home=tmp_path)
    assert outside.exists()
    assert marker.exists()


def test_symlinked_holder_marker_fails_closed(tmp_path: Path) -> None:
    from codesextant import cache_lease

    project_key = "d" * 40
    root = cache_lease.lease_root(tmp_path)
    root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.lock"
    outside.write_bytes(b"\0")
    marker = root / (
        f"{project_key}.holder.123.456."
        f"{'e' * 32}.lock"
    )
    try:
        marker.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symbolic links unavailable: {exc}")

    with pytest.raises(cache_lease.LeaseUnsafeError):
        cache_lease.acquire_shared(project_key, home=tmp_path)
    with pytest.raises(cache_lease.LeaseUnsafeError):
        cache_lease.try_acquire_exclusive(project_key, home=tmp_path)
    assert outside.exists()
    assert marker.is_symlink()


def test_snapshot_io_holds_a_project_lease(
        tmp_path: Path, monkeypatch) -> None:
    from codesextant import cache_lease, storage

    project_key = "f" * 40
    db_file = tmp_path / f"{project_key}.db"
    db_file.write_bytes(b"database-placeholder")
    original_replace = storage.os.replace
    replace_checks = 0

    def checked_replace(source, target):
        nonlocal replace_checks
        replace_checks += 1
        assert cache_lease.try_acquire_exclusive(
            project_key, home=tmp_path) is None
        return original_replace(source, target)

    monkeypatch.setattr(storage.os, "replace", checked_replace)
    storage.write_symbol_snapshot(db_file, (1, 2, 3), [{"name": "sample"}])
    storage.write_map_snapshot(db_file, "digest", {"nodes": []})
    assert replace_checks == 2

    original_load = storage.json.load

    def checked_load(handle):
        assert cache_lease.try_acquire_exclusive(
            project_key, home=tmp_path) is None
        return original_load(handle)

    monkeypatch.setattr(storage.json, "load", checked_load)
    assert storage.load_map_snapshot(db_file, "digest") == {"nodes": []}

    exclusive = cache_lease.try_acquire_exclusive(
        project_key, home=tmp_path)
    assert exclusive is not None
    exclusive.close()


def test_project_store_setup_failure_releases_connection_and_lease(
        tmp_path: Path, monkeypatch) -> None:
    from codesextant import cache_lease, storage

    home = tmp_path / "state"
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("CODESEXTANT_HOME", str(home))

    def fail_pragmas(_connection) -> None:
        raise RuntimeError("injected setup failure")

    monkeypatch.setattr(storage, "apply_connection_pragmas", fail_pragmas)
    with pytest.raises(RuntimeError, match="injected setup failure"):
        storage.ProjectStore.open(str(repo))

    project_key = storage.project_key(str(repo))
    assert not list(
        cache_lease.lease_root(home).glob(f"{project_key}.holder.*.lock")
    )
    db_file = storage.db_path_for(str(repo))
    assert db_file.exists()
    db_file.unlink()
