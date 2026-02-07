#!/bin/bash
# Daily Job Discovery — Run via cron to discover 150 new jobs/day
# Install: crontab -e → 0 9 * * * /path/to/scripts/run_daily_discovery.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Activate venv if present
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Random startup delay (0-10 min) to avoid detection patterns
DELAY=$((RANDOM % 600))
echo "$(date): Waiting ${DELAY}s before starting discovery..."
sleep $DELAY

echo "$(date): Starting daily job discovery (150 new jobs)..."
python3 scripts/job_discovery_supervisor.py --daily --batch-size 150 2>&1

echo "$(date): Daily discovery complete."
