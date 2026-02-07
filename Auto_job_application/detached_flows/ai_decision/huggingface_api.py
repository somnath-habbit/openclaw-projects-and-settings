"""
HuggingFace Pro API integration for Qwen3 model.
Uses existing HF Pro subscription - no additional cost.
"""
import requests
import os
import logging

logger = logging.getLogger(__name__)

# HuggingFace API endpoint
HF_API_URL = "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-72B-Instruct"


def get_hf_token() -> str:
    """Get HuggingFace API token from environment."""
    token = os.getenv('HUGGINGFACE_API_KEY') or os.getenv('HF_TOKEN')
    if not token:
        raise ValueError("HuggingFace API token not found. Set HUGGINGFACE_API_KEY or HF_TOKEN environment variable.")
    return token


def call_huggingface_api(prompt: str, max_tokens: int = 512, timeout: int = 30) -> str:
    """
    Call HuggingFace Inference API with Qwen3 model.

    Uses HuggingFace Pro subscription - faster inference, no rate limits.
    """
    token = get_hf_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature": 0.7,
            "top_p": 0.9,
            "do_sample": True,
            "return_full_text": False
        }
    }

    try:
        response = requests.post(
            HF_API_URL,
            headers=headers,
            json=payload,
            timeout=timeout
        )

        response.raise_for_status()

        data = response.json()

        # HF API returns array of generated texts
        if isinstance(data, list) and len(data) > 0:
            generated_text = data[0].get("generated_text", "").strip()
            logger.info(f"HuggingFace API response ({len(generated_text)} chars)")
            return generated_text

        logger.warning("HuggingFace API returned unexpected format")
        return ""

    except requests.exceptions.Timeout:
        logger.error(f"HuggingFace API timed out after {timeout}s")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"HuggingFace API request failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response: {e.response.text[:500]}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error calling HuggingFace API: {e}")
        raise


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Testing HuggingFace API call...")

    # Check for token
    try:
        token = get_hf_token()
        print(f"✅ HF Token found: {token[:20]}...")
    except ValueError as e:
        print(f"❌ {e}")
        print("\nTo use HuggingFace API, set your token:")
        print("  export HUGGINGFACE_API_KEY='hf_your_token_here'")
        exit(1)

    try:
        response = call_huggingface_api("What is 2+2? Answer with just the number.")
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")
