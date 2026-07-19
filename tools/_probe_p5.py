"""P5 probe — 為 Ruby/C/C++/Kotlin/Swift 認知複雜度坐實控制流 taxonomy（帶 field 名）。

承 _probe_cflow.py（印 named 樹）+ _probe_if_fields.py（印 if field 名），合一：對每語言印
「帶 field 名的完整 named 樹」+ 額外聚焦 function body field 名。填表不腦推、實測坐實。

用法：C:/Python311/python.exe tools/_probe_p5.py [lang ...]   （預設全 5 語言）
      $env:PROBE_MAXD=12 控制深度。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows console gbk 防崩

import tree_sitter
from tree_sitter_language_pack import get_language

# 每語言一段「涵蓋全控制流」的樣本（不求語意正確、只求 parse 出結構）：
#   sumOfPrimes 巢狀+labeled / switch或case或when或match / while / do-while或until或repeat
#   / 例外(try-catch或rescue或無) / ternary或if-expr / boolean run / closure或lambda / 遞迴
SAMPLES = {
    "ruby": '''
def sum_of_primes(max)
  total = 0
  (2..max).each do |i|
    ok = true
    (2...i).each do |j|
      if i % j == 0
        ok = false
      end
    end
    total += i if ok
  end
  case max
  when 1 then puts "one"
  when 2 then puts "two"
  else puts "other"
  end
  i = 0
  while i < max
    i += 1
  end
  until i >= max
    i += 1
  end
  puts "neg" unless max > 0
  begin
    risky
  rescue StandardError => e
    handle
  ensure
    cleanup
  end
  y = max > 0 && max < 10 || max == 0
  z = max > 0 ? 1 : 0
  sum_of_primes(max - 1)
end
''',
    "c": '''
int sumOfPrimes(int max) {
    int total = 0;
    for (int i = 2; i <= max; i++) {
        for (int j = 2; j < i; j++) {
            if (i % j == 0) {
                goto next;
            }
        }
        total += i;
        next:;
    }
    switch (max) {
        case 1: break;
        default: break;
    }
    int i = 0;
    while (i < max) { i++; }
    do { i--; } while (i > 0);
    if (max > 0) { total++; } else if (max < 0) { total--; } else { total = 0; }
    int y = max > 0 && max < 10 || max == 0;
    int z = max > 0 ? 1 : 0;
    return sumOfPrimes(max - 1);
}
''',
    "cpp": '''
int sumOfPrimes(int max) {
    int total = 0;
    for (int i = 2; i <= max; i++) {
        for (int j = 2; j < i; j++) {
            if (i % j == 0) { goto next; }
        }
        total += i;
        next:;
    }
    try { risky(); } catch (std::exception& e) { handle(); }
    auto fn = [](int q) { if (q > 0) { return q; } return 0; };
    for (auto& v : vec) { use(v); }
    while (max > 0) { max--; }
    do { max++; } while (max < 0);
    int y = max > 0 && max < 10 || max == 0;
    int z = max > 0 ? 1 : 0;
    return sumOfPrimes(max - 1);
}
''',
    "kotlin": '''
fun sumOfPrimes(max: Int): Int {
    var total = 0
    outer@ for (i in 2..max) {
        for (j in 2 until i) {
            if (i % j == 0) {
                continue@outer
            }
        }
        total += i
    }
    when (max) {
        1 -> println("one")
        2 -> println("two")
        else -> println("other")
    }
    var i = 0
    while (i < max) { i++ }
    do { i-- } while (i > 0)
    try { risky() } catch (e: Exception) { handle() } finally { cleanup() }
    val y = max > 0 && max < 10 || max == 0
    val z = if (max > 0) 1 else 0
    val f = { q: Int -> q }
    return sumOfPrimes(max - 1)
}
''',
    "swift": '''
func sumOfPrimes(_ max: Int) -> Int {
    var total = 0
    outer: for i in 2...max {
        for j in 2..<i {
            if i % j == 0 {
                continue outer
            }
        }
        total += i
    }
    switch max {
    case 1: print("one")
    default: print("other")
    }
    var i = 0
    while i < max { i += 1 }
    repeat { i -= 1 } while i > 0
    guard max > 0 else { return 0 }
    do { try risky() } catch { handle() }
    let y = max > 0 && max < 10 || max == 0
    let z = max > 0 ? 1 : 0
    let f = { (q: Int) in q }
    return sumOfPrimes(max - 1)
}
''',
}

_FUNC_HINT = {"method", "singleton_method", "function_definition", "function_declaration",
              "function_item", "method_declaration"}


def walk(node, src, depth, maxd, field, out):
    if node.is_named and depth <= maxd:
        txt = src[node.start_byte:node.end_byte].decode("utf-8", "replace")
        snippet = txt.split("\n")[0][:36]
        fmark = f"field={field}" if field else ""
        out.append("  " * depth + f"{node.type:<28} {fmark:<20} | {snippet!r}")
    if depth < maxd:
        cur = node.walk()
        if cur.goto_first_child():
            while True:
                c = cur.node
                walk(c, src, depth + 1, maxd, cur.field_name, out)
                if not cur.goto_next_sibling():
                    break


def find_funcs(node, out):
    if node.type in _FUNC_HINT:
        out.append(node)
    for c in node.children:
        find_funcs(c, out)


def main():
    langs = sys.argv[1:] or list(SAMPLES.keys())
    maxd = int(os.environ.get("PROBE_MAXD", "12"))
    for lang in langs:
        code = SAMPLES.get(lang)
        print(f"\n{'=' * 64}\n=== {lang} ===\n{'=' * 64}")
        if code is None:
            print("  (no sample)")
            continue
        src = code.encode("utf-8")
        try:
            parser = tree_sitter.Parser(get_language(lang))
        except Exception as e:  # noqa: BLE001
            print(f"  load FAIL: {e}")
            continue
        tree = parser.parse(src)
        # function body field 名
        funcs = []
        find_funcs(tree.root_node, funcs)
        for fn in funcs[:3]:
            body = fn.child_by_field_name("body")
            name = fn.child_by_field_name("name")
            nm = src[name.start_byte:name.end_byte].decode() if name else "<no name field>"
            bt = body.type if body is not None else "<no body field>"
            print(f"  FUNC {fn.type} name={nm!r} body_field_type={bt}")
        print("  " + "-" * 60)
        out = []
        walk(tree.root_node, src, 0, maxd, None, out)
        print("\n".join(out))


if __name__ == "__main__":
    main()
