"""
Email priority detection using Claude Haiku.

Scores emails 0-10 for priority. Uses keyword pre-filtering (no tokens)
for obvious cases, falls back to Claude Haiku for nuanced analysis.
"""

import json
import logging
from typing import Dict, List, Optional

try:
    import anthropic
except ImportError:
    anthropic = None

from .models import EmailMetadata

logger = logging.getLogger(__name__)


class PriorityDetector:
    """Detects and scores email priority using Claude Haiku."""

    # Keywords that suggest low priority (newsletters, notifications)
    LOW_PRIORITY_KEYWORDS = [
        "newsletter", "digest", "promotion", "marketing",
        "noreply", "notification", "alert", "update",
        "weekly report", "monthly report",
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
        client: anthropic.Anthropic,
        model: str,
    ) -> Dict[str, float]:
        """
        Score a batch of emails using Claude Haiku.

        Batches up to 20 emails per call for efficiency.

        Args:
            emails: List of EmailMetadata to score.
            client: Anthropic client instance.
            model: Model name (e.g., 'claude-haiku-4-5-20251001').

        Returns:
            Dictionary mapping email_id to priority score (0-10).
            Falls back to keyword_prefilter for API failures.
        """
        if not emails:
            return {}

        scores = {}

        # Try prefilter first (no tokens spent)
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

        # Batch remaining emails to Haiku (up to 20 per call)
        batch_size = 20
        for i in range(0, len(to_analyze), batch_size):
            batch = to_analyze[i : i + batch_size]
            batch_scores = cls._call_haiku_batch(batch, client, model)
            scores.update(batch_scores)

        return scores

    @classmethod
    def _call_haiku_batch(
        cls,
        emails: List[EmailMetadata],
        client: anthropic.Anthropic,
        model: str,
    ) -> Dict[str, float]:
        """
        Call Claude Haiku to score a batch of emails.

        Constructs JSON prompt with email details, parses response.

        Args:
            emails: Batch of up to 20 emails.
            client: Anthropic client.
            model: Model name.

        Returns:
            Dictionary mapping email_id to score.
            On error, falls back to keyword_prefilter for each email.
        """
        # Build email list for Haiku
        email_list = []
        for email in emails:
            email_list.append({
                "id": email.id,
                "from": email.from_addr,
                "subject": email.subject,
                "snippet": email.snippet[:300],  # Limit snippet length
                "is_flagged": email.flagged,
            })

        prompt = f"""You are an email priority assistant. Score each email 0-10 for priority.

0-2: Low priority (newsletters, notifications, FYI messages)
3-5: Medium priority (regular work emails, standard updates)
6-8: High priority (time-sensitive, action required, from important contacts)
9-10: Critical (urgent/ASAP, critical decision, escalated issue)

Return ONLY a JSON array with {{id, score}} objects, no markdown or explanation.

Emails to score:
{json.dumps(email_list, indent=2)}

Response format:
[{{"id": "email_id", "score": 7.5}}, ...]"""

        try:
            message = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text.strip()

            # Extract JSON from response (handle markdown code blocks if present)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            results = json.loads(response_text)

            scores = {}
            for result in results:
                email_id = result.get("id")
                score = result.get("score", 5.0)
                # Clamp to 0-10
                score = max(0.0, min(10.0, float(score)))
                scores[email_id] = score
                logger.debug(f"Scored {email_id}: {score}")

            return scores

        except Exception as e:
            logger.error(f"Haiku batch call failed: {e}. Falling back to prefilter.")
            # Fallback: use prefilter for all
            fallback = {}
            for email in emails:
                prefilter_score = cls.keyword_prefilter(email)
                fallback[email.id] = prefilter_score if prefilter_score is not None else 5.0
            return fallback


__all__ = ["PriorityDetector"]
