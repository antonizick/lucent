"""
Email send validation and safety checks.

Ensures drafts are safe to send before SMTP delivery.
"""

import logging
import re
from typing import List

from .models import Draft

logger = logging.getLogger(__name__)


class SendValidator:
    """Validates drafts before sending."""

    # Simple email format regex: something@something.something
    EMAIL_REGEX = r"^[^@]+@[^@]+\.[^@]+$"

    @classmethod
    def validate(cls, draft: Draft) -> List[str]:
        """
        Validate draft before sending.

        Returns list of error messages (empty = safe to send).

        Args:
            draft: Draft to validate.

        Returns:
            List of validation errors (empty list = valid).
        """
        errors = []

        # Check status is approved
        if draft.status != "approved":
            errors.append(f"Draft status is '{draft.status}', not 'approved'")

        # Check recipients exist
        if not draft.to_addrs or len(draft.to_addrs) == 0:
            errors.append("No recipients specified")

        # Check each recipient is valid email format
        for to_addr in draft.to_addrs:
            if not re.match(cls.EMAIL_REGEX, to_addr.strip()):
                errors.append(f"Invalid email format: {to_addr}")

        # Check subject is not empty
        if not draft.subject or not draft.subject.strip():
            errors.append("Subject is empty")

        # Check body is not empty
        if not draft.body or not draft.body.strip():
            errors.append("Body is empty")

        return errors

    @classmethod
    def is_valid(cls, draft: Draft) -> bool:
        """
        Check if draft is valid to send.

        Args:
            draft: Draft to check.

        Returns:
            True if valid, False otherwise.
        """
        return len(cls.validate(draft)) == 0


__all__ = ["SendValidator"]
