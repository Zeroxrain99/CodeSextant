"""Event-driven daemon, watcher, and recovery lifecycle contracts."""

from __future__ import annotations

import logging
import socket
import threading
import time
from types import SimpleNamespace
from urllib.parse import urlparse


class _FakeTimer:
    created = []

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


def test_idle_shutdown_is_one_shot_and_real_activity_resets_it():
    from codesextant.daemon import _IdleShutdownController

    _FakeTimer.created = []
    shutdowns = []
    controller = _IdleShutdownController(
        timeout_sec=30,
        shutdown=lambda: shutdowns.append("shutdown"),
        busy=lambda: False,
        timer_factory=_FakeTimer,
    )

    controller.start()
    first = _FakeTimer.created[-1]
    controller.begin_request()
    assert first.cancelled is True
    controller.end_request()
    second = _FakeTimer.created[-1]
    assert second is not first and second.started is True

    second.callback()
    second.callback()
    assert shutdowns == ["shutdown"]


def test_daemon_startup_does_not_enumerate_historical_projects(tmp_path, monkeypatch):
    from codesextant import daemon

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "1")

    class FakeServer:
        def __init__(self, *_args):
            pass

        def serve_forever(self):
            pass

        def server_close(self):
            pass

    monkeypatch.setattr(daemon, "_ExclusiveThreadingHTTPServer", FakeServer)
    enumerations = []
    monkeypatch.setattr(
        daemon.storage,
        "list_indexed_projects",
        lambda: enumerations.append("called") or [],
    )
    monkeypatch.setattr(daemon, "_WATCH_MGR", None)

    assert daemon.serve(port=18831)["action"] == "stopped"
    assert enumerations == []


def test_existing_index_recovers_once_on_first_real_query(tmp_path, monkeypatch):
    from codesextant import storage, watcher

    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    storage.db_path_for(str(repo)).parent.mkdir(parents=True, exist_ok=True)
    storage.db_path_for(str(repo)).touch()

    manager = watcher.WatchManager(logging.getLogger("test"), idle_ttl_sec=30)
    monkeypatch.setattr(manager, "ensure_watch", lambda _repo: True)
    calls = []
    monkeypatch.setattr(
        manager,
        "recover",
        lambda path: calls.append(path) or {"indexed": 0, "skipped": 1, "removed": 0},
    )

    manager.ensure_ready(str(repo))
    manager.ensure_ready(str(repo))

    assert calls == [str(repo.resolve())]
    assert manager.recovery_state(str(repo)) == "ready"
    manager.stop_all()


def test_interactive_query_schedules_one_recovery_without_waiting(
        tmp_path, monkeypatch):
    from codesextant import daemon

    repo = tmp_path / "repo"
    repo.mkdir()
    entered = threading.Event()
    release = threading.Event()
    calls = []

    class Manager:
        def recovery_state(self, _project):
            return "unseen"

        def ensure_watch(self, project):
            calls.append(("watch", project))
            time.sleep(0.3)
            return True

        def ensure_ready(self, project, *, deadline=None):
            calls.append(("recover", project, deadline))
            entered.set()
            release.wait(timeout=2)
            return {"indexed": 0}

    manager = Manager()
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "1")
    monkeypatch.setattr(daemon, "_get_watch_mgr", lambda: manager)
    with daemon._RECOVERY_THREADS_LOCK:
        assert not daemon._RECOVERY_THREADS

    target = "/get_map?project=" + str(repo)
    try:
        started = time.monotonic()
        first = daemon._prepare_project(
            "/get_map", urlparse(target), None)
        elapsed = time.monotonic() - started
        assert entered.wait(timeout=1)
        second = daemon._prepare_project(
            "/get_map", urlparse(target), None)

        assert elapsed < 0.2
        assert first == {"recovery": "scheduled", "stale_possible": True}
        assert second == {"recovery": "running", "stale_possible": True}
        assert [call[0] for call in calls].count("recover") == 1
    finally:
        release.set()
        daemon._join_recovery_threads()


def test_interactive_lifecycle_marks_an_explicit_reindex_as_stale(
        tmp_path, monkeypatch):
    from codesextant import daemon

    repo = tmp_path / "repo"
    repo.mkdir()

    class Manager:
        def recovery_state(self, _project):
            return "ready"

    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "1")
    monkeypatch.setattr(daemon, "_get_watch_mgr", lambda: Manager())
    monkeypatch.setattr(
        daemon._HEAVY_COORDINATOR,
        "has_work",
        lambda **_kwargs: True,
        raising=False,
    )

    target = "/get_map?project=" + str(repo)
    lifecycle = daemon._prepare_project(
        "/get_map", urlparse(target), None)

    assert lifecycle == {"recovery": "ready", "stale_possible": True}


def test_project_status_includes_immediate_service_load(tmp_path, monkeypatch):
    from codesextant import daemon

    project = str(tmp_path / "repo")
    load = {"active_jobs": [], "queued_jobs": [], "blocking_reason": None}
    monkeypatch.setattr(
        daemon.project_state,
        "status",
        lambda _project, check_freshness=False, **_kwargs: {
            "indexed": True,
            "freshness_checked": check_freshness,
        },
    )
    monkeypatch.setattr(
        daemon._HEAVY_COORDINATOR, "snapshot", lambda: load)
    monkeypatch.setattr(daemon, "_recovery_snapshot", lambda: [])

    code, result = daemon._ep_status(
        urlparse("/status?project=" + project), None)

    assert code == 200
    assert result["service_load"] == load
    assert result["background_recoveries"] == []


def test_status_returns_partial_telemetry_when_cache_lease_is_busy(
        tmp_path, monkeypatch):
    from codesextant import cache_lease, client, daemon, storage

    project = tmp_path / "repo"
    project.mkdir()
    state_home = tmp_path / "state"
    monkeypatch.setenv("CODESEXTANT_HOME", str(state_home))
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "0")
    monkeypatch.setenv("CODESEXTANT_STATUS_DB_TIMEOUT_MS", "100")
    with storage.ProjectStore.open(str(project)):
        pass
    exclusive = cache_lease.try_acquire_exclusive(
        storage.project_key(str(project)), home=state_home)
    assert exclusive is not None
    server = daemon._ExclusiveThreadingHTTPServer(
        (daemon.HOST, 0), daemon._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    api = client.CodesextantClient(
        project=str(project), port=server.server_port, timeout=2)

    try:
        started = time.monotonic()
        result = api.status()
        elapsed = time.monotonic() - started
    finally:
        exclusive.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert elapsed < 1.5
    assert result["partial"] is True
    assert result["index_status_error"] == "database-busy"
    assert "service_load" in result
    assert "background_recoveries" in result


def test_project_activity_touches_cache_even_when_watcher_is_disabled(
        tmp_path, monkeypatch):
    from codesextant import daemon

    project = str(tmp_path / "repo")
    touched = []
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "0")
    monkeypatch.setattr(
        daemon, "_touch_cache_project", lambda path: touched.append(path))

    lifecycle = daemon._prepare_project(
        "/get_map", urlparse("/get_map?project=" + project), None)

    assert lifecycle is None
    assert touched == [project]


def test_shutdown_cache_prune_excludes_projects_used_by_daemon(
        tmp_path, monkeypatch):
    from codesextant import daemon, storage

    project = str(tmp_path / "repo")
    seen = []
    with daemon._DAEMON_PROJECT_KEYS_LOCK:
        daemon._DAEMON_PROJECT_KEYS.clear()
    monkeypatch.setattr(daemon, "_ACTIVE_SERVER", None)
    monkeypatch.setattr(
        daemon._HEAVY_COORDINATOR,
        "snapshot",
        lambda: {
            "active": None,
            "active_jobs": [],
            "queued": 0,
            "queued_jobs": [],
            "followers": 0,
            "global_in_use": 0,
            "global_waiting": 0,
        },
    )
    monkeypatch.setattr(
        daemon.cache_gc,
        "prune",
        lambda **kwargs: seen.append(kwargs) or {
            "before_bytes": 0,
            "after_bytes": 0,
            "reclaimed_bytes": 0,
            "projects": [],
            "errors": [],
        },
    )

    result = daemon._prune_cache_if_quiescent((project,))

    assert result["action"] == "completed"
    assert seen == [{
        "exclude_project_keys": (storage.project_key(project),),
    }]


def test_shutdown_cache_prune_skips_when_heavy_work_remains(monkeypatch):
    from codesextant import daemon

    monkeypatch.setattr(daemon, "_ACTIVE_SERVER", None)
    monkeypatch.setattr(
        daemon._HEAVY_COORDINATOR,
        "snapshot",
        lambda: {
            "active": "/reindex",
            "active_jobs": [{"label": "/reindex"}],
        },
    )
    monkeypatch.setattr(
        daemon.cache_gc,
        "prune",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("cache prune must not run during heavy work")
        ),
    )

    assert daemon._prune_cache_if_quiescent(()) == {
        "action": "skipped",
        "reason": "work-active",
    }


def test_instance_lock_reports_shutdown_maintenance_without_false_reuse(
        tmp_path, monkeypatch):
    from codesextant import daemon

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    port = 18841
    instance = daemon._InterprocessFileLock(
        daemon._daemon_lock_path(port, "instance"), timeout=0)
    instance.acquire()
    draining = daemon._daemon_lock_path(port, "draining")
    draining.touch()
    try:
        result = daemon._instance_owner_result(port)
    finally:
        instance.release()

    assert result["action"] == "daemon-draining"
    assert result["health_proof"] == "instance-lock-draining"


def test_new_lifetime_owner_removes_a_stale_draining_marker(
        tmp_path, monkeypatch):
    from codesextant import daemon

    port = 18847
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "0")
    marker = daemon._daemon_lock_path(port, "draining")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()

    class FakeServer:
        def __init__(self, *_args):
            pass

        def serve_forever(self):
            assert not marker.exists()

        def server_close(self):
            pass

    monkeypatch.setattr(daemon, "_ExclusiveThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(
        daemon, "_prune_cache_if_quiescent", lambda _projects: {})

    result = daemon.serve(port=port)

    assert result["action"] == "stopped"
    assert not marker.exists()


def test_idle_watcher_eviction_preserves_busy_projects(monkeypatch, tmp_path):
    from codesextant import watcher

    manager = watcher.WatchManager(
        logging.getLogger("test"), idle_ttl_sec=10, clock=lambda: 100.0
    )
    stopped = []
    idle = SimpleNamespace(is_quiescent=lambda: True, stop=lambda: stopped.append("idle"))
    busy = SimpleNamespace(is_quiescent=lambda: False, stop=lambda: stopped.append("busy"))
    manager._watches = {"idle": idle, "busy": busy}
    manager._last_activity = {"idle": 1.0, "busy": 1.0}
    manager._watched_snapshot = ("busy", "idle")

    assert manager.evict_idle(now=100.0) == ["idle"]
    assert stopped == ["idle"]
    assert manager.watched_snapshot() == ("busy",)
    manager.stop_all()


def test_supervisor_run_checks_once_without_sleep(monkeypatch):
    from codesextant import supervisor

    calls = []
    monkeypatch.setattr(
        supervisor,
        "supervise_once",
        lambda **kwargs: calls.append(kwargs) or {"action": "healthy"},
    )
    monkeypatch.setattr(
        supervisor.time,
        "sleep",
        lambda _delay: (_ for _ in ()).throw(AssertionError("run must not poll")),
    )

    assert supervisor.run(port=18832) == 0
    assert calls == [{"port": 18832}]


def test_panel_refreshes_on_user_events_without_interval_polling():
    from codesextant import panel

    html = panel.render_panel()

    assert "setInterval(" not in html
    assert "visibilitychange" in html
    assert "addEventListener('focus'" in html


def test_windows_startup_task_has_no_heartbeat_trigger():
    from pathlib import Path

    script = (Path(__file__).resolve().parents[1]
              / "tools" / "register_windows_startup.ps1")
    text = script.read_text(encoding="utf-8")

    assert "RepetitionInterval" not in text
    assert "RepetitionDuration" not in text
    assert "$Heartbeat" not in text
    assert "recovery heartbeat" not in text


def test_partial_unauthenticated_connections_are_timed_out_and_bounded(
        monkeypatch):
    from codesextant import daemon

    preauth_timeout = 1.0
    monkeypatch.setenv("CODESEXTANT_IDLE_TIMEOUT_SEC", "0")
    monkeypatch.setenv("CODESEXTANT_MAX_HANDLER_THREADS", "1")
    monkeypatch.setenv("CODESEXTANT_PREAUTH_TIMEOUT_SEC", str(preauth_timeout))
    server = daemon._ExclusiveThreadingHTTPServer(
        (daemon.HOST, 0), daemon._Handler
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    first = socket.create_connection((daemon.HOST, server.server_port), timeout=5)
    second = None
    try:
        # A header that never terminates: the handler stays parked in its pre-auth read.
        first.sendall(
            b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        )
        # Wait for the accept loop to actually take the only handler slot. Sleeping here
        # and assuming it had would make the next assert depend on machine speed: on a
        # slow runner the connection can still be in the backlog, and the second request
        # then gets a slot and answers 401 instead of 503.
        assert server.wait_for_active_handlers(1, timeout=10.0), (
            "the partial connection never occupied the only handler slot")

        second = socket.create_connection(
            (daemon.HOST, server.server_port), timeout=5
        )
        second.sendall(
            b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        )
        response = second.recv(2048)
        assert b"503 Service Unavailable" in response

        # The pre-auth timeout must close the stalled connection. Observe the close as
        # EOF rather than sleeping past a deadline and assuming it happened.
        first.settimeout(preauth_timeout + 10.0)
        assert first.recv(1) == b"", "the stalled connection was not timed out"
    finally:
        first.close()
        if second is not None:
            second.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    assert not worker.is_alive()
