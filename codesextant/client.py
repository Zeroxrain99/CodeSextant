"""codesextant C3 預留接口 — 給「接入 Skill / 別代理」一行就能查的瘦客戶端。

設計 §2④/§8.1 的 C3 要求：「關鍵字觸發 Skill → 自動確保 daemon 在跑（冪等）
+ 自動帶當前專案 key → 三個查詢介面」。本模組把那三步打包成函數，C3 Skill
（或 Sancio/Hermes 等代理）import 進去直接用，不必各自重寫 HTTP / ensure 邏輯。

典型用法（C3 Skill 內）：
    from codesextant.client import CodesextantClient
    c = CodesextantClient(project=os.getcwd())   # 自動 ensure daemon + 綁當前 repo
    c.ensure()                                # 冪等：沒在跑才背景拉起
    print(c.status())
    print(c.get_map(budget=1500))
    print(c.find_references("check"))

全代理共用：所有 client 打同一個固定 port 的 daemon（單例冪等保證全機一個）。
不依賴第三方（只用標準庫 urllib），方便塞進任何 Skill / 代理環境。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import daemon


class CodesextantClient:
    """瘦 HTTP 客戶端 + 自動冪等 ensure + 自動帶 project。

    參數
    ----
    project : 當前 repo 絕對路徑（C3 Skill 自動帶當前專案＝這個）。
              daemon 端會用 storage.project_key=sha1(abs path) 分庫，不混線。
    port    : daemon port（預設讀 CODESEXTANT_PORT 或 8790）。
    """

    def __init__(self, project: str | None = None, port: int | None = None,
                 timeout: float = 30.0):
        self.project = os.path.abspath(project) if project else None
        self.port = port or daemon._port()
        self.timeout = timeout
        self.base = f"http://{daemon.HOST}:{self.port}"

    # ── 冪等確保（C3 Skill 觸發第一步）──
    def ensure(self) -> dict:
        """確保 daemon 在跑（已在跑就不重開）。回傳 ensure_running 的結果。"""
        return daemon.ensure_running(port=self.port)

    def is_up(self) -> bool:
        return daemon.http_ping(port=self.port) is not None

    # ── HTTP 基本動作 ──
    def _open_json(self, request, *, timeout: float | None = None) -> dict:
        """Open once, self-heal a dead daemon, then retry exactly once.

        HTTPError means the daemon did answer with an application error and is
        deliberately not retried.  Only transport failures trigger ensure.
        """
        request_timeout = self.timeout if timeout is None else timeout
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=request_timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError:
                raise
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
                reason = getattr(exc, "reason", None)
                timed_out = isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError)
                # 長查詢逾時不等於 daemon 掛掉。若 branded /health 仍正常，重送同一查詢只會
                # 製造第二個昂貴工作、把原本的延遲放大成假死；明確回報逾時並交由呼叫端決定。
                if timed_out and daemon.http_ping(port=self.port, timeout=1.0) is not None:
                    raise TimeoutError(
                        "CodeSextant 查詢逾時，但服務仍在線；已停止自動重送以避免重複重查"
                    ) from exc
                if attempt:
                    raise
                recovered = self.ensure()
                # The one-second probe can miss a busy daemon; ensure() then
                # performs the bounded slow brand confirmation.  If it says
                # the original daemon is still alive, retrying the same long
                # query would duplicate expensive work and amplify the stall.
                if timed_out and recovered.get("action") == "already-running":
                    raise TimeoutError(
                        "CodeSextant 查詢逾時，但慢速確認服務仍在線；"
                        "已停止自動重送以避免重複重查"
                    ) from exc
                if recovered.get("action") not in ("already-running", "spawned"):
                    raise RuntimeError(
                        f"CodeSextant daemon 自癒失敗：{recovered.get('action')}"
                    ) from exc
        raise AssertionError("unreachable")

    def _get(self, path: str, params: dict, *, timeout: float | None = None) -> dict:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self.base}{path}?{qs}" if qs else f"{self.base}{path}"
        return self._open_json(url, timeout=timeout)

    def _post(self, path: str, body: dict, *,
              timeout: float | None = None) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}{path}", data=data, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        return self._open_json(req, timeout=timeout)

    def _heavy_timeout(self, specific_env: str | None = None) -> float:
        """Deadline for FIFO queue wait plus one expensive engine operation."""
        raw = os.environ.get(specific_env) if specific_env else None
        if raw is None:
            raw = os.environ.get("CODESEXTANT_HEAVY_TIMEOUT_SEC", "900")
        try:
            configured = float(raw)
        except (TypeError, ValueError):
            try:
                configured = float(os.environ.get(
                    "CODESEXTANT_HEAVY_TIMEOUT_SEC", "900"))
            except ValueError:
                configured = 900.0
        return max(self.timeout, configured)

    def _proj(self, project: str | None) -> str:
        p = project or self.project
        if not p:
            raise ValueError("CodesextantClient：未指定 project（repo 絕對路徑）")
        return os.path.abspath(p)

    # ── 三查詢介面 + 維護介面（對齊 daemon 端點）──
    def health(self) -> dict:
        return self._get("/health", {})

    def status(self, project: str | None = None, *, fresh: bool = False) -> dict:
        # fresh=True → 帶 ?fresh=1 讓 daemon 比對 git HEAD sha 新鮮度（坑6；預設 lazy 不查，
        # 避免不設防 GET 觸發 git spawn）。回傳含 git_stale / indexed_git_sha / current_git_sha。
        return self._get("/status", {"project": self._proj(project),
                                     "fresh": "1" if fresh else None})

    def get_symbols(self, file: str | None = None, project: str | None = None) -> dict:
        return self._get("/get_symbols", {"project": self._proj(project), "file": file},
                         timeout=self._heavy_timeout())

    def get_map(self, budget: int = 2000, project: str | None = None,
                focus_symbols=None, focus_files=None) -> dict:
        # queue 4：focus_symbols/focus_files（list）→ 逗號分隔給 daemon query-aware 排序
        map_timeout = self._heavy_timeout("CODESEXTANT_MAP_TIMEOUT_SEC")
        return self._get("/get_map", {
            "project": self._proj(project), "budget": budget,
            "focus_symbols": ",".join(focus_symbols) if focus_symbols else None,
            "focus_files": ",".join(focus_files) if focus_files else None},
            timeout=map_timeout)

    def find_references(self, symbol: str, *, def_path: str | None = None,
                        src_root: str | None = None, project: str | None = None,
                        include_low_confidence: bool = True,
                        persist: bool = True) -> dict:
        return self._post("/find_references", {
            "project": self._proj(project), "symbol": symbol,
            "def_path": def_path, "src_root": src_root,
            "include_low_confidence": include_low_confidence, "persist": persist,
        }, timeout=self._heavy_timeout())

    def reindex(self, force: bool = False, project: str | None = None) -> dict:
        return self._post(
            "/reindex", {"project": self._proj(project), "force": force},
            timeout=self._heavy_timeout("CODESEXTANT_REINDEX_TIMEOUT_SEC"))

    def find_deadcode(self, scope_file: str | None = None, lang: str | None = None,
                      project: str | None = None) -> dict:
        # 序3：死碼線索層。scope_file 給了才跑 orphan（對該檔逐符號真解析）。
        return self._get("/deadcode", {"project": self._proj(project),
                                       "file": scope_file, "lang": lang},
                         timeout=self._heavy_timeout())

    def find_ai_usage(self, scope_file: str | None = None,
                      project: str | None = None) -> dict:
        # ai-usage：掃 repo 用了哪些 AI/LLM + dispatch_policy cli/direct/local 三通道。
        return self._get("/ai_usage", {"project": self._proj(project), "file": scope_file},
                         timeout=self._heavy_timeout())

    def find_unwired(self, max_fanout: int | None = None,
                     project: str | None = None) -> dict:
        # 功能 A：未接線檢查（namegraph 名稱級全圖粗篩零外部引用頂層符號；低信心線索層）。
        return self._get("/find_unwired", {"project": self._proj(project),
                                           "max_fanout": max_fanout},
                         timeout=self._heavy_timeout())

    def get_health(self, project: str | None = None) -> dict:
        # 紀律轉美：per-symbol 代碼健康度（低=該讀碼複核處；線索非決策、⛔不出應刪）。
        return self._get("/get_health", {"project": self._proj(project)},
                         timeout=self._heavy_timeout())

    # ── 功能 B：註解管理 + 重複偵測 ──
    def get_comment_overview(self, file: str | None = None, project: str | None = None) -> dict:
        return self._get("/comment_overview", {"project": self._proj(project), "file": file},
                         timeout=self._heavy_timeout())

    def find_comment_tags(self, tags: list[str] | None = None, file: str | None = None,
                          project: str | None = None) -> dict:
        return self._get("/comment_tags", {"project": self._proj(project), "file": file,
                                           "tags": ",".join(tags) if tags else None},
                         timeout=self._heavy_timeout())

    def get_comments(self, file: str | None = None, scope: str | None = None,
                     doc_only: bool = False, tag: str | None = None,
                     project: str | None = None) -> dict:
        return self._get("/get_comments", {"project": self._proj(project), "file": file,
                                           "scope": scope, "tag": tag,
                                           "doc_only": "1" if doc_only else None},
                         timeout=self._heavy_timeout())

    def find_duplicates(self, file: str | None = None, near_global: bool = False,
                        min_similarity: float | None = None,
                        include_call_pattern: bool = False, project: str | None = None) -> dict:
        # 重複/類似偵測。near_global=全域近似 opt-in、calls=開 call_pattern。
        return self._get("/find_duplicates", {"project": self._proj(project), "file": file,
                                              "near_global": "1" if near_global else None,
                                              "min_similarity": min_similarity,
                                              "calls": "1" if include_call_pattern else None},
                         timeout=self._heavy_timeout())

    def call_hierarchy(self, symbol: str, *, direction: str = "both",
                       max_hops: int | None = None, def_path: str | None = None,
                       src_root: str | None = None, project: str | None = None) -> dict:
        # 競品吸收 queue 1：傳遞呼叫鏈。direction up=callers/down=callees/both。
        return self._post("/call_hierarchy", {
            "project": self._proj(project), "symbol": symbol,
            "direction": direction, "max_hops": max_hops,
            "def_path": def_path, "src_root": src_root},
            timeout=self._heavy_timeout())

    def impact(self, symbol: str, *, max_hops: int | None = None,
               def_path: str | None = None, src_root: str | None = None,
               project: str | None = None) -> dict:
        # 競品吸收 queue 2：改動影響 / blast radius（改 X 會牽動誰）。
        return self._post("/impact", {
            "project": self._proj(project), "symbol": symbol,
            "max_hops": max_hops, "def_path": def_path, "src_root": src_root},
            timeout=self._heavy_timeout())
