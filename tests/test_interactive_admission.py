"""Interactive admission must stay responsive without starving maintenance."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from codesextant import work_coordinator as wc


def _wait_for(predicate, message: str, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        remaining = deadline - time.monotonic()
        assert remaining > 0, message
        threading.Event().wait(min(0.01, remaining))


def test_default_admission_topology_reserves_three_interactive_slots(
        monkeypatch) -> None:
    monkeypatch.delenv("CODESEXTANT_HEAVY_GLOBAL_CAP", raising=False)
    monkeypatch.delenv("CODESEXTANT_INTERACTIVE_GLOBAL_RESERVE", raising=False)
    sharded = wc.ShardedHeavyWork(hard_timeout_sec=0)

    snapshot = sharded.snapshot()
    assert snapshot["global_capacity"] == 4
    assert snapshot["interactive_global_reserve"] == 3
    assert snapshot["interactive_lane_capacity"] == 3
    assert snapshot["gate"]["interactive_capacity"] == 3
    assert snapshot["gate"]["noninteractive_capacity"] == 1


def test_same_project_runs_three_distinct_interactive_owners() -> None:
    sharded = wc.ShardedHeavyWork(
        global_capacity=4,
        interactive_global_reserve=3,
        hard_timeout_sec=0,
    )
    started = [threading.Event() for _ in range(3)]
    fourth_started = threading.Event()
    release = threading.Event()

    def held_work(index):
        started[index].set()
        assert release.wait(2)
        return index

    with ThreadPoolExecutor(max_workers=4) as pool:
        owners = [
            pool.submit(
                sharded.run, ("interactive", index),
                lambda index=index: held_work(index),
                label=("/get_map", "/references", "/impact")[index],
                shard="E:/same-project",
                priority="interactive",
            )
            for index in range(3)
        ]
        fourth = None
        try:
            assert all(event.wait(0.5) for event in started), (
                "same-project interactive work was still serialized"
            )
            snapshot = sharded.snapshot()
            assert len(snapshot["active_jobs"]) == 3
            fourth = pool.submit(
                sharded.run, "interactive-fourth", fourth_started.set,
                label="/get_symbols",
                shard="E:/same-project",
                priority="interactive",
            )
            assert not fourth_started.wait(0.2), (
                "same-project interactive work exceeded its three-owner bound"
            )
        finally:
            release.set()
        assert [owner.result(timeout=1) for owner in owners] == [0, 1, 2]
        assert fourth is not None
        assert fourth.result(timeout=1) is None
        assert fourth_started.is_set()


def test_same_project_interactive_identical_key_remains_single_flight() -> None:
    sharded = wc.ShardedHeavyWork(
        global_capacity=4,
        interactive_global_reserve=3,
        shard_follower_capacity=2,
        hard_timeout_sec=0,
    )
    entered = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def work():
        nonlocal calls
        with calls_lock:
            calls += 1
        entered.set()
        assert release.wait(2)
        return "shared"

    with ThreadPoolExecutor(max_workers=3) as pool:
        leader = pool.submit(
            sharded.run, "same-key", work,
            label="/get_map", shard="E:/same-project", priority="interactive",
        )
        assert entered.wait(1)
        followers = [
            pool.submit(
                sharded.run, "same-key", work,
                label="/get_map", shard="E:/same-project",
                priority="interactive",
            )
            for _ in range(2)
        ]
        try:
            _wait_for(
                lambda: sharded.snapshot()["followers"] == 2,
                "identical interactive requests did not join the leader",
            )
        finally:
            release.set()
        assert leader.result(timeout=1) == "shared"
        assert [future.result(timeout=1) for future in followers] == [
            "shared", "shared"
        ]

    assert calls == 1
    assert sharded.snapshot()["lanes"] == 0


def test_active_batch_same_shard_does_not_block_interactive() -> None:
    sharded = wc.ShardedHeavyWork(
        global_capacity=2, interactive_global_reserve=1)
    batch_started = threading.Event()
    release_batch = threading.Event()
    interactive_started = threading.Event()

    def batch() -> str:
        batch_started.set()
        assert release_batch.wait(2)
        return "batch"

    def interactive() -> str:
        interactive_started.set()
        return "interactive"

    with ThreadPoolExecutor(max_workers=2) as pool:
        batch_result = pool.submit(
            sharded.run,
            ("reindex", "repo"),
            batch,
            label="watcher/reindex",
            shard="E:/repo",
            priority="batch",
        )
        assert batch_started.wait(1)
        interactive_result = pool.submit(
            sharded.run,
            ("map", "repo"),
            interactive,
            label="/get_map",
            shard="E:/repo",
            priority="interactive",
        )
        try:
            assert interactive_started.wait(0.5), (
                "an active batch job occupied the same project's interactive lane"
            )
            assert interactive_result.result(timeout=1) == "interactive"
        finally:
            release_batch.set()
        assert batch_result.result(timeout=1) == "batch"


def test_two_batch_jobs_cannot_consume_the_interactive_reserve() -> None:
    sharded = wc.ShardedHeavyWork(
        global_capacity=2, interactive_global_reserve=1)
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    release_second = threading.Event()
    interactive_started = threading.Event()
    release_interactive = threading.Event()

    def first_batch() -> None:
        first_started.set()
        assert release_first.wait(2)

    def second_batch() -> None:
        second_started.set()
        assert release_second.wait(2)

    def interactive_job() -> None:
        interactive_started.set()
        assert release_interactive.wait(2)

    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(
            sharded.run, "batch-a", first_batch,
            label="reindex", shard="E:/a", priority="batch",
        )
        assert first_started.wait(1)
        second = pool.submit(
            sharded.run, "batch-b", second_batch,
            label="reindex", shard="E:/b", priority="batch",
        )
        interactive = pool.submit(
            sharded.run, "interactive", interactive_job,
            label="/impact", shard="E:/c", priority="interactive",
        )
        try:
            assert not second_started.wait(0.2), (
                "a second batch job consumed the interactive reserve"
            )
            assert interactive_started.wait(0.5), (
                "interactive work could not use its reserved slot"
            )
            gate = sharded.snapshot()["gate"]
            assert gate["reserve"] == 1
            assert gate["in_use_by_priority"] == {
                "background": 0,
                "batch": 1,
                "interactive": 1,
            }
            release_first.set()
            assert second_started.wait(0.5)
        finally:
            release_first.set()
            release_second.set()
            release_interactive.set()
        first.result(timeout=1)
        second.result(timeout=1)
        interactive.result(timeout=1)


def test_interactive_waits_only_for_the_interactive_partition() -> None:
    sharded = wc.ShardedHeavyWork(
        global_capacity=2, interactive_global_reserve=1)
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()

    def first_interactive() -> None:
        first_started.set()
        assert release_first.wait(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            sharded.run, "interactive-a", first_interactive,
            label="/get_map", shard="E:/a", priority="interactive",
        )
        assert first_started.wait(1)
        second = pool.submit(
            sharded.run, "interactive-b", second_started.set,
            label="/references", shard="E:/b", priority="interactive",
        )
        try:
            assert not second_started.wait(0.2), (
                "interactive work escaped its bounded partition"
            )
            release_first.set()
            assert second_started.wait(0.5)
        finally:
            release_first.set()
        first.result(timeout=1)
        second.result(timeout=1)


def test_background_eventually_uses_the_noninteractive_partition() -> None:
    sharded = wc.ShardedHeavyWork(
        global_capacity=2, interactive_global_reserve=1)
    batch_started = threading.Event()
    release_batch = threading.Event()
    background_started = threading.Event()
    interactive_started = threading.Event()
    release_interactive = threading.Event()

    def batch() -> None:
        batch_started.set()
        assert release_batch.wait(2)

    def interactive() -> None:
        interactive_started.set()
        assert release_interactive.wait(2)

    with ThreadPoolExecutor(max_workers=3) as pool:
        batch_result = pool.submit(
            sharded.run, "batch", batch,
            label="reindex", shard="E:/a", priority="batch",
        )
        assert batch_started.wait(1)
        background_result = pool.submit(
            sharded.run, "background", background_started.set,
            label="watcher/reindex", shard="E:/b", priority="background",
        )
        interactive_result = pool.submit(
            sharded.run, "interactive", interactive,
            label="/get_map", shard="E:/c", priority="interactive",
        )
        try:
            assert interactive_started.wait(0.5)
            assert not background_started.wait(0.2)
            release_batch.set()
            assert background_started.wait(0.5), (
                "background work did not inherit the released noninteractive slot"
            )
            assert not release_interactive.is_set(), (
                "the test released interactive work before background admission"
            )
        finally:
            release_batch.set()
            release_interactive.set()
        batch_result.result(timeout=1)
        background_result.result(timeout=1)
        interactive_result.result(timeout=1)


def test_snapshot_jobs_are_bounded_and_path_safe() -> None:
    sharded = wc.ShardedHeavyWork(
        global_capacity=2, interactive_global_reserve=1)
    shard = "E:/private/customer/repository"
    batch_started = threading.Event()
    interactive_started = threading.Event()
    release_batch = threading.Event()
    release_interactive = threading.Event()

    def batch() -> None:
        batch_started.set()
        assert release_batch.wait(2)

    def interactive() -> None:
        interactive_started.set()
        assert release_interactive.wait(2)

    with ThreadPoolExecutor(max_workers=3) as pool:
        batch_result = pool.submit(
            sharded.run, "same-key", batch,
            label="watcher/reindex", shard=shard, priority="batch",
            request_identity=shard,
        )
        assert batch_started.wait(1)
        interactive_result = pool.submit(
            sharded.run, "same-key", interactive,
            label="/get_map", shard=shard, priority="interactive",
        )
        try:
            assert interactive_started.wait(0.5), (
                "same-key work coalesced across independent admission lanes"
            )
            queued_result = pool.submit(
                sharded.run, "queued-batch", lambda: "queued",
                label="reindex", shard=shard, priority="batch",
            )
            _wait_for(
                lambda: sharded.snapshot()["queued"] == 1,
                "batch work never appeared in lane telemetry",
            )
            snap = sharded.snapshot()
            required = {
                "label",
                "lane",
                "priority",
                "age_sec",
                "owner_thread_id",
                "owner_identity",
                "request_identity",
                "shard_digest",
                "blocking_reason",
            }
            assert len(snap["active_jobs"]) == 2
            assert len(snap["queued_jobs"]) == 1
            assert len(snap["active_jobs"]) <= snap["job_telemetry_limit"]
            assert len(snap["queued_jobs"]) <= snap["job_telemetry_limit"]
            assert all(required <= job.keys() for job in snap["active_jobs"])
            assert all(required <= job.keys() for job in snap["queued_jobs"])
            assert {job["lane"] for job in snap["active_jobs"]} == {
                "batch", "interactive"
            }
            assert len({job["shard_digest"] for job in snap["active_jobs"]}) == 1
            batch_job = next(
                job for job in snap["active_jobs"] if job["priority"] == "batch"
            )
            assert batch_job["request_identity"].startswith("request:")
            assert all(
                len(job["shard_digest"]) == 16
                and set(job["shard_digest"]) <= set("0123456789abcdef")
                for job in snap["active_jobs"] + snap["queued_jobs"]
            )
            assert all(job["blocking_reason"] for job in snap["queued_jobs"])
            assert snap["gate"]["partition_mode"] == "strict"
            assert snap["gate"]["interactive_capacity"] == 1
            assert snap["gate"]["noninteractive_capacity"] == 1
            encoded = json.dumps(snap).lower()
            assert "private" not in encoded
            assert "customer" not in encoded
            assert "e:/" not in encoded
        finally:
            release_batch.set()
            release_interactive.set()
        batch_result.result(timeout=1)
        interactive_result.result(timeout=1)
        assert queued_result.result(timeout=1) == "queued"


def test_completed_project_lanes_are_evicted() -> None:
    sharded = wc.ShardedHeavyWork(
        global_capacity=2,
        interactive_global_reserve=1,
        hard_timeout_sec=0,
    )

    for index in range(32):
        assert sharded.run(
            ("map", index),
            lambda value=index: value,
            label="/get_map",
            shard=f"E:/repo-{index}",
            priority="interactive",
        ) == index

    snapshot = sharded.snapshot()
    assert snapshot["shards"] == 0
    assert snapshot["lanes"] == 0
    assert sharded._shards == {}


def test_lane_lease_prevents_eviction_before_waiter_enters(monkeypatch) -> None:
    sharded = wc.ShardedHeavyWork(
        global_capacity=2,
        interactive_global_reserve=1,
        hard_timeout_sec=0,
    )
    first_started = threading.Event()
    release_first = threading.Event()
    second_acquired = threading.Event()
    allow_second_to_enter = threading.Event()
    acquisition_lock = threading.Lock()
    acquisition_count = 0
    held = {}
    real_acquire = sharded._acquire_lane

    def acquire_then_pause(shard, lane):
        nonlocal acquisition_count
        lane_key, entry = real_acquire(shard, lane)
        with acquisition_lock:
            acquisition_count += 1
            call_number = acquisition_count
        if call_number == 2:
            held.update(lane_key=lane_key, entry=entry)
            second_acquired.set()
            assert allow_second_to_enter.wait(2)
        return lane_key, entry

    def first_work():
        first_started.set()
        assert release_first.wait(2)
        return "first"

    monkeypatch.setattr(sharded, "_acquire_lane", acquire_then_pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            sharded.run, "first", first_work,
            label="/get_map", shard="E:/same", priority="interactive",
        )
        assert first_started.wait(1)
        second = pool.submit(
            sharded.run, "second", lambda: "second",
            label="/impact", shard="E:/same", priority="interactive",
        )
        try:
            assert second_acquired.wait(1)
            release_first.set()
            assert first.result(timeout=1) == "first"
            with sharded._lock:
                assert sharded._shards[held["lane_key"]] is held["entry"]
                assert held["entry"].leases == 1
        finally:
            release_first.set()
            allow_second_to_enter.set()
        assert second.result(timeout=1) == "second"

    assert sharded.snapshot()["lanes"] == 0
