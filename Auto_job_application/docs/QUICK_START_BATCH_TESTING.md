# Quick Start - Batch Application Testing

**IMPORTANT**: Read [BATCH_APPLICATION_IMPROVEMENTS.md](./BATCH_APPLICATION_IMPROVEMENTS.md) for full details.

## What Was Implemented (2026-02-05)

✅ Loop detection - bot gives up after 3 stuck attempts
✅ Validation error checking - detects empty required fields
✅ Smart fallback answers - rating questions default to 8-9
✅ Screenshot system - captures failures automatically
✅ Detailed status tracking - STUCK_ON_FORM, VALIDATION_ERROR, SUBMITTED

## Testing Now

### 1. Ensure Q&A Manager Running
```bash
# Terminal 1
cd /home/somnath/.openclaw/workspace/Auto_job_application
python -m src.ui.app
# Should be at: http://localhost:5001/qa
```

### 2. Run Batch Application
```bash
# Terminal 2
cd /tmp/claude-1000/-home-somnath-Desktop-openclaw-creds-manager/scratchpad
python batch_apply.py 10
```

## What to Watch For

### Good Signs ✅
- "Login successful!"
- "Application SUBMITTED!"
- "Generated answer: '8'" (fallback working)
- Progress through multiple jobs

### Warning Signs ⚠️
- "Same page detected (1/3)" → loop detection working
- "Validation error found" → error checking working
- "No Easy Apply available" → normal, skip and continue

### Bad Signs ❌
- Bot stuck in infinite loop (same log repeating)
- No progress after 5+ minutes
- Python errors/exceptions

## If It Fails

### Check Screenshots
```bash
ls -lh /home/somnath/.openclaw/workspace/Auto_job_application/data/screenshots/
# Look for: apply_*_stuck.png, apply_*_validation_error.png
```

### Check Database
```bash
sqlite3 /home/somnath/.openclaw/workspace/Auto_job_application/data/autobot.db
```
```sql
SELECT id, title, status, notes FROM jobs ORDER BY id DESC LIMIT 10;
```

### Check Logs
- Console output shows detailed progress
- Look for "Generated answer" to see fallback system working
- "Screenshot saved" messages indicate failure points

## Success Criteria

- At least 5/10 jobs should reach SUBMITTED or STUCK_ON_FORM status
- Bot should NOT hang indefinitely on any job
- Screenshots should be captured for failed jobs
- Database should show detailed error messages in notes field

## Key Files

- **Bot**: `/home/somnath/.openclaw/workspace/Auto_job_application/detached_flows/Playwright/easy_apply_bot.py`
- **Questions**: `/home/somnath/.openclaw/workspace/Auto_job_application/detached_flows/ai_decision/question_handler.py`
- **Batch Script**: `/tmp/claude-1000/-home-somnath-Desktop-openclaw-creds-manager/scratchpad/batch_apply.py`
- **Database**: `/home/somnath/.openclaw/workspace/Auto_job_application/data/autobot.db`
- **Screenshots**: `/home/somnath/.openclaw/workspace/Auto_job_application/data/screenshots/`

## If Session Crashes

1. Check if batch_apply.py is still running: `ps aux | grep batch_apply`
2. Check latest job status in database
3. Review screenshots for last processed job
4. Resume from next job or restart batch

## Emergency Stop

```bash
# Kill batch process
pkill -f batch_apply.py

# Check browser processes
ps aux | grep playwright
```

## Expected Timeline

- Login: 5-15 seconds
- Each application: 30-90 seconds
- 10 applications: ~10-15 minutes total
- Stuck detection triggers after 3 attempts (~2-3 minutes max per job)
