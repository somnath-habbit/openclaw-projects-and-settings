Add this as imprvemtent strategy in a MD file and save in project docs folder. Then Hand it off to a sub agent to work upon. Also I want to to run everyday at certain interval, for a specific duration to mimic human usage. its should not be continuously running, so cron job to start and stop. We test the approach first for 10 to 50 jobs incrimentally, 2 to 3 pageinations. Then setup the cron. Add this to the same subagent to work upon. Also should be part of the md file if things get lost in between

Here’s a clean strategy you can adopt before changing code:

---

## ✅ Scraping Logic Improvements (Strategy)

### 1. **Two-Phase Scrape (Fast → Deep)**
- **Phase 1 (fast)**: collect job IDs + titles only  
- **Phase 2 (deep)**: open each job and enrich details  
**Benefit:** avoids heavy tab opens if no jobs or page load issues

---

### 2. **Adaptive Backoff**
- Track consecutive failures (snapshot fail, tab fail, rate-limit)
- If failures > 2: increase delay (2s → 5s → 10s)
- If failures > 5: pause run and mark jobs `NEEDS_RETRY`

---

### 3. **Structured Retry**
For each job:
- Attempt extraction up to **2–3 times**
- If still empty: save minimal data and mark `NEEDS_ENRICH`

---

## ✅ Logging Strategy

### 1. **Structured Logs**
Use `logging` with JSON format:
```json
{ "job_id": "...", "step": "snapshot", "status": "fail", "err": "tab not found" }
```
So you can filter logs later.

### 2. **Log Levels**
- **INFO**: job counts, progress
- **WARNING**: extraction failed, fallback used
- **ERROR**: browser errors, tab not found
- **DEBUG**: raw snapshot length, parsed counts (optional)

---

## ✅ Screenshot Strategy

Only take screenshots when:
✅ **Extraction fails**  
✅ **apply_type is empty**  
✅ **job page looks broken**

Save to:
```
/data/screenshots/{job_id}_{timestamp}.png
```

Optional: also save **ARIA snapshot** into `/data/snapshots/`

---

## ✅ Data Quality Checks

After extraction:
- If `about_job` < 100 chars → mark `NEEDS_ENRICH`
- If `apply_type` missing → retry once → else mark `NEEDS_ENRICH`
- Always store `last_enrich_error` (if any)

---

## ✅ Minimal Risk Improvements (Low Effort)
- Add `--debug` flag → enables screenshots + verbose logs
- Add `--dry-run` flag → scrape but don’t update DB
- Add `--max-failures` flag → stops run safely

---

If you want, I can now convert this strategy into actual code changes.
