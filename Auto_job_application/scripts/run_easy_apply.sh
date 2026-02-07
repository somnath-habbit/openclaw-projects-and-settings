#!/bin/bash
# Easy Apply Script
# Applies to READY_TO_APPLY jobs using LinkedIn Easy Apply
#
# Usage:
#   ./scripts/run_easy_apply.sh [OPTIONS]
#
# Options:
#   --limit N       Max applications (default: 5)
#   --dry-run       Preview without submitting
#   --debug         Enable debug screenshots
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

# Default values
LIMIT=5
DRY_RUN=""
DEBUG=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --dry-run|-n)
            DRY_RUN="--dry-run"
            shift
            ;;
        --debug)
            DEBUG="--debug"
            shift
            ;;
        --help|-h)
            echo "Easy Apply Script"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --limit N       Max applications to submit (default: 5)"
            echo "  --dry-run, -n   Preview without actually submitting"
            echo "  --debug         Enable debug screenshots"
            echo "  --help, -h      Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run the Easy Apply batch script
echo "📝 Starting Easy Apply..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

python3 -c "
import asyncio
import sys
sys.path.insert(0, '.')

from detached_flows.Playwright.apply_jobs_batch import apply_jobs_batch

asyncio.run(apply_jobs_batch(
    limit=${LIMIT},
    dry_run='${DRY_RUN}' != '',
    debug='${DEBUG}' != ''
))
"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Easy Apply complete"
