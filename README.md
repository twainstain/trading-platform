# Trading Platform

Shared infrastructure for building trading systems such as:
- **ArbitrageTrader**
- **PolymarketTrader**

## What's Included

| Package | Purpose |
|---------|---------|
| `pipeline` | Candidate lifecycle orchestration + priority queue |
| `risk` | Rule-based risk evaluation + circuit breaker |
| `alerting` | Scheduled reports + multi-backend dispatcher |
| `observability` | Metrics, counters, latency percentiles |
| `config` | Environment loading helpers |
| `data` | TTL cache |
| `contracts` | Shared typed contracts for pipeline/risk flows |

## Install

```bash
pip install -e ".[dev]"
```

## Usage

```python
from pipeline import BasePipeline, PriorityQueue
from risk import RuleBasedPolicy, CircuitBreaker
from alerting import BaseAlerter, AlertDispatcher
from observability import MetricsCollector
from data import TTLCache
from contracts import SubmissionRef, VerificationOutcome
```

## Design Principles

- **Zero product-specific code**
- **One-way dependency** — products import platform, never the reverse
- **Typed contracts** — shared pipeline interactions use `SubmissionRef` and `VerificationOutcome`
- **Protocol-based extension** — products plug in custom rules, submitters, verifiers, and simulators
- **Thread-safe shared primitives** where shared mutable state exists
