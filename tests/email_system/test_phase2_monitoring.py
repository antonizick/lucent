"""
Phase 2 Integration Tests for Lucent Email System.

Tests priority detection and monitoring:
- Keyword-based pre-filtering
- Claude Haiku batch scoring
- EmailMonitor run_once() cycle
- Alert formatting
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.lucent_email.config import DatabaseConfig, EmailConfig, IMAPConfig
from src.lucent_email.db import EmailDatabase
from src.lucent_email.email_service import EmailService
from src.lucent_email.models import EmailMetadata
from src.lucent_email.monitor import EmailMonitor
from src.lucent_email.priority import PriorityDetector


@pytest.fixture
def temp_db():
    """Create temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = EmailDatabase(str(db_path))
        db.initialize_schema()
        yield db
        db.close()


@pytest.fixture
def test_config(temp_db):
    """Create test configuration."""
    return EmailConfig(
        pst_file_path="/nonexistent/test.pst",
        imap=IMAPConfig(
            email_address="test@example.com",
            imap_host="imap.example.com",
        ),
        database=DatabaseConfig(path=str(temp_db.db_path)),
    )


@pytest.fixture
def sample_emails():
    """Create sample emails for testing."""
    return [
        EmailMetadata(
            id="test_1",
            backend="test",
            from_addr="alice@example.com",
            to_addrs=["nick@example.com"],
            subject="Q2 Review - Urgent feedback needed",
            timestamp=datetime.now(),
            snippet="Please review the Q2 performance metrics and provide feedback by EOD",
            read=False,
        ),
        EmailMetadata(
            id="test_2",
            backend="test",
            from_addr="newsletter@marketing.com",
            to_addrs=["nick@example.com"],
            subject="Weekly Tech Newsletter - Issue #42",
            timestamp=datetime.now(),
            snippet="This week's top tech stories and trends...",
            read=False,
        ),
        EmailMetadata(
            id="test_3",
            backend="test",
            from_addr="bob@example.com",
            to_addrs=["nick@example.com"],
            subject="Budget approval ASAP",
            timestamp=datetime.now(),
            snippet="Need your signature on the Q3 budget before tomorrow",
            read=False,
            flagged=True,
        ),
    ]


class TestPriorityDetector:
    """Test priority detection logic."""

    def test_keyword_prefilter_low_priority(self):
        """Test that newsletters are scored low."""
        email = EmailMetadata(
            id="test_1",
            backend="test",
            from_addr="newsletter@example.com",
            to_addrs=[],
            subject="Weekly Newsletter",
            timestamp=datetime.now(),
            snippet="This week's top stories",
        )

        score = PriorityDetector.keyword_prefilter(email)
        assert score == 0.0, "Newsletter should score 0"

    def test_keyword_prefilter_high_priority(self):
        """Test that urgent emails are scored high."""
        email = EmailMetadata(
            id="test_2",
            backend="test",
            from_addr="alice@example.com",
            to_addrs=[],
            subject="URGENT: Please review ASAP",
            timestamp=datetime.now(),
            snippet="This needs immediate attention",
        )

        score = PriorityDetector.keyword_prefilter(email)
        assert score == 9.0, "Urgent email should score 9"

    def test_keyword_prefilter_flagged(self):
        """Test that flagged emails are scored high."""
        email = EmailMetadata(
            id="test_3",
            backend="test",
            from_addr="bob@example.com",
            to_addrs=[],
            subject="Regular message",
            timestamp=datetime.now(),
            snippet="Just a normal email",
            flagged=True,
        )

        score = PriorityDetector.keyword_prefilter(email)
        assert score == 8.0, "Flagged email should score 8"

    def test_keyword_prefilter_unknown(self):
        """Test that unknown emails return None for further analysis."""
        email = EmailMetadata(
            id="test_4",
            backend="test",
            from_addr="alice@example.com",
            to_addrs=[],
            subject="Thoughts on the proposal",
            timestamp=datetime.now(),
            snippet="I have some feedback on this proposal",
        )

        score = PriorityDetector.keyword_prefilter(email)
        assert score is None, "Unknown priority should return None"

    def test_score_emails_with_prefilter_only(self, sample_emails):
        """Test scoring batch that all get prefiltered."""
        # All test emails have clear prefilter signals
        client = MagicMock()  # Unused, since prefilter handles all

        scores = PriorityDetector.score_emails(sample_emails, client, "test-model")

        # Should have scores for all
        assert len(scores) == 3
        assert scores["test_1"] == 9.0, "Urgent should be 9"
        assert scores["test_2"] == 0.0, "Newsletter should be 0"
        assert scores["test_3"] == 9.0, "ASAP keyword should be 9"
        # Haiku should not have been called
        assert not client.messages.create.called

    def test_score_emails_with_haiku_fallback(self):
        """Test scoring with Haiku batch call."""
        emails = [
            EmailMetadata(
                id="test_ambiguous",
                backend="test",
                from_addr="alice@example.com",
                to_addrs=[],
                subject="Meeting feedback",
                timestamp=datetime.now(),
                snippet="What did you think of the meeting?",
            ),
        ]

        # Mock Anthropic response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='[{"id": "test_ambiguous", "score": 6.5}]')
        ]
        mock_client.messages.create.return_value = mock_response

        scores = PriorityDetector.score_emails(emails, mock_client, "test-model")

        assert "test_ambiguous" in scores
        assert scores["test_ambiguous"] == 6.5
        assert mock_client.messages.create.called

    def test_score_emails_haiku_error_fallback(self):
        """Test fallback to prefilter when Haiku fails."""
        emails = [
            EmailMetadata(
                id="test_error",
                backend="test",
                from_addr="alice@example.com",
                to_addrs=[],
                subject="Help needed urgently",
                timestamp=datetime.now(),
                snippet="Can you assist?",
            ),
        ]

        # Mock error
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("API error")

        scores = PriorityDetector.score_emails(emails, mock_client, "test-model")

        # Should fall back to prefilter
        assert "test_error" in scores
        assert scores["test_error"] == 9.0, "Should fallback to keyword prefilter"


class TestEmailServicePriority:
    """Test EmailService priority methods."""

    def test_detect_high_priority_emails(self, temp_db, test_config, sample_emails):
        """Test high-priority email detection."""
        service = EmailService(test_config)

        # Insert test emails
        for email in sample_emails:
            service.db.insert_or_update_email(email)

        # Mock Anthropic client
        with patch("src.lucent_email.email_service.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client

            # Mock priority detection (prefilter will handle these)
            with patch.object(
                service, "_get_claude_client", return_value=mock_client
            ):
                high_priority = service.detect_high_priority_emails(limit=10)

                # Should find urgent and flagged emails (test_1 and test_3)
                assert len(high_priority) >= 1
                ids = [e.id for e in high_priority]
                assert "test_1" in ids or "test_3" in ids

    def test_score_new_emails(self, test_config, sample_emails):
        """Test scoring and persisting emails."""
        service = EmailService(test_config)

        # Mock Anthropic
        with patch.object(service, "_get_claude_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            scores = service.score_new_emails(sample_emails)

            # Prefilter should handle all
            assert len(scores) == 3
            assert scores["test_1"] == 9.0
            assert scores["test_2"] == 0.0
            assert scores["test_3"] == 9.0


class TestEmailMonitor:
    """Test background monitoring."""

    def test_monitor_initialization(self, test_config):
        """Test monitor setup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = EmailService(test_config)
            note_path = Path(tmpdir) / "test.md"
            note_path.touch()

            monitor = EmailMonitor(service, test_config, note_path=note_path)

            assert monitor.config == test_config
            assert monitor.note_path == note_path
            assert not monitor._running

    def test_monitor_run_once(self, test_config, sample_emails):
        """Test single sync+score pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = EmailService(test_config)
            note_path = Path(tmpdir) / "test.md"
            note_path.touch()

            # Insert test emails
            for email in sample_emails:
                service.db.insert_or_update_email(email)

            monitor = EmailMonitor(service, test_config, note_path=note_path)

            # Mock sync and alert
            with patch.object(monitor, "_sync_and_alert") as mock_sync:
                monitor.run_once()
                assert mock_sync.called

    def test_monitor_alert_formatting(self, test_config, sample_emails):
        """Test alert message formatting."""
        monitor = EmailMonitor(None, test_config)

        high_priority = [sample_emails[0], sample_emails[2]]  # test_1, test_3

        # Mock voice box and note write
        with patch("src.lucent_email.monitor.subprocess.run"):
            with patch.object(monitor, "_append_daily_note") as mock_note:
                monitor._send_alert(high_priority)

                # Check that note was appended
                assert mock_note.called
                call_args = mock_note.call_args[0][0]
                assert "[Email]" in call_args
                assert "2 high-priority" in call_args

    def test_monitor_start_stop(self, test_config):
        """Test monitor thread lifecycle."""
        service = EmailService(test_config)
        monitor = EmailMonitor(service, test_config)

        monitor.start()
        assert monitor._running
        assert monitor._thread is not None

        monitor.stop()
        assert not monitor._running


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
