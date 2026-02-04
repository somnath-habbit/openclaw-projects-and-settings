#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="${AUTO_JOB_APPLICATION_ROOT:-$BASE_DIR}"
DATA_DIR="$ROOT_DIR/data"
export AUTO_JOB_APPLICATION_ROOT="$ROOT_DIR"
export AUTO_JOB_APPLICATION_DB="${AUTO_JOB_APPLICATION_DB:-$DATA_DIR/autobot.db}"
export AUTO_JOB_APPLICATION_PROFILE="${AUTO_JOB_APPLICATION_PROFILE:-$DATA_DIR/user_profile.json}"
export AUTO_JOB_APPLICATION_RESUMES_DIR="${AUTO_JOB_APPLICATION_RESUMES_DIR:-$DATA_DIR/resumes}"
export AUTO_JOB_APPLICATION_MASTER_PDF="${AUTO_JOB_APPLICATION_MASTER_PDF:-$DATA_DIR/Somnath_Ghosh_Resume_Master.pdf}"
export PYTHONPATH="$BASE_DIR/..${PYTHONPATH:+:${PYTHONPATH}}"
export OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"
LOG_DIR="$DATA_DIR/logs"
PID_FILE="$DATA_DIR/scraper.pid"

mkdir -p "$LOG_DIR"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Scraper already running (PID $(cat "$PID_FILE"))."
  exit 0
fi

STAMP="$(date +"%Y%m%d_%H%M%S")"
LOG_FILE="$LOG_DIR/scraper_$STAMP.log"

CMD=(python "$BASE_DIR/flow/standalone_scraper.py" --phased --phases "10,25,50" --early-stop --max-failures 5)

if [[ "${SCRAPER_DEBUG:-}" == "1" ]]; then
  CMD+=(--debug)
fi

if [[ "${SCRAPER_DRY_RUN:-}" == "1" ]]; then
  CMD+=(--dry-run)
fi

"${CMD[@]}" >> "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"

echo "Scraper started (PID $!) -> $LOG_FILE"
