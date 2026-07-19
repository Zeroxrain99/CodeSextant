"""codesextant C2 — 單例常駐 daemon（一個本機 HTTP 服務、固定 port、探活冪等啟動、全代理共用）。

把 C1 純引擎（engine.py 的 5 個 API）包成 HTTP 端點，給 Claude / Sancio / Hermes /
PsycheForge / 注入大師等所有代理透過同一組 HTTP 介面共用同一張代碼地圖。

設計來源（皆已坐實）：
  - HTTP 橋模式 ← 注入大師 addon_server.py（ThreadingHTTPServer :8788，已驗證可跑）。
  - 探活冪等啟動 ← PoC t5_singleton_daemon.py + ai_king_ensure_watch + authority-process.ts
    的「啟動前探 /health，brand 對得上就判定已在跑、直接退出不重開」。
  - 多專案分庫隔離 ← storage.project_key = sha1(repo 絕對路徑)（不混線）。

端點（一函數對一端點，全帶 project= repo 絕對路徑）：
    GET  /health                                   → daemon 健康 + 中文就緒欄位
    GET  /get_symbols?project=<repo>&file=<檔>      → engine.get_symbols
    POST /find_references  {project, symbol, ...}   → engine.find_references
    GET  /get_map?project=<repo>&budget=<n>          → engine.get_map
    POST /reindex          {project, force?}         → engine.index_project
    GET  /status?project=<repo>                      → engine.status

可觀測 log（對齊 user「新功能須內建可觀測 log」偏好）：
    啟動 / 每個端點命中 / 錯誤 全落 daemon.log（預設 ~/.codesextant/daemon.log）。

服務識別 brand：service == "codesextant"（探活比對用，防別的程式佔同一 port）。

用法：
    python -m codesextant.daemon serve     # 前景跑 server（測試用）
    python -m codesextant.daemon ensure    # 冪等啟動：沒在跑才 detached 背景拉起
    python -m codesextant.daemon ping      # 嚴格探活（/health brand 比對）
    python -m codesextant.daemon stop      # 關掉本機 daemon（給驗證清殘留用）
"""
from __future__ import annotations

import sys

# Windows console / 子進程 stdout 印中文/emoji 不崩（memory: 連犯兩次的坑）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import importlib
import json
import logging
import os
import socket
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# client 只需 ensure/http_ping；不要在 client import 當下把 tree-sitter 引擎全載入。
# storage 很輕且控制鎖/路徑必需；engine/panel/watcher 到 daemon 真正 serve/端點命中才 lazy 載。
if not __package__:  # pragma: no cover - 直接執行檔案的相容退路
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

# queue 3：file-watcher 單例管理器（lazy 建；daemon 持有，全專案共用）
_WATCH_MGR = None


def _get_watch_mgr():
    global _WATCH_MGR
    if _WATCH_MGR is None:
        _WATCH_MGR = watcher.WatchManager(get_logger())
    return _WATCH_MGR

# ── 服務常數 ──
SERVICE_NAME = "codesextant"          # 探活 brand（也接受 "codesextant" 產品名，見 _health_brand_ok）
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
        self._fh = open(self.path, "a+b")
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
                    # 保留原始鏈：是哪一種 OS 錯誤（權限？磁碟？）決定了該怎麼查，
                    # 只留「lock busy」會把診斷線索丟掉。
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
    """固定 port 8790，可由環境變數 CODESEXTANT_PORT 覆寫（對齊 PoC t5 與設計 §3①）。"""
    try:
        return int(os.environ.get("CODESEXTANT_PORT", str(DEFAULT_PORT)))
    except ValueError:
        return DEFAULT_PORT


# ── log（可觀測性）──
def _log_path() -> Path:
    """daemon.log 預設落 ~/.codesextant/daemon.log，與 SQLite 庫同目錄。
    可用 CODESEXTANT_HOME 覆寫（測試隔離用，沿用 storage.default_db_dir）。"""
    d = storage.default_db_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "daemon.log"


_logger: logging.Logger | None = None
_LOGGER_LOCK = threading.Lock()


def get_logger() -> logging.Logger:
    """單例 logger：落檔（RotatingFileHandler，避免 log 無限長）+ stderr。"""
    global _logger
    if _logger is not None:
        return _logger
    with _LOGGER_LOCK:
        if _logger is not None:
            return _logger
        lg = logging.getLogger("codesextant.daemon")
        lg.setLevel(logging.INFO)
        lg.propagate = False
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] pid=%(process)d %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        try:
            fh = RotatingFileHandler(_log_path(), maxBytes=2_000_000, backupCount=3,
                                     encoding="utf-8")
            fh.setFormatter(fmt)
            lg.addHandler(fh)
        except Exception as exc:  # 落檔失敗也不該炸 daemon，退而只用 stderr
            sys.stderr.write(f"[codesextant daemon] log 落檔失敗（改用 stderr）：{exc}\n")
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        lg.addHandler(sh)
        _logger = lg
        return lg


# ── 探活（嚴格：不只 port 開，還要 /health brand 對得上）──
def _health_brand_ok(data: dict) -> bool:
    """brand 比對：service 是 codesextant 或產品名 codesextant 才算「我們的 daemon」。
    （別的程式剛好佔同一 port、回別的 JSON 一律不算，對齊 PoC t5 + memory:
     brain_watchdog 只檢 TCP 半殘 → 要檢 /health HTTP 回應。）"""
    return isinstance(data, dict) and data.get("service") in (SERVICE_NAME, "codesextant")


def http_ping(host: str = HOST, port: int | None = None, timeout: float = 0.6) -> dict | None:
    """嚴格探活：打 GET /health，回傳解析後的 dict（brand 對才回，否則 None）。
    回 dict 比回 bool 多給呼叫者 pid 等資訊（ensure 拿來證明單例）。"""
    port = port or _port()
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data if _health_brand_ok(data) else None
    except Exception:
        return None


def is_port_listening(host: str = HOST, port: int | None = None, timeout: float = 0.3) -> bool:
    """裸 TCP 探活（只看 port 有沒有人 listen，不看 brand）。
    僅供診斷/stop 判斷用——單例判定一律用 http_ping（嚴格 brand）。"""
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


# ── 端點路由表（table-driven：加端點只塞一筆，對齊 code skill OCP）──
# 每筆：method → {path: (handler, 需要 body?)}
def _q(parsed, key: str, default=None):
    """從 query string 取單值（parse_qs 回 list，取第一個）。"""
    vals = parse_qs(parsed.query).get(key)
    return vals[0] if vals else default


def _require_project(project: str | None):
    """所有資料端點都要 project（=repo 絕對路徑）。缺 → 400。"""
    if not project:
        raise _HttpError(400, "缺少必要參數 project（= repo 絕對路徑）")
    # queue 3：查過的專案自動掛 file-watcher（冪等；watchdog 缺則靜默 no-op）。
    # 開關關閉時走純設定判斷，不 import watcher、不建 WatchManager（冷啟成本歸零）。
    if _watch_enabled_config():
        try:
            _get_watch_mgr().ensure_watch(project)
        except Exception:
            pass
    return project


class _HttpError(Exception):
    """帶 HTTP 狀態碼的受控錯誤（→ 端點回對應 code + 中文訊息，不是 500）。"""
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


# 各端點的實作：吃 (parsed_url, body_dict)，回 (code, result_dict)
def _ep_health(parsed, body):
    watch_enabled = _watch_enabled_config()
    return 200, {
        "service": SERVICE_NAME,            # 探活 brand
        "product": "CodeSextant",              # 對外產品名（CodeSextant）
        "status": "ok",
        "就緒": True,                        # 中文就緒欄位（給之後中文面板/可觀測性）
        "狀態": "服務正常運行中",
        "pid": os.getpid(),
        "port": _port(),
        "engine_version": _engine_pkg_version(),
        "庫目錄": str(storage.default_db_dir()),
        "log檔": str(_log_path()),
        "端點": [
            "GET /  (中文面板)",
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
        "watcher": {  # 控制面不得為狀態查詢而 lazy-load watcher/engine
            "enabled": watch_enabled,
            "watched": (
                list(_WATCH_MGR.watched_snapshot())
                if watch_enabled and _WATCH_MGR is not None else []
            ),
        },
        "heavy_work": _HEAVY_COORDINATOR.snapshot(),
    }


def _engine_pkg_version():
    # 絕對 import：daemon 被 ensure 以「檔路徑」detached 拉起時是 __main__（無 package
    # 脈絡），相對 import 會失敗。此時 sys.path 已補過 parent.parent，codesextant 必可 import。
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
        raise _HttpError(400, "find_references 缺少必要參數 symbol")
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
        raise _HttpError(400, f"budget 必須是整數，收到 '{budget_raw}'") from None
    # queue 4：query-aware focus（逗號分隔；呼叫端顯式傳「在改/在問的符號/檔」）
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
    # 坑7-1：git freshness 會 spawn git 子進程，預設不查（避免不設防 GET 被惡意網頁
    # no-cors 觸發 spawn 風暴）；面板/客戶端要新鮮度時明確帶 ?fresh=1。
    fresh = str(_q(parsed, "fresh", "") or "").lower() in ("1", "true", "yes", "on")
    return 200, engine.status(project, check_freshness=fresh)


def _ep_projects(parsed, body):
    # 列本機所有已索引專案（不需 project 參數）——中文面板「總覽」的資料來源。
    return 200, engine.list_projects()


def _ep_deadcode(parsed, body):
    # 序3：死碼線索層。file= 給了才跑 orphan（對該檔逐符號真解析）；lang= 可覆寫語言推斷。
    project = _require_project(_q(parsed, "project"))
    scope_file = _q(parsed, "file")
    lang = _q(parsed, "lang")
    return 200, engine.find_deadcode(project, scope_file=scope_file, lang=lang)


def _ep_ai_usage(parsed, body):
    # ai-usage：掃 repo 用了哪些 AI/LLM + dispatch_policy cli/direct/local 三通道。file= 給了才只掃該檔。
    project = _require_project(_q(parsed, "project"))
    return 200, engine.find_ai_usage(project, scope_file=_q(parsed, "file"))


def _ep_call_hierarchy(parsed, body):
    # 競品吸收 queue 1：傳遞呼叫鏈。POST(參數多)：direction up/down/both、max_hops。
    body = body or {}
    project = _require_project(body.get("project"))
    symbol = body.get("symbol")
    if not symbol:
        raise _HttpError(400, "call_hierarchy 缺少必要參數 symbol")
    return 200, engine.call_hierarchy(
        project, symbol,
        direction=body.get("direction", "both"),
        max_hops=body.get("max_hops"),
        def_path=body.get("def_path"),
        src_root=body.get("src_root"),
        build_edges=body.get("build_edges", True),
    )


def _ep_impact(parsed, body):
    # 競品吸收 queue 2：改動影響 / blast radius（建在 call_hierarchy(up) 上）。
    body = body or {}
    project = _require_project(body.get("project"))
    symbol = body.get("symbol")
    if not symbol:
        raise _HttpError(400, "impact 缺少必要參數 symbol")
    return 200, engine.impact(
        project, symbol,
        max_hops=body.get("max_hops"),
        def_path=body.get("def_path"),
        src_root=body.get("src_root"),
    )


def _ep_find_unwired(parsed, body):
    # 功能 A：未接線檢查（namegraph 名稱級全圖粗篩「零外部引用」的頂層符號）。
    project = _require_project(_q(parsed, "project"))
    mf = _q(parsed, "max_fanout")
    max_fanout = None
    if mf:
        try:
            max_fanout = int(mf)
        except (TypeError, ValueError):
            raise _HttpError(400, f"max_fanout 必須是整數，收到 '{mf}'") from None
    return 200, engine.find_unwired(project, max_fanout=max_fanout)


def _ep_get_health(parsed, body):
    # 紀律轉美：per-symbol 代碼健康度（D1腫脹/D3複雜度/D5重複→health, D6死碼→dead；線索非決策）。
    project = _require_project(_q(parsed, "project"))
    return 200, engine.get_health(project)


def _ep_comment_overview(parsed, body):
    # 功能 B：repo 註解摘要（docstring 覆蓋率 + TODO/FIXME 計數 + 密度）。
    project = _require_project(_q(parsed, "project"))
    return 200, engine.get_comment_overview(project, scope_file=_q(parsed, "file"))


def _ep_comment_tags(parsed, body):
    # 功能 B：TODO/FIXME 索引（逐行掃 marker 回真實行號）。tags 逗號分隔。
    project = _require_project(_q(parsed, "project"))
    raw = _q(parsed, "tags")
    tags = [t for t in raw.split(",") if t] if raw else None
    return 200, engine.find_comment_tags(project, tags=tags, scope_file=_q(parsed, "file"))


def _ep_get_comments(parsed, body):
    # 功能 B：精確過濾取註解（只看該看的）。
    project = _require_project(_q(parsed, "project"))
    doc_only = str(_q(parsed, "doc_only", "") or "").lower() in ("1", "true", "yes", "on")
    return 200, engine.get_comments(project, file=_q(parsed, "file"),
                                    scope=_q(parsed, "scope"), doc_only=doc_only,
                                    tag=_q(parsed, "tag"))


def _ep_find_duplicates(parsed, body):
    # 功能 B：重複/類似偵測。near_global=全域近似 opt-in、calls=開 call_pattern、min_similarity 覆寫門檻。
    project = _require_project(_q(parsed, "project"))
    near = str(_q(parsed, "near_global", "") or "").lower() in ("1", "true", "yes", "on")
    calls = str(_q(parsed, "calls", "") or "").lower() in ("1", "true", "yes", "on")
    ms_raw = _q(parsed, "min_similarity")
    ms = None
    if ms_raw:
        try:
            ms = float(ms_raw)
        except (TypeError, ValueError):
            raise _HttpError(400, f"min_similarity 必須是浮點數，收到 '{ms_raw}'") from None
    return 200, engine.find_duplicates(project, scope_file=_q(parsed, "file"),
                                       near_global=near, min_similarity=ms,
                                       include_call_pattern=calls)


def _ep_graph_data(parsed, body):
    # P0 正路（代碼工作台升級）：選任意 repo 即時出圖（節點帶完整代碼 + 佈局座標 + health + 社群）。
    # lazy import graph_api（scipy/networkx 重依賴、不污染核心引擎輕量）。
    # ⚠ 同步出圖、大 repo 慢（force 全量 index + spectral/louvain 佈局）；後續 P1 加 git-sha 快取。
    import os
    import re
    import sys
    project = _require_project(_q(parsed, "project"))
    name = _q(parsed, "name", "live") or "live"
    if not re.match(r"^[A-Za-z0-9_-]+$", name):   # 防路徑注入 graph_{name}_*.json
        raise _HttpError(400, f"name 只允許英數/底線/連字號，收到 '{name}'")
    poc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_poc_graph_c")
    if poc not in sys.path:
        sys.path.insert(0, poc)
    try:
        import graph_api
        return 200, graph_api.build_graph_data(project, name)
    except _HttpError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _HttpError(500, f"graph_data 出圖失敗：{exc}") from exc


def _ep_links(parsed, body):
    # Phase 1（LLM WIKI 紅藍最佳解 2026-07-09 裁決·元件B）：md 連結衛生源（wiki linkgraph）。
    # subprocess 隔離：linter 掛了 daemon 不掛——graceful 降級回 available:false（⛔不丟 500 不整頁崩）。
    # 預設不含 backlinks 全表（P7 廣度閘：面板只要 dangling/orphan 摘要）；?full=1 才給全量。
    import json as _json
    import os
    import subprocess
    import sys
    script = os.path.join(os.path.expanduser("~"), ".claude", "skills", "handoff-tick",
                          "scripts", "lint_links.py")
    if not os.path.exists(script):
        return 200, {"available": False, "reason": f"lint_links.py 不存在：{script}"}
    try:
        _lk_kw = {"capture_output": True, "timeout": 60}
        if os.name == "nt":
            _lk_kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW（對齊 deadcode/engine/references·不閃黑窗）
        r = subprocess.run([sys.executable, "-X", "utf8", script, "--json"], **_lk_kw)
        if r.returncode == 3:  # 掃描失敗絕不當綠（linter 契約）
            return 200, {"available": False,
                         "reason": f"linkgraph exit 3：{r.stderr.decode('utf-8', errors='replace')[:300]}"}
        data = _json.loads(r.stdout.decode("utf-8", errors="replace") or "{}")
    except Exception as exc:  # noqa: BLE001
        return 200, {"available": False, "reason": f"linkgraph 掃描失敗：{exc}"}
    data["available"] = True
    data["exit_code"] = r.returncode  # 0 乾淨 / 1 dangling / 2 只 orphan
    if _q(parsed, "full") != "1":
        data.pop("backlinks", None)
    # 外部紀律稽核紀錄 tail（可選源·裁決 K：有資料才顯示、空標「無契約」不留白）
    # ⛔ 不預設任何外部工具的目錄存在：CodeSextant 是獨立產品，這塊要用就自己
    # 指路徑（env CODESEXTANT_DISCIPLINE_LOG，任何逐行 JSON 的稽核檔都吃）。
    # 沒設 = 這塊不顯示，不是錯誤。
    dj = os.environ.get("CODESEXTANT_DISCIPLINE_LOG", "")
    try:
        if dj and os.path.exists(dj) and os.path.getsize(dj) > 0:
            with open(dj, encoding="utf-8", errors="replace") as f:
                data["discipline_tail"] = [ln.strip() for ln in f.readlines()[-5:]]
        else:
            data["discipline_tail"] = None  # 無契約
    except OSError:
        data["discipline_tail"] = None
    return 200, data


# 路由表：method → {path: (handler)}
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
    against its own project — not against every other repository on the machine.
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


class _Handler(BaseHTTPRequestHandler):
    server_version = "codesextant-daemon/0.1"

    def log_message(self, *a):
        pass  # 預設 access log 靜音，我們自己用 codesextant.daemon logger 記命中

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
        # 代碼工作台 P0：serve 星圖前端（/starmap=v3-stunning.html、/graph-common.js=共用 JS、
        # /graph_*.json=已生成靜態圖）。與 /graph_data 同源（8790）免跨埠 CORS。
        # three.js 走 CDN（離線 vendored 為後續 carry-forward）。
        import re
        poc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_poc_graph_c")
        if path == "/starmap":
            fn, ctype = "v3-stunning.html", "text/html; charset=utf-8"
        elif path == "/graph-common.js":
            fn, ctype = "graph-common.js", "application/javascript; charset=utf-8"
        elif re.match(r"^/graph_[A-Za-z0-9_]+\.json$", path):   # 白名單防路徑注入
            fn, ctype = path.lstrip("/"), "application/json; charset=utf-8"
        else:
            self._send_json(404, {"error": f"未知星圖資源 {path}", "service": SERVICE_NAME})
            return
        try:
            with open(os.path.join(poc, os.path.basename(fn)), encoding="utf-8") as f:
                body = f.read().encode("utf-8")
        except Exception as exc:  # noqa: BLE001
            self._send_json(404, {"error": f"星圖資源讀取失敗 {fn}：{exc}", "service": SERVICE_NAME})
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
            raise _HttpError(400, f"請求 body 不是合法 JSON：{exc}") from exc

    def _dispatch(self, routes: dict, body: dict | None):
        parsed = urlparse(self.path)
        handler = routes.get(parsed.path)
        lg = get_logger()
        if handler is None:
            lg.info("端點未命中 %s %s → 404", self.command, parsed.path)
            self._send_json(404, {"error": f"未知端點 {self.command} {parsed.path}",
                                  "service": SERVICE_NAME})
            return
        t0 = time.perf_counter()
        try:
            code, result = _execute_route(parsed.path, handler, parsed, body)
            dt = (time.perf_counter() - t0) * 1000
            # 命中 log：端點 + 關鍵摘要（不刷整包 result）
            lg.info("端點命中 %s %s → %d (%.1fms) %s",
                    self.command, parsed.path, code, dt, _summ(result))
            self._send_json(code, result)
        except _HttpError as he:
            lg.warning("端點 %s %s 參數錯誤 → %d：%s",
                       self.command, parsed.path, he.code, he.msg)
            self._send_json(he.code, {"error": he.msg, "service": SERVICE_NAME})
        except Exception as exc:  # 引擎真錯 → 500 + 落 log（含 traceback），不靜默吞
            lg.exception("端點 %s %s 執行失敗：%s", self.command, parsed.path, exc)
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}",
                                  "service": SERVICE_NAME})

    def do_GET(self):
        # `/` 與 `/panel` 吐中文 HTML 面板（其餘走 table-driven JSON 路由）
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/panel"):
            get_logger().info("端點命中 GET %s → 200 (中文面板)", parsed.path)
            self._send_html(200, panel.render_panel())
            return
        if (parsed.path in ("/starmap", "/graph-common.js")
                or (parsed.path.startswith("/graph_") and parsed.path.endswith(".json"))):
            # 代碼工作台 P0：daemon 統一 serve 星圖前端 + 已生成靜態圖 json（與 /graph_data 同源 8790 免 CORS）。
            self._serve_starmap_asset(parsed.path)
            return
        self._dispatch(_ROUTES_GET, None)

    def _csrf_check(self) -> bool:
        """坑7：POST 端點 CSRF 防護。本機惡意網頁能對 /reindex（吃 CPU+探目錄是否存在）
        /find_references（跑 jedi）發跨站 POST——放行本機/Tauri/VSCode webview/無 Origin，
        擋外部跨站 http(s) origin。對「零金鑰本機代碼地圖」定位＝合理硬化（不影響合法前端）。
        開關（L0 鐵律 #6）：env CODESEXTANT_CSRF_GUARD=0 關閉（預設啟用）。
        """
        if os.environ.get("CODESEXTANT_CSRF_GUARD", "1").lower() in ("0", "false", "no", "off"):
            return True
        origin = self.headers.get("Origin")
        if not origin:
            # curl / Python urllib / 同源簡單請求常不帶 Origin → 放行（本機工具定位）
            return True
        if origin == "null":  # file:// 載入的本機面板（Origin 為字面 "null"）
            return True
        # ⚠ 必須 urlparse 精確比對 host，不可用 startswith 裸前綴——否則惡意域名
        # http://127.0.0.1.evil.com / http://localhost.attacker.test 會被前綴匹配繞過。
        try:
            from urllib.parse import urlparse
            p = urlparse(origin)
        except Exception:
            return False
        # 本機殼自訂 scheme：Tauri v1/macOS（tauri://）、VSCode webview（vscode-webview://）
        if p.scheme in ("tauri", "vscode-webview"):
            return True
        if p.scheme not in ("http", "https"):
            return False
        host = p.hostname
        # 字串型 host：localhost、Tauri v2(Windows/Linux) 真實 Origin https://tauri.localhost
        # （精確比對、非 endswith，避免 tauri.localhost.evil.com 繞回）
        if host in ("localhost", "tauri.localhost"):
            return True
        # IP 型 host：ipaddress 精確判 loopback（涵蓋 ::1 全展開寫法 + 127.0.0.0/8）
        try:
            import ipaddress
            if host and ipaddress.ip_address(host).is_loopback:
                return True
        except ValueError:
            pass
        return False

    def do_POST(self):
        if not self._csrf_check():
            get_logger().warning("POST %s CSRF 擋下（Origin=%s）",
                                 self.path, self.headers.get("Origin"))
            self._send_json(403, {
                "error": "CSRF：Origin 不在放行清單（本機/Tauri/webview only）；"
                         "如為合法前端請加入放行或設 env CODESEXTANT_CSRF_GUARD=0",
                "service": SERVICE_NAME})
            return
        try:
            body = self._read_body()
        except _HttpError as he:
            get_logger().warning("POST %s body 解析失敗 → %d：%s",
                                 self.path, he.code, he.msg)
            self._send_json(he.code, {"error": he.msg, "service": SERVICE_NAME})
            return
        self._dispatch(_ROUTES_POST, body)


def _summ(result: dict) -> str:
    """從端點回傳摘出幾個關鍵欄位寫 log（避免整包刷爆 log）。"""
    if not isinstance(result, dict):
        return ""
    keys = ("count", "indexed", "skipped", "symbols_total", "high_confidence",
            "indexed_files", "symbols", "name_match_file_count", "就緒")
    bits = []
    for k in keys:
        if k in result:
            v = result[k]
            v = len(v) if isinstance(v, list) else v
            bits.append(f"{k}={v}")
    return " ".join(bits)


_START_TS = time.time()


def serve(port: int | None = None):
    """前景跑 HTTP server（ensure 會 detached 背景呼叫這個）。"""
    port = port or _port()
    lg = get_logger()
    probe_guard = _InterprocessFileLock(
        _daemon_lock_path(port, "instance-probe"), timeout=1.0)
    try:
        probe_guard.acquire()
    except TimeoutError:
        lg.warning("daemon owner probe 狀態未知（port=%d）→ 本次不啟動", port)
        return {"action": "ownership-unknown", "port": port, "pid": None}
    try:
        try:
            instance_lock = _InterprocessFileLock(
                _daemon_lock_path(port, "instance"), timeout=0.0)
            instance_lock.acquire()
        except TimeoutError:
            alive = http_ping(port=port)
            lg.warning("daemon 重複啟動已擋下（port=%d, existing_pid=%s）",
                       port, (alive or {}).get("pid"))
            return {"action": "already-running", "port": port,
                    "pid": (alive or {}).get("pid")}
    finally:
        probe_guard.release()

    try:
        try:
            srv = _ExclusiveThreadingHTTPServer((HOST, port), _Handler)
        except OSError as exc:
            lg.error("daemon 啟動失敗（port %d 可能已被占用）：%s", port, exc)
            raise
        lg.info("daemon 啟動 listening http://%s:%d  service=%s  log=%s",
                HOST, port, SERVICE_NAME, _log_path())
        print(f"[codesextant daemon] listening http://{HOST}:{port} "
              f"(pid={os.getpid()}, service={SERVICE_NAME})")
        # queue 3：對已索引且路徑還在的專案掛 file-watcher（主動增量、地圖永遠新鮮）
        if _watch_enabled_config():
            try:
                mgr = _get_watch_mgr()
                for p in storage.list_indexed_projects():
                    if p.get("path_exists") and p.get("repo_path"):
                        mgr.ensure_watch(p["repo_path"])
            except Exception as exc:
                lg.warning("watcher 初始掛載略過：%s", exc)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            lg.info("daemon 收到中斷，準備關閉")
        finally:
            srv.server_close()
            if _WATCH_MGR is not None:
                try:
                    _WATCH_MGR.stop_all()
                except Exception:
                    pass
            lg.info("daemon 已關閉")
        return {"action": "stopped", "port": port, "pid": os.getpid()}
    finally:
        instance_lock.release()


# ── 冪等啟動（解 user 痛點「多開跑一堆」）──
def _spawn_daemon(port: int):
    """Spawn one detached daemon process; startup serialization lives above."""
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    creationflags = 0
    kwargs = {}
    if os.name == "nt":
        creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:  # POSIX：start_new_session 讓 daemon 脫離呼叫者的 session
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
    """確保 daemon 在跑——全代理共用入口。

    1) 先嚴格探活（/health brand 比對）。已在跑 → 直接回，⛔不重開（冪等核心）。
    2) 沒在跑 → DETACHED_PROCESS 背景拉起（daemon 活過呼叫者，給別代理共用）。
    3) 輪詢等它 listen，回啟動結果（含 pid，給單例證據）。

    回傳 dict：{action, pid, port, ...}
      action ∈ {"already-running", "spawned", "spawn-timeout"}
    """
    port = port or _port()
    lg = get_logger()

    alive = http_ping(port=port)
    if alive is not None:
        lg.info("ensure：偵測到既有 daemon（pid=%s, port=%d）→ 冪等不重開",
                alive.get("pid"), port)
        return {"action": "already-running", "pid": alive.get("pid"),
                "port": port, "health": alive}

    owner = _instance_owner_result(port)
    if owner is not None:
        lg.warning(
            "ensure：/health 忙碌逾時，但 instance lock 證明既有 daemon "
            "仍在（port=%d）→ 降級復用、不進啟動鎖", port)
        return owner

    # Check-then-spawn 必須跨代理序列化；否則同一瞬間可拉起多個 daemon。
    # 鎖內再次探活，讓排在後面的呼叫者直接復用第一個成功啟動的 PID。
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
                    "ensure：啟動鎖內以 instance lock 確認既有 daemon "
                    "仍在（port=%d）→ 不重開", port)
                return owner

            # 有 listener 但不是可驗證的 CodeSextant 時，禁止再綁同埠造成分流。
            if is_port_listening(port=port):
                # The quick 0.6s health probes above may miss a valid daemon
                # under transient desktop load.  Before declaring a foreign
                # listener, make one bounded slow brand confirmation.
                alive = http_ping(
                    port=port, timeout=_slow_health_timeout(wait_sec))
                if alive is not None:
                    lg.info(
                        "ensure：慢速確認既有 daemon（pid=%s, port=%d）→ 冪等不重開",
                        alive.get("pid"), port)
                    return {"action": "already-running",
                            "pid": alive.get("pid"), "port": port,
                            "health": alive}
                owner = _instance_owner_result(port)
                if owner is not None:
                    lg.warning(
                        "ensure：/health 忙碌逾時，但 instance lock 證明既有 daemon "
                        "仍持有 port %d → 降級復用、不重開", port)
                    return owner
                lg.error("ensure：port %d 已被占用但 /health brand 無效，拒絕重複綁定", port)
                return {"action": "port-conflict", "port": port}

            proc = _spawn_daemon(port)
            lg.info("ensure：背景 detached 拉起 daemon（spawn pid=%d, port=%d）",
                    proc.pid, port)

            deadline = time.time() + wait_sec
            while time.time() < deadline:
                h = http_ping(port=port)
                if h is not None:
                    lg.info("ensure：daemon 已就緒（daemon pid=%s, port=%d）",
                            h.get("pid"), port)
                    return {"action": "spawned", "pid": h.get("pid"),
                            "spawn_pid": proc.pid, "port": port, "health": h}
                time.sleep(0.2)

            lg.error("ensure：daemon 起不來（%ss 內 /health 無回應，port=%d）",
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
                "ensure：等待啟動鎖逾時，但 instance lock 證明既有 daemon "
                "仍在（port=%d）→ 降級復用", port)
            return owner
        lg.error("ensure：等待啟動鎖逾時（port=%d）", port)
        return {"action": "startup-lock-timeout", "port": port}


def stop_running(port: int | None = None) -> dict:
    """關掉本機 daemon（驗證清殘留 / 重啟用）。

    精準殺：只用 /health 拿到的「我們自己 daemon 的 pid」+ 確認 Name=python，
    ⛔不用 CommandLine match 腳本名（memory: 會殺到自己的 shell exit255）。
    """
    port = port or _port()
    lg = get_logger()
    alive = http_ping(port=port)
    if alive is None:
        lg.info("stop：port %d 上沒有我們的 daemon（無需關閉）", port)
        return {"action": "not-running", "port": port}
    pid = alive.get("pid")
    if not pid:
        return {"action": "no-pid", "port": port}
    try:
        if os.name == "nt":
            # taskkill /PID /F：按 PID 精準殺單一進程（不靠腳本名 match）
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW：supervisor 回收 daemon 時不閃黑窗
        else:
            os.kill(int(pid), 15)
        lg.info("stop：已送出關閉 daemon pid=%d（port=%d）", pid, port)
    except Exception as exc:
        lg.exception("stop：關閉 pid=%s 失敗：%s", pid, exc)
        return {"action": "kill-failed", "pid": pid, "port": port, "error": str(exc)}

    # 確認 port 釋放
    for _ in range(15):
        if http_ping(port=port) is None and not is_port_listening(port=port):
            lg.info("stop：daemon 已停、port %d 已釋放", port)
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
    print(f"未知子命令 '{cmd}'。可用：serve | ensure | ping | stop", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
