"""Mine "if you change this, you usually change that" from version-control history.

Some obligations are not in the code. Bumping ``__version__`` means editing
``pyproject.toml``; adding a route means adding it to the allowlist and to the routing
test; adding a language means adding a fixture. Nothing in the source says so, and a
reader who does not already know cannot find out. They are learned, and then forgotten,
one incident at a time.

Version control does know. Two files that keep appearing in the same commit are coupled
whether or not anything imports anything, so the obligation can be recovered from history
instead of written down by hand and remembered.

This is the association-rule form of that idea, kept deliberately small:

  support(A→B)    commits that changed both
  confidence(A→B) support / commits that changed A -- "when A changes, how often does B"

Three things decide whether the output is signal or noise:

* **Sweeping commits are excluded.** A commit touching 250 files (a reformat, a license
  header, a bulk rename) couples all 250 to each other and would drown every real pair.
  Only commits within ``CODESEXTANT_COCHANGE_MAX_COMMIT_FILES`` count.
* **Confidence is directional.** A test file almost always ships with its module, while
  the module often changes alone. A→B and B→A are different rules and both are kept.
* **Support has a floor.** Two files that changed together once are a coincidence, and
  presenting a coincidence as an obligation is how a tool teaches people to ignore it.

The rules are advice, not law: history describes what people did, which is not always
what they should have done. A rule with 100% confidence over five commits is still five
commits.
"""
from __future__ import annotations

import os
import subprocess
from collections import Counter

_HEX = frozenset("0123456789abcdef")


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
        return value if value > 0 else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except ValueError:
        return default


def max_commit_files() -> int:
    """Largest commit still treated as evidence of coupling."""
    return _env_int("CODESEXTANT_COCHANGE_MAX_COMMIT_FILES", 25)


def max_commits() -> int:
    """How far back to read. Old history describes a codebase that no longer exists."""
    return _env_int("CODESEXTANT_COCHANGE_MAX_COMMITS", 2000)


def min_support() -> int:
    """Commits a pair must share before it is called a rule rather than a coincidence."""
    return _env_int("CODESEXTANT_COCHANGE_MIN_SUPPORT", 3)


def min_confidence() -> float:
    """How often B must follow A before the pair is worth interrupting someone over."""
    return _env_float("CODESEXTANT_COCHANGE_MIN_CONFIDENCE", 0.5)


def enabled() -> bool:
    return os.environ.get("CODESEXTANT_COCHANGE_DISABLED", "").lower() not in (
        "1", "true", "yes", "on")


def _git_kwargs(timeout: float = 30.0) -> dict:
    kwargs: dict = {"capture_output": True, "text": True, "timeout": timeout,
                    "errors": "replace"}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return kwargs


def read_commits(repo_path: str, *, limit: int | None = None) -> list[set[str]] | None:
    """Each commit's changed paths, newest first. None outside a Git worktree.

    Merges are excluded: a merge commit lists every path both sides touched, which is the
    same false coupling a sweeping commit creates.
    """
    count = max_commits() if limit is None else limit
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "log", f"--max-count={int(count)}",
             "--format=%H", "--name-only", "--no-merges", "--no-renames"],
            **_git_kwargs())
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    commits: list[set[str]] = []
    current: set[str] | None = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) == 40 and all(ch in _HEX for ch in line):
            if current is not None:
                commits.append(current)
            current = set()
        elif current is not None:
            current.add(line)
    if current is not None:
        commits.append(current)
    return commits


def mine(repo_path: str, *, commits: list[set[str]] | None = None) -> dict:
    """Derive co-change rules for one repository.

    Returns {"rules": [...], "stats": {...}}. ``rules`` are dicts of
    {path, companion, support, changes, confidence}, strongest first, with paths
    repository-relative exactly as Git reports them.
    """
    if commits is None:
        commits = read_commits(repo_path)
    if commits is None:
        return {"rules": [], "stats": {"available": False,
                                       "reason": "not a Git worktree, or Git is unavailable"}}

    cap = max_commit_files()
    usable = [c for c in commits if 2 <= len(c) <= cap]
    changes: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    for files in usable:
        ordered = sorted(files)
        for path in ordered:
            changes[path] += 1
        for i, left in enumerate(ordered):
            for right in ordered[i + 1:]:
                pairs[(left, right)] += 1

    floor_support = min_support()
    floor_confidence = min_confidence()
    rules: list[dict] = []
    for (left, right), support in pairs.items():
        if support < floor_support:
            continue
        # Both directions: a test ships with its module far more reliably than the
        # module drags the test along, and only one of those is worth saying.
        for path, companion in ((left, right), (right, left)):
            total = changes[path]
            confidence = support / total if total else 0.0
            if confidence >= floor_confidence:
                rules.append({
                    "path": path, "companion": companion, "support": support,
                    "changes": total, "confidence": round(confidence, 4),
                })
    rules.sort(key=lambda r: (-r["confidence"], -r["support"], r["path"], r["companion"]))
    return {
        "rules": rules,
        "stats": {
            "available": True,
            "commits_read": len(commits),
            "commits_used": len(usable),
            "commits_skipped_as_sweeping": sum(1 for c in commits if len(c) > cap),
            "max_commit_files": cap,
            "min_support": floor_support,
            "min_confidence": floor_confidence,
            "rules": len(rules),
        },
    }
