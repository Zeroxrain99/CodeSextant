"""Code CodeSextant cannot see is code CodeSextant will not warn you about.

Modules are bound lazily in several places here, because a spawned route worker
imports the package from cold on every heavy request and tree-sitter plus jedi cost
about 85ms it would otherwise always pay. The cost of that trick is invisibility: a
call through an unannotated proxy resolves to nothing, so those callers went missing
from CodeSextant's own blast radius -- the tool was blind to its own codebase in
exactly the way it exists to prevent.

A `if TYPE_CHECKING:` branch fixes it without giving the laziness back, because it
never runs. These tests pin both halves: that the idiom really does restore
resolution, and that no lazy binding here is left outside it.
"""
from __future__ import annotations

import ast
import pathlib
import textwrap

import pytest

from codesextant import daemon, engine, mcp_server

_GUARDED_MODULES = (engine, daemon, mcp_server)


def _write(root: pathlib.Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")


@pytest.fixture()
def lazy_package(tmp_path, monkeypatch):
    """A package that binds a module lazily, the way this codebase does."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "proj"
    _write(root, "pkg/__init__.py", "")
    _write(root, "pkg/target.py", """
        def do_the_work(value):
            return value + 1
    """)
    return root


def test_a_lazily_bound_module_hides_its_callers(lazy_package):
    """The baseline, so the fix below is measured against a real failure."""
    _write(lazy_package, "pkg/caller.py", """
        from codesextant.lazy_import import LazyModule

        target = LazyModule("pkg.target")


        def run():
            return target.do_the_work(1)
    """)
    engine.index_project(str(lazy_package), force=True)

    result = engine.find_references(str(lazy_package), "do_the_work",
                                    def_path=str(lazy_package / "pkg" / "target.py"))

    assert result["high_confidence"] == [], (
        "if this ever resolves on its own, the TYPE_CHECKING branches below are "
        "no longer buying anything and should go")


def test_a_type_checking_branch_restores_resolution_without_the_import(lazy_package):
    """The branch never executes, so laziness is kept and the caller is still found."""
    _write(lazy_package, "pkg/caller.py", """
        from typing import TYPE_CHECKING

        from codesextant.lazy_import import LazyModule

        if TYPE_CHECKING:
            from pkg import target
        else:
            target = LazyModule("pkg.target")


        def run():
            return target.do_the_work(1)
    """)
    engine.index_project(str(lazy_package), force=True)

    result = engine.find_references(str(lazy_package), "do_the_work",
                                    def_path=str(lazy_package / "pkg" / "target.py"))

    assert [pathlib.Path(ref["src_path"]).name for ref in result["high_confidence"]] == [
        "caller.py"]


def _lazily_bound_names(tree: ast.Module) -> set[str]:
    """Names assigned the result of a LazyModule(...) call, anywhere in the module."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                and value.func.id == "LazyModule"):
            continue
        bound.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return bound


def _names_imported_under_type_checking(tree: ast.Module) -> set[str]:
    declared: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                and node.test.id == "TYPE_CHECKING"):
            continue
        for statement in ast.walk(node):
            if isinstance(statement, (ast.Import, ast.ImportFrom)):
                declared.update(alias.asname or alias.name.split(".")[0]
                                for alias in statement.names)
    return declared


@pytest.mark.parametrize("module", _GUARDED_MODULES, ids=lambda m: m.__name__)
def test_every_lazy_binding_is_declared_for_static_analysis(module):
    """A new lazy binding added without the guard reintroduces the blind spot silently.

    Silently is the problem: nothing fails, the module keeps working, and one more of
    this codebase's own call edges just stops existing as far as its own index is
    concerned.
    """
    tree = ast.parse(pathlib.Path(module.__file__).read_text(encoding="utf-8"))
    lazily_bound = _lazily_bound_names(tree)
    assert lazily_bound, "this module is expected to bind modules lazily"
    undeclared = lazily_bound - _names_imported_under_type_checking(tree)
    assert not undeclared, (
        f"{sorted(undeclared)} are bound to LazyModule without a matching import "
        "under `if TYPE_CHECKING:`, so calls through them resolve to nothing")
