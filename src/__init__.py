"""Trading Platform shared infrastructure library."""

from alerting import AlertDispatcher, BaseAlerter
from config import find_env_file, get_env, load_env, require_env
from contracts import RiskVerdict, SubmissionRef, VerificationOutcome
from data import TTLCache
from observability import MetricsCollector
from pipeline import BasePipeline, PipelineResult, PriorityQueue, QueuedItem
from risk import (
    BreakerState,
    CircuitBreaker,
    CircuitBreakerConfig,
    RiskRule,
    RuleBasedPolicy,
)

__all__ = [
    "AlertDispatcher",
    "BaseAlerter",
    "BasePipeline",
    "BreakerState",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "MetricsCollector",
    "PipelineResult",
    "PriorityQueue",
    "QueuedItem",
    "RiskRule",
    "RiskVerdict",
    "RuleBasedPolicy",
    "SubmissionRef",
    "TTLCache",
    "VerificationOutcome",
    "find_env_file",
    "get_env",
    "load_env",
    "require_env",
]

__version__ = "0.1.0"
