"""註解管理 — tree-sitter 抽 comment 節點 + 行號 + 歸屬符號（功能 B 第二半）。

定位（設計 §3.B）：「一次看全 vs 只看該看的 + 知道哪行」——docstring 覆蓋率 / TODO·FIXME
在哪行 / 註解密度，給 repo 摘要 + 精確定位。**輕量、不踩四陷阱、給線索非決策**。

職責單一：吃一個檔路徑或一段原始碼，吐該檔的註解清單。不混進 extract_symbols（守 symbols.py
單一職責），但共用 symbols 的 `_ts_language()` grammar cache 與 LANGUAGE_SPECS 的定義節點表
（拿來標 scope + 找 Python docstring 的 body field）。

誠實邊界（設計 §6）：
  - docstring 偵測限「block/module 第一個 named child 為 string」（Python）：被條件式包住、賦值
    給變數、非首位的字串會漏判。
  - 其他語言 doc（Rust ///、Go/TS /** */）靠「緊鄰下方符號」近似對齊 owner_line，巢狀/跨空行多
    可能對不準——覆蓋率對非 Python 是盡力而為。
  - 覆蓋率/密度是結構統計線索，不評斷註解是否正確/過時/同步（那是語義，看不到）。

開關（L0 鐵律 #6，皆 .lower() 容錯）：
  - CODESEXTANT_COMMENTS_DISABLED        整功能 opt-out
  - CODESEXTANT_COMMENT_MARKERS          標記集（預設 TODO,FIXME,HACK,XXX,BUG,NOTE）
"""
from __future__ import annotations

import os
import re

import tree_sitter

from . import symbols

# 各語言 comment 節點型別（2026-06-19 設計 R2 tree-sitter probe 坐實）。rust 三種、其餘統一 comment。
_COMMENT_TYPES: dict[str, set[str]] = {
    "python": {"comment"},
    "javascript": {"comment"},
    "typescript": {"comment"},
    "tsx": {"comment"},
    "go": {"comment"},
    "rust": {"line_comment", "block_comment", "doc_comment"},
    # 2026-06-22 主流語言一批（tools/_probe_extra.py 坐實 comment 節點型別）：
    "csharp": {"comment"},
    "java": {"line_comment", "block_comment"},
    "c": {"comment"},
    "cpp": {"comment"},
    "lua": {"comment"},
    "ruby": {"comment"},
    "php": {"comment"},
    "bash": {"comment"},
    "kotlin": {"line_comment", "multiline_comment"},
    "swift": {"comment", "multiline_comment"},
}

# doc 判定 text 前綴（Rust /// 不同 grammar 版本解成 line_comment 或 doc_comment、TS jsdoc /** 仍歸
# comment，故節點型別 + text-prefix 雙重判定，FIX 設計 §3.B.1）。
_DOC_PREFIXES = ("///", "//!", "/**", "#'")


def comments_enabled() -> bool:
    return os.environ.get("CODESEXTANT_COMMENTS_DISABLED", "").lower() not in (
        "1", "true", "yes", "on")


def markers() -> list[str]:
    raw = os.environ.get("CODESEXTANT_COMMENT_MARKERS", "TODO,FIXME,HACK,XXX,BUG,NOTE")
    return [m.strip() for m in raw.split(",") if m.strip()]


def _marker_re() -> re.Pattern | None:
    ms = markers()
    if not ms:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(m) for m in ms) + r")\b")


def _first_marker(text: str, marker_re) -> str | None:
    if marker_re is None:
        return None
    m = marker_re.search(text)
    return m.group(1) if m else None


def _is_doc(node_type: str, text: str) -> bool:
    if node_type == "doc_comment":
        return True
    t = text.lstrip()
    return any(t.startswith(p) for p in _DOC_PREFIXES)


def _node_text(src: bytes, node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _docstring_string_node(def_node, src: bytes):
    """function/class 定義節點的 docstring string 節點（body 第一個 named child 若 string；
    含 expression_statement 包裹一層的相容處理）。非 string → None。"""
    body = def_node.child_by_field_name("body")
    if body is None or body.named_child_count == 0:
        return None
    first = body.named_child(0)
    if first is None:
        return None
    if first.type == "string":
        return first
    if first.type == "expression_statement" and first.named_child_count > 0:
        inner = first.named_child(0)
        if inner is not None and inner.type == "string":
            return inner
    return None


def extract_comments_from_source(source: bytes, lang_key: str = "python", *,
                                 file_path: str = "<memory>", tree=None) -> list[dict]:
    """從一段原始碼（bytes）抽註解清單。

    回 list[dict]，每筆：{kind(line/block/doc), text, line, end_line, scope, tag(第一 marker 或 None),
    is_doc(bool), owner_line(doc 所屬符號定義行，無則 None)}。依出現順序。

    fail-loud：source 非 bytes → TypeError；lang_key 不支援 → ValueError。
    """
    if not isinstance(source, (bytes, bytearray)):
        raise TypeError(
            f"extract_comments_from_source 需要 bytes，收到 {type(source).__name__}（{file_path}）")
    spec = symbols.LANGUAGE_SPECS.get(lang_key)
    if spec is None:
        raise ValueError(
            f"extract_comments_from_source 不支援的語言 '{lang_key}'（{file_path}）。"
            f"可用：{sorted(symbols.LANGUAGE_SPECS)}")

    comment_types = _COMMENT_TYPES.get(lang_key, {"comment"})
    always: dict = spec["always"]
    is_python = lang_key == "python"
    marker_re = _marker_re()

    if tree is None:    # 紅隊 L4-MEDIUM：index 共用 tree 省重複 parse
        parser = tree_sitter.Parser(symbols._ts_language(spec["language"]))
        tree = parser.parse(bytes(source))
    root = tree.root_node

    out: list[dict] = []
    # pending doc comment（給非 Python 語言「doc comment 緊鄰下方符號」近似回填 owner_line）
    pending_doc: list[dict] = []  # 用 list 當可變單元素 box（閉包寫入）

    def _add_pending_owner(def_line: int) -> None:
        if pending_doc and pending_doc[0] is not None:
            d = pending_doc[0]
            # 緊鄰才回填（定義行 - doc end_line ∈ [0,2]，容 tree-sitter comment 含尾換行的
            # off-by-one〔end_point 落在下一行開頭〕+ 一個空行）
            if 0 <= def_line - d["end_line"] <= 2:
                d["owner_line"] = def_line
        pending_doc.clear()

    def walk(node, scope_parts: list[str]) -> None:
        node_type = node.type
        child_scope = scope_parts

        if node_type in comment_types:
            text = _node_text(source, node)
            is_block = node_type == "block_comment" or text.lstrip().startswith("/*")
            doc = _is_doc(node_type, text)
            rec = {
                "kind": "doc" if doc else ("block" if is_block else "line"),
                "text": text,
                "line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "scope": ".".join(scope_parts),
                "tag": _first_marker(text, marker_re),
                "is_doc": doc,
                "owner_line": None,
            }
            out.append(rec)
            # 紅隊 L3-MEDIUM：Rust `//!`/`/*!` 是「內部文件註解」、文件化的是所在 enclosing 項目
            # （module/crate），⛔不該回填到下方 sibling 符號（否則放檔首的 //! 會被誤算成下方 fn 的
            # docstring、系統性灌高覆蓋率）。只有 outer doc（///、/**）才進 pending_doc 對齊下方符號。
            is_inner = text.lstrip().startswith(("//!", "/*!"))
            if doc and not is_inner:
                pending_doc[:] = [rec]   # outer doc：記為待對齊（下個定義節點若緊鄰就回填）
            else:
                pending_doc.clear()      # 非 doc / inner doc 都打斷緊鄰鏈
            # comment 節點不再下鑽：Rust `///` 解成 line_comment 內含 doc_comment（巢狀），
            # 下鑽會把同一個 `///` 重複收兩筆（外 line_comment + 內 doc_comment）。
            return

        if node_type in always:
            name = symbols._name_of(source, node)
            def_line = node.start_point[0] + 1
            # 非 Python：doc comment 緊鄰下方符號 → 回填 owner_line（近似）
            if not is_python:
                _add_pending_owner(def_line)
            # Python：body 第一個 string = docstring（精確 owner_line）
            if is_python:
                ds = _docstring_string_node(node, source)
                if ds is not None:
                    dtext = _node_text(source, ds)
                    out.append({
                        "kind": "doc", "text": dtext,
                        "line": ds.start_point[0] + 1,
                        "end_line": ds.end_point[0] + 1,
                        "scope": ".".join(scope_parts),
                        "tag": _first_marker(dtext, marker_re),
                        "is_doc": True,
                        "owner_line": def_line,
                    })
                pending_doc.clear()
            child_scope = scope_parts + [name]
        else:
            # 撞到非 comment / 非定義的實質節點 → 打斷 doc 緊鄰鏈（非 Python）
            if not is_python and node_type not in ("ERROR",) and node.is_named \
                    and node_type not in comment_types:
                # 只在「有 byte 內容的實質節點」打斷，避免容器節點誤清；保守：定義/comment 以外清
                pass  # 不在此處激進清除，交給 _add_pending_owner 的行距判斷把關

        for child in node.children:
            walk(child, child_scope)

    # module docstring（Python module root 第一個 named child 若 string）
    if is_python and root.named_child_count > 0:
        first = root.named_child(0)
        ms = None
        if first is not None and first.type == "string":
            ms = first
        elif first is not None and first.type == "expression_statement" \
                and first.named_child_count > 0 and first.named_child(0).type == "string":
            ms = first.named_child(0)
        if ms is not None:
            mtext = _node_text(source, ms)
            out.append({
                "kind": "doc", "text": mtext,
                "line": ms.start_point[0] + 1, "end_line": ms.end_point[0] + 1,
                "scope": "", "tag": _first_marker(mtext, marker_re),
                "is_doc": True, "owner_line": None,   # module 級無符號 owner
            })

    walk(root, [])
    # 依行號排序（module docstring 可能後加，保持輸出按出現順序）
    out.sort(key=lambda c: (c["line"], c["end_line"]))
    return out


def extract_comments(file_path: str) -> list[dict]:
    """讀一個原始碼檔，按副檔名抽註解。副檔名不支援 → ValueError；讀不到 → FileNotFoundError。"""
    lang_key = symbols.language_for_file(file_path)
    if lang_key is None:
        raise ValueError(
            f"抽註解失敗：不支援的副檔名 {file_path}（支援：{sorted(symbols.SUPPORTED_EXTENSIONS)}）")
    try:
        with open(file_path, "rb") as f:
            source = f.read()
    except OSError as exc:
        raise FileNotFoundError(f"抽註解失敗：讀不到檔 {file_path}（{exc}）") from exc
    return extract_comments_from_source(source, lang_key, file_path=file_path)


def scan_tags_in_text(text: str, base_line: int, marker_re=None) -> list[dict]:
    """對一段註解 text **逐行掃 marker** 回 [{tag, line(真實源碼行), text(該行)}]。

    FIX-3b（設計 §3.B.1，「知道哪行」核心賣點）：多行 block/doc 的 marker 必須回真實源碼行
    （base_line + 相對行 offset），不是 block 起始行。base_line=該註解節點的起始行（1-based）。
    """
    if marker_re is None:
        marker_re = _marker_re()
    if marker_re is None:
        return []
    found: list[dict] = []
    # 紅隊 L3-LOW：用 split("\n") 而非 splitlines()——後者對 U+2028/\v/\f/\x85 等 Unicode 行分隔符
    # 多斷行，跟 tree-sitter 只認 \n 的行號模型不一致 → marker 回的源碼行對不上（跳轉跳錯）。
    for offset, line_text in enumerate(text.split("\n")):
        m = marker_re.search(line_text)
        if m:
            found.append({"tag": m.group(1), "line": base_line + offset,
                          "text": line_text.strip()})
    return found
