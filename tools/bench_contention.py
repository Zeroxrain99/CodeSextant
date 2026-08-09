"""Measure cross-project head-of-line blocking.

This reproducible benchmark checks whether heavy work for one project delays a
cheap query for another project. It remains in the repository so concurrency
changes can be compared with the same workload.

Recorded results from the original fix, on the same machine and workload:
    Global worker: 1,486 ms to 74,772 ms for the cheap query (50.3x slower)
    Per-project workers: 624 ms to 482 ms for the cheap query (no slowdown)

Usage:
    python tools/bench_contention.py --busy <large-project> --idle <small-project>
    python tools/bench_contention.py --busy ... --idle ... --json out.json

The benchmark sends a real heavy query to the daemon and can run for several
minutes. Run it only when no one else is waiting for that daemon.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.parse
import urllib.request

# This short timeout is only for the initial health check. A daemon that cannot
# answer it promptly is already too busy for a useful measurement.
_HEALTH_PROBE_TIMEOUT_SEC = 10.0


def _timed_get(base: str, path: str, params: dict, timeout: float) -> tuple[float, str]:
    """Return elapsed milliseconds and status without aborting the benchmark."""
    url = f"{base}{path}?" + urllib.parse.urlencode(params)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            resp.read()
        status = str(resp.status if hasattr(resp, "status") else 200)
    except Exception as exc:  # noqa: BLE001 - one failed request is a result
        status = type(exc).__name__
    return (time.perf_counter() - started) * 1000, status


def measure(base: str, busy_project: str, idle_project: str, *,
            busy_endpoint: str, idle_endpoint: str,
            timeout: float, settle_sec: float) -> dict:
    """Measure the idle project before and during work on another project."""
    solo_ms, solo_status = _timed_get(
        base, idle_endpoint, {"project": idle_project}, timeout)

    busy_result: dict = {}

    def _run_busy():
        ms, status = _timed_get(
            base, busy_endpoint, {"project": busy_project}, timeout)
        busy_result.update(ms=ms, status=status)

    busy_thread = threading.Thread(target=_run_busy)
    busy_thread.start()
    time.sleep(settle_sec)  # Give the heavy request time to occupy its worker.

    loaded_ms, loaded_status = _timed_get(
        base, idle_endpoint, {"project": idle_project}, timeout)
    busy_thread.join(timeout=timeout)

    return {
        "idle_solo_ms": round(solo_ms, 1),
        "idle_solo_status": solo_status,
        "idle_under_load_ms": round(loaded_ms, 1),
        "idle_under_load_status": loaded_status,
        "busy_ms": round(busy_result.get("ms", -1), 1),
        "busy_status": busy_result.get("status"),
        "inflation_x": round(loaded_ms / solo_ms, 2) if solo_ms else None,
        "busy_project": busy_project,
        "idle_project": idle_project,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--busy", required=True, help="absolute path of the busy project")
    p.add_argument("--idle", required=True, help="absolute path of the idle project")
    p.add_argument("--base", default="http://127.0.0.1:8790", help="daemon URL")
    p.add_argument("--busy-endpoint", default="/get_health")
    p.add_argument("--idle-endpoint", default="/comment_overview")
    # The 600-second default covers the slowest recorded cold query with room
    # to spare. Smaller projects can use a lower value.
    p.add_argument("--timeout", type=float, default=600.0,
                   help="timeout for each request, in seconds")
    p.add_argument("--settle", type=float, default=1.5,
                   help="delay before measuring the idle query, in seconds")
    p.add_argument("--json", dest="json_out", help="write the result to a JSON file")
    args = p.parse_args(argv)

    try:
        with urllib.request.urlopen(
                f"{args.base}/health", timeout=_HEALTH_PROBE_TIMEOUT_SEC) as r:
            health = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"Could not reach the daemon at {args.base}: {exc}", file=sys.stderr)
        return 2

    result = measure(
        args.base, args.busy, args.idle,
        busy_endpoint=args.busy_endpoint, idle_endpoint=args.idle_endpoint,
        timeout=args.timeout, settle_sec=args.settle)
    result["daemon_pid"] = health.get("pid")
    result["heavy_work"] = health.get("heavy_work")

    print(f"daemon pid={result['daemon_pid']}")
    print(f"Cheap query alone             : {result['idle_solo_ms']:9.0f} ms  "
          f"{result['idle_solo_status']}")
    print(f"Cheap query while project busy: {result['idle_under_load_ms']:9.0f} ms  "
          f"{result['idle_under_load_status']}")
    print(f"Heavy query                   : {result['busy_ms']:9.0f} ms  "
          f"{result['busy_status']}")
    print(f"Inflation: {result['inflation_x']}x "
          "(healthy per-project workers should stay near 1x)")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print(f"Wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
