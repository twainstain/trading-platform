"""Base pipeline — generic candidate lifecycle orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from trading_platform.contracts import SubmissionRef, VerificationOutcome

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


@dataclass
class PipelineResult:
    """Outcome of processing one candidate through the pipeline."""

    candidate_id: str
    final_status: str
    reason: str
    net_profit: Decimal = ZERO
    timings: dict[str, float] = field(default_factory=dict)


class Simulator(Protocol):
    """Protocol for stage 4 — simulation (free dry-run)."""

    def simulate(self, candidate: Any) -> tuple[bool, str]: ...


class Submitter(Protocol):
    """Protocol for stage 5 — transaction/order submission."""

    def submit(self, candidate: Any) -> SubmissionRef: ...


class Verifier(Protocol):
    """Protocol for stage 6 — outcome verification."""

    def verify(self, submission: SubmissionRef) -> VerificationOutcome: ...


class BasePipeline:
    """Generic 6-stage pipeline. Products override stage methods.

    The pipeline enforces sequential execution, timing instrumentation, and
    stage hooks. Products own the persistence details for each stage via the
    ``on_*`` callbacks.
    """

    def __init__(
        self,
        simulator: Simulator | None = None,
        submitter: Submitter | None = None,
        verifier: Verifier | None = None,
    ) -> None:
        self.simulator = simulator
        self.submitter = submitter
        self.verifier = verifier

    def detect(self, candidate: Any) -> str:
        raise NotImplementedError

    def price(self, candidate_id: str, candidate: Any) -> None:
        raise NotImplementedError

    def evaluate_risk(self, candidate: Any) -> Any:
        raise NotImplementedError

    def on_approved(self, candidate_id: str, candidate: Any) -> None:
        pass

    def on_rejected(self, candidate_id: str, reason: str, candidate: Any) -> None:
        pass

    def on_simulated(self, candidate_id: str, success: bool, reason: str) -> None:
        pass

    def on_submitted(self, candidate_id: str, submission: SubmissionRef) -> None:
        pass

    def on_verified(self, candidate_id: str, result: VerificationOutcome) -> None:
        pass

    def process(self, candidate: Any) -> PipelineResult:
        """Run a candidate through all configured stages."""
        t0 = time.monotonic()
        timings: dict[str, float] = {}

        candidate_id = self.detect(candidate)
        timings["detect_ms"] = (time.monotonic() - t0) * 1000

        t1 = time.monotonic()
        self.price(candidate_id, candidate)
        timings["price_ms"] = (time.monotonic() - t1) * 1000

        t2 = time.monotonic()
        verdict = self.evaluate_risk(candidate)
        timings["risk_ms"] = (time.monotonic() - t2) * 1000

        if not verdict.approved:
            self.on_rejected(candidate_id, verdict.reason, candidate)
            timings["total_ms"] = (time.monotonic() - t0) * 1000
            return PipelineResult(candidate_id, verdict.reason, verdict.reason, timings=timings)

        self.on_approved(candidate_id, candidate)

        t3 = time.monotonic()
        if self.simulator is not None:
            sim_ok, sim_reason = self.simulator.simulate(candidate)
            self.on_simulated(candidate_id, sim_ok, sim_reason)
            timings["simulate_ms"] = (time.monotonic() - t3) * 1000
            if not sim_ok:
                timings["total_ms"] = (time.monotonic() - t0) * 1000
                return PipelineResult(candidate_id, "simulation_failed", sim_reason, timings=timings)
        else:
            timings["simulate_ms"] = 0.0

        t4 = time.monotonic()
        if self.submitter is not None:
            submission = self.submitter.submit(candidate)
            self.on_submitted(candidate_id, submission)
            timings["submit_ms"] = (time.monotonic() - t4) * 1000

            if self.verifier is not None:
                result = self.verifier.verify(submission)
                self.on_verified(candidate_id, result)
                timings["verify_ms"] = (time.monotonic() - t4) * 1000 - timings["submit_ms"]
                timings["total_ms"] = (time.monotonic() - t0) * 1000
                profit = result.profit if result.profit is not None else ZERO
                return PipelineResult(candidate_id, result.final_status, result.reason, profit, timings)

            timings["total_ms"] = (time.monotonic() - t0) * 1000
            return PipelineResult(candidate_id, "submitted", "awaiting_verification", timings=timings)

        timings["total_ms"] = (time.monotonic() - t0) * 1000
        return PipelineResult(candidate_id, "dry_run", "approved_not_submitted", timings=timings)
