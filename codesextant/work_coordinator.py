"""Process-wide admission control for CodeSextant's expensive work.

The daemon is intentionally a single authority process. Running too many cold
maps or indexes in parallel inside that one Python process only makes all of
them slower and can starve the control plane. This module provides per-project
priority-aware lanes, a priority-aware global capacity gate, and single-flight
coalescing for identical overlapping requests. It is dependency-light so
``/health`` can inspect queue state without importing the parser/index engine.

Known limits:

* Queue waits and coalesced followers honor their own deadlines. Indexing also
  checks cooperative cancellation between files. A follower can detach without
  cancelling a shared result that another subscriber still needs.
* CPython cannot safely interrupt a thread inside Jedi, tree-sitter, SQLite, or
  another native call. Those calls may return after the request deadline. A
  separate one-shot hard timer bounds a call that never returns, and indexing
  persists each file atomically so fail-fast recovery cannot accept a partial
  file as fresh.
* HTTP handler capacity and pre-authentication read time are bounded in the
  daemon. This module separately bounds heavy queues and same-key followers.
  The client never resends a timed-out heavy query while health still answers.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
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
# This must be a child of "codesextant.daemon". A sibling logger has no handler
# of its own, so every line would be silently discarded: observability that
# exists in the source and nowhere in the log file.  Children propagate up to
# the daemon logger's RotatingFileHandler; the daemon's own ``propagate=False``
# only stops it from going further up to root.
_log = logging.getLogger("codesextant.daemon.admission")


class HeavyWorkQueueFull(RuntimeError):
    """Admission rejected before creating another blocked request thread."""


class HeavyWorkDeadlineExceeded(TimeoutError):
    """A request deadline expired before or during heavy work."""


class CancellationToken:
    """Cooperative cancellation checked at safe engine boundaries."""

    def __init__(self, deadline: float | None = None):
        self._lock = threading.Lock()
        self._deadline = deadline
        self._cancelled = threading.Event()

    def extend_deadline(self, deadline: float | None) -> None:
        with self._lock:
            if self._deadline is None:
                return
            if deadline is None:
                self._deadline = None
            else:
                self._deadline = max(self._deadline, deadline)

    def cancel(self) -> None:
        self._cancelled.set()

    def remaining(self) -> float | None:
        """Return the current shared deadline budget in seconds."""
        with self._lock:
            deadline = self._deadline
        return _remaining(deadline)

    def deadline(self) -> float | None:
        """Return the current shared monotonic deadline."""
        with self._lock:
            return self._deadline

    def raise_if_cancelled(self) -> None:
        with self._lock:
            deadline = self._deadline
        if self._cancelled.is_set() or (
                deadline is not None and time.monotonic() >= deadline):
            raise HeavyWorkDeadlineExceeded("heavy work deadline exceeded")


_CURRENT = threading.local()


def cancellation_point() -> None:
    """Raise at a safe boundary when the current heavy request expired."""
    token = getattr(_CURRENT, "token", None)
    if token is not None:
        token.raise_if_cancelled()


def current_cancellation_token() -> CancellationToken | None:
    """Return the token for the heavy job running on this thread."""
    return getattr(_CURRENT, "token", None)


def _set_current_job_blocking_reason(reason: str) -> None:
    job = getattr(_CURRENT, "job", None)
    if job is not None:
        job.blocking_reason = reason


def _remaining(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


_PRIORITY_VALUE = {"background": 0, "batch": 1, "interactive": 2}


def _priority_value(priority: str) -> int:
    try:
        return _PRIORITY_VALUE[priority]
    except KeyError:
        raise ValueError(f"unknown heavy-work priority: {priority!r}") from None


def _positive_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _nonnegative_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _positive_float_env(name: str, default: float) -> float:
    try:
        return max(0.001, float(os.environ.get(name, str(default))))
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


_SAFE_LABEL = re.compile(
    r"(?:/[A-Za-z0-9_.-]+|[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?|"
    r"job:[a-f0-9]{12})\Z"
)
_SAFE_IDENTITY = re.compile(r"[A-Za-z0-9_.:@-]{1,80}\Z")


def _telemetry_label(label: str) -> str:
    """Keep operation labels useful without ever publishing a file path."""
    raw = str(label).strip()
    if len(raw) <= 80 and _SAFE_LABEL.fullmatch(raw):
        return raw
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"job:{digest}"


def _shard_digest(shard: str) -> str:
    return hashlib.sha256(shard.encode("utf-8", errors="replace")).hexdigest()[:16]


def _telemetry_identity(identity: str | None, fallback: str) -> str:
    if identity is None:
        return fallback
    raw = str(identity).strip()
    if _SAFE_IDENTITY.fullmatch(raw):
        return raw
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"request:{digest}"


@dataclass
class _Job:
    key: Hashable
    label: str
    ticket: int
    created_at: float
    owner_thread_id: int
    priority: str
    token: CancellationToken
    request_identity: str | None = None
    started_at: float | None = None
    blocking_reason: str = "project_lane_queue"
    done: bool = False
    followers: int = 0
    result: Any = None
    error: BaseException | None = None


class HeavyWorkCoordinator:
    """Run unique jobs with bounded concurrency, priority, and single-flight."""

    def __init__(self, *, queue_capacity: int | None = None,
                 follower_capacity: int | None = None,
                 interactive_reserve: int | None = None,
                 priority_aging_sec: float | None = None,
                 capacity: int = 1):
        self._condition = threading.Condition()
        self._queue: deque[_Job] = deque()
        self._inflight: dict[Hashable, _Job] = {}
        self._active: dict[Hashable, _Job] = {}
        self._capacity = max(1, int(capacity))
        self._next_ticket = 0
        self._queue_capacity = queue_capacity or _positive_env(
            "CODESEXTANT_HEAVY_QUEUE_CAP", 8)
        self._follower_capacity = follower_capacity or _positive_env(
            "CODESEXTANT_HEAVY_FOLLOWER_CAP", 8)
        self._interactive_reserve = (
            _positive_env("CODESEXTANT_INTERACTIVE_QUEUE_RESERVE", 2)
            if interactive_reserve is None else max(1, interactive_reserve))
        self._priority_aging_sec = (
            _positive_float_env("CODESEXTANT_PRIORITY_AGING_SEC", 30.0)
            if priority_aging_sec is None else max(0.001, priority_aging_sec))
        self._job_telemetry_limit = min(
            128, _positive_env("CODESEXTANT_JOB_TELEMETRY_LIMIT", 32))
        self._rejected_by_priority = {name: 0 for name in _PRIORITY_VALUE}

    def run(self, key: Hashable, work: Callable[[], Any], *, label: str,
            priority: str = "batch", deadline: float | None = None,
            request_identity: str | None = None) -> Any:
        """Run ``work`` in a bounded priority-aware heavy lane.

        Calls with the same key that overlap join the leader and receive its
        result or exception.  Completed results are not cached, so a later
        request always observes current repository state.
        """
        priority_value = _priority_value(priority)
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
                existing.token.extend_deadline(deadline)
                while not existing.done:
                    remaining = _remaining(deadline)
                    if remaining is not None and remaining <= 0:
                        existing.followers -= 1
                        self._condition.notify_all()
                        raise HeavyWorkDeadlineExceeded(
                            "heavy-work follower deadline exceeded")
                    self._condition.wait(timeout=remaining)
                if existing.error is not None:
                    raise _clone_exception(existing.error)
                return existing.result

            if any(
                    active.owner_thread_id == owner_thread_id
                    for active in self._active.values()):
                raise RuntimeError(
                    "reentrant heavy work is not allowed for the owner thread")
            queue_limit = self._queue_capacity + (
                self._interactive_reserve
                if priority_value == _PRIORITY_VALUE["interactive"] else 0)
            if len(self._queue) >= queue_limit:
                self._rejected_by_priority[priority] += 1
                raise HeavyWorkQueueFull(
                    f"{priority} heavy queue capacity reached; retry later")

            self._next_ticket += 1
            job = _Job(
                key=key,
                label=label,
                ticket=self._next_ticket,
                created_at=time.monotonic(),
                owner_thread_id=owner_thread_id,
                priority=priority,
                token=CancellationToken(deadline),
                request_identity=request_identity,
            )
            self._inflight[key] = job
            self._queue.append(job)
            owner_detached = False
            while (len(self._active) >= self._capacity
                   or self._next_job_locked() is not job):
                job.blocking_reason = (
                    "project_lane_active"
                    if len(self._active) >= self._capacity
                    else "priority_order"
                )
                remaining = _remaining(deadline)
                if remaining is not None and remaining <= 0:
                    if job.followers:
                        owner_detached = True
                        remaining = job.token.remaining()
                    else:
                        self._queue.remove(job)
                        self._inflight.pop(job.key, None)
                        job.done = True
                        job.error = HeavyWorkDeadlineExceeded(
                            "heavy-work queue deadline exceeded")
                        self._condition.notify_all()
                        raise job.error
                if owner_detached and remaining is not None and remaining <= 0:
                    self._queue.remove(job)
                    self._inflight.pop(job.key, None)
                    job.done = True
                    job.error = HeavyWorkDeadlineExceeded(
                        "all heavy-work subscribers expired in the queue")
                    self._condition.notify_all()
                    raise job.error
                self._condition.wait(timeout=remaining)
            remaining = _remaining(deadline)
            if remaining is not None and remaining <= 0:
                if job.followers:
                    owner_detached = True
                else:
                    self._queue.remove(job)
                    self._inflight.pop(job.key, None)
                    job.done = True
                    job.error = HeavyWorkDeadlineExceeded(
                        "heavy-work queue deadline exceeded")
                    self._condition.notify_all()
                    raise job.error
            self._queue.remove(job)
            self._active[job.key] = job
            job.started_at = time.monotonic()
            job.blocking_reason = "global_capacity"
            # A capacity-aware lane can dispatch another queued job immediately.
            self._condition.notify_all()

        previous_token = getattr(_CURRENT, "token", None)
        previous_job = getattr(_CURRENT, "job", None)
        _CURRENT.token = job.token
        _CURRENT.job = job
        try:
            job.token.raise_if_cancelled()
            result = work()
        except BaseException as exc:
            self._finish(job, error=exc)
            raise
        else:
            self._finish(job, result=result)
            if owner_detached or (
                    deadline is not None and time.monotonic() >= deadline):
                raise HeavyWorkDeadlineExceeded(
                    "heavy-work owner deadline exceeded; shared result was preserved")
            return result
        finally:
            if previous_token is None:
                try:
                    del _CURRENT.token
                except AttributeError:
                    pass
            else:
                _CURRENT.token = previous_token
            if previous_job is None:
                try:
                    del _CURRENT.job
                except AttributeError:
                    pass
            else:
                _CURRENT.job = previous_job

    def _finish(self, job: _Job, *, result: Any = None,
                error: BaseException | None = None) -> None:
        with self._condition:
            job.result = result
            job.error = error
            job.done = True
            if self._active.get(job.key) is job:
                del self._active[job.key]
            if self._inflight.get(job.key) is job:
                del self._inflight[job.key]
            self._condition.notify_all()

    def is_idle(self) -> bool:
        """Return whether this lane has no active, queued, or shared work."""
        with self._condition:
            return (
                not self._active
                and not self._queue
                and not self._inflight
            )

    def has_work(self, *, label: str | None = None) -> bool:
        """Return whether matching active or queued work exists in this lane."""
        with self._condition:
            return any(
                not job.done and (label is None or job.label == label)
                for job in self._inflight.values()
            )

    def snapshot(self) -> dict:
        """Return path-free queue telemetry safe for the liveness endpoint."""
        with self._condition:
            now = time.monotonic()
            active_jobs = list(self._active.values())
            active = max(
                active_jobs,
                key=lambda job: now - (job.started_at or now),
                default=None,
            )
            next_job = self._next_job_locked()

            def job_details(job: _Job, *, active_job: bool) -> dict:
                if active_job:
                    blocking_reason = job.blocking_reason
                elif len(self._active) >= self._capacity:
                    blocking_reason = "project_lane_active"
                elif job is next_job:
                    blocking_reason = "dispatch_pending"
                else:
                    blocking_reason = "priority_order"
                owner_identity = f"thread:{job.owner_thread_id}"
                return {
                    "label": _telemetry_label(job.label),
                    "priority": job.priority,
                    "age_sec": round(max(0.0, now - job.created_at), 3),
                    "owner_thread_id": job.owner_thread_id,
                    "owner_identity": owner_identity,
                    "request_identity": _telemetry_identity(
                        job.request_identity, owner_identity),
                    "blocking_reason": blocking_reason,
                }

            return {
                "active": (
                    _telemetry_label(active.label) if active is not None else None
                ),
                "active_count": len(active_jobs),
                "queued": len(self._queue),
                "queued_by_priority": {
                    name: sum(job.priority == name for job in self._queue)
                    for name in _PRIORITY_VALUE
                },
                "followers": sum(job.followers for job in self._inflight.values()),
                "active_for_sec": (
                    round(now - active.started_at, 3)
                    if active is not None and active.started_at is not None
                    else 0.0
                ),
                "oldest_queued_for_sec": (
                    round(now - min(job.created_at for job in self._queue), 3)
                    if self._queue else 0.0
                ),
                "queue_capacity": self._queue_capacity,
                "follower_capacity": self._follower_capacity,
                "capacity": self._capacity,
                "interactive_queue_reserve": self._interactive_reserve,
                "priority_aging_sec": self._priority_aging_sec,
                "rejected_by_priority": self._rejected_by_priority.copy(),
                "active_job": (
                    job_details(active, active_job=True)
                    if active is not None else None
                ),
                "active_jobs": [
                    job_details(job, active_job=True)
                    for job in sorted(
                        active_jobs,
                        key=lambda item: item.started_at or now,
                    )[:self._job_telemetry_limit]
                ],
                "queued_jobs": [
                    job_details(job, active_job=False)
                    for job in list(self._queue)[:self._job_telemetry_limit]
                ],
                "job_telemetry_limit": self._job_telemetry_limit,
            }

    def _next_job_locked(self) -> _Job | None:
        """Choose by priority, then age old work upward to prevent starvation."""
        if not self._queue:
            return None
        now = time.monotonic()

        def rank(job: _Job):
            waited = max(0.0, now - job.created_at)
            aged = min(
                _PRIORITY_VALUE["interactive"],
                _priority_value(job.priority) + int(waited / self._priority_aging_sec),
            )
            return aged, -job.ticket

        return max(self._queue, key=rank)


@dataclass
class _GateWaiter:
    priority: str
    ticket: int
    created_at: float


class _PriorityGate:
    """Bound global concurrency with strict interactive admission when possible."""

    def __init__(self, capacity: int, *, interactive_reserve: int,
                 priority_aging_sec: float):
        self._capacity = capacity
        self._interactive_reserve = min(
            max(0, interactive_reserve), max(0, capacity - 1))
        self._partitioned = capacity > 1 and self._interactive_reserve > 0
        self._noninteractive_capacity = (
            capacity - self._interactive_reserve
            if self._partitioned else capacity
        )
        self._interactive_capacity = (
            self._interactive_reserve if self._partitioned else capacity
        )
        self._priority_aging_sec = priority_aging_sec
        self._condition = threading.Condition()
        self._waiters: list[_GateWaiter] = []
        self._next_ticket = 0
        self._in_use = 0
        self._in_use_by_priority = {name: 0 for name in _PRIORITY_VALUE}
        self._throttled_total = 0

    def acquire(self, priority: str, *, deadline: float | None = None,
                token: CancellationToken | None = None) -> float:
        _priority_value(priority)
        with self._condition:
            self._next_ticket += 1
            waiter = _GateWaiter(priority, self._next_ticket, time.monotonic())
            self._waiters.append(waiter)
            if (not self._eligible_locked(waiter)
                    or self._next_waiter_locked() is not waiter):
                self._throttled_total += 1
            while (not self._eligible_locked(waiter)
                   or self._next_waiter_locked() is not waiter):
                remaining = token.remaining() if token is not None else _remaining(deadline)
                if remaining is not None and remaining <= 0:
                    self._waiters.remove(waiter)
                    self._condition.notify_all()
                    raise HeavyWorkDeadlineExceeded(
                        "global heavy-work deadline exceeded")
                self._condition.wait(timeout=remaining)
            remaining = token.remaining() if token is not None else _remaining(deadline)
            if remaining is not None and remaining <= 0:
                self._waiters.remove(waiter)
                self._condition.notify_all()
                raise HeavyWorkDeadlineExceeded(
                    "global heavy-work deadline exceeded")
            self._waiters.remove(waiter)
            self._in_use += 1
            self._in_use_by_priority[priority] += 1
            # Multiple slots may have become free before awakened waiters run.
            # Wake the next eligible waiter after claiming only this one.
            self._condition.notify_all()
            return time.monotonic() - waiter.created_at

    def release(self, priority: str) -> None:
        _priority_value(priority)
        with self._condition:
            if self._in_use <= 0 or self._in_use_by_priority[priority] <= 0:
                raise RuntimeError("global heavy-work gate released without ownership")
            self._in_use -= 1
            self._in_use_by_priority[priority] -= 1
            self._condition.notify_all()

    def _eligible_locked(self, waiter: _GateWaiter) -> bool:
        if not self._partitioned:
            return self._in_use < self._capacity
        if waiter.priority == "interactive":
            return (
                self._in_use_by_priority["interactive"]
                < self._interactive_capacity
            )
        noninteractive_in_use = (
            self._in_use_by_priority["background"]
            + self._in_use_by_priority["batch"]
        )
        return noninteractive_in_use < self._noninteractive_capacity

    def _next_waiter_locked(self) -> _GateWaiter | None:
        eligible = [
            waiter for waiter in self._waiters if self._eligible_locked(waiter)
        ]
        if not eligible:
            return None
        now = time.monotonic()

        def rank(waiter: _GateWaiter):
            waited = max(0.0, now - waiter.created_at)
            aged = min(
                _PRIORITY_VALUE["interactive"],
                _priority_value(waiter.priority)
                + int(waited / self._priority_aging_sec),
            )
            return aged, -waiter.ticket

        return max(eligible, key=rank)

    def snapshot(self) -> dict:
        with self._condition:
            return {
                "in_use": self._in_use,
                "waiting": len(self._waiters),
                "waiting_by_priority": {
                    name: sum(waiter.priority == name for waiter in self._waiters)
                    for name in _PRIORITY_VALUE
                },
                "in_use_by_priority": self._in_use_by_priority.copy(),
                "reserve": self._interactive_reserve,
                "partition_mode": "strict" if self._partitioned else "shared",
                "interactive_capacity": self._interactive_capacity,
                "noninteractive_capacity": self._noninteractive_capacity,
                "throttled_total": self._throttled_total,
            }


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _hard_timeout_env() -> float:
    try:
        return max(0.0, float(os.environ.get(
            "CODESEXTANT_HEAVY_STUCK_SEC", "1800")))
    except (TypeError, ValueError):
        return 1800.0


def fail_fast_stuck_job(label: str) -> None:
    """Terminate a daemon whose native heavy call ignored cooperative cancel."""
    _log.critical("heavy job hard timeout reached: %s; terminating daemon", label)
    logging.shutdown()
    os._exit(70)


@dataclass
class _LaneEntry:
    coordinator: HeavyWorkCoordinator
    leases: int = 0


class ShardedHeavyWork:
    """Per-project priority-aware lanes behind one bounded global budget.

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

    Environment switches:
      CODESEXTANT_HEAVY_SHARDING=0: every request shares one lane
      CODESEXTANT_HEAVY_GLOBAL_CAP: concurrent heavy jobs machine-wide (default 4)
      CODESEXTANT_INTERACTIVE_GLOBAL_RESERVE: interactive-only slots (default 3)
      CODESEXTANT_HEAVY_QUEUE_CAP: queued jobs per shard (default 8)
      CODESEXTANT_HEAVY_FOLLOWER_CAP: coalesced followers per job (default 8)
      CODESEXTANT_INTERACTIVE_QUEUE_RESERVE: extra agent query slots (default 2)
      CODESEXTANT_PRIORITY_AGING_SEC: seconds before queued work rises one level (default 30)

    Known limit: a job that itself calls back into a
    *different* lane or shard would hold one global slot while waiting for
    another. No current endpoint handler does that; same-lane reentrancy still
    fails fast through the underlying coordinator's owner-thread guard.
    """

    def __init__(self, *, global_capacity: int | None = None,
                 interactive_global_reserve: int | None = None,
                 shard_queue_capacity: int | None = None,
                 shard_follower_capacity: int | None = None,
                 hard_timeout_sec: float | None = None,
                 hard_timeout_callback=None,
                 timer_factory=threading.Timer):
        self._lock = threading.Lock()
        self._shards: dict[tuple[str, str], _LaneEntry] = {}
        # ``is None`` rather than ``or``: an explicit 0 must clamp to 1, not
        # silently inherit whatever the environment happens to say.
        self._shard_queue_capacity = (
            None if shard_queue_capacity is None else max(1, shard_queue_capacity))
        self._shard_follower_capacity = (
            None if shard_follower_capacity is None
            else max(1, shard_follower_capacity))
        self._global_capacity = (
            _positive_env("CODESEXTANT_HEAVY_GLOBAL_CAP", 4)
            if global_capacity is None else max(1, global_capacity))
        self._priority_aging_sec = _positive_float_env(
            "CODESEXTANT_PRIORITY_AGING_SEC", 30.0)
        requested_reserve = (
            _nonnegative_env("CODESEXTANT_INTERACTIVE_GLOBAL_RESERVE", 3)
            if interactive_global_reserve is None
            else max(0, interactive_global_reserve)
        )
        self._interactive_global_reserve = min(
            requested_reserve, max(0, self._global_capacity - 1))
        self._interactive_lane_capacity = (
            self._interactive_global_reserve
            if self._interactive_global_reserve > 0
            else self._global_capacity
        )
        self._global_gate = _PriorityGate(
            self._global_capacity,
            interactive_reserve=self._interactive_global_reserve,
            priority_aging_sec=self._priority_aging_sec,
        )
        self._hard_timeout_sec = (
            _hard_timeout_env() if hard_timeout_sec is None
            else max(0.0, float(hard_timeout_sec)))
        self._hard_timeout_callback = (
            hard_timeout_callback or fail_fast_stuck_job)
        self._timer_factory = timer_factory
        # Only log completions slower than this, so the daemon log keeps
        # signal (the minute-long jobs) instead of one line per cheap query.
        self._slow_log_sec = float(
            _positive_env("CODESEXTANT_HEAVY_SLOW_LOG_SEC", 10))
        self._job_telemetry_limit = min(
            128, _positive_env("CODESEXTANT_JOB_TELEMETRY_LIMIT", 32))

    def _shard_name(self, shard: str | None) -> str:
        if not _env_flag("CODESEXTANT_HEAVY_SHARDING", True):
            return ""  # single shared lane == pre-sharding behaviour
        return shard or ""

    def _lane_for(self, priority: str) -> str:
        if self._global_capacity == 1:
            return "shared"
        return "interactive" if priority == "interactive" else "batch"

    @property
    def hard_timeout_sec(self) -> float:
        """Process-level deadline used to bound an uninterruptible heavy call."""
        return self._hard_timeout_sec

    def _acquire_lane(self, shard: str, lane: str) -> tuple[
            tuple[str, str], _LaneEntry]:
        with self._lock:
            lane_key = (shard, lane)
            entry = self._shards.get(lane_key)
            if entry is None:
                entry = _LaneEntry(HeavyWorkCoordinator(
                    queue_capacity=self._shard_queue_capacity,
                    follower_capacity=self._shard_follower_capacity,
                    capacity=(
                        self._interactive_lane_capacity
                        if lane == "interactive" else 1
                    ),
                ))
                self._shards[lane_key] = entry
            entry.leases += 1
            return lane_key, entry

    def _release_lane(self, lane_key: tuple[str, str], entry: _LaneEntry) -> None:
        with self._lock:
            current = self._shards.get(lane_key)
            if current is not entry or entry.leases <= 0:
                raise RuntimeError("heavy-work lane lease accounting drifted")
            entry.leases -= 1
            if entry.leases == 0 and entry.coordinator.is_idle():
                del self._shards[lane_key]

    def has_work(self, *, shard: str | None = None,
                 label: str | None = None) -> bool:
        """Return whether one project currently owns or queues matching work."""
        shard_name = self._shard_name(shard)
        with self._lock:
            coordinators = [
                entry.coordinator
                for (candidate, _lane), entry in self._shards.items()
                if candidate == shard_name
            ]
        return any(
            coordinator.has_work(label=label)
            for coordinator in coordinators
        )

    def run(self, key: Hashable, work: Callable[[], Any], *, label: str,
            shard: str | None = None, priority: str = "batch",
            deadline: float | None = None,
            request_identity: str | None = None) -> Any:
        _priority_value(priority)
        shard_name = self._shard_name(shard)
        lane = self._lane_for(priority)
        lane_key, entry = self._acquire_lane(shard_name, lane)

        def _globally_gated():
            # Count the wait *before* blocking so an operator tuning
            # CODESEXTANT_HEAVY_GLOBAL_CAP can see whether the cap actually
            # binds, instead of guessing from end-to-end latency.
            _set_current_job_blocking_reason("global_capacity")
            token = current_cancellation_token()
            waited = self._global_gate.acquire(
                priority, deadline=deadline, token=token)
            _set_current_job_blocking_reason("running")
            if waited > 0.001:
                _log.info(
                    "global cap throttled %s priority=%s (shard %s) %.1fs; cap=%d",
                    label, priority,
                    shard_name or "(no project)", waited, self._global_capacity)
            started = time.monotonic()
            finished = threading.Event()
            hard_timer = None
            if self._hard_timeout_sec > 0:
                def hard_timeout():
                    if not finished.is_set():
                        self._hard_timeout_callback(label)

                hard_timer = self._timer_factory(
                    self._hard_timeout_sec, hard_timeout)
                hard_timer.daemon = True
                hard_timer.start()
            try:
                cancellation_point()
                result = work()
                cancellation_point()
                return result
            finally:
                finished.set()
                if hard_timer is not None:
                    hard_timer.cancel()
                elapsed = time.monotonic() - started
                self._global_gate.release(priority)
                if elapsed >= self._slow_log_sec:
                    _log.info("heavy job completed %s (shard %s) took %.1fs",
                              label, shard_name or "(no project)", elapsed)

        try:
            return entry.coordinator.run(
                key, _globally_gated, label=label, priority=priority,
                deadline=deadline, request_identity=request_identity)
        finally:
            self._release_lane(lane_key, entry)

    def snapshot(self) -> dict:
        """Aggregate telemetry; keeps the keys ``supervisor`` already watches.

        ``active`` / ``active_for_sec`` report the *longest-running* job across
        every shard so stuck-detection keeps seeing the worst offender.
        """
        with self._lock:
            shards = [
                (lane_key, entry.coordinator)
                for lane_key, entry in self._shards.items()
            ]
        parts = [((name, lane), coordinator.snapshot())
                 for (name, lane), coordinator in shards]
        gate = self._global_gate.snapshot()

        worst_label, worst_age = None, 0.0
        queued = followers = 0
        queued_by_priority = {name: 0 for name in _PRIORITY_VALUE}
        oldest_queued = 0.0
        active_jobs: list[dict] = []
        queued_jobs: list[dict] = []

        def append_bounded(target: list[dict], job: dict) -> None:
            target.append(job)
            target.sort(key=lambda item: item["age_sec"], reverse=True)
            del target[self._job_telemetry_limit:]

        def enrich(job: dict, *, shard_name: str, lane: str) -> dict:
            return {
                **job,
                "lane": lane,
                "shard_digest": _shard_digest(shard_name),
            }

        for (shard_name, lane), snap in parts:
            queued += snap["queued"]
            followers += snap["followers"]
            for name, count in snap["queued_by_priority"].items():
                queued_by_priority[name] += count
            oldest_queued = max(oldest_queued, snap["oldest_queued_for_sec"])
            if snap["active"] is not None and snap["active_for_sec"] >= worst_age:
                worst_label = _telemetry_label(snap["active"])
                worst_age = snap["active_for_sec"]
            for active_job in snap["active_jobs"]:
                append_bounded(
                    active_jobs,
                    enrich(active_job, shard_name=shard_name, lane=lane),
                )
            for queued_job in snap["queued_jobs"]:
                append_bounded(
                    queued_jobs,
                    enrich(queued_job, shard_name=shard_name, lane=lane),
                )

        probe = HeavyWorkCoordinator(
            queue_capacity=self._shard_queue_capacity,
            follower_capacity=self._shard_follower_capacity).snapshot()
        return {
            "active": worst_label,
            "queued": queued,
            "queued_by_priority": queued_by_priority,
            "followers": followers,
            "active_for_sec": worst_age if worst_label is not None else 0.0,
            "oldest_queued_for_sec": oldest_queued,
            "queue_capacity": probe["queue_capacity"],
            "follower_capacity": probe["follower_capacity"],
            "shards": len({name for (name, _lane), _snap in parts}),
            "lanes": len(parts),
            "global_capacity": self._global_capacity,
            "interactive_lane_capacity": self._interactive_lane_capacity,
            "global_in_use": gate["in_use"],
            # Waiting purely on the global cap, not on their own shard queue.
            # Persistently > 0 means the cap is the binding constraint.
            "global_waiting": gate["waiting"],
            "global_waiting_by_priority": gate["waiting_by_priority"],
            "global_throttled_total": gate["throttled_total"],
            "global_in_use_by_priority": gate["in_use_by_priority"],
            "interactive_global_reserve": gate["reserve"],
            "active_jobs": active_jobs,
            "queued_jobs": queued_jobs,
            "job_telemetry_limit": self._job_telemetry_limit,
            "gate": gate,
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
