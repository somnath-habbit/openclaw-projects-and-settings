"""Anthropic Claude provider for AI decision engine."""
import json
import logging

from detached_flows.ai_decision.providers.base import BaseProvider
from detached_flows.config import ANTHROPIC_API_KEY

logger = logging.getLogger("AnthropicProvider")

ACTION_PROMPT = """You are controlling a web browser to automate a task on LinkedIn. Analyze the screenshot and accessibility tree below, then decide the next action.

Current goal: {goal}

Context about the user:
{context_json}

Accessibility snapshot (first 3000 chars):
{a11y_snapshot}

Rules:
- You can ONLY return one of these actions: click, type, select, wait, skip, screenshot_again
- For 'click': provide coordinates [x, y] or a target description
- For 'type': provide the text to type and the target element description
- If you see a CAPTCHA or SMS verification, return 'skip' — we cannot automate these
- If the page is still loading, return 'wait'
- Never hallucinate credential values — only type values from the provided context
- confidence must reflect how certain you are (0.0 to 1.0)

Respond with ONLY valid JSON matching this schema:
{{
  "action": "click|type|select|wait|skip|screenshot_again",
  "target": "description of element",
  "coordinates": [x, y],
  "text": "text to type",
  "reason": "why this action",
  "confidence": 0.0-1.0
}}"""


class AnthropicProvider(BaseProvider):
    """Claude-based AI provider."""

    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set")

        try:
            import anthropic

            self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        except ImportError:
            raise ImportError(
                "anthropic package not installed. Run: pip install anthropic"
            )

    async def analyze(
        self, screenshot_b64: str, a11y_snapshot: str, context: dict, goal: str
    ) -> dict:
        prompt = ACTION_PROMPT.format(
            goal=goal,
            context_json=json.dumps(context, indent=2),
            a11y_snapshot=a11y_snapshot[:3000],  # Truncate if very long
        )

        message = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        raw = message.content[0].text.strip()

        # Extract JSON from response (strip code fences if present)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        return json.loads(raw)
