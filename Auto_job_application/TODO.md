# Auto Job Application - TODO List

> **Last Updated:** 2026-02-04 21:55
> **Status:** Enrichment extraction FIXED ✅ | Batch enrichment COMPLETED ✅ | 16 jobs ready to apply!

---

## 🔴 HIGH PRIORITY

### 1. Fix Job Enrichment Extraction Quality ✅
**Status:** COMPLETED (2026-02-04)
**Issue:** Job descriptions only extracting first ~100-200 characters
**Impact:** Cannot properly screen/filter jobs without full descriptions

**Sub-tasks:**
- [x] Debug current JavaScript extraction logic
  - [x] Inspect LinkedIn job page DOM structure
  - [x] Identify correct container selectors for full description
  - [x] Test different extraction strategies
- [x] Improve `extractSection()` function in `detached_flows/Playwright/job_enricher.py`
  - [x] Try direct selector: `.jobs-description__content`
  - [x] Handle lazy-loaded content (wait for load)
  - [x] Extract all paragraph/div children, not just siblings
  - [x] Implemented 3-tier extraction strategy (direct → heading-based → largest block)
- [x] Test on 5-10 jobs and verify full descriptions (>500 chars)
  - [x] Created TDD tests: `tests/test_enrichment_extraction.py` (7/7 passing)
  - [x] All tests passing with 500-3000+ char descriptions
- [x] Handle edge cases (closed jobs, already applied)
  - [x] Created `tests/test_edge_cases.py` (7/7 passing)
  - [x] Integrated detection into enricher
  - [x] Status tracking: CLOSED, ALREADY_APPLIED
- [x] Made test job URLs configurable via `tests/conftest.py`
  - [x] Override via: `--job-urls` or `TEST_JOB_URLS` env var
- [x] Run batch enrichment on 50 jobs (COMPLETED ✅)
  - [x] Command: `./scripts/run_playwright_enricher.sh --limit 50`
  - [x] Results: 16 READY_TO_APPLY, 31 SKIPPED, 2 NEEDS_ENRICH
  - [x] Duration: ~23 minutes (30s/job average)
  - [x] Success rate: 96% (48/50 successfully enriched)

**Files:**
- `detached_flows/Playwright/job_enricher.py` (fixed extraction + edge cases)
- `tests/test_enrichment_extraction.py` (TDD tests)
- `tests/test_edge_cases.py` (edge case tests)
- `tests/conftest.py` (configurable fixtures)
- `tests/README.md` (documentation)
- `docs/TDD_APPROACH.md` (methodology)
- `docs/TDD_SUCCESS_SUMMARY.md` (results)

---

### 2. Build AI Job Screening System
**Status:** Not Started
**Dependency:** Requires #1 (full job descriptions)
**Purpose:** Filter jobs based on profile match before applying

**Sub-tasks:**
- [ ] Create AI screening module
  - [ ] File: `detached_flows/ai_decision/job_screener.py`
  - [ ] Load user profile from `data/user_profile.json`
  - [ ] Load job description from database
  - [ ] Send to AI provider with screening prompt
- [ ] Implement fit score calculation
  - [ ] Prompt design: "Rate this job match for this candidate (0.0-1.0)"
  - [ ] Extract score + reasoning from AI response
  - [ ] Update `fit_score` and `fit_reasoning` in database
- [ ] Add screening to enrichment pipeline
  - [ ] After enrichment, call screener
  - [ ] Skip jobs with score < 0.6
  - [ ] Update job status based on score
- [ ] Create test script: `tests/test_ai_screening.py`
- [ ] Document in `docs/AI_SCREENING.md`

**AI Provider Options:**
- OpenClaw (default, OAuth-based)
- HuggingFace (Qwen2.5-72B, $2/month)
- Ollama (Phi-3-mini, local, free)

**Database Schema:**
- `fit_score` (REAL) - already exists
- `fit_reasoning` (TEXT) - already exists

---

### 3. Test Application Flow
**Status:** Not Started
**Dependency:** Requires #1 and #2 (enriched + screened jobs)
**Risk:** Existing `ApplicationBot` uses OpenClaw CLI (may need Playwright version)

**Sub-tasks:**
- [ ] Review existing ApplicationBot code
  - [ ] File: `src/tools/linkedin_tools.py` (ApplicationBot class)
  - [ ] Understand multi-step form handling
  - [ ] Identify potential issues
- [ ] Test on 1 READY_TO_APPLY job
  - [ ] Run: `python3 -m Auto_job_application.flow.auto_apply_batch --limit 1`
  - [ ] Monitor for errors (CAPTCHA, 2FA, form changes)
  - [ ] Verify job status updates to APPLIED
- [ ] Fix any issues found
- [ ] Document application success rate

**Potential Issues:**
- LinkedIn form changes
- CAPTCHA/2FA triggers
- Session expiration during application
- Resume upload failures

---

## 🟡 MEDIUM PRIORITY

### 4. Production Readiness - Full Login Flow
**Status:** Partial (skip-login works)
**Blocker:** Credential broker decryption issue (sub-agent investigating)

**Sub-tasks:**
- [ ] Add `OPENCLAW_MASTER_PASSWORD` to `.env`
- [ ] Test login flow without skip-login
  - [ ] Run: `make playwright-scrape` (should auto-login)
  - [ ] Verify credential fetch works
  - [ ] Check session persistence
- [ ] Fix any login issues
- [ ] Test session restoration after expiry
- [ ] Document credential setup in README

**Files:**
- `.env` (add master password)
- `detached_flows/LoginWrapper/login_manager.py`
- `detached_flows/LoginWrapper/cred_fetcher.py`

---

### 5. Build Playwright Application Bot (Optional)
**Status:** Not Started
**Priority:** Lower (existing OpenClaw CLI ApplicationBot works)
**Benefit:** Consistency with Playwright architecture

**Sub-tasks:**
- [ ] Create `detached_flows/Playwright/job_applier.py`
- [ ] Port ApplicationBot logic to Playwright
  - [ ] Handle Easy Apply button click
  - [ ] Navigate multi-step form (Next/Review/Submit)
  - [ ] Upload resume if required
  - [ ] Fill form fields (phone, work authorization, etc.)
- [ ] Integrate with AI decision engine for form handling
- [ ] Add retry logic and error handling
- [ ] Test on 5-10 jobs
- [ ] Update flow to use Playwright applier

**Estimated Effort:** 4-6 hours

---

### 6. Cron Job Setup for Automated Runs
**Status:** Infrastructure ready, not configured
**Dependency:** Requires #1, #2, #3 (full pipeline working)

**Sub-tasks:**
- [ ] Test full pipeline end-to-end
  - [ ] Scrape → Enrich → Screen → Apply
  - [ ] Verify all steps work in sequence
- [ ] Configure cron schedule
  - [ ] Current: 09:10-09:55, 18:30-19:10
  - [ ] Adjust based on LinkedIn rate limits
- [ ] Update cron to use Playwright scripts
  - [ ] Replace `scripts/run_scraper.sh` with `scripts/run_playwright_scraper.sh`
  - [ ] Add enrichment + screening steps
- [ ] Set up monitoring/logging
  - [ ] Log output to `data/logs/cron_YYYY-MM-DD.log`
  - [ ] Email notifications on failures?
- [ ] Install: `make cron-install`

---

## 🟢 LOW PRIORITY / FUTURE ENHANCEMENTS

### 7. Improve Test Coverage
**Status:** Basic tests exist

**Sub-tasks:**
- [ ] Add unit tests for enrichment extraction
- [ ] Add integration tests for full pipeline
- [ ] Mock AI providers for testing
- [ ] Add test fixtures (sample job pages)
- [ ] Set up CI/CD (GitHub Actions?)

---

### 8. Build Admin Dashboard Enhancements
**Status:** Basic UI exists (Flask app)

**Sub-tasks:**
- [ ] Add Playwright scraper stats to dashboard
- [ ] Show AI screening scores in job list
- [ ] Add job filtering by fit_score
- [ ] Visualize application success rate
- [ ] Add manual job screening override

---

### 9. Cost Optimization - Fine-tune Small Language Model
**Status:** Documented in `docs/AI_PROVIDER_ALTERNATIVES.md`
**Benefit:** 10x faster, 100x cheaper AI decisions

**Sub-tasks:**
- [ ] Collect 100-200 AI decision examples
  - [ ] Log all AI decisions to `data/ai_decisions.jsonl`
  - [ ] Include: page state, context, decision, success/failure
- [ ] Fine-tune TinyLlama or Phi-2 on examples
  - [ ] Use Hugging Face AutoTrain or custom LoRA
  - [ ] Target: <100ms inference, 95%+ accuracy
- [ ] Deploy as primary AI provider
- [ ] Keep OpenClaw/HuggingFace as fallback

**Estimated Cost:** $5-20 for fine-tuning
**Estimated Benefit:** $0 ongoing cost, <100ms decisions

---

### 10. Documentation
**Status:** Partial

**Sub-tasks:**
- [ ] Update main README with Playwright migration
- [ ] Document AI screening system
- [ ] Add troubleshooting guide
- [ ] Create video walkthrough?
- [ ] Add architecture diagrams

---

## 📊 METRICS TO TRACK

**Current Database Status (as of 2026-02-04 21:55):**
- ✅ **READY_TO_APPLY**: 16 jobs (Easy Apply detected, ready for automation!)
- ⏭️ **SKIPPED**: 31 jobs (Company site/other apply methods)
- 🔄 **NEEDS_ENRICH**: 2 jobs (extraction retry needed)
- 📝 **NEW**: 6 jobs (not yet processed)
- ✔️ **APPLIED**: 1 job (already applied)
- **TOTAL**: 56 jobs in database

**Performance Metrics:**
- ✅ Enrichment success rate: 96% (48/50)
- ✅ Time per job (enrich): ~30 seconds
- ✅ Extraction quality: 500-3000+ chars per description
- [ ] AI screening acceptance rate (% of jobs passing fit_score threshold)
- [ ] Application success rate (% of applications submitted without errors)
- [ ] Cost per job (if using paid AI providers)

---

## 🐛 KNOWN ISSUES

1. ~~**Enrichment extraction incomplete**~~ ✅ FIXED (2026-02-04)
   - Description: Only getting first ~100-200 chars
   - Impact: High
   - Priority: Critical
   - Resolution: Implemented 3-tier extraction strategy + edge case handling

2. **Credential broker decryption failure**
   - Description: Master password retrieves but decryption fails
   - Impact: Medium (skip-login works as workaround)
   - Priority: Medium
   - Status: Sub-agent investigating

3. **OpenClaw models timeout**
   - Description: `openclaw models status --status-json` times out after 5s
   - Impact: Low (fallback works)
   - Priority: Low

---

## 🎯 NEXT SESSION PRIORITIES

**When starting next session:**
1. ✅ Read this TODO.md first
2. Ask user which priority to tackle
3. Update this file with progress
4. Add any new user requests to appropriate priority section

**Recommended Next Steps:**
- ✅ ~~Fix enrichment extraction (HIGH #1)~~ COMPLETED!
- 🎯 **Build AI screening (HIGH #2)** - READY TO START (16 jobs waiting!)
- 🎯 **Test application flow (HIGH #3)** - Test on 1-2 READY_TO_APPLY jobs
- Then: Full end-to-end pipeline test (scrape → enrich → screen → apply)

---

## 📝 NOTES

- All test scripts in `tests/` folder
- All production scripts in `scripts/` folder
- Makefile targets: `make help` for full list
- Database: `data/autobot.db` (56 jobs, 16 ready to apply!)
- AI providers ready: OpenClaw, HuggingFace, Ollama, Anthropic
- TDD test suite: 7/7 passing (100% success rate)
- Enrichment pipeline: Fully operational with edge case detection
