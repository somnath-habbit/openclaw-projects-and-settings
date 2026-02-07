"""
Fast Claude API integration using pi-ai library (same as OpenClaw).

This bypasses the slow `openclaw agent` subprocess by calling the pi-ai library
directly with the OAuth token. Response time: ~1-2s instead of 30s timeouts.
"""
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to our Node.js wrapper script
CLAUDE_PI_AI_SCRIPT = Path(__file__).parent / "claude_pi_ai.mjs"


def call_claude_fast(prompt: str, max_tokens: int = 1024, timeout: int = 15) -> str:
    """
    Call Claude API using pi-ai library with OAuth token.

    This is MUCH faster than openclaw subprocess:
    - openclaw agent: 10-30s (often times out)
    - this method: 1-3s

    Args:
        prompt: The prompt to send to Claude
        max_tokens: Maximum tokens in response (not enforced yet)
        timeout: Timeout in seconds

    Returns:
        Claude's response text

    Raises:
        subprocess.TimeoutExpired: If call takes longer than timeout
        RuntimeError: If Claude API call fails
    """
    try:
        result = subprocess.run(
            ['node', str(CLAUDE_PI_AI_SCRIPT), prompt],
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Unknown error"
            raise RuntimeError(f"Claude API call failed: {error_msg}")

        response = result.stdout.strip()

        if not response:
            logger.warning("Claude returned empty response")
            return ""

        logger.info(f"Claude response ({len(response)} chars)")
        return response

    except subprocess.TimeoutExpired:
        logger.error(f"Claude API timed out after {timeout}s")
        raise
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        raise


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Testing fast Claude API integration...")
    try:
        response = call_claude_fast("What is 2+2? Answer with just the number.")
        print(f"Response: {response}")
        assert "4" in response, "Expected response to contain '4'"
        print("✅ Test passed!")
    except Exception as e:
        print(f"❌ Test failed: {e}")
