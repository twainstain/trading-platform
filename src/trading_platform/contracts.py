"""Shared typed contracts used across the trading platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class RiskVerdict:
    """Result of a risk evaluation."""

    approved: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubmissionRef:
    """Platform-neutral reference returned by a submitter."""

    reference_id: str
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationOutcome:
    """Platform-neutral verification result returned by a verifier."""

    final_status: str
    reason: str
    profit: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
