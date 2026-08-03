"""S2 regression tests — the auth proxy (:8002) enforces an MFA session
on every path except the small public allowlist.

These pin the fix for the tunnel-reachable auth bypass: before
2026-07-20 the catch-all and several explicit routes forwarded to the
unauthenticated backend (:8001) with no session check, so an
unauthenticated request to the internet-facing proxy could reach the
backend's arbitrary-file-read. The middleware ``enforce_session`` is now
the single choke point.

Public allowlist (must stay reachable unauthenticated):
    prefix  /auth/
    exact   /services/health, /favicon.ico
Everything else requires a valid, non-expired, MFA-verified session
cookie. Browser navigations (GET/HEAD + ``text/html``) get a 302 to the
login page; everything else gets a 401.
"""
import pytest


# --- The headline: unauthenticated arbitrary-read attempt is blocked -------
def test_unauth_arbitrary_read_blocked_and_no_leak(proxy_client):
    """An unauthenticated /view-file for /etc/passwd through the proxy is
    rejected at the gate AND leaks nothing — the request never reaches the
    backend, so no file bytes come back in the response body."""
    r = proxy_client.get(
        "/view-file",
        params={"path": "/etc/passwd"},
        headers={"accept": "application/json"},
    )
    assert r.status_code == 401
    assert "root:" not in r.text  # no /etc/passwd content leaked
    assert r.json()["detail"] == "Not authenticated"


# --- Any private path, unauthenticated → 401 -------------------------------
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/todo"),
        ("get", "/view-file"),
        ("post", "/run-backup"),
        ("post", "/agent/invoke"),
        ("post", "/reflect/apply"),
        ("get", "/some/unmapped/path"),
    ],
)
def test_unauth_private_paths_return_401(proxy_client, method, path):
    r = getattr(proxy_client, method)(path, headers={"accept": "application/json"})
    assert r.status_code == 401


def test_unauth_static_asset_is_gated(proxy_client):
    """/static kept a stale 'proxy directly if no token' handler; the
    middleware must supersede it so an unauth static request is still
    gated (not passed through to the backend)."""
    r = proxy_client.get("/static/app.js", headers={"accept": "application/json"})
    assert r.status_code == 401


def test_unauth_speak_post_is_gated(proxy_client):
    """POST /speak had an explicit 'no additional check needed' handler;
    the gate must block it when unauthenticated."""
    r = proxy_client.post("/speak", json={"text": "should never reach the box"})
    assert r.status_code == 401


# --- Browser navigation is redirected, not 401'd ---------------------------
def test_unauth_browser_navigation_redirects_to_login(proxy_client):
    r = proxy_client.get(
        "/",
        headers={"accept": "text/html"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "/auth/login"


# --- Public allowlist stays open -------------------------------------------
def test_public_login_page_served_unauthenticated(proxy_client):
    r = proxy_client.get("/auth/login")
    assert r.status_code == 200
    assert "login" in r.text.lower()


def test_public_health_probe_not_gated(proxy_client, fake_backend):
    """/services/health is public so startup.py's liveness probe works;
    it passes the gate and is forwarded (here, to the stub)."""
    r = proxy_client.get("/services/health")
    assert r.status_code == 200


# --- Bad credentials never bypass the gate ---------------------------------
def test_garbage_cookie_rejected(proxy_client):
    proxy_client.cookies.set("auth_token", "not-a-real-token")
    r = proxy_client.get("/api/todo", headers={"accept": "application/json"})
    assert r.status_code == 401


def test_expired_session_rejected(proxy_client, login):
    token = login(ttl_hours=-1)  # already expired
    proxy_client.cookies.set("auth_token", token)
    r = proxy_client.get("/api/todo", headers={"accept": "application/json"})
    assert r.status_code == 401


def test_mfa_unverified_session_rejected(proxy_client, login):
    token = login(mfa_verified=False)  # authenticated but MFA not completed
    proxy_client.cookies.set("auth_token", token)
    r = proxy_client.get("/api/todo", headers={"accept": "application/json"})
    assert r.status_code == 401


# --- A valid MFA session is NOT blocked (guards against an always-deny gate)
def test_valid_session_passes_gate(proxy_client, login, fake_backend):
    token = login()
    proxy_client.cookies.set("auth_token", token)
    r = proxy_client.get("/agent/current", headers={"accept": "application/json"})
    assert r.status_code == 200
    # The stub's sentinel body proves the request was served by the fake
    # backend, not the live voice box on :8001 — isolation is real.
    assert r.json() == {"ok": True}


def test_backend_status_code_is_propagated(proxy_client, login, fake_backend):
    """The catch-all must propagate the backend's status, not relabel
    everything 200 — that latent bug previously masked the S3 403."""
    token = login()
    proxy_client.cookies.set("auth_token", token)
    fake_backend["resp"] = type(fake_backend["resp"])(
        status_code=403, content=b'{"detail": "Path not permitted"}'
    )
    r = proxy_client.get(
        "/view-file",
        params={"path": "/etc/passwd"},
        headers={"accept": "application/json"},
    )
    assert r.status_code == 403
