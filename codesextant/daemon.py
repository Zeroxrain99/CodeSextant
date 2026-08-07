"""codesextant C2: singleton long-running daemon (one local HTTP service, fixed port,
idempotent startup via liveness probe, shared by all agents).

Wraps the C1 pure engine (engine.py's 5 APIs) into HTTP endpoints, so every agent on the
machine shares one code map through a single HTTP interface instead of each building its own.

Design decisions:
  - HTTP bridge: a ThreadingHTTPServer on a fixed port, reachable by any HTTP client.
  - Idempotent startup: probe /health first. If the brand matches, a daemon is already running,
    so exit without starting a second one. Checking the brand rather than the open port matters,
    because an unrelated process can hold the port.
  - Per-project isolation: storage.project_key = sha1(repo absolute path), so two repositories
    never share state.

Endpoints (one function per endpoint, all take project= repo absolute path):
    GET  /health                                   → daemon health + a ready field
    GET  /get_symbols?project=<repo>&file=<file>    → engine.get_symbols
    POST /find_references  {project, symbol, ...}   → engine.find_references
    GET  /get_map?project=<repo>&budget=<n>          → engine.get_map
    POST /reindex          {project, force?}         → engine.index_project
    GET  /status?project=<repo>                      → engine.status

Observable logging (aligned with the user's "new features must ship with observable
logging" preference):
    Startup / every endpoint hit / errors all land in daemon.log (default ~/.codesextant/daemon.log).

Service identity brand: service == "codesextant" (used for liveness-probe matching, to
guard against another process occupying the same port).

Usage:
    python -m codesextant.daemon serve     # run the server in the foreground (for testing)
    python -m codesextant.daemon ensure    # idempotent startup: spawns detached in the background only if not already running
    python -m codesextant.daemon ping      # strict liveness probe (matches /health brand)
    python -m codesextant.daemon stop      # stop the local daemon (for cleaning up residue during verification)
"""
from __future__ import annotations

import sys

# Windows console / subprocess stdout must not crash when printing non-ASCII/emoji output (memory: this bit us twice before)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import importlib
import json
import logging
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Clients only need ensure/http_ping; do not load the full tree-sitter engine at client import time.
# storage is lightweight and required for locking/paths; engine/panel/watcher are lazy-loaded only
# when the daemon actually serves or an endpoint gets hit.
if not __package__:  # pragma: no cover - compatibility fallback for running this file directly
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_PACKAGE = __package__ or "codesextant"
storage = importlib.import_module(f"{_PACKAGE}.storage")
work_coordinator = importlib.import_module(f"{_PACKAGE}.work_coordinator")


class _LazyModule:
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.loaded = None

    def __getattr__(self, name: str):
        if self.loaded is None:
            self.loaded = importlib.import_module(self.module_name)
        return getattr(self.loaded, name)


engine = _LazyModule(f"{_PACKAGE}.engine")
panel = _LazyModule(f"{_PACKAGE}.panel")
watcher = _LazyModule(f"{_PACKAGE}.watcher")
_HEAVY_COORDINATOR = work_coordinator.SHARED_SHARDED

# queue 3: file-watcher singleton manager (built lazily; owned by the daemon, shared across all projects)
_WATCH_MGR = None


def _get_watch_mgr():
    global _WATCH_MGR
    if _WATCH_MGR is None:
        _WATCH_MGR = watcher.WatchManager(get_logger())
    return _WATCH_MGR

# ── Service constants ──
SERVICE_NAME = "codesextant"          # liveness-probe brand (also accepts the "codesextant" product name, see _health_brand_ok)
HOST = "127.0.0.1"
DEFAULT_PORT = 8790


class _InterprocessFileLock:
    """Crash-safe cross-process byte lock backed by the local filesystem.

    Windows uses ``msvcrt.locking`` and POSIX uses ``fcntl.flock``.  The OS
    releases the lock automatically when a process exits, so a crashed daemon
    cannot leave a permanent stale lock behind.
    """

    def __init__(self, path: str | Path, *, timeout: float = 0.0,
                 poll_sec: float = 0.05):
        self.path = Path(path)
        self.timeout = max(0.0, float(timeout))
        self.poll_sec = max(0.01, float(poll_sec))
        self._fh = None
        self._acquired = False

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # ⛔ Do not use `with` here: the file handle *is* the lock itself, and must
        # stay open until release() closes it. Wrapping it in a context manager would
        # close the file the moment this function returns, releasing the lock
        # immediately, and multiple daemons could then race to grab the same port.
        # The linter's SIM115 warning is a false positive in this situation.
        self._fh = open(self.path, "a+b")  # noqa: SIM115
        self._fh.seek(0, os.SEEK_END)
        if self._fh.tell() == 0:
            self._fh.write(b"\0")
            self._fh.flush()

        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover - Windows is the production target
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._acquired = True
                return self
            except (OSError, BlockingIOError) as exc:
                if time.monotonic() >= deadline:
                    self._fh.close()
                    self._fh = None
                    # Keep the original exception chain: which OS error occurred
                    # (permissions? disk?) determines how to debug it. Reporting
                    # only "lock busy" would throw away that diagnostic clue.
                    raise TimeoutError(f"lock busy: {self.path}") from exc
                time.sleep(self.poll_sec)

    def release(self):
        if self._fh is None:
            return
        try:
            if self._acquired:
                self._fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover - Windows is the production target
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._acquired = False
            self._fh.close()
            self._fh = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, _exc_type, _exc, _tb):
        self.release()
        return False


def _daemon_lock_path(port: int, kind: str) -> Path:
    return storage.default_db_dir() / f"daemon-{port}.{kind}.lock"


def _instance_lock_held(port: int) -> bool | None:
    """Return whether a live CodeSextant process owns this port's lifetime lock.

    A CPU-bound map can briefly starve the threaded ``/health`` handler long
    enough for every bounded HTTP probe to time out.  The OS-backed instance
    lock is independent of the GIL and is released automatically on process
    exit, so listener + held port-specific lock is a safe degraded ownership
    proof without accepting an unrelated service on the same port.
    """
    # Every ownership checker must first serialize its *probe*.  Otherwise two
    # simultaneous checkers can see each other's millisecond-long test lock and
    # falsely conclude that a lifetime daemon owns it.
    probe_guard = _InterprocessFileLock(
        _daemon_lock_path(port, "instance-probe"), timeout=1.0)
    try:
        probe_guard.acquire()
    except TimeoutError:
        # Contention is not proof that the lifetime lock is held.  Report an
        # explicit unknown state so callers fail closed without claiming a
        # healthy/already-running owner.
        return None
    try:
        probe = _InterprocessFileLock(
            _daemon_lock_path(port, "instance"), timeout=0.0)
        try:
            probe.acquire()
        except TimeoutError:
            return True
        else:
            probe.release()
            return False
    finally:
        probe_guard.release()


def _instance_owner_result(port: int) -> dict | None:
    """Return a degraded-but-crash-safe ownership proof for a busy daemon."""
    held = _instance_lock_held(port)
    if held is False:
        return None
    if held is None:
        return {
            "action": "ownership-unknown",
            "pid": None,
            "port": port,
            "health": None,
            "health_proof": "instance-lock-unknown",
        }
    return {
        "action": "already-running",
        "pid": None,
        "port": port,
        "health": None,
        "health_proof": "instance-lock",
    }


class _ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """HTTP server that cannot share a listen socket with another PID.

    ``HTTPServer`` sets ``allow_reuse_address = True``.  On Windows that means
    four independently started processes can all LISTEN on 127.0.0.1:8790.
    Disable reuse and request SO_EXCLUSIVEADDRUSE as a second guardrail.
    """

    allow_reuse_address = False
    allow_reuse_port = False
    daemon_threads = True
    request_queue_size = 64

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        return super().server_bind()


def _port() -> int:
    """Fixed port 8790, overridable via the CODESEXTANT_PORT environment variable (aligned with PoC t5 and design doc §3①)."""
    try:
        return int(os.environ.get("CODESEXTANT_PORT", str(DEFAULT_PORT)))
    except ValueError:
        return DEFAULT_PORT


# ── log (observability) ──
def _log_path() -> Path:
    """daemon.log defaults to ~/.codesextant/daemon.log, in the same directory as the SQLite database.
    Overridable via CODESEXTANT_HOME (for test isolation; reuses storage.default_db_dir)."""
    d = storage.default_db_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "daemon.log"


_logger: logging.Logger | None = None
_LOGGER_LOCK = threading.Lock()


class _CopyTruncateRotatingFileHandler(RotatingFileHandler):
    """Rotate without renaming the active file (which Windows readers can lock).

    The stdlib handler renames ``daemon.log`` and each numbered backup.  A
    second process merely reading/opening any of those files can deny delete
    sharing on Windows and make every subsequent log emit print WinError 32.
    Copying to a unique archive and truncating our own open stream avoids both
    rename operations.  Locked stale archives are pruned on a later rollover.
    """

    def doRollover(self):
        if self.stream is None:
            self.stream = self._open()
        self.stream.flush()
        base = Path(self.baseFilename)
        archive = base.with_name(
            f"{base.name}.{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{time.time_ns()}")
        try:
            shutil.copyfile(base, archive)
        except FileNotFoundError:
            return

        self.stream.seek(0)
        self.stream.truncate(0)
        self.stream.seek(0, os.SEEK_END)

        archives = sorted(
            base.parent.glob(f"{base.name}.*"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for stale in archives[self.backupCount:]:
            try:
                stale.unlink()
            except PermissionError:
                pass


def get_logger(*, file_output: bool = False) -> logging.Logger:
    """Return the process logger; only the serving daemon owns ``daemon.log``.

    Wrapper/control-plane processes call ``ensure_running`` too.  Giving each
    one a file handler made them race the real daemon's rollover.  They now log
    to stderr only; ``serve`` explicitly upgrades the singleton with the one
    rotating file handler.
    """
    global _logger
    if (_logger is not None
            and (not file_output or any(
                isinstance(h, _CopyTruncateRotatingFileHandler)
                for h in _logger.handlers))):
        return _logger
    with _LOGGER_LOCK:
        if _logger is None:
            lg = logging.getLogger("codesextant.daemon")
            lg.setLevel(logging.INFO)
            lg.propagate = False
            fmt = logging.Formatter(
                "%(asctime)s [%(levelname)s] pid=%(process)d %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            sh = logging.StreamHandler(sys.stderr)
            sh.setFormatter(fmt)
            lg.addHandler(sh)
            _logger = lg
        else:
            lg = _logger
            fmt = lg.handlers[0].formatter or logging.Formatter("%(message)s")

        if file_output and not any(
                isinstance(h, _CopyTruncateRotatingFileHandler) for h in lg.handlers):
            try:
                fh = _CopyTruncateRotatingFileHandler(
                    _log_path(), maxBytes=2_000_000, backupCount=3, encoding="utf-8")
                fh.setFormatter(fmt)
                lg.addHandler(fh)
            except Exception as exc:  # a failed file handler should not crash the daemon; fall back to stderr only
                sys.stderr.write(
                    f"[codesextant daemon] failed to open log file (falling back to stderr): {exc}\n")
        return lg


# ── liveness probe (strict: checks whether the /health brand matches, not merely whether the port is open) ──
def _health_brand_ok(data: dict) -> bool:
    """Brand match: only counts as "our daemon" if service is codesextant or the product name
    codesextant. (Some other process happening to occupy the same port and returning different
    JSON never counts, aligned with PoC t5 + memory: brain_watchdog only checked a half-dead
    TCP connection; you have to check the /health HTTP response.)"""
    return isinstance(data, dict) and data.get("service") in (SERVICE_NAME, "codesextant")


def http_ping(host: str = HOST, port: int | None = None, timeout: float = 0.6) -> dict | None:
    """Strict liveness probe: sends GET /health and returns the parsed dict (only if the brand
    matches, otherwise None). Returning a dict instead of a bool gives the caller extra info like
    pid (ensure uses this as proof of the singleton)."""
    port = port or _port()
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data if _health_brand_ok(data) else None
    except Exception:
        return None


def is_port_listening(host: str = HOST, port: int | None = None, timeout: float = 0.3) -> bool:
    """Bare TCP liveness probe (only checks whether something is listening on the port, ignores
    brand). For diagnostics/stop decisions only. Singleton determination always uses http_ping
    (strict brand check)."""
    port = port or _port()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _slow_health_timeout(wait_sec: float) -> float:
    """Fast health checks stay cheap; an occupied port gets one slower brand proof.

    A busy but valid daemon can occasionally miss the 0.6s fast probe on a
    loaded Windows desktop.  Treating that as a foreign port makes every Skill
    invocation fail even though the same /health answers moments later.  Keep
    the confirmation bounded and configurable instead of globally inflating
    every five-second supervisor probe.
    """
    try:
        configured = float(os.environ.get(
            "CODESEXTANT_HEALTH_CONFIRM_TIMEOUT_SEC", "3.0"))
    except ValueError:
        configured = 3.0
    return min(max(1.0, configured), max(1.0, float(wait_sec)))


# ── endpoint routing table (table-driven: adding an endpoint means adding one entry, aligned with the code skill's OCP) ──
# Each entry: method → {path: (handler, needs body?)}
def _q(parsed, key: str, default=None):
    """Get a single value from the query string (parse_qs returns a list; take the first item)."""
    vals = parse_qs(parsed.query).get(key)
    return vals[0] if vals else default


def _require_project(project: str | None):
    """Every data endpoint requires project (= repo absolute path). Missing → 400."""
    if not project:
        raise _HttpError(400, "missing required parameter project (= repo absolute path)")
    # queue 3: any project that gets queried automatically gets a file-watcher attached
    # (idempotent; silently a no-op if watchdog is missing).
    # When the switch is off, this is a pure config check that never imports watcher or builds a
    # WatchManager (zero cold-start cost).
    if _watch_enabled_config():
        try:
            _get_watch_mgr().ensure_watch(project)
        except Exception:
            pass
    return project


class _HttpError(Exception):
    """A controlled error carrying an HTTP status code (→ the endpoint returns the matching code + message, not a 500)."""
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


# Each endpoint's implementation takes (parsed_url, body_dict) and returns (code, result_dict)
def _ep_health(parsed, body):
    watch_enabled = _watch_enabled_config()
    return 200, {
        "service": SERVICE_NAME,            # liveness-probe brand
        "product": "CodeSextant",              # public-facing product name (CodeSextant)
        "status": "ok",
        "ready": True,                        # ready field (for the panel/observability)
        "status_text": "service running normally",
        "pid": os.getpid(),
        "port": _port(),
        "engine_version": _engine_pkg_version(),
        "db_dir": str(storage.default_db_dir()),
        "log_file": str(_log_path()),
        "endpoints": [
            "GET /  (panel)",
            "GET /health",
            "GET /projects",
            "GET /get_symbols?project=&file=",
            "POST /find_references {project,symbol}",
            "GET /get_map?project=&budget=",
            "POST /reindex {project,force?}",
            "GET /status?project=",
            "GET /deadcode?project=&file=&lang=",
            "GET /ai_usage?project=&file=",
            "GET /find_unwired?project=&max_fanout=",
            "GET /get_health?project=",
            "GET /comment_overview?project=&file=",
            "GET /comment_tags?project=&tags=&file=",
            "GET /get_comments?project=&file=&scope=&doc_only=&tag=",
            "GET /find_duplicates?project=&file=&near_global=&min_similarity=&calls=",
            "POST /call_hierarchy {project,symbol,direction?,max_hops?}",
            "POST /impact {project,symbol,max_hops?}",
        ],
        "uptime_sec": round(time.time() - _START_TS, 1),
        "watcher": {  # the control plane must not lazy-load watcher/engine just to answer a status query
            "enabled": watch_enabled,
            "watched": (
                list(_WATCH_MGR.watched_snapshot())
                if watch_enabled and _WATCH_MGR is not None else []
            ),
        },
        "heavy_work": _HEAVY_COORDINATOR.snapshot(),
    }


def _engine_pkg_version():
    # Absolute import: when ensure spawns the daemon detached by file path, it runs as __main__
    # (no package context), so a relative import would fail. sys.path has already been patched
    # with parent.parent by this point, so codesextant is guaranteed importable.
    try:
        from codesextant import __version__ as v  # type: ignore
        return v
    except Exception:
        return None


def _watch_enabled_config() -> bool:
    """Read the watcher switch without importing the watcher module."""
    return os.environ.get("CODESEXTANT_WATCH_ENABLED", "1").lower() not in (
        "0", "false", "no", "off")


def _ep_get_symbols(parsed, body):
    project = _require_project(_q(parsed, "project"))
    file = _q(parsed, "file")
    return 200, engine.get_symbols(project, file=file)


def _ep_find_references(parsed, body):
    body = body or {}
    project = _require_project(body.get("project"))
    symbol = body.get("symbol")
    if not symbol:
        raise _HttpError(400, "find_references missing required parameter symbol")
    return 200, engine.find_references(
        project, symbol,
        def_path=body.get("def_path"),
        src_root=body.get("src_root"),
        include_low_confidence=body.get("include_low_confidence", True),
        persist=body.get("persist", True),
    )


def _ep_get_map(parsed, body):
    project = _require_project(_q(parsed, "project"))
    budget_raw = _q(parsed, "budget", "2000")
    try:
        budget = int(budget_raw)
    except (TypeError, ValueError):
        raise _HttpError(400, f"budget must be an integer, got '{budget_raw}'") from None
    # queue 4: query-aware focus (comma-separated; callers explicitly pass the symbols/files they're editing or asking about)
    fsy = _q(parsed, "focus_symbols")
    ffi = _q(parsed, "focus_files")
    fs = [x for x in fsy.split(",") if x] if fsy else None
    ff = [x for x in ffi.split(",") if x] if ffi else None
    return 200, engine.get_map(project, token_budget=budget, focus_symbols=fs, focus_files=ff)


def _ep_reindex(parsed, body):
    body = body or {}
    project = _require_project(body.get("project"))
    force = bool(body.get("force", False))
    return 200, engine.index_project(project, force=force)


def _ep_status(parsed, body):
    project = _require_project(_q(parsed, "project"))
    # pitfall 7-1: git freshness spawns a git subprocess; skip it by default (avoids an
    # unguarded GET being triggered into a spawn storm by a malicious no-cors web page).
    # Panel/client callers pass ?fresh=1 explicitly when they need freshness.
    fresh = str(_q(parsed, "fresh", "") or "").lower() in ("1", "true", "yes", "on")
    return 200, engine.status(project, check_freshness=fresh)


def _ep_projects(parsed, body):
    # List every locally indexed project (no project parameter needed), the data source for the panel's "overview".
    return 200, engine.list_projects()


def _ep_deadcode(parsed, body):
    # step 3: the dead-code clue layer. Runs orphan analysis (real per-symbol resolution) only
    # if file= is given; lang= overrides language inference.
    project = _require_project(_q(parsed, "project"))
    scope_file = _q(parsed, "file")
    lang = _q(parsed, "lang")
    return 200, engine.find_deadcode(project, scope_file=scope_file, lang=lang)


def _ep_ai_usage(parsed, body):
    # ai-usage: scans the repo for which AI/LLM it uses + the three dispatch_policy channels
    # (cli/direct/local). file= given -> scan only that file.
    project = _require_project(_q(parsed, "project"))
    return 200, engine.find_ai_usage(project, scope_file=_q(parsed, "file"))


def _ep_call_hierarchy(parsed, body):
    # competitor-parity queue 1: transitive call chain. POST (more parameters): direction up/down/both, max_hops.
    body = body or {}
    project = _require_project(body.get("project"))
    symbol = body.get("symbol")
    if not symbol:
        raise _HttpError(400, "call_hierarchy missing required parameter symbol")
    return 200, engine.call_hierarchy(
        project, symbol,
        direction=body.get("direction", "both"),
        max_hops=body.get("max_hops"),
        def_path=body.get("def_path"),
        src_root=body.get("src_root"),
        build_edges=body.get("build_edges", True),
    )


def _ep_impact(parsed, body):
    # competitor-parity queue 2: change impact / blast radius (built on top of call_hierarchy(up)).
    body = body or {}
    project = _require_project(body.get("project"))
    symbol = body.get("symbol")
    if not symbol:
        raise _HttpError(400, "impact missing required parameter symbol")
    return 200, engine.impact(
        project, symbol,
        max_hops=body.get("max_hops"),
        def_path=body.get("def_path"),
        src_root=body.get("src_root"),
    )


def _ep_find_unwired(parsed, body):
    # feature A: unwired check (namegraph name-level whole-graph coarse filter for top-level
    # symbols with zero external references).
    project = _require_project(_q(parsed, "project"))
    mf = _q(parsed, "max_fanout")
    max_fanout = None
    if mf:
        try:
            max_fanout = int(mf)
        except (TypeError, ValueError):
            raise _HttpError(400, f"max_fanout must be an integer, got '{mf}'") from None
    return 200, engine.find_unwired(project, max_fanout=max_fanout)


def _ep_get_health(parsed, body):
    # code health: per-symbol code health score (D1 bloat / D3 complexity / D5 duplication -> health, D6 dead code -> dead; a clue, not a decision).
    project = _require_project(_q(parsed, "project"))
    return 200, engine.get_health(project)


def _ep_comment_overview(parsed, body):
    # feature B: repo comment summary (docstring coverage + TODO/FIXME counts + density).
    project = _require_project(_q(parsed, "project"))
    return 200, engine.get_comment_overview(project, scope_file=_q(parsed, "file"))


def _ep_comment_tags(parsed, body):
    # feature B: TODO/FIXME index (scans line by line for markers, returns real line numbers). tags is comma-separated.
    project = _require_project(_q(parsed, "project"))
    raw = _q(parsed, "tags")
    tags = [t for t in raw.split(",") if t] if raw else None
    return 200, engine.find_comment_tags(project, tags=tags, scope_file=_q(parsed, "file"))


def _ep_get_comments(parsed, body):
    # feature B: precisely filtered comment retrieval (see only what you asked for).
    project = _require_project(_q(parsed, "project"))
    doc_only = str(_q(parsed, "doc_only", "") or "").lower() in ("1", "true", "yes", "on")
    return 200, engine.get_comments(project, file=_q(parsed, "file"),
                                    scope=_q(parsed, "scope"), doc_only=doc_only,
                                    tag=_q(parsed, "tag"))


def _ep_find_duplicates(parsed, body):
    # feature B: duplicate/similarity detection. near_global=opt-in global near-match, calls=enable
    # call_pattern, min_similarity overrides the threshold.
    project = _require_project(_q(parsed, "project"))
    near = str(_q(parsed, "near_global", "") or "").lower() in ("1", "true", "yes", "on")
    calls = str(_q(parsed, "calls", "") or "").lower() in ("1", "true", "yes", "on")
    ms_raw = _q(parsed, "min_similarity")
    ms = None
    if ms_raw:
        try:
            ms = float(ms_raw)
        except (TypeError, ValueError):
            raise _HttpError(400, f"min_similarity must be a float, got '{ms_raw}'") from None
    return 200, engine.find_duplicates(project, scope_file=_q(parsed, "file"),
                                       near_global=near, min_similarity=ms,
                                       include_call_pattern=calls)


def _ep_graph_data(parsed, body):
    # P0 main path (code-workbench upgrade): pick any repo and generate the graph live (nodes carry
    # full source + layout coordinates + health + community).
    # Lazy-imports graph_api (scipy/networkx are heavy dependencies, so the core engine stays light).
    # ⚠ Synchronous graph generation is slow on large repos (full force index + spectral/louvain
    # layout); P1 will add a git-sha cache.
    import os
    import re
    import sys
    project = _require_project(_q(parsed, "project"))
    name = _q(parsed, "name", "live") or "live"
    if not re.match(r"^[A-Za-z0-9_-]+$", name):   # allowlist guards against path injection into graph_{name}_*.json
        raise _HttpError(400, f"name only allows alphanumerics/underscore/hyphen, got '{name}'")
    poc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_poc_graph_c")
    if poc not in sys.path:
        sys.path.insert(0, poc)
    try:
        import graph_api
        return 200, graph_api.build_graph_data(project, name)
    except _HttpError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _HttpError(500, f"graph_data generation failed: {exc}") from exc


def _ep_links(parsed, body):
    # Phase 1 (LLM WIKI red/blue best-solution decision, 2026-07-09, component B): markdown link
    # hygiene source (wiki linkgraph).
    # Subprocess isolation: if the linter crashes, the daemon does not, and it degrades to
    # available:false (⛔ never throws a 500, never crashes the whole page).
    # Excludes the full backlinks table by default (P7 breadth gate: the panel only needs the
    # dangling/orphan summary); pass ?full=1 for the full set.
    import json as _json
    import os
    import subprocess
    import sys
    script = os.path.join(os.path.expanduser("~"), ".claude", "skills", "handoff-tick",
                          "scripts", "lint_links.py")
    if not os.path.exists(script):
        return 200, {"available": False, "reason": f"lint_links.py does not exist: {script}"}
    try:
        _lk_kw = {"capture_output": True, "timeout": 60}
        if os.name == "nt":
            _lk_kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW (aligned with deadcode/engine/references, no console flash)
        r = subprocess.run([sys.executable, "-X", "utf8", script, "--json"], **_lk_kw)
        if r.returncode == 3:  # a failed scan is never treated as green (linter contract)
            return 200, {"available": False,
                         "reason": f"linkgraph exit 3: {r.stderr.decode('utf-8', errors='replace')[:300]}"}
        data = _json.loads(r.stdout.decode("utf-8", errors="replace") or "{}")
    except Exception as exc:  # noqa: BLE001
        return 200, {"available": False, "reason": f"linkgraph scan failed: {exc}"}
    data["available"] = True
    data["exit_code"] = r.returncode  # 0 clean / 1 dangling / 2 orphan only
    if _q(parsed, "full") != "1":
        data.pop("backlinks", None)
    # External discipline-audit log tail (optional source; decision K: only shown if data exists,
    # labeled "no contract" instead of left blank when empty).
    # ⛔ Does not assume any external tool's directory exists: CodeSextant is a standalone product;
    # anyone who wants this points to their own path (env CODESEXTANT_DISCIPLINE_LOG, accepts any
    # line-delimited JSON audit log).
    # Unset = this section simply isn't shown; that is not an error.
    dj = os.environ.get("CODESEXTANT_DISCIPLINE_LOG", "")
    # Also return the actual source path: when the panel shows "where did this data come from" it
    # has to tell the truth; hardcoding a guessed path would mislead the reader into looking for
    # a file that doesn't exist.
    data["discipline_source"] = dj or None
    try:
        if dj and os.path.exists(dj) and os.path.getsize(dj) > 0:
            with open(dj, encoding="utf-8", errors="replace") as f:
                data["discipline_tail"] = [ln.strip() for ln in f.readlines()[-5:]]
        else:
            data["discipline_tail"] = None  # no contract
    except OSError:
        data["discipline_tail"] = None
    return 200, data


# routing table: method → {path: (handler)}
_ROUTES_GET = {
    "/health": _ep_health,
    "/get_symbols": _ep_get_symbols,
    "/get_map": _ep_get_map,
    "/status": _ep_status,
    "/projects": _ep_projects,
    "/deadcode": _ep_deadcode,
    "/ai_usage": _ep_ai_usage,
    "/find_unwired": _ep_find_unwired,
    "/get_health": _ep_get_health,
    "/comment_overview": _ep_comment_overview,
    "/comment_tags": _ep_comment_tags,
    "/get_comments": _ep_get_comments,
    "/find_duplicates": _ep_find_duplicates,
    "/graph_data": _ep_graph_data,
    "/links": _ep_links,
}
_ROUTES_POST = {
    "/find_references": _ep_find_references,
    "/reindex": _ep_reindex,
    "/call_hierarchy": _ep_call_hierarchy,
    "/impact": _ep_impact,
}


_HEAVY_PATHS = frozenset({
    "/get_symbols",
    "/get_map",
    "/deadcode",
    "/ai_usage",
    "/find_unwired",
    "/get_health",
    "/comment_overview",
    "/comment_tags",
    "/get_comments",
    "/find_duplicates",
    "/graph_data",
    "/links",
    "/find_references",
    "/reindex",
    "/call_hierarchy",
    "/impact",
})


def _route_work_key(path: str, parsed, body: dict | None):
    """Canonicalize one request into (single-flight key, admission shard).

    The shard is the repository, so one project's expensive job queues only
    against its own project, not against every other repository on the machine.
    """
    params: dict = {}
    if parsed is not None:
        params.update(parse_qs(parsed.query, keep_blank_values=True))
    if body:
        params.update(body)
    project = params.pop("project", None)
    if isinstance(project, list):
        project = project[0] if project else None
    if path == "/reindex":
        params["force"] = bool(params.get("force", False))
    key = work_coordinator.make_work_key(path, project, params)
    return key, key[1]  # key[1] is the normalized project path


def _execute_route(path: str, handler, parsed, body: dict | None):
    """Keep control endpoints immediate; admit expensive work per repository."""
    if path not in _HEAVY_PATHS:
        return handler(parsed, body)
    key, shard = _route_work_key(path, parsed, body)
    try:
        return _HEAVY_COORDINATOR.run(
            key, lambda: handler(parsed, body), label=path, shard=shard)
    except work_coordinator.HeavyWorkQueueFull as exc:
        raise _HttpError(503, str(exc)) from exc


def _method_hint(path: str, routes: dict) -> str | None:
    """When the path exists but the wrong HTTP method was used, return a hint about which method
    to use; otherwise None.

    Just returning "unknown endpoint" makes people think the endpoint doesn't exist at all and go
    looking for the cause somewhere else. On 2026-07-19 someone (me) wasted a long time that way.
    The path is right there in the other routing table; just say so.
    """
    if routes is _ROUTES_GET and path in _ROUTES_POST:
        return "This endpoint exists, but requires POST, with parameters in the JSON body (not the URL query string)"
    if routes is _ROUTES_POST and path in _ROUTES_GET:
        return "This endpoint exists, but requires GET, with parameters in the URL query string"
    return None


class _Handler(BaseHTTPRequestHandler):
    server_version = "codesextant-daemon/0.1"

    def log_message(self, *a):
        pass  # default access log silenced; we record hits ourselves via the codesextant.daemon logger

    def _send_json(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _send_html(self, code: int, html: str):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _serve_starmap_asset(self, path):
        # code-workbench P0: serves the star-map frontend (/starmap=v3-stunning.html,
        # /graph-common.js=shared JS, /graph_*.json=already-generated static graphs). Same origin
        # (8790) as /graph_data, avoiding cross-port CORS.
        # three.js is loaded from a CDN (vendoring it offline is a carry-forward item).
        import re
        poc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_poc_graph_c")
        if path == "/starmap":
            fn, ctype = "v3-stunning.html", "text/html; charset=utf-8"
        elif path == "/graph-common.js":
            fn, ctype = "graph-common.js", "application/javascript; charset=utf-8"
        elif re.match(r"^/graph_[A-Za-z0-9_]+\.json$", path):   # allowlist guards against path injection
            fn, ctype = path.lstrip("/"), "application/json; charset=utf-8"
        else:
            self._send_json(404, {"error": f"unknown star-map asset {path}", "service": SERVICE_NAME})
            return
        try:
            with open(os.path.join(poc, os.path.basename(fn)), encoding="utf-8") as f:
                body = f.read().encode("utf-8")
        except Exception as exc:  # noqa: BLE001
            self._send_json(404, {"error": f"failed to read star-map asset {fn}: {exc}", "service": SERVICE_NAME})
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise _HttpError(400, f"request body is not valid JSON: {exc}") from exc

    def _dispatch(self, routes: dict, body: dict | None):
        parsed = urlparse(self.path)
        handler = routes.get(parsed.path)
        lg = get_logger()
        if handler is None:
            lg.info("endpoint miss %s %s → 404", self.command, parsed.path)
            payload = {"error": f"unknown endpoint {self.command} {parsed.path}",
                       "service": SERVICE_NAME}
            hint = _method_hint(parsed.path, routes)
            if hint:
                payload["hint"] = hint
            self._send_json(404, payload)
            return
        t0 = time.perf_counter()
        try:
            code, result = _execute_route(parsed.path, handler, parsed, body)
            dt = (time.perf_counter() - t0) * 1000
            # hit log: endpoint + key summary (does not dump the whole result)
            lg.info("endpoint hit %s %s → %d (%.1fms) %s",
                    self.command, parsed.path, code, dt, _summ(result))
            self._send_json(code, result)
        except _HttpError as he:
            lg.warning("endpoint %s %s parameter error → %d: %s",
                       self.command, parsed.path, he.code, he.msg)
            self._send_json(he.code, {"error": he.msg, "service": SERVICE_NAME})
        except Exception as exc:  # a real engine error → 500 + log it (with traceback), never swallow silently
            lg.exception("endpoint %s %s execution failed: %s", self.command, parsed.path, exc)
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}",
                                  "service": SERVICE_NAME})

    def do_GET(self):
        # `/` and `/panel` serve the HTML panel (everything else goes through the table-driven JSON routes)
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/panel"):
            get_logger().info("endpoint hit GET %s → 200 (panel)", parsed.path)
            self._send_html(200, panel.render_panel())
            return
        if (parsed.path in ("/starmap", "/graph-common.js")
                or (parsed.path.startswith("/graph_") and parsed.path.endswith(".json"))):
            # code-workbench P0: the daemon serves the star-map frontend + already-generated static
            # graph JSON from one place (same origin 8790 as /graph_data, avoiding CORS).
            self._serve_starmap_asset(parsed.path)
            return
        self._dispatch(_ROUTES_GET, None)

    def _csrf_check(self) -> bool:
        """Pitfall 7: CSRF protection for POST endpoints. A malicious local web page could send a
        cross-site POST to /reindex (burns CPU + probes whether a directory exists) or
        /find_references (runs jedi): allow local/Tauri/VSCode webview/no-Origin requests, block
        external cross-site http(s) origins. A reasonable hardening for a "zero-credential local
        code map" (does not affect legitimate frontends).
        Switch (L0 hard rule #6): env CODESEXTANT_CSRF_GUARD=0 disables it (enabled by default).
        """
        if os.environ.get("CODESEXTANT_CSRF_GUARD", "1").lower() in ("0", "false", "no", "off"):
            return True
        origin = self.headers.get("Origin")
        if not origin:
            # curl / Python urllib / same-origin simple requests often omit Origin -> allow (this is a local tool)
            return True
        if origin == "null":  # a local panel loaded via file:// (Origin is the literal string "null")
            return True
        # ⚠ Must use urlparse for an exact host match, not a bare startswith prefix; otherwise a
        # malicious domain like http://127.0.0.1.evil.com / http://localhost.attacker.test could
        # bypass this via prefix matching.
        try:
            from urllib.parse import urlparse
            p = urlparse(origin)
        except Exception:
            return False
        # local shell custom schemes: Tauri v1/macOS (tauri://), VSCode webview (vscode-webview://)
        if p.scheme in ("tauri", "vscode-webview"):
            return True
        if p.scheme not in ("http", "https"):
            return False
        host = p.hostname
        # string-form host: localhost, Tauri v2 (Windows/Linux) real Origin https://tauri.localhost
        # (exact match, not endswith, to avoid tauri.localhost.evil.com bypassing this)
        if host in ("localhost", "tauri.localhost"):
            return True
        # IP-form host: use ipaddress for exact loopback detection (covers every ::1 expansion + 127.0.0.0/8)
        try:
            import ipaddress
            if host and ipaddress.ip_address(host).is_loopback:
                return True
        except ValueError:
            pass
        return False

    def do_POST(self):
        if not self._csrf_check():
            get_logger().warning("POST %s CSRF blocked (Origin=%s)",
                                 self.path, self.headers.get("Origin"))
            self._send_json(403, {
                "error": "CSRF: Origin is not on the allowlist (local/Tauri/webview only); "
                         "if this is a legitimate frontend, add it to the allowlist or set env CODESEXTANT_CSRF_GUARD=0",
                "service": SERVICE_NAME})
            return
        try:
            body = self._read_body()
        except _HttpError as he:
            get_logger().warning("POST %s body parse failed → %d: %s",
                                 self.path, he.code, he.msg)
            self._send_json(he.code, {"error": he.msg, "service": SERVICE_NAME})
            return
        self._dispatch(_ROUTES_POST, body)


def _summ(result: dict) -> str:
    """Pull a few key fields out of an endpoint's return value for logging (avoids flooding the log with the entire payload)."""
    if not isinstance(result, dict):
        return ""
    keys = ("count", "indexed", "skipped", "symbols_total", "high_confidence",
            "indexed_files", "symbols", "name_match_file_count", "ready")
    bits = []
    for k in keys:
        if k in result:
            v = result[k]
            v = len(v) if isinstance(v, list) else v
            bits.append(f"{k}={v}")
    return " ".join(bits)


_START_TS = time.time()


def serve(port: int | None = None):
    """Run the HTTP server in the foreground (ensure spawns this detached in the background)."""
    port = port or _port()
    lg = get_logger(file_output=True)
    probe_guard = _InterprocessFileLock(
        _daemon_lock_path(port, "instance-probe"), timeout=1.0)
    try:
        probe_guard.acquire()
    except TimeoutError:
        lg.warning("daemon owner probe state unknown (port=%d) → not starting this time", port)
        return {"action": "ownership-unknown", "port": port, "pid": None}
    try:
        try:
            instance_lock = _InterprocessFileLock(
                _daemon_lock_path(port, "instance"), timeout=0.0)
            instance_lock.acquire()
        except TimeoutError:
            alive = http_ping(port=port)
            lg.warning("duplicate daemon startup blocked (port=%d, existing_pid=%s)",
                       port, (alive or {}).get("pid"))
            return {"action": "already-running", "port": port,
                    "pid": (alive or {}).get("pid")}
    finally:
        probe_guard.release()

    try:
        try:
            srv = _ExclusiveThreadingHTTPServer((HOST, port), _Handler)
        except OSError as exc:
            lg.error("daemon startup failed (port %d may already be in use): %s", port, exc)
            raise
        lg.info("daemon started listening http://%s:%d  service=%s  log=%s",
                HOST, port, SERVICE_NAME, _log_path())
        print(f"[codesextant daemon] listening http://{HOST}:{port} "
              f"(pid={os.getpid()}, service={SERVICE_NAME})")
        # queue 3: attach a file-watcher to every already-indexed project whose path still exists
        # (proactive incremental updates, the map stays fresh)
        if _watch_enabled_config():
            try:
                mgr = _get_watch_mgr()
                for p in storage.list_indexed_projects():
                    if p.get("path_exists") and p.get("repo_path"):
                        mgr.ensure_watch(p["repo_path"])
            except Exception as exc:
                lg.warning("skipped initial watcher attachment: %s", exc)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            lg.info("daemon received interrupt, shutting down")
        finally:
            srv.server_close()
            if _WATCH_MGR is not None:
                try:
                    _WATCH_MGR.stop_all()
                except Exception:
                    pass
            lg.info("daemon shut down")
        return {"action": "stopped", "port": port, "pid": os.getpid()}
    finally:
        instance_lock.release()


# ── idempotent startup (solves the user pain point "spawning a pile of duplicates") ──
def _spawn_daemon(port: int):
    """Spawn one detached daemon process; startup serialization lives above."""
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    creationflags = 0
    kwargs = {}
    if os.name == "nt":
        creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:  # POSIX: start_new_session detaches the daemon from the caller's session
        kwargs["start_new_session"] = True

    env = dict(os.environ)
    env["CODESEXTANT_PORT"] = str(port)
    return subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "serve"],
        creationflags=creationflags,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        env=env,
        **kwargs,
    )


def ensure_running(port: int | None = None, *, wait_sec: float = 6.0) -> dict:
    """Make sure the daemon is running. This is the shared entry point for every agent.

    1) First, a strict liveness probe (/health brand match). Already running -> return
       immediately, ⛔ do not restart it (the core of idempotency).
    2) Not running -> spawn it detached in the background via DETACHED_PROCESS (the daemon
       outlives its caller, shared by other agents).
    3) Poll until it's listening, then return the startup result (with pid, as proof of the singleton).

    Returns a dict: {action, pid, port, ...}
      action in {"already-running", "spawned", "spawn-timeout"}
    """
    port = port or _port()
    lg = get_logger()

    alive = http_ping(port=port)
    if alive is not None:
        lg.info("ensure: detected an existing daemon (pid=%s, port=%d) → idempotent, not restarting",
                alive.get("pid"), port)
        return {"action": "already-running", "pid": alive.get("pid"),
                "port": port, "health": alive}

    owner = _instance_owner_result(port)
    if owner is not None:
        lg.warning(
            "ensure: /health timed out while busy, but the instance lock proves an existing daemon "
            "is still alive (port=%d) → falling back to reuse, not entering the startup lock", port)
        return owner

    # Check-then-spawn must be serialized across agents; otherwise several daemons could be
    # spawned in the same instant. Re-probe liveness inside the lock so later callers simply
    # reuse the PID that started first.
    try:
        with _InterprocessFileLock(
                _daemon_lock_path(port, "startup"), timeout=wait_sec + 0.5):
            alive = http_ping(port=port)
            if alive is not None:
                return {"action": "already-running", "pid": alive.get("pid"),
                        "port": port, "health": alive}

            owner = _instance_owner_result(port)
            if owner is not None:
                lg.warning(
                    "ensure: confirmed inside the startup lock via instance lock that an existing "
                    "daemon is still alive (port=%d) → not restarting", port)
                return owner

            # A listener exists but cannot be verified as CodeSextant, so refuse to bind the same
            # port and cause a split.
            if is_port_listening(port=port):
                # The quick 0.6s health probes above may miss a valid daemon
                # under transient desktop load.  Before declaring a foreign
                # listener, make one bounded slow brand confirmation.
                alive = http_ping(
                    port=port, timeout=_slow_health_timeout(wait_sec))
                if alive is not None:
                    lg.info(
                        "ensure: slow confirmation of an existing daemon (pid=%s, port=%d) → idempotent, not restarting",
                        alive.get("pid"), port)
                    return {"action": "already-running",
                            "pid": alive.get("pid"), "port": port,
                            "health": alive}
                owner = _instance_owner_result(port)
                if owner is not None:
                    lg.warning(
                        "ensure: /health timed out while busy, but the instance lock proves an "
                        "existing daemon still holds port %d → falling back to reuse, not restarting", port)
                    return owner
                lg.error("ensure: port %d is occupied but the /health brand is invalid, refusing to bind again", port)
                return {"action": "port-conflict", "port": port}

            proc = _spawn_daemon(port)
            lg.info("ensure: spawned the daemon detached in the background (spawn pid=%d, port=%d)",
                    proc.pid, port)

            deadline = time.time() + wait_sec
            while time.time() < deadline:
                h = http_ping(port=port)
                if h is not None:
                    lg.info("ensure: daemon is ready (daemon pid=%s, port=%d)",
                            h.get("pid"), port)
                    return {"action": "spawned", "pid": h.get("pid"),
                            "spawn_pid": proc.pid, "port": port, "health": h}
                time.sleep(0.2)

            lg.error("ensure: daemon failed to come up (no /health response within %ss, port=%d)",
                     wait_sec, port)
            return {"action": "spawn-timeout", "spawn_pid": proc.pid, "port": port}
    except TimeoutError:
        alive = http_ping(
            port=port, timeout=_slow_health_timeout(wait_sec))
        if alive is not None:
            return {"action": "already-running", "pid": alive.get("pid"),
                    "port": port, "health": alive}
        owner = _instance_owner_result(port)
        if owner is not None:
            lg.warning(
                "ensure: timed out waiting for the startup lock, but the instance lock proves an "
                "existing daemon is still alive (port=%d) → falling back to reuse", port)
            return owner
        lg.error("ensure: timed out waiting for the startup lock (port=%d)", port)
        return {"action": "startup-lock-timeout", "port": port}


def stop_running(port: int | None = None) -> dict:
    """Stop the local daemon (for cleaning up residue during verification / for restarts).

    Precise kill: uses only the "pid of our own daemon" obtained from /health, plus a Name=python
    check, ⛔ does not match on CommandLine + script name (memory: that once killed its own shell with exit255).
    """
    port = port or _port()
    lg = get_logger()
    alive = http_ping(port=port)
    if alive is None:
        lg.info("stop: no daemon of ours on port %d (nothing to stop)", port)
        return {"action": "not-running", "port": port}
    pid = alive.get("pid")
    if not pid:
        return {"action": "no-pid", "port": port}
    try:
        if os.name == "nt":
            # taskkill /PID /F: kill exactly one process by PID (does not match on script name)
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW: no console flash when the supervisor reaps the daemon
        else:
            os.kill(int(pid), 15)
        lg.info("stop: sent shutdown to daemon pid=%d (port=%d)", pid, port)
    except Exception as exc:
        lg.exception("stop: failed to stop pid=%s: %s", pid, exc)
        return {"action": "kill-failed", "pid": pid, "port": port, "error": str(exc)}

    # confirm the port was released
    for _ in range(15):
        if http_ping(port=port) is None and not is_port_listening(port=port):
            lg.info("stop: daemon stopped, port %d released", port)
            return {"action": "stopped", "pid": pid, "port": port, "port_released": True}
        time.sleep(0.2)
    return {"action": "stopped", "pid": pid, "port": port, "port_released": False}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "ensure"
    if cmd == "serve":
        serve()
        return 0
    if cmd == "ensure":
        r = ensure_running()
        print(json.dumps(r, ensure_ascii=False, default=str))
        return 0 if r["action"] in ("already-running", "spawned") else 1
    if cmd == "ping":
        h = http_ping()
        if h is None:
            print(json.dumps({"running": False}, ensure_ascii=False))
            return 1
        print(json.dumps({"running": True, "pid": h.get("pid"),
                          "port": h.get("port")}, ensure_ascii=False))
        return 0
    if cmd == "stop":
        r = stop_running()
        print(json.dumps(r, ensure_ascii=False, default=str))
        return 0
    print(f"unknown subcommand '{cmd}'. Available: serve | ensure | ping | stop", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
