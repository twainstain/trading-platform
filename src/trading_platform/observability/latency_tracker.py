"""Latency tracker — records per-stage timing for pipeline executions.

Writes to a JSONL file (one JSON line per event) for post-hoc analysis.
Thread-safe: the lock protects shared state, but file I/O happens
outside the lock to avoid stalling scanner/consumer threads.

Usage:
    tracker = LatencyTracker("logs/latency.jsonl")
    tracker.start_cycle()
    # ... fetch data ...
    tracker.mark("data_fetch")
    # ... process ...
    tracker.record_pipeline("id1", {"detect_ms": 0.3, "total_ms": 0.8}, meta={"pair": "X"})
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


@dataclass
class CycleTiming:
    """Timing data for one processing cycle."""
    cycle_index: int = 0
    started_at: float = 0.0
    marks: dict = field(default_factory=dict)


class LatencyTracker:
    """Thread-safe latency recorder with JSONL output.

    Designed for low overhead in the hot path — only the mark/record
    calls acquire a short lock. File I/O is done outside the lock.
    """

    def __init__(self, output_path: str | Path | None = None) -> None:
        self._lock = Lock()
        self._cycle = CycleTiming()
        self._cycle_count = 0
        self._file = None
        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(path, "a", encoding="utf-8")

    def start_cycle(self) -> None:
        """Mark the start of a new processing cycle."""
        with self._lock:
            self._cycle_count += 1
            self._cycle = CycleTiming(
                cycle_index=self._cycle_count,
                started_at=time.monotonic(),
            )

    def mark(self, stage: str) -> None:
        """Record a timing mark for the current cycle."""
        with self._lock:
            elapsed_ms = (time.monotonic() - self._cycle.started_at) * 1000
            self._cycle.marks[stage] = round(elapsed_ms, 2)

    def get_marks(self) -> dict:
        """Return a snapshot of current cycle marks."""
        with self._lock:
            return dict(self._cycle.marks)

    def record_pipeline(
        self,
        candidate_id: str,
        pipeline_timings: dict,
        status: str = "",
        meta: dict | None = None,
        cycle_marks: dict | None = None,
    ) -> None:
        """Record a pipeline execution with all timing data.

        Args:
            candidate_id: Unique ID for the candidate.
            pipeline_timings: Stage timings from BasePipeline (detect_ms, etc.).
            status: Final status of the candidate.
            meta: Additional metadata (pair, chain, spread, etc.).
            cycle_marks: Snapshot of cycle marks from when the candidate was
                         queued. If None, uses current cycle marks.
        """
        with self._lock:
            total_ms = (time.monotonic() - self._cycle.started_at) * 1000
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cycle_index": self._cycle.cycle_index,
                "candidate_id": candidate_id,
                "status": status,
                "cycle_marks_ms": cycle_marks if cycle_marks is not None else dict(self._cycle.marks),
                "pipeline_ms": {k: round(float(v), 2) for k, v in pipeline_timings.items()},
                "total_cycle_ms": round(total_ms, 2),
            }
            if meta:
                record["meta"] = meta

        if self._file is not None:
            self._file.write(json.dumps(record) + "\n")
            self._file.flush()

    def record_cycle_summary(
        self,
        item_count: int = 0,
        processed_count: int = 0,
        rejected_count: int = 0,
        status: str = "idle",
    ) -> None:
        """Record a cycle-level summary."""
        with self._lock:
            total_ms = (time.monotonic() - self._cycle.started_at) * 1000
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "cycle_summary",
                "cycle_index": self._cycle.cycle_index,
                "item_count": item_count,
                "processed_count": processed_count,
                "rejected_count": rejected_count,
                "status": status,
                "cycle_marks_ms": dict(self._cycle.marks),
                "total_cycle_ms": round(total_ms, 2),
            }

        if self._file is not None:
            self._file.write(json.dumps(record) + "\n")
            self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


def analyze_latency(filepath: str | Path) -> None:
    """Analyze a latency.jsonl file and print a summary report."""
    path = Path(filepath)
    if not path.exists():
        print(f"No latency file found at {path}")
        return

    records = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    pipelines = [r for r in records if "candidate_id" in r]
    summaries = [r for r in records if r.get("type") == "cycle_summary"]

    if not pipelines:
        print("No pipeline records found.")
        return

    print(f"\n{'=' * 70}")
    print(f"  LATENCY ANALYSIS — {len(pipelines)} pipeline records, {len(summaries)} cycles")
    print(f"{'=' * 70}\n")

    stage_times: dict[str, list[float]] = defaultdict(list)
    for r in pipelines:
        for stage, ms in r.get("pipeline_ms", {}).items():
            stage_times[stage].append(ms)

    print("  Pipeline Stage Latency (ms):")
    print(f"  {'Stage':<15s} {'Avg':>8s} {'P50':>8s} {'P95':>8s} {'Max':>8s} {'Count':>8s}")
    print(f"  {'-' * 55}")
    for stage in sorted(stage_times.keys()):
        vals = sorted(stage_times[stage])
        avg = sum(vals) / len(vals)
        p50 = vals[len(vals) // 2]
        p95 = vals[int(len(vals) * 0.95)]
        mx = vals[-1]
        print(f"  {stage:<15s} {avg:>8.2f} {p50:>8.2f} {p95:>8.2f} {mx:>8.2f} {len(vals):>8d}")

    if summaries:
        print(f"\n  Cycle-Level Timings (ms):")
        cycle_totals = sorted(s.get("total_cycle_ms", 0) for s in summaries)
        avg = sum(cycle_totals) / len(cycle_totals)
        p50 = cycle_totals[len(cycle_totals) // 2]
        p95 = cycle_totals[int(len(cycle_totals) * 0.95)]
        print(f"  Total cycle:  avg={avg:.0f}ms  p50={p50:.0f}ms  p95={p95:.0f}ms")

    print()
