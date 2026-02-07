"""
Page Analyzer - AI-powered page classification and understanding.

Takes a DOM snapshot (and optionally a screenshot) and uses AI to classify
the page type, purpose, and recommend actions. This is the "brain" of the
universal job application engine.

Usage:
    analyzer = PageAnalyzer()
    analysis = await analyzer.analyze(page)
    # Returns structured PageAnalysis with page type, elements, actions
"""
import json
import logging
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from detached_flows.ai_decision.dom_snapshot import (
    extract_dom_snapshot,
    snapshot_to_text,
    get_form_fields_only,
    get_buttons,
    get_unfilled_fields,
)

logger = logging.getLogger("PageAnalyzer")


# Page type constants
class PageType:
    LOGIN = "login"
    REGISTRATION = "registration"
    FORM = "form"  # Generic form (application, profile, etc.)
    JOB_LISTING = "job_listing"
    CONFIRMATION = "confirmation"
    ERROR = "error"
    CAPTCHA = "captcha"
    DASHBOARD = "dashboard"
    EMAIL_VERIFICATION = "email_verification"
    PROFILE_COMPLETION = "profile_completion"
    FILE_UPLOAD = "file_upload"
    REVIEW = "review"  # Review before submit
    UNKNOWN = "unknown"


@dataclass
class PageAnalysis:
    """Structured result of page analysis."""
    page_type: str = PageType.UNKNOWN
    page_purpose: str = ""
    confidence: int = 0  # 0-100
    form_fields: List[Dict] = field(default_factory=list)
    unfilled_fields: List[Dict] = field(default_factory=list)
    buttons: List[Dict] = field(default_factory=list)
    primary_action: Optional[Dict] = None
    secondary_actions: List[Dict] = field(default_factory=list)
    errors_visible: List[str] = field(default_factory=list)
    captcha_present: bool = False
    requires_human: bool = False
    human_reason: str = ""
    is_multi_step: bool = False
    current_step: Optional[int] = None
    total_steps: Optional[int] = None
    raw_snapshot: Optional[Dict] = None

    def to_dict(self) -> Dict:
        d = asdict(self)
        d.pop('raw_snapshot', None)
        return d


class PageAnalyzer:
    """
    AI-powered page analyzer that understands any webpage.

    Uses DOM snapshot + AI classification to determine page type,
    purpose, and available actions.
    """

    def __init__(self):
        self._cache = {}  # URL pattern + DOM hash → analysis

    async def analyze(
        self,
        page,
        scope=None,
        goal: str = "",
        use_ai: bool = True
    ) -> PageAnalysis:
        """
        Analyze a page and return structured understanding.

        Args:
            page: Playwright page object
            scope: Optional locator to scope analysis (e.g., modal)
            goal: Current goal context (e.g., "apply to job", "register account")
            use_ai: Whether to use AI for classification (False = heuristic only)

        Returns:
            PageAnalysis with page type, fields, actions, etc.
        """
        # Extract DOM snapshot
        snapshot = await extract_dom_snapshot(page, scope=scope)

        # Check cache
        cache_key = self._get_cache_key(snapshot)
        if cache_key in self._cache:
            logger.info("Page analysis cache hit")
            return self._cache[cache_key]

        # Heuristic classification first (fast, no AI cost)
        analysis = self._heuristic_classify(snapshot)

        # If heuristic is confident enough, skip AI
        if analysis.confidence >= 85 and not use_ai:
            logger.info(
                f"Heuristic classification: {analysis.page_type} "
                f"(confidence: {analysis.confidence}%)"
            )
            analysis.raw_snapshot = snapshot
            self._cache[cache_key] = analysis
            return analysis

        # Use AI for better classification
        if use_ai:
            ai_analysis = self._ai_classify(snapshot, goal)
            if ai_analysis and ai_analysis.confidence > analysis.confidence:
                analysis = ai_analysis

        # Enrich with DOM data
        analysis.form_fields = get_form_fields_only(snapshot)
        analysis.unfilled_fields = get_unfilled_fields(snapshot)
        analysis.buttons = get_buttons(snapshot)
        analysis.errors_visible = snapshot.get('errors', [])
        analysis.raw_snapshot = snapshot

        # Identify primary and secondary actions
        self._identify_actions(analysis)

        # Detect multi-step forms
        self._detect_multi_step(analysis, snapshot)

        # Check if human intervention needed
        self._check_human_needed(analysis)

        logger.info(
            f"Page analysis: type={analysis.page_type}, "
            f"confidence={analysis.confidence}%, "
            f"fields={len(analysis.form_fields)}, "
            f"unfilled={len(analysis.unfilled_fields)}, "
            f"buttons={len(analysis.buttons)}"
        )

        self._cache[cache_key] = analysis
        return analysis

    def _get_cache_key(self, snapshot: Dict) -> str:
        """Generate cache key from URL pattern + element structure hash."""
        url = snapshot.get('page', {}).get('url', '')
        # Normalize URL (remove query params for caching)
        base_url = url.split('?')[0]

        # Hash the element structure (types + labels, not values)
        elements = snapshot.get('elements', [])
        structure = json.dumps(
            [(e.get('type'), e.get('label', '')[:30]) for e in elements],
            sort_keys=True
        )
        structure_hash = hashlib.md5(structure.encode()).hexdigest()[:8]

        return f"{base_url}_{structure_hash}"

    def _heuristic_classify(self, snapshot: Dict) -> PageAnalysis:
        """
        Fast heuristic classification based on DOM structure.
        No AI call needed - purely based on element patterns.
        """
        analysis = PageAnalysis()
        page = snapshot.get('page', {})
        elements = snapshot.get('elements', [])
        url = page.get('url', '').lower()
        title = page.get('title', '').lower()
        headings = [h['text'].lower() for h in page.get('headings', [])]
        all_text = ' '.join(headings + [title])

        # Count element types
        password_count = sum(1 for e in elements if e['type'] == 'password_input')
        email_count = sum(1 for e in elements if e['type'] == 'email_input')
        file_count = sum(1 for e in elements if e['type'] == 'file_upload')
        form_field_count = len(get_form_fields_only(snapshot))
        button_count = sum(1 for e in elements if e['type'] in ('button', 'submit_button'))

        # Detect CAPTCHA
        captcha_indicators = ['captcha', 'recaptcha', 'hcaptcha', 'verify you are human']
        if any(ind in all_text for ind in captcha_indicators):
            analysis.page_type = PageType.CAPTCHA
            analysis.captcha_present = True
            analysis.requires_human = True
            analysis.human_reason = "CAPTCHA detected"
            analysis.confidence = 90
            return analysis

        # Detect LOGIN page
        if password_count >= 1 and form_field_count <= 4:
            login_keywords = ['sign in', 'login', 'log in', 'welcome back']
            if any(kw in all_text for kw in login_keywords) or 'login' in url:
                analysis.page_type = PageType.LOGIN
                analysis.page_purpose = "Login to existing account"
                analysis.confidence = 90
                return analysis

        # Detect REGISTRATION page
        if password_count >= 1 and form_field_count >= 4:
            reg_keywords = ['sign up', 'register', 'create account', 'join', 'get started']
            if any(kw in all_text for kw in reg_keywords) or any(kw in url for kw in ['register', 'signup', 'join']):
                analysis.page_type = PageType.REGISTRATION
                analysis.page_purpose = "Register new account"
                analysis.confidence = 85
                return analysis

        # Detect EMAIL VERIFICATION
        verify_keywords = ['verify your email', 'check your email', 'confirmation email', 'verify your account']
        if any(kw in all_text for kw in verify_keywords):
            analysis.page_type = PageType.EMAIL_VERIFICATION
            analysis.page_purpose = "Email verification required"
            analysis.requires_human = True
            analysis.human_reason = "Email verification needed"
            analysis.confidence = 85
            return analysis

        # Detect CONFIRMATION/SUCCESS page
        success_keywords = ['application submitted', 'thank you', 'successfully', 'application received', 'confirmed']
        if any(kw in all_text for kw in success_keywords) and form_field_count <= 2:
            analysis.page_type = PageType.CONFIRMATION
            analysis.page_purpose = "Application/action confirmed"
            analysis.confidence = 80
            return analysis

        # Detect ERROR page
        error_keywords = ['error', 'something went wrong', 'page not found', '404', '500']
        if any(kw in all_text for kw in error_keywords) and form_field_count == 0:
            analysis.page_type = PageType.ERROR
            analysis.page_purpose = "Error page"
            analysis.confidence = 75
            return analysis

        # Detect FILE UPLOAD focused page
        if file_count >= 1 and form_field_count <= 3:
            upload_keywords = ['resume', 'cv', 'upload', 'attach']
            if any(kw in all_text for kw in upload_keywords):
                analysis.page_type = PageType.FILE_UPLOAD
                analysis.page_purpose = "File upload (resume/documents)"
                analysis.confidence = 80
                return analysis

        # Detect REVIEW page (before final submit)
        review_keywords = ['review', 'summary', 'confirm your', 'review your application']
        if any(kw in all_text for kw in review_keywords) and form_field_count <= 2:
            analysis.page_type = PageType.REVIEW
            analysis.page_purpose = "Review before submission"
            analysis.confidence = 75
            return analysis

        # Detect JOB LISTING page
        job_keywords = ['apply', 'easy apply', 'job description', 'requirements', 'qualifications']
        if any(kw in all_text for kw in job_keywords) and form_field_count <= 2:
            analysis.page_type = PageType.JOB_LISTING
            analysis.page_purpose = "Job listing page"
            analysis.confidence = 70
            return analysis

        # Detect DASHBOARD
        dash_keywords = ['dashboard', 'my applications', 'my jobs', 'profile', 'settings']
        if any(kw in all_text for kw in dash_keywords) and form_field_count <= 3:
            analysis.page_type = PageType.DASHBOARD
            analysis.page_purpose = "User dashboard"
            analysis.confidence = 65
            return analysis

        # Default: FORM (has fillable fields)
        if form_field_count >= 2:
            analysis.page_type = PageType.FORM
            analysis.page_purpose = "Form page with fields to fill"
            analysis.confidence = 60
            return analysis

        # Unknown
        analysis.page_type = PageType.UNKNOWN
        analysis.page_purpose = "Unrecognized page"
        analysis.confidence = 30
        return analysis

    def _ai_classify(self, snapshot: Dict, goal: str = "") -> Optional[PageAnalysis]:
        """
        Use AI to classify the page when heuristics aren't confident enough.
        """
        try:
            from detached_flows.ai_decision.claude_fast import call_claude_fast
        except ImportError:
            logger.warning("Claude fast not available, skipping AI classification")
            return None

        dom_text = snapshot_to_text(snapshot, max_elements=30)

        prompt = f"""Classify this webpage and identify the best action to take.

**Current Goal:** {goal or 'Navigate and interact with this job-related page'}

**Page DOM:**
{dom_text}

**IMPORTANT rules for requires_human:**
- Set requires_human to FALSE for job application forms, even if they have many fields, resume uploads, salary questions, or essay-style questions. An AI bot CAN fill these using the applicant's profile data.
- ONLY set requires_human to TRUE for: CAPTCHA/bot detection, email/phone verification requiring a real inbox, payment/fee pages, or 2FA/MFA challenges.
- Job application forms are NEVER requires_human — that is the bot's primary purpose.

**Respond with JSON only:**
{{
    "page_type": "login|registration|form|job_listing|confirmation|error|captcha|dashboard|email_verification|profile_completion|file_upload|review|unknown",
    "page_purpose": "One sentence describing what this page is for",
    "confidence": 0-100,
    "captcha_present": true/false,
    "requires_human": true/false,
    "human_reason": "reason if requires_human is true, else empty string",
    "primary_action_index": null or element index number for the main button to click,
    "is_multi_step": true/false
}}"""

        try:
            response = call_claude_fast(prompt, timeout=10)

            # Parse JSON from response
            if '```json' in response:
                response = response.split('```json')[1].split('```')[0]
            elif '```' in response:
                response = response.split('```')[1].split('```')[0]

            data = json.loads(response.strip())

            analysis = PageAnalysis(
                page_type=data.get('page_type', PageType.UNKNOWN),
                page_purpose=data.get('page_purpose', ''),
                confidence=data.get('confidence', 50),
                captcha_present=data.get('captcha_present', False),
                requires_human=data.get('requires_human', False),
                human_reason=data.get('human_reason', ''),
                is_multi_step=data.get('is_multi_step', False),
            )

            # Set primary action from AI recommendation
            action_idx = data.get('primary_action_index')
            if action_idx is not None:
                elements = snapshot.get('elements', [])
                if 0 <= action_idx < len(elements):
                    analysis.primary_action = elements[action_idx]

            logger.info(f"AI classification: {analysis.page_type} ({analysis.confidence}%)")
            return analysis

        except Exception as e:
            logger.error(f"AI page classification failed: {e}")
            return None

    def _identify_actions(self, analysis: PageAnalysis):
        """Identify primary and secondary actions from buttons."""
        if analysis.primary_action:
            return  # Already set by AI

        buttons = analysis.buttons
        if not buttons:
            return

        # Priority keywords for primary action
        primary_keywords = [
            'submit', 'apply', 'next', 'continue', 'register',
            'sign up', 'create account', 'sign in', 'login', 'log in',
            'save', 'confirm', 'review'
        ]

        # Keywords for actions to AVOID
        avoid_keywords = [
            'cancel', 'back', 'close', 'skip', 'withdraw', 'delete',
            'remove', 'discard', 'logout', 'sign out'
        ]

        # Find primary action
        for keyword in primary_keywords:
            for btn in buttons:
                label = (btn.get('label') or btn.get('current_value') or '').lower()
                if keyword in label:
                    analysis.primary_action = btn
                    break
            if analysis.primary_action:
                break

        # Fallback: first submit button
        if not analysis.primary_action:
            for btn in buttons:
                if btn['type'] == 'submit_button':
                    analysis.primary_action = btn
                    break

        # Secondary actions: all other buttons that aren't avoid-listed
        for btn in buttons:
            if btn == analysis.primary_action:
                continue
            label = (btn.get('label') or btn.get('current_value') or '').lower()
            if not any(kw in label for kw in avoid_keywords):
                analysis.secondary_actions.append(btn)

    def _detect_multi_step(self, analysis: PageAnalysis, snapshot: Dict):
        """Detect if this is part of a multi-step form."""
        progress = snapshot.get('progress_indicators', [])

        if progress:
            analysis.is_multi_step = True
            for p in progress:
                try:
                    if p.get('value') and p.get('max'):
                        analysis.current_step = int(p['value'])
                        analysis.total_steps = int(p['max'])
                        break
                except (ValueError, TypeError):
                    pass

        # Also check headings for step indicators
        headings = snapshot.get('page', {}).get('headings', [])
        for h in headings:
            text = h.get('text', '').lower()
            if 'step' in text:
                analysis.is_multi_step = True
                # Try to extract step numbers: "Step 2 of 5"
                import re
                match = re.search(r'step\s+(\d+)\s+(?:of|/)\s+(\d+)', text)
                if match:
                    analysis.current_step = int(match.group(1))
                    analysis.total_steps = int(match.group(2))

    def _check_human_needed(self, analysis: PageAnalysis):
        """Check if human intervention is needed."""
        if analysis.requires_human:
            return  # Already flagged

        # CAPTCHA
        if analysis.captcha_present:
            analysis.requires_human = True
            analysis.human_reason = "CAPTCHA detected"
            return

        # Email verification
        if analysis.page_type == PageType.EMAIL_VERIFICATION:
            analysis.requires_human = True
            analysis.human_reason = "Email verification required"
            return

        # Unknown page with low confidence
        if analysis.page_type == PageType.UNKNOWN and analysis.confidence < 50:
            analysis.requires_human = True
            analysis.human_reason = "Page not recognized, human review needed"
            return

        # Check for payment/fee indicators
        errors = analysis.errors_visible
        page_text = ' '.join(errors).lower()
        if any(kw in page_text for kw in ['payment', 'fee', 'charge', 'pay now', 'credit card']):
            analysis.requires_human = True
            analysis.human_reason = "Payment/fee detected"

    def clear_cache(self):
        """Clear the analysis cache."""
        self._cache.clear()
