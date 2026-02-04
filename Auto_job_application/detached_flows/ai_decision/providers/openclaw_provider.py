"""OpenClaw agent provider for AI decision engine — uses local agent with OAuth."""
import json
import logging
import subprocess
import tempfile
from pathlib import Path

from detached_flows.ai_decision.providers.base import BaseProvider

logger = logging.getLogger("OpenClawProvider")

ACTION_PROMPT = """You are controlling a web browser to automate a task on LinkedIn. Based on the information provided, decide the next action.

Current goal: {goal}

Context about the user:
{context_json}

Current page state (accessibility tree):
{a11y_snapshot}

Screenshot has been captured and is available for your analysis.

Rules:
- You can ONLY return one of these actions: click, type, select, wait, skip
- For 'click': provide the target element description
- For 'type': provide the text to type and the target element description
- If you see a CAPTCHA or SMS verification, return 'skip' — we cannot automate these
- If the page is still loading, return 'wait'
- Never hallucinate credential values — only type values from the provided context
- confidence must reflect how certain you are (0.0 to 1.0)

Respond with ONLY valid JSON matching this exact schema (no other text):
{{
  "action": "click|type|select|wait|skip",
  "target": "description of element",
  "text": "text to type (if action is type)",
  "reason": "why this action",
  "confidence": 0.0-1.0
}}"""


class OpenClawProvider(BaseProvider):
    """
    OpenClaw local agent provider.

    Uses 'openclaw agent --local' which runs Claude using your OAuth session.
    No API key needed.

    Model selection: The model used is whatever is configured in OpenClaw.
    To set the model:
        openclaw models set sonnet    # Recommended for speed/quality balance
        openclaw models set haiku     # Faster, cheaper for simple decisions

    Note: Currently uses text-only (accessibility snapshot).
    Vision support via --media would require async messaging flow.
    """

    def __init__(self):
        # Verify openclaw is available
        try:
            result = subprocess.run(
                ["openclaw", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise RuntimeError("openclaw CLI not available")
            logger.info(f"OpenClaw provider initialized: {result.stdout.strip()}")

            # Show current model (for debugging)
            model_result = subprocess.run(
                ["openclaw", "models", "status", "--status-json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if model_result.returncode == 0:
                try:
                    model_info = json.loads(model_result.stdout)
                    current_model = model_info.get("model", "unknown")
                    logger.info(f"Using OpenClaw model: {current_model}")
                except:
                    pass

        except Exception as e:
            raise RuntimeError(f"Failed to initialize OpenClaw provider: {e}")

    async def analyze(
        self, screenshot_b64: str, a11y_snapshot: str, context: dict, goal: str
    ) -> dict:
        """
        Analyze page state using OpenClaw local agent.

        Args:
            screenshot_b64: Base64-encoded screenshot (currently not used - text-only analysis)
            a11y_snapshot: Accessibility tree as text
            context: User profile + job data
            goal: Current task description

        Returns:
            dict matching AIAction schema
        """
        # Build the prompt
        prompt = ACTION_PROMPT.format(
            goal=goal,
            context_json=json.dumps(context, indent=2),
            a11y_snapshot=a11y_snapshot[:2000],  # Truncate to avoid token limits
        )

        # Save screenshot to temp file for potential future use
        # (OpenClaw messaging API could support this, but agent --local doesn't)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            screenshot_path = f.name
            import base64
            f.write(base64.b64decode(screenshot_b64))

        logger.debug(f"Screenshot saved to {screenshot_path}")

        # Call openclaw agent --local
        try:
            result = subprocess.run(
                [
                    "openclaw",
                    "agent",
                    "--local",
                    "--message",
                    prompt,
                    "--json",
                    "--thinking",
                    "low",  # Minimal thinking for faster responses
                ],
                capture_output=True,
                text=True,
                timeout=60,  # 60s timeout for agent response
            )

            if result.returncode != 0:
                logger.error(f"OpenClaw agent failed: {result.stderr}")
                raise RuntimeError(f"Agent error: {result.stderr}")

            # Parse JSON response
            response = json.loads(result.stdout)

            # OpenClaw agent response structure:
            # { "message": "...", "thinking": "...", "usage": {...} }
            agent_message = response.get("message", "")

            # Extract JSON from the message
            raw = agent_message.strip()

            # Handle code fences
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            # Parse the action JSON
            action_dict = json.loads(raw)

            logger.info(f"OpenClaw agent decision: {action_dict}")
            return action_dict

        except subprocess.TimeoutExpired:
            logger.error("OpenClaw agent timed out")
            return {
                "action": "skip",
                "reason": "Agent timeout",
                "confidence": 0.0,
            }
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse agent response: {e}")
            logger.error(f"Raw response: {result.stdout if 'result' in locals() else 'N/A'}")
            return {
                "action": "skip",
                "reason": f"JSON parse error: {e}",
                "confidence": 0.0,
            }
        except Exception as e:
            logger.error(f"OpenClaw agent error: {e}")
            return {
                "action": "skip",
                "reason": f"Agent error: {e}",
                "confidence": 0.0,
            }
        finally:
            # Clean up temp screenshot
            try:
                Path(screenshot_path).unlink()
            except:
                pass
