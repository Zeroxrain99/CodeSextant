"""probe if/else 結構的 field 名 — P4 walker 泛化的物理地基。

現有 _probe_cflow.py 的 walk 只印 node.type、不印 field 名。但 Go/Java/C# 的 else-if
無 else_clause wrapper 節點（if.alternative field 直接指 if_statement），walker 泛化必須
靠 child_by_field_name('consequence'/'alternative') 區分 then-body / else-body / else-if。
本 probe 對每語言的 if-elseif-else 鏈印每個 child 的 field 名 + 型別，坐實：
  - condition field 名（各語言是否一致）
  - then-body field 名（consequence?）
  - else 部分 field 名（alternative?）+ else-if 時 alternative 指 if_statement？純 else 時指 block？
用法：C:/Python311/python.exe tools/_probe_if_fields.py [lang ...]
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import tree_sitter
from tree_sitter_language_pack import get_language

# 每語言一段 if-elseif-else 鏈 + 一個純 if（含巢狀），聚焦 else 結構
SAMPLES = {
    "python": "def f(x):\n    if x > 0:\n        pass\n    elif x < 0:\n        pass\n    else:\n        pass\n",
    "typescript": "function f(x){ if(x>0){} else if(x<0){} else {} }",
    "go": "package m\nfunc f(x int){ if x>0 {} else if x<0 {} else {} }",
    "java": "class C{ void f(int x){ if(x>0){} else if(x<0){} else {} } }",
    "csharp": "class C{ void F(int x){ if(x>0){} else if(x<0){} else {} } }",
    "rust": "fn f(x:i32){ if x>0 {} else if x<0 {} else {} }",
}

IF_TYPES = {"if_statement", "if_expression"}
ELSE_WRAPPER = {"else_clause", "elif_clause"}


def dump_if(node, src, depth, out):
    if node.type in IF_TYPES or node.type in ELSE_WRAPPER:
        line = node.start_point[0]
        out.append(f"  {'  ' * depth}▶ {node.type} @line{line}")
        cur = node.walk()
        if cur.goto_first_child():
            while True:
                child = cur.node
                fn = cur.field_name
                if child.is_named:
                    snippet = src[child.start_byte:child.end_byte].decode("utf-8", "replace").split("\n")[0][:24]
                    out.append(f"  {'  ' * depth}    field={fn!s:<12} type={child.type:<22} | {snippet!r}")
                if not cur.goto_next_sibling():
                    break
    for c in node.children:
        dump_if(c, src, depth + 1, out)


def main():
    langs = sys.argv[1:] or list(SAMPLES.keys())
    for lang in langs:
        code = SAMPLES.get(lang)
        if code is None:
            print(f"=== {lang} === (no sample)")
            continue
        print(f"\n{'=' * 60}\n=== {lang} ===\n{'=' * 60}")
        src = code.encode("utf-8")
        try:
            parser = tree_sitter.Parser(get_language(lang))
        except Exception as e:  # noqa: BLE001
            print(f"  load FAIL: {e}")
            continue
        tree = parser.parse(src)
        out = []
        dump_if(tree.root_node, src, 0, out)
        print("\n".join(out))


if __name__ == "__main__":
    main()
