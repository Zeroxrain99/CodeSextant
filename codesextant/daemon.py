"""Local HTTP daemon shared by CodeSextant clients.

The daemon exposes the engine through a ``ThreadingHTTPServer`` on a fixed local
port. Startup probes ``/health`` and verifies the service identity before
starting another process. Each repository has a separate SQLite database keyed
by its absolute path.

Main endpoints:
    GET  /health
    GET  /get_symbols?project=<repo>&file=<file>
    POST /find_references  {project, symbol, ...}
    GET  /get_map?project=<repo>&budget=<n>
    POST /reindex          {project, force?}
    GET  /status?project=<repo>

Startup, endpoint access, and errors are written to ``daemon.log`` under
``~/.codesextant`` by default.
"""
from __future__ import annotations

import sys

# Preserve non-ASCII paths and symbols in Windows console output.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import importlib
import importlib.util
import ipaddress
import json
import logging
import math
import os
import secrets
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

# Clients only need ensure/http_ping; do not load the full tree-sitter engine at client import time.
# storage is lightweight and required for locking/paths; engine/panel/watcher are lazy-loaded only
# when the daemon actually serves or an endpoint gets hit.
if not __package__:  # pragma: no cover - compatibility fallback for running this file directly
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_PACKAGE = __package__ or "codesextant"
storage = importlib.import_module(f"{_PACKAGE}.storage")
project_state = importlib.import_module(f"{_PACKAGE}.project_state")
work_coordinator = importlib.import_module(f"{_PACKAGE}.work_coordinator")
local_auth = importlib.import_module(f"{_PACKAGE}.local_auth")
_lazy_import = importlib.import_module(f"{_PACKAGE}.lazy_import")


# The TYPE_CHECKING branch never runs. It exists so static analysis -- jedi included,
# which is what CodeSextant resolves references with -- can see what these names are;
# a call through an unannotated proxy resolves to nothing at all.
if TYPE_CHECKING:
    from . import cache_gc, engine, panel, watcher, worker_process
    from .lazy_import import LazyModule
else:
    LazyModule = _lazy_import.LazyModule
    engine = LazyModule(f"{_PACKAGE}.engine")
    panel = LazyModule(f"{_PACKAGE}.panel")
    watcher = LazyModule(f"{_PACKAGE}.watcher")
    cache_gc = LazyModule(f"{_PACKAGE}.cache_gc")
    worker_process = LazyModule(f"{_PACKAGE}.worker_process")
_HEAVY_COORDINATOR = work_coordinator.SHARED_SHARDED

# File-watcher manager, built lazily and shared across projects.
_WATCH_MGR = None
_WATCH_MGR_LOCK = threading.Lock()
_ACTIVE_SERVER = None
_RECOVERY_THREADS: dict[str, tuple[threading.Thread, float]] = {}
_RECOVERY_THREADS_LOCK = threading.Lock()
_DAEMON_PROJECT_KEYS: set[str] = set()
_DAEMON_PROJECT_KEYS_LOCK = threading.Lock()


def _notify_daemon_activity() -> None:
    server = _ACTIVE_SERVER
    if server is not None and hasattr(server, "note_activity"):
        server.note_activity()


def _get_watch_mgr():
    global _WATCH_MGR
    if _WATCH_MGR is None:
        with _WATCH_MGR_LOCK:
            if _WATCH_MGR is None:
                _WATCH_MGR = watcher.WatchManager(
                    get_logger(), on_activity=_notify_daemon_activity)
    return _WATCH_MGR


def _recovery_timeout_sec() -> float:
    try:
        return max(1.0, float(os.environ.get(
            "CODESEXTANT_RECOVERY_TIMEOUT_SEC", "900")))
    except (TypeError, ValueError):
        return 900.0


def _schedule_project_recovery(manager, project: str) -> dict:
    """Start at most one stale-while-revalidate recovery for a project."""
    project_id = storage.project_key(project)
    state = manager.recovery_state(project)
    if state == "ready":
        return {"recovery": "ready", "stale_possible": False}
    with _RECOVERY_THREADS_LOCK:
        current = _RECOVERY_THREADS.get(project_id)
        if current is not None and current[0].is_alive():
            return {"recovery": "running", "stale_possible": True}

        def recover_in_background() -> None:
            try:
                manager.ensure_ready(
                    project,
                    deadline=time.monotonic() + _recovery_timeout_sec(),
                )
            except work_coordinator.HeavyWorkQueueFull as exc:
                get_logger().warning(
                    "first-query background recovery deferred project=%s: %s",
                    project_id[:12], exc)
            except work_coordinator.HeavyWorkDeadlineExceeded as exc:
                get_logger().warning(
                    "first-query background recovery expired project=%s: %s",
                    project_id[:12], exc)
            except Exception as exc:
                get_logger().exception(
                    "first-query background recovery failed project=%s: %s",
                    project_id[:12], exc)
            finally:
                with _RECOVERY_THREADS_LOCK:
                    current_task = _RECOVERY_THREADS.get(project_id)
                    if current_task is not None and current_task[0] is threading.current_thread():
                        _RECOVERY_THREADS.pop(project_id, None)

        thread = threading.Thread(
            target=recover_in_background,
            name=f"codesextant-recovery-{project_id[:12]}",
            daemon=False,
        )
        _RECOVERY_THREADS[project_id] = (thread, time.monotonic())
        thread.start()
    return {"recovery": "scheduled", "stale_possible": True}


def _recovery_snapshot() -> list[dict]:
    now = time.monotonic()
    with _RECOVERY_THREADS_LOCK:
        return [
            {
                "project_id": project_id[:12],
                "age_sec": round(max(0.0, now - started_at), 3),
            }
            for project_id, (thread, started_at) in _RECOVERY_THREADS.items()
            if thread.is_alive()
        ]


def _join_recovery_threads() -> None:
    """Keep daemon ownership until every scheduled recovery has stopped."""
    while True:
        with _RECOVERY_THREADS_LOCK:
            threads = [
                thread for thread, _started_at in _RECOVERY_THREADS.values()
                if thread.is_alive()
            ]
        if not threads:
            return
        for thread in threads:
            thread.join()


def _cache_policy_snapshot() -> dict:
    try:
        policy = cache_gc.policy_from_env()
        return {
            "available": True,
            "max_bytes": policy.max_bytes,
            "target_bytes": policy.target_bytes,
            "missing_grace_seconds": policy.missing_grace_seconds,
            "idle_grace_seconds": policy.idle_grace_seconds,
            "scratch_grace_seconds": policy.scratch_grace_seconds,
        }
    except Exception as exc:
        return {"available": False, "error": type(exc).__name__}


def _record_cache_project(project: str) -> str:
    project_id = storage.project_key(project)
    with _DAEMON_PROJECT_KEYS_LOCK:
        _DAEMON_PROJECT_KEYS.add(project_id)
    return project_id


def _touch_cache_project(project: str) -> None:
    project_id = _record_cache_project(project)
    try:
        cache_gc.touch_project(project)
    except Exception as exc:
        get_logger().warning(
            "cache access marker failed project=%s: %s",
            project_id[:12], type(exc).__name__)


def _prune_cache_if_quiescent(active_projects: tuple[str, ...]) -> dict:
    heavy = _HEAVY_COORDINATOR.snapshot()
    if _ACTIVE_SERVER is not None or _health_has_heavy_work({"heavy_work": heavy}):
        return {"action": "skipped", "reason": "work-active"}
    with _DAEMON_PROJECT_KEYS_LOCK:
        touched = set(_DAEMON_PROJECT_KEYS)
    touched.update(storage.project_key(project) for project in active_projects)
    excluded = tuple(sorted(touched))
    try:
        report = cache_gc.prune(exclude_project_keys=excluded)
    except Exception as exc:
        get_logger().warning("cache prune failed: %s", type(exc).__name__)
        return {"action": "failed", "error": type(exc).__name__}
    get_logger().info(
        "cache prune complete before=%s after=%s reclaimed=%s projects=%s errors=%s",
        report.get("before_bytes"), report.get("after_bytes"),
        report.get("reclaimed_bytes"), len(report.get("projects", [])),
        len(report.get("errors", [])))
    return {"action": "completed", **report}

# ── Service constants ──
SERVICE_NAME = "codesextant"          # liveness-probe brand (also accepts the "codesextant" product name, see _health_brand_ok)
API_VERSION = 2
HOST = "127.0.0.1"
DEFAULT_PORT = 8790
_BROWSER_SESSIONS = local_auth.BrowserSessionStore()


class _InterprocessFileLock:
    """Crash-safe cross-process byte lock backed by the local filesystem.

    Windows uses ``msvcrt.locking`` and POSIX uses ``fcntl.flock``.  The OS
    releases the lock automatically when a process exits, so a crashed daemon
    cannot leave a permanent stale lock behind.
    """

    def __init__(self, path: str | Path, *, timeout: float = 0.0,
                 poll_sec: float = 0.05):
        self.path = Path(path)
        self.timeout = max(0.0, float(timeout))
        self.poll_sec = max(0.01, float(poll_sec))
        self._fh = None
        self._acquired = False

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Do not use `with` here. The file handle is the lock itself and must
        # stay open until release() closes it. Wrapping it in a context manager would
        # close the file the moment this function returns, releasing the lock
        # immediately, and multiple daemons could then race to grab the same port.
        # The linter's SIM115 warning is a false positive in this situation.
        self._fh = open(self.path, "a+b")  # noqa: SIM115

        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._seed_lock_byte()
                self._fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover - Windows is the production target
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._acquired = True
                return self
            except (OSError, BlockingIOError) as exc:
                if time.monotonic() >= deadline:
                    self._fh.close()
                    self._fh = None
                    # Keep the original exception chain: which OS error occurred
                    # (permissions? disk?) determines how to debug it. Reporting
                    # only "lock busy" would throw away that diagnostic clue.
                    raise TimeoutError(f"lock busy: {self.path}") from exc
                time.sleep(self.poll_sec)

    def _seed_lock_byte(self) -> None:
        """Ensure byte 0 exists to lock, treating a rival's hold as contention.

        Windows locks a byte range, so the file needs a byte to lock. Creating it is a
        write to the exact byte another process may already hold, and Windows answers
        that with PermissionError. That is not a failure to report: it means someone
        else won the race and already seeded the byte, which is precisely the state the
        caller was trying to reach. Running inside the retry loop turns it into one more
        wait, so two agents calling ensure() at the same moment queue instead of one of
        them crashing.
        """
        self._fh.seek(0, os.SEEK_END)
        if self._fh.tell() == 0:
            self._fh.write(b"\0")
            self._fh.flush()

    def release(self):
        if self._fh is None:
            return
        try:
            if self._acquired:
                self._fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover - Windows is the production target
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._acquired = False
            self._fh.close()
            self._fh = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, _exc_type, _exc, _tb):
        self.release()
        return False


def _daemon_lock_path(port: int, kind: str) -> Path:
    return storage.default_db_dir() / f"daemon-{port}.{kind}.lock"


def _instance_lock_held(port: int) -> bool | None:
    """Return whether a live CodeSextant process owns this port's lifetime lock.

    A CPU-bound map can briefly starve the threaded ``/health`` handler long
    enough for every bounded HTTP probe to time out.  The OS-backed instance
    lock is independent of the GIL and is released automatically on process
    exit, so listener + held port-specific lock is a safe degraded ownership
    proof without accepting an unrelated service on the same port.
    """
    # Every ownership checker must first serialize its *probe*.  Otherwise two
    # simultaneous checkers can see each other's millisecond-long test lock and
    # falsely conclude that a lifetime daemon owns it.
    probe_guard = _InterprocessFileLock(
        _daemon_lock_path(port, "instance-probe"), timeout=1.0)
    try:
        probe_guard.acquire()
    except TimeoutError:
        # Contention is not proof that the lifetime lock is held.  Report an
        # explicit unknown state so callers fail closed without claiming a
        # healthy/already-running owner.
        return None
    try:
        probe = _InterprocessFileLock(
            _daemon_lock_path(port, "instance"), timeout=0.0)
        try:
            probe.acquire()
        except TimeoutError:
            return True
        else:
            probe.release()
            return False
    finally:
        probe_guard.release()


def _instance_owner_result(port: int) -> dict | None:
    """Return crash-safe ownership state without claiming API compatibility.

    The lifetime lock proves that a CodeSextant process owns this daemon slot.
    It does not prove that the listener speaks the current authentication or
    API protocol. Callers must therefore fail fast instead of reusing it.
    """
    held = _instance_lock_held(port)
    if held is False:
        return None
    if held is None:
        return {
            "action": "ownership-unknown",
            "pid": None,
            "port": port,
            "health": None,
            "health_proof": "instance-lock-unknown",
        }
    if _daemon_lock_path(port, "draining").exists():
        return {
            "action": "daemon-draining",
            "pid": None,
            "port": port,
            "health": None,
            "health_proof": "instance-lock-draining",
        }
    return {
        "action": "owner-alive-unverified",
        "pid": None,
        "port": port,
        "health": None,
        "health_proof": "instance-lock-only",
    }


class _IdleShutdownController:
    """One-shot, event-driven idle shutdown with no periodic probe loop."""

    def __init__(self, *, timeout_sec: float, shutdown, busy,
                 timer_factory=threading.Timer, clock=time.monotonic):
        self.timeout_sec = max(0.0, float(timeout_sec))
        self._shutdown = shutdown
        self._busy = busy
        self._timer_factory = timer_factory
        self._clock = clock
        self._lock = threading.Lock()
        self._timer = None
        self._active_requests = 0
        self._generation = 0
        self._closed = False
        self._last_activity = self._clock()

    def start(self) -> None:
        with self._lock:
            self._arm_locked()

    def begin_request(self) -> bool:
        """Track an accepted handler, or reject it once shutdown has begun."""
        with self._lock:
            if self._closed:
                return False
            self._active_requests += 1
            self._cancel_locked()
            return True

    def end_request(self) -> None:
        with self._lock:
            if self._active_requests > 0:
                self._active_requests -= 1
            if self._active_requests == 0:
                self._arm_locked()

    def touch(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._last_activity = self._clock()
            if self._active_requests == 0:
                self._arm_locked()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cancel_locked()

    def _cancel_locked(self) -> None:
        self._generation += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _arm_locked(self) -> None:
        self._cancel_locked()
        if self._closed or self.timeout_sec <= 0:
            return
        generation = self._generation
        remaining = max(
            0.001,
            self.timeout_sec - (self._clock() - self._last_activity),
        )
        timer = self._timer_factory(
            remaining,
            lambda: self._on_timeout(generation),
        )
        timer.daemon = True
        self._timer = timer
        timer.start()

    def _on_timeout(self, generation: int) -> None:
        should_shutdown = False
        with self._lock:
            if self._closed or generation != self._generation:
                return
            self._timer = None
            if self._active_requests or self._busy():
                # Busy work is itself the event. Rebase the next one-shot check
                # instead of spinning a near-zero timer after the idle deadline.
                self._last_activity = self._clock()
                self._arm_locked()
                return
            self._closed = True
            should_shutdown = True
        if should_shutdown:
            self._shutdown()


class _ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """HTTP server that cannot share a listen socket with another PID.

    ``HTTPServer`` sets ``allow_reuse_address = True``.  On Windows that means
    four independently started processes can all LISTEN on 127.0.0.1:8790.
    Disable reuse and request SO_EXCLUSIVEADDRUSE as a second guardrail.
    """

    allow_reuse_address = False
    allow_reuse_port = False
    daemon_threads = False
    block_on_close = True
    request_queue_size = 64

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            timeout_sec = float(os.environ.get(
                "CODESEXTANT_IDLE_TIMEOUT_SEC", "10800"))
        except ValueError:
            timeout_sec = 10800.0
        try:
            handler_limit = max(1, int(os.environ.get(
                "CODESEXTANT_MAX_HANDLER_THREADS", "64")))
        except ValueError:
            handler_limit = 64
        try:
            self._preauth_timeout_sec = max(0.1, float(os.environ.get(
                "CODESEXTANT_PREAUTH_TIMEOUT_SEC", "5")))
        except ValueError:
            self._preauth_timeout_sec = 5.0
        self._handler_slots = threading.BoundedSemaphore(handler_limit)
        # BoundedSemaphore publishes no count, so occupancy is tracked alongside it.
        # This exists so a caller can wait for "a handler slot is held" instead of
        # sleeping and assuming it: the accept loop takes the slot on its own thread,
        # and nothing else offers a way to observe that it has.
        self._handler_state = threading.Condition()
        self._active_handlers = 0
        self._idle_shutdown = _IdleShutdownController(
            timeout_sec=timeout_sec,
            shutdown=self._shutdown_for_idle,
            busy=self._background_busy,
        )

    def _note_handler_started(self) -> None:
        with self._handler_state:
            self._active_handlers += 1
            self._handler_state.notify_all()

    def _note_handler_finished(self) -> None:
        with self._handler_state:
            self._active_handlers -= 1
            self._handler_state.notify_all()

    @property
    def active_handlers(self) -> int:
        """How many handler slots are currently held."""
        with self._handler_state:
            return self._active_handlers

    def wait_for_active_handlers(self, at_least: int, timeout: float = 5.0) -> bool:
        """Block until at least ``at_least`` handler slots are held. True if reached."""
        deadline = time.monotonic() + timeout
        with self._handler_state:
            while self._active_handlers < at_least:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._handler_state.wait(remaining)
            return True

    def _shutdown_for_idle(self) -> None:
        get_logger().info(
            "daemon idle timeout reached with no active work; shutting down")
        self.shutdown()

    @staticmethod
    def _reject_socket(request, status: str, message: str) -> None:
        body = message.encode("utf-8")
        response = (
            f"HTTP/1.1 {status}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii") + body
        try:
            request.sendall(response)
            request.shutdown(socket.SHUT_WR)
            # On Windows, closing with unread request bytes can turn the close
            # into a reset and discard the 503 already sent. Drain only a small,
            # bounded amount so the rejection remains visible without creating
            # another unbounded pre-auth wait.
            request.settimeout(0.02)
            drained = 0
            while drained < 16_384:
                chunk = request.recv(min(4096, 16_384 - drained))
                if not chunk:
                    break
                drained += len(chunk)
                if b"\r\n\r\n" in chunk:
                    break
        except OSError:
            pass

    def get_request(self):
        request, client_address = super().get_request()
        request.settimeout(self._preauth_timeout_sec)
        return request, client_address

    def process_request(self, request, client_address):
        """Reserve capacity and account for a request before its thread starts."""
        if not self._handler_slots.acquire(blocking=False):
            self._reject_socket(
                request,
                "503 Service Unavailable",
                "CodeSextant handler capacity reached; retry later",
            )
            self.shutdown_request(request)
            return
        if not self._idle_shutdown.begin_request():
            self._handler_slots.release()
            self._reject_socket(
                request,
                "503 Service Unavailable",
                "CodeSextant is shutting down; retry to start a fresh daemon",
            )
            self.shutdown_request(request)
            return
        self._note_handler_started()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._note_handler_finished()
            self._idle_shutdown.end_request()
            self._handler_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._note_handler_finished()
            self._idle_shutdown.end_request()
            self._handler_slots.release()

    def _background_busy(self) -> bool:
        heavy = _HEAVY_COORDINATOR.snapshot()
        if (heavy.get("active") is not None or heavy.get("queued", 0)
                or heavy.get("global_in_use", 0)
                or heavy.get("global_waiting", 0)):
            return True
        if _WATCH_MGR is not None:
            try:
                if _WATCH_MGR.has_pending_work():
                    return True
            except AttributeError:
                pass
        with _RECOVERY_THREADS_LOCK:
            return any(thread.is_alive() for thread, _started in _RECOVERY_THREADS.values())

    def note_activity(self) -> None:
        self._idle_shutdown.touch()

    def initiate_shutdown(self) -> None:
        """Stop accepting new handlers before a graceful shutdown begins."""
        self._idle_shutdown.close()
        self.shutdown()

    def serve_forever(self, poll_interval=0.5):
        self._idle_shutdown.start()
        try:
            return super().serve_forever(poll_interval=poll_interval)
        finally:
            self._idle_shutdown.close()

    def server_close(self):
        self._idle_shutdown.close()
        return super().server_close()

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        return super().server_bind()


def _port() -> int:
    """Return the configured daemon port, defaulting to 8790."""
    try:
        return int(os.environ.get("CODESEXTANT_PORT", str(DEFAULT_PORT)))
    except ValueError:
        return DEFAULT_PORT


# ── log (observability) ──
def _log_path() -> Path:
    """daemon.log defaults to ~/.codesextant/daemon.log, in the same directory as the SQLite database.
    Overridable via CODESEXTANT_HOME (for test isolation; reuses storage.default_db_dir)."""
    d = storage.default_db_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "daemon.log"


_logger: logging.Logger | None = None
_LOGGER_LOCK = threading.Lock()


class _CopyTruncateRotatingFileHandler(RotatingFileHandler):
    """Rotate without renaming the active file (which Windows readers can lock).

    The stdlib handler renames ``daemon.log`` and each numbered backup.  A
    second process merely reading/opening any of those files can deny delete
    sharing on Windows and make every subsequent log emit print WinError 32.
    Copying to a unique archive and truncating our own open stream avoids both
    rename operations.  Locked stale archives are pruned on a later rollover.
    """

    def doRollover(self):
        if self.stream is None:
            self.stream = self._open()
        self.stream.flush()
        base = Path(self.baseFilename)
        archive = base.with_name(
            f"{base.name}.{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{time.time_ns()}")
        try:
            shutil.copyfile(base, archive)
        except FileNotFoundError:
            return

        self.stream.seek(0)
        self.stream.truncate(0)
        self.stream.seek(0, os.SEEK_END)

        archives = sorted(
            base.parent.glob(f"{base.name}.*"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for stale in archives[self.backupCount:]:
            try:
                stale.unlink()
            except PermissionError:
                pass


def get_logger(*, file_output: bool = False) -> logging.Logger:
    """Return the process logger; only the serving daemon owns ``daemon.log``.

    Wrapper/control-plane processes call ``ensure_running`` too.  Giving each
    one a file handler made them race the real daemon's rollover.  They now log
    to stderr only; ``serve`` explicitly upgrades the singleton with the one
    rotating file handler.
    """
    global _logger
    if (_logger is not None
            and (not file_output or any(
                isinstance(h, _CopyTruncateRotatingFileHandler)
                for h in _logger.handlers))):
        return _logger
    with _LOGGER_LOCK:
        if _logger is None:
            lg = logging.getLogger("codesextant.daemon")
            lg.setLevel(logging.INFO)
            lg.propagate = False
            for existing in list(lg.handlers):
                lg.removeHandler(existing)
                existing.close()
            fmt = logging.Formatter(
                "%(asctime)s [%(levelname)s] pid=%(process)d %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            sh = logging.StreamHandler(sys.stderr)
            sh.setFormatter(fmt)
            lg.addHandler(sh)
            _logger = lg
        else:
            lg = _logger
            if lg.handlers:
                fmt = lg.handlers[0].formatter or logging.Formatter("%(message)s")
            else:
                fmt = logging.Formatter(
                    "%(asctime)s [%(levelname)s] pid=%(process)d %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
                sh = logging.StreamHandler(sys.stderr)
                sh.setFormatter(fmt)
                lg.addHandler(sh)

        if file_output and not any(
                isinstance(h, _CopyTruncateRotatingFileHandler) for h in lg.handlers):
            try:
                fh = _CopyTruncateRotatingFileHandler(
                    _log_path(), maxBytes=2_000_000, backupCount=3, encoding="utf-8")
                fh.setFormatter(fmt)
                lg.addHandler(fh)
            except Exception as exc:  # a failed file handler should not crash the daemon; fall back to stderr only
                sys.stderr.write(
                    f"[codesextant daemon] failed to open log file (falling back to stderr): {exc}\n")
        return lg


# ── liveness probe (strict: checks whether the /health brand matches, not merely whether the port is open) ──
def _health_brand_ok(data: dict) -> bool:
    """Accept only a health response that identifies the CodeSextant service."""
    return isinstance(data, dict) and data.get("service") in (SERVICE_NAME, "codesextant")


def http_ping(host: str = HOST, port: int | None = None, timeout: float = 0.6) -> dict | None:
    """Strict liveness probe: sends GET /health and returns the parsed dict (only if the brand
    matches, otherwise None). Returning a dict instead of a bool gives the caller extra info like
    pid (ensure uses this as proof of the singleton)."""
    port = port or _port()
    try:
        request = urllib.request.Request(
            f"http://{host}:{port}/health",
        )
        for name, value in local_auth.request_headers(
                "GET", "/health").items():
            request.add_unredirected_header(name, value)
        with urllib.request.urlopen(request, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data if _health_brand_ok(data) else None
    except Exception:
        return None


def _auth_challenge(host: str = HOST, port: int | None = None,
                    timeout: float = 0.6) -> dict | None:
    """Identify an incompatible local daemon without sending any secret."""
    port = port or _port()
    request = urllib.request.Request(f"http://{host}:{port}/health")
    try:
        urllib.request.urlopen(request, timeout=timeout).close()
    except urllib.error.HTTPError as exc:
        api_version = exc.headers.get("X-CodeSextant-API-Version")
        scheme = exc.headers.get("WWW-Authenticate")
        if exc.code == 401 and api_version and scheme:
            return {"scheme": scheme, "api_version": api_version}
    except Exception:
        pass
    return None


def _auth_state_result(challenge: dict | None, port: int) -> dict | None:
    if not challenge:
        return None
    scheme = str(challenge.get("scheme") or "")
    common = {
        "port": port,
        "current_api_version": challenge.get("api_version"),
        "current_auth_scheme": scheme,
        "required_api_version": API_VERSION,
        "required_auth_scheme": local_auth.AUTH_SCHEME,
    }
    if scheme == local_auth.AUTH_SCHEME:
        return {"action": "authentication-mismatch", **common}
    return {"action": "upgrade-required-auth", **common}


def is_port_listening(host: str = HOST, port: int | None = None, timeout: float = 0.3) -> bool:
    """Bare TCP liveness probe (only checks whether something is listening on the port, ignores
    brand). For diagnostics/stop decisions only. Singleton determination always uses http_ping
    (strict brand check)."""
    port = port or _port()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _slow_health_timeout(wait_sec: float) -> float:
    """Fast health checks stay cheap; an occupied port gets one slower brand proof.

    A busy but valid daemon can occasionally miss the 0.6s fast probe on a
    loaded Windows desktop.  Treating that as a foreign port makes every Skill
    invocation fail even though the same /health answers moments later. Keep
    the confirmation bounded and configurable instead of globally inflating
    every client liveness check.
    """
    try:
        configured = float(os.environ.get(
            "CODESEXTANT_HEALTH_CONFIRM_TIMEOUT_SEC", "3.0"))
    except ValueError:
        configured = 3.0
    return min(max(1.0, configured), max(1.0, float(wait_sec)))


def _health_api_current(health: dict) -> bool:
    return health.get("api_version") == API_VERSION


def _health_has_heavy_work(health: dict) -> bool:
    heavy = health.get("heavy_work")
    if not isinstance(heavy, dict):
        return True
    return bool(
        heavy.get("active") is not None
        or heavy.get("active_jobs")
        or heavy.get("queued", 0)
        or heavy.get("queued_jobs")
        or heavy.get("followers", 0)
        or heavy.get("global_in_use", 0)
        or heavy.get("global_waiting", 0)
    )


def _upgrade_required_result(health: dict, port: int, *, busy: bool) -> dict:
    return {
        "action": "upgrade-required-busy" if busy else "upgrade-required",
        "pid": health.get("pid"),
        "port": port,
        "current_api_version": health.get("api_version"),
        "required_api_version": API_VERSION,
        "health": health,
    }


# ── endpoint routing table (table-driven: adding an endpoint means adding one entry, aligned with the code skill's OCP) ──
# Each entry: method → {path: (handler, needs body?)}
def _q(parsed, key: str, default=None):
    """Get a single value from the query string (parse_qs returns a list; take the first item)."""
    vals = parse_qs(parsed.query).get(key)
    return vals[0] if vals else default


def _require_project(project: str | None):
    """Every data endpoint requires project (= repo absolute path). Missing → 400."""
    if not project:
        raise _HttpError(400, "missing required parameter project (= repo absolute path)")
    return project


def _request_project(parsed, body: dict | None) -> str | None:
    project = (body or {}).get("project")
    if project is None and parsed is not None:
        project = _q(parsed, "project")
    return str(project) if project else None


def _prepare_project(path: str, parsed, body: dict | None,
                     *, deadline: float | None = None) -> dict | None:
    """Attach and recover only the project selected by this request."""
    project = _request_project(parsed, body)
    if not project:
        return None
    if path == "/status":
        # Status is the diagnostic escape hatch when indexing is unhealthy.
        # Do not perform cache IO, construct a watcher, or enter recovery
        # before reporting load.
        _record_cache_project(project)
        return {"recovery": "not-blocking", "stale_possible": True}
    _touch_cache_project(project)
    if not _watch_enabled_config():
        return None
    manager = _get_watch_mgr()
    if path == "/reindex":
        manager.ensure_watch(project)
        return {"recovery": "explicit", "stale_possible": False}
    if path in _INTERACTIVE_HEAVY_PATHS:
        lifecycle = _schedule_project_recovery(manager, project)
        reindex_shard = work_coordinator.make_work_key(
            "/reindex", project, {"force": False})[1]
        if _HEAVY_COORDINATOR.has_work(
                shard=reindex_shard, label="/reindex"):
            lifecycle["stale_possible"] = True
        return lifecycle
    manager.ensure_ready(project, deadline=deadline)
    return {"recovery": "ready", "stale_possible": False}


def _preflight_heavy_request(path: str, parsed, body: dict | None) -> None:
    """Reject structurally invalid heavy calls before watcher or worker setup."""
    if path not in _HEAVY_PATHS:
        return
    _require_project(_request_project(parsed, body))
    if path in {"/find_references", "/call_hierarchy", "/impact"}:
        symbol = (body or {}).get("symbol")
        if not symbol:
            operation = path.removeprefix("/")
            raise _HttpError(
                400, f"{operation} missing required parameter symbol")


class _HttpError(Exception):
    """A controlled error carrying an HTTP status code (→ the endpoint returns the matching code + message, not a 500)."""
    def __init__(self, code: int, msg: str, *, headers: dict[str, str] | None = None,
                 details: dict | None = None):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.headers = headers or {}
        self.details = details or {}


# Each endpoint's implementation takes (parsed_url, body_dict) and returns (code, result_dict)
def _ep_health(parsed, body):
    watch_enabled = _watch_enabled_config()
    return 200, {
        "service": SERVICE_NAME,            # liveness-probe brand
        "product": "CodeSextant",              # public-facing product name (CodeSextant)
        "api_version": API_VERSION,
        "status": "ok",
        "ready": True,                        # ready field (for the panel/observability)
        "status_text": "service running normally",
        "pid": os.getpid(),
        "port": _port(),
        "engine_version": _engine_pkg_version(),
        "db_dir": str(storage.default_db_dir()),
        "log_file": str(_log_path()),
        "endpoints": [
            "GET /  (panel)",
            "GET /health",
            "GET /projects",
            "GET /get_symbols?project=&file=",
            "POST /find_references {project,symbol}",
            "GET /get_map?project=&budget=",
            "POST /reindex {project,force?}",
            "GET /status?project=",
            "GET /deadcode?project=&file=&lang=",
            "GET /ai_usage?project=&file=",
            "GET /find_unwired?project=&max_fanout=",
            "GET /get_health?project=",
            "GET /comment_overview?project=&file=",
            "GET /comment_tags?project=&tags=&file=",
            "GET /get_comments?project=&file=&scope=&doc_only=&tag=",
            "GET /find_duplicates?project=&file=&near_global=&min_similarity=&calls=",
            "GET /preflight?project=&file=&symbol=&budget=",
            "POST /call_hierarchy {project,symbol,direction?,max_hops?}",
            "POST /impact {project,symbol,max_hops?}",
        ],
        "uptime_sec": round(time.time() - _START_TS, 1),
        "watcher": {  # the control plane must not lazy-load watcher/engine just to answer a status query
            "enabled": watch_enabled,
            "watched": (
                list(_WATCH_MGR.watched_snapshot())
                if watch_enabled and _WATCH_MGR is not None else []
            ),
        },
        "heavy_work": _HEAVY_COORDINATOR.snapshot(),
        "background_recoveries": _recovery_snapshot(),
        "local_auth": {
            "scheme": local_auth.AUTH_SCHEME,
            "secret_transmitted": False,
            "browser_storage": "sessionStorage",
        },
        "sqlite": storage.sqlite_runtime_status(),
        "cache": _cache_policy_snapshot(),
    }


def _transient_http_error(message: str, reason: str) -> _HttpError:
    """Overload response for a condition the caller can retry rather than fix."""
    retry_after = _overload_retry_after_sec()
    return _HttpError(
        503, message,
        headers={"Retry-After": str(retry_after)},
        details={"retry_after_sec": retry_after, "reason": reason},
    )


def _busy_index_http_error(message: str) -> _HttpError:
    """Overload response for an index another writer is holding."""
    return _transient_http_error(f"the project index is busy: {message}", "index-busy")


def _engine_pkg_version():
    # Absolute import: when ensure spawns the daemon detached by file path, it runs as __main__
    # (no package context), so a relative import would fail. sys.path has already been patched
    # with parent.parent by this point, so codesextant is guaranteed importable.
    try:
        from codesextant import __version__ as v  # type: ignore
        return v
    except Exception:
        return None


def _watch_enabled_config() -> bool:
    """Read the watcher switch without importing the watcher module."""
    return os.environ.get("CODESEXTANT_WATCH_ENABLED", "1").lower() not in (
        "0", "false", "no", "off")


def _ep_get_symbols(parsed, body):
    project = _require_project(_q(parsed, "project"))
    file = _q(parsed, "file")
    return 200, engine.get_symbols(project, file=file)


def _ep_find_references(parsed, body):
    body = body or {}
    project = _require_project(body.get("project"))
    symbol = body.get("symbol")
    if not symbol:
        raise _HttpError(400, "find_references missing required parameter symbol")
    return 200, engine.find_references(
        project, symbol,
        def_path=body.get("def_path"),
        src_root=body.get("src_root"),
        include_low_confidence=body.get("include_low_confidence", True),
        persist=body.get("persist", True),
    )


def _ep_get_map(parsed, body):
    project = _require_project(_q(parsed, "project"))
    budget_raw = _q(parsed, "budget", "2000")
    try:
        budget = int(budget_raw)
    except (TypeError, ValueError):
        raise _HttpError(400, f"budget must be an integer, got '{budget_raw}'") from None
    # Query focus is supplied as comma-separated symbol and file lists.
    fsy = _q(parsed, "focus_symbols")
    ffi = _q(parsed, "focus_files")
    fs = [x for x in fsy.split(",") if x] if fsy else None
    ff = [x for x in ffi.split(",") if x] if ffi else None
    return 200, engine.get_map(project, token_budget=budget, focus_symbols=fs, focus_files=ff)


def _ep_reindex(parsed, body):
    body = body or {}
    project = _require_project(body.get("project"))
    force = bool(body.get("force", False))
    return 200, engine.index_project(project, force=force)


def _ep_status(parsed, body):
    project = _require_project(_q(parsed, "project"))
    # Git freshness spawns a subprocess, so skip it by default to avoid an
    # unguarded GET being triggered into a spawn storm by a malicious no-cors web page).
    # Panel/client callers pass ?fresh=1 explicitly when they need freshness.
    fresh = str(_q(parsed, "fresh", "") or "").lower() in ("1", "true", "yes", "on")
    try:
        db_timeout_ms = max(0, int(os.environ.get(
            "CODESEXTANT_STATUS_DB_TIMEOUT_MS", "150")))
    except (TypeError, ValueError):
        db_timeout_ms = 150
    try:
        git_timeout_sec = max(0.05, float(os.environ.get(
            "CODESEXTANT_STATUS_GIT_TIMEOUT_SEC", "0.5")))
    except (TypeError, ValueError):
        git_timeout_sec = 0.5
    try:
        result = project_state.status(
            project,
            check_freshness=fresh,
            busy_timeout_ms=db_timeout_ms,
            git_timeout_sec=git_timeout_sec,
        )
    except Exception as exc:  # noqa: BLE001
        get_logger().warning(
            "status details unavailable project=%s: %s",
            storage.project_key(project)[:12], type(exc).__name__)
        result = {
            "indexed": storage.db_path_for(project).exists(),
            "project_key": storage.project_key(project),
            "repo_path": os.path.abspath(project),
            "db_file": str(storage.db_path_for(project)),
            "partial": True,
            "index_status_error": "unavailable",
        }
    result["service_load"] = _HEAVY_COORDINATOR.snapshot()
    result["background_recoveries"] = _recovery_snapshot()
    return 200, result


def _ep_projects(parsed, body):
    # List every locally indexed project (no project parameter needed), the data source for the panel's "overview".
    return 200, project_state.list_projects()


def _ep_browser_session(parsed, body):
    """Issue a short-lived, single-use browser bootstrap code."""
    code = _BROWSER_SESSIONS.issue()
    return 200, {"path": f"/_session?code={code}", "expires_in_sec": 60}


def _ep_deadcode(parsed, body):
    # Run orphan analysis with per-symbol resolution only
    # if file= is given; lang= overrides language inference.
    project = _require_project(_q(parsed, "project"))
    scope_file = _q(parsed, "file")
    lang = _q(parsed, "lang")
    return 200, engine.find_deadcode(project, scope_file=scope_file, lang=lang)


def _ep_ai_usage(parsed, body):
    # ai-usage: scans the repo for which AI/LLM it uses + the three dispatch_policy channels
    # (cli/direct/local). file= given -> scan only that file.
    project = _require_project(_q(parsed, "project"))
    return 200, engine.find_ai_usage(project, scope_file=_q(parsed, "file"))


def _ep_call_hierarchy(parsed, body):
    # Transitive call chain with direction and depth parameters.
    body = body or {}
    project = _require_project(body.get("project"))
    symbol = body.get("symbol")
    if not symbol:
        raise _HttpError(400, "call_hierarchy missing required parameter symbol")
    return 200, engine.call_hierarchy(
        project, symbol,
        direction=body.get("direction", "both"),
        max_hops=body.get("max_hops"),
        def_path=body.get("def_path"),
        src_root=body.get("src_root"),
        build_edges=body.get("build_edges", True),
    )


def _ep_impact(parsed, body):
    # Change impact built on the upward call hierarchy.
    body = body or {}
    project = _require_project(body.get("project"))
    symbol = body.get("symbol")
    if not symbol:
        raise _HttpError(400, "impact missing required parameter symbol")
    return 200, engine.impact(
        project, symbol,
        max_hops=body.get("max_hops"),
        def_path=body.get("def_path"),
        src_root=body.get("src_root"),
    )


def _ep_find_unwired(parsed, body):
    # Find top-level symbols with no name-level external references.
    project = _require_project(_q(parsed, "project"))
    mf = _q(parsed, "max_fanout")
    max_fanout = None
    if mf:
        try:
            max_fanout = int(mf)
        except (TypeError, ValueError):
            raise _HttpError(400, f"max_fanout must be an integer, got '{mf}'") from None
    return 200, engine.find_unwired(project, max_fanout=max_fanout)


def _ep_get_health(parsed, body):
    # Return per-symbol health and unwired evidence.
    project = _require_project(_q(parsed, "project"))
    return 200, engine.get_health(project)


def _ep_preflight(parsed, body):
    # What to know before editing a file: reuse, co-change obligations, blast radius.
    project = _require_project(_q(parsed, "project"))
    target = _q(parsed, "file")
    if not target:
        raise _HttpError(400, "preflight requires file=<the file you are about to change>")
    raw_budget = _q(parsed, "budget")
    try:
        budget = int(raw_budget) if raw_budget else 1200
    except (TypeError, ValueError):
        raise _HttpError(400, f"budget must be an integer, got '{raw_budget}'") from None
    return 200, engine.preflight(project, target, symbol=_q(parsed, "symbol"),
                                 token_budget=budget,
                                 resolve=_q(parsed, "resolve"))


def _ep_check(parsed, body):
    # After editing: what the change looks like it forgot.
    project = _require_project(_q(parsed, "project"))
    raw_budget = _q(parsed, "budget")
    try:
        budget = int(raw_budget) if raw_budget else 1500
    except (TypeError, ValueError):
        raise _HttpError(400, f"budget must be an integer, got '{raw_budget}'") from None
    return 200, engine.check(project, base=_q(parsed, "base"),
                             staged=_q(parsed, "staged") in ("1", "true", "yes", "on"),
                             token_budget=budget, resolve=_q(parsed, "resolve"))


def _ep_comment_overview(parsed, body):
    # Summarize docstring coverage, tags, and comment density.
    project = _require_project(_q(parsed, "project"))
    return 200, engine.get_comment_overview(project, scope_file=_q(parsed, "file"))


def _ep_comment_tags(parsed, body):
    # Return TODO and FIXME markers with source lines. ``tags`` is comma-separated.
    project = _require_project(_q(parsed, "project"))
    raw = _q(parsed, "tags")
    tags = [t for t in raw.split(",") if t] if raw else None
    return 200, engine.find_comment_tags(project, tags=tags, scope_file=_q(parsed, "file"))


def _ep_get_comments(parsed, body):
    # Return comments matching the requested filters.
    project = _require_project(_q(parsed, "project"))
    doc_only = str(_q(parsed, "doc_only", "") or "").lower() in ("1", "true", "yes", "on")
    return 200, engine.get_comments(project, file=_q(parsed, "file"),
                                    scope=_q(parsed, "scope"), doc_only=doc_only,
                                    tag=_q(parsed, "tag"))


def _ep_find_duplicates(parsed, body):
    # Duplicate and similarity detection. near_global enables global near matches; calls enables
    # call_pattern, min_similarity overrides the threshold.
    project = _require_project(_q(parsed, "project"))
    near = str(_q(parsed, "near_global", "") or "").lower() in ("1", "true", "yes", "on")
    calls = str(_q(parsed, "calls", "") or "").lower() in ("1", "true", "yes", "on")
    ms_raw = _q(parsed, "min_similarity")
    ms = None
    if ms_raw:
        try:
            ms = float(ms_raw)
        except (TypeError, ValueError):
            raise _HttpError(400, f"min_similarity must be a float, got '{ms_raw}'") from None
    return 200, engine.find_duplicates(project, scope_file=_q(parsed, "file"),
                                       near_global=near, min_similarity=ms,
                                       include_call_pattern=calls)


def _ep_graph_data(parsed, body):
    # Generate graph data for a selected repository.
    # Lazy-imports graph_api (scipy/networkx are heavy dependencies, so the core engine stays light).
    # Synchronous spectral and Louvain layout can be slow on large repositories.
    import re
    project = _require_project(_q(parsed, "project"))
    if os.environ.get(
            "CODESEXTANT_ENABLE_EXPERIMENTAL_STARMAP", "0").lower() not in (
                "1", "true", "yes", "on"):
        raise _HttpError(404, "the experimental star map is disabled")
    name = _q(parsed, "name", "live") or "live"
    if not re.match(r"^[A-Za-z0-9_-]+$", name):   # allowlist guards against path injection into graph_{name}_*.json
        raise _HttpError(400, f"name only allows alphanumerics/underscore/hyphen, got '{name}'")
    poc = Path(__file__).resolve().parent.parent / "_poc_graph_c"
    module_file = poc / "graph_api.py"
    try:
        poc_info = poc.lstat()
        module_info = module_file.lstat()
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if (not stat.S_ISDIR(poc_info.st_mode)
                or getattr(poc_info, "st_file_attributes", 0) & reparse_flag
                or not stat.S_ISREG(module_info.st_mode)
                or getattr(module_info, "st_file_attributes", 0) & reparse_flag):
            raise _HttpError(404, "the experimental graph generator is unavailable")
        resolved_poc = poc.resolve(strict=True)
        resolved_module = module_file.resolve(strict=True)
        if (not resolved_module.is_file() or module_file.is_symlink()
                or resolved_module.parent != resolved_poc):
            raise _HttpError(404, "the experimental graph generator is unavailable")
        spec = importlib.util.spec_from_file_location(
            "_codesextant_experimental_graph_api", resolved_module)
        if spec is None or spec.loader is None:
            raise _HttpError(404, "the experimental graph generator is unavailable")
        graph_api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(graph_api)
        return 200, graph_api.build_graph_data(project, name)
    except (FileNotFoundError, NotADirectoryError):
        raise _HttpError(404, "the experimental graph generator is unavailable") from None
    except _HttpError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _HttpError(
            500, f"graph_data generation failed: {type(exc).__name__}") from exc


def _ep_links(parsed, body):
    # Run the optional Markdown link scanner in a subprocess so scanner failures
    # do not bring down the daemon. Backlinks are omitted unless full=1.
    import json as _json
    import os
    import subprocess
    import sys
    script = os.path.join(os.path.expanduser("~"), ".claude", "skills", "handoff-tick",
                          "scripts", "lint_links.py")
    if not os.path.exists(script):
        return 200, {"available": False, "reason": f"lint_links.py does not exist: {script}"}
    try:
        _lk_kw = {"capture_output": True, "timeout": 60}
        if os.name == "nt":
            _lk_kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW (aligned with deadcode/engine/references, no console flash)
        r = subprocess.run([sys.executable, "-X", "utf8", script, "--json"], **_lk_kw)
        if r.returncode == 3:  # a failed scan is never treated as green (linter contract)
            return 200, {"available": False,
                         "reason": f"linkgraph exit 3: {r.stderr.decode('utf-8', errors='replace')[:300]}"}
        data = _json.loads(r.stdout.decode("utf-8", errors="replace") or "{}")
    except Exception as exc:  # noqa: BLE001
        return 200, {"available": False, "reason": f"linkgraph scan failed: {exc}"}
    data["available"] = True
    data["exit_code"] = r.returncode  # 0 clean / 1 dangling / 2 orphan only
    if _q(parsed, "full") != "1":
        data.pop("backlinks", None)
    # Optional line-delimited JSON audit log supplied by the host environment.
    # The section is omitted when CODESEXTANT_DISCIPLINE_LOG is unset.
    dj = os.environ.get("CODESEXTANT_DISCIPLINE_LOG", "")
    # Return the configured path so the panel can identify the data source.
    data["discipline_source"] = dj or None
    try:
        if dj and os.path.exists(dj) and os.path.getsize(dj) > 0:
            with open(dj, encoding="utf-8", errors="replace") as f:
                data["discipline_tail"] = [ln.strip() for ln in f.readlines()[-5:]]
        else:
            data["discipline_tail"] = None  # no contract
    except OSError:
        data["discipline_tail"] = None
    return 200, data


# routing table: method → {path: (handler)}
_ROUTES_GET = {
    "/health": _ep_health,
    "/get_symbols": _ep_get_symbols,
    "/get_map": _ep_get_map,
    "/status": _ep_status,
    "/projects": _ep_projects,
    "/deadcode": _ep_deadcode,
    "/ai_usage": _ep_ai_usage,
    "/find_unwired": _ep_find_unwired,
    "/get_health": _ep_get_health,
    "/comment_overview": _ep_comment_overview,
    "/comment_tags": _ep_comment_tags,
    "/get_comments": _ep_get_comments,
    "/find_duplicates": _ep_find_duplicates,
    "/preflight": _ep_preflight,
    "/check": _ep_check,
    "/graph_data": _ep_graph_data,
    "/links": _ep_links,
}
_ROUTES_POST = {
    "/_browser_session": _ep_browser_session,
    "/find_references": _ep_find_references,
    "/reindex": _ep_reindex,
    "/call_hierarchy": _ep_call_hierarchy,
    "/impact": _ep_impact,
}


_HEAVY_PATHS = frozenset({
    "/preflight",
    "/check",
    "/get_symbols",
    "/get_map",
    "/deadcode",
    "/ai_usage",
    "/find_unwired",
    "/get_health",
    "/comment_overview",
    "/comment_tags",
    "/get_comments",
    "/find_duplicates",
    "/graph_data",
    "/links",
    "/find_references",
    "/reindex",
    "/call_hierarchy",
    "/impact",
})

_INTERACTIVE_HEAVY_PATHS = frozenset({
    "/preflight",
    "/check",
    "/get_symbols",
    "/get_map",
    "/find_references",
    "/call_hierarchy",
    "/impact",
})

_BUILTIN_HEAVY_HANDLERS = {
    path: (_ROUTES_POST.get(path) or _ROUTES_GET.get(path))
    for path in _HEAVY_PATHS
}


def _worker_process_enabled() -> bool:
    return os.environ.get(
        "CODESEXTANT_ROUTE_WORKER_PROCESS", "1").strip().lower() not in (
            "0", "false", "no", "off")


def _invoke_heavy_handler(path: str, handler, parsed, body: dict | None,
                          deadline: float | None):
    """Run production heavy handlers in a deadline-bound child process."""
    if (deadline is None or not _worker_process_enabled()
            or _BUILTIN_HEAVY_HANDLERS.get(path) is not handler):
        return handler(parsed, body)
    method = "POST" if path in _ROUTES_POST else "GET"
    target = parsed.geturl() if parsed is not None else path
    token = work_coordinator.current_cancellation_token()
    try:
        max_request_sec = float(os.environ.get(
            "CODESEXTANT_MAX_REQUEST_TIMEOUT_SEC", "3600"))
    except (TypeError, ValueError):
        max_request_sec = 3600.0
    if not math.isfinite(max_request_sec) or max_request_sec <= 0:
        max_request_sec = 3600.0
    child_deadline = max(
        deadline,
        time.monotonic() + max(1.0, max_request_sec),
    )
    try:
        return worker_process.run_route(
            method,
            target,
            body,
            deadline=deadline,
            deadline_provider=(token.deadline if token is not None else None),
            child_deadline=child_deadline,
        )
    except worker_process.WorkerDeadlineExceeded as exc:
        raise work_coordinator.HeavyWorkDeadlineExceeded(str(exc)) from exc
    except worker_process.RemoteHttpError as exc:
        raise _HttpError(
            exc.code,
            exc.message,
            headers=exc.headers,
            details=exc.details,
        ) from exc


def _overload_retry_after_sec() -> int:
    try:
        return max(1, int(os.environ.get(
            "CODESEXTANT_OVERLOAD_RETRY_AFTER_SEC", "5")))
    except (TypeError, ValueError):
        return 5


def _route_work_key(path: str, parsed, body: dict | None):
    """Canonicalize one request into (single-flight key, admission shard).

    The shard is the repository, so one project's expensive job queues only
    against its own project, not against every other repository on the machine.
    """
    params: dict = {}
    if parsed is not None:
        params.update(parse_qs(parsed.query, keep_blank_values=True))
    if body:
        params.update(body)
    project = params.pop("project", None)
    if isinstance(project, list):
        project = project[0] if project else None
    if path == "/reindex":
        params["force"] = bool(params.get("force", False))
    key = work_coordinator.make_work_key(path, project, params)
    return key, key[1]  # key[1] is the normalized project path


def _execute_route(path: str, handler, parsed, body: dict | None,
                   *, deadline: float | None = None):
    """Keep control endpoints immediate; admit expensive work per repository."""
    if path not in _HEAVY_PATHS:
        return handler(parsed, body)
    key, shard = _route_work_key(path, parsed, body)
    priority = "interactive" if path in _INTERACTIVE_HEAVY_PATHS else "batch"
    try:
        run_kwargs = {"label": path, "shard": shard, "priority": priority}
        if deadline is not None:
            run_kwargs["deadline"] = deadline
        return _HEAVY_COORDINATOR.run(
            key,
            lambda: _invoke_heavy_handler(
                path, handler, parsed, body, deadline),
            **run_kwargs,
        )
    except work_coordinator.HeavyWorkDeadlineExceeded as exc:
        raise _HttpError(504, str(exc)) from exc
    except worker_process.RouteWorkerError as exc:
        # A busy index is an overload condition with a remedy, not an internal failure.
        # Reported as 500 it looks like a defect and callers have no documented response;
        # as 503 with Retry-After it joins the other overload answers agents already
        # know to back off from.
        if storage.is_busy_index_error(
                getattr(exc, "error_type", ""), getattr(exc, "remote_message", "")):
            raise _busy_index_http_error(str(exc)) from exc
        # A worker killed by SIGKILL was ended by something outside the work: the
        # containment guardian, or a kernel short of memory with several spawned
        # interpreters running at once. The request did not finish, but nothing about it
        # was wrong and retrying is the caller's move. A crash signal is a different
        # claim entirely and still reaches them as an internal error.
        if worker_process.killed_by_signal(
                getattr(exc, "exitcode", None)) == signal.SIGKILL:
            raise _transient_http_error(
                f"the route worker was killed before answering: {exc}",
                "worker-killed") from exc
        raise
    except sqlite3.OperationalError as exc:
        if not storage.is_busy_index_error(type(exc).__name__, str(exc)):
            raise
        raise _busy_index_http_error(str(exc)) from exc
    except work_coordinator.HeavyWorkQueueFull as exc:
        retry_after = _overload_retry_after_sec()
        heavy = _HEAVY_COORDINATOR.snapshot()
        raise _HttpError(
            503,
            str(exc),
            headers={"Retry-After": str(retry_after)},
            details={
                "retry_after_sec": retry_after,
                "heavy_work": heavy,
            },
        ) from exc


def _method_hint(path: str, routes: dict) -> str | None:
    """When the path exists but the wrong HTTP method was used, return a hint about which method
    to use; otherwise None.

    Just returning "unknown endpoint" makes people think the endpoint doesn't exist at all and go
    looking for the cause somewhere else. On 2026-07-19 someone (me) wasted a long time that way.
    The path is right there in the other routing table; just say so.
    """
    if routes is _ROUTES_GET and path in _ROUTES_POST:
        return "This endpoint exists, but requires POST, with parameters in the JSON body (not the URL query string)"
    if routes is _ROUTES_POST and path in _ROUTES_GET:
        return "This endpoint exists, but requires GET, with parameters in the URL query string"
    return None


class _Handler(BaseHTTPRequestHandler):
    server_version = "codesextant-daemon/0.1"

    def log_message(self, *a):
        pass  # default access log silenced; we record hits ourselves via the codesextant.daemon logger

    def _common_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-CodeSextant-API-Version", str(API_VERSION))

    def _panel_csp(self) -> str:
        return (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'self'"
        )

    def _host_is_loopback(self) -> bool:
        raw = self.headers.get("Host")
        if not raw:
            return False
        try:
            parsed = urlparse(f"//{raw}")
            host = parsed.hostname
            port = parsed.port
        except ValueError:
            return False
        server_port = getattr(self.server, "server_port", _port())
        if port is not None and port != server_port:
            return False
        if host in ("localhost", "tauri.localhost"):
            return True
        try:
            return bool(host and ipaddress.ip_address(host).is_loopback)
        except ValueError:
            return False

    def _auth_kind(self, body: bytes = b"") -> str | None:
        if local_auth.verify_request(
                self.command, self.path, self.headers, body):
            return "hmac"
        session = self.headers.get("X-CodeSextant-Session")
        return "session" if _BROWSER_SESSIONS.valid(session) else None

    def _require_loopback_host(self) -> bool:
        if self._host_is_loopback():
            return True
        self._send_json(421, {
            "error": "the Host header must identify this loopback listener",
            "service": SERVICE_NAME,
        })
        return False

    def _authorize(self, body: bytes = b"", *, host_checked: bool = False) -> str | None:
        if not host_checked and not self._require_loopback_host():
            return None
        auth_kind = self._auth_kind(body)
        if auth_kind is None:
            self._send_json(401, {
                "error": "authentication required; use the CodeSextant client or run `codesextant gui`",
                "service": SERVICE_NAME,
            }, headers={"WWW-Authenticate": local_auth.AUTH_SCHEME})
            return None
        try:
            self.connection.settimeout(None)
        except OSError:
            pass
        return auth_kind

    def _send_json(self, code: int, obj: dict, *,
                   headers: dict[str, str] | None = None):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        _Handler._common_headers(self)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _send_html(self, code: int, html: str, *, csp: str | None = None):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        _Handler._common_headers(self)
        self.send_header(
            "Content-Security-Policy",
            csp or _Handler._panel_csp(self),
        )
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _send_browser_bootstrap(self, session: str) -> None:
        nonce = secrets.token_urlsafe(18)
        session_json = json.dumps(session)
        html = (
            "<!doctype html><meta charset=\"utf-8\">"
            "<meta name=\"referrer\" content=\"no-referrer\">"
            f"<script nonce=\"{nonce}\">"
            f"sessionStorage.setItem(\"codesextant.session\", {session_json});"
            "history.replaceState(null, \"\", \"/\");"
            "location.replace(\"/\");"
            "</script>"
        )
        self._send_html(
            200,
            html,
            csp=(
                "default-src 'none'; "
                f"script-src 'nonce-{nonce}'; "
                "base-uri 'none'; frame-ancestors 'none'"
            ),
        )

    def _serve_starmap_asset(self, path):
        # Serve the star-map frontend (/starmap=v3-stunning.html,
        # /graph-common.js=shared JS, /graph_*.json=already-generated static graphs). Same origin
        # (8790) as /graph_data, avoiding cross-port CORS.
        # The prototype loads three.js from a CDN.
        if os.environ.get(
                "CODESEXTANT_ENABLE_EXPERIMENTAL_STARMAP", "0").lower() not in (
                    "1", "true", "yes", "on"):
            self._send_json(404, {
                "error": "the experimental star map is disabled",
                "service": SERVICE_NAME,
            })
            return
        import re
        poc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_poc_graph_c")
        if path == "/starmap":
            fn, ctype = "v3-stunning.html", "text/html; charset=utf-8"
        elif path == "/graph-common.js":
            fn, ctype = "graph-common.js", "application/javascript; charset=utf-8"
        elif re.match(r"^/graph_[A-Za-z0-9_]+\.json$", path):   # allowlist guards against path injection
            fn, ctype = path.lstrip("/"), "application/json; charset=utf-8"
        else:
            self._send_json(404, {"error": f"unknown star-map asset {path}", "service": SERVICE_NAME})
            return
        try:
            with open(os.path.join(poc, os.path.basename(fn)), encoding="utf-8") as f:
                body = f.read().encode("utf-8")
        except Exception as exc:  # noqa: BLE001
            self._send_json(404, {"error": f"failed to read star-map asset {fn}: {exc}", "service": SERVICE_NAME})
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        _Handler._common_headers(self)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _read_body_bytes(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            raise _HttpError(400, "Content-Length must be an integer") from None
        if length < 0:
            raise _HttpError(400, "Content-Length must not be negative")
        if length <= 0:
            return b""
        try:
            max_body = int(os.environ.get("CODESEXTANT_MAX_BODY_BYTES", "65536"))
        except ValueError:
            max_body = 65536
        max_body = max(1, max_body)
        if length > max_body:
            raise _HttpError(413, f"request body is too large; limit is {max_body} bytes")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise _HttpError(400, "request body ended before Content-Length bytes arrived")
        return raw

    @staticmethod
    def _parse_body(raw: bytes) -> dict:
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _HttpError(400, f"request body is not valid JSON: {exc}") from exc

    def _request_deadline(self, path: str) -> float | None:
        raw = self.headers.get("X-CodeSextant-Timeout-Ms")
        if raw is None:
            if path not in _HEAVY_PATHS:
                return None
            if path in _INTERACTIVE_HEAVY_PATHS:
                raw = os.environ.get(
                    "CODESEXTANT_INTERACTIVE_TIMEOUT_SEC", "15")
            else:
                raw = os.environ.get("CODESEXTANT_HEAVY_TIMEOUT_SEC", "900")
            try:
                timeout_ms = float(raw) * 1000.0
            except ValueError:
                timeout_ms = 900000.0
        else:
            try:
                timeout_ms = float(raw)
            except ValueError:
                raise _HttpError(
                    400, "X-CodeSextant-Timeout-Ms must be a number") from None
        try:
            max_sec = float(os.environ.get(
                "CODESEXTANT_MAX_REQUEST_TIMEOUT_SEC", "3600"))
        except ValueError:
            max_sec = 3600.0
        if not math.isfinite(timeout_ms) or timeout_ms <= 0:
            raise _HttpError(
                400, "X-CodeSextant-Timeout-Ms must be a positive finite number")
        if not math.isfinite(max_sec) or max_sec <= 0:
            max_sec = 3600.0
        timeout_sec = min(max(0.1, timeout_ms / 1000.0), max(1.0, max_sec))
        return time.monotonic() + timeout_sec

    def _dispatch(self, routes: dict, body: dict | None):
        parsed = urlparse(self.path)
        if parsed.path != "/health" and hasattr(self.server, "note_activity"):
            self.server.note_activity()
        return self._dispatch_inner(routes, body)

    def _dispatch_inner(self, routes: dict, body: dict | None):
        parsed = urlparse(self.path)
        handler = routes.get(parsed.path)
        lg = get_logger()
        if handler is None:
            lg.info("endpoint miss %s %s → 404", self.command, parsed.path)
            payload = {"error": f"unknown endpoint {self.command} {parsed.path}",
                       "service": SERVICE_NAME}
            hint = _method_hint(parsed.path, routes)
            if hint:
                payload["hint"] = hint
            self._send_json(404, payload)
            return
        t0 = time.perf_counter()
        try:
            deadline = self._request_deadline(parsed.path)
            _preflight_heavy_request(parsed.path, parsed, body)
            lifecycle = _prepare_project(
                parsed.path, parsed, body, deadline=deadline)
            code, result = _execute_route(
                parsed.path, handler, parsed, body, deadline=deadline)
            if (parsed.path == "/reindex" and code < 400
                    and _watch_enabled_config() and _WATCH_MGR is not None):
                project = _request_project(parsed, body)
                if project:
                    _WATCH_MGR.mark_ready(project)
            if lifecycle is not None and isinstance(result, dict):
                result.setdefault("index_lifecycle", lifecycle)
            dt = (time.perf_counter() - t0) * 1000
            # hit log: endpoint + key summary (does not dump the whole result)
            lg.info("endpoint hit %s %s → %d (%.1fms) %s",
                    self.command, parsed.path, code, dt, _summ(result))
            self._send_json(code, result)
        except _HttpError as he:
            rejection = "parameter error" if he.code < 500 else "request rejected"
            lg.warning("endpoint %s %s %s → %d: %s",
                       self.command, parsed.path, rejection, he.code, he.msg)
            payload = {"error": he.msg, "service": SERVICE_NAME, **he.details}
            self._send_json(he.code, payload, headers=he.headers)
        except work_coordinator.HeavyWorkQueueFull as exc:
            retry_after = _overload_retry_after_sec()
            lg.warning("endpoint %s %s recovery queue full: %s",
                       self.command, parsed.path, exc)
            self._send_json(503, {
                "error": str(exc),
                "service": SERVICE_NAME,
                "retry_after_sec": retry_after,
                "heavy_work": _HEAVY_COORDINATOR.snapshot(),
            }, headers={"Retry-After": str(retry_after)})
        except work_coordinator.HeavyWorkDeadlineExceeded as exc:
            lg.warning("endpoint %s %s deadline exceeded: %s",
                       self.command, parsed.path, exc)
            self._send_json(504, {"error": str(exc), "service": SERVICE_NAME})
        except Exception as exc:  # a real engine error → 500 + log it (with traceback), never swallow silently
            lg.exception("endpoint %s %s execution failed: %s", self.command, parsed.path, exc)
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}",
                                  "service": SERVICE_NAME})

    def do_GET(self):
        parsed = urlparse(self.path)
        if not self._require_loopback_host():
            return
        if parsed.path == "/_session":
            session = _BROWSER_SESSIONS.consume(_q(parsed, "code"))
            if session is None:
                self._send_json(401, {
                    "error": "browser bootstrap code is invalid, expired, or already used",
                    "service": SERVICE_NAME,
                })
                return
            if hasattr(self.server, "note_activity"):
                self.server.note_activity()
            self._send_browser_bootstrap(session)
            return
        if parsed.path in ("/", "/panel"):
            if hasattr(self.server, "note_activity"):
                self.server.note_activity()
            get_logger().info("endpoint hit GET %s → 200 (panel)", parsed.path)
            self._send_html(200, panel.render_panel())
            return
        if self._authorize(host_checked=True) is None:
            return
        if (parsed.path in ("/starmap", "/graph-common.js")
                or (parsed.path.startswith("/graph_") and parsed.path.endswith(".json"))):
            if hasattr(self.server, "note_activity"):
                self.server.note_activity()
            # The daemon serves the star-map frontend and generated static
            # graph JSON from one place (same origin 8790 as /graph_data, avoiding CORS).
            self._serve_starmap_asset(parsed.path)
            return
        self._dispatch(_ROUTES_GET, None)

    def _csrf_check(self, auth_kind: str = "hmac") -> bool:
        """Check the Origin header on POST endpoints.

        A malicious page could send a
        cross-site POST to /reindex (burns CPU + probes whether a directory exists) or
        /find_references (runs jedi): allow local/Tauri/VSCode webview/no-Origin requests, block
        external cross-site HTTP origins. Set CODESEXTANT_CSRF_GUARD=0 to disable
        the check. It is enabled by default.
        """
        origin = self.headers.get("Origin")
        if auth_kind == "session":
            if not origin:
                return False
            try:
                parsed_origin = urlparse(origin)
            except Exception:
                return False
            return (
                parsed_origin.scheme in ("http", "https")
                and parsed_origin.netloc.lower()
                == (self.headers.get("Host") or "").lower()
            )
        if os.environ.get("CODESEXTANT_CSRF_GUARD", "1").lower() in ("0", "false", "no", "off"):
            return True
        if not origin:
            # curl / Python urllib / same-origin simple requests often omit Origin -> allow (this is a local tool)
            return True
        if origin == "null":  # a local panel loaded via file:// (Origin is the literal string "null")
            return True
        # Use urlparse for an exact host match rather than a string prefix. Otherwise a
        # malicious domain like http://127.0.0.1.evil.com / http://localhost.attacker.test could
        # bypass this via prefix matching.
        try:
            p = urlparse(origin)
        except Exception:
            return False
        # local shell custom schemes: Tauri v1/macOS (tauri://), VSCode webview (vscode-webview://)
        if p.scheme in ("tauri", "vscode-webview"):
            return True
        if p.scheme not in ("http", "https"):
            return False
        host = p.hostname
        # string-form host: localhost, Tauri v2 (Windows/Linux) real Origin https://tauri.localhost
        # (exact match, not endswith, to avoid tauri.localhost.evil.com bypassing this)
        if host in ("localhost", "tauri.localhost"):
            return True
        # IP-form host: use ipaddress for exact loopback detection (covers every ::1 expansion + 127.0.0.0/8)
        try:
            import ipaddress
            if host and ipaddress.ip_address(host).is_loopback:
                return True
        except ValueError:
            pass
        return False

    def do_POST(self):
        if not self._require_loopback_host():
            return
        try:
            raw_body = self._read_body_bytes()
        except _HttpError as he:
            get_logger().warning("POST %s body read failed → %d: %s",
                                 self.path, he.code, he.msg)
            self._send_json(he.code, {"error": he.msg, "service": SERVICE_NAME})
            return
        except TimeoutError:
            self._send_json(408, {
                "error": "request body timed out before authentication",
                "service": SERVICE_NAME,
            })
            return
        auth_kind = self._authorize(raw_body, host_checked=True)
        if auth_kind is None:
            return
        if not self._csrf_check(auth_kind):
            get_logger().warning("POST %s CSRF blocked (Origin=%s)",
                                 self.path, self.headers.get("Origin"))
            self._send_json(403, {
                "error": "CSRF: Origin is not on the allowlist (local/Tauri/webview only); "
                         "if this is a legitimate frontend, add it to the allowlist or set env CODESEXTANT_CSRF_GUARD=0",
                "service": SERVICE_NAME})
            return
        try:
            body = self._parse_body(raw_body)
        except _HttpError as he:
            get_logger().warning("POST %s body parse failed → %d: %s",
                                 self.path, he.code, he.msg)
            self._send_json(he.code, {"error": he.msg, "service": SERVICE_NAME})
            return
        parsed = urlparse(self.path)
        if parsed.path == "/_shutdown":
            if auth_kind != "hmac":
                self._send_json(403, {
                    "error": "daemon shutdown requires a signed local client request",
                    "service": SERVICE_NAME,
                })
                return
            self._send_json(202, {
                "action": "stopping",
                "service": SERVICE_NAME,
            })
            threading.Thread(
                target=self.server.initiate_shutdown,
                name="codesextant-graceful-shutdown",
                daemon=True,
            ).start()
            return
        self._dispatch(_ROUTES_POST, body)


def _summ(result: dict) -> str:
    """Pull a few key fields out of an endpoint's return value for logging (avoids flooding the log with the entire payload)."""
    if not isinstance(result, dict):
        return ""
    keys = ("count", "indexed", "skipped", "symbols_total", "high_confidence",
            "indexed_files", "symbols", "name_match_file_count", "ready")
    bits = []
    for k in keys:
        if k in result:
            v = result[k]
            v = len(v) if isinstance(v, list) else v
            bits.append(f"{k}={v}")
    return " ".join(bits)


_START_TS = time.time()


def serve(port: int | None = None):
    """Run the HTTP server in the foreground (ensure spawns this detached in the background)."""
    global _ACTIVE_SERVER, _WATCH_MGR
    port = port or _port()
    lg = get_logger(file_output=True)
    probe_guard = _InterprocessFileLock(
        _daemon_lock_path(port, "instance-probe"), timeout=1.0)
    try:
        probe_guard.acquire()
    except TimeoutError:
        lg.warning("daemon owner probe state unknown (port=%d) → not starting this time", port)
        return {"action": "ownership-unknown", "port": port, "pid": None}
    try:
        try:
            instance_lock = _InterprocessFileLock(
                _daemon_lock_path(port, "instance"), timeout=0.0)
            instance_lock.acquire()
        except TimeoutError:
            alive = http_ping(port=port)
            lg.warning("duplicate daemon startup blocked (port=%d, existing_pid=%s)",
                       port, (alive or {}).get("pid"))
            return {"action": "already-running", "port": port,
                    "pid": (alive or {}).get("pid")}
    finally:
        probe_guard.release()

    try:
        # A previous process may have crashed after creating its advisory
        # draining marker. Holding the lifetime lock proves that no prior
        # daemon can still be draining, so the marker is stale and safe to
        # remove before this owner binds the listener.
        try:
            _daemon_lock_path(port, "draining").unlink(missing_ok=True)
        except OSError:
            pass
        with _DAEMON_PROJECT_KEYS_LOCK:
            _DAEMON_PROJECT_KEYS.clear()
        try:
            srv = _ExclusiveThreadingHTTPServer((HOST, port), _Handler)
        except OSError as exc:
            lg.error("daemon startup failed (port %d may already be in use): %s", port, exc)
            raise
        _ACTIVE_SERVER = srv
        lg.info("daemon started listening http://%s:%d  service=%s  log=%s",
                HOST, port, SERVICE_NAME, _log_path())
        print(f"[codesextant daemon] listening http://{HOST}:{port} "
              f"(pid={os.getpid()}, service={SERVICE_NAME})")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            lg.info("daemon received interrupt, shutting down")
        finally:
            draining_marker = _daemon_lock_path(port, "draining")
            try:
                try:
                    draining_marker.touch(exist_ok=True)
                except OSError:
                    pass
                srv.server_close()
                if _ACTIVE_SERVER is srv:
                    _ACTIVE_SERVER = None
                _join_recovery_threads()
                with _WATCH_MGR_LOCK:
                    manager = _WATCH_MGR
                    _WATCH_MGR = None
                active_projects = (
                    manager.watched_snapshot() if manager is not None else ())
                if manager is not None:
                    try:
                        manager.stop_all()
                    except Exception:
                        pass
                engine_module = _lazy_import.loaded_module(engine)
                snapshots_drained = (
                    engine_module is None
                    or engine_module.wait_for_snapshot_writers(timeout=30.0)
                )
                if snapshots_drained:
                    _prune_cache_if_quiescent(active_projects)
                else:
                    lg.warning(
                        "cache prune skipped because snapshot writers did not drain")
                lg.info("daemon shut down")
            finally:
                try:
                    draining_marker.unlink(missing_ok=True)
                except OSError:
                    pass
        return {"action": "stopped", "port": port, "pid": os.getpid()}
    finally:
        instance_lock.release()


# ── Idempotent startup ──
def _spawn_daemon(port: int):
    """Spawn one detached daemon process; startup serialization lives above."""
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    creationflags = 0
    kwargs = {}
    if os.name == "nt":
        creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:  # POSIX: start_new_session detaches the daemon from the caller's session
        kwargs["start_new_session"] = True

    env = dict(os.environ)
    env["CODESEXTANT_PORT"] = str(port)
    return subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "serve"],
        creationflags=creationflags,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        env=env,
        **kwargs,
    )


def ensure_running(port: int | None = None, *, wait_sec: float = 6.0) -> dict:
    """Make sure the shared daemon is running.

    1) First, a strict liveness probe (/health brand match). Already running -> return
       immediately without restarting it.
    2) Not running -> spawn it detached in the background via DETACHED_PROCESS (the daemon
       outlives its caller, shared by other agents).
    3) Poll until it's listening, then return the startup result (with pid, as proof of the singleton).

    Returns a dict: {action, pid, port, ...}
      action in {"already-running", "spawned", "spawn-timeout"}
    """
    port = port or _port()
    lg = get_logger()

    alive = http_ping(port=port)
    if alive is not None:
        if _health_api_current(alive):
            lg.info("ensure: detected an existing daemon (pid=%s, port=%d) → idempotent, not restarting",
                    alive.get("pid"), port)
            return {
                "action": "already-running",
                "pid": alive.get("pid"),
                "port": port,
                "health": alive,
                # Short client disconnects reconnect to the same daemon and
                # reuse the persistent per-project index instead of redoing work.
                "reconnect": True,
                "index_reuse": "persistent-per-project",
            }
        busy = _health_has_heavy_work(alive)
        lg.warning(
            "ensure: daemon API is outdated; refusing automatic replacement "
            "because a network response is not authority to terminate a PID "
            "(reported_pid=%s, port=%d, busy=%s)",
            alive.get("pid"), port, busy)
        return _upgrade_required_result(alive, port, busy=busy)

    auth_state = _auth_state_result(_auth_challenge(port=port), port)
    if auth_state is not None:
        lg.warning(
            "ensure: daemon authentication is incompatible "
            "(port=%d, current=%s, required=%s)",
            port, auth_state["current_auth_scheme"],
            auth_state["required_auth_scheme"])
        return auth_state

    owner = _instance_owner_result(port)
    if owner is not None:
        lg.warning(
            "ensure: /health could not prove compatibility, while the instance lock proves an "
            "owner is alive (port=%d); refusing both reuse and replacement", port)
        return owner

    # Check-then-spawn must be serialized across agents; otherwise several daemons could be
    # spawned in the same instant. Re-probe liveness inside the lock so later callers simply
    # reuse the PID that started first.
    try:
        with _InterprocessFileLock(
                _daemon_lock_path(port, "startup"), timeout=wait_sec + 0.5):
            alive = http_ping(port=port)
            if alive is not None:
                if _health_api_current(alive):
                    return {
                        "action": "already-running",
                        "pid": alive.get("pid"),
                        "port": port,
                        "health": alive,
                        "reconnect": True,
                        "index_reuse": "persistent-per-project",
                    }
                if _health_has_heavy_work(alive):
                    return _upgrade_required_result(alive, port, busy=True)
                return _upgrade_required_result(alive, port, busy=False)

            auth_state = _auth_state_result(_auth_challenge(port=port), port)
            if auth_state is not None:
                return auth_state

            owner = _instance_owner_result(port)
            if owner is not None:
                lg.warning(
                    "ensure: the instance lock proves an owner is alive but its API is unverified "
                    "(port=%d); refusing both reuse and replacement", port)
                return owner

            # A listener exists but cannot be verified as CodeSextant, so refuse to bind the same
            # port and cause a split.
            if is_port_listening(port=port):
                # The quick 0.6s health probes above may miss a valid daemon
                # under transient desktop load.  Before declaring a foreign
                # listener, make one bounded slow brand confirmation.
                alive = http_ping(
                    port=port, timeout=_slow_health_timeout(wait_sec))
                if alive is not None:
                    if _health_api_current(alive):
                        lg.info(
                            "ensure: slow confirmation of an existing daemon (pid=%s, port=%d) → idempotent, not restarting",
                            alive.get("pid"), port)
                        return {
                            "action": "already-running",
                            "pid": alive.get("pid"),
                            "port": port,
                            "health": alive,
                            "reconnect": True,
                            "index_reuse": "persistent-per-project",
                        }
                    return _upgrade_required_result(
                        alive, port, busy=_health_has_heavy_work(alive))
                auth_state = _auth_state_result(
                    _auth_challenge(
                        port=port, timeout=_slow_health_timeout(wait_sec)),
                    port,
                )
                if auth_state is not None:
                    return auth_state
                owner = _instance_owner_result(port)
                if owner is not None:
                    lg.warning(
                        "ensure: the listener and instance lock are occupied but API compatibility "
                        "is unverified on port %d; refusing both reuse and replacement", port)
                    return owner
                lg.error("ensure: port %d is occupied but the /health brand is invalid, refusing to bind again", port)
                return {"action": "port-conflict", "port": port}

            proc = _spawn_daemon(port)
            lg.info("ensure: spawned the daemon detached in the background (spawn pid=%d, port=%d)",
                    proc.pid, port)

            deadline = time.time() + wait_sec
            while time.time() < deadline:
                h = http_ping(port=port)
                if h is not None and _health_api_current(h):
                    lg.info("ensure: daemon is ready (daemon pid=%s, port=%d)",
                            h.get("pid"), port)
                    return {"action": "spawned", "pid": h.get("pid"),
                            "spawn_pid": proc.pid, "port": port, "health": h}
                time.sleep(0.2)

            lg.error("ensure: daemon failed to come up (no /health response within %ss, port=%d)",
                     wait_sec, port)
            return {"action": "spawn-timeout", "spawn_pid": proc.pid, "port": port}
    except TimeoutError:
        alive = http_ping(
            port=port, timeout=_slow_health_timeout(wait_sec))
        if alive is not None:
            if _health_api_current(alive):
                return {
                    "action": "already-running",
                    "pid": alive.get("pid"),
                    "port": port,
                    "health": alive,
                    "reconnect": True,
                    "index_reuse": "persistent-per-project",
                }
            return _upgrade_required_result(
                alive, port, busy=_health_has_heavy_work(alive))
        auth_state = _auth_state_result(
            _auth_challenge(
                port=port, timeout=_slow_health_timeout(wait_sec)),
            port,
        )
        if auth_state is not None:
            return auth_state
        owner = _instance_owner_result(port)
        if owner is not None:
            lg.warning(
                "ensure: startup lock wait expired and only process ownership is proven on port %d; "
                "refusing both reuse and replacement", port)
            return owner
        lg.error("ensure: timed out waiting for the startup lock (port=%d)", port)
        return {"action": "startup-lock-timeout", "port": port}


def stop_running(port: int | None = None) -> dict:
    """Ask an authenticated current daemon to drain and stop itself.

    A PID returned over HTTP is never passed to an operating-system kill API.
    Legacy daemons fail closed and must be upgraded through an independently
    verified process-management path.
    """
    port = port or _port()
    lg = get_logger()
    alive = http_ping(port=port)
    if alive is None:
        if is_port_listening(port=port):
            return {"action": "unverified-listener", "port": port,
                    "port_released": False}
        lg.info("stop: no daemon of ours on port %d (nothing to stop)", port)
        return {"action": "not-running", "port": port, "port_released": True}
    pid = alive.get("pid")
    if not _health_api_current(alive):
        return {
            **_upgrade_required_result(
                alive, port, busy=_health_has_heavy_work(alive)),
            "port_released": False,
        }
    try:
        target = "/_shutdown"
        request = urllib.request.Request(
            f"http://{HOST}:{port}{target}",
            data=b"",
            method="POST",
        )
        for name, value in local_auth.request_headers(
                "POST", target, b"").items():
            request.add_unredirected_header(name, value)
        with urllib.request.urlopen(request, timeout=2.0) as response:
            if getattr(response, "status", 202) != 202:
                raise RuntimeError(
                    f"daemon rejected graceful shutdown with HTTP {response.status}")
            response.read()
        lg.info("stop: daemon accepted graceful drain (reported_pid=%s, port=%d)",
                pid, port)
    except Exception as exc:
        lg.warning("stop: graceful shutdown request failed on port %d: %s", port, exc)
        return {"action": "shutdown-request-failed", "pid": pid, "port": port,
                "port_released": False, "error": str(exc)}

    # confirm the port was released
    for _ in range(15):
        if http_ping(port=port) is None and not is_port_listening(port=port):
            lg.info("stop: daemon stopped, port %d released", port)
            return {"action": "stopped", "pid": pid, "port": port, "port_released": True}
        time.sleep(0.2)
    return {"action": "draining", "pid": pid, "port": port,
            "port_released": False}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "ensure"
    if cmd == "serve":
        serve()
        return 0
    if cmd == "ensure":
        r = ensure_running()
        print(json.dumps(r, ensure_ascii=False, default=str))
        return 0 if r["action"] in ("already-running", "spawned") else 1
    if cmd == "ping":
        h = http_ping()
        if h is None:
            print(json.dumps({"running": False}, ensure_ascii=False))
            return 1
        print(json.dumps({"running": True, "pid": h.get("pid"),
                          "port": h.get("port")}, ensure_ascii=False))
        return 0
    if cmd == "stop":
        r = stop_running()
        print(json.dumps(r, ensure_ascii=False, default=str))
        return 0
    print(f"unknown subcommand '{cmd}'. Available: serve | ensure | ping | stop", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
