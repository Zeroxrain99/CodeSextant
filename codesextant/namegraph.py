"""名稱級全圖引用邊 — 修 map 開箱退化（PageRank 均分）+ 撐起未接線偵測。

退化根因（親讀 engine/ranking/storage 三層坐實）：
  - index_project 只抽符號、**不建任何引用邊**；refs 表只有對符號跑過
    find_references(persist=True) 才落高信心 jedi/ts-morph 邊。
  - get_map → compute_pagerank 吃 store.all_refs()，開箱 refs=[] → 全靠均勻
    teleport P=[1/n] → 所有符號 rank 完全相等（166 符號 distinct rank=1，無排序價值）。

解法（抄 aider repomap「名稱交集建邊 + PageRank」精髓，移植到本專案符號級圖）：
  - aider：對「同時被定義且被引用」的 identifier 名，連邊 referencer→definer 跑
    PageRank。CodeSextant 的 symbols 表已有全部定義（節點），缺的只是「每個檔用到
    哪些已定義名」——用 regex token 化補出名稱級邊，**body-aware** 排除定義行 self-token。

⛔ 鐵則（交接核心約束 + 紅藍守住，違反即破壞既有能力或踩四陷阱）：
  1. **in-memory only**：名稱級邊**絕不落 refs 表**。callgraph/impact/find_references
     全讀 refs 表，名稱級邊一旦落盤會用「低信心同名雜訊」污染它們的真解析結果。
     名稱級邊只在 get_map 當下臨時建、餵 compute_pagerank、用完即丟。
  2. **全低信心**：純文字交集含同名干擾/字串/註解雜訊，一律 confidence="low"
     （compute_pagerank 給 0.25 權重）；db 的 high 邊（真 import 解析）權重 1.0
     仍主導，名稱級邊只補「開箱無邊」的全圖結構底盤。
  3. **不碰四陷阱**：無 embedding 語義相似 / 無 LSP 重後端 / 不改符號 / 不引圖庫。
     純 regex + body-aware 掃描 + 既有純 Python power-iteration。

body-aware 設計（紅隊 L1-HIGH 修正核心）：
  - 對每個 identifier occurrence，**排除落在它自己定義範圍 [line,end_line] 內的 self-token**
    （定義行 + 遞迴自呼叫），但**保留同檔別符號 body 內 + 跨檔**的 occurrence。
  - 舊版「整檔排除自己定義的名」過度排除：連同檔真互呼叫都消掉 → 單模組/同檔互呼叫為主的
    專案 name 邊=0 原樣退回均分（紅隊實測：單檔 dispatch 被 4 個同檔 handler 呼叫仍全均分）。
  - 一個 cross-ref occurrence 一條邊、**不去重** → compute_pagerank 自然疊加，體現「被呼叫
    越多次越重要」（紅隊實測舊版「跨檔 1 次」恆贏「同檔 5 次」，違反 PageRank 本意）。

compute_pagerank 對接約束（ranking.py 親讀坐實）：
  - 它只認 def_path+def_line 都有、且 (normcase(def_path), def_line) 能對上某符號節點
    (path, line) 的邊。所以名稱級邊必須 **fan-out**：名 X 在檔 F 出現 → 對每個定義 X
    的符號 (dp, dl) 各連一條 (src_path=F, def_path=dp, def_line=dl, confidence=low)。
  - 路徑全程 normcase(abspath)（與 ranking._norm / storage.project_key 對齊，消 Windows
    大小寫不一致導致 body 排除失效的 latent 假陰性）。src_path 經 file_rep 對到該檔代表
    符號；同節點自環 (i==j) 由 compute_pagerank 自動跳過。
  ⚠ file-rep collapse 的已知限制：單檔/同檔結構下所有邊源頭都 collapse 到該檔第一符號，
    「誰呼叫」的 caller 粒度模糊，但「誰被呼叫」（被引用符號）仍能凸顯、脫離均分。

開關（L0 鐵律 #6，皆 .lower() 容錯）：
  - CODESEXTANT_NAMEGRAPH_DISABLED=1/true/yes/on → get_map 不建名稱級邊（退回原退化行為）。
  - CODESEXTANT_NAMEGRAPH_MAX_FANOUT=<int>  同名定義 fan-out 上限（預設 20；防氾濫名笛卡兒積爆邊）。
  - CODESEXTANT_NAMEGRAPH_MAX_FILES=<int>   map 顯式掃描檔數；未設時依 symbol 數自適應（12~5000）。
  - CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES=<int> 唯一邊硬上限（預設 250000；防單次查詢吃光 RAM）。
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict

# identifier token：字母/底線開頭，後接字母數字底線。一次抽出整檔所有 identifier，再跟「已
# 定義名集合」做交集——關鍵字（def/class/if…）自然不在定義名集合裡被濾掉，不需關鍵字黑名單。
# 字串/註解內的同名是雜訊，由 ∩定義名 + low 權重 + 品質係數 + body-aware 排除四重壓制。
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, ""))
        return v if v > 0 else default
    except ValueError:
        return default


def namegraph_enabled() -> bool:
    """名稱級邊是否啟用（預設啟用；CODESEXTANT_NAMEGRAPH_DISABLED 關閉）。"""
    return not _env_on("CODESEXTANT_NAMEGRAPH_DISABLED")


def map_file_limit(symbol_count: int) -> tuple[int, bool]:
    """大型 map 的即時計算檔數上限；回 (limit, is_adaptive)。

    顯式 CODESEXTANT_NAMEGRAPH_MAX_FILES 永遠優先。未設時用固定 work budget / symbol_count，
    小專案仍可全掃 5000 檔；57 萬 symbol 的 monorepo 會落在約 12 檔，讓冷查接近 30 秒內
    有硬邊界，而不是建到數 GB 才由外殼逾時。
    """
    raw = os.environ.get("CODESEXTANT_NAMEGRAPH_MAX_FILES")
    if raw:
        try:
            explicit = int(raw)
            if explicit > 0:
                return explicit, False
        except ValueError:
            pass
    work_budget = _env_int("CODESEXTANT_NAMEGRAPH_MAP_WORK_BUDGET", 7_000_000)
    limit = work_budget // max(1, int(symbol_count))
    return min(5000, max(12, limit)), True


def _read_text(path: str) -> str | None:
    """讀檔成文字（errors=replace 不爆）；讀不到回 None。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _normp(path: str) -> str:
    """路徑正規化 normcase(abspath) — 與 ranking._norm / storage.project_key 對齊。

    紅隊 L4-LOW 修正：原本只 abspath 不 normcase，Windows 上 'E:\\..\\M.py' vs 'e:\\..\\m.py'
    指同檔卻比不相等 → body 排除失效 → 定義行 self-token 漏排 → 真死碼漏報。全模組統一 normcase。
    """
    return os.path.normcase(os.path.abspath(path))


def _defs_by_name(symbols: list[dict]) -> dict[str, list[tuple[str, int, int]]]:
    """name → [(norm_path, line, end_line), ...]：每個名被哪些符號（在哪、body 範圍）定義。

    含所有 symbols（method/巢狀/頂層變數），與 compute_pagerank 的 by_pos 節點集合一致。
    end_line 給 body-aware 排除「落在符號自己 [line,end_line] 內的 self-token」用。
    """
    d: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    path_cache: dict[object, str] = {}
    for s in symbols:
        p = s.get("path")
        if p is None:
            continue
        try:
            np = path_cache[p]
        except KeyError:
            np = _normp(p)
            path_cache[p] = np
        line = s["line"]
        end_line = int(s.get("end_line", line) or line)
        d[s["name"]].append((np, line, end_line))
    return d


def _select_indexed_files(indexed_files, max_files, preferred_files=None):
    """決定性分層取樣：優先 focus files，其餘均勻跨全 repo，避免永遠只看排序前綴。"""
    files = list(indexed_files)
    limit = max(1, int(max_files))
    if len(files) <= limit:
        return files, "all"

    available = set(files)
    chosen: list[str] = []
    seen: set[str] = set()
    for path in preferred_files or []:
        np = _normp(path)
        if np in available and np not in seen:
            chosen.append(np)
            seen.add(np)
            if len(chosen) >= limit:
                return chosen, "focus"

    remaining = [p for p in files if p not in seen]
    slots = min(limit - len(chosen), len(remaining))
    if slots > 0:
        # 每個等寬 bucket 取中點，涵蓋頭中尾且結果可重現。
        for i in range(slots):
            index = min(len(remaining) - 1, int((i + 0.5) * len(remaining) / slots))
            path = remaining[index]
            if path not in seen:
                chosen.append(path)
                seen.add(path)
    return chosen, "stratified"


def _scan_cross_refs(symbols, indexed_files, read_text, max_fanout, max_files,
                     preferred_files=None):
    """body-aware 掃全 repo 的核心（build_name_edges + compute_external_usage 共用，DRY）。

    回 (refs, defs, over_fanout, meta)：
      refs = {(src_norm, src_line, name, def_norm, def_line): multiplicity}：每個「不落在自己定義
             body 內」的已定義名 occurrence；同一行同一 target 折成一筆但保留引用次數。src_line 記真
             occurrence 行號，給 compute_pagerank 把來源映射到真 caller 符號（非 collapse 到檔第一符號）。
      defs = _defs_by_name 結果。over_fanout = 同名定義超上限的名集合。meta = 掃描統計。

    body-aware：token 落在某定義自己的 [line,end_line] → 不算它的 ref（排定義行 self-token +
    遞迴）；同檔別符號 body 內 + 跨檔的 occurrence 都算（保留同檔真互呼叫）。over_fanout 名整個
    跳過。max_files 截斷防超大 repo（紅隊 L4-HIGH：compute_external_usage 原缺此保護 18k 檔卡死）。
    """
    defs = _defs_by_name(symbols)
    over_fanout = {n for n, lst in defs.items() if len(lst) > max_fanout}
    target_names = set(defs) - over_fanout
    meta = {"defined_names": len(defs), "scanned_files": 0, "total_files": 0,
            "truncated": False, "over_fanout_names": len(over_fanout),
            "skipped_fanout_names": len(over_fanout), "sampling": "all",
            "truncation_reasons": []}
    if not target_names:
        return {}, defs, over_fanout, meta

    if indexed_files is None:
        indexed_files = sorted({_normp(s["path"]) for s in symbols if s.get("path")})
    else:
        indexed_files = [_normp(p) for p in indexed_files]
    meta["total_files"] = len(indexed_files)
    if len(indexed_files) > max_files:
        indexed_files, sampling = _select_indexed_files(
            indexed_files, max_files, preferred_files)
        meta["sampling"] = sampling
        meta["truncated"] = True
        meta["truncation_reasons"].append("file_budget")

    refs: dict[tuple[str, int, str, str, int], int] = {}
    max_unique_edges = _env_int("CODESEXTANT_NAMEGRAPH_MAX_UNIQUE_EDGES", 250_000)
    edge_budget_hit = False
    for fp in indexed_files:
        text = read_text(fp)
        if not text:
            continue
        meta["scanned_files"] += 1
        for occ_line, line_text in enumerate(text.splitlines(), 1):
            names = Counter(
                m.group() for m in _IDENT_RE.finditer(line_text)
                if m.group() in target_names)
            for name, multiplicity in names.items():
                for (dp, dl, el) in defs[name]:
                    if fp == dp and dl <= occ_line <= el:
                        continue  # 落在自己 body → self-token，不算 ref
                    key = (fp, occ_line, name, dp, dl)
                    if key not in refs and len(refs) >= max_unique_edges:
                        edge_budget_hit = True
                        break
                    refs[key] = refs.get(key, 0) + multiplicity
                if edge_budget_hit:
                    break
            if edge_budget_hit:
                break
        if edge_budget_hit:
            break
    if edge_budget_hit:
        meta["truncated"] = True
        meta["truncation_reasons"].append("edge_budget")
    return refs, defs, over_fanout, meta


def build_name_edges(symbols: list[dict], *, indexed_files: list[str] | None = None,
                     read_text=_read_text, max_fanout: int | None = None,
                     max_files: int | None = None,
                     preferred_files: list[str] | None = None) -> tuple[list[dict], dict]:
    """建名稱級全圖 low 邊（餵 compute_pagerank）。body-aware（保留同檔真互呼叫、排定義行雜訊）。

    參數
    ----
    symbols : 全專案符號清單（store.get_symbols()），每筆需 path/name/line/end_line。
    indexed_files : 要掃描「用到哪些名」的檔清單；None 則用 symbols 出現過的所有 path。
    read_text : 讀檔函數（可注入，方便測試）。
    max_fanout / max_files : 覆寫對應 env 上限（None 走 env / 預設）。

    回 (edges, meta)：
      edges = [{src_path, src_line, symbol_name, def_path, def_line, confidence:"low",
                multiplicity}, ...]（同一行相同 target 折成一邊，multiplicity 保留引用次數）。
      meta  = {defined_names, scanned_files, total_files, truncated, over_fanout_names,
               skipped_fanout_names, total_edges}
    符號為空 / 無可用目標名 → ([], meta)。
    """
    if max_fanout is None:
        max_fanout = _env_int("CODESEXTANT_NAMEGRAPH_MAX_FANOUT", 20)
    if max_files is None:
        max_files = _env_int("CODESEXTANT_NAMEGRAPH_MAX_FILES", 5000)
    refs, _defs, _over, meta = _scan_cross_refs(
        symbols, indexed_files, read_text, max_fanout, max_files, preferred_files)
    edges = [{
        "src_path": sp, "src_line": sl, "symbol_name": name,
        "def_path": dp, "def_line": dl, "confidence": "low",
        "multiplicity": multiplicity,
    } for (sp, sl, name, dp, dl), multiplicity in refs.items()]
    meta["unique_edges"] = len(edges)
    meta["total_edges"] = sum(refs.values())
    return edges, meta


def compute_external_usage(symbols: list[dict], *, indexed_files: list[str] | None = None,
                           read_text=_read_text, max_fanout: int | None = None,
                           max_files: int | None = None
                           ) -> tuple[dict[tuple, int], set[str], dict]:
    """每個定義符號「在自己 body 之外」被名稱提及的次數（功能 A 未接線判定的計算層）。

    body-aware（排定義行 self-token + 遞迴自呼叫，保留同檔別符號 body 外 + 跨檔的提及）。
    零 external usage = 沒有任何「自己 body 以外」的地方提到此名 = 未接線候選。

    ⚠ 名稱級天花板（誠實標明、無法在此層消除）：
      - 同名多定義：純名稱無法區分呼叫的是哪個同名定義 → 真沒人用的那個會因「別處用同名的另一個」
        被算有 usage（漏報）。
      - 純 token 化不分字串/註解：符號名出現在任何字串/註解中也算 external usage → 真未接線符號
        可能因被某處字串/註解提及而漏報（偏保守、不誤刪）。
    故功能 A 永遠是低信心線索層，須 deadcode 真解析（jedi/ts-morph）複核。

    回 (usage, over_fanout, meta)：
      usage = {(norm_def_path, def_line, name): external_usage_count}（含 0；只統計 fanout<=上限的名）。
      over_fanout = 同名定義數超過 fan-out 上限的名集合（這些名未統計，功能 A 標 UNKNOWN_FANOUT）。
      meta = 掃描統計（含 truncated；功能 A 透傳給誠實層警告 18k 檔截斷時別誤信）。
    """
    if max_fanout is None:
        max_fanout = _env_int("CODESEXTANT_NAMEGRAPH_MAX_FANOUT", 20)
    if max_files is None:
        max_files = _env_int("CODESEXTANT_NAMEGRAPH_MAX_FILES", 5000)
    refs, defs, over_fanout, meta = _scan_cross_refs(
        symbols, indexed_files, read_text, max_fanout, max_files)
    usage: dict[tuple, int] = {}
    for name, lst in defs.items():
        if name in over_fanout:
            continue
        for (dp, dl, _el) in lst:
            usage[(dp, dl, name)] = 0
    for (_sp, _sl, name, dp, dl), multiplicity in refs.items():
        key = (dp, dl, name)
        if key in usage:
            usage[key] += multiplicity
    return usage, over_fanout, meta
