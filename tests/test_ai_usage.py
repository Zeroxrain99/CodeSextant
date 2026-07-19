"""ai-usage 掃描層測試 — provider 偵測 + dispatch_policy 三通道分類 + HUD 產出。

守的不變式：
  - direct（違規）：直呼 Anthropic/OpenAI API（含 langchain wrapper）→ channel=direct、file violation=True。
  - cli（合規）：claude --print / claude_code_sdk / <x>-cli subprocess → channel=cli、非 violation。
  - local（本地無計費）：ollama localhost base_url → channel=local、非 violation（⛔ 不誤標違規）。
  - OpenAI-compat 消歧：DeepSeek/Groq 騎 openai SDK 靠 base_url 分家 → 解析成真 provider、非 OpenAI。
  - FP 護欄：langchain/generate_content 裸字（無真 import）不產生 node。
  - 空 repo graceful；HUD HTML 非空、含 window.GRAPH、XSS 跳脫。

純掃描（不依賴 daemon/index），照 test_deadcode.py 風格用 CODESEXTANT_HOME 隔離。
"""
import json
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import ai_usage, ai_usage_html, engine  # noqa: E402


@pytest.fixture()
def db_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))


def _write(root, rel, content):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


def _files(result):
    return {n["label"]: n for n in result["nodes"] if n["type"] == "file"}


def _provs(result):
    return {n["id"]: n for n in result["nodes"] if n["type"] == "provider"}


def _channels(fnode):
    return {(s["provider"], s["channel"]) for s in fnode["sites"]}


# ─────────────── direct 違規（Anthropic）───────────────
class TestDirectViolation:
    def test_anthropic_sdk_direct_is_violation(self, tmp_path, db_home):
        _write(tmp_path, "api.py", """
            from anthropic import Anthropic
            client = Anthropic()
            def f():
                return client.messages.create(model="x")
        """)
        r = engine.find_ai_usage(str(tmp_path))
        api = _files(r)["api.py"]
        assert api["violation"] is True
        assert ("anthropic", "direct") in _channels(api)
        assert r["stats"]["dispatch_violations"] >= 1

    def test_anthropic_http_host_direct(self, tmp_path, db_home):
        _write(tmp_path, "bench.py", """
            import requests
            def b():
                requests.post("https://api.anthropic.com/v1/messages", json=x)
        """)
        r = engine.find_ai_usage(str(tmp_path))
        assert _files(r)["bench.py"]["violation"] is True

    def test_langchain_anthropic_wrapper_is_violation(self, tmp_path, db_home):
        # wrapper 走 API metered endpoint = 違規（dispatch_policy 反 pattern）
        _write(tmp_path, "pipe.py", "from langchain_anthropic import ChatAnthropic\nllm = ChatAnthropic()\n")
        r = engine.find_ai_usage(str(tmp_path))
        p = _files(r)["pipe.py"]
        assert p["violation"] is True
        assert ("anthropic", "direct") in _channels(p)


# ─────────────── cli 合規 ───────────────
class TestCliCompliant:
    def test_claude_subprocess_is_cli(self, tmp_path, db_home):
        _write(tmp_path, "d.py", """
            import subprocess
            def d():
                subprocess.run(["claude", "--print", payload])
        """)
        r = engine.find_ai_usage(str(tmp_path))
        node = _files(r)["d.py"]
        assert node["violation"] is False
        assert ("anthropic", "cli") in _channels(node)
        assert r["stats"]["cli_compliant"] >= 1

    def test_claude_code_sdk_is_cli(self, tmp_path, db_home):
        _write(tmp_path, "r.py", "from claude_code_sdk import query\n")
        r = engine.find_ai_usage(str(tmp_path))
        assert _files(r)["r.py"]["violation"] is False
        assert ("anthropic", "cli") in _channels(_files(r)["r.py"])

    def test_generic_cli_captures_provider(self, tmp_path, db_home):
        _write(tmp_path, "s.py", """
            import subprocess
            def s():
                subprocess.run(["groq-cli", "run"])
        """)
        r = engine.find_ai_usage(str(tmp_path))
        assert ("groq", "cli") in _channels(_files(r)["s.py"])


# ─────────────── OpenAI-compat 消歧（載重正確性）───────────────
class TestOpenAICompatDisambiguation:
    def test_deepseek_via_base_url_not_openai(self, tmp_path, db_home):
        _write(tmp_path, "ds.py", """
            from openai import OpenAI
            client = OpenAI(base_url="https://api.deepseek.com")
            def h():
                return client.chat.completions.create(model="x")
        """)
        r = engine.find_ai_usage(str(tmp_path))
        node = _files(r)["ds.py"]
        provs = {s["provider"] for s in node["sites"]}
        assert "deepseek" in provs
        assert "openai" not in provs  # base_url 消歧：不誤判成 OpenAI
        assert ("deepseek", "direct") in _channels(node)

    def test_plain_openai_is_direct_violation(self, tmp_path, db_home):
        # 無 base_url → 純 OpenAI direct（user 2026-07-16：direct OpenAI 也算違規）
        _write(tmp_path, "oa.py", """
            from openai import OpenAI
            c = OpenAI()
            def z():
                return c.chat.completions.create(model="gpt")
        """)
        r = engine.find_ai_usage(str(tmp_path))
        node = _files(r)["oa.py"]
        assert ("openai", "direct") in _channels(node)
        assert node["violation"] is True


# ─────────────── local 本地（無計費·非違規）───────────────
class TestLocalChannel:
    def test_ollama_localhost_is_local_not_violation(self, tmp_path, db_home):
        _write(tmp_path, "gemma.py", """
            from openai import OpenAI
            c = OpenAI(base_url="http://127.0.0.1:11434/v1")
            def g():
                return c.chat.completions.create(model="gemma")
        """)
        r = engine.find_ai_usage(str(tmp_path))
        node = _files(r)["gemma.py"]
        assert node["violation"] is False  # 本地無計費，非違規
        assert ("ollama", "local") in _channels(node)
        assert r["stats"]["local"] >= 1
        assert _provs(r)["ollama"]["channel"] == "local"


# ─────────────── FP 護欄 ───────────────
class TestFalsePositiveGuards:
    def test_langchain_bareword_without_import_no_node(self, tmp_path, db_home):
        _write(tmp_path, "doc.py", """
            # langchain retrieval doc reference text
            X = "some langchain mention in a string"
            def helper():
                return 1
        """)
        r = engine.find_ai_usage(str(tmp_path))
        assert "doc.py" not in _files(r)

    def test_generate_content_without_google_import_ignored(self, tmp_path, db_home):
        _write(tmp_path, "t.py", """
            def test_filters_generate_content():
                x = "call generate_content here"
                return x
        """)
        r = engine.find_ai_usage(str(tmp_path))
        assert "t.py" not in _files(r)


# ─────────────── 空 repo / 契約 ───────────────
class TestContract:
    def test_empty_repo_graceful(self, tmp_path, db_home):
        _write(tmp_path, "plain.py", "def f():\n    return 1\n")
        r = engine.find_ai_usage(str(tmp_path))
        assert r["nodes"] == []
        assert r["edges"] == []
        assert r["stats"]["providers_detected"] == 0
        assert "read_code_advisory" in r and r["read_code_advisory"]
        assert "verification_reminder" in r and r["verification_reminder"]

    def test_bad_path_raises(self, db_home):
        with pytest.raises(NotADirectoryError):
            engine.find_ai_usage("E:/__no_such_dir_ai_usage__")

    def test_json_serializable(self, tmp_path, db_home):
        _write(tmp_path, "api.py", "from anthropic import Anthropic\nc = Anthropic()\n")
        r = engine.find_ai_usage(str(tmp_path))
        assert json.dumps(r, ensure_ascii=False)  # 不拋

    def test_scope_file_limits_scan(self, tmp_path, db_home):
        _write(tmp_path, "a.py", "from anthropic import Anthropic\nc = Anthropic()\n")
        b = _write(tmp_path, "b.py", "from openai import OpenAI\nc = OpenAI()\n")
        r = engine.find_ai_usage(str(tmp_path), scope_file=b)
        labels = set(_files(r))
        assert labels == {"b.py"}


# ─────────────── HUD HTML 產出 ───────────────
class TestHtmlRender:
    def test_render_nonempty_and_safe(self, tmp_path, db_home):
        _write(tmp_path, "api.py", """
            from anthropic import Anthropic
            c = Anthropic()
            def f():
                return c.messages.create(model="<script>alert(1)</script>")
        """)
        r = engine.find_ai_usage(str(tmp_path))
        html = ai_usage_html.render_ai_usage(r)
        assert "window.GRAPH" in html
        assert "<svg" in html
        assert "%%GRAPH_JSON%%" not in html  # placeholder 已替換
        # snippet 走前端 esc()，不得注入未跳脫的裸 <script> 進 GRAPH 資料
        assert "<script>alert(1)</script>" not in html

    def test_render_empty_repo(self, tmp_path, db_home):
        _write(tmp_path, "plain.py", "def f():\n    return 1\n")
        r = engine.find_ai_usage(str(tmp_path))
        html = ai_usage_html.render_ai_usage(r)
        assert "window.GRAPH" in html and "<svg" in html


# ─────────────── 掃描層純單元 ───────────────
class TestScanUnit:
    def test_resolve_openai_local_priority(self):
        assert ai_usage._resolve_openai_call(set(), None, True) == ("ollama", "local")

    def test_resolve_openai_base_provider(self):
        assert ai_usage._resolve_openai_call({"openai"}, "deepseek", False) == ("deepseek", "direct")

    def test_resolve_openai_plain(self):
        assert ai_usage._resolve_openai_call({"openai"}, None, False) == ("openai", "direct")

    def test_resolve_openai_no_context_skipped(self):
        assert ai_usage._resolve_openai_call(set(), None, False) == (None, "direct")
