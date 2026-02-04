"""Action schema for AI decision engine responses."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class AIAction:
    """Represents an action the AI can take on a page."""

    action: str  # click | type | select | wait | skip | screenshot_again
    target: Optional[str] = None  # Description of the target element
    coordinates: Optional[list[int]] = None  # [x, y] for click actions
    text: Optional[str] = None  # Text to type for 'type' actions
    reason: str = ""  # Mandatory explanation
    confidence: float = 0.0  # 0.0-1.0 self-reported confidence

    def is_actionable(self) -> bool:
        """Check if this action should be executed (confidence >= 0.5 and not skip/wait)."""
        return self.confidence >= 0.5 and self.action not in ("skip", "wait")
