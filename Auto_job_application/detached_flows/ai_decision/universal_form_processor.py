"""
Universal Form Processor - 5-phase form processing for any website.

Expands the LinkedIn-only FormBatchProcessor to handle forms on any job site.
Uses DOM snapshots + AI for intelligent form understanding and filling.

Architecture:
  Phase 1: PAGE SCAN - DOM snapshot + screenshot + classify
  Phase 2: ELEMENT EXTRACTION - All interactive elements with labels
  Phase 3: SMART ANSWER PREPARATION - Single AI call for all questions
  Phase 4: FILL & VERIFY - Fill each field with verification
  Phase 5: ACTION & CONFIRM - Click submit, verify transition

Usage:
    processor = UniversalFormProcessor(profile, question_handler)
    result = await processor.process_form(page, goal="fill job application")
"""
import json
import logging
import asyncio
from typing import Dict, List, Optional
from pathlib import Path

from detached_flows.ai_decision.dom_snapshot import (
    extract_dom_snapshot,
    snapshot_to_text,
    get_unfilled_fields,
)
from detached_flows.ai_decision.page_analyzer import PageAnalyzer, PageType
from detached_flows.ai_decision.action_planner import ActionPlanner, ActionType, Strategy
from detached_flows.ai_decision.element_handlers import ElementHandlerRegistry

logger = logging.getLogger("UniversalFormProcessor")


class FormProcessResult:
    """Result of processing a form page."""

    def __init__(self):
        self.success = False
        self.fields_filled = 0
        self.fields_failed = 0
        self.fields_skipped = 0
        self.page_type = ""
        self.moved_to_next = False
        self.is_complete = False  # True if application confirmed
        self.requires_human = False
        self.human_reason = ""
        self.errors = []
        self.filled_fields = []  # For logging

    def __repr__(self):
        return (
            f"FormProcessResult(success={self.success}, "
            f"filled={self.fields_filled}, failed={self.fields_failed}, "
            f"moved_to_next={self.moved_to_next}, complete={self.is_complete})"
        )


class UniversalFormProcessor:
    """
    Universal form processor that can handle forms on any website.

    Extends the batch-processing approach from LinkedIn Easy Apply to
    work with any page layout, form structure, and element types.
    """

    def __init__(
        self,
        profile: dict,
        question_handler=None,
        credential_manager=None,
        debug: bool = False
    ):
        """
        Args:
            profile: User profile dict from user_profile.json
            question_handler: QuestionHandler for AI-powered answers
            credential_manager: Optional CredentialManager for credentials
            debug: Enable debug screenshots
        """
        self.profile = profile
        self.question_handler = question_handler
        self.cred_manager = credential_manager
        self.debug = debug

        self.page_analyzer = PageAnalyzer()
        self.action_planner = ActionPlanner(profile, credential_manager)
        self.element_registry = ElementHandlerRegistry()

    async def process_form(
        self,
        page,
        scope=None,
        goal: str = "",
        site_name: str = "",
        job_context: dict = None,
        resume_path: str = "",
        max_retries: int = 3,
    ) -> FormProcessResult:
        """
        Process a single form page - the main entry point.

        Goes through all 5 phases: scan, extract, prepare, fill, confirm.

        Args:
            page: Playwright page object
            scope: Optional locator to scope to (e.g., modal)
            goal: Current goal context
            site_name: Name of the job site
            job_context: Job details for context
            resume_path: Path to resume file
            max_retries: Max retry attempts for validation errors

        Returns:
            FormProcessResult with details of what happened
        """
        result = FormProcessResult()
        job_context = job_context or {}

        try:
            # ============================================
            # PHASE 1: PAGE SCAN
            # ============================================
            logger.info("Phase 1: Scanning page...")
            analysis = await self.page_analyzer.analyze(
                page, scope=scope, goal=goal, use_ai=True
            )
            result.page_type = analysis.page_type

            # Check if human needed
            if analysis.requires_human:
                result.requires_human = True
                result.human_reason = analysis.human_reason
                logger.warning(f"Human intervention needed: {analysis.human_reason}")
                return result

            # Check if already complete (confirmation page)
            if analysis.page_type == PageType.CONFIRMATION:
                result.success = True
                result.is_complete = True
                logger.info("Application confirmed!")
                return result

            # ============================================
            # PHASE 2: ELEMENT EXTRACTION
            # ============================================
            logger.info("Phase 2: Extracting form elements...")
            unfilled_fields = analysis.unfilled_fields

            if not unfilled_fields and analysis.page_type in (PageType.REVIEW, PageType.CONFIRMATION):
                # Review or confirmation page - just need to click the button
                logger.info("No fields to fill - review/confirmation page")
            elif not unfilled_fields:
                logger.info("No unfilled fields found on this page")

            logger.info(
                f"Found {len(unfilled_fields)} unfilled fields, "
                f"{len(analysis.buttons)} buttons"
            )

            # ============================================
            # PHASE 3: SMART ANSWER PREPARATION
            # ============================================
            if unfilled_fields:
                logger.info("Phase 3: Preparing answers...")
                answer_map = await self._prepare_answers(
                    unfilled_fields, analysis, goal, site_name, job_context
                )
            else:
                answer_map = {}

            # ============================================
            # PHASE 4: FILL & VERIFY
            # ============================================
            if answer_map:
                logger.info(f"Phase 4: Filling {len(answer_map)} fields...")
                fill_result = await self._fill_fields(
                    page, scope, unfilled_fields, answer_map, resume_path
                )
                result.fields_filled = fill_result['filled']
                result.fields_failed = fill_result['failed']
                result.fields_skipped = fill_result['skipped']
                result.filled_fields = fill_result['details']

            # Handle terms/agreement checkboxes
            await self._handle_checkboxes(page, scope, analysis)

            # ============================================
            # PHASE 5: ACTION & CONFIRM
            # ============================================
            logger.info("Phase 5: Clicking action button...")

            for attempt in range(max_retries):
                clicked = await self._click_primary_action(page, scope, analysis)

                if not clicked:
                    logger.warning("Could not find/click primary action button")
                    if attempt < max_retries - 1:
                        # Scroll and try again
                        await self._scroll_to_bottom(page, scope)
                        await asyncio.sleep(1)
                        continue
                    break

                # Wait for page transition
                await asyncio.sleep(2)

                # Check page text for verification code requirement (before error check)
                if await self._page_has_verification_prompt(page):
                    logger.info("Verification code prompt detected on page — needs human")
                    result.requires_human = True
                    result.human_reason = "Email verification code required"
                    result.success = False
                    return result

                # Check for validation errors
                errors = await self._check_validation_errors(page, scope)

                if errors:
                    logger.warning(f"Validation errors (attempt {attempt + 1}): {errors}")
                    result.errors.extend(errors)

                    # Check if errors indicate verification/security code requirement
                    if self._is_verification_code_error(errors):
                        logger.info("Verification/security code detected in errors — needs human")
                        result.requires_human = True
                        result.human_reason = "Email verification code required"
                        result.success = False
                        return result

                    if attempt < max_retries - 1:
                        # Re-scan and try to fix
                        logger.info("Re-scanning page to fix errors...")
                        re_analysis = await self.page_analyzer.analyze(
                            page, scope=scope, goal=goal
                        )
                        re_unfilled = re_analysis.unfilled_fields

                        if re_unfilled:
                            re_answers = await self._prepare_answers(
                                re_unfilled, re_analysis, goal, site_name, job_context
                            )
                            if re_answers:
                                await self._fill_fields(
                                    page, scope, re_unfilled, re_answers, resume_path
                                )
                        continue
                    else:
                        logger.error("Max retries reached with validation errors")
                        break
                else:
                    # No errors - success
                    result.moved_to_next = True
                    break

            result.success = result.moved_to_next or result.is_complete
            return result

        except Exception as e:
            logger.error(f"Form processing failed: {e}", exc_info=True)
            result.errors.append(str(e))
            return result

    async def _prepare_answers(
        self,
        unfilled_fields: List[Dict],
        analysis,
        goal: str,
        site_name: str,
        job_context: dict
    ) -> Dict[int, str]:
        """
        Phase 3: Prepare answers for all unfilled fields in a single AI call.

        Returns:
            Dict mapping element index → answer value
        """
        answer_map = {}

        # First pass: rule-based mapping from profile
        fields_needing_ai = []

        for field_el in unfilled_fields:
            # Skip honeypot fields (anti-bot traps — filling them flags us)
            label_lower = (field_el.get('label') or '').lower()
            field_id = field_el.get('attributes', {}).get('id', '').lower()
            field_name = field_el.get('attributes', {}).get('name', '').lower()
            if any('honey' in x for x in [label_lower, field_id, field_name]):
                logger.debug(f"Skipping honeypot field: {field_el.get('label', '?')}")
                continue

            # Handle file uploads directly — use resume path, not AI
            if field_el.get('type') == 'file_upload':
                label_lower = (field_el.get('label') or '').lower()
                if any(kw in label_lower for kw in ['cover letter', 'cover_letter']):
                    answer_map[field_el['index']] = '__AI_GENERATE_COVER_LETTER__'
                else:
                    answer_map[field_el['index']] = '__RESUME_PATH__'
                logger.debug(f"File upload: {field_el.get('label', '?')} → {answer_map[field_el['index']]}")
                continue

            # Try action planner's profile-based mapping
            action = self.action_planner._map_field_to_action(
                field_el, self.profile.get('profile', {}), job_context
            )

            if action and action.value and not action.value.startswith('__'):
                answer_map[field_el['index']] = action.value
                logger.debug(f"Profile match: {field_el.get('label', '?')} → {action.value[:30]}")
            else:
                fields_needing_ai.append(field_el)

        # Second pass: batch AI call for remaining fields
        if fields_needing_ai and self.question_handler:
            ai_answers = await self._batch_ai_answers(
                fields_needing_ai, goal, site_name, job_context
            )
            answer_map.update(ai_answers)

        logger.info(
            f"Answers prepared: {len(answer_map)} total "
            f"({len(answer_map) - len(fields_needing_ai)} profile, "
            f"{len(fields_needing_ai)} AI)"
        )

        return answer_map

    async def _batch_ai_answers(
        self,
        fields: List[Dict],
        goal: str,
        site_name: str,
        job_context: dict
    ) -> Dict[int, str]:
        """Get answers for multiple fields in a single AI call."""
        if not fields:
            return {}

        try:
            from detached_flows.ai_decision.claude_fast import call_claude_fast
        except ImportError:
            logger.warning("Claude fast not available, using question handler fallback")
            return self._fallback_answers(fields, job_context)

        # Build the batch prompt
        profile_summary = self.action_planner._build_profile_summary()

        questions_text = ""
        for i, field_el in enumerate(fields):
            label = field_el.get('label', 'Unknown field')
            field_type = field_el.get('type', 'text')
            required = " (REQUIRED)" if field_el.get('required') else ""
            options = ""
            if field_el.get('options'):
                opt_texts = [o.get('text', '') for o in field_el['options'][:15]]
                options = f" Options: [{', '.join(opt_texts)}]"

            questions_text += f"{i + 1}. [{field_type}] {label}{required}{options}\n"

        prompt = f"""Fill out this job application form. Return ONLY a JSON object mapping question numbers to answers.

**Site:** {site_name or 'Unknown'}
**Goal:** {goal or 'Complete job application'}
**Job:** {job_context.get('title', 'Unknown')} at {job_context.get('company', 'Unknown')}

**Candidate Profile:**
{profile_summary}

**Questions to answer:**
{questions_text}

**Rules:**
- For select/dropdown fields, choose EXACTLY one option from the provided options list
- For number fields, return only digits (no units like "years" or "LPA")
- For text fields, be concise and professional
- For yes/no questions, respond with the exact option text if options are provided
- Use profile data when available, generate reasonable answers when not
- Return JSON: {{"1": "answer1", "2": "answer2", ...}}
- ONLY return the JSON, nothing else"""

        try:
            response = call_claude_fast(prompt, timeout=15)

            # Parse JSON
            if '```json' in response:
                response = response.split('```json')[1].split('```')[0]
            elif '```' in response:
                response = response.split('```')[1].split('```')[0]

            answers = json.loads(response.strip())

            # Map back to element indices
            result = {}
            for i, field_el in enumerate(fields):
                key = str(i + 1)
                if key in answers:
                    result[field_el['index']] = str(answers[key]).strip()

            logger.info(f"AI batch answers: {len(result)} of {len(fields)} answered")
            return result

        except Exception as e:
            logger.error(f"Batch AI answer failed: {e}")
            return self._fallback_answers(fields, job_context)

    def _fallback_answers(self, fields: List[Dict], job_context: dict) -> Dict[int, str]:
        """Fallback: use question_handler for individual answers."""
        result = {}

        if not self.question_handler:
            return result

        for field_el in fields:
            label = field_el.get('label', '')
            field_type = field_el.get('type', 'text')

            try:
                answer = self.question_handler.answer_question(
                    label,
                    context=job_context,
                    field_type=field_type
                )
                if answer and answer != 'N/A':
                    result[field_el['index']] = answer
            except Exception as e:
                logger.debug(f"Fallback answer failed for '{label}': {e}")

        return result

    async def _fill_fields(
        self,
        page,
        scope,
        unfilled_fields: List[Dict],
        answer_map: Dict[int, str],
        resume_path: str
    ) -> Dict:
        """
        Phase 4: Fill form fields with prepared answers.

        Returns:
            Dict with 'filled', 'failed', 'skipped' counts and 'details' list
        """
        from detached_flows.config import MASTER_PDF

        filled = 0
        failed = 0
        skipped = 0
        details = []

        target = scope if scope else page

        for field_el in unfilled_fields:
            idx = field_el['index']
            label = field_el.get('label', 'Unknown')
            el_type = field_el.get('type', 'text_input')

            if idx not in answer_map:
                skipped += 1
                continue

            value = answer_map[idx]

            # Resolve special placeholders
            if value == '__CREDENTIAL_PASSWORD__':
                if self.cred_manager:
                    # Will be resolved by credential manager at fill time
                    skipped += 1
                    continue
                else:
                    skipped += 1
                    continue

            if value == '__RESUME_PATH__':
                value = resume_path or str(MASTER_PDF)

            if value == '__AI_GENERATE_COVER_LETTER__':
                # Generate cover letter via AI
                value = await self._generate_cover_letter(field_el, {})
                if not value:
                    skipped += 1
                    continue

            # Clean phone number: strip country code prefix for phone fields
            # (many ATS have a separate country code dropdown)
            if el_type == 'phone_input' and value:
                import re
                # Strip +XX prefix and spaces/dashes
                cleaned = re.sub(r'^\+?\d{1,3}[\s-]+', '', value)
                # Keep only digits
                cleaned = re.sub(r'[^\d]', '', cleaned)
                if cleaned and len(cleaned) >= 7:
                    value = cleaned

            # Fill using element handler
            try:
                success = await self.element_registry.fill_element(
                    target, field_el, value
                )

                if success:
                    filled += 1
                    details.append({
                        'label': label,
                        'type': el_type,
                        'value': value[:50],
                        'status': 'filled'
                    })

                    # Small delay between fields (human-like)
                    await asyncio.sleep(0.3)
                else:
                    failed += 1
                    details.append({
                        'label': label,
                        'type': el_type,
                        'value': value[:50],
                        'status': 'failed'
                    })

            except Exception as e:
                logger.error(f"Error filling '{label}': {e}")
                failed += 1

        logger.info(f"Fill results: {filled} filled, {failed} failed, {skipped} skipped")
        return {'filled': filled, 'failed': failed, 'skipped': skipped, 'details': details}

    async def _handle_checkboxes(self, page, scope, analysis):
        """Check any agreement/terms checkboxes and custom agreement elements."""
        target = scope if scope else page
        agreement_keywords = ['agree', 'terms', 'accept', 'consent', 'acknowledge']

        for field_el in analysis.form_fields:
            if field_el['type'] != 'checkbox':
                continue

            label = (field_el.get('label') or '').lower()
            value = field_el.get('current_value', '')

            # Auto-check terms/agreement boxes
            if value != 'checked' and any(
                kw in label for kw in agreement_keywords
            ):
                try:
                    await self.element_registry.fill_element(
                        target, field_el, 'check'
                    )
                except Exception as e:
                    logger.debug(f"Could not check checkbox '{label}': {e}")

        # Also handle custom agreement checkboxes (hidden input + styled label)
        # Some ATS platforms (Oracle Cloud, etc.) use hidden <input type="checkbox">
        # with a visible label/span as the clickable element
        await self._handle_custom_agreements(target)

    async def _handle_custom_agreements(self, target):
        """Handle custom checkbox agreements (hidden checkbox + visible label)."""
        agreement_keywords = ['agree', 'terms', 'accept', 'consent', 'acknowledge',
                              'disclaimer', 'legal']
        try:
            # Strategy 1: Find unchecked hidden checkboxes and click their labels
            checkboxes = await target.locator(
                'input[type="checkbox"]'
            ).all()

            for cb in checkboxes:
                try:
                    cb_id = await cb.get_attribute('id') or ''
                    cb_name = await cb.get_attribute('name') or ''
                    is_checked = await cb.is_checked()

                    if is_checked:
                        continue

                    # Check if this checkbox relates to terms/agreement
                    identifier = (cb_id + ' ' + cb_name).lower()
                    if not any(kw in identifier for kw in agreement_keywords):
                        # Check the associated label text
                        label_text = ''
                        if cb_id:
                            try:
                                label_loc = target.locator(f'label[for="{cb_id}"]').first
                                if await label_loc.count() > 0:
                                    label_text = (await label_loc.inner_text()).lower()
                            except Exception:
                                pass
                        if not any(kw in label_text for kw in agreement_keywords):
                            continue

                    # Try clicking via JavaScript (handles hidden checkboxes)
                    if cb_id:
                        clicked = await target.evaluate(
                            f"""() => {{
                                const cb = document.getElementById('{cb_id}');
                                if (cb && !cb.checked) {{
                                    cb.click();
                                    return true;
                                }}
                                // Try clicking the label instead
                                const label = document.querySelector('label[for="{cb_id}"]');
                                if (label) {{ label.click(); return true; }}
                                return false;
                            }}"""
                        )
                        if clicked:
                            logger.info(f"Checked agreement checkbox: #{cb_id}")
                            await asyncio.sleep(0.5)
                            continue

                    # Fallback: force click the checkbox directly
                    await cb.click(force=True)
                    logger.info(f"Force-clicked agreement checkbox")
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.debug(f"Could not check agreement checkbox: {e}")

        except Exception as e:
            logger.debug(f"Custom agreement handling failed: {e}")

    async def _click_primary_action(self, page, scope, analysis) -> bool:
        """Click the primary action button (Next/Submit/Continue)."""
        target = scope if scope else page

        # FIRST: try the actual form submit button (most reliable)
        try:
            form_submit = target.locator('form [type="submit"]:visible').first
            if await form_submit.count() > 0:
                await form_submit.scroll_into_view_if_needed()
                await asyncio.sleep(0.3)
                submit_text = await form_submit.inner_text()
                await form_submit.click()
                logger.info(f"Clicked form submit button: '{submit_text.strip()[:40]}'")
                return True
        except Exception:
            pass

        # Try the identified primary action
        if analysis.primary_action:
            try:
                btn = analysis.primary_action
                attrs = btn.get('attributes', {})
                selector = attrs.get('selector', '')
                label = btn.get('label') or btn.get('current_value', '')

                # Try multiple selector strategies
                selectors_to_try = []
                if selector:
                    selectors_to_try.append(selector)
                if label:
                    selectors_to_try.extend([
                        f'button:has-text("{label}")',
                        f'[type="submit"]:has-text("{label}")',
                        f'a:has-text("{label}")',
                    ])

                for sel in selectors_to_try:
                    locator = target.locator(sel).first
                    if await locator.count() > 0:
                        await locator.scroll_into_view_if_needed()
                        await asyncio.sleep(0.3)
                        await locator.click()
                        logger.info(f"Clicked primary action: '{label}'")
                        return True

            except Exception as e:
                logger.debug(f"Primary action click failed: {e}")

        # Fallback: find submit/next/continue buttons
        fallback_keywords = [
            'submit', 'next', 'continue', 'apply', 'save',
            'register', 'sign up', 'create', 'confirm', 'review'
        ]

        for keyword in fallback_keywords:
            try:
                selectors = [
                    f'button:has-text("{keyword}"):visible',
                    f'[type="submit"]:has-text("{keyword}"):visible',
                    f'a.btn:has-text("{keyword}"):visible',
                ]

                for sel in selectors:
                    locator = target.locator(sel).first
                    if await locator.count() > 0:
                        await locator.scroll_into_view_if_needed()
                        await asyncio.sleep(0.3)
                        await locator.click()
                        logger.info(f"Clicked fallback button: '{keyword}'")
                        return True

            except Exception:
                continue

        # Last resort: any submit button
        try:
            submit = target.locator('[type="submit"]:visible').first
            if await submit.count() > 0:
                await submit.scroll_into_view_if_needed()
                await submit.click()
                logger.info("Clicked generic submit button")
                return True
        except Exception:
            pass

        logger.warning("No action button found on page")
        return False

    async def _check_validation_errors(self, page, scope) -> List[str]:
        """Check for validation errors on the page after form submission."""
        target = scope if scope else page

        errors = []

        error_selectors = [
            '[role="alert"]',
            '.error-message',
            '.field-error',
            '.form-error',
            '.artdeco-inline-feedback--error',
            '.invalid-feedback',
            '[class*="error"]:not(button):not(a)',
        ]

        error_keywords = [
            'required', 'invalid', 'please', 'must', 'cannot',
            'error', 'incorrect', 'missing'
        ]

        for selector in error_selectors:
            try:
                elements = await target.locator(selector).all()
                for elem in elements:
                    if not await elem.is_visible():
                        continue

                    text = (await elem.inner_text()).strip()

                    if not text or len(text) < 3 or len(text) > 300:
                        continue

                    # Verify it contains error keywords (avoid false positives)
                    text_lower = text.lower()
                    if any(kw in text_lower for kw in error_keywords):
                        if text not in errors:
                            errors.append(text)
            except Exception:
                continue

        return errors

    async def _page_has_verification_prompt(self, page) -> bool:
        """Check if the page shows a verification/security code prompt (not just errors)."""
        try:
            text = await page.evaluate(
                "() => document.body?.innerText?.substring(0, 5000) || ''"
            )
            text_lower = text.lower()
            indicators = [
                'verification code was sent',
                'security code was sent',
                'code was sent to',
                'enter the code',
                'enter the 8-character code',
                'confirm you\'re a human',
                'one-time code',
            ]
            return any(ind in text_lower for ind in indicators)
        except Exception:
            return False

    def _is_verification_code_error(self, errors: List[str]) -> bool:
        """Check if validation errors indicate a verification/security code requirement."""
        verification_keywords = [
            'verification code', 'security code', 'confirm you\'re a human',
            'enter the code', 'code was sent', 'verify your email',
            'one-time code', 'incorrect security code', 'incorrect verification',
            'invalid code', 'enter code', 'confirmation code',
        ]
        all_error_text = ' '.join(errors).lower()
        return any(kw in all_error_text for kw in verification_keywords)

    async def _scroll_to_bottom(self, page, scope):
        """Scroll to bottom of page/modal to reveal hidden buttons."""
        try:
            if scope:
                await scope.evaluate("el => el.scrollTo(0, el.scrollHeight)")
            else:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.5)
        except Exception:
            pass

    async def _generate_cover_letter(self, field_el: Dict, job_context: dict) -> Optional[str]:
        """Generate a cover letter using AI."""
        try:
            from detached_flows.ai_decision.claude_fast import call_claude_fast

            profile_summary = self.action_planner._build_profile_summary()

            prompt = f"""Write a brief, professional cover letter (3-4 paragraphs) for this job application.

**Candidate:**
{profile_summary}

**Job:** {job_context.get('title', 'Unknown Position')} at {job_context.get('company', 'Unknown Company')}

Keep it concise, professional, and highlight relevant experience. No placeholder text."""

            return call_claude_fast(prompt, timeout=15)
        except Exception as e:
            logger.error(f"Cover letter generation failed: {e}")
            return None
