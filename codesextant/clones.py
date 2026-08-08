"""Detect duplicate and near-duplicate code with structural fingerprints.

The implementation uses AST shape hashes, called-name sets, and winnowed k-gram
fingerprints. It relies on deterministic hashing and counting rather than embeddings,
semantic models, GPU processing, or optional dependencies.

The detector combines three fingerprints:
  - shape_hash (primary, catches Type-1/2): a pre-order traversal of the body's
    node types with identifier→ID, literal→LIT, anonymous punctuation and comments
    dropped, and keyword node kinds and control-flow structure **kept** → sha1.
    Once values are erased, renaming or swapping constants keeps the same shape and
    therefore the same hash.
  - raw_token_hash (verbatim Type-1 decision): the **un-normalized** terminal token
    values concatenated → sha1. EXACT_DUP requires a matching raw_token_hash so
    unrelated functions with the same structure do not collide.
  - call_hash (call pattern, an orthogonal reinforcement): the sorted multiset of
    called names at call nodes inside the body → sha1.
  - winnowing fingerprint set (catches Type-3): the normalized token stream is cut
    into k-grams → crc32 → a sliding window of size w keeps the minimum (the chosen
    representative). Guarantee threshold t=w+k−1. The k-gram hash is the standard
    library's **zlib.crc32** (fast, stable across processes, no new dependency).
    Python's hash() is unsuitable because PYTHONHASHSEED makes it unstable. Avoid
    sha1 (too slow for short k-grams), do not use xxhash/mmh3 (new dependencies).

Structural-significance gate: after leaves are dropped, a body **must contain at
least one control-flow node** (if/for/while/try/match…) to be eligible for
RENAMED_DUP or above. Plain assignment runs, plain attribute returns and plain
delegating calls are suppressed to BOILERPLATE_SUPPRESSED.

Results are navigation clues, not deletion or merge recommendations. The output reports
structurally similar units, locations, and confidence. Review the code and run its tests
before changing it.

Configuration switches accept case-insensitive values.
"""
from __future__ import annotations

import hashlib
import os
import zlib

import tree_sitter

from . import complexity, symbols

# Leaf nodes treated as identifiers (shared across languages; erased to the
# placeholder "ID", so renaming does not change the shape).
_IDENT_TYPES = {
    "identifier", "property_identifier", "field_identifier", "type_identifier",
    "shorthand_property_identifier", "shorthand_property_identifier_pattern",
    "private_property_identifier", "statement_identifier", "label_name",
}
# Leaf nodes treated as literals (erased to "LIT", so swapping a constant does not
# change the shape). Go integers are int_literal rather than
# integer/integer_literal), and imaginary_literal must be listed too, otherwise Go
# numbers are not erased to LIT and int↔float pairs miss their shared shape.
_LITERAL_TYPES = {
    "integer", "float", "string", "true", "false", "none", "null",
    "integer_literal", "float_literal", "string_literal", "boolean_literal",
    "char_literal", "raw_string_literal", "number", "regex", "nil",
    "interpreted_string_literal", "rune_literal", "int_literal", "imaginary_literal",
    "string_content", "string_fragment", "true_lit", "false_lit",
}
# Control-flow nodes (the structural-significance gate: a body containing any of
# these is "complex enough" to be eligible for RENAMED_DUP or above).
# A plain Go switch parses as expression_switch_statement rather than
# switch_statement. Omitting it gives Go switch-dispatch functions
# has_control_flow=False, so they are systematically misclassified as boilerplate
# and suppressed.
_CONTROL_FLOW = {
    "if_statement", "for_statement", "while_statement", "try_statement",
    "match_statement", "with_statement", "if_expression", "for_expression",
    "while_expression", "match_expression", "switch_statement", "loop_expression",
    "conditional_expression", "ternary_expression", "for_in_statement",
    "do_statement", "except_clause", "case_clause", "guard_statement",
    "type_switch_statement", "select_statement", "expression_switch_statement",
}
# Call node types per language (the 2026-06-19 set plus the 2026-06-22 batch of
# mainstream languages, proved out by tools/_probe_extra.py). Values are sets
# (PHP and Ruby have several call node types); _call_names matches with `in`.
# CALL_PATTERN_SIM is an opt-in secondary feature. The field holding the
# called name has not been probed per language, so _call_names falls back through
# the common field names and its precision is best-effort.
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
    # Guard against NaN ('nan' makes `sim < nan` always False, which
    # silently disables the threshold). Out-of-range clamping is the caller's job.
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


# ── the traversals underlying the three fingerprints and winnowing ──
def _shape_tokens(src: bytes, body) -> list[str]:
    """Pre-order node-type sequence: identifier→ID, literal→LIT, anonymous punctuation
    and comments dropped, structural and keyword named nodes kept."""
    toks: list[str] = []

    def rec(n):
        t = n.type
        if not n.is_named:          # anonymous token (punctuation, literal keyword symbols) → drop; what we keep are named structural nodes
            return
        if t in _COMMENT_LIKE:
            return
        if t in _IDENT_TYPES:
            toks.append("ID")       # a leaf: erase the value, do not descend
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
    """Concatenated raw terminal token values (identifier and literal values are kept,
    for the verbatim Type-1 decision)."""
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
    """Take the last identifier segment of a called name (a.b.c → c; a bare identifier → itself)."""
    last = None

    def rec(n):
        nonlocal last
        if n.type in _IDENT_TYPES:
            last = _node_text(src, n)
        for c in n.children:
            rec(c)

    rec(node)
    return last


# Subscript callees (handlers[key]()): _last_identifier would wrongly take the
# subscript index name as the called name, so skip them entirely
# and contribute nothing to call_hash.
_SUBSCRIPT_TYPES = {"subscript", "subscript_expression", "index_expression"}


def _call_names(src: bytes, body, lang_key: str) -> list[str]:
    """Sorted multiset of called names at every call node in the body (the raw material
    for the call-pattern fingerprint)."""
    call_types = _CALL_TYPES.get(lang_key, {"call_expression"})
    names: list[str] = []

    def rec(n):
        if n.type in call_types:
            # The field holding the called name differs by language (function for the
            # C family, name for Java and Lua, method for Ruby) → try the common ones.
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
    """(node_count = number of named descendants, nstmts = number of direct named
    children of the body, has_control_flow)."""
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
    """k-gram → crc32 (standard library, fast, stable across processes, no dependencies)."""
    return zlib.crc32("\x1f".join(kgram).encode("utf-8")) & 0xFFFFFFFF


def winnow(shape_tokens: list[str], k: int, w: int) -> list[int]:
    """Winnowing fingerprints (MOSS): cut normalized tokens into k-grams → crc32 →
    keep the rightmost minimum hash in each window of size w.

    Guarantee threshold t=w+k−1: any identical substring of length ≥t is guaranteed to
    be detected. Consecutive windows sharing the same minimum are recorded once, which
    lowers the fingerprint density.
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
        # Rightmost minimum position (MOSS: with several minima in a window take the
        # rightmost, which reduces duplicate records).
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
    """Compute the fingerprint of one function/method definition node. If the body
    cannot be obtained, return None (no fingerprint).

    Winnowing runs only when node_count ≥ min_node_count because fingerprints from
    very small units are not useful.
    Returns {shape_hash, raw_token_hash, call_hash, node_count, nstmts,
    has_control_flow, cognitive, winnow:[...]}. cognitive is the cognitive
    complexity (an int for high-confidence languages, None for the rest).
    """
    body = complexity.function_body(def_node, lang_key)  # Kotlin has no function_body field → per-language fallback
    if body is None:
        return None
    node_count, nstmts, has_cf = _metadata(body)
    cog = complexity.cognitive_complexity(body, lang_key, func_name, src)
    shape = _shape_tokens(src, body)
    raw = _raw_tokens(src, body)
    calls = _call_names(src, body, lang_key)
    k = _env_int("CODESEXTANT_DEDUP_WINNOW_K", 5)
    w = _env_int("CODESEXTANT_DEDUP_WINNOW_W", 4)
    # Deduplicate winnow fingerprints before persisting. Within one
    # function, winnowing emits the same fp_value at several positions; without
    # deduplication the DF-cap's COUNT(*) reads "repeated inside a single function" as
    # "flooding across functions" and prunes away the real Type-3 near-clones).
    # Also gate on has_cf. Large boilerplate __init__/builder
    # bodies with no control flow never enter the stage-2 inverted index, so stage-2
    # STRUCTURAL_NEAR inherits the structural-significance hard gate automatically,
    # stops misjudging boilerplate, and saves work at the same time).
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
    """Extract the structural fingerprint of every function/method in a piece of source
    (kept out of extract_symbols to preserve single responsibility).

    Returns list[dict], each entry being {name, kind, line, end_line, scope, shape_hash,
    raw_token_hash, call_hash, node_count, nstmts, has_control_flow, winnow:[fp_value...]}.
    Fails loudly: source that is not bytes → TypeError; an unsupported lang_key →
    ValueError.
    """
    if not isinstance(source, (bytes, bytearray)):
        raise TypeError(
            f"extract_fingerprints_from_source needs bytes, got {type(source).__name__} ({file_path})")
    spec = symbols.LANGUAGE_SPECS.get(lang_key)
    if spec is None:
        raise ValueError(
            f"extract_fingerprints_from_source does not support language '{lang_key}' ({file_path})")
    if min_node_count is None:
        min_node_count = _env_int("CODESEXTANT_DEDUP_MIN_NODE_COUNT", 15)

    always: dict = spec["always"]
    scope_only: dict = spec.get("scope_only", {})
    name_rules: dict = spec.get("name_rules", {})   # naming strategy for nodes with no name field (C/C++ c_declarator, Kotlin child:)
    if tree is None:    # The index can provide its tree to avoid parsing twice.
        parser = tree_sitter.Parser(symbols._ts_language(spec["language"]))
        tree = parser.parse(bytes(source))

    out: list[dict] = []

    def walk(node, scope_parts: list[str]) -> None:
        child_scope = scope_parts
        if node.type in always:
            # Apply name_rules (matching symbols.extract_symbols); for languages that
            # do have a name field the rule is None, so _name_of behaves as before.
            # Calling _name_of without the rule gives every C/C++/Kotlin
            # fingerprint name <anon>, corrupting the persisted dedup/cognitive names.
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
    """Read a file and extract its fingerprints. Unsupported extension → ValueError;
    unreadable → FileNotFoundError."""
    lang_key = symbols.language_for_file(file_path)
    if lang_key is None:
        raise ValueError(f"fingerprint extraction failed: unsupported file extension {file_path}")
    try:
        with open(file_path, "rb") as f:
            source = f.read()
    except OSError as exc:
        raise FileNotFoundError(f"fingerprint extraction failed: cannot read file {file_path} ({exc})") from exc
    return extract_fingerprints_from_source(source, lang_key, file_path=file_path,
                                            min_node_count=min_node_count)
