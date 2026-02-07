"""Playwright browser session manager with anti-detection and session persistence."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page

from detached_flows.config import SESSIONS_DIR, BROWSER_HEADLESS

SESSION_FILE = SESSIONS_DIR / "linkedin_session.json"

# Anti-detection browser args
ANTI_DETECTION_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=TranslateUI",
    "--disable-ipc-sandboxing",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--lang=en-US,en",
]

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"


class BrowserSession:
    """Manages a Playwright browser with session persistence."""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def launch(self):
        """Launch browser and restore session if available."""
        self.playwright = await async_playwright().start()
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

        storage_state = str(SESSION_FILE) if SESSION_FILE.exists() else None

        self.browser = await self.playwright.chromium.launch(
            headless=BROWSER_HEADLESS,
            args=ANTI_DETECTION_ARGS,
        )

        self.context = await self.browser.new_context(
            user_agent=USER_AGENT,
            storage_state=storage_state,
            viewport={"width": 1280, "height": 720},
        )

        # Disable webdriver detection via JS injection
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        self.page = await self.context.new_page()
        return self.page

    async def save_session(self):
        """Save current session state (cookies, localStorage) to disk."""
        if self.context:
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            await self.context.storage_state(path=str(SESSION_FILE))

    async def close(self):
        """Close browser and cleanup resources."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    @property
    def has_session(self) -> bool:
        """Check if a persisted session file exists."""
        return SESSION_FILE.exists()

    def is_alive(self) -> bool:
        """Check if browser, context, and page are still alive."""
        try:
            if not (self.browser and self.context and self.page):
                return False
            # Check if page is closed
            if self.page.is_closed():
                return False
            return True
        except Exception:
            return False

    async def restart(self):
        """Restart the browser session (close and relaunch)."""
        await self.close()
        await self.launch()
        return self.page
