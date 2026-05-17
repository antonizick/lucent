"""
Lucent Email System — Unified email management across PST + IMAP.

Provides EmailService API for reading, searching, analyzing, and composing emails.
Integrates with Lucent agent system for proactive monitoring and intelligent drafting.
"""

__version__ = "0.1.0"
__author__ = "Lucent"

from .composer import DraftComposer
from .email_service import EmailService
from .models import EmailMetadata, FullEmail, Draft, Attachment

__all__ = [
    "EmailService",
    "DraftComposer",
    "EmailMetadata",
    "FullEmail",
    "Draft",
    "Attachment",
]
