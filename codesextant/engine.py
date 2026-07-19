"""引擎門面 — 統籌 symbols / references / storage / ranking 四個模組。

這是 C1 對外的「純引擎 API」，也是 C2 daemon 要包成 HTTP 的那一層。
設計鐵則（給 C2 省力）：
  - 每個對外函數的參數與回傳都用「簡單可序列化型別」(str/int/dict/list)，
    能直接 json.dumps，HTTP daemon 接過去幾乎零轉換。
  - 一個 HTTP 端點對一個函數：
        /reindex  ← index_project(path)
        /get_symbols ← get_symbols(path, file)
        /find_references ← find_references(path, symbol, ...)
        /get_map ← get_map(path, token_budget)
        /status ← status(path)
  - fail-loud：路徑不存在、專案沒索引過就響亮報錯，不回 silent None / 空。

混合架構（PoC 坐實）：
  - index_project：tree-sitter 全量抽符號（快），不跑 jedi。
  - find_references：按需才跑 jedi 二段式精解。
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from collections import OrderedDict
from copy import deepcopy
from threading import RLock, Thread

from . import clones, comments, namegraph, references, storage, symbols
from .ranking import rank_symbols
from .symbols import SUPPORTED_EXTENSIONS

# 索引時掃原始碼檔，跳過這些雜訊目錄（target=Rust build 產物）
_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules",
              ".mypy_cache", ".pytest_cache", "build", "dist", "target", ".tox"}

# daemon 內只留「已裁成 token_budget 的小結果」，不留 57 萬 symbols/完整 edge graph。
# key 綁 SQLite revision + 所有會改排序的參數/env；index/ref 一更新，db mtime 變動即自動 miss。
_MAP_CACHE: OrderedDict[tuple, dict] = OrderedDict()
_MAP_CACHE_LOCK = RLock()
_SYMBOL_SNAPSHOT_INFLIGHT: set[tuple[str, tuple]] = set()
_MAP_CACHE_ENV = (
    "CODESEXTANT_NAMEGRAPH_DISABLED", "CODESEXTANT_NAMEGRAPH_MAX_FANOUT",
    "CODESEXTANT_NAMEGRAPH_MAX_FILES", "CODESEXTANT_NAMEGRAPH_MAP_WORK_BUDGET",
    "CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES", "CODESEXTANT_RANK_PRIVATE_MULT",
    "CODESEXTANT_RANK_WELLNAMED_MINLEN", "CODESEXTANT_RANK_WELLNAMED_MULT",
    "CODESEXTANT_RANK_COMMON_THRESHOLD", "CODESEXTANT_RANK_COMMON_MULT",
    "CODESEXTANT_PAGERANK_FOCUS_BOOST",
)


def _schedule_symbol_snapshot(db_file, revision: tuple, symbols: list[dict]) -> None:
    """回應路徑之外延遲寫快照；同 revision 全程序只准一個 writer。"""
    key = (str(db_file), tuple(revision))
    with _MAP_CACHE_LOCK:
        if key in _SYMBOL_SNAPSHOT_INFLIGHT:
            return
        _SYMBOL_SNAPSHOT_INFLIGHT.add(key)

    def worker():
        try:
            time.sleep(1.0)  # 先讓 HTTP handler 把 map 小結果送完，避免 JSON writer 搶 GIL
            storage.write_symbol_snapshot(db_file, revision, symbols)
        except Exception as exc:
            print(f"  ⚠ symbols snapshot 寫入失敗：{type(exc).__name__}: {exc}",
                  file=sys.stderr)
        finally:
            with _MAP_CACHE_LOCK:
                _SYMBOL_SNAPSHOT_INFLIGHT.discard(key)

    Thread(target=worker, name="codesextant-symbol-snapshot", daemon=True).start()

# 找引用時納入的「可被引用的定義」種類。含 variable：TS/JS 的 exported const、arrow
# function、const 物件都是一等被引用對象（C5b 實機發現排除 variable 會讓 TS const 無候選
# 定義 → def_path=None → 誤走 jedi 死路 high=0，對應 review 問題 4 的常見情況）。
_REFERENCEABLE_KINDS = {"function", "class", "method", "interface", "type",
                        "enum", "struct", "trait", "variable",
                        # 2026-06-22 主流語言一批新增的符號種類：
                        "constructor",   # C#/Java/Swift 建構子
                        "property",      # C#/Swift 屬性
                        "module",        # Ruby module
                        "protocol"}      # Swift protocol


def _iter_source_files(root: str):
    """掃 root 下所有「支援語言」的原始碼檔（C5：多語言；跳過雜訊目錄）。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in SUPPORTED_EXTENSIONS:
                yield os.path.join(dirpath, fn)


def _env_on(name: str) -> bool:
    """env 旗標解析（統一走 .lower()，避免 =True/=TRUE 被當沒設）。"""
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def _infer_project_language(root: str, *, sample_cap: int | None = None) -> str | None:
    """坑9：找引用時 symbol 查無候選定義（def_path=None）且 jedi 也找不到定義時，
    取樣專案主語言做 **fallback**（非 override，見 find_references），避免非 Python
    symbol 走名稱比對死路。

    只在主導語言佔比 ≥ 門檻時回該語言（平手/混合不硬選＝回 None 走保守 jedi、誤判成本
    最低）；判不出回 None。開關（L0 鐵律 #6，皆 .lower() 容錯）：
      - CODESEXTANT_INFER_LANG_DISABLED=1/true/yes/on → 回 None（停用）。
      - CODESEXTANT_INFER_LANG_SAMPLE_CAP=<int> → 取樣上限（預設 1000；<=0 表不截斷全掃）。
      - CODESEXTANT_INFER_LANG_MIN_RATIO=<float> → 主導佔比門檻（預設 0.6）。
    """
    if _env_on("CODESEXTANT_INFER_LANG_DISABLED"):
        return None
    if sample_cap is None:
        try:
            sample_cap = int(os.environ.get("CODESEXTANT_INFER_LANG_SAMPLE_CAP", "1000"))
        except ValueError:
            sample_cap = 1000
    try:
        min_ratio = float(os.environ.get("CODESEXTANT_INFER_LANG_MIN_RATIO", "0.6"))
    except ValueError:
        min_ratio = 0.6

    from collections import Counter
    counts: Counter[str] = Counter()
    for seen, fp in enumerate(_iter_source_files(root), start=1):
        lang = symbols.language_for_file(fp)
        if lang:
            counts[lang] += 1
        if sample_cap > 0 and seen >= sample_cap:
            break
    total = sum(counts.values())
    if total == 0:
        return None
    top_lang, top_n = counts.most_common(1)[0]
    # 主導佔比未達門檻（混合/平手）→ 回 None 走保守 jedi（決定性、誤判成本最低）
    if top_n / total < min_ratio:
        return None
    return top_lang


def _git_head_sha(repo_path: str) -> str | None:
    """坑6：讀 repo 的 git HEAD sha（freshness 比對用）。非 git repo／git 不可用／
    開關關閉 → None。Windows detached daemon 下不彈黑窗（CREATE_NO_WINDOW）。
    開關（L0 鐵律 #6，.lower() 容錯）：CODESEXTANT_GIT_FRESHNESS_DISABLED=1/true/yes/on → None。
    """
    if _env_on("CODESEXTANT_GIT_FRESHNESS_DISABLED"):
        return None
    try:
        import subprocess
        kwargs = {"capture_output": True, "text": True, "timeout": 5}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW（detached 不彈黑窗）
        out = subprocess.run(["git", "-C", repo_path, "rev-parse", "HEAD"], **kwargs)
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception:
        pass
    return None


def index_project(path: str, *, force: bool = False) -> dict:
    """對一個專案建（或增量更新）索引。

    tree-sitter 全量抽符號 + content hash 增量：只重算 hash 變了的檔。
    ⛔ 這一步不跑 jedi（全量 jedi 太慢）；引用解析留給 find_references 按需做。

    參數
    ----
    path  : 專案根目錄（絕對或相對皆可，內部會 normalize）。
    force : True 時忽略 hash、全部重算（除錯/重建用）。

    回傳 dict（可轉 JSON）：
      {indexed, skipped, removed, errors, total_files, elapsed_sec,
       project_key, db_file, symbols_total}
    路徑不是目錄 → NotADirectoryError（fail-loud）。
    """
    if not os.path.isdir(path):
        raise NotADirectoryError(f"index_project：'{path}' 不是有效目錄")

    abs_path = os.path.abspath(path)
    t0 = time.perf_counter()
    indexed = skipped = errors = 0
    error_files: list[dict] = []

    with storage.ProjectStore.open(abs_path) as store:
        seen_files: set[str] = set()
        for fp in _iter_source_files(abs_path):
            seen_files.add(fp)
            # 紅隊 L4-MEDIUM：一檔讀一次 bytes（content_hash 也從 bytes 算，省掉原本 4 次磁碟讀）
            try:
                with open(fp, "rb") as _f:
                    source = _f.read()
            except OSError as exc:
                errors += 1
                error_files.append({"path": fp, "error": f"讀檔失敗: {exc}"})
                continue
            h = hashlib.sha256(source).hexdigest()

            if not force and not store.needs_reindex(fp, h):
                skipped += 1
                continue

            try:
                # 紅隊 L4-MEDIUM：一檔 parse 一次，symbols/comments/fingerprints 共用同一 tree（省重複 parse）
                lang = symbols.language_for_file(fp)
                tree = symbols.parse_source(source, lang) if lang else None
                syms = (symbols.extract_symbols_from_source(source, lang, file_path=fp, tree=tree)
                        if lang else [])
                store.store_file_symbols(fp, h, syms, indexed_at=time.time())
                indexed += 1
                # 功能 B：抽註解落盤（共用 tree；註解失敗不該炸索引，symbols 已落盤、下次 reindex 再補）。
                if lang and comments.comments_enabled():
                    try:
                        store.store_file_comments(fp, comments.extract_comments_from_source(
                            source, lang, file_path=fp, tree=tree))
                    except Exception as exc:  # 註解失敗不炸索引、但記 stderr 不靜默吞（可觀測性）
                        print(f"  ⚠ 註解抽取失敗（{fp}）：{type(exc).__name__}: {exc}",
                              file=sys.stderr)
                # 功能 B：抽結構指紋 + winnowing 倒排落盤（共用 tree；失敗不炸索引）
                if lang and clones.dedup_enabled():
                    try:
                        fps = clones.extract_fingerprints_from_source(
                            source, lang, file_path=fp, tree=tree)
                        winnow_idx = [{"line": f["line"], "fp_value": v}
                                      for f in fps for v in f.get("winnow", [])]
                        store.store_file_fingerprints(fp, fps, winnow_idx)
                    except Exception as exc:  # 指紋/複雜度失敗不炸索引、但記 stderr 不靜默吞（對抗 review CRITICAL #2③）
                        print(f"  ⚠ 指紋/複雜度抽取失敗（{fp}）：{type(exc).__name__}: {exc}",
                              file=sys.stderr)
            except Exception as exc:  # 單檔解析失敗不該炸整個索引，但要記錄（不靜默吞）
                errors += 1
                error_files.append({"path": fp, "error": f"{type(exc).__name__}: {exc}"})

        # 處理已從磁碟消失的檔（從索引移除，保持單一真相）
        removed = 0
        for old_path in store.all_indexed_files():
            if old_path not in seen_files and not os.path.exists(old_path):
                store.remove_file(old_path)
                removed += 1

        # 坑6：記錄本次索引時 repo 的 git HEAD sha（非 git repo → None 不記）
        sha = _git_head_sha(abs_path)
        if sha:
            store.record_git_sha(sha)

        elapsed = time.perf_counter() - t0
        st = store.stats()
        result = {
            "indexed": indexed,
            "skipped": skipped,
            "removed": removed,
            "errors": errors,
            "error_files": error_files,
            "total_files": indexed + skipped,
            "elapsed_sec": round(elapsed, 3),
            "project_key": st["project_key"],
            "db_file": st["db_file"],
            "symbols_total": st["symbols"],
        }
    return result


def get_symbols(path: str, file: str | None = None) -> dict:
    """取某專案的符號（給 file 只取該檔，否則整個專案）。

    回傳 {project_key, file, count, symbols:[...]}。
    專案沒索引過 → 回 count=0 並附 note 提示先 index（不假裝有資料）。
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {
            "project_key": storage.project_key(abs_path),
            "file": file,
            "count": 0,
            "symbols": [],
            "note": f"專案尚未索引（無 {db_file}）。請先呼叫 index_project。",
        }

    target_file = os.path.abspath(file) if file else None
    with storage.ProjectStore.open(abs_path) as store:
        syms = store.get_symbols(target_file)
        return {
            "project_key": store.project_key,
            "file": target_file,
            "count": len(syms),
            "symbols": syms,
        }


def _refs_non_python(root: str, symbol: str, def_path: str | None, lang: str,
                     include_low_confidence: bool) -> dict:
    """非 Python 找引用 dispatch：TS/JS 先試 ts-morph 高信心、不可用 fallback 名稱比對
    （不爆）；其他語言走名稱比對退化（全低信心、誠實標示）。"""
    if lang in ("typescript", "tsx", "javascript"):
        result = references.ts_morph_references(root, symbol, def_path=def_path)
        if result is None:
            result = references.name_match_references(
                root, symbol, def_path=def_path, lang=lang,
                include_low_confidence=include_low_confidence,
            )
        return result
    return references.name_match_references(
        root, symbol, def_path=def_path, lang=lang,
        include_low_confidence=include_low_confidence,
    )


def _refs_reliability(result: dict) -> dict:
    """序6：依 find_references 結果品質自評可靠度 + 給「何時該回去讀原始碼」建議。

    level：high=可直接信任 / medium=部分可信但有盲區、建議補讀 / low=務必讀碼別當定論。
    ⛔ 不管哪一級都**不取代讀碼判斷邏輯對錯**——本工具只看引用關聯、不看語義與業務意圖；
    且靜態解析一律看不到動態/反射/字串拼接的呼叫（這正是最該人工讀碼之處）。
    """
    engine = result.get("engine")
    high = len(result.get("high_confidence") or [])
    low = len(result.get("low_confidence") or [])
    if engine == "name-match":
        return {"level": "low",
                "advice": "純名稱比對（無真 import 解析）——含同名干擾、且看不到動態/反射呼叫；"
                          "務必讀原始碼確認，別把這份清單當完整或精確。"}
    if not result.get("definition"):
        return {"level": "low",
                "advice": "未定位到符號定義（可能拼錯／不在此 repo／是 module 級變數）——"
                          "結果不完整，建議直接讀原始碼確認。"}
    if high == 0 and low == 0:
        return {"level": "medium",
                "advice": "真解析得到零引用——可能真沒人用，也可能是動態/反射/字串拼接呼叫"
                          "（靜態解析一律看不到）；刪改前讀那段碼上下文確認。"}
    if low > high * 3 and low > 5:
        return {"level": "medium",
                "advice": f"低信心({low})遠多於高信心({high})、多為同名干擾；高信心那 {high} 處可信，"
                          "但若你要找的用法不在其中，建議掃一眼低信心或讀原始碼。"}
    return {"level": "high",
            "advice": f"真解析高信心引用 {high} 處、可直接信任省去人肉追引用"
                      "（仍：改簽章/刪除後跑 build 驗證；**邏輯對錯仍需讀碼**）。"}


def find_references(path: str, symbol: str, *, def_path: str | None = None,
                    src_root: str | None = None,
                    include_low_confidence: bool = True,
                    persist: bool = True) -> dict:
    """找某符號「被誰用」——jedi 二段式精解（按需才跑 jedi）。

    參數
    ----
    path   : 專案根（也是 jedi.Project 隔離根，除非另給 src_root）。
    symbol : 符號名（如 "check"）。
    def_path : 該符號定義所在檔。沒給的話，會先查索引庫找候選定義；
               找到唯一一個就用它，找到多個（同名）則用第一個並在回傳裡列出全部候選。
    src_root : jedi.Project 的根。預設 = path。某些 repo 的 import 根在 src/ 子目錄，
               可明確指定（採 src/ 佈局的專案要指到 .../src）。
    include_low_confidence : 是否回名稱比對命中但 jedi 未確認的檔（標 low）。
    persist : True 時把解析出的高信心引用邊落盤（供 PageRank/查詢重用）。

    回傳 references.find_references 的 dict + {candidate_definitions:[...]}。
    """
    abs_path = os.path.abspath(path)
    root = os.path.abspath(src_root) if src_root else abs_path

    # 若沒給 def_path，從索引庫撈同名定義當候選（二段式第一段的「粗篩」也用得上索引）
    candidate_defs: list[dict] = []
    db_file = storage.db_path_for(abs_path)
    if db_file.exists():
        with storage.ProjectStore.open(abs_path) as store:
            candidate_defs = [d for d in store.find_symbol_definitions(symbol)
                              if d["kind"] in _REFERENCEABLE_KINDS]
    if def_path is None and candidate_defs:
        def_path = candidate_defs[0]["path"]

    # C5 按定義檔語言 dispatch：Python（或無法判斷副檔名）走 jedi 真 import 解析；
    # 其他語言走 _refs_non_python（ts-morph／名稱比對退化）。
    lang = symbols.language_for_file(def_path) if def_path else None
    if lang in (None, "python"):
        result = references.find_references(
            root, symbol, def_path=def_path,
            include_low_confidence=include_low_confidence,
        )
        # 坑9（對抗 review 修正：fallback 而非 override）：def_path=None 且 jedi 沒找到定義
        # 時，才以取樣推得的語言重試。⚠ 必須在 jedi 失敗「之後」介入——jedi 不依賴索引/
        # def_path、直接掃磁碟，混合 repo 裡 Python symbol 即使 def_path=None jedi 仍找得到；
        # 先 override 會奪走這能力（pit9-1 回歸：TS 多於 Py 的 repo 把 Python 查詢誤丟成空）。
        if def_path is None and not result.get("definition"):
            inferred = _infer_project_language(root)
            if inferred and inferred != "python":
                lang = inferred
                result = _refs_non_python(root, symbol, None, lang,
                                          include_low_confidence)
    else:
        result = _refs_non_python(root, symbol, def_path, lang,
                                  include_low_confidence)
    result["language"] = lang or "python"
    result["candidate_definitions"] = candidate_defs
    result["src_root"] = root
    # 序1 保險：三路源頭（references.find_references/name_match/ts_morph）都已標 engine，
    # 但 fallback 換 result 或未來新路徑可能漏 → 補一個保守預設（最低信心，不謊報真解析）。
    result.setdefault("engine", "name-match")
    # 序2（Gap3-A 降信心）：誠實揭露能力邊界——查引用/未使用偵測 ≠ 編譯/型別/lint 通過，
    # refs 全綠不代表能 build。清死碼或改簽章後務必自跑 build/CI（紅藍最佳解 §2 保留項）。
    result["verification_reminder"] = (
        "CodeSextant 查的是引用關聯，不等於編譯/型別/lint 通過；"
        "清死碼或改簽章後務必跑 build/CI 驗證。"
    )
    # 序6：自我邊界感知——依本次結果品質自評可靠度 + 主動建議「何時該回去讀原始碼」。
    # ⛔ 工具是導航圖非代碼本身：name-match/零引用/低信心遠多時主動喊讀碼，避免用戶誤以為已涵蓋。
    result["reliability"] = _refs_reliability(result)

    # 落盤高信心引用邊（按來源檔分組），供之後 PageRank 用
    if persist and db_file.exists() and result.get("definition"):
        d = result["definition"]
        edges_by_src: dict[str, list[dict]] = {}
        for ref in result["high_confidence"]:
            sp = ref.get("src_path")
            if not sp:
                continue
            edges_by_src.setdefault(sp, []).append({
                "src_path": sp,
                "src_line": ref["line"],
                "symbol_name": symbol,
                "def_path": d["path"],
                "def_line": d["line"],
                "confidence": "high",
            })
        if edges_by_src:
            with storage.ProjectStore.open(abs_path) as store:
                for sp, edges in edges_by_src.items():
                    # 注意：replace_refs_for 會清掉該 src 檔「所有」舊邊。
                    # 為避免清掉別的符號的邊，這裡採累加策略：先讀回該檔現有邊再合併。
                    existing = [e for e in store.all_refs() if e["src_path"] == sp
                                and e["symbol_name"] != symbol]
                    store.replace_refs_for(sp, existing + edges)

    return result


def call_hierarchy(path: str, symbol: str, *, direction: str = "both",
                   max_hops: int | None = None, def_path: str | None = None,
                   src_root: str | None = None, build_edges: bool = True) -> dict:
    """傳遞呼叫鏈（競品吸收 queue 1）——把單層 refs 升級成傳遞 callers/callees 鏈。

    direction：up=誰(傳遞)呼叫此符號(callers) / down=此符號(傳遞)呼叫誰(callees) / both。
    底層走 storage.traverse_call_graph（refs 表 WITH RECURSIVE CTE），max_hops 防環無限遞迴。

    ⚠ 呼叫鏈基於「已落盤的引用邊」（refs 表，對符號跑過 find_references 才累積）。build_edges=True
    時先對 target 跑一次 find_references(persist=True) 建直接 callers 邊，讓 up 方向直接層即時準；
    傳遞層與 down 方向仍依賴 refs 表既有邊（誠實 note 標明，呼應「誠實 UNKNOWN」哲學——邊不完整
    就說，不假裝完整）。靜態推導看不到動態/反射呼叫。

    參數
    ----
    max_hops : None 時取 env CODESEXTANT_CALL_HIERARCHY_MAX_HOPS（預設 5，L0 鐵律 #6 可調）。
    回 dict：{symbol, direction, definition, callers?, callees?, max_hops, edges_in_graph,
             candidate_definitions, note, verification_reminder}。專案未索引 → RuntimeError。
    """
    if direction not in ("up", "down", "both"):
        raise ValueError(f"direction 必須是 up/down/both，收到 {direction!r}")
    if max_hops is None:
        try:
            max_hops = int(os.environ.get("CODESEXTANT_CALL_HIERARCHY_MAX_HOPS", "5"))
        except ValueError:
            max_hops = 5
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"call_hierarchy：專案尚未索引（無 {db_file}）。請先呼叫 index_project。")

    with storage.ProjectStore.open(abs_path) as store:
        candidate_defs = [d for d in store.find_symbol_definitions(symbol)
                          if d["kind"] in _REFERENCEABLE_KINDS]
    if def_path is None and candidate_defs:
        def_path = candidate_defs[0]["path"]

    result: dict = {
        "symbol": symbol,
        "direction": direction,
        "definition": ({"path": def_path} if def_path else None),
        "max_hops": max_hops,
        "candidate_definitions": candidate_defs,
        "verification_reminder": (
            "呼叫鏈是靜態引用推導，看不到動態/反射/字串拼接呼叫；改動前仍須讀那段碼確認。"),
    }
    if def_path is None:
        result["callers"] = []
        result["callees"] = []
        result["error"] = (f"索引庫找不到符號 '{symbol}' 的可引用定義；"
                           "確認拼字、或先 index_project。")
        return result

    # build_edges：對 target 跑 find_references 建直接 callers 邊（讓 up 直接層即時準）
    if build_edges:
        try:
            find_references(abs_path, symbol, def_path=def_path, src_root=src_root,
                            persist=True)
        except Exception:
            pass  # 建邊失敗不致命——退用 refs 表既有邊

    with storage.ProjectStore.open(abs_path) as store:
        result["edges_in_graph"] = len(store.all_refs())
        if direction in ("up", "both"):
            result["callers"] = store.traverse_call_graph(
                symbol, def_path, direction="up", max_hops=max_hops)
        if direction in ("down", "both"):
            result["callees"] = store.traverse_call_graph(
                symbol, def_path, direction="down", max_hops=max_hops)
    result["note"] = (
        f"呼叫鏈基於已落盤引用邊（refs 表 {result['edges_in_graph']} 條）；"
        "邊在你對符號跑過 find_references(map/refs 會自動 persist)後累積。"
        "傳遞層/callees 方向若邊不足會偏少——先對相關符號跑 refs 補邊可更完整。")
    return result


def _is_test_path(p: str) -> bool:
    """路徑啟發式判測試檔（給 blast radius 分類 test/prod 用、零成本）。"""
    pl = p.replace("\\", "/").lower()
    base = os.path.basename(pl)
    return (base.startswith("test_") or base.endswith("_test.py") or base.endswith("_test.go")
            or ".test." in base or ".spec." in base or base == "conftest.py"
            or "/__tests__/" in pl or "/tests/" in pl or "/test/" in pl or "/spec/" in pl)


def _mark_high_importance(path: str, callers: list[dict]) -> list[dict]:
    """標出受影響 caller 中 PageRank 高重要度者（接 get_map top 符號名集合）。

    紅隊 L2-MEDIUM 修正：with_name_edges=False 走輕量路徑——impact/blast-radius 是高頻熱
    路徑，只需「結構中心 top 符號名」過濾 caller，不需名稱級排序精度；舊版每次 impact 都附帶
    觸發一次全 repo 名稱級掃描（實測 5.5x 退化、且該場景 high_importance 常為 0＝零價值）。
    """
    try:
        m = get_map(path, token_budget=3000, with_name_edges=False)
        top_names = {s.get("name") for s in (m.get("symbols") or [])[:30]}
    except Exception:
        top_names = set()
    return [c for c in callers if c.get("name") in top_names]


def impact(path: str, symbol: str, *, max_hops: int | None = None,
           def_path: str | None = None, src_root: str | None = None) -> dict:
    """改動影響報告 / blast radius（競品吸收 queue 2）——改 X 會牽動誰。

    建在 call_hierarchy(direction=up) 之上：直接+傳遞 callers、caller 分 test/prod/entrypoint、
    接 PageRank 標高重要度受影響符號。誠實層強制：name-match 低信心的傳遞依賴另列『可能還
    影響（未確認）』，⛔不混進確定集誤導。靜態推導看不到動態/反射呼叫。

    回 dict：{symbol, definition, direct_callers, transitive_callers, affected_files,
             by_kind:{test/prod/entrypoint}, high_importance_affected, uncertain_maybe_affected,
             summary, note, verification_reminder}。專案未索引 → RuntimeError。
    """
    from . import deadcode

    ch = call_hierarchy(path, symbol, direction="up", max_hops=max_hops,
                        def_path=def_path, src_root=src_root)
    callers = ch.get("callers", []) or []
    confirmed = [c for c in callers if c.get("confidence") == "high"]
    uncertain = [c for c in callers if c.get("confidence") != "high"]

    by_kind: dict[str, list] = {"test": [], "prod": [], "entrypoint": []}
    for c in confirmed:
        # ⚠ test 優先於 entrypoint：deadcode.is_entrypoint 把 test_*.py 當入口（那是死碼豁免
        # 用途）；但 blast radius 的分類意圖是「改它只影響測試 vs 影響對外行為」，故 test 檔
        # 先歸 test，非 test 的入口（路由/CLI/__main__）才歸 entrypoint。
        if _is_test_path(c["path"]):
            by_kind["test"].append(c)
            continue
        is_entry, reason = deadcode.is_entrypoint(c["path"], symbol_name=c.get("name"))
        if is_entry:
            by_kind["entrypoint"].append({**c, "entry_reason": reason})
        else:
            by_kind["prod"].append(c)

    high_importance = _mark_high_importance(os.path.abspath(path), confirmed)
    return {
        "symbol": symbol,
        "definition": ch.get("definition"),
        "direct_callers": [c for c in confirmed if c.get("depth") == 1],
        "transitive_callers": [c for c in confirmed if c.get("depth", 0) > 1],
        "affected_files": sorted({c["path"] for c in confirmed}),
        "by_kind": by_kind,
        "high_importance_affected": high_importance,
        # ⛔ 低信心傳遞依賴另列、不混進確定集（誠實層）
        "uncertain_maybe_affected": uncertain,
        "max_hops": ch.get("max_hops"),
        "edges_in_graph": ch.get("edges_in_graph"),
        "candidate_definitions": ch.get("candidate_definitions"),
        "error": ch.get("error"),
        "summary": {
            "total_confirmed_affected": len(confirmed),
            "direct": sum(1 for c in confirmed if c.get("depth") == 1),
            "transitive": sum(1 for c in confirmed if c.get("depth", 0) > 1),
            "test": len(by_kind["test"]), "prod": len(by_kind["prod"]),
            "entrypoint": len(by_kind["entrypoint"]),
            "high_importance": len(high_importance),
            "uncertain": len(uncertain),
        },
        "note": ch.get("note"),
        "verification_reminder": (
            "改動影響基於靜態呼叫鏈、看不到動態/反射/字串拼接呼叫；'可能還影響' 區是低信心未確認、"
            "別當定論。改動前仍須讀受影響處確認。"),
    }


def _get_map_uncached(path: str, token_budget: int = 2000, *, damping: float = 0.85,
                      focus_symbols=None, focus_files=None,
                      with_name_edges: bool = True) -> dict:
    """給「token 預算內最重要的 N 個符號」（PageRank 排序）。

    queue 4：focus_symbols/focus_files（呼叫端顯式傳入「在改/在問的符號/檔」）→ query-aware
    排序偏向相關處（personalization）；不傳＝原靜態結構中心度地圖。

    參數
    ----
    path : 專案根。
    token_budget : 約略 token 預算。用「每個符號條目約 12 token」粗估換算成符號數，
                   挑 PageRank 最高的前 N 個。
    damping : PageRank 阻尼係數。
    with_name_edges : True（預設）建名稱級全圖邊修開箱退化；False 走輕量純 SQLite 路徑
                      （不掃磁碟、不建名稱級邊）——給 impact/blast-radius 等只需 top 結構符號名的
                      熱路徑用，避免名稱級全圖掃拖慢（紅隊 L2-MEDIUM）。

    回傳 {project_key, token_budget, approx_tokens, count, symbols:[...帶 rank...], edge_sources, note}。
    專案沒索引過 → fail-loud（RuntimeError），因為「給地圖」必須先有索引。
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"get_map：專案尚未索引（無 {db_file}）。請先呼叫 index_project。"
        )

    # 約略換算：一條符號摘要（kind name @file:line）約 12 token
    tokens_per_symbol = 12
    top_n = max(1, token_budget // tokens_per_symbol)

    with storage.ProjectStore.open(abs_path) as store:
        symbol_revision = store.symbol_revision()
        symbols = store.load_symbol_snapshot(symbol_revision)
        symbol_snapshot_hit = symbols is not None
        if symbols is None:
            symbols = store.get_symbols()
        db_refs = store.all_refs()
        # namegraph（任務一修退化）：名稱級全圖邊，in-memory 算、**不落 refs 表**、全 low 信心。
        # 修「開箱只 reindex 沒跑 find_references → refs=0 → PageRank 全均分」的招牌退化。
        # db 的 high 邊（jedi/ts-morph 真解析，權重 1.0）仍主導；名稱級 low 邊（0.25×品質係數）
        # 只補開箱無邊的全圖結構底盤。callgraph/impact/find_references 都讀 refs 表，零影響。
        name_edges: list[dict] = []
        ng_meta = None
        if with_name_edges and namegraph.namegraph_enabled():
            map_file_limit, adaptive_limit = namegraph.map_file_limit(len(symbols))
            name_edges, ng_meta = namegraph.build_name_edges(
                symbols, indexed_files=store.all_indexed_files(),
                max_files=map_file_limit, preferred_files=focus_files)
            ng_meta["adaptive_file_limit"] = adaptive_limit
            ng_meta["effective_max_files"] = map_file_limit
        refs = db_refs + name_edges
        name_edge_count = int((ng_meta or {}).get("total_edges", len(name_edges)))
        name_unique_count = len(name_edges)
        ranked = rank_symbols(symbols, refs, top_n=top_n, damping=damping,
                              focus_symbols=focus_symbols, focus_files=focus_files)
        # 紅隊 L4-MEDIUM：截斷時 note 不可宣稱「涵蓋全專案」（誠實層）
        truncated = bool((ng_meta or {}).get("truncated"))
        coverage = (f"分層取樣 {(ng_meta or {}).get('scanned_files')}／共 "
                    f"{(ng_meta or {}).get('total_files')} 檔（已截斷，原因="
                    f"{','.join((ng_meta or {}).get('truncation_reasons') or [])}；"
                    "env CODESEXTANT_NAMEGRAPH_MAX_FILES 可調），排序僅涵蓋部分專案、後段符號可能被低估"
                    if truncated else "涵蓋全專案")
        if not refs:
            note = ("無任何引用邊（refs=0、名稱級邊也空），PageRank 退化為均分；"
                    "通常代表專案無互相引用或 namegraph 被停用。")
        elif not db_refs:
            note = (f"PageRank 用名稱級全圖邊排序（{name_edge_count} 次 low 信心引用、"
                    f"折成 {name_unique_count} 條唯一邊，{coverage}）；"
                    "排序已脫離均分、凸顯結構中心符號。要更精準可對熱點符號跑 "
                    "find_references(persist=True) 累積高信心邊。")
        else:
            note = (f"PageRank 混合 {len(db_refs)} 條高信心邊（真解析、主導）+ "
                    f"{name_edge_count} 次名稱級 low 引用（折成 {name_unique_count} 條唯一邊，"
                    f"{coverage}）排序。")
        result = {
            "project_key": store.project_key,
            "token_budget": token_budget,
            "approx_tokens": len(ranked) * tokens_per_symbol,
            "count": len(ranked),
            "symbols": ranked,
            "edge_sources": {
                "db_high_edges": len(db_refs),
                "name_low_edges": name_edge_count,
                "name_low_unique_edges": name_unique_count,
                "symbol_snapshot_hit": symbol_snapshot_hit,
                "namegraph_meta": ng_meta,
            },
            "note": note,
        }
        if not symbol_snapshot_hit:
            _schedule_symbol_snapshot(store.db_file, symbol_revision, symbols)
        return result


def _map_cache_key(path: str, token_budget: int, damping: float,
                   focus_symbols, focus_files, with_name_edges: bool) -> tuple:
    db_file = storage.db_path_for(path)
    stat = db_file.stat()
    env_signature = tuple((name, os.environ.get(name)) for name in _MAP_CACHE_ENV)
    return (
        os.path.normcase(os.path.abspath(path)), stat.st_mtime_ns, stat.st_size,
        int(token_budget), float(damping), tuple(focus_symbols or ()),
        tuple(focus_files or ()), bool(with_name_edges), env_signature,
    )


def _map_cache_digest(key: tuple) -> str:
    return hashlib.sha256(repr(key).encode("utf-8")).hexdigest()


def _map_cache_limit() -> int:
    try:
        return max(1, int(os.environ.get("CODESEXTANT_MAP_CACHE_SIZE", "4")))
    except ValueError:
        return 4


def get_map(path: str, token_budget: int = 2000, *, damping: float = 0.85,
            focus_symbols=None, focus_files=None, with_name_edges: bool = True) -> dict:
    """帶 revision-aware LRU 的公開 map；同索引同參數在 daemon 內直接回小結果副本。"""
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return _get_map_uncached(
            abs_path, token_budget, damping=damping, focus_symbols=focus_symbols,
            focus_files=focus_files, with_name_edges=with_name_edges)

    # 先完成冪等 schema/index migration 再取 revision，避免升級當下把結果存到 migration 前 key、
    # 下一次又白算一遍。open 不再無條件改 meta，所以正常 cache hit 只多一次便宜開關庫。
    with storage.ProjectStore.open(abs_path):
        pass
    key = _map_cache_key(
        abs_path, token_budget, damping, focus_symbols, focus_files, with_name_edges)
    key_digest = _map_cache_digest(key)
    with _MAP_CACHE_LOCK:
        cached = _MAP_CACHE.get(key)
        if cached is not None:
            _MAP_CACHE.move_to_end(key)
            result = deepcopy(cached)
            result["edge_sources"]["map_cache_hit"] = True
            result["edge_sources"]["map_cache_source"] = "memory"
            return result

    persisted = storage.load_map_snapshot(db_file, key_digest)
    if persisted is not None:
        result = deepcopy(persisted)
        result["edge_sources"]["map_cache_hit"] = True
        result["edge_sources"]["map_cache_source"] = "disk"
        with _MAP_CACHE_LOCK:
            _MAP_CACHE[key] = deepcopy(result)
            _MAP_CACHE.move_to_end(key)
            while len(_MAP_CACHE) > _map_cache_limit():
                _MAP_CACHE.popitem(last=False)
        return result

    result = _get_map_uncached(
        abs_path, token_budget, damping=damping, focus_symbols=focus_symbols,
        focus_files=focus_files, with_name_edges=with_name_edges)
    result["edge_sources"]["map_cache_hit"] = False
    result["edge_sources"]["map_cache_source"] = "compute"
    cache_size = _map_cache_limit()
    with _MAP_CACHE_LOCK:
        _MAP_CACHE[key] = deepcopy(result)
        _MAP_CACHE.move_to_end(key)
        while len(_MAP_CACHE) > cache_size:
            _MAP_CACHE.popitem(last=False)
    try:
        storage.write_map_snapshot(db_file, key_digest, result)
    except (OSError, TypeError, ValueError) as exc:
        print(f"  ⚠ map snapshot 寫入失敗：{type(exc).__name__}: {exc}",
              file=sys.stderr)
    return result


def status(path: str, *, check_freshness: bool = False) -> dict:
    """某專案的索引狀態（給 /status 端點與中文面板用）。

    專案沒索引過 → 回 indexed=False（不報錯，狀態查詢本就該能查「沒索引」）。
    check_freshness=True 才比對 git HEAD sha（會 spawn git 子進程）——預設 False，
    避免不設防的 GET /status 被惡意本機網頁 no-cors 觸發 git spawn 風暴（pit7-1）。
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {
            "indexed": False,
            "project_key": storage.project_key(abs_path),
            "repo_path": abs_path,
            "db_file": str(db_file),
        }
    with storage.ProjectStore.open(abs_path) as store:
        st = store.stats()
        st["indexed"] = True
        if check_freshness:
            # 坑6：git freshness——索引時 sha vs 當前 HEAD sha。
            indexed_sha = st.get("indexed_git_sha")
            current_sha = _git_head_sha(abs_path)
            st["current_git_sha"] = current_sha
            if indexed_sha and current_sha:
                st["git_stale"] = (indexed_sha != current_sha)
            elif indexed_sha and not current_sha:
                # 曾記過 sha 但現在 git 不可用（.git 刪/搬走/dubious-ownership）→ 無法判定，
                # ⛔ 不可靜默 False 謊報新鮮（pit6-1）。
                st["git_stale"] = None
                st["git_note"] = "git 目前不可用，無法判定新鮮度（索引時的 sha 仍在）"
            else:
                # 非 git repo／索引時未記 sha → freshness 不適用
                st["git_stale"] = False
                if not indexed_sha and current_sha:
                    st["git_note"] = "此庫索引時未記錄 git sha，重新索引以啟用新鮮度判定"
        return st


def list_projects() -> dict:
    """列出本機所有已索引專案（給 /projects 端點與中文面板用）。

    掃庫目錄下每個 SQLite 庫、反查其 repo_path ＋統計。不需 project 參數
    （這是面板「總覽」的資料來源，跟所有單專案端點互補）。

    回傳 {db_dir, count, projects:[...]}；count 只算讀得成功的庫（壞庫帶 error 仍列出）。
    """
    projects = storage.list_indexed_projects()
    return {
        "db_dir": str(storage.default_db_dir()),
        "count": sum(1 for p in projects if "error" not in p),
        "projects": projects,
    }


# ── C5c：死碼線索層（序3）——複用 find_references 真解析 + deadcode helper 組裝 ──
def _orphans_for_file(root: str, scope_file: str, lang: str | None) -> list[dict]:
    """對 scope_file 的頂層可導出符號逐個判 orphan（複用 find_references 真解析）。

    ⛔ UNKNOWN gate（紅藍最佳解修正一安全閘）：在跑 find_references「之前」先檢
    resolver_available——引擎不可用整個符號回 UNKNOWN_NO_RESOLVER、**跳過 high=0 判斷**
    （紅隊 B2：否則 ts-morph 不可用時會把整個 TS 專案每個 export 標可刪＝災難）。
    只看頂層符號（method/nested 不是 orphan 候選）。
    """
    from . import deadcode  # 延遲 import（engine→deadcode 單向，避免頂層循環）

    scope_abs = os.path.abspath(scope_file)
    file_lang = lang or symbols.language_for_file(scope_abs)
    ok, reason = deadcode.resolver_available(file_lang)
    try:
        with open(scope_abs, encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError:
        source = None

    syms = get_symbols(root, file=scope_abs).get("symbols", [])
    out: list[dict] = []
    pending: list[tuple[str, dict]] = []  # 非 entrypoint、待真解析的頂層符號
    for s in syms:
        if s.get("kind") not in _REFERENCEABLE_KINDS:
            continue
        if s.get("scope"):  # 只看頂層（巢狀/方法不是 orphan 候選）
            continue
        name = s.get("name")
        entry, er = deadcode.is_entrypoint(scope_abs, symbol_name=name, source=source)
        if entry:
            out.append({**s, **deadcode.classify_orphan(None, is_entry=True, entry_reason=er)})
            continue
        if not ok:  # ⛔ 安全閘：引擎不可用 → 不跑 high=0 判斷，誠實回 UNKNOWN
            out.append({**s, "verdict": "UNKNOWN_NO_RESOLVER",
                        "icon": deadcode.verdict_icon("UNKNOWN_NO_RESOLVER"),
                        "reason": reason})
            continue
        pending.append((name, s))

    if pending and file_lang in ("typescript", "tsx", "javascript"):
        # 序5：TS/JS 一次 batch 查全部 pending（一次 new Project 載入專案 loop 多符號），
        # 取代逐符號各 spawn node 各重載專案的 N× 浪費（實測 9 符號 32s → batch 一次）。
        names = [n for n, _ in pending]
        batch = references.ts_morph_references_batch(root, scope_abs, names)
        for name, s in pending:
            refs = batch.get(name) if batch else None  # batch 失敗→None→classify 安全回 UNKNOWN
            out.append({**s, **deadcode.classify_orphan(refs, is_entry=False, entry_reason=None)})
    else:
        # Python / 其他：逐符號 jedi（74ms/次、無 batch 必要）
        for name, s in pending:
            refs = find_references(root, name, def_path=scope_abs, src_root=root, persist=False)
            out.append({**s, **deadcode.classify_orphan(refs, is_entry=False, entry_reason=None)})
    return out


def find_deadcode(path: str, *, scope_file: str | None = None,
                  lang: str | None = None) -> dict:
    """死碼線索層 — unused-import（包 ruff/eslint）+ orphan 分級（複用真解析）+ entrypoint 豁免。

    ⚠ 這是「線索層」非「決策器」：給帶安全分級的線索（LIKELY_UNUSED🟡/UNKNOWN❔/PUBLIC_API⚪/
    KEEP✅），刪除前務必人工複核 + 跑 build/CI（refs 全綠 ≠ 編譯通過）。紅藍最佳解核心紀律：
    引擎/linter 不可用一律回 UNKNOWN_*（誠實），絕不退化成自信假陽性。

    參數
    ----
    path       : 專案根（unused-import 掃描根 + orphan 的 jedi/ts-morph 解析根）。
    scope_file : 給了才跑 orphan（對該檔頂層符號逐個真解析；全專案逐符號太重，序3 先要求指定檔）。
    lang       : 覆寫語言推斷（預設由 scope_file 副檔名 / 專案推斷）。

    回 dict（可轉 JSON）：{root, scope_file, unused_imports, orphans, summary, verification_reminder}
    路徑不是目錄 → NotADirectoryError（fail-loud）。
    """
    from collections import Counter

    from . import deadcode

    if not os.path.isdir(path):
        raise NotADirectoryError(f"find_deadcode：'{path}' 不是有效目錄")
    abs_path = os.path.abspath(path)
    target = os.path.abspath(scope_file) if scope_file else abs_path

    unused = deadcode.detect_unused_imports(target, root=abs_path, lang=lang)
    orphans = _orphans_for_file(abs_path, scope_file, lang) if scope_file else []

    vc: Counter[str] = Counter(o.get("verdict", "?") for o in orphans)
    return {
        "root": abs_path,
        "scope_file": os.path.abspath(scope_file) if scope_file else None,
        "unused_imports": unused,
        "orphans": orphans,
        "summary": {
            "unused_import_count": len(unused.get("findings", [])),
            "unused_import_available": unused.get("available", False),
            "orphan_verdicts": dict(vc),
            "likely_unused": vc.get("LIKELY_UNUSED", 0),
            "keep": vc.get("KEEP", 0),
            "public_api": vc.get("PUBLIC_API", 0),
            # UNKNOWN 合計（無解析引擎 + 解析器未定位到定義，如 module 級變數）
            "unknown": (vc.get("UNKNOWN_NO_RESOLVER", 0) + vc.get("UNKNOWN_UNRESOLVED", 0)),
        },
        "verification_reminder": (
            "死碼線索層給的是帶安全分級的線索、非刪除決策：LIKELY_UNUSED 也務必人工複核 + 跑 "
            "build/CI 再刪；UNKNOWN_* 代表工具無法判定（不是可刪）。refs/未使用偵測 ≠ 編譯通過。"
        ),
        # 序6：把本次結果的盲區攤開——哪些地方工具幫不上、必須人工讀碼（工具沉默≠可刪）
        "read_code_advisory": deadcode.read_code_advisory(unused, orphans),
    }


# ── ai-usage：這個 repo 用了哪些 AI/LLM + dispatch_policy 合規維度（純掃描，不依賴索引庫）──
def find_ai_usage(path: str, *, scope_file: str | None = None) -> dict:
    """掃 repo 用了哪些 AI/LLM，並依 dispatch_policy 標 cli(合規)/direct(違規)/local(本地) 三通道。

    純文字 regex 逐行掃 SUPPORTED_EXTENSIONS 檔（複用 _iter_source_files，跳雜訊目錄），
    不依賴 SQLite 索引（同 find_deadcode 純掃描）。回 {meta, nodes, edges, stats,
    read_code_advisory, verification_reminder}——nodes/edges 給 ai_usage_html 渲染 HUD 關聯圖。

    ⚠ 名稱級線索非執行證明；判 direct（違規）前務必人工讀碼確認確實走 metered endpoint。
    路徑不是目錄 → NotADirectoryError（fail-loud）。
    """
    from . import ai_usage
    if not os.path.isdir(path):
        raise NotADirectoryError(f"find_ai_usage：'{path}' 不是有效目錄")
    abs_path = os.path.abspath(path)
    return ai_usage.scan_ai_usage(
        abs_path, _iter_source_files(abs_path),
        scope_file=os.path.abspath(scope_file) if scope_file else None)


# ── 功能 A：未接線檢查（namegraph 強協同）——「寫完不接線→屎山」源頭粗篩 ──
def find_unwired(path: str, *, max_fanout: int | None = None) -> dict:
    """未接線檢查 — 名稱級全圖快速框出「零外部引用」的已定義頂層符號。

    「寫完不接線→屎山」源頭偵測：定義了函數/類/型別/常數，卻沒有任何自己 body 以外的地方
    提到它的名 = 疑似未接線。強協同 namegraph：用同一張全圖名稱級邊算 external usage
    （body-aware：排定義行 self token + 遞迴自呼叫，保留同檔 body 外呼叫＝同檔 helper 不誤報）。

    ⚠ 線索層非決策器（與 deadcode 同哲學、全程誠實低信心）：
      - 名稱級天花板：同名干擾會**漏報**（別處用同名的另一個定義會讓真沒人用的那個被算有引用）；
        動態/反射/字串拼接呼叫看不到會**誤報**；**對外公開 API**（被 repo 外部/下游 import、本 repo
        內無人用）正好零內部引用 → 會誤報（TS/JS 的 `export` 無 __all__ 對應豁免、尤其危險）。
      - 豁免：檔名約定/裝飾器入口/Python __all__/dunder/pyproject console_scripts 入口
        （複用 deadcode.is_entrypoint + entry_point_func_names）。⚠ __all__ 是 Python-only，
        TS/JS export 公開 API 無對應豁免、會誤報。
      - 同名定義過多（>fan-out 上限）的氾濫名 → UNKNOWN_FANOUT（未建邊不可判、可能反被大量引用）。
      - variable/常數降級標記：module 級變數名稱級判定信心更低（deadcode 真解析對它標 UNKNOWN_UNRESOLVED 不判可刪）。
    定位：全專案一次粗篩 → 對候選跑 find_deadcode（jedi/ts-morph 真解析）複核 + build/CI 再刪。

    參數
    ----
    max_fanout : 同名 fan-out 上限（None 走 env CODESEXTANT_NAMEGRAPH_MAX_FANOUT，預設 20）。

    回 dict（可轉 JSON）：{root, candidates, namegraph_meta, summary,
                          verification_reminder, read_code_advisory}。專案未索引 → RuntimeError。
    """
    from . import deadcode

    if not os.path.isdir(path):
        raise NotADirectoryError(f"find_unwired：'{path}' 不是有效目錄")
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"find_unwired：專案尚未索引（無 {db_file}）。請先呼叫 index_project。")

    with storage.ProjectStore.open(abs_path) as store:
        syms = store.get_symbols()
        indexed = store.all_indexed_files()

    usage, over_fanout, ng_meta = namegraph.compute_external_usage(
        syms, indexed_files=indexed, max_fanout=max_fanout)
    # 紅隊 L3-HIGH：pyproject console_scripts 入口（安裝後 wrapper 反射呼叫、源碼無人提及）豁免
    entry_funcs = deadcode.entry_point_func_names(abs_path)

    _src_cache: dict[str, str] = {}

    def _src_of(p: str) -> str:
        if p not in _src_cache:
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    _src_cache[p] = f.read()
            except OSError:
                _src_cache[p] = ""
        return _src_cache[p]

    candidates: list[dict] = []
    scanned = exempt = unknown = 0
    for s in syms:
        if s.get("kind") not in _REFERENCEABLE_KINDS:
            continue
        if s.get("scope"):              # 只看頂層（method/巢狀不是未接線候選）
            continue
        scanned += 1
        name = s["name"]
        dp = namegraph._normp(s["path"])   # 與 compute_external_usage 的 usage key 對齊（normcase）
        # dunder（__all__/__version__/__main__…）走特殊機制、名稱級看不到 → 豁免
        if name.startswith("__") and name.endswith("__"):
            exempt += 1
            continue
        # pyproject console_scripts 入口豁免（紅隊 L3-HIGH）
        if name in entry_funcs:
            exempt += 1
            continue
        is_entry, _reason = deadcode.is_entrypoint(dp, symbol_name=name, source=_src_of(dp))
        if is_entry:
            exempt += 1
            continue
        if name in over_fanout:
            unknown += 1
            candidates.append({**s, "verdict": "UNKNOWN_FANOUT",
                               "icon": deadcode.verdict_icon("UNKNOWN_NO_RESOLVER"),
                               "reason": ("同名定義過多（>fan-out 上限）未建名稱級邊、無法判引用；"
                                          "可能反而被大量引用，須真解析複核")})
            continue
        if usage.get((dp, s["line"], name)) == 0:
            # 紅隊 L3-MEDIUM：variable/常數名稱級信心更低（deadcode 真解析對 module 級變數標
            # UNKNOWN_UNRESOLVED 不判可刪），降級標記、別與函數候選同等強度。
            is_var = s.get("kind") == "variable"
            cand = {**s, "verdict": "UNWIRED_CANDIDATE", "icon": "🔸",
                    "reason": ("名稱級全圖中無任何自己 body 以外的地方提到此名（零外部引用）；疑似寫完未接線"
                               if not is_var else
                               "module 級變數/常數零外部引用——名稱級判定信心更低，deadcode 真解析會標 "
                               "UNKNOWN_UNRESOLVED 不判可刪；務必讀碼確認（可能是設定常數/反射讀取）")}
            if is_var:
                cand["low_confidence_kind"] = True
            candidates.append(cand)

    likely = sum(1 for c in candidates if c["verdict"] == "UNWIRED_CANDIDATE")
    var_likely = sum(1 for c in candidates
                     if c["verdict"] == "UNWIRED_CANDIDATE" and c.get("low_confidence_kind"))
    advisory = []
    if likely:
        advisory.append(
            f"{likely} 個未接線候選是『線索非定論』——可能是新寫未接的死碼，也可能是動態/反射/CLI/"
            "測試入口、或**被 repo 外部/下游 import 的對外公開 API**（本 repo 內本就無引用）；逐個讀碼或"
            "跑 find_deadcode 真解析複核，別直接刪（誤刪 export 會造成下游 breaking change）。")
    else:
        advisory.append("未發現零外部引用的頂層符號（名稱級層面皆有接線跡象；漏報仍可能，重要符號仍建議複核）。")
    if var_likely:
        advisory.append(
            f"其中 {var_likely} 個是 module 級變數/常數（已標 low_confidence_kind）——名稱級對變數最不準、"
            "deadcode 真解析會標 UNKNOWN 不判可刪，別據此刪設定常數。")
    if unknown:
        advisory.append(
            f"{unknown} 個氾濫同名符號工具判不出（未建邊）——這些常是被大量引用的常見名，"
            "工具沉默 ⛔ 不代表未接線。")
    if ng_meta.get("truncated"):
        advisory.append(
            f"⚠ 已截斷：只掃了前 {ng_meta.get('scanned_files')}／共 {ng_meta.get('total_files')} 檔"
            "（env CODESEXTANT_NAMEGRAPH_MAX_FILES 可調），後段符號的 usage 不完整、勿據此判未接線。")
    return {
        "root": abs_path,
        "candidates": candidates,
        "namegraph_meta": {
            "scanned_files": ng_meta.get("scanned_files"),
            "total_files": ng_meta.get("total_files"),
            "truncated": ng_meta.get("truncated"),
            "usage_targets": len(usage),
            "over_fanout_names": len(over_fanout),
        },
        "summary": {
            "top_level_referenceable_scanned": scanned,
            "unwired_candidates": likely,
            "unwired_variable_candidates": var_likely,
            "unknown_fanout": unknown,
            "exempt_entry_or_dunder": exempt,
        },
        "verification_reminder": (
            "未接線檢查是名稱級低信心粗篩線索：同名干擾會漏報、動態/反射/字串拼接呼叫看不到會誤報、"
            "對外公開 API（被外部 repo 消費、本 repo 內無 import）會誤報；候選務必跑 find_deadcode"
            "（jedi/ts-morph 真解析）複核 + build/CI 再刪——零外部引用 ≠ 確定可刪。"),
        "read_code_advisory": advisory,
    }


# ── 功能 B 註解管理（engine 查詢層，設計 §3.B.2）──
def _comment_coverage_kinds() -> set[str]:
    raw = os.environ.get("CODESEXTANT_COMMENT_COVERAGE_KINDS", "function,class,method,interface")
    return {k.strip() for k in raw.split(",") if k.strip()}


def _comment_skip_private() -> bool:
    return os.environ.get("CODESEXTANT_COMMENT_COVERAGE_SKIP_PRIVATE", "").lower() not in (
        "0", "false", "no", "off")


def _comment_density_enabled() -> bool:
    return os.environ.get("CODESEXTANT_COMMENT_DENSITY_DISABLED", "").lower() not in (
        "1", "true", "yes", "on")


def get_comment_overview(path: str, *, scope_file: str | None = None) -> dict:
    """repo 註解摘要（功能 B「一次看全」）：docstring 覆蓋率（分 kind）+ TODO/FIXME 計數 + 密度。

    覆蓋率＝COVERAGE_KINDS 的符號裡有多少個有 docstring（symbols 對 comments(is_doc=1) 用
    (path, owner_line)==(path, line) 對齊，比 scope 字串相等穩，設計 FIX lens-4）。
    SKIP_PRIVATE 預設排除 `_` 開頭（算「public surface 覆蓋率」非全符號）。專案未索引 → note 不假裝。
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {"project_key": storage.project_key(abs_path), "indexed": False,
                "note": f"專案尚未索引（無 {db_file}）。請先呼叫 index_project。"}
    target = os.path.abspath(scope_file) if scope_file else None
    kinds = _comment_coverage_kinds()
    skip_private = _comment_skip_private()

    with storage.ProjectStore.open(abs_path) as store:
        conn = store.conn
        sym_q = "SELECT path,name,kind,line,scope FROM symbols"
        sym_p: list = []
        if target:
            sym_q += " WHERE path=?"
            sym_p.append(target)
        syms = conn.execute(sym_q, sym_p).fetchall()
        doc_rows = conn.execute(
            "SELECT path, owner_line FROM comments WHERE is_doc=1 AND owner_line IS NOT NULL"
        ).fetchall()
        doc_set = {(r["path"], r["owner_line"]) for r in doc_rows}

        by_kind: dict[str, dict] = {}
        undocumented: list[dict] = []
        for s in syms:
            if s["kind"] not in kinds:
                continue
            if skip_private and (s["name"] or "").startswith("_"):
                continue
            bk = by_kind.setdefault(s["kind"], {"documented": 0, "total": 0})
            bk["total"] += 1
            if (s["path"], s["line"]) in doc_set:
                bk["documented"] += 1
            else:
                undocumented.append({"name": s["name"], "kind": s["kind"],
                                     "path": s["path"], "line": s["line"], "scope": s["scope"]})
        for bk in by_kind.values():
            bk["pct"] = round(100.0 * bk["documented"] / bk["total"], 1) if bk["total"] else 0.0
        tot_doc = sum(b["documented"] for b in by_kind.values())
        tot_all = sum(b["total"] for b in by_kind.values())
        overall_pct = round(100.0 * tot_doc / tot_all, 1) if tot_all else 0.0

        # 紅隊 L3-MEDIUM：tag_counts 改逐行掃 text（不用 comments.tag 欄 GROUP BY——tag 欄每註解只存
        # 第一個 marker，多標記 block 會漏算/吞掉其他 marker，與 find_comment_tags 數字打架）。
        from collections import Counter as _Counter
        tag_q = "SELECT line, text FROM comments WHERE tag IS NOT NULL"
        if target:
            tag_q += " AND path=?"
        _marker_re = comments._marker_re()
        _tagc: _Counter = _Counter()
        for tr in conn.execute(tag_q, ([target] if target else [])).fetchall():
            for t in comments.scan_tags_in_text(tr["text"], tr["line"], _marker_re):
                _tagc[t["tag"]] += 1
        tag_counts = dict(_tagc)

        density = None
        if _comment_density_enabled():
            cl_q = "SELECT COALESCE(SUM(end_line-line+1),0) AS n FROM comments"
            sl_q = "SELECT COALESCE(SUM(end_line-line+1),0) AS n FROM symbols WHERE scope=''"
            cl_p, sl_p = [], []
            if target:
                cl_q += " WHERE path=?"
                cl_p.append(target)
                sl_q += " AND path=?"
                sl_p.append(target)
            comment_lines = conn.execute(cl_q, cl_p).fetchone()["n"]
            code_lines = conn.execute(sl_q, sl_p).fetchone()["n"]
            denom = code_lines or 1
            density = {"comment_lines": comment_lines, "code_lines": code_lines,
                       "ratio": round(comment_lines / denom, 3),
                       "caveat": "粗估：code_lines＝頂層符號跨行總和、不扣空白/註解行；密度高低≠註解品質"}

    undocumented.sort(key=lambda u: (u["path"], u["line"]))
    return {
        "project_key": store.project_key, "indexed": True,
        "scope_file": target,
        "docstring_coverage": {"by_kind": by_kind, "overall_pct": overall_pct,
                               "counted_kinds": sorted(kinds), "skip_private": skip_private},
        "tag_counts": tag_counts,
        "density": density,
        "top_undocumented": undocumented[:30],
        "caveat": ("覆蓋率/密度是靜態結構統計、非語義：高覆蓋率≠註解正確或同步；docstring 偵測限"
                   "「block/module 第一個 string」(Python)，其他語言靠緊鄰近似、可能對不準。"),
    }


def find_comment_tags(path: str, *, tags: list[str] | None = None,
                      scope_file: str | None = None) -> dict:
    """TODO/FIXME 索引（功能 B「知道哪行」）：逐行掃 marker 回**真實源碼行**（含多行 block/doc）。

    FIX-3b：block/doc 註解的 marker 行號用 scan_tags_in_text 逐行精算（base_line+offset），不是
    註解起始行。tags 給了只回那些標記。回 {findings:[{tag,path,line,scope,text}], count_by_tag}。
    """
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {"indexed": False, "findings": [], "count_by_tag": {},
                "note": f"專案尚未索引（無 {db_file}）。請先呼叫 index_project。"}
    target = os.path.abspath(scope_file) if scope_file else None
    want = {t.upper() for t in tags} if tags else None
    marker_re = comments._marker_re()

    with storage.ProjectStore.open(abs_path) as store:
        q = "SELECT path,line,scope,text FROM comments WHERE tag IS NOT NULL"
        p: list = []
        if target:
            q += " AND path=?"
            p.append(target)
        rows = store.conn.execute(q, p).fetchall()

    findings: list[dict] = []
    for r in rows:
        for t in comments.scan_tags_in_text(r["text"], r["line"], marker_re):
            if want and t["tag"].upper() not in want:
                continue
            findings.append({"tag": t["tag"], "path": r["path"], "line": t["line"],
                             "scope": r["scope"], "text": t["text"]})
    findings.sort(key=lambda f: (f["path"], f["line"]))
    from collections import Counter
    count_by_tag = dict(Counter(f["tag"] for f in findings))
    return {"indexed": True, "scope_file": target, "findings": findings,
            "count_by_tag": count_by_tag,
            "verification_reminder": "只列工具掃到的標準標記；動態生成/非標準標記掃不到。"}


def get_comments(path: str, file: str | None = None, *, scope: str | None = None,
                 doc_only: bool = False, tag: str | None = None) -> dict:
    """精確過濾取註解（功能 B「只看該看的」，比照 get_symbols）。未索引 → count=0+note 不假裝。"""
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        return {"project_key": storage.project_key(abs_path), "count": 0, "comments": [],
                "note": f"專案尚未索引（無 {db_file}）。請先呼叫 index_project。"}
    target = os.path.abspath(file) if file else None
    with storage.ProjectStore.open(abs_path) as store:
        q = ("SELECT path,line,end_line,kind,is_doc,tag,scope,owner_line,text "
             "FROM comments WHERE 1=1")
        p: list = []
        if target:
            q += " AND path=?"
            p.append(target)
        if doc_only:
            q += " AND is_doc=1"
        if tag:
            q += " AND tag=?"
            p.append(tag.upper())
        if scope is not None:
            q += " AND scope=?"
            p.append(scope)
        q += " ORDER BY path,line"
        rows = [dict(r) for r in store.conn.execute(q, p).fetchall()]
        return {"project_key": store.project_key, "file": target,
                "count": len(rows), "comments": rows}


# ── 功能 B 重複/類似偵測（engine 組裝層，設計 §3.A）──
_DUP_VERDICT_ICON = {
    "EXACT_DUP": "🟥", "RENAMED_DUP": "🟧", "STRUCTURAL_NEAR": "🟨",
    "CALL_PATTERN_SIM": "🟦", "BOILERPLATE_SUPPRESSED": "⚪", "UNKNOWN_TOO_SMALL": "❔",
}


def _make_dup_group(verdict: str, members: list[dict], similarity, reason: str) -> dict:
    """組一個重複群（jscpd compact 格式：位置+名+信心，⛔不貼原始碼，守唯讀導航圖）。"""
    return {
        "verdict": verdict, "icon": _DUP_VERDICT_ICON[verdict], "similarity": similarity,
        "members": [{"path": m["path"], "line": m["line"], "end_line": m.get("end_line"),
                     "name": m.get("name"), "scope": m.get("scope")} for m in members],
        "representative": members[0].get("name"),
        "node_count": members[0].get("node_count"),
        "reason": reason,
    }


def get_health(path: str) -> dict:
    """per-symbol 代碼健康度（紀律轉美數值層：D1 腫脹 + D3 認知複雜度 + D5 重複 → health；D6 死碼 → dead）。

    把 clean-code 紀律復合成 per-symbol health∈[0,1]（低=該讀碼複核處）+ dead（未接線）。
    ⛔ 唯讀線索非決策器：health 低≠「應刪」，是「值得人工讀碼 + build/CI 複核」的訊號。
    ⛔ 不含視覺映射（飽和度/透明度公式）＝展示層（星圖前端）的事；本 API 只給數值。
    UNKNOWN/N-A（class/變數無指紋、非高信心語言 cognitive）剔除 renormalize 不洗滿分（防 vapor）。

    回 dict（可轉 JSON）：{root, symbols:[{path,name,line,kind,health,dead}],
                          summary:{n_nodes,n_covered,coverage,n_dead,clone_pairs}}。
    專案未索引 → RuntimeError（同 get_map）。
    """
    from collections import Counter

    from . import health as _health
    if not os.path.isdir(path):
        raise NotADirectoryError(f"get_health：'{path}' 不是有效目錄")
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(f"get_health：專案尚未索引（無 {db_file}）。請先呼叫 index_project。")

    with storage.ProjectStore.open(abs_path) as store:
        syms = store.get_symbols()
        fps = store.conn.execute(
            "SELECT path,line,node_count,shape_hash,cognitive FROM fingerprints").fetchall()
    shape_cnt = Counter(r["shape_hash"] for r in fps)
    fp_by = {(os.path.normcase(r["path"]), int(r["line"])):
             (int(r["node_count"] or 0), r["shape_hash"], r["cognitive"]) for r in fps}
    try:   # D6 未接線（→ dead 標記）；失敗不炸 health（fail-soft）
        uw = find_unwired(abs_path)
        dead_keys = {(os.path.normcase(os.path.abspath(c["path"])), int(c["line"]))
                     for c in uw.get("candidates", []) if c.get("verdict") == "UNWIRED_CANDIDATE"}
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠ get_health：find_unwired 失敗（D6 跳過）：{exc}", file=sys.stderr)
        dead_keys = set()

    nodes = [{"path": s["path"], "name": s["name"], "line": s["line"], "kind": s.get("kind", "")}
             for s in syms]
    summary = _health.annotate(
        nodes, fp_by, shape_cnt, dead_keys,
        key_of=lambda n: (os.path.normcase(n["path"]), int(n["line"])))
    return {"root": abs_path, "symbols": nodes, "summary": summary}


def find_duplicates(path: str, *, scope_file: str | None = None, near_global: bool = False,
                    min_similarity: float | None = None,
                    include_call_pattern: bool = False) -> dict:
    """重複/類似功能偵測（統一母版）— 結構指紋分群，純非語義（設計 §3.A）。

    分三段（紅隊 FIX-1：無 scope 預設只跑 stage-1 真 O(n)，全域近似 stage-2/3 須 opt-in）：
      stage-1：GROUP BY shape_hash → EXACT_DUP（raw_token 也同、逐字）/ RENAMED_DUP（同形改名）；
               結構顯著性硬門檻（須含控制流 + node_count/nstmts 夠）擋 getter/__init__ 大宗誤報。
      stage-2/3（scope_file 或 near_global 才跑）：winnowing 倒排 + DF-cap 三道閘 → STRUCTURAL_NEAR。
      call_pattern（include_call_pattern 才跑、最低信心🟦）：call_hash 同、結構不同。

    ⛔ 永不出「應刪/應合併」決策（守鐵律③唯讀導航圖）；結構相同≠語義相同，合併前人工讀碼 + CI。

    參數
    ----
    scope_file : 限該檔範圍（stage-2/3 預設只在此跑）。
    near_global : 全域 stage-2/3 近似比對 opt-in（大 repo 可能慢，DF-cap 防爆）。
    min_similarity : 覆寫 STRUCTURAL_NEAR 門檻（None 走 env，預設 0.8）。
    include_call_pattern : 開 CALL_PATTERN_SIM 層（誤報率最高、預設關）。

    回 dict：{root, scope_file, groups, summary, verification_reminder, read_code_advisory}。
    專案未索引 → RuntimeError。
    """
    if not os.path.isdir(path):
        raise NotADirectoryError(f"find_duplicates：'{path}' 不是有效目錄")
    abs_path = os.path.abspath(path)
    db_file = storage.db_path_for(abs_path)
    if not db_file.exists():
        raise RuntimeError(
            f"find_duplicates：專案尚未索引（無 {db_file}）。請先呼叫 index_project。")

    from collections import defaultdict
    min_node = clones._env_int("CODESEXTANT_DEDUP_MIN_NODE_COUNT", 15)
    sim_thresh = (min_similarity if min_similarity is not None
                  else clones._env_float("CODESEXTANT_DEDUP_SIMILARITY_THRESHOLD", 0.8))
    sim_thresh = max(0.0, min(1.0, sim_thresh))   # 紅隊 L4-LOW：clamp 防越界值破壞門檻語義
    df_cap = clones._env_int("CODESEXTANT_DEDUP_FP_DF_CAP", 50)
    min_shared = clones._env_int("CODESEXTANT_DEDUP_MIN_SHARED_FP", 3)
    near_global = near_global or clones._env_on("CODESEXTANT_DEDUP_NEAR_GLOBAL")
    include_call_pattern = include_call_pattern or clones._env_on(
        "CODESEXTANT_DEDUP_INCLUDE_CALL_PATTERN")
    target = os.path.abspath(scope_file) if scope_file else None

    groups: list[dict] = []
    summary = {"exact": 0, "renamed": 0, "structural_near": 0, "call_pattern": 0,
               "boilerplate_suppressed_groups": 0, "total_units_scanned": 0,
               "stage2_ran": bool(target) or near_global}

    with storage.ProjectStore.open(abs_path) as store:
        conn = store.conn
        # ⚠ 紅隊 L5-HIGH：stage-1（EXACT/RENAMED）**永遠對全 repo fingerprints 跑**（不套 WHERE path）
        # ——否則 scope_file 模式下 stage-1 變 intra-file-only，跨檔逐字重複漏掉、信心序顛倒。scope_file
        # 只用來「過濾要輸出哪些群」（群仍跨檔偵測，但只報含該檔成員的群）。
        rows = [dict(r) for r in conn.execute(
            "SELECT path,name,kind,line,end_line,scope,shape_hash,raw_token_hash,call_hash,"
            "node_count,nstmts,has_control_flow FROM fingerprints").fetchall()]
        summary["total_units_scanned"] = len(rows)   # 全 repo 單元數（stage-1 全域比對）
        meta = {(m["path"], m["line"]): m for m in rows}
        member_key: set = set()   # 已歸 stage-1 EXACT/RENAMED 群的 (path,line)，後段不重報

        def _in_scope(members) -> bool:
            """scope_file 模式：群至少含一個 target 檔成員才輸出（None=不限、全輸出）。"""
            return (not target) or any(os.path.abspath(m["path"]) == target for m in members)

        # ── stage-1：shape_hash GROUP BY，群內按 raw_token 二次分簇（紅隊 L1-MEDIUM：EXACT 子簇與
        #    RENAMED 變體並存、不互相吃掉，f1/f2 逐字得 EXACT、f1/f3 改名得 RENAMED）──
        by_shape: dict[str, list] = defaultdict(list)
        for r in rows:
            by_shape[r["shape_hash"]].append(r)
        for _shape, members in by_shape.items():
            if len(members) < 2:
                continue
            # 紅隊 L1-HIGH 收尾：結構顯著性 = has_control_flow + node_count（去掉 nstmts 門檻——Go 的
            # body=block>statement_list 多一層、且「單一大 switch/if dispatch」top-level nstmts=1 會被
            # 誤殺；node_count 是更好的複雜度指標、has_cf 已要求控制流，nstmts 冗餘且誤傷、與 winnow gate 對齊）。
            sig = [m for m in members if m["has_control_flow"]
                   and m["node_count"] >= min_node]
            if len(sig) < 2:
                if _in_scope(members):
                    summary["boilerplate_suppressed_groups"] += 1   # 同形但都樣板/太小 → 壓制
                continue
            by_raw: dict[str, list] = defaultdict(list)
            for m in sig:
                by_raw[m["raw_token_hash"]].append(m)
            reps: list[dict] = []   # 跨 raw 代表（每 raw 子簇第一個），給 RENAMED 群
            for cluster in by_raw.values():
                cluster.sort(key=lambda m: (m["path"], m["line"]))
                if len(cluster) >= 2 and _in_scope(cluster):
                    groups.append(_make_dup_group(
                        "EXACT_DUP", cluster, 1.0,
                        "逐字相同（shape+raw_token 皆同）。結構相同≠語義相同，合併前讀碼 + CI。"))
                    summary["exact"] += 1
                    for m in cluster:
                        member_key.add((m["path"], m["line"]))
                reps.append(cluster[0])
            if len(by_raw) > 1 and len(reps) >= 2:   # 有改名變體 → RENAMED（跨 raw 代表）
                reps.sort(key=lambda m: (m["path"], m["line"]))
                if _in_scope(reps):
                    groups.append(_make_dup_group(
                        "RENAMED_DUP", reps, None,
                        f"結構相同、識別字/常數不同（{len(by_raw)} 種變體）。可能只是同類樣板，合併前必讀業務語義。"))
                    summary["renamed"] += 1
                    for m in reps:
                        member_key.add((m["path"], m["line"]))

        # ── stage-2/3：winnowing 近似（DF-cap 三道閘；scope_file 或 near_global 才跑）──
        if summary["stage2_ran"]:
            # 閘1：DF-cap 排氾濫指紋。⚠ 紅隊 L4-HIGH：用 DISTINCT(path,line,fp_value) 數**真 document
            # frequency**（出現在幾個不同函數），而非 fingerprint_index 總行數——否則單函數內 winnow 同 fp
            # 多次出現會把自己灌爆 df_cap、誤剔真指紋（winnow 落盤已 set 去重，這裡 DISTINCT 雙保險）。
            flood = {r[0] for r in conn.execute(
                "SELECT fp_value FROM (SELECT DISTINCT path,line,fp_value FROM fingerprint_index) "
                "GROUP BY fp_value HAVING COUNT(*)>?", (df_cap,)).fetchall()}
            # ⚠ 紅隊 L2-MEDIUM：scope_file 模式只載「跟 target 檔 fp 有交集」的單元（不全表載入），
            # 讓單檔查重成本與全 repo 規模脫鉤；near_global 才全載入。
            if target:
                seed = {r[0] for r in conn.execute(
                    "SELECT DISTINCT fp_value FROM fingerprint_index WHERE path=?", (target,)
                ).fetchall()} - flood
                rows_fp: list = []
                seed_list = list(seed)
                for i in range(0, len(seed_list), 900):   # SQLite IN 上限保護、分批
                    chunk = seed_list[i:i + 900]
                    ph = ",".join("?" * len(chunk))
                    rows_fp.extend(conn.execute(
                        f"SELECT path,line,fp_value FROM fingerprint_index WHERE fp_value IN ({ph})",
                        tuple(chunk)).fetchall())
            else:
                rows_fp = conn.execute(
                    "SELECT path,line,fp_value FROM fingerprint_index").fetchall()
            body_fps: dict[tuple, set] = defaultdict(set)
            for r in rows_fp:
                if r["fp_value"] in flood:
                    continue
                body_fps[(r["path"], r["line"])].add(r["fp_value"])
            inv: dict[int, list] = defaultdict(list)
            for k, fps in body_fps.items():
                for v in fps:
                    inv[v].append(k)
            scope_keys = [k for k in body_fps if (not target or k[0] == target)]
            seen_pairs: set = set()
            for ka in scope_keys:
                cand: dict[tuple, int] = defaultdict(int)
                for v in body_fps[ka]:
                    for kb in inv[v]:
                        if kb != ka:
                            cand[kb] += 1
                for kb, shared in cand.items():
                    if shared < min_shared:                     # 閘2：min_shared_fp 候選門檻
                        continue
                    pair = tuple(sorted([ka, kb]))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    if pair[0] in member_key and pair[1] in member_key:
                        continue                                # 已在 stage-1 同群、不重報
                    union = len(body_fps[ka] | body_fps[kb])
                    sim = shared / union if union else 0.0
                    if sim < sim_thresh:                        # 閘3：精確 Jaccard 門檻
                        continue
                    ma, mb = meta.get(pair[0]), meta.get(pair[1])
                    if not ma or not mb:
                        continue
                    # 紅隊 L2-LOW：shape_hash 相同屬 stage-1 EXACT/RENAMED 職責，stage-2 只報「非同形」
                    # 的 Type-3 近似（避免 STRUCTURAL_NEAR 出 sim=1.0 的語義矛盾）。
                    if ma["shape_hash"] == mb["shape_hash"]:
                        continue
                    if not _in_scope([ma, mb]):
                        continue
                    pair_members = sorted([ma, mb], key=lambda m: (m["path"], m["line"]))
                    groups.append(_make_dup_group(
                        "STRUCTURAL_NEAR", pair_members, round(sim, 3),
                        f"winnow 近似相似度 {round(sim, 3)}（非逐字、非同形）；務必讀碼確認是否真重複。"))
                    summary["structural_near"] += 1

        # ── call_pattern（opt-in、最低信心🟦）：call_hash 同、shape 不同 ──
        if include_call_pattern:
            by_call: dict[str, list] = defaultdict(list)
            for r in rows:
                if r["call_hash"] and r["has_control_flow"] and r["node_count"] >= min_node:
                    by_call[r["call_hash"]].append(r)
            for _ch, members in by_call.items():
                shapes = {m["shape_hash"] for m in members}
                if len(members) < 2 or len(shapes) == 1:
                    continue   # 同 call 又同 shape 已被 stage-1 涵蓋；要 shape 不同才是正交線索
                if not _in_scope(members):
                    continue
                members.sort(key=lambda m: (m["path"], m["line"]))
                groups.append(_make_dup_group(
                    "CALL_PATTERN_SIM", members, None,
                    "呼叫名集合完全相同、結構不同（正交線索、最低信心）；可能碰巧用同組 helper，務必讀碼。"))
                summary["call_pattern"] += 1

    summary["high_conf_typed_count"] = summary["exact"]
    summary["needs_human_judge_count"] = summary["renamed"] + summary["structural_near"] \
        + summary["call_pattern"]
    advisory: list[str] = []
    if summary["exact"]:
        advisory.append(f"{summary['exact']} 群逐字相同（高信心 Type-1）——仍可能是不同模組的合理相同樣板，"
                        "🟥 只說「逐字相同」不說「該合併」。")
    if summary["renamed"] + summary["structural_near"]:
        advisory.append(f"{summary['renamed'] + summary['structural_near']} 群是改名/近似——結構像≠語義同"
                        "（兩段長得一樣的 if-return 可能業務無關），務必讀碼判定是否真重複。")
    if not summary["stage2_ran"]:
        advisory.append("未跑全域近似（stage-2/3）：只給逐字/同形重複。要找 Type-3 近似請帶 scope_file 或 near_global。")
    if target:
        advisory.append("scope 模式：stage-1（逐字/同形）仍對全 repo 跨檔偵測、只輸出含此檔成員的群；"
                        "stage-2 近似只比與此檔有指紋交集者。total_units_scanned 是全 repo 數。")
    if not advisory:
        advisory.append("未發現結構相同群（名稱級結構層面）；Type-4 語義克隆本工具誠實偵測不到。")
    return {
        "root": abs_path, "scope_file": target, "groups": groups, "summary": summary,
        "verification_reminder": (
            "重複偵測是結構/詞彙的非語義線索：結構相同≠語義相同、Type-4 語義克隆看不到、"
            "動態/反射/codegen 產生的重複看不到；⛔工具永不出「應刪/應合併」，合併前必人工讀碼 + build/CI。"),
        "read_code_advisory": advisory,
    }
