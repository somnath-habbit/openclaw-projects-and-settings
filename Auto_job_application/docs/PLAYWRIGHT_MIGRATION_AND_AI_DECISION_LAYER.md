# Playwright Migration & AI Decision Layer — Implementation Strategy

> **Status:** Pre-implementation. Review and approve before any code is written.
> **Scope:** Additive only. Nothing in `src/` or `flow/` is touched. All new code lives in `detached_flows/`.
> **Last updated:** 2026-02-04

---

## 1. Why This Exists — Current Bottlenecks

The current stack routes every browser action through the OpenClaw CLI as a subprocess:

```
Python code
  → subprocess: openclaw browser open <url>
  → subprocess: openclaw browser snapshot --format aria
  → regex parse the ARIA text
  → subprocess: openclaw browser click <ref>
```

Three concrete problems this creates:

1. **Fragile extraction.** All page understanding is regex on ARIA text snapshots. A LinkedIn layout change (reordered sections, renamed buttons, new popup layers) silently breaks extraction with no fallback.

2. **Subprocess overhead on every action.** Each `run_browser()` call spawns a new process. The scraper and applier are already pacing with human-like delays, but the subprocess round-trips add latency and make timing less predictable.

3. **No path for intelligent popup handling.** LinkedIn throws verification popups, CAPTCHA challenges, cookie consent dialogs, and dynamic application questions mid-flow. The current code returns `BLOCKED` or `FAILED` when it hits anything it can't regex-match. There is no fallback decision layer.

---

## 2. What Changes, What Doesn't

| Layer | Status | Rationale |
|---|---|---|
| `src/tools/linkedin_tools.py` | **Unchanged** | Existing scraper and applier keep working via OpenClaw. No risk. |
| `flow/` (all files) | **Unchanged** | Cron, phased scraping, enrichment, auto-apply — all untouched. |
| `src/ui/app.py` | **Unchanged** | Dashboard reads from the same `jobs` table regardless of which layer wrote it. |
| `data/autobot.db` | **Shared, append-only** | New flows write to the same DB using the same schema. No migrations needed. |
| `detached_flows/` | **New — all new code goes here** | Completely self-contained. Can be tested, enabled, and disabled independently. |

The migration is not a replacement. It is a parallel track. Once validated, individual flows (scraper, then applier) can be switched over by changing which entry point the cron or Makefile calls.

---

## 3. Proposed Folder Structure

```
detached_flows/
├── config.py                   # Provider selection, API keys, shared paths
├── Playwright/
│   ├── __init__.py
│   ├── browser_session.py      # Launch, cookie persistence, anti-detection args
│   ├── page_utils.py           # Shared: wait, click, type, extract text, screenshot
│   ├── linkedin_scraper.py     # Playwright scraper (mirrors LinkedInAgent logic)
│   └── linkedin_applier.py     # Playwright applier (mirrors ApplicationBot logic)
├── LoginWrapper/
│   ├── __init__.py
│   ├── cred_fetcher.py         # Calls credential_broker.py via subprocess (same interface OpenClaw uses)
│   └── login_manager.py        # Navigate → enter creds → handle 2FA/popup → persist session
└── ai_decision/
    ├── __init__.py
    ├── decision_engine.py      # Orchestrator: screenshot + context → provider → action
    ├── context_builder.py      # Pulls user_profile + job row from DB, formats as prompt context
    ├── action_schema.py        # Pydantic models for the action contract (click, type, select, wait, skip)
    └── providers/
        ├── __init__.py
        ├── base.py             # Abstract provider interface
        ├── anthropic_provider.py
        ├── openai_provider.py
        └── gemini_provider.py
```

---

## 4. Component Design

### 4a. LoginWrapper — Credential Fetching

**How credentials are fetched today:**
OpenClaw invokes the `secure-login` skill, which calls `credential_broker.py` in `openclaw-creds-manager`. The broker outputs `{"username": "...", "password": "..."}` to stdout.

**How LoginWrapper does it:**
Same call. No change to the broker. We just cut OpenClaw out of the middle:

```
LoginWrapper/cred_fetcher.py
  → subprocess: python <path-to>/openclaw-creds-manager/broker/credential_broker.py
                --service linkedin --username <email>
  → parse JSON from stdout
```

The path to `credential_broker.py` is configured in `detached_flows/config.py` and can be set via env var `OPENCLAW_CREDS_BROKER_PATH`. This keeps the two projects decoupled — no direct Python imports across project boundaries.

**Session persistence (critical for LinkedIn):**
After a successful login, Playwright can save the full browser state (cookies, local storage, session tokens) to a JSON file via `browser_context.storage_state()`. On subsequent runs, the session is restored from this file. Login only re-runs if the session is expired or missing.

Session file location: `data/playwright_sessions/linkedin_session.json`

### 4b. Playwright Browser Layer — Anti-Detection

LinkedIn actively detects automation. The existing scraping strategy rules (random delays, session caps, pagination limits) must all be preserved. Additional Playwright-specific measures:

- **Browser launch args:** Disable `AutomationControlled` flag, set a realistic user agent string, disable WebGL fingerprinting tells.
- **Headless mode:** Use Playwright's `chromium` in headless `new` mode (not the legacy `--headless` flag which is trivially detected). If detection persists, switch to headed mode with a visible window.
- **Timing:** All waits use `page.wait_for_load_state("networkidle")` + the same randomized delay ranges from `SCRAPING_STRATEGY_AND_SCHEDULE.md` (3–12s nav, 2–6s typing, 10–20s page loads). These are not optional.
- **Extraction:** Playwright's `page.accessibility.snapshot()` gives the same accessibility tree as OpenClaw's ARIA snapshots — so the same extraction logic (section headers, button refs) can be ported directly. But we also gain `page.evaluate()` for targeted DOM queries as a fallback, and `page.screenshot()` natively for the AI layer.

### 4c. AI Decision Engine — The Core New Capability

This is the layer that handles what the current code cannot: dynamic, unpredictable page states.

**When it activates:**
The AI engine is NOT used for every page interaction. It is a fallback. The normal flow is:

```
1. Take accessibility snapshot
2. Try structured extraction (same logic as current code)
3. If extraction succeeds → act normally
4. If extraction fails OR an unrecognized popup/modal is detected → invoke AI decision engine
```

**What the AI engine receives:**
- A screenshot of the current page (PNG, base64-encoded)
- The accessibility snapshot as text (lightweight context)
- A `context` block built by `context_builder.py`:
  - The relevant fields from `user_profile.json` (name, email, phone, experience summary, skills)
  - If mid-application: the current job row (title, company, JD)
  - The current `goal` — what the flow was trying to do when it hit the unknown state (e.g., "complete Easy Apply for job X", "log in to LinkedIn")
- A strict action schema that the AI must conform to (see below)

**Action schema (what the AI can return):**
```json
{
  "action": "click" | "type" | "select" | "wait" | "skip" | "screenshot_again",
  "target": "<description of the element>",
  "coordinates": [x, y],          // only if action=click and no clear element ref
  "text": "...",                   // only if action=type
  "reason": "...",                 // mandatory — why this action
  "confidence": 0.0–1.0           // self-reported confidence
}
```

**Decision rules applied after the AI responds:**
- If `confidence < 0.5` → do NOT act. Log the state, mark the job as `BLOCKED`, move on.
- If `action = skip` → same as above.
- If `action = type` and the target looks like a password or sensitive field → cross-reference against the credential broker output. Never let the AI hallucinate credentials.
- All AI-driven actions are logged to a new table `ai_decisions` for auditing and replay.

**Example scenarios the AI handles:**
| Popup / State | What happens |
|---|---|
| "Are you a human?" CAPTCHA | AI returns `skip` + reason. Job marked `BLOCKED`. |
| "Verify your identity" with SMS code | AI returns `wait` + reason "OTP required, cannot automate". Job marked `BLOCKED`. |
| "Do you want to save your password?" | AI returns `click` on "Not now" or equivalent dismiss button. |
| Cookie consent banner | AI returns `click` on "Accept" or "Dismiss". |
| Application form question ("years of experience?") | AI reads the user profile context, returns `type` with the correct value. |
| "This job has been filled" overlay | AI returns `skip`. Job status updated to `SKIPPED`. |

### 4d. AI Provider Comparison

| Provider | Vision Model | Cost Tier | Free Tier | Latency | Notes |
|---|---|---|---|---|---|
| **Anthropic Claude** | claude-3-5-sonnet | Medium | No | ~2–4s | Strong at structured output. If you already have `ANTHROPIC_API_KEY` set (likely, since you're using Claude Code), this is zero additional setup. |
| **OpenAI** | gpt-4o | Medium-High | No | ~2–5s | Strong vision. Well-documented. Slightly more expensive at scale. |
| **Google Gemini** | gemini-1.5-flash | Low | Yes (limited RPM) | ~1–2s | Fastest and cheapest. Free tier RPM limits will be hit quickly if AI is called on every popup. Viable as a budget option for low-volume runs. |

**Recommendation: Anthropic Claude as primary, Gemini as fallback/budget.**

Reasoning:
- You likely already have `ANTHROPIC_API_KEY` in your environment from Claude Code. No new key setup.
- Claude is strong at following strict output schemas (the action contract above). Fewer retries needed to get valid structured JSON back.
- Gemini Flash as a fallback keeps costs low if Claude is rate-limited or the run is high-volume.

**Note on "reusing the Claude Code session":** Claude Code's internal API session is managed by Anthropic's infrastructure and is not accessible to user code. You cannot piggyback on it programmatically. What you *can* do is use the same `ANTHROPIC_API_KEY` that Claude Code uses — check with `echo $ANTHROPIC_API_KEY`. If it's set, your code can use it directly with no additional configuration.

---

## 5. Data Flow

### Login flow (new)
```
detached_flows entry point
  → LoginWrapper/cred_fetcher.py
      → subprocess: credential_broker.py --service linkedin
      → returns {username, password}
  → LoginWrapper/login_manager.py
      → Playwright: open linkedin.com/login
      → check session file → if valid, skip login
      → if not: type creds, submit
      → if popup/2FA appears → AI decision engine
      → on success: save session state to data/playwright_sessions/
```

### Scrape flow (new, parallel to existing)
```
detached_flows/Playwright/linkedin_scraper.py
  → restore session from file
  → open search URL (same URL construction as current code)
  → page.accessibility.snapshot() → structured extraction
  → if extraction fails → AI decision engine (fallback)
  → INSERT INTO jobs (same table, same schema)
  → same delay rules as SCRAPING_STRATEGY_AND_SCHEDULE.md
```

### Apply flow (new, parallel to existing)
```
detached_flows/Playwright/linkedin_applier.py
  → restore session
  → open job URL
  → click Easy Apply
  → step through form:
      → structured extraction (accessibility snapshot)
      → if unknown form state → AI decision engine
      → upload resume if prompted
      → submit
  → UPDATE jobs SET status = result
  → 15s anti-detection delay between jobs (same as current)
```

---

## 6. Migration Phases

These are sequential. Do not start a phase until the previous one is validated.

**Phase 1 — Infrastructure only**
- Set up `detached_flows/` folder structure
- Implement `browser_session.py` (launch, anti-detection args, session persistence)
- Implement `cred_fetcher.py` (call credential_broker.py)
- Implement `config.py`
- Validation: Can we open linkedin.com, take a screenshot, and save/restore a session?

**Phase 2 — LoginWrapper**
- Implement `login_manager.py`
- Wire in the AI decision engine for login-time popups only
- Validation: Can we log in to LinkedIn end-to-end, persist the session, and restore it on next run without re-logging in?

**Phase 3 — AI Decision Engine**
- Implement `decision_engine.py`, `context_builder.py`, `action_schema.py`
- Implement the Anthropic provider first. Add others as needed.
- Validation: Feed it 5–10 saved screenshots of known popup types. Verify the returned actions are correct and the confidence scores are calibrated.

**Phase 4 — Playwright Scraper**
- Port `LinkedInAgent.search()` logic into `linkedin_scraper.py`
- Use accessibility snapshots for extraction (same logic), AI engine as fallback
- Validation: Run against LinkedIn with `--dry-run` (no DB writes). Compare discovered jobs against what the OpenClaw scraper finds in the same window. They should match within noise.

**Phase 5 — Playwright Applier**
- Port `ApplicationBot.apply_to_job()` logic into `linkedin_applier.py`
- AI engine handles form questions and unexpected states
- Validation: Run against 3–5 test jobs. Manually verify each application went through correctly before enabling in production.

**Phase 6 — Switchover (optional, future)**
- Update `scripts/run_scraper.sh` or Makefile to point to the new entry points
- Keep old flows in place as fallback for at least one week

---

## 7. Testing Plan

- **No live LinkedIn scraping in unit tests.** All browser-layer tests use saved HTML/accessibility snapshots as fixtures.
- **AI provider tests use real API calls** but against a fixed set of saved screenshots. Record expected actions. Flag regressions if the action changes.
- **Integration tests** (Phase 4 and 5 validation) run against live LinkedIn but are gated behind a `DETACHED_FLOWS_LIVE_TEST=1` env flag. They respect all scraping strategy rules.
- **Session restore test:** Delete the session file mid-flow. Confirm the login wrapper re-authenticates cleanly.
- **AI confidence test:** Feed the engine screenshots of ambiguous states (e.g., partially loaded pages). Confirm it returns `confidence < 0.5` and does not act.

---

## 8. API Key & Secret Management

| Secret | Where it lives | How it's accessed |
|---|---|---|
| LinkedIn credentials | Encrypted SQLite in `openclaw-creds-manager` | Via `credential_broker.py` subprocess — never in env vars or files in this project |
| `ANTHROPIC_API_KEY` | Shell environment (already set for Claude Code) | Read at runtime via `os.environ` |
| `OPENAI_API_KEY` | Shell environment (if OpenAI provider is enabled) | Read at runtime via `os.environ` |
| `GEMINI_API_KEY` | Shell environment (if Gemini provider is enabled) | Read at runtime via `os.environ` |
| Playwright session state | `data/playwright_sessions/linkedin_session.json` | Read/written by LoginWrapper. Contains cookies — treat like a credential. Do not commit to git. |

Add `data/playwright_sessions/` to `.gitignore`.

---

## 9. Open Decisions

These need a call before Phase 1 starts:

1. **Browser mode:** Start with headless (`new` mode). If LinkedIn blocks, switch to headed. Which do you prefer as the default?

2. **AI activation threshold:** The plan says "AI activates only when structured extraction fails." Should there be a secondary trigger — e.g., "activate AI if the page contains any modal/dialog element regardless of whether extraction worked"?

3. **CAPTCHA policy:** When the AI detects a CAPTCHA it cannot solve, the job is marked `BLOCKED`. Should there be an alert (email, notification, dashboard flag) so you can manually intervene, or is silent `BLOCKED` acceptable?

4. **Credential broker path:** Confirm the path to `credential_broker.py` in `openclaw-creds-manager`. It will be set as the default in `config.py`.

5. **Session expiry handling:** LinkedIn sessions typically last 1–2 weeks. Should the login wrapper proactively re-authenticate on a schedule (e.g., every 5 days), or only when a request fails with a 401/redirect-to-login?

---

**Last updated:** 2026-02-04
