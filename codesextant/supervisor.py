"""CodeSextant daemon watchdog used by the Windows startup task.

The supervisor is intentionally tiny: one process-wide lock, strict /health
checks, and the daemon's existing ``ensure_running`` as the only launch path.
This keeps daemon startup logic in one source of truth.
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

    /health is isolated from the heavy lane by design, so a wedged job keeps
    the daemon "healthy" forever while every heavy request piles up to 503.
    The supervisor is the only external actor able to break that state.
    Missing or malformed telemetry (older daemon) must read as not-stuck.
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
    # A CPU-heavy query can starve HTTP/TCP probes while the OS-backed lifetime
    # lock still proves that the authority process exists.  Do not compete with
    # ordinary clients for the startup lock or amplify a busy period with
    # duplicate spawn attempts.
    owner = daemon._instance_owner_result(port)
    if owner is not None:
        return owner
    return daemon.ensure_running(port=port, wait_sec=10.0)


def run(*, port: int | None = None, interval_sec: float | None = None,
        max_backoff_sec: float = 60.0) -> int:
    """Watch forever; a scheduled-task restart policy protects this process."""
    port = port or daemon._port()
    if interval_sec is None:
        try:
            interval_sec = float(os.environ.get(
                "CODESEXTANT_SUPERVISOR_INTERVAL_SEC", "5"))
        except ValueError:
            interval_sec = 5.0
    interval_sec = max(1.0, interval_sec)
    lg = _logger()

    try:
        supervisor_lock = daemon._InterprocessFileLock(
            daemon._daemon_lock_path(port, "supervisor"), timeout=0.0)
        supervisor_lock.acquire()
    except TimeoutError:
        lg.info("supervisor duplicate ignored port=%d", port)
        return 0

    failures = 0
    lg.info("supervisor started port=%d interval=%.1fs", port, interval_sec)
    try:
        while True:
            try:
                result = supervise_once(port=port)
                action = result.get("action")
                if action in ("healthy", "already-running", "spawned"):
                    if action == "spawned":
                        lg.warning("daemon recovered pid=%s port=%d",
                                   result.get("pid"), port)
                    failures = 0
                    delay = interval_sec
                else:
                    failures += 1
                    delay = min(max_backoff_sec,
                                interval_sec * (2 ** min(failures, 4)))
                    lg.error("daemon recovery failed action=%s retry=%.1fs",
                             action, delay)
            except Exception as exc:  # watchdog must survive one bad probe
                failures += 1
                delay = min(max_backoff_sec,
                            interval_sec * (2 ** min(failures, 4)))
                lg.exception("supervisor probe failed retry=%.1fs: %s", delay, exc)
            time.sleep(delay)
    except KeyboardInterrupt:
        lg.info("supervisor interrupted")
        return 0
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
