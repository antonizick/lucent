"""
Phase 5 Integration Tests for Lucent Email System.

Tests adaptive priority learning from user behavior:
- Response time scoring across all time brackets
- Cold-start, ramp-up, and mature blending
- Sender interaction tracking with running averages
- Blended priority computation
- Reply recording integration
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.lucent_email.config import DatabaseConfig, EmailConfig, IMAPConfig
from src.lucent_email.db import EmailDatabase
from src.lucent_email.email_service import EmailService
from src.lucent_email.learner import PriorityLearner
from src.lucent_email.models import Draft, EmailMetadata


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


class TestPriorityLearner:
    """Test PriorityLearner scoring logic."""

    def test_score_from_history_less_than_1_hour(self):
        """Test response time < 1 hour scores 10.0."""
        score = PriorityLearner.score_from_history(
            interaction_count=10,
            response_time_avg_seconds=1800,  # 30 minutes
        )
        assert score == 10.0

    def test_score_from_history_1_to_4_hours(self):
        """Test response time between 1-4 hours scores 8.0."""
        score = PriorityLearner.score_from_history(
            interaction_count=10,
            response_time_avg_seconds=7200,  # 2 hours
        )
        assert score == 8.0

    def test_score_from_history_4_to_24_hours(self):
        """Test response time between 4-24 hours scores 6.0."""
        score = PriorityLearner.score_from_history(
            interaction_count=10,
            response_time_avg_seconds=43200,  # 12 hours
        )
        assert score == 6.0

    def test_score_from_history_1_to_7_days(self):
        """Test response time between 1-7 days scores 4.0."""
        score = PriorityLearner.score_from_history(
            interaction_count=10,
            response_time_avg_seconds=259200,  # 3 days
        )
        assert score == 4.0

    def test_score_from_history_more_than_7_days(self):
        """Test response time >= 7 days scores 2.0."""
        score = PriorityLearner.score_from_history(
            interaction_count=10,
            response_time_avg_seconds=1209600,  # 14 days
        )
        assert score == 2.0

    def test_score_from_history_no_interactions(self):
        """Test that zero interactions returns 0.0."""
        score = PriorityLearner.score_from_history(
            interaction_count=0,
            response_time_avg_seconds=1800,  # Would be 10.0 otherwise
        )
        assert score == 0.0

    def test_score_from_history_partial_weight(self):
        """Test interaction count weighting (1-9 interactions)."""
        # 5 interactions: weight = min(5/10, 1.0) = 0.5
        # 1 hour response → 10.0 * 0.5 = 5.0
        score = PriorityLearner.score_from_history(
            interaction_count=5,
            response_time_avg_seconds=1800,
        )
        assert score == 5.0

    def test_blend_cold_start(self):
        """Test cold start (0 interactions) returns haiku score unchanged."""
        blended = PriorityLearner.blend(
            haiku_score=7.5,
            behavioral_score=9.0,
            interaction_count=0,
        )
        assert blended == 7.5

    def test_blend_ramp_up_1_interaction(self):
        """Test ramp up at 1 interaction."""
        # behavioral_weight = min(1/10, 1.0) * 0.4 = 0.04
        # haiku_weight = 1.0 - 0.04 = 0.96
        # blended = 5.0 * 0.96 + 10.0 * 0.04 = 4.8 + 0.4 = 5.2
        blended = PriorityLearner.blend(
            haiku_score=5.0,
            behavioral_score=10.0,
            interaction_count=1,
        )
        assert abs(blended - 5.2) < 0.01

    def test_blend_ramp_up_5_interactions(self):
        """Test ramp up at 5 interactions (halfway)."""
        # behavioral_weight = min(5/10, 1.0) * 0.4 = 0.2
        # haiku_weight = 1.0 - 0.2 = 0.8
        # blended = 5.0 * 0.8 + 10.0 * 0.2 = 4.0 + 2.0 = 6.0
        blended = PriorityLearner.blend(
            haiku_score=5.0,
            behavioral_score=10.0,
            interaction_count=5,
        )
        assert abs(blended - 6.0) < 0.01

    def test_blend_mature_10_interactions(self):
        """Test mature (10+ interactions) uses 60/40 mix."""
        # behavioral_weight = min(10/10, 1.0) * 0.4 = 0.4
        # haiku_weight = 1.0 - 0.4 = 0.6
        # blended = 5.0 * 0.6 + 10.0 * 0.4 = 3.0 + 4.0 = 7.0
        blended = PriorityLearner.blend(
            haiku_score=5.0,
            behavioral_score=10.0,
            interaction_count=10,
        )
        assert abs(blended - 7.0) < 0.01

    def test_blend_mature_100_interactions(self):
        """Test mature (100+ interactions) still uses 60/40 mix (capped)."""
        # behavioral_weight = min(100/10, 1.0) * 0.4 = 0.4 (capped at 1.0)
        # haiku_weight = 0.6
        blended = PriorityLearner.blend(
            haiku_score=5.0,
            behavioral_score=10.0,
            interaction_count=100,
        )
        assert abs(blended - 7.0) < 0.01

    def test_blend_clamps_to_0_10_range(self):
        """Test that blend result is clamped to 0-10."""
        # Both scores at extremes
        blended = PriorityLearner.blend(
            haiku_score=10.0,
            behavioral_score=10.0,
            interaction_count=10,
        )
        assert 0.0 <= blended <= 10.0
        assert blended == 10.0


class TestSenderInteractionTracking:
    """Test sender interaction history tracking."""

    def test_update_sender_interaction_first_reply(self, temp_db):
        """Test first interaction creates new sender history."""
        temp_db.update_sender_interaction("alice@example.com", 1800.0)

        history = temp_db.get_sender_history("alice@example.com")
        assert history["interaction_count"] == 1
        assert history["response_time_avg"] == 1800.0

    def test_update_sender_interaction_running_average(self, temp_db):
        """Test running average calculation for multiple interactions."""
        # First interaction: 1 hour
        temp_db.update_sender_interaction("alice@example.com", 3600.0)

        # Second interaction: 2 hours
        temp_db.update_sender_interaction("alice@example.com", 7200.0)

        # Average: (3600 * 1 + 7200) / 2 = 5400
        history = temp_db.get_sender_history("alice@example.com")
        assert history["interaction_count"] == 2
        assert abs(history["response_time_avg"] - 5400.0) < 0.01

    def test_update_sender_interaction_three_replies(self, temp_db):
        """Test running average with three interactions."""
        temp_db.update_sender_interaction("bob@example.com", 1800.0)  # 30 min
        temp_db.update_sender_interaction("bob@example.com", 3600.0)  # 1 hour
        temp_db.update_sender_interaction("bob@example.com", 7200.0)  # 2 hours

        # Average: (1800 + 3600 + 7200) / 3 = 4200
        history = temp_db.get_sender_history("bob@example.com")
        assert history["interaction_count"] == 3
        assert abs(history["response_time_avg"] - 4200.0) < 0.01

    def test_get_sender_history_not_found(self, temp_db):
        """Test get_sender_history returns defaults for unknown sender."""
        history = temp_db.get_sender_history("unknown@example.com")

        assert history["from_addr"] == "unknown@example.com"
        assert history["interaction_count"] == 0
        assert history["response_time_avg"] == 0.0
        assert history["priority_score"] == 0.0

    def test_get_sender_history_includes_priority_score(self, temp_db):
        """Test that priority score is included in history."""
        temp_db.update_sender_interaction("alice@example.com", 1800.0)
        temp_db.update_sender_priority("alice@example.com", 8.5)

        history = temp_db.get_sender_history("alice@example.com")
        assert history["priority_score"] == 8.5


class TestComputeSenderPriority:
    """Test blended priority computation."""

    def test_compute_sender_priority_no_history(self, test_config):
        """Test compute with no history returns Haiku score (0.0 default)."""
        service = EmailService(test_config)

        # No history yet, should return 0.0
        score = service.compute_sender_priority("alice@example.com")
        assert score == 0.0

    def test_compute_sender_priority_with_haiku_score(self, test_config):
        """Test compute with existing Haiku score but no interactions."""
        service = EmailService(test_config)

        # Set a Haiku content score
        service.db.update_sender_priority("alice@example.com", 7.5)

        # With 0 interactions, should return haiku score unchanged
        score = service.compute_sender_priority("alice@example.com")
        assert score == 7.5

    def test_compute_sender_priority_blended(self, test_config):
        """Test blended score with interactions and Haiku score."""
        service = EmailService(test_config)

        # Set initial Haiku score
        service.db.update_sender_priority("alice@example.com", 5.0)

        # Add 10 interactions with fast response time (1 hour avg)
        for _ in range(10):
            service.db.update_sender_interaction("alice@example.com", 3600.0)

        # Compute blended score
        score = service.compute_sender_priority("alice@example.com")

        # behavioral_score = 10.0 (1 hour bracket, fully weighted at 10 interactions)
        # blended = 5.0 * 0.6 + 10.0 * 0.4 = 3.0 + 4.0 = 7.0
        assert abs(score - 7.0) < 0.01

    def test_compute_sender_priority_multiple_calls_consistent(self, test_config):
        """Test that multiple calls return consistent blended score."""
        service = EmailService(test_config)

        # Set initial Haiku score and interactions
        service.db.update_sender_priority("alice@example.com", 5.0)
        for _ in range(5):
            service.db.update_sender_interaction("alice@example.com", 3600.0)

        # Compute blended score twice
        score1 = service.compute_sender_priority("alice@example.com")
        score2 = service.compute_sender_priority("alice@example.com")

        # Both calls should return same score (Haiku score unchanged)
        assert abs(score1 - score2) < 0.01


class TestRecordReply:
    """Test recording of replies for adaptive learning."""

    def test_record_reply_updates_interaction(self, test_config):
        """Test that sending a reply records interaction."""
        service = EmailService(test_config)

        # Create original email from alice
        now = datetime.now()
        original = EmailMetadata(
            id="email_1",
            backend="imap",
            from_addr="alice@example.com",
            to_addrs=["nick@example.com"],
            subject="Q2 Review",
            timestamp=now,
            snippet="Here are your metrics...",
        )
        service.db.insert_or_update_email(original)

        # Create and send draft replying to it
        draft = Draft(
            id="",
            to_addrs=["alice@example.com"],
            subject="Re: Q2 Review",
            body="Thanks for the feedback.",
            responding_to_id="email_1",
            status="approved",
        )
        draft_id = service.db.create_draft(draft)
        service.db.update_draft_status(draft_id, "approved")

        # Manually set sent_at to simulate send
        service.db.update_draft_status(draft_id, "sent")

        # Record the reply
        service._record_reply(draft_id)

        # Check interaction was recorded
        history = service.db.get_sender_history("alice@example.com")
        assert history["interaction_count"] == 1
        assert history["response_time_avg"] > 0

    def test_record_reply_computes_response_time(self, test_config):
        """Test that response time is computed correctly."""
        service = EmailService(test_config)

        # Original email 1 hour ago
        now = datetime.now()
        original_time = now - timedelta(hours=1)

        original = EmailMetadata(
            id="email_1",
            backend="imap",
            from_addr="alice@example.com",
            to_addrs=["nick@example.com"],
            subject="Question",
            timestamp=original_time,
            snippet="What do you think?",
        )
        service.db.insert_or_update_email(original)

        # Draft replying now
        draft = Draft(
            id="",
            to_addrs=["alice@example.com"],
            subject="Re: Question",
            body="I think...",
            responding_to_id="email_1",
            status="approved",
        )
        draft_id = service.db.create_draft(draft)
        service.db.update_draft_status(draft_id, "approved")
        service.db.update_draft_status(draft_id, "sent")

        # Record reply
        service._record_reply(draft_id)

        # Check response time is ~3600 seconds (1 hour)
        history = service.db.get_sender_history("alice@example.com")
        assert abs(history["response_time_avg"] - 3600.0) < 10

    def test_record_reply_no_responding_to_id(self, test_config):
        """Test that reply recording handles drafts without responding_to_id."""
        service = EmailService(test_config)

        # Draft not responding to anything
        draft = Draft(
            id="",
            to_addrs=["bob@example.com"],
            subject="New email",
            body="Hello",
            status="approved",
        )
        draft_id = service.db.create_draft(draft)
        service.db.update_draft_status(draft_id, "sent")

        # Should not error
        service._record_reply(draft_id)

        # Bob should have no interaction history
        history = service.db.get_sender_history("bob@example.com")
        assert history["interaction_count"] == 0

    def test_record_reply_original_email_not_found(self, test_config):
        """Test that reply recording handles missing original email gracefully."""
        service = EmailService(test_config)

        # Draft responding to non-existent email
        draft = Draft(
            id="",
            to_addrs=["alice@example.com"],
            subject="Re: Missing",
            body="Reply",
            responding_to_id="nonexistent_email",
            status="approved",
        )
        draft_id = service.db.create_draft(draft)
        service.db.update_draft_status(draft_id, "sent")

        # Should not error
        service._record_reply(draft_id)

        # No interaction should be recorded
        history = service.db.get_sender_history("alice@example.com")
        assert history["interaction_count"] == 0


class TestSendDraftWithLearning:
    """Test that send_draft integrates reply recording."""

    def test_send_draft_calls_record_reply(self, test_config):
        """Test that send_draft triggers reply recording."""
        service = EmailService(test_config)

        # Create original email
        now = datetime.now()
        original = EmailMetadata(
            id="email_1",
            backend="imap",
            from_addr="alice@example.com",
            to_addrs=["nick@example.com"],
            subject="Request",
            timestamp=now,
            snippet="Can you help?",
        )
        service.db.insert_or_update_email(original)

        # Create draft replying
        draft = Draft(
            id="",
            to_addrs=["alice@example.com"],
            subject="Re: Request",
            body="I can help with that.",
            responding_to_id="email_1",
            status="approved",
        )
        draft_id = service.db.create_draft(draft)
        service.db.update_draft_status(draft_id, "approved")

        # Mock send but let tracking and recording happen
        with patch.object(service.imap_backend, "authenticate", return_value=True):
            with patch.object(service.imap_backend, "send_email", return_value=True):
                with patch("subprocess.run"):
                    result = service.send_draft(draft_id)

        assert result is True

        # Check that interaction was recorded
        history = service.db.get_sender_history("alice@example.com")
        assert history["interaction_count"] == 1


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
