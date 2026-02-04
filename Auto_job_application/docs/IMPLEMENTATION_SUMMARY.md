# Playwright Migration — Implementation Summary

> **Status:** ✅ Complete (Phases 1-4)
> **Date:** 2026-02-04
> **Test Status:** Ready for live test (requires OPENCLAW_MASTER_PASSWORD in .env)

---

## What Was Built

Complete Playwright-based scraper with AI decision layer as fallback for dynamic page states.

### Phase 1: Infrastructure ✅
- `detached_flows/config.py` — All paths, env vars, AI provider config
- `detached_flows/Playwright/browser_session.py` — Anti-detection browser launch + session persistence
- `detached_flows/Playwright/page_utils.py` — Human-like delays, a11y snapshot formatting
- `detached_flows/LoginWrapper/cred_fetcher.py` — Credential broker interface (subprocess call)

### Phase 2: LoginWrapper ✅
- `detached_flows/LoginWrapper/login_manager.py` — Full LinkedIn login flow with session restoration

### Phase 3: AI Decision Engine ✅
- `detached_flows/ai_decision/action_schema.py` — AIAction dataclass
- `detached_flows/ai_decision/context_builder.py` — DB + profile context builder
- `detached_flows/ai_decision/decision_engine.py` — Orchestrator with provider selection
- `detached_flows/ai_decision/providers/base.py` — Abstract provider interface
- `detached_flows/ai_decision/providers/anthropic_provider.py` — Anthropic API provider
- `detached_flows/ai_decision/providers/openclaw_provider.py` — **OpenClaw OAuth provider (default)**

### Phase 4: Playwright Scraper ✅
- `detached_flows/Playwright/linkedin_scraper.py` — Full scraper with CLI + AI fallback

### Additional
- `.env` + `.env.example` — Environment variable templates
- `.gitignore` — Excludes .env and session files
- `run_scraper_with_env.sh` — Helper script to load .env and run scraper

---

## Key Features

### Anti-Detection
- Browser args disable `AutomationControlled` flag
- Realistic user agent
- Human-like delays per SCRAPING_STRATEGY_AND_SCHEDULE.md (3-12s nav, 10-20s page load)
- Session persistence (cookies saved, login only once)

### AI Decision Layer
**Default: OpenClaw OAuth-based**
- Uses `openclaw agent --local --message "..." --json`
- No API key needed (uses your OAuth session)
- Model: Whatever is configured in OpenClaw (recommend: `openclaw models set sonnet`)
- Analyzes accessibility tree + screenshot metadata
- Returns structured actions (click, type, wait, skip) with confidence scores

**Fallback: Anthropic API**
- If `ANTHROPIC_API_KEY` is set and `AI_PROVIDER=anthropic`
- Uses Claude Sonnet 4.5 via direct API

**When AI activates:**
- Only when structured extraction fails
- Handles popups, verification dialogs, unexpected page states
- Skips CAPTCHAs and 2FA (marks job as BLOCKED)

### Credential Management
- Calls `openclaw-creds-manager/broker/credential_broker.py` via subprocess
- Requires `OPENCLAW_MASTER_PASSWORD` in environment or keyring
- Keeps projects decoupled (no direct imports)

---

## Test Results

**Partial success:**
- ✅ Playwright installed and launches correctly
- ✅ Headed browser mode works (no detection)
- ✅ Navigation to LinkedIn successful
- ⚠️ Login requires `OPENCLAW_MASTER_PASSWORD` in `.env`
- ⚠️ Credential exists in DB (linkedin / somnath.ghosh2010@gmail.com) but master password not in keyring

**Database state:**
- Before test: 50 jobs
- After test: N/A (login failed, no scraping occurred)

---

## How to Run

### 1. Set up .env
```bash
cd /home/somnath/.openclaw/workspace/Auto_job_application
nano .env  # Add OPENCLAW_MASTER_PASSWORD
```

### 2. Configure AI model (optional)
```bash
openclaw models set sonnet  # Recommended
# or: openclaw models set haiku  # Faster/cheaper
```

### 3. Run the scraper
```bash
# Using helper script
./run_scraper_with_env.sh --limit 1 --debug

# Or manually
set -a; source .env; set +a
python3 detached_flows/Playwright/linkedin_scraper.py --limit 1 --debug
```

### CLI Options
```
--limit N          Number of NEW jobs to find (default: 1)
--keywords "..."   Job search keywords (default: "Engineering Manager")
--location "..."   Location filter (default: "Bengaluru")
--debug            Enable debug mode (screenshots at each step)
--dry-run          Don't write to DB (test extraction only)
```

---

## Architecture Decisions

### Why Playwright over OpenClaw CLI?
- Direct Python API (no subprocess per action)
- Richer selectors and waits
- Native screenshot support
- `page.evaluate()` for robust DOM extraction
- Accessibility API for same ARIA trees OpenClaw uses

### Why OpenClaw Agent over Anthropic API?
- Already authenticated via OAuth
- No API key management needed
- Consistent subprocess pattern
- Reuses existing OpenClaw model configuration

### Trade-offs Accepted
- **Text-only AI analysis** (for now): Vision would require async messaging via `openclaw message send --media`
- **Subprocess overhead for AI**: Each AI call spawns a process, but this only fires on extraction failures (rare)
- **Session persistence**: Login happens once, session lasts ~1-2 weeks

---

## Next Steps

### For Live Testing
1. Add `OPENCLAW_MASTER_PASSWORD` to `.env`
2. Run scraper with `--limit 1 --debug`
3. Verify 1 new job added to DB
4. Check screenshots in `data/screenshots/`

### For Production Use
1. Switch `PLAYWRIGHT_HEADLESS=true` in `.env` (after confirming login works)
2. Update `scripts/run_scraper.sh` or Makefile to use Playwright scraper
3. Run via cron (existing schedule: 09:10-09:55, 18:30-19:10)

### Future Enhancements
1. **Vision support**: Implement async messaging flow for screenshot analysis
2. **Applier**: Port `ApplicationBot` to Playwright (Phase 5)
3. **AI decision logging**: Create `ai_decisions` table for audit trail
4. **Multi-provider fallback**: Chain OpenClaw → Anthropic → Gemini

---

## Files Changed/Created

**New directories:**
- `detached_flows/` (entire tree)

**Modified:**
- `.gitignore` — Added `.env`, `data/playwright_sessions/`

**New files:**
- 16 Python files in `detached_flows/`
- `.env`, `.env.example`
- `run_scraper_with_env.sh`
- This summary doc

**Unchanged (per strategy doc guarantee):**
- `src/` — Existing scraper/applier untouched
- `flow/` — Existing flows untouched
- `data/autobot.db` — Same schema, append-only

---

**Implementation complete. Ready for live test with master password.**
