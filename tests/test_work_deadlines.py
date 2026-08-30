"""Deadlines must bound queued and active heavy work without polling."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlparse

import pytest
from conftest import wait_until


def test_queued_owner_deadline_removes_it_from_lane():
    from codesextant import work_coordinator as wc

    coordinator = wc.HeavyWorkCoordinator(queue_capacity=4)
    started = threading.Event()
    release = threading.Event()

    def blocking():
        started.set()
        release.wait(2)
        return "leader"

    with ThreadPoolExecutor(max_workers=2) as pool:
        leader = pool.submit(coordinator.run, "active", blocking, label="active")
        assert started.wait(1)
        with pytest.raises(wc.HeavyWorkDeadlineExceeded):
            coordinator.run(
                "queued",
                lambda: "must-not-run",
                label="queued",
                deadline=time.monotonic() + 0.05,
            )
        assert coordinator.snapshot()["queued"] == 0
        release.set()
        assert leader.result(timeout=1) == "leader"


def test_expired_follower_detaches_without_cancelling_leader():
    from codesextant import work_coordinator as wc

    coordinator = wc.HeavyWorkCoordinator(queue_capacity=4)
    started = threading.Event()
    release = threading.Event()

    def blocking():
        started.set()
        release.wait(2)
        return "shared"

    with ThreadPoolExecutor(max_workers=2) as pool:
        leader = pool.submit(coordinator.run, "same", blocking, label="leader")
        assert started.wait(1)
        with pytest.raises(wc.HeavyWorkDeadlineExceeded):
            coordinator.run(
                "same",
                lambda: "follower-must-not-run",
                label="follower",
                deadline=time.monotonic() + 0.05,
            )
        assert coordinator.snapshot()["followers"] == 0
        release.set()
        assert leader.result(timeout=1) == "shared"


def test_expired_queued_owner_finishes_for_a_longer_lived_follower():
    from codesextant import work_coordinator as wc

    coordinator = wc.HeavyWorkCoordinator(queue_capacity=4)
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    shared_started = threading.Event()

    def blocker():
        blocker_started.set()
        assert release_blocker.wait(2)
        return "blocker"

    def shared_work():
        shared_started.set()
        return "shared"

    with ThreadPoolExecutor(max_workers=3) as pool:
        active = pool.submit(coordinator.run, "active", blocker, label="active")
        assert blocker_started.wait(1)
        owner = pool.submit(
            coordinator.run,
            "same",
            shared_work,
            label="owner",
            deadline=time.monotonic() + 0.2,
        )
        wait_until(lambda: coordinator.snapshot()["queued"] == 1, timeout=1.0,
                   message="the owner job never reached the queue")
        follower = pool.submit(
            coordinator.run,
            "same",
            lambda: "must-not-run",
            label="follower",
            deadline=time.monotonic() + 1.0,
        )
        # Two separate jobs, and only one of them is a sleep's to do. The follower
        # joining is a state to observe; the owner's 0.2s deadline expiring while it
        # is still queued is the subject of this test, so that one really is time
        # that has to pass.
        wait_until(lambda: coordinator.snapshot()["followers"] >= 1,
                   message="the follower never joined the queued owner")
        time.sleep(0.25)
        release_blocker.set()

        assert active.result(timeout=1) == "blocker"
        assert follower.result(timeout=1) == "shared"
        with pytest.raises(wc.HeavyWorkDeadlineExceeded):
            owner.result(timeout=1)
        assert shared_started.is_set()


def test_active_owner_deadline_does_not_cancel_longer_lived_follower():
    from codesextant import work_coordinator as wc

    coordinator = wc.HeavyWorkCoordinator(queue_capacity=4)
    started = threading.Event()
    original_deadline = time.monotonic() + 0.15

    def shared_work():
        started.set()
        time.sleep(0.25)
        wc.cancellation_point()
        return "shared"

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(
            coordinator.run,
            "same",
            shared_work,
            label="owner",
            deadline=original_deadline,
        )
        assert started.wait(1)
        follower = pool.submit(
            coordinator.run,
            "same",
            lambda: "must-not-run",
            label="follower",
            deadline=time.monotonic() + 1.0,
        )

        assert follower.result(timeout=1) == "shared"
        with pytest.raises(wc.HeavyWorkDeadlineExceeded):
            owner.result(timeout=1)


def test_global_gate_deadline_removes_waiter():
    from codesextant import work_coordinator as wc

    sharded = wc.ShardedHeavyWork(global_capacity=1)
    started = threading.Event()
    release = threading.Event()

    def blocking():
        started.set()
        release.wait(2)
        return "first"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            sharded.run, "a", blocking, label="a", shard="a"
        )
        assert started.wait(1)
        with pytest.raises(wc.HeavyWorkDeadlineExceeded):
            sharded.run(
                "b",
                lambda: "must-not-run",
                label="b",
                shard="b",
                deadline=time.monotonic() + 0.05,
            )
        assert sharded.snapshot()["global_waiting"] == 0
        release.set()
        assert first.result(timeout=1) == "first"


def test_project_work_probe_tracks_active_route():
    from codesextant import work_coordinator as wc

    sharded = wc.ShardedHeavyWork(global_capacity=1)
    started = threading.Event()
    release = threading.Event()

    def blocking():
        started.set()
        assert release.wait(2)
        return "done"

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(
            sharded.run,
            "reindex",
            blocking,
            label="/reindex",
            shard="repo",
        )
        assert started.wait(1)
        assert sharded.has_work(shard="repo", label="/reindex") is True
        assert sharded.has_work(shard="other", label="/reindex") is False
        release.set()
        assert running.result(timeout=1) == "done"

    assert sharded.has_work(shard="repo", label="/reindex") is False


def test_daemon_worker_uses_the_single_flight_shared_deadline(
        tmp_path, monkeypatch):
    from codesextant import daemon
    from codesextant import work_coordinator as wc

    monkeypatch.setenv("CODESEXTANT_ROUTE_WORKER_PROCESS", "1")
    monkeypatch.setattr(
        daemon,
        "_HEAVY_COORDINATOR",
        wc.ShardedHeavyWork(global_capacity=1),
    )
    worker_started = threading.Event()
    original_deadline = time.monotonic() + 0.2

    def fake_worker(_method, _target, _body, *, deadline,
                    deadline_provider, child_deadline):
        assert deadline == original_deadline
        assert child_deadline > deadline
        worker_started.set()
        time.sleep(0.3)
        assert deadline_provider() > time.monotonic()
        return 200, {"shared": True}

    monkeypatch.setattr(daemon.worker_process, "run_route", fake_worker)
    parsed = urlparse("/get_map?project=" + quote(str(tmp_path), safe=""))
    handler = daemon._ROUTES_GET["/get_map"]

    def call(deadline):
        return daemon._execute_route(
            "/get_map", handler, parsed, None, deadline=deadline)

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(call, original_deadline)
        # Admission and thread scheduling can exceed 1s on a loaded Windows
        # desktop; this bound only waits for the fake worker hook to fire.
        assert worker_started.wait(5)
        follower = pool.submit(call, time.monotonic() + 2.0)

        assert follower.result(timeout=5) == (200, {"shared": True})
        with pytest.raises(daemon._HttpError) as expired:
            owner.result(timeout=5)
        assert expired.value.code == 504


def test_client_sends_relative_deadline_for_heavy_requests(tmp_path, monkeypatch):
    from codesextant import client

    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"count":0}'

    def capture(request, *, timeout):
        seen.append((request, timeout))
        return Response()

    monkeypatch.setenv("CODESEXTANT_INTERACTIVE_TIMEOUT_SEC", "12")
    monkeypatch.setattr(client.urllib.request, "urlopen", capture)
    api = client.CodesextantClient(project=str(tmp_path), port=18833, timeout=2)

    assert api.get_map() == {"count": 0}
    request, socket_timeout = seen[0]
    assert socket_timeout == 12
    assert 10_000 <= int(request.get_header("X-codesextant-timeout-ms")) <= 12_000


def test_active_work_arms_one_hard_timeout_and_cancels_it_on_finish():
    from codesextant import work_coordinator as wc

    timers = []
    fired = []

    class Timer:
        def __init__(self, delay, callback):
            self.delay = delay
            self.callback = callback
            self.cancelled = False
            self.daemon = False
            timers.append(self)

        def start(self):
            pass

        def cancel(self):
            self.cancelled = True

    sharded = wc.ShardedHeavyWork(
        global_capacity=1,
        hard_timeout_sec=30,
        hard_timeout_callback=lambda label: fired.append(label),
        timer_factory=Timer,
    )

    assert sharded.run("fast", lambda: 7, label="fast", shard="repo") == 7
    assert len(timers) == 1
    assert timers[0].cancelled is True
    timers[0].callback()
    assert fired == []
