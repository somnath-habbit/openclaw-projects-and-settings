#!/bin/bash
# Helper script to run the Playwright scraper with .env file loaded
# Usage: scripts/run_playwright_scraper.sh [scraper arguments]
# Example: scripts/run_playwright_scraper.sh --limit 10 --keywords "Engineering Manager"

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

# Run the scraper with any arguments passed to this script
python3 detached_flows/Playwright/linkedin_scraper.py "$@"
