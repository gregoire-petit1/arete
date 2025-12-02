"""Token usage tracking and rate limiting for Groq API.

Manages token budgets to stay within Groq free tier limits.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GroqLimits:
    """Groq rate limits for a specific model."""

    model: str
    requests_per_minute: int
    requests_per_day: int
    tokens_per_minute: int
    tokens_per_day: int

    @classmethod
    def for_model(cls, model: str) -> "GroqLimits":
        """Get limits for a specific model."""
        # Groq free tier limits (as of Dec 2024)
        limits = {
            "llama-3.3-70b-versatile": cls(
                model="llama-3.3-70b-versatile",
                requests_per_minute=30,
                requests_per_day=1000,
                tokens_per_minute=12000,
                tokens_per_day=100000,
            ),
            "llama-3.1-8b-instant": cls(
                model="llama-3.1-8b-instant",
                requests_per_minute=30,
                requests_per_day=14400,
                tokens_per_minute=6000,
                tokens_per_day=500000,
            ),
            "meta-llama/llama-4-scout-17b-16e-instruct": cls(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                requests_per_minute=30,
                requests_per_day=1000,
                tokens_per_minute=30000,
                tokens_per_day=500000,
            ),
        }
        return limits.get(
            model,
            cls(
                model=model,
                requests_per_minute=30,
                requests_per_day=1000,
                tokens_per_minute=6000,
                tokens_per_day=100000,
            ),
        )


@dataclass
class UsageRecord:
    """Record of token usage."""

    timestamp: datetime
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class TokenManager:
    """Manages token usage and enforces rate limits.

    Tracks usage per model and provides:
    - Real-time usage statistics
    - Rate limit enforcement
    - Automatic model fallback when quota exceeded
    - Persistent usage tracking (daily reset)
    """

    data_dir: Path = field(default_factory=lambda: Path("data"))
    _usage_records: list[UsageRecord] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)
    _last_save: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Load existing usage data."""
        self._usage_file = self.data_dir / ".llm_usage.json"
        self._load_usage()

    def _load_usage(self) -> None:
        """Load usage from disk."""
        if not self._usage_file.exists():
            return

        try:
            with open(self._usage_file) as f:
                data = json.load(f)

            # Only load today's records
            today = datetime.now().date()
            for record in data.get("records", []):
                ts = datetime.fromisoformat(record["timestamp"])
                if ts.date() == today:
                    self._usage_records.append(
                        UsageRecord(
                            timestamp=ts,
                            model=record["model"],
                            prompt_tokens=record["prompt_tokens"],
                            completion_tokens=record["completion_tokens"],
                            total_tokens=record["total_tokens"],
                        )
                    )
            logger.debug(f"Loaded {len(self._usage_records)} usage records for today")
        except Exception as e:
            logger.warning(f"Failed to load usage data: {e}")

    def _save_usage(self) -> None:
        """Persist usage to disk."""
        # Don't save too frequently
        if (datetime.now() - self._last_save).seconds < 60:
            return

        self.data_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "last_updated": datetime.now().isoformat(),
            "records": [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "model": r.model,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.total_tokens,
                }
                for r in self._usage_records
            ],
        }

        try:
            with open(self._usage_file, "w") as f:
                json.dump(data, f, indent=2)
            self._last_save = datetime.now()
        except Exception as e:
            logger.warning(f"Failed to save usage data: {e}")

    def record_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record token usage for a request."""
        with self._lock:
            record = UsageRecord(
                timestamp=datetime.now(),
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
            self._usage_records.append(record)
            self._save_usage()

            logger.info(
                f"Token usage: {prompt_tokens} prompt + {completion_tokens} completion "
                f"= {record.total_tokens} total ({model})"
            )

    def get_usage_stats(self, model: str | None = None) -> dict[str, Any]:
        """Get current usage statistics."""
        now = datetime.now()
        today = now.date()
        minute_ago = now - timedelta(minutes=1)

        with self._lock:
            # Filter records
            if model:
                records = [r for r in self._usage_records if r.model == model]
            else:
                records = self._usage_records

            # Today's records
            today_records = [r for r in records if r.timestamp.date() == today]

            # Last minute's records
            minute_records = [r for r in today_records if r.timestamp >= minute_ago]

            # Aggregate
            tokens_today = sum(r.total_tokens for r in today_records)
            tokens_minute = sum(r.total_tokens for r in minute_records)
            requests_today = len(today_records)
            requests_minute = len(minute_records)

            # Get limits
            model_name = model or "llama-3.3-70b-versatile"
            limits = GroqLimits.for_model(model_name)

            return {
                "model": model_name,
                "tokens": {
                    "today": tokens_today,
                    "limit_day": limits.tokens_per_day,
                    "percent_day": round(tokens_today / limits.tokens_per_day * 100, 1),
                    "minute": tokens_minute,
                    "limit_minute": limits.tokens_per_minute,
                    "percent_minute": round(
                        tokens_minute / limits.tokens_per_minute * 100, 1
                    ),
                },
                "requests": {
                    "today": requests_today,
                    "limit_day": limits.requests_per_day,
                    "minute": requests_minute,
                    "limit_minute": limits.requests_per_minute,
                },
                "remaining": {
                    "tokens_day": limits.tokens_per_day - tokens_today,
                    "tokens_minute": limits.tokens_per_minute - tokens_minute,
                    "requests_day": limits.requests_per_day - requests_today,
                },
            }

    def can_make_request(
        self,
        model: str,
        estimated_tokens: int = 5000,
    ) -> tuple[bool, str]:
        """Check if a request can be made within rate limits.

        Args:
            model: Model to check
            estimated_tokens: Estimated total tokens for request

        Returns:
            (can_proceed, reason)
        """
        stats = self.get_usage_stats(model)

        # Check daily token limit (with 10% buffer)
        if stats["remaining"]["tokens_day"] < estimated_tokens * 1.1:
            return (
                False,
                f"Daily token limit approaching: {stats['tokens']['percent_day']:.0f}% used",
            )

        # Check per-minute limit
        if stats["remaining"]["tokens_minute"] < estimated_tokens:
            wait_seconds = 60 - (datetime.now().second)
            return (
                False,
                f"Minute limit reached, wait {wait_seconds}s",
            )

        # Check request limits
        if stats["remaining"]["requests_day"] < 5:
            return (
                False,
                f"Daily request limit approaching: {stats['requests']['today']}/{stats['requests']['limit_day']}",
            )

        return (True, "OK")

    def get_best_model(self, estimated_tokens: int = 5000) -> str:
        """Get the best available model considering limits.

        Falls back to lighter models if primary quota exceeded.
        """
        # Order of preference
        models = [
            "llama-3.3-70b-versatile",  # Best quality
            "meta-llama/llama-4-scout-17b-16e-instruct",  # Good quality, higher limits
            "llama-3.1-8b-instant",  # Fast, highest limits
        ]

        for model in models:
            can_use, reason = self.can_make_request(model, estimated_tokens)
            if can_use:
                logger.debug(f"Selected model: {model}")
                return model
            logger.warning(f"Model {model} unavailable: {reason}")

        # If all exhausted, return cheapest with warning
        logger.error("All model quotas exceeded, using fallback")
        return "llama-3.1-8b-instant"

    def wait_if_needed(self, model: str, estimated_tokens: int = 5000) -> float:
        """Wait if rate limited.

        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        can_use, reason = self.can_make_request(model, estimated_tokens)

        if can_use:
            return 0.0

        if "wait" in reason.lower():
            # Extract wait time
            import re

            match = re.search(r"wait (\d+)s", reason)
            if match:
                wait_time = int(match.group(1))
                logger.info(f"Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                return float(wait_time)

        return 0.0


# Singleton instance
_token_manager: TokenManager | None = None


def get_token_manager() -> TokenManager:
    """Get or create the global token manager."""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager
