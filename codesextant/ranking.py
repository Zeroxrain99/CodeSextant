"""重要度排序模組 — PageRank 給「最重要的 N 個符號」。

設計來源（抄 PoC / aider repomap 思路）：
  - 把「被定義的符號」當圖的節點，引用邊（誰用了誰）當連結。
  - 一個符號被越多「本身也重要」的符號引用 → 它越重要（PageRank 的遞迴定義）。
  - aider 的 repomap 用同樣的 graph-rank 思路挑 token 預算內最該給 LLM 看的符號。

實作刻意用純 Python power iteration（冪迭代），不引入 networkx/scipy 依賴
（保持引擎輕量、好被 daemon 打包；符號數即使上萬，這個規模冪迭代也夠快）。

職責（單一）：吃「符號清單 + 引用邊清單」，吐出帶 rank 分數、由高到低排序的符號。
不碰 SQLite、不碰 jedi。所有狀態都在函數內局部，重入安全、無全域污染。
"""
from __future__ import annotations

import os
from bisect import bisect_right
from collections import Counter
from heapq import nlargest

# 高信心引用邊的權重（jedi 確認的指向比名稱比對可信，給更高權重）
_CONFIDENCE_WEIGHT = {"high": 1.0, "low": 0.25}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


def _well_named(name: str) -> bool:
    """命名規範的公開符號（含底線分隔或大小寫混合＝snake/camel/Pascal）。"""
    if name.startswith("_"):
        return False
    return ("_" in name) or (name != name.lower() and name != name.upper())


def _symbol_quality_mult(name: str, defines_count: int) -> float:
    """queue 5（邊權重符號品質係數，aider 啟發式）——凸顯架構性公開 API、壓低低訊號/氾濫符號。

    well-named 公開符號(len>=門檻) ×WELLNAMED；私有 _開頭 ×PRIVATE；在 >N 檔重複定義(過於常見、
    如 utils/handle/run 氾濫名) ×COMMON。全做 config（L0 鐵律 #6 可調）。
    """
    mult = 1.0
    if name.startswith("_"):
        mult *= _env_float("CODESEXTANT_RANK_PRIVATE_MULT", 0.1)
    elif len(name) >= _env_int("CODESEXTANT_RANK_WELLNAMED_MINLEN", 8) and _well_named(name):
        mult *= _env_float("CODESEXTANT_RANK_WELLNAMED_MULT", 10.0)
    if defines_count > _env_int("CODESEXTANT_RANK_COMMON_THRESHOLD", 5):
        mult *= _env_float("CODESEXTANT_RANK_COMMON_MULT", 0.1)
    return mult


def _build_personalization(symbols: list[dict], focus_symbols=None,
                           focus_files=None) -> dict | None:
    """queue 4（query-aware PageRank）——把呼叫端顯式傳入的 focus set 轉成 personalization 向量。

    ⛔ boost 來源是「呼叫端顯式說我在改 X」(focus_symbols/focus_files)，**非監聽對話/接 LLM**
    （守零雲端/不接 LLM 鐵則；aider 是聊天前端才監聽對話，CodeSextant 是被呼叫的導航工具）。
    focus 命中符號的 teleport 權重 +boost 倍。無 focus 回 None（退均勻 teleport＝原靜態行為）。
    """
    fs = set(focus_symbols or [])
    ff = {_norm(f) for f in (focus_files or [])}
    if not fs and not ff:
        return None
    boost = _env_float("CODESEXTANT_PAGERANK_FOCUS_BOOST", 10.0)
    p: dict[str, float] = {}
    for s in symbols:
        w = 1.0
        if s.get("name") in fs:
            w += boost
        if _norm(s.get("path")) in ff:
            w += boost
        p[_symbol_id(s)] = w
    return p


def _symbol_id(sym: dict) -> str:
    """符號的唯一識別：path::scope::name::line。
    用 line 一起當 id，避免同檔同名（如多個同名 getter/setter）互相蓋掉。
    """
    return f"{sym['path']}::{sym.get('scope', '')}::{sym['name']}::{sym['line']}"


def _norm(path: str | None) -> str:
    return os.path.normcase(os.path.abspath(path)) if path else ""


def _compute_pagerank_scores(symbols: list[dict], refs: list[dict],
                             *, damping: float = 0.85, max_iter: int = 100,
                             tol: float = 1.0e-6,
                             personalization: dict[str, float] | None = None
                             ) -> list[float]:
    """對符號圖跑 PageRank，回傳與 symbols 同順序的 score list。

    邊方向：src（引用端所在檔的代表符號）→ def（被引用的符號定義）。
    PageRank 讓分數從引用端流向被引用端，所以「被很多重要符號引用」的符號得高分。
    src 對應不到某個符號節點時（如模組頂層呼叫），當作「外部入流」均攤計入。

    queue 5：邊權重疊「被引用符號的品質係數」（well-named 公開 ×10 / 私有 ×0.1 / 過於常見 ×0.1）。
    queue 4：personalization（{symbol_id: 偏好權重}）灌進 teleport 向量＝query-aware 排序；
             None 退均勻 teleport（原靜態行為，向後相容）。

    symbols 為空回 []。內部以 list index 當 node id；公開 compute_pagerank 最後才轉字串 id，
    rank_symbols 則直接消費 list，避免大型 map 為 57 萬節點建立兩份巨型字串 dict。
    """
    if not symbols:
        return []

    n = len(symbols)

    # namegraph 已可用 multiplicity 折疊同一行的重複 occurrence；db 舊邊沒有此欄位則視為 1。
    # 先聚合再建圖，既保留原本權重，也讓後續只處理 unique edge。
    collapsed_refs: dict[tuple, int] = {}
    for e in refs:
        key = (e.get("src_path"), e.get("src_line"), e.get("def_path"),
               e.get("def_line"), e.get("confidence", "low"))
        try:
            multiplicity = int(e.get("multiplicity", 1) or 1)
        except (TypeError, ValueError):
            multiplicity = 1
        if multiplicity < 1:
            multiplicity = 1
        collapsed_refs[key] = collapsed_refs.get(key, 0) + multiplicity

    # path 正規化在 Windows 不便宜；57 萬符號通常只分布在數萬個檔，依原字串快取可避免
    # 同一 path 在 defines/by_pos/by_body 三層被 os.path.abspath 重算數十次。
    norm_cache: dict[object, str] = {}

    def _norm_cached(path) -> str:
        if not path:
            return ""
        try:
            return norm_cache[path]
        except KeyError:
            value = _norm(path)
            norm_cache[path] = value
            return value

    target_positions = {
        (_norm_cached(dp), dl)
        for (_sp, _sl, dp, dl, _confidence) in collapsed_refs
        if dp is not None and dl is not None
    }
    source_paths = {
        _norm_cached(sp)
        for (sp, _sl, _dp, _dl, _confidence) in collapsed_refs
        if sp
    }

    # 只為實際引用邊的 target/source 建定位表。舊版對 57 萬符號全部建 by_pos/by_body，
    # 即使圖上只有數千條邊也付出全圖巨量 dict/list 成本。
    by_pos: dict[tuple, int] = {}
    target_name_of: dict[int, str] = {}
    file_rep: dict[str, int] = {}
    file_rep_line: dict[str, int] = {}
    by_body: dict[str, list] = {}
    for pos, s in enumerate(symbols):
        p = s.get("path")
        if p is None:
            continue
        np = _norm_cached(p)
        line = s["line"]
        if (np, line) in target_positions:
            by_pos[(np, line)] = pos
            target_name_of[pos] = s["name"]
        if np in source_paths:
            if np not in file_rep_line or line < file_rep_line[np]:
                file_rep[np] = pos
                file_rep_line[np] = line
            by_body.setdefault(np, []).append(
                (line, int(s.get("end_line", line) or line), pos))
    for lst in by_body.values():
        lst.sort()
    body_starts = {path: [row[0] for row in rows] for path, rows in by_body.items()}
    src_node_cache: dict[tuple[str, int], int | None] = {}

    # queue 5：只計算真正成為 edge target 的名稱在幾個 distinct 檔定義；其他 57 萬節點
    # 不會用到品質係數，無須建立全量 name→file 集合。
    target_names = set(target_name_of.values())
    _seen_np: set = set()
    defines: Counter[str] = Counter()
    if target_names:
        for s in symbols:
            name = s["name"]
            if name not in target_names:
                continue
            k = (name, _norm_cached(s.get("path")))
            if k not in _seen_np:
                _seen_np.add(k)
                defines[name] += 1

    def _src_node(src_path, src_line):
        """src_line 映射到「包含它的最內層符號」當來源節點；無 src_line / 找不到 → fallback
        file_rep（向後相容：db 高信心邊有 src_line＝更精確的 caller；src_line=0 退 file_rep）。"""
        np = _norm_cached(src_path) if src_path else ""
        cache_key = (np, int(src_line or 0))
        if cache_key in src_node_cache:
            return src_node_cache[cache_key]
        if src_line and np in by_body:
            rows = by_body[np]
            pos = bisect_right(body_starts[np], src_line) - 1
            while pos >= 0:
                ln, el, node_index = rows[pos]
                if ln <= src_line <= el:
                    src_node_cache[cache_key] = node_index
                    return node_index
                pos -= 1
        result = file_rep.get(np)
        src_node_cache[cache_key] = result
        return result

    # 建稀疏加權鄰接 out_targets[i] = {j: summed_weight}；只有有邊的來源才占一個 dict。
    # namegraph 會保留每次 occurrence 來表達引用次數，但同一 caller→target 可能因此有數萬筆
    # 重複邊。PageRank 只需要總權重：先聚合可保持完全相同的數學語義，又避免每次迭代重走
    # 全部 occurrence（大型 TS repo 曾因此讓 /get_map 超過 client 30s timeout）。
    out_targets: dict[int, dict[int, float]] = {}
    external_inflow: dict[int, float] = {}
    quality_cache: dict[tuple[str, int], float] = {}

    for (src_path, src_line, dp, dl, confidence), multiplicity in collapsed_refs.items():
        if dp is None or dl is None:
            continue
        j = by_pos.get((_norm_cached(dp), dl))
        if j is None:
            continue
        w = _CONFIDENCE_WEIGHT.get(confidence, 0.25) * multiplicity
        # queue 5：疊被引用符號的品質係數（well-named 公開 ×10 / 私有 ×0.1 / 過於常見 ×0.1）
        tname = target_name_of.get(j, "")
        quality_key = (tname, defines.get(tname, 1))
        try:
            quality = quality_cache[quality_key]
        except KeyError:
            quality = _symbol_quality_mult(*quality_key)
            quality_cache[quality_key] = quality
        w *= quality

        i = _src_node(src_path, src_line)
        if i is None:
            external_inflow[j] = external_inflow.get(j, 0.0) + w
            continue
        if i == j:
            continue
        edges = out_targets.setdefault(i, {})
        edges[j] = edges.get(j, 0.0) + w

    n_refs = max(1, sum(collapsed_refs.values()))
    # queue 4：personalization teleport 向量 P（focus 偏好）；無則均勻 1/n（原靜態行為，向後相容）
    if personalization:
        raw_p = [personalization.get(_symbol_id(s), 1.0) for s in symbols]
        tot_p = sum(raw_p) or 1.0
        P = [value / tot_p for value in raw_p]
    else:
        P = [1.0 / n] * n
    # 預先正規化稀疏 transition。沒有可用邊/外部入流時 P 本身就是固定點。
    transitions: dict[int, list[tuple[int, float]]] = {}
    for i, edges in out_targets.items():
        total_w = sum(edges.values())
        if total_w > 0:
            transitions[i] = [(j, w / total_w) for j, w in edges.items()]
    active = set(external_inflow)
    active.update(out_targets)
    for edges in out_targets.values():
        active.update(edges)
    if not active:
        return P

    # 對無任何入/出邊的孤立節點，分數永遠是同一 scalar × P[j]。把數十萬孤點聚合成
    # inactive_factor 一個狀態；每輪只走 active endpoints，結束才 materialize 全部結果。
    active_p_sum = sum(P[i] for i in active)
    inactive_p_sum = max(0.0, 1.0 - active_p_sum)
    inactive_factor = 1.0
    active_score = {i: P[i] for i in active}

    for _ in range(max_iter):
        dangling_sum = inactive_factor * inactive_p_sum
        for i in active:
            if i not in transitions:
                dangling_sum += active_score[i]

        base_factor = (1.0 - damping) + damping * dangling_sum
        new_active = {i: base_factor * P[i] for i in active}
        for i, edges in transitions.items():
            source_score = active_score[i]
            for j, portion in edges:
                new_active[j] += damping * source_score * portion
        for j, infl in external_inflow.items():
            new_active[j] += damping * infl / n_refs

        delta = sum(abs(new_active[i] - active_score[i]) for i in active)
        delta += abs(base_factor - inactive_factor) * inactive_p_sum
        active_score = new_active
        inactive_factor = base_factor
        if delta < tol:
            break

    return [
        active_score[i] if i in active_score else inactive_factor * P[i]
        for i in range(n)
    ]


def compute_pagerank(symbols: list[dict], refs: list[dict],
                     *, damping: float = 0.85, max_iter: int = 100,
                     tol: float = 1.0e-6,
                     personalization: dict[str, float] | None = None) -> dict[str, float]:
    """公開相容層：對符號圖跑 PageRank，回傳 {symbol_id: score}。"""
    scores = _compute_pagerank_scores(
        symbols, refs, damping=damping, max_iter=max_iter, tol=tol,
        personalization=personalization)
    return {_symbol_id(s): scores[i] for i, s in enumerate(symbols)}


def _line_of(sid: str) -> int:
    """從 symbol_id 取出 line（id 格式 path::scope::name::line）。"""
    try:
        return int(sid.rsplit("::", 1)[1])
    except (IndexError, ValueError):
        return 1 << 30


def rank_symbols(symbols: list[dict], refs: list[dict], *, top_n: int | None = None,
                 damping: float = 0.85, focus_symbols=None, focus_files=None) -> list[dict]:
    """對符號排重要度，回傳帶 "rank" 分數、由高到低排序的符號清單。

    每個回傳 dict = 原符號欄位 + "rank"（float 分數）。top_n 給了就只回前 N 個。
    focus_symbols/focus_files（queue 4 query-aware）：呼叫端顯式傳入「在改/在問的符號/檔」，
    讓排序偏向相關處（轉成 personalization 向量）；不傳＝原靜態結構中心度排序。
    """
    personalization = _build_personalization(symbols, focus_symbols, focus_files)
    scores = _compute_pagerank_scores(
        symbols, refs, damping=damping, personalization=personalization)
    if top_n is not None:
        # map 通常只要前 100~200 個；不要先複製 57 萬 dict 再全排序。
        chosen = nlargest(
            top_n, enumerate(symbols),
            key=lambda item: (scores[item[0]], -item[0]),
        )
        return [dict(s, rank=scores[i]) for i, s in chosen]
    ranked = [dict(s, rank=scores[i]) for i, s in enumerate(symbols)]
    ranked.sort(key=lambda x: x["rank"], reverse=True)
    return ranked
