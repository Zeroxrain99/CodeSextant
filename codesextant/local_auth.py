"""Local authentication primitives for the CodeSextant daemon.

The daemon is loopback-only, but loopback is not an authentication boundary.
The long-lived secret never crosses HTTP. Each API request carries a bounded,
single-use HMAC proof over its method, exact request target, timestamp, nonce,
and body digest. The browser uses short-lived in-memory sessions instead.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import stat
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from . import storage

TOKEN_FILE = "daemon.token"
AUTH_SCHEME = "CodeSextant-HMAC-SHA256"
_AUTH_VERSION = "codesextant-hmac-v1"
_TIMESTAMP_HEADER = "X-CodeSextant-Timestamp"
_NONCE_HEADER = "X-CodeSextant-Nonce"
_BODY_DIGEST_HEADER = "X-CodeSextant-Content-SHA256"
_TOKEN_READ_RETRIES = 100
_TOKEN_READ_DELAY_SEC = 0.01


def _env_positive_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_positive_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def token_path() -> Path:
    return storage.default_db_dir() / TOKEN_FILE


def _prepare_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)


def _token_is_valid(token: str) -> bool:
    if not 43 <= len(token) <= 256:
        return False
    return all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in token)


def _read_valid_token(path: Path) -> str | None:
    try:
        token = path.read_text(encoding="ascii").strip()
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return None
    return token if _token_is_valid(token) else None


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.write(fd, view[written:])
        if count <= 0:
            raise OSError("failed to publish the CodeSextant daemon secret")
        written += count


def _write_complete_file(path: Path, token: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(path, flags, stat.S_IRUSR | stat.S_IWUSR)
    complete = False
    try:
        _write_all(fd, (token + "\n").encode("ascii"))
        os.fsync(fd)
        complete = True
    finally:
        os.close(fd)
        if not complete:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    if os.name != "nt":
        path.chmod(0o600)


def _publish_direct(path: Path, token: str) -> bool:
    """Fallback publication with bounded valid-read retry for contenders."""
    try:
        _write_complete_file(path, token)
    except FileExistsError:
        return False
    return True


def _publish_token(path: Path, token: str) -> bool:
    """Publish one complete secret without replacing a concurrent winner."""
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}."
        f"{secrets.token_hex(8)}.tmp"
    )
    try:
        _write_complete_file(temporary, token)
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        except (AttributeError, NotImplementedError, OSError):
            return _publish_direct(path, token)
        return True
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def get_or_create_token() -> str:
    """Return the stable 256-bit local secret, creating it safely once."""
    path = token_path()
    _prepare_private_directory(path.parent)
    saw_path = False
    for attempt in range(_TOKEN_READ_RETRIES):
        token = _read_valid_token(path)
        if token is not None:
            if os.name != "nt":
                path.chmod(0o600)
            return token
        if not path.exists():
            candidate = secrets.token_urlsafe(32)
            if _publish_token(path, candidate):
                return candidate
        else:
            saw_path = True
        if attempt + 1 < _TOKEN_READ_RETRIES:
            time.sleep(_TOKEN_READ_DELAY_SEC)
    detail = "incomplete" if saw_path or path.exists() else "unavailable"
    raise RuntimeError(f"{detail} CodeSextant daemon secret at {path}")


def auth_time_skew_sec() -> float:
    """Maximum accepted difference between signer and verifier wall clocks."""
    return _env_positive_float("CODESEXTANT_AUTH_TIME_SKEW_SEC", 60.0)


def _body_bytes(body: bytes | bytearray | memoryview) -> bytes:
    if isinstance(body, bytes):
        return body
    if isinstance(body, (bytearray, memoryview)):
        return bytes(body)
    raise TypeError("request body must be bytes-like")


def _canonical_request(method: str, target: str, timestamp: str,
                       nonce: str, body_digest: str) -> bytes:
    if not target.startswith("/") or "\r" in target or "\n" in target:
        raise ValueError("request target must be an exact origin-form target")
    normalized_method = method.strip().upper()
    if not normalized_method or any(ch.isspace() for ch in normalized_method):
        raise ValueError("request method is invalid")
    return "\n".join((
        _AUTH_VERSION,
        normalized_method,
        target,
        timestamp,
        nonce,
        body_digest,
    )).encode("utf-8")


def request_headers(method: str, target: str,
                    body: bytes = b"") -> dict[str, str]:
    """Create a single-use HMAC proof for one exact HTTP request."""
    raw_body = _body_bytes(body)
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(18)
    body_digest = hashlib.sha256(raw_body).hexdigest()
    canonical = _canonical_request(
        method, target, timestamp, nonce, body_digest)
    signature = hmac.new(
        get_or_create_token().encode("ascii"),
        canonical,
        hashlib.sha256,
    ).hexdigest()
    return {
        "Authorization": f"{AUTH_SCHEME} {signature}",
        _TIMESTAMP_HEADER: timestamp,
        _NONCE_HEADER: nonce,
        _BODY_DIGEST_HEADER: body_digest,
    }


def auth_headers(method: str, target: str,
                 body: bytes = b"") -> dict[str, str]:
    """Compatibility name for callers that previously requested auth headers."""
    return request_headers(method, target, body)


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    value = headers.get(name)
    if value is not None:
        return str(value)
    lowered = name.lower()
    try:
        items = headers.items()
    except AttributeError:
        return None
    for key, candidate in items:
        if str(key).lower() == lowered:
            return str(candidate)
    return None


class _ReplayCache:
    """Bounded nonce cache that rejects new proofs when safely full."""

    def __init__(self, *, max_entries: int | None = None):
        self.max_entries = (
            _env_positive_int("CODESEXTANT_AUTH_REPLAY_CAP", 8192)
            if max_entries is None else max(1, int(max_entries))
        )
        self._lock = threading.Lock()
        self._expires: dict[str, float] = {}

    def accept(self, nonce: str, *, expires_at: float, now: float) -> bool:
        with self._lock:
            self._expires = {
                key: expiry
                for key, expiry in self._expires.items()
                if expiry >= now
            }
            if nonce in self._expires or len(self._expires) >= self.max_entries:
                return False
            self._expires[nonce] = expires_at
            return True

    def clear(self) -> None:
        with self._lock:
            self._expires.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._expires)


_REPLAY_CACHE = _ReplayCache()


def verify_request(method: str, target: str, headers: Mapping[str, str],
                   body: bytes = b"") -> bool:
    """Verify one request proof and consume its nonce exactly once."""
    try:
        authorization = _header_value(headers, "Authorization")
        prefix = f"{AUTH_SCHEME} "
        if not authorization or not authorization.startswith(prefix):
            return False
        signature = authorization[len(prefix):]
        if len(signature) != 64 or any(ch not in "0123456789abcdef" for ch in signature):
            return False

        timestamp = _header_value(headers, _TIMESTAMP_HEADER)
        nonce = _header_value(headers, _NONCE_HEADER)
        supplied_digest = _header_value(headers, _BODY_DIGEST_HEADER)
        if not timestamp or not timestamp.isascii() or not timestamp.isdigit():
            return False
        if (not nonce or not 16 <= len(nonce) <= 128
                or any(not (ch.isascii() and (ch.isalnum() or ch in "-_"))
                       for ch in nonce)):
            return False
        if (not supplied_digest or len(supplied_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in supplied_digest)):
            return False

        signed_at = int(timestamp)
        now = time.time()
        skew = auth_time_skew_sec()
        if abs(now - signed_at) > skew:
            return False
        actual_digest = hashlib.sha256(_body_bytes(body)).hexdigest()
        if not hmac.compare_digest(supplied_digest, actual_digest):
            return False

        canonical = _canonical_request(
            method, target, timestamp, nonce, supplied_digest)
        expected = hmac.new(
            get_or_create_token().encode("ascii"),
            canonical,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        return _REPLAY_CACHE.accept(
            nonce, expires_at=signed_at + skew, now=now)
    except (OSError, RuntimeError, TypeError, ValueError, UnicodeError):
        return False


@dataclass(frozen=True)
class _ExpiringValue:
    value: str
    expires_at: float


class BrowserSessionStore:
    """Bounded in-memory one-time bootstrap codes and dashboard sessions."""

    def __init__(self, *, bootstrap_ttl_sec: float = 60.0,
                 session_ttl_sec: float = 8 * 60 * 60,
                 max_bootstrap: int | None = None,
                 max_sessions: int | None = None,
                 clock=time.monotonic):
        self.bootstrap_ttl_sec = max(0.1, float(bootstrap_ttl_sec))
        self.session_ttl_sec = max(0.1, float(session_ttl_sec))
        self.max_bootstrap = (
            _env_positive_int("CODESEXTANT_BROWSER_BOOTSTRAP_CAP", 128)
            if max_bootstrap is None else max(1, int(max_bootstrap))
        )
        self.max_sessions = (
            _env_positive_int("CODESEXTANT_BROWSER_SESSION_CAP", 64)
            if max_sessions is None else max(1, int(max_sessions))
        )
        self._clock = clock
        self._lock = threading.Lock()
        self._bootstrap: dict[str, _ExpiringValue] = {}
        self._sessions: dict[str, float] = {}

    @staticmethod
    def _drop_earliest(values: dict[str, object]) -> None:
        if values:
            key = min(
                values,
                key=lambda item: getattr(values[item], "expires_at", values[item]),
            )
            values.pop(key, None)

    def issue(self) -> str:
        code = secrets.token_urlsafe(24)
        now = self._clock()
        with self._lock:
            self._prune_locked(now)
            while len(self._bootstrap) >= self.max_bootstrap:
                self._drop_earliest(self._bootstrap)
            self._bootstrap[code] = _ExpiringValue(
                value=secrets.token_urlsafe(32),
                expires_at=now + self.bootstrap_ttl_sec,
            )
        return code

    def consume(self, code: str | None) -> str | None:
        if not code:
            return None
        now = self._clock()
        with self._lock:
            self._prune_locked(now)
            item = self._bootstrap.pop(code, None)
            if item is None or item.expires_at < now:
                return None
            while len(self._sessions) >= self.max_sessions:
                self._drop_earliest(self._sessions)
            self._sessions[item.value] = now + self.session_ttl_sec
            return item.value

    def valid(self, session: str | None) -> bool:
        if not session:
            return False
        now = self._clock()
        with self._lock:
            self._prune_locked(now)
            expires_at = self._sessions.get(session)
            if expires_at is None or expires_at < now:
                return False
            self._sessions[session] = now + self.session_ttl_sec
            return True

    def _prune_locked(self, now: float) -> None:
        self._bootstrap = {
            key: value
            for key, value in self._bootstrap.items()
            if value.expires_at >= now
        }
        self._sessions = {
            key: expires_at
            for key, expires_at in self._sessions.items()
            if expires_at >= now
        }
