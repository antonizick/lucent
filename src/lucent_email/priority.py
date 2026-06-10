"""
Email priority detection using Ollama local LLM.

Scores emails 0-10 for priority. Uses keyword pre-filtering (no tokens)
for obvious cases, falls back to Ollama for nuanced analysis.

Trusted senders are configured in memory/email/trusted_senders.json.
Each entry has an "email" (substring match), optional "priority" (0-10 float),
and optional "name"/"note" fields. Set "priority" to null to let Ollama score
the sender normally while still bypassing keyword spam filters.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .models import EmailMetadata
from .ollama_client import OllamaClient

logger = logging.getLogger(__name__)

_TRUSTED_SENDERS_PATH = Path("~/dev/lucent/memory/email/trusted_senders.json").expanduser()


class PriorityDetector:
    """Detects and scores email priority using Claude Haiku."""

    _trusted_senders_cache: Optional[List[dict]] = None

    @classmethod
    def _load_trusted_senders(cls) -> List[dict]:
        """Load trusted senders from flat file, with class-level cache."""
        if cls._trusted_senders_cache is not None:
            return cls._trusted_senders_cache
        try:
            cls._trusted_senders_cache = json.loads(_TRUSTED_SENDERS_PATH.read_text())
            logger.debug(f"Loaded {len(cls._trusted_senders_cache)} trusted senders")
        except FileNotFoundError:
            logger.info("trusted_senders.json not found — no trusted senders configured")
            cls._trusted_senders_cache = []
        except Exception as e:
            logger.warning(f"Failed to load trusted_senders.json: {e}")
            cls._trusted_senders_cache = []
        return cls._trusted_senders_cache

    # Keywords that suggest low priority (newsletters, financial spam).
    # Do NOT add generic transactional words like "notification", "update", "alert"
    # — those appear in legitimate account emails and block Ollama from seeing them.
    LOW_PRIORITY_KEYWORDS = [
        "newsletter", "digest", "promotion", "marketing",
        "weekly report", "monthly report",
        # Financial spam / unsolicited offers (from feedback + guidelines)
        "refinancing", "vehicle quote", "insurance quote", "insurance quotes",
        "pending offer", "pending offers", "utility bill",
        "new option", "new options", "refi", "relief offer",
        "home relief", "property notice", "property inquiry",
        # EverQuote / vehicle quote senders (from feedback)
        "everquote", "providing quotes", "deals@providingquotes",
    ]

    # Sender-domain patterns that are always low priority regardless of content.
    LOW_PRIORITY_SENDER_DOMAINS = [
        "mvpsolarpower.com",
        "quickenloanservice.com",
        "knowledgebanner.com",
        "allin1loans.com",
        "providingquotes.com",
        "ratechop.org",
        "silvermagnus.com",
        "award-headquarters.com",
    ]

    # Keywords that suggest high priority (urgent action needed)
    HIGH_PRIORITY_KEYWORDS = [
        "urgent", "asap", "deadline", "critical", "immediate",
        "action required", "due today", "due tomorrow", "expires",
        "please review", "waiting on you",
    ]

    @classmethod
    def keyword_prefilter(cls, email: EmailMetadata) -> Optional[float]:
        """
        Quick priority score based on keywords, no Ollama call.

        Returns a float (0-10) to short-circuit scoring, or None to send to Ollama.

        Trusted senders (trusted_senders.json) are checked first:
        - "priority": <number>  → return that score directly, skip Ollama
        - "priority": null      → skip keyword filters, let Ollama score normally
        """
        from_addr = (email.from_addr or "").lower()

        # Check trusted senders from flat file first.
        for entry in cls._load_trusted_senders():
            if entry.get("email", "").lower() in from_addr:
                fixed_priority = entry.get("priority")
                if fixed_priority is not None:
                    logger.debug(f"Trusted sender {entry['email']} → fixed score {fixed_priority}")
                    return float(fixed_priority)
                else:
                    logger.debug(f"Trusted sender {entry['email']} → bypass filters, send to Ollama")
                    return None

        # Blocklisted sender domains are always low priority.
        for domain in cls.LOW_PRIORITY_SENDER_DOMAINS:
            if domain in from_addr:
                logger.debug(f"Blocked sender domain: {domain} in {email.id}")
                return 0.0

        # Include FROM address in keyword matching (catches noreply@, sender domains, etc)
        text = (email.subject + " " + email.snippet + " " + from_addr).lower()

        # Check low-priority patterns
        for keyword in cls.LOW_PRIORITY_KEYWORDS:
            if keyword in text:
                logger.debug(f"Low priority detected: {keyword} in {email.id}")
                return 0.0

        # Check high-priority patterns
        for keyword in cls.HIGH_PRIORITY_KEYWORDS:
            if keyword in text:
                logger.debug(f"High priority detected: {keyword} in {email.id}")
                return 9.0

        # Flagged emails are important
        if email.flagged:
            return 8.0

        # Unknown; needs Ollama analysis
        return None

    @classmethod
    def score_emails(
        cls,
        emails: List[EmailMetadata],
        ollama_client: Optional[OllamaClient] = None,
    ) -> Dict[str, float]:
        """
        Score a batch of emails using Ollama.

        Uses keyword pre-filter first for obvious cases, then Ollama for nuanced analysis.

        Args:
            emails: List of EmailMetadata to score.
            ollama_client: OllamaClient instance. If None, creates new one.

        Returns:
            Dictionary mapping email_id to priority score (0-10).
            Falls back to keyword_prefilter for API failures.
        """
        if not emails:
            return {}

        if ollama_client is None:
            ollama_client = OllamaClient()

        scores = {}

        # Try prefilter first (no LLM call needed)
        to_analyze = []
        for email in emails:
            prefilter_score = cls.keyword_prefilter(email)
            if prefilter_score is not None:
                scores[email.id] = prefilter_score
            else:
                to_analyze.append(email)

        # If no emails need analysis, return prefilter results
        if not to_analyze:
            return scores

        # Score remaining emails with Ollama (one at a time for simplicity)
        for email in to_analyze:
            score = ollama_client.score_email_priority(
                sender=email.from_addr or "",
                subject=email.subject or "",
                snippet=email.snippet or "",
            )
            if score is not None:
                scores[email.id] = score
            else:
                # Fallback to neutral score on Ollama error
                logger.warning(f"Failed to score {email.id}, using neutral")
                scores[email.id] = 5.0

        return scores


__all__ = ["PriorityDetector"]
