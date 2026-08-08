"""Classify dead-code evidence from linters and reference resolvers.

Unused-import checks delegate to Ruff or ESLint. Orphan classification requires
jedi for Python or ts-morph for TypeScript and JavaScript. Missing or incomplete
resolution returns an ``UNKNOWN_*`` verdict. Entrypoints and reflective symbols
are classified as ``PUBLIC_API``. Every result is evidence to review, not a
deletion instruction.

This module contains linter wrappers, entrypoint detection, and verdict grading.
``engine.find_deadcode`` assembles the resolver results.

Environment switches, parsed case-insensitively:
  - CODESEXTANT_DEADCODE_LINTER = ruff | eslint | auto | off (default auto: chosen by
    language; off runs no linter at all)
  - CODESEXTANT_DEADCODE_ENTRYPOINT_EXTRA = extra entrypoint path fragments (separated by
    os.pathsep; a match means PUBLIC_API)
  - CODESEXTANT_DEADCODE_LINT_TIMEOUT = linter subprocess timeout in seconds (default 60
    for ruff, 120 for eslint)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from . import references, symbols

# Keep Windows subprocesses from flashing a console window (matching the CREATE_NO_WINDOW
# use in references.py and engine.py).
_CREATE_NO_WINDOW = 0x08000000


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def linter_mode() -> str:
    """Linter mode: ruff | eslint | auto | off (default auto)."""
    m = _env("CODESEXTANT_DEADCODE_LINTER", "auto").lower().strip()
    return m or "auto"


def _lint_timeout(default: float) -> float:
    try:
        v = float(_env("CODESEXTANT_DEADCODE_LINT_TIMEOUT", ""))
        return v if v > 0 else default
    except ValueError:
        return default


# ── Unused imports: wrap ruff for Python and eslint for TS/JS ──
def _run_ruff_f401(target: str) -> dict:
    """ruff check --select F401 (unused imports). Returns {available, findings|reason}.

    ruff is the de facto standard Python linter. F401 is `imported but unused`, and ruff
    handles side-effect imports (`# noqa`), `__all__` re-exports and TYPE_CHECKING blocks
    correctly, far better than a hand-rolled AST diff.
    """
    if shutil.which("ruff") is None:
        return {"available": False,
                "reason": "ruff is not installed (pip install ruff to detect unused Python imports)"}
    kw: dict = {"capture_output": True, "timeout": _lint_timeout(60)}
    if os.name == "nt":
        kw["creationflags"] = _CREATE_NO_WINDOW
    try:
        proc = subprocess.run(
            ["ruff", "check", "--select", "F401", "--output-format", "json", target], **kw)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"available": False, "reason": f"ruff failed to run: {exc}"}
    # ruff exit 1 = lint hits found (normal), 0 = no hits; >1 = a real error (config or path problem)
    if proc.returncode not in (0, 1):
        err = proc.stderr.decode("utf-8", "replace")[:200] if proc.stderr else ""
        return {"available": False, "reason": f"ruff exit code {proc.returncode}: {err}"}
    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace") or "[]")
    except json.JSONDecodeError:
        return {"available": False, "reason": "ruff output was not JSON (too old a version? it must support --output-format json)"}
    findings = []
    for d in data:
        if not isinstance(d, dict):
            continue
        loc = d.get("location") or {}
        findings.append({
            "path": d.get("filename"),
            "line": loc.get("row"),
            "code": d.get("code"),
            "message": d.get("message"),
        })
    return {"available": True, "findings": findings}


_ESLINT_CONFIGS = (".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json",
                   ".eslintrc.yml", ".eslintrc.yaml", "eslint.config.js",
                   "eslint.config.mjs", "eslint.config.cjs")


def _run_eslint_unused(target: str, root: str) -> dict:
    """eslint --format json, filtered to no-unused-vars / unused-imports rule hits.

    eslint requires the project's own configuration because rules differ by project.
    Missing configuration or eslint returns UNKNOWN_NO_LINTER.
    """
    if shutil.which("eslint") is None and shutil.which("npx") is None:
        return {"available": False, "reason": "eslint/npx is not installed (cannot detect unused TS/JS imports)"}
    has_cfg = any(os.path.isfile(os.path.join(root, c)) for c in _ESLINT_CONFIGS)
    if not has_cfg:
        return {"available": False, "reason": "the project has no eslint config, so this was skipped (lint rules are not guessed)"}
    if shutil.which("eslint"):
        cmd = ["eslint", "--format", "json", target]
    else:
        cmd = ["npx", "--no-install", "eslint", "--format", "json", target]
    kw: dict = {"capture_output": True, "timeout": _lint_timeout(120), "cwd": root}
    if os.name == "nt":
        kw["creationflags"] = _CREATE_NO_WINDOW
    try:
        proc = subprocess.run(cmd, **kw)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"available": False, "reason": f"eslint failed to run: {exc}"}
    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace") or "[]")
    except json.JSONDecodeError:
        return {"available": False, "reason": "eslint output was not JSON (the config may be wrong, or it did not run in lint mode)"}
    findings = []
    for f in data if isinstance(data, list) else []:
        if not isinstance(f, dict):
            continue
        for m in f.get("messages", []) or []:
            rule = (m.get("ruleId") or "")
            if "no-unused-vars" in rule or "unused-imports" in rule:
                findings.append({
                    "path": f.get("filePath"),
                    "line": m.get("line"),
                    "code": rule,
                    "message": m.get("message"),
                })
    return {"available": True, "findings": findings}


def detect_unused_imports(target: str, *, root: str, lang: str | None = None) -> dict:
    """Detect unused imports, auto-picking ruff (Python) or eslint (TS/JS) by language.

    Returns a dict:
      available: {available:True, linter, findings:[{path,line,code,message}]}
      unavailable: {available:False, linter, verdict:"UNKNOWN_NO_LINTER", reason, findings:[]}
      disabled: {available:False, linter:None, reason:"disabled", findings:[]}
    Unavailable always means UNKNOWN_NO_LINTER; it never degrades into
    hand-rolled AST false positives.
    """
    mode = linter_mode()
    if mode == "off":
        return {"available": False, "linter": None, "findings": [],
                "reason": "disabled (CODESEXTANT_DEADCODE_LINTER=off)"}
    is_dir = os.path.isdir(target)
    tlang = lang if lang else (None if is_dir else symbols.language_for_file(target))
    use = mode
    if mode == "auto":
        if tlang in ("typescript", "tsx", "javascript"):
            use = "eslint"
        elif tlang in ("python", None):   # None = directory scan, keep using ruff (Python only)
            use = "ruff"
        else:
            # 2026-06-22: the other languages (C#/Java/C/C++/Lua/Ruby/PHP/Bash/Kotlin/
            # Swift) have no corresponding unused-import linter (ruff is Python-only,
            # eslint is TS/JS-only), so return UNKNOWN. Do not force ruff to
            # run against .cs/.java and friends, where it reports "no files" and misleads.
            # This upholds the dead-code layer's linchpin: UNKNOWN over a false positive.
            return {"available": False, "linter": None, "findings": [],
                    "verdict": "UNKNOWN_NO_LINTER",
                    "reason": f"language '{tlang}' has no unused-import linter (ruff is Python-only, eslint is TS/JS-only)"}
    if use == "ruff":
        r = _run_ruff_f401(target)
    elif use == "eslint":
        r = _run_eslint_unused(target, root)
    else:
        return {"available": False, "linter": use, "findings": [],
                "verdict": "UNKNOWN_NO_LINTER", "reason": f"unknown linter mode={use}"}
    if r.get("available"):
        return {"available": True, "linter": use, "findings": r["findings"]}
    return {"available": False, "linter": use, "findings": [],
            "verdict": "UNKNOWN_NO_LINTER", "reason": r.get("reason")}


# ── Entrypoint and reflective-entry detection ──
# Filename conventions (matched against posix-style paths; covers web framework routes,
# tests, module entrypoints and barrels).
_ENTRYPOINT_FILE_PATTERNS = [
    (r"(^|/)pages/", "Next.js/Nuxt pages route entrypoint"),
    (r"(^|/)app/.*/(route|page|layout|loading|error|template|default)\.[tj]sx?$",
     "Next.js app router entrypoint"),
    (r"(^|/)test_[^/]*\.py$", "pytest test file"),
    (r"(^|/)[^/]*_test\.py$", "pytest test file"),
    (r"(^|/)tests?/", "test directory"),
    (r"(^|/)conftest\.py$", "pytest conftest"),
    (r"(^|/)__main__\.py$", "Python module entrypoint (python -m)"),
    (r"(^|/)setup\.py$", "Python package entrypoint"),
    (r"(^|/)manage\.py$", "Django management entrypoint"),
    (r"(^|/)index\.[tj]sx?$", "barrel / index entrypoint"),
    (r"(^|/)main\.[tj]sx?$", "front-end application entrypoint"),
]
# Reflective-entry decorators (Python; a hit among the run of @decorators directly above
# a symbol definition means the framework calls it reflectively).
# Match loosely on "@<any object>.<verb>" rather than pinning the
# object name to app/router, because FastAPI code conventionally uses api/application and
# Flask Blueprint variables are named freely (users_bp). Also add FastAPI's common
# websocket/on_event/exception_handler/middleware. Exempting loosely is preferred: it
# rarely misreports a real entrypoint as dead code, at the cost of occasionally treating a
# non-entrypoint decorator as an entrypoint (under-reporting one piece of dead code). That
# matches the conservative stance that deleting an entrypoint by mistake costs far more
# than missing one piece of dead code.
_ENTRYPOINT_DECORATOR_VERBS = (
    "route", "get", "post", "put", "delete", "patch", "options", "head",
    "websocket", "on_event", "exception_handler", "middleware",
    "command", "callback", "group", "task", "fixture", "event",
)
_ENTRYPOINT_DECORATOR_RE = re.compile(
    r"^@\w+(?:\.\w+)*\.(" + "|".join(_ENTRYPOINT_DECORATOR_VERBS) + r")\b")
# Bare decorators with no object prefix (@task/@fixture/@event/@shared_task…)
_ENTRYPOINT_BARE_DECORATORS = (
    "@task", "@fixture", "@event", "@shared_task", "@callback", "@command",
)


def _decorator_hits(deco: str) -> bool:
    d = deco.lstrip()
    if _ENTRYPOINT_DECORATOR_RE.match(d):
        return True
    head = d.split("(", 1)[0].strip()
    return any(head == b for b in _ENTRYPOINT_BARE_DECORATORS)


def entry_point_func_names(root: str) -> set[str]:
    """Parse [project.scripts] / [project.gui-scripts] from the project root's
    pyproject.toml and return the set of function names console_scripts point at
    ("pkg.cli:main" → "main").

    A console_scripts entrypoint is called reflectively by the wrapper
    installed alongside the package, and nothing in the source mentions its name, so its
    name-level external usage is necessarily 0. Without this exemption, find_unwired
    would misreport almost every CLI main entrypoint as unwired.
    Set CODESEXTANT_SCAN_ENTRYPOINTS=0/false/no/off to disable (on by default). A read
    failure or a missing pyproject returns an empty set.
    """
    if os.environ.get("CODESEXTANT_SCAN_ENTRYPOINTS", "").lower() in ("0", "false", "no", "off"):
        return set()
    pyproject = os.path.join(root, "pyproject.toml")
    if not os.path.isfile(pyproject):
        return set()
    try:
        import tomllib  # standard library on Python 3.11+
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return set()
    funcs: set[str] = set()
    proj = (data.get("project") or {}) if isinstance(data, dict) else {}
    for key in ("scripts", "gui-scripts"):
        for _ep, target in (proj.get(key) or {}).items():
            # target looks like "pkg.module:func" or "pkg.module:obj.method"
            if isinstance(target, str) and ":" in target:
                func = target.split(":", 1)[1].strip().split(".")[0]
                if func:
                    funcs.add(func)
    return funcs


def _has_entrypoint_decorator(source: str, symbol_name: str) -> bool:
    """Whether the run of decorators directly above a symbol definition
    (def/class symbol_name) contains a reflective-entry decorator."""
    lines = source.splitlines()
    pat = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+" + re.escape(symbol_name) + r"\b")
    for i, ln in enumerate(lines):
        if not pat.match(ln):
            continue
        j = i - 1
        while j >= 0:
            stripped = lines[j].strip()
            if not stripped:           # blank lines are allowed between decorators
                j -= 1
                continue
            if stripped.startswith("@"):
                if _decorator_hits(stripped):
                    return True
                j -= 1
                continue
            break                       # hit a non-blank, non-decorator line → stop
    return False


def _in_dunder_all(source: str, symbol_name: str) -> bool:
    """Whether the symbol is listed in __all__ (an explicit public API; never deleted)."""
    m = re.search(r"__all__\s*=\s*[\[\(](.*?)[\]\)]", source, re.S)
    if not m:
        return False
    return re.search(r"['\"]" + re.escape(symbol_name) + r"['\"]", m.group(1)) is not None


def is_entrypoint(path: str, *, symbol_name: str | None = None,
                  source: str | None = None) -> tuple[bool, str | None]:
    """Whether a symbol is an entrypoint or reflectively called (→ PUBLIC_API, never a
    deletion candidate).

    Order of checks: filename convention, configured extra paths, then decorators
    and ``__all__`` when source and symbol are supplied.
    Returns (is_entrypoint, reason).
    """
    posix = path.replace("\\", "/")
    for pat, reason in _ENTRYPOINT_FILE_PATTERNS:
        if re.search(pat, posix):
            return True, reason
    extra = _env("CODESEXTANT_DEADCODE_ENTRYPOINT_EXTRA", "")
    for frag in extra.split(os.pathsep):
        frag = frag.strip()
        if frag and frag in posix:
            return True, "user-specified entrypoint (CODESEXTANT_DEADCODE_ENTRYPOINT_EXTRA)"
    if source and symbol_name:
        if _has_entrypoint_decorator(source, symbol_name):
            return True, "carries a route/task/fixture decorator (framework reflective entry)"
        if _in_dunder_all(source, symbol_name):
            return True, "listed in __all__ (explicit public API)"
    return False, None


# ── Resolver availability for the UNKNOWN safety gate ──
def resolver_available(lang: str | None) -> tuple[bool, str | None]:
    """Whether this language has a real import resolver able to judge orphan status.

    Python uses jedi. TS/JS uses ts-morph when Node and the package are available.
    Other languages return False, and the caller marks the result UNKNOWN_NO_RESOLVER.
    """
    if lang in (None, "python"):
        return True, None
    if lang in ("typescript", "tsx", "javascript"):
        if references.ts_morph_available():
            return True, None
        return False, ("TS/JS orphan status needs node + ts-morph for real resolution, "
                       "which is not set up; install them or set "
                       "CODESEXTANT_TS_MORPH_DISABLED=0 to enable it")
    return False, f"language '{lang}' has no real import resolver (jedi is Python-only, ts-morph is TS/JS-only)"


# ── Orphan verdict grading ──
_VERDICT_ICON = {
    "UNKNOWN_NO_RESOLVER": "❔",
    "UNKNOWN_NO_LINTER": "❔",
    "UNKNOWN_UNRESOLVED": "❔",
    "LIKELY_UNUSED": "🟡",
    "REEXPORT_ONLY": "🟡",
    "PUBLIC_API": "⚪",
    "KEEP": "✅",
}


def classify_orphan(refs_result: dict | None, *, is_entry: bool,
                    entry_reason: str | None) -> dict:
    """Grade a symbol's find_references result into an orphan verdict.

    Two checks prevent false-positive orphan verdicts:
      1. Without a real resolver, return UNKNOWN_NO_RESOLVER.
      2. Resolution ran but **did not locate the symbol definition** (an error, or no
         definition), return UNKNOWN_UNRESOLVED. A high=0 result can mean
         "genuinely unreferenced" **or** "the resolver never located the definition at
         all" (jedi's two-stage lookup only recognizes def/class lines, so a module-level
         assignment `NAME = ...` is not located and produces high=0).
    Only a located definition with zero resolved references earns LIKELY_UNUSED.
    """
    if is_entry:
        return {"verdict": "PUBLIC_API", "icon": _VERDICT_ICON["PUBLIC_API"],
                "reason": entry_reason or "entrypoint / reflective call"}
    refs_result = refs_result or {}
    engine = refs_result.get("engine")
    if engine not in ("jedi", "ts-morph"):
        return {"verdict": "UNKNOWN_NO_RESOLVER", "icon": _VERDICT_ICON["UNKNOWN_NO_RESOLVER"],
                "reason": f"no real resolver (engine={engine or 'none'}), so deletability is not judged"}
    if refs_result.get("error") or not refs_result.get("definition"):
        return {"verdict": "UNKNOWN_UNRESOLVED", "icon": _VERDICT_ICON["UNKNOWN_UNRESOLVED"],
                "reason": ("the resolver did not locate this symbol's definition (e.g. a "
                           "module-level assignment, or a non-def/class symbol), so high=0 "
                           "does not mean it is genuinely unreferenced → deletability is not judged")}
    high = refs_result.get("high_confidence") or []
    if high:
        # If every high-confidence reference is a re-export (a barrel
        # `export {X} from`, or this file's own `export {X}`) with no real internal
        # consumption, classify it as REEXPORT_ONLY rather than KEEP,
        # and do not misjudge it as LIKELY_UNUSED (it genuinely is exported and may be a
        # public API). jedi (Python) high-confidence entries carry no is_reexport flag, so
        # all() is False and Python falls through to KEEP unaffected.
        if all(h.get("is_reexport") for h in high):
            return {"verdict": "REEXPORT_ONLY", "icon": _VERDICT_ICON["REEXPORT_ONLY"],
                    "reason": (f"all {len(high)} references are re-exports with no real internal "
                               "consumption; this may be a public API, or the whole export chain "
                               "may be deletable; review it yourself")}
        real = sum(1 for h in high if not h.get("is_reexport"))
        rx = len(high) - real
        suffix = f" (plus {rx} re-export(s))" if rx else ""
        return {"verdict": "KEEP", "icon": _VERDICT_ICON["KEEP"],
                "reason": f"{real} real consuming reference(s), confirmed by {engine}{suffix}"}
    return {"verdict": "LIKELY_UNUSED", "icon": _VERDICT_ICON["LIKELY_UNUSED"],
            "reason": f"{engine} real resolution found zero high-confidence references; review it "
                      "yourself and run the build before deleting (this is not a confident verdict)"}


def verdict_icon(verdict: str) -> str:
    return _VERDICT_ICON.get(verdict, "·")


def read_code_advisory(unused: dict, orphans: list) -> list:
    """Describe dead-code blind spots that still require source inspection.

    State which parts the
    tool could not help with and where you have to read the code yourself.

    Tool silence is not the same as safe to delete. Spell out the boundaries of
    UNKNOWN, missing linter, LIKELY_UNUSED and REEXPORT_ONLY, so nobody reads "it has been
    scanned" as "it has been cleaned". The dead-code layer is a clue, not deletion
    permission.
    """
    notes: list[str] = []
    orphans = orphans or []
    unknown = sum(1 for o in orphans if str(o.get("verdict", "")).startswith("UNKNOWN"))
    likely = sum(1 for o in orphans if o.get("verdict") == "LIKELY_UNUSED")
    reexport = sum(1 for o in orphans if o.get("verdict") == "REEXPORT_ONLY")
    if not unused.get("available"):
        notes.append(f"Unused imports could not be determined ({unused.get('reason')}). The tool "
                     "did not help here; install ruff/eslint or check by hand.")
    if unknown:
        notes.append(f"{unknown} symbol(s) the tool cannot decide on (module-level variables, or no "
                     "real resolver). The tool is silent here, which does not mean they are "
                     "deletable. You have to read the code and confirm these yourself.")
    if likely:
        notes.append(f"{likely} suspected dead symbol(s) are a clue, not a verdict. Before deleting, "
                     "read the surrounding context (they may be dynamic/reflective calls, a public "
                     "API, test fixtures, or other entries the tool cannot see) and run build/CI.")
    if reexport:
        notes.append(f"{reexport} symbol(s) are only re-exported. Deciding whether that is a public "
                     "API or a fully deletable export chain means reading the call sites and external "
                     "consumers. The tool cannot decide it for you.")
    if not notes:
        notes.append("No significant blind spots in this result; but dead-code detection is a clue "
                     "layer by nature, so deletion still rests on human review plus a build.")
    return notes
