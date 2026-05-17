"""
Abstract backend layer for email access.

Defines EmailBackend interface that PST and IMAP backends implement.
Allows service layer to treat all backends uniformly.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import EmailMetadata, FullEmail


class EmailBackend(ABC):
    """
    Abstract base class for email backends.

    All backends (PST, IMAP, etc.) must inherit from this and implement
    all abstract methods.
    """

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with backend.

        For PST: Validate file exists and is readable.
        For IMAP: Log in with credentials.

        Returns:
            True if authentication successful, False otherwise.

        Raises:
            Exception: If authentication fails critically.
        """
        pass

    @abstractmethod
    def list_folders(self) -> List[str]:
        """
        List available folders/labels.

        Returns:
            List of folder names (e.g., ["Inbox", "Sent", "Drafts"]).
        """
        pass

    @abstractmethod
    def list_emails(self, folder: str, limit: int = 100) -> List[EmailMetadata]:
        """
        List emails in folder.

        Returns metadata only (headers, IDs, timestamps).
        Bodies are fetched separately via get_email().

        Args:
            folder: Folder name (e.g., "Inbox").
            limit: Maximum emails to return.

        Returns:
            List of EmailMetadata objects.
        """
        pass

    @abstractmethod
    def get_email(self, email_id: str) -> Optional[FullEmail]:
        """
        Fetch full email with body and attachments.

        Args:
            email_id: Email ID (e.g., "pst_123" or "imap_456").

        Returns:
            FullEmail object, or None if not found.
        """
        pass

    @abstractmethod
    def search(self, query: str) -> List[str]:
        """
        Search emails by query.

        Returns list of matching email IDs.

        Args:
            query: Search query (e.g., "from:alice subject:meeting").

        Returns:
            List of matching email IDs.
        """
        pass

    @abstractmethod
    def send_email(self, to: str, subject: str, body: str) -> bool:
        """
        Send email.

        Args:
            to: Recipient email address(es).
            subject: Email subject.
            body: Email body (plain text or HTML).

        Returns:
            True if sent successfully, False otherwise.
        """
        pass

    @abstractmethod
    def move_email(self, email_id: str, folder: str) -> bool:
        """
        Move email to folder.

        Args:
            email_id: Email ID.
            folder: Target folder name.

        Returns:
            True if moved successfully, False otherwise.
        """
        pass

    @abstractmethod
    def flag_email(self, email_id: str, flag: bool) -> bool:
        """
        Flag or unflag email.

        Args:
            email_id: Email ID.
            flag: True to flag, False to unflag.

        Returns:
            True if operation successful, False otherwise.
        """
        pass

    @abstractmethod
    def mark_read(self, email_id: str, read: bool) -> bool:
        """
        Mark email as read or unread.

        Args:
            email_id: Email ID.
            read: True to mark read, False to mark unread.

        Returns:
            True if operation successful, False otherwise.
        """
        pass

    @abstractmethod
    def sync_metadata(self) -> List[EmailMetadata]:
        """
        Return newly added/modified emails since last sync.

        Implementation-specific logic for detecting changes.

        Returns:
            List of new/modified EmailMetadata objects.
        """
        pass

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Return backend name (e.g., 'pst', 'imap')."""
        pass

    @property
    @abstractmethod
    def is_writable(self) -> bool:
        """Return True if backend supports write operations."""
        pass


__all__ = ["EmailBackend"]
