"""HTTP regression for interactive graph latency during a same-project rebuild."""

from __future__ import annotations

import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor


def _percentile(samples: list[float], percentile: int) -> float:
    values = statistics.quantiles(samples, n=100, method="inclusive")
    return values[percentile - 1]


def test_map_references_and_impact_meet_deadline_during_reindex(
        tmp_path, monkeypatch):
    from codesextant import client, daemon, work_coordinator

    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "0")
    monkeypatch.setenv("CODESEXTANT_INTERACTIVE_TIMEOUT_SEC", "2")
    monkeypatch.setenv("CODESEXTANT_REINDEX_TIMEOUT_SEC", "35")
    monkeypatch.setenv("CODESEXTANT_IDLE_TIMEOUT_SEC", "0")

    entered = threading.Event()
    release = threading.Event()

    def reindex(_parsed, _body):
        entered.set()
        if not release.wait(timeout=30):
            raise TimeoutError("test rebuild was not released")
        return 200, {"indexed": 1}

    monkeypatch.setitem(daemon._ROUTES_POST, "/reindex", reindex)
    monkeypatch.setitem(
        daemon._ROUTES_GET,
        "/get_map",
        lambda _parsed, _body: (200, {"route": "map"}),
    )
    monkeypatch.setitem(
        daemon._ROUTES_POST,
        "/find_references",
        lambda _parsed, _body: (200, {"route": "references"}),
    )
    monkeypatch.setitem(
        daemon._ROUTES_POST,
        "/impact",
        lambda _parsed, _body: (200, {"route": "impact"}),
    )
    coordinator = work_coordinator.ShardedHeavyWork(
        global_capacity=2,
        interactive_global_reserve=1,
        hard_timeout_sec=0,
    )
    monkeypatch.setattr(daemon, "_HEAVY_COORDINATOR", coordinator)

    server = daemon._ExclusiveThreadingHTTPServer(
        (daemon.HOST, 0), daemon._Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    api = client.CodesextantClient(
        project=str(project), port=server.server_port, timeout=2)
    rebuild_errors: list[BaseException] = []

    def run_rebuild() -> None:
        try:
            api.reindex()
        except BaseException as exc:
            rebuild_errors.append(exc)

    rebuild = threading.Thread(target=run_rebuild)
    rebuild.start()

    samples: list[float] = []

    def timed(call, expected: str) -> None:
        started = time.perf_counter()
        result = call()
        samples.append((time.perf_counter() - started) * 1000)
        assert result["route"] == expected

    try:
        assert entered.wait(timeout=2)
        for _ in range(20):
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = (
                    pool.submit(timed, api.get_map, "map"),
                    pool.submit(
                        timed, lambda: api.find_references("target"),
                        "references"),
                    pool.submit(
                        timed, lambda: api.impact("target"), "impact"),
                )
                for future in futures:
                    future.result(timeout=2)
    finally:
        release.set()
        rebuild.join(timeout=10)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

    assert not rebuild.is_alive()
    assert rebuild_errors == []
    assert len(samples) == 60
    p95 = _percentile(samples, 95)
    p99 = _percentile(samples, 99)
    print(json.dumps({
        "samples": len(samples),
        "p95_ms": round(p95, 3),
        "p99_ms": round(p99, 3),
        "deadline_ms": 2000,
    }))
    assert p99 < 1500
