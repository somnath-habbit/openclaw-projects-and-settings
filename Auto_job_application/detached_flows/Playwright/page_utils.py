"""Page interaction utilities with human-like timing per scraping strategy."""
import random
import asyncio
from playwright.async_api import Page


async def human_delay(min_s: float, max_s: float):
    """Random delay in the specified range."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def nav_delay():
    """3-12s navigation delay per SCRAPING_STRATEGY_AND_SCHEDULE.md."""
    await human_delay(3, 12)


async def typing_delay():
    """2-6s typing delay."""
    await human_delay(2, 6)


async def page_load_delay():
    """10-20s page load delay."""
    await human_delay(10, 20)


async def get_accessibility_snapshot(page: Page) -> str:
    """Get accessibility tree as formatted text (mirrors OpenClaw ARIA)."""
    tree = await page.accessibility.snapshot()
    return format_a11y_tree(tree) if tree else ""


def format_a11y_tree(node, indent=0) -> str:
    """Recursively format accessibility tree into readable text."""
    if node is None:
        return ""

    lines = []
    prefix = "  " * indent
    role = node.get("role", "")
    name = node.get("name", "")
    value = node.get("value", "")

    if name:
        lines.append(f'{prefix}{role} "{name}"')
    elif value:
        lines.append(f"{prefix}{role}: {value}")
    elif role:
        lines.append(f"{prefix}{role}")

    for child in node.get("children", []):
        child_text = format_a11y_tree(child, indent + 1)
        if child_text:
            lines.append(child_text)

    return "\n".join(lines)


async def extract_text_content(page: Page) -> str:
    """Get all visible text from the page."""
    return await page.evaluate("() => document.body.innerText")


async def click_by_text(page: Page, text: str, timeout: int = 5000) -> bool:
    """Click an element containing the given text."""
    try:
        await page.click(f"text={text}", timeout=timeout)
        return True
    except Exception:
        return False


async def type_into(page: Page, locator: str, text: str):
    """Type text with per-character delays to mimic human typing."""
    element = page.locator(locator).first
    await element.click()
    await element.type(text, delay=random.randint(30, 80))
