"""Configuration for detached_flows — all paths, API keys, and settings."""
import os
import json
from pathlib import Path

# Resolve project root (Auto_job_application/)
_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = Path(
    os.environ.get("AUTO_JOB_APPLICATION_ROOT", str(_THIS_FILE.parent.parent))
).resolve()

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(os.environ.get("AUTO_JOB_APPLICATION_DB", str(DATA_DIR / "autobot.db")))
PROFILE_PATH = Path(
    os.environ.get("AUTO_JOB_APPLICATION_PROFILE", str(DATA_DIR / "user_profile.json"))
)
MASTER_PDF = Path(
    os.environ.get(
        "AUTO_JOB_APPLICATION_MASTER_PDF",
        str(DATA_DIR / "Somnath_Ghosh_Resume_Master.pdf"),
    )
)
SESSIONS_DIR = DATA_DIR / "playwright_sessions"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"

# Credential broker path (openclaw-creds-manager)
CREDS_BROKER_PATH = os.environ.get(
    "OPENCLAW_CREDS_BROKER_PATH",
    "/home/somnath/Desktop/openclaw-creds-manager/broker/credential_broker.py",
)

# AI configuration
AI_PROVIDER = os.environ.get("AI_PROVIDER", "openclaw")  # openclaw | huggingface | anthropic | ollama
AI_MODEL = os.environ.get("AI_MODEL", "sonnet")  # Model for OpenClaw (sonnet, opus, haiku)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# HuggingFace Inference API configuration
HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY")
HUGGINGFACE_MODEL = os.environ.get("HUGGINGFACE_MODEL", "Qwen/Qwen2.5-72B-Instruct")

# Ollama local model configuration
OLLAMA_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "phi3:mini")

# Browser
BROWSER_HEADLESS = os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() != "false"


def get_linkedin_email() -> str | None:
    """Read LinkedIn email from user_profile.json."""
    if not PROFILE_PATH.exists():
        return os.environ.get("LINKEDIN_EMAIL")

    try:
        with open(PROFILE_PATH) as f:
            profile = json.load(f)
        # Email is under profile.email
        return profile.get("profile", {}).get("email") or os.environ.get("LINKEDIN_EMAIL")
    except Exception:
        return os.environ.get("LINKEDIN_EMAIL")
