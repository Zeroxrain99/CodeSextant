"""Names that do not exist everywhere this package claims to run.

The local loop is one platform and one Python. CI is twelve combinations, and the six
that are not the local one can only report a mistake after it is pushed. That gap let
two of these through at once:

* ``signal.SIGKILL`` in a daemon exception handler, which does not exist on Windows, so
  every route-worker failure there raised AttributeError instead of the 503 it meant to;
* ``import tomllib`` in a test, which is stdlib only from 3.11, while this package
  supports 3.10 and already declares ``tomli`` for it.

Neither was a hard problem and neither was a new idea. The guarded form was already
written correctly in six other places -- ``if os.name == "nt": ... else: import fcntl``
appears four times, the ``tomllib``/``tomli`` fallback three times. The convention
existed, was understood, and was simply forgotten twice, in the two spots the author
could not run.

So this walks the AST and fails when a name that is not everywhere is used as though it
were. It is the same shape as ``test_lazy_resolution.py`` and exists for the same
reason: the failure is invisible where the code is written and expensive where it lands.

Accepted ways of using one of these names:

* inside a platform branch -- ``if os.name != "nt":``, ``if sys.platform == "win32":``
  and their negations, including as one operand of an ``and``;
* inside a ``try:`` whose handler catches what the failure would actually raise --
  ImportError or ModuleNotFoundError for an import, AttributeError for a name. An
  ``except OSError`` guards neither, which is the hole the first version of this
  checker had and this one does not;
* through ``getattr(signal, "SIGKILL", None)``, which states the absence in the call;
* in a function whose docstring or comments say ``posix-only`` or ``version-gated``,
  which is how a caller-enforced precondition gets written down instead of assumed.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Signals Windows does not have. SIGTERM, SIGINT, SIGABRT, SIGSEGV, SIGILL and SIGFPE
# are defined there and are deliberately absent from this list.
POSIX_ONLY_SIGNALS = frozenset({
    "SIGKILL", "SIGUSR1", "SIGUSR2", "SIGHUP", "SIGQUIT", "SIGALRM", "SIGCHLD",
    "SIGPIPE", "SIGWINCH", "SIGSTOP", "SIGCONT", "SIGTSTP", "SIGBUS", "SIGTRAP",
})
POSIX_ONLY_OS = frozenset({
    "fork", "forkpty", "setsid", "setpgrp", "setpgid", "killpg", "getpgid", "getpgrp",
    "getuid", "geteuid", "getgid", "getegid", "setuid", "seteuid", "setgid", "nice",
    "wait3", "wait4", "WIFSIGNALED", "WTERMSIG", "WEXITSTATUS", "uname", "fchown",
    "lchown", "mkfifo", "getpriority", "setpriority", "getloadavg",
})
POSIX_ONLY_MODULES = frozenset({
    "fcntl", "pwd", "grp", "termios", "resource", "posix", "syslog", "tty", "pty",
})
# Stdlib modules and names that arrived after this package's floor. The floor is read
# from pyproject rather than written here, so raising it retires these entries instead
# of leaving a second place to remember.
VERSION_GATED_MODULES = {"tomllib": (3, 11), "zoneinfo": (3, 9)}
VERSION_GATED_NAMES = {
    "typing": {"Self": (3, 11), "override": (3, 12), "assert_never": (3, 11),
               "LiteralString": (3, 11), "TypeVarTuple": (3, 11)},
    "enum": {"StrEnum": (3, 11), "ReprEnum": (3, 11)},
    "itertools": {"batched": (3, 12)},
    "datetime": {"UTC": (3, 11)},
    "asyncio": {"TaskGroup": (3, 11), "timeout": (3, 11), "Runner": (3, 11)},
}
# An explicit opt-in phrase, accepted in a comment or in the docstring. The
# docstring is the better home: a precondition the caller has to honour is
# documentation, not an aside, and a reader arriving at the function should meet
# it before the body rather than beside one line of it.
MARKER = re.compile(r"\b(posix-only|version-gated|windows-only)\b")


def _floor() -> tuple[int, ...]:
    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        raw = tomllib.load(handle)["project"]["requires-python"]
    digits = re.search(r"(\d+)\.(\d+)", raw)
    return (int(digits.group(1)), int(digits.group(2)))


def _platform_polarity(test: ast.expr) -> bool | None:
    """True when the body is the POSIX branch, False when the ``else`` is, None if
    this is not a platform test at all."""
    if isinstance(test, ast.BoolOp):
        for operand in test.values:
            polarity = _platform_polarity(operand)
            if polarity is not None:
                return polarity
        return None
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _platform_polarity(test.operand)
        return None if inner is None else not inner
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    left, operator, right = test.left, test.ops[0], test.comparators[0]
    if not isinstance(right, ast.Constant) or not isinstance(right.value, str):
        return None
    if isinstance(left, ast.Attribute) and left.attr == "name" and _is_name(left.value, "os"):
        posix_value = right.value != "nt"
    elif isinstance(left, ast.Attribute) and left.attr == "platform" and _is_name(
            left.value, "sys"):
        posix_value = right.value not in ("win32", "cygwin")
    else:
        return None
    if isinstance(operator, ast.Eq):
        return posix_value
    if isinstance(operator, ast.NotEq):
        return not posix_value
    return None


def _is_name(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _end(node) -> int:
    return getattr(node, "end_lineno", None) or node.lineno


# A try/except only guards what its handler would actually catch. This distinction is
# not pedantry: the one place in this repository where a POSIX-only name sits inside a
# `try: ... except OSError:` is a real hole, because the AttributeError that Windows
# raises there is not an OSError and would not be caught. The first version of this
# checker missed exactly that, which is why the two are separated.
_IMPORT_CATCHERS = frozenset({"ImportError", "ModuleNotFoundError",
                              "Exception", "BaseException"})
_ATTRIBUTE_CATCHERS = frozenset({"AttributeError", "Exception", "BaseException"})


def _guarded_ranges(tree: ast.Module, source: str) -> list[tuple[int, int, frozenset]]:
    """Line spans where a not-everywhere name is legitimate, and for which use.

    ``kinds`` is what the span excuses: ``"import"``, ``"attr"``, or both. A platform
    branch and an explicit marker excuse both, because they establish the platform
    rather than catching a consequence.
    """
    both = frozenset({"import", "attr"})
    ranges: list[tuple[int, int, frozenset]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            polarity = _platform_polarity(node.test)
            if polarity is True and node.body:
                ranges.append((node.body[0].lineno, _end(node.body[-1]), both))
            elif polarity is False and node.orelse:
                ranges.append((node.orelse[0].lineno, _end(node.orelse[-1]), both))
        elif isinstance(node, ast.Try):
            caught = set()
            for handler in node.handlers:
                for name in ast.walk(handler.type) if handler.type is not None else ():
                    if isinstance(name, ast.Name):
                        caught.add(name.id)
            kinds = set()
            if caught & _IMPORT_CATCHERS:
                kinds.add("import")
            if caught & _ATTRIBUTE_CATCHERS:
                kinds.add("attr")
            if kinds and node.body:
                ranges.append((node.body[0].lineno, _end(node.body[-1]),
                               frozenset(kinds)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = ast.get_source_segment(source, node) or ""
            if MARKER.search(body):
                ranges.append((node.lineno, _end(node), both))
    return ranges


def _covered(ranges: list[tuple[int, int, frozenset]], line: int, kind: str) -> bool:
    return any(start <= line <= stop and kind in kinds
               for start, stop, kinds in ranges)


def _findings(path: pathlib.Path, floor: tuple[int, ...]) -> list[str]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    ranges = _guarded_ranges(tree, source)
    relative = path.relative_to(REPO_ROOT).as_posix()
    out: list[str] = []

    # `import signal as signal_module` puts the same names behind a different local
    # name. The first version of this checker matched only the literal `signal.`, and
    # missed a real use in tests/test_daemon_routing.py for exactly that reason -- which
    # Windows CI then found, one push later, which is the loop this file exists to end.
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "." not in alias.name:
                    aliases[alias.asname or alias.name] = alias.name

    def report(line: int, kind: str, what: str) -> None:
        if not _covered(ranges, line, kind):
            out.append(f"{relative}:{line}  {what}")

    # getattr(signal, "SIGKILL", None) states the absence rather than assuming it, so
    # the name inside it is not a finding.
    excused: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and _is_name(node.func, "getattr")
                and len(node.args) == 3 and isinstance(node.args[1], ast.Constant)):
            excused.add((node.lineno, str(node.args[1].value)))

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            local, attribute = node.value.id, node.attr
            module = aliases.get(local, local)
            if (node.lineno, attribute) in excused:
                continue
            if module == "signal" and attribute in POSIX_ONLY_SIGNALS:
                report(node.lineno, "attr",
                       f"signal.{attribute} does not exist on Windows")
            elif module == "os" and attribute in POSIX_ONLY_OS:
                report(node.lineno, "attr",
                       f"os.{attribute} does not exist on Windows")
            else:
                needs = VERSION_GATED_NAMES.get(module, {}).get(attribute)
                if needs and needs > floor:
                    report(node.lineno, "attr",
                           f"{module}.{attribute} needs Python "
                           f"{needs[0]}.{needs[1]}, floor is {floor[0]}.{floor[1]}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in POSIX_ONLY_MODULES:
                    report(node.lineno, "import",
                           f"{root} does not exist on Windows")
                needs = VERSION_GATED_MODULES.get(root)
                if needs and needs > floor:
                    report(node.lineno, "import",
                           f"{root} needs Python {needs[0]}.{needs[1]}, "
                           f"floor is {floor[0]}.{floor[1]}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in POSIX_ONLY_MODULES:
                report(node.lineno, "import", f"{root} does not exist on Windows")
            needs = VERSION_GATED_MODULES.get(root)
            if needs and needs > floor:
                report(node.lineno, "import",
                       f"{root} needs Python {needs[0]}.{needs[1]}, "
                       f"floor is {floor[0]}.{floor[1]}")
            for alias in node.names:
                gate = VERSION_GATED_NAMES.get(root, {}).get(alias.name)
                if gate and gate > floor:
                    report(node.lineno, "import",
                           f"{root}.{alias.name} needs Python {gate[0]}.{gate[1]}, "
                           f"floor is {floor[0]}.{floor[1]}")
    return out


def _sources() -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for directory in ("codesextant", "tests", "experiments", "tools"):
        root = REPO_ROOT / directory
        if root.is_dir():
            paths.extend(p for p in root.rglob("*.py")
                         if "__pycache__" not in p.parts)
    return sorted(paths)


def test_no_platform_or_version_gated_name_is_used_unguarded():
    """The whole repository, on every platform, from whichever one you happen to run.

    Both halves of the failure this pins were pushed green from a Linux checkout on
    3.11: the platform that cannot see either. Reading the AST costs nothing and does
    not care which machine it runs on.
    """
    floor = _floor()
    findings = [line for path in _sources() for line in _findings(path, floor)]
    assert not findings, (
        "these names are not available everywhere this package claims to run:\n  "
        + "\n  ".join(findings)
        + "\n\nGuard with an os.name / sys.platform branch, a try/except ImportError, "
          "getattr(module, 'NAME', default), or say 'posix-only' in the function's "
          "docstring when its caller guarantees the platform.")


def test_the_guard_catches_the_two_that_were_actually_shipped():
    """A guard nobody has seen fail is a guard nobody knows the shape of.

    These are the two real defects, reduced. If the checker stops catching them it has
    stopped being worth running, and that has to fail here rather than on the next
    push to a platform nobody ran.
    """
    floor = (3, 10)
    tree = ast.parse("import signal\nx = signal.SIGKILL\n")
    assert _guarded_ranges(tree, "") == []

    import tempfile
    with tempfile.TemporaryDirectory() as home:
        sample = pathlib.Path(home) / "sample.py"
        sample.write_text("import signal\nimport tomllib\n"
                          "def f(exitcode):\n    return exitcode == signal.SIGKILL\n",
                          encoding="utf-8")
        # _findings reports paths relative to the repository, so the probe file has to
        # live inside it; a temporary copy under tests/ keeps the run self-cleaning.
        target = REPO_ROOT / "tests" / "_portability_probe.py"
        target.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            findings = _findings(target, floor)
        finally:
            target.unlink()
    assert any("signal.SIGKILL" in f for f in findings), findings
    assert any("tomllib" in f for f in findings), findings


def test_the_accepted_guarded_forms_are_all_accepted():
    """Every shape the codebase actually uses, so the checker cannot become a nuisance.

    A checker with false positives gets an exemption added rather than a fix, and then
    it is no longer a fence. These are the five forms already in this repository.
    """
    floor = (3, 10)
    target = REPO_ROOT / "tests" / "_portability_probe.py"
    target.write_text(
        "import os\nimport signal\n"
        "if os.name == 'nt':\n    pass\nelse:\n    import fcntl\n"
        "if os.name != 'nt':\n    os.setsid()\n"
        "try:\n    import tomllib\nexcept ModuleNotFoundError:\n"
        "    import tomli as tomllib\n"
        "_K = getattr(signal, 'SIGKILL', None)\n"
        "def teardown(pid):\n"
        "    # posix-only: the caller checks os.name before reaching this\n"
        "    os.killpg(pid, signal.SIGKILL)\n",
        encoding="utf-8")
    try:
        findings = _findings(target, floor)
    finally:
        target.unlink()
    assert findings == [], findings


def test_the_python_floor_is_the_same_number_in_all_three_places():
    """One number, three places that each believe it, and nothing joining them.

    ``requires-python`` says what the package supports, the CI matrix says what is
    proven, and ruff's ``target-version`` says what the linter will accept. They were
    not the same: ruff targeted 3.11 while the package claimed 3.10, so the one tool
    that reads every file on every commit was quietly agreeing to syntax a third of the
    matrix cannot run.
    """
    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        config = tomllib.load(handle)
    floor = _floor()

    workflow = (REPO_ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8")
    versions = re.findall(r'"(\d+\.\d+)"', workflow)
    lowest = min((tuple(int(p) for p in v.split(".")) for v in versions
                  if v.startswith("3.")), default=None)
    assert lowest == floor, (
        f"pyproject requires-python floor is {floor} but the CI matrix's lowest "
        f"Python is {lowest}; one of them is testing something nobody supports")

    target = config["tool"]["ruff"]["target-version"]
    assert target == f"py{floor[0]}{floor[1]}", (
        f"ruff targets {target} but requires-python floor is "
        f"py{floor[0]}{floor[1]}; the linter would accept syntax the floor cannot run")
    assert sys.version_info >= floor
