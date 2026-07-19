"""生成 storage.ts 黃金測試的 ground truth（用凍結的 Python 版 storage.py 算）。
輸出 fixtures/expected_storage.json：
  - project_key：一組絕對路徑 → sha1（驗 TS 與 Python 算出相同 key，共用同一個 .db 庫的命脈）。
  - file_content_hash：fixtures/samples 下每檔 → sha256（驗增量失效 key 一致）。

直接把 codesextant/ 加進 sys.path 後 `import storage`（不走 package __init__，避開 tree-sitter/jedi 依賴）。
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

here = os.path.dirname(os.path.abspath(__file__))           # ts/test
ts_dir = os.path.dirname(here)                              # ts
cs_root = os.path.dirname(ts_dir)                           # CodeSextant
sys.path.insert(0, os.path.join(cs_root, "codesextant"))   # 直接當頂層 import storage（不觸發 __init__）

import storage  # noqa: E402

samples = os.path.join(here, "fixtures", "samples")

# project_key：用絕對路徑（resolve/abspath 為 identity，不依賴 cwd），涵蓋大小寫 + 正/反斜線 + 中文
# + 元件尾點/尾空格剝除（abspath/GetFullPathName Windows 語義，project_key 命脈）。
pk_paths = [
    r"E:\ai-king\項目資料\CodeSextant",
    r"E:\Ai-King\Foo",          # 測 normcase 小寫化
    r"C:\Users\zerox",
    "E:/ai-king/foo",           # 測 normcase 把 / 統一成 \
    r"E:\foo.\bar",             # 測中間元件尾點剝除
    r"E:\a b ",                 # 測末元件尾空格剝除
    r"E:\專案 \Foo.",            # 測中文 + 尾空格 + 尾點混合
]
pk = {p: storage.project_key(p) for p in pk_paths}

fh = {}
for name in sorted(os.listdir(samples)):
    fp = os.path.join(samples, name)
    if os.path.isfile(fp):
        fh[name] = storage.file_content_hash(fp)

out = {"platform": sys.platform, "project_key": pk, "file_content_hash": fh}
dest = os.path.join(here, "fixtures", "expected_storage.json")
with open(dest, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("wrote", dest)
print(json.dumps(out, ensure_ascii=False, indent=2))
