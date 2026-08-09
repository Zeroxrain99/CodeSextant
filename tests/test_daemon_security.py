"""Security contracts for the loopback daemon and browser dashboard."""

from __future__ import annotations

import http.client
import json
import os
import re
import stat
import sys
import threading
import urllib.error
from contextlib import contextmanager

import pytest


@contextmanager
def _running_server():
    from codesextant import daemon

    server = daemon._ExclusiveThreadingHTTPServer((daemon.HOST, 0), daemon._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(port: int, method: str, path: str, *, headers=None, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    payload = response.read()
    result = response.status, dict(response.getheaders()), payload
    connection.close()
    return result


def _signed_headers(method: str, path: str, body: bytes = b"") -> dict[str, str]:
    from codesextant import local_auth

    return local_auth.request_headers(method, path, body)


def test_local_token_is_stable_and_private(tmp_path, monkeypatch):
    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path))
    from codesextant import local_auth

    first = local_auth.get_or_create_token()
    second = local_auth.get_or_create_token()

    assert first == second
    assert len(first) >= 43
    token_path = tmp_path / "daemon.token"
    assert token_path.read_text(encoding="ascii").strip() == first
    if os.name != "nt":
        assert stat.S_IMODE(token_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700


def test_all_daemon_routes_require_authentication(monkeypatch):
    from codesextant import daemon

    with _running_server() as port:
        status, headers, _ = _request(port, "GET", "/health")
        assert status == 401
        assert headers["Cache-Control"] == "no-store"

        status, _, payload = _request(
            port,
            "GET",
            "/health",
            headers=_signed_headers("GET", "/health"),
        )
        assert status == 200
        health = json.loads(payload)
        assert health["api_version"] == daemon.API_VERSION


def test_daemon_rejects_non_loopback_host_header():
    with _running_server() as port:
        status, _, _ = _request(
            port,
            "GET",
            "/health",
            headers={
                **_signed_headers("GET", "/health"),
                "Host": "attacker.example",
            },
        )
    assert status == 421


def test_experimental_graph_route_never_imports_an_unqualified_module(
        monkeypatch):
    from codesextant import daemon

    monkeypatch.delenv("CODESEXTANT_ENABLE_EXPERIMENTAL_STARMAP", raising=False)
    monkeypatch.setitem(sys.modules, "graph_api", object())
    parsed = daemon.urlparse("/graph_data?project=C%3A%5Crepo")

    with pytest.raises(daemon._HttpError) as raised:
        daemon._ep_graph_data(parsed, None)

    assert raised.value.code == 404
    assert sys.modules["graph_api"].__class__ is object


def test_browser_bootstrap_is_single_use_and_uses_port_scoped_session_storage():
    from codesextant import local_auth

    long_lived_secret = local_auth.get_or_create_token()
    with _running_server() as port:
        status, _, payload = _request(
            port,
            "POST",
            "/_browser_session",
            headers=_signed_headers("POST", "/_browser_session"),
        )
        assert status == 200
        bootstrap_path = json.loads(payload)["path"]
        assert long_lived_secret not in bootstrap_path

        status, headers, bootstrap_html = _request(port, "GET", bootstrap_path)
        assert status == 200
        assert "Set-Cookie" not in headers
        assert headers["Cache-Control"] == "no-store"
        assert headers["Referrer-Policy"] == "no-referrer"
        text = bootstrap_html.decode("utf-8")
        assert "sessionStorage.setItem" in text
        assert "localStorage" not in text
        assert "history.replaceState" in text
        assert long_lived_secret not in text
        match = re.search(
            r'sessionStorage\.setItem\("codesextant\.session",\s*"([^"]+)"\)',
            text,
        )
        assert match is not None
        browser_session = match.group(1)

        status, _, _ = _request(port, "GET", bootstrap_path)
        assert status == 401

        status, _, _ = _request(port, "GET", "/health")
        assert status == 401

        status, headers, payload = _request(
            port,
            "GET",
            "/health",
            headers={"X-CodeSextant-Session": browser_session},
        )
        assert status == 200
        assert long_lived_secret.encode("ascii") not in payload

        status, headers, payload = _request(port, "GET", "/")
        assert status == 200
        assert headers["Content-Security-Policy"]
        assert long_lived_secret.encode("ascii") not in payload


def test_request_body_size_is_bounded(monkeypatch):
    monkeypatch.setenv("CODESEXTANT_MAX_BODY_BYTES", "32")
    body = b'{"project":"' + (b"x" * 64) + b'"}'
    with _running_server() as port:
        status, _, payload = _request(
            port,
            "POST",
            "/reindex",
            headers={
                **_signed_headers("POST", "/reindex", body),
                "Content-Type": "application/json",
            },
            body=body,
        )
    assert status == 413
    assert b"too large" in payload.lower()


def test_client_authenticates_get_post_and_browser_bootstrap(tmp_path, monkeypatch):
    from codesextant import client, local_auth

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    seen = []

    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.body).encode("utf-8")

    def capture(request, *, timeout):
        seen.append(request)
        if request.full_url.endswith("/_browser_session"):
            return Response({"path": "/_session?code=one-time"})
        return Response({"ok": True})

    monkeypatch.setattr(client.urllib.request, "urlopen", capture)
    api = client.CodesextantClient(project=str(tmp_path), port=18830)

    assert api.health() == {"ok": True}
    assert api.reindex() == {"ok": True}
    dashboard_url = api.dashboard_url()
    assert dashboard_url == "http://127.0.0.1:18830/_session?code=one-time"

    token = local_auth.get_or_create_token()
    assert len(seen) == 3
    assert all(token not in str(dict(request.header_items())) for request in seen)
    assert all(
        request.get_header("Authorization", "").startswith(
            "CodeSextant-HMAC-SHA256 "
        )
        for request in seen
    )
    assert seen[0].get_method() == "GET"
    assert seen[1].get_method() == "POST"
    assert token not in dashboard_url


def test_outdated_busy_daemon_is_not_silently_reused_or_killed(monkeypatch):
    from codesextant import daemon

    old_health = {
        "service": "codesextant",
        "pid": 42,
        "heavy_work": {"active": "/reindex", "queued": 2, "followers": 0},
    }
    monkeypatch.setattr(daemon, "http_ping", lambda **_kwargs: old_health)
    monkeypatch.setattr(
        daemon,
        "stop_running",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("busy daemon must not be killed")
        ),
    )

    result = daemon.ensure_running(port=18834)

    assert result["action"] == "upgrade-required-busy"
    assert result["current_api_version"] is None
    assert result["required_api_version"] == daemon.API_VERSION


def test_outdated_idle_daemon_is_never_killed_from_network_pid(monkeypatch):
    from codesextant import daemon

    old_health = {
        "service": "codesextant",
        "pid": 999999,
        "heavy_work": {"active": None, "queued": 0, "followers": 0},
    }
    monkeypatch.setattr(daemon, "http_ping", lambda **_kwargs: old_health)
    monkeypatch.setattr(
        daemon,
        "stop_running",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("a PID learned from HTTP must never be killed")
        ),
    )

    result = daemon.ensure_running(port=18835)

    assert result["action"] == "upgrade-required"
    assert result["pid"] == 999999


def test_legacy_auth_daemon_is_reported_before_instance_lock_fallback(monkeypatch):
    from codesextant import daemon

    monkeypatch.setattr(daemon, "http_ping", lambda **_kwargs: None)
    monkeypatch.setattr(
        daemon,
        "_auth_challenge",
        lambda **_kwargs: {"scheme": "Bearer", "api_version": "2"},
    )
    monkeypatch.setattr(
        daemon,
        "_instance_owner_result",
        lambda _port: (_ for _ in ()).throw(
            AssertionError("legacy authentication must not look like a busy daemon")
        ),
    )

    result = daemon.ensure_running(port=18839)

    assert result == {
        "action": "upgrade-required-auth",
        "port": 18839,
        "current_api_version": "2",
        "current_auth_scheme": "Bearer",
        "required_api_version": daemon.API_VERSION,
        "required_auth_scheme": "CodeSextant-HMAC-SHA256",
    }


def test_client_explains_legacy_authentication_instead_of_raw_401(
        tmp_path, monkeypatch):
    from codesextant import client

    def legacy_auth(request, **_kwargs):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {"WWW-Authenticate": "Bearer"},
            None,
        )

    monkeypatch.setattr(client.urllib.request, "urlopen", legacy_auth)
    api = client.CodesextantClient(project=str(tmp_path), port=18840)

    try:
        api.health()
    except RuntimeError as exc:
        assert "older authentication protocol" in str(exc)
    else:
        raise AssertionError("legacy authentication must be explained")


def test_graceful_stop_never_passes_a_network_pid_to_the_os(monkeypatch):
    from codesextant import daemon

    health = {
        "service": "codesextant",
        "api_version": daemon.API_VERSION,
        "pid": 999999,
        "heavy_work": {"active": None, "queued": 0, "followers": 0},
    }

    class Response:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"action":"stopping"}'

    monkeypatch.setattr(daemon, "http_ping", lambda **_kwargs: health)
    monkeypatch.setattr(daemon, "is_port_listening", lambda **_kwargs: True)
    monkeypatch.setattr(daemon.urllib.request, "urlopen", lambda *_a, **_k: Response())
    monkeypatch.setattr(
        daemon.subprocess,
        "run",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("taskkill must not be called")
        ),
    )
    monkeypatch.setattr(
        daemon.os,
        "kill",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("os.kill must not be called")
        ),
    )

    result = daemon.stop_running(port=18836)

    assert result["action"] == "draining"
    assert result["pid"] == 999999
    assert result["port_released"] is False


def test_recovery_overload_is_reported_as_retryable_503(monkeypatch):
    from codesextant import daemon, work_coordinator

    monkeypatch.setattr(
        daemon,
        "_prepare_project",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            work_coordinator.HeavyWorkQueueFull("recovery follower cap reached")
        ),
    )
    target = "/get_map?project=C%3A%5Crepo"
    with _running_server() as port:
        status, headers, payload = _request(
            port,
            "GET",
            target,
            headers=_signed_headers("GET", target),
        )

    assert status == 503
    assert headers["Retry-After"]
    assert b"recovery follower cap reached" in payload


def test_browser_session_post_requires_exact_same_origin(monkeypatch):
    from codesextant import daemon

    worker_calls = []
    monkeypatch.setattr(
        daemon.worker_process,
        "run_route",
        lambda *args, **kwargs: worker_calls.append((args, kwargs)) or (200, {}),
    )
    code = daemon._BROWSER_SESSIONS.issue()
    session = daemon._BROWSER_SESSIONS.consume(code)
    assert session
    body = b"{}"
    with _running_server() as port:
        missing, _, _ = _request(
            port,
            "POST",
            "/find_references",
            headers={"X-CodeSextant-Session": session},
            body=body,
        )
        foreign, _, _ = _request(
            port,
            "POST",
            "/find_references",
            headers={
                "X-CodeSextant-Session": session,
                "Origin": "http://127.0.0.1:9",
            },
            body=body,
        )
        same_origin, _, _ = _request(
            port,
            "POST",
            "/find_references",
            headers={
                "X-CodeSextant-Session": session,
                "Origin": f"http://127.0.0.1:{port}",
            },
            body=body,
        )

    assert missing == 403
    assert foreign == 403
    assert same_origin == 400
    assert worker_calls == []


def test_redirected_request_does_not_copy_hmac_headers(tmp_path, monkeypatch):
    import urllib.request

    from codesextant import client, local_auth

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    request = urllib.request.Request("http://127.0.0.1:18837/health")
    client.CodesextantClient._refresh_request_auth(request)

    redirected = urllib.request.HTTPRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://example.com/capture",
    )

    assert redirected is not None
    for name in local_auth.request_headers("GET", "/health"):
        assert redirected.get_header(name) is None


def test_health_probe_sends_a_proof_but_not_the_long_lived_secret(
        tmp_path, monkeypatch):
    from codesextant import daemon, local_auth

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path / "state"))
    secret = local_auth.get_or_create_token()
    captured = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"service":"codesextant","api_version":2}'

    def capture(request, *, timeout):
        captured.append(dict(request.header_items()))
        return Response()

    monkeypatch.setattr(daemon.urllib.request, "urlopen", capture)

    assert daemon.http_ping(port=18838) is not None
    serialized = json.dumps(captured, sort_keys=True)
    assert secret not in serialized
    assert "CodeSextant-HMAC-SHA256" in serialized


def test_watch_manager_singleton_is_safe_under_concurrent_first_use(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from codesextant import daemon

    constructed = []
    gate = threading.Barrier(2)

    class Manager:
        def __init__(self, *_args, **_kwargs):
            constructed.append(self)
            if len(constructed) == 1:
                gate.wait(timeout=1)

    monkeypatch.setattr(daemon.watcher, "WatchManager", Manager)
    monkeypatch.setattr(daemon, "_WATCH_MGR", None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(daemon._get_watch_mgr)
        gate.wait(timeout=1)
        second = pool.submit(daemon._get_watch_mgr)
        one = first.result(timeout=1)
        two = second.result(timeout=1)

    assert one is two
    assert constructed == [one]
