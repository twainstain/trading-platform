"""Bounded retry logic with re-evaluation between attempts.

Generic pattern: execute a callable with bounded retries, optionally
re-checking profitability/validity before each retry. Supports config
hashing for audit trails.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class RetryPolicy:
    """Configuration for bounded retry behavior."""
    max_retries: int = 2
    delay_seconds: float = 1.0
    require_re_evaluation: bool = True


@dataclass
class RetryResult:
    """Outcome of a retry-wrapped execution."""
    success: bool
    attempts: int
    last_reason: str
    config_hash: str = ""


def config_hash(config_dict: dict) -> str:
    """Compute a deterministic hash of a config dict for versioning."""
    raw = json.dumps(config_dict, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def execute_with_retry(
    execute_fn: Callable[[], tuple[bool, str]],
    is_still_valid: Callable[[], bool] | None = None,
    policy: RetryPolicy | None = None,
    current_config_hash: str = "",
) -> RetryResult:
    """Execute with bounded retries, re-evaluating validity between attempts.

    Args:
        execute_fn: Callable returning (success, reason).
        is_still_valid: Optional check before each retry. If False, abort.
        policy: Retry configuration.
        current_config_hash: Hash of the active config for audit trail.

    Returns:
        RetryResult with the outcome.
    """
    pol = policy or RetryPolicy()
    last_reason = ""

    for attempt in range(1, pol.max_retries + 2):  # 1 initial + max_retries
        if attempt > 1:
            if pol.require_re_evaluation and is_still_valid is not None:
                if not is_still_valid():
                    logger.info("Retry aborted: no longer valid (attempt %d)", attempt)
                    return RetryResult(
                        success=False, attempts=attempt - 1,
                        last_reason="retry_aborted:not_valid",
                        config_hash=current_config_hash,
                    )
            time.sleep(pol.delay_seconds)

        success, reason = execute_fn()
        last_reason = reason

        if success:
            return RetryResult(
                success=True, attempts=attempt,
                last_reason=reason, config_hash=current_config_hash,
            )

        logger.warning("Execution failed (attempt %d/%d): %s",
                       attempt, pol.max_retries + 1, reason)

        if attempt > pol.max_retries:
            break

    return RetryResult(
        success=False, attempts=pol.max_retries + 1,
        last_reason=last_reason, config_hash=current_config_hash,
    )
