"""測試碼判定 — 單一真相源（變數收斂紀律 dogfood）。

CodeSextant「代碼地圖分離測試」優化的判定中樞：build_repo_graph 標記 node、
group_in_box 分離佈局，**都只 import 這一個函數**。未來改測試慣例規則只改這裡，
搜 is_test_path 就全部出來、不漏改（= 用戶要的「同一身分只用一個名字呼叫」）。

判定依跨語言業界慣例（Python/JS/TS/Go/Rust/Java），純路徑字串判定（零 IO、確定性）。
"""
import re

# 目錄段：路徑任一層是這些目錄 → 測試（用 / 與 \ 都切）
_TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs", "testing", "e2e"}

# 檔名 regex：覆蓋各語言測試檔命名慣例
_TEST_FILE_PATTERNS = [
    re.compile(r"^test_.*\.py$"),         # pytest:  test_foo.py
    re.compile(r".*_test\.py$"),          # pytest:  foo_test.py
    re.compile(r"^conftest\.py$"),        # pytest fixture 中樞
    re.compile(r".*\.(test|spec)\.[jt]sx?$"),  # JS/TS: foo.test.ts / foo.spec.jsx
    re.compile(r".*_test\.go$"),          # Go:     foo_test.go
    re.compile(r".*_test\.rs$"),          # Rust:   foo_test.rs
    re.compile(r".*Test\.java$"),         # Java:   FooTest.java
    re.compile(r".*Tests\.java$"),        # Java:   FooTests.java
    re.compile(r".*Spec\.java$"),         # Java:   FooSpec.java
]


def is_test_path(path: str) -> bool:
    """path（相對或絕對皆可）是否屬測試碼。純字串判定、確定性、零 IO。"""
    if not path:
        return False
    parts = path.replace("\\", "/").split("/")
    # ① 任一目錄段命中測試目錄名（目錄名大小寫不敏感：Tests/ tests/ 皆算）
    if any(seg.lower() in _TEST_DIRS for seg in parts[:-1]):
        return True
    # ② 檔名命中測試檔慣例（保留原大小寫：Java FooTest.java 用 CamelCase，
    #    不全 lower 以免 latest.java 之類誤判；py/js/go/rust 慣例本就小寫副檔名）
    fname = parts[-1]
    return any(p.match(fname) for p in _TEST_FILE_PATTERNS)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    cases = [
        ("tests/test_engine.py", True),
        ("src/codesextant/engine.py", False),
        ("foo/bar_test.py", True),
        ("conftest.py", True),
        ("web/src/app.test.ts", True),
        ("web/src/app.spec.jsx", True),
        ("web/src/App.tsx", False),
        ("pkg/handler_test.go", True),
        ("pkg/handler.go", False),
        ("src/main/java/FooTest.java", True),
        (r"E:\proj\__tests__\helper.js", True),
        ("spec/models/user_spec.rb", True),  # 目錄段 spec
        ("e2e/login.ts", True),              # 目錄段 e2e
        ("src/contest.py", False),           # 不誤判 contest≠conftest
        ("src/latest/x.py", False),          # 不誤判 latest 含 test
        ("", False),
    ]
    ok = 0
    for p, want in cases:
        got = is_test_path(p)
        flag = "OK " if got == want else "FAIL"
        if got == want:
            ok += 1
        print(f"  {flag}  is_test_path({p!r}) = {got}  (期望 {want})")
    print(f"\n{ok}/{len(cases)} 通過")
    sys.exit(0 if ok == len(cases) else 1)
