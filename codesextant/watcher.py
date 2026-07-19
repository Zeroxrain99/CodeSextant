"""檔案監看主動增量索引（競品吸收 queue 3，CodeGraph/aider 啟發）。

CodeSextant 原本是「被查詢時才比 content-hash」的被動增量——查詢端要等、且未 commit 的改動
（content 變但 git sha 沒變）wrapper 不會自動 reindex（已知盲區）。本模組讓單例 daemon 掛
OS 原生 file-watcher（watchdog：Windows 走 ReadDirectoryChangesW / Linux inotify / macOS
FSEvents），檔一變就**防抖後主動增量索引**，地圖永遠新鮮、查詢零等待、不靠 git sha。

設計鐵則：
  - ⛔ 不取代 content-hash 增量（index_project 仍 content-hash 只重算變的檔）——watcher 只是
    「主動觸發 index_project」的前置；watcher 漏抓時查詢端比 hash 仍是兜底。
  - 防抖窗口必設（git checkout/大量改檔不觸發重索引風暴）。
  - watchdog 沒裝 → 靜默退化（不啟動 watcher，content-hash 兜底照常），不報錯不擋。
  - 開關 + 參數全 config（L0 鐵律 #6）。

開關（皆 .lower() 容錯）：
  - CODESEXTANT_WATCH_ENABLED = 0/false/no/off 關閉（預設 on）。
  - CODESEXTANT_WATCH_DEBOUNCE_MS = 防抖窗口毫秒（預設 2000）。
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
    """關閉時等 OS 監看執行緒收工的上限秒數（可調，見呼叫處註解）。"""
    try:
        v = float(os.environ.get("CODESEXTANT_WATCH_STOP_JOIN_SEC", "2"))
        return v if v > 0 else 2.0
    except ValueError:
        return 2.0


class _ProjectWatch:
    """單一專案的 watchdog observer + 防抖增量索引。"""

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
            def on_any_event(self, event):
                if event.is_directory:
                    return
                p = getattr(event, "dest_path", "") or event.src_path
                # 只理會支援語言的原始碼檔變動（跳過 .pyc/.db/雜訊）
                if os.path.splitext(p)[1].lower() in symbols.SUPPORTED_EXTENSIONS:
                    mgr._enqueue(p)

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
            # 增量（content-hash 只重算真的變的檔）；watcher 只負責「主動觸發」
            key = work_coordinator.make_work_key(
                "/reindex", self.repo_path, {
                    "force": False,
                    "source": "watcher",
                    "generation": generation,
                })
            # 與 HTTP 端點共用同一個分片權威：同一 repo ⇒ 同一車道，所以
            # watcher 觸發的重索引會跟 /reindex 排隊而不是並行跑兩份，也一樣
            # 受全域併發上限管控。用兩個 coordinator 會讓兩者互相看不見。
            r = work_coordinator.SHARED_SHARDED.run(
                key,
                lambda: engine.index_project(self.repo_path),
                label="watcher/reindex",
                shard=key[1],
            )
            self.logger.info(
                "watcher 增量重索引 %s（%d 檔變動觸發）→ indexed=%s skipped=%s removed=%s",
                self.repo_path, n, r.get("indexed"), r.get("skipped"), r.get("removed"))
        except Exception as exc:  # 索引失敗不該炸 watcher thread
            self.logger.warning("watcher 增量索引失敗 %s：%s", self.repo_path, exc)
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
                # 有界等待：關閉路徑不可被卡住的 OS 監看執行緒無限拖住（daemon
                # 關閉會連帶擋住重啟）。逾時就放生該執行緒——它是 daemon 執行緒，
                # 進程結束時一併回收。可調：CODESEXTANT_WATCH_STOP_JOIN_SEC。
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
    """管多專案的 watcher（daemon 單例持有）。冪等：同專案只掛一次。"""

    def __init__(self, logger):
        self.logger = logger
        self._watches: dict[str, _ProjectWatch] = {}
        self._lock = threading.Lock()
        self._watched_snapshot: tuple[str, ...] = ()

    def ensure_watch(self, repo_path: str) -> bool:
        """確保某專案被監看（冪等）。回 True=有在監看 / False=未掛（關閉/watchdog 缺/失敗）。"""
        if not watch_enabled():
            return False
        try:
            import watchdog.observers  # noqa: F401  探可用性
        except ImportError:
            return False  # watchdog 沒裝 → 靜默退（content-hash 兜底仍在）
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
            self.logger.warning("watcher 掛載失敗 %s：%s", rp, exc)
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
        self.logger.info("watcher 掛載 %s（防抖 %.1fs）", rp, _debounce_sec())
        return True

    def watched(self) -> list[str]:
        return list(self._watched_snapshot)

    def watched_snapshot(self) -> tuple[str, ...]:
        """Lock-free immutable snapshot for the health control plane."""
        return self._watched_snapshot

    def stop_all(self) -> None:
        with self._lock:
            watches = list(self._watches.values())
            self._watches.clear()
            self._watched_snapshot = ()
        for w in watches:
            w.stop()
