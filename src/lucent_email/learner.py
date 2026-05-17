"""
Adaptive priority learning from user behavior.

Tracks sender interaction history (response time, frequency) and blends
with Claude Haiku's content-based scores for improved priority detection.
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class PriorityLearner:
    """Learns priority scoring from user behavior."""

    @staticmethod
    def score_from_history(interaction_count: int, response_time_avg_seconds: float) -> float:
        """
        Compute behavioral priority score from interaction history.

        Response time brackets:
        - ≤ 3600s (1 hour): 10.0
        - ≤ 14400s (4 hours): 8.0
        - ≤ 86400s (24 hours): 6.0
        - ≤ 604800s (7 days): 4.0
        - > 604800s (> 7 days): 2.0

        Weight by interaction count: new senders start at weight 0,
        fully weighted after 10+ interactions.

        Args:
            interaction_count: Number of times Nick has replied to this sender.
            response_time_avg_seconds: Average response time in seconds.

        Returns:
            Priority score 0-10 based on behavior.
        """
        # No interactions yet — no signal
        if interaction_count == 0:
            return 0.0

        # Score based on response time
        if response_time_avg_seconds <= 3600:  # ≤ 1 hour
            time_score = 10.0
        elif response_time_avg_seconds <= 14400:  # ≤ 4 hours
            time_score = 8.0
        elif response_time_avg_seconds <= 86400:  # ≤ 24 hours
            time_score = 6.0
        elif response_time_avg_seconds <= 604800:  # ≤ 7 days
            time_score = 4.0
        else:  # > 7 days
            time_score = 2.0

        # Weight by interaction count
        # After 10 interactions, fully trust the behavior signal
        interaction_weight = min(interaction_count / 10.0, 1.0)
        return time_score * interaction_weight

    @staticmethod
    def blend(
        haiku_score: float,
        behavioral_score: float,
        interaction_count: int,
    ) -> float:
        """
        Blend Haiku content score with behavioral score.

        Cold start (0 interactions): pure Haiku.
        Ramp up (1-10 interactions): linear blend from Haiku → 60/40 Haiku/Behavioral.
        Mature (10+ interactions): 60% Haiku + 40% Behavioral.

        Args:
            haiku_score: Content-based score from Claude Haiku (0-10).
            behavioral_score: Behavior-based score from interaction history (0-10).
            interaction_count: Number of interactions with this sender.

        Returns:
            Blended priority score (0-10).
        """
        # Cold start: trust Haiku only
        if interaction_count == 0:
            return haiku_score

        # Ramp up: gradually increase weight on behavioral signal
        behavioral_weight = min(interaction_count / 10.0, 1.0) * 0.4
        haiku_weight = 1.0 - behavioral_weight

        blended = (haiku_score * haiku_weight) + (behavioral_score * behavioral_weight)

        # Clamp to 0-10
        return max(0.0, min(10.0, blended))


__all__ = ["PriorityLearner"]
