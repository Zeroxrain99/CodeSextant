"""Defer an expensive module import until something actually reaches into it.

Heavy HTTP routes run in a spawned child process, and a spawned child imports from
cold: nothing is inherited from the daemon. Importing ``codesextant.engine`` eagerly
pulls in jedi and the tree-sitter language pack, about 90ms, and it pulled them in for
every route -- including a cached ``get_map``, which resolves no references and parses
no source. That import was most of the request.

``LazyModule`` keeps the module reachable as an attribute (so ``engine.references``
still names something, and tests can still patch through it) while charging the import
to the first attribute access.
"""
from __future__ import annotations

import importlib
from types import ModuleType


class LazyModule:
    """A stand-in that imports its module on first attribute access."""

    __slots__ = ("_module_name", "_loaded")

    def __init__(self, module_name: str):
        object.__setattr__(self, "_module_name", module_name)
        object.__setattr__(self, "_loaded", None)

    def _load(self) -> ModuleType:
        module = object.__getattribute__(self, "_loaded")
        if module is None:
            module = importlib.import_module(
                object.__getattribute__(self, "_module_name"))
            object.__setattr__(self, "_loaded", module)
        return module

    def __getattr__(self, name: str):
        return getattr(self._load(), name)

    def __setattr__(self, name: str, value) -> None:
        # Patching through the stand-in has to reach the real module, or a test that
        # replaces one function would silently leave the original in place for every
        # caller that imported the module directly.
        setattr(self._load(), name, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._load(), name)

    def __dir__(self):
        return dir(self._load())

    def __repr__(self) -> str:
        loaded = object.__getattribute__(self, "_loaded")
        name = object.__getattribute__(self, "_module_name")
        return f"<LazyModule {name} {'loaded' if loaded else 'deferred'}>"


def loaded_module(candidate) -> ModuleType | None:
    """The module a LazyModule has already imported, or None.

    Never triggers the import. Shutdown asks "did anything actually use the engine?" so
    it can drain that module's background writers; answering by importing it would make
    the question create the thing it is asking about.
    """
    if isinstance(candidate, LazyModule):
        return object.__getattribute__(candidate, "_loaded")
    return None
