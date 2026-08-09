"""One-shot CodeSextant daemon check used by the Windows startup task.

Clients recover the daemon on demand after transport failure. The startup task
uses this module once at login so it never turns liveness into a polling loop.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from . import daemon, storage
except ImportError:  # direct ``python supervisor.py run`` from Task Scheduler
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from codesextant import daemon, storage  # type: ignore


def _logger() -> logging.Logger:
    lg = logging.getLogger("codesextant.supervisor")
    if lg.handlers:
        return lg
    lg.setLevel(logging.INFO)
    lg.propagate = False
    path = storage.default_db_dir() / "supervisor.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] pid=%(process)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"))
    lg.addHandler(handler)
    return lg


def _heavy_stuck_threshold_sec() -> float:
    """Age after which one active heavy job counts as stuck (0 disables).

    Default 1800s = 2x the client's 900s heavy deadline, so a legitimate
    cold map that merely runs long is never recycled.  Tunable/switchable
    via ``CODESEXTANT_HEAVY_STUCK_SEC`` per the switch-first rule.
    """
    raw = os.environ.get("CODESEXTANT_HEAVY_STUCK_SEC", "1800")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 1800.0
    return max(0.0, value)


def _heavy_job_is_stuck(health: dict) -> bool:
    """True when /health telemetry proves an over-age active heavy job.

    /health is isolated from the heavy lane by design. Production HTTP engine
    calls are deadline-bound child processes, and background native work has an
    in-process one-shot hard timer. This one-shot supervisor check remains a
    manual and login-time recovery aid, not a polling authority. Missing or
    malformed telemetry from an older daemon must read as not-stuck.
    """
    threshold = _heavy_stuck_threshold_sec()
    if threshold <= 0:
        return False
    heavy = health.get("heavy_work")
    if not isinstance(heavy, dict) or heavy.get("active") is None:
        return False
    try:
        active_for = float(heavy.get("active_for_sec") or 0.0)
    except (TypeError, ValueError):
        return False
    return active_for >= threshold


def supervise_once(*, port: int | None = None) -> dict:
    """Return healthy, or restart through daemon.ensure_running."""
    port = port or daemon._port()
    health = daemon.http_ping(port=port, timeout=1.0)
    if health is not None:
        if _heavy_job_is_stuck(health):
            heavy = health.get("heavy_work") or {}
            _logger().error(
                "heavy job stuck: active=%s active_for_sec=%s queued=%s "
                "followers=%s (threshold=%.0fs) -> recycling daemon pid=%s",
                heavy.get("active"), heavy.get("active_for_sec"),
                heavy.get("queued"), heavy.get("followers"),
                _heavy_stuck_threshold_sec(), health.get("pid"))
            daemon.stop_running(port=port)
            result = daemon.ensure_running(port=port, wait_sec=10.0)
            result.setdefault("recovered_from", "heavy-stuck")
            return result
        return {"action": "healthy", "pid": health.get("pid"),
                "port": port, "health": health}
    # The OS-backed lifetime lock proves only that an authority process exists.
    # It does not prove API or authentication compatibility, so return the
    # explicit unverified state and never reuse or replace that owner here.
    owner = daemon._instance_owner_result(port)
    if owner is not None:
        return owner
    return daemon.ensure_running(port=port, wait_sec=10.0)


def run(*, port: int | None = None, interval_sec: float | None = None,
        max_backoff_sec: float = 60.0) -> int:
    """Perform one startup check and exit without polling."""
    port = port or daemon._port()
    lg = _logger()

    try:
        supervisor_lock = daemon._InterprocessFileLock(
            daemon._daemon_lock_path(port, "supervisor"), timeout=0.0)
        supervisor_lock.acquire()
    except TimeoutError:
        lg.info("supervisor duplicate ignored port=%d", port)
        return 0

    started = time.monotonic()
    try:
        result = supervise_once(port=port)
        action = result.get("action")
        elapsed = time.monotonic() - started
        if action in ("healthy", "already-running", "spawned"):
            lg.info("one-shot startup check complete action=%s port=%d elapsed=%.3fs",
                    action, port, elapsed)
            return 0
        lg.error("one-shot startup check failed action=%s port=%d elapsed=%.3fs",
                 action, port, elapsed)
        return 1
    except Exception as exc:
        lg.exception("one-shot startup check failed port=%d: %s", port, exc)
        return 1
    finally:
        supervisor_lock.release()


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "run"
    if cmd == "run":
        return run()
    if cmd == "once":
        result = supervise_once()
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 0 if result.get("action") in ("healthy", "already-running", "spawned") else 1
    print("usage: supervisor.py [run|once]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
