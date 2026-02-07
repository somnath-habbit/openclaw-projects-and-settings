"""
Direct Claude API integration using SSO token from OpenClaw.
Bypasses the slow `openclaw agent` command for faster responses.
"""
import json
import os
import requests
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to OpenClaw auth profiles
AUTH_PROFILES_PATH = Path.home() / ".openclaw/agents/main/agent/auth-profiles.json"


def get_claude_token() -> str:
    """Get Claude SSO token from OpenClaw auth profiles."""
    try:
        with open(AUTH_PROFILES_PATH, 'r') as f:
            auth_data = json.load(f)

        # Try claude-code-open-claw-token first, then default
        for profile_name in ["anthropic:claude-code-open-claw-token", "anthropic:default"]:
            if profile_name in auth_data.get("profiles", {}):
                token = auth_data["profiles"][profile_name].get("token")
                if token:
                    logger.info(f"Using Claude token from {profile_name}")
                    return token

        # Fallback to environment variable
        token = os.getenv('ANTHROPIC_API_KEY')
        if token:
            logger.info("Using Claude token from environment")
            return token

        raise ValueError("No Claude API token found")

    except Exception as e:
        logger.error(f"Failed to get Claude token: {e}")
        raise


def call_claude_api(prompt: str, max_tokens: int = 1024, timeout: int = 30) -> str:
    """
    Call Claude API directly using SSO token.

    This is much faster than openclaw agent command and uses the same SSO subscription.
    """
    token = get_claude_token()

    headers = {
        "x-api-key": token,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": "claude-sonnet-4-5-20250929",  # Latest Sonnet model
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=timeout
        )

        response.raise_for_status()

        data = response.json()

        # Extract text from response
        if "content" in data and len(data["content"]) > 0:
            text = data["content"][0].get("text", "").strip()
            logger.info(f"Claude API response ({len(text)} chars)")
            return text

        logger.warning("Claude API returned empty response")
        return ""

    except requests.exceptions.Timeout:
        logger.error(f"Claude API timed out after {timeout}s")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Claude API request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response: {e.response.text[:500]}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error calling Claude API: {e}")
        raise


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Testing direct Claude API call...")
    try:
        response = call_claude_api("What is 2+2? Answer with just the number.")
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")
