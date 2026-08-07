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
