"""Lightweight project status queries that do not load the parser engine."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import time
from collections.abc import Callable

from . import cache_lease, storage


def git_head_sha(repo_path: str, *, timeout_sec: float = 5.0) -> str | None:
    """Read a repository's Git HEAD without opening the parsing stack."""
    if os.environ.get("CODESEXTANT_GIT_FRESHNESS_DISABLED", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return None
    try:
        kwargs = {
            "capture_output": True,
            "text": True,
            "timeout": max(0.05, float(timeout_sec)),
        }
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        result = subprocess.run(["git", "-C", repo_path, "rev-parse", "HEAD"], **kwargs)
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def status(
    path: str,
    *,
    check_freshness: bool = False,
    git_head_reader: Callable[[str], str | None] = git_head_sha,
    busy_timeout_ms: int | None = None,
    git_timeout_sec: float = 5.0,
) -> dict:
    """Return index state without importing tree-sitter, Jedi, or ranking code."""
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {
            "indexed": False,
            "project_key": storage.project_key(abs_path),
            "repo_path": abs_path,
            "db_file": str(db_file),
        }
    try:
        database_budget_sec = (
            None if busy_timeout_ms is None
            else max(0.0, float(busy_timeout_ms) / 1000.0))
        database_deadline = (
            None if database_budget_sec is None
            else time.monotonic() + database_budget_sec)
        with storage.ProjectStore.open_readonly(
            abs_path,
            busy_timeout_ms=busy_timeout_ms,
            lease_timeout_sec=database_budget_sec,
        ) as store:
            state = store.stats(deadline=database_deadline)
    except (sqlite3.DatabaseError, OSError, cache_lease.LeaseError) as exc:
        error_text = str(exc).lower()
        reason = (
            "database-busy"
            if (isinstance(exc, cache_lease.LeaseBusyError)
                or "locked" in error_text or "busy" in error_text)
            else "unavailable"
        )
        return {
            "indexed": True,
            "project_key": storage.project_key(abs_path),
            "repo_path": abs_path,
            "db_file": str(db_file),
            "partial": True,
            "index_status_error": reason,
        }
    state["indexed"] = True
    if check_freshness:
        indexed_sha = state.get("indexed_git_sha")
        if git_head_reader is git_head_sha:
            current_sha = git_head_reader(
                abs_path, timeout_sec=git_timeout_sec)
        else:
            current_sha = git_head_reader(abs_path)
        state["current_git_sha"] = current_sha
        if indexed_sha and current_sha:
            state["git_stale"] = indexed_sha != current_sha
        elif indexed_sha and not current_sha:
            state["git_stale"] = None
            state["git_note"] = (
                "git is currently unavailable, so freshness cannot be determined "
                "(the sha recorded at index time is still here)"
            )
        else:
            state["git_stale"] = False
            if not indexed_sha and current_sha:
                state["git_note"] = (
                    "this database recorded no git sha at index time; "
                    "reindex to enable freshness checking"
                )
    return state


def list_projects() -> dict:
    """Return the local project overview without importing the parser engine."""
    projects = storage.list_indexed_projects()
    return {
        "db_dir": str(storage.default_db_dir()),
        "count": sum(1 for project in projects if "error" not in project),
        "projects": projects,
    }
