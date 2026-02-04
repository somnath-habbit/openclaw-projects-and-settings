"""LinkedIn login manager — handles authentication and session persistence."""
import asyncio
import logging

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.LoginWrapper.cred_fetcher import fetch_credentials
from detached_flows.Playwright.page_utils import human_delay, page_load_delay
from detached_flows.config import get_linkedin_email

logger = logging.getLogger("LoginManager")


async def ensure_logged_in(session: BrowserSession) -> bool:
    """
    Check if already logged in via session. If not, fetch creds and log in.

    Returns:
        True if logged in successfully, False otherwise.
    """
    page = session.page

    # Navigate to LinkedIn home
    logger.info("Navigating to LinkedIn...")
    await page.goto("https://www.linkedin.com", wait_until="networkidle", timeout=30000)
    await human_delay(2, 4)

    # Check current URL and page content
    current_url = page.url
    page_text = await page.evaluate("() => document.body.innerText")

    # If we're on feed, jobs, or mynetwork → logged in
    if (
        "/feed" in current_url
        or "/mynetwork" in current_url
        or "/jobs" in current_url
    ):
        logger.info("Session valid — already on feed/jobs")
        return True

    # If page has feed elements and no "Sign in" → logged in
    if "Sign in" not in page_text and ("Feed" in page_text or "Search jobs" in page_text):
        logger.info("Already logged in (detected via page content)")
        return True

    # Need to log in
    logger.info("Not logged in — starting login flow")
    return await _do_login(session)


async def _do_login(session: BrowserSession) -> bool:
    """Execute the full login flow."""
    page = session.page

    # Fetch credentials
    linkedin_email = get_linkedin_email()
    if not linkedin_email:
        logger.error("LinkedIn email not found in config or user_profile.json")
        return False

    logger.info(f"Fetching credentials for {linkedin_email}...")
    creds = fetch_credentials("linkedin", linkedin_email)
    if not creds:
        logger.error("Failed to fetch credentials from broker")
        return False

    logger.info("Credentials fetched successfully")

    # Navigate to login page
    await page.goto("https://www.linkedin.com/login", wait_until="networkidle", timeout=30000)
    await human_delay(2, 4)

    # Fill email
    email_input = page.locator(
        'input#username, input[name="session_key"], input[type="email"], input[name="email"]'
    ).first
    if await email_input.count() == 0:
        logger.error("Email input not found on login page")
        await page.screenshot(path="data/screenshots/login_no_email_input.png")
        return False

    await email_input.click()
    await human_delay(0.5, 1.5)
    await email_input.type(creds["username"], delay=60)
    await human_delay(1, 2)

    # Fill password
    password_input = page.locator(
        'input#password, input[name="session_password"], input[type="password"], input[name="password"]'
    ).first
    if await password_input.count() == 0:
        logger.error("Password input not found on login page")
        await page.screenshot(path="data/screenshots/login_no_password_input.png")
        return False

    await password_input.click()
    await human_delay(0.5, 1.5)
    await password_input.type(creds["password"], delay=60)
    await human_delay(1, 2)

    # Click Sign In
    signin_btn = page.locator('button[type="submit"], button:has-text("Sign in")')
    if await signin_btn.count() == 0:
        logger.error("Sign in button not found")
        await page.screenshot(path="data/screenshots/login_no_submit_button.png")
        return False

    await signin_btn.click()
    logger.info("Clicked Sign In, waiting for response...")
    await page_load_delay()  # 10-20s

    # Check result
    current_url = page.url
    page_text = await page.evaluate("() => document.body.innerText")

    # Success indicators
    if "/feed" in current_url or "/mynetwork" in current_url:
        logger.info("Login successful (redirected to feed)")
        await session.save_session()
        return True

    if "Feed" in page_text or "Search jobs" in page_text:
        logger.info("Login successful (feed elements detected)")
        await session.save_session()
        return True

    # Check for verification/captcha
    if "verification" in page_text.lower() or "verify" in page_text.lower():
        logger.warning("Login requires verification (2FA/CAPTCHA)")
        await page.screenshot(path="data/screenshots/login_verification_required.png")
        return False

    if "Sign in" in page_text or "login" in current_url.lower():
        logger.warning("Login failed — still on login page")
        await page.screenshot(path="data/screenshots/login_failed.png")
        return False

    # Unclear state — assume success and save session
    logger.info("Login result unclear — saving session and continuing")
    await session.save_session()
    return True
