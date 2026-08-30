"""Active deadline enforcement for isolated heavy route workers."""
from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import pickle
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _return_immediately(connection, _method, _target, _body, _deadline) -> None:
    connection.send_bytes(json.dumps(
        {"kind": "result", "value": [200, {"ok": True}]}
    ).encode("utf-8"))
    connection.close()


def _sleep_past_deadline(connection, _method, _target, _body, _deadline) -> None:
    try:
        time.sleep(30)
    finally:
        connection.close()


def _return_after_delay(connection, _method, _target, _body, _deadline) -> None:
    time.sleep(0.3)
    _return_immediately(connection, _method, _target, _body, _deadline)


def _send_oversized(connection, _method, _target, _body, _deadline) -> None:
    connection.send_bytes(b"x" * 4096)
    connection.close()


def _send_body_bytes(connection, _method, _target, body, _deadline) -> None:
    connection.send_bytes(body["raw"])
    connection.close()


def _send_partial_frame(connection, _method, _target, _body, _deadline) -> None:
    connection._send(struct.pack("!i", 4096))  # noqa: SLF001
    time.sleep(30)


def _write_marker(path: str) -> str:
    Path(path).write_text("executed", encoding="utf-8")
    return path


class _PickleGadget:
    def __init__(self, path: str):
        self.path = path

    def __reduce__(self):
        return _write_marker, (self.path,)


def _spawn_grandchild(connection, _method, _target, body, _deadline) -> None:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    grandchild = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        creationflags=creationflags,
    )
    Path(body["pid_file"]).write_text(
        f"{os.getpid()}\n{grandchild.pid}\n", encoding="ascii")
    try:
        time.sleep(30)
    finally:
        connection.close()


def _owner_with_contained_worker(pid_file: str) -> None:
    from codesextant import worker_process

    worker_process.run_route(
        "GET",
        "/get_map",
        {"pid_file": pid_file},
        deadline=time.monotonic() + 30,
        child_target=_spawn_grandchild,
    )


def _pid_is_active(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        return bool(
            kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            and exit_code.value == 259
        )
    finally:
        kernel32.CloseHandle(handle)


def _wait_for_pids_to_exit(pids: list[int], timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_pid_is_active(pid) for pid in pids):
            return True
        time.sleep(0.05)
    return not any(_pid_is_active(pid) for pid in pids)


def test_worker_returns_route_result() -> None:
    from codesextant import worker_process

    result = worker_process.run_route(
        "GET",
        "/get_map",
        None,
        deadline=time.monotonic() + 5,
        child_target=_return_immediately,
    )

    assert result == (200, {"ok": True})


def test_deadline_terminates_and_reaps_worker() -> None:
    from codesextant import worker_process

    before = {child.pid for child in multiprocessing.active_children()}
    started = time.monotonic()

    with pytest.raises(worker_process.WorkerDeadlineExceeded):
        worker_process.run_route(
            "POST",
            "/reindex",
            {},
            deadline=time.monotonic() + 0.25,
            child_target=_sleep_past_deadline,
        )

    elapsed = time.monotonic() - started
    after = {child.pid for child in multiprocessing.active_children()}
    assert elapsed < 10
    assert after <= before


def test_dynamic_shared_deadline_keeps_worker_for_longer_lived_follower() -> None:
    """A follower with a longer deadline keeps a worker its own owner would have killed.

    The claim is that run_route re-reads the deadline through deadline_provider instead
    of fixing it once, so the extension is applied through the provider itself, on the
    consultation that happens after the worker has started. Extending from a thread that
    sleeps first cannot work: the sleeper needs the GIL to do it, and the main thread is
    inside process.start(), which on a loaded runner holds the GIL well past the 0.15s
    the original deadline allowed.
    """
    from codesextant import worker_process

    original_deadline = time.monotonic() + 0.15
    shared_deadline = [original_deadline]
    consulted: list[float] = []

    def provider() -> float:
        consulted.append(time.monotonic())
        if len(consulted) == 2:  # the first consultation after the worker started
            shared_deadline[0] = time.monotonic() + 10.0
        return shared_deadline[0]

    result = worker_process.run_route(
        "GET",
        "/get_map",
        None,
        deadline=original_deadline,
        deadline_provider=provider,
        child_deadline=time.monotonic() + 12.0,
        child_target=_return_after_delay,
    )

    assert result == (200, {"ok": True})
    assert len(consulted) > 2, (
        "the deadline has to be consulted repeatedly, or extending it could not help")
    assert shared_deadline[0] > original_deadline


def test_worker_rejects_oversized_result_without_blocking(monkeypatch) -> None:
    from codesextant import worker_process

    monkeypatch.setenv("CODESEXTANT_WORKER_RESPONSE_MAX_BYTES", "1024")
    with pytest.raises(worker_process.RouteWorkerError, match="result channel"):
        worker_process.run_route(
            "GET",
            "/get_symbols",
            None,
            deadline=time.monotonic() + 5,
            child_target=_send_oversized,
        )


def test_worker_result_channel_never_unpickles_child_bytes(tmp_path) -> None:
    from codesextant import worker_process

    marker = tmp_path / "pickle-executed"
    raw = pickle.dumps(_PickleGadget(str(marker)))

    with pytest.raises(worker_process.RouteWorkerError, match="result channel"):
        worker_process.run_route(
            "GET",
            "/get_symbols",
            {"raw": raw},
            deadline=time.monotonic() + 5,
            child_target=_send_body_bytes,
        )

    assert not marker.exists()


def test_partial_result_frame_cannot_block_past_deadline() -> None:
    from codesextant import worker_process

    if os.name == "nt":
        pytest.skip("Windows named-pipe messages are delivered atomically")
    started = time.monotonic()
    with pytest.raises(worker_process.WorkerDeadlineExceeded):
        worker_process.run_route(
            "GET",
            "/get_symbols",
            None,
            deadline=time.monotonic() + 5.0,
            child_target=_send_partial_frame,
        )

    assert time.monotonic() - started < 10.0


def test_request_deadline_kills_worker_and_real_grandchild(tmp_path) -> None:
    from codesextant import worker_process

    pid_file = tmp_path / "deadline-pids"
    with pytest.raises(worker_process.WorkerDeadlineExceeded):
        worker_process.run_route(
            "GET",
            "/get_map",
            {"pid_file": str(pid_file)},
            deadline=time.monotonic() + 15.0,
            child_target=_spawn_grandchild,
        )
    pids = [int(value) for value in pid_file.read_text(encoding="ascii").split()]
    assert _wait_for_pids_to_exit(pids)


def test_abrupt_owner_exit_kills_worker_and_real_grandchild(tmp_path) -> None:
    pid_file = tmp_path / "owner-pids"
    owner = multiprocessing.get_context("spawn").Process(
        target=_owner_with_contained_worker,
        args=(str(pid_file),),
    )
    owner.start()
    # Nested spawn (owner process + contained worker + grandchild) is slow on a
    # loaded Windows desktop; wait long enough for the pid marker only.
    deadline = time.monotonic() + 30
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert pid_file.exists(), (
        f"owner process never published pid marker "
        f"(alive={owner.is_alive()}, exitcode={owner.exitcode})"
    )
    pids = [int(value) for value in pid_file.read_text(encoding="ascii").split()]

    owner.terminate()
    owner.join(timeout=5)

    assert not owner.is_alive()
    assert _wait_for_pids_to_exit(pids)
