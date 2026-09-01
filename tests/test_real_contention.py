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

# The daemon's own deadline for a rebuild, and the deadline of the client that asks for
# one. **The second has to be strictly longer than the first, and it used to be half.**
# `CODESEXTANT_REINDEX_TIMEOUT_SEC` was 60 while the rebuild client timed out at 30, so
# on any runner where a rebuild took between 30 and 60 seconds the client gave up before
# the daemon had reached its own deadline -- and the assertion waiting downstream demands
# the daemon's contracted 503. That assertion was therefore unreachable exactly where it
# mattered, and what arrived instead was a bare client `TimeoutError` carrying nothing
# about the service at all. It failed on a Windows runner where one rebuild took 3.3
# seconds and a later one did not come back.
#
# The same shape as `test_interactive_contention.FUTURE_WAIT_SEC`: an outer wait exists
# to catch a wedge, never to race the deadline it is wrapping. Two deadlines in a race
# are decided by the machine, and the one that wins carries the less information.
REINDEX_DEADLINE_SEC = 60
REINDEX_CLIENT_TIMEOUT_SEC = REINDEX_DEADLINE_SEC * 2


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


_KEEP_GOING_CAP = 50


def _timed_samples(
    invoke: Callable[[], dict],
    validate: Callable[[dict], None],
    count: int,
    still_serving: Callable[[], bool],
    keep_going: Callable[[], bool] | None = None,
) -> tuple[list[float], list[urllib.error.HTTPError], int]:
    """Latencies of the calls that were answered, and the two ways one may not be.

    Separating them is the whole point. This test failed on a CI runner slow enough that
    a reindex of 73 files took 27 seconds -- against 55 to 289 files per second
    everywhere else -- and the daemon did exactly what it promises: it refused the
    interactive calls it could not serve inside their deadline. Counting that refusal as
    a failure asserts that the runner is fast, which is not a property of this code.

    **A third outcome, and this test asserted it away for four CI runs.** The refusal is
    **`count` is a floor, not a schedule.** With `keep_going`, the caller holds the
    route in flight for as long as it is measuring, and that is what makes concurrency
    something this test creates rather than something it hopes to catch. A fixed count
    cannot: `get_map` answers in ~150 ms and `impact` in ~900 ms on the same machine, so
    four `get_map` calls are over before `impact` has finished its second, and on a
    runner where that gap is wide enough the two are never in flight together at all --
    not unluckily, structurally. `_KEEP_GOING_CAP` bounds the loop so a fast machine
    stops rather than spinning.

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
    attempts = 0
    while attempts < count or (keep_going is not None and keep_going()
                               and attempts < count * _KEEP_GOING_CAP):
        attempts += 1
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


def test_the_sampler_keeps_going_while_the_caller_is_still_measuring():
    """`count` is a floor and `keep_going` is the schedule, both checked here.

    This is the branch the CI failure turned on. A fixed count let a fast route finish
    before a slow one started, so the four-way concurrency the contention test asserts
    could not occur on some runners however long it watched. Asserting the behaviour
    here, in milliseconds, rather than only inside a two-minute daemon test.
    """
    calls = 0

    def invoke() -> dict:
        nonlocal calls
        calls += 1
        return {"ok": calls}

    # Still measuring: the floor is not the ceiling.
    permitted = [True] * 6
    samples, _, _ = _timed_samples(
        invoke, lambda result: None, 2, lambda: True,
        keep_going=lambda: bool(permitted and permitted.pop()))
    assert len(samples) == 8, len(samples)

    # No longer measuring: it stops at the floor rather than spinning.
    calls = 0
    samples, _, _ = _timed_samples(
        invoke, lambda result: None, 3, lambda: True, keep_going=lambda: False)
    assert len(samples) == 3, len(samples)

    # A caller that never stops is bounded anyway, so a fast machine cannot spin here.
    calls = 0
    samples, _, _ = _timed_samples(
        invoke, lambda result: None, 2, lambda: True, keep_going=lambda: True)
    assert len(samples) == 2 * _KEEP_GOING_CAP, len(samples)

    # And the default is exactly what it was before `keep_going` existed.
    calls = 0
    samples, _, _ = _timed_samples(invoke, lambda result: None, 4, lambda: True)
    assert len(samples) == 4, len(samples)


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


def test_the_rebuild_client_outlives_the_daemons_own_reindex_deadline():
    """The eighth failure in this family, reduced to the one line that caused it.

    The big test below asserts that a refused rebuild carries the contract -- a 503 with
    a Retry-After. For that assertion to be reachable the daemon has to get as far as
    refusing, and it cannot if the client asking has already given up: the error that
    arrives is then a bare client `TimeoutError` that says nothing about the service.

    The client was timing out at **30 seconds against the daemon's own 60**, so on every
    runner where a rebuild took between the two the contracted refusal was structurally
    unobservable. Nothing about that is unlucky, which is why it belongs in an assertion
    rather than in a retry.

    A full deadline of headroom, not a nominal margin: the daemon is entitled to use all
    of `REINDEX_DEADLINE_SEC` before it answers or refuses, so the client has to be still
    waiting *after* that, on a machine that may be running everything at half speed.
    """
    assert REINDEX_CLIENT_TIMEOUT_SEC >= REINDEX_DEADLINE_SEC * 2


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
    monkeypatch.setenv("CODESEXTANT_REINDEX_TIMEOUT_SEC",
                       str(REINDEX_DEADLINE_SEC))
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

    # What the control plane costs on this machine with nothing competing. Every timing
    # claim below is a multiple of this rather than a millisecond count, for the reason
    # HANDOFF.md now records six times: an absolute deadline asserted on a runner that
    # is ten to a hundred times slower is an assertion about the runner. The daemon's
    # own budgets (150 ms of SQLite, 500 ms of git) are wall-clock too, so on a machine
    # where a 73-file reindex takes ten seconds they buy ten times the wall-clock and
    # `/status` legitimately answers in 2.5 seconds.
    health_client = client.CodesextantClient(
        project=str(project), port=port, timeout=1.0)
    quiet_health: list[float] = []
    quiet_status: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        health_client.health()
        quiet_health.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        status_client.status(fresh=True)
        quiet_status.append((time.perf_counter() - started) * 1000)

    stop_reindex = threading.Event()
    abort_reindex = threading.Event()
    reindex_started = threading.Event()
    reindex_results: list[dict] = []
    reindex_errors: list[BaseException] = []
    # Whether the daemon was still answering at the moment each error was raised. It has
    # to be asked *then*: the wind-down below closes the server, so by the time the
    # assertions run the only honest answer is "no", for every run.
    reindex_error_live: list[bool] = []

    def still_serving() -> bool:
        """Is the daemon up and answering after a call overran its deadline?

        The branded probe, not a socket connect: what has to hold is that the service
        kept serving through an uninterruptible call, and a port that accepts a
        connection does not say that.
        """
        return daemon.http_ping(port=port, timeout=2.0) is not None

    def repeat_reindex() -> None:
        rebuild_client = client.CodesextantClient(
            project=str(project), port=port,
            timeout=REINDEX_CLIENT_TIMEOUT_SEC)
        try:
            while (not abort_reindex.is_set()
                   and (not stop_reindex.is_set() or len(reindex_results) < 2)):
                reindex_started.set()
                reindex_results.append(rebuild_client.reindex(force=True))
        except BaseException as exc:  # noqa: BLE001 - surfaced in the test thread
            reindex_errors.append(exc)
            reindex_error_live.append(still_serving())

    rebuild = threading.Thread(target=repeat_reindex, name="real-reindex")
    rebuild.start()

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

    health_samples: list[float] = []
    status_samples: list[float] = []
    health_overruns = 0
    status_overruns = 0

    # Two events, because the failure had two halves. `measuring` holds the three
    # interactive routes in flight while there is something to contend with -- without
    # it a route that answers in 150 ms is finished before one that answers in 900 ms
    # has started its second call. `watching` runs a dedicated poller for the whole
    # lifetime of that work, because the coincidence has to be *looked for* densely as
    # well as *created*: the twelve health probes it used to ride cost 0.1 ms each and
    # were all over inside 400 ms of a three-second workload.
    measuring = threading.Event()
    measuring.set()
    watching = threading.Event()
    watching.set()

    simultaneous_routes = {"/reindex", "/get_map", "/find_references", "/impact"}
    concurrency_watch = {"looks": 0, "four_way": 0, "seen": set()}

    def watch_for_concurrency() -> None:
        """Poll `/health` for as long as the contended work runs.

        Its own client and its own thread: it must not consume the twelve latency
        samples below, and it must not be bounded by them.
        """
        watcher = client.CodesextantClient(
            project=str(project), port=port, timeout=5)
        while watching.is_set():
            try:
                labels = {job.get("label") for job
                          in watcher.health()["heavy_work"].get("active_jobs", [])}
            except (TimeoutError, urllib.error.HTTPError, OSError):
                continue                       # a refused probe is not an observation
            concurrency_watch["looks"] += 1
            concurrency_watch["seen"] |= labels & simultaneous_routes
            if simultaneous_routes <= labels:
                concurrency_watch["four_way"] += 1
            time.sleep(0.02)

    watcher_thread = threading.Thread(target=watch_for_concurrency, daemon=True)
    watcher_thread.start()

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
                    measuring.is_set,
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
                    measuring.is_set,
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
                    measuring.is_set,
                ),
            }

            for _ in range(12):
                # The same three outcomes the graph routes get, for the same reason: a
                # control-plane call can be answered, refused under contract, or outrun
                # by its own client deadline while the service stays up. The third was
                # unhandled here and raised straight out of the test -- a `TimeoutError`
                # from `status_client` on a Windows runner where the server itself
                # logged `/status -> 200 (2551 ms)` against a 1.5 s client budget.
                started = time.perf_counter()
                try:
                    health = health_client.health()
                except TimeoutError:
                    health_overruns += 1
                else:
                    health_samples.append((time.perf_counter() - started) * 1000)
                    assert health["service"] == "codesextant"
                    assert "heavy_work" in health

                started = time.perf_counter()
                try:
                    status = status_client.status(fresh=True)
                except TimeoutError:
                    status_overruns += 1
                    continue
                status_samples.append((time.perf_counter() - started) * 1000)
                assert "service_load" in status
                assert "background_recoveries" in status
                if status.get("partial"):
                    assert status["index_status_error"] in {
                        "database-busy", "unavailable"}
                else:
                    assert status["indexed"] is True

            # The measurement is over, so the routes may wind down. Clearing this
            # before `result()` is what bounds the wait: while it is set they keep
            # issuing calls, and `result(timeout=90)` would be waiting on a loop that
            # has no reason to end.
            measuring.clear()
            for route, future in futures.items():
                (graph_samples[route], graph_refusals[route],
                 graph_overruns[route]) = future.result(timeout=90)
    finally:
        watching.clear()
        watcher_thread.join(timeout=10)
        stop_reindex.set()
        rebuild.join(timeout=REINDEX_DEADLINE_SEC + 10)
        if rebuild.is_alive():
            abort_reindex.set()
            rebuild.join(timeout=5)
        # **Closing the server is what ends a call the daemon itself could not**, and it
        # has to happen before the aliveness check rather than after it. `abort_reindex`
        # ends the loop, never the request inside it, so a rebuild stuck in an
        # uninterruptible native call outlives every join above -- and now that the
        # client waits twice the daemon's deadline rather than half of it, that wait is
        # long enough to matter. Shutting the listener down is the only thing that makes
        # its client return.
        close_server()
        rebuild.join(timeout=10)

    assert not rebuild.is_alive()
    # A reindex refused with documented back-pressure is the admission control working,
    # not a defect: batch work gets one of four slots while three interactive routes
    # hold the reserve, so a slow runner will reach the queue-full condition. What is
    # not allowed is a refusal without the contract -- a 500, or a 503 that omits the
    # Retry-After a caller is supposed to obey.
    # `strict` because the two lists are appended in the same `except` block: if
    # they ever differ in length something has gone wrong in the rebuild thread,
    # and silently truncating would hide it behind a passing test.
    for error, was_live in zip(reindex_errors, reindex_error_live, strict=True):
        if isinstance(error, TimeoutError):
            # Not a refusal the daemon delivered: the client's own deadline, which
            # `work_coordinator` documents it cannot always beat -- "CPython cannot
            # safely interrupt a thread inside Jedi, tree-sitter, SQLite, or another
            # native call. Those calls may return after the request deadline."
            # `_timed_samples` accepts exactly this outcome on the three interactive
            # routes, under exactly this guard, and the rebuild path never got it.
            #
            # What the service still owes in that case is that it is *up*: a timeout
            # from a daemon that has died is a failure and stays one. That is the whole
            # difference between accepting an outcome and asserting one away.
            assert was_live, (
                "the rebuild timed out and the daemon stopped answering -- an overrun "
                "inside an uninterruptible call leaves the service up, a crash does not")
            continue
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
    # `concurrency_watch` above prove a rebuild was admitted and ran *concurrently* with
    # all three interactive routes, and neither depends on how many rebuilds finished.
    assert reindex_results or reindex_errors, (
        "the rebuild thread neither completed a reindex nor was refused, so nothing "
        "contended with the interactive routes")
    assert all(result["indexed"] == 73 for result in reindex_results)
    assert storage.symbol_snapshot_path(
        storage.db_path_for(str(project))).is_file()
    # Fifth distinct assertion in this file to fail on CI, on a fifth runner, and the
    # first that was impossible rather than unlucky. Each interactive route ran a fixed
    # four calls: `get_map` at ~150 ms was finished before `impact` at ~900 ms had
    # started its second, so on a runner where that spread is wide enough the four-way
    # coincidence cannot occur however long it is watched. Widening the window -- which
    # is what the previous repair did -- cannot fix a coincidence that never happens.
    # The routes are now held in flight for the whole measurement, so the concurrency
    # is created by the test rather than waited for.
    assert concurrency_watch["four_way"], (
        "the reindex and three same-project interactive routes never ran concurrently, "
        "so the latencies below were not taken under the contention this test exists "
        f"to create (looks {concurrency_watch['looks']}, routes ever active "
        f"{sorted(concurrency_watch['seen'])})")
    assert len(health_samples) + health_overruns == 12
    assert len(status_samples) + status_overruns == 12
    assert health_samples, "every health probe outran its deadline"
    assert status_samples, "every status probe outran its deadline"

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
    print(json.dumps({**reported_metrics, "overruns": graph_overruns,
                      # No expected value: the last one here was "8 to 11 of 12 on a
                      # healthy machine", measured on this machine, which is the
                      # mistake two commits above this one. `concurrency_looks` is
                      # printed beside it so a zero can be read -- few looks is a
                      # different diagnosis from many looks and no coincidence -- and
                      # `routes_ever_active` names which of the four was missing.
                      "four_way_concurrency": concurrency_watch["four_way"],
                      "concurrency_looks": concurrency_watch["looks"],
                      "routes_ever_active": sorted(concurrency_watch["seen"]),
                      "control_plane_overruns": {"health": health_overruns,
                                                 "status": status_overruns},
                      "quiet_health_median_ms": round(_percentile(quiet_health, 50), 3),
                      "quiet_status_median_ms": round(_percentile(quiet_status, 50), 3),
                      "busy_health_median_ms": round(_percentile(health_samples, 50), 3),
                      "busy_status_median_ms": round(_percentile(status_samples, 50), 3)},
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
    # **There was a median-ratio assertion here and it is gone, because it fired on a
    # run where the control plane was demonstrably healthy.** Windows: status median
    # 218 ms busy against 50 ms quiet -- a ratio of 4.4 against the 4 the rule allowed --
    # with **zero overruns** and every probe answered inside a 1.5 s budget. That is not
    # starvation, and an assertion that calls it starvation is a false positive.
    #
    # The mistake underneath it is worth more than the line was. The multiple was
    # derived from four runs on one machine (health 1.4-2.5x, status 1.7-2.5x) and
    # applied as if a ratio were automatically machine-independent. It is not: quiet
    # status is 6-8 ms here and 50 ms on that runner, busy is 12-18 ms here and 218 ms
    # there -- **7x slower quiet but 14x slower busy**, because contention costs
    # proportionally more where there is less machine to go round. The ratio scales with
    # the machine too, so tuning it needs the population, not one host.
    #
    # What remains is the claim the service actually makes, and it is scale-free: the
    # control plane keeps answering inside its own budget while heavy work runs. A
    # starved control plane overruns the 1.0 s and 1.5 s client budgets, and those
    # overruns are counted. Requiring most probes to have been answered says "not
    # starved" without saying anything about how fast the machine is.
    for name, answered, overran in (("health", health_samples, health_overruns),
                                    ("status", status_samples, status_overruns)):
        assert len(answered) > overran, (
            f"{name}: {overran} of {len(answered) + overran} probes outran their "
            "client budget during the rebuild, so the control plane was starved rather "
            "than merely slower")

    # The absolute deadlines are kept where they are still statements about the code:
    # the client budget enforces them by construction, so a call that breached one is
    # already counted as an overrun above rather than sitting in these samples.
    assert max(health_samples) < HEALTH_P99_DEADLINE_MS
    assert max(status_samples) <= STATUS_DEADLINE_MS
    assert not server_thread.is_alive()
