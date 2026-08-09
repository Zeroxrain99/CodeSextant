"""Cross-process leases that keep live index caches out of garbage collection.

Reader concurrency is preserved with one short project gate and one uniquely
named, OS-locked holder file per open cache user. Garbage collection keeps the
gate for its whole delete operation and proceeds only after every holder file
is both structurally safe and provably unlocked. Process crashes leave marker
files behind, but the operating system releases their locks so a later collector
can reap them without trusting a PID or wall clock.
"""
from __future__ import annotations

import errno
import os
import re
import secrets
import stat
import threading
import time
from pathlib import Path

_LEASE_DIR = ".leases"
_PROJECT_KEY_RE = re.compile(r"[0-9a-f]{40}\Z")
_HOLDER_RE = re.compile(
    r"(?P<key>[0-9a-f]{40})\.holder\."
    r"(?P<pid>[0-9]+)\.(?P<thread>[0-9]+)\."
    r"(?P<nonce>[0-9a-f]{32})\.lock\Z"
)
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_DEFAULT_GATE_TIMEOUT_SEC = 5.0


class LeaseError(RuntimeError):
    """Base class for cache lease acquisition failures."""


class LeaseBusyError(LeaseError):
    """The short registration gate did not become available in time."""


class LeaseUnsafeError(LeaseError):
    """Lease state could not be proven to be a private regular file tree."""


def lease_root(home: str | Path) -> Path:
    """Return the lease directory path without creating or trusting it."""
    return Path(home) / _LEASE_DIR


def _default_home() -> Path:
    configured = os.environ.get("CODESEXTANT_HOME")
    return Path(configured) if configured else Path.home() / ".codesextant"


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _validate_directory(path: Path, *, label: str) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise LeaseUnsafeError(f"cannot inspect {label}") from exc
    if not stat.S_ISDIR(info.st_mode) or _is_reparse(info):
        raise LeaseUnsafeError(f"{label} is not a safe local directory")


def _prepare_root(home: str | Path | None) -> Path:
    state_home = Path(home) if home is not None else _default_home()
    try:
        state_home.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise LeaseUnsafeError("cannot create the cache home") from exc
    _validate_directory(state_home, label="cache home")
    root = lease_root(state_home)
    try:
        root.mkdir(mode=0o700, exist_ok=True)
    except OSError as exc:
        raise LeaseUnsafeError("cannot create the cache lease directory") from exc
    _validate_directory(root, label="cache lease directory")
    if root.parent.resolve(strict=False) != state_home.resolve(strict=False):
        raise LeaseUnsafeError("cache lease directory escaped its cache home")
    if os.name != "nt":
        try:
            state_home.chmod(0o700)
            root.chmod(0o700)
        except OSError as exc:
            raise LeaseUnsafeError("cannot make the cache lease directory private") from exc
    return root


def _project_key(value: str) -> str:
    key = str(value)
    if _PROJECT_KEY_RE.fullmatch(key) is None:
        raise ValueError("project_key must be exactly 40 lowercase hexadecimal characters")
    return key


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_nlink),
        int(info.st_size),
        int(info.st_mtime_ns),
    )


def _validate_lock_info(info: os.stat_result, *, label: str) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise LeaseUnsafeError(f"{label} is not a regular file")
    if _is_reparse(info):
        raise LeaseUnsafeError(f"{label} is a reparse point")
    if int(info.st_nlink) != 1:
        raise LeaseUnsafeError(f"{label} is hard linked")


def _open_lock_file(path: Path, *, exclusive_create: bool = False,
                    create: bool = True) -> int:
    flags = os.O_RDWR
    if exclusive_create:
        flags |= os.O_CREAT | os.O_EXCL
    elif create:
        flags |= os.O_CREAT
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise LeaseUnsafeError(f"cannot open cache lease file {path.name}") from exc
    try:
        _validate_open_path(descriptor, path)
        opened = os.fstat(descriptor)
        if opened.st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _validate_open_path(descriptor: int, path: Path) -> tuple[
        int, int, int, int, int, int]:
    try:
        opened = os.fstat(descriptor)
        listed = path.lstat()
    except OSError as exc:
        raise LeaseUnsafeError(
            f"cannot verify cache lease file {path.name}") from exc
    _validate_lock_info(opened, label=path.name)
    _validate_lock_info(listed, label=path.name)
    identity = _identity(opened)
    if identity != _identity(listed):
        raise LeaseUnsafeError(
            f"cache lease file changed while opening {path.name}")
    return identity


def _unlink_verified(path: Path, expected_identity: tuple[
        int, int, int, int, int, int]) -> None:
    try:
        listed = path.lstat()
    except OSError as exc:
        raise LeaseUnsafeError(
            f"cannot verify cache lease marker {path.name}") from exc
    _validate_lock_info(listed, label=path.name)
    if _identity(listed) != expected_identity:
        raise LeaseUnsafeError(
            f"cache lease marker changed before removal {path.name}")
    try:
        path.unlink()
    except OSError as exc:
        raise LeaseUnsafeError(
            f"cannot remove cache lease marker {path.name}") from exc


def _lock_once(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:  # pragma: no cover - exercised on Linux and macOS CI
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(descriptor: int) -> None:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:  # pragma: no cover - exercised on Linux and macOS CI
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError:
        pass


def _acquire(descriptor: int, *, timeout_sec: float) -> bool:
    deadline = time.monotonic() + max(0.0, float(timeout_sec))
    while True:
        try:
            _lock_once(descriptor)
            return True
        except OSError as exc:
            if exc.errno == errno.EINTR:
                continue
            contended = exc.errno in (
                errno.EACCES,
                errno.EAGAIN,
                getattr(errno, "EDEADLK", errno.EACCES),
            ) or getattr(exc, "winerror", None) in (33, 36)
            if not contended:
                raise LeaseUnsafeError(
                    "operating system cache lock failed") from exc
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)


def _gate_path(root: Path, project_key: str) -> Path:
    return root / f"{project_key}.gate.lock"


def _project_entries(root: Path, project_key: str) -> list[Path]:
    expected_gate = f"{project_key}.gate.lock"
    entries: list[Path] = []
    try:
        candidates = list(root.iterdir())
    except OSError as exc:
        raise LeaseUnsafeError("cannot scan the cache lease directory") from exc
    for candidate in candidates:
        if not candidate.name.startswith(f"{project_key}."):
            continue
        if candidate.name != expected_gate:
            match = _HOLDER_RE.fullmatch(candidate.name)
            if match is None or match.group("key") != project_key:
                raise LeaseUnsafeError(
                    "unrecognized cache lease marker for this project")
        try:
            info = candidate.lstat()
        except OSError as exc:
            raise LeaseUnsafeError("cannot inspect a cache lease marker") from exc
        _validate_lock_info(info, label=candidate.name)
        entries.append(candidate)
    return entries


def _unlocked_holder_identity(holder: Path) -> tuple[
        int, int, int, int, int, int] | None:
    """Return a stable identity only when the holder is provably unlocked."""
    descriptor = _open_lock_file(holder, create=False)
    locked = False
    try:
        locked = _acquire(descriptor, timeout_sec=0.0)
        if not locked:
            return None
        return _validate_open_path(descriptor, holder)
    finally:
        if locked:
            _unlock(descriptor)
        os.close(descriptor)


def _reap_unlocked_holders(entries: list[Path]) -> None:
    """Remove holder markers whose operating system locks are available."""
    for holder in entries:
        if _HOLDER_RE.fullmatch(holder.name) is None:
            continue
        holder_identity = _unlocked_holder_identity(holder)
        if holder_identity is not None:
            _unlink_verified(holder, holder_identity)


class ProjectLease:
    """A concurrent cache-user marker held until its SQLite work is closed."""

    def __init__(self, *, descriptor: int, marker: Path, gate: Path,
                 marker_identity: tuple[int, int, int, int, int, int]):
        self._descriptor = descriptor
        self.marker = marker
        self._gate = gate
        self._marker_identity = marker_identity
        self._closed = False
        self._close_lock = threading.Lock()

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            gate_descriptor: int | None = None
            gate_locked = False
            try:
                gate_descriptor = _open_lock_file(self._gate, create=False)
                gate_locked = _acquire(
                    gate_descriptor, timeout_sec=_DEFAULT_GATE_TIMEOUT_SEC)
                if gate_locked:
                    _validate_open_path(gate_descriptor, self._gate)
            except LeaseError:
                if gate_descriptor is not None:
                    if gate_locked:
                        _unlock(gate_descriptor)
                    os.close(gate_descriptor)
                gate_descriptor = None
                gate_locked = False
            try:
                _unlock(self._descriptor)
                os.close(self._descriptor)
                if gate_locked:
                    try:
                        _unlink_verified(
                            self.marker, self._marker_identity)
                    except LeaseUnsafeError:
                        pass
            finally:
                if gate_descriptor is not None:
                    if gate_locked:
                        _unlock(gate_descriptor)
                    os.close(gate_descriptor)

    def __enter__(self) -> ProjectLease:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


class ExclusiveProjectLease:
    """A project gate retained for the complete cache deletion transaction."""

    def __init__(self, descriptor: int):
        self._descriptor = descriptor
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _unlock(self._descriptor)
        os.close(self._descriptor)

    def __enter__(self) -> ExclusiveProjectLease:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def acquire_shared(project_key: str, *, home: str | Path | None = None,
                   timeout_sec: float = _DEFAULT_GATE_TIMEOUT_SEC) -> ProjectLease:
    """Register one concurrent cache user before it opens project artifacts."""
    key = _project_key(project_key)
    root = _prepare_root(home)
    gate = _gate_path(root, key)
    gate_descriptor = _open_lock_file(gate)
    try:
        gate_locked = _acquire(gate_descriptor, timeout_sec=timeout_sec)
    except BaseException:
        os.close(gate_descriptor)
        raise
    if not gate_locked:
        os.close(gate_descriptor)
        raise LeaseBusyError("cache lease registration gate is busy")
    marker: Path | None = None
    holder_descriptor: int | None = None
    try:
        _validate_open_path(gate_descriptor, gate)
        entries = _project_entries(root, key)
        _reap_unlocked_holders(entries)
        marker = root / (
            f"{key}.holder.{os.getpid()}.{threading.get_ident()}."
            f"{secrets.token_hex(16)}.lock"
        )
        holder_descriptor = _open_lock_file(marker, exclusive_create=True)
        if not _acquire(holder_descriptor, timeout_sec=0.0):
            raise LeaseUnsafeError("new cache holder marker could not be locked")
        marker_identity = _validate_open_path(holder_descriptor, marker)
        return ProjectLease(
            descriptor=holder_descriptor,
            marker=marker,
            gate=gate,
            marker_identity=marker_identity,
        )
    except BaseException:
        if holder_descriptor is not None:
            _unlock(holder_descriptor)
            os.close(holder_descriptor)
        if marker is not None:
            try:
                marker.unlink()
            except OSError:
                pass
        raise
    finally:
        _unlock(gate_descriptor)
        os.close(gate_descriptor)


def try_acquire_exclusive(
        project_key: str, *, home: str | Path | None = None,
) -> ExclusiveProjectLease | None:
    """Return a GC lease only when every holder is provably inactive.

    ``None`` means the project is active or a holder lock could not be proven
    stale. Structurally unsafe state raises ``LeaseUnsafeError`` so callers can
    distinguish a normal active skip from a fail-closed integrity error.
    """
    key = _project_key(project_key)
    root = _prepare_root(home)
    gate = _gate_path(root, key)
    gate_descriptor = _open_lock_file(gate)
    try:
        gate_locked = _acquire(gate_descriptor, timeout_sec=0.0)
    except BaseException:
        os.close(gate_descriptor)
        raise
    if not gate_locked:
        os.close(gate_descriptor)
        return None
    try:
        _validate_open_path(gate_descriptor, gate)
        entries = _project_entries(root, key)
        holders = [
            entry for entry in entries
            if _HOLDER_RE.fullmatch(entry.name) is not None
        ]
        stale: list[tuple[Path, tuple[int, int, int, int, int, int]]] = []
        for holder in holders:
            holder_identity = _unlocked_holder_identity(holder)
            if holder_identity is None:
                _unlock(gate_descriptor)
                os.close(gate_descriptor)
                return None
            stale.append((holder, holder_identity))
        for holder, holder_identity in stale:
            _unlink_verified(holder, holder_identity)
        return ExclusiveProjectLease(gate_descriptor)
    except BaseException:
        _unlock(gate_descriptor)
        os.close(gate_descriptor)
        raise
