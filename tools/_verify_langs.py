"""冒煙驗證 LANGUAGE_SPECS 新語言：對 _probe_langs.py 的樣本跑 extract，印 kind/name/scope。

用法：在 repo root 跑 C:/Python311/python.exe tools/_verify_langs.py [lang ...]
不帶參數 = 全部 2026-06-22 新增語言。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))          # tools/（拿 _probe_langs.SAMPLES）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root（拿 codesextant）

from _probe_langs import SAMPLES  # noqa: E402

from codesextant import symbols  # noqa: E402

NEW = ["csharp", "java", "c", "cpp", "kotlin", "swift", "php", "ruby", "bash", "lua"]


def main():
    langs = sys.argv[1:] or NEW
    for lang in langs:
        code = SAMPLES[lang].encode("utf-8")
        syms = symbols.extract_symbols_from_source(code, lang)
        print(f"\n{'='*56}\n=== {lang} — {len(syms)} symbols ===\n{'='*56}")
        for s in syms:
            sc = f"   @{s['scope']}" if s["scope"] else ""
            anon = "  ⚠<anon>" if s["name"] == "<anon>" else ""
            print(f"  {s['kind']:12s} {s['name']}{sc}{anon}")


if __name__ == "__main__":
    main()
