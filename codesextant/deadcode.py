"""死碼線索層（C5c）— unused-import（包 ruff/eslint）+ orphan 分級 + entrypoint 豁免。

紅藍 CBUA 最佳解核心紀律（2026-06-19，artifact: CodeSextant_優化_紅藍CBUA最佳解_2026-06-19.md）：
  - ⛔ **不自造裸 tree-sitter AST 差集**判 unused import。紅隊證明那會給「錯誤的刪除許可」：
    副作用 import（`import side_effect`）/ re-export（`from x import y` 給別人用）/
    type-only import 全會被誤判成可刪。改**包 ruff(F401) / eslint**——工作量更小、正確性高一個數量級。
  - ⛔ **verdict 永不出「放心刪」紅燈**。真解析引擎（jedi/ts-morph）不可用 → 回 `UNKNOWN_*`
    （誠實「我不知道」），絕不退化成自信假陽性。**一個誠實的 UNKNOWN 比一個自信的錯誤刪除
    許可有用得多**——這是整個死碼層的設計命門（紅隊 B2：ts-morph 不可用時把整個 TS 專案每個
    export 標可刪＝災難）。
  - orphan 只信 jedi(Python)/ts-morph(TS) 真解析；引擎不可用整個符號回 `UNKNOWN_NO_RESOLVER`。
  - entrypoint/反射入口（pages/route/test_/__main__/裝飾器/__all__）永遠 `PUBLIC_API`、永不進刪除候選。

verdict 分級（icon 給人看、verdict 給程式判）：
  UNKNOWN_NO_RESOLVER ❔  無真 import 解析引擎，不判 orphan（**安全閘**，最危險的退化路徑）
  UNKNOWN_NO_LINTER   ❔  無 ruff/eslint，不判 unused-import
  LIKELY_UNUSED       🟡  真引擎確認零高信心引用 + 非入口（**請人工複核 + 跑 build 再刪**）
  REEXPORT_ONLY       🟡  只在 barrel/__init__ 被 re-export（序4 細分；序3 暫不獨立判）
  PUBLIC_API          ⚪  entrypoint/反射入口/__all__，永不進刪除候選
  KEEP                ✅  有高信心引用

本模組只放**純 helper**（linter 子進程包裝、entrypoint 判定、verdict 分級），不 import engine
（engine → deadcode 單向依賴、避免循環）；orphan 的真解析複用由 engine.find_deadcode 組裝。

開關（L0 鐵律 #6，皆 .lower() 容錯）：
  - CODESEXTANT_DEADCODE_LINTER = ruff | eslint | auto | off（預設 auto：依語言選；off 完全不跑 linter）
  - CODESEXTANT_DEADCODE_ENTRYPOINT_EXTRA = 額外入口路徑片段（os.pathsep 分隔；命中即 PUBLIC_API）
  - CODESEXTANT_DEADCODE_LINT_TIMEOUT = linter 子進程逾時秒（預設 ruff 60 / eslint 120）
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from . import references, symbols

# Windows 子進程不彈黑窗（對齊 references.py / engine.py 的 CREATE_NO_WINDOW）
_CREATE_NO_WINDOW = 0x08000000


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def linter_mode() -> str:
    """linter 模式：ruff | eslint | auto | off（預設 auto）。"""
    m = _env("CODESEXTANT_DEADCODE_LINTER", "auto").lower().strip()
    return m or "auto"


def _lint_timeout(default: float) -> float:
    try:
        v = float(_env("CODESEXTANT_DEADCODE_LINT_TIMEOUT", ""))
        return v if v > 0 else default
    except ValueError:
        return default


# ── unused-import：包 ruff(Python F401) / eslint(TS/JS)，⛔ 不自造裸 AST ──
def _run_ruff_f401(target: str) -> dict:
    """ruff check --select F401（未使用 import）。回 {available, findings|reason}。

    ruff 是事實標準的 Python linter，F401=`imported but unused`，正確處理副作用 import
    （`# noqa`）、`__all__` re-export、TYPE_CHECKING 區塊——遠勝自造 AST 差集。
    """
    if shutil.which("ruff") is None:
        return {"available": False,
                "reason": "未裝 ruff（pip install ruff 後即可偵測 Python 未使用 import）"}
    kw: dict = {"capture_output": True, "timeout": _lint_timeout(60)}
    if os.name == "nt":
        kw["creationflags"] = _CREATE_NO_WINDOW
    try:
        proc = subprocess.run(
            ["ruff", "check", "--select", "F401", "--output-format", "json", target], **kw)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"available": False, "reason": f"ruff 執行失敗：{exc}"}
    # ruff exit 1 = 有 lint 命中（正常），0 = 無命中；>1 = 真錯（config/路徑問題）
    if proc.returncode not in (0, 1):
        err = proc.stderr.decode("utf-8", "replace")[:200] if proc.stderr else ""
        return {"available": False, "reason": f"ruff 退出碼 {proc.returncode}：{err}"}
    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace") or "[]")
    except json.JSONDecodeError:
        return {"available": False, "reason": "ruff 輸出非 JSON（版本過舊？需支援 --output-format json）"}
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
    """eslint --format json，過濾 no-unused-vars / unused-imports 規則命中。

    ⚠ eslint 需專案自帶 config（規則因專案而異，⛔ 不臆測）；無 config / 無 eslint →
    回不可用，呼叫端據此標 UNKNOWN_NO_LINTER（誠實「我不知道」，不亂判）。
    """
    if shutil.which("eslint") is None and shutil.which("npx") is None:
        return {"available": False, "reason": "未裝 eslint/npx（無法偵測 TS/JS 未使用 import）"}
    has_cfg = any(os.path.isfile(os.path.join(root, c)) for c in _ESLINT_CONFIGS)
    if not has_cfg:
        return {"available": False, "reason": "專案無 eslint config，跳過（不臆測 lint 規則）"}
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
        return {"available": False, "reason": f"eslint 執行失敗：{exc}"}
    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace") or "[]")
    except json.JSONDecodeError:
        return {"available": False, "reason": "eslint 輸出非 JSON（config 可能有誤或非 lint 模式）"}
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
    """偵測未使用 import——auto 依語言選 ruff(Python)/eslint(TS/JS)。

    回 dict：
      可用 → {available:True, linter, findings:[{path,line,code,message}]}
      不可用 → {available:False, linter, verdict:"UNKNOWN_NO_LINTER", reason, findings:[]}
      關閉 → {available:False, linter:None, reason:"已關閉", findings:[]}
    ⛔ 不可用一律 UNKNOWN_NO_LINTER（誠實），絕不退化成自造 AST 假陽性。
    """
    mode = linter_mode()
    if mode == "off":
        return {"available": False, "linter": None, "findings": [],
                "reason": "已關閉（CODESEXTANT_DEADCODE_LINTER=off）"}
    is_dir = os.path.isdir(target)
    tlang = lang if lang else (None if is_dir else symbols.language_for_file(target))
    use = mode
    if mode == "auto":
        if tlang in ("typescript", "tsx", "javascript"):
            use = "eslint"
        elif tlang in ("python", None):   # None = 目錄掃描，沿用既有 ruff（限 Python）
            use = "ruff"
        else:
            # 2026-06-22：其他語言（C#/Java/C/C++/Lua/Ruby/PHP/Bash/Kotlin/Swift）無對應
            # unused-import linter（ruff 限 Python、eslint 限 TS/JS）→ 誠實 UNKNOWN，⛔ 不硬跑 ruff
            # 對 .cs/.java 等（會回無檔誤導）。對齊死碼層「寧 UNKNOWN 不假陽性」命門。
            return {"available": False, "linter": None, "findings": [],
                    "verdict": "UNKNOWN_NO_LINTER",
                    "reason": f"語言 '{tlang}' 無 unused-import linter（ruff 限 Python、eslint 限 TS/JS）"}
    if use == "ruff":
        r = _run_ruff_f401(target)
    elif use == "eslint":
        r = _run_eslint_unused(target, root)
    else:
        return {"available": False, "linter": use, "findings": [],
                "verdict": "UNKNOWN_NO_LINTER", "reason": f"未知 linter mode={use}"}
    if r.get("available"):
        return {"available": True, "linter": use, "findings": r["findings"]}
    return {"available": False, "linter": use, "findings": [],
            "verdict": "UNKNOWN_NO_LINTER", "reason": r.get("reason")}


# ── entrypoint / 反射入口判定（修正二）：命中 → PUBLIC_API 永不刪 ──
# 檔名約定（posix-style 路徑上比對；涵蓋 Web 框架路由 + 測試 + 模組入口 + barrel）
_ENTRYPOINT_FILE_PATTERNS = [
    (r"(^|/)pages/", "Next.js/Nuxt pages 路由入口"),
    (r"(^|/)app/.*/(route|page|layout|loading|error|template|default)\.[tj]sx?$",
     "Next.js app router 入口"),
    (r"(^|/)test_[^/]*\.py$", "pytest 測試檔"),
    (r"(^|/)[^/]*_test\.py$", "pytest 測試檔"),
    (r"(^|/)tests?/", "測試目錄"),
    (r"(^|/)conftest\.py$", "pytest conftest"),
    (r"(^|/)__main__\.py$", "Python 模組入口（python -m）"),
    (r"(^|/)setup\.py$", "Python 套件入口"),
    (r"(^|/)manage\.py$", "Django 管理入口"),
    (r"(^|/)index\.[tj]sx?$", "barrel/入口 index"),
    (r"(^|/)main\.[tj]sx?$", "前端應用入口"),
]
# 反射入口裝飾器（Python；符號定義前連續 @裝飾器命中即視為被框架反射呼叫）。
# 紅隊 L3-MEDIUM 修正：改「@<任意物件>.<動詞>」寬鬆匹配，不綁死物件名 app/router——FastAPI
# 慣例物件名常是 api/application、Flask Blueprint 變數名任意（users_bp），且補 FastAPI 常用
# websocket/on_event/exception_handler/middleware。寧可寬鬆豁免（少誤報真入口為死碼），代價是
# 偶爾把非入口裝飾器當入口（漏報一個死碼），符合「誤刪入口後果 >> 漏報一個死碼」的保守取向。
_ENTRYPOINT_DECORATOR_VERBS = (
    "route", "get", "post", "put", "delete", "patch", "options", "head",
    "websocket", "on_event", "exception_handler", "middleware",
    "command", "callback", "group", "task", "fixture", "event",
)
_ENTRYPOINT_DECORATOR_RE = re.compile(
    r"^@\w+(?:\.\w+)*\.(" + "|".join(_ENTRYPOINT_DECORATOR_VERBS) + r")\b")
# 無物件前綴的裸裝飾器（@task/@fixture/@event/@shared_task…）
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
    """解析專案根 pyproject.toml 的 [project.scripts]/[project.gui-scripts]，回 console_scripts
    指向的 func 名集合（"pkg.cli:main" → "main"）。

    紅隊 L3-HIGH：console_scripts 入口是安裝後 wrapper 反射呼叫、源碼裡無人提及它的名 →
    名稱級 external usage 必為 0 → find_unwired 不豁免就會把幾乎每個 CLI 主入口誤報未接線。
    env CODESEXTANT_SCAN_ENTRYPOINTS=0/false/no/off 關閉（預設 on）。讀檔失敗/無 pyproject → 空集合。
    """
    if os.environ.get("CODESEXTANT_SCAN_ENTRYPOINTS", "").lower() in ("0", "false", "no", "off"):
        return set()
    pyproject = os.path.join(root, "pyproject.toml")
    if not os.path.isfile(pyproject):
        return set()
    try:
        import tomllib  # Python 3.11+ 標準庫
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return set()
    funcs: set[str] = set()
    proj = (data.get("project") or {}) if isinstance(data, dict) else {}
    for key in ("scripts", "gui-scripts"):
        for _ep, target in (proj.get(key) or {}).items():
            # target 形如 "pkg.module:func" 或 "pkg.module:obj.method"
            if isinstance(target, str) and ":" in target:
                func = target.split(":", 1)[1].strip().split(".")[0]
                if func:
                    funcs.add(func)
    return funcs


def _has_entrypoint_decorator(source: str, symbol_name: str) -> bool:
    """符號定義（def/class symbol_name）上方連續裝飾器是否含反射入口裝飾器。"""
    lines = source.splitlines()
    pat = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+" + re.escape(symbol_name) + r"\b")
    for i, ln in enumerate(lines):
        if not pat.match(ln):
            continue
        j = i - 1
        while j >= 0:
            stripped = lines[j].strip()
            if not stripped:           # 允許空行夾在裝飾器間
                j -= 1
                continue
            if stripped.startswith("@"):
                if _decorator_hits(stripped):
                    return True
                j -= 1
                continue
            break                       # 撞到非裝飾器非空行 → 停
    return False


def _in_dunder_all(source: str, symbol_name: str) -> bool:
    """符號是否列在 __all__（顯式公開 API、永不刪）。"""
    m = re.search(r"__all__\s*=\s*[\[\(](.*?)[\]\)]", source, re.S)
    if not m:
        return False
    return re.search(r"['\"]" + re.escape(symbol_name) + r"['\"]", m.group(1)) is not None


def is_entrypoint(path: str, *, symbol_name: str | None = None,
                  source: str | None = None) -> tuple[bool, str | None]:
    """某符號是否屬入口/反射呼叫（→ PUBLIC_API、永不進刪除候選）。

    判定順序：檔名約定 → 使用者額外清單 → （給了 source+symbol）裝飾器 / __all__。
    回 (是否入口, 中文原因)。
    """
    posix = path.replace("\\", "/")
    for pat, reason in _ENTRYPOINT_FILE_PATTERNS:
        if re.search(pat, posix):
            return True, reason
    extra = _env("CODESEXTANT_DEADCODE_ENTRYPOINT_EXTRA", "")
    for frag in extra.split(os.pathsep):
        frag = frag.strip()
        if frag and frag in posix:
            return True, "使用者指定入口（CODESEXTANT_DEADCODE_ENTRYPOINT_EXTRA）"
    if source and symbol_name:
        if _has_entrypoint_decorator(source, symbol_name):
            return True, "帶路由/任務/fixture 裝飾器（框架反射入口）"
        if _in_dunder_all(source, symbol_name):
            return True, "列於 __all__（顯式公開 API）"
    return False, None


# ── 真解析引擎可用性（UNKNOWN gate 的判據；修正一安全閘）──
def resolver_available(lang: str | None) -> tuple[bool, str | None]:
    """該語言是否有真 import 解析引擎可判 orphan。

    Python → jedi（隨 package 裝、恆可用）。
    TS/JS  → ts-morph（需 node + node_modules/ts-morph；references.ts_morph_available()）。
    其他   → 無 → 回 False（呼叫端標 UNKNOWN_NO_RESOLVER）。
    """
    if lang in (None, "python"):
        return True, None
    if lang in ("typescript", "tsx", "javascript"):
        if references.ts_morph_available():
            return True, None
        return False, ("TS/JS 需 node + ts-morph 才能真解析 orphan（未備妥）；"
                       "裝好或設 CODESEXTANT_TS_MORPH_DISABLED=0 後可判")
    return False, f"語言 '{lang}' 無真 import 解析引擎（jedi 限 Python、ts-morph 限 TS/JS）"


# ── orphan verdict 分級（修正一）──
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
    """把「某符號的 find_references 結果」分級成 orphan verdict。

    安全閘（兩道，皆「寧 UNKNOWN 不假陽性」）：
      ① engine 不是真解析（jedi/ts-morph）→ UNKNOWN_NO_RESOLVER（紅隊 B2：無引擎不可判可刪）。
      ② 真解析了、但**沒定位到符號定義**（error 或 definition 缺）→ UNKNOWN_UNRESOLVED。
         這條至關重要：high=0 可能是「真沒引用」**也可能是「解析器根本沒定位到定義」**
         （如 jedi 二段式只認 def/class 行、module 級變數賦值 `NAME = ...` 定位不到 → 直接
         error → high=0）。若不擋，module 級常數/變數會被自信誤判 LIKELY_UNUSED（2026-06-19
         序3 實跑 daemon.py SERVICE_NAME/HOST/_ROUTES_GET 假陽性現形）。variable 的真解析待序4。
    只有「真解析 + 有定位到定義 + high=0」才敢給 LIKELY_UNUSED🟡（且仍要人工複核+build）。
    """
    if is_entry:
        return {"verdict": "PUBLIC_API", "icon": _VERDICT_ICON["PUBLIC_API"],
                "reason": entry_reason or "入口/反射呼叫"}
    refs_result = refs_result or {}
    engine = refs_result.get("engine")
    if engine not in ("jedi", "ts-morph"):
        return {"verdict": "UNKNOWN_NO_RESOLVER", "icon": _VERDICT_ICON["UNKNOWN_NO_RESOLVER"],
                "reason": f"無真解析引擎（engine={engine or '無'}），不判定是否可刪"}
    if refs_result.get("error") or not refs_result.get("definition"):
        return {"verdict": "UNKNOWN_UNRESOLVED", "icon": _VERDICT_ICON["UNKNOWN_UNRESOLVED"],
                "reason": ("解析器未定位到此符號定義（如 module 級變數賦值 / 非 def-class 符號），"
                           "high=0 不代表真沒引用 → 不判可刪")}
    high = refs_result.get("high_confidence") or []
    if high:
        # 序4：若全部高信心引用都是 re-export（barrel `export {X} from` / 本檔 `export {X}` 導出、
        # 無真內部消費）→ REEXPORT_ONLY，⛔ 不當真 KEEP（沒人真用）也不誤判 LIKELY_UNUSED
        # （它確實被導出、可能是對外 public API）。jedi（Python）的 high 無 is_reexport 旗標 →
        # all() 為 False → 自然走 KEEP，Python 不受影響。
        if all(h.get("is_reexport") for h in high):
            return {"verdict": "REEXPORT_ONLY", "icon": _VERDICT_ICON["REEXPORT_ONLY"],
                    "reason": (f"{len(high)} 處引用全是 re-export/導出、無真內部消費；"
                               "可能是對外 public API，也可能整條導出鏈皆可刪——請人工複核")}
        real = sum(1 for h in high if not h.get("is_reexport"))
        rx = len(high) - real
        suffix = f"（另 {rx} 處 re-export）" if rx else ""
        return {"verdict": "KEEP", "icon": _VERDICT_ICON["KEEP"],
                "reason": f"{real} 處真消費引用（{engine} 確認）{suffix}"}
    return {"verdict": "LIKELY_UNUSED", "icon": _VERDICT_ICON["LIKELY_UNUSED"],
            "reason": f"{engine} 真解析零高信心引用；請人工複核 + 跑 build 再刪（非自信定論）"}


def verdict_icon(verdict: str) -> str:
    return _VERDICT_ICON.get(verdict, "·")


def read_code_advisory(unused: dict, orphans: list) -> list:
    """序6：依死碼結果的盲區，主動列出「哪些地方工具幫不上、必須你讀碼」。

    ⛔ 工具沉默 ≠ 安全可刪。把 UNKNOWN / 無 linter / LIKELY_UNUSED / REEXPORT_ONLY 的真實
    邊界攤開講，避免用戶誤以為「掃過就等於清乾淨」。死碼層是線索、不是刪除許可。
    """
    notes: list[str] = []
    orphans = orphans or []
    unknown = sum(1 for o in orphans if str(o.get("verdict", "")).startswith("UNKNOWN"))
    likely = sum(1 for o in orphans if o.get("verdict") == "LIKELY_UNUSED")
    reexport = sum(1 for o in orphans if o.get("verdict") == "REEXPORT_ONLY")
    if not unused.get("available"):
        notes.append(f"未使用 import 無法判定（{unused.get('reason')}）——這塊工具沒幫上，"
                     "需裝 ruff/eslint 或人工檢查。")
    if unknown:
        notes.append(f"{unknown} 個符號工具判不出（如 module 級變數、無真解析引擎）——"
                     "工具在此沉默 ⛔ 不代表它們可刪，這些必須你自己讀碼確認。")
    if likely:
        notes.append(f"{likely} 個疑似死碼是『線索非定論』——刪前必讀該符號上下文"
                     "（可能是動態/反射呼叫、對外 API、測試夾具等工具看不到的入口）+ 跑 build/CI。")
    if reexport:
        notes.append(f"{reexport} 個只被 re-export——判斷它是對外公開 API 還是整條導出鏈可刪，"
                     "需讀呼叫端/外部使用方，工具無法替你決定。")
    if not notes:
        notes.append("此次結果無顯著盲區；但死碼判定本質是線索層、刪除仍以人工複核 + build 為準。")
    return notes
