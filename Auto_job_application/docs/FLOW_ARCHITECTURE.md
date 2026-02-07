# Auto Job Application - Flow Architecture

> **Last Updated:** 2026-02-04
> **Status:** Architecture Design Document

---

## Overview

The Auto Job Application system follows a **multi-stage pipeline architecture** where each flow is:
- **Independent** - Can run standalone
- **Idempotent** - Safe to re-run without duplicating work
- **Fault-tolerant** - Handles errors gracefully with cleanup

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   FLOW 1    │───▶│   FLOW 2    │───▶│   FLOW 3    │───▶│   FLOW 4    │
│   SCRAPE    │    │   ENRICH    │    │  AI SCREEN  │    │    APPLY    │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                  │                  │                  │
      ▼                  ▼                  ▼                  ▼
  NEW jobs           ENRICHED          SCREENED          APPLIED
  (basic info)       (full details)    (fit_score)       (submitted)
```

---

## Flow 1: SCRAPE (Job Discovery)

### Purpose
Discover and save new job listings from LinkedIn search results.

### Input
- Keywords (e.g., "Engineering Manager")
- Location (e.g., "Bengaluru")
- Limit (number of jobs to scrape)

### Output
Jobs saved to database with status `NEW`:
```python
{
    "external_id": "4367707125",
    "job_title": "Engineering Manager",
    "company": "Tech Corp",
    "job_url": "https://www.linkedin.com/jobs/view/4367707125/",
    "location": "Bengaluru, India",
    "enrich_status": "NEW",
    "scraped_at": "2026-02-04T10:00:00Z"
}
```

### Error Handling
| Error | Action |
|-------|--------|
| Duplicate job (same external_id) | Skip, don't insert |
| LinkedIn rate limit | Wait 5 min, retry |
| Session expired | Re-authenticate, retry |
| Search returns 0 results | Log warning, continue |

### Script
```bash
# Production
./scripts/run_playwright_scraper.sh --limit 10 --keywords "Engineering Manager" --location "Bengaluru"

# Test
make test-scraper
```

### Files
- `detached_flows/Playwright/linkedin_scraper.py`
- `scripts/run_playwright_scraper.sh`

---

## Flow 2: ENRICH (Detail Extraction)

### Purpose
Visit each job page and extract full details (description, compensation, apply type).

### Input
Jobs with `enrich_status IN ('NEW', 'NEEDS_ENRICH')`

### Output
Jobs updated with status based on outcome:

| Status | Description |
|--------|-------------|
| `ENRICHED` | Successfully extracted, `apply_type = 'Easy Apply'` |
| `SKIPPED` | Successfully extracted, `apply_type = 'Company Site'` (external apply) |
| `CLOSED` | Job no longer accepting applications |
| `ALREADY_APPLIED` | User already applied to this job |
| `INVALID` | Job URL doesn't load (404, deleted) → **DELETE from DB** |
| `NEEDS_ENRICH` | Extraction failed, retry later |

### Error Handling
| Error | Action | Status |
|-------|--------|--------|
| Job URL returns 404 | Delete from database | `DELETED` |
| Job page shows "No longer accepting" | Mark as closed | `CLOSED` |
| Job page shows "You applied" | Mark as already applied | `ALREADY_APPLIED` |
| Page load timeout (>30s) | Retry once, then mark | `NEEDS_ENRICH` |
| Extraction returns empty | Retry with different selectors | `NEEDS_ENRICH` |
| LinkedIn blocks/CAPTCHA | Wait 10 min, retry | `NEEDS_ENRICH` |

### Data Extracted
```python
{
    "about_job": "Full job description (500-3000 chars)...",
    "about_company": "Company overview...",
    "compensation": "₹40-50 LPA",
    "work_mode": "Hybrid",
    "apply_type": "Easy Apply" | "Company Site" | None,
    "is_closed": False,
    "already_applied": False,
    "enrich_status": "ENRICHED",
    "enriched_at": "2026-02-04T10:30:00Z"
}
```

### Script
```bash
# Production
./scripts/run_playwright_enricher.sh --limit 20

# Test
make test-enrichment
make test-extraction
make test-edge-cases
```

### Files
- `detached_flows/Playwright/job_enricher.py`
- `detached_flows/Playwright/enrich_jobs_batch.py`
- `scripts/run_playwright_enricher.sh`

---

## Flow 3: AI SCREEN (Fitness Scoring)

### Purpose
Score each job based on profile match using AI. Separate from enrichment for:
- **Cost control** - Only score valid jobs
- **Retry flexibility** - Re-score without re-enriching
- **Provider flexibility** - Switch AI providers independently

### Input
Jobs with `enrich_status = 'ENRICHED'` AND `fit_score IS NULL`

### Output
Jobs updated with AI screening results:
```python
{
    "fit_score": 0.85,  # 0.0 to 1.0
    "fit_reasoning": "Strong match - EM role, 12+ years, AWS/Python skills...",
    "screened_at": "2026-02-04T11:00:00Z",
    "enrich_status": "READY_TO_APPLY" if fit_score >= 0.6 else "LOW_FIT"
}
```

### Scoring Thresholds
| Score Range | Status | Action |
|-------------|--------|--------|
| 0.8 - 1.0 | `READY_TO_APPLY` | High priority, auto-apply |
| 0.6 - 0.79 | `READY_TO_APPLY` | Good fit, auto-apply |
| 0.4 - 0.59 | `REVIEW` | Manual review recommended |
| 0.0 - 0.39 | `LOW_FIT` | Skip, don't apply |

### Error Handling
| Error | Action |
|-------|--------|
| AI provider timeout | Retry with backoff |
| AI provider error | Try fallback provider |
| Score parsing failed | Use default 0.5, log warning |
| Missing job description | Skip, log error |

### AI Providers (Priority Order)
1. **OpenClaw** (default) - Uses local agent, no API cost
2. **Anthropic** - Direct API, requires key
3. **HuggingFace** - Qwen2.5-72B, $2/month
4. **Ollama** - Local LLM, free

### Script
```bash
# Production
./scripts/run_ai_screening.sh --limit 20 --threshold 0.6

# Test
make test-ai-screening
```

### Files
- `detached_flows/ai_decision/job_screener.py` ✅ Created
- `detached_flows/ai_decision/screen_jobs_batch.py` 📝 To create
- `scripts/run_ai_screening.sh` 📝 To create

---

## Flow 4: APPLY (Job Application)

### 4A: Easy Apply (LinkedIn Native)

### Purpose
Automate LinkedIn's Easy Apply process for matched jobs.

### Input
Jobs with `enrich_status = 'READY_TO_APPLY'` AND `apply_type = 'Easy Apply'`

### Process
```
1. Navigate to job page
2. Click "Easy Apply" button
3. Handle multi-step form:
   - Contact info (pre-filled)
   - Resume upload (select or upload)
   - Additional questions (AI-assisted)
   - Review and submit
4. Update job status to APPLIED
5. Store Q&A for future reuse
```

### Question Handling
| Question Type | Strategy |
|---------------|----------|
| Yes/No | AI inference from profile |
| Dropdown | AI selection based on context |
| Text (short) | AI-generated response, cached |
| Text (long) | AI-generated, user review |
| File upload | Use master resume or JD-optimized |

### Error Handling
| Error | Action |
|-------|--------|
| CAPTCHA detected | Pause, notify user |
| Form validation error | Log, retry with corrections |
| Application limit reached | Stop, wait 24h |
| Missing required field | AI-fill or skip job |
| Resume upload failed | Retry with different format |

### Script
```bash
# Production
./scripts/run_easy_apply.sh --limit 5

# Test (dry-run)
./scripts/run_easy_apply.sh --limit 1 --dry-run
```

### Files
- `detached_flows/Playwright/easy_apply_bot.py` 📝 To create
- `detached_flows/ai_decision/question_handler.py` 📝 To create
- `scripts/run_easy_apply.sh` 📝 To create

---

### 4B: Advanced Apply (External Sites)

### Purpose
Handle complex external application processes.

### Scope (Future)
- Account creation on external sites
- Multi-page form navigation
- Document uploads
- ATS-specific handling

### Complexity
- Requires per-site adapters
- May need AI for form understanding
- Higher failure rate expected

### Status: 📅 Future Phase

---

## Flow 5: RESUME (ATS Optimization)

### Purpose
Generate ATS-friendly resumes tailored to specific job descriptions.

### Process
```
1. Load master resume (PDF/JSON)
2. Load job description
3. AI analysis:
   - Extract key requirements
   - Match with profile skills
   - Identify gaps
   - Suggest optimizations
4. Generate tailored resume:
   - Reorder experience by relevance
   - Highlight matching skills
   - Add relevant keywords
   - Maintain ATS compatibility
5. Output: HTML → CSS → PDF
```

### Integration Points
- **Flow 3 (AI Screen)**: Uses same AI provider
- **Flow 4 (Apply)**: Uploads generated resume
- **Dashboard**: Shows generated resumes

### Files (Existing - Fine Tune)
- `src/resume/resume_generator.py` 📝 Fine-tune
- `src/resume/templates/` 📝 ATS templates
- `data/resumes/` - Output directory

### Status: 📅 Priority after Flow 4A

---

## Flow 6: DASHBOARD (Monitoring & Management)

### Purpose
Web UI for monitoring pipeline and managing applications.

### Features
- Job status overview (counts by status)
- Resume template management
- Generated resume gallery
- Application history
- Q&A response library
- Manual job review

### Existing Code
- `src/ui/app.py` - Flask web app
- `src/ui/templates/` - HTML templates

### Enhancements Needed
- Add AI screening stats
- Resume preview/download
- Q&A management page
- Pipeline status indicators

### Status: 📅 Enhance after core flows

---

## Flow Chaining & Orchestration

### Option 1: Sequential Scripts (Current)
```bash
# Run each flow separately
./scripts/run_playwright_scraper.sh --limit 10
./scripts/run_playwright_enricher.sh --limit 20
./scripts/run_ai_screening.sh --limit 20
./scripts/run_easy_apply.sh --limit 5
```

### Option 2: Pipeline Script (Recommended)
```bash
# Single orchestrated run
./scripts/run_pipeline.sh --mode full
./scripts/run_pipeline.sh --mode enrich-only
./scripts/run_pipeline.sh --mode apply-only
```

### Option 3: Cron Scheduler
```bash
# Install cron jobs
make cron-install

# Schedule:
# 09:10 - Scrape new jobs
# 09:30 - Enrich jobs
# 10:00 - AI screening
# 10:30 - Easy Apply (limit 5)
```

### Option 4: Event-Driven (Future)
```python
# Database triggers or message queue
on_job_created -> trigger enrichment
on_job_enriched -> trigger screening
on_job_screened -> trigger apply (if score >= 0.6)
```

---

## Database Schema Updates

### Current Fields
```sql
-- Jobs table
external_id TEXT PRIMARY KEY,
job_title TEXT,
company TEXT,
job_url TEXT,
location TEXT,
about_job TEXT,
about_company TEXT,
compensation TEXT,
work_mode TEXT,
apply_type TEXT,
enrich_status TEXT,  -- NEW, ENRICHED, SKIPPED, CLOSED, etc.
fit_score REAL,
fit_reasoning TEXT,
scraped_at TIMESTAMP,
enriched_at TIMESTAMP,
applied_at TIMESTAMP
```

### New Fields Needed
```sql
-- Add to jobs table
is_deleted BOOLEAN DEFAULT FALSE,  -- Soft delete for invalid jobs
screened_at TIMESTAMP,
applied_status TEXT,  -- SUBMITTED, FAILED, PENDING
application_id TEXT,  -- LinkedIn application reference

-- New table: question_responses
CREATE TABLE question_responses (
    id INTEGER PRIMARY KEY,
    question_text TEXT,
    question_type TEXT,  -- yes_no, dropdown, text_short, text_long
    response TEXT,
    job_id TEXT,
    created_at TIMESTAMP,
    reuse_count INTEGER DEFAULT 0
);

-- New table: generated_resumes
CREATE TABLE generated_resumes (
    id INTEGER PRIMARY KEY,
    job_id TEXT,
    template_name TEXT,
    pdf_path TEXT,
    html_content TEXT,
    created_at TIMESTAMP
);
```

---

## Implementation Roadmap

### Phase 1: Core Pipeline (Current Sprint)
| Step | Task | Status | Priority |
|------|------|--------|----------|
| 1.1 | Flow 1: Scrape | ✅ Done | - |
| 1.2 | Flow 2: Enrich (basic) | ✅ Done | - |
| 1.3 | Flow 2: Enrich (error handling) | 📝 To Do | HIGH |
| 1.4 | Flow 3: AI Screen (module) | ✅ Done | - |
| 1.5 | Flow 3: AI Screen (batch script) | 📝 To Do | HIGH |
| 1.6 | Database cleanup for invalid jobs | 📝 To Do | HIGH |

### Phase 2: Application Flow (Next Sprint)
| Step | Task | Status | Priority |
|------|------|--------|----------|
| 2.1 | Flow 4A: Easy Apply (basic) | 📝 To Do | HIGH |
| 2.2 | Flow 4A: Question handling | 📝 To Do | HIGH |
| 2.3 | Q&A storage and reuse | 📝 To Do | MEDIUM |
| 2.4 | Application tracking | 📝 To Do | MEDIUM |

### Phase 3: Resume & Dashboard (Later)
| Step | Task | Status | Priority |
|------|------|--------|----------|
| 3.1 | Flow 5: Resume generator (fine-tune) | 📝 To Do | MEDIUM |
| 3.2 | ATS templates | 📝 To Do | MEDIUM |
| 3.3 | Flow 6: Dashboard enhancements | 📝 To Do | LOW |

### Phase 4: Advanced Features (Future)
| Step | Task | Status | Priority |
|------|------|--------|----------|
| 4.1 | Flow 4B: Advanced Apply | 📝 To Do | LOW |
| 4.2 | Event-driven orchestration | 📝 To Do | LOW |
| 4.3 | Fine-tuned local LLM | 📝 To Do | LOW |

---

## Implementation Steps (Detailed)

### Step 1.3: Enrich Error Handling

**Goal:** Handle invalid jobs gracefully

**Changes to `job_enricher.py`:**
```python
# Add new status types
ENRICH_STATUS = {
    'NEW': 'Not yet processed',
    'ENRICHED': 'Successfully enriched, Easy Apply',
    'SKIPPED': 'Company site apply (external)',
    'CLOSED': 'Job no longer accepting',
    'ALREADY_APPLIED': 'User already applied',
    'INVALID': 'Job URL invalid (404/deleted)',
    'NEEDS_ENRICH': 'Extraction failed, retry needed',
}

# Add detection for invalid jobs
async def detect_invalid_job(page) -> bool:
    """Check if job page is invalid (404, deleted, etc.)"""
    indicators = [
        'page not found',
        'job not available',
        'this job has been removed',
        'job no longer exists',
    ]
    text = await page.inner_text('body')
    return any(ind in text.lower() for ind in indicators)

# Add cleanup function
def cleanup_invalid_job(external_id: str):
    """Mark job as invalid or delete from database."""
    # Option A: Soft delete
    db.execute("UPDATE jobs SET is_deleted = TRUE WHERE external_id = ?", [external_id])
    # Option B: Hard delete
    db.execute("DELETE FROM jobs WHERE external_id = ?", [external_id])
```

**Implementation time:** 1-2 hours

---

### Step 1.5: AI Screen Batch Script

**Goal:** Create standalone screening script

**New file: `detached_flows/ai_decision/screen_jobs_batch.py`**
```python
"""
Batch AI screening for enriched jobs.

Usage:
    python screen_jobs_batch.py --limit 20 --threshold 0.6
"""
import argparse
from job_screener import JobScreener
from database import get_enriched_jobs, update_job_score

async def screen_jobs_batch(limit: int, threshold: float):
    screener = JobScreener()
    jobs = get_enriched_jobs(limit=limit)
    
    for job in jobs:
        result = screener.score_job(job)
        
        status = 'READY_TO_APPLY' if result['fit_score'] >= threshold else 'LOW_FIT'
        
        update_job_score(
            external_id=job['external_id'],
            fit_score=result['fit_score'],
            fit_reasoning=result['reasoning'],
            enrich_status=status
        )
        
        print(f"[{status}] {job['job_title']} @ {job['company']}: {result['fit_score']:.2f}")
```

**Implementation time:** 2-3 hours

---

### Step 1.6: Database Cleanup

**Goal:** Remove invalid/stale jobs

**New utility: `scripts/cleanup_jobs.py`**
```python
"""
Cleanup invalid and stale jobs from database.

Actions:
- Delete jobs with INVALID status
- Delete jobs older than 30 days with NEW status
- Archive jobs with CLOSED status
"""

def cleanup_invalid_jobs():
    """Delete jobs marked as invalid."""
    count = db.execute("DELETE FROM jobs WHERE enrich_status = 'INVALID'")
    print(f"Deleted {count} invalid jobs")

def cleanup_stale_jobs(days: int = 30):
    """Delete jobs that have been NEW for too long."""
    count = db.execute("""
        DELETE FROM jobs 
        WHERE enrich_status = 'NEW' 
        AND scraped_at < datetime('now', '-{days} days')
    """)
    print(f"Deleted {count} stale jobs")

def archive_closed_jobs():
    """Move closed jobs to archive table."""
    # Implementation...
```

**Implementation time:** 1 hour

---

## Next Steps (Recommended Order)

1. **Add error handling to enrichment** (1.3)
   - Detect invalid/404 jobs
   - Implement cleanup logic
   - Test with known invalid URLs

2. **Create AI screening batch script** (1.5)
   - Separate script from enrichment
   - Add threshold configuration
   - Test on 16 READY_TO_APPLY jobs

3. **Create pipeline orchestration** 
   - Single script to run all flows
   - Status reporting between flows
   - Error handling and recovery

4. **Test end-to-end on 1-2 jobs**
   - Full pipeline: scrape → enrich → screen
   - Verify all status transitions
   - Document any issues

---

## Files Reference

### Existing (✅)
- `detached_flows/Playwright/linkedin_scraper.py`
- `detached_flows/Playwright/job_enricher.py`
- `detached_flows/Playwright/browser_session.py`
- `detached_flows/ai_decision/job_screener.py`
- `scripts/run_playwright_scraper.sh`
- `scripts/run_playwright_enricher.sh`

### To Create (📝)
- `detached_flows/ai_decision/screen_jobs_batch.py`
- `detached_flows/Playwright/easy_apply_bot.py`
- `detached_flows/ai_decision/question_handler.py`
- `scripts/run_ai_screening.sh`
- `scripts/run_easy_apply.sh`
- `scripts/run_pipeline.sh`
- `scripts/cleanup_jobs.py`

### To Fine-Tune (🔧)
- `src/resume/resume_generator.py`
- `src/ui/app.py`

---

## Summary

This architecture separates concerns into distinct flows:
1. **Scrape** - Job discovery (minimal data)
2. **Enrich** - Detail extraction (with cleanup)
3. **AI Screen** - Fitness scoring (separate flow)
4. **Apply** - Easy Apply + Advanced Apply
5. **Resume** - ATS-optimized generation
6. **Dashboard** - Monitoring and management

Each flow is independent, testable, and can be run separately or chained together via scripts or cron.
