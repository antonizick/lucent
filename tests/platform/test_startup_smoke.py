"""M1 Phase 2 hook smoke tests — scripts/startup.py.

startup.py's ``run()``/``main()`` orchestrate real side effects (network
health checks, a possible ``bash start.sh`` restart, a compression
subprocess, checkpoint writes, and — at the day boundary — real voice
announcements). Invoking that live, even in a test, would violate the
"never hit prod services / mutate memory/ / send real voice" constraint,
so this suite does NOT run ``main()`` or ``run()`` end-to-end.

Instead it exercises the individual check functions the orchestrator is
built from — each reads ``LUCENT_ROOT`` as a module-level global at call
time, so monkeypatching ``startup.LUCENT_ROOT`` to a ``tmp_path`` fully
isolates them from the real ``memory/`` tree. This directly tests the M1
claim: these checks must degrade gracefully, never crash, when their
expected files are missing.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import startup  # noqa: E402


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    (tmp_path / "memory").mkdir()
    monkeypatch.setattr(startup, "LUCENT_ROOT", tmp_path)
    return tmp_path


# --- check_context_files ----------------------------------------------
def test_check_context_files_all_missing_reports_missing_not_crash(fake_root):
    result = startup.check_context_files()
    assert result.ok is False
    assert "LTMemory.md" in result.reason
    assert "core.md" in result.reason


def test_check_context_files_all_present_ok(fake_root):
    for rel in startup.REQUIRED_CONTEXT_FILES:
        p = fake_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    from datetime import date
    (fake_root / "memory" / f"{date.today().isoformat()}.md").write_text("x")

    result = startup.check_context_files()
    assert result.ok is True


# --- check_ltmemory_completeness ---------------------------------------
def test_ltmemory_completeness_missing_file_is_ok(fake_root):
    """No LTMemory.md yet (fresh install) must not be treated as a stub."""
    result = startup.check_ltmemory_completeness()
    assert result.ok is True


def test_ltmemory_completeness_detects_stub_marker(fake_root):
    ltmem = fake_root / "memory" / "LTMemory.md"
    ltmem.write_text(
        "## Recent Sessions\n\n"
        "### Session 2026-07-19\n"
        "**⚠️ UNSUMMARIZED** — See full details in memory/archive/2026-07-19.md\n"
    )
    result = startup.check_ltmemory_completeness()
    assert result.ok is False
    assert "stub" in result.reason.lower()


def test_ltmemory_completeness_detects_too_brief_session(fake_root):
    ltmem = fake_root / "memory" / "LTMemory.md"
    ltmem.write_text(
        "## Recent Sessions\n\n"
        "### Session 2026-07-19\n"
        "- just one bullet\n"
    )
    result = startup.check_ltmemory_completeness()
    assert result.ok is False


def test_ltmemory_completeness_accepts_real_summary(fake_root):
    # NOTE: pins an observed off-by-one, not the documented intent. The
    # bullet_count logic does `session_content.count('\n-')`, but the
    # regex-captured session_content starts immediately after the
    # header's own '\n' — so the FIRST bullet line has no leading '\n-'
    # inside the captured group and is never counted. A session with
    # exactly 3 bullets (the threshold CLAUDE.md and this function's own
    # docstring call sufficient) measures bullet_count=2 and is wrongly
    # flagged as a stub; 4 bullets are required in practice. Flagged to
    # Nick as a real finding — not fixed here (out of scope for M1 test
    # authoring, and curator.py may share the same counting convention).
    ltmem = fake_root / "memory" / "LTMemory.md"
    ltmem.write_text(
        "## Recent Sessions\n\n"
        "### Session 2026-07-19\n"
        "- did the first thing\n"
        "- did the second thing\n"
        "- did the third thing\n"
        "- did a fourth thing\n"
    )
    result = startup.check_ltmemory_completeness()
    assert result.ok is True


def test_ltmemory_completeness_off_by_one_flags_documented_minimum_as_stub(fake_root):
    """Regression pin for the off-by-one above: a session with exactly the
    3 bullets CLAUDE.md/the docstring call sufficient is (incorrectly)
    flagged as a stub today. If this test starts failing because someone
    fixed the off-by-one, delete this test and keep only the 4-bullet
    happy-path test above."""
    ltmem = fake_root / "memory" / "LTMemory.md"
    ltmem.write_text(
        "## Recent Sessions\n\n"
        "### Session 2026-07-19\n"
        "- did the first thing\n"
        "- did the second thing\n"
        "- did the third thing\n"
    )
    result = startup.check_ltmemory_completeness()
    assert result.ok is False


def test_ltmemory_completeness_unreadable_file_is_nonfatal(fake_root, monkeypatch):
    """Any exception scanning LTMemory.md must be non-fatal (ok=True with
    a note), never propagate and crash startup."""
    ltmem = fake_root / "memory" / "LTMemory.md"
    ltmem.write_text("some content")
    ltmem.chmod(0o000)
    try:
        result = startup.check_ltmemory_completeness()
        assert result.ok is True
    finally:
        ltmem.chmod(0o644)  # restore so tmp_path cleanup can remove it


# --- check_ltmemory_size -------------------------------------------------
def test_ltmemory_size_missing_file_is_ok(fake_root):
    result = startup.check_ltmemory_size()
    assert result.ok is True


def test_ltmemory_size_within_threshold_is_ok(fake_root):
    ltmem = fake_root / "memory" / "LTMemory.md"
    ltmem.write_text("short\n" * 10)
    result = startup.check_ltmemory_size()
    assert result.ok is True


def test_ltmemory_size_over_threshold_warns_not_crashes(fake_root):
    ltmem = fake_root / "memory" / "LTMemory.md"
    ltmem.write_text("x" * 26_000)
    result = startup.check_ltmemory_size()
    assert result.ok is False
    assert "curator.py" in result.reason


# --- check_voice_box (network-resilience, not a prod dependency) --------
def test_check_voice_box_unreachable_port_returns_ok_false_not_crash():
    """Port 1 is a real, always-closed low port — proves the health check
    degrades to a clean CheckResult instead of raising when the service
    is down. Does not touch any Lucent service."""
    result = startup.check_voice_box(port=1, timeout=1.0)
    assert result.ok is False
    assert isinstance(result.reason, str) and result.reason
