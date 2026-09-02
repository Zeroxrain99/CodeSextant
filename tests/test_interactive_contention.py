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
import urllib.error
from concurrent.futures import ThreadPoolExecutor

# The deadline under test: the client's own timeout, and the value
# `CODESEXTANT_INTERACTIVE_TIMEOUT_SEC` is set to. A call that breaches it must fail the
# test, and it does -- the client raises and `timed` lets it out.
INTERACTIVE_DEADLINE_SEC = 2

# **Strictly longer, and that is the whole point.** This wait exists only so a wedged
# worker cannot hang the suite; it is not the deadline and must never be the thing that
# fires first. Set to the same 2 seconds it raced the client's timeout on a loaded
# Windows runner and won -- producing a bare `concurrent.futures.TimeoutError` with no
# message, from a run whose server-side times were all under 900 ms. Two timeouts of
# equal length race, and the one that wins is the one carrying no information.
FUTURE_WAIT_SEC = INTERACTIVE_DEADLINE_SEC * 5

# Refusals the daemon is *supposed* to make when it cannot serve in time: 504 is the
# request deadline firing, 503 is the admission queue full. **This file's own docstring
# has said so since the last repair -- "a 504 from the admission deadline, which is the
# daemon behaving correctly on a machine too slow to serve the request in time" -- and
# the code then let that 504 raise out of the worker and fail the run.** It did, on a
# Windows runner whose served latencies climbed from 17 ms to 185, 723 and 530 before
# two calls were refused, on a commit that changed nothing but a Markdown file.
#
# `test_real_contention._CONTRACTED_REFUSALS` is the same constant for the same reason.
# The claim being made here does not need every call answered; it needs the answered
# ones to be no slower under a rebuild than without one.
_CONTRACTED_REFUSALS = (503, 504)


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
        project=str(project), port=server.server_port,
        timeout=INTERACTIVE_DEADLINE_SEC)
    rebuild_errors: list[BaseException] = []

    def run_rebuild() -> None:
        try:
            api.reindex()
        except BaseException as exc:
            rebuild_errors.append(exc)

    rebuild = threading.Thread(target=run_rebuild)
    rebuild.start()

    samples: list[float] = []
    refused: list[int] = []

    def timed(call, expected: str) -> None:
        started = time.perf_counter()
        try:
            result = call()
        except urllib.error.HTTPError as exc:
            if exc.code not in _CONTRACTED_REFUSALS:
                raise
            # Not a latency sample and not a failure: the daemon declining work it
            # could not finish inside the deadline. Counted, so a run that refused
            # everything cannot pass by having measured nothing.
            refused.append(exc.code)
            return
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
                    try:
                        future.result(timeout=FUTURE_WAIT_SEC)
                    except TimeoutError as exc:      # pragma: no cover - a wedge
                        # Not the deadline firing: the client's own timeout is shorter
                        # and would have raised inside the worker with a real message.
                        # Reaching here means the call never came back at all.
                        raise AssertionError(
                            f"an interactive call did not return within "
                            f"{FUTURE_WAIT_SEC}s -- "
                            f"{FUTURE_WAIT_SEC - INTERACTIVE_DEADLINE_SEC}s past the "
                            f"{INTERACTIVE_DEADLINE_SEC}s client deadline that should "
                            "have raised inside the worker first. The worker is "
                            "wedged, not slow."
                        ) from exc

    try:
        # Warm first and measure second. The very first requests pay for connection
        # setup and lazy imports, and folding that into the baseline would inflate it --
        # which loosens the ratio below, in the direction that hides a regression.
        sweep(2)
        samples.clear()
        refused.clear()

        # What these calls cost on this machine with nothing competing. Without it the
        # numbers below say how fast the runner is, not whether the rebuild starved
        # anything -- which is the only claim the code makes.
        sweep(5)
        baseline = list(samples)
        quiet_refusals = len(refused)
        samples.clear()
        refused.clear()

        assert entered.wait(timeout=2)
        sweep(20)
    finally:
        release.set()
        rebuild.join(timeout=10)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)

    busy_refusals = len(refused)

    assert not rebuild.is_alive()
    assert rebuild_errors == []
    # Every call is accounted for as either a sample or a refusal, so nothing is lost
    # silently -- which is the failure mode a bare floor would have.
    assert len(baseline) + quiet_refusals == 15
    assert len(samples) + busy_refusals == 60

    # **The uncontended phase says whether this machine can serve these routes at all.**
    # If it cannot, every number below describes the runner and not this code, and the
    # honest outcome is to say that rather than to compare two noise distributions.
    assert len(baseline) >= 8, (
        f"{quiet_refusals} of 15 interactive calls were refused with nothing competing, "
        "so this runner cannot serve them even uncontended and the comparison below "
        "would be measuring the machine")

    # And the relative claim, in the same shape as the latency one below: a rebuild may
    # cost some refusals on a loaded runner, but not several times what the same routes
    # cost with nothing competing. **Unlike the 100 ms floor below, the 0.5 here was not
    # swept against starved and healthy distributions** -- it is set where refusing half
    # the calls is starvation on any reading, and it is the looser of the two guards.
    quiet_rate = quiet_refusals / 15
    busy_rate = busy_refusals / 60
    assert busy_rate <= max(quiet_rate * 4, 0.5), (
        f"{busy_refusals} of 60 interactive calls were refused during a rebuild "
        f"against {quiet_refusals} of 15 with nothing competing, which is the rebuild "
        "taking the routes rather than sharing them")
    assert len(samples) >= 30, (
        f"only {len(samples)} of 60 calls were answered during the rebuild, too few "
        "to say anything about the distribution below")
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
    # construction: every call above runs under the client's own
    # `INTERACTIVE_DEADLINE_SEC` timeout, so a sample that breached the interactive
    # deadline raised inside its worker -- with a message naming the route -- before
    # reaching this line. A call merely slower than usual and still inside the deadline
    # is the machine, not a defect, which is exactly what the old assertion could not
    # tell apart. `FUTURE_WAIT_SEC` is deliberately longer and catches only a wedge.
    assert p99 < 2000, f"a call took {p99:.0f} ms, past the interactive deadline"
