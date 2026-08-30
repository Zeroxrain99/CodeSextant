"""Shared test fixtures and synchronization helpers.

Keep the test suite out of the operator's live CodeSextant home.

Both ``storage.default_db_dir()`` and ``supervisor._logger()`` resolve through
``CODESEXTANT_HOME``.  Without this fixture a plain ``pytest`` run writes into
``~/.codesextant``, most visibly by appending fabricated
``heavy job stuck ... pid=7 ... active_for_sec=5400.0`` ERROR lines to the real
``supervisor.log`` (from the recycle tests), which then reads like a production
incident during a postmortem.  Spawned daemon subprocesses inherit the variable,
so they are redirected too.

Individual tests may still monkeypatch ``storage.default_db_dir``; this fixture
only moves the default so that *forgetting* to isolate can no longer touch live
operator state.
"""
from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable

import pytest


def wait_until(predicate: Callable[[], object], *, timeout: float = 5.0,
               message: str = "", interval: float = 0.005) -> None:
    """Block until ``predicate()`` is truthy, or fail the test saying what never happened.

    Use this wherever a test needs a background thread to have reached some state before
    the next assertion makes sense: a request occupying a handler slot, a job reaching a
    queue, a watcher registering a path.

    Sleeping instead is the bug this helper exists to prevent. ``time.sleep`` may only be
    used to *advance* time -- to let a deadline you deliberately set actually expire. It
    must never be used to *establish* a precondition, because "long enough on my machine"
    is not a synchronization primitive: the assert that follows then fails on whichever
    CI runner happens to be slower that day, and reads like a real defect.

    The rule, stated as a test you can apply to any sleep you are about to write:

        If the assertion after a ``time.sleep`` could fail merely because the machine
        is slow, the sleep is doing a job it cannot do. Sleep to pass time; observe
        the state you actually need.
    """
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value:
            return
        if time.monotonic() >= deadline:
            raise AssertionError(
                message or f"condition never became true within {timeout}s")
        time.sleep(min(interval, max(0.0, deadline - time.monotonic())))


@pytest.fixture(autouse=True, scope="session")
def _isolate_codesextant_home(tmp_path_factory):
    home = tmp_path_factory.mktemp("codesextant_home")
    previous = os.environ.get("CODESEXTANT_HOME")
    os.environ["CODESEXTANT_HOME"] = str(home)
    try:
        yield home
    finally:
        if previous is None:
            os.environ.pop("CODESEXTANT_HOME", None)
        else:
            os.environ["CODESEXTANT_HOME"] = previous


def thread_is_executing(thread: object, function_name: str) -> bool:
    """Whether ``thread`` currently has ``function_name`` somewhere on its stack.

    Some states have no flag to poll: "the callback has started and is now blocked on a
    lock the test holds" is invisible from outside, because the thread that would set a
    flag is the one that is stuck. Reading the thread's frame observes it directly,
    which is still an observation rather than an assumption about how long it takes.
    """
    ident = getattr(thread, "ident", None)
    if ident is None:
        return False
    frame = sys._current_frames().get(ident)
    while frame is not None:
        if frame.f_code.co_name == function_name:
            return True
        frame = frame.f_back
    return False
