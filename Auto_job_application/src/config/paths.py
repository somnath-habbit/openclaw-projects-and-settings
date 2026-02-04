from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    env_root = os.environ.get("AUTO_JOB_APPLICATION_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return project_root() / "data"


def db_path() -> Path:
    env_db = os.environ.get("AUTO_JOB_APPLICATION_DB")
    if env_db:
        return Path(env_db).expanduser().resolve()
    return data_dir() / "autobot.db"


def profile_path() -> Path:
    env_profile = os.environ.get("AUTO_JOB_APPLICATION_PROFILE")
    if env_profile:
        return Path(env_profile).expanduser().resolve()
    return data_dir() / "user_profile.json"


def resumes_dir() -> Path:
    env_resume_dir = os.environ.get("AUTO_JOB_APPLICATION_RESUMES_DIR")
    if env_resume_dir:
        return Path(env_resume_dir).expanduser().resolve()
    return data_dir() / "resumes"


def master_pdf_path() -> Path:
    env_master = os.environ.get("AUTO_JOB_APPLICATION_MASTER_PDF")
    if env_master:
        return Path(env_master).expanduser().resolve()
    return data_dir() / "Somnath_Ghosh_Resume_Master.pdf"


def openclaw_bin() -> str:
    return os.environ.get("OPENCLAW_BIN", "openclaw")
