"""M1 memory-integrity tests — scripts/guard_memory_write.py.

Root cause this hook exists for: the 2026-07-17 incident where a Write
tool call replaced memory/2026-07-17.md's 201 lines with 5, deleting a
day's session record, with nothing validating the new content first.

The hook's actual interface is a subprocess: Claude Code invokes it via
``python3 scripts/guard_memory_write.py``, feeds the PreToolUse payload
as JSON on stdin, and reads a JSON permission decision from stdout. That
subprocess boundary is exercised directly here — not by importing and
calling its internals — since that IS the real surface.

Isolation: every payload targets a file under ``tmp_path``, never
anything in the real ``memory/`` tree.
"""
import json
import subprocess
import sys
from pathlib import Path

GUARD = Path(__file__).resolve().parents[2] / "scripts" / "guard_memory_write.py"


def run_guard(payload: dict) -> dict:
    result = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"guard exited nonzero: {result.stderr}"
    return json.loads(result.stdout)["hookSpecificOutput"]


def _payload(file_path: str, content: str) -> dict:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


def test_drastic_shrink_of_daily_note_is_denied(tmp_path):
    note = tmp_path / "2026-07-17.md"
    note.write_text("\n".join(f"line {i}" for i in range(200)))

    decision = run_guard(_payload(str(note), "line 1\nline 2\n"))
    assert decision["permissionDecision"] == "deny"
    assert "200" in decision["permissionDecisionReason"] or "shrink" in decision["permissionDecisionReason"].lower()


def test_archive_path_shrink_is_also_denied(tmp_path):
    """The regex covers archive/YYYY-MM-DD.md too, not just the live note."""
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    note = archive_dir / "2026-07-17.md"
    note.write_text("\n".join(f"line {i}" for i in range(200)))

    decision = run_guard(_payload(str(note), "short\n"))
    assert decision["permissionDecision"] == "deny"


def test_normal_append_sized_write_is_allowed(tmp_path):
    note = tmp_path / "2026-07-18.md"
    note.write_text("\n".join(f"line {i}" for i in range(200)))
    grown = note.read_text() + "\nnew entry for today\n"

    decision = run_guard(_payload(str(note), grown))
    assert decision["permissionDecision"] == "allow"


def test_new_file_with_no_existing_content_is_allowed(tmp_path):
    note = tmp_path / "2026-07-19.md"  # does not exist yet
    decision = run_guard(_payload(str(note), "first entry\n"))
    assert decision["permissionDecision"] == "allow"


def test_unsummarized_placeholder_shrink_is_allowlisted(tmp_path):
    """The known legitimate shrink case: auto-compress writes a short
    placeholder into yesterday's note, marked with 'UNSUMMARIZED'."""
    note = tmp_path / "2026-07-17.md"
    note.write_text("\n".join(f"line {i}" for i in range(200)))

    decision = run_guard(_payload(str(note), "UNSUMMARIZED — see archive\n"))
    assert decision["permissionDecision"] == "allow"


def test_non_daily_note_write_is_ignored(tmp_path):
    """A drastic shrink of a file that ISN'T a daily note/archive is none
    of this guard's business — it must not block unrelated Writes."""
    other = tmp_path / "notes.md"
    other.write_text("\n".join(f"line {i}" for i in range(200)))

    decision = run_guard(_payload(str(other), "short\n"))
    assert decision["permissionDecision"] == "allow"


def test_non_write_tool_is_ignored(tmp_path):
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "2026-07-17.md")}}
    decision = run_guard(payload)
    assert decision["permissionDecision"] == "allow"


def test_malformed_stdin_fails_open(tmp_path):
    """A broken/garbage payload must not block all Writes — fail open."""
    result = subprocess.run(
        [sys.executable, str(GUARD)],
        input="not json at all {{{",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "allow"


def test_small_file_below_threshold_is_ignored(tmp_path):
    """Files under MIN_EXISTING_LINES (20) are exempt — avoids false
    positives on brand-new or tiny notes."""
    note = tmp_path / "2026-07-20.md"
    note.write_text("\n".join(f"line {i}" for i in range(10)))
    decision = run_guard(_payload(str(note), "x\n"))
    assert decision["permissionDecision"] == "allow"
