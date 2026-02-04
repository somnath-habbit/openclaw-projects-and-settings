# CLAUDE.md — Auto Job Application

## What This Is

Automated LinkedIn job scraper and applicator with a Flask web dashboard. Scrapes jobs, enriches details, auto-submits Easy Apply applications, and lets you manually manage cover letters and tailored resumes.

Browser automation is handled entirely via the **OpenClaw CLI** (`openclaw browser` subcommands) — not Selenium or Playwright.

---

## Folder Structure

```
flow/                   # Orchestration entry points (scraper, enrich, apply)
src/
  config/paths.py       # All path/env resolution lives here
  tools/
    database_tool.py    # DatabaseManager — single class for all SQLite ops
    linkedin_tools.py   # BaseAgent, LinkedInAgent, ApplicationBot
    task_processor.py   # Pending cover-letter / resume task queue
  ui/
    app.py              # Flask app (routes + dashboard)
    templates/          # Jinja HTML templates (Bootstrap 5.3)
  tests/                # Test files
scripts/                # Shell wrappers for cron (run/stop scraper)
migrations/             # DB schema migrations (run manually)
data/                   # Runtime data — DB, logs, resumes, screenshots
docs/                   # Strategy & improvement docs
config/                 # Reserved (currently empty)
```

---

## Key Commands

```bash
make start            # Flask web UI on localhost:5000
make stop             # Kill Flask
make start-scraper    # Run phased scraper in background (PID-managed)
make stop-scraper     # Graceful stop (SIGINT → SIGTERM)
make cron-install     # Install cron: morning 09:10-09:55, evening 18:30-19:10
make cron-remove      # Remove cron jobs
make cron-list        # Show cron entries
make help             # All targets
```

Manual flow commands (run from project root):
```bash
python flow/standalone_scraper.py --phased --phases "10,25,50" --early-stop
python flow/enrich_jobs.py 50          # Enrich up to 50 jobs missing details
python flow/auto_apply_batch.py        # Auto-apply READY_TO_APPLY jobs
python flow/run_apply_only.py          # Apply only, no discovery (limit 10)
```

---

## Environment Variables

All resolved in `src/config/paths.py`. Makefile exports these automatically:

| Variable | Default |
|---|---|
| `AUTO_JOB_APPLICATION_ROOT` | project root (derived from `paths.py` location) |
| `AUTO_JOB_APPLICATION_DB` | `data/autobot.db` |
| `AUTO_JOB_APPLICATION_PROFILE` | `data/user_profile.json` |
| `AUTO_JOB_APPLICATION_RESUMES_DIR` | `data/resumes/` |
| `AUTO_JOB_APPLICATION_MASTER_PDF` | `data/Somnath_Ghosh_Resume_Master.pdf` |
| `OPENCLAW_BIN` | `openclaw` |

---

## Job Lifecycle & Statuses

```
LinkedIn Search
  → NEW (inserted into jobs table)
  → NEEDS_ENRICH (missing about_job / apply_type)
  → READY_TO_APPLY (Easy Apply detected)
  → APPLIED / BLOCKED / FAILED (after auto-apply attempt)

Manual statuses: PENDING_TAILORING, PENDING_GENERATION
```

Status transitions are set by `enrich_jobs.py` based on `apply_type`:
- `"Easy Apply"` → `READY_TO_APPLY`
- `"Company Site"` / `"Apply"` → `SKIPPED`
- missing → `NEEDS_ENRICH`

---

## Database

SQLite at `data/autobot.db`. Managed entirely by `DatabaseManager` in `database_tool.py`.

Key tables: `jobs`, `companies`, `profile`, `interactions`, `scans`, `voice_logs`

Schema is additive — new columns added via `_ensure_column()` at runtime. Migrations in `migrations/` handle bigger structural changes and must be run manually.

---

## Scraping Rules (Non-Negotiable)

Defined in `docs/SCRAPING_STRATEGY_AND_SCHEDULE.md`. When modifying scraper logic, stay within these:

- **10–50 jobs per run**, max 2–3 pages
- Random delays: 3–12s navigation, 2–6s typing, 10–20s page loads
- Session cap with backoff on 429/403
- Checkpoint to DB after each job (no batch-at-end)
- Max 5 consecutive failures before stopping
- Phased testing: 10 → 25 → 50 jobs with early-stop

---

## OpenClaw Browser API

All browser automation goes through subprocess calls to `openclaw browser`:

```
open <url>                        → returns tab_id
snapshot --format aria            → ARIA tree (parsed with regex)
click <ref>                       → click element by accessibility ref
press <key>                       → keyboard input
upload --paths <file> --request <json>
screenshot --path <file>
close <target_id>
```

Parsing ARIA snapshots with regex is the primary extraction method — no DOM/CSS selectors.

---

## Testing

```bash
python src/tests/test_new_scraper.py   # Phased pipeline test (10 → 25 → 50)
```

- Do **not** use a live browser agent for UI testing
- Tests live in `src/tests/`
- Use `SCRAPER_DRY_RUN=1` to run scraper logic without real LinkedIn access

---

## Common Gotchas

- Path resolution depends on `AUTO_JOB_APPLICATION_ROOT`. If running scripts outside the Makefile, set it manually or run from project root.
- `enrich_jobs.py` opens a real browser tab per job — don't run with a high limit in testing.
- `voice_logs` table and UI exist but the voice input pipeline itself is not in this repo.
- `task_processor.py` returns pending tasks but the actual generation (cover letters, resume tailoring) is handled externally (likely an OpenClaw agent skill).
