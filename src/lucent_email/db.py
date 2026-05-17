"""
SQLite database layer for email metadata cache.

Manages schema, CRUD operations, and full-text search.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from .models import Draft, EmailMetadata, SyncResult

logger = logging.getLogger(__name__)


class EmailDatabase:
    """
    SQLite database for email metadata cache and drafts.

    Provides caching, full-text search, and draft management.
    """

    def __init__(self, db_path: str):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = None
        self._connect()

    def _connect(self) -> None:
        """Open database connection."""
        self.connection = sqlite3.connect(str(self.db_path))
        self.connection.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        self.connection.execute("PRAGMA journal_mode=WAL")

    def initialize_schema(self) -> None:
        """Create database schema with all tables and indexes."""
        cursor = self.connection.cursor()

        # Emails metadata cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id TEXT PRIMARY KEY,
                backend TEXT NOT NULL,
                from_addr TEXT,
                to_addrs TEXT,
                subject TEXT,
                timestamp DATETIME,
                received_date DATETIME,
                read BOOLEAN DEFAULT 0,
                flagged BOOLEAN DEFAULT 0,
                folder TEXT,
                labels TEXT,
                snippet TEXT,
                message_id TEXT,
                in_reply_to TEXT,
                sender_priority_score REAL DEFAULT 0.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_synced DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Sender priority/interaction history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sender_priority (
                from_addr TEXT PRIMARY KEY,
                interaction_count INTEGER DEFAULT 0,
                response_time_avg REAL DEFAULT 0.0,
                priority_score REAL DEFAULT 0.0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Draft management
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS drafts (
                id TEXT PRIMARY KEY,
                to_addrs TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                original_email_id TEXT,
                status TEXT DEFAULT 'pending_review',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                approved_at DATETIME,
                sent_at DATETIME
            )
        """)

        # Full-text search index
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
                subject, snippet, from_addr,
                content='emails', content_rowid='id'
            )
        """)

        # Indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_folder ON emails(folder)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_timestamp ON emails(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_from ON emails(from_addr)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status)")

        self.connection.commit()
        logger.info("Database schema initialized")

    def migrate_remove_message_id_unique(self) -> None:
        """Remove UNIQUE constraint from message_id column.

        Needed because IMAP UIDs are per-folder, and the same message can appear
        in multiple folders. UNIQUE constraint was causing INSERT OR REPLACE failures.
        """
        cursor = self.connection.cursor()
        try:
            # Check if emails table exists with UNIQUE constraint on message_id
            cursor.execute("PRAGMA table_info(emails)")
            columns = cursor.fetchall()

            # Check if table has the old schema (we can check for message_id existence)
            has_message_id = any(col[1] == "message_id" for col in columns)
            if not has_message_id:
                return

            # Try to get constraint info (SQLite doesn't support PRAGMA for constraints easily)
            # Instead, we'll try to insert a duplicate message_id and catch the error
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='emails'")
            if cursor.fetchone()[0] == 0:
                return

            # Check if we have old schema by trying to access the constraint
            cursor.execute("""
                SELECT sql FROM sqlite_master WHERE type='table' AND name='emails'
            """)
            table_sql = cursor.fetchone()

            if table_sql and "UNIQUE" in str(table_sql[0]):
                logger.info("Migrating emails table to remove UNIQUE constraint on message_id...")

                # Rename old table
                cursor.execute("ALTER TABLE emails RENAME TO emails_old")

                # Create new table without UNIQUE constraint
                cursor.execute("""
                    CREATE TABLE emails (
                        id TEXT PRIMARY KEY,
                        backend TEXT NOT NULL,
                        from_addr TEXT,
                        to_addrs TEXT,
                        subject TEXT,
                        timestamp DATETIME,
                        received_date DATETIME,
                        read BOOLEAN DEFAULT 0,
                        flagged BOOLEAN DEFAULT 0,
                        folder TEXT,
                        labels TEXT,
                        snippet TEXT,
                        message_id TEXT,
                        in_reply_to TEXT,
                        sender_priority_score REAL DEFAULT 0.0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        last_synced DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Copy data from old table
                cursor.execute("""
                    INSERT INTO emails
                    SELECT id, backend, from_addr, to_addrs, subject, timestamp,
                           received_date, read, flagged, folder, labels, snippet,
                           message_id, in_reply_to, sender_priority_score, created_at, last_synced
                    FROM emails_old
                """)

                # Recreate indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_folder ON emails(folder)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_timestamp ON emails(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_from ON emails(from_addr)")

                # Drop old table
                cursor.execute("DROP TABLE emails_old")

                self.connection.commit()
                logger.info("Migration complete: UNIQUE constraint removed from message_id")
        except Exception as e:
            logger.warning(f"Migration error (may not be needed): {e}")

    def insert_or_update_email(self, email: EmailMetadata) -> None:
        """Insert or update email metadata."""
        cursor = self.connection.cursor()

        # Prepare data
        to_addrs_json = json.dumps(email.to_addrs) if email.to_addrs else "[]"
        # Use NULL for missing message_id (empty string breaks UNIQUE constraint)
        message_id = email.message_id if email.message_id else None

        cursor.execute("""
            INSERT OR REPLACE INTO emails (
                id, backend, from_addr, to_addrs, subject, timestamp,
                received_date, read, flagged, folder, labels, snippet,
                message_id, in_reply_to, sender_priority_score, last_synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            email.id, email.backend, email.from_addr, to_addrs_json,
            email.subject, email.timestamp.isoformat(),
            email.timestamp.isoformat(), int(email.read), int(email.flagged),
            email.folder, "[]", email.snippet,
            message_id, email.in_reply_to,
            email.priority_score, datetime.now().isoformat()
        ))

        self.connection.commit()

    def search(self, query: str, limit: int = 100) -> List[EmailMetadata]:
        """Full-text search via LIKE (FTS5 optimization available)."""
        cursor = self.connection.cursor()

        # Simple LIKE search on subject and snippet (FTS5 can optimize this later)
        search_term = f"%{query}%"
        cursor.execute("""
            SELECT * FROM emails
            WHERE subject LIKE ? OR snippet LIKE ? OR from_addr LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (search_term, search_term, search_term, limit))

        return [self._row_to_email_metadata(row) for row in cursor.fetchall()]

    def get_email_by_id(self, email_id: str) -> Optional[EmailMetadata]:
        """Get cached email metadata by ID."""
        cursor = self.connection.cursor()

        cursor.execute("SELECT * FROM emails WHERE id = ?", (email_id,))
        row = cursor.fetchone()

        return self._row_to_email_metadata(row) if row else None

    def sync_emails(self, emails: List[EmailMetadata]) -> None:
        """Batch insert/update emails from sync."""
        cursor = self.connection.cursor()

        for email in emails:
            self.insert_or_update_email(email)

        logger.info(f"Synced {len(emails)} emails")

    def list_emails(self, folder: str = None, limit: int = 50) -> List[EmailMetadata]:
        """List emails in folder."""
        cursor = self.connection.cursor()

        if folder:
            cursor.execute("""
                SELECT * FROM emails
                WHERE folder = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (folder, limit))
        else:
            cursor.execute("""
                SELECT * FROM emails
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))

        return [self._row_to_email_metadata(row) for row in cursor.fetchall()]

    def get_conversation(self, message_id: str) -> List[EmailMetadata]:
        """Get email thread by message ID."""
        cursor = self.connection.cursor()

        # Get root message
        cursor.execute("SELECT * FROM emails WHERE message_id = ?", (message_id,))
        root = cursor.fetchone()
        if not root:
            return []

        # Get all related messages (in reply to root or its replies)
        cursor.execute("""
            SELECT * FROM emails
            WHERE message_id = ? OR in_reply_to = ?
            ORDER BY timestamp ASC
        """, (message_id, message_id))

        return [self._row_to_email_metadata(row) for row in cursor.fetchall()]

    def update_email_priority(self, email_id: str, score: float) -> None:
        """Update email's priority score."""
        cursor = self.connection.cursor()

        cursor.execute("""
            UPDATE emails SET sender_priority_score = ?
            WHERE id = ?
        """, (score, email_id))

        self.connection.commit()

    def update_sender_priority(self, from_addr: str, score: float) -> None:
        """Update sender priority score."""
        cursor = self.connection.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO sender_priority (from_addr, priority_score, last_updated)
            VALUES (?, ?, ?)
        """, (from_addr, score, datetime.now().isoformat()))

        self.connection.commit()

    def get_sender_priority(self, from_addr: str) -> float:
        """Get priority score for sender."""
        cursor = self.connection.cursor()

        cursor.execute("""
            SELECT priority_score FROM sender_priority WHERE from_addr = ?
        """, (from_addr,))

        row = cursor.fetchone()
        return row[0] if row else 0.0

    def update_sender_interaction(self, from_addr: str, response_time_seconds: float) -> None:
        """Update sender interaction history with response time.

        Increments interaction count and updates running average response time.
        Formula: new_avg = (old_avg * old_count + response_time) / (old_count + 1)
        """
        cursor = self.connection.cursor()

        # Get current history (including priority_score to preserve it)
        cursor.execute("""
            SELECT interaction_count, response_time_avg, priority_score FROM sender_priority WHERE from_addr = ?
        """, (from_addr,))

        row = cursor.fetchone()
        if row:
            old_count = row[0]
            old_avg = row[1]
            priority_score = row[2]
        else:
            old_count = 0
            old_avg = 0.0
            priority_score = 0.0

        # Calculate new running average
        new_count = old_count + 1
        new_avg = (old_avg * old_count + response_time_seconds) / new_count

        # Update sender_priority with new interaction data (preserve priority_score)
        cursor.execute("""
            INSERT OR REPLACE INTO sender_priority (
                from_addr, interaction_count, response_time_avg, priority_score, last_updated
            ) VALUES (?, ?, ?, ?, ?)
        """, (from_addr, new_count, new_avg, priority_score, datetime.now().isoformat()))

        self.connection.commit()
        logger.info(f"Updated sender {from_addr}: {new_count} interactions, avg response time {new_avg:.1f}s")

    def get_sender_history(self, from_addr: str) -> dict:
        """Get full sender interaction history.

        Returns:
            Dict with from_addr, interaction_count, response_time_avg, priority_score.
            Returns zero-default dict if sender not found.
        """
        cursor = self.connection.cursor()

        cursor.execute("""
            SELECT from_addr, interaction_count, response_time_avg, priority_score
            FROM sender_priority WHERE from_addr = ?
        """, (from_addr,))

        row = cursor.fetchone()
        if row:
            return {
                "from_addr": row[0],
                "interaction_count": row[1],
                "response_time_avg": row[2],
                "priority_score": row[3],
            }
        else:
            return {
                "from_addr": from_addr,
                "interaction_count": 0,
                "response_time_avg": 0.0,
                "priority_score": 0.0,
            }

    def create_draft(self, draft: Draft) -> str:
        """Create new draft, return draft ID."""
        cursor = self.connection.cursor()

        draft_id = str(uuid4())
        to_addrs_json = json.dumps(draft.to_addrs)

        cursor.execute("""
            INSERT INTO drafts (id, to_addrs, subject, body, original_email_id, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            draft_id, to_addrs_json, draft.subject, draft.body,
            draft.responding_to_id, draft.status
        ))

        self.connection.commit()
        logger.info(f"Created draft {draft_id}")
        return draft_id

    def get_draft(self, draft_id: str) -> Optional[Draft]:
        """Retrieve draft by ID."""
        cursor = self.connection.cursor()

        cursor.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_draft(row)

    def update_draft_status(self, draft_id: str, status: str) -> None:
        """Update draft status."""
        cursor = self.connection.cursor()

        if status == "approved":
            # Only update approved_at when transitioning to approved
            cursor.execute("""
                UPDATE drafts SET status = ?, approved_at = ?
                WHERE id = ?
            """, (status, datetime.now().isoformat(), draft_id))
        elif status == "sent":
            # Only update sent_at when transitioning to sent
            cursor.execute("""
                UPDATE drafts SET status = ?, sent_at = ?
                WHERE id = ?
            """, (status, datetime.now().isoformat(), draft_id))
        else:
            # For other statuses, only update status
            cursor.execute("""
                UPDATE drafts SET status = ?
                WHERE id = ?
            """, (status, draft_id))

        self.connection.commit()
        logger.info(f"Updated draft {draft_id} to {status}")

    def list_drafts(self, status: str = None) -> List[Draft]:
        """List drafts by status."""
        cursor = self.connection.cursor()

        if status:
            cursor.execute("SELECT * FROM drafts WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            cursor.execute("SELECT * FROM drafts ORDER BY created_at DESC")

        return [self._row_to_draft(row) for row in cursor.fetchall()]

    def email_count(self) -> int:
        """Get total email count."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM emails")
        return cursor.fetchone()[0]

    def email_count_by_backend(self) -> dict:
        """Get email count by backend."""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT backend, COUNT(*) FROM emails GROUP BY backend
        """)
        return {row[0]: row[1] for row in cursor.fetchall()}

    def cleanup_deleted_emails(self, current_email_ids: List[str], folder: str) -> int:
        """Remove emails from database that are no longer on the server.

        Args:
            current_email_ids: List of email IDs currently on the server for this folder.
            folder: The folder to clean up (e.g., "INBOX", "INBOX.Sent").

        Returns:
            Number of emails deleted.
        """
        cursor = self.connection.cursor()

        # Get all email IDs for this folder in the database
        cursor.execute("""
            SELECT id FROM emails WHERE folder = ?
        """, (folder,))
        db_emails = set(row[0] for row in cursor.fetchall())

        # Find emails in database but not on server
        current_set = set(current_email_ids)
        emails_to_delete = db_emails - current_set

        if emails_to_delete:
            # Delete the orphaned emails
            placeholders = ','.join('?' * len(emails_to_delete))
            cursor.execute(f"""
                DELETE FROM emails WHERE id IN ({placeholders})
            """, tuple(emails_to_delete))

            self.connection.commit()
            logger.info(f"Cleaned up {len(emails_to_delete)} deleted emails from {folder}")
            return len(emails_to_delete)

        return 0

    def vacuum(self) -> None:
        """Optimize database."""
        cursor = self.connection.cursor()
        cursor.execute("VACUUM")
        self.connection.commit()
        logger.info("Database vacuumed")

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def _row_to_email_metadata(self, row: sqlite3.Row) -> EmailMetadata:
        """Convert database row to EmailMetadata."""
        to_addrs = json.loads(row["to_addrs"]) if row["to_addrs"] else []

        return EmailMetadata(
            id=row["id"],
            backend=row["backend"],
            from_addr=row["from_addr"],
            to_addrs=to_addrs,
            subject=row["subject"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            snippet=row["snippet"],
            read=bool(row["read"]),
            flagged=bool(row["flagged"]),
            folder=row["folder"],
            message_id=row["message_id"],
            in_reply_to=row["in_reply_to"],
            priority_score=row["sender_priority_score"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_synced=datetime.fromisoformat(row["last_synced"]),
        )

    def _row_to_draft(self, row: sqlite3.Row) -> Draft:
        """Convert database row to Draft."""
        to_addrs = json.loads(row["to_addrs"])

        return Draft(
            id=row["id"],
            to_addrs=to_addrs,
            subject=row["subject"],
            body=row["body"],
            responding_to_id=row["original_email_id"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
            sent_at=datetime.fromisoformat(row["sent_at"]) if row["sent_at"] else None,
        )

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        self.close()


__all__ = ["EmailDatabase"]
