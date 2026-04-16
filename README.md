# Trading Platform

Shared infrastructure for building trading bots. Used by:
- **ArbitrageTrader** — DEX arbitrage on Ethereum/L2s
- **PolymarketTrader** — prediction market latency arbitrage

## What's Included

| Package | Purpose |
|---------|---------|
| `pipeline/` | 6-stage candidate lifecycle + heapq priority queue |
| `risk/` | Rule-based risk evaluation + circuit breaker |
| `alerting/` | Scheduled reports + multi-backend dispatcher |
| `observability/` | Metrics, counters, latency percentiles |
| `config/` | Environment loading (.env) |
| `data/` | TTL cache |

## Install

```bash
# From git
pip install "trading-platform @ git+https://github.com/twainstain/trading-platform.git"

# With extras
pip install "trading-platform[all] @ git+https://github.com/twainstain/trading-platform.git"

# For development
pip install -e ".[dev]"
```

## Usage

```python
from pipeline import BasePipeline, PriorityQueue
from risk import RuleBasedPolicy, CircuitBreaker
from alerting.base_alerter import BaseAlerter
from observability.metrics import MetricsCollector
from data.cache import TTLCache
```

## Design Principles

- **Zero product-specific code** — platform has no knowledge of DEXes, Polymarket, or any trading venue
- **One-way dependency** — products import platform, never the reverse
- **Protocol-based extension** — products plug in via Protocol classes (Simulator, Submitter, Verifier, RiskRule)
- **Thread-safe** — all shared state protected by locks
- **Capital preservation > profit** — risk framework defaults to rejecting, not approving
