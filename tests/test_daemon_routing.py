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
