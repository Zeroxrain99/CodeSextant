"""Process-wide admission control for CodeSextant's expensive work.

The daemon is intentionally a single authority process.  Running two cold
maps or indexes in parallel inside that one Python process only makes both
slower and can starve the control plane.  This module provides one FIFO lane
for expensive work plus single-flight coalescing for identical overlapping
requests.  It is dependency-light so ``/health`` can inspect queue state
without importing the parser/index engine.

Residual risks (documented deliberately, honesty over cover-up):

* Deadline stacking: the client's heavy deadline (default 900s via
  ``CODESEXTANT_HEAVY_TIMEOUT_SEC``; ``CODESEXTANT_MAP_TIMEOUT_SEC`` /
  ``CODESEXTANT_REINDEX_TIMEOUT_SEC`` override per action) covers FIFO
  queue wait plus one run for typical loads, but several stacked
  near-deadline jobs can exceed a queued client's deadline.  The client
  deliberately does NOT resend on timeout (no duplicate amplification);
  the caller retries later or raises the env deadline.
* Handler threads: stdlib ``ThreadingHTTPServer`` spawns one thread per
  connection.  This lane bounds the threads *blocked on heavy work*
  (queue cap + per-job follower cap); control endpoints answer
  immediately; total connection threads are not globally capped.
* Wedged jobs: an active job cannot be cancelled in-process (CPython
  has no safe thread kill).  Recovery is external: the supervisor
  recycles the daemon when ``/health`` reports
  ``heavy_work.active_for_sec`` beyond ``CODESEXTANT_HEAVY_STUCK_SEC``
  (default 1800s; 0 disables).
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any

# Admission decisions are invisible in the request log: a slow response looks
# identical whether it computed for 40s or waited 40s behind someone else.
# These lines are what an operator reads when asked "why was my query slow".
#
# ⚠ Must be a *child* of "codesextant.daemon".  A sibling logger has no handler
# of its own, so every line would be silently discarded: observability that
# exists in the source and nowhere in the log file.  Children propagate up to
# the daemon logger's RotatingFileHandler; the daemon's own ``propagate=False``
# only stops it from going further up to root.
_log = logging.getLogger("codesextant.daemon.admission")


class HeavyWorkQueueFull(RuntimeError):
    """Admission rejected before creating another blocked request thread."""


def _positive_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _clone_exception(exc: BaseException) -> BaseException:
    """Give each follower an independent exception without losing its contract."""
    try:
        try:
            # Built-in exceptions may keep contract fields in C-level slots.
            cloned = copy.copy(exc)
        except Exception:
            # Pure-Python exceptions can require constructor arguments that
            # Exception.args does not retain (for example _HttpError.code).
            cloned = BaseException.__new__(type(exc))
            BaseException.__init__(cloned, *exc.args)
        if cloned is exc:
            raise TypeError("exception copy returned the original object")
        cloned.__dict__.update(exc.__dict__.copy())
        cloned.__cause__ = exc.__cause__
        cloned.__context__ = exc.__context__
        cloned.__suppress_context__ = exc.__suppress_context__
        cloned.__traceback__ = None
        if hasattr(exc, "__notes__"):
            cloned.__notes__ = list(exc.__notes__)
        return cloned
    except Exception:  # pragma: no cover - defensive for exotic constructors
        return RuntimeError(f"{type(exc).__name__}: {exc}")


@dataclass
class _Job:
    key: Hashable
    label: str
    ticket: int
    created_at: float
    owner_thread_id: int
    started_at: float | None = None
    done: bool = False
    followers: int = 0
    result: Any = None
    error: BaseException | None = None


class HeavyWorkCoordinator:
    """Serialize unique heavy jobs and coalesce identical concurrent jobs."""

    def __init__(self, *, queue_capacity: int | None = None,
                 follower_capacity: int | None = None):
        self._condition = threading.Condition()
        self._queue: deque[_Job] = deque()
        self._inflight: dict[Hashable, _Job] = {}
        self._active: _Job | None = None
        self._next_ticket = 0
        self._queue_capacity = queue_capacity or _positive_env(
            "CODESEXTANT_HEAVY_QUEUE_CAP", 8)
        self._follower_capacity = follower_capacity or _positive_env(
            "CODESEXTANT_HEAVY_FOLLOWER_CAP", 8)

    def run(self, key: Hashable, work: Callable[[], Any], *, label: str) -> Any:
        """Run ``work`` in the process-wide FIFO heavy lane.

        Calls with the same key that overlap join the leader and receive its
        result or exception.  Completed results are not cached, so a later
        request always observes current repository state.
        """
        with self._condition:
            owner_thread_id = threading.get_ident()
            existing = self._inflight.get(key)
            if existing is not None:
                if existing.owner_thread_id == owner_thread_id:
                    raise RuntimeError(
                        "reentrant heavy work is not allowed for the owner thread")
                if existing.followers >= self._follower_capacity:
                    raise HeavyWorkQueueFull(
                        "heavy follower capacity reached; retry later")
                existing.followers += 1
                while not existing.done:
                    self._condition.wait()
                if existing.error is not None:
                    raise _clone_exception(existing.error)
                return existing.result

            if (self._active is not None and
                    self._active.owner_thread_id == owner_thread_id):
                raise RuntimeError(
                    "reentrant heavy work is not allowed for the owner thread")
            if len(self._queue) >= self._queue_capacity:
                raise HeavyWorkQueueFull(
                    "heavy queue capacity reached; retry later")

            self._next_ticket += 1
            job = _Job(
                key=key,
                label=label,
                ticket=self._next_ticket,
                created_at=time.monotonic(),
                owner_thread_id=owner_thread_id,
            )
            self._inflight[key] = job
            self._queue.append(job)
            while self._active is not None or self._queue[0] is not job:
                self._condition.wait()
            self._queue.popleft()
            self._active = job
            job.started_at = time.monotonic()

        try:
            result = work()
        except BaseException as exc:
            self._finish(job, error=exc)
            raise
        else:
            self._finish(job, result=result)
            return result

    def _finish(self, job: _Job, *, result: Any = None,
                error: BaseException | None = None) -> None:
        with self._condition:
            job.result = result
            job.error = error
            job.done = True
            if self._active is job:
                self._active = None
            if self._inflight.get(job.key) is job:
                del self._inflight[job.key]
            self._condition.notify_all()

    def snapshot(self) -> dict:
        """Return path-free queue telemetry safe for the liveness endpoint."""
        with self._condition:
            active = self._active
            now = time.monotonic()
            return {
                "active": active.label if active is not None else None,
                "queued": len(self._queue),
                "followers": sum(job.followers for job in self._inflight.values()),
                "active_for_sec": (
                    round(now - active.started_at, 3)
                    if active is not None and active.started_at is not None
                    else 0.0
                ),
                "oldest_queued_for_sec": (
                    round(now - self._queue[0].created_at, 3)
                    if self._queue else 0.0
                ),
                "queue_capacity": self._queue_capacity,
                "follower_capacity": self._follower_capacity,
            }


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


class ShardedHeavyWork:
    """Per-project FIFO lanes behind one bounded global concurrency budget.

    One global lane made any repository's expensive job block every other
    repository's cheap one.  Measured in production on 2026-07-18: a query
    against a 23-file *unindexed* project returned ``count=0 symbols=0`` after
    152 seconds because it queued behind another project's ``/find_unwired``.
    That is a queueing failure, not a shortage of compute.

    Sharding alone would be the wrong cure.  Measured on this machine, four
    CPU-bound Python threads complete a fixed workload at **0.64x** the speed of
    running them sequentially. Under the GIL, extra runnable threads make
    everything slower and starve the control plane (a 135s reindex once pushed
    ``/health`` to 23.6s).  So lanes are split for *fairness*, while a small
    global slot count preserves the contention protection the single lane was
    introduced for.

    Switches (per L0 rule 6):
      CODESEXTANT_HEAVY_SHARDING=0     → every request shares one lane (old behaviour)
      CODESEXTANT_HEAVY_GLOBAL_CAP     → concurrent heavy jobs machine-wide (default 2)
      CODESEXTANT_HEAVY_QUEUE_CAP      → queued jobs *per shard* (default 8)
      CODESEXTANT_HEAVY_FOLLOWER_CAP   → coalesced followers per job (default 8)

    Known limit (documented, not hidden): a job that itself calls back into a
    *different* shard would hold one global slot while waiting for another.  No
    current endpoint handler does that; same-shard reentrancy still fails fast
    through the underlying coordinator's owner-thread guard.
    """

    def __init__(self, *, global_capacity: int | None = None,
                 shard_queue_capacity: int | None = None,
                 shard_follower_capacity: int | None = None):
        self._lock = threading.Lock()
        self._shards: dict[str, HeavyWorkCoordinator] = {}
        # ``is None`` rather than ``or``: an explicit 0 must clamp to 1, not
        # silently inherit whatever the environment happens to say.
        self._shard_queue_capacity = (
            None if shard_queue_capacity is None else max(1, shard_queue_capacity))
        self._shard_follower_capacity = (
            None if shard_follower_capacity is None
            else max(1, shard_follower_capacity))
        self._global_capacity = (
            _positive_env("CODESEXTANT_HEAVY_GLOBAL_CAP", 2)
            if global_capacity is None else max(1, global_capacity))
        self._global_slots = threading.BoundedSemaphore(self._global_capacity)
        self._in_use = 0
        self._waiting = 0
        self._throttled_total = 0
        # Only log completions slower than this, so the daemon log keeps
        # signal (the minute-long jobs) instead of one line per cheap query.
        self._slow_log_sec = float(
            _positive_env("CODESEXTANT_HEAVY_SLOW_LOG_SEC", 10))

    def _shard_name(self, shard: str | None) -> str:
        if not _env_flag("CODESEXTANT_HEAVY_SHARDING", True):
            return ""  # single shared lane == pre-sharding behaviour
        return shard or ""

    def _coordinator_for(self, shard: str) -> HeavyWorkCoordinator:
        with self._lock:
            coord = self._shards.get(shard)
            if coord is None:
                coord = HeavyWorkCoordinator(
                    queue_capacity=self._shard_queue_capacity,
                    follower_capacity=self._shard_follower_capacity)
                self._shards[shard] = coord
            return coord

    def run(self, key: Hashable, work: Callable[[], Any], *, label: str,
            shard: str | None = None) -> Any:
        shard_name = self._shard_name(shard)
        coord = self._coordinator_for(shard_name)

        def _globally_gated():
            # Count the wait *before* blocking so an operator tuning
            # CODESEXTANT_HEAVY_GLOBAL_CAP can see whether the cap actually
            # binds, instead of guessing from end-to-end latency.
            acquired = self._global_slots.acquire(blocking=False)
            if not acquired:
                with self._lock:
                    self._waiting += 1
                    self._throttled_total += 1
                waited_from = time.monotonic()
                try:
                    self._global_slots.acquire()
                finally:
                    with self._lock:
                        self._waiting -= 1
                _log.info(
                    "global cap throttled %s (shard %s) %.1fs; cap=%d, raise it via "
                    "CODESEXTANT_HEAVY_GLOBAL_CAP",
                    label, shard_name or "(no project)",
                    time.monotonic() - waited_from, self._global_capacity)
            with self._lock:
                self._in_use += 1
            started = time.monotonic()
            try:
                return work()
            finally:
                elapsed = time.monotonic() - started
                with self._lock:
                    self._in_use -= 1
                self._global_slots.release()
                if elapsed >= self._slow_log_sec:
                    _log.info("heavy job completed %s (shard %s) took %.1fs",
                              label, shard_name or "(no project)", elapsed)

        return coord.run(key, _globally_gated, label=label)

    def snapshot(self) -> dict:
        """Aggregate telemetry; keeps the keys ``supervisor`` already watches.

        ``active`` / ``active_for_sec`` report the *longest-running* job across
        every shard so stuck-detection keeps seeing the worst offender.
        """
        with self._lock:
            shards = list(self._shards.items())
            in_use = self._in_use
            waiting = self._waiting
            throttled_total = self._throttled_total
        parts = [(name, coord.snapshot()) for name, coord in shards]

        worst_label, worst_age = None, 0.0
        queued = followers = 0
        oldest_queued = 0.0
        for _name, snap in parts:
            queued += snap["queued"]
            followers += snap["followers"]
            oldest_queued = max(oldest_queued, snap["oldest_queued_for_sec"])
            if snap["active"] is not None and snap["active_for_sec"] >= worst_age:
                worst_label, worst_age = snap["active"], snap["active_for_sec"]

        probe = HeavyWorkCoordinator(
            queue_capacity=self._shard_queue_capacity,
            follower_capacity=self._shard_follower_capacity).snapshot()
        return {
            "active": worst_label,
            "queued": queued,
            "followers": followers,
            "active_for_sec": worst_age if worst_label is not None else 0.0,
            "oldest_queued_for_sec": oldest_queued,
            "queue_capacity": probe["queue_capacity"],
            "follower_capacity": probe["follower_capacity"],
            "shards": len(parts),
            "global_capacity": self._global_capacity,
            "global_in_use": in_use,
            # Waiting purely on the global cap (not on their own shard's FIFO).
            # Persistently > 0 means the cap is the binding constraint.
            "global_waiting": waiting,
            "global_throttled_total": throttled_total,
            "sharding_enabled": _env_flag("CODESEXTANT_HEAVY_SHARDING", True),
        }


def make_work_key(action: str, project: str | None,
                  params: dict | None = None) -> tuple[str, str, str]:
    """Build a stable, process-local single-flight key.

    Project paths remain internal; queue telemetry exposes only ``action``.
    There is deliberately no completed-result cache, so no repository revision
    is needed to prevent stale reuse.
    """
    normalized_project = (
        os.path.normcase(os.path.abspath(project)) if project else ""
    )
    canonical_params = json.dumps(
        params or {}, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str,
    )
    return action, normalized_project, canonical_params


# One admission authority for the whole process.  ``HeavyWorkCoordinator`` is
# still the per-shard lane implementation, but it is deliberately not exposed as
# a second module-level singleton: a producer wired to that one would escape both
# the global concurrency cap and cross-producer single-flight.
SHARED_SHARDED = ShardedHeavyWork()
