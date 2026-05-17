"""
Email Service API — High-level interface for email operations.

Unifies PST + IMAP backends, provides search, sync, and drafting.
"""

import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

try:
    import anthropic
except ImportError:
    anthropic = None

from .composer import DraftComposer
from .config import EmailConfig, get_api_key
from .db import EmailDatabase
from .imap_backend import IMAPBackend
from .models import Draft, EmailMetadata, FullEmail, SyncResult
from .priority import PriorityDetector
from .pst_backend import PSTBackend
from .sender import SendValidator

logger = logging.getLogger(__name__)


class EmailService:
    """
    High-level email service API.

    Provides unified interface over PST + IMAP backends.
    Manages caching, searching, syncing, and drafting.
    """

    def __init__(self, config: EmailConfig):
        """
        Initialize email service.

        Args:
            config: EmailConfig with all settings.
        """
        self.config = config
        self.pst_backend = PSTBackend(config.pst_file_path)
        self.imap_backend = IMAPBackend(config.imap)
        self.db = EmailDatabase(config.database.path)
        self.db.initialize_schema()
        self.backends = [self.pst_backend, self.imap_backend]
        self._claude_client: Optional[anthropic.Anthropic] = None

    # Query operations

    def search(
        self, query: str, backend: str = None, limit: int = 100
    ) -> List[EmailMetadata]:
        """
        Search emails across backends.

        Uses SQLite FTS5 for fast full-text search.

        Args:
            query: Search query string.
            backend: Filter by backend ("pst", "imap", or None for both).
            limit: Maximum results to return.

        Returns:
            List of matching EmailMetadata objects.
        """
        try:
            results = self.db.search(query, limit=limit)

            # Filter by backend if specified
            if backend:
                results = [r for r in results if r.backend == backend]

            logger.info(f"Search '{query}': {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def get_email(self, email_id: str) -> Optional[FullEmail]:
        """
        Fetch full email with body and attachments.

        Fetches from appropriate backend (determined by email_id prefix).

        Args:
            email_id: Email ID (format: "backend_<data>").

        Returns:
            FullEmail object, or None if not found.
        """
        try:
            # Determine backend from ID prefix
            if email_id.startswith("pst_"):
                if not self.pst_backend.authenticate():
                    logger.warning("PST not authenticated")
                    return None
                return self.pst_backend.get_email(email_id)
            elif email_id.startswith("imap_"):
                if not self.imap_backend.authenticate():
                    logger.warning("IMAP not authenticated")
                    return None
                return self.imap_backend.get_email(email_id)
            else:
                logger.warning(f"Unknown email ID format: {email_id}")
                return None

        except Exception as e:
            logger.error(f"Error fetching email: {e}")
            return None

    def list_emails(self, folder: str = "Inbox", limit: int = 50) -> List[EmailMetadata]:
        """
        List recent emails in folder.

        Returns cached metadata from SQLite.

        Args:
            folder: Folder name.
            limit: Maximum emails to return.

        Returns:
            List of EmailMetadata objects.
        """
        try:
            return self.db.list_emails(folder=folder, limit=limit)
        except Exception as e:
            logger.error(f"Error listing emails: {e}")
            return []

    def get_conversation(self, message_id: str) -> List[EmailMetadata]:
        """
        Get entire email conversation thread.

        Uses message_id + in_reply_to to reconstruct thread.

        Args:
            message_id: Message ID to get conversation for.

        Returns:
            List of emails in conversation thread.
        """
        try:
            return self.db.get_conversation(message_id)
        except Exception as e:
            logger.error(f"Error getting conversation: {e}")
            return []

    # Sync operations

    def sync_all(self) -> SyncResult:
        """
        Sync all backends, update cache.

        Fetches new emails from all backends and populates SQLite cache.

        Returns:
            SyncResult with counts and timing information.
        """
        try:
            start_time = time.time()
            result = SyncResult()

            # Sync PST backend
            try:
                if self.pst_backend.authenticate():
                    pst_emails = self.pst_backend.sync_metadata()
                    self.db.sync_emails(pst_emails)
                    result.pst_new = len(pst_emails)
                    logger.info(f"PST sync: {len(pst_emails)} emails")
                else:
                    result.errors.append("PST authentication failed")
            except Exception as e:
                result.errors.append(f"PST sync error: {e}")
                logger.error(f"PST sync error: {e}")

            # Sync IMAP backend
            try:
                if self.imap_backend.authenticate():
                    imap_emails = self.imap_backend.sync_metadata()
                    self.db.sync_emails(imap_emails)
                    result.imap_new = len(imap_emails)
                    logger.info(f"IMAP sync: {len(imap_emails)} emails")
                else:
                    result.errors.append("IMAP authentication failed")
            except Exception as e:
                result.errors.append(f"IMAP sync error: {e}")
                logger.error(f"IMAP sync error: {e}")

            result.duration_seconds = time.time() - start_time
            logger.info(f"Sync complete: {result}")
            return result

        except Exception as e:
            logger.error(f"Sync error: {e}")
            return SyncResult(errors=[str(e)])

    def get_new_emails(self, since: datetime) -> List[EmailMetadata]:
        """
        Get emails added since timestamp.

        Args:
            since: Timestamp to filter by.

        Returns:
            List of emails added after timestamp.
        """
        try:
            # Query cache for emails after timestamp
            all_emails = []
            folders = ["Inbox", "Sent", "Drafts"]

            for folder in folders:
                try:
                    emails = self.db.list_emails(folder=folder, limit=1000)
                    for email in emails:
                        if email.timestamp > since:
                            all_emails.append(email)
                except:
                    pass

            return sorted(all_emails, key=lambda e: e.timestamp, reverse=True)

        except Exception as e:
            logger.error(f"Error getting new emails: {e}")
            return []

    # Priority analysis (Phase 2+)

    def _get_claude_client(self) -> Optional[anthropic.Anthropic]:
        """Get Anthropic client (lazy init)."""
        if self._claude_client is None and anthropic:
            try:
                api_key = get_api_key(self.config)
                self._claude_client = anthropic.Anthropic(api_key=api_key)
            except (ValueError, ImportError) as e:
                logger.warning(f"Could not init Anthropic client: {e}")
                return None
        return self._claude_client

    def compute_sender_priority(self, from_addr: str) -> float:
        """
        Compute priority score for sender.

        Phase 2: Uses Claude Haiku for analysis.

        Args:
            from_addr: Sender email address.

        Returns:
            Priority score (0-10 scale).
        """
        return self.db.get_sender_priority(from_addr)

    def score_new_emails(self, emails: List[EmailMetadata]) -> dict:
        """
        Score emails and persist priority scores.

        Uses Claude Haiku via PriorityDetector.

        Args:
            emails: List of emails to score.

        Returns:
            Dictionary mapping email_id to score.
        """
        try:
            client = self._get_claude_client()
            if not client:
                logger.warning("Skipping email scoring (no Anthropic client)")
                return {}

            scores = PriorityDetector.score_emails(
                emails, client, self.config.claude.model_haiku
            )

            # Persist scores to database
            for email_id, score in scores.items():
                email = next((e for e in emails if e.id == email_id), None)
                if email:
                    self.db.update_sender_priority(email.from_addr, score)

            logger.info(f"Scored {len(scores)} emails")
            return scores

        except Exception as e:
            logger.error(f"Error scoring emails: {e}")
            return {}

    def detect_high_priority_emails(self, limit: int = 10) -> List[EmailMetadata]:
        """
        Get high-priority emails.

        Uses Claude Haiku for priority detection. Returns emails scoring >= 7.0.

        Args:
            limit: Maximum emails to return.

        Returns:
            List of high-priority EmailMetadata objects.
        """
        try:
            # Get recent unread emails
            recent = self.list_emails(limit=100)
            unread = [e for e in recent if not e.read]

            if not unread:
                return []

            # Score them
            scores = self.score_new_emails(unread)

            # Filter high-priority (>= 7.0)
            high_priority = [
                e for e in unread
                if scores.get(e.id, 0.0) >= 7.0
            ][:limit]

            logger.info(f"Detected {len(high_priority)} high-priority emails")
            return high_priority

        except Exception as e:
            logger.error(f"Error detecting high-priority emails: {e}")
            return []

    # Draft operations (Phase 3+)

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        responding_to_id: str = None,
    ) -> str:
        """
        Create draft, return draft ID.

        Phase 3: Will integrate Claude Sonnet for composition.

        Args:
            to: Recipient email address.
            subject: Email subject.
            body: Email body.
            responding_to_id: Which email this responds to (optional).

        Returns:
            Draft ID (UUID).
        """
        try:
            draft = Draft(
                id="",  # Will be assigned by database
                to_addrs=[to],
                subject=subject,
                body=body,
                responding_to_id=responding_to_id,
                status="pending_review",
            )

            draft_id = self.db.create_draft(draft)
            logger.info(f"Created draft {draft_id}")
            return draft_id

        except Exception as e:
            logger.error(f"Error creating draft: {e}")
            return ""

    def get_draft(self, draft_id: str) -> Optional[Draft]:
        """
        Retrieve draft by ID.

        Args:
            draft_id: Draft ID (UUID).

        Returns:
            Draft object, or None if not found.
        """
        try:
            return self.db.get_draft(draft_id)
        except Exception as e:
            logger.error(f"Error getting draft: {e}")
            return None

    def approve_draft(self, draft_id: str) -> bool:
        """
        Mark draft as approved.

        Args:
            draft_id: Draft ID.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self.db.update_draft_status(draft_id, "approved")
            logger.info(f"Approved draft {draft_id}")
            return True
        except Exception as e:
            logger.error(f"Error approving draft: {e}")
            return False

    def compose_reply(self, email_id: str, instructions: str = "") -> str:
        """
        Compose a reply to an email using Claude Sonnet.

        Fetches the original email, generates a reply draft, and persists it.

        Args:
            email_id: ID of the email to reply to.
            instructions: Optional custom instructions for the reply.

        Returns:
            Draft ID of the composed reply, or empty string on error.
        """
        try:
            # Try to get full email with body
            full_email = self.get_email(email_id)

            # Fall back to cached metadata if full email fetch fails
            if not full_email:
                original_email = self.db.get_email_by_id(email_id)
                if not original_email:
                    logger.error(f"Email not found: {email_id}")
                    return ""
            else:
                original_email = full_email

            # Get Sonnet client
            client = self._get_claude_client()
            if not client:
                logger.warning("Skipping composition (no Anthropic client)")
                return ""

            # Compose reply
            draft = DraftComposer.compose_reply(
                original_email=original_email,
                full_email=full_email,
                client=client,
                model=self.config.claude.model_sonnet,
                instructions=instructions,
            )

            # Persist draft
            draft_id = self.db.create_draft(draft)
            logger.info(f"Composed reply to {email_id} as draft {draft_id}")
            return draft_id

        except Exception as e:
            logger.error(f"Error composing reply: {e}")
            return ""

    def compose_new(
        self,
        to: str,
        subject: str,
        context: str = "",
        instructions: str = "",
    ) -> str:
        """
        Compose a new email using Claude Sonnet.

        Args:
            to: Recipient email address.
            subject: Email subject.
            context: Context or topic for the email.
            instructions: Optional custom instructions.

        Returns:
            Draft ID, or empty string on error.
        """
        try:
            # Get Sonnet client
            client = self._get_claude_client()
            if not client:
                logger.warning("Skipping composition (no Anthropic client)")
                return ""

            # Compose email
            draft = DraftComposer.compose_new(
                to=to,
                subject=subject,
                context=context,
                client=client,
                model=self.config.claude.model_sonnet,
                instructions=instructions,
            )

            # Persist draft
            draft_id = self.db.create_draft(draft)
            logger.info(f"Composed new email to {to} as draft {draft_id}")
            return draft_id

        except Exception as e:
            logger.error(f"Error composing email: {e}")
            return ""

    def discard_draft(self, draft_id: str) -> bool:
        """
        Mark draft as discarded.

        Args:
            draft_id: Draft ID.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self.db.update_draft_status(draft_id, "discarded")
            logger.info(f"Discarded draft {draft_id}")
            return True
        except Exception as e:
            logger.error(f"Error discarding draft: {e}")
            return False

    # Sending (Phase 4+)

    def send_email(self, to: str, subject: str, body: str) -> bool:
        """
        Send email via IMAP/SMTP.

        Phase 4: Direct email sending (not draft-based).

        Args:
            to: Recipient email address.
            subject: Email subject.
            body: Email body.

        Returns:
            True if sent successfully, False otherwise.
        """
        try:
            if not self.imap_backend.authenticate():
                logger.warning("IMAP not authenticated")
                return False

            return self.imap_backend.send_email(to, subject, body)

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False

    def send_draft(self, draft_id: str) -> bool:
        """
        Send approved draft with safety checks.

        Validates draft, sends via IMAP/SMTP, tracks in cache, confirms via voice.

        Args:
            draft_id: Draft ID.

        Returns:
            True if sent successfully, False otherwise.
        """
        try:
            # Load draft
            draft = self.get_draft(draft_id)
            if not draft:
                logger.warning(f"Draft not found: {draft_id}")
                return False

            # Validate before sending
            errors = SendValidator.validate(draft)
            if errors:
                logger.warning(f"Draft validation failed: {', '.join(errors)}")
                return False

            # Send to all recipients (comma-separated)
            to = ", ".join(draft.to_addrs)
            if not self.send_email(to, draft.subject, draft.body):
                logger.error(f"Failed to send draft {draft_id}")
                return False

            # Success: update status with sent_at timestamp
            self.db.update_draft_status(draft_id, "sent")

            # Track sent email in cache
            self._track_sent_email(draft)

            # Confirm via voice box
            self._confirm_send(draft)

            logger.info(f"Sent draft {draft_id}")
            return True

        except Exception as e:
            logger.error(f"Error sending draft: {e}")
            return False

    def _track_sent_email(self, draft: Draft) -> None:
        """
        Add sent email to cache in "Sent" folder.

        Args:
            draft: Draft that was just sent.
        """
        try:
            # Create metadata from draft
            sent_email = EmailMetadata(
                id=f"imap_sent_{draft.id}",
                backend="imap",
                from_addr=self.config.imap.email_address,
                to_addrs=draft.to_addrs,
                subject=draft.subject,
                timestamp=datetime.now(),
                snippet=draft.body[:200],
                read=True,
                folder="Sent",
                message_id=None,
                in_reply_to=None,
            )

            self.db.insert_or_update_email(sent_email)
            logger.debug(f"Tracked sent email in cache: {draft.id}")

        except Exception as e:
            logger.error(f"Error tracking sent email: {e}")

    def _confirm_send(self, draft: Draft) -> None:
        """
        Confirm send via voice box and daily note.

        Args:
            draft: Draft that was just sent.
        """
        try:
            # Format confirmation message
            to_str = ", ".join(draft.to_addrs[:2])  # First 2 recipients
            if len(draft.to_addrs) > 2:
                to_str += f", +{len(draft.to_addrs) - 2} more"

            message = f"[Email] Sent '{draft.subject}' to {to_str}"

            # Send via voice box
            subprocess.run(
                [
                    "curl",
                    "-X",
                    "POST",
                    "http://localhost:8001/speak",
                    "-H",
                    "Content-Type: application/json",
                    "-d",
                    json.dumps({"text": message}),
                ],
                timeout=5,
            )

            # Log to daily note
            note_path = Path.home() / ".lucent" / "memory"
            from datetime import date
            today = date.today().isoformat()
            note_file = note_path / f"{today}.md"

            if note_file.exists():
                with open(note_file, "a") as f:
                    f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")

        except Exception as e:
            logger.error(f"Error confirming send: {e}")

    # Information

    def get_stats(self) -> dict:
        """
        Get service statistics.

        Returns:
            Dictionary with counts and info.
        """
        try:
            return {
                "total_emails": self.db.email_count(),
                "by_backend": self.db.email_count_by_backend(),
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}

    # Cleanup

    def close(self) -> None:
        """Close all connections."""
        try:
            self.imap_backend.close()
            self.db.close()
            logger.info("Email service closed")
        except Exception as e:
            logger.error(f"Error closing service: {e}")

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        self.close()


__all__ = ["EmailService"]
