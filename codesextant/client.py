"""codesextant C3 reserved interface: a thin client that lets "any Skill / other agent
that wires it in" query CodeSextant in one line.

Implements the C3 requirement from design §2④/§8.1: "a keyword triggers the Skill ->
automatically ensure the daemon is running (idempotent) + automatically attach the
current project's key -> three query interfaces". This module packages those three
steps into functions; a Skill or any other agent just imports it and uses it directly,
without reimplementing the HTTP and ensure logic itself.

Typical usage (inside a C3 Skill):
    from codesextant.client import CodesextantClient
    c = CodesextantClient(project=os.getcwd())   # auto-ensures the daemon + binds the current repo
    c.ensure()                                # idempotent: only spawns in the background if not already running
    print(c.status())
    print(c.get_map(budget=1500))
    print(c.find_references("check"))

Shared across all agents: every client talks to the same daemon on a fixed port (a
singleton, idempotently guaranteed to be one-per-machine). No third-party dependency
(stdlib urllib only), so it's easy to drop into any Skill / agent environment.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import daemon


class CodesextantClient:
    """A thin HTTP client with automatic idempotent ensure + automatic project binding.

    Parameters
    ----------
    project : the current repo's absolute path (this is what a C3 Skill auto-attaches as
              the current project). The daemon side shards storage by
              project_key=sha1(abs path), so projects never cross-contaminate.
    port    : the daemon's port (defaults to reading CODESEXTANT_PORT, or 8790).
    """

    def __init__(self, project: str | None = None, port: int | None = None,
                 timeout: float = 30.0):
        self.project = os.path.abspath(project) if project else None
        self.port = port or daemon._port()
        self.timeout = timeout
        self.base = f"http://{daemon.HOST}:{self.port}"

    # ── idempotent ensure (the first step a C3 Skill triggers) ──
    def ensure(self) -> dict:
        """Ensure the daemon is running (does nothing if it's already up). Returns the
        result of ensure_running."""
        return daemon.ensure_running(port=self.port)

    def is_up(self) -> bool:
        return daemon.http_ping(port=self.port) is not None

    # ── basic HTTP actions ──
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
                # A long query timing out does not mean the daemon is down. If the branded
                # /health still checks out, resending the same query would only create a
                # second expensive job and amplify the original delay into an apparent
                # hang; report the timeout explicitly and let the caller decide.
                if timed_out and daemon.http_ping(port=self.port, timeout=1.0) is not None:
                    raise TimeoutError(
                        "CodeSextant query timed out, but the service is still up; "
                        "auto-resend has been stopped to avoid a duplicate re-query"
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
                        "CodeSextant query timed out, but the slow confirmation says the "
                        "service is still up; auto-resend has been stopped to avoid a "
                        "duplicate re-query"
                    ) from exc
                if recovered.get("action") not in ("already-running", "spawned"):
                    raise RuntimeError(
                        f"CodeSextant daemon self-heal failed: {recovered.get('action')}"
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
            raise ValueError("CodesextantClient: no project specified (repo absolute path)")
        return os.path.abspath(p)

    # ── three query interfaces + maintenance interface (aligned with daemon endpoints) ──
    def health(self) -> dict:
        return self._get("/health", {})

    def status(self, project: str | None = None, *, fresh: bool = False) -> dict:
        # fresh=True -> passes ?fresh=1 so the daemon compares against the git HEAD sha for
        # freshness (pitfall 6; defaults to lazy, not checking, so an unguarded GET can't
        # trigger a git spawn). The response includes git_stale / indexed_git_sha /
        # current_git_sha.
        return self._get("/status", {"project": self._proj(project),
                                     "fresh": "1" if fresh else None})

    def get_symbols(self, file: str | None = None, project: str | None = None) -> dict:
        return self._get("/get_symbols", {"project": self._proj(project), "file": file},
                         timeout=self._heavy_timeout())

    def get_map(self, budget: int = 2000, project: str | None = None,
                focus_symbols=None, focus_files=None) -> dict:
        # queue 4: focus_symbols/focus_files (list) -> comma-joined for the daemon's
        # query-aware ranking
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
        # sequence 3: the dead-code clue layer. orphan only runs (real per-symbol
        # resolution against that file) when scope_file is given.
        return self._get("/deadcode", {"project": self._proj(project),
                                       "file": scope_file, "lang": lang},
                         timeout=self._heavy_timeout())

    def find_ai_usage(self, scope_file: str | None = None,
                      project: str | None = None) -> dict:
        # ai-usage: scan which AI/LLM providers the repo uses + the dispatch_policy
        # cli/direct/local three-channel axis.
        return self._get("/ai_usage", {"project": self._proj(project), "file": scope_file},
                         timeout=self._heavy_timeout())

    def find_unwired(self, max_fanout: int | None = None,
                     project: str | None = None) -> dict:
        # Feature A: unwired check (a coarse namegraph name-level, whole-graph filter for
        # top-level symbols with zero external references; a low-confidence clue layer).
        return self._get("/find_unwired", {"project": self._proj(project),
                                           "max_fanout": max_fanout},
                         timeout=self._heavy_timeout())

    def get_health(self, project: str | None = None) -> dict:
        # Discipline-to-beauty: per-symbol code health (low = a spot worth reading and
        # double-checking; a clue, not a verdict, and ⛔ never emits a "should delete").
        return self._get("/get_health", {"project": self._proj(project)},
                         timeout=self._heavy_timeout())

    # ── Feature B: comment management + duplicate detection ──
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
        # Duplicate/similarity detection. near_global=opt-in global approximate matching,
        # calls=turns on call_pattern.
        return self._get("/find_duplicates", {"project": self._proj(project), "file": file,
                                              "near_global": "1" if near_global else None,
                                              "min_similarity": min_similarity,
                                              "calls": "1" if include_call_pattern else None},
                         timeout=self._heavy_timeout())

    def call_hierarchy(self, symbol: str, *, direction: str = "both",
                       max_hops: int | None = None, def_path: str | None = None,
                       src_root: str | None = None, project: str | None = None) -> dict:
        # Competitor-feature-absorption queue 1: transitive call chain. direction
        # up=callers/down=callees/both.
        return self._post("/call_hierarchy", {
            "project": self._proj(project), "symbol": symbol,
            "direction": direction, "max_hops": max_hops,
            "def_path": def_path, "src_root": src_root},
            timeout=self._heavy_timeout())

    def impact(self, symbol: str, *, max_hops: int | None = None,
               def_path: str | None = None, src_root: str | None = None,
               project: str | None = None) -> dict:
        # Competitor-feature-absorption queue 2: change impact / blast radius (who gets
        # dragged in if X changes).
        return self._post("/impact", {
            "project": self._proj(project), "symbol": symbol,
            "max_hops": max_hops, "def_path": def_path, "src_root": src_root},
            timeout=self._heavy_timeout())
