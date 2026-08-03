"""Shared fixtures for the platform security suite (M1 Phase 1).

These tests pin the S2 (proxy session enforcement) and S3 (backend
file-read allowlist) boundaries closed on 2026-07-20. They must never
touch prod state or the live services on this box. Isolation guarantees:

- ``ui/`` is placed on ``sys.path`` so ``auth_proxy`` and ``server``
  import exactly as they do in production.
- ``TestClient`` is always used WITHOUT a ``with`` block, so neither
  app's startup lifespan fires: no log compression, no piper voice
  load, no auth-dir creation.
- ``auth_proxy.load_sessions`` is monkeypatched to an in-test dict, so
  the real ``ui/.auth/sessions.json`` is never read or written.
- ``auth_proxy``'s ``httpx.AsyncClient`` is replaced with a stub, so a
  request that *passes* the gate hits the stub, NEVER the live voice
  box on :8001. Belt-and-suspenders: even a broken assertion that lets
  a request through cannot reach a prod service.

The S3 tests exercise ``server.py``'s ``/view-file`` directly. They
only read files (allowlist denials return 403 before any read; the one
allowed-path case reads a committed, read-only doc), so they mutate
nothing.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))


# --------------------------------------------------------------------------
# S2 — auth_proxy fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def auth_proxy_mod():
    import auth_proxy
    return auth_proxy


class _FakeResp:
    """Minimal stand-in for an httpx.Response the proxy forwards."""

    def __init__(self, status_code=200, content=b'{"ok": true}', headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"content-type": "application/json"}

    def json(self):
        import json
        return json.loads(self.content or b"null")


@pytest.fixture
def fake_backend(monkeypatch, auth_proxy_mod):
    """Replace the proxy's ``httpx.AsyncClient`` so passing the gate hits a
    stub instead of the live :8001. Returns a mutable holder — set
    ``holder['resp']`` to control what the stubbed backend returns."""
    holder = {"resp": _FakeResp()}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def _respond(self, *a, **k):
            return holder["resp"]

        get = post = put = delete = patch = _respond

    monkeypatch.setattr(auth_proxy_mod.httpx, "AsyncClient", _Client)
    return holder


@pytest.fixture
def sessions(monkeypatch, auth_proxy_mod):
    """In-test session store; the real sessions.json is never touched."""
    store = {}
    monkeypatch.setattr(auth_proxy_mod, "load_sessions", lambda: dict(store))
    return store


@pytest.fixture
def login(sessions):
    """Return a helper that registers a session and yields its token."""

    def _login(*, token="tok-valid", mfa_verified=True, ttl_hours=1):
        sessions[token] = {
            "token": token,
            "username": "tester",
            "expires_at": (datetime.now() + timedelta(hours=ttl_hours)).isoformat(),
            "mfa_verified": mfa_verified,
        }
        return token

    return _login


@pytest.fixture
def proxy_client(auth_proxy_mod, sessions, fake_backend):
    from fastapi.testclient import TestClient
    # No `with` block → the app's on_event("startup") never runs.
    return TestClient(auth_proxy_mod.app)


# --------------------------------------------------------------------------
# S3 — server (backend) fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def server_mod():
    import server
    return server


@pytest.fixture
def backend_client(server_mod):
    from fastapi.testclient import TestClient
    # No `with` block → lifespan (log compression, piper load) never runs.
    return TestClient(server_mod.app)
