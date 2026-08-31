"""HTTP routing: wrong-method hints, plus a structural guard on the handler class.

Why this file exists. Dropping a module-level def inside a class body is perfectly legal
Python: every method indented below it gets swallowed as an inner function of that def,
and `_Handler` silently loses do_GET, do_POST, _dispatch and _csrf_check. `ast.parse()`
returns fine, ruff stays clean, the import does not blow up, and the breakage only shows
when a real HTTP request arrives. So these tests assert on whether the class actually has
the methods, rather than on whether the file parses.
"""
import ast
import os
import time

import pytest

from codesextant import daemon

# Losing any one of these means the whole HTTP service has failed silently.
_REQUIRED_HANDLER_METHODS = ("do_GET", "do_POST", "_dispatch", "_csrf_check")


def test_handler_keeps_its_http_methods():
    for name in _REQUIRED_HANDLER_METHODS:
        assert hasattr(daemon._Handler, name), (
            f"_Handler is missing {name}. The likeliest cause is a module-level def "
            f"dropped inside the class body, swallowing the methods indented after it. "
            f"The syntax is legal and the service is dead.")


def test_handler_methods_are_not_swallowed_by_a_module_level_def():
    """Check again against the source AST: the methods must sit in the class body, not
    merely happen to be reachable."""
    src = os.path.join(os.path.dirname(daemon.__file__), "daemon.py")
    with open(src, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    handler = next((n for n in tree.body
                    if isinstance(n, ast.ClassDef) and n.name == "_Handler"), None)
    assert handler is not None, "no _Handler class definition found"
    methods = {n.name for n in handler.body if isinstance(n, ast.FunctionDef)}
    missing = [m for m in _REQUIRED_HANDLER_METHODS if m not in methods]
    assert not missing, f"these methods are not in the _Handler class body: {missing}"


def test_get_on_a_post_only_route_says_use_post():
    hint = daemon._method_hint("/reindex", daemon._ROUTES_GET)
    assert hint and "POST" in hint, "a GET against a POST-only route should suggest POST"


def test_post_on_a_get_only_route_says_use_get():
    hint = daemon._method_hint("/health", daemon._ROUTES_POST)
    assert hint and "GET" in hint, "a POST against a GET-only route should suggest GET"


def test_genuinely_unknown_path_gets_no_hint():
    """A path that genuinely does not exist gets no hint, or the hints become noise."""
    assert daemon._method_hint("/no_such_endpoint", daemon._ROUTES_GET) is None
    assert daemon._method_hint("/no_such_endpoint", daemon._ROUTES_POST) is None


def test_reindex_is_post_only():
    """Pin this down. It cost a long detour once, and if /reindex ever starts accepting
    GET, this test is the reminder to update the docs alongside it."""
    assert "/reindex" in daemon._ROUTES_POST
    assert "/reindex" not in daemon._ROUTES_GET


def test_a_busy_index_is_an_overload_answer_not_an_internal_error():
    """A reindex holding the write lock must read as "retry", not as a defect.

    Agents are told to back off on 503 and 504. Reported as 500 the same condition looks
    like a bug in CodeSextant and has no documented response, so the caller cannot tell a
    contended index from a broken one.
    """
    import sqlite3
    from urllib.parse import urlparse

    from codesextant import daemon, storage, worker_process

    assert storage.is_busy_index_error("OperationalError", "database is locked")
    assert not storage.is_busy_index_error("OperationalError", "no such table: symbols")

    # Both shapes the condition arrives in: raised inside an isolated route worker and
    # relayed back, or raised directly in the daemon process.
    for failure in (
        worker_process.RouteWorkerError(
            "OperationalError: database is locked",
            error_type="OperationalError", remote_message="database is locked"),
        sqlite3.OperationalError("database is locked"),
    ):
        def handler(_parsed, _body, _failure=failure):
            raise _failure

        with pytest.raises(daemon._HttpError) as caught:
            daemon._execute_route(
                "/get_map", handler, urlparse("/get_map?project=/tmp/x"), None,
                deadline=time.monotonic() + 30)
        assert caught.value.code == 503
        assert caught.value.headers.get("Retry-After")
        assert caught.value.details.get("reason") == "index-busy"


def test_a_real_engine_failure_is_still_an_internal_error():
    """Only lock contention degrades; a genuine fault must not be dressed up as overload."""
    import sqlite3
    from urllib.parse import urlparse

    from codesextant import daemon

    def handler(_parsed, _body):
        raise sqlite3.OperationalError("no such table: symbols")

    with pytest.raises(sqlite3.OperationalError):
        daemon._execute_route(
            "/get_map", handler, urlparse("/get_map?project=/tmp/x"), None,
            deadline=time.monotonic() + 30)


def test_a_worker_killed_before_answering_is_retryable_not_a_defect():
    """SIGKILL comes from outside the work: containment, or a kernel short of memory.

    The request did not finish, but nothing about it was wrong, and the caller's move is
    to retry. Reported as 500 it reads as a defect in CodeSextant and carries no
    documented response.
    """
    from urllib.parse import urlparse

    from codesextant import daemon, worker_process

    def handler(_parsed, _body):
        raise worker_process.RouteWorkerError(
            "route worker exited without a result (exit=-9)", exitcode=-9)

    with pytest.raises(daemon._HttpError) as caught:
        daemon._execute_route(
            "/get_map", handler, urlparse("/get_map?project=/tmp/x"), None,
            deadline=time.monotonic() + 30)

    assert caught.value.code == 503
    assert caught.value.headers.get("Retry-After")
    assert caught.value.details.get("reason") == "worker-killed"


def test_a_worker_that_crashed_is_still_a_defect():
    """A crash signal is a different claim and must not be dressed up as weather."""
    from urllib.parse import urlparse

    from codesextant import daemon, worker_process

    for exitcode in (-11, -6, 1):  # SIGSEGV, SIGABRT, a plain nonzero exit
        def handler(_parsed, _body, _code=exitcode):
            raise worker_process.RouteWorkerError(
                f"route worker exited without a result (exit={_code})", exitcode=_code)

        with pytest.raises(worker_process.RouteWorkerError):
            daemon._execute_route(
                "/get_map", handler, urlparse("/get_map?project=/tmp/x"), None,
                deadline=time.monotonic() + 30)


def test_signal_reading_separates_a_kill_from_a_clean_exit():
    from codesextant import worker_process

    assert worker_process.killed_by_signal(-9) == 9
    assert worker_process.killed_by_signal(-11) == 11
    assert worker_process.killed_by_signal(0) is None
    assert worker_process.killed_by_signal(1) is None
    assert worker_process.killed_by_signal(None) is None


def test_the_kill_reading_survives_a_platform_without_SIGKILL():
    """Windows, exercised from wherever you happen to be.

    `signal.SIGKILL` does not exist there, and naming it raised AttributeError out of
    the very exception handler meant to turn a killed worker into a retryable 503 --
    on four of thirteen CI jobs, for a fault no Linux run could reproduce. The first
    repair swapped the crash for a quieter mistake: resolving the constant to None made
    the predicate answer False on Windows, which is a *different definition of the
    question* by platform, and only Windows CI could say so.

    What is compared is a number. multiprocessing encodes a signal death as the negated
    signal number and SIGKILL is 9 everywhere POSIX defines it, so the reading holds
    with or without the symbol. This removes the symbol and checks that it does, which
    is the difference between a fix and a fix nobody has to push to verify.
    """
    import importlib
    import signal as signal_module

    from codesextant import worker_process

    saved = signal_module.SIGKILL
    del signal_module.SIGKILL
    try:
        windows_like = importlib.reload(worker_process)
        assert windows_like._SIGKILL == 9, "SIGKILL's number is fixed by POSIX"
        assert windows_like.killed_externally(-9) is True
        assert windows_like.killed_externally(-11) is False, "a crash is still a defect"
        assert windows_like.killed_externally(None) is False
    finally:
        signal_module.SIGKILL = saved
        importlib.reload(worker_process)

    assert worker_process.killed_externally(-9) is True
