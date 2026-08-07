"""Ground-truth generator for the golden tests (full TypeScript rewrite, P1).

Runs the frozen Python codesextant v0.15.0 over every language sample under fixtures/samples/ and
writes fixtures/expected/<name>.json as the ground truth. symbols.test.ts extracts the same samples
with the TypeScript version and deep-equals the results. Agreement proves symbol parity between the
two versions.

After changing a sample or a spec, rerun this file to regenerate the ground truth:
    python ts/test/gen_ground_truth.py   (from the CodeSextant project root or any cwd; paths resolve
                                          relative to this file)
Note: use C:/Python311, the Python that has codesextant installed locally, and make sure the Python
version imports (tree-sitter and tree-sitter-language-pack must be present).
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))          # .../CodeSextant/ts/test
ROOT = os.path.dirname(os.path.dirname(HERE))              # .../CodeSextant (holds the codesextant/ package)
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

print(f"=== {total} symbols in total; ground truth generated ===")
