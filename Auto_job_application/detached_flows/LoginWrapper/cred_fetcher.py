"""Credential fetcher — calls credential_broker.py via subprocess."""
import subprocess
import json
import sys

from detached_flows.config import CREDS_BROKER_PATH


def fetch_credentials(service: str, username: str) -> dict | None:
    """
    Call credential_broker.py and return {username, password} or None.

    Args:
        service: Service name (e.g. "linkedin")
        username: Email/username for the account

    Returns:
        dict with 'username' and 'password' keys, or None if fetch failed
    """
    try:
        result = subprocess.run(
            [
                sys.executable,
                CREDS_BROKER_PATH,
                "--service",
                service,
                "--username",
                username,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())

        return None

    except Exception:
        return None
