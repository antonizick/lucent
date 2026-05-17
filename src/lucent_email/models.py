"""
Data models for Lucent Email System.

Defines Email, Draft, and related dataclasses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Attachment:
    """Email attachment metadata."""
    filename: str
    size: int
    content_type: str
    content: Optional[bytes] = None  # Lazy-loaded


@dataclass
class EmailMetadata:
    """
    Lightweight email metadata from cache.

    Used for listing, searching, and quick access.
    Full body/attachments fetched separately via get_email().
    """
    id: str  # "pst_123" or "imap_456"
    backend: str  # "pst" or "imap"
    from_addr: str
    to_addrs: List[str]
    subject: str
    timestamp: datetime
    snippet: str  # First 200 chars
    read: bool = False
    flagged: bool = False
    folder: str = "Inbox"
    message_id: str = ""
    in_reply_to: Optional[str] = None
    priority_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    last_synced: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        """String representation for display."""
        return f"{self.from_addr}: {self.subject}"

    def short_id(self) -> str:
        """Short version of ID for display."""
        return self.id.split("_", 1)[1] if "_" in self.id else self.id


@dataclass
class FullEmail(EmailMetadata):
    """
    Complete email with body and attachments.

    Extends EmailMetadata with content.
    """
    body: str
    html_body: Optional[str] = None
    attachments: List[Attachment] = field(default_factory=list)

    def text_preview(self, max_chars: int = 300) -> str:
        """Get text preview of email body."""
        text = self.body[:max_chars]
        if len(self.body) > max_chars:
            text += "..."
        return text


@dataclass
class Draft:
    """Email draft awaiting approval or sent."""
    id: str  # UUID
    to_addrs: List[str]
    subject: str
    body: str
    responding_to_id: Optional[str] = None  # Which email this responds to
    status: str = "pending_review"  # pending_review, approved, sent, discarded
    created_at: datetime = field(default_factory=datetime.now)
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

    def __str__(self) -> str:
        """String representation."""
        return f"[{self.status}] {self.subject}"

    def is_approved(self) -> bool:
        """Check if draft is approved."""
        return self.status == "approved"

    def is_sent(self) -> bool:
        """Check if draft was sent."""
        return self.status == "sent"


@dataclass
class SyncResult:
    """Result of a sync operation."""
    pst_new: int = 0  # New emails from PST
    imap_new: int = 0  # New emails from IMAP
    pst_updated: int = 0  # Updated emails from PST
    imap_updated: int = 0  # Updated emails from IMAP
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def __str__(self) -> str:
        """String representation."""
        return (
            f"Sync: PST +{self.pst_new} upd:{self.pst_updated}, "
            f"IMAP +{self.imap_new} upd:{self.imap_updated}, "
            f"{self.duration_seconds:.1f}s"
        )

    def total_new(self) -> int:
        """Total new emails across all backends."""
        return self.pst_new + self.imap_new

    def has_errors(self) -> bool:
        """Check if sync encountered errors."""
        return len(self.errors) > 0


@dataclass
class SearchQuery:
    """Structured email search query."""
    text: Optional[str] = None
    from_addr: Optional[str] = None
    to_addr: Optional[str] = None
    subject: Optional[str] = None
    folder: Optional[str] = None
    read: Optional[bool] = None
    flagged: Optional[bool] = None
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    backend: Optional[str] = None  # "pst", "imap", or None for both

    def to_fts_query(self) -> str:
        """Convert to SQLite FTS5 query string."""
        parts = []
        if self.text:
            parts.append(self.text)
        if self.from_addr:
            parts.append(f"from_addr:{self.from_addr}")
        if self.subject:
            parts.append(f"subject:{self.subject}")
        return " ".join(parts)


__all__ = [
    "Attachment",
    "EmailMetadata",
    "FullEmail",
    "Draft",
    "SyncResult",
    "SearchQuery",
]
