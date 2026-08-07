"""Hardening tests for pitfalls 9, 7 and 6, plus regressions covering the holes
an adversarial review turned up.

- Pitfall 9: when a reference lookup finds no candidate definition
  (def_path=None) and jedi cannot find one either, the project's dominant
  language is sampled as a fallback, not as an override, so a non-Python symbol
  does not hit a dead end. jedi keeps its Python capability, which is what the
  pit9-1 regression pins down.
- Pitfall 6: git HEAD sha freshness. Indexing records the sha and
  status(check_freshness=True) compares against it. If git breaks, the answer is
  git_stale=None rather than a false claim of freshness (pit6-1).
- Pitfall 7: CSRF on daemon POST, letting Tauri v2 (tauri.localhost) through,
  and loopback checks via ipaddress.

Self-contained and repeatable, in the style of test_codesextant.py.
"""
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import engine  # noqa: E402


@pytest.fixture()
def db_home(tmp_path, monkeypatch):
    """Isolate the database directory so the real ~/.codesextant stays clean."""
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))


def _write(root, rel, content):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


# Pitfall 9: language inference when def_path is None, used as a fallback and
# never as an override.

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
        # pit9-4: an even mix misses the 0.6 threshold, so this returns None and
        # falls back to jedi. The result is deterministic, not walk-order dependent.
        for i in range(5):
            _write(tmp_path, f"t{i}.ts", "export const x = 1;\n")
        for i in range(5):
            _write(tmp_path, f"p{i}.py", "x = 1\n")
        assert engine._infer_project_language(str(tmp_path)) is None

    def test_infer_disabled_env_lowercase_robust(self, tmp_path, monkeypatch):
        # pit9-3: the switch goes through .lower(), so an uppercase True disables it
        _write(tmp_path, "a.ts", "export const x = 1;\n")
        monkeypatch.setenv("CODESEXTANT_INFER_LANG_DISABLED", "True")
        assert engine._infer_project_language(str(tmp_path)) is None
        monkeypatch.setenv("CODESEXTANT_INFER_LANG_DISABLED", "1")
        assert engine._infer_project_language(str(tmp_path)) is None

    def test_infer_min_ratio_env_tunable(self, tmp_path, monkeypatch):
        # pit9-2: the threshold is tunable, so lowering it lets an uneven split
        # resolve to the dominant language
        for i in range(6):
            _write(tmp_path, f"t{i}.ts", "export const x = 1;\n")
        for i in range(4):
            _write(tmp_path, f"p{i}.py", "x = 1\n")
        monkeypatch.setenv("CODESEXTANT_INFER_LANG_MIN_RATIO", "0.5")
        assert engine._infer_project_language(str(tmp_path)) == "typescript"

    def test_find_refs_ts_fallback_not_jedi(self, tmp_path, db_home):
        # in a pure TS repo an unindexed symbol goes to jedi first, jedi finds no
        # definition, and the inferred TS language takes over as the fallback
        _write(tmp_path, "a.ts", "export function realFn() { return 1; }\n")
        engine.index_project(str(tmp_path))
        res = engine.find_references(str(tmp_path), "nonexistentSymbolXYZ")
        assert res["language"] != "python"

    def test_find_refs_python_unchanged(self, tmp_path, db_home):
        # the same lookup in a pure Python project stays with jedi, so
        # language=python and the behaviour is unchanged
        _write(tmp_path, "a.py", "def realFn():\n    return 1\n")
        engine.index_project(str(tmp_path))
        res = engine.find_references(str(tmp_path), "nonexistentSymbolXYZ")
        assert res["language"] == "python"

    def test_mixed_repo_python_not_regressed(self, tmp_path, db_home):
        # pit9-1 regression: an unindexed repo holding more TS than Python, queried
        # for a real Python symbol (def_path=None). jedi runs first, scans disk and
        # finds the definition, because inferring TS is a fallback and never takes
        # that capability away.
        for i in range(8):
            _write(tmp_path, f"ui/c{i}.tsx", f"export const C{i} = {i};\n")
        _write(tmp_path, "pay.py", "def process_payment(amount):\n    return amount * 2\n")
        _write(tmp_path, "app.py",
               "from pay import process_payment\n"
               "def run():\n    return process_payment(10) + process_payment(20)\n")
        # deliberately not indexed: with no db, candidate_defs is empty and
        # def_path is None, while TS accounts for 80% of the files
        res = engine.find_references(str(tmp_path), "process_payment")
        assert res["language"] == "python"  # jedi found it; inferring tsx did not win
        assert res.get("definition") is not None  # the definition was not dropped


# Pitfall 6: git HEAD sha freshness.

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
        # pit7-1: status does not consult git by default, so nothing is spawned and
        # neither git_stale nor current_git_sha appears in the result
        repo = self._new_repo(tmp_path)
        _write(repo, "a.py", "x = 1\n")
        self._git(str(repo), "add", "-A")
        self._git(str(repo), "commit", "-m", "c1")
        engine.index_project(str(repo))
        st = engine.status(str(repo))  # no check_freshness argument
        assert "git_stale" not in st
        assert "current_git_sha" not in st
        assert st["indexed_git_sha"] is not None  # recorded at index time; stats always return it

    def test_stale_after_new_commit(self, tmp_path, db_home):
        repo = self._new_repo(tmp_path)
        _write(repo, "a.py", "def foo():\n    return 1\n")
        self._git(str(repo), "add", "-A")
        self._git(str(repo), "commit", "-m", "c1")
        engine.index_project(str(repo))
        st1 = engine.status(str(repo), check_freshness=True)
        assert st1["indexed_git_sha"] is not None
        assert st1["git_stale"] is False  # just indexed, so the sha still matches
        _write(repo, "b.py", "def bar():\n    return 2\n")
        self._git(str(repo), "add", "-A")
        self._git(str(repo), "commit", "-m", "c2")
        st2 = engine.status(str(repo), check_freshness=True)
        assert st2["current_git_sha"] != st1["indexed_git_sha"]
        assert st2["git_stale"] is True

    def test_git_unavailable_stale_none(self, tmp_path, db_home):
        # pit6-1: git breaks after indexing (.git gets renamed), so git_stale comes
        # back as None instead of a False that would claim the index is fresh
        repo = self._new_repo(tmp_path)
        _write(repo, "a.py", "x = 1\n")
        self._git(str(repo), "add", "-A")
        self._git(str(repo), "commit", "-m", "c1")
        engine.index_project(str(repo))
        os.rename(str(repo / ".git"), str(repo / ".git_disabled"))  # simulate broken git
        st = engine.status(str(repo), check_freshness=True)
        assert st["indexed_git_sha"] is not None  # recorded while indexing
        assert st["current_git_sha"] is None       # unreadable now
        assert st["git_stale"] is None             # False here would be a lie about freshness
        assert "git_note" in st

    def test_non_git_repo_not_stale(self, tmp_path, db_home):
        _write(tmp_path, "a.py", "def foo():\n    return 1\n")
        engine.index_project(str(tmp_path))
        st = engine.status(str(tmp_path), check_freshness=True)
        assert st["indexed_git_sha"] is None
        assert st["git_stale"] is False

    def test_freshness_disabled_env_lowercase_robust(self, tmp_path, db_home, monkeypatch):
        # pit6: the switch goes through .lower(), so an uppercase TRUE disables it
        repo = self._new_repo(tmp_path)
        _write(repo, "a.py", "x = 1\n")
        self._git(str(repo), "add", "-A")
        self._git(str(repo), "commit", "-m", "c1")
        monkeypatch.setenv("CODESEXTANT_GIT_FRESHNESS_DISABLED", "TRUE")
        engine.index_project(str(repo))
        st = engine.status(str(repo), check_freshness=True)
        assert st["indexed_git_sha"] is None  # switch off, so no sha is recorded
        assert st["git_stale"] is False


# Pitfall 7: localhost CSRF.

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
        # pit7-2: Tauri v2 on Windows and Linux sends https://tauri.localhost as its
        # real Origin, so blocking it would break a legitimate client
        assert self._check("https://tauri.localhost") is True
        assert self._check("http://tauri.localhost") is True

    def test_ipv6_loopback_variants_allowed(self):
        # pit7-3: the expanded spelling of ::1 and IPv4-mapped loopback pass as
        # well, since ipaddress.is_loopback resolves both
        assert self._check("http://[0:0:0:0:0:0:0:1]:8790") is True
        assert self._check("http://127.0.0.1") is True

    def test_null_origin_allowed(self):
        assert self._check("null") is True  # a local panel loaded over file://

    def test_external_origin_blocked(self):
        assert self._check("http://evil.example.com") is False
        assert self._check("https://attacker.test") is False

    def test_prefix_bypass_blocked(self):
        # a bare startswith test lets a hostile domain slip in behind a matching
        # prefix, so urlparse compares the host exactly and rejects all of these
        assert self._check("http://127.0.0.1.evil.com") is False
        assert self._check("http://localhost.attacker.test") is False
        assert self._check("http://127.0.0.1@evil.com") is False
        assert self._check("http://tauri.localhost.evil.com") is False  # follows from pit7-2

    def test_guard_disabled_env_lowercase_robust(self, monkeypatch):
        # the CSRF switch goes through .lower(), so an uppercase FALSE disables it
        monkeypatch.setenv("CODESEXTANT_CSRF_GUARD", "FALSE")
        assert self._check("http://evil.example.com") is True
        monkeypatch.setenv("CODESEXTANT_CSRF_GUARD", "0")
        assert self._check("http://evil.example.com") is True
