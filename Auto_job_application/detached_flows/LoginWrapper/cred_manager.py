"""
Credential Manager - Extended credential operations for multi-site job applications.

Builds on existing cred_fetcher.py to add: store, generate password, backup triggers.
Uses OpenClaw Credential Manager's broker and credential store.

Usage:
    manager = CredentialManager()
    creds = manager.fetch("naukri", "user@email.com")
    manager.store("naukri", "user@email.com", "s3cur3P@ss", tier="medium")
"""
import subprocess
import json
import sys
import secrets
import string
import logging
from typing import Optional, Dict
from pathlib import Path

from detached_flows.config import CREDS_BROKER_PATH
from detached_flows.LoginWrapper.cred_fetcher import fetch_credentials

logger = logging.getLogger("CredentialManager")

# Path to OpenClaw Credential Manager project
OPENCLAW_PROJECT_ROOT = Path(CREDS_BROKER_PATH).parent.parent
BACKUP_SCRIPT_PATH = OPENCLAW_PROJECT_ROOT / "scripts" / "backup_to_s3.py"


class CredentialManager:
    """
    Extended credential operations for the universal job application engine.

    Wraps OpenClaw's credential broker for fetch, and calls the credential
    store directly (via subprocess) for store/update/delete operations.
    """

    def __init__(self):
        self.broker_path = CREDS_BROKER_PATH

    def fetch(self, site_name: str, username: str) -> Optional[Dict]:
        """
        Fetch credentials for a site from OpenClaw.

        Reuses existing fetch_credentials() from cred_fetcher.py.

        Args:
            site_name: Service name (e.g., "naukri", "indeed")
            username: Email/username for the account

        Returns:
            {"username": "...", "password": "..."} or None
        """
        creds = fetch_credentials(site_name, username)

        if creds:
            logger.info(f"Fetched credentials for {site_name}/{username}")
        else:
            logger.info(f"No credentials found for {site_name}/{username}")

        return creds

    def has_credentials(self, site_name: str, username: str) -> bool:
        """Check if credentials exist for a site without fetching the password."""
        return self.fetch(site_name, username) is not None

    def store(
        self,
        site_name: str,
        username: str,
        password: str,
        tier: str = "medium"
    ) -> bool:
        """
        Store new credentials in OpenClaw.

        Calls OpenClaw's Flask API endpoint to add credentials.
        Falls back to direct CredentialStore import if API not available.

        Args:
            site_name: Service name
            username: Email/username
            password: Plain text password (will be encrypted by OpenClaw)
            tier: Security tier (low, medium, high, critical)

        Returns:
            True if stored successfully
        """
        try:
            # Method 1: Call OpenClaw's Flask API (if running)
            import requests
            response = requests.post(
                "http://localhost:5000/api/credentials",
                json={
                    "service": site_name.lower().strip(),
                    "username": username.strip(),
                    "password": password,
                    "tier": tier
                },
                timeout=5
            )

            if response.status_code in (200, 201):
                logger.info(f"Stored credentials for {site_name}/{username} via API")
                self._trigger_backup()
                return True

        except Exception as e:
            logger.debug(f"API store failed (expected if app not running): {e}")

        # Method 2: Direct import of CredentialStore
        try:
            # Add OpenClaw project to path temporarily
            sys.path.insert(0, str(OPENCLAW_PROJECT_ROOT))

            from src.credential_store import CredentialStore
            from src.repository import SecurityTier
            from src.auth import get_master_password_from_keyring

            master_password = get_master_password_from_keyring()
            if not master_password:
                import os
                master_password = os.environ.get("OPENCLAW_MASTER_PASSWORD")

            if not master_password:
                logger.error("Cannot store credentials: no master password available")
                return False

            tier_map = {
                'low': SecurityTier.LOW,
                'medium': SecurityTier.MEDIUM,
                'high': SecurityTier.HIGH,
                'critical': SecurityTier.CRITICAL,
            }

            store = CredentialStore(master_password=master_password)
            store.add(
                service=site_name.lower().strip(),
                username=username.strip(),
                password=password,
                tier=tier_map.get(tier, SecurityTier.MEDIUM)
            )
            store.close()

            logger.info(f"Stored credentials for {site_name}/{username} via direct import")
            self._trigger_backup()
            return True

        except Exception as e:
            logger.error(f"Failed to store credentials: {e}")
            return False

        finally:
            # Clean up sys.path
            if str(OPENCLAW_PROJECT_ROOT) in sys.path:
                sys.path.remove(str(OPENCLAW_PROJECT_ROOT))

    def update_password(
        self,
        site_name: str,
        username: str,
        new_password: str
    ) -> bool:
        """
        Update password for existing credentials.

        Args:
            site_name: Service name
            username: Email/username
            new_password: New plain text password

        Returns:
            True if updated successfully
        """
        try:
            sys.path.insert(0, str(OPENCLAW_PROJECT_ROOT))

            from src.credential_store import CredentialStore
            from src.auth import get_master_password_from_keyring
            import os

            master_password = (
                get_master_password_from_keyring() or
                os.environ.get("OPENCLAW_MASTER_PASSWORD")
            )

            if not master_password:
                logger.error("Cannot update: no master password")
                return False

            store = CredentialStore(master_password=master_password)
            result = store.update(
                service=site_name.lower().strip(),
                username=username.strip(),
                password=new_password
            )
            store.close()

            if result:
                logger.info(f"Updated password for {site_name}/{username}")
                self._trigger_backup()

            return result

        except Exception as e:
            logger.error(f"Failed to update password: {e}")
            return False

        finally:
            if str(OPENCLAW_PROJECT_ROOT) in sys.path:
                sys.path.remove(str(OPENCLAW_PROJECT_ROOT))

    def generate_password(self, length: int = 20) -> str:
        """
        Generate a cryptographically strong password.

        Args:
            length: Password length (default 20)

        Returns:
            Strong random password
        """
        # Ensure at least one of each character type
        lower = secrets.choice(string.ascii_lowercase)
        upper = secrets.choice(string.ascii_uppercase)
        digit = secrets.choice(string.digits)
        special = secrets.choice('!@#$%^&*()_+-=')

        # Fill the rest randomly
        remaining_length = length - 4
        all_chars = string.ascii_letters + string.digits + '!@#$%^&*()_+-='
        remaining = ''.join(secrets.choice(all_chars) for _ in range(remaining_length))

        # Combine and shuffle
        password_chars = list(lower + upper + digit + special + remaining)
        secrets.SystemRandom().shuffle(password_chars)

        password = ''.join(password_chars)
        logger.info(f"Generated {length}-char password")
        return password

    def _trigger_backup(self):
        """Trigger S3 backup after credential changes."""
        if not BACKUP_SCRIPT_PATH.exists():
            logger.warning(f"Backup script not found: {BACKUP_SCRIPT_PATH}")
            return

        try:
            result = subprocess.run(
                [sys.executable, str(BACKUP_SCRIPT_PATH), '--backup'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                logger.info("S3 backup triggered successfully")
            else:
                logger.warning(f"S3 backup returned non-zero: {result.stderr[:200]}")

        except subprocess.TimeoutExpired:
            logger.warning("S3 backup timed out (30s)")
        except Exception as e:
            logger.warning(f"S3 backup trigger failed: {e}")

    def list_sites(self) -> list:
        """List all stored service/site names."""
        try:
            sys.path.insert(0, str(OPENCLAW_PROJECT_ROOT))

            from src.credential_store import CredentialStore
            from src.auth import get_master_password_from_keyring
            import os

            master_password = (
                get_master_password_from_keyring() or
                os.environ.get("OPENCLAW_MASTER_PASSWORD")
            )

            if not master_password:
                return []

            store = CredentialStore(master_password=master_password)
            creds = store.list()
            store.close()

            return [
                {
                    'service': c.get('service'),
                    'username': c.get('username'),
                    'tier': c.get('tier'),
                }
                for c in creds
            ]

        except Exception as e:
            logger.error(f"Failed to list sites: {e}")
            return []

        finally:
            if str(OPENCLAW_PROJECT_ROOT) in sys.path:
                sys.path.remove(str(OPENCLAW_PROJECT_ROOT))
