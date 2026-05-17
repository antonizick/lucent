"""
Ollama client for local LLM inference.

Provides unified interface to Ollama API for email system tasks.
"""

import logging
import requests
import json
from typing import Optional
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class OllamaConfig:
    """Ollama configuration."""
    base_url: str = "http://localhost:11434"
    model_fast: str = "qwen3:0.6b"  # Fast model for priority detection
    model_quality: str = "qwen3-30b-a3b:latest"  # Quality model for composition
    temperature: float = 0.7


class OllamaClient:
    """Ollama API client for local LLM inference."""

    def __init__(self, config: Optional[OllamaConfig] = None):
        """
        Initialize Ollama client.

        Args:
            config: OllamaConfig instance. If None, uses defaults.
        """
        self.config = config or OllamaConfig()
        self.base_url = self.config.base_url.rstrip("/")
        self._guidelines_cache = None

    def _load_priority_guidelines(self) -> str:
        """Load email priority guidelines from ~/.lucent/priority_guidelines.md."""
        if self._guidelines_cache is not None:
            return self._guidelines_cache

        guidelines_path = Path.home() / ".lucent" / "priority_guidelines.md"

        if guidelines_path.exists():
            try:
                content = guidelines_path.read_text()
                self._guidelines_cache = content
                return content
            except Exception as e:
                logger.warning(f"Failed to load priority guidelines: {e}")
                return ""
        else:
            logger.info(f"Priority guidelines not found at {guidelines_path}")
            return ""

    def _call_ollama(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> Optional[str]:
        """
        Call Ollama API.

        Args:
            model: Model name (e.g., "qwen3:0.6b")
            prompt: Input prompt
            temperature: Sampling temperature
            max_tokens: Max tokens to generate

        Returns:
            Generated text, or None on error.
        """
        try:
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": model,
                "prompt": prompt,
                "temperature": temperature,
                "num_predict": max_tokens,
                "stream": False,
            }

            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()

            data = response.json()
            return data.get("response", "").strip()

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Ollama connection error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return None

    def score_email_priority(self, sender: str, subject: str, snippet: str) -> Optional[float]:
        """
        Score email priority using fast model.

        Args:
            sender: Email sender address
            subject: Email subject
            snippet: Email preview/snippet

        Returns:
            Priority score 0-10, or None on error.
        """
        guidelines = self._load_priority_guidelines()
        guidelines_context = f"\n\nPriority Guidelines:\n{guidelines}" if guidelines else ""

        prompt = f"""Analyze this email and score its priority from 0-10.
Consider: urgency, importance, action required.{guidelines_context}

Sender: {sender}
Subject: {subject}
Preview: {snippet}

Respond with ONLY a number 0-10, nothing else."""

        result = self._call_ollama(
            model=self.config.model_fast,
            prompt=prompt,
            temperature=0.3,  # Low temperature for consistent scoring
            max_tokens=10,
        )

        if result:
            try:
                # Try direct float conversion first
                score = float(result.strip())
                return max(0.0, min(10.0, score))
            except ValueError:
                # Fall back to extracting number from text
                import re
                # Look for "Score: X" or just a number followed by .
                match = re.search(r'(?:Score:|^|\s)(\d+(?:\.\d+)?)\s*(?:\.)?$', result.strip(), re.MULTILINE)
                if match:
                    try:
                        score = float(match.group(1))
                        return max(0.0, min(10.0, score))
                    except ValueError:
                        pass

                # Last resort: look for any number 0-10
                match = re.search(r'\b([0-9]+(?:\.[0-9]+)?)\b', result)
                if match:
                    try:
                        score = float(match.group(1))
                        if 0 <= score <= 10:
                            return score
                    except ValueError:
                        pass

                logger.warning(f"Failed to parse score from: {result[:100]}")
                return None

        return None

    def compose_reply(
        self,
        sender: str,
        original_subject: str,
        original_snippet: str,
        instructions: str,
        tone: str = "casual",
    ) -> Optional[str]:
        """
        Compose email reply using quality model.

        Args:
            sender: Original email sender
            original_subject: Original email subject
            original_snippet: Original email preview
            instructions: User instructions for reply
            tone: Email tone ('formal', 'casual', 'urgent')

        Returns:
            Composed email text, or None on error.
        """
        tone_guidance = {
            "formal": "professional, respectful, structured",
            "urgent": "concise, action-oriented, time-sensitive",
            "casual": "friendly, conversational, natural",
        }

        tone_desc = tone_guidance.get(tone, "friendly")

        prompt = f"""Compose a professional email reply.

Original email from {sender}:
Subject: {original_subject}
Preview: {original_snippet}

Tone: {tone_desc}
Instructions: {instructions}

Write ONLY the email body (no subject, no salutation, no closing signature)."""

        result = self._call_ollama(
            model=self.config.model_quality,
            prompt=prompt,
            temperature=0.7,
            max_tokens=500,
        )

        return result if result else None

    def compose_new_email(
        self,
        recipient: str,
        subject: str,
        context: str,
        tone: str = "casual",
    ) -> Optional[str]:
        """
        Compose new email using quality model.

        Args:
            recipient: Email recipient
            subject: Email subject
            context: Context/background for email
            tone: Email tone

        Returns:
            Composed email text, or None on error.
        """
        tone_guidance = {
            "formal": "professional, respectful, structured",
            "urgent": "concise, action-oriented, time-sensitive",
            "casual": "friendly, conversational, natural",
        }

        tone_desc = tone_guidance.get(tone, "friendly")

        prompt = f"""Compose a professional email.

To: {recipient}
Subject: {subject}
Context: {context}

Tone: {tone_desc}

Write ONLY the email body (no subject, no salutation, no closing signature)."""

        result = self._call_ollama(
            model=self.config.model_quality,
            prompt=prompt,
            temperature=0.7,
            max_tokens=500,
        )

        return result if result else None

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            url = f"{self.base_url}/api/tags"
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False


__all__ = ["OllamaClient", "OllamaConfig"]
