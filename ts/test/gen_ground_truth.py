"""黃金測試 ground truth 生成器（全 TS 重寫 P1）。

用「凍結的 Python 版 codesextant v0.15.0」對 fixtures/samples/ 下每個語言樣本抽符號，
生成 fixtures/expected/<name>.json 當 ground truth。symbols.test.ts 用 TS 版抽同樣本後
deep-equal 對照——一致即證 TS 版與 Python 版抽符號 parity。

樣本或 spec 改動後重跑本檔即可重生 ground truth：
    python ts/test/gen_ground_truth.py      （在 CodeSextant 專案根跑，或任意 cwd 皆可，路徑自動相對定位）
⚠ 用 C:/Python311（本機 codesextant 的 Python），且 Python 版需可 import（tree-sitter + tree-sitter-language-pack 已裝）。
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))          # .../CodeSextant/ts/test
ROOT = os.path.dirname(os.path.dirname(HERE))              # .../CodeSextant（含 codesextant/ 套件）
sys.path.insert(0, ROOT)
from codesextant.symbols import extract_symbols  # noqa: E402

samples_dir = os.path.join(HERE, "fixtures", "samples")
expected_dir = os.path.join(HERE, "fixtures", "expected")
os.makedirs(expected_dir, exist_ok=True)

total = 0
for f in sorted(glob.glob(os.path.join(samples_dir, "*"))):
    name = os.path.basename(f)
    try:
        syms = extract_symbols(f)
    except Exception as e:  # noqa: BLE001
        print(f"  SKIP {name}: {e}")
        continue
    out_path = os.path.join(expected_dir, name + ".json")
    with open(out_path, "w", encoding="utf-8") as w:
        json.dump(syms, w, ensure_ascii=False, indent=2)
    total += len(syms)
    print(f"  {name}: {len(syms)} symbols -> expected/{name}.json")

print(f"=== 共 {total} 符號，ground truth 生成完畢 ===")
