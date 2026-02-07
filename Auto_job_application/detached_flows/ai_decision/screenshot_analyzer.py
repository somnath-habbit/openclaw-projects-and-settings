"""
AI-powered screenshot analyzer for handling unexpected UI states.

Uses Claude's vision capabilities to analyze screenshots and recommend actions.
"""
import base64
import logging
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger("ScreenshotAnalyzer")


def analyze_screenshot_for_action(screenshot_path: Path, context: str = "") -> Optional[Dict]:
    """
    Analyze a screenshot using Claude vision to determine what action to take.

    Args:
        screenshot_path: Path to screenshot image
        context: Additional context about current state

    Returns:
        Dict with action recommendation:
        {
            'action': 'click' | 'skip' | 'wait',
            'selector': 'button text or description',
            'reasoning': 'why this action',
            'confidence': 0-100
        }
    """
    try:
        # Read and encode screenshot
        with open(screenshot_path, 'rb') as f:
            image_data = base64.standard_b64encode(f.read()).decode('utf-8')

        # Build prompt for Claude
        prompt = f"""You are analyzing a LinkedIn Easy Apply job application screenshot to help automate the process.

**Current Context:**
{context or 'Applying to a job, unexpected modal or UI state appeared'}

**Your Task:**
Analyze this screenshot and determine what action the bot should take to continue the application.

**Look for:**
1. Pop-up modals that need to be closed or have buttons clicked
2. "Old model" vs "New model" selection buttons
3. "Continue" / "Next" / "Submit" buttons
4. Error messages or validation issues
5. Search overlays blocking the form
6. Any other UI elements blocking progress

**Response Format (JSON):**
{{
    "action": "click" | "skip" | "wait" | "close",
    "selector_text": "exact button text to click (or 'none')",
    "selector_type": "button" | "link" | "close_icon" | "overlay",
    "reasoning": "brief explanation of what you see and why this action",
    "confidence": 0-100 (how confident you are this is correct),
    "modal_type": "description of modal if present (or 'none')"
}}

**Important:**
- If you see a modal asking to choose between options, identify which button to click
- If you see "Old" vs "New" model, recommend clicking the button that continues the application
- If you see a search overlay, recommend closing it
- If the form looks ready to proceed, recommend clicking Next/Continue/Submit
- Only respond with the JSON, no other text

Analyze the screenshot and provide your recommendation:"""

        # Call Claude with vision
        from detached_flows.ai_decision.claude_fast import call_claude_fast

        # For vision, we need to use the full Claude API with image support
        # For now, let's use a text-based analysis as a proof of concept
        # TODO: Integrate proper vision API once we set it up

        response = call_claude_fast(prompt, timeout=10)

        # Parse JSON response
        import json
        # Extract JSON from response (might have extra text)
        if '```json' in response:
            response = response.split('```json')[1].split('```')[0]
        elif '```' in response:
            response = response.split('```')[1].split('```')[0]

        response = response.strip()
        result = json.loads(response)

        logger.info(f"AI Analysis: {result['action']} - {result['reasoning']}")
        logger.info(f"Confidence: {result['confidence']}%")

        return result

    except Exception as e:
        logger.error(f"Screenshot analysis failed: {e}")
        return None


def get_click_selector_from_text(button_text: str, selector_type: str = "button") -> list:
    """
    Convert button text description into Playwright selectors.

    Args:
        button_text: Text on the button or description
        selector_type: Type of element (button, link, etc.)

    Returns:
        List of Playwright selectors to try
    """
    selectors = []

    if selector_type == "button":
        # Try various button selectors
        selectors.extend([
            f'button:has-text("{button_text}")',
            f'button[aria-label*="{button_text}"]',
            f'a:has-text("{button_text}")',
            f':text("{button_text}")',
        ])
    elif selector_type == "close_icon":
        selectors.extend([
            '[data-test-modal-close-btn]',
            'button[aria-label*="Dismiss"]',
            'button[aria-label*="Close"]',
            '.artdeco-modal__dismiss',
        ])
    elif selector_type == "link":
        selectors.extend([
            f'a:has-text("{button_text}")',
            f'[role="link"]:has-text("{button_text}")',
        ])

    return selectors


# Example usage for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python screenshot_analyzer.py <screenshot_path>")
        sys.exit(1)

    screenshot = Path(sys.argv[1])
    if not screenshot.exists():
        print(f"Screenshot not found: {screenshot}")
        sys.exit(1)

    result = analyze_screenshot_for_action(screenshot, "Testing screenshot analysis")

    if result:
        print(f"\nAnalysis Result:")
        print(f"  Action: {result['action']}")
        print(f"  Selector: {result.get('selector_text', 'N/A')}")
        print(f"  Reasoning: {result['reasoning']}")
        print(f"  Confidence: {result['confidence']}%")

        if result['action'] == 'click':
            selectors = get_click_selector_from_text(
                result['selector_text'],
                result.get('selector_type', 'button')
            )
            print(f"\nGenerated selectors:")
            for sel in selectors:
                print(f"  - {sel}")
    else:
        print("Analysis failed")
