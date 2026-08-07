"""AI usage scan layer: provider detection, channel classification, HUD output.

The invariants these tests hold:
  - direct (a violation): calling the Anthropic or OpenAI API straight, langchain
    wrappers included, gives channel=direct and marks the file as a violation.
  - cli (compliant): claude --print, claude_code_sdk or an <x>-cli subprocess gives
    channel=cli and is not a violation.
  - local (nothing metered): an ollama localhost base_url gives channel=local and is not
    a violation, because flagging local inference would be the worst kind of noise.
  - OpenAI-compatible disambiguation: DeepSeek and Groq ride the openai SDK, so base_url
    is what tells them apart. They resolve to the real provider, not to OpenAI.
  - False-positive guards: a bare "langchain" or "generate_content" word with no real
    import produces no node at all.
  - An empty repo degrades gracefully. The HUD HTML is non-empty, carries window.GRAPH,
    and escapes anything that could inject script.

Pure scanning, with no dependency on the daemon or the index. CODESEXTANT_HOME is
redirected per test, the same way test_deadcode.py does it.
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


# ---- direct calls, which count as violations ----
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
        # The wrapper still hits the metered API endpoint, so it is a violation.
        _write(tmp_path, "pipe.py", "from langchain_anthropic import ChatAnthropic\nllm = ChatAnthropic()\n")
        r = engine.find_ai_usage(str(tmp_path))
        p = _files(r)["pipe.py"]
        assert p["violation"] is True
        assert ("anthropic", "direct") in _channels(p)


# ---- CLI calls, which are compliant ----
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


# ---- telling OpenAI-compatible providers apart ----
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
        assert "openai" not in provs  # base_url decides it, so no OpenAI misfire
        assert ("deepseek", "direct") in _channels(node)

    def test_plain_openai_is_direct_violation(self, tmp_path, db_home):
        # No base_url means plain OpenAI direct, which counts as a violation too.
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


# ---- local inference: nothing metered, so not a violation ----
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
        assert node["violation"] is False  # runs locally, nothing is metered
        assert ("ollama", "local") in _channels(node)
        assert r["stats"]["local"] >= 1
        assert _provs(r)["ollama"]["channel"] == "local"


# ---- false-positive guards ----
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


# ---- empty repos and the result contract ----
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
        assert json.dumps(r, ensure_ascii=False)  # must not raise

    def test_scope_file_limits_scan(self, tmp_path, db_home):
        _write(tmp_path, "a.py", "from anthropic import Anthropic\nc = Anthropic()\n")
        b = _write(tmp_path, "b.py", "from openai import OpenAI\nc = OpenAI()\n")
        r = engine.find_ai_usage(str(tmp_path), scope_file=b)
        labels = set(_files(r))
        assert labels == {"b.py"}


# ---- HUD HTML output ----
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
        assert "%%GRAPH_JSON%%" not in html  # the placeholder was substituted
        # Snippets go through the front-end esc(), so no raw unescaped <script> may
        # reach the GRAPH data.
        assert "<script>alert(1)</script>" not in html

    def test_render_empty_repo(self, tmp_path, db_home):
        _write(tmp_path, "plain.py", "def f():\n    return 1\n")
        r = engine.find_ai_usage(str(tmp_path))
        html = ai_usage_html.render_ai_usage(r)
        assert "window.GRAPH" in html and "<svg" in html


# ---- scan layer, pure unit tests ----
class TestScanUnit:
    def test_resolve_openai_local_priority(self):
        assert ai_usage._resolve_openai_call(set(), None, True) == ("ollama", "local")

    def test_resolve_openai_base_provider(self):
        assert ai_usage._resolve_openai_call({"openai"}, "deepseek", False) == ("deepseek", "direct")

    def test_resolve_openai_plain(self):
        assert ai_usage._resolve_openai_call({"openai"}, None, False) == ("openai", "direct")

    def test_resolve_openai_no_context_skipped(self):
        assert ai_usage._resolve_openai_call(set(), None, False) == (None, "direct")
