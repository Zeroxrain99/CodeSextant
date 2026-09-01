"""Event-driven incremental indexing for watched repositories.

The singleton daemon attaches a native OS file watcher (ReadDirectoryChangesW on
Windows, inotify on Linux, and FSEvents on macOS). Normal changes are passed to the
engine as exact dirty paths after debouncing, so saving one file never traverses the
whole repository.

Design principles:
  - Content hashes remain a per-file safety check, not a repository discovery mechanism.
  - A debounce window is mandatory (so a git checkout / mass file change doesn't trigger
    a reindex storm).
  - Watchdog is a required package dependency. If a broken environment still lacks it,
    watcher attachment fails closed and an explicit reconciliation remains available.
  - Environment variables configure watcher behavior and debounce timing.

Switches (all tolerant of .lower()):
  - CODESEXTANT_WATCH_ENABLED = 0/false/no/off to disable (default on).
  - CODESEXTANT_WATCH_DEBOUNCE_MS = the debounce window in milliseconds (default 2000).
  - CODESEXTANT_WATCH_RETRY_MAX_SEC = overload retry cap in seconds (default 60).
  - CODESEXTANT_WATCH_RETRY_JITTER = retry spread as a fraction (default 0.2).
  - CODESEXTANT_WATCH_RECOVERY_FOLLOWER_CAP = concurrent recovery followers
    (defaults to CODESEXTANT_HEAVY_FOLLOWER_CAP, normally 8).
"""
from __future__ import annotations

import os
import random
import threading
import time

from . import engine, storage, symbols, work_coordinator


def watch_enabled() -> bool:
    return os.environ.get("CODESEXTANT_WATCH_ENABLED", "1").lower() not in (
        "0", "false", "no", "off")


def _max_watched_dirs() -> int:
    """A ceiling for the repository that is still enormous after skipping build output.

    Past it the watcher stops adding rather than exhausting a system limit -- on Linux
    that limit is per *user*, so running out breaks every editor and build tool on the
    machine, not just this one. 4,000 is far above any source tree measured here and far
    below a default `fs.inotify.max_user_watches`.
    """
    try:
        return max(1, int(os.environ.get("CODESEXTANT_WATCH_MAX_DIRS", "4000")))
    except (TypeError, ValueError):
        return 4000


def _debounce_sec() -> float:
    try:
        ms = float(os.environ.get("CODESEXTANT_WATCH_DEBOUNCE_MS", "2000"))
        return ms / 1000.0 if ms > 0 else 2.0
    except ValueError:
        return 2.0


def _stop_join_timeout() -> float:
    """Max seconds to wait for the OS watcher thread to wind down on shutdown (tunable,
    see the comment at the call site)."""
    try:
        v = float(os.environ.get("CODESEXTANT_WATCH_STOP_JOIN_SEC", "2"))
        return v if v > 0 else 2.0
    except ValueError:
        return 2.0


def _retry_max_sec() -> float:
    try:
        value = float(os.environ.get("CODESEXTANT_WATCH_RETRY_MAX_SEC", "60"))
        return value if value > 0 else 60.0
    except ValueError:
        return 60.0


def _retry_jitter() -> float:
    try:
        return min(1.0, max(0.0, float(os.environ.get(
            "CODESEXTANT_WATCH_RETRY_JITTER", "0.2"))))
    except ValueError:
        return 0.2


class _RecoveryAttempt:
    """One recovery generation shared by its leader and waiting followers."""

    def __init__(self):
        self.event = threading.Event()
        self.error: BaseException | None = None
        self.followers = 0


def _recovery_follower_capacity() -> int:
    raw_value = os.environ.get(
        "CODESEXTANT_WATCH_RECOVERY_FOLLOWER_CAP",
        os.environ.get("CODESEXTANT_HEAVY_FOLLOWER_CAP", "8"),
    )
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return 8


def _clone_recovery_error(exc: BaseException) -> BaseException:
    """Give each follower its own exception while retaining type and details."""
    try:
        cloned = type(exc)(*exc.args)
        if hasattr(exc, "__dict__"):
            cloned.__dict__.update(exc.__dict__.copy())
        return cloned
    except Exception:  # pragma: no cover - defensive for exotic exceptions
        return RuntimeError(f"{type(exc).__name__}: {exc}")


class _ProjectWatch:
    """A single project's watchdog observer + debounced incremental indexing."""

    def __init__(self, repo_path: str, logger, *, on_activity=None):
        self.repo_path = os.path.abspath(repo_path)
        self.logger = logger
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._observer = None
        self._generation = 0
        self._stopping = False
        self._retry_delay: float | None = None
        self._flushing = 0
        self._flush_done = threading.Event()
        self._flush_done.set()
        self._on_activity = on_activity or (lambda: None)

    def start(self) -> None:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        mgr = self

        class _Handler(FileSystemEventHandler):
            def _add(self, event, *, include_destination=False):
                paths = [event.src_path]
                if include_destination:
                    destination = getattr(event, "dest_path", "")
                    if destination:
                        paths.append(destination)
                for event_path in paths:
                    if event.is_directory or (
                        os.path.splitext(event_path)[1].lower()
                        in symbols.SUPPORTED_EXTENSIONS
                    ):
                        mgr._enqueue(event_path)

            def on_created(self, event):
                if event.is_directory:
                    mgr._watch_new_directory(event.src_path)
                self._add(event)

            def on_modified(self, event):
                if not event.is_directory:
                    self._add(event)

            def on_deleted(self, event):
                self._add(event)

            def on_moved(self, event):
                self._add(event, include_destination=True)

        obs = Observer()
        self._handler = _Handler()
        watched, skipped, capped = self._watch_tree(obs, self._handler)
        obs.daemon = True
        obs.start()
        self._observer = obs
        if skipped or capped:
            self.logger.info(
                "watcher attached %s (%d directories watched, %d skipped as build or "
                "dependency output%s)", self.repo_path, watched, skipped,
                f", capped at {_max_watched_dirs()}" if capped else "")

    def _watch_tree(self, obs, handler) -> tuple[int, int, bool]:
        """Watch the directories that hold source, and only those.

        `recursive=True` over a repository root is one call and the wrong one: watchdog
        puts a watch on every directory under it, including `node_modules`, `.venv`,
        `build` and `.git`. Measured on a project shaped like a real front end -- 1,317
        directories, 22 of them source -- that is 98.3% of the watches spent on files
        this tool never reads. On Linux they are inotify descriptors against a per-user
        cap, and everywhere they are an event storm on every install or build.

        So the tree is walked with the *indexer's own* skip list and each surviving
        directory gets its own non-recursive watch. New directories are picked up in
        `_Handler.on_created`, which is where a recursive watch's one advantage went.

        A cap is kept for the repository that is enormous even after skipping: past it
        the watcher stops adding, and says so, rather than exhausting a system limit
        that would break every other tool on the machine too.
        """
        ceiling = _max_watched_dirs()
        watched = skipped = 0
        capped = False
        for base, dirs, _files in os.walk(self.repo_path):
            pruned = [d for d in dirs if d in engine._SKIP_DIRS]
            skipped += len(pruned)
            dirs[:] = [d for d in dirs if d not in engine._SKIP_DIRS]
            if watched >= ceiling:
                capped = True
                dirs[:] = []
                continue
            try:
                obs.schedule(handler, base, recursive=False)
                watched += 1
            except OSError:
                # A directory that vanished between the walk and the schedule, or a
                # system watch limit already reached. Neither is worth failing a whole
                # index over.
                capped = True
        return watched, skipped, capped

    def _watch_new_directory(self, path: str) -> None:
        """Extend the watch to a directory created after start().

        The one thing `recursive=True` gave for free. Without it a newly created package
        would be invisible until the next attach.
        """
        observer, handler = self._observer, getattr(self, "_handler", None)
        if observer is None or handler is None:
            return
        if os.path.basename(path) in engine._SKIP_DIRS or not os.path.isdir(path):
            return
        try:
            observer.schedule(handler, path, recursive=False)
        except (OSError, RuntimeError):
            pass

    def _enqueue(self, path: str) -> None:
        with self._lock:
            if self._stopping:
                return
            self._pending.add(path)
            self._generation += 1
            if self._timer is not None:
                self._timer.cancel()
            self._arm_timer_locked(self._jittered_retry_delay_locked())
        self._on_activity()

    def _arm_timer_locked(self, delay: float | None = None) -> None:
        """Arm at most one debounce/retry timer while holding ``_lock``."""
        self._timer = threading.Timer(
            _debounce_sec() if delay is None else delay, self._flush)
        self._timer.daemon = True
        self._timer.start()

    def _jittered_retry_delay_locked(self) -> float | None:
        if self._retry_delay is None:
            return None
        jitter = _retry_jitter()
        factor = random.uniform(1.0 - jitter, 1.0 + jitter)
        return min(_retry_max_sec(), self._retry_delay * factor)

    def _advance_retry_delay_locked(self) -> float:
        base = _debounce_sec()
        self._retry_delay = (
            base if self._retry_delay is None
            else min(_retry_max_sec(), self._retry_delay * 2.0))
        return self._jittered_retry_delay_locked() or base

    def _flush(self) -> None:
        caller = threading.current_thread()
        called_by_timer = isinstance(caller, threading.Timer)
        with self._lock:
            # cancel() cannot stop a callback that already started.  A stale
            # callback must not consume pending work or clear a newer timer.
            if called_by_timer and caller is not self._timer:
                return
            if self._stopping:
                self._timer = None
                return
            if not called_by_timer and self._timer is not None:
                self._timer.cancel()
            pending = set(self._pending)
            n = len(pending)
            self._pending.clear()
            generation = self._generation
            self._timer = None
            if pending:
                self._flushing += 1
                self._flush_done.clear()
        if not pending:
            return
        try:
            # The event batch is the discovery source. Normal saves must never turn into
            # a repository traversal.
            key = work_coordinator.make_work_key(
                "/reindex", self.repo_path, {
                    "force": False,
                    "source": "watcher",
                    "generation": generation,
                })
            # Shares the same shard authority as the HTTP endpoint: same repo => same
            # lane, so a reindex triggered by the watcher queues behind /reindex instead of
            # running two copies in parallel, and is subject to the same global
            # concurrency cap. Using two separate coordinators would make them blind to
            # each other.
            r = work_coordinator.SHARED_SHARDED.run(
                key,
                lambda: engine.index_paths(self.repo_path, sorted(pending)),
                label="watcher/reindex",
                shard=key[1],
                priority="background",
            )
            self.logger.info(
                "watcher targeted reindex %s (triggered by %d changed paths) -> "
                "indexed=%s skipped=%s removed=%s",
                self.repo_path, n, r.get("indexed"), r.get("skipped"), r.get("removed"))
            with self._lock:
                self._retry_delay = None
        except Exception as exc:  # an indexing failure must not crash the watcher thread
            self.logger.warning("watcher incremental index failed %s: %s", self.repo_path, exc)
            with self._lock:
                if not self._stopping:
                    # Admission rejection or index failure must not consume the
                    # dirty batch.  Merge with events received during the run;
                    # a single bounded debounce timer retries the whole set.
                    self._pending.update(pending)
                    if self._timer is None:
                        self._arm_timer_locked(self._advance_retry_delay_locked())
        finally:
            try:
                self._on_activity()
            finally:
                with self._lock:
                    self._flushing -= 1
                    if self._flushing == 0:
                        self._flush_done.set()

    def is_quiescent(self) -> bool:
        """Return whether eviction can stop this watcher without dropping work."""
        with self._lock:
            return (
                not self._pending
                and self._timer is None
                and not self._flushing
            )

    def stop(self) -> None:
        with self._lock:
            self._stopping = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if self._observer is not None:
            try:
                self._observer.stop()
                # Bounded wait: the shutdown path must not be dragged out indefinitely by
                # a stuck OS watcher thread (daemon shutdown would then also block a
                # restart). If it times out, let the thread go, since it's a daemon thread and
                # gets reclaimed when the process exits anyway. Tunable via
                # CODESEXTANT_WATCH_STOP_JOIN_SEC.
                self._observer.join(timeout=_stop_join_timeout())
            except Exception:
                pass
            self._observer = None
        # A timer may have entered _flush immediately before _stopping was set.
        # Cancel any re-arm after the observer has stopped producing callbacks.
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        # An entered timer callback may already own an index transaction. The
        # daemon must retain its instance lock until every such callback leaves,
        # otherwise a replacement daemon can overlap the old writer. Running
        # heavy calls already use this timeout as their process-level hard-stop
        # boundary. A configured zero deliberately disables that boundary.
        hard_timeout = getattr(
            work_coordinator.SHARED_SHARDED, "hard_timeout_sec", 0
        )
        if not self._flush_done.wait(
                timeout=hard_timeout if hard_timeout > 0 else None):
            work_coordinator.fail_fast_stuck_job("watcher/shutdown-drain")


class WatchManager:
    """Attach, recover, and evict project watchers on demand."""

    def __init__(self, logger, *, idle_ttl_sec: float | None = None,
                 clock=time.monotonic, on_activity=None):
        self.logger = logger
        self._watches: dict[str, _ProjectWatch] = {}
        self._lock = threading.Lock()
        self._watched_snapshot: tuple[str, ...] = ()
        self._project_paths: dict[str, str] = {}
        self._last_activity: dict[str, float] = {}
        self._recovery_states: dict[str, str] = {}
        self._recovery_attempts: dict[str, _RecoveryAttempt] = {}
        self._recovery_follower_capacity = _recovery_follower_capacity()
        self._clock = clock
        self._on_activity = on_activity or (lambda: None)
        if idle_ttl_sec is None:
            try:
                idle_ttl_sec = float(os.environ.get(
                    "CODESEXTANT_WATCH_IDLE_TTL_SEC", "10800"))
            except ValueError:
                idle_ttl_sec = 10800.0
        self._idle_ttl_sec = max(0.0, float(idle_ttl_sec))
        self._eviction_timer: threading.Timer | None = None
        self._stopped = False

    @staticmethod
    def _normalize(repo_path: str) -> str:
        return os.path.normcase(os.path.abspath(repo_path))

    @staticmethod
    def _absolute(repo_path: str) -> str:
        """Return an I/O path without changing its case on Windows."""
        return os.path.abspath(repo_path)

    def _refresh_snapshot_locked(self) -> None:
        self._watched_snapshot = tuple(sorted(
            self._project_paths.get(
                project_key, getattr(watch, "repo_path", project_key)
            )
            for project_key, watch in self._watches.items()
        ))

    def _touch_locked(self, project_key: str) -> None:
        self._last_activity[project_key] = self._clock()
        self._arm_eviction_locked()

    def _arm_eviction_locked(self) -> None:
        if self._eviction_timer is not None:
            self._eviction_timer.cancel()
            self._eviction_timer = None
        if self._stopped or self._idle_ttl_sec <= 0 or not self._last_activity:
            return
        next_expiry = min(self._last_activity.values()) + self._idle_ttl_sec
        delay = max(0.001, next_expiry - self._clock())
        timer = threading.Timer(delay, self._eviction_due)
        timer.daemon = True
        self._eviction_timer = timer
        timer.start()

    def _eviction_due(self) -> None:
        with self._lock:
            self._eviction_timer = None
        self.evict_idle()

    def _watch_activity(self, project_key: str) -> None:
        with self._lock:
            if self._stopped or project_key not in self._watches:
                return
            self._touch_locked(project_key)
        self._on_activity()

    def ensure_watch(self, repo_path: str) -> bool:
        """Ensure a project is being watched (idempotent). Returns True=being watched /
        False=not attached (disabled/watchdog missing/failed)."""
        if not watch_enabled() or not repo_path:
            return False
        rp = self._absolute(repo_path)
        project_key = self._normalize(rp)
        with self._lock:
            if self._stopped:
                return False
            if project_key in self._watches:
                self._touch_locked(project_key)
                return True
        try:
            import watchdog.observers  # noqa: F401  probe availability
        except ImportError:
            return False  # watchdog not installed -> silently back off (content-hash fallback still applies)
        if not os.path.isdir(rp):
            return False
        w = _ProjectWatch(
            rp, self.logger,
            on_activity=lambda: self._watch_activity(project_key))
        try:
            w.start()
        except Exception as exc:
            self.logger.warning("watcher attach failed %s: %s", rp, exc)
            return False
        keep = False
        available = False
        with self._lock:
            if self._stopped:
                available = False
            elif project_key not in self._watches:
                self._watches[project_key] = w
                self._project_paths.setdefault(project_key, rp)
                self._refresh_snapshot_locked()
                self._touch_locked(project_key)
                keep = True
                available = True
            else:
                self._touch_locked(project_key)
                available = True
        if not keep:
            w.stop()
            return available
        self.logger.info("watcher attached %s (debounce %.1fs)", rp, _debounce_sec())
        self._on_activity()
        return True

    def watched(self) -> list[str]:
        return list(self._watched_snapshot)

    def watched_snapshot(self) -> tuple[str, ...]:
        """Lock-free immutable snapshot for the health control plane."""
        return self._watched_snapshot

    def ensure_ready(self, repo_path: str, *, deadline: float | None = None) -> dict:
        """Reconcile one existing index before its first real query."""
        rp = self._absolute(repo_path)
        project_key = self._normalize(rp)
        with self._lock:
            if self._stopped:
                raise RuntimeError("CodeSextant watcher manager is stopped")
        self.ensure_watch(rp)
        if not storage.db_path_for(rp).exists():
            self.mark_ready(rp)
            return {"action": "not-indexed", "repo_path": rp}

        with self._lock:
            if self._stopped:
                raise RuntimeError("CodeSextant watcher manager is stopped")
            self._project_paths.setdefault(project_key, rp)
            self._touch_locked(project_key)
            state = self._recovery_states.get(project_key, "unseen")
            if state == "ready":
                return {"action": "ready", "repo_path": rp}
            if state == "recovering":
                attempt = self._recovery_attempts[project_key]
                if attempt.followers >= self._recovery_follower_capacity:
                    raise work_coordinator.HeavyWorkQueueFull(
                        "watcher recovery follower capacity reached; retry later")
                attempt.followers += 1
                leader = False
            else:
                attempt = _RecoveryAttempt()
                self._recovery_states[project_key] = "recovering"
                self._recovery_attempts[project_key] = attempt
                leader = True

        if not leader:
            try:
                remaining = (
                    None if deadline is None
                    else max(0.0, deadline - time.monotonic())
                )
                if not attempt.event.wait(timeout=remaining):
                    raise work_coordinator.HeavyWorkDeadlineExceeded(
                        "watcher recovery follower deadline exceeded")
                if attempt.error is not None:
                    raise _clone_recovery_error(attempt.error)
                with self._lock:
                    if self._stopped:
                        raise RuntimeError("CodeSextant watcher manager is stopped")
                    self._touch_locked(project_key)
                return {"action": "ready", "repo_path": rp}
            finally:
                with self._lock:
                    attempt.followers -= 1

        try:
            result = (
                self.recover(rp)
                if deadline is None
                else self.recover(rp, deadline=deadline)
            )
        except BaseException as exc:
            with self._lock:
                attempt.error = exc
                if self._recovery_attempts.get(project_key) is attempt:
                    self._recovery_states[project_key] = "unseen"
                    self._recovery_attempts.pop(project_key, None)
                attempt.event.set()
            raise
        else:
            notify = False
            with self._lock:
                if (not self._stopped
                        and self._recovery_attempts.get(project_key) is attempt):
                    self._recovery_states[project_key] = "ready"
                    self._recovery_attempts.pop(project_key, None)
                    self._touch_locked(project_key)
                    notify = True
                attempt.event.set()
            if notify:
                self._on_activity()
            return result

    def mark_ready(self, repo_path: str) -> None:
        rp = self._absolute(repo_path)
        project_key = self._normalize(rp)
        with self._lock:
            if self._stopped:
                return
            self._project_paths.setdefault(project_key, rp)
            self._recovery_states[project_key] = "ready"
            self._touch_locked(project_key)
            attempt = self._recovery_attempts.pop(project_key, None)
            if attempt is not None:
                attempt.event.set()

    def recovery_state(self, repo_path: str) -> str:
        project_key = self._normalize(repo_path)
        with self._lock:
            return self._recovery_states.get(project_key, "unseen")

    def recover(self, repo_path: str, *, deadline: float | None = None) -> dict:
        """Reconcile on the first real query after a daemon restart.

        The watcher is attached first, so an edit during recovery remains queued
        for the targeted incremental pass that follows.
        """
        rp = self._absolute(repo_path)
        key = work_coordinator.make_work_key(
            "/reindex", rp, {"force": False}
        )
        result = work_coordinator.SHARED_SHARDED.run(
            key,
            lambda: engine.index_project(rp),
            label="watcher/recovery",
            shard=key[1],
            priority="background",
            deadline=deadline,
        )
        self.logger.info(
            "watcher first-query recovery %s -> indexed=%s skipped=%s removed=%s",
            rp,
            result.get("indexed"),
            result.get("skipped"),
            result.get("removed"),
        )
        return result

    def evict_idle(self, *, now: float | None = None) -> list[str]:
        """Evict expired lifecycle entries, stopping quiescent watchers."""
        now = self._clock() if now is None else now
        expired: list[tuple[str, _ProjectWatch | None]] = []
        with self._lock:
            if self._stopped:
                return []
            for project_key, last_activity in list(self._last_activity.items()):
                idle_for = now - last_activity
                if idle_for < self._idle_ttl_sec:
                    continue
                if self._recovery_states.get(project_key) == "recovering":
                    self._last_activity[project_key] = now
                    continue
                watch = self._watches.get(project_key)
                if watch is not None and not watch.is_quiescent():
                    self._last_activity[project_key] = now
                    continue
                rp = self._project_paths.pop(project_key, project_key)
                expired.append((rp, watch))
                self._watches.pop(project_key, None)
                self._last_activity.pop(project_key, None)
                self._recovery_states.pop(project_key, None)
                self._recovery_attempts.pop(project_key, None)
            self._refresh_snapshot_locked()
            self._arm_eviction_locked()
        for rp, watch in expired:
            if watch is not None:
                watch.stop()
                self.logger.info("watcher evicted after idle timeout %s", rp)
        return [rp for rp, _watch in expired]

    def has_pending_work(self) -> bool:
        with self._lock:
            if any(state == "recovering" for state in self._recovery_states.values()):
                return True
            watches = list(self._watches.values())
        return any(not watch.is_quiescent() for watch in watches)

    def stop_all(self) -> None:
        with self._lock:
            watches = list(self._watches.values())
            self._watches.clear()
            self._watched_snapshot = ()
            self._project_paths.clear()
            self._last_activity.clear()
            self._recovery_states.clear()
            attempts = list(self._recovery_attempts.values())
            self._recovery_attempts.clear()
            self._stopped = True
            if self._eviction_timer is not None:
                self._eviction_timer.cancel()
                self._eviction_timer = None
        for attempt in attempts:
            if attempt.error is None:
                attempt.error = RuntimeError(
                    "CodeSextant watcher manager stopped during recovery")
            attempt.event.set()
        for w in watches:
            w.stop()
