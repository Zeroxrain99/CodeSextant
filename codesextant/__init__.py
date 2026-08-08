"""codesextant: the pure code-map engine (C1).

The public surface is 5 plain functions whose arguments and return values are
all serializable (dict/list), so the C2 daemon can wrap them as HTTP:
    index_project(path)              → /reindex
    get_symbols(path, file)          → /get_symbols
    find_references(path, symbol)    → /find_references
    get_map(path, token_budget)      → /get_map
    status(path)                     → /status   (+ /health served by the daemon)

Hybrid architecture (proven by the PoC): tree-sitter extracts every symbol
(fast) + jedi resolves references on demand (accurate) + SQLite content-hash
incremental indexing + PageRank importance. Multi-language: tree-sitter symbol
extraction covers 16 languages: Python/JS/TS/TSX/Go/Rust/C#/Java/C/C++/Kotlin/
Swift/PHP/Ruby/Bash/Lua. Reference lookup: Python→jedi, TS/JS→ts-morph (C5b, a
Node subprocess bridge), everything else→name matching (low confidence, falls
back automatically when the bridge is unavailable, and says so).
"""
from __future__ import annotations

import importlib

# C3 is only an HTTP client; importing it must not drag tree-sitter/engine in.
# The public API stays fully compatible with `from codesextant import get_map`
# via PEP 562 lazy attributes. The module loads on first attribute access.
_ENGINE_EXPORTS = {
    "index_project", "index_paths", "get_symbols", "find_references", "find_deadcode",
    "find_unwired", "find_duplicates", "get_comment_overview",
    "find_comment_tags", "get_comments", "call_hierarchy", "impact",
    "get_health", "get_map", "status", "list_projects", "find_ai_usage",
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
    # C1 pure engine
    "index_project",
    "index_paths",
    "get_symbols",
    "find_references",
    "find_deadcode",  # C5c step 3: dead-code clue layer (unused imports + orphan grading + entrypoint exemptions)
    "find_unwired",  # Feature A: unwired check (name-level whole-graph sweep for top-level symbols with zero external references)
    "find_duplicates",  # Feature B: duplicate/near-duplicate detection (structural fingerprint + winnowing)
    "get_comment_overview",  # Feature B: comment summary (docstring coverage / TODO counts / density)
    "find_comment_tags",  # Feature B: TODO/FIXME index (real line numbers)
    "get_comments",  # Feature B: exact comment retrieval
    "call_hierarchy",  # Competitor-parity queue 1: transitive call chains (refs table, WITH RECURSIVE CTE)
    "impact",  # Competitor-parity queue 2: change blast radius (built on call_hierarchy(up))
    "get_health",  # Discipline made presentable: per-symbol code health (D1 bloat / D3 complexity / D5 duplication → health, D6 dead code → dead)
    "get_map",
    "status",
    "list_projects",  # C4: list every project indexed on this machine (data source for the panel overview)
    "find_ai_usage",  # ai-usage: which AI/LLM the repo uses + dispatch_policy cli/direct/local channels
    # C2 daemon
    "ensure_daemon",
    "ping_daemon",
    "stop_daemon",
    # C3 client
    "CodesextantClient",
]

__version__ = "0.16.0"  # ai-usage action: scan a repo for AI/LLM usage + dispatch_policy cli/direct/local channels + a dark HUD relationship graph (three new modules ai_usage.py/ai_usage_patterns.py/ai_usage_html.py, wired into engine/daemon/client/__main__). Prior work: P5 extended cognitive complexity to 5 more languages (+C/C++/Ruby/Kotlin/Swift, 11 high-confidence total; 91 cognitive pytest green, adversarial review wf_ba17da36) plus a 2026-06-23 external check against the original white paper (closely aligned with SonarSource; the one deviation is that indirect recursion is not counted, which under-reports; validity per Muñoz Barón 2020: comprehension time r=0.54 strong, correctness r=-0.13 weak). P4 language expansion: cognitive complexity went from 4 languages (Py/JS/TS/TSX) to 8 (+Go/Rust/Java/C#). Walker generalization: if_style wrapper (wrapped in else_clause, as in Py/TS/Rust) vs field (if.alternative points straight at the if, as in Go/Java/C#, handled by visit_if_field) + if_types as a set (Rust=if_expression) + per-language label_child_types/callee_field; probes proved it out (_probe_if_fields/_probe_labeled/_probe_types, field names consistent across all 8 languages). Golden cases per language: sumOfPrimes=7, field-style else-if, switch/match/do/catch/recursion, and cross-object false-positive guards; 269 pytest, zero regressions. A 5-lens distinct sub-agent adversarial review found 3 bugs, all fixed (C# switch expression not counted; brace-less then-else in a wrapper failed to increment nesting, twice, and that fix also covered the pre-existing P3 TS/JS/TSX game vector). v0.13.0 = health wired back into the real engine (engine.get_health + health.py pure functions, single source of truth for engine and PoC). v0.12.0 = P3 D3 first cut of cognitive complexity (4 languages high confidence, the rest None=UNKNOWN). semver minor, cumulative, never reset
