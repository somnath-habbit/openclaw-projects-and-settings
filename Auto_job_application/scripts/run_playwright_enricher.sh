#!/bin/bash
# Helper script to run the Playwright enricher with .env file loaded
# Usage: scripts/run_playwright_enricher.sh [enricher arguments]
# Example: scripts/run_playwright_enricher.sh --limit 20 --debug

cd "$(dirname "$0")/.."

# Load environment variables from .env file
if [ -f .env ]; then
    set -a  # Export all variables
    source .env
    set +a
    echo "✓ Loaded .env file"
else
    echo "⚠️  Warning: .env file not found"
fi

# Run the enricher with any arguments passed to this script
python3 detached_flows/Playwright/enrich_jobs_batch.py "$@"
