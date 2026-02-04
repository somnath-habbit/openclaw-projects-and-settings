"""Decision engine — orchestrates AI-powered page interaction decisions."""
import logging
import asyncio
from pathlib import Path

from detached_flows.ai_decision.action_schema import AIAction
from detached_flows.ai_decision.context_builder import build_context
from detached_flows.ai_decision.providers.base import BaseProvider
from detached_flows.config import (
    AI_PROVIDER,
    ANTHROPIC_API_KEY,
    HUGGINGFACE_API_KEY,
    HUGGINGFACE_MODEL,
    OLLAMA_ENDPOINT,
    OLLAMA_MODEL,
)

logger = logging.getLogger("DecisionEngine")


def _get_provider() -> BaseProvider | None:
    """Get the configured AI provider. Returns None if no provider available."""

    # Try OpenClaw agent first (uses OAuth, no API key needed)
    if AI_PROVIDER == "openclaw":
        try:
            from detached_flows.ai_decision.providers.openclaw_provider import (
                OpenClawProvider,
            )
            logger.info("Using OpenClaw local agent (OAuth-based)")
            return OpenClawProvider()
        except Exception as e:
            logger.warning(f"OpenClaw provider not available: {e}")

    # HuggingFace Inference API
    if AI_PROVIDER == "huggingface" and HUGGINGFACE_API_KEY:
        try:
            from detached_flows.ai_decision.providers.huggingface_provider import (
                HuggingFaceProvider,
            )
            logger.info(f"Using HuggingFace provider with model: {HUGGINGFACE_MODEL}")
            return HuggingFaceProvider(
                api_key=HUGGINGFACE_API_KEY, model=HUGGINGFACE_MODEL
            )
        except Exception as e:
            logger.warning(f"Failed to initialize HuggingFace provider: {e}")

    # Anthropic API
    if AI_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        try:
            from detached_flows.ai_decision.providers.anthropic_provider import (
                AnthropicProvider,
            )
            logger.info("Using Anthropic API provider")
            return AnthropicProvider()
        except Exception as e:
            logger.warning(f"Failed to initialize Anthropic provider: {e}")

    # Ollama local model
    if AI_PROVIDER == "ollama":
        try:
            from detached_flows.ai_decision.providers.ollama_provider import (
                OllamaProvider,
            )
            logger.info(f"Using Ollama provider with model: {OLLAMA_MODEL}")
            return OllamaProvider(model=OLLAMA_MODEL, endpoint=OLLAMA_ENDPOINT)
        except Exception as e:
            logger.warning(f"Failed to initialize Ollama provider: {e}")

    # Fallback: try OpenClaw if no specific provider worked
    if AI_PROVIDER not in ["openclaw", "huggingface", "anthropic", "ollama"]:
        try:
            from detached_flows.ai_decision.providers.openclaw_provider import (
                OpenClawProvider,
            )
            logger.info(
                f"Unknown provider '{AI_PROVIDER}', falling back to OpenClaw agent"
            )
            return OpenClawProvider()
        except Exception as e:
            logger.warning(f"OpenClaw fallback not available: {e}")

    logger.warning(
        f"No AI provider available (configured: {AI_PROVIDER}, keys: "
        f"HF={bool(HUGGINGFACE_API_KEY)}, Anthropic={bool(ANTHROPIC_API_KEY)})"
    )
    return None


class DecisionEngine:
    """AI decision engine for handling unexpected page states."""

    def __init__(self):
        self.provider = _get_provider()

    @property
    def available(self) -> bool:
        """Check if an AI provider is available."""
        return self.provider is not None

    async def decide(self, page, goal: str, job_id: int | None = None) -> AIAction:
        """
        Take a screenshot, build context, ask AI, return action.

        Args:
            page: Playwright Page object
            goal: Current task description
            job_id: Optional job ID for context

        Returns:
            AIAction object
        """
        if not self.provider:
            logger.warning("AI provider not available. Returning skip.")
            return AIAction(
                action="skip", reason="No AI provider configured", confidence=0.0
            )

        # Screenshot
        screenshot_path = "/tmp/ai_decision_screenshot.png"
        await page.screenshot(path=screenshot_path)
        screenshot_b64 = BaseProvider.image_to_b64(screenshot_path)

        # Accessibility snapshot
        tree = await page.accessibility.snapshot()
        from detached_flows.Playwright.page_utils import format_a11y_tree

        a11y_text = format_a11y_tree(tree) if tree else ""

        # Context
        context = build_context(goal=goal, job_id=job_id)

        # Call provider
        try:
            raw = await self.provider.analyze(screenshot_b64, a11y_text, context, goal)
            action = AIAction(
                action=raw.get("action", "skip"),
                target=raw.get("target"),
                coordinates=raw.get("coordinates"),
                text=raw.get("text"),
                reason=raw.get("reason", ""),
                confidence=raw.get("confidence", 0.0),
            )
        except Exception as e:
            logger.error(f"AI provider error: {e}")
            action = AIAction(
                action="skip", reason=f"Provider error: {e}", confidence=0.0
            )

        logger.info(f"AI decision: {action}")
        return action

    async def execute_action(self, page, action: AIAction) -> bool:
        """
        Execute the action on the page. Returns True if executed.

        Args:
            page: Playwright Page object
            action: AIAction to execute

        Returns:
            True if action was executed, False otherwise
        """
        if not action.is_actionable():
            logger.info(
                f"Action not actionable: {action.action} (confidence={action.confidence})"
            )
            return False

        try:
            if action.action == "click":
                if action.coordinates:
                    # Click at specific coordinates
                    await page.mouse.click(
                        action.coordinates[0], action.coordinates[1]
                    )
                elif action.target:
                    # Click by text
                    await page.click(f"text={action.target}", timeout=5000)
                return True

            elif action.action == "type":
                if action.target and action.text:
                    locator = page.locator(f"text={action.target}").first
                    await locator.click()
                    await locator.type(action.text)
                    return True

            elif action.action == "screenshot_again":
                return True  # Caller should loop and take another screenshot

            return False

        except Exception as e:
            logger.error(f"Failed to execute action {action.action}: {e}")
            return False
