"""Pure-function tests for the cognitive complexity walker, covering algorithm
correctness including the golden sumOfPrimes=7 case.

Deterministic ground truth. The algorithm is proven right first, and only then
wired up to persist scores. Every expected value below was worked out by hand.
"""
import os
import sys

import pytest
import tree_sitter

CS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CS not in sys.path:
    sys.path.insert(0, CS)

from codesextant import complexity, symbols  # noqa: E402

_FUNC_TYPES = {"function_definition", "function_declaration", "method_definition",
               "method_declaration", "function_item",  # function_item=Rust
               "method", "singleton_method"}            # Ruby def and def self.x


def _func_name(fn, sb: bytes) -> str | None:
    """Get the function's name, which recursion detection needs. The name field
    wins; C and C++ walk the declarator chain; Kotlin uses simple_identifier."""
    nn = fn.child_by_field_name("name")
    if nn is not None:
        return sb[nn.start_byte:nn.end_byte].decode()
    decl = fn.child_by_field_name("declarator")          # C/C++: function_declarator > identifier
    while decl is not None:
        if decl.type == "identifier":
            return sb[decl.start_byte:decl.end_byte].decode()
        decl = decl.child_by_field_name("declarator")
    for c in fn.children:                                 # Kotlin: the first simple_identifier child
        if c.type == "simple_identifier":
            return sb[c.start_byte:c.end_byte].decode()
    return None


def cc(src: str, lang: str) -> int | None:
    """Parse a source snippet holding one top-level function and score the
    cognitive complexity of its body."""
    sb = src.encode("utf-8")
    parser = tree_sitter.Parser(symbols._ts_language(lang))
    tree = parser.parse(sb)
    found = []

    def rec(n):
        if n.type in _FUNC_TYPES:
            found.append(n)
            return  # take the outermost function and do not descend into nested ones
        for c in n.children:
            rec(c)

    rec(tree.root_node)
    assert found, f"no function found in the {lang} snippet"
    fn = found[0]
    body = complexity.function_body(fn, lang)            # Kotlin has no body field, so this falls back
    name = _func_name(fn, sb)
    return complexity.cognitive_complexity(body, lang, name, sb)


# The golden case from the original white paper, which the industry agrees on.
def test_golden_sum_of_primes_ts():
    src = """
function sumOfPrimes(max) {
    let total = 0;
    OUT: for (let i = 1; i <= max; i++) {
        for (let j = 2; j < i; j++) {
            if (i % j === 0) {
                continue OUT;
            }
        }
        total += i;
    }
    return total;
}
"""
    # for +1 / for +2(n1) / if +3(n2) / continue LABEL +1 = 7
    assert cc(src, "typescript") == 7


# The basics. A simple function scores 0, so clean code never gets penalized.
def test_trivial_zero():
    assert cc("def f(x):\n    y = x + 1\n    return y\n", "python") == 0


# A nested if picks up the nesting increment.
def test_nested_if_python():
    src = "def f(a, b):\n    if a:\n        if b:\n            pass\n"
    assert cc(src, "python") == 3  # if +1 / if +1+1=2


# An else-if chain: each branch scores +1 with no nesting accumulation, which is
# what stops the same construct from being counted twice.
def test_elif_chain_python():
    src = ("def f(x):\n"
           "    if x == 1:\n        pass\n"
           "    elif x == 2:\n        pass\n"
           "    elif x == 3:\n        pass\n"
           "    else:\n        pass\n")
    assert cc(src, "python") == 4  # 4 branches at +1 each, no nesting increment


def test_elif_chain_with_nested_body_python():
    src = ("def f(x):\n"
           "    if x == 1:\n        pass\n"
           "    elif x == 2:\n        for i in x:\n            pass\n")
    assert cc(src, "python") == 4  # if +1 / elif +1 / for +1+1=2, since the for sits at n=1


def test_elseif_chain_ts_no_nesting_accumulation():
    src = """
function f(x) {
    if (x === 1) {}
    else if (x === 2) {}
    else if (x === 3) {
        for (const i of x) {}
    }
}
"""
    # if +1 / else-if +1 / else-if +1 / for +1+1=2. The for sits at n=1 inside the
    # third branch, and the else-if chain itself does not deepen the nesting.
    assert cc(src, "typescript") == 5


# Boolean operator sequences: each run scores +1.
def test_boolean_runs_python():
    src = ("def f(a, b, c):\n"
           "    if a and b:\n        pass\n"
           "    if a and b or c:\n        pass\n")
    assert cc(src, "python") == 5  # if+1 + (and run=1) ; if+1 + (and|or=2 runs)


def test_boolean_runs_ts():
    src = """
function f(a, b, c, d) {
    if (a && b && c) { return 1; }
    if (a && b || c && d) { return 2; }
    return 0;
}
"""
    # if+1+(&& run=1)=2 ; if+1+(&&|| | && =3 runs)=4 → 6
    assert cc(src, "typescript") == 6


# Direct recursion scores +1.
def test_recursion_python():
    src = ("def fact(n):\n"
           "    if n <= 1:\n        return 1\n"
           "    return n * fact(n - 1)\n")
    assert cc(src, "python") == 2  # if +1 / recursion +1


# A switch scores +1 as a whole and its cases do not each add. This is where
# cognitive complexity parts ways with cyclomatic complexity.
def test_switch_counts_once_ts():
    src = """
function f(x) {
    switch (x) {
        case 1: return 1;
        case 2: return 2;
        default: return 0;
    }
}
"""
    assert cc(src, "typescript") == 1  # switch +1, and the 3 cases add nothing


def test_switch_nested_ts():
    src = """
function f(x) {
    if (x > 0) {
        switch (x) {
            case 1: break;
        }
    }
}
"""
    assert cc(src, "typescript") == 3  # if +1 / switch +1+1=2


# A nested function or lambda deepens the nesting, making control flow inside it
# more expensive, while the declaration itself scores nothing.
def test_nested_function_adds_nesting_python():
    src = ("def f(items):\n"
           "    def inner(x):\n"
           "        if x:\n            return 1\n"
           "        return 0\n"
           "    return inner\n")
    assert cc(src, "python") == 2  # inner scores 0 but deepens / the if inside +1+1=2


# A ternary takes the nesting increment and is weighted when nested.
def test_ternary_python():
    assert cc("def f(x):\n    return 1 if x else 2\n", "python") == 1


def test_nested_ternary_python():
    src = "def f(x, y):\n    return 1 if x else (2 if y else 3)\n"
    assert cc(src, "python") == 3  # outer +1 / inner +1+1=2


# try/except/finally: try and finally are transparent, except scores and deepens
# the nesting, and a try-else scores nothing.
def test_try_except_else_finally_python():
    src = ("def f(x):\n"
           "    try:\n        pass\n"
           "    except ValueError:\n        pass\n"
           "    else:\n        pass\n"
           "    finally:\n        pass\n")
    assert cc(src, "python") == 1  # only except scores; try, finally and try-else do not


def test_except_adds_nesting_python():
    src = ("def f(x):\n"
           "    try:\n        pass\n"
           "    except ValueError:\n        if x:\n            pass\n")
    assert cc(src, "python") == 3  # except +1 / the if inside +1+1=2


# Languages still marked UNKNOWN return None. Thirteen languages are scored with
# high confidence; lua, php and bash degrade honestly instead of reporting 0,
# which would read as clean code.
def test_remaining_unknown_none():
    # the control-flow grammars for lua, php and bash have not been verified, so
    # cognitive comes back None rather than a flattering score.
    # Symbol extraction already supports these languages and their function nodes
    # parse fine. What is missing is the cognitive spec, which proves the gap is
    # "language not supported yet" rather than a problem reading the body.
    assert cc("function f(x)\n  if x > 0 then\n    return 1\n  end\n  return 0\nend\n", "lua") is None
    assert cc("<?php\nfunction f($x) {\n  if ($x > 0) { return 1; }\n  return 0;\n}\n", "php") is None


def test_supported_set():
    # the original 4 high-confidence languages
    assert complexity.supported("python")
    assert complexity.supported("typescript")
    assert complexity.supported("tsx")
    assert complexity.supported("javascript")
    # the next 4 added
    assert complexity.supported("go")
    assert complexity.supported("rust")
    assert complexity.supported("java")
    assert complexity.supported("csharp")
    # and the 5 added after that
    assert complexity.supported("c")
    assert complexity.supported("cpp")
    assert complexity.supported("ruby")
    assert complexity.supported("kotlin")
    assert complexity.supported("swift")
    # still UNKNOWN: symbols work, but no cognitive spec has been written
    assert not complexity.supported("lua")
    assert not complexity.supported("php")
    assert not complexity.supported("bash")


# ════════════════════════════════════════════════════════════
# Golden cases for the Go, Java, C# and Rust expansion. Every expected value
# below was worked out by hand.
# ════════════════════════════════════════════════════════════

# The white paper's sumOfPrimes=7 case, once per language:
# for+1 / for+2(n1) / if+3(n2) / labeled continue+1.
def test_golden_sum_of_primes_go():
    src = ("package m\n"
           "func sumOfPrimes(max int) int {\n"
           "\ttotal := 0\n"
           "OUT:\n"
           "\tfor i := 2; i <= max; i++ {\n"
           "\t\tfor j := 2; j < i; j++ {\n"
           "\t\t\tif i%j == 0 {\n"
           "\t\t\t\tcontinue OUT\n"
           "\t\t\t}\n"
           "\t\t}\n"
           "\t\ttotal += i\n"
           "\t}\n"
           "\treturn total\n}\n")
    assert cc(src, "go") == 7


def test_golden_sum_of_primes_java():
    src = ("class C {\n"
           "    int sumOfPrimes(int max) {\n"
           "        int total = 0;\n"
           "        OUT:\n"
           "        for (int i = 2; i <= max; i++) {\n"
           "            for (int j = 2; j < i; j++) {\n"
           "                if (i % j == 0) {\n"
           "                    continue OUT;\n"
           "                }\n"
           "            }\n"
           "            total += i;\n"
           "        }\n"
           "        return total;\n    }\n}\n")
    assert cc(src, "java") == 7


def test_golden_sum_of_primes_rust():
    src = ("fn sum_of_primes(max: i32) -> i32 {\n"
           "    let mut total = 0;\n"
           "    'outer: for i in 2..max {\n"
           "        for j in 2..i {\n"
           "            if i % j == 0 {\n"
           "                continue 'outer;\n"
           "            }\n"
           "        }\n"
           "        total += i;\n"
           "    }\n"
           "    total\n}\n")
    assert cc(src, "rust") == 7


# Field-style else-if in Go, Java and C#: a nested if takes the nesting
# increment, an else-if does not, and a plain else still scores +1.
# if x>0(+1) / nested if x>10(+1 plus nesting 1 = +2) / nested else(+1) /
# else-if x<0(+1, no nesting) / else(+1) = 6
_ELSEIF_GO = ("package m\n"
              "func classify(x int) int {\n"
              "\tif x > 0 {\n"
              "\t\tif x > 10 {\n\t\t\treturn 2\n\t\t} else {\n\t\t\treturn 1\n\t\t}\n"
              "\t} else if x < 0 {\n\t\treturn -1\n\t} else {\n\t\treturn 0\n\t}\n}\n")
_ELSEIF_JAVA = ("class C {\n  int classify(int x) {\n"
                "    if (x > 0) {\n      if (x > 10) { return 2; } else { return 1; }\n"
                "    } else if (x < 0) { return -1; } else { return 0; }\n  }\n}\n")
_ELSEIF_CS = ("class C {\n  int Classify(int x) {\n"
              "    if (x > 0) {\n      if (x > 10) { return 2; } else { return 1; }\n"
              "    } else if (x < 0) { return -1; } else { return 0; }\n  }\n}\n")


def test_field_elseif_go():
    assert cc(_ELSEIF_GO, "go") == 6


def test_field_elseif_java():
    assert cc(_ELSEIF_JAVA, "java") == 6


def test_field_elseif_csharp():
    assert cc(_ELSEIF_CS, "csharp") == 6


# Java switch_expression plus ternary, do-while and catch = 4. try and finally
# are transparent, and the cases do not each add.
def test_java_switch_ternary_do_catch():
    src = ("class C {\n  int h(int x) {\n"
           "    switch (x) { case 1: break; default: break; }\n"   # +1
           "    int y = x > 0 ? 1 : 0;\n"                          # ternary +1
           "    do { x--; } while (x > 0);\n"                      # do +1
           "    try { g(); } catch (Exception e) { x = 0; } finally { }\n"  # catch +1
           "    return y;\n  }\n}\n")
    assert cc(src, "java") == 4


# C# switch_statement plus conditional_expression, do and catch = 4.
def test_csharp_switch_conditional_do_catch():
    src = ("class C {\n  int H(int x) {\n"
           "    switch (x) { case 1: break; default: break; }\n"   # +1
           "    int y = x > 0 ? 1 : 0;\n"                          # conditional +1
           "    do { x--; } while (x > 0);\n"                      # do +1
           "    try { G(); } catch (System.Exception e) { x = 0; } finally { }\n"  # catch +1
           "    return y;\n  }\n}\n")
    assert cc(src, "csharp") == 4


# Rust match plus loop and a nested while = 4. match and loop sit at n0, while
# the while inside the loop sits at n1 and takes the nesting increment.
def test_rust_match_loop_while():
    src = ("fn k(x: i32) -> i32 {\n"
           "    match x {\n        1 => {},\n        _ => {},\n    }\n"   # match +1
           "    loop {\n"                                                 # loop +1 (n0)
           "        while x > 0 {\n            break;\n        }\n"        # while +1+nesting(1)=+2 (n1)
           "        break;\n    }\n"
           "    x\n}\n")
    assert cc(src, "rust") == 4


# Go switch plus a boolean run = 5: switch+1, nested if+2, and a&&b||c is 2 runs.
def test_go_switch_boolean():
    src = ("package m\n"
           "func g(x int) int {\n"
           "\tswitch x {\n\tcase 1:\n\t\tif x > 0 {\n\t\t}\n\tdefault:\n\t}\n"  # switch+1, nested if+2
           "\ty := x > 0 && x < 10 || x == 0\n\t_ = y\n"                        # boolean 2 runs
           "\treturn 0\n}\n")
    assert cc(src, "go") == 5


# A bare recursive call scores +1 each time the function calls itself.
def test_recursion_go():
    src = ("package m\n"
           "func fib(n int) int {\n"
           "\tif n < 2 {\n\t\treturn n\n\t}\n"            # if +1
           "\treturn fib(n-1) + fib(n-2)\n}\n")           # 2 recursive calls, +2
    assert cc(src, "go") == 3


def test_recursion_rust():
    src = ("fn fib(n: i32) -> i32 {\n"
           "    if n < 2 {\n        return n;\n    }\n"     # if +1
           "    fib(n - 1) + fib(n - 2)\n}\n")             # 2 recursive calls, +2
    assert cc(src, "rust") == 3


# Calling a same-named method on another object is not recursion. In Java,
# other.f() inside a method named f does not count.
def test_no_false_recursion_java():
    src = ("class C {\n  int f(int x) {\n"
           "    return other.f(x);\n  }\n}\n")   # other.f() is not recursion, so 0
    assert cc(src, "java") == 0


# Field-style else with no braces, which Go, Java and C# allow as `else stmt;`.
# A plain else still scores +1, so nothing goes uncounted.
def test_field_no_brace_else():
    # if(+1) + plain else(+1) = 2
    assert cc("class C{ int f(int x){ if(x>0) return 1; else return 0; } }", "java") == 2
    assert cc("class C{ int F(int x){ if(x>0) return 1; else return 0; } }", "csharp") == 2
    # brace-less else-if chain: if(+1) / else-if(+1, no nesting) / else(+1) = 3
    assert cc("class C{ int f(int x){ if(x>0) return 1; else if(x<0) return -1; else return 0; } }",
              "java") == 3


# A trivial function scores 0 in every language, so clean code stays clean.
def test_trivial_zero_p4():
    assert cc("package m\nfunc f(x int) int {\n\ty := x + 1\n\treturn y\n}\n", "go") == 0
    assert cc("fn f(x: i32) -> i32 {\n    let y = x + 1;\n    y\n}\n", "rust") == 0
    assert cc("class C {\n  int f(int x) {\n    int y = x + 1;\n    return y;\n  }\n}\n", "java") == 0
    assert cc("class C {\n  int F(int x) {\n    int y = x + 1;\n    return y;\n  }\n}\n", "csharp") == 0


# ════════════════════════════════════════════════════════════
# Regressions for fixes that came out of an adversarial review, where five
# reviewers worked through the arithmetic independently.
# ════════════════════════════════════════════════════════════

# A C# switch expression, `x switch {}`, has to score. It used to be missed
# entirely, because its node type is switch_expression, not switch_statement.
def test_csharp_switch_expression():
    # if(+1) + switch expr(+1) = 2. This used to come back as 1.
    assert cc("class C{ int M(int x){ if(x>0) return 1; return x switch { 1=>10, _=>0 }; } }",
              "csharp") == 2
    # a ternary inside a switch arm is weighted by nesting: switch_expr(+1 at n0)
    # plus the ternary at n1(+1 plus nesting = 2) = 3. This used to come back as 1.
    assert cc("class C{ int M(int x,int y){ return x switch { 1 => y>0?10:20, _=>0 }; } }",
              "csharp") == 3


# Across languages, a wrapper-style then or else without braces still deepens the
# nesting. Braced and brace-less code scoring the same closes off a way to game
# the metric by deleting braces.
def test_braceless_body_increments_nesting():
    braced = "function f(a,b,c){ if(a){ if(b){ if(c){} } } }"
    braceless = "function f(a,b,c){ if(a) if(b) if(c) {} }"
    assert cc(braced, "typescript") == 6
    assert cc(braceless, "typescript") == 6        # same score; this used to be 3
    assert cc("function f(x){ if(x) for(let i=0;i<x;i++){} }", "typescript") == 3        # used to be 2
    assert cc("function f(a){ if(a){} else for(let i=0;i<1;i++){} }", "typescript") == 4  # used to be 3
    # Python always uses blocks, so its grammar was never affected and stays right
    assert cc("def f(a,b):\n    if a:\n        if b:\n            pass\n", "python") == 3


# The feature is switchable.
def test_disable_switch(monkeypatch):
    monkeypatch.setenv("CODESEXTANT_COGNITIVE_DISABLED", "1")
    assert cc("def f(x):\n    if x:\n        pass\n", "python") is None


# Resistance to gaming: split a complex function into several tight small ones
# and each of them scores low, which is the honest outcome.
def test_game_resistance_small_functions_stay_low():
    # each extracted function holds one if, so cognitive=1 and health stays high
    for src in ("def a(x):\n    if x:\n        return 1\n    return 0\n",
                "def b(x):\n    if x:\n        return 2\n    return 0\n"):
        assert cc(src, "python") == 1


# ════════════ Regression locks from adversarial review. The expected values are
# the counterexamples the reviewers actually ran. ════════════

def test_nullish_not_counted_ts():
    # the white paper says outright to ignore null-coalescing, so ?? scores nothing
    assert cc("function f(a, b) { return a ?? b; }", "typescript") == 0
    assert cc("function f(a, b, c) { return a ?? b ?? c; }", "typescript") == 0
    # ?? still scores nothing, while a real && beside it counts normally
    assert cc("function f(a, b, c) { if (a && (b ?? c)) return 1; return 0; }",
              "typescript") == 2  # if+1 + && run 1


def test_recursion_attr_same_name_not_counted():
    # obj.foo() inside a function named foo is not recursion; review tightened this
    assert cc("def foo(obj):\n    return obj.foo()\n", "python") == 0
    assert cc("function save(repo) { return repo.save(); }", "typescript") == 0
    # self.foo() and this.foo() are genuine recursion
    assert cc("def foo(self):\n    if self.x:\n        return self.foo()\n    return 0\n",
              "python") == 2  # if+1 + self recursion+1
    # a bare-name recursive call still counts; tightening did not break it
    assert cc("def f(n):\n    return f(n - 1)\n", "python") == 1


def test_for_else_no_extra_nesting():
    # the else body of a for-else does not inherit the loop's nesting depth
    src = ("def f(xs, x):\n"
           "    for v in xs:\n"
           "        if v:\n            break\n"
           "    else:\n"
           "        if x:\n            pass\n")
    # for+1 / inner if+1+1=2 / unlabeled break 0 / else transparent / if in else +1 at n=0
    assert cc(src, "python") == 4


def test_nested_comprehension_sibling_for():
    # two for clauses in one comprehension are siblings in the AST, so the second
    # does not accumulate nesting. The tests state this rather than hide it.
    assert cc("def f(b):\n    return [x for a in b for x in a]\n", "python") == 2  # +1 each


# The schema migration contract: an ALTER that adds a column leaves existing rows intact.
def test_migration_adds_cognitive_to_old_db(tmp_path):
    import sqlite3

    from codesextant import storage
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE fingerprints(path TEXT, name TEXT, node_count INTEGER)")
    conn.execute("INSERT INTO fingerprints VALUES('a.py', 'foo', 10)")
    conn.commit()
    conn.close()
    conn = sqlite3.connect(str(db))
    storage._ensure_columns(conn)  # the migration hook
    cols = {r[1] for r in conn.execute("PRAGMA table_info(fingerprints)").fetchall()}
    assert "cognitive" in cols  # the new column was added
    row = conn.execute("SELECT name, node_count, cognitive FROM fingerprints").fetchone()
    assert row[0] == "foo" and row[1] == 10 and row[2] is None  # old row intact, new column NULL
    conn.close()


# On the code_health side, a cognitive of None renormalizes properly rather than
# quietly turning into a perfect score.
def test_code_health_none_cog_renormalize(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "dbs"))
    poc = os.path.join(CS, "_poc_graph_c")
    if poc not in sys.path:
        sys.path.insert(0, poc)
    import code_health

    from codesextant import storage
    repo = str(tmp_path / "repo")
    os.makedirs(repo, exist_ok=True)
    ap = os.path.join(repo, "a.py")
    with storage.ProjectStore.open(repo) as store:
        store.conn.execute("INSERT INTO files(path,content_hash,indexed_at) VALUES(?,?,?)",
                           (ap, "h", 0.0))
        store.conn.commit()
        store.store_file_fingerprints(ap, [{
            "name": "f", "kind": "function", "line": 1, "end_line": 9, "node_count": 300,
            "shape_hash": "uniq", "raw_token_hash": "r", "call_hash": None, "nstmts": 5,
            "has_control_flow": True, "cognitive": None, "winnow": [],
        }], [])
    nodes = [{"name": "f", "file": "a.py", "line": 1}]
    code_health.compute(repo, nodes)
    h = nodes[0]["health"]
    # cognitive=None drops that axis. What remains, bloat at full 1 and dup at 0,
    # renormalizes to penalty = 0.25/(0.25+0.30), roughly 0.45.
    # The point: None is neither treated as a perfect health of 1 nor poured into
    # the denominator as if it were cognitive=0.
    assert h is not None and 0.4 < h < 0.65


# End-to-end integration through engine.get_health: the health calculation is
# wired back into the real engine, and a complex function scores lower than a
# simple one.
def test_get_health_integration(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "dbs"))
    from codesextant import engine
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "m.py").write_text(
        "def simple(x):\n    return x + 1\n\n"
        "def complex_fn(items):\n"
        "    t = 0\n"
        "    for a in items:\n"
        "        for b in a:\n"
        "            if b > 0:\n"
        "                if b > 10:\n"
        "                    t += b\n"
        "    return t\n", encoding="utf-8")
    engine.index_project(str(repo), force=True)
    r = engine.get_health(str(repo))
    assert "symbols" in r and "summary" in r and "root" in r
    by_name = {s["name"]: s for s in r["symbols"]}
    # deeply nested complex_fn scores high cognitive and therefore low health,
    # while simple sits at cognitive 0 and keeps its health high
    assert by_name["complex_fn"]["health"] is not None
    assert by_name["simple"]["health"] is not None
    assert by_name["complex_fn"]["health"] < by_name["simple"]["health"]


# End to end for Go, Rust, Java and C#: cognitive scores really land in the
# fingerprints table, which proves lang_key resolves to a spec and that symbol
# extraction hands over the function nodes.
def test_p4_cognitive_persisted_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "dbs"))
    from codesextant import engine, storage
    repo = tmp_path / "repo"
    repo.mkdir()
    # one complex function per language: for+1 / for+2(n1) / if+3(n2) = 6 with nesting
    (repo / "m.go").write_text(
        "package m\nfunc complexGo(items [][]int) int {\n\tt := 0\n"
        "\tfor _, a := range items {\n\t\tfor _, b := range a {\n"
        "\t\t\tif b > 0 {\n\t\t\t\tt += b\n\t\t\t}\n\t\t}\n\t}\n\treturn t\n}\n",
        encoding="utf-8")
    (repo / "m.rs").write_text(
        "fn complex_rust(items: Vec<Vec<i32>>) -> i32 {\n    let mut t = 0;\n"
        "    for a in &items {\n        for b in a {\n            if *b > 0 {\n"
        "                t += b;\n            }\n        }\n    }\n    t\n}\n",
        encoding="utf-8")
    (repo / "M.java").write_text(
        "class M {\n  int complexJava(int[][] items) {\n    int t = 0;\n"
        "    for (int[] a : items) {\n      for (int b : a) {\n        if (b > 0) {\n"
        "          t += b;\n        }\n      }\n    }\n    return t;\n  }\n}\n",
        encoding="utf-8")
    (repo / "M.cs").write_text(
        "class M {\n  int ComplexCs(int[][] items) {\n    int t = 0;\n"
        "    foreach (var a in items) {\n      foreach (var b in a) {\n        if (b > 0) {\n"
        "          t += b;\n        }\n      }\n    }\n    return t;\n  }\n}\n",
        encoding="utf-8")
    engine.index_project(str(repo), force=True)
    with storage.ProjectStore.open(str(repo)) as store:
        rows = dict(store.conn.execute("SELECT name, cognitive FROM fingerprints").fetchall())
    # all four score 6 and land as real values rather than NULL, which means the
    # whole chain is connected: lang_key to spec, symbol extraction, and body field
    assert rows.get("complexGo") == 6, f"Go stored {rows.get('complexGo')}, expected 6"
    assert rows.get("complex_rust") == 6, f"Rust stored {rows.get('complex_rust')}, expected 6"
    assert rows.get("complexJava") == 6, f"Java stored {rows.get('complexJava')}, expected 6"
    assert rows.get("ComplexCs") == 6, f"C# stored {rows.get('ComplexCs')}, expected 6"


# ════════════════════════════════════════════════════════════
# Golden cases for the C, C++, Ruby, Kotlin and Swift expansion, checked with
# tools/_smoke_p5.py. Every expected value was worked out by hand.
# ════════════════════════════════════════════════════════════
# For the sumOfPrimes=7 case, C and C++ use goto (for+1/for+2/if+3/goto+1) and
# Kotlin and Swift use a labeled continue. Ruby has no labeled jump at all, since
# next, break and redo only ever jump to the innermost loop, so the Ruby version
# uses an idiomatic combination of control flow, scored by hand.
_P5_CASES = [
    # C: wrapper-style, a labeled goto, no try, and a conditional ternary
    ("c", "sumOfPrimes-goto",
     "int s(int max){int t=0;for(int i=2;i<=max;i++){for(int j=2;j<i;j++){if(i%j==0){goto next;}}t+=i;next:;}return t;}", 7),
    ("c", "trivial", "int f(int x){int y=x+1;return y;}", 0),
    ("c", "if-elseif-else", "int f(int x){if(x>0)return 1;else if(x<0)return -1;else return 0;}", 3),
    ("c", "nested-if", "int f(int a,int b){if(a){if(b){return 1;}}return 0;}", 3),
    ("c", "switch", "int f(int x){switch(x){case 1:return 1;default:return 0;}}", 1),
    ("c", "while+do", "int f(int x){while(x>0){x--;}do{x++;}while(x<0);return x;}", 2),
    ("c", "boolean-2run", "int f(int a,int b,int c){if(a&&b||c){return 1;}return 0;}", 3),
    ("c", "ternary", "int f(int x){return x>0?1:0;}", 1),
    ("c", "recursion-fib", "int fib(int n){if(n<2){return n;}return fib(n-1)+fib(n-2);}", 3),
    # C++: everything C has, plus try/catch, a lambda and a range-for
    ("cpp", "sumOfPrimes-goto",
     "int s(int max){int t=0;for(int i=2;i<=max;i++){for(int j=2;j<i;j++){if(i%j==0){goto next;}}t+=i;next:;}return t;}", 7),
    ("cpp", "try-catch", "int f(){try{g();}catch(std::exception&e){h();}return 0;}", 1),
    ("cpp", "range-for", "int f(std::vector<int>v){int t=0;for(auto&x:v){t+=x;}return t;}", 1),
    ("cpp", "lambda-nest", "int f(int x){auto g=[](int q){if(q>0){return q;}return 0;};return g(x);}", 2),
    # Ruby: the if node type is if, plus case/when, while/until, unless, rescue,
    # if_modifier, and a callee of method
    ("ruby", "for-for-if",
     "def s(max)\n  t=0\n  for i in 2..max\n    for j in 2...i\n      if i%j==0\n        t+=1\n      end\n    end\n  end\n  t\nend\n", 6),
    ("ruby", "trivial", "def f(x)\n  y=x+1\n  y\nend\n", 0),
    ("ruby", "if-elsif-else", "def f(x)\n  if x>0\n    1\n  elsif x<0\n    2\n  else\n    3\n  end\nend\n", 3),
    ("ruby", "case-when", "def f(x)\n  case x\n  when 1 then 1\n  when 2 then 2\n  else 0\n  end\nend\n", 1),
    ("ruby", "while+until", "def f(x)\n  while x>0\n    x-=1\n  end\n  until x<0\n    x-=1\n  end\nend\n", 2),
    ("ruby", "unless", "def f(x)\n  unless x>0\n    a\n  end\nend\n", 1),
    ("ruby", "if-modifier", "def f(x)\n  a=1 if x>0\nend\n", 1),
    ("ruby", "rescue", "def f(x)\n  begin\n    risky\n  rescue StandardError=>e\n    handle\n  ensure\n    cleanup\n  end\nend\n", 1),
    ("ruby", "boolean-2run", "def f(a,b,c)\n  if a && b || c\n    1\n  end\nend\n", 3),
    ("ruby", "recursion", "def f(n)\n  f(n-1)\nend\n", 1),
    ("ruby", "no-false-recursion", "def f(o)\n  o.f\nend\n", 0),
    ("ruby", "each-block-nest", "def f(xs)\n  xs.each do |i|\n    if i>0\n      i\n    end\n  end\nend\n", 2),
    # Kotlin: field-style if, when, a function_body with no field, && and ||
    # spanning two node types, the callee fallback, and jump_expression
    ("kotlin", "sumOfPrimes-labeled",
     "fun s(max:Int):Int{var t=0\nouter@ for(i in 2..max){for(j in 2 until i){if(i%j==0){continue@outer}}\nt+=i}\nreturn t}", 7),
    ("kotlin", "trivial", "fun f(x:Int):Int{val y=x+1\nreturn y}", 0),
    ("kotlin", "when", "fun f(x:Int){when(x){1->println(1)\nelse->println(0)}}", 1),
    ("kotlin", "if-elseif-else-field", "fun f(x:Int):Int{if(x>0)return 1 else if(x<0)return -1 else return 0}", 3),
    ("kotlin", "while+dowhile", "fun f(x:Int){var y=x\nwhile(y>0){y--}\ndo{y++}while(y<0)}", 2),
    ("kotlin", "try-catch", "fun f(){try{risky()}catch(e:Exception){handle()}finally{cleanup()}}", 1),
    ("kotlin", "boolean-2run", "fun f(a:Boolean,b:Boolean,c:Boolean){val y=a&&b||c}", 2),
    ("kotlin", "recursion", "fun f(n:Int):Int{return f(n-1)}", 1),
    ("kotlin", "nested-if-field", "fun f(a:Boolean,b:Boolean){if(a){if(b){println(1)}}}", 3),
    # Swift: its own if form, guard, switch, repeat-while, do/catch, a ternary,
    # and a labeled control_transfer
    ("swift", "sumOfPrimes-labeled",
     "func s(_ max:Int)->Int{var t=0\nouter: for i in 2...max{for j in 2..<i{if i%j==0{continue outer}}\nt+=i}\nreturn t}", 7),
    ("swift", "trivial", "func f(x:Int)->Int{let y=x+1\nreturn y}", 0),
    ("swift", "switch", "func f(x:Int){switch x{case 1:print(1)\ndefault:print(0)}}", 1),
    ("swift", "guard", "func f(x:Int)->Int{guard x>0 else{return 0}\nreturn x}", 1),
    ("swift", "if-elseif-else-swift", "func f(x:Int)->Int{if x>0{return 1}else if x<0{return -1}else{return 0}}", 3),
    ("swift", "while+repeat", "func f(x:Int){var y=x\nwhile y>0{y-=1}\nrepeat{y+=1}while y<0}", 2),
    ("swift", "do-catch", "func f(){do{try risky()}catch{handle()}}", 1),
    ("swift", "ternary", "func f(x:Int)->Int{return x>0 ?1:0}", 1),
    ("swift", "recursion", "func f(n:Int)->Int{return f(n-1)}", 1),
    ("swift", "nested-if-swift", "func f(a:Bool,b:Bool){if a{if b{print(1)}}}", 3),
]


@pytest.mark.parametrize("lang,label,src,expected", _P5_CASES,
                         ids=[f"{c[0]}-{c[1]}" for c in _P5_CASES])
def test_p5_golden(lang, label, src, expected):
    assert cc(src, lang) == expected, f"{lang} {label}: got {cc(src, lang)}, expected {expected}"


# A same-named method on another object is not recursion, whether it arrives as a
# Ruby receiver or as Swift and Kotlin navigation.
def test_p5_no_false_recursion():
    assert cc("def f(o)\n  o.f\nend\n", "ruby") == 0          # Ruby receiver.f is not recursion
    assert cc("fun f(o:T){o.f()}", "kotlin") == 0            # Kotlin .f navigation is not either
    assert cc("func f(o:T){o.f()}", "swift") == 0            # nor is Swift .f navigation
    # a bare-name recursive call still counts
    assert cc("def f(n)\n  f(n-1)\nend\n", "ruby") == 1
    assert cc("fun f(n:Int):Int{return f(n-1)}", "kotlin") == 1


# End to end for the five newer languages: cognitive scores really land in the
# fingerprints table, proving lang_key resolves to a spec, symbol extraction
# hands over function nodes, and the body field is read correctly.
def test_p5_cognitive_persisted_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "dbs"))
    from codesextant import engine, storage
    repo = tmp_path / "repo"
    repo.mkdir()
    # one complex function per language: for+1 / for+2(n1) / if+3(n2) = 6 with nesting
    (repo / "m.c").write_text(
        "int complexC(int n){int t=0;\n"
        "  for(int i=0;i<n;i++){for(int j=0;j<i;j++){if(j>0){t+=j;}}}\n  return t;}\n", encoding="utf-8")
    (repo / "m.cpp").write_text(
        "int complexCpp(int n){int t=0;\n"
        "  for(int i=0;i<n;i++){for(int j=0;j<i;j++){if(j>0){t+=j;}}}\n  return t;}\n", encoding="utf-8")
    (repo / "m.rb").write_text(
        "def complex_rb(n)\n  t=0\n  for i in 0..n\n    for j in 0..i\n      if j>0\n        t+=j\n      end\n    end\n  end\n  t\nend\n",
        encoding="utf-8")
    (repo / "M.kt").write_text(
        "fun complexKt(n:Int):Int{var t=0\n  for(i in 0..n){for(j in 0..i){if(j>0){t+=j}}}\n  return t}\n",
        encoding="utf-8")
    (repo / "m.swift").write_text(
        "func complexSwift(_ n:Int)->Int{var t=0\n  for i in 0...n{for j in 0...i{if j>0{t+=j}}}\n  return t}\n",
        encoding="utf-8")
    engine.index_project(str(repo), force=True)
    with storage.ProjectStore.open(str(repo)) as store:
        rows = dict(store.conn.execute("SELECT name, cognitive FROM fingerprints").fetchall())
    # all five score 6 and land as real values rather than NULL, which means the
    # whole chain is connected: lang_key to spec, symbol extraction, and body
    assert rows.get("complexC") == 6, f"C stored {rows.get('complexC')}, expected 6"
    assert rows.get("complexCpp") == 6, f"C++ stored {rows.get('complexCpp')}, expected 6"
    assert rows.get("complex_rb") == 6, f"Ruby stored {rows.get('complex_rb')}, expected 6"
    assert rows.get("complexKt") == 6, f"Kotlin stored {rows.get('complexKt')}, expected 6"
    assert rows.get("complexSwift") == 6, f"Swift stored {rows.get('complexSwift')}, expected 6"
