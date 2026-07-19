"""階段2 硬化測試（坑表 9/7/6）＋對抗 review 抓到的破口回歸測試。

- 坑9：找引用時 symbol 查無候選定義（def_path=None）且 jedi 也找不到定義時，取樣
       專案主語言做 **fallback**（非 override），避免非 Python symbol 走死路；
       ⚠ jedi 對 Python 的能力不被奪走（pit9-1 回歸測試）。
- 坑6：git HEAD sha freshness——index 記 sha，status(check_freshness=True) 比對；
       git 壞掉時回 git_stale=None 不謊報新鮮（pit6-1）。
- 坑7：daemon POST CSRF + Tauri v2(tauri.localhost) 放行 + ipaddress loopback。

全自包含、可重複（照 test_codesextant.py 風格）。
"""
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine  # noqa: E402


@pytest.fixture()
def db_home(tmp_path, monkeypatch):
    """隔離庫目錄，避免污染真實 ~/.codesextant。"""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))


def _write(root, rel, content):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


# ─────────────── 坑9：def_path=None 語言判定（fallback 而非 override）───────────────

class TestPit9InferLanguage:
    def test_infer_ts_project(self, tmp_path):
        _write(tmp_path, "a.ts", "export function foo() { return 1; }\n")
        _write(tmp_path, "b.ts", "export const bar = 2;\n")
        assert engine._infer_project_language(str(tmp_path)) == "typescript"

    def test_infer_python_project(self, tmp_path):
        _write(tmp_path, "a.py", "def foo():\n    return 1\n")
        assert engine._infer_project_language(str(tmp_path)) == "python"

    def test_infer_empty_returns_none(self, tmp_path):
        assert engine._infer_project_language(str(tmp_path)) is None

    def test_infer_mixed_below_ratio_returns_none(self, tmp_path):
        # pit9-4：50/50 混合未達門檻(0.6) → 回 None 走保守 jedi（決定性、不依 walk 順序）
        for i in range(5):
            _write(tmp_path, f"t{i}.ts", "export const x = 1;\n")
        for i in range(5):
            _write(tmp_path, f"p{i}.py", "x = 1\n")
        assert engine._infer_project_language(str(tmp_path)) is None

    def test_infer_disabled_env_lowercase_robust(self, tmp_path, monkeypatch):
        # pit9-3：開關須 .lower() 容錯——大寫 True 也要能關
        _write(tmp_path, "a.ts", "export const x = 1;\n")
        monkeypatch.setenv("CODESEXTANT_INFER_LANG_DISABLED", "True")
        assert engine._infer_project_language(str(tmp_path)) is None
        monkeypatch.setenv("CODESEXTANT_INFER_LANG_DISABLED", "1")
        assert engine._infer_project_language(str(tmp_path)) is None

    def test_infer_min_ratio_env_tunable(self, tmp_path, monkeypatch):
        # pit9-2：門檻可調——把門檻降到 0.4，50/50 就會選出主導語言
        for i in range(6):
            _write(tmp_path, f"t{i}.ts", "export const x = 1;\n")
        for i in range(4):
            _write(tmp_path, f"p{i}.py", "x = 1\n")
        monkeypatch.setenv("CODESEXTANT_INFER_LANG_MIN_RATIO", "0.5")
        assert engine._infer_project_language(str(tmp_path)) == "typescript"

    def test_find_refs_ts_fallback_not_jedi(self, tmp_path, db_home):
        # 純 TS repo 查未索引 symbol → jedi 先跑找不到定義 → fallback inferred=ts
        _write(tmp_path, "a.ts", "export function realFn() { return 1; }\n")
        engine.index_project(str(tmp_path))
        res = engine.find_references(str(tmp_path), "nonexistentSymbolXYZ")
        assert res["language"] != "python"

    def test_find_refs_python_unchanged(self, tmp_path, db_home):
        # 純 Python 專案查未索引 symbol → jedi（language=python，行為不變）
        _write(tmp_path, "a.py", "def realFn():\n    return 1\n")
        engine.index_project(str(tmp_path))
        res = engine.find_references(str(tmp_path), "nonexistentSymbolXYZ")
        assert res["language"] == "python"

    def test_mixed_repo_python_not_regressed(self, tmp_path, db_home):
        # ⭐pit9-1 回歸：TS 多於 Py 的「未索引」repo，查真實 Python symbol（def_path=None）
        # → jedi 先跑掃磁碟找到定義（不被 inferred=ts override 奪走能力＝fallback 而非 override）
        for i in range(8):
            _write(tmp_path, f"ui/c{i}.tsx", f"export const C{i} = {i};\n")
        _write(tmp_path, "pay.py", "def process_payment(amount):\n    return amount * 2\n")
        _write(tmp_path, "app.py",
               "from pay import process_payment\n"
               "def run():\n    return process_payment(10) + process_payment(20)\n")
        # ⛔ 不 index（db 不存在 → candidate_defs=[] → def_path=None），且 TS 佔 80%
        res = engine.find_references(str(tmp_path), "process_payment")
        assert res["language"] == "python"  # jedi 找到、不被 inferred=tsx override
        assert res.get("definition") is not None  # 定義沒被誤丟


# ─────────────── 坑6：git HEAD sha freshness ───────────────

class TestPit6GitFreshness:
    @staticmethod
    def _git(cwd, *args):
        import subprocess
        subprocess.run(["git", "-C", cwd, *args], capture_output=True, check=True)

    def _new_repo(self, tmp_path):
        repo = tmp_path / "proj"
        repo.mkdir()
        r = str(repo)
        self._git(r, "init")
        self._git(r, "config", "user.email", "t@t.com")
        self._git(r, "config", "user.name", "t")
        return repo

    def test_default_status_no_freshness(self, tmp_path, db_home):
        # pit7-1：預設 status 不查 git（不 spawn）→ 無 git_stale/current_git_sha key
        repo = self._new_repo(tmp_path)
        _write(repo, "a.py", "x = 1\n")
        self._git(str(repo), "add", "-A")
        self._git(str(repo), "commit", "-m", "c1")
        engine.index_project(str(repo))
        st = engine.status(str(repo))  # 不帶 check_freshness
        assert "git_stale" not in st
        assert "current_git_sha" not in st
        assert st["indexed_git_sha"] is not None  # 索引時有記（stats 一律回）

    def test_stale_after_new_commit(self, tmp_path, db_home):
        repo = self._new_repo(tmp_path)
        _write(repo, "a.py", "def foo():\n    return 1\n")
        self._git(str(repo), "add", "-A")
        self._git(str(repo), "commit", "-m", "c1")
        engine.index_project(str(repo))
        st1 = engine.status(str(repo), check_freshness=True)
        assert st1["indexed_git_sha"] is not None
        assert st1["git_stale"] is False  # 剛索引，sha 相同
        _write(repo, "b.py", "def bar():\n    return 2\n")
        self._git(str(repo), "add", "-A")
        self._git(str(repo), "commit", "-m", "c2")
        st2 = engine.status(str(repo), check_freshness=True)
        assert st2["current_git_sha"] != st1["indexed_git_sha"]
        assert st2["git_stale"] is True

    def test_git_unavailable_stale_none(self, tmp_path, db_home):
        # ⭐pit6-1：索引後 git 壞掉（.git 改名）→ git_stale=None（不謊報 False 新鮮）
        repo = self._new_repo(tmp_path)
        _write(repo, "a.py", "x = 1\n")
        self._git(str(repo), "add", "-A")
        self._git(str(repo), "commit", "-m", "c1")
        engine.index_project(str(repo))
        os.rename(str(repo / ".git"), str(repo / ".git_disabled"))  # 模擬 git 壞
        st = engine.status(str(repo), check_freshness=True)
        assert st["indexed_git_sha"] is not None  # 索引時記過
        assert st["current_git_sha"] is None       # 現在取不到
        assert st["git_stale"] is None             # ⛔ 不可 False 謊報新鮮
        assert "git_note" in st

    def test_non_git_repo_not_stale(self, tmp_path, db_home):
        _write(tmp_path, "a.py", "def foo():\n    return 1\n")
        engine.index_project(str(tmp_path))
        st = engine.status(str(tmp_path), check_freshness=True)
        assert st["indexed_git_sha"] is None
        assert st["git_stale"] is False

    def test_freshness_disabled_env_lowercase_robust(self, tmp_path, db_home, monkeypatch):
        # pit6 開關 .lower() 容錯——大寫 TRUE 也要能關
        repo = self._new_repo(tmp_path)
        _write(repo, "a.py", "x = 1\n")
        self._git(str(repo), "add", "-A")
        self._git(str(repo), "commit", "-m", "c1")
        monkeypatch.setenv("CODESEXTANT_GIT_FRESHNESS_DISABLED", "TRUE")
        engine.index_project(str(repo))
        st = engine.status(str(repo), check_freshness=True)
        assert st["indexed_git_sha"] is None  # 開關關 → 不記 sha
        assert st["git_stale"] is False


# ─────────────── 坑7：localhost CSRF ───────────────

class TestPit7Csrf:
    @staticmethod
    def _check(origin):
        import types

        from codesextant.daemon import _Handler
        fake = types.SimpleNamespace(headers={"Origin": origin} if origin else {})
        return _Handler._csrf_check(fake)

    def test_no_origin_allowed(self):
        assert self._check(None) is True

    def test_localhost_allowed(self):
        assert self._check("http://127.0.0.1:8790") is True
        assert self._check("http://localhost:3000") is True
        assert self._check("http://[::1]:8790") is True

    def test_tauri_v1_vscode_webview_allowed(self):
        assert self._check("tauri://localhost") is True
        assert self._check("vscode-webview://abc123def") is True

    def test_tauri_v2_localhost_allowed(self):
        # ⭐pit7-2：Tauri v2(Windows/Linux) 真實 Origin https://tauri.localhost 不可誤擋
        assert self._check("https://tauri.localhost") is True
        assert self._check("http://tauri.localhost") is True

    def test_ipv6_loopback_variants_allowed(self):
        # pit7-3：::1 的展開寫法與 IPv4-mapped loopback 也放行（ipaddress.is_loopback）
        assert self._check("http://[0:0:0:0:0:0:0:1]:8790") is True
        assert self._check("http://127.0.0.1") is True

    def test_null_origin_allowed(self):
        assert self._check("null") is True  # file:// 載入的本機面板

    def test_external_origin_blocked(self):
        assert self._check("http://evil.example.com") is False
        assert self._check("https://attacker.test") is False

    def test_prefix_bypass_blocked(self):
        # 裸 startswith 會被惡意域名前綴繞過 → urlparse 精確比對 host 必擋
        assert self._check("http://127.0.0.1.evil.com") is False
        assert self._check("http://localhost.attacker.test") is False
        assert self._check("http://127.0.0.1@evil.com") is False
        assert self._check("http://tauri.localhost.evil.com") is False  # pit7-2 衍生

    def test_guard_disabled_env_lowercase_robust(self, monkeypatch):
        # CSRF 開關 .lower() 容錯——大寫 FALSE 也要能關
        monkeypatch.setenv("CODESEXTANT_CSRF_GUARD", "FALSE")
        assert self._check("http://evil.example.com") is True
        monkeypatch.setenv("CODESEXTANT_CSRF_GUARD", "0")
        assert self._check("http://evil.example.com") is True
