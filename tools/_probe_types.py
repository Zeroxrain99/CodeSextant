"""收集每語言 sample 出現的全部控制流相關節點型別（去重排序）— P4 spec 填表依據。
重用 _probe_cflow.SAMPLES（已含 switch/select/catch/try/finally/do/match/loop/if-let 等）。
用法：C:/Python311/python.exe tools/_probe_types.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))

import tree_sitter
from _probe_cflow import SAMPLES
from tree_sitter_language_pack import get_language

KW = ("if", "else", "elif", "for", "foreach", "while", "do", "switch", "case", "catch",
      "try", "finally", "match", "loop", "select", "ternary", "conditional", "cond",
      "binary", "boolean", "logical", "call", "invocation", "method_inv", "label",
      "break", "continue", "return", "guard", "when", "expression_switch", "type_switch",
      "arm", "block")


def collect(node, types):
    if node.is_named:
        types.add(node.type)
    for c in node.children:
        collect(c, types)


def main():
    for lang in ["go", "java", "csharp", "rust", "python", "typescript"]:
        code = SAMPLES.get(lang)
        if not code:
            print(f"=== {lang} === (no sample)")
            continue
        src = code.encode("utf-8")
        try:
            parser = tree_sitter.Parser(get_language(lang))
        except Exception as e:  # noqa: BLE001
            print(f"=== {lang} === load FAIL {e}")
            continue
        types = set()
        collect(parser.parse(src).root_node, types)
        cf = sorted(t for t in types if any(k in t for k in KW))
        print(f"\n=== {lang} 控制流相關型別（{len(cf)}）===")
        for t in cf:
            print("  ", t)


if __name__ == "__main__":
    main()
