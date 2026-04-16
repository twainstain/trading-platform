#!/usr/bin/env python3
"""Test bot — exercises the full platform pipeline with simulated data.

Produces logs/latency.jsonl for performance analysis, matching the
ArbitrageTrader format so the same analysis tools work on both.

This is the platform's equivalent of ArbitrageTrader's simulation mode.
It validates that the platform primitives (pipeline, risk, observability,
persistence, metrics, cache) all work together end-to-end.

Usage:
    PYTHONPATH=src python scripts/run_test_bot.py
    PYTHONPATH=src python scripts/run_test_bot.py --config config/test_agent.json
    PYTHONPATH=src python scripts/run_test_bot.py --iterations 50
    PYTHONPATH=src python scripts/run_test_bot.py --iterations 100 --analyze
"""

from __future__ import annotations

import argparse
import json
import random
import signal
import sys
import time
import uuid
from trading_platform.dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

# Ensure src/ is on the path.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from trading_platform.contracts import RiskVerdict, SubmissionRef, VerificationOutcome
from trading_platform.data.cache import TTLCache
from trading_platform.observability.latency_tracker import LatencyTracker, analyze_latency
from trading_platform.observability.log import setup_logging, get_logger, log_json
from trading_platform.observability.metrics import MetricsCollector
from trading_platform.observability.time_windows import WINDOWS
from trading_platform.persistence.db import init_db, close_db
from trading_platform.persistence.base_repository import BaseRepository
from trading_platform.pipeline.base_pipeline import BasePipeline, PipelineResult, Simulator
from trading_platform.pipeline.queue import PriorityQueue
from trading_platform.risk.base_policy import RuleBasedPolicy
from trading_platform.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from trading_platform.risk.retry import execute_with_retry, RetryPolicy

D = Decimal
ZERO = D("0")
ONE = D("1")
BPS = D("10000")

logger = get_logger("test_bot")


# ---------------------------------------------------------------------------
# Simulated market
# ---------------------------------------------------------------------------

@dataclass
class Quote:
    venue: str
    pair: str
    buy_price: Decimal
    sell_price: Decimal
    fee_bps: int
    timestamp: float = 0.0


@dataclass
class VenueConfig:
    name: str
    fee_bps: int = 30
    volatility_bps: int = 18


@dataclass
class PairConfig:
    name: str
    base_price: Decimal = D("3000")
    venues: list[VenueConfig] = field(default_factory=list)


@dataclass
class Candidate:
    """A detected opportunity candidate."""
    candidate_id: str
    pair: str
    buy_venue: str
    sell_venue: str
    buy_price: Decimal
    sell_price: Decimal
    spread_bps: Decimal
    gross_profit: Decimal
    net_profit: Decimal
    fee_cost: Decimal
    slippage_cost: Decimal
    estimated_cost: Decimal
    detected_at: float = 0.0


class SimulatedMarket:
    """Random-walk market across multiple pairs and venues."""

    def __init__(self, pairs: list[PairConfig], seed: int = 42) -> None:
        self._rng = random.Random(seed)
        self._pairs = pairs
        # Per-venue current mid prices.
        self._prices: dict[str, dict[str, Decimal]] = {}
        for pair_cfg in pairs:
            self._prices[pair_cfg.name] = {}
            for v in pair_cfg.venues:
                jitter = D(str(self._rng.uniform(0.998, 1.002)))
                self._prices[pair_cfg.name][v.name] = pair_cfg.base_price * jitter

    def get_quotes(self) -> list[Quote]:
        now = time.time()
        quotes = []
        for pair_cfg in self._pairs:
            for v in pair_cfg.venues:
                mid = self._prices[pair_cfg.name][v.name]
                # Random walk tick.
                move_bps = D(str(self._rng.uniform(-v.volatility_bps, v.volatility_bps)))
                mid *= ONE + move_bps / BPS
                self._prices[pair_cfg.name][v.name] = mid
                half_spread = mid * D("0.0005")
                quotes.append(Quote(
                    venue=v.name,
                    pair=pair_cfg.name,
                    buy_price=mid + half_spread,
                    sell_price=mid - half_spread,
                    fee_bps=v.fee_bps,
                    timestamp=now,
                ))
        return quotes


# ---------------------------------------------------------------------------
# Risk rules
# ---------------------------------------------------------------------------

class MinSpreadRule:
    name = "min_spread"

    def __init__(self, min_bps: Decimal = D("15")):
        self.min_bps = min_bps

    def evaluate(self, candidate, context):
        if candidate.spread_bps < self.min_bps:
            return RiskVerdict(False, "below_min_spread",
                               {"spread": str(candidate.spread_bps), "min": str(self.min_bps)})
        return RiskVerdict(True, "ok")


class MinProfitRule:
    name = "min_profit"

    def __init__(self, min_profit: Decimal = D("0.005")):
        self.min_profit = min_profit

    def evaluate(self, candidate, context):
        if candidate.net_profit < self.min_profit:
            return RiskVerdict(False, "below_min_profit",
                               {"profit": str(candidate.net_profit), "min": str(self.min_profit)})
        return RiskVerdict(True, "ok")


class CostRatioRule:
    name = "cost_ratio"

    def __init__(self, max_ratio: Decimal = D("0.5")):
        self.max_ratio = max_ratio

    def evaluate(self, candidate, context):
        if candidate.gross_profit == ZERO:
            return RiskVerdict(False, "zero_gross_profit")
        ratio = candidate.estimated_cost / candidate.gross_profit
        if ratio > self.max_ratio:
            return RiskVerdict(False, "cost_too_high",
                               {"ratio": str(ratio), "max": str(self.max_ratio)})
        return RiskVerdict(True, "ok")


# ---------------------------------------------------------------------------
# Pipeline implementation
# ---------------------------------------------------------------------------

class FakeSimulator:
    """Simulated stage 4 — always succeeds (no real execution)."""
    def simulate(self, candidate):
        return (True, "simulation_approved")


class TestBotPipeline(BasePipeline):
    """Concrete pipeline for the test bot."""

    def __init__(self, risk_policy, metrics, repo, breaker, trade_size, estimated_cost,
                 slippage_bps, **kwargs):
        super().__init__(**kwargs)
        self.risk_policy = risk_policy
        self.metrics = metrics
        self.repo = repo
        self.breaker = breaker
        self.trade_size = trade_size
        self.estimated_cost = estimated_cost
        self.slippage_bps = slippage_bps

    def detect(self, candidate):
        self.metrics.increment("pipeline_detect")
        return candidate.candidate_id

    def price(self, candidate_id, candidate):
        self.metrics.increment("pipeline_price")

    def evaluate_risk(self, candidate):
        self.metrics.increment("pipeline_risk")
        if self.breaker.should_block():
            return RiskVerdict(False, "circuit_breaker_open")
        return self.risk_policy.evaluate(candidate)

    def on_approved(self, candidate_id, candidate):
        self.metrics.increment("approved")

    def on_rejected(self, candidate_id, reason, candidate):
        self.metrics.increment("rejected", tag=reason)

    def on_simulated(self, candidate_id, success, reason):
        self.metrics.increment("simulated")


# ---------------------------------------------------------------------------
# Scanner — find opportunities from quotes
# ---------------------------------------------------------------------------

def scan_opportunities(
    quotes: list[Quote],
    trade_size: Decimal,
    estimated_cost: Decimal,
    slippage_bps: Decimal,
) -> list[Candidate]:
    """Find cross-venue spread opportunities from quotes."""
    by_pair: dict[str, list[Quote]] = {}
    for q in quotes:
        by_pair.setdefault(q.pair, []).append(q)

    candidates = []
    for pair, pair_quotes in by_pair.items():
        for buy_q in pair_quotes:
            for sell_q in pair_quotes:
                if buy_q.venue == sell_q.venue:
                    continue
                if sell_q.sell_price <= buy_q.buy_price:
                    continue
                spread = sell_q.sell_price - buy_q.buy_price
                spread_bps = (spread / buy_q.buy_price) * BPS
                gross = spread * trade_size / buy_q.buy_price
                fee_cost = trade_size * (D(str(buy_q.fee_bps)) + D(str(sell_q.fee_bps))) / BPS
                slippage_cost = trade_size * slippage_bps / BPS
                net = gross - fee_cost - slippage_cost - estimated_cost

                candidates.append(Candidate(
                    candidate_id=f"opp_{uuid.uuid4().hex[:12]}",
                    pair=pair,
                    buy_venue=buy_q.venue,
                    sell_venue=sell_q.venue,
                    buy_price=buy_q.buy_price,
                    sell_price=sell_q.sell_price,
                    spread_bps=spread_bps.quantize(D("0.01")),
                    gross_profit=gross.quantize(D("0.00000001")),
                    net_profit=net.quantize(D("0.00000001")),
                    fee_cost=fee_cost.quantize(D("0.00000001")),
                    slippage_cost=slippage_cost.quantize(D("0.00000001")),
                    estimated_cost=estimated_cost,
                    detected_at=time.time(),
                ))
    # Highest net profit first.
    candidates.sort(key=lambda c: c.net_profit, reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Test bot schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS system_checkpoints (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_type TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Main bot loop
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    raw = json.loads(Path(path).read_text())
    pairs = []
    for p in raw.get("pairs", []):
        venues = [VenueConfig(**v) for v in p.get("venues", [])]
        pairs.append(PairConfig(
            name=p["name"],
            base_price=D(str(p["base_price"])),
            venues=venues,
        ))
    return {
        "pairs": pairs,
        "trade_size": D(raw.get("trade_size", "1.5")),
        "min_spread_bps": D(str(raw.get("min_spread_bps", 15))),
        "min_profit": D(raw.get("min_profit", "0.005")),
        "estimated_cost": D(raw.get("estimated_cost", "0.003")),
        "slippage_bps": D(str(raw.get("slippage_bps", 15))),
        "iterations": int(raw.get("iterations", 20)),
        "poll_interval": float(raw.get("poll_interval_seconds", 0)),
    }


def run(args: argparse.Namespace) -> None:
    # Resolve config.
    config_path = args.config or str(_PROJECT_ROOT / "config" / "test_agent.json")
    cfg = load_config(config_path)
    iterations = args.iterations or cfg["iterations"]

    # Setup directories.
    log_dir = _PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    data_dir = _PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    # Setup logging.
    setup_logging(log_dir=str(log_dir), log_prefix="test_bot")

    # Setup latency tracker — truncate on each run for clean analysis.
    latency_path = log_dir / "latency.jsonl"
    if latency_path.exists():
        latency_path.unlink()
    tracker = LatencyTracker(output_path=latency_path)

    # Setup metrics.
    metrics = MetricsCollector()

    # Setup persistence (SQLite in data/).
    db = init_db(db_path=str(data_dir / "test_bot.db"), schema=_SCHEMA)
    repo = BaseRepository(db)

    # Setup cache.
    cache = TTLCache(ttl_seconds=60)

    # Setup risk.
    risk_policy = RuleBasedPolicy(rules=[
        MinSpreadRule(cfg["min_spread_bps"]),
        MinProfitRule(cfg["min_profit"]),
        CostRatioRule(),
    ])
    breaker = CircuitBreaker(CircuitBreakerConfig(
        max_failures=5, failure_window_seconds=60,
        max_stale_seconds=9999,  # no staleness in sim
    ))

    # Setup queue.
    queue = PriorityQueue(max_size=100)

    # Setup pipeline.
    pipeline = TestBotPipeline(
        risk_policy=risk_policy,
        metrics=metrics,
        repo=repo,
        breaker=breaker,
        trade_size=cfg["trade_size"],
        estimated_cost=cfg["estimated_cost"],
        slippage_bps=cfg["slippage_bps"],
        simulator=FakeSimulator(),
    )

    # Setup market.
    market = SimulatedMarket(cfg["pairs"])

    # --- Banner ---
    print()
    print("=" * 60)
    print("  Trading Platform — Test Bot (Simulation)")
    print("=" * 60)
    print(f"  Config:      {config_path}")
    print(f"  Iterations:  {iterations}")
    print(f"  Pairs:       {len(cfg['pairs'])}")
    total_venues = sum(len(p.venues) for p in cfg['pairs'])
    print(f"  Venues:      {total_venues}")
    print(f"  Trade Size:  {cfg['trade_size']}")
    print(f"  Min Spread:  {cfg['min_spread_bps']} bps")
    print(f"  Min Profit:  {cfg['min_profit']}")
    print(f"  Est Cost:    {cfg['estimated_cost']}")
    print(f"  Latency Log: {latency_path}")
    print("=" * 60)
    print()

    logger.info("Test bot starting — %d iterations", iterations)
    breaker.record_fresh_data()

    total_candidates = 0
    total_approved = 0
    total_rejected = 0
    total_profit = ZERO
    shutdown_requested = False

    def _handle_signal(sig, frame):
        nonlocal shutdown_requested
        if shutdown_requested:
            sys.exit(1)
        shutdown_requested = True
        logger.info("Shutdown requested — finishing current scan")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    for scan_idx in range(1, iterations + 1):
        if shutdown_requested:
            logger.info("Shutting down after scan %d", scan_idx - 1)
            break
        t_scan_start = time.monotonic()
        tracker.start_cycle()

        # 1. Fetch quotes.
        quotes = market.get_quotes()
        tracker.mark("data_fetch")
        metrics.increment("scans")

        # Cache hit/miss simulation.
        for q in quotes:
            cache_key = f"{q.pair}:{q.venue}"
            cached = cache.get(cache_key)
            if cached is None:
                cache.set(cache_key, q.buy_price, reason="quote")
            else:
                metrics.increment("cache_hits")

        tracker.mark("scanner_start")

        # 2. Scan for opportunities.
        candidates = scan_opportunities(
            quotes, cfg["trade_size"], cfg["estimated_cost"], cfg["slippage_bps"],
        )
        tracker.mark("scanner")
        metrics.increment("candidates_found", amount=len(candidates))
        total_candidates += len(candidates)

        if not candidates:
            tracker.record_cycle_summary(
                item_count=len(quotes),
                processed_count=0,
                rejected_count=0,
                status="no_opportunity",
            )
            metrics.increment("empty_scans")
            if cfg["poll_interval"] > 0:
                time.sleep(cfg["poll_interval"])
            continue

        # 3. Queue candidates.
        for c in candidates:
            queue.push(c, priority=float(c.net_profit), metadata={"pair": c.pair})
        tracker.mark("queue")

        # 4. Process through pipeline.
        processed = 0
        rejected = 0
        scan_marks = tracker.get_marks()

        while not queue.is_empty:
            item = queue.pop()
            if item is None:
                break
            candidate = item.item

            result = pipeline.process(candidate)
            metrics.record_latency(result.timings.get("total_ms", 0))

            if result.final_status in ("dry_run", "submitted", "verified"):
                total_approved += 1
                processed += 1
                total_profit += result.net_profit
                log_json("pipeline_approved",
                         candidate_id=candidate.candidate_id,
                         pair=candidate.pair,
                         net_profit=str(candidate.net_profit))
            else:
                total_rejected += 1
                rejected += 1

            # Record to latency log (matching ArbitrageTrader format).
            tracker.record_pipeline(
                candidate_id=candidate.candidate_id,
                pipeline_timings=result.timings,
                status=result.final_status,
                meta={
                    "pair": candidate.pair,
                    "buy_venue": candidate.buy_venue,
                    "sell_venue": candidate.sell_venue,
                    "spread_bps": float(candidate.spread_bps),
                    "net_profit": float(candidate.net_profit),
                },
                cycle_marks=scan_marks,
            )

        tracker.record_cycle_summary(
            item_count=len(quotes),
            processed_count=processed,
            rejected_count=rejected,
            status="processed" if processed > 0 else "all_rejected",
        )

        scan_ms = (time.monotonic() - t_scan_start) * 1000

        if scan_idx % 5 == 0 or scan_idx == 1:
            logger.info(
                "Scan %d/%d: %d quotes, %d candidates, %d approved, %d rejected (%.1fms)",
                scan_idx, iterations, len(quotes), len(candidates),
                processed, rejected, scan_ms,
            )

        if cfg["poll_interval"] > 0:
            time.sleep(cfg["poll_interval"])

    # --- Summary ---
    tracker.close()
    snap = metrics.snapshot()

    print()
    print("=" * 60)
    print("  Test Bot — Run Complete")
    print("=" * 60)
    print(f"  Iterations:      {iterations}")
    print(f"  Total Candidates: {total_candidates}")
    print(f"  Approved:         {total_approved}")
    print(f"  Rejected:         {total_rejected}")
    print(f"  Empty Scans:      {snap['counters'].get('empty_scans', 0)}")
    print(f"  Total Profit:     {total_profit}")
    print(f"  Avg Latency:      {snap['avg_latency_ms']:.2f}ms")
    print(f"  P95 Latency:      {snap['p95_latency_ms']:.2f}ms")
    print(f"  Cache Hits:       {snap['counters'].get('cache_hits', 0)}")
    print(f"  Uptime:           {snap['uptime_seconds']:.1f}s")
    print(f"  Latency Log:      {latency_path}")
    print("=" * 60)

    # Rejection breakdown.
    tagged = snap.get("tagged_counters", {}).get("rejected", {})
    if tagged:
        print()
        print("  Rejection Reasons:")
        for reason, count in sorted(tagged.items(), key=lambda x: -x[1]):
            print(f"    {reason}: {count}")

    print()
    logger.info("Test bot finished — %d approved, %d rejected", total_approved, total_rejected)

    # Save checkpoint.
    repo.save_checkpoint("last_test_run", BaseRepository._now())
    repo.save_checkpoint("last_test_result", json.dumps({
        "iterations": iterations,
        "approved": total_approved,
        "rejected": total_rejected,
        "profit": str(total_profit),
        "avg_latency_ms": snap["avg_latency_ms"],
        "p95_latency_ms": snap["p95_latency_ms"],
    }))

    close_db()

    # Optionally run analysis.
    if args.analyze:
        print()
        analyze_latency(latency_path)


def main():
    parser = argparse.ArgumentParser(description="Test bot — platform simulation")
    parser.add_argument("--config", default=None, help="Config JSON file")
    parser.add_argument("--iterations", type=int, default=None, help="Number of scan cycles")
    parser.add_argument("--analyze", action="store_true", help="Run latency analysis after")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
