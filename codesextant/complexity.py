"""Compute cognitive complexity from tree-sitter syntax trees.

The implementation follows the SonarSource cognitive complexity model. A break in
linear control flow adds one point, and nested flow structures add their current
nesting depth. The walker handles each supported language through a small grammar
specification. Unsupported grammars return ``None`` instead of a numeric score.

Only direct recursion is counted. Python comprehension clauses count as loop and
condition nodes. Very deep trees return ``None`` on ``RecursionError``. C# ``goto``
is not counted because its label structure differs from labeled break and continue
statements.

Set ``CODESEXTANT_COGNITIVE_DISABLED=1`` to disable scoring.
"""
from __future__ import annotations

import copy
import os
import sys

_BLOCK_TYPES = {"block", "statement_block"}
# simple_identifier = Kotlin/Swift's identifier node (used for call-callee direct-recursion detection)
_IDENT_TYPES = {"identifier", "property_identifier", "field_identifier", "simple_identifier"}
# Swift grammar has a quirky operator-precedence parse: `n * fact(...)` / `fib(n-1)+fib(n-2)`
# parse as a whole into call_expression(binary_expr, call_suffix), with the true callee
# identifier buried in the binary expression's last operand (rhs)
# Direct-recursion detection drills into the last operand. Boolean expressions use
# the same parser shape.
_BINARY_CALLEE_WRAP = {"multiplicative_expression", "additive_expression",
                       "comparison_expression", "equality_expression",
                       "conjunction_expression", "disjunction_expression"}

# Per-language control-flow taxonomy.
#
# Shared schema fields (per language spec):
#   incr_nest          B1+B3+nest increase (flow-breaking structures weighted by nesting:
#                      loops/switch/match/catch/ternary...)
#   if_types           set of if-node types (mostly {"if_statement"}; Rust is
#                      expression-based = {"if_expression"})
#   if_style           "wrapper" = else-if wrapped in else_clause/elif_clause (Py/TS/JS/TSX/Rust);
#                      "field" = else-if is the if's alternative field pointing directly
#                      at another if (no wrapper: Go/Java/C#)
#   elif/else          sibling-level branch node types for wrapper style (empty for field
#                      style, which uses the alternative field instead)
#   transparent        containers that add no score, no nesting, pure pass-through
#                      recursion (try itself, finally)
#   nest_only          increases nesting level but adds no score (nested function/lambda/closure)
#   comp_for/comp_if   Python comprehension's for/if clauses
#   boolean/bool_ops   logical-operator node types + the operators counted as a run
#                      (does NOT include ??/null-coalescing)
#   call/callee_field  call-node types + the callee's field name (direct recursion +1)
#   labeled_jump       labeled-jump node types (+1 only when it actually carries a label)
#   label_child_types  this language's label child node type (used to tell whether
#                      break/continue carries a label)
COGNITIVE_SPECS: dict[str, dict] = {
    "python": {
        # B1+B3+nest increase (breaks flow and is nesting-weighted)
        "incr_nest": {"for_statement", "while_statement", "conditional_expression",
                      "match_statement", "except_clause"},
        "if_types": {"if_statement"},
        "if_style": "wrapper",
        # if is handled by visit_if (else-if chains are flattened); elif/else are sibling branches
        "elif": {"elif_clause"},
        "else": {"else_clause"},
        # transparent containers (no score, no nesting, just recurse): try itself, finally
        "transparent": {"try_statement", "finally_clause"},
        # increases nesting but adds no score (nested function/lambda)
        "nest_only": {"lambda", "function_definition"},
        "comp_for": {"for_in_clause"},
        "comp_if": {"if_clause"},
        "boolean": {"boolean_operator"},
        "bool_ops": {"and", "or"},
        "call": {"call"},
        "callee_field": "function",
        "labeled_jump": set(),  # Python has no labeled jumps
        "label_child_types": set(),
    },
    "typescript": {
        "incr_nest": {"for_statement", "for_in_statement", "while_statement",
                      "do_statement", "ternary_expression", "switch_statement",
                      "catch_clause"},
        "if_types": {"if_statement"},
        "if_style": "wrapper",
        "elif": set(),  # TS has no separate elif; else-if = else_clause(if_statement), flattened by visit_else
        "else": {"else_clause"},
        "transparent": {"try_statement", "finally_clause"},
        "nest_only": {"arrow_function", "function_expression", "function_declaration"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary_expression"},
        # does NOT include ?? (nullish coalescing): the white paper explicitly says to
        # ignore null-coalescing, since ?? does not break the linear reading flow
        "bool_ops": {"&&", "||"},
        "call": {"call_expression"},
        "callee_field": "function",
        "labeled_jump": {"continue_statement", "break_statement"},  # only counts when labeled
        "label_child_types": {"statement_identifier"},
    },
    # Field-style else-if: Go, Java, and C# point directly at the alternative if.
    "go": {
        # Go: `for` covers every loop form; switch has three variants; no do/while, ternary, or try-catch
        "incr_nest": {"for_statement", "expression_switch_statement",
                      "type_switch_statement", "select_statement"},
        "if_types": {"if_statement"},
        "if_style": "field",
        "elif": set(),
        "else": set(),
        "transparent": set(),  # Go has no try (uses error returns)
        "nest_only": {"func_literal"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary_expression"},
        "bool_ops": {"&&", "||"},
        "call": {"call_expression"},
        "callee_field": "function",
        "labeled_jump": {"continue_statement", "break_statement", "goto_statement"},
        "label_child_types": {"label_name"},  # continue OUT -> continue_statement>label_name
    },
    "java": {
        # Java represents switch as switch_expression, not switch_statement.
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
        "callee_field": "name",  # Java method_invocation uses the "name" field (not "function")
        "labeled_jump": {"continue_statement", "break_statement"},
        "label_child_types": {"identifier"},  # continue OUT; -> continue_statement>identifier
    },
    "csharp": {
        # C# has classic switch_statement and C# 8.0+ switch_expression forms.
        # ternary is conditional_expression
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
        # C# has no labeled break/continue (it uses goto); break/continue in
        # switch/loop are always bare -> not counted.
        # goto has a different label structure and is not counted here.
        "labeled_jump": set(),
        "label_child_types": set(),
    },
    "rust": {
        # Rust: expression-based - if is if_expression, loops/match are all *_expression;
        # no try-catch/ternary/do
        "incr_nest": {"for_expression", "while_expression", "loop_expression",
                      "match_expression"},
        "if_types": {"if_expression"},
        "if_style": "wrapper",  # Rust has an else_clause wrapper (like TS), but if is if_expression
        "elif": set(),
        "else": {"else_clause"},
        "transparent": set(),  # Rust has no try (Result/? does not count as control flow)
        "nest_only": {"closure_expression"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary_expression"},
        "bool_ops": {"&&", "||"},
        "call": {"call_expression"},
        "callee_field": "function",
        "labeled_jump": {"break_expression", "continue_expression"},
        "label_child_types": {"label"},  # continue 'outer -> continue_expression>label (break value expr doesn't count)
    },
    # Additional language specifications.
    "c": {
        # C: wrapper-style (else_clause is the alternative field, same structure as TS);
        # no try-catch (no exceptions); jumps use goto (goto_statement>statement_identifier),
        # not labeled break/continue
        "incr_nest": {"for_statement", "while_statement", "do_statement",
                      "switch_statement", "conditional_expression"},
        "if_types": {"if_statement"},
        "if_style": "wrapper",
        "elif": set(),
        "else": {"else_clause"},
        "transparent": set(),               # C has no try
        "nest_only": {"function_definition"},  # GCC nested functions count as a nesting increase on the outer scope, consistent with Python's nest_only (per review wf_ba17da36)
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary_expression"},
        "bool_ops": {"&&", "||"},
        "call": {"call_expression"},
        "callee_field": "function",
        "labeled_jump": {"goto_statement"},  # goto always carries a label -> +1
        "label_child_types": {"statement_identifier"},
    },
    "cpp": {
        # C++: everything C has, plus try/catch + lambda + range-based for (for_range_loop is a separate node type)
        "incr_nest": {"for_statement", "for_range_loop", "while_statement",
                      "do_statement", "switch_statement", "conditional_expression",
                      "catch_clause"},
        "if_types": {"if_statement"},
        "if_style": "wrapper",
        "elif": set(),
        "else": {"else_clause"},
        "transparent": {"try_statement"},   # try is transparent, catch adds score
        # +local-class method (function_definition) nesting counts against the outer scope,
        # consistent with Python's nest_only (per review wf_ba17da36)
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
        # Ruby: if/elsif/else (the then-body is the `then` node's consequence field;
        # elsif/else is the alternative field); case/when + case/in (case_match, Ruby
        # 2.7+ pattern matching, both switch-like); while/until/for (body field = do);
        # begin/rescue/ensure (exceptions); a leading `unless` is treated as if-not;
        # conditional (ternary); postfix modifiers are all included (equivalent to
        # block form, prevents a gaming vector): if/unless/while/until/rescue _modifier;
        # no labeled break/continue (Ruby's next/break/redo are always bare, jumping
        # the innermost loop only).
        # Modifier forms and case_match use the same control-flow rules as block forms.
        "incr_nest": {"while", "until", "for", "case", "case_match", "conditional", "rescue",
                      "if_modifier", "unless_modifier", "while_modifier", "until_modifier",
                      "rescue_modifier"},
        "if_types": {"if", "unless"},       # leading unless = if-not
        "if_style": "wrapper",
        "elif": {"elsif"},
        "else": {"else"},
        "transparent": {"begin", "ensure"},  # begin is transparent, ensure(finally) is transparent, rescue adds score via incr_nest
        "nest_only": {"do_block", "block"},  # iterator block (each/map) = nested-function semantics
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"binary"},
        "bool_ops": {"&&", "||", "and", "or"},
        "call": {"call"},
        "callee_field": "method",            # Ruby call uses the "method" field (receiver is in the "receiver" field)
        "labeled_jump": set(),
        "label_child_types": set(),
    },
    "kotlin": {
        # Kotlin: field-style if (if_expression, alternative field); `when` replaces switch;
        # function body has no field (function_body is an unnamed child -> needs the
        # function_body() helper); &&/|| are conjunction_expression/disjunction_expression
        # (distinct node types, mapped via bool_type_ops); call has no callee field
        # (callee = first named child); labeled = jump_expression>label
        "incr_nest": {"for_statement", "while_statement", "do_while_statement",
                      "when_expression", "catch_block"},
        "if_types": {"if_expression"},
        "if_style": "field",
        "elif": set(),
        "else": set(),
        "transparent": {"try_expression", "finally_block"},
        # +local fun (function_declaration) nesting counts against the outer scope,
        # consistent with Python's nest_only (per review wf_ba17da36)
        "nest_only": {"lambda_literal", "anonymous_function", "function_declaration"},
        "comp_for": set(),
        "comp_if": set(),
        "boolean": {"conjunction_expression", "disjunction_expression"},
        "bool_ops": set(),                   # operator is given by node type (see bool_type_ops)
        "bool_type_ops": {"conjunction_expression": "&&", "disjunction_expression": "||"},
        "call": {"call_expression"},
        "callee_field": None,                # no callee field -> first named child
        "labeled_jump": {"jump_expression"},
        "label_child_types": {"label"},
    },
    "swift": {
        # Swift: bespoke if (then-body is unfielded "statements", else is a marker node,
        # else-if is a sibling of else); guard_statement (early-exit, treated as if);
        # switch; repeat_while (do-while); do/catch (do is transparent, catch adds score);
        # ternary_expression; &&/|| share the same dual-node-type scheme as Kotlin;
        # call has no callee field; labeled = control_transfer_statement (unifies
        # continue/break/return) -> disambiguated via jump_keywords
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
        # control_transfer_statement unifies continue/break/return/throw; only counts
        # (+1) when the first child (the keyword token) is in jump_keywords AND it
        # carries a label (simple_identifier) - this prevents `return x`'s
        # simple_identifier result from being read as a label (a false positive).
        "jump_keywords": {"continue", "break"},
    },
}
# Deep copies prevent per-language mutations from leaking across related grammars.
COGNITIVE_SPECS["javascript"] = copy.deepcopy(COGNITIVE_SPECS["typescript"])
COGNITIVE_SPECS["tsx"] = copy.deepcopy(COGNITIVE_SPECS["typescript"])


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def supported(lang_key: str) -> bool:
    """Is this language scored with high confidence? (other languages return cognitive=None, UNKNOWN)."""
    return lang_key in COGNITIVE_SPECS and not _env_on("CODESEXTANT_COGNITIVE_DISABLED")


# Most languages' function-definition nodes have a "body" field; a few (Kotlin's
# function_declaration) have a body that is an unnamed child node (function_body)
# requiring a per-language fallback lookup. The clone
# fingerprinter and test helpers share this function as the single source of
# truth for body extraction.
_BODY_FALLBACK_TYPES: dict[str, set] = {
    "kotlin": {"function_body"},
}


def function_body(def_node, lang_key: str):
    """Get the body node of a function/method definition node (None if absent). Kotlin uses the function_body fallback."""
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
    """Compute the cognitive complexity of a function body. Returns None (UNKNOWN) for non-high-confidence languages, when disabled, or when body=None.

    body=the function's body node; func_name=the function name (used for direct-recursion
    +1); src=the raw bytes (used to read operator/callee text).
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
    bool_type_ops = spec.get("bool_type_ops")   # Kotlin/Swift node type -> operator
    call_t = spec["call"]
    callee_field = spec["callee_field"]
    labeled_jump = spec["labeled_jump"]
    label_child_types = spec["label_child_types"]
    jump_keywords = spec.get("jump_keywords")   # Swift distinguishes jumps from return
    _dbg = _env_on("CODESEXTANT_COG_DEBUG")     # debug trace (env-gated, read once on the hot path)

    total = 0

    def is_logical(n) -> bool:
        if bool_type_ops is not None:
            return n.type in bool_type_ops
        return n.type in boolean and _op_text(n, src) in bool_ops

    def is_bool_root(n) -> bool:
        # Is this the outermost logical node of a boolean expression? (if a logical
        # ancestor is found while walking up, this node is not the root.)
        # bool_type_ops languages (Kotlin/Swift) use this check to avoid the grammar
        # splitting a&&b||c into multiple independent conjunction/disjunction nodes
        # that would each fire separately and double-count (especially since Swift's
        # operator-precedence quirk buries a logical node under a comparison node).
        p = n.parent
        while p is not None:
            if is_logical(p):
                return False
            p = p.parent
        return True

    def count_bool_runs(node) -> int:
        """Consecutive logical operators: collect operators in-order, count the number of "adjacent-different" runs (a&&b||c=2)."""
        ops: list[str] = []

        if bool_type_ops is not None:
            # Kotlin/Swift: &&/|| are distinct node types, operands have no left/right
            # field (use positional named children); walks through non-logical
            # intermediate layers (Swift grammar's operator-precedence quirk buries
            # a logical node under a comparison node).
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
        # Only counts when a label is actually present (bare break/continue don't count);
        # each language's label-child node type differs (per-spec).
        # jump_keywords (Swift): control_transfer_statement unifies continue/break/return,
        # so the first child (the keyword token) must be in jump_keywords for this to
        # count (prevents `return x`'s simple_identifier result from being read as a label, a false positive).
        if jump_keywords is not None:
            kids = node.children
            if not kids or kids[0].type not in jump_keywords:
                return False
        return any(c.type in label_child_types for c in node.children)

    def is_direct_recursion(call_node) -> bool:
        # Direct recursion: a bare identifier==func_name, or self/cls/this.<func_name>;
        # a same-named method on a different object, obj.foo() called inside a function
        # named foo does not count, which avoids cross-object false positives.
        if callee_field is not None:
            fn = call_node.child_by_field_name(callee_field)
        else:
            # Kotlin/Swift call_expression has no callee field -> callee = first named child
            # (a bare call is simple_identifier; a member call is navigation_expression,
            # handled by the navigation branch below)
            fn = next((c for c in call_node.children if c.is_named), None)
            # Swift's arithmetic/comparison wrapping (n * fact(n-1)): the callee is a
            # binary expression -> drill into the last operand to find the true callee
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
            # has a receiver/object and it is not self/this/cls -> same name on a
            # different object, does not count (Java/C# object, Ruby receiver)
            cobj = (call_node.child_by_field_name("object")
                    or call_node.child_by_field_name("receiver"))
            if cobj is not None and _node_text(cobj, src) not in ("self", "cls", "this"):
                return False
            return _node_text(fn, src) == func_name
        if fn.type == "navigation_expression":
            # Kotlin/Swift member call this.f()/self.f(): navigation_expression
            #   Kotlin (no field): [this_expression/identifier, navigation_suffix > simple_identifier]
            #   Swift (has fields): target field (self_expression), suffix field (navigation_suffix > simple_identifier)
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
        # wrapper-style (Py/TS/JS/TSX/Rust). Recognizes the then-body via the
        # "consequence" field name: a block or an unbraced single statement
        # (TS `if(x) for(){}`) both receive the same nesting increment.
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
                visit_else(c, nesting)        # sibling level (does not inherit the then-body's nesting)
            elif ct in elif_t:
                visit_elif(c, nesting)        # sibling level (Python)
            elif fld == "consequence":
                visit(c, nesting + 1)         # then body gets +nesting (block or unbraced single statement)
            elif c.is_named:
                visit(c, nesting)             # condition / other (boolean run / recursion)
            if not cur.goto_next_sibling():
                break

    def visit_elif(node, nesting):
        nonlocal total
        total += 1                            # B1 only, no B3
        cur = node.walk()
        if not cur.goto_first_child():
            return
        while True:
            c = cur.node
            if cur.field_name == "consequence":
                visit(c, nesting + 1)         # elif body gets +nesting
            elif c.is_named:
                visit(c, nesting)             # condition
            if not cur.goto_next_sibling():
                break

    def visit_else(node, nesting):
        nonlocal total
        p = node.parent
        # A valid if-like parent for else = if (including Ruby unless) or elsif
        # (Ruby's else may have an elsif parent); otherwise (else on a for/while/
        # try/begin/case) -> transparent (Py for-else, Ruby case-else, etc.).
        if p is not None and p.type not in if_types and p.type not in elif_t:
            for c in node.children:
                visit(c, nesting)
            return
        inner_if = next((c for c in node.children if c.type in if_types), None)
        if inner_if is not None:              # else-if (flattened: sibling level, no B3; Rust=if_expression)
            visit_if(inner_if, nesting, as_elseif=True)
        else:                                 # plain else: +1, body gets +nesting (block or unbraced single statement, either way)
            total += 1
            for c in node.children:
                if c.is_named:
                    visit(c, nesting + 1)

    def _unwrap_elseif(node):
        # Is the alternative field an else-if? Go/Java/C# point directly at if;
        # Kotlin's else-if is a control_structure_body wrapping a single
        # if_expression adds an extra wrapper layer that must be unwrapped.
        # to get the inner if. control_structure_body is a Kotlin-only node type
        # that Go/Java/C# never produce -> zero effect on them.
        if node.type in if_types:
            return node
        if node.type == "control_structure_body":
            named = [c for c in node.children if c.is_named]
            if len(named) == 1 and named[0].type in if_types:
                return named[0]
        return None

    def visit_if_field(node, nesting, as_elseif):
        # field-style else-if (Go/Java/C#/Kotlin): the if's "alternative" field
        # points at an if (else-if) or a block (plain else), with no
        # else_clause/elif_clause wrapper. Uses the "consequence"/"alternative"
        # field names to distinguish then from else.
        nonlocal total
        total += 1 if as_elseif else (1 + nesting)
        cur = node.walk()
        if not cur.goto_first_child():
            return
        while True:
            child = cur.node
            fld = cur.field_name
            if fld == "consequence":
                visit(child, nesting + 1)             # then body gets +nesting
            elif fld == "alternative":
                inner_if = _unwrap_elseif(child)
                if inner_if is not None:              # else-if: sibling level, +1, no B3
                    visit_if_field(inner_if, nesting, as_elseif=True)
                else:                                 # plain else (block or unbraced single statement): body gets +nesting
                    total += 1                        # Go/Java/C# allow a braceless `else stmt;`, which still needs +1
                    visit(child, nesting + 1)
            elif child.is_named:
                visit(child, nesting)                 # condition / initializer (catches boolean run / recursion)
            if not cur.goto_next_sibling():
                break

    def visit_if_swift(node, nesting, as_elseif):
        # Swift-specific: the then-body is an unfielded "statements" node, else
        # is a marker token node, and the else-if/plain-else body is a sibling
        # of else. The seen_else flag distinguishes
        # then-body from else-body.
        nonlocal total
        total += 1 if as_elseif else (1 + nesting)
        seen_else = False
        for c in node.children:
            if c.type in else_t:                       # else marker (type "else")
                seen_else = True
                continue
            if not c.is_named:
                continue
            if not seen_else:
                if c.type == "statements":             # then-body (unfielded) gets +nesting
                    visit(c, nesting + 1)
                else:                                  # condition / other (boolean run / recursion)
                    visit(c, nesting)
            elif c.type in if_types:                   # else-if (sibling level, +1, no B3)
                visit_if_swift(c, nesting, as_elseif=True)
            else:                                      # plain else body (statements): +1, body gets +nesting
                total += 1
                visit(c, nesting + 1)

    def visit(node, nesting):
        nonlocal total
        t = node.type
        if _dbg:
            sys.stderr.write(f"[cog] {'. ' * nesting}{t} n={nesting} tot_in={total}\n")

        if not node.is_named:
            # A keyword token's type can collide with a node type (Ruby's
            # while/until/for/case/unless/if keyword tokens have type
            # while/until/... = the same as the control-flow node types) ->
            # must not be scored, or incr_nest/if_types would double-+1 the token.
            # symbols.py's walk() (v0.11.0) hit the same pitfall with the same
            # fix (filter by is_named).
            return

        if t in if_types:
            p = node.parent
            if if_style == "field":
                # field-style (Go/Java/C#/Kotlin): the inner if of an else-if is the
                # parent if's "alternative" -> already handled by visit_if_field
                if p is not None and p.type in if_types:
                    return
                visit_if_field(node, nesting, as_elseif=False)
            elif if_style == "swift":
                # Swift: the inner if_statement of an else-if is a direct child of
                # the outer if_statement (a sibling of else) -> when the parent is
                # an if_statement it was already handled by visit_if_swift, so skip
                # (a genuinely nested if's parent is "statements", not skipped)
                if p is not None and p.type in if_types:
                    return
                visit_if_swift(node, nesting, as_elseif=False)
            else:
                # wrapper-style (Py/TS/JS/TSX/Rust/C/C++/Ruby): the inner if of an
                # else-if lives inside else_clause/elsif -> already handled by visit_else
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
                # A loop's else is at sibling level and does not inherit the loop body's nesting.
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
                    # Kotlin/Swift: &&/|| are distinct node types, use is_bool_root to
                    # find the outermost one (walks up ancestors to avoid double-counting)
                    if is_bool_root(node):
                        total += count_bool_runs(node)
                else:
                    p = node.parent
                    if not (p is not None and is_logical(p)):
                        total += count_bool_runs(node)   # only counted once, at the outermost logical node
            for c in node.children:
                visit(c, nesting)
            return
        if t in labeled_jump:
            if is_labeled(node):
                total += 1
            # Still visits children: Kotlin's jump_expression / Swift's
            # control_transfer_statement uniformly cover return too, and its value
            # expression (the recursive call in `return f(n-1)`, the ternary in
            # `return x>0?1:0`) must still be counted - skipping non-return jumps
            # would undercount.
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
        # Extremely deep generated code can exhaust the Python stack. Return UNKNOWN
        # instead of failing the file's entire fingerprint pass.
        return None
    return total
