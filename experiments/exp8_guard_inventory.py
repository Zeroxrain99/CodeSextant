"""Can the guards be found at all, and do they carry their own reasons?

The failure this asks about is the second of the three the tool exists for, sharpened.
Not "the change forgot its test" but: *a guard the author wrote themselves, months ago,
blocks them now; they do not remember it exists, cannot see why it is there, and the
cheapest way out looks like deleting it.* A registry of guards is the obvious answer and
the obvious answer has failed before -- ADRs and feature-flag inventories are both
hand-maintained, and both go stale for exactly the reason the registry was wanted.

So before designing anything, two questions decide the shape of everything after, and
both are cheap:

1. **How many guards are there?** An index over forty of them per project is worth
   reading; an index over three thousand is a second codebase. Density, per kind, per
   thousand lines.
2. **Where does the reason live?** Progressive disclosure needs a middle layer to
   disclose. If four guards in five carry nothing but a name, the middle layer is empty
   and the design has to get the reason from somewhere else -- which for this tool means
   the commit that introduced the line, since it already mines history.

What counts as a guard, stated up front because the number means nothing without it:

    test        a test function -- the fence that fails the build
    assert      an assert statement inside library code
    raise       a guard clause: a raise reached only through a condition
    allowlist   a module-level collection something has to be added to
    threshold   a module-level numeric constant: a limit, budget, timeout, cap
    env_switch  an environment variable read: the runtime valve

Rationale is looked for in the four places it can be, in the order a reader would find
it: the definition's own docstring, a comment sitting directly above it, the message
carried by the assert or raise itself, and -- only when none of those exist -- the
message of the commit that introduced the line.

Read with ``ast`` rather than through the shipped extractors on purpose. This is a
feasibility probe, and what it should report is the *ceiling*: what is in the source at
all, not what a particular extractor currently reaches. A shipped version would use
tree-sitter and cover the other twelve languages; if the ceiling is not there, there is
nothing to build with either.

    python -m experiments.exp8_guard_inventory
    python -m experiments.exp8_guard_inventory --repo . --blame-sample 300
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import references  # noqa: E402
from experiments import corpus  # noqa: E402

KINDS = ("test", "assert", "raise", "allowlist", "threshold", "env_switch")
SOURCES = ("docstring", "comment", "message", "commit", "none")

# A module-level collection whose name says something has to be added to it. These are
# the ones that block a newcomer silently: the thing works everywhere except the one
# place that keeps a list of the things that are allowed to work.
_LIST_NAME = re.compile(
    r"(ALLOW|DENY|BLOCK|VALID|INVALID|SUPPORTED|KNOWN|SKIP|EXCLUDE|IGNORE|SAFE|"
    r"PERMITTED|WHITELIST|BLACKLIST|EXEMPT|REGISTERED|HANDLERS|_TYPES|_KINDS|_NAMES)",
    re.IGNORECASE)
# A module-level number that decides whether something is refused.
_LIMIT_NAME = re.compile(
    r"(MAX|MIN|LIMIT|TIMEOUT|BUDGET|CAP|THRESHOLD|RETRIES|INTERVAL|SIZE|COUNT|"
    r"DEFAULT|WINDOW|DEPTH)", re.IGNORECASE)
_WHY = re.compile(
    r"\b(because|so that|to avoid|to prevent|otherwise|would break|used to|"
    r"regression|do not remove|don't remove|deliberate|on purpose|intentional)\b",
    re.IGNORECASE)


def _is_test_file(relative: str) -> bool:
    base = os.path.basename(relative)
    return (base.startswith("test_") or base.endswith("_test.py")
            or "/tests/" in f"/{relative}" or relative.startswith("test/"))


class Guard:
    __slots__ = ("kind", "path", "line", "name", "source", "why")

    def __init__(self, kind, path, line, name, source, why):
        self.kind = kind
        self.path = path
        self.line = line
        self.name = name
        self.source = source
        self.why = why


def _comment_above(lines: list[str], line: int) -> str:
    """The comment block sitting directly above a definition, if there is one.

    Directly above and nothing between: a comment two blank lines up is describing
    something else, and counting it would inflate the one number this probe exists to
    report honestly.
    """
    collected = []
    index = line - 2  # line is 1-based and points at the definition itself
    while index >= 0:
        text = lines[index].strip()
        if text.startswith("#"):
            collected.append(text.lstrip("#").strip())
            index -= 1
            continue
        break
    return " ".join(reversed(collected))


def _literal_message(node) -> str:
    """The human-readable message an assert or raise carries, if any."""
    if isinstance(node, ast.Assert) and node.msg is not None:
        if isinstance(node.msg, ast.Constant) and isinstance(node.msg.value, str):
            return node.msg.value
        return "<expression>"
    if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
        for argument in node.exc.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                return argument.value
            if isinstance(argument, ast.JoinedStr):
                return "".join(part.value for part in argument.values
                               if isinstance(part, ast.Constant)
                               and isinstance(part.value, str))
    return ""


def _collect(tree: ast.Module, relative: str, lines: list[str]) -> list[Guard]:
    guards: list[Guard] = []
    test_file = _is_test_file(relative)

    def rationale(node, message: str = "") -> tuple[str, str]:
        doc = ast.get_docstring(node) if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None
        if doc and doc.strip():
            return "docstring", doc.strip().splitlines()[0]
        above = _comment_above(lines, node.lineno)
        if above:
            return "comment", above
        if message:
            return "message", message
        return "none", ""

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if test_file and node.name.startswith("test"):
                source, why = rationale(node)
                guards.append(Guard("test", relative, node.lineno, node.name, source, why))
        elif isinstance(node, ast.Assert) and not test_file:
            # Asserts inside tests are the test, already counted above; asserts in
            # library code are a separate fence with a separate failure mode.
            message = _literal_message(node)
            source, why = rationale(node, message)
            guards.append(Guard("assert", relative, node.lineno, "", source, why))
        elif isinstance(node, ast.Raise) and not test_file:
            message = _literal_message(node)
            if not message:
                continue  # a bare re-raise is not a guard, it is plumbing
            source, why = rationale(node, message)
            guards.append(Guard("raise", relative, node.lineno, "", source, why))

    for node in tree.body:  # module level only: these are the ones you have to update
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            name = target.id
            if isinstance(value, (ast.Set, ast.Tuple, ast.List, ast.Dict)) or (
                    isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                    and value.func.id in ("frozenset", "set", "tuple")):
                size = len(getattr(value, "elts", None) or getattr(value, "keys", None)
                           or getattr(value, "args", None) or ())
                if _LIST_NAME.search(name) and size >= 2:
                    source, why = rationale(node)
                    guards.append(Guard("allowlist", relative, node.lineno, name,
                                        source, why))
            elif (isinstance(value, ast.Constant)
                  and isinstance(value.value, (int, float))
                  and not isinstance(value.value, bool)
                  and name.isupper() and _LIMIT_NAME.search(name)):
                source, why = rationale(node)
                guards.append(Guard("threshold", relative, node.lineno, name,
                                    source, why))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attribute, value = node.func.attr, node.func.value
        is_environ = (attribute in ("get", "getenv")
                      and ((isinstance(value, ast.Attribute) and value.attr == "environ")
                           or (isinstance(value, ast.Name) and value.id == "os")))
        if not is_environ or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            source, why = rationale(node)
            guards.append(Guard("env_switch", relative, node.lineno, first.value,
                                source, why))
    return guards


def _blame_commits(root: str, wanted: dict[str, list[int]]) -> dict[tuple[str, int], str]:
    """The full commit message behind each (file, line), one blame per file.

    The reason a guard exists is very often in the commit that added it and nowhere
    else -- which is a thing this tool can reach and a hand-written registry cannot.
    Whether it is *worth* reaching is the number this function is here to produce.
    """
    at_line: dict[tuple[str, int], str] = {}
    for relative, numbers in wanted.items():
        done = subprocess.run(
            ["git", "-C", root, "blame", "--line-porcelain", "--", relative],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if done.returncode != 0:
            continue
        line_no, sha = 0, ""
        for raw in done.stdout.splitlines():
            if raw.startswith("\t"):
                line_no += 1
                if line_no in numbers and sha:
                    at_line[(relative, line_no)] = sha
            elif len(raw) >= 40 and raw[:40].isalnum() and " " in raw:
                candidate = raw.split(" ", 1)[0]
                if len(candidate) == 40:
                    sha = candidate

    # The subject line almost never carries the reason -- "Resolve references against
    # every same-named definition" says what, not why. The body does, and reading only
    # the subject is what made the first run of this probe report a flat zero.
    bodies: dict[str, str] = {}
    for sha in set(at_line.values()):
        done = subprocess.run(["git", "-C", root, "log", "-1", "--format=%B", sha],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        if done.returncode == 0:
            bodies[sha] = done.stdout.strip()
    return {key: bodies.get(sha, "") for key, sha in at_line.items()}


def survey(root: str, *, blame_sample: int = 250, seed: int = 0) -> dict:
    root = os.path.abspath(root)
    guards: list[Guard] = []
    files = physical = 0
    for absolute in references._iter_python_files(root):
        relative = os.path.relpath(absolute, root).replace(os.sep, "/")
        try:
            with open(absolute, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            tree = ast.parse(text)
        except (OSError, SyntaxError, ValueError):
            continue
        files += 1
        lines = text.splitlines()
        physical += len(lines)
        guards.extend(_collect(tree, relative, lines))

    # Only guards with nothing in the source get a blame lookup: the question is
    # whether history *rescues* the ones the source abandons.
    orphans = [g for g in guards if g.source == "none"]
    import random
    random.Random(seed).shuffle(orphans)
    sampled = orphans[:blame_sample]
    wanted: dict[str, list[int]] = defaultdict(list)
    for guard in sampled:
        wanted[guard.path].append(guard.line)
    subjects = _blame_commits(root, wanted) if wanted else {}
    rescued = 0
    for guard in sampled:
        message = subjects.get((guard.path, guard.line), "")
        match = _WHY.search(message) if message else None
        if match:
            # The sentence carrying the reason, not the whole message: what a middle
            # disclosure layer would actually be able to show.
            start = message.rfind(".", 0, match.start()) + 1
            end = message.find(".", match.end())
            guard.source = "commit"
            guard.why = message[start:end if end != -1 else None].strip()
            rescued += 1

    by_kind: Counter = Counter(g.kind for g in guards)
    by_source: dict[str, Counter] = {kind: Counter() for kind in KINDS}
    for guard in guards:
        by_source[guard.kind][guard.source] += 1
    return {"repo": os.path.basename(root), "files": files, "lines": physical,
            "total": len(guards), "by_kind": dict(by_kind),
            "by_source": {k: dict(v) for k, v in by_source.items()},
            "blame_sampled": len(sampled), "blame_rescued": rescued,
            "examples": [{"kind": g.kind, "path": g.path, "line": g.line,
                          "name": g.name, "source": g.source, "why": g.why[:120]}
                         for g in guards[:40]]}


def _print(report: dict) -> None:
    lines = report["lines"] or 1
    print(f"\n=== {report['repo']}  ({report['files']} files, {lines} lines, "
          f"{report['total']} guards, {report['total'] / lines * 1000:.1f} per kLOC)")
    print(f"{'kind':12} {'n':>6} {'/kLOC':>7}   "
          + "".join(f"{s:>10}" for s in SOURCES))
    for kind in KINDS:
        count = report["by_kind"].get(kind, 0)
        if not count:
            continue
        sources = report["by_source"][kind]
        shares = "".join(f"{sources.get(s, 0) / count:10.2f}" for s in SOURCES)
        print(f"{kind:12} {count:6} {count / lines * 1000:7.1f}   {shares}")
    if report["blame_sampled"]:
        share = report["blame_rescued"] / report["blame_sampled"]
        print(f"  of {report['blame_sampled']} guards with no reason in the source, "
              f"{report['blame_rescued']} ({share:.2f}) have one in their commit")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", default=None)
    parser.add_argument("--blame-sample", type=int, default=250)
    parser.add_argument("--dump", default=None)
    args = parser.parse_args()
    repos = args.repo or ([corpus.ensure(name, url) for name, url in corpus.EXTERNAL]
                          + [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))])
    reports = []
    for repo in repos:
        report = survey(repo, blame_sample=args.blame_sample)
        reports.append(report)
        _print(report)
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as handle:
            json.dump(reports, handle, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
