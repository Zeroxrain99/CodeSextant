"""HMAC authentication and bounded local-session contracts."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor


def _reset_replay(local_auth) -> None:
    local_auth._REPLAY_CACHE.clear()


def test_request_headers_sign_without_transmitting_the_secret(tmp_path, monkeypatch):
    from codesextant import local_auth

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path))
    monkeypatch.setattr(local_auth.time, "time", lambda: 1_700_000_000.0)
    _reset_replay(local_auth)

    secret = local_auth.get_or_create_token()
    headers = local_auth.request_headers(
        "POST", "/impact?project=C%3A%5Crepo", b'{"symbol":"run"}'
    )
    compatibility_headers = local_auth.auth_headers(
        "POST", "/impact?project=C%3A%5Crepo", b'{"symbol":"run"}'
    )

    assert headers.keys() == compatibility_headers.keys()
    encoded_headers = json.dumps(headers, sort_keys=True)
    assert secret not in encoded_headers
    assert secret not in json.dumps(compatibility_headers, sort_keys=True)
    assert "Bearer " not in encoded_headers
    assert headers["Authorization"].startswith("CodeSextant-HMAC-SHA256 ")
    assert local_auth.verify_request(
        "POST", "/impact?project=C%3A%5Crepo", headers, b'{"symbol":"run"}'
    )
    assert local_auth.verify_request(
        "POST",
        "/impact?project=C%3A%5Crepo",
        compatibility_headers,
        b'{"symbol":"run"}',
    )


def test_hmac_rejects_tampering_replay_expiry_and_body_changes(
    tmp_path, monkeypatch
):
    from codesextant import local_auth

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path))
    now = [2_000_000_000.0]
    monkeypatch.setattr(local_auth.time, "time", lambda: now[0])
    _reset_replay(local_auth)
    body = b'{"project":"C:/repo","force":false}'
    target = "/reindex?source=gui"

    method_headers = local_auth.request_headers("POST", target, body)
    assert not local_auth.verify_request("GET", target, method_headers, body)

    target_headers = local_auth.request_headers("POST", target, body)
    assert not local_auth.verify_request(
        "POST", "/reindex?source=agent", target_headers, body
    )

    timestamp_headers = local_auth.request_headers("POST", target, body)
    timestamp_headers["X-CodeSextant-Timestamp"] = str(
        int(timestamp_headers["X-CodeSextant-Timestamp"]) + 1
    )
    assert not local_auth.verify_request("POST", target, timestamp_headers, body)

    nonce_headers = local_auth.request_headers("POST", target, body)
    nonce_headers["X-CodeSextant-Nonce"] += "x"
    assert not local_auth.verify_request("POST", target, nonce_headers, body)

    body_headers = local_auth.request_headers("POST", target, body)
    assert not local_auth.verify_request("POST", target, body_headers, body + b" ")

    signature_headers = local_auth.request_headers("POST", target, body)
    signature_headers["Authorization"] = (
        signature_headers["Authorization"][:-1]
        + ("0" if signature_headers["Authorization"][-1] != "0" else "1")
    )
    assert not local_auth.verify_request("POST", target, signature_headers, body)

    replay_headers = local_auth.request_headers("POST", target, body)
    assert local_auth.verify_request("POST", target, replay_headers, body)
    assert not local_auth.verify_request("POST", target, replay_headers, body)

    expired_headers = local_auth.request_headers("POST", target, body)
    now[0] += local_auth.auth_time_skew_sec() + 1
    assert not local_auth.verify_request("POST", target, expired_headers, body)


def test_replay_cache_fails_closed_at_its_bound(tmp_path, monkeypatch):
    from codesextant import local_auth

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path))
    monkeypatch.setattr(local_auth.time, "time", lambda: 3_000_000_000.0)
    monkeypatch.setattr(
        local_auth,
        "_REPLAY_CACHE",
        local_auth._ReplayCache(max_entries=2),
    )

    first = local_auth.request_headers("GET", "/health")
    second = local_auth.request_headers("GET", "/health")
    third = local_auth.request_headers("GET", "/health")

    assert local_auth.verify_request("GET", "/health", first)
    assert local_auth.verify_request("GET", "/health", second)
    assert not local_auth.verify_request("GET", "/health", third)
    assert len(local_auth._REPLAY_CACHE) == 2
    assert not local_auth.verify_request("GET", "/health", first)


def test_browser_bootstraps_and_sessions_are_one_use_expiring_and_bounded():
    from codesextant import local_auth

    now = [100.0]
    store = local_auth.BrowserSessionStore(
        bootstrap_ttl_sec=5,
        session_ttl_sec=10,
        max_bootstrap=2,
        max_sessions=2,
        clock=lambda: now[0],
    )

    evicted = store.issue()
    first = store.issue()
    second = store.issue()
    assert store.consume(evicted) is None

    first_session = store.consume(first)
    second_session = store.consume(second)
    assert first_session and second_session
    assert store.consume(first) is None
    now[0] += 1
    assert store.valid(first_session)

    third_code = store.issue()
    third_session = store.consume(third_code)
    assert third_session
    assert not store.valid(second_session)
    assert store.valid(first_session)
    assert store.valid(third_session)

    expiring = store.issue()
    now[0] += 6
    assert store.consume(expiring) is None
    now[0] += 5
    assert not store.valid(first_session)


def test_concurrent_cold_start_publishes_one_complete_token(tmp_path, monkeypatch):
    from codesextant import local_auth

    monkeypatch.setenv("CODESEXTANT_HOME", str(tmp_path))
    callers = 8
    publication_barrier = threading.Barrier(callers)
    original_publish = local_auth._publish_token

    def synchronized_publish(path, token):
        publication_barrier.wait(timeout=2)
        return original_publish(path, token)

    monkeypatch.setattr(local_auth, "_publish_token", synchronized_publish)
    with ThreadPoolExecutor(max_workers=callers) as pool:
        results = list(pool.map(lambda _index: local_auth.get_or_create_token(), range(callers)))

    assert len(set(results)) == 1
    published = (tmp_path / local_auth.TOKEN_FILE).read_text(encoding="ascii").strip()
    assert published == results[0]
    assert len(published) >= 43
    assert sorted(path.name for path in tmp_path.iterdir()) == [local_auth.TOKEN_FILE]
