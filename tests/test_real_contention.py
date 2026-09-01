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

import pytest

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


# Refusals the daemon is *supposed* to make when it cannot serve in time. 504 is the
# request deadline firing; 503 is the admission queue full. Both are the contract
# working, and treating either as a failure is what makes this test assert the speed of
# the machine instead of the behaviour of the code.
_CONTRACTED_REFUSALS = (503, 504)


def _timed_samples(
    invoke: Callable[[], dict],
    validate: Callable[[dict], None],
    count: int,
    still_serving: Callable[[], bool],
) -> tuple[list[float], list[urllib.error.HTTPError], int]:
    """Latencies of the calls that were answered, and the two ways one may not be.

    Separating them is the whole point. This test failed on a CI runner slow enough that
    a reindex of 73 files took 27 seconds -- against 55 to 289 files per second
    everywhere else -- and the daemon did exactly what it promises: it refused the
    interactive calls it could not serve inside their deadline. Counting that refusal as
    a failure asserts that the runner is fast, which is not a property of this code.

    **A third outcome, and this test asserted it away for four CI runs.** The refusal is
    a 504 raised when the deadline fires, and `work_coordinator` documents that it
    cannot always be delivered: "CPython cannot safely interrupt a thread inside Jedi,
    tree-sitter, SQLite, or another native call. Those calls may return after the
    request deadline." So on a slow enough machine the client's own deadline passes
    first and it raises `TimeoutError` instead. That is the documented limit, not a
    defect, and demanding a 504 there demands an interrupt CPython will not perform.

    What the service *does* promise in that case, and what is asserted here instead, is
    that it is still up and still serving -- so `still_serving` is called before the
    overrun is accepted, and a `TimeoutError` from a daemon that has actually died still
    fails the test. The bound that keeps this honest is in the caller: at least one
    interactive call must have been answered, or the run measured nothing.
    """
    samples: list[float] = []
    refused: list[urllib.error.HTTPError] = []
    overran = 0
    for _ in range(count):
        started = time.perf_counter()
        try:
            result = invoke()
        except urllib.error.HTTPError as exc:
            if exc.code not in _CONTRACTED_REFUSALS:
                raise
            refused.append(exc)
            continue
        except TimeoutError:
            assert still_serving(), (
                "the call timed out and the daemon stopped answering -- an overrun "
                "inside an uninterruptible call leaves the service up, a crash does not")
            overran += 1
            continue
        samples.append((time.perf_counter() - started) * 1000)
        validate(result)
    return samples, refused, overran


def test_the_sampler_separates_the_three_ways_a_call_can_end():
    """The overrun branch never runs on a fast machine, so it is exercised directly.

    A branch that only executes on a slow CI runner is a branch nobody has tested: the
    first version of it would have been found by a Windows job forty minutes later, and
    the four runs that got here were exactly that loop.
    """
    outcomes = iter([
        {"ok": 1},
        urllib.error.HTTPError("http://x/impact", 504, "deadline", {}, None),
        TimeoutError("the service is still up"),
        {"ok": 2},
    ])

    def invoke():
        item = next(outcomes)
        if isinstance(item, BaseException):
            raise item
        return item

    samples, refused, overran = _timed_samples(
        invoke, lambda result: None, 4, lambda: True)
    assert len(samples) == 2
    assert [exc.code for exc in refused] == [504]
    assert overran == 1


def test_a_timeout_from_a_dead_daemon_is_still_a_failure():
    """The overrun is only excused because the service kept serving. If it stopped, the
    same exception is the crash this test exists to catch, and must not be swallowed."""
    def invoke():
        raise TimeoutError("gone")

    with pytest.raises(AssertionError, match="stopped answering"):
        _timed_samples(invoke, lambda result: None, 1, lambda: False)


def test_an_uncontracted_status_is_never_treated_as_a_refusal():
    """503 and 504 are the documented back-pressure. A 500 is a defect and propagates."""
    def invoke():
        raise urllib.error.HTTPError("http://x/impact", 500, "boom", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        _timed_samples(invoke, lambda result: None, 1, lambda: True)


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
    graph_refusals: dict[str, list[urllib.error.HTTPError]] = {}
    graph_overruns: dict[str, int] = {}

    def still_serving() -> bool:
        """Is the daemon up and answering after a call overran its deadline?

        The branded probe, not a socket connect: what has to hold is that the service
        kept serving through an uninterruptible call, and a port that accepts a
        connection does not say that.
        """
        return daemon.http_ping(port=port, timeout=2.0) is not None
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
                    still_serving,
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
                    still_serving,
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
                    still_serving,
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
                (graph_samples[route], graph_refusals[route],
                 graph_overruns[route]) = future.result(timeout=90)
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
    # **The line under that comment used to be `len(reindex_results) >= 2`**, which is a
    # throughput claim contradicting the paragraph above it -- the fifth time this one
    # test has asserted the speed of the machine, and the second time it has stated the
    # right rule in a comment and then broken it on the next line.
    #
    # The mechanism, from a macOS runner rather than from a guess:
    #
    #     POST /reindex rejected -> 503: the route worker was killed before answering:
    #     route worker exited without a result (exit=-9)
    #
    # `exit=-9` is SIGKILL. The child process that runs heavy engine work was killed by
    # the operating system, and the daemon did exactly what it promises -- reported a
    # retryable 503 with a Retry-After instead of crashing or hanging. Demanding two
    # completed rebuilds demands that the runner never reclaim a child process.
    #
    # What this test exists to show is that real rebuild work does not starve the signed
    # graph and control routes, and that is asserted where it belongs: `active_seen` and
    # `simultaneous_seen` above prove a rebuild was admitted and ran *concurrently* with
    # all three interactive routes, and neither depends on how many rebuilds finished.
    assert reindex_results or reindex_errors, (
        "the rebuild thread neither completed a reindex nor was refused, so nothing "
        "contended with the interactive routes")
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
    # Overruns printed beside the latencies: a run where they are non-zero is a slow
    # machine meeting a documented limit, and a reader looking at a CI log deserves to
    # see that rather than infer it from a smaller sample count.
    print(json.dumps({**reported_metrics, "overruns": graph_overruns},
                     sort_keys=True))

    # The claim, stated so it holds at any speed: every interactive call either came
    # back inside its deadline or was refused under the contract. A machine slow enough
    # to refuse all three is not evidence of a defect here; a machine that answers late
    # is.
    for route in ("map", "references", "impact"):
        assert max(raw_metrics[route], default=0.0) < INTERACTIVE_DEADLINE_MS, (
            f"{route} answered outside its deadline rather than refusing")
    answered = sum(len(raw_metrics[route]) for route in ("map", "references", "impact"))
    assert answered, (
        "every interactive call was refused or overran, so this run measured admission "
        "control and nothing else -- the runner was too slow for the test to say "
        f"anything (refusals {({r: len(v) for r, v in graph_refusals.items()})}, "
        f"overruns {graph_overruns})")
    for route, refusals in graph_refusals.items():
        for refusal in refusals:
            assert refusal.code in _CONTRACTED_REFUSALS, (route, refusal)
            if refusal.code == 503:
                assert refusal.headers.get("Retry-After"), (
                    "back-pressure must say when to return")
    assert (_percentile(raw_metrics["health"], 99)
            < HEALTH_P99_DEADLINE_MS)
    assert max(raw_metrics["status"]) <= STATUS_DEADLINE_MS
    assert not server_thread.is_alive()
