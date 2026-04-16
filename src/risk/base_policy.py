"""Rule-based risk evaluation framework."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from contracts import RiskVerdict

logger = logging.getLogger(__name__)


class RiskRule(Protocol):
    """One risk check. Products implement their own rules."""

    name: str

    def evaluate(self, candidate: Any, context: dict[str, Any]) -> RiskVerdict:
        ...


class RuleBasedPolicy:
    """Evaluates a list of rules sequentially. Any failure = hard veto."""

    def __init__(
        self,
        rules: list[RiskRule] | None = None,
        simulation_mode: bool = False,
    ) -> None:
        self.rules = list(rules or [])
        self.simulation_mode = simulation_mode

    def add_rule(self, rule: RiskRule) -> None:
        self.rules.append(rule)

    def evaluate(self, candidate: Any, **context: Any) -> RiskVerdict:
        for rule in self.rules:
            try:
                verdict = rule.evaluate(candidate, context)
            except Exception as exc:
                name = getattr(rule, "name", "?")
                logger.error("Risk rule '%s' raised: %s", name, exc)
                return RiskVerdict(False, f"rule_error:{name}", {"error": str(exc)})

            if not verdict.approved:
                logger.debug(
                    "Risk rejected by '%s': %s",
                    getattr(rule, "name", "?"),
                    verdict.reason,
                )
                return verdict

        if self.simulation_mode:
            return RiskVerdict(True, "simulation_approved", {"simulation": True})

        return RiskVerdict(True, "all_rules_passed")
