"""ai-usage 掃描的偵測目錄（純資料 + 編譯好的 regex）——單一真相源。

只放「怎麼認出某段碼在用哪家 AI/LLM、走哪條通道」的 pattern 與對照表，
不放掃描邏輯（邏輯在 ai_usage.py，本檔零 import engine，避免循環）。

三通道語義（對齊 dispatch_policy「既有代碼審計」+ user 2026-07-16 directive）：
  - cli   ＝合規：走 Claude Code CLI 通道 / <x>-cli subprocess（CC subscription 計費，非 metered）
  - direct＝違規：直呼遠端計費 API（Anthropic / OpenAI / Google 等 metered endpoint）
  - local ＝中性：本地模型（ollama 等 localhost），無計費、非違規（⛔ 不塗紅、誠實標灰）

⚠ 名稱級 regex 偵測＝行級線索、非執行證明：字串拼接 base_url / 動態 import /
   經 wrapper 間接 hit API 會漏；判「違規」前務必人工讀碼確認確實走 metered endpoint。
   （對齊 deadcode.py「寧誠實線索、不自信假陽性」命門。）

維護：新增廠商只改本檔（PROVIDER_META + OPENAI_COMPAT_HOST_MAP + SITE_RULES），
掃描邏輯不動（開放封閉，對齊既有 code skill OCP）。
"""
from __future__ import annotations

import re

# ── provider 顯示中繼資料（節點 label / 首字母的單一真相源）──
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
    """回某 provider 的顯示資料；未知 provider 誠實給 fallback（首字母大寫）。"""
    m = PROVIDER_META.get(pid)
    if m:
        return m
    return {"label": pid[:1].upper() + pid[1:] if pid else "?",
            "initial": (pid[:1] or "?").upper()}


# ── OpenAI-compat base_url host → 真正 provider ──
# DeepSeek / Groq / Ollama 等常騎 openai SDK、靠 base_url 分家；不查 base_url 會全誤判成 OpenAI。
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

# 本地 host（→ channel=local、無計費）
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

# base_url = "..." / baseURL: "..."（Python + JS/TS 兩式）
BASE_URL_RE = re.compile(r"""base[_]?url\s*[=:]\s*["']([^"']+)["']""", re.I)


# ── import 標記（file context：判斷該檔拉了哪家 base SDK，供共用呼叫簽名解析 provider）──
# 值＝context marker（不直接產 site，只當上下文；langchain/cc 另在 SITE_RULES 直接產 site）。
IMPORT_MARKERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:from\s+anthropic\b|import\s+anthropic\b|@anthropic-ai/sdk)"), "anthropic"),
    (re.compile(r"""(?:from\s+openai\b|import\s+openai\b|from\s+["']openai["']|require\(\s*["']openai["']\s*\))"""), "openai"),
    (re.compile(r"(?:google\.generativeai|from\s+google\s+import\s+genai|import\s+google\.generativeai|@google/gen(?:erative-)?ai)"), "google"),
    (re.compile(r"(?:from\s+groq\b|import\s+groq\b|@ai-sdk/groq)"), "groq"),
    (re.compile(r"(?:from\s+mistralai\b|import\s+mistralai\b|@mistralai/)"), "mistral"),
    (re.compile(r"(?:from\s+cohere\b|import\s+cohere\b)"), "cohere"),
]


# ── SITE_RULES：直接產生一個「呼叫點」的 pattern ──
# 每筆 (compiled_regex, kind, need_import)：
#   kind        → ai_usage._resolve() 據此決定 (provider, channel, compliance)
#   need_import → 該 file 必須偵測到此 base SDK import 才算數（FP 護欄；None=無條件）
# 順序＝優先序（每行取第一個命中，避免同行重複計）：cli → wrapper → ctor → create → host。
SITE_RULES: list[tuple[re.Pattern[str], str, str | None]] = [
    # 1) 合規 CLI 通道（channel=cli）
    (re.compile(r"(?:claude_code_sdk|claude_agent_sdk|@anthropic-ai/claude-code)"), "cc_sdk", None),
    (re.compile(r"""\bAgent\s*\([^)]*model\s*[=:]\s*["'](?:claude|opus|sonnet|haiku)""", re.I), "cc_agent", None),
    (re.compile(r"""(?:claude\s+--print|["']claude["']\s*,\s*["']--print["']|subprocess[.\w]*\([^)]*["']claude["'])"""), "claude_subprocess", None),
    (re.compile(r"""subprocess[.\w]*\([^)]*["']([a-z0-9_]+)-cli["']"""), "generic_cli", None),
    # 2) langchain wrapper（走 API metered endpoint = 違規 direct）
    (re.compile(r"(?:langchain_anthropic|@langchain/anthropic|\bChatAnthropic\b)"), "langchain_anthropic", None),
    (re.compile(r"(?:langchain_openai|@langchain/openai|\bChatOpenAI\b)"), "langchain_openai", None),
    # 3) 建構子（需對應 import；OpenAI ctor 走 base_url 消歧）
    (re.compile(r"\b(?:Async)?Anthropic\s*\("), "anthropic_ctor", "anthropic"),
    (re.compile(r"\b(?:Async)?OpenAI\s*\("), "openai_ctor", "openai"),
    # 4) 共用呼叫簽名（需對應 import；⛔ 永不單獨當 provider，繼承檔內解析）
    (re.compile(r"\.messages\.create\b"), "anthropic_msg_create", "anthropic"),
    (re.compile(r"\.chat\.completions\.create\b"), "openai_chat_create", "openai"),
    (re.compile(r"\.generate_content\b"), "google_generate", "google"),
    # 5) API host 字面（direct；host 本身即證據，無需 import）
    (re.compile(r"api\.anthropic\.com"), "anthropic_host", None),
    (re.compile(r"api\.openai\.com"), "openai_host", None),
    (re.compile(r"generativelanguage\.googleapis\.com"), "google_host", None),
    (re.compile(r"api\.groq\.com"), "groq_host", None),
    (re.compile(r"api\.deepseek\.com"), "deepseek_host", None),
    (re.compile(r"api\.mistral\.ai"), "mistral_host", None),
    (re.compile(r"api\.x\.ai"), "xai_host", None),
    (re.compile(r"api\.cohere\.(?:com|ai)"), "cohere_host", None),
]

# host-kind → provider（direct）對照（step 5 那批）
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

# 通道 → 合規性中文描述（drawer / CLI formatter 用）
COMPLIANCE_LABEL: dict[str, str] = {
    "cli": "CLI subprocess（合規·CC subscription 通道）",
    "direct": "direct API（違規·metered endpoint）",
    "local": "本地模型（無計費·非違規）",
}
