#!/bin/bash
# AI Job Screening Script
# Runs AI-powered fitness scoring on enriched jobs
#
# Usage:
#   ./scripts/run_ai_screening.sh [OPTIONS]
#
# Options:
#   --limit N       Max jobs to screen (default: 20)
#   --threshold N   Minimum score for READY_TO_APPLY (default: 0.6)
#   --dry-run       Preview without updating database
#   --verbose       Show detailed reasoning
#   --help          Show this help

set -e

# Resolve script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

# Load environment
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run the batch screening script
echo "🤖 Starting AI Job Screening..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

python3 detached_flows/ai_decision/screen_jobs_batch.py "$@"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ AI Screening complete"
