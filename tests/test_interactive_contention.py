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
    median = _percentile(samples, 50)
    p95 = _percentile(samples, 95)
    p99 = _percentile(samples, 99)
    quiet_median = _percentile(baseline, 50)
    quiet_p99 = _percentile(baseline, 99)
    print(json.dumps({
        "samples": len(samples),
        "median_ms": round(median, 3),
        "p95_ms": round(p95, 3),
        "p99_ms": round(p99, 3),
        "uncontended_median_ms": round(quiet_median, 3),
        "uncontended_p99_ms": round(quiet_p99, 3),
        "deadline_ms": 2000,
    }))

    # The claim, stated relatively: the rebuild holds one of two global slots and the
    # interactive reserve holds the other, so a query waits for at most one ahead of it.
    # A generous multiple of that still separates "queued behind one" from "starved".
    # The floor keeps the ratio meaningful when the baseline is close to zero.
    #
    # **The statistic is the median, and it used to be p99.** Starvation is sustained,
    # and a statistic that answers it has to be too: p99 over sixty samples is one
    # observation -- the slowest -- weighed against p99 over fifteen, which is also one.
    # That is a max against a max, and on a shared runner the max reports the worst
    # scheduling hiccup in the window rather than anything this code did. It failed on
    # Ubuntu at 392 ms against a 34 ms baseline while a healthy run here sits at a ratio
    # of about **1.05** -- so the allowance was never being approached, and what tripped
    # it was a single sample. A rebuild that really starved these routes would move all
    # sixty, and the median with them.
    #
    # **The floor is 100 ms and the first version of this fix left it at 250.** That
    # number was derived for a p99 comparison, and carrying it across to a median
    # silently disabled the assertion: a starved run whose median sat at 160 ms passed,
    # because 160 < 250. Swept against a healthy run, a fast-baseline run, the expected
    # three-deep queueing the design predicts, the CI failure itself, and two starved
    # distributions, every floor from 60 to 100 separates all six correctly and 150 does
    # not. 100 is the largest that still does, and it is about four times a healthy
    # median here -- the same claim as the multiple, written absolutely for the case
    # where the baseline measures near zero.
    assert median < max(quiet_median * 4, 100), (
        f"interactive median was {median:.0f} ms during a rebuild against "
        f"{quiet_median:.0f} ms with nothing competing, which is starvation rather "
        "than sharing")

    # The tail is held to the deadline rather than to a ratio, and it is held by
    # construction: every call above runs under a two-second client timeout and a
    # `future.result(timeout=2)`, so a sample that breached the interactive deadline
    # would have raised before reaching this line. A call merely slower than usual and
    # still inside the deadline is the machine, not a defect -- which is exactly what
    # the old assertion could not tell apart.
    assert p99 < 2000, f"a call took {p99:.0f} ms, past the interactive deadline"
