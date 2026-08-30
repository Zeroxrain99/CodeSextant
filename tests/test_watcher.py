"""The file watcher, which reindexes incrementally on its own.

A debounced flush really does run an incremental index. These tests enqueue by hand
rather than waiting on real OS events, because the timing of those makes tests flaky.
Also covered: ensure_watch is idempotent, the off switch makes it a no-op, and a missing
watchdog is a required dependency, while a broken environment still fails closed.
"""
import logging
import os
import sys
import textwrap
import time
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import wait_until  # noqa: E402

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
    def test_watchdog_is_a_required_install_dependency(self):
        pyproject = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )
        dependencies = pyproject["project"]["dependencies"]
        assert any(dependency.startswith("watchdog") for dependency in dependencies)

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

    def test_recovery_is_an_explicit_full_reconciliation(self, tmp_path, db_home, monkeypatch):
        calls = []
        monkeypatch.setattr(
            engine,
            "index_project",
            lambda project: calls.append(project)
            or {"indexed": 0, "skipped": 1, "removed": 0},
        )
        manager = watcher.WatchManager(_LOG)

        result = manager.recover(str(tmp_path))

        assert calls == [str(tmp_path.resolve())]
        assert result["skipped"] == 1

    def test_real_file_event_indexes_new_source_without_manual_flush(self, tmp_path, db_home):
        engine.index_project(str(tmp_path))
        manager = watcher.WatchManager(_LOG)
        assert manager.ensure_watch(str(tmp_path)) is True
        try:
            created = _write(tmp_path, "created.py", "def arrived_by_event(): return 1\n")
            deadline = time.time() + 8
            names = set()
            while time.time() < deadline:
                names = {
                    symbol["name"]
                    for symbol in engine.get_symbols(str(tmp_path), file=created)["symbols"]
                }
                if "arrived_by_event" in names:
                    break
                time.sleep(0.1)
            assert "arrived_by_event" in names
        finally:
            manager.stop_all()


class TestDebounceFlush:
    def test_flush_passes_dirty_paths_without_calling_full_index(
            self, tmp_path, db_home, monkeypatch):
        changed = str(tmp_path / "changed.py")
        calls = []

        def targeted(project, paths):
            calls.append((project, set(paths)))
            return {"indexed": 1, "skipped": 0, "removed": 0}

        monkeypatch.setattr(engine, "index_paths", targeted, raising=False)
        monkeypatch.setattr(
            engine,
            "index_project",
            lambda _project: (_ for _ in ()).throw(
                AssertionError("normal watcher event triggered full scan")
            ),
        )
        watch = watcher._ProjectWatch(str(tmp_path), _LOG)
        watch._pending.add(changed)

        watch._flush()

        assert calls == [(str(tmp_path.resolve()), {changed})]

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

        def indexed_names():
            return {s["name"] for s in engine.get_symbols(
                str(tmp_path), file=str(tmp_path / "a.py"))["symbols"]}

        # How long the debounce plus the reindex takes is a property of the machine,
        # so wait for the symbol to appear instead of guessing a duration.
        wait_until(lambda: "brand_new_sym" in indexed_names(), timeout=15.0,
                   message="the debounced flush never reindexed the edited file")
        assert "brand_new_sym" in indexed_names()

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
            time.sleep(0.02)  # spacing the edits is the point: real time has to pass
        wait_until(lambda: flushes, timeout=15.0,
                   message="the debounced flush never fired at all")
        # Nothing is enqueued after the burst, so no further flush can be armed: one
        # flush having happened is the whole claim.
        assert len(flushes) == 1, f"debounce should coalesce into 1 flush, got {len(flushes)}"
