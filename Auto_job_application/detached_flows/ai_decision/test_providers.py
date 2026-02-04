#!/usr/bin/env python3
"""Test script for AI providers — verifies providers can be initialized and return valid responses."""
import asyncio
import json
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ProviderTest")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from detached_flows.ai_decision.providers.huggingface_provider import (
    HuggingFaceProvider,
)
from detached_flows.ai_decision.providers.ollama_provider import OllamaProvider


# Mock data for testing
MOCK_A11Y_SNAPSHOT = """
Document "LinkedIn Login"
  Heading "Welcome back"
  TextBox "Email or phone" (value: "")
  TextBox "Password" (value: "")
  Button "Sign in"
  Link "Forgot password?"
"""

MOCK_CONTEXT = {
    "user_email": "test@example.com",
    "goal": "Log into LinkedIn",
    "session": "test_session",
}

MOCK_SCREENSHOT_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


async def test_huggingface_provider():
    """Test HuggingFace provider initialization and error handling."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing HuggingFace Provider")
    logger.info("=" * 60)

    # Test without API key (should fail gracefully)
    try:
        provider = HuggingFaceProvider(api_key="", model="Qwen/Qwen2.5-72B-Instruct")
        logger.error("Should have raised ValueError for missing API key")
    except ValueError as e:
        logger.info(f"✓ Correctly raised error for missing API key: {e}")

    # Test with fake API key (will fail on actual request, but tests initialization)
    try:
        provider = HuggingFaceProvider(
            api_key="hf_fake_key_for_testing", model="Qwen/Qwen2.5-72B-Instruct"
        )
        logger.info(f"✓ Provider initialized with model: {provider.model}")
        logger.info(f"✓ Endpoint: {provider.endpoint}")

        # Test analyze method (will fail due to fake key, but tests error handling)
        result = await provider.analyze(
            screenshot_b64=MOCK_SCREENSHOT_B64,
            a11y_snapshot=MOCK_A11Y_SNAPSHOT,
            context=MOCK_CONTEXT,
            goal="Log into LinkedIn",
        )

        logger.info(f"✓ Provider returned error response: {result}")
        assert result["action"] == "skip", "Should return skip action on API error"
        assert "confidence" in result, "Should include confidence in response"

    except Exception as e:
        logger.error(f"✗ Unexpected error: {e}")
        raise


async def test_ollama_provider():
    """Test Ollama provider initialization and error handling."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Ollama Provider")
    logger.info("=" * 60)

    # Test with default settings (will warn if Ollama not running)
    try:
        provider = OllamaProvider(model="phi3:mini", endpoint="http://localhost:11434")
        logger.info(f"✓ Provider initialized with model: {provider.model}")
        logger.info(f"✓ Endpoint: {provider.endpoint}")

        # Test analyze method (will fail if Ollama not running, but tests error handling)
        result = await provider.analyze(
            screenshot_b64=MOCK_SCREENSHOT_B64,
            a11y_snapshot=MOCK_A11Y_SNAPSHOT,
            context=MOCK_CONTEXT,
            goal="Log into LinkedIn",
        )

        # If Ollama is running and has the model, we'll get a real response
        if result["action"] != "skip":
            logger.info(f"✓ Ollama is running and returned: {result}")
        else:
            logger.info(f"✓ Provider returned error response (Ollama not available): {result}")

        assert "action" in result, "Should include action in response"
        assert "confidence" in result, "Should include confidence in response"

    except Exception as e:
        logger.error(f"✗ Unexpected error: {e}")
        raise


async def test_json_parsing():
    """Test JSON parsing with different response formats."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing JSON Parsing")
    logger.info("=" * 60)

    test_cases = [
        # Plain JSON
        '{"action": "click", "target": "Sign in", "confidence": 0.9}',
        # JSON with code fence
        '```json\n{"action": "type", "target": "Email", "text": "test@example.com", "confidence": 0.95}\n```',
        # JSON with text before
        'Here is the action:\n{"action": "wait", "reason": "Page loading", "confidence": 0.7}',
        # JSON with explanation after
        '{"action": "skip", "reason": "CAPTCHA detected", "confidence": 1.0}\nThis is because...',
    ]

    for i, raw_response in enumerate(test_cases, 1):
        logger.info(f"\nTest case {i}:")
        logger.info(f"Raw: {raw_response[:50]}...")

        try:
            # Simulate the parsing logic from providers
            raw = raw_response.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            if not raw.startswith("{"):
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start >= 0 and end > start:
                    raw = raw[start:end]

            parsed = json.loads(raw)
            logger.info(f"✓ Parsed: {parsed}")
            assert "action" in parsed, "Should have action field"

        except Exception as e:
            logger.error(f"✗ Failed to parse: {e}")


async def main():
    """Run all tests."""
    logger.info("Starting provider tests...")

    try:
        await test_json_parsing()
        await test_huggingface_provider()
        await test_ollama_provider()

        logger.info("\n" + "=" * 60)
        logger.info("All tests completed!")
        logger.info("=" * 60)
        logger.info(
            """
Next steps:
1. Set HUGGINGFACE_API_KEY in .env to test HuggingFace provider
   Get key from: https://huggingface.co/settings/tokens

2. Install and run Ollama to test local provider:
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull phi3:mini
   ollama serve

3. Set AI_PROVIDER in .env to choose provider:
   - openclaw (default, uses OAuth)
   - huggingface (requires HUGGINGFACE_API_KEY)
   - anthropic (requires ANTHROPIC_API_KEY)
   - ollama (requires Ollama running locally)
"""
        )

    except Exception as e:
        logger.error(f"Test suite failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
