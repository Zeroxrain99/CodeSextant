"""ai-usage scan layer: "which AI/LLM providers does this repo use, and how does it score
on the dispatch_policy compliance axis".

Consumes the file iterator the engine hands over (SUPPORTED_EXTENSIONS only, noise
directories already skipped), regex-scans file by file, line by line for AI/LLM call
sites. Per file, first collects imports/base_url as context, then resolves each call's
provider and channel (cli/direct/local), and finally assembles a bipartite graph
{file node, provider node, edge} for ai_usage_html to render as a dark HUD relationship
graph.

Three channels (aligned with dispatch_policy's existing-code-audit + the user's
2026-07-16 directive):
  cli   = compliant (Claude Code CLI / <x>-cli subprocess, the CC subscription channel)
  direct= violation (calling a remote metered API directly: Anthropic / OpenAI / Google, etc.)
  local = neutral (a local model on ollama localhost, unmetered)

⛔ The top level does not import engine (engine lazy-imports this module in reverse, to
avoid a cycle).
⚠ Name-level regex = a line-level clue, not proof of execution (read_code_advisory honestly
lays out the blind spot).
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

_SEVERITY = {"direct": 3, "local": 2, "cli": 1}  # an edge/provider takes its "most severe" channel


def _host_of(url: str) -> str:
    """Extract host[:port] from a base_url (urlparse only if a scheme is present; a bare
    host is sliced directly)."""
    u = url.strip()
    try:
        net = urlparse(u).netloc if "://" in u else u.split("/", 1)[0]
    except Exception:
        net = u
    return net.lower()


def _detect_base_url(text: str) -> tuple[str | None, bool]:
    """Scan the whole file for base_url, return (compat_provider, is_local). If there are
    multiple, take the first valid one."""
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
    """Which base SDK this file pulls in (feeds the false-positive guard used when
    resolving a provider from a shared call signature)."""
    found: set[str] = set()
    for rx, marker in IMPORT_MARKERS:
        if rx.search(text):
            found.add(marker)
    return found


def _resolve_openai_call(imports: set[str], base_provider: str | None,
                         base_local: bool) -> tuple[str | None, str]:
    """Resolve the real provider+channel for an openai-style call (OpenAI ctor /
    chat.completions.create).

    base_url is the authority for telling OpenAI-compat providers apart: localhost ->
    ollama/local, a compat host -> that vendor/direct, neither -> plain OpenAI/direct.
    Without this step, DeepSeek/Groq/Ollama riding the openai SDK would all be
    misclassified as OpenAI.
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
    """kind -> (provider, channel). provider=None means there isn't enough context and this
    call should be skipped."""
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
    """A one-line gray description of the file's purpose: prefers the first sentence of the
    module docstring/header comment, otherwise infers one from the directory."""
    for raw in text.splitlines()[:40]:
        s = raw.strip()
        if not s:
            continue
        # First sentence of a Python module docstring / JS-TS header comment
        for pre in ('"""', "'''", "//", "/*", "*", "#"):
            if s.startswith(pre):
                s = s.lstrip('"\'/*# ').strip()
                break
        else:
            # Hit the first line of real code (not a comment) -> stop looking for a
            # docstring, fall back to directory inference
            s = ""
        # Strip trailing docstring/comment closing marks (single-line docstring like
        # \"\"\"desc.\"\"\")
        s = s.rstrip().rstrip('"\'').rstrip("*/").rstrip('"\'').strip()
        if s and len(s) >= 4 and not s.startswith(("import ", "from ", "package ")):
            return s[:48]
    parent = os.path.basename(os.path.dirname(rel)) or "root"
    return f"{parent} · AI consumer"


def _scan_one_file(abs_path: str, rel: str) -> list[dict]:
    """Scan a single file -> sites[{line, provider, channel, snippet, compliance}] (returns
    [] on no match)."""
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
    seen: set[tuple[int, str, str]] = set()  # (line, provider, channel) dedup
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        for rx, kind, need_import in SITE_RULES:
            m = rx.search(line)
            if not m:
                continue
            if need_import and need_import not in imports:
                continue  # FP guard: doesn't count without the matching import (e.g.
                # .generate_content colliding with a test name)
            provider, channel = _resolve(kind, m, imports, base_provider, base_local)
            if not provider:
                continue  # not enough context to resolve a provider -> skip honestly
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
            break  # take the first match per line, to avoid double-counting the same line
    return sites


def scan_ai_usage(root: str, iter_files, *, scope_file: str | None = None) -> dict:
    """Scan which AI/LLM providers a repo uses, plus its dispatch_policy compliance axis.

    root      : the repo's absolute path (goes into meta / used for relative-path math).
    iter_files: an iterable of absolute file paths (engine passes
                _iter_source_files(root); tests may pass a list).
    scope_file: if given, scan only that file (for debugging).

    Returns a dict (json.dumps-able): {meta, nodes, edges, stats, read_code_advisory, verification_reminder}
      - nodes/edges = the bipartite graph (file nodes + provider nodes) that ai_usage_html
        consumes directly
      - stats       = for the CLI text formatter / JSON consumers (site-level counts)
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

    # ── assemble nodes/edges ──
    nodes: list[dict] = []
    edges: list[dict] = []
    prov_channels: dict[str, list[str]] = {}   # provider -> channels it has appeared on
    prov_files: dict[str, set[str]] = {}        # provider -> rel paths of files consuming it

    cli_sites = direct_sites = local_sites = 0
    for fid, (rel, sites) in enumerate(sorted(file_sites.items()), 1):
        # Re-read the original file to get desc (already read once during scan; re-reading
        # 40 lines here is negligible cost; give empty on error)
        abs_p = os.path.join(root, rel)
        try:
            with open(abs_p, encoding="utf-8", errors="replace") as f:
                head = f.read()
        except OSError:
            head = ""
        # aggregate per-file -> provider, take each (file,provider) pair's most severe
        # channel as its edge
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

    # provider nodes (channel = the most severe channel across all its sites)
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
            "The AI-usage scan is a name-level regex line-level clue, not proof of "
            "execution: a concatenated base_url string, a dynamic import, or hitting the "
            "API indirectly through a wrapper can all slip past it. Before flagging "
            "something as direct (a violation), read the code yourself to confirm it "
            "really hits a metered endpoint and not a CLI channel.",
            "Local models (ollama on localhost) are labeled local (unmetered, not a "
            "violation); direct is the metered channel dispatch_policy cares about.",
        ],
        "verification_reminder": (
            "The AI-usage scan gives channel-graded clues, not a compliance verdict: the "
            "billing channel ultimately depends on which endpoint the runtime actually "
            "hits. cli=compliant / direct=violation / local=local, unmetered."
        ),
    }
