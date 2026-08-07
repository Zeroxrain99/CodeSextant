"""Generate the ground truth for the storage.ts golden tests, computed with the frozen Python storage.py.

Writes fixtures/expected_storage.json:
  - project_key: a set of absolute paths → sha1, proving TypeScript and Python derive the same key,
    which is what keeps one project on one .db.
  - file_content_hash: every file under fixtures/samples → sha256, proving the incremental
    invalidation key agrees.

codesextant/ is put on sys.path and `import storage` is done directly, bypassing the package
__init__ so it does not pull in the tree-sitter/jedi dependencies.
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

here = os.path.dirname(os.path.abspath(__file__))           # ts/test
ts_dir = os.path.dirname(here)                              # ts
cs_root = os.path.dirname(ts_dir)                           # CodeSextant
sys.path.insert(0, os.path.join(cs_root, "codesextant"))   # import storage as a top-level module, never triggering __init__

import storage  # noqa: E402

samples = os.path.join(here, "fixtures", "samples")

# project_key: absolute paths only (resolve/abspath is the identity on them, so nothing depends on
# cwd), covering case folding, forward/back slashes, non-ASCII, and the stripping of trailing dots and
# spaces from components: the Windows abspath/GetFullPathName semantics that project_key rests on.
pk_paths = [
    r"E:\workspace\Проект\CodeSextant",  # non-ASCII (multi-byte UTF-8) component
    r"E:\Work-Space\Foo",       # exercises normcase lowercasing
    r"C:\Users\example",        # a plain user-profile path
    "E:/workspace/foo",         # exercises normcase turning / into \
    r"E:\foo.\bar",             # exercises stripping a trailing dot from an intermediate component
    r"E:\a b ",                 # exercises stripping a trailing space from the last component
    r"E:\Проект \Foo.",          # non-ASCII + trailing space + trailing dot combined
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
