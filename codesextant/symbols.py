"""Symbol extraction module - a fast, full-coverage, multi-language tree-sitter symbol table (C1 Python + C5 cross-language).

Design provenance (confirmed by a PoC - follow it, do not re-learn the hard way):
  - tree-sitter parse API pitfall: always use `get_language(<grammar>)` +
    `tree_sitter.Parser(lang).parse(bytes)`.
    Do not use tree_sitter_language_pack's `get_parser()` - the native Parser
    it returns is not compatible with the local tree_sitter 0.25 wrapper
    (raises an error on bytes input).
  - Full symbol-table extraction goes through tree-sitter (measured ~5 ms/file),
    not jedi (jedi handles references, a different concern).
  - C5 multi-language: tree-sitter-language-pack bundles multi-language grammars;
    each language's "definition" node types differ (confirmed on 2026-06-18 by
    `_probe.py`, which empirically verified every language's node types and name
    fields). Described via a per-language table - adding a language is one new
    entry, adding a symbol kind is one table edit (aligned with the code skill's
    Open/Closed Principle).

Responsibility (single): given a file path or a chunk of source, emit that
file's symbol-definition list (function / class / method / type / module-level
variable + line number + enclosing scope). Does not touch SQLite, does not
touch jedi, does not touch sorting - those are other modules' concerns.

The return value is always a "directly JSON-serializable" dict/list, so the C2
daemon can wrap it as HTTP.
"""
from __future__ import annotations

import os

import tree_sitter
from tree_sitter_language_pack import get_language

# -- per-language spec (table-driven) --
#   language : the grammar name in tree-sitter-language-pack
#   exts     : file extensions (lowercase, with dot)
#   always   : {tree-sitter node type: symbol kind}
#              "structural definitions" - always collected regardless of nesting
#              depth (function/class/method/type/...), and their own name is
#              pushed onto the scope (so methods/nested items show their owner).
#   vars     : {node type: kind}
#              "variable definitions" - only collected at module top level
#              (empty scope), to avoid local-variable noise.
#   py_assignment : Python-specific flag (module-level assignment.left ->
#              variable, since assignment has no name field).
# Every node type gets its name via child_by_field_name("name") (confirmed
# empirically by `_probe.py` on 2026-06-18).
LANGUAGE_SPECS: dict[str, dict] = {
    "python": {
        "language": "python",
        "exts": [".py", ".pyi"],
        "always": {"function_definition": "function", "class_definition": "class"},
        "vars": {},                       # Python variables go through the assignment special case
        "py_assignment": True,
    },
    "javascript": {
        "language": "javascript",
        "exts": [".js", ".jsx", ".mjs", ".cjs"],
        "always": {
            "function_declaration": "function",
            "class_declaration": "class",
            "method_definition": "method",
        },
        "vars": {"variable_declarator": "variable"},
    },
    "typescript": {
        "language": "typescript",
        "exts": [".ts", ".mts", ".cts"],
        "always": {
            "function_declaration": "function",
            "class_declaration": "class",
            "abstract_class_declaration": "class",       # abstract class Foo (confirmed by _probe2)
            "method_definition": "method",
            "abstract_method_signature": "method",        # abstract m(): void
            "interface_declaration": "interface",
            "type_alias_declaration": "type",
            "enum_declaration": "enum",
        },
        "vars": {"variable_declarator": "variable"},
    },
    "tsx": {
        "language": "tsx",
        "exts": [".tsx"],
        "always": {
            "function_declaration": "function",
            "class_declaration": "class",
            "abstract_class_declaration": "class",
            "method_definition": "method",
            "abstract_method_signature": "method",
            "interface_declaration": "interface",
            "type_alias_declaration": "type",
            "enum_declaration": "enum",
        },
        "vars": {"variable_declarator": "variable"},
    },
    "go": {
        "language": "go",
        "exts": [".go"],
        "always": {
            "function_declaration": "function",
            "method_declaration": "method",
            "type_spec": "type",
        },
        "vars": {"var_spec": "variable", "const_spec": "variable"},
    },
    "rust": {
        "language": "rust",
        "exts": [".rs"],
        "always": {
            "function_item": "function",
            "function_signature_item": "function",
            "struct_item": "struct",
            "enum_item": "enum",
            "trait_item": "trait",
        },
        "vars": {"const_item": "variable", "static_item": "variable"},
        # An impl block itself does not count as a symbol, but its target type is
        # pushed onto the scope so inner fns show their owner (otherwise a
        # method's scope inside `impl MyStruct` would be empty and get confused
        # with a top-level function of the same name; confirmed by _probe2).
        "scope_only": {"impl_item": "type"},
    },
    # -- 2026-06-22 mainstream-language batch (every node type / name field
    # confirmed empirically by tools/_probe_langs.py, not guessed) --
    "csharp": {
        "language": "csharp",
        "exts": [".cs"],
        "always": {
            "class_declaration": "class",
            "struct_declaration": "struct",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "record_declaration": "class",          # record is close enough to class in meaning; classified as class for referenceability
            "delegate_declaration": "type",
            "method_declaration": "method",
            "constructor_declaration": "constructor",
            "property_declaration": "property",
        },
        "vars": {},                                  # no top-level variables (fields live inside a class and have no name field)
    },
    "java": {
        "language": "java",
        "exts": [".java"],
        "always": {
            "class_declaration": "class",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "record_declaration": "class",
            "annotation_type_declaration": "interface",   # @interface
            "method_declaration": "method",
            "constructor_declaration": "constructor",
        },
        "vars": {},
    },
    "c": {
        "language": "c",
        "exts": [".c", ".h"],                        # .h defaults to C (C++ headers use .hpp/.hh/.hxx)
        "always": {
            "function_definition": "function",       # name is buried in the declarator chain -> c_declarator
            "struct_specifier": "struct",
            "enum_specifier": "enum",
            "union_specifier": "struct",             # union is folded into the struct kind
        },
        "vars": {},
        "name_rules": {"function_definition": "c_declarator"},
    },
    "cpp": {
        "language": "cpp",
        "exts": [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"],
        "always": {
            "function_definition": "function",       # Widget::doIt -> c_declarator takes the last segment, doIt
            "class_specifier": "class",
            "struct_specifier": "struct",
            "enum_specifier": "enum",
        },
        "vars": {},
        "name_rules": {"function_definition": "c_declarator"},
    },
    "kotlin": {
        "language": "kotlin",
        "exts": [".kt", ".kts"],
        # Kotlin grammar's definition nodes have "no name field" (the name lives
        # in a type_identifier/simple_identifier child node), so everything uses
        # the name_rules "child:<type>" strategy (confirmed by _probe).
        "always": {
            "class_declaration": "class",            # enum class / data class are both class_declaration
            "object_declaration": "class",
            "function_declaration": "function",      # a function inside a class gets kind=function, scope marks its owning class
        },
        "vars": {},
        "name_rules": {
            "class_declaration": "child:type_identifier",
            "object_declaration": "child:type_identifier",
            "function_declaration": "child:simple_identifier",
        },
    },
    "swift": {
        "language": "swift",
        "exts": [".swift"],
        # Swift grammar parses enum/struct/class/actor all as class_declaration
        # (cannot be distinguished further) -> all classified as class; this
        # limitation is honestly documented here (confirmed by _probe:
        # `enum Color`/`struct Point` are both class_declaration).
        "always": {
            "class_declaration": "class",
            "protocol_declaration": "protocol",
            "protocol_function_declaration": "method",
            "function_declaration": "function",
            "init_declaration": "constructor",
            "property_declaration": "property",
        },
        "vars": {},
    },
    "php": {
        "language": "php",
        "exts": [".php"],
        "always": {
            "class_declaration": "class",
            "interface_declaration": "interface",
            "trait_declaration": "trait",
            "enum_declaration": "enum",
            "function_definition": "function",
            "method_declaration": "method",
        },
        "vars": {},
    },
    "ruby": {
        "language": "ruby",
        "exts": [".rb"],
        "always": {
            "module": "module",
            "class": "class",
            "method": "method",
            "singleton_method": "method",            # def self.x
        },
        "vars": {},
    },
    "bash": {
        "language": "bash",
        "exts": [".sh", ".bash"],
        "always": {"function_definition": "function"},   # both `explicit_fn()` and `function explicit_fn` are this type
        "vars": {},                                       # top-level variable name fields are not identifiers, so walk() does not collect them (honestly left empty)
    },
    "lua": {
        "language": "lua",
        "exts": [".lua"],
        "always": {"function_declaration": "function"},   # global/local/M.method are all function_declaration (a dotted name is fine)
        "vars": {},
    },
}

# extension -> lang key (reverse lookup table), used by the engine for scanning /
# determining a file's language when resolving references.
_EXT_TO_LANG: dict[str, str] = {
    ext: name for name, spec in LANGUAGE_SPECS.items() for ext in spec["exts"]
}
SUPPORTED_EXTENSIONS = frozenset(_EXT_TO_LANG)


# -- tree-sitter Language object lazy cache (loaded on first use, shared per language) --
_lang_obj_cache: dict[str, tree_sitter.Language] = {}


def _ts_language(grammar: str) -> tree_sitter.Language:
    obj = _lang_obj_cache.get(grammar)
    if obj is None:
        obj = get_language(grammar)
        _lang_obj_cache[grammar] = obj
    return obj


def language_for_file(file_path: str) -> str | None:
    """Extension -> language key (returns None if unsupported)."""
    return _EXT_TO_LANG.get(os.path.splitext(file_path)[1].lower())


def parse_source(source: bytes, lang_key: str):
    """Parse a chunk of source into a tree-sitter tree.

    Per adversarial review L4-MEDIUM: index_project parses each file once and
    shares that same tree across symbols/comments/fingerprints (by passing
    tree= into each module's *_from_source), avoiding the redundancy of
    re-parsing the same file three times. Unsupported lang_key -> ValueError.
    """
    spec = LANGUAGE_SPECS.get(lang_key)
    if spec is None:
        raise ValueError(f"parse_source: unsupported language '{lang_key}'")
    parser = tree_sitter.Parser(_ts_language(spec["language"]))
    return parser.parse(bytes(source))


def _node_text(src: bytes, node) -> str:
    """Get the raw byte span for a node and decode it to str."""
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _name_of(src: bytes, node) -> str:
    """Get the name from a definition node (its "name" child). Returns '<anon>' if not found (never silently returns None)."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return "<anon>"
    return _node_text(src, name_node)


# C/C++ declarator chain: a function_definition's name is not in the name field,
# it is buried in (pointer/reference/...) -> function_declarator ->
# identifier / qualified_identifier (take the last segment). Confirmed by
# _probe on 2026-06-22.
_C_DECLARATOR_WRAPPERS = {
    "function_declarator", "pointer_declarator", "reference_declarator",
    "parenthesized_declarator", "array_declarator",
}


def _c_declarator_name(src: bytes, node) -> str:
    """C/C++ function_definition: drill down through the declarator wrapper chain to
    find the function_declarator, then take the declared name (for a
    qualified_identifier like Widget::doIt, take the last segment). Returns
    '<anon>' if not found."""
    # find the first-level declarator wrapper
    decl = None
    for c in node.children:
        if c.type in _C_DECLARATOR_WRAPPERS:
            decl = c
            break
    # drill through pointer/reference and other wrappers until function_declarator
    seen = 0
    while decl is not None and decl.type != "function_declarator" and seen < 8:
        seen += 1
        nxt = None
        for c in decl.children:
            if c.type in _C_DECLARATOR_WRAPPERS:
                nxt = c
                break
        decl = nxt
    if decl is None:
        return "<anon>"
    # function_declarator's first non-parameter_list child = the declared name
    for c in decl.children:
        if c.type == "parameter_list":
            continue
        if c.type == "qualified_identifier":
            # namespace::name -> take the last segment (identifier/field_identifier)
            for q in reversed(c.children):
                if q.type in ("identifier", "field_identifier", "destructor_name"):
                    return _node_text(src, q)
        if c.type in ("identifier", "field_identifier", "destructor_name", "operator_name"):
            return _node_text(src, c)
    return "<anon>"


def _extract_name(src: bytes, node, rule: str | None) -> str:
    """Get a definition node's name per the name_rules strategy. rule=None -> default child_by_field_name('name').

    "child:<type>" -> takes the text of the first direct child of that type
    (Kotlin's name lives in type_identifier/simple_identifier).
    "c_declarator" -> the C/C++ declarator chain (see _c_declarator_name).
    """
    if rule is None:
        return _name_of(src, node)
    if rule.startswith("child:"):
        want = rule[len("child:"):]
        for c in node.children:
            if c.type == want:
                return _node_text(src, c)
        return "<anon>"
    if rule == "c_declarator":
        return _c_declarator_name(src, node)
    return _name_of(src, node)


def extract_symbols_from_source(source: bytes, lang_key: str = "python", *,
                                file_path: str = "<memory>", tree=None) -> list[dict]:
    """Extract the symbol-definition list from a chunk of source (bytes).

    Parameters
    ----------
    source : bytes
        The file's raw bytes (always pass bytes, not str - matches the PoC's
        parse(bytes) path).
    lang_key : str
        Language key (a key of LANGUAGE_SPECS; defaults to "python" to keep C1 compatibility).
    file_path : str
        Used only for error messages and the return marker; the file is not read.

    Returns
    -------
    list[dict], one entry per symbol, with fields:
      - kind  : "function" / "class" / "method" / "interface" / "type" / "enum"
                / "struct" / "trait" / "variable" (depends on language)
      - name  : the symbol's name
      - line / end_line : the definition's start/end line numbers (1-based)
      - scope : the enclosing scope (e.g. "MyClass" means the method is inside
                MyClass; "" means module top level)
    Listed in order of appearance.

    fail-loud: source not being bytes raises TypeError directly; an unsupported
    lang_key raises ValueError directly.
    """
    if not isinstance(source, (bytes, bytearray)):
        raise TypeError(
            f"extract_symbols_from_source requires bytes, got {type(source).__name__}"
            f" (file_path={file_path}). Read the file as bytes before passing it in."
        )
    spec = LANGUAGE_SPECS.get(lang_key)
    if spec is None:
        raise ValueError(
            f"extract_symbols_from_source: unsupported language '{lang_key}'"
            f" (file_path={file_path}). Available: {sorted(LANGUAGE_SPECS)}"
        )

    if tree is None:    # per adversarial review L4-MEDIUM: index_project may pass in an already-parsed tree, shared across the three modules to skip redundant re-parsing
        parser = tree_sitter.Parser(_ts_language(spec["language"]))
        tree = parser.parse(bytes(source))
    root = tree.root_node

    always: dict = spec["always"]
    varkinds: dict = spec["vars"]
    scope_only: dict = spec.get("scope_only", {})   # only pushes scope, does not count as a symbol (e.g. Rust impl)
    name_rules: dict = spec.get("name_rules", {})   # name-extraction strategy for nodes without a name field (C/C++/Kotlin)
    py_assignment: bool = spec.get("py_assignment", False)

    symbols: list[dict] = []

    def walk(node, scope_parts: list[str]) -> None:
        node_type = node.type
        child_scope = scope_parts

        # A tree-sitter keyword/punctuation is an unnamed token whose type can
        # collide with a definition node's type (Ruby's `module`/`class` keyword
        # tokens have type == the definition node type "module"/"class"); only an
        # is_named node is actually a symbol definition -> this filters out
        # keyword tokens that would otherwise be miscollected as <anon>.
        if node.is_named and node_type in always:
            name = _extract_name(source, node, name_rules.get(node_type))
            symbols.append({
                "kind": always[node_type],
                "name": name,
                "line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "scope": ".".join(scope_parts),
            })
            # when descending into the definition, add its own name to the scope
            # so methods/nested functions show their owner
            child_scope = scope_parts + [name]

        elif node_type in scope_only:
            # a container node (e.g. Rust's impl_item): pushes the designated
            # field as a scope name and does not itself count as a symbol, so
            # inner methods show their owning type (otherwise an fn's scope
            # inside impl would be empty and get confused with a global function
            # of the same name).
            field_node = node.child_by_field_name(scope_only[node_type])
            if field_node is not None:
                child_scope = scope_parts + [_node_text(source, field_node)]

        elif node_type in varkinds and not scope_parts:
            # variables are only collected at module top level, and the name
            # must be a single identifier - a destructuring `const {a,b}=...`'s
            # name field is object_pattern/array_pattern, which is skipped to
            # avoid emitting a junk symbol name like "{a, b}".
            name_node = node.child_by_field_name("name")
            if name_node is not None and name_node.type == "identifier":
                symbols.append({
                    "kind": varkinds[node_type],
                    "name": _node_text(source, name_node),
                    "line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "scope": "",
                })

        elif py_assignment and node_type == "assignment" and not scope_parts:
            # Python special case: a module-level identifier assignment counts
            # as a variable (assignment has no name field)
            left = node.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                symbols.append({
                    "kind": "variable",
                    "name": _node_text(source, left),
                    "line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "scope": "",
                })

        for child in node.children:
            walk(child, child_scope)

    walk(root, [])
    return symbols


def extract_symbols(file_path: str) -> list[dict]:
    """Read a source file, select the language by extension, and extract its symbol-definition list.

    This is the main external entry point (read file + extract symbols). An
    unsupported extension -> ValueError (fail-loud); a file that can't be read
    -> FileNotFoundError. The return value matches extract_symbols_from_source.
    """
    lang_key = language_for_file(file_path)
    if lang_key is None:
        raise ValueError(
            f"symbol extraction failed: unsupported extension {file_path}"
            f" (supported: {sorted(SUPPORTED_EXTENSIONS)})"
        )
    try:
        with open(file_path, "rb") as f:
            source = f.read()
    except OSError as exc:
        raise FileNotFoundError(f"symbol extraction failed: could not read file {file_path} ({exc})") from exc
    return extract_symbols_from_source(source, lang_key, file_path=file_path)
