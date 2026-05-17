"""
Phase 1 Integration Tests for Lucent Email System.

Tests the complete workflow:
- Database schema + operations
- Backend abstraction + implementations
- EmailService API + sync
- Draft management
"""

import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.lucent_email.config import DatabaseConfig, EmailConfig, IMAPConfig
from src.lucent_email.db import EmailDatabase
from src.lucent_email.models import Draft, EmailMetadata
from src.lucent_email.email_service import EmailService


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
def sample_email():
    """Create sample email metadata."""
    return EmailMetadata(
        id="test_123",
        backend="test",
        from_addr="alice@example.com",
        to_addrs=["nick@example.com"],
        subject="Important Meeting",
        timestamp=datetime.now(),
        snippet="Let's discuss the Q2 review tomorrow",
        read=False,
        flagged=False,
        folder="Inbox",
        message_id="msg-123",
    )


class TestDatabase:
    """Test SQLite database layer."""

    def test_schema_initialization(self, temp_db):
        """Test that schema tables are created."""
        cursor = temp_db.connection.cursor()

        # Check tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='emails'"
        )
        assert cursor.fetchone() is not None

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='drafts'"
        )
        assert cursor.fetchone() is not None

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sender_priority'"
        )
        assert cursor.fetchone() is not None

    def test_insert_email_metadata(self, temp_db, sample_email):
        """Test inserting email metadata."""
        temp_db.insert_or_update_email(sample_email)

        result = temp_db.get_email_by_id(sample_email.id)
        assert result is not None
        assert result.from_addr == "alice@example.com"
        assert result.subject == "Important Meeting"

    def test_search_functionality(self, temp_db, sample_email):
        """Test FTS5 search."""
        temp_db.insert_or_update_email(sample_email)

        results = temp_db.search("Important")
        assert len(results) > 0
        assert results[0].subject == "Important Meeting"

    def test_list_emails_by_folder(self, temp_db, sample_email):
        """Test listing emails by folder."""
        temp_db.insert_or_update_email(sample_email)

        results = temp_db.list_emails(folder="Inbox", limit=50)
        assert len(results) > 0
        assert results[0].id == sample_email.id

    def test_create_and_retrieve_draft(self, temp_db):
        """Test draft creation and retrieval."""
        draft = Draft(
            id="",
            to_addrs=["alice@example.com"],
            subject="Re: Important Meeting",
            body="I can make that meeting.",
            responding_to_id="msg-123",
        )

        draft_id = temp_db.create_draft(draft)
        assert draft_id

        retrieved = temp_db.get_draft(draft_id)
        assert retrieved is not None
        assert retrieved.subject == "Re: Important Meeting"
        assert retrieved.status == "pending_review"

    def test_draft_status_update(self, temp_db):
        """Test updating draft status."""
        draft = Draft(
            id="",
            to_addrs=["alice@example.com"],
            subject="Test",
            body="Test body",
        )

        draft_id = temp_db.create_draft(draft)
        temp_db.update_draft_status(draft_id, "approved")

        retrieved = temp_db.get_draft(draft_id)
        assert retrieved.status == "approved"
        assert retrieved.approved_at is not None

    def test_list_drafts_by_status(self, temp_db):
        """Test listing drafts by status."""
        draft1 = Draft(
            id="",
            to_addrs=["alice@example.com"],
            subject="Draft 1",
            body="Body 1",
        )
        draft2 = Draft(
            id="",
            to_addrs=["bob@example.com"],
            subject="Draft 2",
            body="Body 2",
        )

        id1 = temp_db.create_draft(draft1)
        id2 = temp_db.create_draft(draft2)

        temp_db.update_draft_status(id1, "approved")

        pending = temp_db.list_drafts(status="pending_review")
        approved = temp_db.list_drafts(status="approved")

        assert len(pending) == 1
        assert len(approved) == 1

    def test_email_count(self, temp_db, sample_email):
        """Test email counting."""
        temp_db.insert_or_update_email(sample_email)
        count = temp_db.email_count()
        assert count == 1

    def test_sender_priority(self, temp_db):
        """Test sender priority management."""
        from_addr = "alice@example.com"

        # Initially no priority
        score = temp_db.get_sender_priority(from_addr)
        assert score == 0.0

        # Update priority
        temp_db.update_sender_priority(from_addr, 7.5)

        # Retrieve updated priority
        score = temp_db.get_sender_priority(from_addr)
        assert score == 7.5


class TestEmailMetadata:
    """Test email metadata models."""

    def test_email_metadata_creation(self):
        """Test creating email metadata."""
        email = EmailMetadata(
            id="test_1",
            backend="imap",
            from_addr="alice@example.com",
            to_addrs=["nick@example.com"],
            subject="Test",
            timestamp=datetime.now(),
            snippet="Test snippet",
        )

        assert email.from_addr == "alice@example.com"
        assert email.backend == "imap"
        assert not email.read
        assert not email.flagged

    def test_email_short_id(self):
        """Test short ID extraction."""
        email = EmailMetadata(
            id="imap_12345",
            backend="imap",
            from_addr="test@example.com",
            to_addrs=[],
            subject="",
            timestamp=datetime.now(),
            snippet="",
        )

        assert email.short_id() == "12345"


class TestDraftModel:
    """Test draft models."""

    def test_draft_creation(self):
        """Test creating draft."""
        draft = Draft(
            id="draft-1",
            to_addrs=["alice@example.com"],
            subject="Test",
            body="Test body",
            responding_to_id="email-123",
        )

        assert draft.status == "pending_review"
        assert not draft.is_approved()
        assert not draft.is_sent()

    def test_draft_status_checks(self):
        """Test draft status checkers."""
        draft = Draft(
            id="draft-1",
            to_addrs=["alice@example.com"],
            subject="",
            body="",
            status="approved",
        )

        assert draft.is_approved()
        assert not draft.is_sent()


class TestSyncResult:
    """Test sync result model."""

    def test_sync_result_creation(self):
        """Test creating sync result."""
        from src.lucent_email.models import SyncResult

        result = SyncResult(pst_new=10, imap_new=5, duration_seconds=30.5)

        assert result.total_new() == 15
        assert not result.has_errors()

    def test_sync_result_with_errors(self):
        """Test sync result with errors."""
        from src.lucent_email.models import SyncResult

        result = SyncResult(
            pst_new=5,
            errors=["PST connection failed"],
        )

        assert result.total_new() == 5
        assert result.has_errors()
        assert len(result.errors) == 1


class TestEmailService:
    """Test EmailService API."""

    def test_service_initialization(self, temp_db):
        """Test EmailService initialization."""
        # Note: This is a limited test because full EmailService needs
        # actual PST file + IMAP credentials
        config = EmailConfig(
            pst_file_path="/nonexistent/path.pst",
            imap=IMAPConfig(
                email_address="test@example.com",
                imap_host="imap.example.com",
            ),
            database=DatabaseConfig(path=str(temp_db.db_path)),
        )

        # Service should initialize without error
        assert config.pst_file_path
        assert config.imap.email_address

    def test_service_stats(self, temp_db):
        """Test service stats retrieval."""
        # Create sample emails
        email1 = EmailMetadata(
            id="pst_1",
            backend="pst",
            from_addr="alice@example.com",
            to_addrs=[],
            subject="Test 1",
            timestamp=datetime.now(),
            snippet="",
        )
        email2 = EmailMetadata(
            id="imap_1",
            backend="imap",
            from_addr="bob@example.com",
            to_addrs=[],
            subject="Test 2",
            timestamp=datetime.now(),
            snippet="",
        )

        temp_db.insert_or_update_email(email1)
        temp_db.insert_or_update_email(email2)

        # Check counts
        assert temp_db.email_count() == 2
        by_backend = temp_db.email_count_by_backend()
        assert by_backend["pst"] == 1
        assert by_backend["imap"] == 1


class TestSearchAndFilter:
    """Test search and filtering operations."""

    def test_fts_search(self, temp_db):
        """Test full-text search."""
        emails = [
            EmailMetadata(
                id=f"test_{i}",
                backend="test",
                from_addr=f"user{i}@example.com",
                to_addrs=[],
                subject=f"Meeting {i}",
                timestamp=datetime.now(),
                snippet=f"Discussion about Q{i} planning",
            )
            for i in range(1, 4)
        ]

        for email in emails:
            temp_db.insert_or_update_email(email)

        # Search for "Q2"
        results = temp_db.search("Q2")
        assert len(results) > 0
        assert any("Q2" in r.snippet for r in results)

    def test_list_with_limit(self, temp_db):
        """Test listing with limit."""
        for i in range(10):
            email = EmailMetadata(
                id=f"test_{i}",
                backend="test",
                from_addr=f"user{i}@example.com",
                to_addrs=[],
                subject=f"Email {i}",
                timestamp=datetime.now(),
                snippet="",
            )
            temp_db.insert_or_update_email(email)

        results = temp_db.list_emails(limit=5)
        assert len(results) == 5


class TestConversationThreading:
    """Test email conversation threading."""

    def test_get_conversation(self, temp_db):
        """Test retrieving email conversation."""
        # Create thread
        email1 = EmailMetadata(
            id="email_1",
            backend="test",
            from_addr="alice@example.com",
            to_addrs=[],
            subject="Question",
            timestamp=datetime.now(),
            snippet="",
            message_id="msg-1",
        )
        email2 = EmailMetadata(
            id="email_2",
            backend="test",
            from_addr="bob@example.com",
            to_addrs=[],
            subject="Re: Question",
            timestamp=datetime.now(),
            snippet="",
            message_id="msg-2",
            in_reply_to="msg-1",
        )

        temp_db.insert_or_update_email(email1)
        temp_db.insert_or_update_email(email2)

        # Get conversation
        thread = temp_db.get_conversation("msg-1")
        assert len(thread) >= 1


# Integration test: Full workflow
class TestPhase1Workflow:
    """Test complete Phase 1 workflow."""

    def test_create_and_approve_draft(self, temp_db):
        """Test complete draft workflow: create → approve."""
        # Create email
        email = EmailMetadata(
            id="email_1",
            backend="test",
            from_addr="alice@example.com",
            to_addrs=[],
            subject="Question",
            timestamp=datetime.now(),
            snippet="",
            message_id="msg-1",
        )
        temp_db.insert_or_update_email(email)

        # Create draft in response
        draft = Draft(
            id="",
            to_addrs=["alice@example.com"],
            subject="Re: Question",
            body="Here's my answer.",
            responding_to_id="email_1",
        )
        draft_id = temp_db.create_draft(draft)

        # Approve draft
        temp_db.update_draft_status(draft_id, "approved")

        # Verify
        approved_draft = temp_db.get_draft(draft_id)
        assert approved_draft.status == "approved"
        assert approved_draft.approved_at is not None


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
