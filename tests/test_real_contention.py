"""End-to-end contention regression using the real graph engine and store."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import urllib.error
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

INTERACTIVE_DEADLINE_MS = 15_000.0
STATUS_DEADLINE_MS = 1_500.0
HEALTH_P99_DEADLINE_MS = 1_000.0


def _percentile(samples: list[float], percentile: int) -> float:
    """Return a linearly interpolated percentile for a small latency sample."""
    ordered = sorted(samples)
    position = (len(ordered) - 1) * percentile / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _write_real_project(project: Path) -> Path:
    definition = project / "core.py"
    definition.write_text(
        "def target(value: int) -> int:\n"
        "    return value + 1\n",
        encoding="utf-8",
    )
    for module_number in range(72):
        functions = ["from core import target", ""]
        for function_number in range(4):
            functions.extend((
                "def caller_"
                f"{module_number:03d}_{function_number:02d}"
                "(value: int) -> int:",
                "    return target(value)",
                "",
            ))
        (project / f"module_{module_number:03d}.py").write_text(
            "\n".join(functions), encoding="utf-8")
    return definition


def _timed_samples(
    invoke: Callable[[], dict],
    validate: Callable[[dict], None],
    count: int,
) -> list[float]:
    samples: list[float] = []
    for _ in range(count):
        started = time.perf_counter()
        result = invoke()
        samples.append((time.perf_counter() - started) * 1000)
        validate(result)
    return samples


def test_real_queries_and_control_plane_meet_deadlines_during_repeated_reindex(
    tmp_path, monkeypatch, request,
):
    """Real reindex work must not starve signed graph or control requests."""
    from codesextant import client, daemon, storage, watcher, work_coordinator

    project = tmp_path / "repo"
    project.mkdir()
    definition = _write_real_project(project)

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "1")
    monkeypatch.setenv("CODESEXTANT_IDLE_TIMEOUT_SEC", "0")
    monkeypatch.setenv("CODESEXTANT_INTERACTIVE_TIMEOUT_SEC", "15")
    monkeypatch.setenv("CODESEXTANT_REINDEX_TIMEOUT_SEC", "60")
    monkeypatch.delenv("CODESEXTANT_SQLITE_UNSAFE_WAL", raising=False)
    monkeypatch.delenv("CODESEXTANT_SQLITE_WAL", raising=False)
    monkeypatch.delenv("CODESEXTANT_SQLITE_BUSY_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("CODESEXTANT_SQLITE_SYNC_NORMAL", raising=False)
    monkeypatch.delenv("CODESEXTANT_HEAVY_GLOBAL_CAP", raising=False)
    monkeypatch.delenv(
        "CODESEXTANT_INTERACTIVE_GLOBAL_RESERVE", raising=False)
    monkeypatch.delenv("CODESEXTANT_ROUTE_WORKER_PROCESS", raising=False)

    coordinator = work_coordinator.ShardedHeavyWork(
        hard_timeout_sec=0,
    )
    monkeypatch.setattr(daemon, "_HEAVY_COORDINATOR", coordinator)
    watch_manager = watcher.WatchManager(
        daemon.get_logger(), idle_ttl_sec=3600)
    monkeypatch.setattr(daemon, "_WATCH_MGR", watch_manager)
    monkeypatch.setattr(daemon, "_get_watch_mgr", lambda: watch_manager)

    server = daemon._ExclusiveThreadingHTTPServer(
        (daemon.HOST, 0), daemon._Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = server.server_port
    server_closed = threading.Event()

    def close_server() -> None:
        if server_closed.is_set():
            return
        server_closed.set()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        daemon._join_recovery_threads()
        watch_manager.stop_all()

    request.addfinalizer(close_server)

    setup_client = client.CodesextantClient(
        project=str(project), port=port, timeout=30)
    status_client = client.CodesextantClient(
        project=str(project), port=port, timeout=1.5)
    first_index = setup_client.reindex(force=True)
    assert first_index["indexed"] == 73

    initial_health = setup_client.health()
    assert initial_health["watcher"]["enabled"] is True
    assert str(project.resolve()) in initial_health["watcher"]["watched"]
    sqlite_policy = initial_health["sqlite"]
    assert sqlite_policy["unsafe_wal_override"] is False
    assert sqlite_policy["wal_allowed"] is (
        sqlite_policy["wal_requested"] and sqlite_policy["wal_safe"])
    with closing(sqlite3.connect(storage.db_path_for(str(project)))) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert (journal_mode.lower() == "wal") is sqlite_policy["wal_allowed"]
    admission = initial_health["heavy_work"]
    assert admission["global_capacity"] == 4
    assert admission["interactive_global_reserve"] == 3
    ready_status = status_client.status(fresh=False)
    assert ready_status["indexed"] is True
    # Partial is allowed here for the same reason the loop below allows it: the watcher
    # is attached with a two-second debounce and has just seen seventy-three files
    # appear, so a background re-index can hold the lease exactly now. What must hold is
    # that a partial answer *says why* -- degradation is announced, never silent. The
    # earlier form asserted the machine was quiet, which is not a property of this code.
    if ready_status.get("partial"):
        assert ready_status["index_status_error"] in {"database-busy", "unavailable"}
    if not sqlite_policy["wal_allowed"]:
        with closing(sqlite3.connect(
                storage.db_path_for(str(project)), timeout=1.0)) as blocker:
            blocker.execute("BEGIN EXCLUSIVE")
            started = time.perf_counter()
            busy_status = status_client.status(fresh=True)
            busy_status_ms = (time.perf_counter() - started) * 1000
            blocker.rollback()
        assert busy_status["partial"] is True
        assert busy_status["index_status_error"] == "database-busy"
        assert "service_load" in busy_status
        assert "background_recoveries" in busy_status
        assert busy_status_ms <= STATUS_DEADLINE_MS

    stop_reindex = threading.Event()
    abort_reindex = threading.Event()
    reindex_started = threading.Event()
    reindex_results: list[dict] = []
    reindex_errors: list[BaseException] = []

    def repeat_reindex() -> None:
        rebuild_client = client.CodesextantClient(
            project=str(project), port=port, timeout=30)
        try:
            while (not abort_reindex.is_set()
                   and (not stop_reindex.is_set() or len(reindex_results) < 2)):
                reindex_started.set()
                reindex_results.append(rebuild_client.reindex(force=True))
        except BaseException as exc:  # noqa: BLE001 - surfaced in the test thread
            reindex_errors.append(exc)

    rebuild = threading.Thread(target=repeat_reindex, name="real-reindex")
    rebuild.start()

    health_client = client.CodesextantClient(
        project=str(project), port=port, timeout=1.0)
    assert reindex_started.wait(timeout=5)

    active_seen = False
    health_probe_deadline = time.monotonic() + 10
    while time.monotonic() < health_probe_deadline:
        health = health_client.health()
        if any(
            job.get("label") == "/reindex"
            for job in health["heavy_work"].get("active_jobs", [])
        ):
            active_seen = True
            break
        time.sleep(0.01)
    assert active_seen, "the real rebuild never overlapped the HTTP workload"

    def validate_map(result: dict) -> None:
        assert result["symbols"]

    def validate_references(result: dict) -> None:
        assert result["engine"] == "jedi"
        assert result["definition"]["path"] == str(definition)

    def validate_impact(result: dict) -> None:
        assert result["symbol"] == "target"
        assert "summary" in result

    graph_clients = [
        client.CodesextantClient(project=str(project), port=port, timeout=15)
        for _ in range(3)
    ]
    graph_samples: dict[str, list[float]] = {}
    health_samples: list[float] = []
    status_samples: list[float] = []

    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                "map": pool.submit(
                    _timed_samples,
                    lambda: graph_clients[0].get_map(
                        budget=3000, focus_symbols=["target"]),
                    validate_map,
                    4,
                ),
                "references": pool.submit(
                    _timed_samples,
                    lambda: graph_clients[1].find_references(
                        "target",
                        def_path=str(definition),
                        src_root=str(project),
                        persist=True,
                    ),
                    validate_references,
                    4,
                ),
                "impact": pool.submit(
                    _timed_samples,
                    lambda: graph_clients[2].impact(
                        "target",
                        max_hops=2,
                        def_path=str(definition),
                        src_root=str(project),
                    ),
                    validate_impact,
                    4,
                ),
            }

            simultaneous_routes = {
                "/reindex", "/get_map", "/find_references", "/impact"}
            simultaneous_seen = False
            overlap_deadline = time.monotonic() + 5
            while time.monotonic() < overlap_deadline:
                health = health_client.health()
                active_routes = {
                    job.get("label")
                    for job in health["heavy_work"].get("active_jobs", [])
                }
                if simultaneous_routes <= active_routes:
                    simultaneous_seen = True
                    break
                time.sleep(0.01)
            assert simultaneous_seen, (
                "the reindex and three same-project interactive routes never "
                "ran concurrently")

            for _ in range(12):
                started = time.perf_counter()
                health = health_client.health()
                health_samples.append((time.perf_counter() - started) * 1000)
                assert health["service"] == "codesextant"
                assert "heavy_work" in health

                started = time.perf_counter()
                status = status_client.status(fresh=True)
                status_samples.append((time.perf_counter() - started) * 1000)
                assert "service_load" in status
                assert "background_recoveries" in status
                if status.get("partial"):
                    assert status["index_status_error"] in {
                        "database-busy", "unavailable"}
                else:
                    assert status["indexed"] is True

            for route, future in futures.items():
                graph_samples[route] = future.result(timeout=90)
    finally:
        stop_reindex.set()
        rebuild.join(timeout=70)
        if rebuild.is_alive():
            abort_reindex.set()
            rebuild.join(timeout=5)
        close_server()

    assert not rebuild.is_alive()
    # A reindex refused with documented back-pressure is the admission control working,
    # not a defect: batch work gets one of four slots while three interactive routes
    # hold the reserve, so a slow runner will reach the queue-full condition. What is
    # not allowed is a refusal without the contract -- a 500, or a 503 that omits the
    # Retry-After a caller is supposed to obey.
    for error in reindex_errors:
        assert isinstance(error, urllib.error.HTTPError), error
        assert error.code == 503, error
        assert error.headers.get("Retry-After"), "back-pressure must say when to return"
    assert len(reindex_results) >= 2
    assert all(result["indexed"] == 73 for result in reindex_results)
    assert storage.symbol_snapshot_path(
        storage.db_path_for(str(project))).is_file()
    assert len(health_samples) == 12
    assert len(status_samples) == 12

    raw_metrics = {
        **graph_samples,
        "health": health_samples,
        "status": status_samples,
    }
    reported_metrics = {
        route: {
            "samples": len(samples),
            "p95_ms": round(_percentile(samples, 95), 3),
            "p99_ms": round(_percentile(samples, 99), 3),
            "max_ms": round(max(samples), 3),
        }
        for route, samples in raw_metrics.items()
    }
    print(json.dumps(reported_metrics, sort_keys=True))

    for route in ("map", "references", "impact"):
        assert max(raw_metrics[route]) < INTERACTIVE_DEADLINE_MS
    assert (_percentile(raw_metrics["health"], 99)
            < HEALTH_P99_DEADLINE_MS)
    assert max(raw_metrics["status"]) <= STATUS_DEADLINE_MS
    assert not server_thread.is_alive()
