#!/usr/bin/env bash
# Run the batch orchestrator (foreground or background).
#
# Usage:
#   ./scripts/run_batch_apply.sh                   # foreground, 200 jobs
#   ./scripts/run_batch_apply.sh --bg               # background, 200 jobs
#   ./scripts/run_batch_apply.sh --total 40 --bg    # background, 40 jobs
#   ./scripts/run_batch_apply.sh --dry-run           # dry run
#   ./scripts/run_batch_apply.sh --status            # check running job
#   ./scripts/run_batch_apply.sh --stop              # stop running job
#   ./scripts/run_batch_apply.sh --tail              # tail latest log

set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${DATA_DIR:-$BASE_DIR/data}"
LOG_DIR="$DATA_DIR/logs"
PID_FILE="$LOG_DIR/batch_orchestrator.pid"

export AUTO_JOB_APPLICATION_ROOT="$BASE_DIR"
export PYTHONPATH="${BASE_DIR}/..${PYTHONPATH:+:$PYTHONPATH}"

# Source .env if present
if [ -f "$BASE_DIR/.env" ]; then
    set -a
    source "$BASE_DIR/.env"
    set +a
fi

mkdir -p "$LOG_DIR"

# ── Helper functions ─────────────────────────────────────────────────────

_is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        rm -f "$PID_FILE"
    fi
    return 1
}

_status() {
    if _is_running; then
        local pid
        pid=$(cat "$PID_FILE")
        echo "Batch orchestrator is RUNNING (PID $pid)"
        # Show latest report
        local latest_report
        latest_report=$(ls -t "$DATA_DIR/batch_reports"/batch_report_*.json 2>/dev/null | head -1)
        if [ -n "$latest_report" ]; then
            echo ""
            echo "Latest report: $latest_report"
            python3 -c "
import json, sys
r = json.load(open('$latest_report'))
s = r.get('summary', {})
batches = len(r.get('batches', []))
print(f'  Batches completed: {batches}')
print(f'  Attempted: {s.get(\"total_attempted\", 0)}')
print(f'  Applied:   {s.get(\"total_applied\", 0)}')
print(f'  Failed:    {s.get(\"total_failed\", 0)}')
print(f'  Timed out: {s.get(\"total_timed_out\", 0)}')
"
        fi
    else
        echo "Batch orchestrator is NOT running"
    fi
}

_stop() {
    if _is_running; then
        local pid
        pid=$(cat "$PID_FILE")
        echo "Stopping batch orchestrator (PID $pid)..."
        kill "$pid"
        # Wait up to 30s for graceful shutdown
        for i in $(seq 1 30); do
            if ! kill -0 "$pid" 2>/dev/null; then
                echo "Stopped."
                rm -f "$PID_FILE"
                return 0
            fi
            sleep 1
        done
        echo "Force killing..."
        kill -9 "$pid" 2>/dev/null || true
        rm -f "$PID_FILE"
    else
        echo "Batch orchestrator is not running"
    fi
}

_tail() {
    local latest_log
    latest_log=$(ls -t "$LOG_DIR"/batch_apply_*.log 2>/dev/null | head -1)
    if [ -n "$latest_log" ]; then
        echo "Tailing: $latest_log"
        tail -f "$latest_log"
    else
        echo "No batch log files found in $LOG_DIR"
    fi
}

# ── Parse special commands ───────────────────────────────────────────────

case "${1:-}" in
    --status)
        _status
        exit 0
        ;;
    --stop)
        _stop
        exit 0
        ;;
    --tail)
        _tail
        exit 0
        ;;
esac

# ── Parse args ───────────────────────────────────────────────────────────

RUN_BG=false
PYTHON_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bg|--background)
            RUN_BG=true
            shift
            ;;
        *)
            PYTHON_ARGS+=("$1")
            shift
            ;;
    esac
done

# Check if already running
if _is_running; then
    pid=$(cat "$PID_FILE")
    echo "ERROR: Batch orchestrator already running (PID $pid)"
    echo "Use --stop to kill it, or --status to check progress"
    exit 1
fi

# ── Run ──────────────────────────────────────────────────────────────────

if [ "$RUN_BG" = true ]; then
    LOG_FILE="$LOG_DIR/batch_apply_$(date +%Y%m%d_%H%M%S).log"
    echo "Starting batch orchestrator in background..."
    echo "  Log: $LOG_FILE"
    echo "  Check status: make batch-status"
    echo "  Tail log:     make batch-tail"
    echo "  Stop:         make batch-stop"

    nohup python3 "$BASE_DIR/detached_flows/Playwright/batch_orchestrator.py" \
        "${PYTHON_ARGS[@]}" \
        >> "$LOG_FILE" 2>&1 &

    echo $! > "$PID_FILE"
    echo "  PID: $(cat "$PID_FILE")"
else
    exec python3 "$BASE_DIR/detached_flows/Playwright/batch_orchestrator.py" \
        "${PYTHON_ARGS[@]}"
fi
