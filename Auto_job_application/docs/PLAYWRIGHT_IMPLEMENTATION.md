# Playwright Implementation - Complete Documentation

> **Implementation Date:** 2026-02-04
> **Status:** Phase 1-4 Complete
> **Architecture:** Direct Playwright Python API (replacing OpenClaw CLI subprocess calls)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Implementation Details](#implementation-details)
4. [Use Cases](#use-cases)
5. [Developer Guide](#developer-guide)
6. [Testing](#testing)
7. [Production Deployment](#production-deployment)
8. [Troubleshooting](#troubleshooting)

---

## Overview

### What Was Built

Complete Playwright-based job scraping and enrichment system with AI decision layer for handling dynamic page states.

**Key Components:**
- **Job Scraper** - Scrapes LinkedIn job listings from search results
- **Job Enricher** - Visits individual job pages to extract full details
- **AI Decision Engine** - Handles popups, verification dialogs, and dynamic forms
- **Multi-Provider Support** - OpenClaw, HuggingFace, Ollama, Anthropic

### Why Playwright?

**Before (OpenClaw CLI):**
```python
# Subprocess overhead per action
result = subprocess.run(["openclaw", "browser", "open", url])
result = subprocess.run(["openclaw", "browser", "click", "button"])
result = subprocess.run(["openclaw", "browser", "snapshot"])
```

**After (Playwright):**
```python
# Direct Python API
await page.goto(url)
await page.click("button")
content = await page.evaluate("() => document.body.innerText")
```

**Benefits:**
- ⚡ 10x faster (no subprocess overhead)
- 🎯 More reliable (direct DOM access)
- 🔧 Better debugging (Python stack traces)
- 📸 Native screenshot support
- 🔄 Consistent architecture

---

## Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    LinkedIn Automation                       │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Scraper    │     │  Enricher    │     │   Applier    │
│  (Phase 4)   │────▶│  (Phase 4)   │────▶│  (Future)    │
└──────────────┘     └──────────────┘     └──────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Browser Session  │
                    │  - Anti-detect   │
                    │  - Session store │
                    │  - Login mgmt    │
                    └──────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ LoginWrapper │     │ AI Decision  │     │  Database    │
│  (Phase 2)   │     │   (Phase 3)  │     │   (SQLite)   │
└──────────────┘     └──────────────┘     └──────────────┘
        │                     │
        ▼                     ▼
┌──────────────┐     ┌──────────────────────────────┐
│ Cred Broker  │     │   AI Providers:              │
│  (Encrypted) │     │   - OpenClaw (OAuth)         │
└──────────────┘     │   - HuggingFace (API)        │
                     │   - Ollama (Local)           │
                     │   - Anthropic (API)          │
                     └──────────────────────────────┘
```

### File Structure

```
detached_flows/
├── config.py                          # Central configuration
├── Playwright/
│   ├── browser_session.py            # Browser launcher with anti-detection
│   ├── page_utils.py                 # Human-like delays, utilities
│   ├── linkedin_scraper.py           # Main scraper (Phase 4)
│   ├── job_enricher.py               # Job detail extractor (Phase 4)
│   └── enrich_jobs_batch.py          # Batch enrichment script
├── LoginWrapper/
│   ├── login_manager.py              # LinkedIn login flow (Phase 2)
│   └── cred_fetcher.py               # Credential broker interface (Phase 1)
└── ai_decision/
    ├── decision_engine.py            # AI orchestrator (Phase 3)
    ├── action_schema.py              # AIAction dataclass
    ├── context_builder.py            # Context for AI decisions
    └── providers/
        ├── base.py                   # Abstract provider
        ├── openclaw_provider.py      # OpenClaw OAuth (default)
        ├── anthropic_provider.py     # Anthropic API
        ├── huggingface_provider.py   # HuggingFace Inference API
        └── ollama_provider.py        # Local Ollama models
```

---

## Implementation Details

### Phase 1: Infrastructure

**Files Created:**
- `detached_flows/config.py` - All configuration in one place
- `detached_flows/Playwright/browser_session.py` - Anti-detection browser setup
- `detached_flows/Playwright/page_utils.py` - Human-like delays
- `detached_flows/LoginWrapper/cred_fetcher.py` - Credential broker interface

**Key Features:**
```python
# Anti-detection browser arguments
ANTI_DETECTION_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=TranslateUI",
    "--no-sandbox",
    "--lang=en-US,en",
]

# Realistic user agent
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Human-like delays
async def nav_delay():
    await human_delay(3, 12)  # 3-12 seconds for navigation

async def typing_delay():
    await human_delay(2, 6)   # 2-6 seconds for typing
```

**Session Persistence:**
```python
# Save session after login
await context.storage_state(path=session_file)

# Restore session on next run
context = await browser.new_context(storage_state=session_file)
```

---

### Phase 2: Login Wrapper

**File:** `detached_flows/LoginWrapper/login_manager.py`

**Flow:**
1. Check if already logged in (detect feed/jobs page)
2. If not logged in:
   - Fetch credentials via broker
   - Navigate to login page
   - Enter email and password
   - Handle verification if needed
   - Save session state

**Code Example:**
```python
async def ensure_logged_in(session: BrowserSession) -> bool:
    """Ensure user is logged into LinkedIn."""

    # Check current page
    await session.page.goto("https://www.linkedin.com", timeout=30000)
    await asyncio.sleep(3)

    current_url = session.page.url
    if "/feed" in current_url or "/jobs" in current_url:
        logger.info("Session valid — already on feed/jobs")
        return True

    # Login flow
    logger.info("Not logged in — starting login flow")
    email = get_linkedin_email()
    password = get_linkedin_password(email)

    # Fill form and submit
    await session.page.fill('input[name="session_key"]', email)
    await session.page.fill('input[name="session_password"]', password)
    await session.page.click('button[type="submit"]')

    # Wait for navigation
    await session.page.wait_for_url("**/feed/**", timeout=30000)

    # Save session
    await session.save_session()
    return True
```

---

### Phase 3: AI Decision Engine

**Purpose:** Handle dynamic page states (popups, verification, unexpected forms)

**Architecture:**
```python
class DecisionEngine:
    def __init__(self):
        self.provider = _get_provider()  # Auto-selects based on config

    async def decide(self, page, goal: str, job_id: int = None) -> AIAction:
        # 1. Take screenshot
        screenshot = await page.screenshot()

        # 2. Get accessibility tree
        tree = await page.accessibility.snapshot()

        # 3. Build context (user profile + job details)
        context = build_context(goal, job_id)

        # 4. Ask AI
        raw = await self.provider.analyze(screenshot, tree, context, goal)

        # 5. Return structured action
        return AIAction(
            action=raw["action"],      # click | type | wait | skip
            target=raw["target"],      # Element description
            confidence=raw["confidence"], # 0.0 - 1.0
            reason=raw["reason"]       # Explanation
        )
```

**Providers:**

| Provider | API Key? | Cost | Model | Use Case |
|----------|----------|------|-------|----------|
| OpenClaw | No (OAuth) | Included | Sonnet/Haiku | Default, no setup |
| HuggingFace | Yes | $2/month | Qwen2.5-72B | Cost-effective |
| Ollama | No | Free | Phi-3-mini | Local, privacy |
| Anthropic | Yes | Pay-per-use | Claude | High quality |

**Configuration:**
```bash
# .env
AI_PROVIDER=openclaw  # openclaw | huggingface | anthropic | ollama

# OpenClaw model selection
openclaw models set sonnet  # or haiku for faster/cheaper
```

---

### Phase 4: Scraper & Enricher

#### Job Scraper

**File:** `detached_flows/Playwright/linkedin_scraper.py`

**What it does:**
1. Navigates to LinkedIn job search
2. Extracts job listings from search results
3. Saves to database with status NEW
4. Takes debug screenshots

**Extraction Method:**
```python
# Uses page.evaluate() for robust DOM access
jobs = await page.evaluate("""
    () => {
        const jobCards = document.querySelectorAll('.job-card-container');
        return Array.from(jobCards).map(card => ({
            external_id: card.dataset.jobId,
            title: card.querySelector('.job-card-list__title')?.innerText,
            company: card.querySelector('.job-card-container__company-name')?.innerText,
            location: card.querySelector('.job-card-container__metadata-item')?.innerText,
            job_url: card.querySelector('a')?.href
        }));
    }
""")
```

**CLI Usage:**
```bash
python3 detached_flows/Playwright/linkedin_scraper.py \
    --limit 10 \
    --keywords "Engineering Manager" \
    --location "Bengaluru" \
    --debug
```

#### Job Enricher

**File:** `detached_flows/Playwright/job_enricher.py`

**What it does:**
1. Visits individual job page
2. Scrolls to load lazy content
3. Clicks "Show more" buttons
4. Extracts full job details
5. Updates database

**Extracted Data:**
- `about_job` - Full job description
- `about_company` - Company information
- `compensation` - Salary/pay (if listed)
- `work_mode` - Remote/Hybrid/On-site
- `apply_type` - Easy Apply | Company Site | Apply

**Extraction Strategy:**
```javascript
function extractSection(headings) {
    // 1. Find heading (h2, h3)
    const matchedElement = findHeading(headings);

    // 2. Get parent container
    const container = matchedElement.closest('.jobs-description__content');

    // 3. Extract all text
    return container.innerText;
}
```

**Quality Validation:**
```python
def _assess_quality(details):
    # Must have apply_type
    if not details.get("apply_type"):
        return True, "apply_type_missing"

    # Description must be > 100 chars
    if len(details.get("about_job", "")) < 100:
        return True, "about_job_too_short"

    return False, None
```

---

## Use Cases

### Use Case 1: Daily Job Scraping

**Goal:** Automatically find new Engineering Manager jobs in Bengaluru every day

**Workflow:**
```bash
# Morning: Scrape new jobs
make playwright-scrape
# → Finds 10 new jobs, saves to database

# Afternoon: Enrich job details
make playwright-enrich
# → Visits each job page, extracts full descriptions
```

**Cron Schedule:**
```bash
# Run at 9:10 AM and 6:30 PM daily
10 9 * * * cd /path/to/Auto_job_application && make playwright-scrape
30 18 * * * cd /path/to/Auto_job_application && make playwright-enrich
```

---

### Use Case 2: Manual Job Search with Custom Criteria

**Goal:** Find 50 Senior Engineer jobs in Remote locations

**Command:**
```bash
scripts/run_playwright_scraper.sh \
    --limit 50 \
    --keywords "Senior Software Engineer" \
    --location "Remote" \
    --debug
```

**Output:**
- 50 jobs saved to `data/autobot.db`
- Debug screenshots in `data/screenshots/`
- Logs show progress

---

### Use Case 3: Testing New Features

**Goal:** Test scraper on 5 jobs without affecting production database

**Command:**
```bash
# Run test with skip-login (assumes active session)
make test-scraper

# Or test enrichment
make test-enrichment
```

**Benefits:**
- No login required (reuses session)
- Smaller dataset (faster)
- Debug mode enabled
- Won't interfere with production runs

---

### Use Case 4: Handling LinkedIn Popup/Verification

**Scenario:** LinkedIn shows "Verify you're human" popup

**AI Decision Flow:**
1. Scraper encounters unexpected page state
2. Calls `decision_engine.decide(page, goal="Continue job scraping")`
3. AI analyzes page:
   ```
   Screenshot: [Shows verification popup]
   Accessibility: "Verify you're human" button visible
   Goal: Continue job scraping
   ```
4. AI returns:
   ```python
   AIAction(
       action="skip",
       reason="CAPTCHA detected - cannot proceed automatically",
       confidence=0.95
   )
   ```
5. Scraper marks job as BLOCKED and moves on

---

## Developer Guide

### Getting Started

**1. Install Dependencies:**
```bash
pip install playwright python-dotenv
playwright install chromium
```

**2. Configure Environment:**
```bash
cp .env.example .env
nano .env  # Add your settings
```

**Required Settings:**
```bash
OPENCLAW_MASTER_PASSWORD=your-password-here
LINKEDIN_EMAIL=your-email@example.com
PLAYWRIGHT_HEADLESS=false  # Use true for production
AI_PROVIDER=openclaw
```

**3. Test the Setup:**
```bash
make test-scraper
```

---

### Adding a New Feature

**Example: Add job salary extraction**

**1. Update Enricher:**
```python
# In job_enricher.py, add to _extract_job_details()
def extractCompensation() {
    const salaryPatterns = [
        /\$\s*([\d,]+)\s*-\s*\$\s*([\d,]+)\s*\/\s*(year|yr)/i,
        /([\\d,]+)\s*LPA/i,  # Indian Lakhs Per Annum
    ];

    for (const pattern of salaryPatterns) {
        const match = document.body.innerText.match(pattern);
        if (match) return match[0];
    }
    return null;
}
```

**2. Update Database Schema:**
```sql
-- Check if column exists
SELECT compensation FROM jobs LIMIT 1;

-- If not, add it
ALTER TABLE jobs ADD COLUMN compensation TEXT;
```

**3. Test:**
```bash
# Reset a job for testing
sqlite3 data/autobot.db "UPDATE jobs SET about_job = NULL WHERE external_id = '123456';"

# Run enrichment
python3 tests/test_enrichment.py

# Verify
sqlite3 data/autobot.db "SELECT external_id, compensation FROM jobs WHERE external_id = '123456';"
```

---

### Debugging Tips

**1. Enable Debug Mode:**
```python
scraper = PlaywrightScraper(debug=True)
# or
enricher = JobEnricher(debug=True)
```

**2. Check Screenshots:**
```bash
ls -lh data/screenshots/
eog data/screenshots/enrich_4367707125_expanded.png  # View image
```

**3. Inspect Database:**
```bash
sqlite3 data/autobot.db
.tables
.schema jobs
SELECT * FROM jobs WHERE status = 'NEW' LIMIT 5;
.exit
```

**4. Check Logs:**
```bash
# Scraper logs
grep "PlaywrightScraper" logs/scraper.log

# Enrichment logs
grep "JobEnricher" logs/enrichment.log
```

**5. Test Extraction Locally:**
```python
# Python REPL
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://www.linkedin.com/jobs/view/123456")

    # Test extraction
    result = page.evaluate("""
        () => document.querySelector('.jobs-description__content').innerText
    """)
    print(len(result), result[:200])
```

---

### Common Patterns

**Pattern 1: Safe DOM Queries**
```python
# Bad - will throw if element not found
title = await page.query_selector('.job-title').inner_text()

# Good - returns None if not found
title_element = await page.query_selector('.job-title')
title = await title_element.inner_text() if title_element else "Unknown"

# Better - use evaluate for robust extraction
title = await page.evaluate("""
    () => document.querySelector('.job-title')?.innerText || 'Unknown'
""")
```

**Pattern 2: Waiting for Dynamic Content**
```python
# Bad - fixed delay
await asyncio.sleep(5)

# Good - wait for specific element
await page.wait_for_selector('.job-description', timeout=10000)

# Better - wait for network idle
await page.goto(url, wait_until='networkidle')
```

**Pattern 3: Error Handling**
```python
try:
    await page.click('.apply-button', timeout=5000)
except TimeoutError:
    logger.warning("Apply button not found - job may not be available")
    return AIAction(action="skip", reason="Apply button not found")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    return AIAction(action="skip", reason=f"Error: {e}")
```

---

## Testing

### Test Structure

```
tests/
├── README.md                    # Test documentation
├── test_scraper_skip_login.py  # Scraper test (assumes active session)
└── test_enrichment.py          # Enricher test (assumes active session)
```

### Running Tests

**All Tests:**
```bash
make test-all
```

**Individual Tests:**
```bash
make test-scraper      # Test scraping
make test-enrichment   # Test enrichment
```

**Manual Testing:**
```bash
# Test scraper with custom args
python3 detached_flows/Playwright/linkedin_scraper.py --limit 1 --debug

# Test enricher with custom args
python3 detached_flows/Playwright/enrich_jobs_batch.py --limit 1 --debug
```

### Test Results

**Successful Scraper Test:**
```
Testing Playwright Scraper (Login Check DISABLED)
============================================================

⚠️  [MOCK] Skipping login check, assuming active session...
✓ Navigated to LinkedIn successfully

============================================================
Test Results
============================================================
New jobs found: 5
  - [4362094736] Delivery Manager- Design Verification
  - [4354953488] Engineering Manager
  - [4344362817] Senior Manager Engineering - Full Stack
  - [4365949799] Vice President - Electrolyser Stack Engineering
  - [4352585545] Director, Engineering

Check data/screenshots/ for debug screenshots
============================================================
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] Add `OPENCLAW_MASTER_PASSWORD` to `.env`
- [ ] Test full login flow (not skip-login)
- [ ] Set `PLAYWRIGHT_HEADLESS=true` in `.env`
- [ ] Test scraper: `make playwright-scrape`
- [ ] Test enrichment: `make playwright-enrich`
- [ ] Verify database writes correctly
- [ ] Check logs for errors
- [ ] Set up monitoring (optional)

### Deployment Steps

**1. Configure Production Settings:**
```bash
# .env
PLAYWRIGHT_HEADLESS=true  # Run browser in background
AI_PROVIDER=ollama        # Or huggingface for cost-effective API
OLLAMA_MODEL=phi3:mini    # If using Ollama
```

**2. Test Production Run:**
```bash
# Scrape 10 jobs
make playwright-scrape

# Enrich all unenriched jobs
make playwright-enrich
```

**3. Set Up Cron Jobs:**
```bash
# Install cron schedule
make cron-install

# Verify
make cron-list
```

**4. Monitor First Runs:**
```bash
# Check logs
tail -f data/logs/scraper_$(date +%Y-%m-%d).log

# Check database
sqlite3 data/autobot.db "SELECT COUNT(*) FROM jobs WHERE status = 'NEW';"
```

---

### Production Monitoring

**Key Metrics:**
```bash
# Jobs scraped today
sqlite3 data/autobot.db "SELECT COUNT(*) FROM jobs WHERE date(discovered_at) = date('now');"

# Enrichment success rate
sqlite3 data/autobot.db "SELECT
    COUNT(*) as total,
    SUM(CASE WHEN enrich_status = 'ENRICHED' THEN 1 ELSE 0 END) as enriched
FROM jobs WHERE about_job IS NOT NULL;"

# Application success rate (future)
sqlite3 data/autobot.db "SELECT status, COUNT(*) FROM jobs GROUP BY status;"
```

**Log Analysis:**
```bash
# Errors in last 24 hours
grep -i error data/logs/*.log | grep "$(date +%Y-%m-%d)"

# AI decision frequency
grep "AI decision" data/logs/*.log | wc -l
```

---

## Troubleshooting

### Issue 1: "Session expired" errors

**Symptom:** Scraper redirects to login page even though logged in

**Cause:** Session cookies expired (typically after 1-2 weeks)

**Fix:**
```bash
# Delete old session
rm data/playwright_sessions/linkedin_session.json

# Run scraper with full login
make playwright-scrape
```

---

### Issue 2: Job descriptions incomplete (< 100 chars)

**Symptom:** Enrichment completes but `about_job` field has very short text

**Cause:** JavaScript extraction not finding correct container

**Debug:**
```bash
# Check screenshots
ls data/screenshots/enrich_*_expanded.png

# View screenshot
eog data/screenshots/enrich_4367707125_expanded.png

# Check database
sqlite3 data/autobot.db "SELECT LENGTH(about_job), about_job FROM jobs WHERE external_id = '4367707125';"
```

**Fix:** Improve extraction selectors (see TODO #1)

---

### Issue 3: AI decision engine timeout

**Symptom:** `OpenClaw provider not available: Command '['openclaw', 'models', 'status'] timed out`

**Cause:** OpenClaw CLI slow to respond

**Fix:** Switch to different AI provider
```bash
# In .env
AI_PROVIDER=ollama  # or huggingface

# Restart scraper
make playwright-scrape
```

---

### Issue 4: LinkedIn CAPTCHA/Verification

**Symptom:** AI returns `action="skip", reason="CAPTCHA detected"`

**Cause:** LinkedIn rate limiting or bot detection

**Fix:**
```bash
# Increase delays in config.py
async def nav_delay():
    await human_delay(5, 15)  # Increased from 3-12

# Run fewer jobs per session
make playwright-scrape --limit 5  # Instead of 10
```

---

### Issue 5: Database locked

**Symptom:** `sqlite3.OperationalError: database is locked`

**Cause:** Multiple processes accessing database simultaneously

**Fix:**
```bash
# Check for running processes
ps aux | grep linkedin_scraper
ps aux | grep enrich_jobs_batch

# Kill if needed
pkill -f linkedin_scraper
```

---

## Future Enhancements

See [TODO.md](../TODO.md) for complete list.

**High Priority:**
- Fix enrichment extraction quality
- Build AI job screening system
- Test application flow

**Medium Priority:**
- Build Playwright application bot
- Set up cron automation
- Add monitoring dashboard

**Low Priority:**
- Fine-tune small language model for AI decisions
- Add more AI providers
- Build admin UI enhancements

---

## References

- [Playwright Python Docs](https://playwright.dev/python/docs/intro)
- [TODO.md](../TODO.md) - Task tracking
- [AI_PROVIDER_ALTERNATIVES.md](AI_PROVIDER_ALTERNATIVES.md) - AI provider options
- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - Initial implementation summary
- [tests/README.md](../tests/README.md) - Test documentation

---

**Last Updated:** 2026-02-04
**Maintained By:** Auto Job Application Team
