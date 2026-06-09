"""
IMAP backend for email accounts with IMAP/SMTP access.

Read/write access to remote email accounts.
"""

import imaplib
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.parser import BytesParser
from typing import Dict, List, Optional

from .backend import EmailBackend
from .config import IMAPConfig, get_imap_password
from .models import EmailMetadata, FullEmail

logger = logging.getLogger(__name__)


class IMAPBackend(EmailBackend):
    """
    IMAP backend for remote email accounts.

    Supports full read/write operations via IMAP + SMTP.
    Bidirectional sync with server.
    """

    def __init__(self, config: IMAPConfig, sync_folders: List[str] = None):
        """
        Initialize IMAP backend.

        Args:
            config: IMAPConfig with email, host, port settings.
            sync_folders: List of folder names to sync. If None, syncs all folders.
        """
        self.config = config
        self.sync_folders = sync_folders
        self.imap = None
        self.smtp = None
        self.last_sync_uids: Dict[str, set] = {}

    def authenticate(self) -> bool:
        """
        Log in to IMAP and SMTP servers.

        Returns:
            True if both connections successful, False otherwise.
        """
        try:
            # Get password from keyring
            password = get_imap_password(self.config)

            # Connect to IMAP
            try:
                self.imap = imaplib.IMAP4_SSL(
                    self.config.imap_host,
                    self.config.imap_port
                )
                self.imap.login(self.config.email_address, password)
                logger.info(f"Connected to IMAP: {self.config.imap_host}")
            except imaplib.IMAP4.error as e:
                logger.error(f"IMAP login failed: {e}")
                return False

            # Connect to SMTP
            try:
                # Port 465 requires SMTP_SSL, 587 uses SMTP with STARTTLS
                if self.config.smtp_port == 465:
                    self.smtp = smtplib.SMTP_SSL(
                        self.config.smtp_host,
                        self.config.smtp_port
                    )
                    self.smtp.login(self.config.email_address, password)
                else:
                    self.smtp = smtplib.SMTP(
                        self.config.smtp_host,
                        self.config.smtp_port
                    )
                    if self.config.use_tls:
                        self.smtp.starttls()
                    self.smtp.login(self.config.email_address, password)
                logger.info(f"Connected to SMTP: {self.config.smtp_host}")
            except smtplib.SMTPException as e:
                logger.error(f"SMTP login failed: {e}")
                return False

            return True

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def list_folders(self) -> List[str]:
        """
        List folders accessible via IMAP.

        Returns:
            List of folder names.
        """
        if not self.imap:
            logger.warning("IMAP not connected.")
            return []

        try:
            _, mailboxes = self.imap.list()
            folders = []
            for mailbox in mailboxes:
                decoded = mailbox.decode()
                # IMAP LIST format: (flags) "delimiter" mailbox-name
                # Example: (\\HasChildren) "." INBOX
                # Example: (\\HasNoChildren) "." "INBOX.Deleted Messages"

                # Find the second quoted string (delimiter) and extract mailbox name after it
                quote_count = 0
                in_quote = False
                for i, char in enumerate(decoded):
                    if char == '"':
                        quote_count += 1
                        in_quote = not in_quote
                    elif quote_count == 2 and not in_quote and char != ' ':
                        # After the delimiter quote, find the mailbox name
                        mailbox_name = decoded[i:]
                        # Remove surrounding quotes if present
                        mailbox_name = mailbox_name.strip().strip('"')
                        if mailbox_name:
                            folders.append(mailbox_name)
                        break
            return folders
        except Exception as e:
            logger.error(f"Error listing folders: {e}")
            return []

    def list_emails(self, folder: str, limit: int = 100) -> List[EmailMetadata]:
        """
        List recent emails in IMAP folder.

        Args:
            folder: Folder name (e.g., "INBOX").
            limit: Maximum emails to return.

        Returns:
            List of EmailMetadata objects.
        """
        if not self.imap:
            logger.warning("IMAP not connected.")
            return []

        try:
            self.imap.select(folder)
            _, [response] = self.imap.search(None, "ALL")
            uids = response.split()

            # Get most recent emails
            if limit and len(uids) > limit:
                uids = uids[-limit:]

            emails = []
            for uid in uids:
                try:
                    _, msg_data = self.imap.fetch(uid, "(RFC822)")
                    if msg_data[0]:
                        metadata = self._parse_email_metadata(msg_data[0][1], uid.decode(), folder)
                        if metadata:
                            emails.append(metadata)
                except Exception as e:
                    logger.warning(f"Error parsing email: {e}")
                    continue

            logger.info(f"Listed {len(emails)} emails from {folder}")
            return emails

        except Exception as e:
            logger.error(f"Error listing emails: {e}")
            return []

    def get_email(self, email_id: str) -> Optional[FullEmail]:
        """
        Fetch full email from IMAP.

        Args:
            email_id: Email UID (format: "imap_<uid>").

        Returns:
            FullEmail object, or None if not found.
        """
        if not self.imap:
            logger.warning("IMAP not connected.")
            return None

        try:
            # Parse email_id
            parts = email_id.split("_", 1)
            if len(parts) < 2:
                return None

            uid = parts[1]
            _, msg_data = self.imap.fetch(uid.encode(), "(RFC822)")

            if not msg_data[0]:
                return None

            # Parse full email
            msg_bytes = msg_data[0][1]
            parser = BytesParser()
            msg = parser.parsebytes(msg_bytes)

            # Get metadata
            metadata = self._parse_email_metadata(msg_bytes, uid, "INBOX")
            if not metadata:
                return None

            # Extract body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        except:
                            body = part.get_payload()
                        break
            else:
                try:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
                except:
                    body = msg.get_payload()

            full_email = FullEmail(
                id=metadata.id,
                backend=metadata.backend,
                from_addr=metadata.from_addr,
                to_addrs=metadata.to_addrs,
                subject=metadata.subject,
                timestamp=metadata.timestamp,
                snippet=metadata.snippet,
                read=metadata.read,
                flagged=metadata.flagged,
                folder=metadata.folder,
                message_id=metadata.message_id,
                in_reply_to=metadata.in_reply_to,
                body=body,
            )

            return full_email

        except Exception as e:
            logger.error(f"Error fetching email: {e}")
            return None

    def search(self, query: str) -> List[str]:
        """
        Search emails via IMAP SEARCH.

        Args:
            query: Search query (basic IMAP SEARCH format).

        Returns:
            List of matching email UIDs (as "imap_<uid>").
        """
        if not self.imap:
            return []

        try:
            # Simple search on subject
            _, [response] = self.imap.search(None, f"SUBJECT {query}")
            uids = response.split()
            email_ids = [f"imap_{uid.decode()}" for uid in uids]
            logger.info(f"Search '{query}': found {len(email_ids)} matches")
            return email_ids
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def send_email(self, to: str, subject: str, body: str) -> bool:
        """
        Send email via SMTP.

        Args:
            to: Recipient email address(es), comma-separated.
            subject: Email subject.
            body: Email body.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self.smtp:
            logger.warning("SMTP not connected.")
            return False

        try:
            # Parse comma-separated recipients
            to_addrs = [addr.strip() for addr in to.split(",")]

            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = self.config.email_address
            msg["To"] = to  # Keep original format in header

            # Send to all recipients
            self.smtp.sendmail(self.config.email_address, to_addrs, msg.as_string())
            logger.info(f"Sent email to {to}")
            return True

        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

    def move_email(self, email_id: str, folder: str) -> bool:
        """
        Move email to folder.

        Args:
            email_id: Email UID.
            folder: Target folder name.

        Returns:
            True if successful, False otherwise.
        """
        if not self.imap:
            return False

        try:
            uid = email_id.split("_", 1)[1]
            self.imap.copy(uid.encode(), folder)
            self.imap.store(uid.encode(), "+FLAGS", "(\\Deleted,)")
            self.imap.expunge()
            logger.info(f"Moved email {uid} to {folder}")
            return True
        except Exception as e:
            logger.error(f"Move error: {e}")
            return False

    def flag_email(self, email_id: str, flag: bool) -> bool:
        """
        Flag/unflag email.

        Args:
            email_id: Email UID.
            flag: True to flag, False to unflag.

        Returns:
            True if successful, False otherwise.
        """
        if not self.imap:
            return False

        try:
            uid = email_id.split("_", 1)[1]
            if flag:
                self.imap.store(uid.encode(), "+FLAGS", "(\\Flagged,)")
            else:
                self.imap.store(uid.encode(), "-FLAGS", "(\\Flagged,)")
            logger.info(f"Flagged email {uid}: {flag}")
            return True
        except Exception as e:
            logger.error(f"Flag error: {e}")
            return False

    def mark_read(self, email_id: str, read: bool) -> bool:
        """
        Mark email as read/unread.

        Args:
            email_id: Email UID.
            read: True to mark read, False to mark unread.

        Returns:
            True if successful, False otherwise.
        """
        if not self.imap:
            return False

        try:
            uid = email_id.split("_", 1)[1]
            if read:
                self.imap.store(uid.encode(), "+FLAGS", "(\\Seen,)")
            else:
                self.imap.store(uid.encode(), "-FLAGS", "(\\Seen,)")
            logger.info(f"Mark read email {uid}: {read}")
            return True
        except Exception as e:
            logger.error(f"Mark read error: {e}")
            return False

    def sync_metadata(self) -> List[EmailMetadata]:
        """
        Sync new/modified emails from IMAP.

        Returns:
            List of new EmailMetadata objects.
        """
        if not self.imap:
            logger.warning("IMAP not connected.")
            return []

        try:
            all_emails = []
            folders = self.list_folders()

            # Filter folders if sync_folders is configured
            if self.sync_folders:
                folders = [f for f in folders if f in self.sync_folders]
                logger.info(f"Syncing IMAP folders: {folders}")
            else:
                logger.info(f"Syncing all IMAP folders: {folders}")

            for folder in folders:
                try:
                    self.imap.select(folder)
                    _, [response] = self.imap.search(None, "ALL")
                    uids = response.split()

                    for uid in uids:
                        try:
                            _, msg_data = self.imap.fetch(uid, "(RFC822)")
                            if msg_data[0]:
                                metadata = self._parse_email_metadata(msg_data[0][1], uid.decode(), folder)
                                if metadata:
                                    all_emails.append(metadata)
                        except Exception as e:
                            logger.warning(f"Error processing email: {e}")
                            continue
                except Exception as e:
                    logger.warning(f"Error syncing folder {folder}: {e}")
                    continue

            logger.info(f"Synced {len(all_emails)} emails from IMAP")
            return all_emails

        except Exception as e:
            logger.error(f"Sync error: {e}")
            return []

    def _parse_email_metadata(self, msg_bytes: bytes, uid: str, folder: str) -> Optional[EmailMetadata]:
        """Parse email message into metadata."""
        try:
            parser = BytesParser()
            msg = parser.parsebytes(msg_bytes)

            from_addr = str(msg.get("From", ""))
            to_addrs = [str(msg.get("To", ""))] if msg.get("To") else []
            subject = str(msg.get("Subject", ""))
            message_id = str(msg.get("Message-ID", ""))
            in_reply_to = str(msg.get("In-Reply-To")) if msg.get("In-Reply-To") else None

            # Parse timestamp
            date_str = msg.get("Date", "")
            try:
                from email.utils import parsedate_to_datetime
                timestamp = parsedate_to_datetime(date_str)
            except:
                timestamp = datetime.now(timezone.utc)

            # Get snippet (first 200 chars of body)
            snippet = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            snippet = part.get_payload(decode=True).decode("utf-8", errors="replace")[:200]
                        except:
                            snippet = part.get_payload()[:200]
                        break
            else:
                try:
                    snippet = msg.get_payload(decode=True).decode("utf-8", errors="replace")[:200]
                except:
                    snippet = msg.get_payload()[:200]

            email_id = f"imap_{folder}_{uid}"

            return EmailMetadata(
                id=email_id,
                backend="imap",
                from_addr=from_addr,
                to_addrs=to_addrs,
                subject=subject,
                timestamp=timestamp,
                snippet=snippet,
                read=False,
                flagged=False,
                folder=folder,
                message_id=message_id,
                in_reply_to=in_reply_to,
            )

        except Exception as e:
            logger.warning(f"Error parsing email metadata: {e}")
            return None

    def close(self) -> None:
        """Close IMAP and SMTP connections."""
        if self.imap:
            try:
                self.imap.close()
                self.imap.logout()
            except:
                pass
        if self.smtp:
            try:
                self.smtp.quit()
            except:
                pass

    @property
    def backend_name(self) -> str:
        """Backend name."""
        return "imap"

    @property
    def is_writable(self) -> bool:
        """IMAP is fully writable."""
        return True


__all__ = ["IMAPBackend"]
