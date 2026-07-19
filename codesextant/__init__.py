"""codesextant — 代碼地圖純引擎（C1）。

對外只暴露 5 個乾淨函數，參數/回傳皆可序列化（dict/list），方便 C2 daemon
包成 HTTP：
    index_project(path)              → /reindex
    get_symbols(path, file)          → /get_symbols
    find_references(path, symbol)    → /find_references
    get_map(path, token_budget)      → /get_map
    status(path)                     → /status   (+ /health 由 daemon 自己給)

混合架構（PoC 坐實）：tree-sitter 全量抽符號（快）+ jedi 按需精解引用（準）
+ SQLite content-hash 增量 + PageRank 重要度。多語言：tree-sitter 抽符號支援 16 種
Python/JS/TS/TSX/Go/Rust/C#/Java/C/C++/Kotlin/Swift/PHP/Ruby/Bash/Lua；找引用
Python→jedi、TS/JS→ts-morph（C5b，Node 子進程橋）、其他語言→名稱比對（低信心、
偵測不到自動 fallback、誠實標示）。

內部 package 名暫用 codesextant（對外產品名查名中，之後再改）。
"""
from __future__ import annotations

import importlib

# C3 只是 HTTP client；匯入它不應連 tree-sitter/engine 一起載。公開 API 以 PEP 562 lazy
# attribute 保持 `from codesextant import get_map` 完全相容，真正第一次取該屬性才載對應模組。
_ENGINE_EXPORTS = {
    "index_project", "get_symbols", "find_references", "find_deadcode",
    "find_unwired", "find_duplicates", "get_comment_overview",
    "find_comment_tags", "get_comments", "call_hierarchy", "impact",
    "get_health", "get_map", "status", "list_projects", "find_ai_usage",
}
_DAEMON_EXPORTS = {
    "ensure_daemon": "ensure_running",
    "ping_daemon": "http_ping",
    "stop_daemon": "stop_running",
}


def __getattr__(name: str):
    if name in _ENGINE_EXPORTS:
        value = getattr(importlib.import_module(".engine", __name__), name)
    elif name == "CodesextantClient":
        value = importlib.import_module(".client", __name__).CodesextantClient
    elif name in _DAEMON_EXPORTS:
        value = getattr(
            importlib.import_module(".daemon", __name__), _DAEMON_EXPORTS[name])
    else:
        # 支援既有 `from codesextant import ranking/namegraph/storage/...`。
        try:
            value = importlib.import_module(f".{name}", __name__)
        except ModuleNotFoundError as exc:
            if exc.name != f"{__name__}.{name}":
                raise
            raise AttributeError(name) from None
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))

__all__ = [
    # C1 純引擎
    "index_project",
    "get_symbols",
    "find_references",
    "find_deadcode",  # C5c 序3：死碼線索層（unused-import + orphan 分級 + entrypoint 豁免）
    "find_unwired",  # 功能 A：未接線檢查（namegraph 名稱級全圖粗篩零外部引用頂層符號）
    "find_duplicates",  # 功能 B：重複/類似偵測（結構指紋 + winnowing）
    "get_comment_overview",  # 功能 B：註解摘要（docstring 覆蓋率/TODO 計數/密度）
    "find_comment_tags",  # 功能 B：TODO/FIXME 索引（真實行號）
    "get_comments",  # 功能 B：精確取註解
    "call_hierarchy",  # 競品吸收 queue 1：傳遞呼叫鏈（refs 表 WITH RECURSIVE CTE）
    "impact",  # 競品吸收 queue 2：改動影響 blast radius（建在 call_hierarchy(up) 上）
    "get_health",  # 紀律轉美：per-symbol 代碼健康度（D1腫脹/D3複雜度/D5重複→health, D6死碼→dead）
    "get_map",
    "status",
    "list_projects",  # C4：列本機所有已索引專案（面板總覽資料源）
    "find_ai_usage",  # ai-usage：repo 用了哪些 AI/LLM + dispatch_policy cli/direct/local 三通道
    # C2 daemon
    "ensure_daemon",
    "ping_daemon",
    "stop_daemon",
    # C3 client
    "CodesextantClient",
]

__version__ = "0.16.0"  # ai-usage action：掃 repo AI/LLM 用量 + dispatch_policy cli/direct/local 三通道 + 深色 HUD 關聯圖（ai_usage.py/ai_usage_patterns.py/ai_usage_html.py 三新模組 + engine/daemon/client/__main__ 接線）。以下為 P5 認知複雜度擴 5 語言（+C/C++/Ruby/Kotlin/Swift，共 11 種高信心；91 cognitive pytest 綠、對抗 review wf_ba17da36）＋2026-06-23 白皮書對齊外部查證（高度對齊 SonarSource、唯一偏差間接遞迴漏算=低估、效度 Muñoz Barón 2020 理解時間 r=0.54 強/正確性 r=−0.13 弱、見 docs/認知複雜度_白皮書對齊與學術效度_查證評估_2026-06-23.md）。P4 認知複雜度語言擴展：cognitive complexity 從 4 語言（Py/JS/TS/TSX）擴到 8（+Go/Rust/Java/C#）。walker 泛化：if_style wrapper（else_clause 包，Py/TS/Rust）vs field（if.alternative 直接指 if，Go/Java/C#，visit_if_field 專責）+ if_types 集合化（Rust=if_expression）+ per-language label_child_types/callee_field；probe 坐實（_probe_if_fields/_probe_labeled/_probe_types，field 名跨 8 語言一致）。黃金案例各語言 sumOfPrimes=7、field-style else-if、switch/match/do/catch/遞迴/跨物件防誤判；269 pytest 零回歸。5-lens distinct 子代理對抗 review 抓 3 bug 全修（CS switch expression 漏算/wrapper 無大括號 then-else 漏增層×2，後者順帶修 P3 既有 TS/JS/TSX game 向量）。v0.13.0=health 接回正式引擎（engine.get_health + health.py 純函數、引擎/PoC 單一真相源）。v0.12.0=P3 D3 認知複雜度初版（4 語言高信心、其餘 None=UNKNOWN）。semver minor，累積不歸零
