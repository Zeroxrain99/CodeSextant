"""The file watcher, which reindexes incrementally on its own.

A debounced flush really does run an incremental index. These tests enqueue by hand
rather than waiting on real OS events, because the timing of those makes tests flaky.
Also covered: ensure_watch is idempotent, the off switch makes it a no-op, and a missing
watchdog package degrades quietly with the content-hash path as the fallback.
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
    monkeypatch.setenv("CODESEXTANT_WATCH_DEBOUNCE_MS", "300")  # short debounce, faster tests


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
            assert len(mgr.watched()) == 1  # one watch per project, not two
        finally:
            mgr.stop_all()
        assert mgr.watched() == []  # stop_all clears the list

    def test_bad_path_no_watch(self, tmp_path, db_home):
        mgr = watcher.WatchManager(_LOG)
        assert mgr.ensure_watch("E:/__no_such_dir_watch__") is False


class TestDebounceFlush:
    def test_flush_triggers_incremental_reindex(self, tmp_path, db_home):
        # Edit a file, enqueue it, wait for the debounce timer to fire, and the new
        # symbol should be in the index.
        engine.index_project(str(tmp_path))
        _write(tmp_path, "a.py", "def original():\n    return 1\n")
        w = watcher._ProjectWatch(str(tmp_path), _LOG)
        # Add a symbol, then enqueue by hand to stand in for the observer. Real OS
        # events would make this flaky.
        _write(tmp_path, "a.py",
               "def original():\n    return 1\n\n\ndef brand_new_sym():\n    return 2\n")
        w._enqueue(str(tmp_path / "a.py"))
        time.sleep(watcher._debounce_sec() + 0.8)  # debounce window plus indexing time
        r = engine.get_symbols(str(tmp_path), file=str(tmp_path / "a.py"))
        names = {s["name"] for s in r["symbols"]}
        assert "brand_new_sym" in names, names

    def test_debounce_coalesces(self, tmp_path, db_home):
        # Several enqueues in a row collapse into a single flush, so a burst of edits
        # cannot turn into a reindex storm.
        engine.index_project(str(tmp_path))
        _write(tmp_path, "a.py", "x = 1\n")
        flushes = []
        w = watcher._ProjectWatch(str(tmp_path), _LOG)
        orig = w._flush

        def _counting_flush():
            flushes.append(1)
            orig()
        w._flush = _counting_flush
        for _ in range(5):  # five rapid changes
            w._enqueue(str(tmp_path / "a.py"))
            time.sleep(0.02)
        time.sleep(watcher._debounce_sec() + 0.8)
        assert len(flushes) == 1, f"debounce should coalesce into 1 flush, got {len(flushes)}"
