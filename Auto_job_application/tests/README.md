# Test Scripts

Playwright-based test scripts for the Auto Job Application system.

## Prerequisites

- Active LinkedIn session (logged in via browser)
- Environment variables loaded from `.env`
- Playwright installed (`pip install playwright && playwright install chromium`)

## Test Scripts

### 1. Scraper Test (`test_scraper_skip_login.py`)

Tests the Playwright job scraper.

**What it does:**
- Scrapes LinkedIn job listings
- Extracts basic job info (title, company, external_id)
- Saves jobs to database
- Takes debug screenshots

**Run:**
```bash
make test-scraper
# or
python3 tests/test_scraper_skip_login.py
```

**Configuration:**
- Limit: 5 jobs (hardcoded in script)
- Keywords: "Engineering Manager"
- Location: "Bengaluru"
- Debug mode: ON (screenshots saved to `data/screenshots/`)

### 2. Enrichment Test (`test_enrichment.py`)

Tests the Playwright job enricher.

**What it does:**
- Visits individual job pages
- Extracts full job details (description, company info, compensation, work mode, apply type)
- Shows extraction results (doesn't update database)
- Takes debug screenshots

**Run:**
```bash
make test-enrichment
# or
python3 tests/test_enrichment.py
```

**Configuration:**
- Limit: 3 jobs (from database where `about_job IS NULL`)
- Debug mode: ON (screenshots saved to `data/screenshots/`)

### 3. Run All Tests

```bash
make test-all
```

## Test Environment

Both tests use **skip-login mode** which:
- Assumes you're already logged into LinkedIn
- Navigates to linkedin.com to verify session
- Skips credential broker authentication

**Important:** Make sure to log into LinkedIn in a browser before running tests, or the session will be active from previous scraper/enrichment runs.

## Debugging

Debug screenshots are saved to:
```
data/screenshots/
├── pw_search_0.png           # Scraper: search page at offset 0
├── pw_search_25.png          # Scraper: search page at offset 25
├── enrich_<job_id>_initial.png    # Enricher: initial page load
├── enrich_<job_id>_expanded.png   # Enricher: after expanding sections
```

## Makefile Integration

The tests are integrated into the project Makefile:

```bash
make test-scraper      # Test scraping
make test-enrichment   # Test enrichment
make test-all          # Run both tests
make help              # Show all available commands
```

## Production Scripts

For production use (with full login flow):

**Scraping:**
```bash
python3 detached_flows/Playwright/linkedin_scraper.py --limit 10 --keywords "Engineering Manager" --location "Bengaluru"
```

**Enrichment:**
```bash
python3 detached_flows/Playwright/enrich_jobs_batch.py --limit 20 --debug
```

These scripts use the full login flow via credential broker and are intended for scheduled/automated runs.
