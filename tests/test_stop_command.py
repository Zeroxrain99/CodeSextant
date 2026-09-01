"""`codesextant stop` must be able to say no without starting anything.

Two things are pinned here, and the second one is the more embarrassing.

**It must not start a daemon.** Every other client call goes through `_open_json`,
which survives a dead daemon by starting one. For `stop` that is backwards, and the
first version got it wrong twice over: asking to stop when nothing was running spawned
a daemon and then failed with `self-heal failed: spawn-timeout`, and the dropped
connection after a successful shutdown spawned a replacement for the process just
stopped. A stop command that starts a process is worse than no stop command, because
somebody would believe it.

**There must be exactly one of it.** `daemon.stop_running` and the `/_shutdown` route
already existed when a second endpoint, a second client method and a second drain
confirmation were written next to them -- in the same file, by an author with that file
open. That is the failure this whole project is about, committed by the project, and
`test_one_shutdown_path` is what stops it happening a third time.
"""
from __future__ import annotations

import urllib.error

import pytest

from codesextant import client as client_module
from codesextant import daemon


def _fail_on_ensure(*_a, **_k):
    raise AssertionError("stop must never start a daemon")


@pytest.fixture
def api(monkeypatch):
    api = client_module.CodesextantClient(project="/tmp", port=8799)
    monkeypatch.setattr(api, "ensure", _fail_on_ensure)
    monkeypatch.setattr(client_module.daemon, "ensure_running", _fail_on_ensure)
    return api


def test_one_shutdown_path():
    """One endpoint and one function, because there were briefly two of each."""
    routes = set(daemon._ROUTES_POST) | set(daemon._ROUTES_GET)
    shutdown_routes = {path for path in routes if "shutdown" in path}
    assert shutdown_routes == set(), (
        "shutdown is handled directly in the POST handler so it can enforce hmac auth "
        f"and reply 202 before draining; found route(s) {shutdown_routes}")
    # One function owns the transport. `_stop_impl` is the name the client is bound to,
    # so a second implementation would have to rebind it here to pass.
    import inspect
    body = inspect.getsource(client_module.CodesextantClient.stop)
    assert "daemon.stop_running(" in body
    assert "urlopen" not in body and "Request(" not in body, (
        "the client must call stop_running, not build a second shutdown request")


def test_absent_daemon_is_reported_without_starting_one(monkeypatch, api):
    monkeypatch.setattr(client_module.daemon, "stop_running",
                        lambda port=None: {"action": "not-running", "port": port})
    result = api.stop()
    assert result["stopped"] is False
    assert result["daemon_present"] is False
    assert "no daemon" in result["reason"]


def test_refused_proof_is_not_reported_as_nothing_to_stop(monkeypatch, api):
    monkeypatch.setattr(
        client_module.daemon, "stop_running",
        lambda port=None: {"action": "shutdown-refused", "pid": 7, "port": port,
                           "error": "the daemon rejected the request proof (HTTP 403)"})
    result = api.stop()
    assert result["stopped"] is False
    # The distinction an early version lost: a process is still on this machine.
    assert result["daemon_present"] is True
    assert "rejected" in result["reason"]


def test_a_daemon_that_will_not_drain_is_reported_not_guessed(monkeypatch, api):
    monkeypatch.setattr(
        client_module.daemon, "stop_running",
        lambda port=None: {"action": "draining", "pid": 7, "port": port,
                           "port_released": False})
    result = api.stop()
    assert result["stopped"] is True
    assert result["drained"] is False


def test_stop_waits_for_the_process_not_just_the_port(monkeypatch):
    """"Stopped" has to mean stopped.

    The daemon replies before it exits and then drains in-flight work. The port closing
    is not the end of that: the refusal the next command meets is keyed on the lifetime
    lock, so confirming the port alone reported "stopped" while `ensure` 0.2s later was
    still refused with `daemon-draining`.
    """
    monkeypatch.setenv("CODESEXTANT_STOP_DRAIN_SEC", "5")
    monkeypatch.setattr(daemon, "http_ping", lambda port=None, **_k: (
        {"pid": 7, "api_version": daemon.API_VERSION} if _first_call(pings) else None))
    pings = {"n": 0}

    def _first_call(state):
        state["n"] += 1
        return state["n"] == 1

    posted = {}
    monkeypatch.setattr(daemon, "_health_api_current", lambda _h: True)
    monkeypatch.setattr(daemon, "is_port_listening", lambda port=None, **_k: False)
    monkeypatch.setattr(daemon.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse(posted))

    lock_still_held = {"n": 0}

    def _owner(_port):
        lock_still_held["n"] += 1
        return None if lock_still_held["n"] > 2 else {"action": "daemon-draining"}

    monkeypatch.setattr(daemon, "_instance_owner_result", _owner)

    result = daemon.stop_running(port=8799)
    assert result["action"] == "stopped"
    assert lock_still_held["n"] > 2, "it must keep asking the lock, not only the port"


class _FakeResponse:
    status = 202

    def __init__(self, sink):
        sink["called"] = True

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self):
        return b""


def test_a_refusal_is_not_reported_as_unreachable(monkeypatch):
    """HTTP 403 means it was reached, answered, and said no."""
    monkeypatch.setattr(daemon, "http_ping",
                        lambda port=None, **_k: {"pid": 7})
    monkeypatch.setattr(daemon, "_health_api_current", lambda _h: True)

    def _forbidden(*_a, **_k):
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8799/_shutdown", 403, "Forbidden", {}, None)

    monkeypatch.setattr(daemon.urllib.request, "urlopen", _forbidden)
    result = daemon.stop_running(port=8799)
    assert result["action"] == "shutdown-refused"
    assert result["status"] == 403


def test_cli_exits_non_zero_while_a_daemon_is_still_resident(monkeypatch, capsys):
    from codesextant import __main__ as cli

    monkeypatch.setattr(
        client_module.CodesextantClient, "stop",
        lambda self: {"stopped": False, "daemon_present": True,
                      "reason": "it rejected the request proof"})
    code = cli.cmd_stop(object())
    out = capsys.readouterr().out
    assert code == 1
    assert "still running" in out
    # "It starts again by itself" is a reassurance about an absence. Printing it while
    # the process is still up tells the user the opposite of the truth.
    assert "starts again" not in out


def test_cli_exits_zero_when_there_was_nothing_to_stop(monkeypatch, capsys):
    from codesextant import __main__ as cli

    monkeypatch.setattr(
        client_module.CodesextantClient, "stop",
        lambda self: {"stopped": False, "daemon_present": False,
                      "reason": "no daemon was running"})
    assert cli.cmd_stop(object()) == 0
    assert "Nothing to stop" in capsys.readouterr().out


def test_cli_does_not_promise_a_restart_while_the_daemon_is_draining(monkeypatch, capsys):
    from codesextant import __main__ as cli

    monkeypatch.setattr(
        client_module.CodesextantClient, "stop",
        lambda self: {"stopped": True, "pid": 7, "drained": False})
    assert cli.cmd_stop(object()) == 0
    out = capsys.readouterr().out
    assert "finishing work" in out
    assert "starts again" not in out
