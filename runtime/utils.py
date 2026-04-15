"""Shared utilities for the RetailOS runtime."""

import json
import logging
import time

logger = logging.getLogger(__name__)


def extract_json_from_llm(text: str) -> dict:
    """Extract and parse JSON from an LLM response.

    Handles common patterns: raw JSON, ```json fenced blocks,
    and generic ``` fenced blocks.

    Raises:
        json.JSONDecodeError: If no valid JSON can be extracted.
    """
    cleaned = text
    try:
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) >= 3:
                cleaned = parts[1]
    except (IndexError, ValueError):
        pass
    return json.loads(cleaned.strip())


class CircuitBreaker:
    """Simple circuit breaker for external API calls.

    After `failure_threshold` consecutive failures, the breaker opens
    and stays open for `cooldown_seconds`. During that window, `allow()`
    returns False so callers can skip the API and go straight to fallback.
    """

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 60):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._consecutive_failures = 0
        self._opened_at: float = 0

    @property
    def is_open(self) -> bool:
        if self._consecutive_failures < self.failure_threshold:
            return False
        if time.time() - self._opened_at > self.cooldown_seconds:
            # Cooldown expired — allow a probe request
            return False
        return True

    def allow(self) -> bool:
        """Check whether the call should proceed."""
        return not self.is_open

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._opened_at = time.time()
            logger.warning(
                "Circuit breaker OPEN after %d consecutive failures (cooldown %ds)",
                self._consecutive_failures, self.cooldown_seconds,
            )
