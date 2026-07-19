"""ai-usage 掃描層 — 「這個 repo 用了哪些 AI/LLM + dispatch_policy 合規維度」。

吃 engine 傳來的 file iterator（只含 SUPPORTED_EXTENSIONS、已跳雜訊目錄），逐檔逐行
regex 偵測 AI/LLM 呼叫點，per-file 先收集 imports/base_url 當上下文再解析每個呼叫的
provider 與通道（cli/direct/local），最後聚成二分圖 {file 節點, provider 節點, edge}
給 ai_usage_html 渲染成深色 HUD 關聯圖。

三通道（對齊 dispatch_policy 既有代碼審計 + user 2026-07-16）：
  cli   ＝合規（Claude Code CLI / <x>-cli subprocess，CC subscription 通道）
  direct＝違規（直呼遠端 metered API：Anthropic / OpenAI / Google 等）
  local ＝中性（本地模型 ollama localhost，無計費）

⛔ 頂層不 import engine（engine 反向 lazy import 本模組，避免循環）。
⚠ 名稱級 regex＝行級線索非執行證明（read_code_advisory 誠實攤盲區）。
"""
from __future__ import annotations

import datetime
import os
from urllib.parse import urlparse

from .ai_usage_patterns import (
    BASE_URL_RE,
    COMPLIANCE_LABEL,
    HOST_KIND_PROVIDER,
    IMPORT_MARKERS,
    LOCAL_HOSTS,
    OPENAI_COMPAT_HOST_MAP,
    SITE_RULES,
    provider_meta,
)

_SEVERITY = {"direct": 3, "local": 2, "cli": 1}  # edge/provider 取「最嚴重」通道


def _host_of(url: str) -> str:
    """從 base_url 取 host[:port]（帶 scheme 才 urlparse，裸 host 直接切）。"""
    u = url.strip()
    try:
        if "://" in u:
            net = urlparse(u).netloc
        else:
            net = u.split("/", 1)[0]
    except Exception:
        net = u
    return net.lower()


def _detect_base_url(text: str) -> tuple[str | None, bool]:
    """掃全檔 base_url，回 (compat_provider, is_local)。多個取第一個有效的。"""
    base_provider: str | None = None
    base_local = False
    for m in BASE_URL_RE.finditer(text):
        host = _host_of(m.group(1))
        bare = host.split(":", 1)[0]
        if bare in LOCAL_HOSTS or host in LOCAL_HOSTS:
            base_local = True
        elif host in OPENAI_COMPAT_HOST_MAP and base_provider is None:
            base_provider = OPENAI_COMPAT_HOST_MAP[host]
    return base_provider, base_local


def _detect_imports(text: str) -> set[str]:
    """該檔拉了哪家 base SDK（供共用呼叫簽名解析 provider 的 FP 護欄）。"""
    found: set[str] = set()
    for rx, marker in IMPORT_MARKERS:
        if rx.search(text):
            found.add(marker)
    return found


def _resolve_openai_call(imports: set[str], base_provider: str | None,
                         base_local: bool) -> tuple[str | None, str]:
    """openai-style 呼叫（OpenAI ctor / chat.completions.create）解析真 provider+通道。

    base_url 是 OpenAI-compat 分家的權威：localhost→ollama/local、compat host→該廠/direct、
    皆無→純 OpenAI/direct。少了這步，DeepSeek/Groq/Ollama 騎 openai SDK 會全誤判成 OpenAI。
    """
    if base_local:
        return "ollama", "local"
    if base_provider:
        return base_provider, "direct"
    if "openai" in imports:
        return "openai", "direct"
    return None, "direct"


def _resolve(kind: str, match, imports: set[str], base_provider: str | None,
             base_local: bool) -> tuple[str | None, str]:
    """kind → (provider, channel)。provider=None 表示無足夠上下文、該呼叫略過。"""
    if kind in ("cc_sdk", "cc_agent", "claude_subprocess"):
        return "anthropic", "cli"
    if kind == "generic_cli":
        return (match.group(1) or None), "cli"
    if kind == "langchain_anthropic":
        return "anthropic", "direct"
    if kind == "langchain_openai":
        return "openai", "direct"
    if kind in ("anthropic_ctor", "anthropic_msg_create"):
        return "anthropic", "direct"
    if kind in ("openai_ctor", "openai_chat_create"):
        return _resolve_openai_call(imports, base_provider, base_local)
    if kind == "google_generate":
        return "google", "direct"
    if kind in HOST_KIND_PROVIDER:
        return HOST_KIND_PROVIDER[kind], "direct"
    return None, "direct"


def _file_desc(text: str, rel: str) -> str:
    """一行灰字功能敘述：優先取 module docstring/檔頭註解首句，否則由目錄推斷。"""
    for raw in text.splitlines()[:40]:
        s = raw.strip()
        if not s:
            continue
        # Python module docstring / JS-TS 檔頭註解首句
        for pre in ('"""', "'''", "//", "/*", "*", "#"):
            if s.startswith(pre):
                s = s.lstrip('"\'/*# ').strip()
                break
        else:
            # 撞到第一行實碼（非註解）→ 停止找 docstring，走目錄推斷
            s = ""
        # 去尾端 docstring/註解收尾標記（單行 docstring 如 \"\"\"desc.\"\"\"）
        s = s.rstrip().rstrip('"\'').rstrip("*/").rstrip('"\'').strip()
        if s and len(s) >= 4 and not s.startswith(("import ", "from ", "package ")):
            return s[:48]
    parent = os.path.basename(os.path.dirname(rel)) or "root"
    return f"{parent} · AI 消費端"


def _scan_one_file(abs_path: str, rel: str) -> list[dict]:
    """掃單檔 → sites[{line, provider, channel, snippet, compliance}]（無命中回 []）。"""
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    if not text:
        return []

    imports = _detect_imports(text)
    base_provider, base_local = _detect_base_url(text)

    sites: list[dict] = []
    seen: set[tuple[int, str, str]] = set()  # (line, provider, channel) 去重
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        for rx, kind, need_import in SITE_RULES:
            m = rx.search(line)
            if not m:
                continue
            if need_import and need_import not in imports:
                continue  # FP 護欄：缺對應 import 不算（.generate_content 撞測試名等）
            provider, channel = _resolve(kind, m, imports, base_provider, base_local)
            if not provider:
                continue  # 無足夠上下文解析 provider → 誠實略過
            key = (lineno, provider, channel)
            if key in seen:
                break
            seen.add(key)
            sites.append({
                "line": lineno,
                "provider": provider,
                "channel": channel,
                "compliance": COMPLIANCE_LABEL.get(channel, channel),
                "snippet": " ".join(line.split())[:140],
            })
            break  # 每行取第一個命中，避免同行重複計
    return sites


def scan_ai_usage(root: str, iter_files, *, scope_file: str | None = None) -> dict:
    """掃 repo 用了哪些 AI/LLM + dispatch_policy 合規維度。

    root      : repo 絕對路徑（入 meta / 相對路徑計算）。
    iter_files: 可疊代的檔案絕對路徑（engine 傳 _iter_source_files(root)；測試可傳 list）。
    scope_file: 給了才只掃該檔（除錯用）。

    回 dict（可 json.dumps）：{meta, nodes, edges, stats, read_code_advisory, verification_reminder}
      - nodes/edges ＝ ai_usage_html 直接吃的二分圖（file 節點 + provider 節點）
      - stats       ＝ CLI 文字 formatter / JSON 消費者用（site 級計數）
    """
    scope_abs = os.path.abspath(scope_file) if scope_file else None

    file_sites: dict[str, list[dict]] = {}   # rel → sites
    files_total = 0
    for abs_path in iter_files:
        files_total += 1
        if scope_abs and os.path.abspath(abs_path) != scope_abs:
            continue
        sites = _scan_one_file(abs_path, os.path.relpath(abs_path, root))
        if sites:
            rel = os.path.relpath(abs_path, root).replace("\\", "/")
            file_sites[rel] = sites

    # ── 組節點/邊 ──
    nodes: list[dict] = []
    edges: list[dict] = []
    prov_channels: dict[str, list[str]] = {}   # provider → 出現過的通道
    prov_files: dict[str, set[str]] = {}        # provider → 消費它的檔 rel

    cli_sites = direct_sites = local_sites = 0
    for fid, (rel, sites) in enumerate(sorted(file_sites.items()), 1):
        # 讀原檔取 desc（已在 scan 讀過一次，這裡再讀 40 行成本可忽略；出錯給空）
        abs_p = os.path.join(root, rel)
        try:
            with open(abs_p, encoding="utf-8", errors="replace") as f:
                head = f.read()
        except OSError:
            head = ""
        # per-file → provider 聚合，取每個 (file,provider) pair 的最嚴重通道當 edge
        pair_channel: dict[str, str] = {}
        for s in sites:
            p, ch = s["provider"], s["channel"]
            cur = pair_channel.get(p)
            if cur is None or _SEVERITY[ch] > _SEVERITY[cur]:
                pair_channel[p] = ch
            prov_channels.setdefault(p, []).append(ch)
            prov_files.setdefault(p, set()).add(rel)
            if ch == "cli":
                cli_sites += 1
            elif ch == "direct":
                direct_sites += 1
            else:
                local_sites += 1
        providers = sorted(pair_channel)
        f_viol = any(ch == "direct" for ch in pair_channel.values())
        node_id = f"f{fid}"
        nodes.append({
            "id": node_id, "type": "file",
            "label": os.path.basename(rel), "path": rel,
            "desc": _file_desc(head, rel),
            "providers": providers, "violation": f_viol,
            "sites": sites,
        })
        for p, ch in pair_channel.items():
            edges.append({"from": node_id, "to": p, "channel": ch})

    # provider 節點（channel＝其所有 site 的最嚴重通道）
    for p in sorted(prov_channels):
        chans = prov_channels[p]
        worst = max(chans, key=lambda c: _SEVERITY[c])
        meta = provider_meta(p)
        nodes.append({
            "id": p, "type": "provider",
            "label": meta["label"], "initial": meta["initial"],
            "channel": worst, "files": len(prov_files.get(p, ())),
            "violation": "direct" in chans,
        })

    stats = {
        "providers_detected": len(prov_channels),
        "consumer_files": len(file_sites),
        "cli_compliant": cli_sites,
        "dispatch_violations": direct_sites,
        "local": local_sites,
        "total_sites": cli_sites + direct_sites + local_sites,
        "files_scanned": files_total,
    }

    return {
        "meta": {
            "project": root,
            "files_total": files_total,
            "scanned_at": datetime.date.today().isoformat(),
        },
        "nodes": nodes,
        "edges": edges,
        "stats": stats,
        "read_code_advisory": [
            "AI 用量掃描是名稱級 regex 行級線索、非執行證明：字串拼接 base_url / 動態 import / "
            "經 wrapper 間接 hit API 會漏；判 direct（違規）前務必人工讀碼確認確實走 metered "
            "endpoint 而非 CLI 通道。",
            "本地模型（ollama localhost）標為 local（無計費·非違規）；direct 才是 dispatch_policy "
            "關切的計費通道。",
        ],
        "verification_reminder": (
            "AI 用量掃描給的是帶通道分級的線索、非合規定論：計費通道最終看 runtime 實際打哪個 "
            "endpoint。cli=合規 / direct=違規 / local=本地無計費。"
        ),
    }
