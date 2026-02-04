# Scraping Improvement Strategy + Human-like Run Schedule

> **Purpose:** Define safe, human-like scraping/application behavior. This document is meant to be a *single source of truth* so the workflow can resume even if execution is interrupted.

---

## ✅ Requirements (Non‑Negotiable)
- **Incremental runs:** 10–50 jobs per run (never more in a single session).
- **Pagination depth:** Only **2–3 pages** per run.
- **Human‑like pacing:** Randomized delays, jitter, and natural breaks.
- **Start/stop windows:** Use cron to **start/stop runs only inside defined time windows**.
- **Resume‑safe:** Logs and checkpoints must allow restart without duplicating work.

---

## 1) Scraping Improvement Strategy

### A) Reduce detection risk
- **Random delays** between actions: 3–12s for navigation clicks, 2–6s for typing, 10–20s between page loads.
- **Micro‑pauses** to mimic reading: 5–15s after page render before interacting.
- **Session cap:** Hard stop after 10–50 jobs or after 2–3 paginations (whichever comes first).
- **Backoff on failures:** If 429/403 or repeated DOM load errors:
  - pause run for 30–60 minutes
  - reduce pagination depth next run
  - lower job cap by 30–50%

### B) Improve reliability
- **Checkpoint after each job:** Store job ID, URL, and application status.
- **Idempotency:** Skip jobs already processed (hash URL or job ID).
- **Error classification:**
  - transient (network/timeouts)
  - structural (selectors missing)
  - access (captcha/blocked)
- **Retry policy:** Only retry transient errors; stop run if access error occurs.

### C) Improve quality
- **Focus on relevant roles only:** Apply filters before pagination.
- **Rate‑limit low quality listings:** Skip if title/location/company mismatch.

---

## 2) Human‑Like Run Schedule (Minimum Required Behavior)

### Run Cadence
- **Daily runs:** 2–4 times/day (not continuous)
- **Each run:** 10–50 jobs total, 2–3 pages max
- **Cooldown between runs:** 2–4 hours
- **Weekends:** Reduce cadence or pause

### Within a Run
- **Page 1:** apply to 3–10 jobs then pause (5–10 min)
- **Page 2:** apply to 3–10 jobs then pause (3–6 min)
- **Page 3 (optional):** apply to remaining jobs, then stop

> **Stop immediately** if: captcha, access errors, 2+ failed pages, or throttling signals.

---

## 3) Proposed Cron Start/Stop Windows

> Goal: start a run at allowed times and force stop at end of window.

### Suggested Windows (Asia/Calcutta)
- **Morning:** 09:30–11:30
- **Afternoon:** 14:30–16:00
- **Evening:** 19:00–21:00

### Example Cron Entries (start/stop)
> Replace `RUN_SCRIPT` and `STOP_SCRIPT` with actual command/script names.

```
# Morning window
30 9 * * *  /path/to/RUN_SCRIPT --max-jobs 10-50 --max-pages 2-3
30 11 * * * /path/to/STOP_SCRIPT

# Afternoon window
30 14 * * * /path/to/RUN_SCRIPT --max-jobs 10-50 --max-pages 2-3
0 16 * * *  /path/to/STOP_SCRIPT

# Evening window
0 19 * * *  /path/to/RUN_SCRIPT --max-jobs 10-50 --max-pages 2-3
0 21 * * *  /path/to/STOP_SCRIPT
```

> **Important:** stop cron must be a hard kill / graceful stop mechanism that prevents jobs from continuing outside window.

---

## 4) Testing Steps (Before Enabling Cron)

1. **Dry run (single page)**
   - limit to 5 jobs, 1 pagination
   - confirm no duplicate job IDs

2. **Full run simulation**
   - limit to 15–20 jobs, 2 pages
   - verify delays, pauses, checkpoints

3. **Stop behavior test**
   - manually invoke STOP_SCRIPT mid‑run
   - confirm run terminates and checkpoints are preserved

4. **Resume test**
   - restart run after forced stop
   - ensure previously processed jobs are skipped

---

## 5) Coordination Checklist (In case of interruption)

If session is interrupted, continue from this checklist:

- [ ] Confirm the **max‑jobs per run** (10–50) is enforced.
- [ ] Confirm **pagination cap** (2–3 pages) is enforced.
- [ ] Verify **cron start/stop windows** are correct for the timezone.
- [ ] Confirm **STOP_SCRIPT** safely terminates ongoing work.
- [ ] Run the **testing steps** above before enabling cron.

---

## 6) Questions for Somnath (to finalize)

1. Preferred **time windows** for runs (keep or adjust?)
2. Which command/script should be used for **RUN_SCRIPT**?
3. What command/script should be used for **STOP_SCRIPT**?
4. Should weekends be disabled or low‑cadence only?

---

**Last updated:** 2026‑02‑04
