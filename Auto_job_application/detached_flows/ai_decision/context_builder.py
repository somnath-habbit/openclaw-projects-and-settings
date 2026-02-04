"""Context builder — pulls user profile and job data from DB for AI prompts."""
import json
from pathlib import Path

from detached_flows.config import PROFILE_PATH, DB_PATH


def build_context(goal: str, job_id: int | None = None) -> dict:
    """
    Build context dict for AI decision engine.

    Args:
        goal: The current task (e.g., "log in to LinkedIn", "apply to job X")
        job_id: Optional job ID to include job details

    Returns:
        dict with goal, user_profile, and optionally job info
    """
    context = {"goal": goal}

    # Load user profile
    if PROFILE_PATH.exists():
        try:
            with open(PROFILE_PATH) as f:
                profile_data = json.load(f)
            profile = profile_data.get("profile", {})
            context["user_profile"] = {
                "name": profile.get("name"),
                "email": profile.get("email"),
                "phone": profile.get("phone"),
                "location": profile.get("location"),
                "title": profile.get("title", ""),
                "bio": profile.get("bio", "")[:300],  # Truncate long bio
            }
        except Exception:
            pass

    # Load job if provided
    if job_id and DB_PATH.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            if row:
                context["job"] = {
                    "title": row["title"],
                    "company": row["company"],
                    "location": row["location"],
                    "about_job": row.get("about_job", "")[:500],  # Truncate
                }
            conn.close()
        except Exception:
            pass

    return context
