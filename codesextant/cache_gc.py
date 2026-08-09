"""Event-driven inventory and garbage collection for project index caches.

Only exact SHA-1 project database names anchor a managed cache group. Unknown
files, daemon credentials, logs, and lock files are never candidates. Callers
invoke ``touch_project`` on real project activity and ``prune`` at a quiescent
lifecycle boundary. This module starts no threads, timers, or polling loops.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import stat
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from . import cache_lease, storage

_DEFAULT_MAX_BYTES = 10 * 1024 ** 3
_DEFAULT_TARGET_RATIO = 0.9
_DEFAULT_MISSING_GRACE_DAYS = 30.0
_DEFAULT_TOUCH_INTERVAL_SECONDS = 60.0
_PROJECT_DB_RE = re.compile(r"^(?P<key>[0-9a-f]{40})\.db$")
_SNAPSHOT_SUFFIX_RE = re.compile(
    r"^\.(?:symbols|map)-v[0-9]+\.json$")
_ACCESS_SUFFIX = ".access.json"
_ACCESS_FORMAT = 1
_MAX_ACCESS_SIDECAR_BYTES = 64 * 1024

_TOUCH_LOCK = threading.Lock()
_TOUCH_TIMES: dict[tuple[str, str], float] = {}


@dataclass(frozen=True)
class CachePolicy:
    """Validated cache retention policy resolved from the environment."""

    max_bytes: int
    target_ratio: float
    missing_grace_seconds: float
    touch_interval_seconds: float

    @property
    def target_bytes(self) -> int:
        return int(self.max_bytes * self.target_ratio)


@dataclass(frozen=True)
class _Artifact:
    path: Path
    name: str
    size: int
    kind: str
    modified_at: float = 0.0
    identity: tuple[int, int, int, int, int] | None = None


@dataclass(frozen=True)
class _ProjectRecord:
    project_key: str
    artifacts: tuple[_Artifact, ...]
    total_bytes: int
    last_access: float
    repo_state: str
    issues: tuple[dict, ...]
    access_source: str = "mtime"


def _finite_float(value: str | None, default: float, *, minimum: float,
                  maximum: float | None = None) -> float:
    try:
        parsed = float(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed) or parsed < minimum:
        return default
    if maximum is not None and parsed > maximum:
        return default
    return parsed


def _positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return parsed if 1 <= parsed <= (2 ** 63 - 1) else default


def policy_from_env() -> CachePolicy:
    """Return a safe retention policy without trusting malformed env values.

    Supported switches:

    * ``CODESEXTANT_CACHE_MAX_BYTES`` defaults to 10 GiB.
    * ``CODESEXTANT_CACHE_TARGET_RATIO`` defaults to 0.9.
    * ``CODESEXTANT_CACHE_MISSING_GRACE_DAYS`` defaults to 30 days.
    * ``CODESEXTANT_CACHE_TOUCH_INTERVAL_SEC`` defaults to 60 seconds.
    """
    max_bytes = _positive_int(
        os.environ.get("CODESEXTANT_CACHE_MAX_BYTES"), _DEFAULT_MAX_BYTES)
    target_ratio = _finite_float(
        os.environ.get("CODESEXTANT_CACHE_TARGET_RATIO"),
        _DEFAULT_TARGET_RATIO,
        minimum=0.001,
        maximum=1.0,
    )
    missing_days = _finite_float(
        os.environ.get("CODESEXTANT_CACHE_MISSING_GRACE_DAYS"),
        _DEFAULT_MISSING_GRACE_DAYS,
        minimum=0.0,
    )
    touch_interval = _finite_float(
        os.environ.get("CODESEXTANT_CACHE_TOUCH_INTERVAL_SEC"),
        _DEFAULT_TOUCH_INTERVAL_SECONDS,
        minimum=0.0,
    )
    return CachePolicy(
        max_bytes=max_bytes,
        target_ratio=target_ratio,
        missing_grace_seconds=missing_days * 86400.0,
        touch_interval_seconds=touch_interval,
    )


def _resolved_home() -> Path:
    return storage.default_db_dir().resolve(strict=False)


def _is_within_home(path: Path, home: Path) -> bool:
    """Reject targets whose resolved location escapes the configured cache home."""
    try:
        resolved_home = home.resolve(strict=False)
        resolved_target = path.resolve(strict=False)
        home_text = os.path.normcase(str(resolved_home))
        target_text = os.path.normcase(str(resolved_target))
        return (
            resolved_target != resolved_home
            and os.path.commonpath((home_text, target_text)) == home_text
        )
    except (OSError, RuntimeError, ValueError):
        return False


def _issue(project_key: str | None, artifact: str | None, operation: str,
           error: str) -> dict:
    return {
        "project_key": project_key,
        "artifact": artifact,
        "operation": operation,
        "error": error,
    }


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_mode),
    )


def _artifact_kind(anchor_name: str, candidate_name: str) -> str | None:
    if candidate_name == anchor_name:
        return "db"
    suffix = candidate_name[len(anchor_name):]
    if suffix == "-wal":
        return "wal"
    if suffix == "-shm":
        return "shm"
    if suffix == _ACCESS_SUFFIX:
        return "access"
    if _SNAPSHOT_SUFFIX_RE.fullmatch(suffix):
        return "snapshot"
    return None


def _read_access_sidecar(path: Path, project_key: str) -> tuple[
        str | None, float | None, dict | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = handle.read(_MAX_ACCESS_SIDECAR_BYTES + 1)
        if len(raw.encode("utf-8")) > _MAX_ACCESS_SIDECAR_BYTES:
            raise ValueError("sidecar-too-large")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("invalid-sidecar")
        repo_path = payload.get("repo_path")
        accessed_at = float(payload.get("accessed_at"))
        if (
            payload.get("format") != _ACCESS_FORMAT
            or payload.get("project_key") != project_key
            or not isinstance(repo_path, str)
            or not repo_path
            or storage.project_key(repo_path) != project_key
            or not math.isfinite(accessed_at)
            or accessed_at < 0
        ):
            raise ValueError("invalid-sidecar")
        return repo_path, accessed_at, None
    except FileNotFoundError:
        return None, None, None
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return None, None, _issue(
            project_key, path.name, "read-access", type(exc).__name__)


def _read_repo_path_from_db(path: Path, project_key: str) -> tuple[
        str | None, dict | None]:
    try:
        with cache_lease.acquire_shared(project_key, home=path.parent):
            uri = path.resolve(strict=True).as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=0.1)) as conn:
                conn.execute("PRAGMA query_only=1")
                conn.execute("PRAGMA busy_timeout=100")
                row = conn.execute(
                    "SELECT value FROM meta WHERE key='repo_path'"
                ).fetchone()
        repo_path = row[0] if row else None
        if (
            not isinstance(repo_path, str)
            or storage.project_key(repo_path) != project_key
        ):
            return None, _issue(
                project_key, path.name, "read-repo", "invalid-repo-metadata")
        return repo_path, None
    except (OSError, sqlite3.Error, cache_lease.LeaseError) as exc:
        return None, _issue(
            project_key, path.name, "read-repo", type(exc).__name__)


def _inventory_records() -> tuple[list[_ProjectRecord], list[dict]]:
    home = storage.default_db_dir()
    resolved_home = _resolved_home()
    if not home.exists():
        return [], []
    try:
        entries = list(home.iterdir())
    except OSError as exc:
        return [], [_issue(None, None, "scan", type(exc).__name__)]

    by_name = {entry.name: entry for entry in entries}
    anchors: list[tuple[str, Path]] = []
    issues: list[dict] = []
    for entry in entries:
        match = _PROJECT_DB_RE.fullmatch(entry.name)
        if match is None:
            continue
        project_key = match.group("key")
        if not _is_within_home(entry, resolved_home):
            issues.append(_issue(
                project_key, entry.name, "validate", "outside-cache-home"))
            continue
        try:
            mode = entry.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as exc:
            issues.append(_issue(
                project_key, entry.name, "stat", type(exc).__name__))
            continue
        if not stat.S_ISREG(mode):
            issues.append(_issue(
                project_key, entry.name, "stat", "not-a-file"))
            continue
        anchors.append((project_key, entry))

    records: list[_ProjectRecord] = []
    for project_key, anchor in sorted(anchors):
        project_issues: list[dict] = []
        artifacts: list[_Artifact] = []
        for name, candidate in by_name.items():
            if not name.startswith(anchor.name):
                continue
            kind = _artifact_kind(anchor.name, name)
            if kind is None:
                continue
            if not _is_within_home(candidate, resolved_home):
                project_issues.append(_issue(
                    project_key, name, "validate", "outside-cache-home"))
                continue
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                project_issues.append(_issue(
                    project_key, name, "stat", type(exc).__name__))
                continue
            if not stat.S_ISREG(info.st_mode):
                project_issues.append(_issue(
                    project_key, name, "stat", "not-a-file"))
                continue
            try:
                canonical = candidate.resolve(strict=True)
                canonical_info = canonical.lstat()
            except (FileNotFoundError, OSError, RuntimeError) as exc:
                project_issues.append(_issue(
                    project_key, name, "resolve", type(exc).__name__))
                continue
            if (
                not _is_within_home(canonical, resolved_home)
                or _file_identity(canonical_info) != _file_identity(info)
            ):
                project_issues.append(_issue(
                    project_key, name, "validate", "changed-during-inventory"))
                continue
            artifacts.append(_Artifact(
                path=canonical,
                name=name,
                size=max(0, int(info.st_size)),
                kind=kind,
                modified_at=float(info.st_mtime),
                identity=_file_identity(info),
            ))

        if not any(artifact.kind == "db" for artifact in artifacts):
            issues.extend(project_issues)
            continue
        artifacts.sort(key=lambda artifact: (artifact.kind != "db", artifact.name))
        sidecar = next(
            (artifact for artifact in artifacts if artifact.kind == "access"), None)
        repo_path: str | None = None
        accessed_at: float | None = None
        access_source = "mtime"
        if sidecar is not None:
            repo_path, accessed_at, access_issue = _read_access_sidecar(
                sidecar.path, project_key)
            if access_issue is not None:
                project_issues.append(access_issue)
            elif accessed_at is not None:
                access_source = "sidecar"
        if repo_path is None:
            db_artifact = next(
                artifact for artifact in artifacts if artifact.kind == "db")
            repo_path, db_issue = _read_repo_path_from_db(
                db_artifact.path, project_key)
            if db_issue is not None:
                project_issues.append(db_issue)
        last_access = (
            accessed_at if accessed_at is not None
            else max((artifact.modified_at for artifact in artifacts), default=0.0)
        )
        repo_state = (
            "unknown" if repo_path is None
            else "present" if os.path.isdir(repo_path)
            else "missing"
        )
        records.append(_ProjectRecord(
            project_key=project_key,
            artifacts=tuple(artifacts),
            total_bytes=sum(artifact.size for artifact in artifacts),
            last_access=last_access,
            repo_state=repo_state,
            issues=tuple(project_issues),
            access_source=access_source,
        ))
    return records, issues


def inventory() -> dict:
    """Return managed project cache groups without exposing repository paths."""
    records, global_issues = _inventory_records()
    projects = []
    issues = list(global_issues)
    for record in records:
        issues.extend(record.issues)
        projects.append({
            "project_key": record.project_key,
            "bytes": record.total_bytes,
            "last_access": record.last_access,
            "access_source": record.access_source,
            "repo_state": record.repo_state,
            "artifact_count": len(record.artifacts),
            "artifacts": [
                {
                    "name": artifact.name,
                    "bytes": artifact.size,
                    "kind": artifact.kind,
                }
                for artifact in record.artifacts
            ],
            "issues": list(record.issues),
        })
    return {
        "managed_bytes": sum(record.total_bytes for record in records),
        "project_count": len(records),
        "projects": projects,
        "issues": issues,
    }


def _write_access_sidecar(path: Path, payload: dict) -> None:
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def touch_project(repo_path: str) -> dict:
    """Record project use at most once per configured in-process interval."""
    absolute_repo = os.path.abspath(repo_path)
    project_key = storage.project_key(absolute_repo)
    resolved_home = _resolved_home()
    db_file = resolved_home / f"{project_key}.db"
    sidecar = Path(f"{db_file}{_ACCESS_SUFFIX}")
    if (
        not _is_within_home(db_file, resolved_home)
        or not _is_within_home(sidecar, resolved_home)
    ):
        return {
            "project_key": project_key,
            "touched": False,
            "reason": "unsafe-cache-path",
        }
    try:
        lease = cache_lease.acquire_shared(project_key, home=resolved_home)
    except cache_lease.LeaseError as exc:
        return {
            "project_key": project_key,
            "touched": False,
            "reason": "lease-unavailable",
            "error": type(exc).__name__,
        }

    with lease:
        try:
            if not stat.S_ISREG(db_file.lstat().st_mode):
                return {
                    "project_key": project_key,
                    "touched": False,
                    "reason": "not-indexed",
                }
        except FileNotFoundError:
            return {
                "project_key": project_key,
                "touched": False,
                "reason": "not-indexed",
            }
        except OSError:
            return {
                "project_key": project_key,
                "touched": False,
                "reason": "stat-failed",
            }

        policy = policy_from_env()
        now_monotonic = time.monotonic()
        throttle_key = (os.path.normcase(str(resolved_home)), project_key)
        with _TOUCH_LOCK:
            previous = _TOUCH_TIMES.get(throttle_key)
            if (
                previous is not None
                and now_monotonic - previous < policy.touch_interval_seconds
            ):
                return {
                    "project_key": project_key,
                    "touched": False,
                    "reason": "throttled",
                }
            _TOUCH_TIMES[throttle_key] = now_monotonic

        try:
            _write_access_sidecar(sidecar, {
                "format": _ACCESS_FORMAT,
                "project_key": project_key,
                "repo_path": absolute_repo,
                "accessed_at": time.time(),
            })
        except OSError as exc:
            with _TOUCH_LOCK:
                if _TOUCH_TIMES.get(throttle_key) == now_monotonic:
                    _TOUCH_TIMES.pop(throttle_key, None)
            return {
                "project_key": project_key,
                "touched": False,
                "reason": "write-failed",
                "error": type(exc).__name__,
            }
        return {"project_key": project_key, "touched": True}


def _validate_record(record: _ProjectRecord, home: Path) -> list[dict]:
    errors = []
    for artifact in record.artifacts:
        if (
            not _is_within_home(artifact.path, home)
            or artifact.path.parent.resolve(strict=False) != home
        ):
            errors.append(_issue(
                record.project_key,
                artifact.name,
                "validate",
                "outside-cache-home",
            ))
    return errors


def _freshness_errors(record: _ProjectRecord, home: Path) -> list[dict]:
    expected_names = {artifact.name for artifact in record.artifacts}
    anchor_name = f"{record.project_key}.db"
    try:
        current_names = {
            path.name for path in home.iterdir()
            if path.name.startswith(anchor_name)
            and _artifact_kind(anchor_name, path.name) is not None
        }
    except OSError as exc:
        return [_issue(
            record.project_key, None, "rescan", type(exc).__name__)]
    if current_names != expected_names:
        return [_issue(
            record.project_key, anchor_name, "rescan", "group-changed")]
    errors = []
    for artifact in record.artifacts:
        if artifact.identity is None:
            continue
        try:
            info = artifact.path.lstat()
        except (FileNotFoundError, OSError) as exc:
            errors.append(_issue(
                record.project_key, artifact.name, "restat", type(exc).__name__))
            continue
        if (
            not stat.S_ISREG(info.st_mode)
            or _file_identity(info) != artifact.identity
        ):
            errors.append(_issue(
                record.project_key,
                artifact.name,
                "restat",
                "changed-since-inventory",
            ))
    return errors


def _delete_record(record: _ProjectRecord, home: Path, *, dry_run: bool) -> tuple[
        dict, list[dict]]:
    validation_errors = _validate_record(record, home)
    base = {
        "project_key": record.project_key,
        "bytes_before": record.total_bytes,
        "bytes_reclaimed": 0,
        "artifacts_deleted": [],
    }
    if validation_errors:
        return {**base, "status": "failed"}, validation_errors
    freshness_errors = _freshness_errors(record, home)
    if freshness_errors:
        return {**base, "status": "failed"}, freshness_errors
    if dry_run:
        return {
            **base,
            "status": "planned",
            "bytes_planned": record.total_bytes,
            "artifacts_planned": [
                artifact.name for artifact in record.artifacts
            ],
        }, []

    reclaimed = 0
    deleted: list[str] = []
    errors: list[dict] = []
    deletion_rank = {"snapshot": 0, "wal": 0, "shm": 0, "access": 1, "db": 2}
    ordered = sorted(record.artifacts, key=lambda artifact: (
        deletion_rank.get(artifact.kind, 0), artifact.name))
    for artifact in ordered:
        if artifact.kind == "db":
            remaining_names = {
                candidate.name for candidate in ordered
                if candidate.name not in deleted
            }
            try:
                current_names = {
                    path.name for path in home.iterdir()
                    if path.name.startswith(f"{record.project_key}.db")
                    and _artifact_kind(
                        f"{record.project_key}.db", path.name) is not None
                }
            except OSError as exc:
                errors.append(_issue(
                    record.project_key, None, "rescan", type(exc).__name__))
                break
            if current_names != remaining_names:
                errors.append(_issue(
                    record.project_key,
                    artifact.name,
                    "rescan",
                    "group-changed",
                ))
                break
        if not _is_within_home(artifact.path, home):
            errors.append(_issue(
                record.project_key,
                artifact.name,
                "validate",
                "outside-cache-home",
            ))
            break
        if artifact.identity is not None:
            try:
                current_info = artifact.path.lstat()
            except (FileNotFoundError, OSError) as exc:
                errors.append(_issue(
                    record.project_key,
                    artifact.name,
                    "restat",
                    type(exc).__name__,
                ))
                break
            if (
                not stat.S_ISREG(current_info.st_mode)
                or _file_identity(current_info) != artifact.identity
            ):
                errors.append(_issue(
                    record.project_key,
                    artifact.name,
                    "restat",
                    "changed-since-inventory",
                ))
                break
        try:
            artifact.path.unlink()
        except FileNotFoundError:
            reclaimed += artifact.size
            deleted.append(artifact.name)
        except OSError as exc:
            errors.append(_issue(
                record.project_key,
                artifact.name,
                "delete",
                type(exc).__name__,
            ))
            break
        else:
            reclaimed += artifact.size
            deleted.append(artifact.name)
    status = (
        "deleted" if not errors
        else "partial" if deleted
        else "failed"
    )
    return {
        **base,
        "status": status,
        "bytes_reclaimed": reclaimed,
        "artifacts_deleted": deleted,
    }, errors


def _policy_report(policy: CachePolicy) -> dict:
    return {
        "max_bytes": policy.max_bytes,
        "target_ratio": policy.target_ratio,
        "target_bytes": policy.target_bytes,
        "missing_grace_seconds": policy.missing_grace_seconds,
        "touch_interval_seconds": policy.touch_interval_seconds,
    }


def prune(*, exclude_project_keys=(), dry_run: bool = False) -> dict:
    """Prune missing old groups, then inactive LRU groups under quota pressure.

    Exclusions apply to every deletion reason. Reports contain cache keys and
    artifact basenames, but never repository paths, credentials, or file data.
    """
    policy = policy_from_env()
    records, inventory_issues = _inventory_records()
    home = _resolved_home()
    excluded = sorted({str(key).lower() for key in exclude_project_keys})
    excluded_set = set(excluded)
    before_bytes = sum(record.total_bytes for record in records)
    projected_bytes = before_bytes
    actions: list[dict] = []
    errors = list(inventory_issues)
    for record in records:
        errors.extend(record.issues)
    attempted: set[str] = set()

    for record in records:
        if record.project_key in excluded_set or not record.issues:
            continue
        unsafe_lease = any(
            issue.get("error") == cache_lease.LeaseUnsafeError.__name__
            for issue in record.issues
        )
        actions.append({
            "project_key": record.project_key,
            "bytes_before": record.total_bytes,
            "bytes_reclaimed": 0,
            "artifacts_deleted": [],
            "status": "failed" if unsafe_lease else "skipped",
            "reason": (
                "unsafe-project-lease" if unsafe_lease
                else "inventory-issues"
            ),
        })
        attempted.add(record.project_key)

    def apply(record: _ProjectRecord, reason: str) -> None:
        nonlocal projected_bytes
        base = {
            "project_key": record.project_key,
            "bytes_before": record.total_bytes,
            "bytes_reclaimed": 0,
            "artifacts_deleted": [],
        }
        try:
            exclusive = cache_lease.try_acquire_exclusive(
                record.project_key, home=home)
        except cache_lease.LeaseUnsafeError as exc:
            actions.append({
                **base,
                "status": "failed",
                "reason": "unsafe-project-lease",
            })
            errors.append(_issue(
                record.project_key, None, "lease", type(exc).__name__))
            attempted.add(record.project_key)
            return
        if exclusive is None:
            actions.append({
                **base,
                "status": "skipped",
                "reason": "active-project-lease",
            })
            attempted.add(record.project_key)
            return
        with exclusive:
            action, action_errors = _delete_record(
                record, home, dry_run=bool(dry_run))
        action["reason"] = reason
        actions.append(action)
        errors.extend(action_errors)
        attempted.add(record.project_key)
        if action["status"] == "planned":
            projected_bytes = max(0, projected_bytes - record.total_bytes)
        else:
            projected_bytes = max(
                0, projected_bytes - int(action["bytes_reclaimed"]))

    cutoff = time.time() - policy.missing_grace_seconds
    missing_candidates = sorted(
        (
            record for record in records
            if record.project_key not in excluded_set
            and not record.issues
            and record.repo_state == "missing"
            and record.last_access <= cutoff
        ),
        key=lambda record: (record.last_access, record.project_key),
    )
    for record in missing_candidates:
        apply(record, "missing-repo")

    quota_triggered = projected_bytes > policy.max_bytes
    if quota_triggered:
        lru_candidates = sorted(
            (
                record for record in records
                if record.project_key not in excluded_set
                and record.project_key not in attempted
                and not record.issues
            ),
            key=lambda record: (record.last_access, record.project_key),
        )
        for record in lru_candidates:
            if projected_bytes <= policy.target_bytes:
                break
            apply(record, "quota-lru")

    if dry_run:
        after_bytes = before_bytes
        reclaimed_bytes = 0
    else:
        after_records, after_issues = _inventory_records()
        errors.extend(after_issues)
        after_bytes = sum(record.total_bytes for record in after_records)
        projected_bytes = after_bytes
        reclaimed_bytes = max(0, before_bytes - after_bytes)
    quota_limit = policy.target_bytes if quota_triggered else policy.max_bytes
    return {
        "dry_run": bool(dry_run),
        "policy": _policy_report(policy),
        "before_bytes": before_bytes,
        "after_bytes": after_bytes,
        "projected_after_bytes": projected_bytes,
        "reclaimed_bytes": reclaimed_bytes,
        "quota_triggered": quota_triggered,
        "quota_satisfied": projected_bytes <= quota_limit,
        "excluded_project_keys": excluded,
        "projects": actions,
        "errors": errors,
    }
