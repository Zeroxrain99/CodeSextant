"""The fences in this repository, and what each one actually checks.

The failure this exists for is not "the change forgot its test". It is the one after
that: a guard you wrote yourself months ago blocks you now, you do not remember writing
it, you cannot see why it is there, and deleting it looks cheaper than understanding
it. Every fence in that sentence works. That is what makes it expensive.

Why this leads with the *rule* rather than the reason
----------------------------------------------------
The obvious design is a registry showing name, then reason, then full text. It was
measured before it was built (``experiments/exp8_guard_inventory.py``, seven
repositories) and the measurement refused it:

* guards are dense -- 16 to 34 per thousand lines, 182 to 935 per project, of which
  72-89% are tests. A flat list is a second codebase, so disclosure has to be
  progressive and bounded by relevance rather than by the repository;
* the reason is usually **not written down**. ``raise`` and ``assert`` carry their
  message and are 94-100% self-documenting, but tests are 3% documented in jinja and 7%
  in httpie, and thresholds and environment switches -- the literal safety valves -- sit
  at or near zero nearly everywhere, this repository included, where 88% of 78
  environment switches say nothing at all;
* and history does not rescue them: searching the whole commit message of 250
  undocumented guards per repository for an explanatory clause found one in 0.00 to 0.04
  of cases.

So a middle layer made of prose would be empty for exactly the guards that block people.
What a guard *does* is machine-readable whether or not anyone wrote down why, and it is
also what a blocked reader needs first: the value, the members, the variable, the
default, the message, the symbols a test exercises. Prose is kept when it exists, and
labelled with where it came from, because "the author said this" and "the tool derived
this" are different claims.

What counts as a guard, stated here rather than left implicit:

    test        a test function -- the fence that fails the build
    assert      an assert in library code
    raise       a raise reached through a condition, carrying a message
    allowlist   a module-level collection something has to be added to
    threshold   a module-level numeric constant: a limit, budget, timeout, cap
    env_switch  an environment variable read: the runtime valve

Python only, for now, and deliberately: reference resolution is Python-only too, so this
matches the reach the rest of the tool already has. The other twelve languages have the
same fences and would need per-language patterns.
"""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field

# A module-level collection whose name says something has to be added to it. These are
# the fences that block a newcomer silently: the feature works everywhere except the one
# place keeping a list of the things allowed to work.
_LIST_NAME = re.compile(
    r"(ALLOW|DENY|BLOCK|VALID|INVALID|SUPPORTED|KNOWN|SKIP|EXCLUDE|IGNORE|SAFE|"
    r"PERMITTED|WHITELIST|BLACKLIST|EXEMPT|REGISTERED|HANDLERS|_TYPES|_KINDS|_NAMES)",
    re.IGNORECASE)
# A module-level number that decides whether something is refused.
_LIMIT_NAME = re.compile(
    r"(MAX|MIN|LIMIT|TIMEOUT|BUDGET|CAP|THRESHOLD|RETRIES|INTERVAL|SIZE|COUNT|"
    r"DEFAULT|WINDOW|DEPTH)", re.IGNORECASE)

KINDS = ("test", "assert", "raise", "allowlist", "threshold", "env_switch")
# Where a stated reason came from, strongest first. The distinction is reported rather
# than flattened: a docstring is the author speaking, a derived rule is the tool
# speaking, and a reader deciding whether to remove a fence needs to know which.
REASON_SOURCES = ("docstring", "comment", "message", "none")

# One rule line is a budget, not a suggestion: layer one shows a handful of guards and
# has to stay glanceable. Anything longer is what layer three is for.
MAX_RULE = 160


@dataclass
class Guard:
    """One fence: where it is, what it checks, and why -- if anyone said why."""

    kind: str
    name: str
    path: str
    line: int
    end_line: int
    # What it checks, derived from the code. Always present.
    rule: str
    # Why it is there, in the author's words. Usually absent -- see the module docstring.
    reason: str = ""
    reason_source: str = "none"
    # Project symbols the guard mentions: what it is fencing. Filled in by the caller,
    # which is the half that needs the index.
    covers: list[str] = field(default_factory=list)

    def as_row(self) -> dict:
        return {"kind": self.kind, "name": self.name, "path": self.path,
                "line": self.line, "end_line": self.end_line, "rule": self.rule,
                "reason": self.reason, "reason_source": self.reason_source,
                "covers": sorted(self.covers)}


def is_test_file(relative: str) -> bool:
    base = os.path.basename(relative)
    return (base.startswith("test_") or base.endswith("_test.py")
            or "/tests/" in f"/{relative}" or relative.startswith("test/")
            or base == "conftest.py")


def _clip(text: str, limit: int = MAX_RULE) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit - 1].rstrip() + "…"


def _comment_above(lines: list[str], line: int) -> str:
    """The comment block directly above a definition, and nothing further.

    Directly above with nothing in between: a comment two blank lines up is describing
    something else, and counting it would inflate the one number this whole design was
    revised around.
    """
    collected: list[str] = []
    index = line - 2  # line is 1-based and points at the definition itself
    while index >= 0:
        text = lines[index].strip()
        if not text.startswith("#"):
            break
        collected.append(text.lstrip("#").strip())
        index -= 1
    return " ".join(reversed(collected))


def _segment(lines: list[str], node) -> str:
    """The source behind a node, sliced from lines already in hand.

    ``ast.get_source_segment`` is the obvious call and it re-splits the whole file on
    every invocation: profiling a query over ten files showed 174 of those calls costing
    2.4 of 3.1 seconds, which is most of the answer spent re-reading text this function
    was handed. Column offsets are UTF-8 byte offsets in the AST, so the slicing goes
    through bytes rather than characters -- an accented identifier would otherwise shift
    every column after it on its line.
    """
    start, end = node.lineno - 1, (getattr(node, "end_lineno", None) or node.lineno) - 1
    if start < 0 or end >= len(lines):
        return ""
    first_col = getattr(node, "col_offset", 0)
    last_col = getattr(node, "end_col_offset", None)
    if start == end:
        raw = lines[start].encode("utf-8")[first_col:last_col]
        return raw.decode("utf-8", "replace")
    head = lines[start].encode("utf-8")[first_col:].decode("utf-8", "replace")
    tail = lines[end].encode("utf-8")[:last_col].decode("utf-8", "replace")
    return "\n".join([head, *lines[start + 1:end], tail])


def _literal(node) -> str:
    """A short readable rendering of a literal, for the rule line."""
    try:
        return _clip(ast.unparse(node), 60)
    except Exception:  # noqa: BLE001 - a rule line is never worth an exception
        return "…"


def _message(node) -> str:
    """The human-readable message an assert or raise carries, if any."""
    if isinstance(node, ast.Assert) and node.msg is not None:
        if isinstance(node.msg, ast.Constant) and isinstance(node.msg.value, str):
            return node.msg.value
        return ""
    if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
        for argument in node.exc.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                return argument.value
            if isinstance(argument, ast.JoinedStr):
                # Interpolations become a visible placeholder rather than vanishing.
                # Dropping them silently turns "cannot read {path}" into "cannot read
                # ()", which reads like the message itself is broken -- a rule line the
                # reader distrusts is worse than no rule line.
                joined = "".join(
                    part.value if isinstance(part, ast.Constant)
                    and isinstance(part.value, str) else "{…}"
                    for part in argument.values)
                if joined.replace("{…}", "").strip():
                    return joined
    return ""


def _exception_name(node: ast.Raise) -> str:
    target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return "an exception"


def _collection_rule(name: str, value) -> str | None:
    """"Membership set of N: a, b, c" -- the members are the rule."""
    members: list[str] = []
    if isinstance(value, ast.Dict):
        members = [_literal(key) for key in value.keys if key is not None]
    elif isinstance(value, (ast.Set, ast.Tuple, ast.List)):
        members = [_literal(item) for item in value.elts]
    elif (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
          and value.func.id in ("frozenset", "set", "tuple", "list")):
        inner = value.args[0] if value.args else None
        if isinstance(inner, (ast.Set, ast.Tuple, ast.List)):
            members = [_literal(item) for item in inner.elts]
    if len(members) < 2:
        return None
    shown = ", ".join(members[:8])
    more = f" (+{len(members) - 8} more)" if len(members) > 8 else ""
    return _clip(f"{name} admits {len(members)}: {shown}{more}")


def _environment_rule(node: ast.Call) -> str | None:
    """"reads FOO, default 'bar'" -- the variable and what happens without it."""
    function = node.func
    if not isinstance(function, ast.Attribute):
        return None
    holder = function.value
    is_environ = (function.attr in ("get", "getenv")
                  and ((isinstance(holder, ast.Attribute) and holder.attr == "environ")
                       or (isinstance(holder, ast.Name) and holder.id == "os")))
    if not is_environ or not node.args:
        return None
    first = node.args[0]
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return None
    if len(node.args) > 1:
        return _clip(f"reads {first.value}, default {_literal(node.args[1])}")
    return _clip(f"reads {first.value}, unset by default")


def _test_rule(node, lines: list[str]) -> str:
    """What a test asserts, which is the closest thing to what it fences.

    The count and the first assertion, not the whole body: a reader deciding whether
    their change should satisfy this test or change it needs to see the shape of the
    claim, and the body is one keystroke away in layer three.
    """
    asserts = [child for child in ast.walk(node) if isinstance(child, ast.Assert)]
    if not asserts:
        calls = sum(1 for child in ast.walk(node) if isinstance(child, ast.Call))
        return f"no assert; {calls} call(s) -- it fails only by raising"
    first = _segment(lines, asserts[0].test)
    plural = "s" if len(asserts) != 1 else ""
    return _clip(f"{len(asserts)} assertion{plural}, first: {_clip(first, 90)}")


def extract(relative: str, source: str) -> list[Guard]:
    """Every guard in one Python file, each with a rule derived from the code.

    ``relative`` is the repository-relative path, which is what decides whether this is
    a test file -- and therefore whether its asserts are the guard itself or a fence
    inside library code, which are different findings with different remedies.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    lines = source.splitlines()
    in_test_file = is_test_file(relative)
    found: list[Guard] = []

    def stated(node, message: str = "") -> tuple[str, str]:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc and doc.strip():
                return _clip(doc.strip().splitlines()[0]), "docstring"
        above = _comment_above(lines, node.lineno)
        if above:
            return _clip(above), "comment"
        if message:
            return _clip(message), "message"
        return "", "none"

    def end_of(node) -> int:
        return getattr(node, "end_lineno", None) or node.lineno

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if in_test_file and node.name.startswith("test"):
                reason, origin = stated(node)
                found.append(Guard("test", node.name, relative, node.lineno,
                                   end_of(node), _test_rule(node, lines),
                                   reason, origin))
        elif isinstance(node, ast.Assert) and not in_test_file:
            # An assert inside a test is the test; an assert in library code is a
            # separate fence with a separate failure mode and a separate remedy.
            message = _message(node)
            expression = _segment(lines, node.test)
            reason, origin = stated(node, message)
            found.append(Guard("assert", "", relative, node.lineno, end_of(node),
                               _clip(f"requires {_clip(expression, 110)}"),
                               reason, origin))
        elif isinstance(node, ast.Raise) and not in_test_file:
            message = _message(node)
            if not message:
                continue  # a bare re-raise is plumbing, not a fence
            reason, origin = stated(node, message)
            found.append(Guard("raise", _exception_name(node), relative, node.lineno,
                               end_of(node),
                               _clip(f"raises {_exception_name(node)}: {message}"),
                               reason, origin))
        elif isinstance(node, ast.Call):
            rule = _environment_rule(node)
            if rule:
                reason, origin = stated(node)
                variable = node.args[0].value
                found.append(Guard("env_switch", variable, relative, node.lineno,
                                   end_of(node), rule, reason, origin))

    # Module level only: these are the ones a change has to remember to update.
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            name = target.id
            collection = _collection_rule(name, value) if _LIST_NAME.search(name) else None
            if collection:
                reason, origin = stated(node)
                found.append(Guard("allowlist", name, relative, node.lineno,
                                   end_of(node), collection, reason, origin))
            elif (isinstance(value, ast.Constant)
                  and isinstance(value.value, (int, float))
                  and not isinstance(value.value, bool)
                  and name.isupper() and _LIMIT_NAME.search(name)):
                reason, origin = stated(node)
                found.append(Guard("threshold", name, relative, node.lineno,
                                   end_of(node), f"{name} = {value.value}",
                                   reason, origin))
    found.sort(key=lambda guard: (guard.line, guard.kind))
    return found


def extract_file(abs_path: str, relative: str) -> list[Guard]:
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as handle:
            return extract(relative, handle.read())
    except OSError:
        return []
