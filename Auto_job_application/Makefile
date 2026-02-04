.PHONY: start stop start-scraper stop-scraper cron-install cron-remove cron-list help

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

help:
	@echo "Available commands:"
	@echo "  make start         - Start the application server"
	@echo "  make stop          - Stop the application server (kill port 5000)"
	@echo "  make start-scraper - Start the scraper (scripts/run_scraper.sh)"
	@echo "  make stop-scraper  - Stop the scraper (scripts/stop_scraper.sh)"
	@echo "  make cron-install  - Install scraper cron entries into user crontab"
	@echo "  make cron-remove   - Remove scraper cron entries from user crontab"
	@echo "  make cron-list     - Show scraper cron entries from user crontab"
	@echo "  make help          - Show this help message"
	@echo ""
	@echo "Cron guidance: these targets manage your *user* crontab (crontab -e)."
	@echo "For system-wide cron, run 'sudo crontab -e' and paste the entries shown by 'make cron-list'."
