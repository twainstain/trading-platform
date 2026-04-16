# Trading Platform Refactor Status

> Current implementation status for turning `trading_platform` into a shared
> infrastructure library for both `ArbitrageTrader` and `PolymarketTrader`.

---

## Current Direction

The repository is now organized as a **flat `src/` layout** with a mix of
top-level modules and small packages.

Current public surface:

- `pipeline/`
- `risk/`
- `alerting/`
- `config.py`
- `data.py`
- `observability.py`
- `contracts.py`

Current import style:

```python
from pipeline import BasePipeline, PriorityQueue
from risk import RuleBasedPolicy, CircuitBreaker
from alerting import AlertDispatcher
from config import find_env_file
from data import TTLCache
from observability import MetricsCollector
from contracts import SubmissionRef, VerificationOutcome
```

This is different from the earlier namespaced-package proposal
(`trading_platform.pipeline`, `trading_platform.risk`, etc.). The repo is
currently aligned around the flat layout, so this document tracks that reality
rather than the older proposal.

---

## Goal

The goal remains the same:

- provide reusable shared infrastructure
- keep abstractions product-agnostic
- define a small and honest public API
- avoid product-specific payload assumptions

The library should not contain:

- DEX-specific models
- CLOB-specific payload formats
- product dashboards
- venue-specific persistence schemas

---

## Current Shape

Implemented source layout:

- `src/__init__.py`
- `src/contracts.py`
- `src/config.py`
- `src/data.py`
- `src/observability.py`
- `src/alerting/`
- `src/pipeline/`
- `src/risk/`

Design intent:

- keep single-file concerns as top-level modules
- keep multi-file concerns as packages
- avoid placeholder wrapper packages where they add no value

---

## Status Summary

### Completed

1. Flatten package structure into the current `src/` layout.
2. Add shared typed contracts in `src/contracts.py`.
3. Refactor `BasePipeline` to use `SubmissionRef` and `VerificationOutcome`.
4. Move `RiskVerdict` into shared contracts and update risk imports.
5. Update README and tests to match the current import style.
6. Reduce false surface area in README by not advertising placeholder
   `api` and `persistence` functionality.
7. Remove placeholder `api/` and `persistence/` packages.
8. Replace fixed-offset alert scheduling with real timezone support.
9. Upgrade the priority queue so push/pop are both `O(log n)`.

### Still Open

1. Add a few missing tests around import smoke coverage and any remaining edge
   cases we care about long-term.
2. Decide whether we want broader packaging/install smoke tests in CI.
3. Revisit namespacing later if the shared library becomes large enough for
   generic top-level module names to become a problem.

### Verified State

- Test suite passes.
- README matches the current flat import layout.
- Packaging includes top-level modules via `pyproject.toml`.

---

## Workstream 1: Package Layout

### Current Decision

We are currently using a flat layout rather than a namespaced
`trading_platform.*` package layout.

### Why

- the codebase is still small
- several concerns only need one file
- the flat layout reduces wrapper-module ceremony

### Tradeoff

Top-level names like `pipeline`, `risk`, and `config` are more generic and more
collision-prone than a namespaced package would be.

### Status

Accepted for now.

If the shared library grows or starts being installed broadly across multiple
repos, revisiting a namespaced package may still be worthwhile.

---

## Workstream 2: Shared Contracts

### Objective

Use typed, platform-neutral contracts instead of loose product-shaped payloads.

### Implemented

- `RiskVerdict`
- `SubmissionRef`
- `VerificationOutcome`

### Status

Complete.

This is one of the strongest improvements in the refactor because it keeps
shared semantics separate from product-specific execution payloads.

---

## Workstream 3: Base Pipeline

### Objective

Keep `BasePipeline` responsible only for orchestration.

### Implemented

The pipeline now works in terms of shared contracts instead of assuming product
fields like transaction hashes or order IDs.

### Status

Mostly complete.

### Remaining Watchouts

- Keep product adapters outside the shared package.
- Avoid letting product-specific metadata creep back into core hooks.

---

## Workstream 4: Risk Package

### Objective

Keep risk focused on the rule engine while shared verdict semantics live in
`contracts.py`.

### Implemented

- `RiskVerdict` lives in `contracts.py`
- `RiskRule` and `RuleBasedPolicy` remain in `risk/`
- risk imports now depend on shared contracts

### Status

Complete.

---

## Workstream 5: Alerting Timezones

### Implemented

`BaseAlerter` now uses a real timezone string API, for example:

```python
def __init__(..., daily_timezone: str = "UTC")
```

and use `zoneinfo.ZoneInfo`.

This removes the old fixed-offset behavior and makes daily scheduling DST-safe.

### Status

Complete.

---

## Workstream 6: Queue Semantics

### Implemented

The queue now uses dual heaps with lazy removal so it can:

- evict the lowest-priority item when full
- pop the highest-priority item in `O(log n)`
- preserve FIFO ordering for equal priorities

The default queue size is now `333`, which is a reasonable operational default
for the current shared use cases.

### Status

Complete.

---

## Workstream 7: Surface Area

### Objective

Advertise only what the library actually implements.

### Current Status

Improved.

The README now focuses on the real shared primitives, and the placeholder
`api/` and `persistence/` packages have been removed.

### Status

Complete.

---

## Workstream 8: Public API

### Objective

Keep a small explicit public surface.

### Current Public API

- `BasePipeline`
- `PipelineResult`
- `PriorityQueue`
- `RiskRule`
- `RuleBasedPolicy`
- `CircuitBreaker`
- `CircuitBreakerConfig`
- `RiskVerdict`
- `SubmissionRef`
- `VerificationOutcome`
- `AlertDispatcher`
- `BaseAlerter`
- `MetricsCollector`
- `TTLCache`
- `find_env_file`
- `load_env`
- `get_env`
- `require_env`

### Status

Good enough for the current layout.

The key thing now is to avoid expanding exports casually.

---

## Workstream 9: Tests

### Current Status

Tests are aligned with the current flat import layout and are passing.

### Still Worth Adding

- alert timezone tests
- queue ordering and complexity-behavior tests
- package/module import smoke tests

### Status

Mostly complete.

---

## Recommended Next Steps

1. Add import/install smoke coverage if we want stronger packaging confidence.
2. Do a final release-readiness pass on docs and public API if this is about to
   be consumed by other repos.
3. Revisit namespacing later only if the flat top-level modules become a real
   collision problem.

---

## Bottom Line

The refactor is in a solid place.

The repo now has:

- a consistent flat module/package layout
- shared typed contracts
- a more honest README
- fewer placeholder surfaces
- DST-safe alert scheduling
- a true `O(log n)` priority queue
- passing tests

The main remaining work is no longer structural package cleanup. It is about
release confidence and packaging polish.

Those are the areas that still determine whether this should be treated as a
stable long-term shared library.
