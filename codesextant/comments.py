"""Comment management: tree-sitter extracts comment nodes + line numbers + owning symbol (Feature B, second half).

Positioning (design doc §3.B): "see everything at once vs. see only what matters + know which
line": docstring coverage / where each TODO·FIXME sits / comment density, feeding both a repo
summary and precise navigation. **Lightweight, avoids the four pitfalls, gives a clue, not a verdict.**

Single responsibility: takes a file path or a chunk of source, emits that file's comment list.
Not folded into extract_symbols (keeps symbols.py's single responsibility), but shares symbols'
`_ts_language()` grammar cache and the LANGUAGE_SPECS definition-node table (used to tag scope
and to find the body field for a Python docstring).

Honest boundaries (design doc §6):
  - docstring detection is limited to "the first named child of a block/module is a string node"
    (Python): a string wrapped in a conditional, assigned to a variable, or not in first position
    will be missed.
  - Doc comments in other languages (Rust ///, Go/TS /** */) are approximately aligned to
    owner_line by "immediately precedes the symbol below it"; nesting or several blank lines in
    between can throw this off; coverage for non-Python languages is best-effort.
  - Coverage/density are structural statistical clues, not a judgment on whether a comment is
    correct, stale, or in sync with the code (that's semantics, which this can't see).

Switches (L0 hard rule #6, all tolerant of .lower() case):
  - CODESEXTANT_COMMENTS_DISABLED        opt out of the whole feature
  - CODESEXTANT_COMMENT_MARKERS          marker set (default TODO,FIXME,HACK,XXX,BUG,NOTE)
"""
from __future__ import annotations

import os
import re

import tree_sitter

from . import symbols

# Comment node type per language (proved out by the design doc's R2 tree-sitter probe on 2026-06-19). Rust has three; the rest use a single "comment" type.
_COMMENT_TYPES: dict[str, set[str]] = {
    "python": {"comment"},
    "javascript": {"comment"},
    "typescript": {"comment"},
    "tsx": {"comment"},
    "go": {"comment"},
    "rust": {"line_comment", "block_comment", "doc_comment"},
    # 2026-06-22, a batch of mainstream languages added (comment node types proved out by tools/_probe_extra.py):
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

# Text prefixes used to decide "is this a doc comment" (Rust /// parses as line_comment or
# doc_comment depending on the grammar version; TS jsdoc /** still parses as a plain comment --
# hence the double check on node type + text prefix, per design doc fix §3.B.1).
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
    """The docstring string node for a function/class definition node (the body's first named
    child, if it's a string; handles the case where it's wrapped one level in expression_statement).
    Not a string -> None."""
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
    """Extract the comment list from a chunk of source code (bytes).

    Returns list[dict], each entry: {kind(line/block/doc), text, line, end_line, scope,
    tag(first marker or None), is_doc(bool), owner_line(the doc's owning symbol's definition
    line, or None)}. In order of appearance.

    fail-loud: source not bytes -> TypeError; unsupported lang_key -> ValueError.
    """
    if not isinstance(source, (bytes, bytearray)):
        raise TypeError(
            f"extract_comments_from_source requires bytes, got {type(source).__name__} ({file_path})")
    spec = symbols.LANGUAGE_SPECS.get(lang_key)
    if spec is None:
        raise ValueError(
            f"extract_comments_from_source: unsupported language '{lang_key}' ({file_path}). "
            f"Available: {sorted(symbols.LANGUAGE_SPECS)}")

    comment_types = _COMMENT_TYPES.get(lang_key, {"comment"})
    always: dict = spec["always"]
    is_python = lang_key == "python"
    marker_re = _marker_re()

    if tree is None:    # Red team L4-MEDIUM: index shares the tree to avoid re-parsing
        parser = tree_sitter.Parser(symbols._ts_language(spec["language"]))
        tree = parser.parse(bytes(source))
    root = tree.root_node

    out: list[dict] = []
    # pending doc comment (for non-Python languages, approximates owner_line backfill via "doc comment immediately precedes the symbol below it")
    pending_doc: list[dict] = []  # a list used as a mutable single-element box (written from a closure)

    def _add_pending_owner(def_line: int) -> None:
        if pending_doc and pending_doc[0] is not None:
            d = pending_doc[0]
            # only backfill when immediately adjacent (definition line - doc end_line ∈ [0,2],
            # allowing for tree-sitter comment nodes whose trailing newline causes an off-by-one
            # [end_point lands at the start of the next line] plus one blank line)
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
            # Red team L3-MEDIUM: Rust `//!`/`/*!` is an "inner doc comment"; it documents the
            # enclosing item (module/crate), and must not be backfilled onto the sibling symbol
            # below it (otherwise a `//!` at the top of a file would get misattributed as the
            # docstring for the fn below it, systematically inflating coverage). Only an outer
            # doc (///, /**) goes into pending_doc to align with the symbol below it.
            is_inner = text.lstrip().startswith(("//!", "/*!"))
            if doc and not is_inner:
                pending_doc[:] = [rec]   # outer doc: record as pending alignment (backfilled if the next definition node is adjacent)
            else:
                pending_doc.clear()      # both non-doc and inner-doc comments break the adjacency chain
            # Don't descend into comment nodes: Rust `///` parses as a line_comment containing a
            # nested doc_comment; descending would collect the same `///` twice (the outer
            # line_comment plus the inner doc_comment).
            return

        if node_type in always:
            name = symbols._name_of(source, node)
            def_line = node.start_point[0] + 1
            # non-Python: doc comment immediately precedes the symbol below it -> backfill owner_line (approximate)
            if not is_python:
                _add_pending_owner(def_line)
            # Python: the body's first string = the docstring (precise owner_line)
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
            # hit a substantive node that's neither a comment nor a definition -> breaks the doc adjacency chain (non-Python)
            if not is_python and node_type not in ("ERROR",) and node.is_named \
                    and node_type not in comment_types:
                # only break on "a substantive node with actual byte content", to avoid clearing
                # on a mere container node by mistake; conservative: clear on anything besides a
                # definition/comment
                pass  # not cleared aggressively here; left to _add_pending_owner's line-distance check to gate it

        for child in node.children:
            walk(child, child_scope)

    # module docstring (Python module root's first named child, if it's a string)
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
                "is_doc": True, "owner_line": None,   # no symbol owner at module level
            })

    walk(root, [])
    # sort by line number (the module docstring may be appended later; keep output in appearance order)
    out.sort(key=lambda c: (c["line"], c["end_line"]))
    return out


def extract_comments(file_path: str) -> list[dict]:
    """Read a source file and extract its comments based on file extension. Unsupported extension -> ValueError; unreadable -> FileNotFoundError."""
    lang_key = symbols.language_for_file(file_path)
    if lang_key is None:
        raise ValueError(
            f"extract_comments failed: unsupported file extension {file_path} (supported: {sorted(symbols.SUPPORTED_EXTENSIONS)})")
    try:
        with open(file_path, "rb") as f:
            source = f.read()
    except OSError as exc:
        raise FileNotFoundError(f"extract_comments failed: cannot read file {file_path} ({exc})") from exc
    return extract_comments_from_source(source, lang_key, file_path=file_path)


def scan_tags_in_text(text: str, base_line: int, marker_re=None) -> list[dict]:
    """**Scan a chunk of comment text line by line for markers**, returning [{tag, line(the real source line), text(that line's text)}].

    Fix 3b (design doc §3.B.1, the core selling point of "know which line"): a marker inside a
    multi-line block/doc comment must map back to the real source line (base_line + relative line
    offset), not the block's starting line. base_line = that comment node's starting line (1-based).
    """
    if marker_re is None:
        marker_re = _marker_re()
    if marker_re is None:
        return []
    found: list[dict] = []
    # Red team L3-LOW: uses split("\n") rather than splitlines(), because the latter also splits on
    # Unicode line separators like U+2028/\v/\f/\x85, which disagrees with tree-sitter's line
    # numbering model (which only recognizes \n) -> markers would map to the wrong source line
    # (jumping to the wrong place).
    for offset, line_text in enumerate(text.split("\n")):
        m = marker_re.search(line_text)
        if m:
            found.append({"tag": m.group(1), "line": base_line + offset,
                          "text": line_text.strip()})
    return found
