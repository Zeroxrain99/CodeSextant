"""What a working tree has actually changed, as files and line ranges.

preflight asks its three questions *before* an edit, from a name and an intention.
That is the half that has to happen early, and it is also the half with the least to
work with: there is no body to fingerprint, no diff to read, and it only runs at all if
the author remembers to ask.

This module is the input to the other half. After the edit there is a diff, and a diff
is not a guess: it names exactly which files changed and exactly which lines, so the
same three questions can be asked again with evidence instead of intent behind them.

Only the standard library and git.
"""
from __future__ import annotations

import os
import re
import subprocess

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
# Reading a diff is bounded by the change, not the repository -- that is the whole
# reason this is affordable to run on every edit. A change that is not bounded by
# anything is a different kind of event and is reported as one rather than analysed.
MAX_CHANGED_FILES = 200


def _git(root: str, *args: str) -> tuple[int, str]:
    try:
        done = subprocess.run(["git", "-C", root, *args], capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return done.returncode, done.stdout


def is_worktree(root: str) -> bool:
    code, out = _git(root, "rev-parse", "--is-inside-work-tree")
    return code == 0 and out.strip() == "true"


def _diff_args(base: str | None, staged: bool) -> list[str]:
    if staged:
        return ["diff", "--cached"]
    if base:
        # Three dots: what this branch added, not what the base gained meanwhile.
        # Diffing against the tip would blame the author for someone else's commits.
        return ["diff", f"{base}..."]
    return ["diff", "HEAD"]


def _pre_image_ref(base: str | None, staged: bool) -> str:
    """The revision the diff is measured *from*.

    It has to match `_diff_args` exactly or the two disagree about what "before"
    means: with a base the diff is three-dot, so the pre-image is the merge base and
    not the base tip, which is the whole point of using three dots there.
    """
    if staged:
        return "HEAD"
    return base + "..." if base else "HEAD"


def content_before(root: str, path: str, *, base: str | None = None,
                   staged: bool = False) -> str | None:
    """The file as it was before this change, or None if it did not exist then.

    `changed_files` says *that* a file changed and `changed_ranges` says where. Neither
    can answer what the change took **away**, because everything they read is the text
    that is still there. Reading the pre-image is the only way to see a fence that is
    now gone.
    """
    ref = _pre_image_ref(base, staged)
    if ref.endswith("..."):
        code, merge_base = _git(root, "merge-base", ref[:-3], "HEAD")
        if code != 0 or not merge_base.strip():
            return None
        ref = merge_base.strip()
    code, out = _git(root, "show", f"{ref}:{path}")
    return out if code == 0 else None


def changed_files(root: str, *, base: str | None = None,
                  staged: bool = False) -> dict[str, str] | None:
    """{relative path: status letter}, or None outside a Git worktree.

    Untracked files count as added when looking at the working tree: a new module
    nobody has staged is exactly the kind of thing that gets written twice.
    """
    if not is_worktree(root):
        return None
    code, out = _git(root, *_diff_args(base, staged), "--name-status", "-z")
    if code != 0:
        return None
    changed: dict[str, str] = {}
    fields = [f for f in out.split("\0") if f]
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if status.startswith(("R", "C")) and index + 1 < len(fields):
            # Rename and copy carry two paths; the destination is what exists now.
            changed[fields[index + 1].replace(os.sep, "/")] = status[0]
            index += 2
            continue
        if index < len(fields):
            changed[fields[index].replace(os.sep, "/")] = status[0]
            index += 1
    if not staged and base is None:
        code, out = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
        if code == 0:
            for path in out.split("\0"):
                if path:
                    changed.setdefault(path.replace(os.sep, "/"), "A")
    return changed


def changed_ranges(root: str, path: str, *, base: str | None = None,
                   staged: bool = False) -> dict[str, list[tuple[int, int]]]:
    """{"added": new-side ranges, "removed": old-side ranges} for one file.

    Two sides because the two questions need different ones. "Is this new code a copy
    of something?" is about lines that exist now. "Whose callers did I disturb?" is
    about the definitions that were there before.
    """
    code, out = _git(root, *_diff_args(base, staged), "--unified=0", "--", path)
    added: list[tuple[int, int]] = []
    removed: list[tuple[int, int]] = []
    if code != 0 or not out.strip():
        # Untracked: nothing to diff against, so every line is new.
        absolute = os.path.join(root, path)
        try:
            with open(absolute, encoding="utf-8", errors="replace") as handle:
                total = sum(1 for _ in handle)
        except OSError:
            return {"added": [], "removed": []}
        return {"added": [(1, max(total, 1))], "removed": []}
    for line in out.splitlines():
        match = _HUNK.match(line)
        if not match:
            continue
        old_start, old_len = int(match.group(1)), int(match.group(2) or 1)
        new_start, new_len = int(match.group(3)), int(match.group(4) or 1)
        if old_len:
            removed.append((old_start, old_start + old_len - 1))
        if new_len:
            added.append((new_start, new_start + new_len - 1))
    return {"added": added, "removed": removed}


def overlaps(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    """Whether [start, end] touches any span. Both ends inclusive."""
    return any(low <= end and start <= high for low, high in spans)
