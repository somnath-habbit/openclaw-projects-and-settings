# Scraping Improvements & Scheduling Plan

This document captures the implemented scraping improvements, the proposed scheduling plan, and the test strategy. It replaces the previous placeholder notes.

---

## ✅ Implemented Scraping Improvements

### 1) Two-Phase Scrape (Fast → Deep)
- **Phase 1**: Collect job IDs + titles per page only.
- **Phase 2**: Enrich details for **new jobs only** (open job page tabs after discovery).

### 2) Adaptive Backoff + Failure Cap
- Track consecutive failures across tab/snapshot/enrich attempts.
- Backoff delays: **2s → 5s → 10s**.
- Stop safely after `--max-failures` consecutive failures.

### 3) Structured Retry (Per Job)
- Detail extraction attempts: **up to 3 retries**.
- If still incomplete, store minimal data and mark `NEEDS_ENRICH` with `last_enrich_error`.

### 4) Structured Logging (JSON)
All key steps emit JSON logs, e.g.
```json
{ "ts": "...Z", "event": "snapshot_failed", "job_id": "123" }
```
Levels:
- **INFO**: discovery progress
- **WARNING**: retries
- **ERROR**: tab/snapshot failures

### 5) Screenshot & Snapshot Strategy
Only capture artifacts when **debug enabled** *and* extraction fails or apply_type missing:
- **Screenshots**: `data/screenshots/{job_id}_{timestamp}.png`
- **ARIA snapshots**: `data/snapshots/{job_id}_{timestamp}.txt`

### 6) Data Quality Checks
- If `about_job` < 100 chars → `NEEDS_ENRICH`
- If `apply_type` missing → `NEEDS_ENRICH`
- Save `enrich_status` and `last_enrich_error`

### 7) New CLI Flags
Standalone scraper supports:
- `--debug`: verbose logs + screenshot/snapshot on failures
- `--dry-run`: no DB writes
- `--max-failures`: stop after N consecutive failures

---

## ✅ Test Plan (Required)

**Goal:** 10–50 jobs, 2–3 pages, incremental phases.

**Phases:** `10 → 25 → 50`

Run:
```bash
python flow/standalone_scraper.py --phased --phases "10,25,50" --early-stop
```

Expected:
- 2–3 pages max
- JSON logs reflect per-page discovery + enrichment
- `NEEDS_ENRICH` on weak pages

---

## ✅ Scheduling Plan (Human-like Run Windows)

**Goal:** Start/stop runs daily in short windows (not continuous).
**Confirmed windows:** 09:10–09:55 and 18:30–19:10 local time.

### Start/Stop Scripts
- `scripts/run_scraper.sh`
- `scripts/stop_scraper.sh`

These manage a PID file: `data/scraper.pid`

### Recommended Cron Entries (example)
Two daily windows with jitter:
```cron
# Start morning window (random 0-10 min delay)
10 9 * * * AUTO_JOB_APPLICATION_ROOT=/path/to/Auto_job_application AUTO_JOB_APPLICATION_DB=/path/to/Auto_job_application/data/autobot.db AUTO_JOB_APPLICATION_PROFILE=/path/to/Auto_job_application/data/user_profile.json AUTO_JOB_APPLICATION_RESUMES_DIR=/path/to/Auto_job_application/data/resumes AUTO_JOB_APPLICATION_MASTER_PDF=/path/to/Auto_job_application/data/Somnath_Ghosh_Resume_Master.pdf /bin/bash -lc 'sleep $((RANDOM%600)); /path/to/Auto_job_application/scripts/run_scraper.sh'
# Stop after ~45 mins
55 9 * * * AUTO_JOB_APPLICATION_ROOT=/path/to/Auto_job_application AUTO_JOB_APPLICATION_DB=/path/to/Auto_job_application/data/autobot.db AUTO_JOB_APPLICATION_PROFILE=/path/to/Auto_job_application/data/user_profile.json AUTO_JOB_APPLICATION_RESUMES_DIR=/path/to/Auto_job_application/data/resumes AUTO_JOB_APPLICATION_MASTER_PDF=/path/to/Auto_job_application/data/Somnath_Ghosh_Resume_Master.pdf /bin/bash -lc '/path/to/Auto_job_application/scripts/stop_scraper.sh'

# Start evening window
30 18 * * * AUTO_JOB_APPLICATION_ROOT=/path/to/Auto_job_application AUTO_JOB_APPLICATION_DB=/path/to/Auto_job_application/data/autobot.db AUTO_JOB_APPLICATION_PROFILE=/path/to/Auto_job_application/data/user_profile.json AUTO_JOB_APPLICATION_RESUMES_DIR=/path/to/Auto_job_application/data/resumes AUTO_JOB_APPLICATION_MASTER_PDF=/path/to/Auto_job_application/data/Somnath_Ghosh_Resume_Master.pdf /bin/bash -lc 'sleep $((RANDOM%600)); /path/to/Auto_job_application/scripts/run_scraper.sh'
# Stop after ~40 mins
10 19 * * * AUTO_JOB_APPLICATION_ROOT=/path/to/Auto_job_application AUTO_JOB_APPLICATION_DB=/path/to/Auto_job_application/data/autobot.db AUTO_JOB_APPLICATION_PROFILE=/path/to/Auto_job_application/data/user_profile.json AUTO_JOB_APPLICATION_RESUMES_DIR=/path/to/Auto_job_application/data/resumes AUTO_JOB_APPLICATION_MASTER_PDF=/path/to/Auto_job_application/data/Somnath_Ghosh_Resume_Master.pdf /bin/bash -lc '/path/to/Auto_job_application/scripts/stop_scraper.sh'
```

### Optional Environment Flags
```bash
SCRAPER_DEBUG=1  # enable screenshots on failures
SCRAPER_DRY_RUN=1  # run without DB writes
```

---

## ✅ Notes
- Enrichment flow now honors `enrich_status` and `last_enrich_error`.
- New DB columns are auto-added on startup.
- Search remains safe when no jobs are available (fast exit on duplicates).
