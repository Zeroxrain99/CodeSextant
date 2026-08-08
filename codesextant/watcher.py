"""File-watch proactive incremental indexing (competitor-feature-absorption queue 3,
inspired by CodeGraph/aider).

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
  - Switches + parameters are all configurable (L0 hard rule #6).

Switches (all tolerant of .lower()):
  - CODESEXTANT_WATCH_ENABLED = 0/false/no/off to disable (default on).
  - CODESEXTANT_WATCH_DEBOUNCE_MS = the debounce window in milliseconds (default 2000).
"""
from __future__ import annotations

import os
import threading

from . import engine, symbols, work_coordinator


def watch_enabled() -> bool:
    return os.environ.get("CODESEXTANT_WATCH_ENABLED", "1").lower() not in (
        "0", "false", "no", "off")


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


class _ProjectWatch:
    """A single project's watchdog observer + debounced incremental indexing."""

    def __init__(self, repo_path: str, logger):
        self.repo_path = os.path.abspath(repo_path)
        self.logger = logger
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._observer = None
        self._generation = 0
        self._stopping = False

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
                self._add(event)

            def on_modified(self, event):
                if not event.is_directory:
                    self._add(event)

            def on_deleted(self, event):
                self._add(event)

            def on_moved(self, event):
                self._add(event, include_destination=True)

        obs = Observer()
        obs.schedule(_Handler(), self.repo_path, recursive=True)
        obs.daemon = True
        obs.start()
        self._observer = obs

    def _enqueue(self, path: str) -> None:
        with self._lock:
            if self._stopping:
                return
            self._pending.add(path)
            self._generation += 1
            if self._timer is not None:
                self._timer.cancel()
            self._arm_timer_locked()

    def _arm_timer_locked(self) -> None:
        """Arm at most one debounce/retry timer while holding ``_lock``."""
        self._timer = threading.Timer(_debounce_sec(), self._flush)
        self._timer.daemon = True
        self._timer.start()

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
            )
            self.logger.info(
                "watcher targeted reindex %s (triggered by %d changed paths) -> "
                "indexed=%s skipped=%s removed=%s",
                self.repo_path, n, r.get("indexed"), r.get("skipped"), r.get("removed"))
        except Exception as exc:  # an indexing failure must not crash the watcher thread
            self.logger.warning("watcher incremental index failed %s: %s", self.repo_path, exc)
            with self._lock:
                if not self._stopping:
                    # Admission rejection or index failure must not consume the
                    # dirty batch.  Merge with events received during the run;
                    # a single bounded debounce timer retries the whole set.
                    self._pending.update(pending)
                    if self._timer is None:
                        self._arm_timer_locked()

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


class WatchManager:
    """Manages watchers for multiple projects (held by the daemon singleton). Idempotent:
    a given project is only attached once."""

    def __init__(self, logger):
        self.logger = logger
        self._watches: dict[str, _ProjectWatch] = {}
        self._lock = threading.Lock()
        self._watched_snapshot: tuple[str, ...] = ()

    def ensure_watch(self, repo_path: str) -> bool:
        """Ensure a project is being watched (idempotent). Returns True=being watched /
        False=not attached (disabled/watchdog missing/failed)."""
        if not watch_enabled():
            return False
        try:
            import watchdog.observers  # noqa: F401  probe availability
        except ImportError:
            return False  # watchdog not installed -> silently back off (content-hash fallback still applies)
        if not repo_path:
            return False
        rp = os.path.abspath(repo_path)
        if not os.path.isdir(rp):
            return False
        with self._lock:
            if rp in self._watches:
                return True
        w = _ProjectWatch(rp, self.logger)
        try:
            w.start()
        except Exception as exc:
            self.logger.warning("watcher attach failed %s: %s", rp, exc)
            return False
        keep = False
        with self._lock:
            if rp not in self._watches:
                self._watches[rp] = w
                self._watched_snapshot = tuple(sorted(self._watches))
                keep = True
        if not keep:
            w.stop()
            return True
        self.logger.info("watcher attached %s (debounce %.1fs)", rp, _debounce_sec())
        return True

    def watched(self) -> list[str]:
        return list(self._watched_snapshot)

    def watched_snapshot(self) -> tuple[str, ...]:
        """Lock-free immutable snapshot for the health control plane."""
        return self._watched_snapshot

    def recover(self, repo_path: str) -> dict:
        """Reconcile once after daemon startup to cover changes made while it was down.

        This is deliberately lifecycle-triggered, never periodic. The watcher must be
        attached before this runs so an edit during recovery is still queued afterward.
        """
        rp = os.path.abspath(repo_path)
        key = work_coordinator.make_work_key(
            "/reindex", rp, {"force": False, "source": "watcher-recovery"}
        )
        result = work_coordinator.SHARED_SHARDED.run(
            key,
            lambda: engine.index_project(rp),
            label="watcher/recovery",
            shard=key[1],
        )
        self.logger.info(
            "watcher startup recovery %s -> indexed=%s skipped=%s removed=%s",
            rp,
            result.get("indexed"),
            result.get("skipped"),
            result.get("removed"),
        )
        return result

    def stop_all(self) -> None:
        with self._lock:
            watches = list(self._watches.values())
            self._watches.clear()
            self._watched_snapshot = ()
        for w in watches:
            w.stop()
