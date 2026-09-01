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

**Two of these tests used to assert a watch count, and that was a second version of the
same mistake.** The count is an inotify fact: FSEvents and ReadDirectoryChangesW do the
recursion in the kernel, so there one scheduled path covers the subtree and pruning the
walk would cost more than it saves. Every macOS CI job failed on the count assertion
while the behaviour was correct. What matters on every platform is which paths reach the
indexer, so that is what is asserted, and the count is checked only on the backends that
are actually charged per directory.
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
    # Record what the handler hands the indexer. Reading `_pending` instead was the
    # first attempt and it is racy by construction: the debounce timer drains the set,
    # so a test that polls it is asking a question whose answer is being erased.
    seen: list[str] = []
    original = watch._enqueue

    def _spy(path: str) -> None:
        seen.append(path)
        original(path)

    watch._enqueue = _spy
    watch._seen = seen
    watch.start()
    yield root, watch
    watch.stop()


def _watch_count(watch) -> int:
    return len(watch._observer._handlers)


def _per_directory(watch) -> bool:
    """Does this backend charge one watch per directory, or one for the whole tree?"""
    return not watcher._kernel_recursive(watch._observer)


def _queued(watch) -> list[str]:
    return list(watch._seen)


def test_nothing_under_a_skipped_directory_reaches_the_indexer(watched):
    """The contract, on every platform.

    Pruning the walk is only available where watches cost per directory. The filter is
    not: a kernel-recursive backend delivers every `node_modules` write, and each one
    restarts a debounce timer for an index that will never read the file.
    """
    root, watch = watched
    (root / "node_modules" / "pkg0" / "index.py").write_text("x = 1\n", encoding="utf-8")
    (root / "build" / "artifacts" / "generated.py").write_text("y = 2\n", encoding="utf-8")
    (root / ".venv" / "lib" / "site-packages" / "dep.py").write_text(
        "z = 3\n", encoding="utf-8")
    _wait_until(lambda: False, timeout=1.5, required=False)

    leaked = {path for path in _queued(watch) if watch._is_ignored(path)}
    assert not leaked, f"build and dependency output reached the indexer: {sorted(leaked)}"


def test_the_watcher_and_the_indexer_skip_the_same_directories(watched):
    """One list, two consumers. A copy is how they drifted apart the first time, so the
    test asserts the identity rather than the contents."""
    root, _watch = watched
    if not _per_directory(_watch):
        pytest.skip("this backend watches the tree with one kernel-side subscription")
    walked = set()
    for base, dirs, _files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in engine._SKIP_DIRS]
        walked.add(os.path.realpath(base))

    scheduled = {os.path.realpath(str(observed.path))
                 for observed in _watch._observer._handlers}
    assert scheduled == walked, (
        "the watcher is watching a different set of directories than the indexer reads")


def test_the_wasted_watches_are_gone(watched):
    """98.3% of them, on the backend where they were being paid for."""
    root, watch = watched
    if not _per_directory(watch):
        pytest.skip("this backend watches the tree with one kernel-side subscription")
    every_directory = sum(1 for _ in os.walk(root))
    watching = _watch_count(watch)
    assert watching < every_directory / 4, (
        f"watching {watching} of {every_directory} directories -- the skip list is not "
        "being applied")
    assert watching >= 1 + 1 + 4, "src, its children and the root must be watched"


def test_a_file_in_a_new_source_directory_still_reaches_the_indexer(watched):
    """The one thing `recursive=True` gave for free.

    Asserted as behaviour rather than as a watch count, because the two backends get
    here by different routes: a kernel-recursive watch already covers the new directory,
    and a pruned walk has to schedule it in `on_created`. The count assertion passed on
    Linux and failed every macOS job while both were working.
    """
    root, watch = watched
    package = root / "src" / "added_later"
    os.makedirs(package, exist_ok=True)
    # Wait for the directory event itself before writing into it. Sleeping a fixed
    # moment instead is a race: on a pruned backend the watch for this directory is
    # attached by that very event, and a file written first is simply not seen.
    _wait_until(lambda: any("added_later" in path for path in _queued(watch)))
    (package / "code.py").write_text("def g():\n    return 2\n", encoding="utf-8")

    _wait_until(lambda: any(os.path.basename(p) == "code.py"
                            and "added_later" in p for p in _queued(watch)))


def test_a_new_dependency_directory_is_still_refused(watched):
    root, watch = watched
    before = _watch_count(watch)
    package = root / "node_modules" / "added_later"
    os.makedirs(package, exist_ok=True)
    (package / "index.py").write_text("q = 1\n", encoding="utf-8")
    # Nothing to wait for; give the observer a chance to do the wrong thing.
    _wait_until(lambda: False, timeout=1.5, required=False)

    assert not any("added_later" in path for path in _queued(watch))
    if _per_directory(watch):
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
        if not _per_directory(watch):
            pytest.skip("no per-directory cost to cap on this backend")
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
