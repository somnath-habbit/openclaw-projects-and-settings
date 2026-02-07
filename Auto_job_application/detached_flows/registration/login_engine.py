"""
Login Engine - Universal login handler for any job site.

Generalizes the LinkedIn-specific login_manager.py to work with any site
using AI page analysis instead of hardcoded selectors.

Usage:
    engine = LoginEngine(session, profile, cred_manager)
    logged_in = await engine.ensure_logged_in("naukri", "user@email.com")
"""
import asyncio
import logging
from typing import Optional
from pathlib import Path

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.Playwright.page_utils import human_delay, page_load_delay
from detached_flows.ai_decision.page_analyzer import PageAnalyzer, PageType
from detached_flows.ai_decision.action_planner import ActionPlanner, ActionType
from detached_flows.ai_decision.element_handlers import ElementHandlerRegistry
from detached_flows.LoginWrapper.cred_manager import CredentialManager
from detached_flows.site_registry import SiteRegistry

logger = logging.getLogger("LoginEngine")


class LoginEngine:
    """
    Universal login engine that can log into any job site.

    Based on the pattern from login_manager.py but uses AI page analysis
    instead of hardcoded CSS selectors for site-agnostic operation.
    """

    def __init__(
        self,
        session: BrowserSession,
        profile: dict,
        cred_manager: CredentialManager = None,
        site_registry: SiteRegistry = None,
    ):
        self.session = session
        self.profile = profile
        self.cred_manager = cred_manager or CredentialManager()
        self.site_registry = site_registry or SiteRegistry()

        self.page_analyzer = PageAnalyzer()
        self.action_planner = ActionPlanner(profile, cred_manager)
        self.element_registry = ElementHandlerRegistry()

    async def ensure_logged_in(
        self,
        site_name: str,
        username: str = "",
    ) -> bool:
        """
        Check if logged in, and log in if not.

        Args:
            site_name: Site key (e.g., "naukri", "indeed")
            username: Email/username (defaults to profile email)

        Returns:
            True if logged in successfully
        """
        page = self.session.page

        if not username:
            username = self.profile.get('profile', {}).get('email', '')

        site_config = self.site_registry.get(site_name)
        if not site_config:
            site_config = self.site_registry.get_or_create_unknown(site_name)

        # Check if already logged in
        if await self._is_logged_in(page, site_config):
            logger.info(f"Already logged in to {site_name}")
            return True

        # Need to log in
        logger.info(f"Not logged in to {site_name} - starting login flow")
        return await self._do_login(page, site_config, username)

    async def _is_logged_in(self, page, site_config) -> bool:
        """
        Check if currently logged in to the site.

        Uses AI page analysis rather than hardcoded URL/content checks.
        """
        try:
            # Navigate to the site's base URL
            await page.goto(
                site_config.base_url,
                wait_until="domcontentloaded",
                timeout=30000
            )
            await human_delay(2, 4)

            current_url = page.url

            # Quick heuristic checks first (avoid AI call if obvious)
            # Check for common dashboard/logged-in URL patterns
            logged_in_patterns = ['/feed', '/dashboard', '/home', '/profile', '/myjobs', '/myapply']
            if any(pattern in current_url for pattern in logged_in_patterns):
                logger.info(f"Logged in (URL pattern match): {current_url[:80]}")
                return True

            # Check for common login URL patterns (means NOT logged in)
            login_patterns = ['/login', '/signin', '/auth', '/signup']
            if any(pattern in current_url for pattern in login_patterns):
                return False

            # Use page analysis for ambiguous cases
            analysis = await self.page_analyzer.analyze(
                page, goal="Check if logged in", use_ai=False
            )

            if analysis.page_type == PageType.DASHBOARD:
                return True
            if analysis.page_type == PageType.LOGIN:
                return False

            # Check page content for logged-in indicators
            page_text = await page.evaluate("() => document.body?.innerText?.substring(0, 2000) || ''")
            page_text_lower = page_text.lower()

            # Logged-in indicators
            logged_in_indicators = [
                'my profile', 'my applications', 'my jobs', 'dashboard',
                'notification', 'messages', 'settings', 'logout', 'sign out'
            ]
            logged_in_score = sum(1 for ind in logged_in_indicators if ind in page_text_lower)

            # Not-logged-in indicators
            not_logged_indicators = ['sign in', 'log in', 'create account', 'register']
            not_logged_score = sum(1 for ind in not_logged_indicators if ind in page_text_lower)

            return logged_in_score > not_logged_score

        except Exception as e:
            logger.error(f"Login check failed: {e}")
            return False

    async def _do_login(self, page, site_config, username: str) -> bool:
        """Execute the full login flow."""

        # Get credentials from OpenClaw
        creds = self.cred_manager.fetch(site_config.key, username)
        if not creds:
            logger.error(f"No credentials found for {site_config.key}/{username}")
            return False

        logger.info(f"Credentials fetched for {site_config.key}/{username}")

        # Navigate to login page
        login_url = site_config.login_url or f"{site_config.base_url}/login"

        try:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(2, 4)
        except Exception as e:
            logger.error(f"Failed to navigate to login page: {e}")
            return False

        # Check if we got redirected (already logged in)
        current_url = page.url
        logged_in_patterns = ['/feed', '/dashboard', '/home', '/profile']
        if any(pattern in current_url for pattern in logged_in_patterns):
            logger.info("Already logged in (redirected from login page)")
            await self.session.save_session()
            return True

        # Analyze the login page
        analysis = await self.page_analyzer.analyze(
            page, goal="Log in to account"
        )

        if analysis.page_type == PageType.CAPTCHA:
            logger.warning("CAPTCHA on login page - needs human intervention")
            return False

        # Fill login form
        max_attempts = 3
        for attempt in range(max_attempts):
            logger.info(f"Login attempt {attempt + 1}/{max_attempts}")

            # Find and fill email/username field
            email_filled = False
            password_filled = False

            for field_el in analysis.form_fields:
                field_type = field_el.get('type', '')
                label = (field_el.get('label') or '').lower()

                if field_type == 'email_input' or 'email' in label or 'username' in label:
                    success = await self.element_registry.fill_element(
                        page, field_el, creds['username']
                    )
                    email_filled = success
                    await asyncio.sleep(0.5)

                elif field_type == 'password_input' or 'password' in label:
                    success = await self.element_registry.fill_element(
                        page, field_el, creds['password']
                    )
                    password_filled = success
                    await asyncio.sleep(0.5)

            if not email_filled or not password_filled:
                logger.warning(f"Could not fill login form (email={email_filled}, pw={password_filled})")
                if attempt < max_attempts - 1:
                    # Re-analyze page
                    analysis = await self.page_analyzer.analyze(page, goal="Log in")
                    continue
                return False

            # Check "Remember me" if available
            for field_el in analysis.form_fields:
                if field_el.get('type') == 'checkbox':
                    label = (field_el.get('label') or '').lower()
                    if any(kw in label for kw in ['remember', 'keep me', 'stay signed']):
                        await self.element_registry.fill_element(page, field_el, 'check')

            # Click sign in button
            clicked = False
            if analysis.primary_action:
                btn = analysis.primary_action
                label = btn.get('label') or btn.get('current_value', '')
                attrs = btn.get('attributes', {})
                selector = attrs.get('selector', '')

                for sel in [selector, f'button:has-text("{label}")', '[type="submit"]']:
                    if not sel:
                        continue
                    try:
                        locator = page.locator(sel).first
                        if await locator.count() > 0:
                            await locator.click()
                            clicked = True
                            break
                    except Exception:
                        continue

            if not clicked:
                # Fallback: find any submit button
                try:
                    submit = page.locator('[type="submit"]:visible, button:has-text("Sign in"):visible, button:has-text("Log in"):visible').first
                    if await submit.count() > 0:
                        await submit.click()
                        clicked = True
                except Exception:
                    pass

            if not clicked:
                logger.error("Could not find/click login button")
                if attempt < max_attempts - 1:
                    continue
                return False

            logger.info("Clicked login button, waiting for response...")
            await page_load_delay()

            # Check result
            if await self._verify_login_success(page, site_config):
                logger.info(f"Login successful for {site_config.key}")
                await self.session.save_session()
                return True

            # Check for specific issues
            post_analysis = await self.page_analyzer.analyze(page)

            if post_analysis.page_type == PageType.CAPTCHA:
                logger.warning("CAPTCHA after login attempt")
                return False

            if post_analysis.page_type == PageType.EMAIL_VERIFICATION:
                logger.warning("2FA/verification required")
                return False

            # Still on login page - credentials might be wrong
            if post_analysis.page_type == PageType.LOGIN:
                logger.warning("Still on login page - credentials may be incorrect")
                if attempt < max_attempts - 1:
                    # Re-analyze for error messages
                    if post_analysis.errors_visible:
                        logger.error(f"Login errors: {post_analysis.errors_visible}")
                    analysis = post_analysis
                    continue

        logger.error(f"Login failed after {max_attempts} attempts for {site_config.key}")
        return False

    async def _verify_login_success(self, page, site_config) -> bool:
        """Verify that login was successful."""
        current_url = page.url

        # URL-based check
        logged_in_patterns = ['/feed', '/dashboard', '/home', '/profile', '/myjobs']
        if any(pattern in current_url for pattern in logged_in_patterns):
            return True

        # Still on login page = failure
        login_patterns = ['/login', '/signin', '/auth']
        if any(pattern in current_url for pattern in login_patterns):
            return False

        # Content-based check
        try:
            page_text = await page.evaluate(
                "() => document.body?.innerText?.substring(0, 2000) || ''"
            )
            page_text_lower = page_text.lower()

            logged_in_count = sum(1 for ind in [
                'my profile', 'dashboard', 'notifications',
                'messages', 'logout', 'sign out', 'my jobs'
            ] if ind in page_text_lower)

            not_logged_count = sum(1 for ind in [
                'sign in', 'log in', 'create account'
            ] if ind in page_text_lower)

            return logged_in_count > not_logged_count

        except Exception:
            # Can't determine - assume success if not on login page
            return '/login' not in current_url and '/signin' not in current_url

    async def login_or_register(
        self,
        site_name: str,
        email: str = "",
        resume_path: str = "",
    ) -> bool:
        """
        Ensure access to a site: try login first, register if no credentials exist.

        Args:
            site_name: Site key
            email: Email/username
            resume_path: Resume path (for registration if needed)

        Returns:
            True if logged in (either via login or after registration)
        """
        if not email:
            email = self.profile.get('profile', {}).get('email', '')

        # Try login first
        if self.cred_manager.has_credentials(site_name, email):
            if await self.ensure_logged_in(site_name, email):
                return True
            logger.warning(f"Login failed for {site_name}, credentials may be outdated")

        # No credentials or login failed - try registration
        from detached_flows.registration.registration_engine import RegistrationEngine

        reg_engine = RegistrationEngine(
            session=self.session,
            profile=self.profile,
            cred_manager=self.cred_manager,
            site_registry=self.site_registry,
        )

        reg_result = await reg_engine.register(site_name, email, resume_path)

        if reg_result.success and reg_result.credentials_saved:
            # Now try logging in with the new credentials
            if reg_result.needs_verification:
                logger.info(f"Registration needs {reg_result.verification_type} verification")
                return False

            return await self.ensure_logged_in(site_name, email)

        logger.error(f"Could not access {site_name}: {reg_result.error}")
        return False
