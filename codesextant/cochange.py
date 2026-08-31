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
import re
import subprocess
import tempfile
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


def read_commits(repo_path: str, *, limit: int | None = None,
                 since: str | None = None) -> list[tuple[str, set[str]]] | None:
    """Each commit as (sha, changed paths), newest first. None outside a Git worktree.

    The sha is carried so the per-file symbol pass can join back onto the same commits
    and learn what else changed alongside a symbol.

    Merges are excluded: a merge commit lists every path both sides touched, which is the
    same false coupling a sweeping commit creates.
    """
    count = max_commits() if limit is None else limit
    # `since..HEAD` is what makes an update cost the new commits rather than the whole
    # history: the counts accumulate, so nothing already read is read again.
    span = [f"{since}..HEAD"] if since else []
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "log", f"--max-count={int(count)}",
             "--format=%H", "--name-only", "--no-merges", "--no-renames", *span],
            **_git_kwargs())
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    commits: list[tuple[str, set[str]]] = []
    sha: str | None = None
    current: set[str] | None = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) == 40 and all(ch in _HEX for ch in line):
            if current is not None and sha is not None:
                commits.append((sha, current))
            sha, current = line, set()
        elif current is not None:
            current.add(line)
    if current is not None and sha is not None:
        commits.append((sha, current))
    return commits


def is_ancestor(repo_path: str, sha: str) -> bool:
    """Whether ``sha`` is still on HEAD's history.

    Accumulated counts describe the commits reached from the sha they were last updated
    at. A rebase, a force-push or a branch switch can leave that sha off the current
    history, and `sha..HEAD` would then describe a different set of commits than the one
    the totals assume -- so the totals have to be rebuilt rather than added to.
    """
    if not sha:
        return False
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "merge-base", "--is-ancestor", sha, "HEAD"],
            **_git_kwargs(timeout=10.0))
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def tally(commits: list[tuple[str, set[str]]]) -> tuple[Counter, Counter]:
    """(changes per path, co-occurrences per unordered pair) for a set of commits.

    Counters rather than rules, because counters add and rules do not. Storing only the
    pairs that cleared the thresholds would make every new commit a reason to re-read the
    whole history, just to recover the ones that had not cleared them yet.
    """
    cap = max_commit_files()
    changes: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    for _sha, files in commits:
        if not 2 <= len(files) <= cap:
            continue
        ordered = sorted(files)
        for path in ordered:
            changes[path] += 1
        for index, left in enumerate(ordered):
            for right in ordered[index + 1:]:
                pairs[(left, right)] += 1
    return changes, pairs


def rules_from(changes, pairs) -> list[dict]:
    """Apply the support and confidence thresholds to accumulated counters.

    Applied here rather than baked into what is stored, so raising or lowering a
    threshold takes effect without re-reading any history.
    """
    floor_support = min_support()
    floor_confidence = min_confidence()
    rules: list[dict] = []
    for (left, right), support in pairs.items():
        if support < floor_support:
            continue
        # Both directions: a test ships with its module far more reliably than the
        # module drags the test along, and only one of those is worth saying.
        for path, companion in ((left, right), (right, left)):
            total = changes.get(path, 0)
            confidence = support / total if total else 0.0
            if confidence >= floor_confidence:
                rules.append({
                    "path": path, "companion": companion, "support": support,
                    "changes": total, "confidence": round(confidence, 4),
                })
    rules.sort(key=lambda r: (-r["confidence"], -r["support"], r["path"], r["companion"]))
    return rules


def mine(repo_path: str,
         *, commits: list[tuple[str, set[str]]] | None = None) -> dict:
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
    usable = [files for _sha, files in commits if 2 <= len(files) <= cap]
    changes, pairs = tally(commits)
    rules = rules_from(changes, pairs)
    return {
        "rules": rules,
        "stats": {
            "available": True,
            "commits_read": len(commits),
            "commits_used": len(usable),
            "commits_skipped_as_sweeping": sum(
                1 for _sha, files in commits if len(files) > cap),
            "max_commit_files": cap,
            "min_support": min_support(),
            "min_confidence": min_confidence(),
            "rules": len(rules),
        },
    }


# ── symbol-level coupling ──
#
# "engine.py changes with storage.py" is true and nearly useless on a file of two
# thousand lines. What a caller needs is the coupling of the thing they are about to
# touch. Reading full diffs for a whole repository costs about 50MB and two seconds per
# sixty commits here, so it is not something to do up front -- but preflight always asks
# about one file, so the diff is read for that file alone, which is a hundred times
# cheaper, and joined against the file-level pass to learn what changed alongside.
#
# Attribution comes from the name Git already puts in each hunk header. Git only writes
# a useful one when a diff driver is configured for the language, which most repositories
# have not done, so a generated attributes file supplies the mapping for the languages
# Git has built-in drivers for. It is passed as core.attributesFile, the lowest-priority
# source, so a repository that configures its own driver keeps it and nothing on disk is
# modified.
#
# The heuristic reports the nearest preceding definition, which mis-attributes a change
# that falls outside every definition -- a module-level constant is credited to the
# function above it. The definition-shaped filter below rejects the clearest cases
# (imports, plain assignments); the rest is why symbol-level rules supplement the
# file-level ones rather than replacing them.

_GIT_DIFF_DRIVERS = {
    ".py": "python", ".rb": "ruby", ".php": "php", ".java": "java", ".cs": "csharp",
    ".go": "golang", ".rs": "rust", ".kt": "kotlin", ".kts": "kotlin", ".sh": "bash",
    ".c": "cpp", ".h": "cpp", ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp",
    ".m": "objc", ".pl": "perl", ".pm": "perl", ".ex": "elixir", ".exs": "elixir",
}

# A hunk header: @@ -a,b +c,d @@ trailing context
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@ ?(.*)$")
# Contexts that introduce a definition. Anything else -- an import block, a bare
# assignment -- means the hunk fell outside every definition and is left unattributed.
_DEFINITION_RE = re.compile(
    r"^\s*(?:@|export\s+|public\s+|private\s+|protected\s+|internal\s+|static\s+"
    r"|final\s+|abstract\s+|open\s+|suspend\s+|async\s+|pub\s+|const\s+)*"
    r"(?:def|class|func|function|fn|sub|struct|impl|interface|trait|type|module|object)\b")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DEFINITION_KEYWORDS = frozenset({
    "def", "class", "func", "function", "fn", "sub", "struct", "impl", "interface",
    "trait", "type", "module", "object", "async", "export", "public", "private",
    "protected", "internal", "static", "final", "abstract", "open", "suspend", "pub",
    "const", "var", "let",
})

_ATTRIBUTES_PATH: str | None = None


def _diff_attributes_file() -> str:
    """A generated attributes file naming Git's built-in diff driver per extension.

    Written once per process into a temporary directory. Git reads core.attributesFile
    only after the repository's own .gitattributes, so a project that already configures
    a driver is left alone.
    """
    global _ATTRIBUTES_PATH
    if _ATTRIBUTES_PATH and os.path.exists(_ATTRIBUTES_PATH):
        return _ATTRIBUTES_PATH
    directory = tempfile.mkdtemp(prefix="codesextant-attrs-")
    path = os.path.join(directory, "attributes")
    with open(path, "w", encoding="utf-8") as handle:
        for extension, driver in sorted(_GIT_DIFF_DRIVERS.items()):
            handle.write(f"*{extension} diff={driver}\n")
    _ATTRIBUTES_PATH = path
    return path


def _context_symbol(context: str) -> str | None:
    """The defined name in a hunk's trailing context, or None if it names no definition."""
    context = context.strip()
    if not context or not _DEFINITION_RE.match(context):
        return None
    for token in _IDENT_RE.findall(context):
        if token not in _DEFINITION_KEYWORDS:
            return token
    return None


def read_symbol_commits(repo_path: str, rel_path: str,
                        *, limit: int | None = None) -> dict[str, set[str]] | None:
    """{commit sha: symbols of ``rel_path`` it touched}. None outside a Git worktree.

    Output is consumed as it streams. One file's history is small, but a generated or
    vendored file can be enormous, and holding a diff in memory to count its hunk
    headers would be the kind of waste this tool exists to find.
    """
    count = max_commits() if limit is None else limit
    command = [
        "git", "-c", f"core.attributesFile={_diff_attributes_file()}",
        "-C", repo_path, "log", f"--max-count={int(count)}",
        "--format=%x00%H", "--unified=0", "--no-merges", "--no-renames",
        "--no-color", "--", rel_path,
    ]
    creationflags = {"creationflags": 0x08000000} if os.name == "nt" else {}
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, errors="replace", **creationflags)
    except (OSError, subprocess.SubprocessError):
        return None

    touched: dict[str, set[str]] = {}
    sha: str | None = None
    try:
        for line in process.stdout:
            if line.startswith("\x00"):
                sha = line[1:].strip() or None
                if sha:
                    touched.setdefault(sha, set())
            elif sha and line.startswith("@@"):
                match = _HUNK_RE.match(line.rstrip("\n"))
                if match:
                    name = _context_symbol(match.group(2))
                    if name:
                        touched[sha].add(name)
    finally:
        if process.stdout is not None:
            process.stdout.close()
        process.wait()
    if process.returncode != 0:
        return None
    return touched


def mine_symbols(repo_path: str, rel_path: str,
                 commits: list[tuple[str, set[str]]] | None = None) -> dict:
    """Co-change rules keyed by a symbol of ``rel_path`` rather than the whole file.

    The companion side stays a file. Narrowing the question is what matters -- "changing
    this function" instead of "changing this two-thousand-line module" -- and keeping the
    answer a file gives the rule enough support to clear the thresholds, which
    symbol-to-symbol pairs almost never do outside a long history.

    Returns {"rules": [...], "stats": {...}}; rules are {symbol, companion, support,
    changes, confidence}.
    """
    if commits is None:
        commits = read_commits(repo_path)
    if commits is None:
        return {"rules": [], "stats": {"available": False,
                                       "reason": "not a Git worktree, or Git is unavailable"}}
    touched = read_symbol_commits(repo_path, rel_path)
    if touched is None:
        return {"rules": [], "stats": {"available": False,
                                       "reason": f"no diff history for {rel_path}"}}

    cap = max_commit_files()
    files_by_sha = {sha: files for sha, files in commits if 2 <= len(files) <= cap}
    changes: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    used = 0
    for sha, symbols in touched.items():
        files = files_by_sha.get(sha)
        if not files or not symbols:
            continue
        used += 1
        companions = files - {rel_path}
        for symbol in symbols:
            changes[symbol] += 1
            for companion in companions:
                pairs[(symbol, companion)] += 1

    floor_support = min_support()
    floor_confidence = min_confidence()
    rules = []
    for (symbol, companion), support in pairs.items():
        if support < floor_support:
            continue
        total = changes[symbol]
        confidence = support / total if total else 0.0
        if confidence >= floor_confidence:
            rules.append({"symbol": symbol, "companion": companion,
                          "support": support, "changes": total,
                          "confidence": round(confidence, 4)})
    rules.sort(key=lambda r: (-r["confidence"], -r["support"], r["symbol"], r["companion"]))
    return {
        "rules": rules,
        "stats": {"available": True, "path": rel_path, "commits_used": used,
                  "symbols_seen": len(changes), "rules": len(rules)},
    }
