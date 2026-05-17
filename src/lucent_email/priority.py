"""
Email priority detection using Ollama local LLM.

Scores emails 0-10 for priority. Uses keyword pre-filtering (no tokens)
for obvious cases, falls back to Ollama for nuanced analysis.
"""

import json
import logging
from typing import Dict, List, Optional

from .models import EmailMetadata
from .ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class PriorityDetector:
    """Detects and scores email priority using Claude Haiku."""

    # Keywords that suggest low priority (newsletters, notifications, financial spam)
    LOW_PRIORITY_KEYWORDS = [
        "newsletter", "digest", "promotion", "marketing",
        "noreply", "notification", "alert", "update",
        "weekly report", "monthly report",
        # Financial spam / unsolicited offers (from updated guidelines)
        "refinancing", "property", "vehicle", "insurance quote",
        "pending offer", "utility bill relief", "right away",
        "new option", "refi", "vehicle quote", "relief offer",
        "home relief", "property notice", "property inquiry",
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
        Quick priority score based on keywords, no Claude call.

        Returns 0 (low), 5 (medium), 9 (high), or None (needs Haiku analysis).
        """
        text = (email.subject + " " + email.snippet).lower()
        from_addr = email.from_addr.lower()

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

        # Unknown; needs Haiku analysis
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
