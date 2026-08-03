"""M1 Phase 2 hook smoke test — scripts/lucent-init.sh.

lucent-init.sh hardcodes ``LUCENT_DIR="/home/nick/dev/lucent"`` with no
override mechanism, and (when a startup-readiness marker file is present)
fires a real ``curl`` to the voice box. Running the real script against
the real path is therefore not safe to do repeatedly/automatically.

Isolation strategy: copy the ENTIRE real ``scripts/`` tree into a
throwaway directory, write a patched copy of ``lucent-init.sh`` with
``LUCENT_DIR`` pointed at that directory, and run that copy. Every helper
script it shells out to (memory_recall.py, active_reminders.py,
priority_email_check.py, reflect.py, ...) derives its own root from
``Path(__file__).parent.parent`` — so once copied, they resolve entirely
inside the throwaway tree too. Nothing here ever reads or writes the real
``memory/``, and the marker file (which triggers the live curl) simply
doesn't exist in the fake tree, so that branch structurally cannot fire.

This is the concrete test of the M1 claim: the hook "produces valid
output and never crashes on missing files" — exercised here by NOT
pre-seeding memory/core.md, LTMemory.md, or any reminders/email state,
which is exactly the missing-files condition a fresh install hits.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SCRIPTS_DIR = REPO_ROOT / "scripts"
REAL_INIT_SH = REAL_SCRIPTS_DIR / "lucent-init.sh"


def test_lucent_init_sh_syntax_is_valid():
    """Cheap, zero-execution sanity check."""
    result = subprocess.run(
        ["bash", "-n", str(REAL_INIT_SH)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def isolated_hook(tmp_path):
    """Build a throwaway LUCENT_DIR with the real scripts/ copied in, and
    a patched lucent-init.sh pointed at it. Returns (script_path, fake_dir)."""
    fake_dir = tmp_path / "lucent"
    shutil.copytree(REAL_SCRIPTS_DIR, fake_dir / "scripts")
    (fake_dir / "memory").mkdir(parents=True)

    patched = REAL_INIT_SH.read_text().replace(
        'LUCENT_DIR="/home/nick/dev/lucent"',
        f'LUCENT_DIR="{fake_dir}"',
        1,
    )
    script_path = fake_dir / "scripts" / "lucent-init.sh"
    script_path.write_text(patched)
    script_path.chmod(0o755)
    return script_path, fake_dir


def run_hook(script_path, prompt="hello"):
    import json

    return subprocess.run(
        ["bash", str(script_path)],
        input=json.dumps({"prompt": prompt}),
        capture_output=True,
        text=True,
        timeout=40,
    )


def test_runs_clean_against_completely_empty_memory_dir(isolated_hook):
    """No core.md, no LTMemory.md, no today's note, no reminders file, no
    email db — the exact 'missing files' condition a fresh install hits.
    Must exit 0 and produce well-formed, traceback-free output."""
    script_path, fake_dir = isolated_hook
    result = run_hook(script_path)

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "[Lucent] Today is" in result.stdout
    assert "=== ACTIVE REMINDERS ===" in result.stdout
    assert "=== TODAY'S SESSION LOG" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_creates_todays_note_when_missing(isolated_hook):
    script_path, fake_dir = isolated_hook
    from datetime import date

    note = fake_dir / "memory" / f"{date.today().isoformat()}.md"
    assert not note.exists()

    run_hook(script_path)

    assert note.exists()
    assert "Session started." in note.read_text()


def test_preserves_existing_daily_note_content(isolated_hook):
    """The hook must never truncate/overwrite an existing note — only
    tail it. This is the exact failure class guard_memory_write.py
    separately guards against on the Write-tool side."""
    script_path, fake_dir = isolated_hook
    from datetime import date

    note = fake_dir / "memory" / f"{date.today().isoformat()}.md"
    note.write_text("# Existing content that must survive\nPRESERVE-ME-MARKER\n")

    run_hook(script_path)

    content = note.read_text()
    assert "PRESERVE-ME-MARKER" in content


def test_no_marker_file_means_no_readiness_branch_fires(isolated_hook):
    """With no .startup_ready_*.txt in the fake tree, the branch that
    fires a real curl to the voice box must not execute."""
    script_path, fake_dir = isolated_hook
    result = run_hook(script_path)
    assert "STARTUP READINESS MARKER" not in result.stdout


def test_unsummarized_marker_surfaces_action_required(isolated_hook):
    """Exercises the one real conditional branch that depends on a
    memory/ file existing — proves it activates correctly, isolated."""
    script_path, fake_dir = isolated_hook
    import json

    marker = fake_dir / "memory" / ".unsummarized_sessions.json"
    marker.write_text(json.dumps([{"date": "2026-07-18"}]))

    result = run_hook(script_path)

    assert "ACTION REQUIRED: UNSUMMARIZED SESSIONS" in result.stdout
    assert "2026-07-18" in result.stdout
