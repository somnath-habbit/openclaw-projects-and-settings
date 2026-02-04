# Auto Job Application - LinkedIn Automation System

Automated job discovery, enrichment, and application system for LinkedIn using Playwright and AI decision-making.

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install playwright python-dotenv
playwright install chromium

# 2. Configure environment
cp .env.example .env
nano .env  # Add your OPENCLAW_MASTER_PASSWORD and LINKEDIN_EMAIL

# 3. Test the system
make test-scraper      # Scrape 5 jobs
make test-enrichment   # Enrich 3 jobs

# 4. Run production
make playwright-scrape  # Scrape 10 new jobs
make playwright-enrich  # Enrich all unenriched jobs
```

## 📋 Documentation

| Document | Description |
|----------|-------------|
| **[TODO.md](TODO.md)** | Task tracking with priority ordering |
| **[docs/PLAYWRIGHT_IMPLEMENTATION.md](docs/PLAYWRIGHT_IMPLEMENTATION.md)** | Complete technical documentation |
| **[docs/AI_PROVIDER_ALTERNATIVES.md](docs/AI_PROVIDER_ALTERNATIVES.md)** | AI provider options & cost comparison |
| **[tests/README.md](tests/README.md)** | Test documentation |
| **[Makefile](Makefile)** | Run `make help` for all commands |

## 🎯 Features

### ✅ Implemented (Phases 1-4)

- **Job Scraper** - Playwright-based LinkedIn job scraping
- **Job Enricher** - Extract full job details from individual pages
- **AI Decision Engine** - Handle popups and dynamic page states
- **Multi-AI Provider** - OpenClaw, HuggingFace, Ollama, Anthropic
- **Anti-Detection** - Human-like delays, realistic user agent
- **Session Persistence** - Login once, reuse cookies
- **Test Suite** - Automated testing with skip-login mode

### 🚧 In Progress

- **AI Job Screening** - Match jobs against profile (see TODO.md #2)
- **Enrichment Quality** - Improve extraction completeness (see TODO.md #1)

### 📅 Planned

- **Application Bot** - Automated Easy Apply submissions
- **Cron Automation** - Scheduled runs (infrastructure ready)
- **Fine-tuned SLM** - Ultra-fast, cost-optimized AI decisions

## 📊 Current Status

```
Database: 56 jobs
├─ NEW: 22 (scraped, not enriched)
├─ READY_TO_APPLY: 1 (enriched, Easy Apply)
├─ SKIPPED: 30 (not Easy Apply)
├─ GENERATING_CV: 2
└─ APPLIED: 1

AI Providers: 4 (OpenClaw, HuggingFace, Ollama, Anthropic)
Tests: Passing ✅
Production: Ready (pending TODO #1, #2)
```

## 🛠️ Common Commands

```bash
# Scraping
make playwright-scrape              # Scrape 10 new jobs
make test-scraper                   # Test scraper (5 jobs)

# Enrichment
make playwright-enrich              # Enrich 20 jobs
make test-enrichment                # Test enrichment (3 jobs)

# Testing
make test-all                       # Run all tests

# Application
make start                          # Start web UI (port 5000)
make stop                           # Stop web UI

# Cron Jobs
make cron-install                   # Install automated schedule
make cron-list                      # Show cron entries
make cron-remove                    # Remove cron entries

# Help
make help                           # Show all commands
```

## 📁 Project Structure

```
Auto_job_application/
├── data/                           # Database, resumes, screenshots
│   ├── autobot.db                 # SQLite database
│   ├── user_profile.json          # User profile for AI screening
│   ├── playwright_sessions/       # Saved browser sessions
│   └── screenshots/               # Debug screenshots
├── detached_flows/                # Playwright implementation (NEW)
│   ├── Playwright/
│   │   ├── linkedin_scraper.py   # Main scraper
│   │   ├── job_enricher.py       # Job detail extractor
│   │   └── enrich_jobs_batch.py  # Batch enrichment
│   ├── LoginWrapper/
│   │   ├── login_manager.py      # LinkedIn login
│   │   └── cred_fetcher.py       # Credential broker
│   └── ai_decision/
│       ├── decision_engine.py    # AI orchestrator
│       └── providers/            # AI provider implementations
├── src/                           # Original implementation (OpenClaw CLI)
│   ├── tools/
│   │   ├── linkedin_tools.py     # LinkedInAgent, ApplicationBot
│   │   └── database_tool.py      # DatabaseManager
│   └── ui/
│       └── app.py                # Flask web UI
├── scripts/                       # Helper scripts
│   ├── run_playwright_scraper.sh # Scraper with .env
│   └── run_playwright_enricher.sh # Enricher with .env
├── tests/                         # Test suite
│   ├── test_scraper_skip_login.py
│   └── test_enrichment.py
├── docs/                          # Documentation
│   ├── PLAYWRIGHT_IMPLEMENTATION.md  # Complete tech docs
│   └── AI_PROVIDER_ALTERNATIVES.md   # AI providers
├── TODO.md                        # Task tracking (READ THIS FIRST!)
├── Makefile                       # Command shortcuts
└── .env                           # Configuration (create from .env.example)
```

## 🔧 Configuration

### Environment Variables (.env)

```bash
# Required
OPENCLAW_MASTER_PASSWORD=your-password-here
LINKEDIN_EMAIL=your-email@example.com

# Optional (defaults shown)
PLAYWRIGHT_HEADLESS=true           # false for visible browser
AI_PROVIDER=openclaw               # openclaw | huggingface | anthropic | ollama
AI_MODEL=sonnet                    # sonnet | haiku | opus

# HuggingFace (if using)
HUGGINGFACE_API_KEY=your-key
HUGGINGFACE_MODEL=Qwen/Qwen2.5-72B-Instruct

# Ollama (if using)
OLLAMA_ENDPOINT=http://localhost:11434
OLLAMA_MODEL=phi3:mini

# Anthropic (if using)
ANTHROPIC_API_KEY=your-key
```

### AI Provider Selection

| Provider | Setup | Cost | Speed | Use Case |
|----------|-------|------|-------|----------|
| **OpenClaw** | None (OAuth) | Included | 2-4s | Default, no API key needed |
| **HuggingFace** | API key | $2/month | 1-3s | Cost-effective |
| **Ollama** | Install locally | Free | 0.5-1s | Privacy, offline |
| **Anthropic** | API key | Pay-per-use | 1-2s | High quality |

**Recommendation:** Start with OpenClaw (default), switch to HuggingFace for cost optimization.

## 🧪 Testing

```bash
# Test scraping (assumes active LinkedIn session)
make test-scraper

# Test enrichment
make test-enrichment

# Run all tests
make test-all
```

**Note:** Tests use skip-login mode - make sure you're logged into LinkedIn in a browser first, or the session is active from a previous run.

## 🚀 Production Deployment

1. **Configure:**
   ```bash
   # Set headless mode
   echo "PLAYWRIGHT_HEADLESS=true" >> .env
   ```

2. **Test:**
   ```bash
   make playwright-scrape
   make playwright-enrich
   ```

3. **Set up cron:**
   ```bash
   make cron-install
   ```

4. **Monitor:**
   ```bash
   # Check logs
   tail -f data/logs/scraper_$(date +%Y-%m-%d).log

   # Check database
   sqlite3 data/autobot.db "SELECT COUNT(*) FROM jobs WHERE status = 'NEW';"
   ```

## 📈 Roadmap

**Next Session (High Priority):**
1. Fix enrichment extraction quality (TODO #1)
2. Build AI job screening system (TODO #2)
3. Test application flow (TODO #3)

**Medium Priority:**
- Full login flow testing (add master password)
- Cron automation setup
- Monitoring dashboard

**Future:**
- Fine-tune small language model for AI decisions
- Build Playwright application bot
- Enhanced admin UI

See [TODO.md](TODO.md) for detailed task list.

## 🐛 Troubleshooting

### Session expired
```bash
rm data/playwright_sessions/linkedin_session.json
make playwright-scrape
```

### Job descriptions incomplete
See TODO.md #1 - extraction quality improvement in progress

### AI provider timeout
```bash
# Switch provider in .env
AI_PROVIDER=ollama  # or huggingface
```

### Database locked
```bash
# Kill running processes
pkill -f linkedin_scraper
pkill -f enrich_jobs_batch
```

See [docs/PLAYWRIGHT_IMPLEMENTATION.md](docs/PLAYWRIGHT_IMPLEMENTATION.md) for complete troubleshooting guide.

## 📝 Development

**Adding a new feature:**
1. Read [TODO.md](TODO.md) - check priority list
2. Read [docs/PLAYWRIGHT_IMPLEMENTATION.md](docs/PLAYWRIGHT_IMPLEMENTATION.md) - understand architecture
3. Create feature branch
4. Add tests in `tests/`
5. Update documentation
6. Submit PR

**Coding standards:**
- Use async/await for Playwright operations
- Add type hints
- Include docstrings
- Follow existing patterns (see Developer Guide in docs)

## 🤝 Contributing

1. Check [TODO.md](TODO.md) for open tasks
2. Pick a task with your skill level
3. Ask questions if unclear
4. Submit clean, tested code
5. Update documentation

## 📄 License

[Your License Here]

## 📞 Support

- Documentation: [docs/](docs/)
- Issues: [GitHub Issues](https://github.com/your-repo/issues)
- Questions: [Discussions](https://github.com/your-repo/discussions)

---

**Current Version:** Phase 1-4 Complete (Playwright Migration)
**Last Updated:** 2026-02-04
**Status:** Production-ready (pending TODO #1, #2)
