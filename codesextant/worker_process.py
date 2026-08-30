"""Deadline-bound subprocess execution for HTTP engine routes.

Python threads cannot safely interrupt Jedi, tree-sitter, SQLite, or a child
Node.js bridge in the middle of a native call. Heavy HTTP routes therefore run
in a disposable child process. The daemon owns and contains that exact process
tree, then reaps it before releasing the execution slot.
"""
from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import queue
import signal
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse


class WorkerDeadlineExceeded(TimeoutError):
    """The route worker exceeded the caller's monotonic deadline."""


class RouteWorkerError(RuntimeError):
    """A route worker exited without a successful endpoint result.

    ``error_type`` and ``remote_message`` carry the child's own classification, so the
    caller can tell a busy index from a broken one without parsing the joined string.
    """

    def __init__(self, message: str, *, error_type: str = "",
                 remote_message: str = ""):
        super().__init__(message)
        self.error_type = error_type
        self.remote_message = remote_message


class RemoteHttpError(RuntimeError):
    """A controlled HTTP error raised inside the isolated worker."""

    def __init__(self, code: int, message: str, *, headers: dict | None = None,
                 details: dict | None = None):
        super().__init__(message)
        self.code = int(code)
        self.message = message
        self.headers = dict(headers or {})
        self.details = dict(details or {})


def _send_json(connection, payload: dict) -> None:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    connection.send_bytes(raw)


def _route_child(send_connection, method: str, target: str,
                 body: dict | None, deadline: float) -> None:
    """Import the route table in a clean interpreter and return one result."""
    os.environ["CODESEXTANT_ROUTE_DEADLINE_MONOTONIC"] = repr(deadline)
    os.environ["CODESEXTANT_ROUTE_WORKER_CHILD"] = "1"
    try:
        from . import daemon

        parsed = urlparse(target)
        routes = daemon._ROUTES_GET if method == "GET" else daemon._ROUTES_POST
        handler = routes.get(parsed.path)
        if handler is None:
            raise RuntimeError(f"isolated route is not registered: {method} {parsed.path}")
        value = handler(parsed, body)
        _send_json(send_connection, {"kind": "result", "value": value})
    except BaseException as exc:  # noqa: BLE001
        if hasattr(exc, "code") and hasattr(exc, "msg"):
            payload = {
                "kind": "http-error",
                "code": int(exc.code),
                "message": str(exc.msg),
                "headers": dict(getattr(exc, "headers", {}) or {}),
                "details": dict(getattr(exc, "details", {}) or {}),
            }
        else:
            payload = {
                "kind": "error",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        try:
            _send_json(send_connection, payload)
        except (BrokenPipeError, EOFError, OSError):
            pass


def _kill_group_when_parent_closes(connection) -> None:
    """Block on a parent-owned pipe and kill the POSIX worker group at EOF."""
    try:
        connection.recv_bytes()
    except (EOFError, OSError):
        try:
            os.killpg(os.getpid(), signal.SIGKILL)
        except OSError:
            os._exit(71)


def _contained_child_entry(child_target, send_connection, method: str,
                           target: str, body: dict | None, deadline: float,
                           start_event, lifetime_connection) -> None:
    """Establish containment before allowing repository work to begin."""
    if os.name != "nt":
        try:
            os.setsid()
        except OSError:
            pass
        guardian = threading.Thread(
            target=_kill_group_when_parent_closes,
            args=(lifetime_connection,),
            name="codesextant-parent-lifetime-guard",
            daemon=True,
        )
        guardian.start()
    try:
        remaining = max(0.0, deadline - time.monotonic())
        if not start_event.wait(timeout=remaining):
            return
        child_target(send_connection, method, target, body, deadline)
    finally:
        send_connection.close()
        if lifetime_connection is not None:
            lifetime_connection.close()


class _WindowsJob:
    """A parent-owned Job Object that kills the assigned worker tree on close."""

    def __init__(self, handle, kernel32):
        self.handle = handle
        self._kernel32 = kernel32
        self._closed = False

    def assign(self, pid: int) -> None:
        process_access = 0x0001 | 0x0100 | 0x1000
        process_handle = self._kernel32.OpenProcess(
            process_access, False, int(pid))
        if not process_handle:
            raise OSError(ctypes.get_last_error(), "OpenProcess failed")
        try:
            if not self._kernel32.AssignProcessToJobObject(
                    self.handle, process_handle):
                raise OSError(
                    ctypes.get_last_error(), "AssignProcessToJobObject failed")
        finally:
            self._kernel32.CloseHandle(process_handle)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._kernel32.CloseHandle(self.handle)


def _create_windows_job() -> _WindowsJob | None:
    if os.name != "nt":
        return None
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
    ]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise RouteWorkerError("Windows worker containment could not be created")
    information = ExtendedLimitInformation()
    information.BasicLimitInformation.LimitFlags = 0x00002000
    if not kernel32.SetInformationJobObject(
            handle, 9, ctypes.byref(information), ctypes.sizeof(information)):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        raise RouteWorkerError(
            f"Windows worker containment could not be configured ({error})")
    return _WindowsJob(handle, kernel32)


def _terminate_contained_process(process, job: _WindowsJob | None, *,
                                 join_timeout: float = 5.0) -> None:
    """Terminate only the process tree owned by this daemon request."""
    if job is not None:
        job.close()
    elif process.pid is not None and os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            process.terminate()
    elif process.is_alive():
        process.terminate()
    process.join(timeout=max(0.1, join_timeout))
    if process.is_alive():
        if os.name != "nt" and process.pid is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
        process.kill()
        process.join(timeout=max(0.1, join_timeout))


def _response_max_bytes() -> int:
    try:
        configured = int(os.environ.get(
            "CODESEXTANT_WORKER_RESPONSE_MAX_BYTES", str(64 * 1024 * 1024)))
    except (TypeError, ValueError):
        configured = 64 * 1024 * 1024
    return min(max(1024, configured), 512 * 1024 * 1024)


def _read_one_message(connection, output: queue.Queue) -> None:
    try:
        raw = connection.recv_bytes(maxlength=_response_max_bytes())
        payload = json.loads(raw.decode("utf-8"))
        output.put((True, payload))
    except BaseException as exc:  # noqa: BLE001
        output.put((False, exc))


def _validated_result(payload: Any) -> tuple[int, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("kind"), str):
        raise RouteWorkerError("route worker returned an invalid JSON envelope")
    kind = payload["kind"]
    if kind == "result":
        value = payload.get("value")
        if (not isinstance(value, list) or len(value) != 2
                or not isinstance(value[0], int)
                or not isinstance(value[1], dict)):
            raise RouteWorkerError("route worker returned an invalid endpoint result")
        return value[0], value[1]
    if kind == "http-error":
        code = payload.get("code")
        message = payload.get("message")
        headers = payload.get("headers", {})
        details = payload.get("details", {})
        if (not isinstance(code, int) or not isinstance(message, str)
                or not isinstance(headers, dict) or not isinstance(details, dict)
                or not all(isinstance(k, str) and isinstance(v, str)
                           for k, v in headers.items())):
            raise RouteWorkerError("route worker returned an invalid HTTP error")
        raise RemoteHttpError(
            code, message, headers=headers, details=details)
    if kind == "error":
        error_type = payload.get("error_type", "RouteWorkerError")
        message = payload.get("message", "isolated route failed")
        if not isinstance(error_type, str) or not isinstance(message, str):
            raise RouteWorkerError("route worker returned an invalid error")
        raise RouteWorkerError(f"{error_type}: {message}",
                               error_type=error_type, remote_message=message)
    raise RouteWorkerError("route worker returned an unknown JSON message")


def run_route(
    method: str,
    target: str,
    body: dict | None,
    *,
    deadline: float,
    deadline_provider: Callable[[], float | None] | None = None,
    child_deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    context=None,
    child_target: Callable = _route_child,
) -> tuple[int, Any]:
    """Run one route in a contained spawned child and enforce its deadline."""
    def effective_deadline() -> float:
        current = deadline_provider() if deadline_provider is not None else deadline
        if current is None:
            return child_deadline if child_deadline is not None else deadline
        return current

    if effective_deadline() - clock() <= 0:
        raise WorkerDeadlineExceeded("request deadline expired before worker start")
    execution_deadline = max(
        deadline,
        child_deadline if child_deadline is not None else deadline,
    )
    ctx = context or multiprocessing.get_context("spawn")
    receive_connection, send_connection = ctx.Pipe(duplex=False)
    start_event = ctx.Event()
    lifetime_receive = lifetime_send = None
    if os.name != "nt":
        lifetime_receive, lifetime_send = ctx.Pipe(duplex=False)
    job = _create_windows_job()
    process = ctx.Process(
        target=_contained_child_entry,
        args=(
            child_target,
            send_connection,
            method,
            target,
            body,
            execution_deadline,
            start_event,
            lifetime_receive,
        ),
        name="codesextant-route-worker",
        daemon=False,
    )
    messages: queue.Queue = queue.Queue(maxsize=1)
    reader = threading.Thread(
        target=_read_one_message,
        args=(receive_connection, messages),
        name="codesextant-worker-result-reader",
        daemon=True,
    )
    try:
        process.start()
        send_connection.close()
        if lifetime_receive is not None:
            lifetime_receive.close()
        if job is not None:
            try:
                job.assign(process.pid)
            except BaseException:
                _terminate_contained_process(process, job, join_timeout=1.0)
                raise
        if effective_deadline() - clock() <= 0:
            _terminate_contained_process(process, job, join_timeout=1.0)
            raise WorkerDeadlineExceeded(
                "request deadline expired before worker execution")
        start_event.set()
        reader.start()
        while True:
            remaining = effective_deadline() - clock()
            if remaining <= 0:
                _terminate_contained_process(process, job)
                raise WorkerDeadlineExceeded(
                    f"isolated route exceeded its request deadline ({target.split('?', 1)[0]})"
                )
            try:
                ok, value = messages.get(timeout=min(0.05, remaining))
            except queue.Empty:
                if not process.is_alive():
                    process.join(timeout=0.1)
                    try:
                        ok, value = messages.get_nowait()
                    except queue.Empty:
                        raise RouteWorkerError(
                            "route worker exited without a result "
                            f"(exit={process.exitcode})") from None
                else:
                    continue
            if not ok:
                raise RouteWorkerError(
                    f"route worker result channel failed: {type(value).__name__}")
            process.join(timeout=min(
                1.0, max(0.0, effective_deadline() - clock())))
            if process.is_alive():
                _terminate_contained_process(process, job, join_timeout=1.0)
            return _validated_result(value)
    except BaseException:
        if process.is_alive():
            _terminate_contained_process(process, job)
        raise
    finally:
        if lifetime_send is not None:
            lifetime_send.close()
        receive_connection.close()
        try:
            send_connection.close()
        except OSError:
            pass
        if job is not None:
            job.close()
        if reader.is_alive():
            reader.join(timeout=1.0)
