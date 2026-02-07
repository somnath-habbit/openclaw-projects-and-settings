"""
Universal Apply Bot - Apply to jobs on ANY job site, not just LinkedIn.

This is the main orchestrator for external job applications. It handles
authentication, navigation, multi-page form filling, and submission.

Usage:
    async with UniversalApplyBot(session, profile) as bot:
        result = await bot.apply_to_job(job_url, site_name="naukri")

Architecture:
    UniversalApplyBot
    ├─ LoginEngine (authentication)
    ├─ UniversalFormProcessor (form filling)
    ├─ PageAnalyzer (page understanding)
    └─ CredentialManager (OpenClaw bridge)
"""
import asyncio
import logging
import hashlib
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.Playwright.page_utils import human_delay, page_load_delay
from detached_flows.ai_decision.page_analyzer import PageAnalyzer, PageType
from detached_flows.ai_decision.universal_form_processor import UniversalFormProcessor
from detached_flows.ai_decision.universal_question_handler import UniversalQuestionHandler
from detached_flows.registration.login_engine import LoginEngine
from detached_flows.LoginWrapper.cred_manager import CredentialManager
from detached_flows.site_registry import SiteRegistry
from detached_flows.config import PROFILE_PATH, SCREENSHOTS_DIR, MASTER_PDF

logger = logging.getLogger("UniversalApplyBot")


# Application status codes
class ApplyStatus:
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    LOGIN_FAILED = "LOGIN_FAILED"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    CAPTCHA = "CAPTCHA"
    BROWSER_CRASH = "BROWSER_CRASH"
    STUCK = "STUCK"
    DRY_RUN = "DRY_RUN"  # Filled but not submitted


@dataclass
class ApplicationResult:
    """Result of a job application attempt."""
    status: str = ApplyStatus.FAILED
    job_url: str = ""
    site_name: str = ""
    pages_navigated: int = 0
    fields_filled: int = 0
    errors: List[str] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)
    timestamp: str = ""
    duration_seconds: float = 0
    filled_fields_log: List[Dict] = field(default_factory=list)

    def __repr__(self):
        return (
            f"ApplicationResult(status={self.status}, site={self.site_name}, "
            f"pages={self.pages_navigated}, fields={self.fields_filled})"
        )


class UniversalApplyBot:
    """
    Universal job application bot that works with any job site.

    Features:
    - AI-powered page understanding (no hardcoded selectors)
    - Multi-page form navigation
    - Automatic login/registration
    - Resume upload
    - Validation error retry
    - Stuck detection
    - Screenshot logging
    - Dry-run mode
    """

    def __init__(
        self,
        session: Optional[BrowserSession] = None,
        profile: dict = None,
        debug: bool = False,
        dry_run: bool = False,
    ):
        self.session = session
        self.owns_session = session is None
        self.debug = debug
        self.dry_run = dry_run

        # Load profile
        if profile:
            self.profile = profile
        else:
            self.profile = self._load_profile()

        # Initialize components
        self.cred_manager = CredentialManager()
        self.site_registry = SiteRegistry()
        self.page_analyzer = PageAnalyzer()
        self.question_handler = UniversalQuestionHandler(self.profile)
        self.form_processor = UniversalFormProcessor(
            profile=self.profile,
            question_handler=self.question_handler,
            credential_manager=self.cred_manager,
            debug=debug,
        )

        # Stats
        self.stats = {
            "attempted": 0,
            "submitted": 0,
            "failed": 0,
            "needs_human": 0,
        }

    # ATS platforms that have open application forms (no login required)
    OPEN_FORM_ATS = [
        'greenhouse.io', 'lever.co', 'workday.com', 'myworkdayjobs.com',
        'icims.com', 'smartrecruiters.com', 'jobvite.com', 'bamboohr.com',
        'ashbyhq.com', 'breezy.hr', 'recruitee.com', 'jazz.co',
        'applytojob.com', 'boards.eu.greenhouse.io', 'job-boards.greenhouse.io',
        'jobs.lever.co', 'boards.greenhouse.io',
        'oraclecloud.com', 'taleo.net', 'successfactors.com',
        'peoplestrong.com', 'darwinbox.com', 'zohorecruit.com',
    ]

    @classmethod
    def _is_open_form_ats(cls, url: str) -> bool:
        """Check if URL belongs to an ATS with open application forms (no login)."""
        url_lower = url.lower()
        return any(ats in url_lower for ats in cls.OPEN_FORM_ATS)

    async def __aenter__(self):
        if self.owns_session:
            self.session = BrowserSession()
            await self.session.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.owns_session and self.session:
            await self.session.close()

    def _load_profile(self) -> dict:
        """Load user profile from JSON."""
        import json
        try:
            with open(PROFILE_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load profile: {e}")
            return {}

    async def apply_to_job(
        self,
        job_url: str,
        site_name: str = "",
        job_context: dict = None,
        resume_path: str = "",
    ) -> ApplicationResult:
        """
        Apply to a job on any site.

        Args:
            job_url: Full URL of the job posting
            site_name: Site key (auto-detected from URL if empty)
            job_context: Job details (title, company, etc.)
            resume_path: Path to resume file

        Returns:
            ApplicationResult with status and details
        """
        start_time = datetime.now()
        result = ApplicationResult(
            job_url=job_url,
            site_name=site_name,
            timestamp=start_time.isoformat()
        )

        self.stats["attempted"] += 1
        job_context = job_context or {}
        resume_path = resume_path or str(MASTER_PDF)

        try:
            page = self.session.page

            # Auto-detect site from URL
            if not site_name:
                site_config = self.site_registry.identify_site(job_url)
                if site_config:
                    site_name = site_config.key
                    result.site_name = site_name
                else:
                    # Extract domain as site name
                    from urllib.parse import urlparse
                    domain = urlparse(job_url).netloc.replace('www.', '')
                    site_name = domain.split('.')[0]
                    result.site_name = site_name

            logger.info(f"Applying to job on {site_name}: {job_url[:80]}")

            # ==============================
            # STEP 1: AUTHENTICATE (skip for open ATS forms)
            # ==============================
            if self._is_open_form_ats(job_url):
                logger.info(f"Open-form ATS detected — skipping login for {site_name}")
            else:
                login_engine = LoginEngine(
                    session=self.session,
                    profile=self.profile,
                    cred_manager=self.cred_manager,
                    site_registry=self.site_registry,
                )

                username = self.profile.get('profile', {}).get('email', '')

                logged_in = await login_engine.login_or_register(
                    site_name, username, resume_path
                )

                if not logged_in:
                    result.status = ApplyStatus.LOGIN_FAILED
                    result.errors.append(f"Could not log in to {site_name}")
                    logger.error(f"Login failed for {site_name}")
                    self.stats["failed"] += 1
                    return result

            # ==============================
            # STEP 2: NAVIGATE TO JOB
            # ==============================
            logger.info(f"Navigating to job: {job_url[:80]}")
            await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(2, 4)

            # Analyze job page
            analysis = await self.page_analyzer.analyze(
                page, goal="Find and click Apply button"
            )

            if analysis.page_type == PageType.ERROR:
                result.status = ApplyStatus.NOT_FOUND
                result.errors.append("Job page returned error")
                self.stats["failed"] += 1
                return result

            # ==============================
            # STEP 3: CLICK APPLY BUTTON
            # ==============================
            apply_clicked = await self._find_and_click_apply(page, analysis)

            if not apply_clicked:
                result.status = ApplyStatus.FAILED
                result.errors.append("Could not find Apply button")
                self.stats["failed"] += 1
                return result

            await human_delay(2, 3)

            # ==============================
            # STEP 4: MULTI-PAGE FORM LOOP
            # ==============================
            max_pages = 15
            page_hashes = []

            for page_num in range(max_pages):
                logger.info(f"--- Application Page {page_num + 1} ---")
                result.pages_navigated = page_num + 1

                # Screenshot before processing
                await self._save_screenshot(
                    page, result, f"page_{page_num + 1}_before"
                )

                # Check for stuck state
                current_hash = await self._get_page_hash(page)
                if current_hash in page_hashes:
                    # Before declaring stuck, check for validation errors
                    validation_errors = await self._get_validation_errors(page)
                    if validation_errors:
                        logger.warning(f"Validation errors blocking submit: {validation_errors}")
                        result.errors.extend(validation_errors)
                    # Take full-page screenshot for debugging
                    if self.debug:
                        await self._save_screenshot(page, result, "stuck_fullpage", full_page=True)
                    logger.warning("Stuck detected: same page appeared twice")
                    result.status = ApplyStatus.STUCK
                    result.errors.append("Application loop detected")
                    break
                page_hashes.append(current_hash)

                # Analyze current page
                page_analysis = await self.page_analyzer.analyze(
                    page, goal="Complete job application"
                )

                # Handle special page types
                if page_analysis.page_type == PageType.CONFIRMATION:
                    logger.info("Application CONFIRMED!")
                    result.status = ApplyStatus.SUBMITTED
                    await self._save_screenshot(page, result, "confirmation")
                    break

                if page_analysis.page_type == PageType.CAPTCHA:
                    result.status = ApplyStatus.CAPTCHA
                    result.errors.append("CAPTCHA detected")
                    await self._save_screenshot(page, result, "captcha")
                    break

                # Check for email verification / security code requirement
                if await self._check_verification_needed(page):
                    logger.info("Email verification / security code required — needs human")
                    result.status = ApplyStatus.NEEDS_HUMAN
                    result.errors.append("Email verification code required")
                    await self._save_screenshot(page, result, "verification")
                    break

                if page_analysis.requires_human:
                    # Override: FORM pages are the bot's purpose — never skip them
                    if page_analysis.page_type == PageType.FORM:
                        logger.info(
                            f"requires_human overridden for FORM page "
                            f"(reason was: {page_analysis.human_reason})"
                        )
                        page_analysis.requires_human = False
                    else:
                        result.status = ApplyStatus.NEEDS_HUMAN
                        result.errors.append(page_analysis.human_reason)
                        await self._save_screenshot(page, result, "needs_human")
                        break

                # Check for "already applied" indicators
                if await self._check_already_applied(page):
                    result.status = ApplyStatus.ALREADY_APPLIED
                    logger.info("Already applied to this job")
                    break

                # Check if this is a review page (dry run stops here)
                if page_analysis.page_type == PageType.REVIEW and self.dry_run:
                    logger.info("DRY RUN: Reached review page, stopping before submit")
                    result.status = ApplyStatus.DRY_RUN
                    await self._save_screenshot(page, result, "dry_run_review")
                    break

                # Process the form page
                # Check if there's a modal/dialog
                scope = await self._find_application_scope(page)

                form_result = await self.form_processor.process_form(
                    page=page,
                    scope=scope,
                    goal="Complete job application",
                    site_name=site_name,
                    job_context=job_context,
                    resume_path=resume_path,
                )

                result.fields_filled += form_result.fields_filled
                result.filled_fields_log.extend(form_result.filled_fields)

                if form_result.is_complete:
                    result.status = ApplyStatus.SUBMITTED
                    logger.info("Application SUBMITTED!")
                    await self._save_screenshot(page, result, "submitted")
                    break

                if form_result.requires_human:
                    result.status = ApplyStatus.NEEDS_HUMAN
                    result.errors.append(form_result.human_reason)
                    break

                if not form_result.success and not form_result.moved_to_next:
                    result.errors.extend(form_result.errors)
                    logger.warning(f"Page {page_num + 1} processing failed")
                    # Try to continue anyway
                    if page_num >= 3 and result.fields_filled == 0:
                        result.status = ApplyStatus.FAILED
                        break

                # Wait for next page to load
                await human_delay(1, 2)

                # Screenshot after processing
                await self._save_screenshot(
                    page, result, f"page_{page_num + 1}_after"
                )

            # If we exhausted all pages without confirmation
            if result.status not in (
                ApplyStatus.SUBMITTED, ApplyStatus.DRY_RUN,
                ApplyStatus.ALREADY_APPLIED, ApplyStatus.NEEDS_HUMAN,
                ApplyStatus.CAPTCHA, ApplyStatus.STUCK
            ):
                result.status = ApplyStatus.FAILED
                result.errors.append(f"Exhausted {max_pages} pages without confirmation")

        except Exception as e:
            logger.error(f"Application failed with error: {e}", exc_info=True)
            result.status = ApplyStatus.FAILED
            result.errors.append(str(e))

            # Check for browser crash
            if self._is_browser_closed_error(e):
                result.status = ApplyStatus.BROWSER_CRASH

        # Update stats
        if result.status == ApplyStatus.SUBMITTED:
            self.stats["submitted"] += 1
        elif result.status == ApplyStatus.NEEDS_HUMAN:
            self.stats["needs_human"] += 1
        else:
            self.stats["failed"] += 1

        # Calculate duration
        result.duration_seconds = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"Application result: {result.status} | "
            f"Pages: {result.pages_navigated} | "
            f"Fields: {result.fields_filled} | "
            f"Duration: {result.duration_seconds:.1f}s"
        )

        return result

    async def _find_and_click_apply(self, page, analysis) -> bool:
        """Find and click the Apply button on a job listing page."""

        # Strategy 1: Look for apply buttons in page analysis
        for btn in analysis.buttons:
            label = (btn.get('label') or btn.get('current_value') or '').lower()
            if 'apply' in label and 'don' not in label:
                attrs = btn.get('attributes', {})
                selector = attrs.get('selector', '')

                for sel in [selector, f'button:has-text("{label}")', f'a:has-text("{label}")']:
                    if not sel:
                        continue
                    try:
                        locator = page.locator(sel).first
                        if await locator.count() > 0:
                            await locator.scroll_into_view_if_needed()
                            await asyncio.sleep(0.3)
                            await locator.click()
                            logger.info(f"Clicked apply button: '{label}'")
                            return True
                    except Exception:
                        continue

        # Strategy 2: Common apply button selectors
        apply_selectors = [
            'button:has-text("Apply")',
            'a:has-text("Apply Now")',
            'button:has-text("Apply Now")',
            'a:has-text("Quick Apply")',
            'button:has-text("Quick Apply")',
            '[data-testid*="apply"]',
            '.apply-button',
            '#apply-button',
            'a[href*="apply"]',
        ]

        for selector in apply_selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible():
                    await locator.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
                    await locator.click()
                    logger.info(f"Clicked apply button via selector: {selector}")
                    return True
            except Exception:
                continue

        # Strategy 3: JavaScript fallback
        try:
            clicked = await page.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('button, a');
                    for (const btn of buttons) {
                        const text = btn.innerText?.toLowerCase() || '';
                        if (text.includes('apply') && !text.includes('don')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if clicked:
                logger.info("Clicked apply button via JavaScript fallback")
                return True
        except Exception:
            pass

        logger.warning("Could not find Apply button")
        return False

    async def _find_application_scope(self, page):
        """Check if application form is in a modal/dialog.

        Only returns a scope if the modal actually contains form fields.
        Otherwise returns None so the full page is used.
        """
        modal_selectors = [
            '[role="dialog"]:visible',
            '.modal:visible',
            '[class*="modal"]:visible',
            '[class*="dialog"]:visible',
            '.application-form:visible',
        ]

        for selector in modal_selectors:
            try:
                modal = page.locator(selector).first
                if await modal.count() > 0:
                    # Validate: modal must contain form fields (input/select/textarea)
                    field_count = await modal.locator(
                        'input:visible, select:visible, textarea:visible'
                    ).count()
                    if field_count > 0:
                        logger.info(
                            f"Found application modal: {selector} "
                            f"({field_count} form fields)"
                        )
                        return modal
                    else:
                        logger.debug(
                            f"Skipping {selector} — no form fields inside"
                        )
            except Exception:
                continue

        return None  # No modal, use full page

    async def _check_already_applied(self, page) -> bool:
        """Check if already applied to this job."""
        try:
            text = await page.evaluate(
                "() => document.body?.innerText?.substring(0, 3000) || ''"
            )
            text_lower = text.lower()

            indicators = [
                'already applied',
                'you have applied',
                'application submitted',
                'you applied on',
                'applied on',
            ]

            return any(ind in text_lower for ind in indicators)
        except Exception:
            return False

    async def _get_page_hash(self, page) -> str:
        """Get a hash of the current page state for stuck detection.
        Includes field values so filling changes the hash."""
        try:
            state = await page.evaluate("""
                () => {
                    const inputs = document.querySelectorAll('input, select, textarea');
                    const buttons = document.querySelectorAll('button');
                    const parts = [];
                    inputs.forEach(i => {
                        const key = i.name || i.id || '';
                        const val = i.value?.substring(0, 30) || '';
                        parts.push(key + '=' + val);
                    });
                    buttons.forEach(b => parts.push(b.innerText?.trim()?.substring(0, 20) || ''));
                    // Include URL to detect page navigation
                    return document.location.href + '|' + parts.join('|');
                }
            """)
            return hashlib.md5(state.encode()).hexdigest()
        except Exception:
            return ""

    async def _check_verification_needed(self, page) -> bool:
        """Check if the page requires email/phone verification code."""
        try:
            text = await page.evaluate(
                "() => document.body?.innerText?.substring(0, 5000) || ''"
            )
            text_lower = text.lower()
            indicators = [
                'verification code',
                'security code',
                'confirm you\'re a human',
                'enter the code',
                'code was sent to',
                'verify your email',
                'one-time code',
            ]
            return any(ind in text_lower for ind in indicators)
        except Exception:
            return False

    async def _get_validation_errors(self, page) -> list:
        """Extract validation error messages from the page."""
        try:
            errors = await page.evaluate("""
                () => {
                    const errors = [];
                    // Common error selectors
                    const selectors = [
                        '[class*="error"]:not([style*="display: none"])',
                        '[role="alert"]',
                        '[aria-invalid="true"]',
                        '.field-error', '.form-error', '.validation-error',
                        '[class*="invalid"]',
                        '[id*="error"]',
                    ];
                    for (const sel of selectors) {
                        document.querySelectorAll(sel).forEach(el => {
                            const text = (el.innerText || el.textContent || '').trim();
                            if (text && text.length < 200 && text.length > 2) {
                                errors.push(text.substring(0, 150));
                            }
                        });
                    }
                    // Deduplicate
                    return [...new Set(errors)].slice(0, 10);
                }
            """)
            return errors
        except Exception:
            return []

    async def _save_screenshot(self, page, result: ApplicationResult, label: str, full_page: bool = False):
        """Save a debug screenshot."""
        if not self.debug:
            return

        try:
            site = result.site_name or "unknown"
            timestamp = datetime.now().strftime("%H%M%S")
            filename = f"{site}_{label}_{timestamp}.png"
            filepath = SCREENSHOTS_DIR / site / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)

            await page.screenshot(path=str(filepath), full_page=full_page)
            result.screenshots.append(str(filepath))
            logger.debug(f"Screenshot saved: {filepath}")
        except Exception as e:
            logger.debug(f"Screenshot failed: {e}")

    @staticmethod
    def _is_browser_closed_error(error: Exception) -> bool:
        """Check if error is due to browser/page being closed."""
        error_str = str(error).lower()
        return any(keyword in error_str for keyword in [
            "target page, context or browser has been closed",
            "page has been closed",
            "browser has been closed",
            "connection closed"
        ])
