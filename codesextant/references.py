"""引用解析模組 — jedi 二段式 goto（定義在哪）+ get_references（被誰用）。

設計來源（PoC 已坐實，這是整條路線的命脈）：
  - ⛔ 不可全量跑 jedi（18k 檔要 17 分鐘）。jedi 只在「要查某符號定義在哪 /
    被誰用」時按需精解（實測 74 ms/次）。
  - 找引用二段式：
      第一段 = tree-sitter / 文字粗篩，先用「名稱」掃出候選檔（便宜）；
      第二段 = jedi 只對候選檔精解（jedi 對全 repo get_references 太慢）。
  - jedi 精度實測完勝名稱比對（同名 check：名稱比對 99% 誤判 vs jedi 0% 誤判）。
  - 專案隔離：jedi.Project(path=src_root) 天然按專案根隔離。

confidence 標記規則（對齊主架構「引用邊標信心度」）：
  - "high"  = jedi 真 import 解析命中（resolved-import），agent 可自動信任。
  - "low"   = 只靠名稱比對的候選，未經 jedi 確認（name-match），僅供人看。

職責（單一）：給「某符號定義在哪 / 被誰用」的精解。
不碰 SQLite、不碰排序——呼叫端（engine）負責落盤與組裝。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import jedi

from . import symbols

# 用於粗篩的「該行可能用到某符號」的樣式快取（避免每檔重編譯 regex）
_word_re_cache: dict[str, re.Pattern] = {}


def _word_re(symbol: str) -> re.Pattern:
    pat = _word_re_cache.get(symbol)
    if pat is None:
        pat = re.compile(r"\b" + re.escape(symbol) + r"\b")
        _word_re_cache[symbol] = pat
    return pat


def _iter_python_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳過常見的雜訊目錄（避免掃 .git / venv / __pycache__）
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__", ".venv", "venv",
                                    "node_modules", ".mypy_cache", ".pytest_cache")]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def _prefilter_candidate_files(src_root: str, symbol: str) -> list[str]:
    """第一段（粗篩）：名稱出現在哪些檔。便宜、寬鬆，寧可多框幾個。

    回傳含該符號名（當作獨立 word）的所有 .py 檔。jedi 只精解這些。
    """
    pat = _word_re(symbol)
    candidates: list[str] = []
    for fp in _iter_python_files(src_root):
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        if pat.search(text):
            candidates.append(fp)
    return candidates


def _make_project(src_root: str) -> jedi.Project:
    """每專案一個 jedi.Project（天然按專案根隔離）。"""
    return jedi.Project(path=os.path.abspath(src_root))


def goto_definition(src_root: str, file_path: str, line: int, column: int) -> list[dict]:
    """jedi goto：某位置的符號，定義在哪（follow_imports，跨 import 鏈精確指向）。

    參數 line/column：line 1-based、column 0-based（jedi 慣例：column 指到識別字內）。
    回傳 list[dict]：{path, line, name, type, confidence:"high"}。
    解析不到回 []（這是 jedi 真的查無，不是錯誤——但呼叫端應視為「沒高信心定義」）。
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
    except OSError as exc:
        raise FileNotFoundError(f"goto 失敗：讀不到 {file_path}（{exc}）") from exc

    project = _make_project(src_root)
    script = jedi.Script(source, path=file_path, project=project)
    defs = script.goto(line, column, follow_imports=True)
    out = []
    for d in defs:
        out.append({
            "path": str(d.module_path) if d.module_path else None,
            "line": d.line,
            "name": d.name,
            "type": d.type,
            "confidence": "high",  # jedi 解析命中 = 高信心
        })
    return out


def _locate_definition_position(src_root: str, def_name: str,
                                def_path: str | None) -> tuple[str, int, int] | None:
    """在定義檔裡定位 `def_name` 的 def/class 那一行（jedi get_references 要有起點）。

    若給了 def_path 就只找該檔；否則跨 src_root 找第一個命中。
    回傳 (path, line, column 1-based 指到名稱起點) 或 None。
    """
    pat = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(" + re.escape(def_name) + r")\b")
    search_files = [def_path] if def_path else list(_iter_python_files(src_root))
    for fp in search_files:
        if not fp or not os.path.exists(fp):
            continue
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                for i, line_text in enumerate(f, 1):
                    m = pat.match(line_text)
                    if m:
                        return (fp, i, m.start(1) + 1)
        except OSError:
            continue
    return None


def _occurrences_in_file(file_path: str, symbol: str) -> list[tuple[int, int]]:
    """檔內 `symbol`（當獨立 word）每個出現位置，回 [(line 1-based, col 0-based), ...]。

    col 用 0-based（jedi goto/column 慣例）。供第二段對每個出現點做 goto 用。
    """
    pat = _word_re(symbol)
    out: list[tuple[int, int]] = []
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            for li, line_text in enumerate(f, 1):
                for m in pat.finditer(line_text):
                    out.append((li, m.start()))
    except OSError:
        pass
    return out


def find_references(src_root: str, symbol: str, def_path: str | None = None,
                    *, include_low_confidence: bool = True,
                    max_candidate_files: int = 400) -> dict:
    """找「symbol 被誰用」——二段式精解（方向：呼叫點 goto 回定義）。

    為什麼是這個方向（PoC + 本機實測雙重坐實，不是隨意選）：
      - jedi 的「從定義端 get_references 找呼叫者」在大型專案只回已載入模組範圍，
        對 importlib 動態載入的入口（例如掛鉤系統用字串組出模組名再載入）會漏抓真實呼叫者。
      - jedi 的「從呼叫點 goto 回定義」極準：能無視 N 個同名定義精確指向唯一那個。
    所以二段式 = 粗篩候選檔（便宜文字篩）→ 對每個候選檔內 symbol 的每個出現點做
    goto，**指向目標定義** 才收為高信心引用。這把「找引用」轉成「對每個候選呼叫點
    各跑一次 goto」，每次 goto 都是 jedi 最擅長的精確方向。

    參數
    ----
    src_root : 專案原始碼根（jedi.Project 隔離 + import 解析根）。
    symbol   : 要找引用的符號名（如 "check"）。
    def_path : 該符號定義所在檔；給了能精確鎖定「要找哪一個同名定義的引用」。
    include_low_confidence : True 時把「名稱命中但 goto 不指向目標定義」的點也回（標 low）。
    max_candidate_files : 候選檔數上限（防超大 repo 上 goto 次數爆炸）。超過會截斷並標記。

    回傳 dict（可直接轉 JSON）：
      {
        "symbol", "definition": {path,line,column} 或 None,
        "high_confidence": [{src_path, line, column, confidence:"high"}, ...],
        "low_confidence":  [{src_path, line, column, confidence:"low", note}, ...],
        "name_match_file_count": int,        # 純名稱比對會框到幾個檔（對比基準）
        "name_match_hit_count": int,         # 純名稱比對的總文字命中數（含定義/同名）
        "candidates_scanned": int,           # 實際 goto 掃描的候選檔數
        "truncated": bool,
      }
    """
    located = _locate_definition_position(src_root, symbol, def_path)
    candidate_files = _prefilter_candidate_files(src_root, symbol)

    result: dict = {
        "symbol": symbol,
        "definition": None,
        "high_confidence": [],
        "low_confidence": [],
        "name_match_file_count": len(candidate_files),
        "name_match_hit_count": 0,
        "candidates_scanned": 0,
        "truncated": False,
        "engine": "jedi",  # 序1：三路都標解析引擎（jedi=Python 真 import 解析）
    }

    if located is None:
        result["error"] = (
            f"在 src_root 內找不到 '{symbol}' 的 def/class 定義行"
            f"（def_path={def_path}）；無法做高信心引用解析。"
        )
        return result

    def_file, def_line, def_col = located
    result["definition"] = {"path": def_file, "line": def_line, "column": def_col}
    def_file_norm = os.path.normcase(os.path.abspath(def_file))

    project = _make_project(src_root)

    scan_files = candidate_files
    if len(scan_files) > max_candidate_files:
        scan_files = scan_files[:max_candidate_files]
        result["truncated"] = True
    result["candidates_scanned"] = len(scan_files)

    total_hits = 0
    for fp in scan_files:
        occ = _occurrences_in_file(fp, symbol)
        total_hits += len(occ)
        if not occ:
            continue
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                source = f.read()
        except OSError:
            continue
        script = jedi.Script(source, path=fp, project=project)
        for (line, col) in occ:
            try:
                defs = script.goto(line, col, follow_imports=True)
            except Exception:
                # 單一位置 goto 失敗（語法殘缺等）不該炸整個查詢，記為低信心
                if include_low_confidence:
                    result["low_confidence"].append({
                        "src_path": fp, "line": line, "column": col,
                        "confidence": "low", "note": "goto 解析失敗，無法確認指向"})
                continue
            # 這個出現點是否指向「目標定義」？
            points_to_target = any(
                d.module_path
                and os.path.normcase(os.path.abspath(str(d.module_path))) == def_file_norm
                and d.line == def_line
                for d in defs
            )
            # 排除「定義自身那一行」（不算引用）
            is_definition_site = (os.path.normcase(os.path.abspath(fp)) == def_file_norm
                                  and line == def_line)
            if points_to_target and not is_definition_site:
                result["high_confidence"].append({
                    "src_path": fp, "line": line, "column": col, "confidence": "high"})
            elif include_low_confidence and not is_definition_site:
                result["low_confidence"].append({
                    "src_path": fp, "line": line, "column": col, "confidence": "low",
                    "note": "名稱命中，但 goto 指向別的同名符號（非此定義）"})

    result["name_match_hit_count"] = total_hits
    return result


# ── C5：非 Python 語言的「找引用」退化版（純名稱比對，全低信心） ──
_SKIP_DIRS_MULTI = (".git", "__pycache__", ".venv", "venv", "node_modules",
                    ".mypy_cache", ".pytest_cache", "build", "dist", "target", ".tox")


def _iter_files_by_ext(root: str, exts):
    """掃 root 下指定副檔名的檔（跳過雜訊目錄）。給跨語言名稱比對用。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS_MULTI]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in exts:
                yield os.path.join(dirpath, fn)


def name_match_references(src_root: str, symbol: str, *, def_path: str | None = None,
                          lang: str | None = None, include_low_confidence: bool = True,
                          max_candidate_files: int = 400) -> dict:
    """非 Python 語言的找引用——純名稱比對退化（jedi 限 Python，無真 import 解析）。

    ⛔ 全部標 **low confidence**：誠實表明未經 jedi / ts-morph 級解析確認、會把同名
    干擾也框進來。TS/JS 的高信心解析待 C5b（ts-morph）。回傳結構與 jedi 版
    find_references 對齊（high_confidence 恆空），讓 engine / 面板無痛共用。

    參數 lang：只掃該語言的副檔名（None 則掃全部支援副檔名）。
    """
    if lang and lang in symbols.LANGUAGE_SPECS:
        exts = frozenset(symbols.LANGUAGE_SPECS[lang]["exts"])
    else:
        exts = symbols.SUPPORTED_EXTENSIONS

    result: dict = {
        "symbol": symbol,
        "definition": None,
        "high_confidence": [],
        "low_confidence": [],
        "name_match_file_count": 0,
        "name_match_hit_count": 0,
        "candidates_scanned": 0,
        "truncated": False,
        "engine": "name-match",  # 序1：名稱比對退化（未經真 import 解析、全低信心）
        "note": (
            f"語言 '{lang or '?'}' 的高信心 import 解析尚未支援（jedi 限 Python）；"
            "以下為名稱比對結果、全部低信心（含同名干擾）。"
            "TS/JS 高信心解析待 C5b（ts-morph）。"
        ),
    }
    if def_path and os.path.exists(def_path):
        # 名稱比對無法精確定位定義行，只標檔（行/欄留 None）
        result["definition"] = {"path": def_path, "line": None, "column": None}

    files = list(_iter_files_by_ext(src_root, exts))
    result["name_match_file_count"] = len(files)
    if len(files) > max_candidate_files:
        files = files[:max_candidate_files]
        result["truncated"] = True
    result["candidates_scanned"] = len(files)

    if not include_low_confidence:
        return result

    total = 0
    for fp in files:
        for (line, col) in _occurrences_in_file(fp, symbol):
            total += 1
            result["low_confidence"].append({
                "src_path": fp, "line": line, "column": col,
                "confidence": "low", "note": "名稱比對（未經真 import 解析）",
            })
    result["name_match_hit_count"] = total
    return result


# ── C5b：TS/JS 高信心解析（ts-morph Node 子進程橋；不可用自動 fallback 回名稱比對） ──
def _ts_bridge_dir() -> str:
    """ts_bridge/ 在 CodeSextant 根（references.py 在 codesextant/ 內、上一層即根）。"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ts_bridge")


def ts_morph_available() -> bool:
    """node 在 PATH 且 ts_bridge 已備妥（find_refs.mjs + node_modules/ts-morph）。
    任一不滿足 → 回 False，呼叫端據此 fallback 回 C5a 名稱比對（不爆）。

    開關（L0 鐵律 #6）：env CODESEXTANT_TS_MORPH_DISABLED=1 → 強制停用 ts-morph、
    一律走 C5a 名稱比對（給「不想要 Node 子進程」或除錯時用）。"""
    if os.environ.get("CODESEXTANT_TS_MORPH_DISABLED", "").lower() in ("1", "true", "yes", "on"):
        return False
    if shutil.which("node") is None:
        return False
    bridge = _ts_bridge_dir()
    return (os.path.isfile(os.path.join(bridge, "find_refs.mjs"))
            and os.path.isdir(os.path.join(bridge, "node_modules", "ts-morph")))


def _run_ts_bridge(payload: dict, timeout: float) -> dict | None:
    """跑 ts_bridge/find_refs.mjs（stdin JSON → stdout JSON）。失敗/畸形/逾時 → None。永不拋。

    用 bytes stdin（UTF-8）——中文路徑經 stdin 不會像 PS Invoke-WebRequest 那樣編碼壞。
    CREATE_NO_WINDOW（Windows）：不彈 node 黑窗干擾 user（2026-06-19 user 反映補上、序4+5 沿用）。
    """
    bridge = _ts_bridge_dir()
    raw = json.dumps(payload).encode("utf-8")
    try:
        _kw = {"input": raw, "capture_output": True, "cwd": bridge, "timeout": timeout}
        if os.name == "nt":
            _kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        proc = subprocess.run(["node", os.path.join(bridge, "find_refs.mjs")], **_kw)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _shape_ts_one(symbol: str, r: dict) -> dict:
    """把 mjs 回的單符號結果轉成與 jedi/name_match 對齊的 dict（含序4 is_reexport）。

    防禦式取欄位（M1）：不依賴 mjs 永遠輸出完整 shape，缺/畸形元素跳過——維持「永不拋」契約。
    路徑統一 os.path.normpath（M2：與 jedi 反斜線格式一致，persist 累加 merge 比對才對得上）。
    保留 high 的 is_reexport 旗標 + reexport_count——序4 據此把「只被 barrel re-export、無真消費」
    標 REEXPORT_ONLY 而非誤判 LIKELY_UNUSED。error 欄位原樣帶回（orphan 用來判 UNKNOWN_UNRESOLVED）。
    """
    high = []
    reexport = 0
    for ref in (r.get("high_confidence") or []):
        if not isinstance(ref, dict) or not ref.get("src_path") or ref.get("line") is None:
            continue
        rx = bool(ref.get("is_reexport"))
        if rx:
            reexport += 1
        high.append({
            "src_path": os.path.normpath(ref["src_path"]),
            "line": ref["line"],
            "column": ref.get("column", 0),
            "confidence": "high",
            "is_reexport": rx,
        })
    definition = r.get("definition")
    if isinstance(definition, dict) and definition.get("path"):
        definition = {**definition, "path": os.path.normpath(definition["path"])}
    return {
        "symbol": symbol,
        "definition": definition,
        "high_confidence": high,
        "low_confidence": [],
        "name_match_file_count": 0,
        "name_match_hit_count": len(high),
        "candidates_scanned": 0,
        "truncated": False,
        "engine": "ts-morph",
        "reexport_count": reexport,
        "error": r.get("error"),
    }


def ts_morph_references(src_root: str, symbol: str, *, def_path: str | None,
                        timeout: float | None = None) -> dict | None:
    """單一符號 TS/JS 高信心 import 解析（findReferences 排除同名干擾）。

    不可用（無 node / 未 npm install / 子進程失敗 / 逾時 / 找不到定義 / 輸出畸形）→ 回 None，
    讓呼叫端 fallback 回 name_match_references（C5a 名稱比對）。**永不拋**。

    timeout：None 時取 env CODESEXTANT_TS_MORPH_TIMEOUT（預設 30 秒；L0 鐵律 #6 可調閾值
    ——超大 TS 專案 ts-morph 載入較久時可調高，逾時會靜默降級成名稱比對）。
    """
    if not def_path or not ts_morph_available():
        return None
    if timeout is None:
        try:
            timeout = float(os.environ.get("CODESEXTANT_TS_MORPH_TIMEOUT", "30"))
        except ValueError:
            timeout = 30.0
    data = _run_ts_bridge({
        "projectRoot": os.path.abspath(src_root),
        "defFile": os.path.abspath(def_path),
        "symbol": symbol,
    }, timeout)
    if data is None:
        return None
    # ts-morph 找不到定義（error 且無引用）→ 視為不可用，讓 fallback 名稱比對（一般查詢場景）
    if data.get("error") and not data.get("high_confidence"):
        return None
    try:
        return _shape_ts_one(symbol, data)
    except (KeyError, TypeError, AttributeError):
        return None


def ts_morph_references_batch(src_root: str, def_file: str, symbols,
                              *, timeout: float | None = None) -> dict | None:
    """序5：一次 spawn node 批查「同一檔多符號」（orphan 專用，避免逐符號各重載整個專案）。

    回 {symbol: result_dict|None}；ts-morph 不可用 / 子進程失敗 / 輸出畸形 → None
    （呼叫端據此逐符號 fallback 或整批標 UNKNOWN）。**永不拋**。

    與單一版的關鍵差異：error **不**回 None 而是帶 error 的 dict——orphan 場景要的是「ts-morph
    沒定位到 → UNKNOWN_UNRESOLVED」，⛔ 不該 fallback 名稱比對給低信心垃圾冒充。

    timeout：None 時取 env CODESEXTANT_TS_MORPH_BATCH_TIMEOUT（預設 90 秒；批量符號多、給更長）。
    """
    syms = [s for s in (symbols or []) if s]
    if not syms or not def_file or not ts_morph_available():
        return None
    if timeout is None:
        try:
            timeout = float(os.environ.get("CODESEXTANT_TS_MORPH_BATCH_TIMEOUT", "90"))
        except ValueError:
            timeout = 90.0
    data = _run_ts_bridge({
        "projectRoot": os.path.abspath(src_root),
        "defFile": os.path.abspath(def_file),
        "symbols": syms,
    }, timeout)
    if data is None:
        return None
    results = data.get("results")
    if not isinstance(results, dict):
        return None
    out: dict = {}
    for sym in syms:
        r = results.get(sym)
        try:
            out[sym] = _shape_ts_one(sym, r) if isinstance(r, dict) else None
        except (KeyError, TypeError, AttributeError):
            out[sym] = None
    return out
