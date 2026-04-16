#!/bin/bash
# ============================================================
# Run the test bot locally — exercises the full platform pipeline
# with simulated data and produces latency.jsonl.
#
# Usage:
#   ./scripts/run_local.sh                   # default 20 iterations
#   ./scripts/run_local.sh --iterations 100  # custom iterations
#   ./scripts/run_local.sh --analyze         # run + latency analysis
#   ./scripts/run_local.sh --fast            # 100 iterations + analysis
#   ./scripts/run_local.sh --clean           # wipe logs/ and data/
#
# Output:
#   logs/latency.jsonl   — per-pipeline and per-scan timing data
#   logs/test_bot_*.log  — human-readable log
#   logs/test_bot_*.jsonl — structured JSON events
#   data/test_bot.db     — SQLite persistence
#
# Latency Analysis:
#   PYTHONPATH=src python3.11 -c \
#     "from observability.latency_tracker import analyze_latency; analyze_latency('logs/latency.jsonl')"
# ============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# --- Clean ---
if [ "${1:-}" = "--clean" ]; then
    rm -rf logs/ data/
    echo "Cleaned logs/ and data/"
    exit 0
fi

# --- Parse args ---
EXTRA_ARGS=()
ITERATIONS=""
ANALYZE=""

for arg in "$@"; do
    case "$arg" in
        --fast)
            ITERATIONS="100"
            ANALYZE="--analyze"
            ;;
        --analyze)
            ANALYZE="--analyze"
            ;;
        --iterations)
            ;; # next arg is the value, handled by passthrough
        *)
            EXTRA_ARGS+=("$arg")
            ;;
    esac
done

# Build the command.
CMD=(python3.11 -m scripts.run_test_bot)

if [ -n "$ITERATIONS" ]; then
    CMD+=(--iterations "$ITERATIONS")
fi

if [ -n "$ANALYZE" ]; then
    CMD+=($ANALYZE)
fi

# Pass through any extra args (--config, --iterations N, etc.).
CMD+=("${EXTRA_ARGS[@]}")

# --- Ensure dirs ---
mkdir -p logs data

# --- Run ---
echo "============================================================"
echo "  Trading Platform — Test Bot"
echo "============================================================"
echo "  Project: $PROJECT_DIR"
echo "  Python:  $(python3.11 --version 2>&1)"
echo "  Command: PYTHONPATH=src ${CMD[*]}"
echo "============================================================"
echo ""

PYTHONPATH=src "${CMD[@]}"
