"""
Background email monitoring loop.

Syncs email every 30 minutes, scores new emails for priority,
and alerts Nick via voice box when high-priority emails arrive.
"""

import json
import logging
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .config import EmailConfig, get_api_key
from .email_service import EmailService
from .models import EmailMetadata
from .priority import PriorityDetector

try:
    import anthropic
except ImportError:
    anthropic = None

logger = logging.getLogger(__name__)


class EmailMonitor:
    """Background email monitoring with priority detection and alerts."""

    def __init__(
        self,
        service: EmailService,
        config: EmailConfig,
        note_path: Optional[Path] = None,
        priority_threshold: float = 7.0,
    ):
        """
        Initialize email monitor.

        Args:
            service: EmailService instance.
            config: EmailConfig instance.
            note_path: Path to daily note file (for appending alerts).
            priority_threshold: Score threshold for high-priority alerts (0-10).
        """
        self.service = service
        self.config = config
        self.note_path = note_path
        self.priority_threshold = priority_threshold

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_sync_at: Optional[datetime] = None
        self._claude_client: Optional[anthropic.Anthropic] = None

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

    def start(self) -> None:
        """Start background monitoring thread."""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"Email monitor started (interval: {self.config.sync_interval_minutes} min)")

    def stop(self) -> None:
        """Stop background monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Email monitor stopped")

    def run_once(self) -> None:
        """Run a single sync+score+alert cycle (for testing/cron)."""
        self._sync_and_alert()

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        interval_seconds = self.config.sync_interval_minutes * 60
        while self._running:
            try:
                self._sync_and_alert()
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            # Sleep in small intervals so we can exit quickly
            for _ in range(int(interval_seconds / 10)):
                if not self._running:
                    break
                time.sleep(10)

    @staticmethod
    def is_suspended() -> bool:
        """Return True if the email monitor is suspended via flag file."""
        flag = Path.home() / "dev/lucent/memory/email/.suspended"
        return flag.exists()

    def _sync_and_alert(self) -> None:
        """Sync email and alert on high-priority emails."""
        if self.is_suspended():
            logger.info("Email monitor suspended — skipping sync cycle")
            return
        try:
            # Sync all backends
            logger.info("Starting email sync...")
            sync_result = self.service.sync_all()
            self._last_sync_at = datetime.now()

            if sync_result.has_errors():
                logger.warning(f"Sync errors: {sync_result.errors}")

            # Get new emails since last sync
            new_email_count = sync_result.total_new()
            logger.info(f"Sync complete: {new_email_count} new emails")

            if new_email_count == 0:
                return

            # Score new emails
            high_priority = self._detect_and_score_new_emails()

            # Alert if high-priority found
            if high_priority:
                self._send_alert(high_priority)
            else:
                logger.info(f"Synced {new_email_count} emails, none high-priority")

        except Exception as e:
            logger.error(f"Sync and alert error: {e}")

    def _detect_and_score_new_emails(self) -> List[EmailMetadata]:
        """
        Detect and score new/unread emails.

        Returns list of high-priority (>= threshold) emails.
        """
        try:
            # Get recent unread emails
            recent = self.service.list_emails(limit=100)
            unread = [e for e in recent if not e.read]

            if not unread:
                return []

            # Score them
            client = self._get_claude_client()
            if not client:
                logger.warning("Skipping priority scoring (no Anthropic client)")
                return []

            scores = PriorityDetector.score_emails(
                unread, client, self.config.claude.model_haiku
            )

            # Update database with scores
            for email_id, score in scores.items():
                # Find corresponding email to extract sender
                email = next((e for e in unread if e.id == email_id), None)
                if email:
                    self.service.db.update_sender_priority(email.from_addr, score)

            # Filter high-priority
            high_priority = [
                e for e in unread
                if scores.get(e.id, 0.0) >= self.priority_threshold
            ]

            return high_priority

        except Exception as e:
            logger.error(f"Error detecting priorities: {e}")
            return []

    def _send_alert(self, emails: List[EmailMetadata]) -> None:
        """
        Send alert via voice box and append to daily note.

        Args:
            emails: List of high-priority emails to alert about.
        """
        if not emails:
            return

        # Format alert message
        email_list = ", ".join(
            f"{e.from_addr}: {e.subject[:40]}"
            for e in emails[:3]  # First 3
        )
        if len(emails) > 3:
            email_list += f", +{len(emails) - 3} more"

        message = f"[Email] {len(emails)} high-priority: {email_list}"

        # Send via voice box
        try:
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
        except Exception as e:
            logger.error(f"Voice box alert failed: {e}")

        # Append to daily note
        self._append_daily_note(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def _append_daily_note(self, content: str) -> None:
        """Append line to daily note file."""
        if not self.note_path:
            return

        try:
            with open(self.note_path, "a") as f:
                f.write(content + "\n")
        except Exception as e:
            logger.error(f"Failed to write daily note: {e}")


__all__ = ["EmailMonitor"]
