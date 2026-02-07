"""
Registration Engine - Automated account registration on job sites.

Handles the full registration flow: navigate to signup page, fill form,
handle verification, save credentials to OpenClaw.

Usage:
    engine = RegistrationEngine(session, profile, cred_manager)
    result = await engine.register("naukri", "user@email.com")
"""
import asyncio
import logging
from typing import Dict, Optional
from pathlib import Path
from dataclasses import dataclass

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.Playwright.page_utils import human_delay, page_load_delay
from detached_flows.ai_decision.page_analyzer import PageAnalyzer, PageType
from detached_flows.ai_decision.action_planner import ActionPlanner, ActionType, Strategy
from detached_flows.ai_decision.universal_form_processor import UniversalFormProcessor
from detached_flows.ai_decision.element_handlers import ElementHandlerRegistry
from detached_flows.LoginWrapper.cred_manager import CredentialManager
from detached_flows.site_registry import SiteRegistry, SiteConfig

logger = logging.getLogger("RegistrationEngine")


@dataclass
class RegistrationResult:
    """Result of a registration attempt."""
    success: bool = False
    site_name: str = ""
    username: str = ""
    needs_verification: bool = False
    verification_type: str = ""  # email, phone, captcha
    error: str = ""
    credentials_saved: bool = False


class RegistrationEngine:
    """
    Automated registration engine for job sites.

    Flow:
    1. Check if already registered (credentials exist)
    2. Navigate to registration page
    3. AI-analyze the page
    4. Fill registration form
    5. Handle verification steps
    6. Save credentials to OpenClaw
    """

    def __init__(
        self,
        session: BrowserSession,
        profile: dict,
        cred_manager: CredentialManager = None,
        site_registry: SiteRegistry = None,
        debug: bool = False,
    ):
        self.session = session
        self.profile = profile
        self.cred_manager = cred_manager or CredentialManager()
        self.site_registry = site_registry or SiteRegistry()
        self.debug = debug

        self.page_analyzer = PageAnalyzer()
        self.action_planner = ActionPlanner(profile, cred_manager)
        self.element_registry = ElementHandlerRegistry()

    async def register(
        self,
        site_name: str,
        email: str = "",
        resume_path: str = "",
    ) -> RegistrationResult:
        """
        Register on a job site.

        Args:
            site_name: Site key (e.g., "naukri", "indeed")
            email: Email to register with (defaults to profile email)
            resume_path: Path to resume file

        Returns:
            RegistrationResult
        """
        result = RegistrationResult(site_name=site_name)

        # Get email from profile if not provided
        if not email:
            email = self.profile.get('profile', {}).get('email', '')

        if not email:
            result.error = "No email provided and none in profile"
            return result

        result.username = email

        # Step 1: Check if already registered
        if self.cred_manager.has_credentials(site_name, email):
            logger.info(f"Already registered on {site_name} with {email}")
            result.success = True
            result.credentials_saved = True
            return result

        # Step 2: Get site config
        site_config = self.site_registry.get(site_name)
        if not site_config:
            site_config = self.site_registry.get_or_create_unknown(site_name)

        # Step 3: Navigate to registration page
        reg_url = site_config.registration_url
        if not reg_url:
            result.error = f"No registration URL known for {site_name}"
            return result

        page = self.session.page
        logger.info(f"Navigating to registration: {reg_url}")

        try:
            await page.goto(reg_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(2, 4)
        except Exception as e:
            result.error = f"Failed to navigate to registration: {e}"
            return result

        # Step 4: Generate password
        password = self.cred_manager.generate_password(length=20)

        # Step 5: Registration form loop (handle multi-page registration)
        max_pages = 10
        for page_num in range(max_pages):
            logger.info(f"Registration page {page_num + 1}...")

            # Analyze current page
            analysis = await self.page_analyzer.analyze(
                page, goal="Register a new account"
            )

            # Handle different page types
            if analysis.page_type == PageType.CONFIRMATION:
                logger.info("Registration confirmed!")
                result.success = True
                break

            if analysis.page_type == PageType.DASHBOARD:
                logger.info("Reached dashboard - registration complete!")
                result.success = True
                break

            if analysis.page_type == PageType.EMAIL_VERIFICATION:
                logger.info("Email verification required")
                result.needs_verification = True
                result.verification_type = "email"
                result.success = True  # Registration succeeded, just needs verification
                break

            if analysis.page_type == PageType.CAPTCHA:
                logger.warning("CAPTCHA detected during registration")
                result.needs_verification = True
                result.verification_type = "captcha"
                result.error = "CAPTCHA needs human intervention"
                break

            if analysis.requires_human:
                result.error = f"Human intervention needed: {analysis.human_reason}"
                break

            # Plan and execute actions
            plan = self.action_planner.plan_actions(
                analysis, goal="Register a new account", site_name=site_name
            )

            if plan.strategy == Strategy.ESCALATE_TO_HUMAN:
                result.error = "Could not determine registration actions"
                break

            # Execute fill actions
            for action in plan.actions:
                try:
                    await self._execute_action(
                        page, analysis, action, email, password
                    )
                except Exception as e:
                    logger.error(f"Action failed: {e}")

            # Wait for page to update
            await asyncio.sleep(2)

            # Check if page changed (detect stuck state)
            new_url = page.url
            new_analysis = await self.page_analyzer.analyze(page)

            if new_analysis.page_type == analysis.page_type and page_num > 2:
                logger.warning("Appears stuck - same page type after multiple attempts")
                result.error = "Registration appears stuck"
                break

        # Step 6: Save credentials if registration succeeded
        if result.success:
            saved = self.cred_manager.store(
                site_name=site_name,
                username=email,
                password=password,
                tier=site_config.credential_tier
            )
            result.credentials_saved = saved

            if saved:
                logger.info(f"Credentials saved for {site_name}/{email}")
            else:
                logger.warning(f"Failed to save credentials for {site_name}")

        # Debug screenshot
        if self.debug:
            try:
                screenshot_path = Path(f"data/screenshots/registration_{site_name}_final.png")
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(screenshot_path))
            except Exception:
                pass

        return result

    async def _execute_action(
        self,
        page,
        analysis,
        action,
        email: str,
        password: str,
    ):
        """Execute a single planned action."""
        elements = analysis.raw_snapshot.get('elements', []) if analysis.raw_snapshot else []

        # Find the target element
        target_el = None
        for el in elements:
            if el['index'] == action.element_index:
                target_el = el
                break

        if not target_el and action.action != ActionType.WAIT:
            logger.warning(f"Element not found for action: index={action.element_index}")
            return

        # Resolve value placeholders
        value = action.value
        if value == '__CREDENTIAL_PASSWORD__':
            value = password

        # Map profile fields for common registration fields
        if not value and target_el:
            label = (target_el.get('label') or '').lower()
            el_type = target_el.get('type', '')

            if el_type == 'email_input' or 'email' in label:
                value = email
            elif el_type == 'password_input' or 'password' in label:
                value = password

        # Execute the action
        if action.action == ActionType.FILL:
            if target_el and value:
                await self.element_registry.fill_element(page, target_el, value)
                await asyncio.sleep(0.3)

        elif action.action == ActionType.SELECT:
            if target_el and value:
                await self.element_registry.fill_element(page, target_el, value)
                await asyncio.sleep(0.3)

        elif action.action == ActionType.CHECK:
            if target_el:
                await self.element_registry.fill_element(page, target_el, 'check')
                await asyncio.sleep(0.2)

        elif action.action == ActionType.CLICK:
            if target_el:
                # Find and click the button
                label = target_el.get('label') or target_el.get('current_value', '')
                attrs = target_el.get('attributes', {})
                selector = attrs.get('selector', '')

                clicked = False
                for sel in [selector, f'button:has-text("{label}")', f'a:has-text("{label}")']:
                    if not sel:
                        continue
                    try:
                        locator = page.locator(sel).first
                        if await locator.count() > 0:
                            await locator.scroll_into_view_if_needed()
                            await asyncio.sleep(0.3)
                            await locator.click()
                            clicked = True
                            break
                    except Exception:
                        continue

                if clicked:
                    logger.info(f"Clicked: {label}")
                    await asyncio.sleep(1)
                else:
                    logger.warning(f"Could not click: {label}")

        elif action.action == ActionType.UPLOAD:
            if target_el and value:
                await self.element_registry.fill_element(page, target_el, value)
                await asyncio.sleep(1)

        elif action.action == ActionType.WAIT:
            await asyncio.sleep(2)
