"""Per-project heavy lanes: fairness without raising CPU concurrency.

Measured problem (2026-07-18 production log): a query against a 23-file,
*unindexed* project returned ``count=0 symbols=0`` after **152 seconds**, purely
because it sat behind another project's ``/find_unwired``.  One global FIFO lane
means any repository's expensive job blocks every other repository's cheap one.

Sharding by project fixes the queueing, while a small global slot count keeps
the CPU-contention protection the single lane was introduced for: measured on
this machine, four CPU-bound Python threads finish a fixed workload in 0.64x the
speed of running them one after another, so unbounded concurrency is a
regression, not a win.
"""
from __future__ import annotations

import threading
import time

import pytest

from codesextant import work_coordinator as wc


def _sharded(**kwargs):
    return wc.ShardedHeavyWork(**kwargs)


def test_other_project_is_not_blocked_by_a_slow_project():
    """The production incident, as a regression test."""
    sharded = _sharded(global_capacity=2)
    slow_started = threading.Event()
    release_slow = threading.Event()

    def slow():
        slow_started.set()
        release_slow.wait(timeout=5)
        return "slow"

    slow_thread = threading.Thread(
        target=lambda: sharded.run(("k", "big", ""), slow,
                                   label="/find_unwired", shard="E:/big"))
    slow_thread.start()
    assert slow_started.wait(timeout=5), "slow job never started"

    started = time.monotonic()
    result = sharded.run(("k", "small", ""), lambda: "fast",
                         label="/get_symbols", shard="E:/small")
    elapsed = time.monotonic() - started

    release_slow.set()
    slow_thread.join(timeout=5)

    assert result == "fast"
    assert elapsed < 1.0, (
        f"a different project's cheap query waited {elapsed:.2f}s behind a slow "
        "project; lanes are still shared")


def test_same_project_still_serializes():
    """Within one repository the FIFO protection must survive."""
    sharded = _sharded(global_capacity=4)
    concurrent = []
    lock = threading.Lock()
    live = 0

    def job():
        nonlocal live
        with lock:
            live += 1
            concurrent.append(live)
        time.sleep(0.05)
        with lock:
            live -= 1
        return True

    threads = [
        threading.Thread(target=lambda i=i: sharded.run(
            ("k", "same", str(i)), job, label="/get_map", shard="E:/same"))
        for i in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert max(concurrent) == 1, (
        f"same-project jobs ran {max(concurrent)} at a time; FIFO lane lost")


def test_global_capacity_bounds_total_concurrency():
    """Sharding must not become unbounded parallelism (threads make CPU work slower)."""
    sharded = _sharded(global_capacity=2)
    lock = threading.Lock()
    live = 0
    peak = 0

    def job():
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.08)
        with lock:
            live -= 1
        return True

    threads = [
        threading.Thread(target=lambda i=i: sharded.run(
            ("k", f"p{i}", ""), job, label="/get_map", shard=f"E:/p{i}"))
        for i in range(6)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert peak <= 2, f"global cap breached: {peak} heavy jobs ran at once"


def test_single_flight_still_coalesces_within_a_shard():
    """Identical overlapping requests must keep merging (measured 4x saving)."""
    sharded = _sharded(global_capacity=2)
    runs = []

    def job():
        runs.append(1)
        time.sleep(0.15)
        return "shared"

    results = []
    threads = [
        threading.Thread(target=lambda: results.append(sharded.run(
            ("k", "same", "same-params"), job,
            label="/get_map", shard="E:/same")))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert results == ["shared"] * 4
    assert sum(runs) == 1, f"work ran {sum(runs)} times instead of coalescing"


def test_snapshot_keeps_supervisor_contract():
    """supervisor watches heavy_work.active_for_sec; the keys must not change."""
    sharded = _sharded(global_capacity=2)
    snap = sharded.snapshot()
    for key in ("active", "queued", "followers", "active_for_sec",
                "oldest_queued_for_sec", "queue_capacity", "follower_capacity"):
        assert key in snap, f"missing supervisor telemetry key: {key}"
    assert snap["active"] is None
    assert snap["active_for_sec"] == 0.0


def test_snapshot_reports_the_longest_running_job():
    """Stuck-detection must see the worst offender across all shards."""
    sharded = _sharded(global_capacity=2)
    started = threading.Event()
    release = threading.Event()

    def slow():
        started.set()
        release.wait(timeout=5)
        return True

    t = threading.Thread(target=lambda: sharded.run(
        ("k", "big", ""), slow, label="/find_unwired", shard="E:/big"))
    t.start()
    assert started.wait(timeout=5)
    time.sleep(0.05)

    snap = sharded.snapshot()
    assert snap["active"] == "/find_unwired"
    assert snap["active_for_sec"] > 0
    assert snap["shards"] >= 1

    release.set()
    t.join(timeout=5)


def test_queue_capacity_is_per_shard_and_rejects_overflow():
    sharded = _sharded(global_capacity=1, shard_queue_capacity=1)
    release = threading.Event()
    started = threading.Event()

    def blocker():
        started.set()
        release.wait(timeout=5)
        return True

    t = threading.Thread(target=lambda: sharded.run(
        ("k", "p", "a"), blocker, label="/get_map", shard="E:/p"))
    t.start()
    assert started.wait(timeout=5)

    queued = threading.Thread(target=lambda: sharded.run(
        ("k", "p", "b"), lambda: True, label="/get_map", shard="E:/p"))
    queued.start()
    time.sleep(0.1)

    with pytest.raises(wc.HeavyWorkQueueFull):
        sharded.run(("k", "p", "c"), lambda: True, label="/get_map", shard="E:/p")

    release.set()
    t.join(timeout=5)
    queued.join(timeout=5)


def test_sharding_can_be_disabled(monkeypatch):
    """Escape hatch back to the single global lane."""
    monkeypatch.setenv("CODESEXTANT_HEAVY_SHARDING", "0")
    sharded = _sharded(global_capacity=4)
    lock = threading.Lock()
    live = 0
    peak = 0

    def job():
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.05)
        with lock:
            live -= 1
        return True

    threads = [
        threading.Thread(target=lambda i=i: sharded.run(
            ("k", f"p{i}", ""), job, label="/get_map", shard=f"E:/p{i}"))
        for i in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert peak == 1, "sharding disabled must behave exactly like one global lane"


def test_reentrancy_still_fails_fast():
    """The owner-thread guard from the single lane must survive sharding."""
    sharded = _sharded(global_capacity=2)

    def outer():
        return sharded.run(("k", "p", "inner"), lambda: True,
                           label="/get_map", shard="E:/p")

    with pytest.raises(RuntimeError):
        sharded.run(("k", "p", "inner"), outer, label="/get_map", shard="E:/p")


def test_interactive_work_overtakes_background_in_the_same_project():
    """A full background lane must not make an agent query wait behind maintenance."""
    sharded = _sharded(global_capacity=1, shard_queue_capacity=1)
    active_started = threading.Event()
    release_active = threading.Event()
    order = []

    def active_background():
        active_started.set()
        release_active.wait(timeout=5)
        order.append("active")

    holder = threading.Thread(target=lambda: sharded.run(
        ("k", "p", "active"), active_background,
        label="watcher/reindex", shard="E:/p", priority="background"))
    holder.start()
    assert active_started.wait(timeout=5)

    queued_background = threading.Thread(target=lambda: sharded.run(
        ("k", "p", "queued"), lambda: order.append("background"),
        label="watcher/reindex", shard="E:/p", priority="background"))
    queued_background.start()

    deadline = time.monotonic() + 5
    while sharded.snapshot().get("queued_by_priority", {}).get("background") != 1:
        assert time.monotonic() < deadline, "background job never entered the queue"
        time.sleep(0.01)

    interactive = threading.Thread(target=lambda: sharded.run(
        ("k", "p", "interactive"), lambda: order.append("interactive"),
        label="/get_map", shard="E:/p", priority="interactive"))
    interactive.start()

    deadline = time.monotonic() + 5
    while sharded.snapshot().get("queued_by_priority", {}).get("interactive") != 1:
        assert time.monotonic() < deadline, "interactive reserve was not admitted"
        time.sleep(0.01)

    release_active.set()
    for thread in (holder, interactive, queued_background):
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert order == ["active", "interactive", "background"]


def test_interactive_work_overtakes_background_at_the_global_gate():
    """Background work from other repositories must not monopolize global slots."""
    sharded = _sharded(global_capacity=1)
    active_started = threading.Event()
    release_active = threading.Event()
    order = []

    def active_background():
        active_started.set()
        release_active.wait(timeout=5)
        order.append("active")

    holder = threading.Thread(target=lambda: sharded.run(
        ("k", "a", "active"), active_background,
        label="watcher/reindex", shard="E:/a", priority="background"))
    holder.start()
    assert active_started.wait(timeout=5)

    queued_background = threading.Thread(target=lambda: sharded.run(
        ("k", "b", "queued"), lambda: order.append("background"),
        label="watcher/reindex", shard="E:/b", priority="background"))
    queued_background.start()

    interactive = threading.Thread(target=lambda: sharded.run(
        ("k", "c", "interactive"), lambda: order.append("interactive"),
        label="/get_map", shard="E:/c", priority="interactive"))
    interactive.start()

    deadline = time.monotonic() + 5
    while sharded.snapshot().get("global_waiting") != 2:
        assert time.monotonic() < deadline, "jobs never reached the global gate"
        time.sleep(0.01)

    release_active.set()
    for thread in (holder, interactive, queued_background):
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert order == ["active", "interactive", "background"]
