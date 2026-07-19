"""D3 認知複雜度（Cognitive Complexity, G. Ann Campbell / SonarSource）— 紀律轉美的複雜度維度。

純函數、零隨機、零新依賴（只用 tree-sitter node）。對一個 function/method body 算
cognitive complexity：每次「打斷線性控制流」+1，巢狀時打斷流結構**額外** +當前巢狀深度。

三類規則（藍圖 §1 查證版）：
  B1 基本增量（+1）：if/else if/else、ternary、switch、for/while/do-while、catch/except、
                     帶標籤跳轉(continue/break LABEL)、連續邏輯運算子(每 run +1)、直接遞迴。
  B2 增巢狀層：if/else if/else、ternary、switch、loops、catch、巢狀 function/lambda。
  B3 巢狀增量(+nesting)：if、ternary、switch、loops、catch。⛔ else/else if 不拿 B3（同決策鏈延續）。

⚠ 高信心語言（P3：Python/JS/TS/TSX；P4 2026-06-23 擴：Go/Rust/Java/C#，共 8 種）計分；其餘
語言回 None（UNKNOWN 中性、不洗滿分）——控制流 grammar 跨語言差異大（Ruby case / Kotlin when /
Swift guard…）逐一驗透徹才升級。

P4 walker 泛化（probe 坐實 tools/_probe_if_fields.py + _probe_labeled.py，field 名跨 8 語言一致）：
  - if_style：wrapper（else-if 由 else_clause/elif_clause 包，Py/TS/JS/TSX/Rust）vs
              field（else-if＝if.alternative field 直接指 if、無 wrapper，Go/Java/C#，visit_if_field 專責）
  - if_types：集合化（多數 if_statement；Rust expression-based＝if_expression）
  - label_child_types / callee_field：per-language（label 判定、直接遞迴 callee field 名）

規則查證狀態：SonarSource 官方 PDF 逐字抓不到，用公開標準演算法知識 + 黃金案例
sumOfPrimes=7（白皮書招牌範例，P4 逐語言 Go/Java/Rust 版皆驗）pytest 當確定性 ground truth
+ distinct 子代理對抗 review。藍圖：docs/P3認知複雜度子系統_實作藍圖_2026-06-22.md §8。

誠實標限制：①只算直接遞迴（間接遞迴白皮書算、實作難、未做）；直接遞迴認「裸名==func_name 或
self/cls/this.func_name」，跨物件同名方法（obj.foo() 於名為 foo 的函數內）不算（對抗 review 收緊）；
⚠ P4：Go/C# 的 receiver.method()/this.Method()、C# member_access 遞迴保守不算（receiver 名不固定/節點型別異），
漏算只低估不誤殺 ②Python comprehension 的 for/if 當 loop/condition 計（白皮書未明訂）；但同一 comprehension
的多個 for（[x for a in b for x in a]）在 AST 為 sibling、第二個 for 只各 +1、不累積巢狀增量
③超深 AST（罕見）觸發 RecursionError → 回 None（UNKNOWN、不炸）④C# 無 labeled break/continue（用 goto）；
goto 罕見、label 機制異，誠實不計（漏算只低估）。

開關（L0 鐵律 #6，.lower() 容錯）：env CODESEXTANT_COGNITIVE_DISABLED=1 全關（回 None）。
"""
from __future__ import annotations

import copy
import os
import sys

_BLOCK_TYPES = {"block", "statement_block"}
# simple_identifier＝Kotlin/Swift 的識別字節點（call callee 直接遞迴判定用）
_IDENT_TYPES = {"identifier", "property_identifier", "field_identifier", "simple_identifier"}
# Swift grammar 運算子優先級畸形：`n * fact(...)` / `fib(n-1)+fib(n-2)` 整段 parse 成
# call_expression(binary_expr, call_suffix)，真 callee 識別字埋在 binary 最末 operand（rhs）
# → 直接遞迴判定時往最末 operand 下鑽（同 boolean 畸形根源、對抗 review wf_ba17da36）。
_BINARY_CALLEE_WRAP = {"multiplicative_expression", "additive_expression",
                       "comparison_expression", "equality_expression",
                       "conjunction_expression", "disjunction_expression"}

# 各語言控制流 taxonomy（tools/_probe_cflow.py + _probe_if_fields.py + _probe_labeled.py
# 2026-06-22~23 實測坐實，非腦推）。
#
# 共用 schema 欄位（每語言 spec）：
#   incr_nest          B1+B3+增層（打斷流、受巢狀加權的結構：loops/switch/match/catch/ternary…）
#   if_types           if 節點型別集合（多數 {"if_statement"}；Rust expression-based={"if_expression"}）
#   if_style           "wrapper"＝else-if 由 else_clause/elif_clause 包（Py/TS/JS/TSX/Rust）；
#                      "field"＝else-if 是 if 的 alternative field 直接指 if（無 wrapper：Go/Java/C#）
#   elif/else          wrapper style 的平級分支節點型別（field style 留空、走 alternative field）
#   transparent        不加分/不增層、純遞迴的容器（try 本身、finally）
#   nest_only          增巢狀層但不加分（巢狀函數/lambda/closure）
#   comp_for/comp_if   Python comprehension 的 for/if 子句
#   boolean/bool_ops   邏輯運算子節點型別 + 算 run 的運算子（⛔ 不含 ??/null-coalescing）
#   call/callee_field  呼叫節點型別 + callee 的 field 名（直接遞迴 +1）
#   labeled_jump       帶標籤跳轉節點型別（僅「帶 label」才 +1）
#   label_child_types  該語言 label 的 child 型別（藉此判斷 break/continue 是否帶 label）
COGNITIVE_SPECS: dict[str, dict] = {
    "python": {
        # B1+B3+增層（打斷流且受巢狀加權）
        "incr_nest": {"for_statement", "while_statement", "conditional_expression",
                      "match_statement", "except_clause"},
        "if_types": {"if_statement"},
        "if_style": "wrapper",
        # if 由 visit_if 專責（else-if 鏈展平）；elif/else 平級分支
        "elif": {"elif_clause"},
        "else": {"else_clause"},
        # 透明容器（不加分、不增層、遞迴）：try 本身、finally
        "transparent": {"try_statement", "finally_clause"},
        # 增層不加分（巢狀函數/lambda）
        "nest_only": {"lambda", "function_definition"},
        "comp_for": {"for_in_clause"},
        "comp_if": {"if_clause"},
        "boolean": {"boolean_operator"},
        "bool_ops": {"and", "or"},
        "call": {"call"},
        "callee_field": "function",
        "labeled_jump": set(),  # Python 無帶標籤跳轉
        "label_child_types": set(),
    },
    "typescript": {
        "incr_nest": {"for_statement", "for_in_statement", "while_statement",
                      "do_statement", "ternary_expression", "switch_statement",
                      "catch_clause"},
        "if_types": {"if_statement"},
        "if_style": "wrapper",
        "elif": set(),  # TS 無獨立 elif；else if = else_clause(if_statement)，由 visit_else 展平
        "else": {"else_clause"},
        "transparent": {"try_statement", "finally_clause"},
        "nest_only": {"arrow_function", "function_expression", "function_declaration"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary_expression"},
        # ⛔ 不含 ??（空值合併）：白皮書明文 ignore null-coalescing，?? 不打斷理解線性流（對抗 review HIGH）
        "bool_ops": {"&&", "||"},
        "call": {"call_expression"},
        "callee_field": "function",
        "labeled_jump": {"continue_statement", "break_statement"},  # 僅帶 label 才算
        "label_child_types": {"statement_identifier"},
    },
    # ── P4 新增（field-style else-if：Go/Java/C# 的 if.alternative 直接指 if，無 wrapper）──
    "go": {
        # Go: for 統一所有迴圈；switch 三型；無 do/while/三元/try-catch
        "incr_nest": {"for_statement", "expression_switch_statement",
                      "type_switch_statement", "select_statement"},
        "if_types": {"if_statement"},
        "if_style": "field",
        "elif": set(),
        "else": set(),
        "transparent": set(),  # Go 無 try（error return）
        "nest_only": {"func_literal"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary_expression"},
        "bool_ops": {"&&", "||"},
        "call": {"call_expression"},
        "callee_field": "function",
        "labeled_jump": {"continue_statement", "break_statement", "goto_statement"},
        "label_child_types": {"label_name"},  # continue OUT → continue_statement>label_name
    },
    "java": {
        # Java: switch 是 switch_expression（probe 坐實，非 switch_statement）
        "incr_nest": {"for_statement", "enhanced_for_statement", "while_statement",
                      "do_statement", "switch_expression", "ternary_expression",
                      "catch_clause"},
        "if_types": {"if_statement"},
        "if_style": "field",
        "elif": set(),
        "else": set(),
        "transparent": {"try_statement", "finally_clause"},
        "nest_only": {"lambda_expression"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary_expression"},
        "bool_ops": {"&&", "||"},
        "call": {"method_invocation"},
        "callee_field": "name",  # Java method_invocation 用 name field（非 function）
        "labeled_jump": {"continue_statement", "break_statement"},
        "label_child_types": {"identifier"},  # continue OUT; → continue_statement>identifier
    },
    "csharp": {
        # C#: switch 兩型——switch_statement（傳統）+ switch_expression（C# 8.0+ `x switch {…}` 極常見，
        # 對抗 review CS-1 抓漏）；三元是 conditional_expression
        "incr_nest": {"for_statement", "foreach_statement", "while_statement",
                      "do_statement", "switch_statement", "switch_expression",
                      "conditional_expression", "catch_clause"},
        "if_types": {"if_statement"},
        "if_style": "field",
        "elif": set(),
        "else": set(),
        "transparent": {"try_statement", "finally_clause"},
        "nest_only": {"lambda_expression", "anonymous_method_expression"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary_expression"},
        "bool_ops": {"&&", "||"},
        "call": {"invocation_expression"},
        "callee_field": "function",
        # C# 無 labeled break/continue（用 goto）；break/continue 在 switch/loop 皆裸 → 不計。
        # goto 罕見、label child 機制不同，誠實標限制不計（漏算只低估、不誤殺）。
        "labeled_jump": set(),
        "label_child_types": set(),
    },
    "rust": {
        # Rust: expression-based — if 是 if_expression、迴圈/match 皆 *_expression；無 try-catch/三元/do
        "incr_nest": {"for_expression", "while_expression", "loop_expression",
                      "match_expression"},
        "if_types": {"if_expression"},
        "if_style": "wrapper",  # Rust 有 else_clause wrapper（同 TS），但 if 是 if_expression
        "elif": set(),
        "else": {"else_clause"},
        "transparent": set(),  # Rust 無 try（Result/? 不算控制流）
        "nest_only": {"closure_expression"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary_expression"},
        "bool_ops": {"&&", "||"},
        "call": {"call_expression"},
        "callee_field": "function",
        "labeled_jump": {"break_expression", "continue_expression"},
        "label_child_types": {"label"},  # continue 'outer → continue_expression>label（break value 的 expr 不算）
    },
    # ── P5 新增（2026-06-23，tools/_probe_p5.py + _probe_p5_gap.py 實測坐實）──
    "c": {
        # C: wrapper-style（else_clause 是 alternative field，結構同 TS）；無 try-catch（無例外）；
        # 跳轉用 goto（goto_statement>statement_identifier）非 labeled break/continue
        "incr_nest": {"for_statement", "while_statement", "do_statement",
                      "switch_statement", "conditional_expression"},
        "if_types": {"if_statement"},
        "if_style": "wrapper",
        "elif": set(),
        "else": {"else_clause"},
        "transparent": set(),               # C 無 try
        "nest_only": {"function_definition"},  # GCC 巢狀函數增層計入外層、與 Python nest_only 一致（review wf_ba17da36）
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary_expression"},
        "bool_ops": {"&&", "||"},
        "call": {"call_expression"},
        "callee_field": "function",
        "labeled_jump": {"goto_statement"},  # goto 永遠帶 label → +1
        "label_child_types": {"statement_identifier"},
    },
    "cpp": {
        # C++: C 全部 + try/catch + lambda + range-based for（for_range_loop 獨立型別）
        "incr_nest": {"for_statement", "for_range_loop", "while_statement",
                      "do_statement", "switch_statement", "conditional_expression",
                      "catch_clause"},
        "if_types": {"if_statement"},
        "if_style": "wrapper",
        "elif": set(),
        "else": {"else_clause"},
        "transparent": {"try_statement"},   # try 透明、catch 加分
        # +local-class method（function_definition）巢狀增層計入外層、與 Python nest_only 一致（review wf_ba17da36）
        "nest_only": {"lambda_expression", "function_definition"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary_expression"},
        "bool_ops": {"&&", "||"},
        "call": {"call_expression"},
        "callee_field": "function",
        "labeled_jump": {"goto_statement"},
        "label_child_types": {"statement_identifier"},
    },
    "ruby": {
        # Ruby: if/elsif/else（then-body 是 `then` 節點 consequence field；elsif/else 是 alternative field）
        # case/when + case/in（case_match，Ruby 2.7+ pattern matching，皆 switch-like）、while/until/for
        # （body field=do）、begin/rescue/ensure（例外）、前置 unless 當 if-not、conditional（三元）；
        # 後置 modifier 全收（與區塊形式等價、防 game 向量）：if/unless/while/until/rescue _modifier；
        # 無 labeled break/continue（Ruby next/break/redo 皆裸、跳最內層）。
        # ⚠ 對抗 review（wf_ba17da36）抓漏：while_modifier/until_modifier/rescue_modifier/case_match 原漏列。
        "incr_nest": {"while", "until", "for", "case", "case_match", "conditional", "rescue",
                      "if_modifier", "unless_modifier", "while_modifier", "until_modifier",
                      "rescue_modifier"},
        "if_types": {"if", "unless"},       # 前置 unless = if-not
        "if_style": "wrapper",
        "elif": {"elsif"},
        "else": {"else"},
        "transparent": {"begin", "ensure"},  # begin 透明、ensure(finally) 透明、rescue 在 incr_nest 加分
        "nest_only": {"do_block", "block"},  # iterator block（each/map）= 巢狀函數語意
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary"},
        "bool_ops": {"&&", "||", "and", "or"},
        "call": {"call"},
        "callee_field": "method",            # Ruby call 用 method field（receiver 在 receiver field）
        "labeled_jump": set(),
        "label_child_types": set(),
    },
    "kotlin": {
        # Kotlin: field-style if（if_expression，alternative field）；when 取代 switch；
        # function body 無 field（function_body 無名 child→需 function_body() helper）；
        # &&/|| 是 conjunction_expression/disjunction_expression（不同節點型別，bool_type_ops 映射）；
        # call 無 callee field（callee=第一個 named child）；labeled = jump_expression>label
        "incr_nest": {"for_statement", "while_statement", "do_while_statement",
                      "when_expression", "catch_block"},
        "if_types": {"if_expression"},
        "if_style": "field",
        "elif": set(),
        "else": set(),
        "transparent": {"try_expression", "finally_block"},
        # +local fun（function_declaration）巢狀增層計入外層、與 Python nest_only 一致（review wf_ba17da36）
        "nest_only": {"lambda_literal", "anonymous_function", "function_declaration"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"conjunction_expression", "disjunction_expression"},
        "bool_ops": set(),                   # 運算子由節點型別給（見 bool_type_ops）
        "bool_type_ops": {"conjunction_expression": "&&", "disjunction_expression": "||"},
        "call": {"call_expression"},
        "callee_field": None,                # 無 callee field → 第一個 named child
        "labeled_jump": {"jump_expression"},
        "label_child_types": {"label"},
    },
    "swift": {
        # Swift: 客製 if（then-body 是無 field 的 statements、else 是 marker 節點、else-if 是 else 的 sibling）；
        # guard_statement（early-exit 當 if）；switch；repeat_while（do-while）；do/catch（do 透明、catch 加分）；
        # ternary_expression；&&/|| 同 Kotlin 雙節點型別；call 無 callee field；
        # labeled = control_transfer_statement（統一 continue/break/return）→ 靠 jump_keywords 區分
        "incr_nest": {"for_statement", "while_statement", "repeat_while_statement",
                      "switch_statement", "ternary_expression", "guard_statement",
                      "catch_block"},
        "if_types": {"if_statement"},
        "if_style": "swift",
        "elif": set(),
        "else": {"else"},
        "transparent": {"do_statement"},
        "nest_only": {"lambda_literal"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"conjunction_expression", "disjunction_expression"},
        "bool_ops": set(),
        "bool_type_ops": {"conjunction_expression": "&&", "disjunction_expression": "||"},
        "call": {"call_expression"},
        "callee_field": None,
        "labeled_jump": {"control_transfer_statement"},
        "label_child_types": {"simple_identifier"},
        # control_transfer_statement 統一 continue/break/return/throw；只有第一個 child（keyword token）
        # ∈ jump_keywords 且帶 label（simple_identifier）才 +1（防 `return x` 的 simple_identifier 誤判）
        "jump_keywords": {"continue", "break"},
    },
}
# deepcopy 而非共用同一物件：防未來 per-language mutate（probe/debug 對某語言 spec .add()）
# 跨語言污染（對抗 review LOW footgun）。三者目前 taxonomy 相同、但各自獨立物件。
COGNITIVE_SPECS["javascript"] = copy.deepcopy(COGNITIVE_SPECS["typescript"])
COGNITIVE_SPECS["tsx"] = copy.deepcopy(COGNITIVE_SPECS["typescript"])


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def supported(lang_key: str) -> bool:
    """該語言是否高信心計分（其餘語言 cognitive=None UNKNOWN）。"""
    return lang_key in COGNITIVE_SPECS and not _env_on("CODESEXTANT_COGNITIVE_DISABLED")


# 多數語言 function 定義節點有 "body" field；少數（Kotlin function_declaration）的 body 是無 field
# 名的子節點（function_body），需 per-lang fallback 取（probe 坐實）。clones 抽指紋與測試 helper
# 共用此函數＝body 抽取單一真相源。
_BODY_FALLBACK_TYPES: dict[str, set] = {
    "kotlin": {"function_body"},
}


def function_body(def_node, lang_key: str):
    """取 function/method 定義節點的 body 節點（無 → None）。Kotlin 走 function_body fallback。"""
    if def_node is None:
        return None
    b = def_node.child_by_field_name("body")
    if b is not None:
        return b
    fallback = _BODY_FALLBACK_TYPES.get(lang_key)
    if fallback:
        for c in def_node.children:
            if c.type in fallback:
                return c
    return None


def _node_text(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _op_text(node, src: bytes) -> str:
    op = node.child_by_field_name("operator")
    return _node_text(op, src) if op is not None else ""


def cognitive_complexity(body, lang_key: str, func_name: str | None = None,
                         src: bytes = b"") -> int | None:
    """算 function body 的 cognitive complexity。非高信心語言/關閉/body=None → None（UNKNOWN）。

    body=function 的 body node；func_name=函數名（直接遞迴 +1）；src=原始 bytes（取 operator/callee 文字）。
    """
    spec = COGNITIVE_SPECS.get(lang_key)
    if spec is None or body is None or _env_on("CODESEXTANT_COGNITIVE_DISABLED"):
        return None

    incr_nest = spec["incr_nest"]
    if_types = spec["if_types"]
    if_style = spec["if_style"]
    elif_t = spec["elif"]
    else_t = spec["else"]
    transparent = spec["transparent"]
    nest_only = spec["nest_only"]
    comp_for = spec["comp_for"]
    comp_if = spec["comp_if"]
    boolean = spec["boolean"]
    bool_ops = spec["bool_ops"]
    bool_type_ops = spec.get("bool_type_ops")   # P5：節點型別→運算子（Kotlin/Swift conjunction/disjunction）
    call_t = spec["call"]
    callee_field = spec["callee_field"]
    labeled_jump = spec["labeled_jump"]
    label_child_types = spec["label_child_types"]
    jump_keywords = spec.get("jump_keywords")   # P5：Swift control_transfer 區分 continue/break vs return
    _dbg = _env_on("CODESEXTANT_COG_DEBUG")     # debug trace（env-gated、熱路徑只讀一次）

    total = 0

    def is_logical(n) -> bool:
        if bool_type_ops is not None:
            return n.type in bool_type_ops
        return n.type in boolean and _op_text(n, src) in bool_ops

    def is_bool_root(n) -> bool:
        # 是否為一個布林表達式的最外層 logical 節點（往上若遇另一個 logical 祖先＝非根）。
        # bool_type_ops 語言（Kotlin/Swift）用此判定，避免 grammar 把 a&&b||c 拆成 conjunction/disjunction
        # 多節點各自獨立觸發而 double-count（尤其 Swift 運算子優先級畸形把 logical 埋在 comparison 下）。
        p = n.parent
        while p is not None:
            if is_logical(p):
                return False
            p = p.parent
        return True

    def count_bool_runs(node) -> int:
        """連續邏輯運算子：中序收集 operator，數「相鄰不同」的 run 數（a&&b||c=2）。"""
        ops: list[str] = []

        if bool_type_ops is not None:
            # Kotlin/Swift：&&/|| 是不同節點型別、operand 無 left/right field（用位置 named children）；
            # 穿過非 logical 中間層（Swift grammar 運算子優先級畸形會把 logical 埋在 comparison 之下）。
            def collect(n):
                kids = [c for c in n.children if c.is_named]
                if n.type in bool_type_ops:
                    if kids:
                        collect(kids[0])
                    ops.append(bool_type_ops[n.type])
                    for kk in kids[1:]:
                        collect(kk)
                else:
                    for kk in kids:
                        collect(kk)
        else:
            def collect(n):
                if is_logical(n):
                    left = n.child_by_field_name("left")
                    right = n.child_by_field_name("right")
                    if left is not None:
                        collect(left)
                    ops.append(_op_text(n, src))
                    if right is not None:
                        collect(right)

        collect(node)
        if not ops:
            return 0
        runs = 1
        for i in range(1, len(ops)):
            if ops[i] != ops[i - 1]:
                runs += 1
        return runs

    def is_labeled(node) -> bool:
        # 帶 label 才算（裸 break/continue 不算）；各語言 label child 型別不同（per-spec）。
        # jump_keywords（Swift）：control_transfer_statement 統一 continue/break/return，須第一個 child
        # （keyword token）∈ jump_keywords 才算（防 `return x` 的 simple_identifier result 誤判 label）。
        if jump_keywords is not None:
            kids = node.children
            if not kids or kids[0].type not in jump_keywords:
                return False
        return any(c.type in label_child_types for c in node.children)

    def is_direct_recursion(call_node) -> bool:
        # 直接遞迴：裸 identifier==func_name，或 self/cls/this.<func_name>；
        # ⛔ 跨物件同名方法 obj.foo() 於名為 foo 的函數內不算（對抗 review MEDIUM 收緊誤判）
        if callee_field is not None:
            fn = call_node.child_by_field_name(callee_field)
        else:
            # Kotlin/Swift call_expression 無 callee field → callee＝第一個 named child
            # （裸呼叫=simple_identifier；member 呼叫=navigation_expression、走下方 navigation 分支）
            fn = next((c for c in call_node.children if c.is_named), None)
            # Swift 算術/比較外包（n * fact(n-1)）：callee 是 binary expression → 下鑽最末 operand 取真 callee
            seen = 0
            while fn is not None and fn.type in _BINARY_CALLEE_WRAP and seen < 8:
                seen += 1
                rhs = fn.child_by_field_name("rhs")
                if rhs is None:
                    named = [c for c in fn.children if c.is_named]
                    rhs = named[-1] if named else None
                fn = rhs
        if fn is None:
            return False
        if fn.type in _IDENT_TYPES:
            # 有 receiver/object 且非 self/this/cls → 跨物件同名、不算（Java/C# object、Ruby receiver）
            cobj = (call_node.child_by_field_name("object")
                    or call_node.child_by_field_name("receiver"))
            if cobj is not None and _node_text(cobj, src) not in ("self", "cls", "this"):
                return False
            return _node_text(fn, src) == func_name
        if fn.type == "navigation_expression":
            # Kotlin/Swift member 呼叫 this.f()/self.f()：navigation_expression
            #   Kotlin（無 field）：[this_expression/identifier, navigation_suffix > simple_identifier]
            #   Swift（有 field）：target field（self_expression）、suffix field（navigation_suffix > simple_identifier）
            tgt = (fn.child_by_field_name("target")
                   or next((c for c in fn.children if c.is_named), None))
            suf = (fn.child_by_field_name("suffix")
                   or next((c for c in fn.children if c.type == "navigation_suffix"), None))
            attr = (next((c for c in suf.children if c.type == "simple_identifier"), None)
                    if suf is not None else None)
            if tgt is not None and attr is not None:
                return (_node_text(tgt, src) in ("self", "cls", "this")
                        and _node_text(attr, src) == func_name)
            return False
        if fn.type in ("attribute", "member_expression", "field_expression",
                       "selector_expression"):
            obj = fn.child_by_field_name("object") or fn.child_by_field_name("operand")
            attr = (fn.child_by_field_name("attribute") or fn.child_by_field_name("property")
                    or fn.child_by_field_name("field"))
            if obj is not None and attr is not None:
                return (_node_text(obj, src) in ("self", "cls", "this")
                        and _node_text(attr, src) == func_name)
        return False

    def visit_if(node, nesting, as_elseif):
        # wrapper-style（Py/TS/JS/TSX/Rust）。靠 field 名 consequence 認 then-body：block 或無大括號單語句
        # （TS `if(x) for(){}`）皆 +層——對齊 visit_if_field/incr_nest 語意（對抗 review 修「無括號漏增層＝game 向量」）。
        nonlocal total
        total += 1 if as_elseif else (1 + nesting)
        cur = node.walk()
        if not cur.goto_first_child():
            return
        while True:
            c = cur.node
            ct = c.type
            fld = cur.field_name
            if ct in else_t:
                visit_else(c, nesting)        # 平級（不繼承 then-body 的層）
            elif ct in elif_t:
                visit_elif(c, nesting)        # 平級（Python）
            elif fld == "consequence":
                visit(c, nesting + 1)         # then body 增層（block 或無大括號單語句）
            elif c.is_named:
                visit(c, nesting)             # condition / 其他（boolean run / 遞迴）
            if not cur.goto_next_sibling():
                break

    def visit_elif(node, nesting):
        nonlocal total
        total += 1                            # B1 無 B3
        cur = node.walk()
        if not cur.goto_first_child():
            return
        while True:
            c = cur.node
            if cur.field_name == "consequence":
                visit(c, nesting + 1)         # elif body 增層
            elif c.is_named:
                visit(c, nesting)             # condition
            if not cur.goto_next_sibling():
                break

    def visit_else(node, nesting):
        nonlocal total
        p = node.parent
        # else 的合法 if-like parent＝if（含 Ruby unless）或 elsif（Ruby else 的 parent 可能是 elsif）；
        # 否則（for/while/try/begin/case 的 else）→ 透明（Py for-else、Ruby case-else 等）。
        if p is not None and p.type not in if_types and p.type not in elif_t:
            for c in node.children:
                visit(c, nesting)
            return
        inner_if = next((c for c in node.children if c.type in if_types), None)
        if inner_if is not None:              # else if（展平：平級、無 B3；Rust=if_expression）
            visit_if(inner_if, nesting, as_elseif=True)
        else:                                 # 純 else：+1、body 增層（block 或無大括號單語句皆 +層）
            total += 1
            for c in node.children:
                if c.is_named:
                    visit(c, nesting + 1)

    def _unwrap_elseif(node):
        # alternative field 是否為 else-if：Go/Java/C# 直接指 if；Kotlin 的 else-if 是
        # control_structure_body 包單一 if_expression（多一層 wrapper，probe 坐實）→ 剝開取內層 if。
        # control_structure_body 是 Kotlin 專屬節點、Go/Java/C# 不產生 → 對它們零影響。
        if node.type in if_types:
            return node
        if node.type == "control_structure_body":
            named = [c for c in node.children if c.is_named]
            if len(named) == 1 and named[0].type in if_types:
                return named[0]
        return None

    def visit_if_field(node, nesting, as_elseif):
        # field-style else-if（Go/Java/C#/Kotlin）：if.alternative field 指 if（else-if）或 block（純 else），
        # 無 else_clause/elif_clause wrapper。靠 field 名 consequence/alternative 區分 then/else（probe 證跨語言一致）。
        nonlocal total
        total += 1 if as_elseif else (1 + nesting)
        cur = node.walk()
        if not cur.goto_first_child():
            return
        while True:
            child = cur.node
            fld = cur.field_name
            if fld == "consequence":
                visit(child, nesting + 1)             # then body 增層
            elif fld == "alternative":
                inner_if = _unwrap_elseif(child)
                if inner_if is not None:              # else-if：平級、+1 無 B3
                    visit_if_field(inner_if, nesting, as_elseif=True)
                else:                                 # 純 else（block 或無大括號單語句皆 +1）：body 增層
                    total += 1                        # ⚠ Go/Java/C# 允許 `else stmt;` 無 block，仍須 +1
                    visit(child, nesting + 1)
            elif child.is_named:
                visit(child, nesting)                 # condition / initializer（抓 boolean run / 遞迴）
            if not cur.goto_next_sibling():
                break

    def visit_if_swift(node, nesting, as_elseif):
        # Swift 客製：then-body 是無 field 的 statements、else 是 marker token 節點、
        # else-if/純-else body 是 else 的 sibling（probe 坐實）。靠 seen_else flag 區分 then/else-body。
        nonlocal total
        total += 1 if as_elseif else (1 + nesting)
        seen_else = False
        for c in node.children:
            if c.type in else_t:                       # else marker（型別 else）
                seen_else = True
                continue
            if not c.is_named:
                continue
            if not seen_else:
                if c.type == "statements":             # then-body（無 field 名）增層
                    visit(c, nesting + 1)
                else:                                  # condition / 其他（boolean run / 遞迴）
                    visit(c, nesting)
            elif c.type in if_types:                   # else-if（平級、+1 無 B3）
                visit_if_swift(c, nesting, as_elseif=True)
            else:                                      # 純 else body（statements）：+1、body 增層
                total += 1
                visit(c, nesting + 1)

    def visit(node, nesting):
        nonlocal total
        t = node.type
        if _dbg:
            sys.stderr.write(f"[cog] {'. ' * nesting}{t} n={nesting} tot_in={total}\n")

        if not node.is_named:
            # keyword token 與節點型別撞名（Ruby while/until/for/case/unless/if 的 keyword token 之 type
            # ＝while/until/...＝控制流節點型別）→ 不可計分，否則 incr_nest/if_types 對 token 重複 +1。
            # ⚠ symbols.walk v0.11.0 抽符號踩過同坑、同解（is_named 過濾）。
            return

        if t in if_types:
            p = node.parent
            if if_style == "field":
                # field-style（Go/Java/C#/Kotlin）：else-if 內層 if＝parent if 的 alternative → 已由 visit_if_field 處理
                if p is not None and p.type in if_types:
                    return
                visit_if_field(node, nesting, as_elseif=False)
            elif if_style == "swift":
                # Swift：else-if 的內層 if_statement 是 outer if_statement 的直接 child（else 的 sibling）→
                # parent 是 if_statement 時已由 visit_if_swift 處理、skip（巢狀 if 的 parent 是 statements、不 skip）
                if p is not None and p.type in if_types:
                    return
                visit_if_swift(node, nesting, as_elseif=False)
            else:
                # wrapper-style（Py/TS/JS/TSX/Rust/C/C++/Ruby）：else-if 內層 if 在 else_clause/elsif 內 → 已由 visit_else 處理
                if p is not None and p.type in else_t:
                    return
                visit_if(node, nesting, as_elseif=False)
            return
        if t in else_t:
            visit_else(node, nesting)
            return
        if t in elif_t:
            visit_elif(node, nesting)
            return
        if t in transparent:
            for c in node.children:
                visit(c, nesting)
            return
        if t in incr_nest:
            total += 1 + nesting
            for c in node.children:
                # loop 的 else（for-else/while-else）是兄弟層、不繼承 loop body 巢狀深度（對抗 review MEDIUM）
                visit(c, nesting if c.type in else_t else nesting + 1)
            return
        if t in nest_only:
            for c in node.children:
                visit(c, nesting + 1)
            return
        if t in comp_for:
            total += 1 + nesting
            for c in node.children:
                visit(c, nesting + 1)
            return
        if t in comp_if:
            total += 1
            for c in node.children:
                visit(c, nesting)
            return
        if t in boolean:
            if is_logical(node):
                if bool_type_ops is not None:
                    # Kotlin/Swift：&&/|| 是不同節點型別，用 is_bool_root 找最外層（穿祖先防 double-count）
                    if is_bool_root(node):
                        total += count_bool_runs(node)
                else:
                    p = node.parent
                    if not (p is not None and is_logical(p)):
                        total += count_bool_runs(node)   # 只在最外層邏輯節點算一次
            for c in node.children:
                visit(c, nesting)
            return
        if t in labeled_jump:
            if is_labeled(node):
                total += 1
            # 繼續遍歷 children：Kotlin jump_expression / Swift control_transfer_statement 統一涵蓋 return，
            # 其 value 表達式（return f(n-1) 的遞迴 call、return x>0?1:0 的 ternary）須照算（非 return 即漏）。
            for c in node.children:
                visit(c, nesting)
            return
        if t in call_t:
            if func_name and is_direct_recursion(node):
                total += 1
            for c in node.children:
                visit(c, nesting)
            return

        for c in node.children:
            visit(c, nesting)

    try:
        visit(body, 0)
    except RecursionError:
        # 超深 AST（罕見 autogen / 超長布林鏈 / 深 method chain）打爆 Python 堆疊 → 誠實回 None
        # （UNKNOWN），不炸、也不讓上游 engine 裸 except 靜默吞掉整檔指紋（對抗 review CRITICAL）
        return None
    return total
