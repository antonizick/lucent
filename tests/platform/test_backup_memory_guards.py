"""M1 memory-integrity tests — scripts/backup_memory.py's secret-scan and
shrink guards.

Root causes these exist for:
  - 2026-05-17: a credential typed into a daily note was committed+pushed
    to the private LucentMemory repo by this same script.
  - 2026-07-17: memory/2026-07-17.md's 201 lines were overwritten with 5
    and nearly backed up as-is.

``scan_staged_for_secrets`` and ``scan_staged_for_shrinkage`` both take a
``cwd`` and run ``git diff --cached`` against it — they don't reference
the real ``memory/`` tree directly. Tests exercise them against a real,
throwaway git repo under ``tmp_path``, which is the actual interface
``backup_memory()`` calls (a temp repo IS a real git repo, just not the
production one) — never against the real memory backup repo.
"""
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import backup_memory as bm  # noqa: E402


def _git(cwd, *args):
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return result.stdout


@pytest.fixture
def repo(tmp_path):
    """A real, throwaway git repo — never the production memory/.git."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "seed.md").write_text("seed\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "seed")
    return tmp_path


def _stage(repo, name, content):
    (repo / name).write_text(content)
    _git(repo, "add", "-A")


# --- Secret scan -------------------------------------------------------
def test_credential_shaped_line_is_caught(repo):
    _stage(repo, "notes.md", 'api_key: "sk-abcdEFGH12345678ijklMNOP"\n')
    findings = bm.scan_staged_for_secrets(str(repo))
    assert len(findings) == 1
    # the masked finding must not contain the raw secret value
    assert "sk-abcdEFGH12345678ijklMNOP" not in findings[0]


def test_known_token_format_is_caught(repo):
    _stage(repo, "notes.md", "leaked AWS key AKIAABCDEFGHIJKLMNOP in a note\n")
    findings = bm.scan_staged_for_secrets(str(repo))
    assert len(findings) == 1


def test_private_key_block_is_caught(repo):
    _stage(repo, "notes.md", "-----BEGIN RSA PRIVATE KEY-----\nMIIC...\n")
    findings = bm.scan_staged_for_secrets(str(repo))
    assert len(findings) == 1


def test_ordinary_prose_mentioning_password_is_not_flagged(repo):
    """High precision by design: the word 'password' alone (no
    high-entropy value) must not trip the guard, or it'd block routine
    daily-note writing about the auth work itself."""
    _stage(repo, "notes.md", "Discussed the password hashing weakness (S5) with Nick today.\n")
    findings = bm.scan_staged_for_secrets(str(repo))
    assert findings == []


def test_redaction_placeholder_is_not_flagged(repo):
    _stage(repo, "notes.md", 'token: "************"\n')
    findings = bm.scan_staged_for_secrets(str(repo))
    assert findings == []


def test_unstaged_secret_is_not_seen(repo):
    """Scanner reads --cached only; a secret written but not `git add`ed
    must not show up (mirrors real pre-commit staging semantics)."""
    (repo / "notes.md").write_text('api_key: "sk-abcdEFGH12345678ijklMNOP"\n')
    findings = bm.scan_staged_for_secrets(str(repo))
    assert findings == []


# --- Shrink guard --------------------------------------------------------
def test_drastic_daily_note_shrink_is_caught(repo):
    old = "\n".join(f"line {i}" for i in range(200))
    _stage(repo, "2026-07-17.md", old)
    _git(repo, "commit", "-q", "-m", "full note")

    _stage(repo, "2026-07-17.md", "line 1\nline 2\n")
    findings = bm.scan_staged_for_shrinkage(str(repo))
    assert len(findings) == 1
    assert "2026-07-17.md" in findings[0]


def test_archive_path_shrink_is_caught(repo):
    (repo / "archive").mkdir()
    old = "\n".join(f"line {i}" for i in range(200))
    _stage(repo, "archive/2026-07-17.md", old)
    _git(repo, "commit", "-q", "-m", "archived")

    _stage(repo, "archive/2026-07-17.md", "short\n")
    findings = bm.scan_staged_for_shrinkage(str(repo))
    assert len(findings) == 1


def test_unsummarized_placeholder_shrink_is_allowlisted(repo):
    old = "\n".join(f"line {i}" for i in range(200))
    _stage(repo, "2026-07-17.md", old)
    _git(repo, "commit", "-q", "-m", "full note")

    _stage(repo, "2026-07-17.md", "UNSUMMARIZED — see archive\n")
    findings = bm.scan_staged_for_shrinkage(str(repo))
    assert findings == []


def test_normal_growth_is_not_flagged(repo):
    old = "\n".join(f"line {i}" for i in range(200))
    _stage(repo, "2026-07-18.md", old)
    _git(repo, "commit", "-q", "-m", "full note")

    grown = old + "\nnew entry\n"
    _stage(repo, "2026-07-18.md", grown)
    findings = bm.scan_staged_for_shrinkage(str(repo))
    assert findings == []


def test_small_trim_below_threshold_is_not_flagged(repo):
    old = "\n".join(f"line {i}" for i in range(200))
    _stage(repo, "2026-07-18.md", old)
    _git(repo, "commit", "-q", "-m", "full note")

    trimmed = "\n".join(f"line {i}" for i in range(195))  # only 5 lines deleted
    _stage(repo, "2026-07-18.md", trimmed)
    findings = bm.scan_staged_for_shrinkage(str(repo))
    assert findings == []


def test_non_daily_note_shrink_is_ignored(repo):
    old = "\n".join(f"line {i}" for i in range(200))
    _stage(repo, "README.md", old)
    _git(repo, "commit", "-q", "-m", "full readme")

    _stage(repo, "README.md", "short\n")
    findings = bm.scan_staged_for_shrinkage(str(repo))
    assert findings == []
