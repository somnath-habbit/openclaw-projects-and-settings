#!/bin/bash
# Helper script to run the Playwright scraper with .env file loaded

# Load environment variables from .env file
set -a  # Export all variables
source .env
set +a

# Run the scraper with any arguments passed to this script
python3 detached_flows/Playwright/linkedin_scraper.py "$@"
