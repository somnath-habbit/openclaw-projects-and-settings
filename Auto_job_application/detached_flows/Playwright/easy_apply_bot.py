"""
Easy Apply Bot - Automates LinkedIn Easy Apply process.

Handles:
- Click "Easy Apply" button
- Navigate multi-step forms
- Fill form fields (with AI assistance)
- Upload resume
- Submit application

Usage:
    from easy_apply_bot import EasyApplyBot

    async with EasyApplyBot(session) as bot:
        result = await bot.apply_to_job(job_url, resume_path)
"""
import asyncio
import logging
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.Playwright.page_utils import human_delay, page_load_delay
from detached_flows.config import SCREENSHOTS_DIR, MASTER_PDF
from detached_flows.ai_decision.question_handler import QuestionHandler
from detached_flows.ai_decision.form_batch_processor import FormBatchProcessor
from detached_flows.ai_decision.screenshot_analyzer import analyze_screenshot_for_action, get_click_selector_from_text

logger = logging.getLogger("EasyApplyBot")


class EasyApplyBot:
    """
    Automates LinkedIn Easy Apply applications.

    Features:
    - Multi-step form navigation
    - AI-assisted question answering
    - Resume upload
    - Application tracking
    """

    def __init__(
        self,
        session: Optional[BrowserSession] = None,
        debug: bool = False,
        dry_run: bool = False,
        use_ai: bool = True
    ):
        """
        Initialize Easy Apply bot.

        Args:
            session: Optional BrowserSession to reuse
            debug: Enable debug screenshots
            dry_run: If True, don't actually submit applications
            use_ai: Use AI for answering form questions
        """
        self.session = session
        self.owns_session = session is None
        self.debug = debug
        self.dry_run = dry_run
        self.use_ai = use_ai
        self.stats = {
            "attempted": 0,
            "submitted": 0,
            "failed": 0,
            "skipped": 0,
        }

        # Initialize question handler for AI-powered form filling
        self.question_handler = QuestionHandler(use_ai=use_ai)

        # Current job context (set when applying)
        self.job_context = {}

    async def __aenter__(self):
        """Context manager entry."""
        if self.owns_session:
            self.session = BrowserSession()
            await self.session.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.owns_session and self.session:
            await self.session.close()

    @staticmethod
    def _is_browser_closed_error(error: Exception) -> bool:
        """Check if error is due to browser/page being closed."""
        error_str = str(error).lower()
        return any(keyword in error_str for keyword in [
            "target page, context or browser has been closed",
            "page has been closed",
            "browser has been closed",
            "context or browser",
            "connection closed"
        ])

    async def _recover_from_browser_crash(self, job_url: str) -> bool:
        """
        Attempt to recover from browser crash by restarting session.

        Returns:
            True if recovery successful, False otherwise
        """
        try:
            logger.warning("Browser crashed - attempting recovery...")

            # Restart browser session
            if self.session:
                await self.session.restart()
                logger.info("Browser restarted successfully")

                # Re-navigate to job page
                await self.session.page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                await page_load_delay()
                logger.info(f"Navigated back to {job_url}")

                return True
        except Exception as e:
            logger.error(f"Browser recovery failed: {e}")
            return False

    async def apply_to_job(
        self,
        job_url: str,
        resume_path: Optional[str] = None,
        external_id: Optional[str] = None,
        job_context: Optional[dict] = None
    ) -> dict:
        """
        Apply to a job using Easy Apply.

        Args:
            job_url: URL of the job to apply to
            resume_path: Path to resume PDF (uses MASTER_PDF if not provided)
            external_id: LinkedIn job ID for tracking
            job_context: Optional dict with job_title, company, location for AI

        Returns:
            dict with keys: success, status, error, steps_completed
        """
        if not self.session:
            raise RuntimeError("Session not initialized. Use as context manager.")

        resume_path = resume_path or str(MASTER_PDF)
        external_id = external_id or job_url.split("/")[-2]

        # Set job context for question handler
        self.job_context = job_context or {}
        self.job_context['external_id'] = external_id
        self.job_context['job_url'] = job_url

        logger.info(f"Applying to job {external_id}")
        self.stats["attempted"] += 1

        result = {
            "success": False,
            "status": "PENDING",
            "error": None,
            "steps_completed": 0,
            "external_id": external_id,
            "job_url": job_url,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # Navigate to job page
            await self.session.page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            await page_load_delay()

            # Take screenshot
            if self.debug:
                await self._screenshot(f"apply_{external_id}_1_initial")

            # Check if Easy Apply is available
            easy_apply_button = await self._find_easy_apply_button()
            if not easy_apply_button:
                logger.warning(f"No Easy Apply button found for {external_id}")
                result["status"] = "NO_EASY_APPLY"
                result["error"] = "Easy Apply button not found"
                self.stats["skipped"] += 1
                return result

            # Click Easy Apply (unless already clicked via JS)
            if easy_apply_button != "JS_CLICKED":
                await easy_apply_button.click()

            # Wait longer for modal to appear (LinkedIn modals can be slow + anti-detection)
            logger.info("Waiting for Easy Apply modal to open...")
            await human_delay(5, 8)

            if self.debug:
                await self._screenshot(f"apply_{external_id}_2_modal_opened")

            # Process multi-step form
            steps_completed = 0
            max_steps = 10  # Safety limit
            unfilled_fields_count = 0  # Track consecutive steps with unfilled required fields
            previous_page_hash = None  # Track if we're stuck on the same page

            while steps_completed < max_steps:
                # Check for modal/form with longer timeout
                modal = await self._find_application_modal()
                if not modal:
                    # Wait a bit more and retry once
                    await human_delay(2, 3)
                    modal = await self._find_application_modal()
                    if not modal:
                        logger.info("No application modal found - may be complete or not opened")
                        break

                # Early check: if Submit button visible immediately, we're done filling
                # (This handles single-page applications)
                if await self._has_submit_button():
                    logger.info("Submit button found - attempting to submit")

                    has_errors = await self._check_validation_errors()
                    if has_errors:
                        logger.warning("Validation errors detected before submission")
                        # Continue to fill form below
                    else:
                        # No errors, attempt submission
                        if self.dry_run:
                            logger.info("[DRY RUN] Would submit application here")
                            result["status"] = "DRY_RUN_COMPLETE"
                            result["success"] = True
                            self.stats["submitted"] += 1
                            break

                        submitted = await self._submit_application()
                        if submitted:
                            result["status"] = "SUBMITTED"
                            result["success"] = True
                            self.stats["submitted"] += 1
                        else:
                            result["status"] = "SUBMIT_FAILED"
                            result["error"] = "Failed to submit application"
                            self.stats["failed"] += 1
                        break

                # Detect if we're stuck on the same page
                current_page_hash = await self._get_page_hash()
                if previous_page_hash and current_page_hash == previous_page_hash:
                    unfilled_fields_count += 1
                    logger.warning(f"Same page detected ({unfilled_fields_count}/3) - may be stuck")

                    if unfilled_fields_count >= 3:
                        logger.error("Stuck on same page after 3 attempts - giving up")
                        await self._screenshot(f"apply_{external_id}_stuck")
                        result["status"] = "STUCK_ON_FORM"
                        result["error"] = "Unable to progress through form - required fields may not be fillable"
                        self.stats["failed"] += 1
                        break
                else:
                    unfilled_fields_count = 0  # Reset counter if we progressed

                previous_page_hash = current_page_hash

                # Fill current step (scoped to modal)
                step_result = await self._fill_current_step(resume_path, modal)

                if not step_result["success"]:
                    result["status"] = "FORM_ERROR"
                    result["error"] = step_result.get("error", "Failed to fill form")
                    self.stats["failed"] += 1
                    break

                # Take screenshot before clicking Next (to see button state)
                await self._screenshot(f"apply_{external_id}_before_next_{steps_completed}")

                # Click Next/Continue/Review with retry logic for validation errors
                next_clicked = False
                retry_attempts = 0
                max_retries = 3

                while not next_clicked and retry_attempts < max_retries:
                    next_clicked = await self._click_next_button()

                    if not next_clicked:
                        # Check if we failed due to validation errors
                        has_validation_errors = await self._check_validation_errors()

                        if has_validation_errors and retry_attempts < max_retries - 1:
                            logger.warning(f"Validation errors detected, attempting to fill missing fields (attempt {retry_attempts + 1}/{max_retries})")

                            # Re-scan and fill missing fields on current page
                            refill_result = await self._fill_current_step(resume_path, modal)
                            if refill_result["success"]:
                                logger.info("Re-filled missing fields, retrying button click...")
                                retry_attempts += 1
                                await human_delay(1, 2)
                                continue
                            else:
                                logger.warning("Failed to re-fill missing fields")
                                break
                        else:
                            # No validation errors, or max retries exceeded
                            break

                if not next_clicked:
                    logger.warning("Could not find Next button - checking if we're on final page")
                    await self._screenshot(f"apply_{external_id}_no_next_button")

                    # Check if we're on the final review/submit page
                    if await self._is_review_page():
                        logger.info("Detected review/submit page after Next button not found")

                        # Check for validation errors
                        has_errors = await self._check_validation_errors()
                        if has_errors:
                            logger.error("Validation errors on final page - cannot submit after retries")
                            result["status"] = "VALIDATION_ERROR"
                            result["error"] = "Required fields not filled after multiple attempts"
                            self.stats["failed"] += 1
                            break

                        # Attempt submission
                        if self.dry_run:
                            logger.info("[DRY RUN] Would submit application here")
                            result["status"] = "DRY_RUN_COMPLETE"
                            result["success"] = True
                            self.stats["submitted"] += 1
                        else:
                            submitted = await self._submit_application()
                            if submitted:
                                result["status"] = "SUBMITTED"
                                result["success"] = True
                                self.stats["submitted"] += 1
                            else:
                                result["status"] = "SUBMIT_FAILED"
                                result["error"] = "Failed to submit application"
                                self.stats["failed"] += 1
                    break

                steps_completed += 1
                result["steps_completed"] = steps_completed

                await human_delay(1, 2)

                if self.debug:
                    await self._screenshot(f"apply_{external_id}_step_{steps_completed + 2}")

            return result

        except Exception as e:
            # Check if error is due to browser crash
            if self._is_browser_closed_error(e):
                logger.error(f"Browser closed while applying to {external_id}: {e}")

                # Attempt recovery
                recovered = await self._recover_from_browser_crash(job_url)

                if recovered:
                    # Retry application after recovery
                    logger.info(f"Retrying application to {external_id} after browser recovery...")
                    try:
                        # Recursive retry (only once to avoid infinite loop)
                        retry_result = await self.apply_to_job(
                            job_url=job_url,
                            resume_path=resume_path,
                            external_id=external_id,
                            job_context=job_context
                        )
                        # Adjust stats (avoid double counting)
                        self.stats["attempted"] -= 1
                        return retry_result
                    except Exception as retry_error:
                        logger.error(f"Retry failed after browser recovery: {retry_error}")
                        result["status"] = "BROWSER_CRASH"
                        result["error"] = f"Browser crashed and retry failed: {str(retry_error)}"
                else:
                    result["status"] = "BROWSER_CRASH_RECOVERY_FAILED"
                    result["error"] = f"Browser crashed and recovery failed: {str(e)}"
            else:
                # Regular error (not browser crash)
                logger.error(f"Error applying to {external_id}: {e}")
                result["status"] = "ERROR"
                result["error"] = str(e)

            self.stats["failed"] += 1

            if self.debug:
                await self._screenshot(f"apply_{external_id}_error")

            return result

    async def _find_easy_apply_button(self):
        """Find the Easy Apply button on the page."""
        page = self.session.page

        # Wait for page to settle
        await human_delay(2, 3)

        # First, wait for any of these key elements to appear
        try:
            await page.wait_for_selector(
                '.jobs-unified-top-card, .jobs-details, .job-details-jobs-unified-top-card',
                timeout=10000
            )
            logger.debug("Job details container loaded")
        except Exception as e:
            logger.debug(f"Timeout waiting for job details: {e}")

        # Method 1: Find button by aria-label containing "Easy Apply"
        # LinkedIn uses aria-label="Easy Apply to this job"
        try:
            button = page.locator('button[aria-label*="Easy Apply"]').first
            if await button.is_visible(timeout=5000):
                logger.info("Found Easy Apply button via aria-label")
                return button
        except Exception as e:
            logger.debug(f"aria-label selector failed: {e}")

        # Method 2: Find button by data-view-name attribute
        try:
            button = page.locator('button[data-view-name="job-apply-button"]').first
            if await button.is_visible(timeout=3000):
                logger.info("Found Easy Apply button via data-view-name")
                return button
        except Exception as e:
            logger.debug(f"data-view-name selector failed: {e}")

        # Method 3: Find the parent button of span containing "Easy Apply"
        try:
            span = page.get_by_text("Easy Apply", exact=True).first
            if await span.is_visible(timeout=2000):
                # Get the closest button ancestor using evaluate
                button_handle = await span.evaluate_handle("""
                    el => {
                        let parent = el.parentElement;
                        while (parent && parent.tagName !== 'BUTTON') {
                            parent = parent.parentElement;
                        }
                        return parent;
                    }
                """)
                if button_handle:
                    # Convert handle to locator
                    button = page.locator('button[aria-label*="Easy Apply"]').first
                    if await button.is_visible(timeout=1000):
                        logger.info("Found Easy Apply button via span parent traversal")
                        return button
        except Exception as e:
            logger.debug(f"span ancestor method failed: {e}")

        # Method 4: Use Playwright's get_by_role with partial name match
        try:
            button = page.get_by_role("button", name="Easy Apply to this job")
            if await button.is_visible(timeout=3000):
                logger.info("Found Easy Apply button via get_by_role (full name)")
                return button
        except Exception as e:
            logger.debug(f"get_by_role with full name failed: {e}")

        # Method 5: Try various CSS selectors
        selectors = [
            'button:has-text("Easy Apply")',
            '.jobs-apply-button--top-card button',
            'button.jobs-apply-button',
            '.jobs-s-apply button',
        ]

        for selector in selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=2000):
                    logger.info(f"Found Easy Apply button with selector: {selector}")
                    return button
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue

        # Method 6: Scan all buttons by aria-label
        try:
            all_buttons = await page.locator('button').all()
            logger.debug(f"Scanning {len(all_buttons)} buttons for Easy Apply")
            for btn in all_buttons:
                try:
                    aria = await btn.get_attribute("aria-label") or ""
                    if "Easy Apply" in aria:
                        if await btn.is_visible():
                            logger.info(f"Found Easy Apply button via aria scan: {aria[:50]}")
                            return btn
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Button scan failed: {e}")

        # Method 7: Use JavaScript to find and return the button element
        try:
            button_found = await page.evaluate("""
                () => {
                    // Try to find by aria-label
                    let btn = document.querySelector('button[aria-label*="Easy Apply"]');
                    if (btn) return true;

                    // Try to find button containing "Easy Apply" text
                    const buttons = document.querySelectorAll('button');
                    for (const b of buttons) {
                        if (b.innerText.includes('Easy Apply')) {
                            return true;
                        }
                    }

                    // Try all elements with aria-label
                    const allWithAria = document.querySelectorAll('[aria-label*="Easy Apply"]');
                    if (allWithAria.length > 0) return true;

                    return false;
                }
            """)
            if button_found:
                logger.info("JavaScript found Easy Apply element, trying to click...")
                # Click using JavaScript
                clicked = await page.evaluate("""
                    () => {
                        let btn = document.querySelector('button[aria-label*="Easy Apply"]');
                        if (!btn) {
                            const allWithAria = document.querySelectorAll('[aria-label*="Easy Apply"]');
                            btn = allWithAria[0];
                        }
                        if (btn) {
                            btn.click();
                            return true;
                        }
                        return false;
                    }
                """)
                if clicked:
                    logger.info("Clicked Easy Apply via JavaScript")
                    # Return a dummy locator (we've already clicked)
                    return "JS_CLICKED"
        except Exception as e:
            logger.debug(f"JavaScript method failed: {e}")

        # Log page state for debugging
        try:
            page_text = await page.evaluate("() => document.body.innerText.substring(0, 500)")
            logger.warning(f"Page content preview: {page_text[:200]}...")
        except Exception:
            pass

        return None

    async def _find_application_modal(self):
        """Find the Easy Apply modal/dialog."""
        selectors = [
            'div[role="dialog"]',
            '.jobs-easy-apply-modal',
            'div[data-test-modal]',
            '.artdeco-modal',
        ]

        for selector in selectors:
            try:
                modal = self.session.page.locator(selector).first
                if await modal.is_visible(timeout=5000):  # Increased from 2s to 5s
                    return modal
            except Exception:
                continue

        return None

    async def _has_submit_button(self) -> bool:
        """Quick check if Submit button is visible."""
        submit_selectors = [
            'button:has-text("Submit application")',
            'button:has-text("Submit")',
            'button:has-text("Send application")',
            'button[aria-label*="Submit"]',
        ]

        for selector in submit_selectors:
            try:
                if await self.session.page.locator(selector).is_visible(timeout=500):
                    return True
            except Exception:
                continue
        return False

    async def _is_review_page(self) -> bool:
        """Check if we're on the review/submit page."""
        # ONLY check for actual Submit button - all text-based indicators cause false positives
        # LinkedIn shows similar text on multiple pages
        submit_button_selectors = [
            'button:has-text("Submit application")',
            'button:has-text("Submit")',
            'button:has-text("Send application")',
            'button[aria-label*="Submit"]',
            'button[aria-label*="Send application"]',
        ]

        for selector in submit_button_selectors:
            try:
                element = self.session.page.locator(selector).first
                if await element.is_visible(timeout=1000):
                    logger.info(f"Review page detected via Submit button: {selector}")
                    return True
            except Exception:
                continue

        # Additional heuristic: Check progress indicator (LinkedIn shows percentage)
        # Review page is typically at high percentage (80%+) and has "Review" button
        try:
            # Check if we're at high progress (near completion)
            progress_text = await self.session.page.locator('text=/\\d+%/').first.inner_text(timeout=500)
            if progress_text:
                progress = int(progress_text.replace('%', ''))
                if progress >= 80:  # Only consider review page if we're at 80%+ progress
                    has_review_btn = await self.session.page.locator('button:has-text("Review")').is_visible(timeout=500)
                    if has_review_btn:
                        logger.debug(f"Review page detected: {progress}% complete with Review button")
                        return True
        except Exception:
            pass

        # Fallback heuristic: If we see "Review" button AND "Back" button AND
        # NO empty required fields, we're likely on the final review page
        try:
            has_review_btn = await self.session.page.locator('button:has-text("Review")').is_visible(timeout=500)
            has_back_btn = await self.session.page.locator('button:has-text("Back")').is_visible(timeout=500)
            has_next_btn = await self.session.page.locator('button:has-text("Next"), button:has-text("Continue")').is_visible(timeout=500)

            if has_review_btn and has_back_btn and not has_next_btn:
                # Additional check: count empty required fields
                # If there are many empty required fields, we're probably NOT on review page yet
                empty_required = await self.session.page.evaluate("""
                    () => {
                        const inputs = document.querySelectorAll('input[required]:visible, textarea[required]:visible, select[required]:visible');
                        return Array.from(inputs).filter(el => !el.value || el.value.trim() === '').length;
                    }
                """)

                if empty_required == 0:  # Only consider it review page if no empty required fields
                    logger.debug("Review page detected via button combination with no empty required fields")
                    return True
                else:
                    logger.debug(f"Found Review button but {empty_required} empty required fields - not final review page")
        except Exception:
            pass

        return False

    async def _fill_current_step(self, resume_path: str, modal=None) -> dict:
        """
        Fill the current form step.

        Args:
            resume_path: Path to resume file
            modal: Modal element to scope searches (prevents filling page elements)

        Returns:
            dict with success and error keys
        """
        try:
            # Handle resume upload
            await self._handle_resume_upload(resume_path)

            # BATCH PROCESSING: Extract all questions → Prepare answers → Fill form
            if modal:
                # Initialize batch processor
                batch_processor = FormBatchProcessor(
                    self.question_handler,
                    self.question_handler.profile
                )

                # Step 1: Extract all questions from modal
                questions = await batch_processor.extract_form_questions(modal)

                if questions:
                    logger.info(f"Extracted {len(questions)} questions from form")

                    # Step 2: Prepare answers (exact match + AI batch)
                    answers = batch_processor.prepare_answers_batch(
                        questions,
                        self.job_context
                    )

                    # Step 3: Fill form with prepared answers (relocate by order/index)
                    await batch_processor.fill_form_with_answers(modal, questions, answers)
                else:
                    logger.info("No questions found in form")

            # Handle dropdowns (scoped to modal)
            await self._fill_dropdowns(modal)

            # Handle radio buttons (scoped to modal)
            await self._fill_radio_buttons(modal)

            # Handle checkboxes (scoped to modal)
            await self._fill_checkboxes(modal)

            return {"success": True}

        except Exception as e:
            logger.error(f"Error filling form step: {e}")
            return {"success": False, "error": str(e)}

    async def _handle_resume_upload(self, resume_path: str):
        """Handle resume upload if present."""
        upload_selectors = [
            'input[type="file"]',
            'input[name*="resume"]',
            'input[accept*="pdf"]',
        ]

        for selector in upload_selectors:
            try:
                upload_input = self.session.page.locator(selector).first
                if await upload_input.count() > 0:
                    # Check if file already uploaded
                    existing = await self.session.page.locator('.jobs-document-upload-redesign-card__file-name').count()
                    if existing > 0:
                        logger.info("Resume already uploaded")
                        return

                    await upload_input.set_input_files(resume_path)
                    logger.info(f"Uploaded resume: {resume_path}")
                    await human_delay(1, 2)
                    return
            except Exception as e:
                logger.debug(f"Resume upload selector {selector} failed: {e}")

    async def _fill_text_inputs(self, modal=None):
        """Fill text input fields using AI-powered question handler.

        Args:
            modal: Modal element to scope searches to (prevents filling page elements)
        """
        # Get all visible text inputs (scoped to modal if provided)
        scope = modal if modal else self.session.page
        inputs = await scope.locator(
            'input[type="text"]:visible, input[type="number"]:visible, input:not([type]):visible, textarea:visible'
        ).all()

        logger.info(f"Found {len(inputs)} visible input fields to process")

        for idx, input_elem in enumerate(inputs):
            try:
                # Get input type for debugging
                input_type = await input_elem.get_attribute('type') or 'text'
                input_name = await input_elem.get_attribute('name') or ''

                # Skip if already filled
                value = await input_elem.input_value()
                if value and len(value.strip()) > 0:
                    logger.debug(f"Input {idx} ({input_type}, {input_name[:20]}): Already has value '{value[:30]}'")
                    continue

                # Get label/placeholder for context
                label = await self._get_input_label(input_elem)

                logger.info(f"Input {idx} ({input_type}): Label='{label[:60]}...' Name='{input_name[:20]}'")

                # Skip search fields (not part of Easy Apply form)
                if label and 'search' in label.lower():
                    logger.info(f"  -> Skipping search field: '{label}'")
                    continue

                if label and label != "Unknown field":
                    # Use AI question handler to generate answer
                    answer = self.question_handler.answer_question(
                        label,
                        context=self.job_context,
                        job_id=self.job_context.get('external_id'),
                        field_type=input_type  # Pass field type for type-aware caching
                    )

                    logger.info(f"  -> Generated answer: '{answer}'")

                    if answer and answer != "N/A":
                        # Clear any existing value first
                        await input_elem.fill('')
                        await input_elem.fill(answer)
                        logger.info(f"  -> Filled successfully!")
                        await human_delay(0.3, 0.7)

                        # Close any overlays/dropdowns that might have appeared
                        try:
                            await self.session.page.keyboard.press('Escape')
                            await human_delay(0.2, 0.4)
                        except:
                            pass

                        # Take screenshot after filling (to capture any overlays/dropdowns)
                        if self.debug:
                            await self._screenshot(f"apply_{self.job_context.get('external_id')}_after_fill_{idx}")

                        # Verify fill worked
                        new_value = await input_elem.input_value()
                        if new_value != answer:
                            logger.warning(f"  -> Value mismatch after fill: expected '{answer}', got '{new_value}'")
                    else:
                        logger.warning(f"  -> No valid answer generated (got: {answer})")
                else:
                    logger.debug(f"  -> Skipping input with unknown label")

            except Exception as e:
                logger.error(f"Error handling text input {idx}: {e}")

    async def _fill_dropdowns(self, modal=None):
        """Fill dropdown/select fields.

        Args:
            modal: Modal element to scope searches to (prevents filling page elements)
        """
        # Get all visible selects (scoped to modal if provided)
        scope = modal if modal else self.session.page
        selects = await scope.locator('select:visible').all()

        for select in selects:
            try:
                # Check if already selected
                selected = await select.input_value()
                if selected and selected.strip():
                    continue

                # TODO: Use AI to select appropriate option
                logger.debug("Found unselected dropdown")

            except Exception as e:
                logger.debug(f"Error handling dropdown: {e}")

    async def _fill_radio_buttons(self, modal=None):
        """Fill radio button groups.

        Args:
            modal: Modal element to scope searches to (prevents filling page elements)
        """
        # Find radio groups (scoped to modal if provided)
        scope = modal if modal else self.session.page
        radio_groups = await scope.locator(
            'fieldset:has(input[type="radio"]):visible'
        ).all()

        for group in radio_groups:
            try:
                # Check if already selected
                selected = await group.locator('input[type="radio"]:checked').count()
                if selected > 0:
                    continue

                # TODO: Use AI to select appropriate option
                logger.debug("Found unselected radio group")

            except Exception as e:
                logger.debug(f"Error handling radio group: {e}")

    async def _fill_checkboxes(self, modal=None):
        """Fill checkbox fields (typically terms/conditions).

        Args:
            modal: Modal element to scope searches to (prevents filling page elements)
        """
        # Get checkboxes (scoped to modal if provided)
        scope = modal if modal else self.session.page
        checkboxes = await scope.locator(
            'input[type="checkbox"]:visible:not(:checked)'
        ).all()

        for checkbox in checkboxes:
            try:
                # Get label to check if it's terms/conditions
                label = await self._get_input_label(checkbox)

                if any(term in label.lower() for term in ['agree', 'terms', 'acknowledge', 'confirm']):
                    await checkbox.check()
                    logger.info(f"Checked: {label[:50]}")

            except Exception as e:
                logger.debug(f"Error handling checkbox: {e}")

    async def _get_input_label(self, element) -> str:
        """Get the label text for an input element."""
        try:
            # Try aria-label
            aria_label = await element.get_attribute('aria-label')
            if aria_label:
                logger.debug(f"Found label via aria-label: {aria_label[:50]}")
                return aria_label

            # Try id -> label[for]
            elem_id = await element.get_attribute('id')
            if elem_id:
                try:
                    label = await self.session.page.locator(f'label[for="{elem_id}"]').text_content()
                    if label:
                        logger.debug(f"Found label via label[for]: {label[:50]}")
                        return label.strip()
                except Exception:
                    pass

            # Try placeholder
            placeholder = await element.get_attribute('placeholder')
            if placeholder:
                logger.debug(f"Found label via placeholder: {placeholder[:50]}")
                return placeholder

            # Try parent label
            try:
                parent_label = await element.locator('xpath=ancestor::label').text_content()
                if parent_label:
                    logger.debug(f"Found label via ancestor: {parent_label[:50]}")
                    return parent_label.strip()
            except Exception:
                pass

            # LinkedIn-specific: Look for label in parent container
            # LinkedIn forms use divs with label as sibling
            try:
                # Use JavaScript to find the label text from parent container
                label_text = await element.evaluate("""
                    el => {
                        // Try to find label in parent form element container
                        let container = el.closest('.fb-dash-form-element, .artdeco-text-input, [class*="form-element"], [class*="form-component"]');
                        if (container) {
                            // Look for label element
                            let label = container.querySelector('label');
                            if (label) return label.innerText.trim();

                            // Look for any span/div with label-like class
                            let labelEl = container.querySelector('[class*="label"], .t-14, .t-bold');
                            if (labelEl) return labelEl.innerText.trim();
                        }

                        // Try previous sibling
                        let prev = el.previousElementSibling;
                        while (prev) {
                            if (prev.tagName === 'LABEL' || prev.classList.contains('fb-dash-form-element__label')) {
                                return prev.innerText.trim();
                            }
                            prev = prev.previousElementSibling;
                        }

                        // Try parent's previous sibling (label before input wrapper)
                        let parent = el.parentElement;
                        if (parent) {
                            prev = parent.previousElementSibling;
                            while (prev) {
                                if (prev.tagName === 'LABEL' || prev.innerText) {
                                    let text = prev.innerText.trim();
                                    if (text && text.length < 200) return text;
                                }
                                prev = prev.previousElementSibling;
                            }
                        }

                        return null;
                    }
                """)
                if label_text:
                    logger.debug(f"Found label via JS container search: {label_text[:50]}")
                    return label_text
            except Exception as e:
                logger.debug(f"JS label search failed: {e}")

        except Exception as e:
            logger.debug(f"Error in _get_input_label: {e}")

        return "Unknown field"

    async def _click_next_button(self) -> bool:
        """Click the Next/Continue/Review button with AI-assisted fallback."""
        # First check if there are validation errors - if so, don't click
        has_errors = await self._check_validation_errors()
        if has_errors:
            logger.warning("Validation errors detected - cannot proceed to next step")
            # Try to identify which fields are causing errors
            try:
                error_text = await self.session.page.locator('[role="alert"]:visible, .artdeco-inline-feedback--error:visible').first.inner_text()
                logger.warning(f"Validation error message: {error_text}")
            except Exception:
                pass
            return False

        # Scroll modal to bottom to reveal Next/Continue/Review buttons
        try:
            # Find the modal footer or button container and scroll it into view
            modal = await self.session.page.locator('.jobs-easy-apply-modal, div[data-test-modal], .artdeco-modal').first
            if await modal.is_visible(timeout=1000):
                # Scroll to bottom of modal content
                await modal.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                await human_delay(0.5, 1.0)
                logger.debug("Scrolled modal to reveal buttons")
        except Exception as e:
            logger.debug(f"Could not scroll modal: {e}")

        button_selectors = [
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button:has-text("Review")',
            'button[aria-label*="Continue"]',
            'button[aria-label*="Next"]',
            'button[aria-label*="Review"]',
            'button[data-easy-apply-next-button]',
        ]

        for selector in button_selectors:
            try:
                button = self.session.page.locator(selector).first
                if await button.is_visible(timeout=1000):
                    # Scroll button into view before clicking
                    await button.scroll_into_view_if_needed()
                    await human_delay(0.3, 0.5)
                    text = await button.inner_text()
                    await button.click()
                    logger.info(f"Clicked {text.strip()} button")
                    return True
            except Exception:
                continue

        # If standard selectors failed, try AI-assisted approach
        logger.warning("Standard Next button selectors failed, trying AI analysis...")
        return await self._ai_assisted_click("next_button")

    async def _ai_assisted_click(self, context: str) -> bool:
        """
        Use AI to analyze screenshot and determine what to click.

        Args:
            context: Description of what we're trying to do (e.g., "next_button", "close_modal")

        Returns:
            True if successful click, False otherwise
        """
        try:
            # Take screenshot for analysis
            external_id = self.job_context.get('external_id', 'unknown')
            screenshot_path = SCREENSHOTS_DIR / f"apply_{external_id}_ai_analysis_{context}.png"
            await self.session.page.screenshot(path=str(screenshot_path))
            logger.info(f"Screenshot saved for AI analysis: {screenshot_path}")

            # Analyze with AI
            result = analyze_screenshot_for_action(
                screenshot_path,
                context=f"Trying to {context.replace('_', ' ')} in Easy Apply form"
            )

            if not result:
                logger.error("AI analysis failed to return result")
                return False

            logger.info(f"AI recommends: {result['action']} - {result['reasoning']}")

            # Execute recommended action
            if result['action'] == 'click' and result.get('selector_text'):
                selectors = get_click_selector_from_text(
                    result['selector_text'],
                    result.get('selector_type', 'button')
                )

                for selector in selectors:
                    try:
                        element = self.session.page.locator(selector).first
                        if await element.is_visible(timeout=2000):
                            await element.click()
                            logger.info(f"AI-assisted click successful: {selector}")
                            await human_delay(1, 2)
                            return True
                    except Exception as e:
                        logger.debug(f"Selector {selector} failed: {e}")
                        continue

            elif result['action'] == 'close':
                # Try to close modal/overlay
                close_selectors = get_click_selector_from_text("", "close_icon")
                for selector in close_selectors:
                    try:
                        element = self.session.page.locator(selector).first
                        if await element.is_visible(timeout=1000):
                            await element.click()
                            logger.info(f"Closed modal using: {selector}")
                            await human_delay(0.5, 1)
                            return True
                    except:
                        continue

            logger.warning(f"AI recommended {result['action']} but couldn't execute")
            return False

        except Exception as e:
            logger.error(f"AI-assisted click failed: {e}")
            return False

    async def _submit_application(self) -> bool:
        """Submit the final application."""
        submit_selectors = [
            'button:has-text("Submit application")',
            'button:has-text("Submit")',
            'button[aria-label*="Submit"]',
        ]

        for selector in submit_selectors:
            try:
                button = self.session.page.locator(selector).first
                if await button.is_visible(timeout=2000):
                    await button.click()
                    logger.info("Clicked Submit button")
                    await human_delay(2, 3)

                    # Check for success message
                    success_indicators = [
                        ':text("Application sent")',
                        ':text("application submitted")',
                        '.artdeco-modal:has-text("Application sent")',
                    ]

                    for indicator in success_indicators:
                        try:
                            if await self.session.page.locator(indicator).is_visible(timeout=3000):
                                logger.info("Application submitted successfully!")
                                return True
                        except Exception:
                            continue

                    # Assume success if no error
                    return True

            except Exception as e:
                logger.error(f"Error clicking submit: {e}")

        return False

    async def _screenshot(self, name: str):
        """Take a debug screenshot."""
        try:
            path = SCREENSHOTS_DIR / f"{name}.png"
            await self.session.page.screenshot(path=str(path))
            logger.info(f"Screenshot saved: {path}")
        except Exception as e:
            logger.debug(f"Screenshot failed: {e}")

    async def _get_page_hash(self) -> str:
        """Get a hash of the current page to detect if we're stuck."""
        try:
            # Get a signature of the current page (input labels + button text)
            page_signature = await self.session.page.evaluate("""
                () => {
                    const labels = Array.from(document.querySelectorAll('label')).map(l => l.innerText).join('|');
                    const buttons = Array.from(document.querySelectorAll('button')).map(b => b.innerText).join('|');
                    const inputs = document.querySelectorAll('input:visible, textarea:visible, select:visible').length;
                    return `${labels}_${buttons}_${inputs}`;
                }
            """)
            return page_signature
        except Exception as e:
            logger.debug(f"Error getting page hash: {e}")
            return ""

    async def _check_validation_errors(self) -> bool:
        """Check if there are validation errors on the page."""
        try:
            # Look for ACTUAL validation error indicators (not field labels)
            # LinkedIn shows errors with specific classes and role="alert"
            error_selectors = [
                '.artdeco-inline-feedback--error:visible',
                '[role="alert"]:visible',
                '.form-error:visible',
                '.error-message:visible',
            ]

            for selector in error_selectors:
                try:
                    error_elem = self.session.page.locator(selector).first
                    if await error_elem.is_visible(timeout=500):
                        # Verify it's an actual error message, not just a label
                        error_text = await error_elem.inner_text()
                        error_text_lower = error_text.lower() if error_text else ""

                        # Only flag as error if it contains actual error keywords
                        error_keywords = ['required', 'invalid', 'error', 'must', 'cannot', 'please enter']
                        if any(keyword in error_text_lower for keyword in error_keywords):
                            logger.warning(f"Validation error found: {error_text.strip()}")
                            return True
                except Exception:
                    continue

            # Check for empty required fields within the modal
            try:
                # Scope to modal only to avoid checking page elements
                modal = await self.session.page.locator('.jobs-easy-apply-modal, div[data-test-modal], .artdeco-modal').first
                if await modal.is_visible(timeout=500):
                    required_empty = await modal.evaluate("""
                        (el) => {
                            // Only check visible required fields that are actually empty
                            const requiredInputs = el.querySelectorAll('input[required], textarea[required], select[required]');
                            return Array.from(requiredInputs).some(input => {
                                // Check if field is visible
                                const style = window.getComputedStyle(input);
                                if (style.display === 'none' || style.visibility === 'hidden') return false;

                                // Check if field is empty
                                const value = input.value?.trim() || '';
                                return value === '';
                            });
                        }
                    """)
                    if required_empty:
                        logger.warning("Found empty required fields in modal")
                        return True
            except Exception as e:
                logger.debug(f"Error checking required fields: {e}")

            return False
        except Exception as e:
            logger.debug(f"Error checking validation errors: {e}")
            return False

    def get_stats(self) -> dict:
        """Get application statistics."""
        return self.stats.copy()


async def apply_to_jobs_batch(
    jobs: list[dict],
    dry_run: bool = False,
    debug: bool = False,
    limit: int = 5
) -> list[dict]:
    """
    Apply to multiple jobs.

    Args:
        jobs: List of job dicts with job_url and external_id
        dry_run: If True, don't actually submit
        debug: Enable debug screenshots
        limit: Maximum applications to submit

    Returns:
        List of application results
    """
    results = []

    async with EasyApplyBot(debug=debug, dry_run=dry_run) as bot:
        for i, job in enumerate(jobs[:limit]):
            job_url = job.get("job_url")
            external_id = job.get("external_id")

            if not job_url:
                continue

            logger.info(f"[{i+1}/{min(len(jobs), limit)}] Applying to {external_id}")

            result = await bot.apply_to_job(
                job_url=job_url,
                external_id=external_id
            )
            results.append(result)

            # Delay between applications
            if i < len(jobs) - 1:
                await human_delay(5, 10)

        # Print stats
        stats = bot.get_stats()
        logger.info(f"\n=== Application Stats ===")
        logger.info(f"Attempted: {stats['attempted']}")
        logger.info(f"Submitted: {stats['submitted']}")
        logger.info(f"Failed: {stats['failed']}")
        logger.info(f"Skipped: {stats['skipped']}")

    return results
