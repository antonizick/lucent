"""S3 regression tests — the backend (:8001) /view-file endpoint only
serves files under an explicit allowlist of roots.

Pins the fix for the unrestricted arbitrary-file-read closed on
2026-07-20. ``_is_allowed_file_path`` resolves the target (collapsing
``..``) and requires it to live under one of:
    memory, idea, logs, docs, presentation, scratchpad
(all under the repo root). Anything else — /etc/passwd, ~/.ssh keys,
the auth ``credentials.json`` inside ``ui/`` — is 403, even for an
authenticated caller (defense-in-depth behind the S2 gate).
"""
from pathlib import Path

import pytest


def _abs(server_mod, *parts):
    return str(server_mod._LUCENT_ROOT.joinpath(*parts))


@pytest.mark.parametrize("path", ["/etc/passwd", "/etc/shadow"])
def test_system_files_blocked(backend_client, path):
    r = backend_client.get("/view-file", params={"path": path})
    assert r.status_code == 403
    assert "root:" not in r.text  # nothing leaks, even in the error body


def test_auth_credentials_file_blocked(backend_client, server_mod):
    """The MFA secret + password hash live at ui/.auth/credentials.json —
    inside the repo but NOT under an allowed root. Must be 403."""
    p = _abs(server_mod, "ui", ".auth", "credentials.json")
    r = backend_client.get("/view-file", params={"path": p})
    assert r.status_code == 403
    assert "mfa_secret" not in r.text
    assert "password_hash" not in r.text


def test_ssh_private_key_blocked(backend_client):
    p = str(Path.home() / ".ssh" / "id_rsa")
    r = backend_client.get("/view-file", params={"path": p})
    assert r.status_code == 403


def test_traversal_out_of_allowed_root_blocked(backend_client, server_mod):
    """A path that starts under an allowed root but climbs out with ..
    must be blocked — resolve() collapses the traversal before the check."""
    p = _abs(server_mod, "memory", "..", "ui", ".auth", "credentials.json")
    r = backend_client.get("/view-file", params={"path": p})
    assert r.status_code == 403


def test_allowed_file_is_served(backend_client, server_mod):
    """A real file under an allowed root (docs/) is served 200."""
    p = _abs(server_mod, "docs", "Lucent-Operation-Audit.md")
    r = backend_client.get("/view-file", params={"path": p})
    assert r.status_code == 200
    assert "Operation-Audit" in r.text


def test_empty_path_rejected(backend_client):
    r = backend_client.get("/view-file", params={"path": ""})
    assert r.status_code == 400


def test_allowlist_predicate_boundary(server_mod):
    """Direct assertions on the predicate that both routes rely on."""
    allow = server_mod._is_allowed_file_path
    root = server_mod._LUCENT_ROOT
    assert allow(root / "memory" / "any-note.md") is True
    assert allow(root / "scratchpad" / "tmp.txt") is True
    assert allow(root / "docs" / "Lucent-Operation-Audit.md") is True
    assert allow(Path("/etc/passwd")) is False
    assert allow(root / "ui" / "server.py") is False  # ui/ is not allowed
    assert allow(root / "ui" / ".auth" / "credentials.json") is False
