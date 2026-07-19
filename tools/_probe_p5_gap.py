"""P5 補洞 probe — 坐實 _probe_p5.py 漏測的關鍵控制流：
  ruby:   if/elsif/else 鏈、前置 unless、for-in、block {}、binary && 的 operator field
  kotlin: labeled continue(@)、&&/|| 節點型別、member call(navigation)、if/else
  swift:  if/elsif/else 鏈、&&/|| 節點型別、member call

用法：C:/Python311/python.exe tools/_probe_p5_gap.py [lang ...]
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

import tree_sitter
from tree_sitter_language_pack import get_language

SAMPLES = {
    "ruby": '''
def f(x, items)
  if x > 0
    a
  elsif x < 0
    b
  else
    c
  end
  unless x > 0
    d
  end
  for i in items
    e
  end
  items.each { |y| y }
  z = x > 0 && x < 10 || x == 0
  obj.f(x)
end
''',
    "kotlin": '''
fun f(x: Int) {
    loop@ for (i in 1..x) {
        if (i > 0) {
            continue@loop
        } else {
            break@loop
        }
    }
    val y = x > 0 && x < 10 || x == 0
    obj.method(x)
    f(x - 1)
}
''',
    "swift": '''
func f(x: Int) {
    if x > 0 {
        a()
    } else if x < 0 {
        b()
    } else {
        c()
    }
    let y = x > 0 && x < 10 || x == 0
    obj.method(x)
}
''',
}


def walk(node, src, depth, maxd, field, out):
    if node.is_named and depth <= maxd:
        txt = src[node.start_byte:node.end_byte].decode("utf-8", "replace")
        snippet = txt.split("\n")[0][:34]
        fmark = f"field={field}" if field else ""
        # 額外印 operator field（boolean run 判定關鍵）
        op = node.child_by_field_name("operator")
        opmark = f" OP={src[op.start_byte:op.end_byte].decode('utf-8','replace')!r}" if op is not None else ""
        out.append("  " * depth + f"{node.type:<30} {fmark:<18}{opmark} | {snippet!r}")
    if depth < maxd:
        cur = node.walk()
        if cur.goto_first_child():
            while True:
                walk(cur.node, src, depth + 1, maxd, cur.field_name, out)
                if not cur.goto_next_sibling():
                    break


def main():
    langs = sys.argv[1:] or list(SAMPLES.keys())
    maxd = int(os.environ.get("PROBE_MAXD", "14"))
    for lang in langs:
        code = SAMPLES.get(lang)
        print(f"\n{'=' * 64}\n=== {lang} ===\n{'=' * 64}")
        if code is None:
            print("  (no sample)")
            continue
        src = code.encode("utf-8")
        parser = tree_sitter.Parser(get_language(lang))
        tree = parser.parse(src)
        out = []
        walk(tree.root_node, src, 0, maxd, None, out)
        print("\n".join(out))


if __name__ == "__main__":
    main()
