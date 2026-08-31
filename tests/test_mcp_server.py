"""The calling convention is part of the feature.

Everything CodeSextant knows was already reachable before this server existed --
through the CLI, the client class, and HTTP. All three ask the agent to write code
first, and an agent weighing that against one ``rg`` call picks ``rg``. So these
tests pin the things that decide whether the tool is reached for at all: that the
handshake works with a real client's messages, that one malformed line does not end
the session, that a cold project answers instead of erroring, and that a tool that
cannot answer says why in a way the model can read and act on.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import textwrap
import urllib.error

import pytest

from codesextant import __version__, mcp_server, render


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "_db"))
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "core.py").write_text(textwrap.dedent("""
        def load_settings(path):
            return {"path": path}
    """).lstrip(), encoding="utf-8")
    (root / "tests_core.py").write_text("from core import load_settings\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    return root


def _server(project=None, backend=None):
    return mcp_server.MCPServer(
        backend or mcp_server.Backend(project, use_daemon=False))


def _initialized(project=None, backend=None):
    server = _server(project, backend)
    server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": mcp_server.PROTOCOL_VERSION,
                              "capabilities": {},
                              "clientInfo": {"name": "test", "version": "1"}}})
    return server


def _call(server, name, **arguments):
    return server.handle({"jsonrpc": "2.0", "id": 99, "method": "tools/call",
                          "params": {"name": name, "arguments": arguments}})


def _text(response) -> str:
    return response["result"]["content"][0]["text"]


# ── the handshake ────────────────────────────────────────────────────────────

def test_initialize_echoes_a_version_the_client_asked_for():
    server = _server()
    for version in mcp_server.SUPPORTED_PROTOCOL_VERSIONS:
        reply = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": version}})
        assert reply["result"]["protocolVersion"] == version


def test_initialize_answers_an_unknown_version_with_one_it_speaks():
    """Refusing would strand a client that could have negotiated down."""
    reply = _server().handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "1999-01-01"}})
    assert reply["result"]["protocolVersion"] == mcp_server.PROTOCOL_VERSION


def test_initialize_reports_the_package_version_and_says_when_to_call_preflight():
    result = _server().handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {}})["result"]
    assert result["serverInfo"]["version"] == __version__
    assert result["capabilities"]["tools"]["listChanged"] is False
    # The instructions are the only text every client is guaranteed to show the
    # model. If they do not say when to call preflight, nothing does.
    assert "preflight" in result["instructions"]
    assert "BEFORE" in result["instructions"]


def test_a_request_before_initialize_is_refused_with_the_remedy():
    reply = _server().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert reply["error"]["code"] == -32002
    assert "initialize" in reply["error"]["message"]


def test_ping_works_before_initialize():
    """A transport health check must not depend on session state."""
    reply = _server().handle({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert reply["result"] == {}


def test_notifications_get_no_reply():
    server = _initialized()
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/cancelled",
                          "params": {"requestId": 4}}) is None


def test_a_notification_that_fails_still_gets_no_reply():
    """A reply to a notification is a protocol violation, error or not."""
    server = _initialized()
    assert server.handle({"jsonrpc": "2.0", "method": "tools/call",
                          "params": {"name": "nope"}}) is None


def test_a_response_message_is_ignored_rather_than_answered():
    """Answering a response would ping-pong with the client forever."""
    assert _initialized().handle({"jsonrpc": "2.0", "id": 7, "result": {}}) is None


# ── the tool surface ─────────────────────────────────────────────────────────

def test_every_tool_declares_what_it_is_for_and_what_it_takes():
    tools = _initialized().handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert {t["name"] for t in tools} == set(mcp_server.TOOLS_BY_NAME)
    for tool in tools:
        assert tool["description"].strip()
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        # A required argument that is not described is a required argument the
        # model has to guess the meaning of.
        for name in schema.get("required", []):
            assert schema["properties"][name]["description"].strip()
        assert tool["annotations"]["readOnlyHint"] is (tool["name"] != "index")


def test_the_tool_surface_stays_small():
    """Eight sharp tools beat thirty-four: every tool is permanent context cost."""
    assert len(mcp_server.TOOLS) <= 10


def test_unknown_tool_names_the_ones_that_exist():
    reply = _call(_initialized(), "find_the_bug")
    assert reply["error"]["code"] == -32602
    assert "preflight" in reply["error"]["message"]


def test_a_missing_required_argument_is_a_protocol_error_naming_the_argument():
    reply = _call(_initialized(), "preflight")
    assert reply["error"]["code"] == -32602
    assert "'file'" in reply["error"]["message"]


def test_an_argument_of_the_wrong_type_says_what_was_expected():
    reply = _call(_initialized(), "preflight", file="a.py", budget=["not an int"])
    assert reply["error"]["code"] == -32602
    assert "budget" in reply["error"]["message"]


def test_unknown_methods_are_refused_without_ending_the_session():
    server = _initialized()
    assert server.handle({"jsonrpc": "2.0", "id": 3,
                          "method": "resources/list"})["error"]["code"] == -32601
    assert server.handle({"jsonrpc": "2.0", "id": 4, "method": "ping"})["result"] == {}


def test_comma_separated_lists_are_accepted_where_an_array_is_declared(repo, monkeypatch):
    """Models pass "a,b" for array arguments; rejecting it teaches nothing."""
    seen = {}

    def fake_get_map(project, token_budget=2000, focus_symbols=None, focus_files=None):
        seen.update(focus_files=focus_files, focus_symbols=focus_symbols)
        return {"count": 0, "symbols": [], "token_budget": token_budget, "approx_tokens": 0}

    monkeypatch.setattr(mcp_server, "engine", type("E", (), {"get_map": staticmethod(fake_get_map)}))
    _call(_initialized(str(repo)), "code_map", focus_files="a.py, b.py")
    assert seen["focus_files"] == ["a.py", "b.py"]


# ── answering ────────────────────────────────────────────────────────────────

def test_preflight_returns_the_three_pillars_as_text(repo):
    from codesextant import engine
    engine.index_project(str(repo), force=True)
    reply = _call(_initialized(str(repo)), "preflight",
                  file="core.py", symbol="load_settings")
    assert reply["result"]["isError"] is False
    text = _text(reply)
    assert "ALREADY EXISTS" in text
    assert "load_settings" in text
    # Paths are relative to the project the agent is working in, not absolute
    # machine paths that mean nothing to it.
    assert str(repo) not in text


def test_the_mcp_text_is_the_cli_text(repo):
    """One renderer, two surfaces: they cannot describe a result differently."""
    from codesextant import engine
    engine.index_project(str(repo), force=True)
    # Warm the reference resolution first. Otherwise whichever of the two calls runs
    # first resolves and reports what that cost, and the second -- correctly -- does
    # not, so the texts would differ over something other than the renderer.
    engine.preflight(str(repo), "core.py", symbol="load_settings")

    result = engine.preflight(str(repo), "core.py", symbol="load_settings")
    reply = _call(_initialized(str(repo)), "preflight",
                  file="core.py", symbol="load_settings")
    assert _text(reply) == "\n".join(render.preflight_lines(result, str(repo)))


def test_a_cold_project_is_indexed_once_and_says_so(repo):
    server = _initialized(str(repo))
    first = _text(_call(server, "preflight", file="core.py", symbol="load_settings"))
    assert "had never been indexed" in first
    assert "ALREADY EXISTS" in first  # the question asked still got answered
    # Saying it twice would be noise, and re-indexing would be worse than noise.
    second = _text(_call(server, "preflight", file="core.py", symbol="load_settings"))
    assert "had never been indexed" not in second
    assert "ALREADY EXISTS" in second


def test_a_tool_that_cannot_answer_reports_it_in_the_result_not_the_protocol(monkeypatch):
    """A JSON-RPC error is the client's problem; an isError result is the model's.

    The model is the only party that can pick a different approach, so the reason
    has to reach it.
    """
    def explode(*_args, **_kwargs):
        raise RuntimeError("jedi could not resolve the import root")

    monkeypatch.setattr(mcp_server, "engine",
                        type("E", (), {"find_references": staticmethod(explode)}))
    reply = _call(_initialized(), "find_references", symbol="whatever")
    assert "error" not in reply
    assert reply["result"]["isError"] is True
    assert "jedi could not resolve" in _text(reply)


# ── the transport ────────────────────────────────────────────────────────────

def test_one_malformed_line_does_not_end_the_session():
    """A client that sends garbage still has a session; dropping it loses the rest."""
    lines = [
        b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n',
        b'this is not json\n',
        b'\n',
        b'{"jsonrpc":"2.0","id":2,"method":"ping"}\n',
    ]
    out = io.BytesIO()
    _server().serve(iter(lines), out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r.get("id") for r in replies] == [1, None, 2]
    assert replies[1]["error"]["code"] == -32700
    assert replies[2]["result"] == {}


def test_batched_requests_are_refused_rather_than_half_answered():
    out = io.BytesIO()
    _server().serve(iter([b'[{"jsonrpc":"2.0","id":1,"method":"ping"}]\n']), out)
    reply = json.loads(out.getvalue())
    assert reply["error"]["code"] == -32600
    assert "batching" in reply["error"]["message"]


def test_every_reply_is_one_line_of_utf8():
    """A framing bug shows up in the client as an unrelated parse error."""
    out = io.BytesIO()
    _server().serve(iter([
        b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n',
        b'{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n']), out)
    raw = out.getvalue()
    assert raw.endswith(b"\n")
    assert len(raw.splitlines()) == 2
    for line in raw.splitlines():
        json.loads(line.decode("utf-8"))


def test_the_real_process_speaks_the_protocol_on_stdout_alone(tmp_path):
    """Anything else printed under the server corrupts the stream it shares."""
    env = dict(os.environ, CODESEXTANT_HOME=str(tmp_path / "_db"),
               CODESEXTANT_MCP_NO_DAEMON="1")
    handshake = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": mcp_server.PROTOCOL_VERSION}}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
    done = subprocess.run([sys.executable, "-m", "codesextant", "mcp", str(tmp_path)],
                          input=handshake, capture_output=True, text=True,
                          env=env, timeout=180)
    assert done.returncode == 0
    replies = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
    assert [r["id"] for r in replies] == [1, 2]
    assert {t["name"] for t in replies[1]["result"]["tools"]} == set(mcp_server.TOOLS_BY_NAME)


# ── which process answers ────────────────────────────────────────────────────

class _StubClient:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = 0

    def status(self, project=None, fresh=False):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return {"indexed": True, "repo_path": project, "indexed_files": 3,
                "symbols": 9, "refs": 2}


def _backend_with(client, monkeypatch, direct):
    backend = mcp_server.Backend("/somewhere")
    backend._client = client  # the seam: a daemon that is already "connected"
    monkeypatch.setattr(mcp_server, "engine", type("E", (), {"status": staticmethod(direct)}))
    return backend


def test_the_shared_daemon_answers_when_it_is_up(monkeypatch):
    """One index and one process for every agent on the machine, not one each."""
    client = _StubClient()
    backend = _backend_with(client, monkeypatch, lambda *_a, **_k: pytest.fail("used engine"))
    text = _text(_call(_initialized(backend=backend), "status"))
    assert client.calls == 1
    assert "3 file(s)" in text


def test_a_daemon_that_will_not_talk_falls_back_in_process_and_says_so(monkeypatch):
    """Failing here would teach the agent to stop calling CodeSextant at all."""
    client = _StubClient(failure=ConnectionRefusedError("connection refused"))
    backend = _backend_with(client, monkeypatch,
                            lambda *_a, **_k: {"indexed": True, "repo_path": "/somewhere",
                                               "indexed_files": 3, "symbols": 9, "refs": 2})
    text = _text(_call(_initialized(backend=backend), "status"))
    assert "Answered in this process" in text
    assert "3 file(s)" in text
    # And it stays fallen back rather than paying the timeout on every call.
    assert backend._daemon() is None


def test_a_busy_daemon_is_not_second_guessed_by_rerunning_the_query_here(monkeypatch):
    """A timeout means the work is already too slow; doing it twice makes it worse."""
    client = _StubClient(failure=TimeoutError("query timed out"))
    backend = _backend_with(client, monkeypatch, lambda *_a, **_k: pytest.fail("used engine"))
    reply = _call(_initialized(backend=backend), "status")
    assert reply["result"]["isError"] is True
    assert "timed out" in _text(reply)


def test_an_answer_of_no_from_the_daemon_is_not_retried_locally(monkeypatch):
    """An HTTP error is the daemon answering. Re-asking in-process changes nothing."""
    failure = urllib.error.HTTPError(
        "http://localhost/status", 400, "Bad Request", {},
        io.BytesIO(json.dumps({"error": "project= is required"}).encode()))
    client = _StubClient(failure=failure)
    backend = _backend_with(client, monkeypatch, lambda *_a, **_k: pytest.fail("used engine"))
    reply = _call(_initialized(backend=backend), "status")
    assert reply["result"]["isError"] is True
    # The daemon's real reason, not "HTTP Error 400: Bad Request".
    assert "project= is required" in _text(reply)


def test_a_daemon_reason_survives_being_read_twice():
    """The body of an HTTP response can be read once; this code reads it twice.

    Classifying an error and reporting it are separate steps, and without a cache
    the second one gets an empty body and reports "HTTP Error 500: Internal Server
    Error" -- the exact useless message reading the body was meant to replace.
    """
    failure = urllib.error.HTTPError(
        "http://localhost/preflight", 500, "Internal Server Error", {},
        io.BytesIO(json.dumps({"error": "RuntimeError: preflight: project has not "
                                        "been indexed yet"}).encode()))
    first = mcp_server._error_text(failure)
    assert "has not been indexed" in first
    assert mcp_server._error_text(failure) == first


def test_the_no_daemon_switch_is_not_reported_as_a_degradation():
    """It was asked for. Announcing it on every answer would be noise."""
    backend = mcp_server.Backend("/somewhere", use_daemon=False)
    assert backend.take_notes() == []
    assert backend._daemon() is None
