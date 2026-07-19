"""D3 認知複雜度 walker 純函數測試 — 演算法正確性（含黃金案例 sumOfPrimes=7）。

確定性 ground truth：先驗演算法對，再接線落盤。每個 expected 都有手算依據（藍圖 §5）。
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
               "method", "singleton_method"}            # P5：Ruby def / def self.x


def _func_name(fn, sb: bytes) -> str | None:
    """取 function 名（遞迴判定用）。name field 優先；C/C++ 走 declarator 鏈；Kotlin 走 simple_identifier。"""
    nn = fn.child_by_field_name("name")
    if nn is not None:
        return sb[nn.start_byte:nn.end_byte].decode()
    decl = fn.child_by_field_name("declarator")          # C/C++: function_declarator > identifier
    while decl is not None:
        if decl.type == "identifier":
            return sb[decl.start_byte:decl.end_byte].decode()
        decl = decl.child_by_field_name("declarator")
    for c in fn.children:                                 # Kotlin: 第一個 simple_identifier child
        if c.type == "simple_identifier":
            return sb[c.start_byte:c.end_byte].decode()
    return None


def cc(src: str, lang: str) -> int | None:
    """parse 一段含單一頂層 function 的 source，算其 body 的 cognitive complexity。"""
    sb = src.encode("utf-8")
    parser = tree_sitter.Parser(symbols._ts_language(lang))
    tree = parser.parse(sb)
    found = []

    def rec(n):
        if n.type in _FUNC_TYPES:
            found.append(n)
            return  # 取最外層 function（不下鑽巢狀）
        for c in n.children:
            rec(c)

    rec(tree.root_node)
    assert found, f"找不到 function（{lang}）"
    fn = found[0]
    body = complexity.function_body(fn, lang)            # Kotlin function_body 無 field → fallback
    name = _func_name(fn, sb)
    return complexity.cognitive_complexity(body, lang, name, sb)


# ── 黃金案例（白皮書招牌、業界共識）──
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


# ── 基本：簡單函數 = 0（乾淨碼不褪色）──
def test_trivial_zero():
    assert cc("def f(x):\n    y = x + 1\n    return y\n", "python") == 0


# ── 巢狀 if 拿 B3 ──
def test_nested_if_python():
    src = "def f(a, b):\n    if a:\n        if b:\n            pass\n"
    assert cc(src, "python") == 3  # if +1 / if +1+1=2


# ── else-if 鏈：各分支 +1、不累積巢狀（關鍵防雙算）──
def test_elif_chain_python():
    src = ("def f(x):\n"
           "    if x == 1:\n        pass\n"
           "    elif x == 2:\n        pass\n"
           "    elif x == 3:\n        pass\n"
           "    else:\n        pass\n")
    assert cc(src, "python") == 4  # 4 分支各 +1、無 B3 累積


def test_elif_chain_with_nested_body_python():
    src = ("def f(x):\n"
           "    if x == 1:\n        pass\n"
           "    elif x == 2:\n        for i in x:\n            pass\n")
    assert cc(src, "python") == 4  # if +1 / elif +1 / for +1+1=2（for 在 elif body n=1）


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
    # if +1 / else-if +1 / else-if +1 / for +1+1=2（for 在第三分支 body n=1，不因 else-if 鏈加深）
    assert cc(src, "typescript") == 5


# ── 布林運算子序列：每個 run +1 ──
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


# ── 直接遞迴 +1 ──
def test_recursion_python():
    src = ("def fact(n):\n"
           "    if n <= 1:\n        return 1\n"
           "    return n * fact(n - 1)\n")
    assert cc(src, "python") == 2  # if +1 / recursion +1


# ── switch：整體 +1、case 不各加（cognitive vs cyclomatic 關鍵差異）──
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
    assert cc(src, "typescript") == 1  # switch +1，3 個 case 不加


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


# ── 巢狀函數/lambda 增層（讓裡面控制流更貴、宣告本身不加分）──
def test_nested_function_adds_nesting_python():
    src = ("def f(items):\n"
           "    def inner(x):\n"
           "        if x:\n            return 1\n"
           "        return 0\n"
           "    return inner\n")
    assert cc(src, "python") == 2  # inner 不加分但增層 / 內層 if +1+1=2


# ── ternary 拿 B3、巢狀加權 ──
def test_ternary_python():
    assert cc("def f(x):\n    return 1 if x else 2\n", "python") == 1


def test_nested_ternary_python():
    src = "def f(x, y):\n    return 1 if x else (2 if y else 3)\n"
    assert cc(src, "python") == 3  # outer +1 / inner +1+1=2


# ── try/except/finally：try/finally 透明、except 算且增層、try-else 不算 ──
def test_try_except_else_finally_python():
    src = ("def f(x):\n"
           "    try:\n        pass\n"
           "    except ValueError:\n        pass\n"
           "    else:\n        pass\n"
           "    finally:\n        pass\n")
    assert cc(src, "python") == 1  # 只 except +1；try/finally/try-else 不算


def test_except_adds_nesting_python():
    src = ("def f(x):\n"
           "    try:\n        pass\n"
           "    except ValueError:\n        if x:\n            pass\n")
    assert cc(src, "python") == 3  # except +1 / 內層 if +1+1=2


# ── 仍 UNKNOWN 的語言回 None（P5 後高信心集＝13 語言；lua/php/bash 仍誠實降級不顯成 0=乾淨）──
def test_remaining_unknown_none():
    # lua/php/bash 控制流 grammar 未驗透 → cognitive=None（UNKNOWN、不洗滿分）。
    # 這些語言抽符號已支援（symbols）、function 節點能 parse，但 cognitive spec 未填 → 證「語言未支援」非「body 問題」。
    assert cc("function f(x)\n  if x > 0 then\n    return 1\n  end\n  return 0\nend\n", "lua") is None
    assert cc("<?php\nfunction f($x) {\n  if ($x > 0) { return 1; }\n  return 0;\n}\n", "php") is None


def test_supported_set():
    # P3 高信心 4 語言
    assert complexity.supported("python")
    assert complexity.supported("typescript")
    assert complexity.supported("tsx")
    assert complexity.supported("javascript")
    # P4 新增 4 語言（2026-06-23）
    assert complexity.supported("go")
    assert complexity.supported("rust")
    assert complexity.supported("java")
    assert complexity.supported("csharp")
    # P5 新增 5 語言（2026-06-23）
    assert complexity.supported("c")
    assert complexity.supported("cpp")
    assert complexity.supported("ruby")
    assert complexity.supported("kotlin")
    assert complexity.supported("swift")
    # 仍 UNKNOWN（抽符號支援但 cognitive spec 未填）
    assert not complexity.supported("lua")
    assert not complexity.supported("php")
    assert not complexity.supported("bash")


# ════════════════════════════════════════════════════════════
# P4 語言擴展黃金案例（Go/Java/C#/Rust，2026-06-23）— 每個 expected 皆手算
# ════════════════════════════════════════════════════════════

# ── 黃金案例 sumOfPrimes=7（白皮書招牌）逐語言：for+1 / for+2(n1) / if+3(n2) / labeled continue+1 ──
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


# ── field-style else-if（Go/Java/C#）：巢狀 if 拿 B3、else-if 不拿 B3、純 else +1 ──
# if x>0(+1) / 巢狀 if x>10(+1+B3 1=+2) / 巢狀 else(+1) / else-if x<0(+1 無 B3) / else(+1) = 6
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


# ── Java switch_expression + ternary + do-while + catch（try/finally 透明、case 不各加）= 4 ──
def test_java_switch_ternary_do_catch():
    src = ("class C {\n  int h(int x) {\n"
           "    switch (x) { case 1: break; default: break; }\n"   # +1
           "    int y = x > 0 ? 1 : 0;\n"                          # ternary +1
           "    do { x--; } while (x > 0);\n"                      # do +1
           "    try { g(); } catch (Exception e) { x = 0; } finally { }\n"  # catch +1
           "    return y;\n  }\n}\n")
    assert cc(src, "java") == 4


# ── C# switch_statement + conditional_expression + do + catch = 4 ──
def test_csharp_switch_conditional_do_catch():
    src = ("class C {\n  int H(int x) {\n"
           "    switch (x) { case 1: break; default: break; }\n"   # +1
           "    int y = x > 0 ? 1 : 0;\n"                          # conditional +1
           "    do { x--; } while (x > 0);\n"                      # do +1
           "    try { G(); } catch (System.Exception e) { x = 0; } finally { }\n"  # catch +1
           "    return y;\n  }\n}\n")
    assert cc(src, "csharp") == 4


# ── Rust match + loop + 巢狀 while（match/loop n0、while 在 loop 內 n1 拿 B3）= 4 ──
def test_rust_match_loop_while():
    src = ("fn k(x: i32) -> i32 {\n"
           "    match x {\n        1 => {},\n        _ => {},\n    }\n"   # match +1
           "    loop {\n"                                                 # loop +1 (n0)
           "        while x > 0 {\n            break;\n        }\n"        # while +1+B3(1)=+2 (n1)
           "        break;\n    }\n"
           "    x\n}\n")
    assert cc(src, "rust") == 4


# ── Go switch + boolean run（switch+1 / 巢狀 if+2 / a&&b||c=2 runs）= 5 ──
def test_go_switch_boolean():
    src = ("package m\n"
           "func g(x int) int {\n"
           "\tswitch x {\n\tcase 1:\n\t\tif x > 0 {\n\t\t}\n\tdefault:\n\t}\n"  # switch+1, 巢狀if+2
           "\ty := x > 0 && x < 10 || x == 0\n\t_ = y\n"                        # boolean 2 runs
           "\treturn 0\n}\n")
    assert cc(src, "go") == 5


# ── 裸遞迴 +1（每次直接呼叫自己）──
def test_recursion_go():
    src = ("package m\n"
           "func fib(n int) int {\n"
           "\tif n < 2 {\n\t\treturn n\n\t}\n"            # if +1
           "\treturn fib(n-1) + fib(n-2)\n}\n")           # 2 遞迴 +2
    assert cc(src, "go") == 3


def test_recursion_rust():
    src = ("fn fib(n: i32) -> i32 {\n"
           "    if n < 2 {\n        return n;\n    }\n"     # if +1
           "    fib(n - 1) + fib(n - 2)\n}\n")             # 2 遞迴 +2
    assert cc(src, "rust") == 3


# ── 跨物件同名方法不誤判遞迴（Java other.f() 於名為 f 的方法內不算）──
def test_no_false_recursion_java():
    src = ("class C {\n  int f(int x) {\n"
           "    return other.f(x);\n  }\n}\n")   # other.f() 非遞迴 → 0
    assert cc(src, "java") == 0


# ── field-style 無大括號 else（Go/Java/C# 允許 `else stmt;`）純 else 仍 +1（防漏算）──
def test_field_no_brace_else():
    # if(+1) + 純 else(+1) = 2
    assert cc("class C{ int f(int x){ if(x>0) return 1; else return 0; } }", "java") == 2
    assert cc("class C{ int F(int x){ if(x>0) return 1; else return 0; } }", "csharp") == 2
    # 無大括號 else-if 鏈：if(+1) / else-if(+1 無B3) / else(+1) = 3
    assert cc("class C{ int f(int x){ if(x>0) return 1; else if(x<0) return -1; else return 0; } }",
              "java") == 3


# ── 各語言 trivial = 0（乾淨碼不褪色）──
def test_trivial_zero_p4():
    assert cc("package m\nfunc f(x int) int {\n\ty := x + 1\n\treturn y\n}\n", "go") == 0
    assert cc("fn f(x: i32) -> i32 {\n    let y = x + 1;\n    y\n}\n", "rust") == 0
    assert cc("class C {\n  int f(int x) {\n    int y = x + 1;\n    return y;\n  }\n}\n", "java") == 0
    assert cc("class C {\n  int F(int x) {\n    int y = x + 1;\n    return y;\n  }\n}\n", "csharp") == 0


# ════════════════════════════════════════════════════════════
# 對抗 review 修正迴歸（2026-06-23 wf_d7dda04d，5 lens distinct 子代理真跑驗算）
# ════════════════════════════════════════════════════════════

# ── CS-1/CS-2：C# switch expression `x switch {}` 計分（曾完全漏算：型別 switch_expression 非 switch_statement）──
def test_csharp_switch_expression():
    # if(+1) + switch expr(+1) = 2（曾 actual=1）
    assert cc("class C{ int M(int x){ if(x>0) return 1; return x switch { 1=>10, _=>0 }; } }",
              "csharp") == 2
    # switch expr arm 內三元受巢狀加權：switch_expr(+1 n0) + 三元 at n1(+1+B3=2) = 3（曾 actual=1）
    assert cc("class C{ int M(int x,int y){ return x switch { 1 => y>0?10:20, _=>0 }; } }",
              "csharp") == 3


# ── 跨語言：wrapper-style 無大括號 then/else 增巢狀層（braced 與 brace-less 同分＝消除 game 向量）──
def test_braceless_body_increments_nesting():
    braced = "function f(a,b,c){ if(a){ if(b){ if(c){} } } }"
    braceless = "function f(a,b,c){ if(a) if(b) if(c) {} }"
    assert cc(braced, "typescript") == 6
    assert cc(braceless, "typescript") == 6        # 同分（曾 actual=3＝加不加括號改分數的 game 向量）
    assert cc("function f(x){ if(x) for(let i=0;i<x;i++){} }", "typescript") == 3        # 曾 2
    assert cc("function f(a){ if(a){} else for(let i=0;i<1;i++){} }", "typescript") == 4  # 曾 3
    # Python 恆 block（語法強制）不受影響、仍正確
    assert cc("def f(a,b):\n    if a:\n        if b:\n            pass\n", "python") == 3


# ── 開關（L0 鐵律 #6）──
def test_disable_switch(monkeypatch):
    monkeypatch.setenv("CODESEXTANT_COGNITIVE_DISABLED", "1")
    assert cc("def f(x):\n    if x:\n        pass\n", "python") is None


# ── game 抵抗（C4）：把一個複雜函數拆成多個緊密小函數，每個小函數 cognitive 低 ──
def test_game_resistance_small_functions_stay_low():
    # 拆出來的小函數每個只 1 個 if → cognitive=1（health 高、不褪色）
    for src in ("def a(x):\n    if x:\n        return 1\n    return 0\n",
                "def b(x):\n    if x:\n        return 2\n    return 0\n"):
        assert cc(src, "python") == 1


# ════════════ 對抗 review 修正的迴歸鎖（distinct 子代理實測反例當期望值）════════════

def test_nullish_not_counted_ts():
    # ?? 空值合併：白皮書明文 ignore null-coalescing，不計（review HIGH）
    assert cc("function f(a, b) { return a ?? b; }", "typescript") == 0
    assert cc("function f(a, b, c) { return a ?? b ?? c; }", "typescript") == 0
    # ?? 不算、但內含的真 && 仍正確計數
    assert cc("function f(a, b, c) { if (a && (b ?? c)) return 1; return 0; }",
              "typescript") == 2  # if+1 + && run 1


def test_recursion_attr_same_name_not_counted():
    # obj.foo() 於名為 foo 的函數內不算遞迴（review MEDIUM 收緊誤判）
    assert cc("def foo(obj):\n    return obj.foo()\n", "python") == 0
    assert cc("function save(repo) { return repo.save(); }", "typescript") == 0
    # self.foo()/this.foo() 算真遞迴
    assert cc("def foo(self):\n    if self.x:\n        return self.foo()\n    return 0\n",
              "python") == 2  # if+1 + self 遞迴+1
    # 裸名遞迴仍算（不被收緊破壞）
    assert cc("def f(n):\n    return f(n - 1)\n", "python") == 1


def test_for_else_no_extra_nesting():
    # for-else 的 else body 不繼承 loop 巢狀深度（review MEDIUM）
    src = ("def f(xs, x):\n"
           "    for v in xs:\n"
           "        if v:\n            break\n"
           "    else:\n"
           "        if x:\n            pass\n")
    assert cc(src, "python") == 4  # for+1 / 內 if+1+1=2 / 無 label break 0 / else 透明 / else 內 if+1(n=0)


def test_nested_comprehension_sibling_for():
    # 同一 comprehension 多個 for 在 AST 是 sibling、第二個 for 不累積巢狀（review LOW、誠實標）
    assert cc("def f(b):\n    return [x for a in b for x in a]\n", "python") == 2  # 兩 for 各 +1


# ── schema migration 契約（review LOW，鎖「ALTER 補欄不破壞既有列」）──
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
    storage._ensure_columns(conn)  # migration hook（藍圖 §3 所稱）
    cols = {r[1] for r in conn.execute("PRAGMA table_info(fingerprints)").fetchall()}
    assert "cognitive" in cols  # 新欄補上
    row = conn.execute("SELECT name, node_count, cognitive FROM fingerprints").fetchone()
    assert row[0] == "foo" and row[1] == 10 and row[2] is None  # 既有列保留、新欄 NULL
    conn.close()


# ── code_health 端 cognitive=None 正確 renormalize 不洗滿分（鎖 SSOT C2 防 vapor）──
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
    # cognitive=None → D3 剔除；剩 bloat(滿1)+dup(0) renormalize：penalty=0.25/(0.25+0.30)≈0.45
    # 關鍵：None 沒被當滿分(health=1) 也沒被當 cog=0 灌進分母（C2 防 vapor）
    assert h is not None and 0.4 < h < 0.65


# ── engine.get_health 端到端整合（PoC health 接回正式引擎、複雜函數 health 低於簡單函數）──
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
    # 巢狀地獄 complex_fn → cognitive 高 → health 低；simple(cog=0) → health 高
    assert by_name["complex_fn"]["health"] is not None
    assert by_name["simple"]["health"] is not None
    assert by_name["complex_fn"]["health"] < by_name["simple"]["health"]


# ── P4 端到端：Go/Rust/Java/C# cognitive 真落盤 fingerprints（驗 lang_key 對上 spec + symbols 抽 function 全接通）──
def test_p4_cognitive_persisted_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "dbs"))
    from codesextant import engine, storage
    repo = tmp_path / "repo"
    repo.mkdir()
    # 四語言各一複雜函數：for+1 / for+2(n1) / if+3(n2) = 6（巢狀加權）
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
    # 四語言複雜函數 cognitive 皆 6（端到端落盤、非 NULL）＝接線全通（lang_key→spec、symbols 抽 function、body field）
    assert rows.get("complexGo") == 6, f"Go 落盤={rows.get('complexGo')} (應 6)"
    assert rows.get("complex_rust") == 6, f"Rust 落盤={rows.get('complex_rust')} (應 6)"
    assert rows.get("complexJava") == 6, f"Java 落盤={rows.get('complexJava')} (應 6)"
    assert rows.get("ComplexCs") == 6, f"C# 落盤={rows.get('ComplexCs')} (應 6)"


# ════════════════════════════════════════════════════════════
# P5 語言擴展黃金案例（C/C++/Ruby/Kotlin/Swift，2026-06-23）— tools/_smoke_p5.py 驗證、每 expected 手算
# ════════════════════════════════════════════════════════════
# 招牌 sumOfPrimes=7：C/C++ 用 goto（for+1/for+2/if+3/goto+1）、Kotlin/Swift 用 labeled continue。
# Ruby 無 labeled jump（next/break/redo 皆裸跳最內層）→ 改用 Ruby 慣用控制流組合手算。
_P5_CASES = [
    # ── C：wrapper-style、goto labeled、無 try、conditional 三元 ──
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
    # ── C++：C 全部 + try/catch + lambda + range-for ──
    ("cpp", "sumOfPrimes-goto",
     "int s(int max){int t=0;for(int i=2;i<=max;i++){for(int j=2;j<i;j++){if(i%j==0){goto next;}}t+=i;next:;}return t;}", 7),
    ("cpp", "try-catch", "int f(){try{g();}catch(std::exception&e){h();}return 0;}", 1),
    ("cpp", "range-for", "int f(std::vector<int>v){int t=0;for(auto&x:v){t+=x;}return t;}", 1),
    ("cpp", "lambda-nest", "int f(int x){auto g=[](int q){if(q>0){return q;}return 0;};return g(x);}", 2),
    # ── Ruby：if 節點型別 if、case/when、while/until、unless、rescue、if_modifier、callee=method ──
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
    # ── Kotlin：field-style if、when、function_body 無 field、&&/|| 雙節點型別、callee fallback、jump_expression ──
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
    # ── Swift：客製 if、guard、switch、repeat-while、do/catch、ternary、control_transfer labeled ──
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
    assert cc(src, lang) == expected, f"{lang} {label}: got {cc(src, lang)} 應 {expected}"


# ── 跨物件同名方法不誤判遞迴（Ruby receiver、Swift/Kotlin navigation）──
def test_p5_no_false_recursion():
    assert cc("def f(o)\n  o.f\nend\n", "ruby") == 0          # Ruby receiver.f 非遞迴
    assert cc("fun f(o:T){o.f()}", "kotlin") == 0            # Kotlin navigation .f 非遞迴
    assert cc("func f(o:T){o.f()}", "swift") == 0            # Swift navigation .f 非遞迴
    # 裸名遞迴仍算
    assert cc("def f(n)\n  f(n-1)\nend\n", "ruby") == 1
    assert cc("fun f(n:Int):Int{return f(n-1)}", "kotlin") == 1


# ── P5 端到端：五語言 cognitive 真落盤 fingerprints（驗 lang_key→spec、symbols 抽 function、body field 全接通）──
def test_p5_cognitive_persisted_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "dbs"))
    from codesextant import engine, storage
    repo = tmp_path / "repo"
    repo.mkdir()
    # 五語言各一複雜函數：for+1 / for+2(n1) / if+3(n2) = 6（巢狀加權）
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
    # 五語言複雜函數 cognitive 皆 6（端到端落盤、非 NULL）＝接線全通（lang_key→spec、symbols 抽 function、body）
    assert rows.get("complexC") == 6, f"C 落盤={rows.get('complexC')} (應 6)"
    assert rows.get("complexCpp") == 6, f"C++ 落盤={rows.get('complexCpp')} (應 6)"
    assert rows.get("complex_rb") == 6, f"Ruby 落盤={rows.get('complex_rb')} (應 6)"
    assert rows.get("complexKt") == 6, f"Kotlin 落盤={rows.get('complexKt')} (應 6)"
    assert rows.get("complexSwift") == 6, f"Swift 落盤={rows.get('complexSwift')} (應 6)"
