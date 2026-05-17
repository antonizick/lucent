"""
Phase 3 Integration Tests for Lucent Email System.

Tests draft composition with Claude Sonnet:
- Tone detection (formal, urgent, casual)
- Sonnet reply composition with mocked client
- Fallback from full body to snippet
- Draft creation, review, and discard workflows
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.lucent_email.composer import DraftComposer
from src.lucent_email.config import DatabaseConfig, EmailConfig, IMAPConfig
from src.lucent_email.db import EmailDatabase
from src.lucent_email.email_service import EmailService
from src.lucent_email.models import Draft, EmailMetadata, FullEmail


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
def sample_email():
    """Create sample email for testing."""
    return EmailMetadata(
        id="email_1",
        backend="test",
        from_addr="alice@example.com",
        to_addrs=["nick@example.com"],
        subject="Q2 Review Feedback",
        timestamp=datetime.now(),
        snippet="Can you please review the Q2 metrics and provide feedback?",
        read=False,
    )


@pytest.fixture
def full_sample_email():
    """Create full email with body."""
    return FullEmail(
        id="email_1",
        backend="test",
        from_addr="alice@example.com",
        to_addrs=["nick@example.com"],
        subject="Q2 Review Feedback",
        timestamp=datetime.now(),
        snippet="Can you please review the Q2 metrics and provide feedback?",
        body="Hi Nick,\n\nCan you please review the Q2 metrics and provide feedback?\n\nI need your input by Friday EOD.\n\nThanks,\nAlice",
        read=False,
    )


class TestDraftComposer:
    """Test draft composition logic."""

    def test_detect_tone_formal(self):
        """Test formal tone detection."""
        subject = "Proposal for Contract Review"
        tone = DraftComposer.detect_tone(subject)
        assert tone == "formal"

    def test_detect_tone_urgent(self):
        """Test urgent tone detection."""
        subject = "URGENT: Action Required ASAP"
        tone = DraftComposer.detect_tone(subject)
        assert tone == "urgent"

    def test_detect_tone_casual(self):
        """Test casual (default) tone detection."""
        subject = "Quick question about the project"
        tone = DraftComposer.detect_tone(subject)
        assert tone == "casual"

    def test_compose_reply_with_full_body(self, sample_email, full_sample_email):
        """Test composing reply with full email body."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text="Hi Alice,\n\nThanks for sending the Q2 metrics. I've reviewed them and have some thoughts.\n\nBest,\nNick"
            )
        ]
        mock_client.messages.create.return_value = mock_response

        draft = DraftComposer.compose_reply(
            original_email=sample_email,
            full_email=full_sample_email,
            client=mock_client,
            model="test-model",
        )

        assert draft is not None
        assert draft.to_addrs == ["alice@example.com"]
        assert draft.subject == "Re: Q2 Review Feedback"
        assert draft.status == "pending_review"
        assert draft.responding_to_id == "email_1"
        assert "Hi Alice" in draft.body

    def test_compose_reply_fallback_to_snippet(self, sample_email):
        """Test composing reply falls back to snippet when full_email is None."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text="Hi Alice,\n\nThanks for reaching out. I'll review and get back to you.\n\nBest,\nNick"
            )
        ]
        mock_client.messages.create.return_value = mock_response

        draft = DraftComposer.compose_reply(
            original_email=sample_email,
            full_email=None,  # No full body available
            client=mock_client,
            model="test-model",
        )

        assert draft is not None
        assert "Hi Alice" in draft.body
        # Verify Sonnet was called with snippet in context
        assert mock_client.messages.create.called
        call_args = mock_client.messages.create.call_args
        assert "review" in call_args[1]["messages"][0]["content"].lower()

    def test_compose_new_email(self):
        """Test composing a new (non-reply) email."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text="Hi Bob,\n\nI wanted to check in about the project timeline.\n\nBest,\nNick"
            )
        ]
        mock_client.messages.create.return_value = mock_response

        draft = DraftComposer.compose_new(
            to="bob@example.com",
            subject="Project Timeline Check-in",
            context="Need to align on Q3 deliverables",
            client=mock_client,
            model="test-model",
        )

        assert draft is not None
        assert draft.to_addrs == ["bob@example.com"]
        assert draft.subject == "Project Timeline Check-in"
        assert draft.responding_to_id is None
        assert "Hi Bob" in draft.body

    def test_format_for_review(self):
        """Test draft formatting for review presentation."""
        draft = Draft(
            id="draft_1",
            to_addrs=["alice@example.com"],
            subject="Re: Q2 Review",
            body="Hi Alice,\n\nThanks for the feedback. I'll take a look.\n\nBest,\nNick",
            responding_to_id="email_1",
            status="pending_review",
        )

        formatted = DraftComposer.format_for_review(draft)

        assert "[Email]" in formatted
        assert "Draft ready for review" in formatted
        assert "alice@example.com" in formatted
        assert "Re: Q2 Review" in formatted
        assert "Hi Alice" in formatted
        assert "Approve, revise, or discard?" in formatted

    def test_format_for_review_long_body(self):
        """Test that long bodies are truncated in review."""
        long_body = "This is a very long email body. " * 100  # Over 500 chars
        draft = Draft(
            id="draft_1",
            to_addrs=["test@example.com"],
            subject="Long Email",
            body=long_body,
            status="pending_review",
        )

        formatted = DraftComposer.format_for_review(draft, show_body_limit=100)

        assert "..." in formatted
        assert len(formatted) < len(long_body) + 200


class TestEmailServiceComposition:
    """Test EmailService draft composition."""

    def test_compose_reply_with_full_body(self, test_config, sample_email):
        """Test compose_reply with full email fetch."""
        service = EmailService(test_config)

        # Insert test email
        service.db.insert_or_update_email(sample_email)

        # Mock Anthropic and get_email
        with patch.object(service, "_get_claude_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            with patch.object(service, "get_email") as mock_get_email:
                full_email = FullEmail(
                    **{
                        **sample_email.__dict__,
                        "body": "Full body content...",
                    }
                )
                mock_get_email.return_value = full_email

                with patch.object(
                    DraftComposer, "compose_reply"
                ) as mock_compose:
                    mock_draft = Draft(
                        id="",
                        to_addrs=["alice@example.com"],
                        subject="Re: Q2 Review",
                        body="Hi Alice, thanks for the feedback.",
                        responding_to_id="email_1",
                    )
                    mock_compose.return_value = mock_draft

                    draft_id = service.compose_reply("email_1")

                    assert draft_id  # Should return non-empty string
                    assert mock_compose.called

    def test_compose_reply_fallback_to_cached(self, test_config, sample_email):
        """Test compose_reply falls back to cached email if get_email fails."""
        service = EmailService(test_config)

        # Insert test email
        service.db.insert_or_update_email(sample_email)

        # Mock Anthropic and get_email (returns None)
        with patch.object(service, "_get_claude_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            with patch.object(service, "get_email", return_value=None):
                with patch.object(
                    DraftComposer, "compose_reply"
                ) as mock_compose:
                    mock_draft = Draft(
                        id="",
                        to_addrs=["alice@example.com"],
                        subject="Re: Q2 Review",
                        body="Hi Alice...",
                        responding_to_id="email_1",
                    )
                    mock_compose.return_value = mock_draft

                    draft_id = service.compose_reply("email_1")

                    # Should still compose using cached metadata
                    assert draft_id
                    assert mock_compose.called

    def test_compose_new_email(self, test_config):
        """Test composing a new email."""
        service = EmailService(test_config)

        with patch.object(service, "_get_claude_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            with patch.object(DraftComposer, "compose_new") as mock_compose:
                mock_draft = Draft(
                    id="",
                    to_addrs=["bob@example.com"],
                    subject="New Email",
                    body="Hi Bob...",
                )
                mock_compose.return_value = mock_draft

                draft_id = service.compose_new(
                    to="bob@example.com",
                    subject="New Email",
                    context="Test context",
                )

                assert draft_id
                assert mock_compose.called

    def test_discard_draft(self, test_config):
        """Test discarding a draft."""
        service = EmailService(test_config)

        # Create a draft
        draft = Draft(
            id="",
            to_addrs=["alice@example.com"],
            subject="Test",
            body="Test body",
        )
        draft_id = service.db.create_draft(draft)

        # Discard it
        result = service.discard_draft(draft_id)
        assert result is True

        # Verify status changed
        retrieved = service.get_draft(draft_id)
        assert retrieved.status == "discarded"

    def test_compose_reply_missing_email(self, test_config):
        """Test compose_reply with non-existent email ID."""
        service = EmailService(test_config)

        with patch.object(service, "_get_claude_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            with patch.object(service, "get_email", return_value=None):
                # Email doesn't exist in cache either
                draft_id = service.compose_reply("nonexistent_email")

                assert draft_id == ""  # Error case


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
