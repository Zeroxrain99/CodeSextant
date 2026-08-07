"""The contention benchmark is a kept tool, so its arithmetic is pinned.

A benchmark that silently reports the wrong inflation factor is worse than no
benchmark: the whole point is that someone re-runs it next week and compares
against the recorded 50.3x / 0.8x numbers.
"""
from __future__ import annotations

import importlib.util
import os
import sys

_TOOL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tools", "bench_contention.py")
_spec = importlib.util.spec_from_file_location("bench_contention", _TOOL)
bench = importlib.util.module_from_spec(_spec)
sys.modules["bench_contention"] = bench
_spec.loader.exec_module(bench)


def test_measure_reports_inflation_when_idle_query_is_blocked(monkeypatch):
    """Reproduce the old-code shape: cheap query inflates while another runs."""
    timings = {
        ("/comment_overview", 1): (1486.0, "200"),   # solo
        ("/get_health", 0): (76256.0, "200"),        # the busy job
        ("/comment_overview", 2): (74772.0, "200"),  # blocked by the busy job
    }
    calls = {"idle": 0}

    def fake_get(_base, path, _params, _timeout):
        if path == "/comment_overview":
            calls["idle"] += 1
            return timings[(path, calls["idle"])]
        return timings[(path, 0)]

    monkeypatch.setattr(bench, "_timed_get", fake_get)
    result = bench.measure(
        "http://x", "E:/big", "E:/small",
        busy_endpoint="/get_health", idle_endpoint="/comment_overview",
        timeout=5, settle_sec=0)

    assert result["idle_solo_ms"] == 1486.0
    assert result["idle_under_load_ms"] == 74772.0
    assert result["inflation_x"] == 50.32


def test_measure_reports_no_inflation_when_lanes_are_sharded(monkeypatch):
    """The fixed shape: cheap query unaffected by another project's load."""
    calls = {"idle": 0}

    def fake_get(_base, path, _params, _timeout):
        if path == "/comment_overview":
            calls["idle"] += 1
            return (624.0, "200") if calls["idle"] == 1 else (482.0, "200")
        return (36549.0, "200")

    monkeypatch.setattr(bench, "_timed_get", fake_get)
    result = bench.measure(
        "http://x", "E:/big", "E:/small",
        busy_endpoint="/get_health", idle_endpoint="/comment_overview",
        timeout=5, settle_sec=0)

    assert result["inflation_x"] == 0.77
    assert result["busy_ms"] == 36549.0


def test_measure_survives_a_failing_request(monkeypatch):
    """A timeout must be reported rather than raised, so that the run still finishes."""
    def fake_get(_base, _path, _params, _timeout):
        return (0.0, "TimeoutError")

    monkeypatch.setattr(bench, "_timed_get", fake_get)
    result = bench.measure(
        "http://x", "E:/big", "E:/small",
        busy_endpoint="/get_health", idle_endpoint="/comment_overview",
        timeout=1, settle_sec=0)

    assert result["idle_solo_status"] == "TimeoutError"
    assert result["inflation_x"] is None, "divide-by-zero must not fabricate a ratio"


def test_timed_get_returns_exception_name_instead_of_raising(monkeypatch):
    def boom(*_args, **_kwargs):
        raise ConnectionRefusedError("no daemon")

    monkeypatch.setattr(bench.urllib.request, "urlopen", boom)
    ms, status = bench._timed_get("http://127.0.0.1:1", "/health", {}, 1)
    assert status == "ConnectionRefusedError"
    assert ms >= 0
