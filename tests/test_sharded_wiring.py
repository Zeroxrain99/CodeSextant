"""Every heavy producer must share one admission authority.

Sharding the HTTP routes without moving the watcher would split admission into
two coordinators that cannot see each other: the watcher's reindex would escape
the global concurrency budget, and — worse — it would stop coalescing with an
HTTP ``/reindex`` for the same repository, so one project could run two full
reindexes at once.  That is exactly the contention the 2026-07-16 work removed.
"""
from __future__ import annotations

import logging
import threading
import time

import pytest

from codesextant import daemon, watcher
from codesextant import work_coordinator as wc


def test_no_second_admission_authority_exists():
    """Remove the footgun: one shared object, so nobody can pick the wrong one."""
    assert daemon._HEAVY_COORDINATOR is wc.SHARED_SHARDED
    assert not hasattr(wc, "SHARED_COORDINATOR"), (
        "the pre-sharding global singleton still exists; a producer wired to it "
        "would escape both the global cap and cross-producer single-flight")


def test_watcher_reindex_is_admitted_through_the_sharded_lane(monkeypatch, tmp_path):
    """The watcher's flush must go through the shared sharded coordinator."""
    seen = []

    class CoordinatorProbe:
        def run(self, key, work, *, label, shard=None):
            seen.append((label, shard))
            return {"indexed": 1, "skipped": 0, "removed": 0}

    monkeypatch.setattr(wc, "SHARED_SHARDED", CoordinatorProbe())
    monkeypatch.setattr(watcher.engine, "index_project", lambda _p: {})

    repo = tmp_path / "repo"
    repo.mkdir()
    mgr = watcher._ProjectWatch(str(repo), logging.getLogger("test-watcher"))
    mgr._pending.add(str(repo / "a.py"))
    mgr._flush()

    assert len(seen) == 1, "watcher did not go through the shared coordinator"
    label, shard = seen[0]
    assert label == "watcher/reindex"
    assert shard, "watcher submitted no shard; it would land in the catch-all lane"


def test_watcher_reindex_shares_the_project_lane_with_http():
    """Same repository ⇒ same lane, so the two producers serialize, not collide."""
    sharded = wc.ShardedHeavyWork(global_capacity=4)
    live = 0
    peak = 0
    lock = threading.Lock()

    def job():
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.05)
        with lock:
            live -= 1
        return True

    repo = "E:/same-repo"
    threads = [
        threading.Thread(target=lambda i=i: sharded.run(
            ("/reindex", repo, str(i)), job,
            label="watcher/reindex" if i else "/reindex", shard=repo))
        for i in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert peak == 1, (
        "watcher and HTTP reindex ran concurrently on one repository")


def test_capacities_accept_explicit_zero_without_falling_back(monkeypatch):
    """A caller passing 0 must not silently inherit the environment default."""
    monkeypatch.setenv("CODESEXTANT_HEAVY_GLOBAL_CAP", "7")
    monkeypatch.setenv("CODESEXTANT_HEAVY_QUEUE_CAP", "9")

    sharded = wc.ShardedHeavyWork(global_capacity=0, shard_queue_capacity=0)
    snap = sharded.snapshot()
    assert snap["global_capacity"] == 1, "0 fell through to the env default"
    assert snap["queue_capacity"] == 1, "0 fell through to the env default"

    inherited = wc.ShardedHeavyWork()
    assert inherited.snapshot()["global_capacity"] == 7


def test_throttling_is_observable(monkeypatch):
    """Operators tuning the global cap need evidence that it actually binds."""
    sharded = wc.ShardedHeavyWork(global_capacity=1)
    release = threading.Event()
    started = threading.Event()

    def blocker():
        started.set()
        release.wait(timeout=5)
        return True

    holder = threading.Thread(target=lambda: sharded.run(
        ("k", "a", ""), blocker, label="/get_map", shard="E:/a"))
    holder.start()
    assert started.wait(timeout=5)

    waiter = threading.Thread(target=lambda: sharded.run(
        ("k", "b", ""), lambda: True, label="/impact", shard="E:/b"))
    waiter.start()
    time.sleep(0.2)

    stats = sharded.snapshot()
    assert stats["global_waiting"] >= 1, (
        "a request blocked purely by the global cap is invisible in telemetry")

    release.set()
    holder.join(timeout=5)
    waiter.join(timeout=5)
    assert sharded.snapshot()["global_throttled_total"] >= 1, (
        "no cumulative counter of cap-induced waits")


def test_admission_log_reaches_the_daemon_log_handler():
    """Observability must exist in the log file, not only in the source.

    A sibling logger (``codesextant.admission``) has no handler of its own, so
    every admission line would be silently dropped while the source still looks
    instrumented.  This pins the parent-child relationship that makes the lines
    actually land in daemon.log.
    """
    from codesextant import work_coordinator as mod

    assert mod._log.name.startswith("codesextant.daemon."), (
        f"admission logger {mod._log.name!r} is not a child of the daemon "
        "logger; its records will never reach daemon.log")

    daemon_logger = logging.getLogger("codesextant.daemon")
    captured: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record):
            captured.append(record)

    handler = Capture()
    daemon_logger.addHandler(handler)
    previous_level = daemon_logger.level
    daemon_logger.setLevel(logging.INFO)
    try:
        sharded = wc.ShardedHeavyWork(global_capacity=1)
        sharded._slow_log_sec = 0.0  # log every completion for the assertion
        sharded.run(("k", "p", ""), lambda: "ok", label="/get_map", shard="E:/p")
    finally:
        daemon_logger.removeHandler(handler)
        daemon_logger.setLevel(previous_level)

    assert any("/get_map" in r.getMessage() for r in captured), (
        "no admission record propagated to the daemon logger")


@pytest.mark.parametrize("shard", ["", None])
def test_projectless_requests_still_admitted(shard):
    """Endpoints without a project must not crash the shard lookup."""
    sharded = wc.ShardedHeavyWork(global_capacity=2)
    assert sharded.run(("k", "", ""), lambda: "ok",
                       label="/links", shard=shard) == "ok"
