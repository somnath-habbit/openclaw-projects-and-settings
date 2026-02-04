"""Base provider interface for AI vision models."""
from abc import ABC, abstractmethod
import base64


class BaseProvider(ABC):
    """Abstract base class for AI providers (Anthropic, OpenAI, Gemini, etc.)."""

    @abstractmethod
    async def analyze(
        self, screenshot_b64: str, a11y_snapshot: str, context: dict, goal: str
    ) -> dict:
        """
        Send screenshot + context to AI, return raw action dict.

        Args:
            screenshot_b64: Base64-encoded PNG screenshot
            a11y_snapshot: Accessibility tree as text
            context: User profile + job data
            goal: Current task description

        Returns:
            dict matching AIAction schema (action, target, coordinates, text, reason, confidence)
        """
        pass

    @staticmethod
    def image_to_b64(path: str) -> str:
        """Convert image file to base64 string."""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
