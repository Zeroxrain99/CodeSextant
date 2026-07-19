"""符號抽取模組 — tree-sitter 多語言全量快速符號表（C1 Python + C5 跨語言）。

設計來源（PoC 已坐實，務必照做、別重踩）：
  - tree-sitter parse API 坑：固定用 `get_language(<grammar>)` +
    `tree_sitter.Parser(lang).parse(bytes)`。
    ⛔ 別用 tree_sitter_language_pack 的 `get_parser()`——它回傳的 native
    Parser 與本機 tree_sitter 0.25 wrapper 不相容（對 bytes 報錯）。
  - 全量符號表走 tree-sitter（實測 ~5 ms/檔），不走 jedi（jedi 是 references 的事）。
  - C5 多語言：tree-sitter-language-pack 內建多語言 grammar，各語言的「定義」節點型別
    不同（2026-06-18 `_probe.py` 實測每語言節點型別、name field 全部坐實），用一張
    per-language table 描述，加語言只加一筆、加符號種類只改表（對齊 code skill OCP）。

職責（單一）：吃一個檔路徑或一段原始碼，吐出該檔的符號定義清單
（函數 / 類別 / 方法 / 型別 / 模組層級變數 + 行號 + 所屬範圍）。
不碰 SQLite、不碰 jedi、不碰排序——那些是別的模組的事。

回傳一律是「可直接轉 JSON 的 dict/list」，方便 C2 daemon 包成 HTTP。
"""
from __future__ import annotations

import os

import tree_sitter
from tree_sitter_language_pack import get_language

# ── per-language spec（table-driven） ──
#   language : tree-sitter-language-pack 的 grammar 名
#   exts     : 副檔名（小寫、含點）
#   always   : {tree-sitter 節點型別: 符號 kind}
#              「結構定義」——不論巢狀深度一律收（function/class/method/型別…），
#              並把自己的名字 push 進 scope（讓 method/巢狀標出歸屬）。
#   vars     : {節點型別: kind}
#              「變數定義」——只在模組頂層（scope 為空）收，避免區域變數噪音。
#   py_assignment : Python 特例旗標（模組層級 assignment.left → variable，無 name field）。
# 所有節點型別均用 child_by_field_name("name") 抓名字（_probe.py 2026-06-18 實測坐實）。
LANGUAGE_SPECS: dict[str, dict] = {
    "python": {
        "language": "python",
        "exts": [".py", ".pyi"],
        "always": {"function_definition": "function", "class_definition": "class"},
        "vars": {},                       # Python 變數走 assignment 特例
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
            "abstract_class_declaration": "class",       # abstract class Foo（_probe2 坐實）
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
        # impl 區塊本身不算符號，但要把目標型別 push 進 scope，讓內部 fn 標出歸屬
        # （否則 impl MyStruct 內的 method scope 全空、與全域同名函數混淆，_probe2 坐實）。
        "scope_only": {"impl_item": "type"},
    },
    # ── 2026-06-22 主流語言一批（tools/_probe_langs.py 全節點型別/name field 實測坐實，無腦推）──
    "csharp": {
        "language": "csharp",
        "exts": [".cs"],
        "always": {
            "class_declaration": "class",
            "struct_declaration": "struct",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "record_declaration": "class",          # record 語意近 class，referenceable 收 class
            "delegate_declaration": "type",
            "method_declaration": "method",
            "constructor_declaration": "constructor",
            "property_declaration": "property",
        },
        "vars": {},                                  # 頂層無變數（field 在 class 內、無 name field）
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
        "exts": [".c", ".h"],                        # .h 預設歸 C（C++ header 走 .hpp/.hh/.hxx）
        "always": {
            "function_definition": "function",       # 名字埋在 declarator 鏈 → c_declarator
            "struct_specifier": "struct",
            "enum_specifier": "enum",
            "union_specifier": "struct",             # union 併入 struct kind
        },
        "vars": {},
        "name_rules": {"function_definition": "c_declarator"},
    },
    "cpp": {
        "language": "cpp",
        "exts": [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"],
        "always": {
            "function_definition": "function",       # Widget::doIt → c_declarator 取末段 doIt
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
        # ⚠ Kotlin grammar 的定義節點「無 name field」（名字在 type_identifier/simple_identifier
        #    子節點），故全走 name_rules 的 child:<type> 策略（_probe 坐實）。
        "always": {
            "class_declaration": "class",            # enum class / data class 都是 class_declaration
            "object_declaration": "class",
            "function_declaration": "function",      # 類內函數 kind=function、scope 標出類名歸屬
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
        # ⚠ Swift grammar 把 enum/struct/class/actor 全 parse 成 class_declaration（無法細分）→
        #    一律標 class，誠實記錄此限制（_probe 坐實 enum Color/struct Point 皆 class_declaration）。
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
        "always": {"function_definition": "function"},   # explicit_fn() 與 function explicit_fn 皆此型別
        "vars": {},                                       # 頂層變數 name field 非 identifier、walk 不收（誠實留空）
    },
    "lua": {
        "language": "lua",
        "exts": [".lua"],
        "always": {"function_declaration": "function"},   # global/local/M.method 皆 function_declaration（name 含點 OK）
        "vars": {},
    },
}

# 副檔名 → lang key（反查表），給 engine 掃描 / 找引用判語言用。
_EXT_TO_LANG: dict[str, str] = {
    ext: name for name, spec in LANGUAGE_SPECS.items() for ext in spec["exts"]
}
SUPPORTED_EXTENSIONS = frozenset(_EXT_TO_LANG)


# ── tree-sitter Language 物件 lazy cache（用到才載、各語言只載一次共享） ──
_lang_obj_cache: dict[str, tree_sitter.Language] = {}


def _ts_language(grammar: str) -> tree_sitter.Language:
    obj = _lang_obj_cache.get(grammar)
    if obj is None:
        obj = get_language(grammar)
        _lang_obj_cache[grammar] = obj
    return obj


def language_for_file(file_path: str) -> str | None:
    """副檔名 → 語言 key（不支援回 None）。"""
    return _EXT_TO_LANG.get(os.path.splitext(file_path)[1].lower())


def parse_source(source: bytes, lang_key: str):
    """parse 一段原始碼成 tree-sitter tree。

    紅隊 L4-MEDIUM：給 index_project 一檔 parse 一次、symbols/comments/fingerprints 三者共用同一
    tree（傳 tree= 進各自的 *_from_source），省掉每檔重複 parse 三次的冗餘。lang_key 不支援 → ValueError。
    """
    spec = LANGUAGE_SPECS.get(lang_key)
    if spec is None:
        raise ValueError(f"parse_source 不支援的語言 '{lang_key}'")
    parser = tree_sitter.Parser(_ts_language(spec["language"]))
    return parser.parse(bytes(source))


def _node_text(src: bytes, node) -> str:
    """取節點對應的原始位元組片段，解成 str。"""
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _name_of(src: bytes, node) -> str:
    """從定義節點抓名字（name 子節點）。抓不到回 '<anon>'（不靜默 None）。"""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return "<anon>"
    return _node_text(src, name_node)


# C/C++ declarator 鏈：function_definition 名字不在 name field，埋在 (pointer/reference/...)
# → function_declarator → identifier / qualified_identifier（取末段）。2026-06-22 _probe 坐實。
_C_DECLARATOR_WRAPPERS = {
    "function_declarator", "pointer_declarator", "reference_declarator",
    "parenthesized_declarator", "array_declarator",
}


def _c_declarator_name(src: bytes, node) -> str:
    """C/C++ function_definition：往下穿過 declarator wrapper 找 function_declarator，
    取被宣告名（qualified_identifier 如 Widget::doIt 取末段 identifier）。抓不到回 '<anon>'。"""
    # 找第一層 declarator wrapper
    decl = None
    for c in node.children:
        if c.type in _C_DECLARATOR_WRAPPERS:
            decl = c
            break
    # 穿過 pointer/reference 等 wrapper 直到 function_declarator
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
    # function_declarator 的第一個非 parameter_list 子 = 被宣告名
    for c in decl.children:
        if c.type == "parameter_list":
            continue
        if c.type == "qualified_identifier":
            # namespace::name → 取最後一段 identifier/field_identifier
            for q in reversed(c.children):
                if q.type in ("identifier", "field_identifier", "destructor_name"):
                    return _node_text(src, q)
        if c.type in ("identifier", "field_identifier", "destructor_name", "operator_name"):
            return _node_text(src, c)
    return "<anon>"


def _extract_name(src: bytes, node, rule: str | None) -> str:
    """依 name_rules 策略取定義節點的名字。rule=None → 預設 child_by_field_name('name')。

    "child:<type>" → 取第一個該型別的直接子節點文字（Kotlin 名字在 type_identifier/simple_identifier）。
    "c_declarator" → C/C++ declarator 鏈（見 _c_declarator_name）。
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
    """從一段原始碼（bytes）抽出符號定義清單。

    參數
    ----
    source : bytes
        檔案原始位元組（一律傳 bytes，不傳 str——對齊 PoC 的 parse(bytes) 路徑）。
    lang_key : str
        語言 key（LANGUAGE_SPECS 的鍵；預設 "python" 保持 C1 相容）。
    file_path : str
        僅用於錯誤訊息與回傳標記，不會讀檔。

    回傳
    ----
    list[dict]，每符號一筆，欄位：
      - kind  : "function" / "class" / "method" / "interface" / "type" / "enum"
                / "struct" / "trait" / "variable"（依語言）
      - name  : 符號名稱
      - line / end_line : 定義起訖行號（1-based）
      - scope : 所屬範圍（如 "MyClass" 表示 method 在 MyClass 內；"" 表示模組頂層）
    依出現順序排列。

    fail-loud：source 不是 bytes 直接 TypeError；lang_key 不支援直接 ValueError。
    """
    if not isinstance(source, (bytes, bytearray)):
        raise TypeError(
            f"extract_symbols_from_source 需要 bytes，收到 {type(source).__name__}"
            f"（file_path={file_path}）。請先讀成 bytes 再傳入。"
        )
    spec = LANGUAGE_SPECS.get(lang_key)
    if spec is None:
        raise ValueError(
            f"extract_symbols_from_source 不支援的語言 '{lang_key}'"
            f"（file_path={file_path}）。可用：{sorted(LANGUAGE_SPECS)}"
        )

    if tree is None:    # 紅隊 L4-MEDIUM：index 可傳入已 parse 的 tree、三模組共用省重複 parse
        parser = tree_sitter.Parser(_ts_language(spec["language"]))
        tree = parser.parse(bytes(source))
    root = tree.root_node

    always: dict = spec["always"]
    varkinds: dict = spec["vars"]
    scope_only: dict = spec.get("scope_only", {})   # 只 push scope、不當符號（如 Rust impl）
    name_rules: dict = spec.get("name_rules", {})   # 無 name field 節點的取名策略（C/C++/Kotlin）
    py_assignment: bool = spec.get("py_assignment", False)

    symbols: list[dict] = []

    def walk(node, scope_parts: list[str]) -> None:
        node_type = node.type
        child_scope = scope_parts

        # tree-sitter 關鍵字/標點是 unnamed token，其 type 可能與定義節點型別撞名
        # （Ruby `module`/`class` keyword token 的 type == 定義節點 type "module"/"class"），
        # 只有 is_named 的節點才是真正的符號定義 → 擋掉 keyword token 誤收成 <anon>。
        if node.is_named and node_type in always:
            name = _extract_name(source, node, name_rules.get(node_type))
            symbols.append({
                "kind": always[node_type],
                "name": name,
                "line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "scope": ".".join(scope_parts),
            })
            # 進到定義內部時把自己加進 scope，讓 method/巢狀函數標出歸屬
            child_scope = scope_parts + [name]

        elif node_type in scope_only:
            # 容器節點（如 Rust impl_item）：用指定 field 當 scope 名 push 下去、自己不算符號，
            # 讓內部方法標出所屬型別（否則 impl 內 fn 的 scope 全空、與全域同名函數混淆）。
            field_node = node.child_by_field_name(scope_only[node_type])
            if field_node is not None:
                child_scope = scope_parts + [_node_text(source, field_node)]

        elif node_type in varkinds and not scope_parts:
            # 變數只收模組頂層，且名字必須是單一識別字——解構 `const {a,b}=…` 的 name field
            # 是 object_pattern/array_pattern，跳過免吐 "{a, b}" 這種垃圾符號名。
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
            # Python 特例：模組層級 identifier 賦值當變數（assignment 無 name field）
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
    """讀一個原始碼檔，按副檔名選語言、抽出符號定義清單。

    這是對外主要入口（讀檔 + 抽符號）。副檔名不支援 → ValueError（fail-loud）；
    檔讀不到 → FileNotFoundError。回傳同 extract_symbols_from_source。
    """
    lang_key = language_for_file(file_path)
    if lang_key is None:
        raise ValueError(
            f"抽符號失敗：不支援的副檔名 {file_path}"
            f"（支援：{sorted(SUPPORTED_EXTENSIONS)}）"
        )
    try:
        with open(file_path, "rb") as f:
            source = f.read()
    except OSError as exc:
        raise FileNotFoundError(f"抽符號失敗：讀不到檔 {file_path}（{exc}）") from exc
    return extract_symbols_from_source(source, lang_key, file_path=file_path)
