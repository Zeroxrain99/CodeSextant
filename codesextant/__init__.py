"""Public Python API for CodeSextant.

The package exposes indexing, symbol, reference, ranking, status, daemon, and
client helpers through lazy imports. Symbols are extracted with tree-sitter.
Python references use jedi, TypeScript and JavaScript can use ts-morph, and
other languages return low-confidence name matches.

Lifecycle notes (agent disconnect / reconnect / forget):

* Heavy HTTP workers run in contained process trees (Windows Job Object /
  POSIX process group). Deadline expiry or abrupt parent death reaps the tree;
  agents do not leave orphan workers as a steady-state failure mode.
* Short client disconnects reconnect with ``ensure()`` / ``already-running``
  and reuse the persistent per-project SQLite index (no full reindex).
* Long abandonment is reclaimed by ``cache_gc.prune`` (missing-repo grace,
  idle-present grace, quota LRU) plus disposable temp workspace cleanup.
  Explicit session cleanup: ``codesextant cache --forget PATH``.
"""
from __future__ import annotations

import importlib

# Keep client imports lazy so importing the package does not load the engine.
# The public API stays fully compatible with `from codesextant import get_map`
# via PEP 562 lazy attributes. The module loads on first attribute access.
_ENGINE_EXPORTS = {
    "index_project", "index_paths", "get_symbols", "find_references", "find_deadcode",
    "find_unwired", "find_duplicates", "get_comment_overview",
    "find_comment_tags", "get_comments", "call_hierarchy", "impact",
    "get_health", "get_map", "status", "list_projects", "find_ai_usage",
    "preflight", "check",
}
_DAEMON_EXPORTS = {
    "ensure_daemon": "ensure_running",
    "ping_daemon": "http_ping",
    "stop_daemon": "stop_running",
}


def __getattr__(name: str):
    if name in _ENGINE_EXPORTS:
        value = getattr(importlib.import_module(".engine", __name__), name)
    elif name == "CodesextantClient":
        value = importlib.import_module(".client", __name__).CodesextantClient
    elif name in _DAEMON_EXPORTS:
        value = getattr(
            importlib.import_module(".daemon", __name__), _DAEMON_EXPORTS[name])
    else:
        # Keep `from codesextant import ranking/namegraph/storage/...` working.
        try:
            value = importlib.import_module(f".{name}", __name__)
        except ModuleNotFoundError as exc:
            if exc.name != f"{__name__}.{name}":
                raise
            raise AttributeError(name) from None
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))

__all__ = [
    # Engine
    "index_project",
    "index_paths",
    "get_symbols",
    "find_references",
    "find_deadcode",  # unused imports and orphan-symbol evidence
    "find_unwired",  # top-level symbols with no name-level external references
    "find_duplicates",  # structural duplicate and near-duplicate detection
    "get_comment_overview",  # docstring coverage, tags, and comment density
    "find_comment_tags",  # TODO and FIXME index with source lines
    "get_comments",  # filtered comment retrieval
    "call_hierarchy",  # transitive call chains from the references table
    "impact",  # change impact built on the caller hierarchy
    "get_health",  # per-symbol health and unwired evidence
    "get_map",
    "preflight",  # reuse, co-change obligations and blast radius, before an edit
    "check",  # the same three questions asked of the diff, after an edit
    "status",
    "list_projects",  # projects indexed on this machine
    "find_ai_usage",  # ai-usage: which AI/LLM the repo uses + dispatch_policy cli/direct/local channels
    # Daemon
    "ensure_daemon",
    "ping_daemon",
    "stop_daemon",
    # Client
    "CodesextantClient",
]

__version__ = "0.28.0"
