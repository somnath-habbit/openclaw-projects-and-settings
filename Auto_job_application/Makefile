.PHONY: start stop start-scraper stop-scraper playwright-scrape playwright-enrich ai-screen ai-screen-dry easy-apply easy-apply-dry pipeline pipeline-dry pipeline-full db-stats db-cleanup db-cleanup-force cron-install cron-remove cron-list discover-500 discover-daily cron-install-daily test-scraper test-enrichment test-extraction test-edge-cases test-ai-screening test-all batch-apply batch-apply-bg batch-apply-dry batch-status batch-tail batch-stop register-sites apply-external apply-external-dry scrape-naukri scrape-indeed scrape-instahyre scrape-external scrape-external-dry test-external-scrapers help

BASE_DIR := $(abspath .)
DATA_DIR ?= $(BASE_DIR)/data
PYTHONPATH ?=
OPENCLAW_BIN ?= openclaw
AUTO_JOB_APPLICATION_DB ?= $(DATA_DIR)/autobot.db
AUTO_JOB_APPLICATION_PROFILE ?= $(DATA_DIR)/user_profile.json
AUTO_JOB_APPLICATION_RESUMES_DIR ?= $(DATA_DIR)/resumes
AUTO_JOB_APPLICATION_MASTER_PDF ?= $(DATA_DIR)/Somnath_Ghosh_Resume_Master.pdf
export AUTO_JOB_APPLICATION_ROOT := $(BASE_DIR)
export AUTO_JOB_APPLICATION_DB
export AUTO_JOB_APPLICATION_PROFILE
export AUTO_JOB_APPLICATION_RESUMES_DIR
export AUTO_JOB_APPLICATION_MASTER_PDF
export PYTHONPATH := $(BASE_DIR)/..$(if $(PYTHONPATH),:$(PYTHONPATH))
export OPENCLAW_BIN
CRON_TAG := AUTO_JOB_APPLICATION

start:
	@echo "Starting Auto_job_application..."
	@python3 -m Auto_job_application.src.ui.app

stop:
	@echo "Stopping application on port 5000..."
	@-kill -9 $$(lsof -t -i:5000) 2>/dev/null || echo "No process found on port 5000"

start-scraper:
	@echo "Starting scraper..."
	@$(BASE_DIR)/scripts/run_scraper.sh

stop-scraper:
	@echo "Stopping scraper..."
	@$(BASE_DIR)/scripts/stop_scraper.sh

discover-500:
	@echo "Discovering jobs until 500 total in DB..."
	python3 scripts/job_discovery_supervisor.py --target 500

discover-daily:
	@echo "Running daily discovery (150 new jobs)..."
	python3 scripts/job_discovery_supervisor.py --daily --batch-size 150

cron-install-daily:
	@echo "Installing daily discovery cron (9 AM every day)..."
	@{ \
		crontab -l 2>/dev/null | sed '/# $(CRON_TAG)_DAILY START/,/# $(CRON_TAG)_DAILY END/d'; \
		echo "# $(CRON_TAG)_DAILY START"; \
		echo "0 9 * * * /bin/bash -lc '$(BASE_DIR)/scripts/run_daily_discovery.sh >> $(DATA_DIR)/logs/cron_discovery.log 2>&1'"; \
		echo "# $(CRON_TAG)_DAILY END"; \
	} | crontab -
	@echo "Installed daily discovery at 9 AM. Use 'make cron-list' to verify."

cron-install:
	@echo "Installing cron entries into user crontab..."
	@{ \
		crontab -l 2>/dev/null | sed '/# $(CRON_TAG) START/,/# $(CRON_TAG) END/d'; \
		echo "# $(CRON_TAG) START"; \
		echo "10 9 * * * /bin/bash -lc 'sleep $$((RANDOM%600)); $(BASE_DIR)/scripts/run_scraper.sh'"; \
		echo "55 9 * * * /bin/bash -lc '$(BASE_DIR)/scripts/stop_scraper.sh'"; \
		echo "30 18 * * * /bin/bash -lc 'sleep $$((RANDOM%600)); $(BASE_DIR)/scripts/run_scraper.sh'"; \
		echo "10 19 * * * /bin/bash -lc '$(BASE_DIR)/scripts/stop_scraper.sh'"; \
		echo "# $(CRON_TAG) END"; \
	} | crontab -
	@echo "Installed. Use 'make cron-list' to verify."

cron-remove:
	@echo "Removing cron entries from user crontab..."
	@{ \
		crontab -l 2>/dev/null | sed '/# $(CRON_TAG) START/,/# $(CRON_TAG) END/d'; \
	} | crontab -
	@echo "Removed."

cron-list:
	@echo "Listing cron entries for $(CRON_TAG)..."
	@crontab -l 2>/dev/null | sed -n '/# $(CRON_TAG) START/,/# $(CRON_TAG) END/p' || true

# Playwright production targets
playwright-scrape:
	@echo "Running Playwright scraper (production)..."
	@$(BASE_DIR)/scripts/run_playwright_scraper.sh --limit 10 --keywords "Engineering Manager" --location "Bengaluru"

playwright-enrich:
	@echo "Running Playwright enrichment (production)..."
	@$(BASE_DIR)/scripts/run_playwright_enricher.sh --limit 20

ai-screen:
	@echo "Running AI job screening (production)..."
	@$(BASE_DIR)/scripts/run_ai_screening.sh --limit 20

ai-screen-dry:
	@echo "Running AI job screening (dry-run preview)..."
	@$(BASE_DIR)/scripts/run_ai_screening.sh --limit 20 --dry-run --verbose

easy-apply:
	@echo "Running Easy Apply (production, limit=5)..."
	@python3 $(BASE_DIR)/detached_flows/Playwright/apply_jobs_batch.py --limit 5

easy-apply-dry:
	@echo "Running Easy Apply (dry-run preview)..."
	@python3 $(BASE_DIR)/detached_flows/Playwright/apply_jobs_batch.py --limit 5 --dry-run --debug

# Batch orchestrator targets (batches of 20, up to 200)
batch-apply:
	@echo "Running batch apply (200 jobs, batches of 20, foreground)..."
	@$(BASE_DIR)/scripts/run_batch_apply.sh --total 200 --batch-size 20

batch-apply-bg:
	@echo "Running batch apply in BACKGROUND (200 jobs, batches of 20)..."
	@$(BASE_DIR)/scripts/run_batch_apply.sh --total 200 --batch-size 20 --bg

batch-apply-dry:
	@echo "Running batch apply DRY RUN (200 jobs, batches of 20)..."
	@$(BASE_DIR)/scripts/run_batch_apply.sh --total 200 --batch-size 20 --dry-run

batch-status:
	@$(BASE_DIR)/scripts/run_batch_apply.sh --status

batch-tail:
	@$(BASE_DIR)/scripts/run_batch_apply.sh --tail

batch-stop:
	@$(BASE_DIR)/scripts/run_batch_apply.sh --stop

# Database management targets
db-stats:
	@python3 $(BASE_DIR)/scripts/cleanup_jobs.py --stats

db-cleanup:
	@echo "Running database cleanup (dry-run preview)..."
	@python3 $(BASE_DIR)/scripts/cleanup_jobs.py --all --dry-run

db-cleanup-force:
	@echo "Running database cleanup (ACTUAL DELETE)..."
	@python3 $(BASE_DIR)/scripts/cleanup_jobs.py --all

# Pipeline targets (full orchestration)
pipeline:
	@$(BASE_DIR)/scripts/run_pipeline.sh --mode full

pipeline-dry:
	@$(BASE_DIR)/scripts/run_pipeline.sh --mode full --dry-run

pipeline-full:
	@echo "Running full pipeline with external sites: Scrape → Enrich → Screen → Apply (LinkedIn + External)..."
	@$(BASE_DIR)/scripts/run_pipeline.sh --mode full
	@echo "Now applying to external jobs..."
	@python3 -c "import asyncio; from detached_flows.apply_router import ApplyRouter; print('External apply would run here')"

# External job application targets
register-sites:
	@echo "Registering on configured job sites..."
	@python3 -c "\
import asyncio, json; \
from detached_flows.site_registry import SiteRegistry; \
registry = SiteRegistry(); \
print('Configured sites:'); \
[print(f'  - {s.key}: {s.name} ({s.base_url})') for s in registry.list_sites()]; \
print('\nTo register, run: python3 scripts/register_on_site.py --site <name>')"

apply-external:
	@echo "Running external job applications (limit=5)..."
	@python3 $(BASE_DIR)/scripts/apply_external_batch.py --limit 5

apply-external-dry:
	@echo "Running external job applications (dry-run, limit=5)..."
	@DRY_RUN=true python3 $(BASE_DIR)/scripts/apply_external_batch.py --limit 5 --dry-run

# External scraper targets
scrape-naukri:
	@echo "Scraping Naukri.com..."
	@python3 $(BASE_DIR)/detached_flows/Playwright/naukri_scraper.py --keywords "$(or $(KEYWORDS),Engineering Manager)" --location "$(or $(LOCATION),Bengaluru)" --limit $(or $(LIMIT),10)

scrape-indeed:
	@echo "Scraping Indeed..."
	@python3 $(BASE_DIR)/detached_flows/Playwright/indeed_scraper.py --keywords "$(or $(KEYWORDS),Engineering Manager)" --location "$(or $(LOCATION),Bengaluru)" --limit $(or $(LIMIT),10)

scrape-instahyre:
	@echo "Scraping Instahyre..."
	@python3 $(BASE_DIR)/detached_flows/Playwright/instahyre_scraper.py --keywords "$(or $(KEYWORDS),Engineering Manager)" --location "$(or $(LOCATION),Bengaluru)" --limit $(or $(LIMIT),10)

scrape-external:
	@echo "Scraping all external sites..."
	@python3 $(BASE_DIR)/detached_flows/Playwright/scrape_orchestrator.py --sites naukri indeed --keywords "$(or $(KEYWORDS),Engineering Manager)" --location "$(or $(LOCATION),Bengaluru)" --limit $(or $(LIMIT),10)

scrape-external-dry:
	@echo "Scraping all external sites (dry-run)..."
	@python3 $(BASE_DIR)/detached_flows/Playwright/scrape_orchestrator.py --sites naukri indeed --keywords "$(or $(KEYWORDS),Engineering Manager)" --location "$(or $(LOCATION),Bengaluru)" --limit $(or $(LIMIT),10) --dry-run

test-external-scrapers:
	@echo "Testing external scrapers (dry-run)..."
	@python3 $(BASE_DIR)/scripts/test_external_scrapers.py --site naukri --dry-run --debug --limit 3

# Test targets
test-scraper:
	@echo "Testing Playwright scraper (assumes active LinkedIn session)..."
	@cd $(BASE_DIR) && python3 tests/test_scraper_skip_login.py

test-enrichment:
	@echo "Testing Playwright enrichment (assumes active LinkedIn session)..."
	@cd $(BASE_DIR) && python3 tests/test_enrichment.py

test-extraction:
	@echo "Running TDD extraction tests (pytest)..."
	@cd $(BASE_DIR) && pytest tests/test_enrichment_extraction.py -v

test-edge-cases:
	@echo "Running edge case tests (pytest)..."
	@cd $(BASE_DIR) && pytest tests/test_edge_cases.py -v

test-ai-screening:
	@echo "Running AI screening tests (pytest, excludes integration tests)..."
	@cd $(BASE_DIR) && pytest tests/test_ai_screening.py -v -k "not integration"

test-all: test-scraper test-enrichment test-extraction test-edge-cases test-ai-screening
	@echo "All tests completed!"

help:
	@echo "Available commands:"
	@echo ""
	@echo "Application:"
	@echo "  make start         - Start the application server"
	@echo "  make stop          - Stop the application server (kill port 5000)"
	@echo ""
	@echo "Scraper (OpenClaw CLI):"
	@echo "  make start-scraper - Start the scraper (scripts/run_scraper.sh)"
	@echo "  make stop-scraper  - Stop the scraper (scripts/stop_scraper.sh)"
	@echo ""
	@echo "Playwright (Production):"
	@echo "  make playwright-scrape  - Run Playwright scraper (limit=10)"
	@echo "  make playwright-enrich  - Run Playwright enrichment (limit=20)"
	@echo "  make ai-screen          - Run AI job screening (limit=20)"
	@echo "  make ai-screen-dry      - Preview AI screening without DB changes"
	@echo "  make easy-apply         - Run Easy Apply (limit=5)"
	@echo "  make easy-apply-dry     - Preview Easy Apply without submitting"
	@echo ""
	@echo "Batch Apply (batches of 20, up to 200):"
	@echo "  make batch-apply        - Run batch apply in foreground"
	@echo "  make batch-apply-bg     - Run batch apply in BACKGROUND"
	@echo "  make batch-apply-dry    - Preview batch apply (dry-run)"
	@echo "  make batch-status       - Check background batch status"
	@echo "  make batch-tail         - Tail the latest batch log"
	@echo "  make batch-stop         - Stop background batch process"
	@echo ""
	@echo "Database Management:"
	@echo "  make db-stats           - Show database statistics"
	@echo "  make db-cleanup         - Preview database cleanup (dry-run)"
	@echo "  make db-cleanup-force   - Run database cleanup (deletes invalid/stale jobs)"
	@echo ""
	@echo "Pipeline (Full Orchestration):"
	@echo "  make pipeline           - Run full pipeline: Scrape → Enrich → Screen"
	@echo "  make pipeline-dry       - Preview pipeline (dry-run)"
	@echo "  make pipeline-full      - Full pipeline + external apply"
	@echo ""
	@echo "External Scrapers:"
	@echo "  make scrape-naukri          - Scrape Naukri.com (KEYWORDS=, LOCATION=, LIMIT=)"
	@echo "  make scrape-indeed          - Scrape Indeed (KEYWORDS=, LOCATION=, LIMIT=)"
	@echo "  make scrape-instahyre       - Scrape Instahyre (requires login)"
	@echo "  make scrape-external        - Scrape all external sites"
	@echo "  make scrape-external-dry    - Scrape all external sites (dry-run)"
	@echo "  make test-external-scrapers - Test external scrapers (dry-run)"
	@echo ""
	@echo "External Job Applications:"
	@echo "  make register-sites     - List and register on job sites"
	@echo "  make apply-external     - Apply to external jobs (limit=5)"
	@echo "  make apply-external-dry - Preview external apply (dry-run)"
	@echo ""
	@echo "Cron Jobs:"
	@echo "  make cron-install  - Install scraper cron entries into user crontab"
	@echo "  make cron-remove   - Remove scraper cron entries from user crontab"
	@echo "  make cron-list     - Show scraper cron entries from user crontab"
	@echo ""
	@echo "Testing (Playwright - requires active LinkedIn session):"
	@echo "  make test-scraper      - Test job scraping (limit=5)"
	@echo "  make test-enrichment   - Test job enrichment (limit=3)"
	@echo "  make test-extraction   - Run TDD extraction tests (pytest)"
	@echo "  make test-edge-cases   - Run edge case tests (closed jobs, already applied)"
	@echo "  make test-ai-screening - Run AI job screening tests (pytest)"
	@echo "  make test-all          - Run all tests"
	@echo ""
	@echo "  make help          - Show this help message"
	@echo ""
	@echo "Cron guidance: these targets manage your *user* crontab (crontab -e)."
	@echo "For system-wide cron, run 'sudo crontab -e' and paste the entries shown by 'make cron-list'."
