"""Lightweight project status queries that do not load the parser engine."""
from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

from . import storage


def git_head_sha(repo_path: str) -> str | None:
    """Read a repository's Git HEAD without opening the parsing stack."""
    if os.environ.get("CODESEXTANT_GIT_FRESHNESS_DISABLED", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return None
    try:
        kwargs = {"capture_output": True, "text": True, "timeout": 5}
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
    with storage.ProjectStore.open_readonly(abs_path) as store:
        state = store.stats()
    state["indexed"] = True
    if check_freshness:
        indexed_sha = state.get("indexed_git_sha")
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
