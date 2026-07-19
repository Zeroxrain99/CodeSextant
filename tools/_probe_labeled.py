"""probe labeled break/continue + switch case body 結構 — 黃金案例 sumOfPrimes 需 labeled continue。
各語言 label 的 child 型別不同（Go/Java/Rust），walker is_labeled 須認得；switch case 不可多算。
用法：C:/Python311/python.exe tools/_probe_labeled.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import tree_sitter
from tree_sitter_language_pack import get_language

# 每語言：labeled 迴圈 + labeled continue/break + switch(case body 含 if)
SAMPLES = {
    "go": "package m\nfunc f(n int) {\n\tOUT:\n\tfor i := 0; i < n; i++ {\n\t\tfor j := 0; j < i; j++ {\n\t\t\tif i%j == 0 {\n\t\t\t\tcontinue OUT\n\t\t\t}\n\t\t}\n\t}\n\tswitch n {\n\tcase 1:\n\t\tif n > 0 {\n\t\t}\n\tdefault:\n\t}\n}\n",
    "java": "class C {\n\tvoid f(int n) {\n\t\tOUT:\n\t\tfor (int i = 0; i < n; i++) {\n\t\t\tfor (int j = 0; j < i; j++) {\n\t\t\t\tif (i % j == 0) {\n\t\t\t\t\tcontinue OUT;\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t\tswitch (n) {\n\t\tcase 1:\n\t\t\tif (n > 0) {}\n\t\t\tbreak;\n\t\tdefault:\n\t\t}\n\t}\n}\n",
    "rust": "fn f(n: i32) {\n\t'outer: for i in 0..n {\n\t\tfor j in 0..i {\n\t\t\tif i % j == 0 {\n\t\t\t\tcontinue 'outer;\n\t\t\t}\n\t\t}\n\t}\n\tmatch n {\n\t\t1 => { if n > 0 {} }\n\t\t_ => {}\n\t}\n}\n",
}


def walk(node, src, depth, out, maxd=14):
    if node.is_named and depth <= maxd:
        cur = node.walk()
        fn = None
        # 取相對 parent 的 field（從 parent cursor 較準，這裡簡化只印型別樹 + break/continue 細節）
        snippet = src[node.start_byte:node.end_byte].decode("utf-8", "replace").split("\n")[0][:30]
        mark = ""
        if any(k in node.type for k in ("continue", "break", "label", "switch", "case", "match_arm", "default")):
            mark = "  ★"
        out.append(f"{'  ' * depth}{node.type}{mark}  | {snippet!r}")
    if depth < maxd:
        for c in node.children:
            walk(c, src, depth + 1, out, maxd)


def main():
    for lang in SAMPLES:
        print(f"\n{'=' * 56}\n=== {lang} ===\n{'=' * 56}")
        src = SAMPLES[lang].encode("utf-8")
        parser = tree_sitter.Parser(get_language(lang))
        out = []
        walk(parser.parse(src).root_node, src, 0, out)
        print("\n".join(out))


if __name__ == "__main__":
    main()
