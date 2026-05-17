"""
Phase 4 Integration Tests for Lucent Email System.

Tests email sending with validation and safety checks:
- Recipient validation (format, presence)
- Subject/body validation
- Draft status validation
- Mock SMTP sending
- Sent email tracking
- Send confirmation
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.lucent_email.config import DatabaseConfig, EmailConfig, IMAPConfig
from src.lucent_email.db import EmailDatabase
from src.lucent_email.email_service import EmailService
from src.lucent_email.models import Draft
from src.lucent_email.sender import SendValidator


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
            email_address="nick@example.com",
            imap_host="imap.example.com",
        ),
        database=DatabaseConfig(path=str(temp_db.db_path)),
    )


@pytest.fixture
def approved_draft():
    """Create an approved draft."""
    return Draft(
        id="draft_1",
        to_addrs=["alice@example.com"],
        subject="Re: Q2 Review",
        body="Hi Alice,\n\nThanks for the feedback. I'll review the metrics.\n\nBest,\nNick",
        responding_to_id="email_1",
        status="approved",
    )


class TestSendValidator:
    """Test send validation logic."""

    def test_validate_approved_draft_valid(self, approved_draft):
        """Test that an approved draft validates."""
        errors = SendValidator.validate(approved_draft)
        assert errors == []
        assert SendValidator.is_valid(approved_draft)

    def test_validate_not_approved(self, approved_draft):
        """Test that unapproved drafts fail validation."""
        approved_draft.status = "pending_review"
        errors = SendValidator.validate(approved_draft)
        assert len(errors) > 0
        assert any("approved" in e.lower() for e in errors)

    def test_validate_empty_recipients(self, approved_draft):
        """Test that empty recipients fail validation."""
        approved_draft.to_addrs = []
        errors = SendValidator.validate(approved_draft)
        assert len(errors) > 0
        assert any("recipient" in e.lower() for e in errors)

    def test_validate_invalid_email_format(self, approved_draft):
        """Test that invalid email addresses fail validation."""
        approved_draft.to_addrs = ["not-an-email"]
        errors = SendValidator.validate(approved_draft)
        assert len(errors) > 0
        assert any("invalid" in e.lower() or "format" in e.lower() for e in errors)

    def test_validate_empty_subject(self, approved_draft):
        """Test that empty subject fails validation."""
        approved_draft.subject = ""
        errors = SendValidator.validate(approved_draft)
        assert len(errors) > 0
        assert any("subject" in e.lower() for e in errors)

    def test_validate_empty_body(self, approved_draft):
        """Test that empty body fails validation."""
        approved_draft.body = ""
        errors = SendValidator.validate(approved_draft)
        assert len(errors) > 0
        assert any("body" in e.lower() for e in errors)

    def test_validate_multiple_recipients(self, approved_draft):
        """Test that multiple valid recipients pass validation."""
        approved_draft.to_addrs = ["alice@example.com", "bob@example.com", "charlie@example.com"]
        errors = SendValidator.validate(approved_draft)
        assert errors == []


class TestSendDraft:
    """Test draft sending flow."""

    def test_send_draft_success(self, test_config, approved_draft):
        """Test successful draft send."""
        service = EmailService(test_config)
        draft_id = service.db.create_draft(approved_draft)

        # Approve it
        service.db.update_draft_status(draft_id, "approved")

        # Mock IMAP/SMTP
        with patch.object(service.imap_backend, "authenticate", return_value=True):
            with patch.object(service.imap_backend, "send_email", return_value=True):
                with patch("subprocess.run"):  # Mock voice box
                    result = service.send_draft(draft_id)

                    assert result is True
                    # Verify status changed to sent
                    retrieved = service.get_draft(draft_id)
                    assert retrieved.status == "sent"
                    assert retrieved.sent_at is not None

    def test_send_draft_validation_failure(self, test_config, approved_draft):
        """Test that validation failures prevent send."""
        service = EmailService(test_config)
        approved_draft.to_addrs = []  # Invalid: no recipients
        draft_id = service.db.create_draft(approved_draft)
        service.db.update_draft_status(draft_id, "approved")

        result = service.send_draft(draft_id)

        assert result is False
        # Status should still be "approved" (not sent)
        retrieved = service.get_draft(draft_id)
        assert retrieved.status == "approved"

    def test_send_draft_not_approved(self, test_config, approved_draft):
        """Test that non-approved drafts cannot be sent."""
        service = EmailService(test_config)
        approved_draft.status = "pending_review"
        draft_id = service.db.create_draft(approved_draft)

        result = service.send_draft(draft_id)

        assert result is False

    def test_send_draft_not_found(self, test_config):
        """Test sending non-existent draft returns False."""
        service = EmailService(test_config)

        result = service.send_draft("nonexistent_draft_id")

        assert result is False

    def test_send_draft_tracking(self, test_config, approved_draft):
        """Test that sent emails are tracked in cache."""
        service = EmailService(test_config)
        draft_id = service.db.create_draft(approved_draft)
        service.db.update_draft_status(draft_id, "approved")

        # Mock IMAP/SMTP and voice box
        with patch.object(service.imap_backend, "authenticate", return_value=True):
            with patch.object(service.imap_backend, "send_email", return_value=True):
                with patch("subprocess.run"):
                    service.send_draft(draft_id)

        # Check that sent email was added to cache
        sent_emails = service.list_emails(folder="Sent", limit=10)
        assert len(sent_emails) > 0
        sent = sent_emails[0]
        assert sent.to_addrs == ["alice@example.com"]
        assert sent.subject == "Re: Q2 Review"

    def test_send_draft_multiple_recipients(self, test_config):
        """Test sending to multiple recipients."""
        service = EmailService(test_config)
        draft = Draft(
            id="",
            to_addrs=["alice@example.com", "bob@example.com"],
            subject="Team Update",
            body="Hi everyone, here's the update.",
            status="pending_review",
        )
        draft_id = service.db.create_draft(draft)
        service.db.update_draft_status(draft_id, "approved")

        # Mock IMAP/SMTP
        with patch.object(service.imap_backend, "authenticate", return_value=True):
            with patch.object(
                service.imap_backend, "send_email"
            ) as mock_send:
                mock_send.return_value = True

                with patch("subprocess.run"):
                    result = service.send_draft(draft_id)

                    assert result is True
                    # Check that send_email was called with comma-separated addresses
                    assert mock_send.called
                    call_args = mock_send.call_args[0]
                    assert "alice@example.com" in call_args[0]
                    assert "bob@example.com" in call_args[0]

    def test_send_draft_confirmation_called(self, test_config, approved_draft):
        """Test that confirmation is called after successful send."""
        service = EmailService(test_config)
        draft_id = service.db.create_draft(approved_draft)
        service.db.update_draft_status(draft_id, "approved")

        # Mock IMAP/SMTP
        with patch.object(service.imap_backend, "authenticate", return_value=True):
            with patch.object(service.imap_backend, "send_email", return_value=True):
                with patch("subprocess.run") as mock_run:
                    service.send_draft(draft_id)

                    # Verify curl was called for voice box
                    assert mock_run.called
                    call_args = mock_run.call_args[0][0]
                    assert "curl" in call_args


class TestSentAtTimestamp:
    """Test that sent_at timestamp is set correctly."""

    def test_sent_at_set_on_status_change(self, test_config):
        """Test that sent_at is populated when status changes to 'sent'."""
        service = EmailService(test_config)
        draft = Draft(
            id="",
            to_addrs=["alice@example.com"],
            subject="Test",
            body="Test body",
        )
        draft_id = service.db.create_draft(draft)

        # Approve it
        service.db.update_draft_status(draft_id, "approved")
        retrieved = service.get_draft(draft_id)
        assert retrieved.approved_at is not None
        assert retrieved.sent_at is None

        # Mark as sent
        service.db.update_draft_status(draft_id, "sent")
        retrieved = service.get_draft(draft_id)
        assert retrieved.sent_at is not None
        assert retrieved.approved_at is not None


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
