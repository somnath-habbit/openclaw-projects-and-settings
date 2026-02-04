"""Ollama local provider for AI decision engine."""
import json
import logging
import requests

from detached_flows.ai_decision.providers.base import BaseProvider

logger = logging.getLogger("OllamaProvider")

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


class OllamaProvider(BaseProvider):
    """
    Ollama local model provider.

    Runs AI models locally using Ollama. 100% free, no API keys needed.
    Recommended models:
    - phi3:mini (3.8B, very fast, excellent reasoning)
    - llama3.2:3b (3B, Meta's latest)
    - qwen2.5:7b (7B, best quality in this size)
    - mistral:7b (7B, classic choice)

    Setup:
        curl -fsSL https://ollama.com/install.sh | sh
        ollama pull phi3:mini
        ollama serve  # Starts on localhost:11434
    """

    def __init__(
        self, model: str = "phi3:mini", endpoint: str = "http://localhost:11434"
    ):
        """
        Initialize Ollama provider.

        Args:
            model: Ollama model name (e.g., phi3:mini, llama3.2:3b)
            endpoint: Ollama server endpoint
        """
        self.model = model
        self.endpoint = endpoint.rstrip("/")

        # Verify Ollama is running
        try:
            response = requests.get(f"{self.endpoint}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name") for m in models]
                logger.info(
                    f"Ollama provider initialized with model: {model} (available: {model_names})"
                )

                # Warn if model not found
                if model not in model_names:
                    logger.warning(
                        f"Model '{model}' not found. Run: ollama pull {model}"
                    )
            else:
                logger.warning(
                    f"Ollama server responded with status {response.status_code}"
                )
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"Could not connect to Ollama at {self.endpoint}: {e}. Make sure Ollama is running."
            )

    async def analyze(
        self, screenshot_b64: str, a11y_snapshot: str, context: dict, goal: str
    ) -> dict:
        """
        Analyze page state using Ollama local model.

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
            # Call Ollama API
            response = requests.post(
                f"{self.endpoint}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                        "num_predict": 300,
                    },
                },
                timeout=120,  # Longer timeout for local inference
            )

            # Check for errors
            if response.status_code != 200:
                error_msg = response.text
                logger.error(f"Ollama API error ({response.status_code}): {error_msg}")
                return {
                    "action": "skip",
                    "reason": f"Ollama API error: {response.status_code}",
                    "confidence": 0.0,
                }

            # Parse response
            result = response.json()

            # Ollama response format: {"response": "...", "model": "...", ...}
            raw = result.get("response", "")

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

            logger.info(f"Ollama decision: {action_dict}")
            return action_dict

        except requests.exceptions.ConnectionError:
            logger.error(
                f"Could not connect to Ollama at {self.endpoint}. Is Ollama running?"
            )
            return {
                "action": "skip",
                "reason": "Ollama server not available",
                "confidence": 0.0,
            }
        except requests.exceptions.Timeout:
            logger.error("Ollama API request timed out")
            return {
                "action": "skip",
                "reason": "Ollama timeout (model might be slow)",
                "confidence": 0.0,
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API request failed: {e}")
            return {
                "action": "skip",
                "reason": f"Request error: {e}",
                "confidence": 0.0,
            }
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Ollama response as JSON: {e}")
            logger.error(f"Raw response: {raw if 'raw' in locals() else 'N/A'}")
            return {
                "action": "skip",
                "reason": f"JSON parse error: {e}",
                "confidence": 0.0,
            }
        except Exception as e:
            logger.error(f"Ollama provider error: {e}")
            return {
                "action": "skip",
                "reason": f"Provider error: {e}",
                "confidence": 0.0,
            }
