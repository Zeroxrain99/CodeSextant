"""重複/類似功能偵測（統一母版）— 結構指紋 + winnowing，純非語義（功能 B 第一半）。

核心張力（設計 §1.2）：「類似功能」最易踩 embedding 語義相似陷阱（CodeSextant 鐵律拒絕）。
本模組一律把「類似」降維成**結構/詞彙的離散信號**——AST 形狀雜湊、呼叫名集合、winnowing
k-gram 指紋，全程只有雜湊/集合/計數運算，⛔零向量、零語義模型、零 GPU、零新依賴。

三條正交指紋（設計 §3.A.1）：
  - shape_hash（主指紋，抓 Type-1/2）：body 前序遍歷 node-type 序列，identifier→ID、literal→LIT、
    丟匿名標點/註解、**保留**關鍵字 node kind 與控制流結構 → sha1。抹值後改名/換常數仍同形→同 hash。
  - raw_token_hash（Type-1 逐字判定）：**未正規化**的 terminal token 原值串接 → sha1。
    ⛔ 只有 raw_token_hash 也相同才配 EXACT_DUP（紅隊 FIX-2：否則三個語義無關的 __init__ collide）。
  - call_hash（呼叫模式，正交補強）：body 內呼叫節點的被呼叫名 sorted multiset → sha1。
  - winnowing 指紋集（抓 Type-3）：正規化 token 流切 k-gram→crc32→大小 w 滑窗留最小（選代表）。
    guarantee threshold t=w+k−1。k-gram hash 用標準庫 **zlib.crc32**（快、跨進程穩定、零新依賴；
    ⛔不用 Python hash()〔PYTHONHASHSEED 不穩〕、不用 sha1〔短 k-gram 過慢〕、不用 xxhash/mmh3〔新依賴〕）。

結構顯著性硬門檻（紅隊 FIX-2/3，擋 __init__/getter 大宗誤報）：去葉後 body **必含至少一個控制流
節點**（if/for/while/try/match…）才有資格進 RENAMED_DUP 以上；純賦值串/純 return 屬性/純委派呼叫
壓制到 BOILERPLATE_SUPPRESSED。此硬規則取代失效的 kind_diversity 啟發式（紅隊實測 getter diversity=4 擋不住）。

⛔ 鐵律③（唯讀導航圖）：永不出「應刪/應合併」決策，只報「結構相同群 + 位置 + 信心等級」，刪改前人工讀碼+CI。

開關（L0 鐵律 #6，皆 .lower() 容錯）：見 §3.C / switches.md `codesextant_dedup`。
"""
from __future__ import annotations

import hashlib
import os
import zlib

import tree_sitter

from . import complexity, symbols

# 視為 ID 的葉子節點（跨語言通用，抹成佔位符 "ID"——換名不換形）
_IDENT_TYPES = {
    "identifier", "property_identifier", "field_identifier", "type_identifier",
    "shorthand_property_identifier", "shorthand_property_identifier_pattern",
    "private_property_identifier", "statement_identifier", "label_name",
}
# 視為 LIT 的葉子節點（抹成 "LIT"——換常數不換形）。⚠ 紅隊 L1-MEDIUM：Go 整數是 int_literal
# （非 integer/integer_literal）、imaginary_literal 也要列，否則 Go 數值不抹 LIT → int↔float 漏同形。
_LITERAL_TYPES = {
    "integer", "float", "string", "true", "false", "none", "null",
    "integer_literal", "float_literal", "string_literal", "boolean_literal",
    "char_literal", "raw_string_literal", "number", "regex", "nil",
    "interpreted_string_literal", "rune_literal", "int_literal", "imaginary_literal",
    "string_content", "string_fragment", "true_lit", "false_lit",
}
# 控制流節點（結構顯著性門檻：body 含任一即「夠複雜」、有資格判 RENAMED_DUP 以上）。
# ⚠ 紅隊 L1-HIGH：Go 普通 switch 解成 expression_switch_statement（非 switch_statement），漏列會讓
# Go switch dispatch 函數 has_control_flow=False 被當 boilerplate 系統性誤壓制。
_CONTROL_FLOW = {
    "if_statement", "for_statement", "while_statement", "try_statement",
    "match_statement", "with_statement", "if_expression", "for_expression",
    "while_expression", "match_expression", "switch_statement", "loop_expression",
    "conditional_expression", "ternary_expression", "for_in_statement",
    "do_statement", "except_clause", "case_clause", "guard_statement",
    "type_switch_statement", "select_statement", "expression_switch_statement",
}
# 各語言呼叫節點型別（2026-06-19 既有 + 2026-06-22 主流語言一批，tools/_probe_extra.py 坐實）。
# 值＝set（PHP/Ruby 有多種呼叫節點）；_call_names 用 `in` 比對。⚠ Type-4 CALL_PATTERN_SIM 是
# opt-in 次要功能：被呼叫名的 field 未逐語言 probe，_call_names 用常見 field 容錯、精度盡力而為。
_CALL_TYPES: dict[str, set[str]] = {
    "python": {"call"}, "javascript": {"call_expression"}, "typescript": {"call_expression"},
    "tsx": {"call_expression"}, "go": {"call_expression"}, "rust": {"call_expression"},
    "csharp": {"invocation_expression"},
    "java": {"method_invocation"},
    "c": {"call_expression"}, "cpp": {"call_expression"},
    "kotlin": {"call_expression"}, "swift": {"call_expression"},
    "php": {"function_call_expression", "member_call_expression", "scoped_call_expression"},
    "lua": {"function_call"},
    "ruby": {"call", "method_call"},
    "bash": {"command"},
}
_COMMENT_LIKE = {"comment", "line_comment", "block_comment", "doc_comment"}


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, ""))
        return v if v > 0 else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    # 紅隊 L4-LOW：NaN 保護（'nan' 會讓 `sim < nan` 恆 False＝門檻形同關閉）；越界 clamp 由消費端做。
    import math
    try:
        v = float(os.environ.get(name, ""))
    except ValueError:
        return default
    return v if not math.isnan(v) else default


def dedup_enabled() -> bool:
    return not _env_on("CODESEXTANT_DEDUP_DISABLED")


def _node_text(src: bytes, node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


# ── 三條指紋 + winnow 的底層遍歷 ──
def _shape_tokens(src: bytes, body) -> list[str]:
    """前序遍歷 node-type 序列：identifier→ID、literal→LIT、丟匿名標點/註解、保留結構+關鍵字命名節點。"""
    toks: list[str] = []

    def rec(n):
        t = n.type
        if not n.is_named:          # 匿名 token（標點、字面關鍵字符號）→ 丟（保留的是結構命名節點）
            return
        if t in _COMMENT_LIKE:
            return
        if t in _IDENT_TYPES:
            toks.append("ID")       # 葉子，抹值不下鑽
            return
        if t in _LITERAL_TYPES:
            toks.append("LIT")
            return
        toks.append(t)
        for c in n.children:
            rec(c)

    rec(body)
    return toks


def _raw_tokens(src: bytes, body) -> list[str]:
    """terminal token 原值串接（保留 identifier/literal 實際值，給逐字 Type-1 判定）。"""
    toks: list[str] = []

    def rec(n):
        if n.type in _COMMENT_LIKE:
            return
        if n.child_count == 0:      # terminal token
            txt = _node_text(src, n)
            if txt.strip():
                toks.append(txt)
        else:
            for c in n.children:
                rec(c)

    rec(body)
    return toks


def _last_identifier(src: bytes, node) -> str | None:
    """取被呼叫名的最後一段 identifier（a.b.c → c；單 identifier → 自己）。"""
    last = None

    def rec(n):
        nonlocal last
        if n.type in _IDENT_TYPES:
            last = _node_text(src, n)
        for c in n.children:
            rec(c)

    rec(node)
    return last


# 下標型 callee（handlers[key]()）——_last_identifier 會誤取下標 index 名當被呼叫名（紅隊 L1-LOW），
# 直接 skip 不貢獻 call_hash 條目。
_SUBSCRIPT_TYPES = {"subscript", "subscript_expression", "index_expression"}


def _call_names(src: bytes, body, lang_key: str) -> list[str]:
    """body 內所有呼叫節點的被呼叫名 sorted multiset（呼叫模式指紋原料）。"""
    call_types = _CALL_TYPES.get(lang_key, {"call_expression"})
    names: list[str] = []

    def rec(n):
        if n.type in call_types:
            # 被呼叫名的 field 跨語言不同（function=C系/name=Java·Lua/method=Ruby）→ 試常見 field 容錯
            fn = (n.child_by_field_name("function")
                  or n.child_by_field_name("name")
                  or n.child_by_field_name("method"))
            if fn is not None and fn.type not in _SUBSCRIPT_TYPES:
                nm = _last_identifier(src, fn)
                if nm:
                    names.append(nm)
        for c in n.children:
            rec(c)

    rec(body)
    return sorted(names)


def _metadata(body) -> tuple[int, int, bool]:
    """(node_count=named 子孫數, nstmts=body 直接 named children 數, has_control_flow)。"""
    node_count = 0
    has_cf = False

    def rec(n):
        nonlocal node_count, has_cf
        if n.is_named:
            node_count += 1
            if n.type in _CONTROL_FLOW:
                has_cf = True
        for c in n.children:
            rec(c)

    rec(body)
    return node_count, body.named_child_count, has_cf


def _kgram_hash(kgram: tuple) -> int:
    """k-gram → crc32（標準庫、快、跨進程穩定、零依賴）。"""
    return zlib.crc32("\x1f".join(kgram).encode("utf-8")) & 0xFFFFFFFF


def winnow(shape_tokens: list[str], k: int, w: int) -> list[int]:
    """winnowing 指紋（MOSS）：正規化 token 切 k-gram→crc32→大小 w 滑窗留最右最小 hash。

    guarantee threshold t=w+k−1：任何 ≥t 的相同子串保證被偵測。同一最小值連續窗只記一次（降密度）。
    """
    if not shape_tokens:
        return []
    if len(shape_tokens) < k:
        return [_kgram_hash(tuple(shape_tokens))]
    grams = [_kgram_hash(tuple(shape_tokens[i:i + k]))
             for i in range(len(shape_tokens) - k + 1)]
    if len(grams) < w:
        return [min(grams)]
    out: list[int] = []
    prev_pos = -1
    for i in range(len(grams) - w + 1):
        window = grams[i:i + w]
        m = min(window)
        # 最右最小位置（MOSS：同窗多個最小取最右，降重複記錄）
        pos = i + (len(window) - 1 - window[::-1].index(m))
        if pos != prev_pos:
            out.append(m)
            prev_pos = pos
    return out


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _fingerprint_unit(src: bytes, def_node, lang_key: str, *,
                      func_name: str | None = None,
                      min_node_count: int) -> dict | None:
    """對一個 function/method 定義節點算指紋。body 取不到 → None（不指紋）。

    winnow 只在 node_count ≥ min_node_count 才算（FIX-2 省算力：小單元 winnow 無意義）。
    回 {shape_hash, raw_token_hash, call_hash, node_count, nstmts, has_control_flow,
    cognitive, winnow:[...]}。cognitive=P3 D3 認知複雜度（高信心語言 int / 其餘 None）。
    """
    body = complexity.function_body(def_node, lang_key)  # Kotlin function_body 無 field → per-lang fallback
    if body is None:
        return None
    node_count, nstmts, has_cf = _metadata(body)
    cog = complexity.cognitive_complexity(body, lang_key, func_name, src)
    shape = _shape_tokens(src, body)
    raw = _raw_tokens(src, body)
    calls = _call_names(src, body, lang_key)
    k = _env_int("CODESEXTANT_DEDUP_WINNOW_K", 5)
    w = _env_int("CODESEXTANT_DEDUP_WINNOW_W", 4)
    # winnow 指紋落盤前去重（紅隊 L4-HIGH：同一函數內 winnow 會在多位置吐同一 fp_value，不去重
    # 會讓 DF-cap 的 COUNT(*) 把「單函數內重複」誤算成「跨函數氾濫」→ 把真 Type-3 近似克隆 flood 砍光）
    # + gate has_cf（紅隊 L2-HIGH/L4-LOW：無控制流的大型樣板 __init__/builder 根本不進 stage-2 倒排，
    # 讓 stage-2 STRUCTURAL_NEAR 自動繼承「結構顯著性硬門檻」、不再漏判樣板、同時省算力防膨脹）。
    winnow_fps = (sorted(set(winnow(shape, k, w)))
                  if (node_count >= min_node_count and has_cf) else [])
    return {
        "shape_hash": _sha1("\x02".join(shape)),
        "raw_token_hash": _sha1("\x02".join(raw)),
        "call_hash": _sha1("\x02".join(calls)) if calls else None,
        "node_count": node_count,
        "nstmts": nstmts,
        "has_control_flow": has_cf,
        "cognitive": cog,
        "winnow": winnow_fps,
    }


def extract_fingerprints_from_source(source: bytes, lang_key: str = "python", *,
                                     file_path: str = "<memory>",
                                     min_node_count: int | None = None, tree=None) -> list[dict]:
    """抽一段原始碼裡每個 function/method 的結構指紋（不混進 extract_symbols，守單一職責）。

    回 list[dict]：每筆 = {name, kind, line, end_line, scope, shape_hash, raw_token_hash,
    call_hash, node_count, nstmts, has_control_flow, winnow:[fp_value...]}。
    fail-loud：source 非 bytes → TypeError；lang_key 不支援 → ValueError。
    """
    if not isinstance(source, (bytes, bytearray)):
        raise TypeError(
            f"extract_fingerprints_from_source 需要 bytes，收到 {type(source).__name__}（{file_path}）")
    spec = symbols.LANGUAGE_SPECS.get(lang_key)
    if spec is None:
        raise ValueError(
            f"extract_fingerprints_from_source 不支援的語言 '{lang_key}'（{file_path}）")
    if min_node_count is None:
        min_node_count = _env_int("CODESEXTANT_DEDUP_MIN_NODE_COUNT", 15)

    always: dict = spec["always"]
    scope_only: dict = spec.get("scope_only", {})
    name_rules: dict = spec.get("name_rules", {})   # 無 name field 節點取名策略（C/C++ c_declarator、Kotlin child:）
    if tree is None:    # 紅隊 L4-MEDIUM：index 共用 tree 省重複 parse
        parser = tree_sitter.Parser(symbols._ts_language(spec["language"]))
        tree = parser.parse(bytes(source))

    out: list[dict] = []

    def walk(node, scope_parts: list[str]) -> None:
        child_scope = scope_parts
        if node.type in always:
            # 套 name_rules（與 symbols.extract_symbols 一致）；有 name field 的語言 rule=None→_name_of 不變行為。
            # ⛔ 原直接 _name_of 不套 rule → C/C++/Kotlin fingerprint name 全 <anon>（dedup/cognitive 落盤名失真）
            name = symbols._extract_name(source, node, name_rules.get(node.type))
            if always[node.type] in ("function", "method"):
                fp = _fingerprint_unit(source, node, lang_key, func_name=name,
                                       min_node_count=min_node_count)
                if fp is not None:
                    fp.update({"name": name, "kind": always[node.type],
                               "line": node.start_point[0] + 1,
                               "end_line": node.end_point[0] + 1,
                               "scope": ".".join(scope_parts)})
                    out.append(fp)
            child_scope = scope_parts + [name]
        elif node.type in scope_only:
            fld = node.child_by_field_name(scope_only[node.type])
            if fld is not None:
                child_scope = scope_parts + [_node_text(source, fld)]
        for c in node.children:
            walk(c, child_scope)

    walk(tree.root_node, [])
    return out


def extract_fingerprints(file_path: str, *, min_node_count: int | None = None) -> list[dict]:
    """讀檔抽指紋。副檔名不支援 → ValueError；讀不到 → FileNotFoundError。"""
    lang_key = symbols.language_for_file(file_path)
    if lang_key is None:
        raise ValueError(f"抽指紋失敗：不支援的副檔名 {file_path}")
    try:
        with open(file_path, "rb") as f:
            source = f.read()
    except OSError as exc:
        raise FileNotFoundError(f"抽指紋失敗：讀不到檔 {file_path}（{exc}）") from exc
    return extract_fingerprints_from_source(source, lang_key, file_path=file_path,
                                            min_node_count=min_node_count)
