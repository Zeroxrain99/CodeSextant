"""HTTP regression for interactive graph latency during a same-project rebuild.

The claim is *relative*: a rebuild must not starve interactive queries. An absolute
millisecond bound cannot express that, and this test failed on a CI runner running at
half speed -- with a 504 from the admission deadline, which is the daemon behaving
correctly on a machine too slow to serve the request in time. So the same calls are timed
twice, once with no rebuild in flight and once with one held open, and the assertion is
about the ratio. The absolute bound is kept as a second assertion, applied only where the
uncontended baseline shows the machine could meet it.
"""

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

    def sweep(rounds: int) -> None:
        for _ in range(rounds):
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

    try:
        # Warm first and measure second. The very first requests pay for connection
        # setup and lazy imports, and folding that into the baseline would inflate it --
        # which loosens the ratio below, in the direction that hides a regression.
        sweep(2)
        samples.clear()

        # What these calls cost on this machine with nothing competing. Without it the
        # numbers below say how fast the runner is, not whether the rebuild starved
        # anything -- which is the only claim the code makes.
        sweep(5)
        baseline = list(samples)
        samples.clear()

        assert entered.wait(timeout=2)
        sweep(20)
    finally:
        release.set()
        rebuild.join(timeout=10)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

    assert not rebuild.is_alive()
    assert rebuild_errors == []
    assert len(baseline) == 15
    assert len(samples) == 60
    p95 = _percentile(samples, 95)
    p99 = _percentile(samples, 99)
    quiet_p99 = _percentile(baseline, 99)
    print(json.dumps({
        "samples": len(samples),
        "p95_ms": round(p95, 3),
        "p99_ms": round(p99, 3),
        "uncontended_p99_ms": round(quiet_p99, 3),
        "deadline_ms": 2000,
    }))

    # The claim, stated relatively: the rebuild holds one of two global slots and the
    # interactive reserve holds the other, so a query waits for at most one ahead of it.
    # A generous multiple of that still separates "queued behind one" from "starved".
    # The floor keeps the ratio meaningful when the baseline is close to zero.
    assert p99 < max(quiet_p99 * 8, 250), (
        f"interactive p99 was {p99:.0f} ms during a rebuild against {quiet_p99:.0f} ms "
        "with nothing competing, which is starvation rather than sharing")

    # And the absolute bound this test was written with, kept where it means something.
    # On a machine that cannot serve these in 190 ms while idle it is a statement about
    # the machine, and asserting it there is what made this test fail on correct code.
    if quiet_p99 < 1500 / 8:
        assert p99 < 1500
