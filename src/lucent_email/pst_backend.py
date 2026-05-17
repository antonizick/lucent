"""
PST backend for reading Outlook PST files.

Read-only access to local Outlook archives.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .backend import EmailBackend
from .models import EmailMetadata, FullEmail

logger = logging.getLogger(__name__)


class PSTBackend(EmailBackend):
    """
    PST backend for reading Outlook PST files.

    Read-only access to local Outlook archives.
    Uses python-pst library for cross-platform PST reading.
    """

    def __init__(self, pst_file_path: str):
        """
        Initialize PST backend.

        Args:
            pst_file_path: Absolute path to PST file.
        """
        self.pst_file_path = Path(pst_file_path)
        self.pst = None
        self.email_cache: Dict[str, tuple] = {}  # Cache for full emails
        self._last_sync_time = None

    def authenticate(self) -> bool:
        """
        Validate PST file exists and is readable.

        Returns:
            True if PST file is accessible, False otherwise.
        """
        try:
            if not self.pst_file_path.exists():
                logger.error(f"PST file not found: {self.pst_file_path}")
                return False

            if not os.access(self.pst_file_path, os.R_OK):
                logger.error(f"PST file not readable: {self.pst_file_path}")
                return False

            # Try to open PST file
            try:
                import pst

                self.pst = pst.PSTFile(str(self.pst_file_path))
                logger.info(f"Connected to PST file: {self.pst_file_path}")
                return True
            except ImportError:
                logger.warning(
                    "python-pst library not installed. "
                    "Install with: pip install python-pst"
                )
                return False
            except Exception as e:
                logger.error(f"Failed to open PST file: {e}")
                return False

        except Exception as e:
            logger.error(f"PST authentication failed: {e}")
            return False

    def list_folders(self) -> List[str]:
        """
        List folders in PST file.

        Returns:
            List of folder names (e.g., ["Inbox", "Sent", "Drafts"]).
        """
        if not self.pst:
            logger.warning("PST not connected. Call authenticate() first.")
            return []

        try:
            folders = []
            root = self.pst.root_folder

            def traverse(folder, folders_list):
                """Recursively traverse folder tree."""
                if folder.display_name:
                    folders_list.append(folder.display_name)
                for subfolder in folder.sub_folders:
                    traverse(subfolder, folders_list)

            traverse(root, folders)
            return folders
        except Exception as e:
            logger.error(f"Error listing folders: {e}")
            return []

    def list_emails(self, folder: str, limit: int = 100) -> List[EmailMetadata]:
        """
        List emails in PST folder.

        Args:
            folder: Folder name (e.g., "Inbox").
            limit: Maximum emails to return.

        Returns:
            List of EmailMetadata objects.
        """
        if not self.pst:
            logger.warning("PST not connected. Call authenticate() first.")
            return []

        try:
            emails = []
            root = self.pst.root_folder

            # Find folder
            target_folder = self._find_folder(root, folder)
            if not target_folder:
                logger.warning(f"Folder not found: {folder}")
                return []

            # Extract emails from folder
            count = 0
            for email in target_folder.messages:
                if count >= limit:
                    break

                try:
                    metadata = self._message_to_metadata(email, folder)
                    if metadata:
                        emails.append(metadata)
                        count += 1
                except Exception as e:
                    logger.warning(f"Error processing email: {e}")
                    continue

            logger.info(f"Listed {len(emails)} emails from {folder}")
            return emails

        except Exception as e:
            logger.error(f"Error listing emails: {e}")
            return []

    def get_email(self, email_id: str) -> Optional[FullEmail]:
        """
        Fetch full email from PST.

        Args:
            email_id: Email ID (format: "pst_<folder>_<index>").

        Returns:
            FullEmail object, or None if not found.
        """
        if not self.pst:
            logger.warning("PST not connected.")
            return None

        try:
            # Parse email_id
            parts = email_id.split("_", 2)
            if len(parts) < 3:
                logger.warning(f"Invalid email ID format: {email_id}")
                return None

            folder_name = parts[1]
            index = int(parts[2])

            root = self.pst.root_folder
            target_folder = self._find_folder(root, folder_name)
            if not target_folder:
                logger.warning(f"Folder not found: {folder_name}")
                return None

            # Get email at index
            messages = list(target_folder.messages)
            if index >= len(messages):
                logger.warning(f"Email index out of range: {index}")
                return None

            message = messages[index]
            metadata = self._message_to_metadata(message, folder_name)
            if not metadata:
                return None

            # Add body
            body = getattr(message, "body", "")
            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="replace")

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
                priority_score=metadata.priority_score,
                body=body,
            )

            return full_email

        except Exception as e:
            logger.error(f"Error fetching email: {e}")
            return None

    def search(self, query: str) -> List[str]:
        """
        Search PST emails by query.

        Basic search on subject + snippet.

        Args:
            query: Search query string.

        Returns:
            List of matching email IDs.
        """
        if not self.pst:
            return []

        try:
            query_lower = query.lower()
            matching_ids = []
            root = self.pst.root_folder

            def search_folder(folder):
                """Recursively search folders."""
                try:
                    for idx, message in enumerate(folder.messages):
                        subject = getattr(message, "subject", "").lower()
                        body_preview = getattr(message, "body", "")
                        if isinstance(body_preview, bytes):
                            body_preview = body_preview.decode("utf-8", errors="replace").lower()
                        else:
                            body_preview = str(body_preview).lower()

                        if query_lower in subject or query_lower in body_preview[:500]:
                            email_id = f"pst_{folder.display_name}_{idx}"
                            matching_ids.append(email_id)
                except Exception:
                    pass

                for subfolder in folder.sub_folders:
                    search_folder(subfolder)

            search_folder(root)
            logger.info(f"Search '{query}': found {len(matching_ids)} matches")
            return matching_ids

        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def send_email(self, to: str, subject: str, body: str) -> bool:
        """PST is read-only."""
        raise NotImplementedError("PST backend is read-only. Cannot send emails.")

    def move_email(self, email_id: str, folder: str) -> bool:
        """PST is read-only."""
        raise NotImplementedError("PST backend is read-only. Cannot move emails.")

    def flag_email(self, email_id: str, flag: bool) -> bool:
        """PST is read-only."""
        raise NotImplementedError("PST backend is read-only. Cannot flag emails.")

    def mark_read(self, email_id: str, read: bool) -> bool:
        """PST is read-only."""
        raise NotImplementedError("PST backend is read-only. Cannot mark emails as read.")

    def sync_metadata(self) -> List[EmailMetadata]:
        """
        Sync metadata from all PST folders.

        Returns:
            List of all EmailMetadata objects in PST.
        """
        if not self.pst:
            logger.warning("PST not connected.")
            return []

        try:
            all_emails = []
            root = self.pst.root_folder

            def traverse_and_extract(folder):
                """Recursively extract emails from all folders."""
                try:
                    for email in folder.messages:
                        try:
                            metadata = self._message_to_metadata(email, folder.display_name)
                            if metadata:
                                all_emails.append(metadata)
                        except Exception as e:
                            logger.warning(f"Error processing email: {e}")
                            continue
                except Exception:
                    pass

                for subfolder in folder.sub_folders:
                    traverse_and_extract(subfolder)

            traverse_and_extract(root)
            self._last_sync_time = datetime.now()
            logger.info(f"Synced {len(all_emails)} emails from PST")
            return all_emails

        except Exception as e:
            logger.error(f"Sync error: {e}")
            return []

    def _find_folder(self, folder, name: str):
        """Recursively find folder by name."""
        if folder.display_name == name:
            return folder

        for subfolder in folder.sub_folders:
            result = self._find_folder(subfolder, name)
            if result:
                return result

        return None

    def _message_to_metadata(self, message, folder_name: str) -> Optional[EmailMetadata]:
        """Convert PST message to EmailMetadata."""
        try:
            sender = getattr(message, "sender_name", "") or getattr(message, "from", "")
            subject = getattr(message, "subject", "") or ""
            body = getattr(message, "body", "") or ""

            if isinstance(body, bytes):
                body = body.decode("utf-8", errors="replace")

            snippet = str(body)[:200]
            timestamp = getattr(message, "creation_time", None) or datetime.now()
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)

            message_id = getattr(message, "message_id", "") or ""

            email_id = f"pst_{folder_name}_{id(message)}"

            return EmailMetadata(
                id=email_id,
                backend="pst",
                from_addr=str(sender),
                to_addrs=[],
                subject=str(subject),
                timestamp=timestamp,
                snippet=snippet,
                read=False,
                flagged=False,
                folder=folder_name,
                message_id=message_id,
            )
        except Exception as e:
            logger.warning(f"Error converting message to metadata: {e}")
            return None

    @property
    def backend_name(self) -> str:
        """Backend name."""
        return "pst"

    @property
    def is_writable(self) -> bool:
        """PST is read-only."""
        return False


__all__ = ["PSTBackend"]
