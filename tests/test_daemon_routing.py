# -*- coding: utf-8 -*-
"""HTTP 路由層：方法用錯的提示，以及「類別方法沒被縮排吃掉」的結構護欄。

⛔ 這個檔存在的理由（2026-07-19 真實事故）：在 class 內部插進一個模組層 def，
Python **語法完全合法**——後面縮排的 method 會被當成那個 def 的內部函式吞掉，
`_Handler` 因此靜默失去 do_GET / do_POST / _dispatch 四個方法。`ast.parse()` 回 OK、
ruff 回 clean，import 也不會炸，要到真的送出一個 HTTP 請求才會壞。
所以這裡直接對「類別到底有沒有這些方法」下斷言，而不是只驗語法。
"""
import ast
import os

from codesextant import daemon

# _Handler 少了任何一個都代表整個 HTTP 服務靜默失效
_REQUIRED_HANDLER_METHODS = ("do_GET", "do_POST", "_dispatch", "_csrf_check")


def test_handler_keeps_its_http_methods():
    for name in _REQUIRED_HANDLER_METHODS:
        assert hasattr(daemon._Handler, name), (
            f"_Handler 少了 {name}——最可能的原因是有人在 class 內部插了一個模組層 def，"
            f"把後面的 method 縮排吞進去了。語法合法但服務全死。")


def test_handler_methods_are_not_swallowed_by_a_module_level_def():
    """直接讀原始碼的 AST 再驗一次：方法要真的掛在 class 底下，不是巧合可存取。"""
    src = os.path.join(os.path.dirname(daemon.__file__), "daemon.py")
    with open(src, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    handler = next((n for n in tree.body
                    if isinstance(n, ast.ClassDef) and n.name == "_Handler"), None)
    assert handler is not None, "找不到 _Handler 類別定義"
    methods = {n.name for n in handler.body if isinstance(n, ast.FunctionDef)}
    missing = [m for m in _REQUIRED_HANDLER_METHODS if m not in methods]
    assert not missing, f"這些方法不在 _Handler 的 class body 裡：{missing}"


def test_get_on_a_post_only_route_says_use_post():
    hint = daemon._method_hint("/reindex", daemon._ROUTES_GET)
    assert hint and "POST" in hint, "GET 打 POST-only 端點時應提示改用 POST"


def test_post_on_a_get_only_route_says_use_get():
    hint = daemon._method_hint("/health", daemon._ROUTES_POST)
    assert hint and "GET" in hint, "POST 打 GET-only 端點時應提示改用 GET"


def test_genuinely_unknown_path_gets_no_hint():
    """真的不存在的路徑不該亂給提示——否則提示本身變成雜訊。"""
    assert daemon._method_hint("/no_such_endpoint", daemon._ROUTES_GET) is None
    assert daemon._method_hint("/no_such_endpoint", daemon._ROUTES_POST) is None


def test_reindex_is_post_only():
    """釘住這個事實：它害我繞了很久，之後若改成支援 GET，這條會提醒同步更新文件。"""
    assert "/reindex" in daemon._ROUTES_POST
    assert "/reindex" not in daemon._ROUTES_GET
