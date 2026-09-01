"""What the filesystem watcher puts a watch on, and what it refuses to.

This exists because of a measurement. The watcher asked watchdog for
`recursive=True` over the repository root, which puts a watch on every directory
underneath -- `node_modules`, `.venv`, `build`, `.git`, all of it. On a tree shaped like
a real front end (1,317 directories, 22 of them source) that was **98.3% of the watches
spent on files this tool never reads**.

On Linux those are inotify descriptors against a cap that is per *user*, so exhausting
it breaks every editor and build tool on the machine rather than just this one. Anywhere
else it is an event storm on every install or build, waking a debounce timer that
re-arms and burns CPU for nothing.

The indexer already had the list of directories to skip. The watcher did not use it.
That is the same forgotten-fence failure this whole project is about, so the fix is one
list with two consumers, and these tests are what stop them drifting apart again.
"""
from __future__ import annotations

import logging
import os

import pytest

from codesextant import engine, watcher


def _tree(root, *, packages: int = 20, sources: int = 4) -> None:
    """A repository shaped like a real one: mostly dependency and build output."""
    for index in range(packages):
        for leaf in ("", "/lib", "/dist"):
            os.makedirs(root / "node_modules" / f"pkg{index}{leaf}", exist_ok=True)
    os.makedirs(root / ".venv" / "lib" / "site-packages", exist_ok=True)
    os.makedirs(root / "build" / "artifacts", exist_ok=True)
    os.makedirs(root / ".git" / "objects", exist_ok=True)
    for index in range(sources):
        package = root / "src" / f"feature{index}"
        os.makedirs(package, exist_ok=True)
        (package / "code.py").write_text("def f():\n    return 1\n", encoding="utf-8")


@pytest.fixture()
def watched(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "repo"
    root.mkdir()
    _tree(root)
    watch = watcher._ProjectWatch(str(root), logging.getLogger("test"))
    watch.start()
    yield root, watch
    watch.stop()


def _watch_count(watch) -> int:
    return len(watch._observer._handlers)


def test_dependency_and_build_directories_get_no_watch(watched):
    root, watch = watched
    every_directory = sum(1 for _ in os.walk(root))
    watching = _watch_count(watch)

    assert watching < every_directory / 4, (
        f"watching {watching} of {every_directory} directories -- the skip list is not "
        "being applied")
    # Positively: the source directories are all there.
    assert watching >= 1 + 1 + 4, "src, its children and the root must be watched"


def test_the_watcher_and_the_indexer_skip_the_same_directories(watched):
    """One list, two consumers. A copy is how they drifted apart the first time, so the
    test asserts the identity rather than the contents."""
    root, _watch = watched
    walked = set()
    for base, dirs, _files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in engine._SKIP_DIRS]
        walked.add(os.path.realpath(base))

    scheduled = {os.path.realpath(str(observed.path))
                 for observed in _watch._observer._handlers}
    assert scheduled == walked, (
        "the watcher is watching a different set of directories than the indexer reads")


def test_a_new_source_directory_is_picked_up(watched):
    """The one thing `recursive=True` gave for free. Without replacing it, a package
    created after startup would stay invisible until the next attach."""
    root, watch = watched
    before = _watch_count(watch)
    os.makedirs(root / "src" / "added_later", exist_ok=True)
    _wait_until(lambda: _watch_count(watch) > before)
    assert _watch_count(watch) == before + 1


def test_a_new_dependency_directory_is_still_refused(watched):
    root, watch = watched
    before = _watch_count(watch)
    os.makedirs(root / "node_modules" / "added_later", exist_ok=True)
    # Nothing to wait for; give the observer a chance to do the wrong thing.
    _wait_until(lambda: False, timeout=1.0, required=False)
    assert _watch_count(watch) == before


def test_an_enormous_tree_stops_rather_than_exhausting_a_system_limit(
        tmp_path, monkeypatch):
    """Past the ceiling the watcher stops adding and says so. Running a per-user inotify
    cap to zero breaks every other tool on the machine, which is a worse outcome than
    missing a file change."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    monkeypatch.setenv("CODESEXTANT_WATCH_MAX_DIRS", "5")
    root = tmp_path / "huge"
    root.mkdir()
    for index in range(40):
        os.makedirs(root / "src" / f"package{index}", exist_ok=True)

    watch = watcher._ProjectWatch(str(root), logging.getLogger("test"))
    try:
        watch.start()
        assert _watch_count(watch) <= 5
    finally:
        watch.stop()


def _wait_until(predicate, *, timeout: float = 5.0, required: bool = True) -> None:
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    if required:
        raise AssertionError("condition never became true")
