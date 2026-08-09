"""Concurrency and eviction contracts for on-demand project watchers."""

from __future__ import annotations

import logging
import threading
import time

import pytest


class _FakeTimer:
    created: list[_FakeTimer] = []

    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.cancelled = False
        self.daemon = False
        self.started = False
        self.__class__.created.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


def _indexed_repo(tmp_path, monkeypatch):
    from codesextant import storage

    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    db_file = storage.db_path_for(str(repo))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    db_file.touch()
    return repo


def test_unwatched_lifecycle_state_expires_without_timer_spin(
        tmp_path, monkeypatch):
    from codesextant import watcher

    now = [100.0]
    _FakeTimer.created = []
    monkeypatch.setattr(watcher.threading, "Timer", _FakeTimer)
    manager = watcher.WatchManager(
        logging.getLogger("test"), idle_ttl_sec=10, clock=lambda: now[0]
    )
    project = str(tmp_path / "watch-attach-failed")

    manager.mark_ready(project)
    assert len(_FakeTimer.created) == 1

    now[0] = 111.0
    assert manager.evict_idle() == [manager._absolute(project)]
    assert manager._last_activity == {}
    assert manager._recovery_states == {}
    assert manager._eviction_timer is None
    assert len(_FakeTimer.created) == 1
    manager.stop_all()


def test_recovery_follower_honors_its_own_deadline(tmp_path, monkeypatch):
    from codesextant import watcher, work_coordinator

    repo = _indexed_repo(tmp_path, monkeypatch)
    manager = watcher.WatchManager(logging.getLogger("test"), idle_ttl_sec=0)
    monkeypatch.setattr(manager, "ensure_watch", lambda _repo: True)
    entered = threading.Event()
    release = threading.Event()

    def recover(_repo, *, deadline=None):
        entered.set()
        assert release.wait(2)
        return {"indexed": 0, "skipped": 1, "removed": 0}

    monkeypatch.setattr(manager, "recover", recover)
    leader_errors = []

    def run_leader():
        try:
            manager.ensure_ready(str(repo))
        except BaseException as exc:  # pragma: no cover - assertion reports details
            leader_errors.append(exc)

    leader = threading.Thread(target=run_leader)
    leader.start()
    assert entered.wait(1)
    project_key = manager._normalize(str(repo))
    attempt = manager._recovery_attempts[project_key]

    started = time.monotonic()
    with pytest.raises(work_coordinator.HeavyWorkDeadlineExceeded):
        manager.ensure_ready(
            str(repo), deadline=time.monotonic() + 0.05
        )
    assert time.monotonic() - started < 0.5
    assert attempt.followers == 0

    release.set()
    leader.join(timeout=2)
    assert not leader.is_alive()
    assert leader_errors == []
    manager.stop_all()


def test_recovery_follower_capacity_rejects_without_joining(
        tmp_path, monkeypatch):
    from codesextant import watcher, work_coordinator

    repo = _indexed_repo(tmp_path, monkeypatch)
    monkeypatch.setenv("CODESEXTANT_WATCH_RECOVERY_FOLLOWER_CAP", "1")
    manager = watcher.WatchManager(logging.getLogger("test"), idle_ttl_sec=0)
    monkeypatch.setattr(manager, "ensure_watch", lambda _repo: True)
    entered = threading.Event()
    release = threading.Event()
    follower_waiting = threading.Event()
    real_event = threading.Event

    class TrackingEvent:
        def __init__(self):
            self._event = real_event()

        def set(self):
            return self._event.set()

        def is_set(self):
            return self._event.is_set()

        def wait(self, timeout=None):
            follower_waiting.set()
            return self._event.wait(timeout)

    def recover(_repo, *, deadline=None):
        entered.set()
        assert release.wait(2)
        return {"indexed": 0, "skipped": 1, "removed": 0}

    monkeypatch.setattr(manager, "recover", recover)
    results = []
    errors = []

    def call():
        try:
            results.append(manager.ensure_ready(str(repo)))
        except BaseException as exc:  # pragma: no cover - assertion reports details
            errors.append(exc)

    leader = threading.Thread(target=call)
    follower = threading.Thread(target=call)
    monkeypatch.setattr(watcher.threading, "Event", TrackingEvent)
    leader.start()
    assert entered.wait(1)
    follower.start()
    assert follower_waiting.wait(1)

    project_key = manager._normalize(str(repo))
    attempt = manager._recovery_attempts[project_key]
    assert attempt.followers == 1
    with pytest.raises(work_coordinator.HeavyWorkQueueFull):
        manager.ensure_ready(
            str(repo), deadline=time.monotonic() + 0.05
        )
    assert attempt.followers == 1

    release.set()
    leader.join(timeout=2)
    follower.join(timeout=2)
    assert not leader.is_alive() and not follower.is_alive()
    assert errors == []
    assert len(results) == 2
    assert attempt.followers == 0
    manager.stop_all()


def test_recovery_follower_receives_the_leader_exception(tmp_path, monkeypatch):
    from codesextant import watcher

    repo = _indexed_repo(tmp_path, monkeypatch)
    manager = watcher.WatchManager(logging.getLogger("test"), idle_ttl_sec=0)
    monkeypatch.setattr(manager, "ensure_watch", lambda _repo: True)
    entered = threading.Event()
    release = threading.Event()
    follower_waiting = threading.Event()
    real_event = threading.Event

    class RecoveryFailure(ValueError):
        pass

    class TrackingEvent:
        def __init__(self):
            self._event = real_event()

        def set(self):
            return self._event.set()

        def is_set(self):
            return self._event.is_set()

        def wait(self, timeout=None):
            follower_waiting.set()
            return self._event.wait(timeout)

    def recover(_repo, *, deadline=None):
        entered.set()
        assert release.wait(2)
        raise RecoveryFailure("recovery exploded")

    monkeypatch.setattr(manager, "recover", recover)
    outcomes = {}

    def call(name):
        try:
            manager.ensure_ready(str(repo))
        except BaseException as exc:
            outcomes[name] = exc

    leader = threading.Thread(target=call, args=("leader",))
    follower = threading.Thread(target=call, args=("follower",))
    monkeypatch.setattr(watcher.threading, "Event", TrackingEvent)
    leader.start()
    assert entered.wait(1)
    follower.start()
    assert follower_waiting.wait(1)
    release.set()
    leader.join(timeout=2)
    follower.join(timeout=2)

    assert isinstance(outcomes["leader"], RecoveryFailure)
    assert isinstance(outcomes["follower"], RecoveryFailure)
    assert str(outcomes["follower"]) == "recovery exploded"
    manager.stop_all()


def test_stop_during_watcher_start_never_installs_the_late_watcher(
        tmp_path, monkeypatch):
    from codesextant import watcher

    # Production default is on; force it so ambient CODESEXTANT_WATCH_ENABLED=0
    # cannot skip attach and make start() look like it never ran.
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "1")
    repo = tmp_path / "repo"
    repo.mkdir()
    manager = watcher.WatchManager(logging.getLogger("test"), idle_ttl_sec=0)
    started = threading.Event()
    release = threading.Event()
    stopped = []

    class FakeProjectWatch:
        def __init__(self, repo_path, logger, *, on_activity=None):
            self.repo_path = repo_path

        def start(self):
            started.set()
            assert release.wait(2)

        def stop(self):
            stopped.append(self.repo_path)

    monkeypatch.setattr(watcher, "_ProjectWatch", FakeProjectWatch)
    result = []
    worker = threading.Thread(
        target=lambda: result.append(manager.ensure_watch(str(repo)))
    )
    worker.start()
    assert started.wait(1)
    manager.stop_all()
    release.set()
    worker.join(timeout=2)

    assert result == [False]
    assert manager.watched_snapshot() == ()
    assert stopped == [manager._absolute(str(repo))]


def test_recovery_finishing_after_stop_does_not_restore_manager_state(
        tmp_path, monkeypatch):
    from codesextant import watcher

    repo = _indexed_repo(tmp_path, monkeypatch)
    manager = watcher.WatchManager(logging.getLogger("test"), idle_ttl_sec=0)
    monkeypatch.setattr(manager, "ensure_watch", lambda _repo: True)
    entered = threading.Event()
    release = threading.Event()

    def recover(_repo, *, deadline=None):
        entered.set()
        assert release.wait(2)
        return {"indexed": 0, "skipped": 1, "removed": 0}

    monkeypatch.setattr(manager, "recover", recover)
    worker = threading.Thread(target=lambda: manager.ensure_ready(str(repo)))
    worker.start()
    assert entered.wait(1)
    manager.stop_all()
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert manager._last_activity == {}
    assert manager._recovery_states == {}
    assert manager.watched_snapshot() == ()


def test_expired_busy_watcher_defers_the_next_eviction_check(monkeypatch):
    from codesextant import watcher

    now = [100.0]
    stopped = []
    _FakeTimer.created = []
    monkeypatch.setattr(watcher.threading, "Timer", _FakeTimer)
    manager = watcher.WatchManager(
        logging.getLogger("test"), idle_ttl_sec=10, clock=lambda: now[0]
    )

    class BusyWatch:
        repo_path = "repo"

        def is_quiescent(self):
            return False

        def stop(self):
            stopped.append("repo")

    manager._watches = {"repo": BusyWatch()}
    manager._watched_snapshot = ("repo",)
    manager._last_activity = {"repo": now[0]}
    manager._arm_eviction_locked()

    now[0] = 111.0
    assert manager.evict_idle() == []
    assert manager._last_activity["repo"] == 111.0
    assert _FakeTimer.created[-1].delay == 10.0
    assert stopped == []
    manager.stop_all()
    assert stopped == ["repo"]


def test_project_keys_apply_normcase_after_absolute_normalization(monkeypatch):
    from codesextant import watcher

    calls = []
    monkeypatch.setattr(
        watcher.os.path, "abspath", lambda path: calls.append(("abs", path)) or "C:\\Repo"
    )
    monkeypatch.setattr(
        watcher.os.path, "normcase", lambda path: calls.append(("case", path)) or "c:\\repo"
    )

    assert watcher.WatchManager._normalize("relative") == "c:\\repo"
    assert calls == [("abs", "relative"), ("case", "C:\\Repo")]


def test_recovery_docstring_describes_lazy_first_query_reconciliation():
    from codesextant import watcher

    doc = watcher.WatchManager.recover.__doc__ or ""
    assert "first real query" in doc
    assert "during daemon startup" not in doc


def test_project_watch_stop_waits_for_an_entered_flush(tmp_path, monkeypatch):
    from codesextant import watcher

    repo = tmp_path / "repo"
    repo.mkdir()
    changed = repo / "changed.py"
    entered = threading.Event()
    release = threading.Event()
    stop_started = threading.Event()
    stop_finished = threading.Event()

    def blocked_run(_key, _work, **_kwargs):
        entered.set()
        assert release.wait(2)
        return {"indexed": 1, "skipped": 0, "removed": 0}

    monkeypatch.setattr(
        watcher.work_coordinator.SHARED_SHARDED, "run", blocked_run
    )
    project_watch = watcher._ProjectWatch(
        str(repo), logging.getLogger("test")
    )
    with project_watch._lock:
        project_watch._pending.add(str(changed))
        project_watch._generation += 1

    flush_thread = threading.Thread(target=project_watch._flush)
    flush_thread.start()
    assert entered.wait(1)

    def stop_watch():
        stop_started.set()
        project_watch.stop()
        stop_finished.set()

    stop_thread = threading.Thread(target=stop_watch)
    stop_thread.start()
    try:
        assert stop_started.wait(1)
        assert not stop_finished.wait(0.2), (
            "stop released ownership while an entered flush was still running"
        )
    finally:
        release.set()
        flush_thread.join(timeout=2)
        stop_thread.join(timeout=2)
    assert not flush_thread.is_alive()
    assert not stop_thread.is_alive()
    assert stop_finished.is_set()


def test_project_watch_stop_honors_the_heavy_hard_timeout(
        tmp_path, monkeypatch):
    from codesextant import watcher

    repo = tmp_path / "repo"
    repo.mkdir()
    entered = threading.Event()
    release = threading.Event()
    hard_stops = []

    class HardStopSignal(BaseException):
        pass

    def blocked_run(_key, _work, **_kwargs):
        entered.set()
        assert release.wait(1)
        return {"indexed": 1, "skipped": 0, "removed": 0}

    def hard_stop(label):
        hard_stops.append(label)
        raise HardStopSignal

    monkeypatch.setattr(
        watcher.work_coordinator.SHARED_SHARDED, "run", blocked_run
    )
    monkeypatch.setattr(
        watcher.work_coordinator.SHARED_SHARDED, "_hard_timeout_sec", 0.05
    )
    monkeypatch.setattr(
        watcher.work_coordinator, "fail_fast_stuck_job", hard_stop
    )
    project_watch = watcher._ProjectWatch(
        str(repo), logging.getLogger("test")
    )
    with project_watch._lock:
        project_watch._pending.add(str(repo / "changed.py"))

    flush_thread = threading.Thread(target=project_watch._flush)
    flush_thread.start()
    assert entered.wait(1)
    try:
        with pytest.raises(HardStopSignal):
            project_watch.stop()
    finally:
        release.set()
        flush_thread.join(timeout=2)

    assert hard_stops == ["watcher/shutdown-drain"]
    assert not flush_thread.is_alive()


def test_project_watch_stop_waits_for_all_entered_flushes(
        tmp_path, monkeypatch):
    from codesextant import watcher

    repo = tmp_path / "repo"
    repo.mkdir()
    entered = [threading.Event(), threading.Event()]
    release = [threading.Event(), threading.Event()]
    call_lock = threading.Lock()
    calls = 0

    def blocked_run(_key, _work, **_kwargs):
        nonlocal calls
        with call_lock:
            call_index = calls
            calls += 1
        entered[call_index].set()
        assert release[call_index].wait(2)
        return {"indexed": 1, "skipped": 0, "removed": 0}

    monkeypatch.setattr(
        watcher.work_coordinator.SHARED_SHARDED, "run", blocked_run
    )
    project_watch = watcher._ProjectWatch(
        str(repo), logging.getLogger("test")
    )
    with project_watch._lock:
        project_watch._pending.add(str(repo / "first.py"))
    first_flush = threading.Thread(target=project_watch._flush)
    first_flush.start()
    assert entered[0].wait(1)

    with project_watch._lock:
        project_watch._pending.add(str(repo / "second.py"))
    second_flush = threading.Thread(target=project_watch._flush)
    second_flush.start()
    assert entered[1].wait(1)

    stopped = threading.Event()
    stop_thread = threading.Thread(
        target=lambda: (project_watch.stop(), stopped.set())
    )
    stop_thread.start()
    try:
        assert not stopped.wait(0.2)
        release[0].set()
        first_flush.join(timeout=1)
        assert not first_flush.is_alive()
        assert not stopped.wait(0.2), (
            "stop returned after only one of two entered flushes completed"
        )
    finally:
        release[0].set()
        release[1].set()
        first_flush.join(timeout=2)
        second_flush.join(timeout=2)
        stop_thread.join(timeout=2)

    assert stopped.is_set()
    assert not second_flush.is_alive()
    assert not stop_thread.is_alive()
