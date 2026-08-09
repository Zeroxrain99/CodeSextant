"""Reliability regressions for the daemon: staying a singleton, healing itself,
and behaving under the supervisor."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import client, daemon  # noqa: E402


def test_log_rollover_does_not_rename_files_locked_by_windows(tmp_path, monkeypatch):
    """Readers can deny rename/delete sharing on Windows; rotation must still work."""
    log_path = tmp_path / "daemon.log"

    def locked_rename(*_args, **_kwargs):
        raise PermissionError(32, "file is being used by another process")

    monkeypatch.setattr(os, "rename", locked_rename)
    handler = daemon._CopyTruncateRotatingFileHandler(
        log_path, maxBytes=80, backupCount=2, encoding="utf-8")
    logger = logging.getLogger(f"codesextant.rollover-test.{id(tmp_path)}")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        logger.info("A" * 100)
        logger.info("after-rollover")
    finally:
        handler.close()
        logger.handlers.clear()

    assert "after-rollover" in log_path.read_text(encoding="utf-8")
    archives = list(tmp_path.glob("daemon.log.*"))
    assert 1 <= len(archives) <= 2
    assert any("A" * 100 in path.read_text(encoding="utf-8") for path in archives)


def test_control_plane_logger_does_not_open_daemon_log(tmp_path, monkeypatch):
    """Only the serving daemon may own daemon.log; wrapper clients use stderr."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path))
    previous = daemon._logger
    daemon._logger = None
    try:
        logger = daemon.get_logger()
        assert not any(isinstance(h, RotatingFileHandler) for h in logger.handlers)
        assert not (tmp_path / "daemon.log").exists()

        logger = daemon.get_logger(file_output=True)
        file_handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert isinstance(file_handlers[0], daemon._CopyTruncateRotatingFileHandler)
    finally:
        for handler in list(daemon._logger.handlers if daemon._logger else []):
            handler.close()
            if daemon._logger:
                daemon._logger.removeHandler(handler)
        daemon._logger = previous


def test_thin_client_import_does_not_load_heavy_engine():
    """The CLI only speaks HTTP, so importing it must not pull in tree-sitter or
    the engine. Only the daemon needs the full engine loaded."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    probe = subprocess.run(
        [sys.executable, "-c",
         "import sys; import codesextant.client; "
         "print('codesextant.engine' in sys.modules)"],
        cwd=root, capture_output=True, text=True, timeout=30,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == "False"


def test_http_server_disables_windows_address_reuse():
    """HTTPServer sets allow_reuse_address=1 by default, which on Windows lets
    several PIDs bind port 8790 at once."""
    assert daemon._ExclusiveThreadingHTTPServer.allow_reuse_address is False
    assert daemon._ExclusiveThreadingHTTPServer.allow_reuse_port is False


def test_http_server_has_room_for_control_plane_during_heavy_work():
    """Heavy requests must not fill the tiny stdlib backlog and starve /health."""
    assert daemon._ExclusiveThreadingHTTPServer.request_queue_size >= 64


def test_health_endpoint_does_not_load_engine_or_watcher(monkeypatch):
    """The liveness endpoint is control-plane code and must stay dependency-light."""
    class ExplodingLazyModule:
        def __getattr__(self, name):
            pytest.fail(f"/health must not lazy-load heavy module attribute {name}")

    monkeypatch.setattr(daemon, "engine", ExplodingLazyModule())
    monkeypatch.setattr(daemon, "watcher", ExplodingLazyModule())
    monkeypatch.setattr(daemon, "_WATCH_MGR", None)

    code, result = daemon._ep_health(None, None)

    assert code == 200
    assert result["service"] == "codesextant"
    assert result["watcher"]["watched"] == []


def test_health_reads_lock_free_watcher_snapshot(monkeypatch):
    """Health must not enter WatchManager's lifecycle lock."""
    class ManagerProbe:
        def watched(self):
            pytest.fail("health must not call the locking watched() API")

        def watched_snapshot(self):
            return ("C:/repo-a", "C:/repo-b")

    monkeypatch.setattr(daemon, "_WATCH_MGR", ManagerProbe())
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "1")

    code, result = daemon._ep_health(None, None)

    assert code == 200
    assert result["watcher"]["watched"] == ["C:/repo-a", "C:/repo-b"]


def test_health_returns_promptly_while_watcher_manager_lock_is_held(monkeypatch):
    """Spec red test: hold the real WatchManager lifecycle lock, /health must
    still answer immediately (an OS observer hanging inside ensure_watch must
    never take the liveness endpoint down with it)."""
    from codesextant import watcher as watcher_module

    logger = SimpleNamespace(info=lambda *_args, **_kwargs: None,
                             warning=lambda *_args, **_kwargs: None)
    mgr = watcher_module.WatchManager(logger)
    with mgr._lock:  # publish one watched repo the way ensure_watch does
        mgr._watches["C:/repo-a"] = object()
        mgr._watched_snapshot = tuple(sorted(mgr._watches))

    monkeypatch.setattr(daemon, "_WATCH_MGR", mgr)
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "1")

    outcome = {}

    def call_health():
        outcome["response"] = daemon._ep_health(None, None)

    assert mgr._lock.acquire(timeout=1)  # simulate a stuck ensure_watch/stop_all
    try:
        worker = threading.Thread(target=call_health, daemon=True)
        worker.start()
        worker.join(timeout=2)
        health_blocked = worker.is_alive()
    finally:
        mgr._lock.release()
    assert not health_blocked, "/health blocked on the watcher manager lock"

    code, result = outcome["response"]
    assert code == 200
    assert result["watcher"]["watched"] == ["C:/repo-a"]


def test_interprocess_lock_excludes_second_holder(tmp_path):
    lock_path = tmp_path / "daemon.lock"
    with daemon._InterprocessFileLock(lock_path, timeout=0.1), pytest.raises(TimeoutError):
        with daemon._InterprocessFileLock(lock_path, timeout=0.05):
            pass


def test_instance_probe_timeout_is_unknown_not_a_healthy_owner(tmp_path, monkeypatch):
    """Probe contention must prevent duplicate spawn without claiming a proven owner."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    real_lock = daemon._InterprocessFileLock

    class ProbeTimeoutLock(real_lock):
        def acquire(self):
            if self.path.name.endswith("instance-probe.lock"):
                raise TimeoutError("probe state unavailable")
            return super().acquire()

    monkeypatch.setattr(daemon, "_InterprocessFileLock", ProbeTimeoutLock)

    result = daemon._instance_owner_result(18811)

    assert result["action"] == "ownership-unknown"
    assert result["health_proof"] == "instance-lock-unknown"


def test_serve_serializes_lifetime_lock_with_probe_guard(tmp_path, monkeypatch):
    """A new server must hold the probe guard while claiming the lifetime lock."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "0")
    events = []

    class RecordingLock:
        def __init__(self, path, timeout=0.0, **_kwargs):
            self.kind = path.name.split(".")[-2]

        def acquire(self):
            events.append(f"acquire:{self.kind}")
            return self

        def release(self):
            events.append(f"release:{self.kind}")

    class FakeServer:
        def __init__(self, *_args):
            events.append("server:init")

        def serve_forever(self):
            events.append("server:serve")

        def server_close(self):
            events.append("server:close")

    monkeypatch.setattr(daemon, "_InterprocessFileLock", RecordingLock)
    monkeypatch.setattr(daemon, "_ExclusiveThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(daemon.storage, "list_indexed_projects", lambda: [])
    monkeypatch.setattr(daemon, "_WATCH_MGR", None)

    daemon.serve(port=18812)

    assert events.index("acquire:instance-probe") < events.index("acquire:instance")
    assert events.index("acquire:instance") < events.index("release:instance-probe")
    assert events[-1] == "release:instance"


def test_serve_with_watcher_disabled_never_imports_watcher_or_engine(
        tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "0")

    class ExplodingLazyModule:
        def __getattr__(self, name):
            pytest.fail(f"disabled watcher must not load module attribute {name}")

    class FakeServer:
        def __init__(self, *_args):
            pass

        def serve_forever(self):
            pass

        def server_close(self):
            pass

    monkeypatch.setattr(daemon, "watcher", ExplodingLazyModule())
    monkeypatch.setattr(daemon, "engine", ExplodingLazyModule())
    monkeypatch.setattr(daemon, "_ExclusiveThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(daemon.storage, "list_indexed_projects", lambda: pytest.fail(
        "disabled watcher must not enumerate indexed projects"))
    monkeypatch.setattr(daemon, "_WATCH_MGR", None)

    assert daemon.serve(port=18813)["action"] == "stopped"


def test_require_project_with_watcher_disabled_never_imports_watcher(monkeypatch):
    """Data endpoints must not build the watch manager when the switch is off.

    ``_require_project`` runs on every data endpoint; with
    ``CODESEXTANT_WATCH_ENABLED=0`` it must not import the watcher module nor
    construct a WatchManager as a side effect.
    """
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "0")

    class ExplodingLazyModule:
        def __getattr__(self, name):
            pytest.fail(f"disabled watcher must not load module attribute {name}")

    monkeypatch.setattr(daemon, "watcher", ExplodingLazyModule())
    monkeypatch.setattr(daemon, "_WATCH_MGR", None)

    assert daemon._require_project("C:/some/project") == "C:/some/project"
    assert daemon._WATCH_MGR is None


def test_require_project_with_watcher_enabled_still_registers_watch(monkeypatch):
    """The queue-3 auto-watch behaviour must survive the disabled-switch gate."""
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "1")
    calls = []
    monkeypatch.setattr(
        daemon, "_get_watch_mgr",
        lambda: SimpleNamespace(ensure_watch=lambda p: calls.append(p)))

    assert daemon._require_project("C:/some/project") == "C:/some/project"
    assert calls == ["C:/some/project"]


def test_concurrent_ensure_spawns_only_once(tmp_path, monkeypatch):
    """When several clients make their first call at the same moment, exactly
    one detached daemon may spawn."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    state = {"health": None, "spawns": 0}

    def fake_ping(*_args, **_kwargs):
        return state["health"]

    def fake_spawn(port):
        state["spawns"] += 1
        state["health"] = {"service": "codesextant", "pid": 4242, "port": port}
        return SimpleNamespace(pid=4242)

    monkeypatch.setattr(daemon, "http_ping", fake_ping)
    monkeypatch.setattr(daemon, "is_port_listening", lambda **_kwargs: False)
    monkeypatch.setattr(daemon, "_spawn_daemon", fake_spawn)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda _n: daemon.ensure_running(port=18790, wait_sec=1.0),
            range(8),
        ))

    assert state["spawns"] == 1
    assert {r["action"] for r in results} <= {"spawned", "already-running"}
    assert {r["pid"] for r in results} == {4242}


def test_ensure_confirms_slow_branded_listener_before_port_conflict(
        tmp_path, monkeypatch):
    """A fast probe can time out while our own listener answers a moment later.
    That must not be reported as some outside process holding the port."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    timeouts = []

    def delayed_ping(*_args, timeout=0.6, **_kwargs):
        timeouts.append(timeout)
        if timeout >= 2.0:
            return {"service": "codesextant", "pid": 4243, "port": 18795}
        return None

    monkeypatch.setattr(daemon, "http_ping", delayed_ping)
    monkeypatch.setattr(daemon, "is_port_listening", lambda **_kwargs: True)
    monkeypatch.setattr(
        daemon, "_spawn_daemon",
        lambda _port: pytest.fail("slow live daemon must not be respawned"),
    )

    result = daemon.ensure_running(port=18795, wait_sec=4.0)
    assert result["action"] == "already-running"
    assert result["pid"] == 4243
    assert max(timeouts) >= 2.0


def test_ensure_uses_instance_lock_when_busy_daemon_health_times_out(
        tmp_path, monkeypatch):
    """CPU-bound map may starve /health; the daemon's lifetime lock still proves ownership."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    monkeypatch.setattr(daemon, "http_ping", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(daemon, "is_port_listening", lambda **_kwargs: True)
    monkeypatch.setattr(
        daemon, "_spawn_daemon",
        lambda _port: pytest.fail("lock-proven live daemon must not be respawned"),
    )

    lock = daemon._InterprocessFileLock(
        daemon._daemon_lock_path(18798, "instance"), timeout=0.0)
    lock.acquire()
    try:
        result = daemon.ensure_running(port=18798, wait_sec=0.1)
    finally:
        lock.release()

    assert result["action"] == "already-running"
    assert result["port"] == 18798
    assert result["health_proof"] == "instance-lock"


def test_ensure_uses_instance_lock_even_when_tcp_probe_misses(
        tmp_path, monkeypatch):
    """A full accept backlog must not bypass the stronger lifetime-lock proof."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    monkeypatch.setattr(daemon, "http_ping", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(daemon, "is_port_listening", lambda **_kwargs: False)
    monkeypatch.setattr(
        daemon, "_spawn_daemon",
        lambda _port: pytest.fail("lock-proven daemon must never be respawned"),
    )

    lock = daemon._InterprocessFileLock(
        daemon._daemon_lock_path(18801, "instance"), timeout=0.0)
    lock.acquire()
    try:
        result = daemon.ensure_running(port=18801, wait_sec=0.05)
    finally:
        lock.release()

    assert result["action"] == "already-running"
    assert result["health_proof"] == "instance-lock"


def test_startup_lock_timeout_falls_back_to_instance_lock(
        tmp_path, monkeypatch):
    """A client losing the startup-lock race must still reuse the live owner."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    monkeypatch.setattr(daemon, "http_ping", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        daemon, "_spawn_daemon",
        lambda _port: pytest.fail("startup-lock timeout must not spawn"),
    )
    ownership_checks = iter((False, True))
    monkeypatch.setattr(
        daemon, "_instance_lock_held", lambda _port: next(ownership_checks))

    startup = daemon._InterprocessFileLock(
        daemon._daemon_lock_path(18802, "startup"), timeout=0.0)
    startup.acquire()
    try:
        result = daemon.ensure_running(port=18802, wait_sec=0.01)
    finally:
        startup.release()

    assert result["action"] == "already-running"
    assert result["health_proof"] == "instance-lock"


class _JsonResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


def test_client_connection_failure_restarts_and_retries_once(monkeypatch, tmp_path):
    calls = {"open": 0, "ensure": 0}

    def flaky_open(*_args, **_kwargs):
        calls["open"] += 1
        if calls["open"] == 1:
            raise urllib.error.URLError("daemon stopped")
        return _JsonResponse({"indexed": True})

    def fake_ensure(*_args, **_kwargs):
        calls["ensure"] += 1
        return {"action": "spawned", "pid": 99, "port": 18791}

    monkeypatch.setattr(client.urllib.request, "urlopen", flaky_open)
    monkeypatch.setattr(daemon, "ensure_running", fake_ensure)

    c = client.CodesextantClient(project=str(tmp_path), port=18791)
    assert c.status() == {"indexed": True}
    assert calls == {"open": 2, "ensure": 1}


def test_client_timeout_does_not_duplicate_a_live_long_query(monkeypatch, tmp_path):
    """While the service is still healthy, a query timeout must not lead to an
    ensure followed by the same heavy query going out a second time."""
    calls = {"open": 0, "ensure": 0, "health": 0}

    def slow_open(*_args, **_kwargs):
        calls["open"] += 1
        raise TimeoutError("query exceeded client timeout")

    def healthy_ping(*_args, **_kwargs):
        calls["health"] += 1
        return {"service": "codesextant", "pid": 42, "port": 18794}

    def fake_ensure(*_args, **_kwargs):
        calls["ensure"] += 1
        return {"action": "already-running", "pid": 42}

    monkeypatch.setattr(client.urllib.request, "urlopen", slow_open)
    monkeypatch.setattr(daemon, "http_ping", healthy_ping)
    monkeypatch.setattr(daemon, "ensure_running", fake_ensure)

    c = client.CodesextantClient(project=str(tmp_path), port=18794)
    with pytest.raises(TimeoutError, match="still up"):
        c.status()
    assert calls == {"open": 1, "ensure": 0, "health": 1}


def test_status_route_does_not_import_the_parser_engine(monkeypatch, tmp_path):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "0")

    class ExplodingEngine:
        def __getattr__(self, _name):
            raise AssertionError("status must not load the parser engine")

    monkeypatch.setattr(daemon, "engine", ExplodingEngine())
    parsed = urllib.parse.urlparse(f"/status?project={urllib.parse.quote(str(tmp_path))}")

    code, result = daemon._ep_status(parsed, None)

    assert code == 200
    assert result["indexed"] is False


def test_projects_route_does_not_import_the_parser_engine(monkeypatch, tmp_path):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "0")

    class ExplodingEngine:
        def __getattr__(self, _name):
            raise AssertionError("projects must not load the parser engine")

    monkeypatch.setattr(daemon, "engine", ExplodingEngine())

    code, result = daemon._ep_projects(urllib.parse.urlparse("/projects"), None)

    assert code == 200
    assert result == {"db_dir": str(tmp_path / "db"), "count": 0, "projects": []}


def test_client_timeout_does_not_retry_when_ensure_confirms_slow_live_daemon(
        monkeypatch, tmp_path):
    """A one-second health check that fails, followed by a slower confirmation
    that succeeds, still means the original query is running. No second copy."""
    calls = {"open": 0, "ensure": 0, "health": 0}

    def slow_open(*_args, **_kwargs):
        calls["open"] += 1
        raise TimeoutError("query exceeded client timeout")

    def transient_ping(*_args, **_kwargs):
        calls["health"] += 1
        return None

    def confirm_existing(*_args, **_kwargs):
        calls["ensure"] += 1
        return {"action": "already-running", "pid": 42, "port": 18796}

    monkeypatch.setattr(client.urllib.request, "urlopen", slow_open)
    monkeypatch.setattr(daemon, "http_ping", transient_ping)
    monkeypatch.setattr(daemon, "ensure_running", confirm_existing)

    c = client.CodesextantClient(project=str(tmp_path), port=18796)
    with pytest.raises(TimeoutError, match="still up"):
        c.status()
    assert calls == {"open": 1, "ensure": 1, "health": 1}


def test_client_does_not_retry_http_application_error(monkeypatch, tmp_path):
    calls = {"ensure": 0}

    def http_error(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "http://127.0.0.1:18792/status", 500, "server error", {}, None)

    def fake_ensure(*_args, **_kwargs):
        calls["ensure"] += 1
        return {"action": "spawned"}

    monkeypatch.setattr(client.urllib.request, "urlopen", http_error)
    monkeypatch.setattr(daemon, "ensure_running", fake_ensure)

    c = client.CodesextantClient(project=str(tmp_path), port=18792)
    with pytest.raises(urllib.error.HTTPError):
        c.status()
    assert calls["ensure"] == 0


def test_client_map_has_longer_cold_query_deadline(monkeypatch, tmp_path):
    """A cold map may legitimately take minutes, including FIFO queue wait."""
    seen = []

    def capture_open(*_args, timeout=None, **_kwargs):
        seen.append(timeout)
        return _JsonResponse({"count": 1})

    monkeypatch.setattr(client.urllib.request, "urlopen", capture_open)
    c = client.CodesextantClient(project=str(tmp_path), port=18797, timeout=5.0)
    assert c.get_map() == {"count": 1}
    assert seen == [900.0]


def test_client_reindex_has_dedicated_long_deadline(monkeypatch, tmp_path):
    """Queue wait plus a cold index must not inherit the 30-second RPC deadline."""
    seen = []

    def capture_open(*_args, timeout=None, **_kwargs):
        seen.append(timeout)
        return _JsonResponse({"indexed": 1})

    monkeypatch.setenv("CODESEXTANT_REINDEX_TIMEOUT_SEC", "321")
    monkeypatch.setattr(client.urllib.request, "urlopen", capture_open)
    c = client.CodesextantClient(project=str(tmp_path), port=18803, timeout=5.0)

    assert c.reindex() == {"indexed": 1}
    assert seen == [321.0]


def test_client_impact_uses_shared_heavy_deadline(monkeypatch, tmp_path):
    seen = []

    def capture_open(*_args, timeout=None, **_kwargs):
        seen.append(timeout)
        return _JsonResponse({"blast_radius": 1})

    monkeypatch.setenv("CODESEXTANT_HEAVY_TIMEOUT_SEC", "432")
    monkeypatch.setattr(client.urllib.request, "urlopen", capture_open)
    c = client.CodesextantClient(project=str(tmp_path), port=18804, timeout=5.0)

    assert c.impact("renderGameSettings") == {"blast_radius": 1}
    assert seen == [432.0]


def test_send_json_ignores_windows_client_abort():
    """WinError 10053, raised when a client closes its socket on timeout, is an
    ordinary cancellation and must not be escalated into a 500 from the endpoint."""
    class AbortWriter:
        def write(self, _body):
            raise ConnectionAbortedError(10053, "client aborted")

    class HandlerProbe:
        wfile = AbortWriter()

        def send_response(self, _code):
            pass

        def send_header(self, _name, _value):
            pass

        def end_headers(self):
            pass

    daemon._Handler._send_json(HandlerProbe(), 200, {"ok": True})


def test_supervisor_restarts_only_when_health_is_down(monkeypatch):
    from codesextant import supervisor

    calls = []
    monkeypatch.setattr(supervisor.daemon, "http_ping", lambda **_kwargs: None)
    monkeypatch.setattr(
        supervisor.daemon,
        "ensure_running",
        lambda **kwargs: calls.append(kwargs) or {"action": "spawned", "pid": 7},
    )
    assert supervisor.supervise_once(port=18793)["action"] == "spawned"
    assert len(calls) == 1

    monkeypatch.setattr(
        supervisor.daemon,
        "http_ping",
        lambda **_kwargs: {"service": "codesextant", "pid": 7, "port": 18793},
    )
    assert supervisor.supervise_once(port=18793)["action"] == "healthy"
    assert len(calls) == 1


def test_supervisor_busy_instance_never_calls_ensure(monkeypatch):
    from codesextant import supervisor

    monkeypatch.setattr(supervisor.daemon, "http_ping", lambda **_kwargs: None)
    monkeypatch.setattr(supervisor.daemon, "_instance_lock_held", lambda _port: True)
    monkeypatch.setattr(
        supervisor.daemon, "ensure_running",
        lambda **_kwargs: pytest.fail("busy lifetime owner must not enter startup path"),
    )

    result = supervisor.supervise_once(port=18805)

    assert result["action"] == "already-running"
    assert result["health_proof"] == "instance-lock"


def test_busy_owner_never_spawns_under_concurrent_supervisor_and_client(
        tmp_path, monkeypatch):
    from codesextant import supervisor

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "db"))
    monkeypatch.setattr(daemon, "http_ping", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(daemon, "is_port_listening", lambda **_kwargs: False)
    monkeypatch.setattr(
        daemon, "_spawn_daemon",
        lambda _port: pytest.fail("busy lifetime owner must never spawn"),
    )

    instance = daemon._InterprocessFileLock(
        daemon._daemon_lock_path(18806, "instance"), timeout=0.0)
    instance.acquire()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(daemon.ensure_running, port=18806, wait_sec=0.05),
                pool.submit(supervisor.supervise_once, port=18806),
            ]
            results = [future.result() for future in futures]
    finally:
        instance.release()

    assert {result["action"] for result in results} == {"already-running"}
    assert {result["health_proof"] for result in results} == {"instance-lock"}


def test_heavy_work_coordinator_single_flights_same_key():
    from codesextant.work_coordinator import HeavyWorkCoordinator

    coordinator = HeavyWorkCoordinator()
    started = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def work():
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        assert release.wait(2)
        return {"value": 7}

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(coordinator.run, ("map", "repo"), work, label="/get_map")
        assert started.wait(1)
        second = pool.submit(coordinator.run, ("map", "repo"), work, label="/get_map")
        time.sleep(0.05)
        release.set()
        assert first.result() == {"value": 7}
        assert second.result() == {"value": 7}

    assert calls == 1


def test_heavy_work_coordinator_serializes_different_projects_fifo():
    from codesextant.work_coordinator import HeavyWorkCoordinator

    coordinator = HeavyWorkCoordinator()
    first_started = threading.Event()
    release_first = threading.Event()
    order = []
    active = 0
    max_active = 0
    state_lock = threading.Lock()

    def work(name, gate=None):
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)
            order.append(f"start:{name}")
        if name == "a":
            first_started.set()
            assert release_first.wait(2)
        if gate is not None:
            assert gate.wait(2)
        with state_lock:
            order.append(f"end:{name}")
            active -= 1
        return name

    with ThreadPoolExecutor(max_workers=3) as pool:
        a = pool.submit(coordinator.run, ("map", "a"), lambda: work("a"), label="map")
        assert first_started.wait(1)
        b = pool.submit(coordinator.run, ("map", "b"), lambda: work("b"), label="map")
        time.sleep(0.02)
        c = pool.submit(coordinator.run, ("reindex", "c"), lambda: work("c"), label="reindex")
        time.sleep(0.05)
        release_first.set()
        assert [a.result(), b.result(), c.result()] == ["a", "b", "c"]

    assert max_active == 1
    assert order == ["start:a", "end:a", "start:b", "end:b", "start:c", "end:c"]


def test_heavy_work_coordinator_releases_followers_after_error():
    from codesextant.work_coordinator import HeavyWorkCoordinator

    coordinator = HeavyWorkCoordinator()
    started = threading.Event()
    release = threading.Event()
    calls = 0

    def broken():
        nonlocal calls
        calls += 1
        started.set()
        assert release.wait(2)
        raise ValueError("boom")

    with ThreadPoolExecutor(max_workers=2) as pool:
        leader = pool.submit(coordinator.run, ("impact", "repo"), broken, label="impact")
        assert started.wait(1)
        follower = pool.submit(coordinator.run, ("impact", "repo"), broken, label="impact")
        time.sleep(0.05)
        release.set()
        with pytest.raises(ValueError, match="boom"):
            leader.result()
        with pytest.raises(ValueError, match="boom"):
            follower.result()

    assert calls == 1
    assert coordinator.run(("impact", "repo"), lambda: "retry", label="impact") == "retry"


def test_heavy_work_coordinator_same_key_reentry_fails_fast():
    from codesextant.work_coordinator import HeavyWorkCoordinator

    coordinator = HeavyWorkCoordinator()
    finished = threading.Event()
    errors = []

    def outer():
        try:
            coordinator.run(
                ("map", "repo"),
                lambda: coordinator.run(
                    ("map", "repo"), lambda: None, label="nested"),
                label="outer",
            )
        except BaseException as exc:  # noqa: BLE001 - assertion captures exact failure
            errors.append(exc)
        finally:
            finished.set()

    threading.Thread(target=outer, daemon=True).start()

    assert finished.wait(0.5), "same-key reentry deadlocked"
    assert isinstance(errors[0], RuntimeError)
    assert "reentrant" in str(errors[0]).lower()


def test_heavy_work_coordinator_different_key_reentry_fails_fast():
    from codesextant.work_coordinator import HeavyWorkCoordinator

    coordinator = HeavyWorkCoordinator()
    finished = threading.Event()
    errors = []

    def outer():
        try:
            coordinator.run(
                ("map", "repo-a"),
                lambda: coordinator.run(
                    ("impact", "repo-b"), lambda: None, label="nested"),
                label="outer",
            )
        except BaseException as exc:  # noqa: BLE001 - assertion captures exact failure
            errors.append(exc)
        finally:
            finished.set()

    threading.Thread(target=outer, daemon=True).start()

    assert finished.wait(0.5), "different-key reentry deadlocked"
    assert isinstance(errors[0], RuntimeError)
    assert "reentrant" in str(errors[0]).lower()


def test_heavy_work_followers_receive_distinct_exception_objects():
    from codesextant.work_coordinator import HeavyWorkCoordinator

    coordinator = HeavyWorkCoordinator()
    started = threading.Event()
    release = threading.Event()

    def broken():
        started.set()
        assert release.wait(2)
        raise ValueError("boom")

    with ThreadPoolExecutor(max_workers=3) as pool:
        leader = pool.submit(coordinator.run, ("impact", "repo"), broken, label="impact")
        assert started.wait(1)
        follower_a = pool.submit(
            coordinator.run, ("impact", "repo"), broken, label="impact")
        follower_b = pool.submit(
            coordinator.run, ("impact", "repo"), broken, label="impact")
        time.sleep(0.05)
        release.set()
        caught = []
        for future in (leader, follower_a, follower_b):
            with pytest.raises(ValueError, match="boom") as info:
                future.result()
            caught.append(info.value)

    assert len({id(exc) for exc in caught}) == 3
    assert all(exc.__traceback__ is not None for exc in caught)


def test_heavy_work_followers_preserve_custom_exception_contract():
    from codesextant.work_coordinator import HeavyWorkCoordinator

    coordinator = HeavyWorkCoordinator()
    started = threading.Event()
    release = threading.Event()

    def broken():
        started.set()
        assert release.wait(2)
        raise daemon._HttpError(429, "retry later")

    with ThreadPoolExecutor(max_workers=2) as pool:
        leader = pool.submit(
            coordinator.run, ("impact", "repo"), broken, label="impact")
        assert started.wait(1)
        follower = pool.submit(
            coordinator.run, ("impact", "repo"), broken, label="impact")
        time.sleep(0.05)
        release.set()
        caught = []
        for future in (leader, follower):
            with pytest.raises(daemon._HttpError) as info:
                future.result()
            caught.append(info.value)

    assert caught[0] is not caught[1]
    assert [(exc.code, exc.msg) for exc in caught] == [
        (429, "retry later"), (429, "retry later")]


def test_heavy_work_exception_clone_preserves_builtin_exception_slots():
    from codesextant.work_coordinator import _clone_exception

    missing = FileNotFoundError(2, "missing", "C:/absent.py")
    missing_clone = _clone_exception(missing)
    assert missing_clone is not missing
    assert type(missing_clone) is FileNotFoundError
    assert missing_clone.args == missing.args
    assert missing_clone.errno == missing.errno
    assert missing_clone.filename == missing.filename
    assert str(missing_clone) == str(missing)

    decoding = UnicodeDecodeError("utf-8", b"x", 0, 1, "bad")
    decoding_clone = _clone_exception(decoding)
    assert decoding_clone is not decoding
    assert type(decoding_clone) is UnicodeDecodeError
    assert decoding_clone.args == decoding.args
    assert decoding_clone.encoding == decoding.encoding
    assert decoding_clone.object == decoding.object
    assert decoding_clone.start == decoding.start
    assert decoding_clone.end == decoding.end
    assert decoding_clone.reason == decoding.reason
    assert str(decoding_clone) == str(decoding)


def test_heavy_work_coordinator_caps_queue_and_followers():
    from codesextant.work_coordinator import (
        HeavyWorkCoordinator,
        HeavyWorkQueueFull,
    )

    coordinator = HeavyWorkCoordinator(queue_capacity=1, follower_capacity=1)
    started = threading.Event()
    release = threading.Event()

    def blocking():
        started.set()
        assert release.wait(2)
        return "done"

    with ThreadPoolExecutor(max_workers=4) as pool:
        active = pool.submit(coordinator.run, ("map", "a"), blocking, label="map")
        assert started.wait(1)
        queued = pool.submit(
            coordinator.run, ("map", "b"), lambda: "b", label="map")
        time.sleep(0.05)
        with pytest.raises(HeavyWorkQueueFull, match="queue capacity"):
            coordinator.run(("map", "c"), lambda: "c", label="map")
        follower = pool.submit(
            coordinator.run, ("map", "a"), blocking, label="map")
        time.sleep(0.05)
        with pytest.raises(HeavyWorkQueueFull, match="follower capacity"):
            coordinator.run(("map", "a"), blocking, label="map")
        release.set()
        assert active.result() == "done"
        assert follower.result() == "done"
        assert queued.result() == "b"

    snapshot = coordinator.snapshot()
    assert snapshot["queue_capacity"] == 1
    assert snapshot["follower_capacity"] == 1
    assert "oldest_queued_for_sec" in snapshot


def test_health_bypasses_heavy_route_coordinator(monkeypatch):
    class CoordinatorProbe:
        def run(self, *_args, **_kwargs):
            pytest.fail("/health must never enter the heavy queue")

        def snapshot(self):
            return {"active": None, "queued": 0, "followers": 0,
                    "active_for_sec": 0.0}

    monkeypatch.setattr(daemon, "_HEAVY_COORDINATOR", CoordinatorProbe())
    code, result = daemon._execute_route("/health", daemon._ep_health, None, None)
    assert code == 200
    assert result["service"] == "codesextant"


def test_heavy_http_route_uses_shared_coordinator(monkeypatch):
    from urllib.parse import urlparse

    calls = []

    class CoordinatorProbe:
        def run(self, key, work, *, label, shard=None, priority="batch"):
            calls.append((key, label, shard, priority))
            return work()

        def snapshot(self):
            return {"active": None, "queued": 0, "followers": 0,
                    "active_for_sec": 0.0}

    monkeypatch.setattr(daemon, "_HEAVY_COORDINATOR", CoordinatorProbe())
    body = {"project": "C:/repo", "symbol": "renderGameSettings"}
    result = daemon._execute_route(
        "/impact", lambda _parsed, _body: (200, {"ok": True}),
        urlparse("/impact"), body)

    assert result == (200, {"ok": True})
    assert len(calls) == 1
    assert calls[0][1] == "/impact"
    # Admission is sharded by repository so one project cannot queue behind
    # another project's expensive job.
    assert calls[0][2] == os.path.normcase(os.path.abspath("C:/repo"))
    assert calls[0][3] == "interactive"


def test_heavy_route_shards_distinct_projects_apart(monkeypatch):
    """Two repositories must land in different admission lanes."""
    from urllib.parse import urlparse

    shards = []

    class CoordinatorProbe:
        def run(self, key, work, *, label, shard=None, priority="batch"):
            shards.append(shard)
            return work()

    monkeypatch.setattr(daemon, "_HEAVY_COORDINATOR", CoordinatorProbe())
    for project in ("C:/repo-a", "C:/repo-b"):
        daemon._execute_route(
            "/impact", lambda _parsed, _body: (200, {"ok": True}),
            urlparse("/impact"), {"project": project, "symbol": "x"})

    assert len(set(shards)) == 2, f"projects shared one lane: {shards}"


def test_queue_rejection_returns_retry_after_and_load_telemetry(monkeypatch):
    from urllib.parse import urlparse

    class RejectingCoordinator:
        def run(self, *_args, **_kwargs):
            raise daemon.work_coordinator.HeavyWorkQueueFull("interactive queue full")

        def snapshot(self):
            return {"queued": 10, "queued_by_priority": {"interactive": 2}}

    monkeypatch.setattr(daemon, "_HEAVY_COORDINATOR", RejectingCoordinator())
    monkeypatch.setenv("CODESEXTANT_OVERLOAD_RETRY_AFTER_SEC", "7")

    with pytest.raises(daemon._HttpError) as info:
        daemon._execute_route(
            "/get_map", lambda _parsed, _body: (200, {}),
            urlparse("/get_map?project=C%3A%2Frepo"), None)

    error = info.value
    assert error.code == 503
    assert error.headers == {"Retry-After": "7"}
    assert error.details["retry_after_sec"] == 7
    assert error.details["heavy_work"]["queued"] == 10


def test_ai_usage_scan_is_admitted_as_heavy_work(monkeypatch, tmp_path):
    seen = []

    def capture_open(*_args, timeout=None, **_kwargs):
        seen.append(timeout)
        return _JsonResponse({"summary": {"files_scanned": 1}})

    monkeypatch.setenv("CODESEXTANT_HEAVY_TIMEOUT_SEC", "543")
    monkeypatch.setattr(client.urllib.request, "urlopen", capture_open)
    c = client.CodesextantClient(project=str(tmp_path), port=18807, timeout=5.0)

    assert "/ai_usage" in daemon._HEAVY_PATHS
    assert c.find_ai_usage() == {"summary": {"files_scanned": 1}}
    assert seen == [543.0]


def test_watcher_reindex_uses_same_heavy_coordinator(monkeypatch, tmp_path):
    from codesextant import watcher as watcher_module

    calls = []

    class CoordinatorProbe:
        def run(self, key, work, *, label, shard=None, priority="batch"):
            calls.append((key, label, priority))
            return work()

    monkeypatch.setattr(
        watcher_module.work_coordinator, "SHARED_SHARDED", CoordinatorProbe())
    monkeypatch.setattr(
        watcher_module.engine, "index_paths",
        lambda project, paths: {"indexed": len(paths), "skipped": 0, "removed": 0,
                                "project": project})
    logger = SimpleNamespace(info=lambda *_args, **_kwargs: None,
                             warning=lambda *_args, **_kwargs: None)
    project_watch = watcher_module._ProjectWatch(str(tmp_path), logger)
    project_watch._pending.add(str(tmp_path / "changed.py"))

    project_watch._flush()

    assert len(calls) == 1
    assert calls[0][1] == "watcher/reindex"
    assert calls[0][2] == "background"


def test_watcher_reindex_uses_generation_key_not_http_singleflight_key(
        monkeypatch, tmp_path):
    from codesextant import watcher as watcher_module

    keys = []

    class CoordinatorProbe:
        def run(self, key, work, *, label, shard=None, priority="batch"):
            keys.append(key)
            return work()

    monkeypatch.setattr(
        watcher_module.work_coordinator, "SHARED_SHARDED", CoordinatorProbe())
    monkeypatch.setattr(
        watcher_module.engine, "index_paths",
        lambda project, paths: {"indexed": len(paths), "skipped": 0, "removed": 0,
                                "project": project})
    logger = SimpleNamespace(info=lambda *_args, **_kwargs: None,
                             warning=lambda *_args, **_kwargs: None)
    project_watch = watcher_module._ProjectWatch(str(tmp_path), logger)

    project_watch._enqueue(str(tmp_path / "first.py"))
    project_watch._timer.cancel()
    project_watch._flush()
    project_watch._enqueue(str(tmp_path / "second.py"))
    project_watch._timer.cancel()
    project_watch._flush()

    http_key = watcher_module.work_coordinator.make_work_key(
        "/reindex", str(tmp_path), {"force": False})
    assert keys[0] != http_key
    assert keys[1] != http_key
    assert keys[0] != keys[1]


def test_watcher_batch_during_inflight_reindex_is_not_swallowed_by_join(
        monkeypatch, tmp_path):
    """Spec lost-update red test: a file changed after an old reindex started
    must trigger a real second index run once the old scan finishes, not be
    single-flight joined onto the stale in-flight scan's result."""
    from codesextant import watcher as watcher_module

    coordinator = watcher_module.work_coordinator.ShardedHeavyWork()
    monkeypatch.setattr(
        watcher_module.work_coordinator, "SHARED_SHARDED", coordinator)

    first_started = threading.Event()
    release_first = threading.Event()
    index_calls = []

    def slow_index(project, paths):
        index_calls.append((project, tuple(paths)))
        if len(index_calls) == 1:
            first_started.set()
            assert release_first.wait(timeout=10)
        return {"indexed": 1, "skipped": 0, "removed": 0}

    monkeypatch.setattr(watcher_module.engine, "index_paths", slow_index)
    logger = SimpleNamespace(info=lambda *_args, **_kwargs: None,
                             warning=lambda *_args, **_kwargs: None)
    project_watch = watcher_module._ProjectWatch(str(tmp_path), logger)

    project_watch._enqueue(str(tmp_path / "old_change.py"))
    project_watch._timer.cancel()
    old_scan = threading.Thread(target=project_watch._flush, daemon=True)
    old_scan.start()
    assert first_started.wait(timeout=5)  # old reindex is now mid-scan

    # The file changes while the old scan is still running.
    project_watch._enqueue(str(tmp_path / "changed_during_scan.py"))
    project_watch._timer.cancel()
    new_scan = threading.Thread(target=project_watch._flush, daemon=True)
    new_scan.start()

    # Wait until the second batch reached the coordinator: a queued FIFO job
    # (fixed behaviour) or a follower join (the lost-update bug).
    deadline = time.time() + 5
    while time.time() < deadline:
        snap = coordinator.snapshot()
        if snap["queued"] >= 1 or snap["followers"] >= 1:
            break
        time.sleep(0.01)
    release_first.set()
    old_scan.join(timeout=5)
    new_scan.join(timeout=5)
    assert not old_scan.is_alive() and not new_scan.is_alive()

    assert len(index_calls) == 2, (
        "batch enqueued during the in-flight reindex was swallowed by "
        "single-flight join instead of re-running")
    project_watch.stop()


def test_watcher_queue_rejection_keeps_pending_changes_and_schedules_retry(
        monkeypatch, tmp_path):
    from codesextant import watcher as watcher_module

    class RejectingCoordinator:
        def run(self, *_args, **_kwargs):
            raise watcher_module.work_coordinator.HeavyWorkQueueFull("full")

    monkeypatch.setattr(
        watcher_module.work_coordinator, "SHARED_SHARDED", RejectingCoordinator())
    monkeypatch.setattr(watcher_module, "_debounce_sec", lambda: 60.0)
    logger = SimpleNamespace(info=lambda *_args, **_kwargs: None,
                             warning=lambda *_args, **_kwargs: None)
    project_watch = watcher_module._ProjectWatch(str(tmp_path), logger)
    changed = str(tmp_path / "changed.py")
    project_watch._pending.add(changed)
    project_watch._generation = 7

    project_watch._flush()

    assert project_watch._pending == {changed}
    assert project_watch._timer is not None
    assert project_watch._timer.is_alive()
    project_watch.stop()


def test_watcher_overload_retries_back_off_exponentially(monkeypatch, tmp_path):
    """A saturated daemon must not receive another watcher attempt every debounce window."""
    from codesextant import watcher as watcher_module

    class RejectingCoordinator:
        def run(self, *_args, **_kwargs):
            raise watcher_module.work_coordinator.HeavyWorkQueueFull("full")

    monkeypatch.setattr(
        watcher_module.work_coordinator, "SHARED_SHARDED", RejectingCoordinator())
    monkeypatch.setattr(watcher_module, "_debounce_sec", lambda: 2.0)
    monkeypatch.setattr(watcher_module.random, "uniform", lambda _low, _high: 1.0)
    logger = SimpleNamespace(info=lambda *_args, **_kwargs: None,
                             warning=lambda *_args, **_kwargs: None)
    project_watch = watcher_module._ProjectWatch(str(tmp_path), logger)
    project_watch._pending.add(str(tmp_path / "changed.py"))
    delays = []
    project_watch._arm_timer_locked = lambda delay=None: delays.append(delay)

    project_watch._flush()
    project_watch._flush()
    project_watch._flush()

    assert delays == [2.0, 4.0, 8.0]


def test_watcher_stop_prevents_callbacks_from_rearming_timer(tmp_path):
    from codesextant import watcher as watcher_module

    logger = SimpleNamespace(info=lambda *_args, **_kwargs: None,
                             warning=lambda *_args, **_kwargs: None)
    project_watch = watcher_module._ProjectWatch(str(tmp_path), logger)

    project_watch.stop()
    project_watch._enqueue(str(tmp_path / "late.py"))

    assert project_watch._pending == set()
    assert project_watch._timer is None


def test_stale_watcher_callback_cannot_clear_new_timer_reference(
        monkeypatch, tmp_path):
    from codesextant import watcher as watcher_module

    delays = iter((0.01, 60.0))
    monkeypatch.setattr(watcher_module, "_debounce_sec", lambda: next(delays))
    logger = SimpleNamespace(info=lambda *_args, **_kwargs: None,
                             warning=lambda *_args, **_kwargs: None)
    project_watch = watcher_module._ProjectWatch(str(tmp_path), logger)
    project_watch._lock.acquire()
    try:
        project_watch._pending.add(str(tmp_path / "first.py"))
        project_watch._generation += 1
        project_watch._arm_timer_locked()
        stale_timer = project_watch._timer
        time.sleep(0.05)  # stale callback has started and is waiting on _lock
        project_watch._pending.add(str(tmp_path / "second.py"))
        project_watch._generation += 1
        stale_timer.cancel()
        project_watch._arm_timer_locked()
        current_timer = project_watch._timer
    finally:
        project_watch._lock.release()

    stale_timer.join(timeout=1)

    assert project_watch._timer is current_timer
    assert current_timer.is_alive()
    project_watch.stop()
    current_timer.join(timeout=1)
    assert not current_timer.is_alive()


def test_links_scan_is_admitted_as_heavy_work():
    assert "/links" in daemon._HEAVY_PATHS


def _healthy_payload_with_heavy(active, active_for_sec, port):
    return {
        "service": "codesextant", "pid": 7, "port": port,
        "heavy_work": {
            "active": active, "active_for_sec": active_for_sec,
            "queued": 0, "followers": 0,
            "queue_capacity": 8, "follower_capacity": 8,
        },
    }


def test_supervisor_recycles_daemon_when_heavy_job_stuck_beyond_threshold(
        monkeypatch):
    """A permanently stuck heavy job keeps /health green (control plane is
    isolated by design), so the supervisor must consume the active-age
    telemetry and recycle the daemon instead of reporting healthy forever."""
    from codesextant import supervisor

    monkeypatch.setenv("CODESEXTANT_HEAVY_STUCK_SEC", "1800")
    calls = []
    monkeypatch.setattr(
        supervisor.daemon, "http_ping",
        lambda **_kwargs: _healthy_payload_with_heavy("/get_map", 5400.0, 18808))
    monkeypatch.setattr(
        supervisor.daemon, "stop_running",
        lambda **kwargs: calls.append(("stop", kwargs)) or
        {"action": "stopped", "pid": 7, "port_released": True})
    monkeypatch.setattr(
        supervisor.daemon, "ensure_running",
        lambda **kwargs: calls.append(("ensure", kwargs)) or
        {"action": "spawned", "pid": 8, "port": 18808})

    result = supervisor.supervise_once(port=18808)

    assert [name for name, _ in calls] == ["stop", "ensure"]
    assert result["action"] == "spawned"
    assert result["recovered_from"] == "heavy-stuck"


def test_supervisor_leaves_long_but_unstuck_heavy_job_alone(monkeypatch):
    """A legitimate multi-minute cold map below the threshold must never be
    recycled: killing it would lose real work and amplify load."""
    from codesextant import supervisor

    monkeypatch.setenv("CODESEXTANT_HEAVY_STUCK_SEC", "1800")
    monkeypatch.setattr(
        supervisor.daemon, "http_ping",
        lambda **_kwargs: _healthy_payload_with_heavy("/get_map", 540.0, 18809))
    monkeypatch.setattr(
        supervisor.daemon, "stop_running",
        lambda **_kwargs: pytest.fail("job below stuck threshold must not be killed"))
    monkeypatch.setattr(
        supervisor.daemon, "ensure_running",
        lambda **_kwargs: pytest.fail("healthy daemon must not be respawned"))

    assert supervisor.supervise_once(port=18809)["action"] == "healthy"


def test_supervisor_stuck_recovery_switch_off_disables_recycling(monkeypatch):
    """The feature must be switchable: setting it to 0 disables it entirely."""
    from codesextant import supervisor

    monkeypatch.setenv("CODESEXTANT_HEAVY_STUCK_SEC", "0")
    monkeypatch.setattr(
        supervisor.daemon, "http_ping",
        lambda **_kwargs: _healthy_payload_with_heavy("/get_map", 999999.0, 18810))
    monkeypatch.setattr(
        supervisor.daemon, "stop_running",
        lambda **_kwargs: pytest.fail("switch off must disable stuck recycling"))
    monkeypatch.setattr(
        supervisor.daemon, "ensure_running",
        lambda **_kwargs: pytest.fail("switch off must disable stuck recycling"))

    assert supervisor.supervise_once(port=18810)["action"] == "healthy"


def test_supervisor_tolerates_health_payload_without_heavy_telemetry(monkeypatch):
    """An older daemon with no heavy_work field, or garbage telemetry, maps to
    plain healthy. The watchdog must not crash, and it must not recycle the
    daemon over nothing."""
    from codesextant import supervisor

    monkeypatch.setenv("CODESEXTANT_HEAVY_STUCK_SEC", "1800")
    monkeypatch.setattr(
        supervisor.daemon, "http_ping",
        lambda **_kwargs: {"service": "codesextant", "pid": 7, "port": 18814,
                           "heavy_work": {"active": "/get_map",
                                          "active_for_sec": "not-a-number"}})
    monkeypatch.setattr(
        supervisor.daemon, "stop_running",
        lambda **_kwargs: pytest.fail("bad telemetry must not trigger recycling"))
    monkeypatch.setattr(
        supervisor.daemon, "ensure_running",
        lambda **_kwargs: pytest.fail("bad telemetry must not trigger recycling"))

    assert supervisor.supervise_once(port=18814)["action"] == "healthy"
