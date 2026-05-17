"""
Email Service API — High-level interface for email operations.

Unifies PST + IMAP backends, provides search, sync, and drafting.
"""

import logging
import time
from datetime import datetime
from typing import List, Optional

from .config import EmailConfig
from .db import EmailDatabase
from .imap_backend import IMAPBackend
from .models import Draft, EmailMetadata, FullEmail, SyncResult
from .pst_backend import PSTBackend

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

    def compute_sender_priority(self, from_addr: str) -> float:
        """
        Compute priority score for sender.

        Phase 2: Uses Claude Haiku for analysis.

        Args:
            from_addr: Sender email address.

        Returns:
            Priority score (0-10 scale).
        """
        # Phase 2: Will integrate Claude Haiku
        # For now, return cached score or default
        return self.db.get_sender_priority(from_addr)

    def detect_high_priority_emails(self, limit: int = 10) -> List[EmailMetadata]:
        """
        Get high-priority emails.

        Phase 2: Will use Claude Haiku for priority detection.

        Args:
            limit: Maximum emails to return.

        Returns:
            List of high-priority EmailMetadata objects.
        """
        # Phase 2: Will call Claude Haiku for each email
        # For now, return empty (placeholder)
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
        Send approved draft.

        Phase 4: Send draft from database.

        Args:
            draft_id: Draft ID.

        Returns:
            True if sent successfully, False otherwise.
        """
        try:
            draft = self.get_draft(draft_id)
            if not draft:
                logger.warning(f"Draft not found: {draft_id}")
                return False

            if draft.status != "approved":
                logger.warning(f"Draft not approved: {draft_id}")
                return False

            to = draft.to_addrs[0] if draft.to_addrs else ""
            if self.send_email(to, draft.subject, draft.body):
                self.db.update_draft_status(draft_id, "sent")
                logger.info(f"Sent draft {draft_id}")
                return True
            else:
                logger.error(f"Failed to send draft {draft_id}")
                return False

        except Exception as e:
            logger.error(f"Error sending draft: {e}")
            return False

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
