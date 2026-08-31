"""Repositories to evaluate against, and their history in evaluation order.

CodeSextant's own history is deliberately *not* the primary corpus. Most of it was
written while building the thing being measured, and its recent commits were shaped
by preflight telling the author what to change -- evaluating the tool on those would
be measuring its own advice coming back. The external repositories here were written
by people who have never heard of it.
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import cochange  # noqa: E402

# Chosen before any result was seen: three long-lived Python projects of different
# shapes and team sizes. Picking them afterwards would make every number a selection.
EXTERNAL = (
    ("requests", "https://github.com/psf/requests.git"),
    ("click", "https://github.com/pallets/click.git"),
    ("tqdm", "https://github.com/tqdm/tqdm.git"),
)

# A third set, for Phase E only, chosen and written down before a single commit in any
# of them was read -- the same discipline that makes HELD_OUT worth quoting. Every rule
# in this repository was derived on EXTERNAL and confirmed on HELD_OUT, so both have been
# looked at; a prevention experiment run on either would be measuring a tool against
# repositories that shaped it.
#
# Chosen for the three shapes the existing corpus does not have, each named with what it
# is expected to stress:
#
#   flask     a framework rather than a library: blueprints, extension points and
#             application factories, so "changing A" reaches through registration rather
#             than through a call.
#   pytest    a plugin architecture -- hooks resolved at runtime by name. This is the
#             jinja failure mode on purpose: exp2 and exp9 both degrade where dispatch is
#             indirect, and a prevention set that avoided it would flatter the tool.
#   alembic   migrations and schema constraints. exp10 found no `.sql` file anywhere in
#             the other six repositories, which is why roadmap C4 is blocked; this is the
#             corpus that unblocks it.
PREVENTION = (
    ("flask", "https://github.com/pallets/flask.git"),
    ("pytest", "https://github.com/pytest-dev/pytest.git"),
    ("alembic", "https://github.com/sqlalchemy/alembic.git"),
)


def corpus_root() -> str:
    return os.environ.get(
        "CODESEXTANT_CORPUS",
        os.path.join(os.path.expanduser("~"), ".cache", "codesextant-corpus"))


def ensure(name: str, url: str) -> str:
    """Clone if absent. Blobless: history and trees are all the mining reads."""
    root = corpus_root()
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, name)
    if not os.path.isdir(os.path.join(path, ".git")):
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", url, path],
                       check=True)
    return path


def history(repo_path: str, *, limit: int | None = None) -> list[tuple[str, set[str]]]:
    """Commits oldest first, read through the shipped reader.

    Oldest first because the evaluation is prequential: every prediction must be made
    from a state that contains only what happened before it. Reading the shipped
    reader rather than a local reimplementation means merge handling and path
    normalization are the ones that ship.
    """
    commits = cochange.read_commits(repo_path, limit=limit)
    if commits is None:
        raise RuntimeError(f"{repo_path} is not a Git worktree")
    return list(reversed(commits))
