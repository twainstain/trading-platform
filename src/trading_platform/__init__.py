"""Trading Platform shared infrastructure library."""

from trading_platform.alerting import AlertBackend, AlertDispatcher, BaseAlerter
from trading_platform.config import BaseConfig, find_env_file, get_env, load_env, require_env
from trading_platform.contracts import RiskVerdict, SubmissionRef, VerificationOutcome
from trading_platform.data import CacheEntry, EndpointProvider, TTLCache
from trading_platform.observability import (
    DecimalEncoder,
    LatencyTracker,
    MetricsCollector,
    get_logger,
    setup_logging,
)
from trading_platform.persistence import BaseRepository, DbConnection, close_db, get_db, init_db
from trading_platform.pipeline import BasePipeline, PipelineResult, PriorityQueue, QueuedItem
from trading_platform.risk import (
    BreakerState,
    CircuitBreaker,
    CircuitBreakerConfig,
    RetryPolicy,
    RetryResult,
    RiskRule,
    RuleBasedPolicy,
    config_hash,
    execute_with_retry,
)

__all__ = [
    # Alerting
    "AlertBackend",
    "AlertDispatcher",
    "BaseAlerter",
    # Config
    "BaseConfig",
    "find_env_file",
    "get_env",
    "load_env",
    "require_env",
    # Contracts
    "RiskVerdict",
    "SubmissionRef",
    "VerificationOutcome",
    # Data
    "CacheEntry",
    "EndpointProvider",
    "TTLCache",
    # Observability
    "DecimalEncoder",
    "LatencyTracker",
    "MetricsCollector",
    "get_logger",
    "setup_logging",
    # Persistence
    "BaseRepository",
    "DbConnection",
    "close_db",
    "get_db",
    "init_db",
    # Pipeline
    "BasePipeline",
    "PipelineResult",
    "PriorityQueue",
    "QueuedItem",
    # Risk
    "BreakerState",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "RetryPolicy",
    "RetryResult",
    "RiskRule",
    "RuleBasedPolicy",
    "config_hash",
    "execute_with_retry",
]

__version__ = "0.1.0"
