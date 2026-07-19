"""競品吸收 queue 3：file-watcher 主動增量索引測試。

防抖 flush 真會跑增量索引（手動 enqueue 測，不靠真 OS 事件避免時序 flaky）；
ensure_watch 冪等；開關關閉 no-op；watchdog 缺則靜默退（content-hash 兜底）。
"""
import logging
import os
import sys
import textwrap
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine, watcher  # noqa: E402

_LOG = logging.getLogger("test_watcher")


@pytest.fixture()
def db_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "1")
    monkeypatch.setenv("CODESEXTANT_WATCH_DEBOUNCE_MS", "300")  # 縮短防抖加速測試


def _write(root, rel, content):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


class TestWatchSwitch:
    def test_enabled_default(self, monkeypatch):
        monkeypatch.delenv("CODESEXTANT_WATCH_ENABLED", raising=False)
        assert watcher.watch_enabled() is True

    def test_disabled_env(self, monkeypatch):
        monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "0")
        assert watcher.watch_enabled() is False

    def test_debounce_env(self, monkeypatch):
        monkeypatch.setenv("CODESEXTANT_WATCH_DEBOUNCE_MS", "1500")
        assert abs(watcher._debounce_sec() - 1.5) < 1e-9

    def test_disabled_ensure_noop(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODESEXTANT_WATCH_ENABLED", "0")
        mgr = watcher.WatchManager(_LOG)
        _write(tmp_path, "a.py", "x = 1\n")
        assert mgr.ensure_watch(str(tmp_path)) is False
        assert mgr.watched() == []


class TestWatchManager:
    def test_ensure_idempotent(self, tmp_path, db_home):
        mgr = watcher.WatchManager(_LOG)
        _write(tmp_path, "a.py", "def f():\n    return 1\n")
        ok1 = mgr.ensure_watch(str(tmp_path))
        ok2 = mgr.ensure_watch(str(tmp_path))
        try:
            assert ok1 is True and ok2 is True
            assert len(mgr.watched()) == 1  # 同專案只掛一次
        finally:
            mgr.stop_all()
        assert mgr.watched() == []  # stop 後清空

    def test_bad_path_no_watch(self, tmp_path, db_home):
        mgr = watcher.WatchManager(_LOG)
        assert mgr.ensure_watch("E:/__no_such_dir_watch__") is False


class TestDebounceFlush:
    def test_flush_triggers_incremental_reindex(self, tmp_path, db_home):
        # 防抖 flush 真會跑增量索引：改檔→enqueue→等防抖 timer fire→新符號進索引
        engine.index_project(str(tmp_path))
        _write(tmp_path, "a.py", "def original():\n    return 1\n")
        w = watcher._ProjectWatch(str(tmp_path), _LOG)
        # 改檔加新符號 + 手動 enqueue（模擬 observer 偵測，不靠真 OS 事件避免 flaky）
        _write(tmp_path, "a.py",
               "def original():\n    return 1\n\n\ndef brand_new_sym():\n    return 2\n")
        w._enqueue(str(tmp_path / "a.py"))
        time.sleep(watcher._debounce_sec() + 0.8)  # 等防抖窗口 + 索引完成
        r = engine.get_symbols(str(tmp_path), file=str(tmp_path / "a.py"))
        names = {s["name"] for s in r["symbols"]}
        assert "brand_new_sym" in names, names

    def test_debounce_coalesces(self, tmp_path, db_home):
        # 連續多次 enqueue 只觸發一次 flush（防抖合併，不重索引風暴）
        engine.index_project(str(tmp_path))
        _write(tmp_path, "a.py", "x = 1\n")
        flushes = []
        w = watcher._ProjectWatch(str(tmp_path), _LOG)
        orig = w._flush

        def _counting_flush():
            flushes.append(1)
            orig()
        w._flush = _counting_flush
        for _ in range(5):  # 快速連續 5 次變動
            w._enqueue(str(tmp_path / "a.py"))
            time.sleep(0.02)
        time.sleep(watcher._debounce_sec() + 0.8)
        assert len(flushes) == 1, f"防抖應合併成 1 次 flush，實際 {len(flushes)}"
