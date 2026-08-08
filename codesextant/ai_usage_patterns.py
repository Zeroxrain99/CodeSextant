"""Provider metadata and compiled patterns for AI usage detection.

The scanner in ``ai_usage.py`` uses these tables to identify providers and classify
their channels. Keeping provider metadata, compatible hosts, and call-site patterns in
one module lets new providers be added without changing the scanning logic.

Channels:
  - cli: subscription-backed CLI subprocess
  - direct: remote metered API
  - local: local unmetered model

The patterns provide line-level evidence only. Dynamic imports, constructed URLs, and
indirect wrappers can evade detection, so callers must verify direct-channel findings
against the source and runtime configuration.
"""
from __future__ import annotations

import re

# ── provider display metadata (single source of truth for node label / initial) ──
PROVIDER_META: dict[str, dict[str, str]] = {
    "anthropic": {"label": "Anthropic", "initial": "A"},
    "openai": {"label": "OpenAI", "initial": "O"},
    "google": {"label": "Google Gemini", "initial": "G"},
    "groq": {"label": "Groq", "initial": "G"},
    "deepseek": {"label": "DeepSeek", "initial": "D"},
    "ollama": {"label": "Ollama (local)", "initial": "O"},
    "mistral": {"label": "Mistral", "initial": "M"},
    "cohere": {"label": "Cohere", "initial": "C"},
    "xai": {"label": "xAI Grok", "initial": "X"},
    "together": {"label": "Together", "initial": "T"},
    "fireworks": {"label": "Fireworks", "initial": "F"},
    "openrouter": {"label": "OpenRouter", "initial": "R"},
    "perplexity": {"label": "Perplexity", "initial": "P"},
}


def provider_meta(pid: str) -> dict[str, str]:
    """Return provider display data, with a generated label for unknown providers."""
    m = PROVIDER_META.get(pid)
    if m:
        return m
    return {"label": pid[:1].upper() + pid[1:] if pid else "?",
            "initial": (pid[:1] or "?").upper()}


# ── OpenAI-compat base_url host -> the real provider ──
# DeepSeek / Groq / Ollama etc. often ride the openai SDK and are distinguished only by
# base_url; without checking base_url they'd all be misclassified as OpenAI.
OPENAI_COMPAT_HOST_MAP: dict[str, str] = {
    "api.openai.com": "openai",
    "api.deepseek.com": "deepseek",
    "api.groq.com": "groq",
    "api.x.ai": "xai",
    "api.together.xyz": "together",
    "api.fireworks.ai": "fireworks",
    "openrouter.ai": "openrouter",
    "api.perplexity.ai": "perplexity",
    "api.mistral.ai": "mistral",
}

# Local hosts (-> channel=local, unmetered)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

# base_url = "..." / baseURL: "..." (covers both the Python and JS/TS forms)
BASE_URL_RE = re.compile(r"""base[_]?url\s*[=:]\s*["']([^"']+)["']""", re.I)


# ── import markers (file context: which base SDK this file pulls in, used to resolve a
#    provider from a shared call signature) ──
# value = a context marker (does not produce a site directly, context only; langchain/cc
# separately produce a site directly in SITE_RULES).
IMPORT_MARKERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:from\s+anthropic\b|import\s+anthropic\b|@anthropic-ai/sdk)"), "anthropic"),
    (re.compile(r"""(?:from\s+openai\b|import\s+openai\b|from\s+["']openai["']|require\(\s*["']openai["']\s*\))"""), "openai"),
    (re.compile(r"(?:google\.generativeai|from\s+google\s+import\s+genai|import\s+google\.generativeai|@google/gen(?:erative-)?ai)"), "google"),
    (re.compile(r"(?:from\s+groq\b|import\s+groq\b|@ai-sdk/groq)"), "groq"),
    (re.compile(r"(?:from\s+mistralai\b|import\s+mistralai\b|@mistralai/)"), "mistral"),
    (re.compile(r"(?:from\s+cohere\b|import\s+cohere\b)"), "cohere"),
]


# ── SITE_RULES: patterns that each directly produce a "call site" ──
# Each entry is (compiled_regex, kind, need_import):
#   kind        -> ai_usage._resolve() uses this to decide (provider, channel, compliance)
#   need_import -> the file must be found to import this base SDK for the match to count
#                  (an FP guard; None=unconditional)
# Order = priority (each line takes its first match, to avoid double-counting the same
# line): cli -> wrapper -> ctor -> create -> host.
SITE_RULES: list[tuple[re.Pattern[str], str, str | None]] = [
    # 1) compliant CLI channel (channel=cli)
    (re.compile(r"(?:claude_code_sdk|claude_agent_sdk|@anthropic-ai/claude-code)"), "cc_sdk", None),
    (re.compile(r"""\bAgent\s*\([^)]*model\s*[=:]\s*["'](?:claude|opus|sonnet|haiku)""", re.I), "cc_agent", None),
    (re.compile(r"""(?:claude\s+--print|["']claude["']\s*,\s*["']--print["']|subprocess[.\w]*\([^)]*["']claude["'])"""), "claude_subprocess", None),
    (re.compile(r"""subprocess[.\w]*\([^)]*["']([a-z0-9_]+)-cli["']"""), "generic_cli", None),
    # 2) langchain wrapper (hits a metered API endpoint = a direct violation)
    (re.compile(r"(?:langchain_anthropic|@langchain/anthropic|\bChatAnthropic\b)"), "langchain_anthropic", None),
    (re.compile(r"(?:langchain_openai|@langchain/openai|\bChatOpenAI\b)"), "langchain_openai", None),
    # 3) constructors (needs the matching import; OpenAI ctor is disambiguated via base_url)
    (re.compile(r"\b(?:Async)?Anthropic\s*\("), "anthropic_ctor", "anthropic"),
    (re.compile(r"\b(?:Async)?OpenAI\s*\("), "openai_ctor", "openai"),
    # 4) shared call signatures. Each match requires an import and inherits the provider
    #    resolved from the surrounding file context.
    (re.compile(r"\.messages\.create\b"), "anthropic_msg_create", "anthropic"),
    (re.compile(r"\.chat\.completions\.create\b"), "openai_chat_create", "openai"),
    (re.compile(r"\.generate_content\b"), "google_generate", "google"),
    # 5) literal API hosts (direct; the host itself is the evidence, no import needed)
    (re.compile(r"api\.anthropic\.com"), "anthropic_host", None),
    (re.compile(r"api\.openai\.com"), "openai_host", None),
    (re.compile(r"generativelanguage\.googleapis\.com"), "google_host", None),
    (re.compile(r"api\.groq\.com"), "groq_host", None),
    (re.compile(r"api\.deepseek\.com"), "deepseek_host", None),
    (re.compile(r"api\.mistral\.ai"), "mistral_host", None),
    (re.compile(r"api\.x\.ai"), "xai_host", None),
    (re.compile(r"api\.cohere\.(?:com|ai)"), "cohere_host", None),
]

# host-kind -> provider (direct) lookup table (the step-5 batch)
HOST_KIND_PROVIDER: dict[str, str] = {
    "anthropic_host": "anthropic",
    "openai_host": "openai",
    "google_host": "google",
    "groq_host": "groq",
    "deepseek_host": "deepseek",
    "mistral_host": "mistral",
    "xai_host": "xai",
    "cohere_host": "cohere",
}

# channel -> compliance description (used by the drawer / CLI formatter)
COMPLIANCE_LABEL: dict[str, str] = {
    "cli": "CLI subprocess (compliant, CC subscription channel)",
    "direct": "direct API (violation, metered endpoint)",
    "local": "local model (unmetered, not a violation)",
}
