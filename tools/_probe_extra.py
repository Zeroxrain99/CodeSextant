"""probe 各語言的 comment 節點型別（comments.py 用）+ call 節點型別（clones.py _CALL_TYPES 用）。"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
import tree_sitter
from tree_sitter_language_pack import get_language

SAMP = {
    "csharp": "class X{ void M(){ Foo(); bar.Baz(); } }  // c\n/* b */",
    "java":   "class X{ void m(){ foo(); this.bar(); } } // c\n/* b */",
    "c":      "int m(){ foo(); return 0; } // c\n/* b */",
    "cpp":    "int m(){ foo(); obj.bar(); return 0; } // c\n/* b */",
    "kotlin": "fun m(){ foo(); bar() } // c\n/* b */",
    "swift":  "func m(){ foo(); self.bar() } // c\n/* b */",
    "php":    "<?php\nfunction m(){ foo(); $o->bar(); } // c\n/* b */",
    "lua":    "function m() foo() end -- c\n--[[ b ]]",
    "ruby":   "def m\n foo\n bar()\nend # c",
    "bash":   "m(){ echo hi; foo; } # c",
}

KEYS = ("comment", "call", "invocation", "command")


def collect(node, acc):
    t = node.type
    if any(k in t for k in KEYS):
        acc.add(t)
    for c in node.children:
        collect(c, acc)


for lang, code in SAMP.items():
    try:
        p = tree_sitter.Parser(get_language(lang))
    except Exception as e:
        print(lang, "LOAD FAIL", e)
        continue
    tree = p.parse(code.encode("utf-8"))
    acc = set()
    collect(tree.root_node, acc)
    print(f"{lang:8s} {sorted(acc)}")
