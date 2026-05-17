"""
Email draft composition using Claude Sonnet.

Generates thoughtful email replies based on conversation context,
with automatic tone detection and fallback to snippet-based composition.
"""

import logging
from typing import Optional

try:
    import anthropic
except ImportError:
    anthropic = None

from .models import Draft, EmailMetadata, FullEmail

logger = logging.getLogger(__name__)


class DraftComposer:
    """Generates email drafts using Claude Sonnet."""

    # Formal tone indicators
    FORMAL_KEYWORDS = [
        "formal", "professional", "proposal", "contract", "agreement",
        "legal", "compliance", "audit", "executive", "board",
    ]

    # Urgent tone indicators
    URGENT_KEYWORDS = [
        "urgent", "asap", "deadline", "critical", "immediate",
        "action required", "deadline", "expires", "don't delay",
    ]

    @classmethod
    def detect_tone(cls, subject: str, body: str = "") -> str:
        """
        Detect email tone from subject and body.

        Returns: "formal", "urgent", or "casual"
        """
        text = (subject + " " + body).lower()

        for keyword in cls.FORMAL_KEYWORDS:
            if keyword in text:
                return "formal"

        for keyword in cls.URGENT_KEYWORDS:
            if keyword in text:
                return "urgent"

        return "casual"

    @classmethod
    def compose_reply(
        cls,
        original_email: Optional[EmailMetadata],
        full_email: Optional[FullEmail],
        client: anthropic.Anthropic,
        model: str,
        instructions: str = "",
    ) -> Draft:
        """
        Generate a reply to an email.

        Args:
            original_email: EmailMetadata for the email being replied to.
            full_email: FullEmail with body (can be None; will use snippet).
            client: Anthropic client instance.
            model: Model name (e.g., 'claude-sonnet-4-6').
            instructions: Optional custom instructions for the reply.

        Returns:
            Draft object (not persisted).
        """
        if not original_email:
            logger.error("No original email provided")
            raise ValueError("original_email is required")

        # Determine subject (add Re: if not already present)
        subject = original_email.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        # Detect tone
        body_text = ""
        if full_email:
            body_text = full_email.body
        else:
            body_text = original_email.snippet

        tone = cls.detect_tone(original_email.subject, body_text)

        # Build context
        context = f"""Original email from {original_email.from_addr}:
Subject: {original_email.subject}

{body_text}"""

        # Compose the reply
        reply_body = cls._call_sonnet_compose(
            context=context,
            instructions=instructions,
            tone=tone,
            client=client,
            model=model,
        )

        # Create Draft object
        draft = Draft(
            id="",  # Will be assigned by database
            to_addrs=[original_email.from_addr],
            subject=subject,
            body=reply_body,
            responding_to_id=original_email.id,
            status="pending_review",
        )

        return draft

    @classmethod
    def compose_new(
        cls,
        to: str,
        subject: str,
        context: str,
        client: anthropic.Anthropic,
        model: str,
        instructions: str = "",
    ) -> Draft:
        """
        Compose a new (non-reply) email.

        Args:
            to: Recipient email address.
            subject: Email subject.
            context: Context or topic for the email.
            client: Anthropic client.
            model: Model name.
            instructions: Optional custom instructions.

        Returns:
            Draft object (not persisted).
        """
        # Compose the body
        body = cls._call_sonnet_compose(
            context=f"Topic: {subject}\nContext: {context}",
            instructions=instructions,
            tone="casual",
            client=client,
            model=model,
        )

        draft = Draft(
            id="",
            to_addrs=[to],
            subject=subject,
            body=body,
            responding_to_id=None,
            status="pending_review",
        )

        return draft

    @classmethod
    def _call_sonnet_compose(
        cls,
        context: str,
        instructions: str,
        tone: str,
        client: anthropic.Anthropic,
        model: str,
    ) -> str:
        """
        Call Claude Sonnet to compose email body.

        Args:
            context: Email context (original message or topic).
            instructions: Custom instructions for composition.
            tone: Detected tone ("formal", "urgent", "casual").
            client: Anthropic client.
            model: Model name.

        Returns:
            Email body text.
        """
        tone_guidance = {
            "formal": "Use professional language, complete sentences, structured format.",
            "urgent": "Be direct and action-oriented. Clearly state what's needed and timeline.",
            "casual": "Use a friendly, conversational tone. Keep it concise.",
        }.get(tone, "Use a professional but friendly tone.")

        system_prompt = f"""You are an email composition assistant for Nick.
You help draft thoughtful, professional email replies.

Tone guidance for this email: {tone_guidance}

Reply format:
- Start with appropriate greeting (e.g., "Hi [Name],")
- Address the main points/questions
- Keep paragraphs short and clear
- End with appropriate closing (e.g., "Best, Nick")

Custom instructions: {instructions if instructions else "None"}

Generate only the email body text, no subject line or greeting/closing labels."""

        try:
            message = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": f"Please draft a reply to this email:\n\n{context}",
                    }
                ],
            )

            body = message.content[0].text.strip()
            logger.debug(f"Composed {len(body)} char reply")
            return body

        except Exception as e:
            logger.error(f"Sonnet composition failed: {e}")
            raise

    @classmethod
    def format_for_review(cls, draft: Draft, show_body_limit: int = 500) -> str:
        """
        Format draft for user review (voice + text display).

        Args:
            draft: Draft to format.
            show_body_limit: Max chars of body to show (... if longer).

        Returns:
            Human-readable draft summary.
        """
        to_addrs = ", ".join(draft.to_addrs) if draft.to_addrs else "(no recipient)"

        body_preview = draft.body
        if len(body_preview) > show_body_limit:
            body_preview = body_preview[:show_body_limit] + "..."

        return f"""[Email] Draft ready for review:
To: {to_addrs}
Subject: {draft.subject}
---
{body_preview}
---
Approve, revise, or discard?"""


__all__ = ["DraftComposer"]
