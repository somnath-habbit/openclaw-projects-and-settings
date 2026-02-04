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
PID_FILE="$DATA_DIR/scraper.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "No scraper PID file found."
  exit 0
fi

PID="$(cat "$PID_FILE")"

if kill -0 "$PID" 2>/dev/null; then
  echo "Stopping scraper PID $PID"
  kill -INT "$PID"
  sleep 5
  if kill -0 "$PID" 2>/dev/null; then
    echo "Force killing scraper PID $PID"
    kill -TERM "$PID"
  fi
else
  echo "Scraper PID $PID not running."
fi

rm -f "$PID_FILE"
