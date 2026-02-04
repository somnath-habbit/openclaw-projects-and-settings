"""HuggingFace Inference API provider for AI decision engine."""
import json
import logging
import requests

from detached_flows.ai_decision.providers.base import BaseProvider

logger = logging.getLogger("HuggingFaceProvider")

ACTION_PROMPT = """You are controlling a web browser to automate a task on LinkedIn. Based on the information provided, decide the next action.

Current goal: {goal}

Context about the user:
{context_json}

Current page state (accessibility tree):
{a11y_snapshot}

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


class HuggingFaceProvider(BaseProvider):
    """
    HuggingFace Inference API provider.

    Uses serverless inference API for cost-effective AI decisions.
    Recommended models:
    - Qwen/Qwen2.5-72B-Instruct (best quality)
    - mistralai/Mixtral-8x7B-Instruct-v0.1 (fast)
    - meta-llama/Llama-3.1-70B-Instruct (excellent balance)

    Pricing: Free tier available, $2/month for higher rate limits.
    """

    def __init__(self, api_key: str, model: str = "Qwen/Qwen2.5-72B-Instruct"):
        """
        Initialize HuggingFace provider.

        Args:
            api_key: HuggingFace API token
            model: Model ID on HuggingFace Hub
        """
        if not api_key:
            raise ValueError("HuggingFace API key is required")

        self.api_key = api_key
        self.model = model
        # Updated endpoint (api-inference.huggingface.co is deprecated)
        self.endpoint = f"https://router.huggingface.co/models/{model}"

        logger.info(f"HuggingFace provider initialized with model: {model}")

    async def analyze(
        self, screenshot_b64: str, a11y_snapshot: str, context: dict, goal: str
    ) -> dict:
        """
        Analyze page state using HuggingFace Inference API.

        Args:
            screenshot_b64: Base64-encoded screenshot (not used - text-only)
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

        try:
            # Call HuggingFace Inference API
            response = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "inputs": prompt,
                    "parameters": {
                        "max_new_tokens": 300,
                        "temperature": 0.3,
                        "top_p": 0.9,
                        "return_full_text": False,
                    },
                },
                timeout=60,
            )

            # Check for errors
            if response.status_code != 200:
                error_msg = response.text
                logger.error(f"HuggingFace API error ({response.status_code}): {error_msg}")

                # Check for model loading
                if response.status_code == 503:
                    logger.warning("Model is loading, please retry in a few seconds")
                    return {
                        "action": "wait",
                        "reason": "Model is loading on HuggingFace",
                        "confidence": 0.5,
                    }

                return {
                    "action": "skip",
                    "reason": f"API error: {response.status_code}",
                    "confidence": 0.0,
                }

            # Parse response
            result = response.json()

            # HuggingFace response format: [{"generated_text": "..."}]
            if isinstance(result, list) and len(result) > 0:
                raw = result[0].get("generated_text", "")
            else:
                raw = str(result)

            # Extract JSON from response (strip code fences if present)
            raw = raw.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            # Try to find JSON in the response if not at the start
            if not raw.startswith("{"):
                # Look for the first { and last }
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start >= 0 and end > start:
                    raw = raw[start:end]

            # Parse the action JSON
            action_dict = json.loads(raw)

            logger.info(f"HuggingFace decision: {action_dict}")
            return action_dict

        except requests.exceptions.Timeout:
            logger.error("HuggingFace API request timed out")
            return {
                "action": "skip",
                "reason": "API timeout",
                "confidence": 0.0,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"HuggingFace API request failed: {e}")
            return {
                "action": "skip",
                "reason": f"Request error: {e}",
                "confidence": 0.0,
            }
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse HuggingFace response as JSON: {e}")
            logger.error(f"Raw response: {raw if 'raw' in locals() else 'N/A'}")
            return {
                "action": "skip",
                "reason": f"JSON parse error: {e}",
                "confidence": 0.0,
            }
        except Exception as e:
            logger.error(f"HuggingFace provider error: {e}")
            return {
                "action": "skip",
                "reason": f"Provider error: {e}",
                "confidence": 0.0,
            }
