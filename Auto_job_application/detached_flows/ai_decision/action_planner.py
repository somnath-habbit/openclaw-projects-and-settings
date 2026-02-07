"""
Action Planner - AI-powered action sequence planning for page interactions.

Given a page analysis and a goal, determines the sequence of actions to take.
This replaces hardcoded form-filling logic with intelligent, adaptive planning.

Usage:
    planner = ActionPlanner(profile, credential_manager)
    plan = planner.plan_actions(page_analysis, goal="fill job application")
    # Returns ActionPlan with ordered actions to execute
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger("ActionPlanner")


class ActionType(str, Enum):
    FILL = "fill"          # Fill a text/number/email field
    SELECT = "select"      # Select from dropdown
    CHECK = "check"        # Check a checkbox
    UNCHECK = "uncheck"    # Uncheck a checkbox
    RADIO = "radio"        # Select a radio option
    CLICK = "click"        # Click a button/link
    UPLOAD = "upload"      # Upload a file
    TYPE_RICH = "type_rich"  # Type into rich text editor
    WAIT = "wait"          # Wait for something
    SCROLL = "scroll"      # Scroll the page
    SKIP = "skip"          # Skip this element
    ESCALATE = "escalate"  # Escalate to human


class Strategy(str, Enum):
    FILL_AND_SUBMIT = "fill_and_submit"
    NAVIGATE = "navigate"
    WAIT = "wait"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    LOGIN = "login"
    REGISTER = "register"
    UPLOAD = "upload"
    REVIEW_AND_SUBMIT = "review_and_submit"


@dataclass
class PlannedAction:
    """A single action to execute on the page."""
    action: ActionType
    element_index: int  # Index in the DOM snapshot elements
    value: str = ""     # Value to fill/select
    source: str = ""    # Where the value came from (e.g., "profile.name")
    reason: str = ""    # Why this action
    confidence: int = 100  # 0-100 confidence in this action
    fallback: str = ""  # What to do if this fails


@dataclass
class ActionPlan:
    """Complete action plan for a page."""
    strategy: Strategy
    actions: List[PlannedAction] = field(default_factory=list)
    expected_outcome: str = ""
    fallback_strategy: str = ""
    requires_confirmation: bool = False
    confirmation_reason: str = ""


class ActionPlanner:
    """
    Plans actions for page interactions based on analysis + profile data.

    Uses a combination of rule-based planning (fast, no API cost) and
    AI planning (for complex/unknown pages).
    """

    def __init__(self, profile: dict, credential_manager=None):
        """
        Args:
            profile: User profile dict from user_profile.json
            credential_manager: Optional CredentialManager for credential lookups
        """
        self.profile = profile
        self.cred_manager = credential_manager

    def plan_actions(
        self,
        analysis,  # PageAnalysis
        goal: str = "",
        site_name: str = "",
        job_context: dict = None,
    ) -> ActionPlan:
        """
        Create an action plan for the current page.

        Args:
            analysis: PageAnalysis from PageAnalyzer
            goal: Current goal (e.g., "apply to job", "register account")
            site_name: Name of the site (for site-specific rules)
            job_context: Optional job details for context

        Returns:
            ActionPlan with ordered actions
        """
        from detached_flows.ai_decision.page_analyzer import PageType

        page_type = analysis.page_type
        job_context = job_context or {}

        # Route to appropriate planner based on page type
        if analysis.requires_human:
            return ActionPlan(
                strategy=Strategy.ESCALATE_TO_HUMAN,
                expected_outcome="Human intervention needed",
                fallback_strategy=analysis.human_reason
            )

        if page_type == PageType.LOGIN:
            return self._plan_login(analysis, site_name)

        if page_type == PageType.REGISTRATION:
            return self._plan_registration(analysis, site_name)

        if page_type == PageType.FORM or page_type == PageType.PROFILE_COMPLETION:
            return self._plan_form_fill(analysis, goal, site_name, job_context)

        if page_type == PageType.FILE_UPLOAD:
            return self._plan_file_upload(analysis)

        if page_type == PageType.REVIEW:
            return self._plan_review_submit(analysis)

        if page_type == PageType.JOB_LISTING:
            return self._plan_job_apply(analysis)

        if page_type == PageType.CONFIRMATION:
            return ActionPlan(
                strategy=Strategy.NAVIGATE,
                expected_outcome="Application confirmed, done."
            )

        if page_type == PageType.CAPTCHA:
            return ActionPlan(
                strategy=Strategy.ESCALATE_TO_HUMAN,
                expected_outcome="CAPTCHA solved by human",
                fallback_strategy="Skip this application"
            )

        # Unknown page - try AI planning
        return self._plan_with_ai(analysis, goal, site_name, job_context)

    def _plan_login(self, analysis, site_name: str) -> ActionPlan:
        """Plan login actions."""
        plan = ActionPlan(
            strategy=Strategy.LOGIN,
            expected_outcome="Logged in, redirected to dashboard or job page"
        )

        unfilled = analysis.unfilled_fields

        for field_el in unfilled:
            field_type = field_el['type']
            label = (field_el.get('label') or '').lower()
            category = field_el.get('field_category', '')

            if field_type == 'email_input' or 'email' in label or 'username' in label:
                # Get email from profile
                email = self._get_profile_value('email', '')
                plan.actions.append(PlannedAction(
                    action=ActionType.FILL,
                    element_index=field_el['index'],
                    value=email,
                    source="profile.email",
                    reason="Login email/username"
                ))

            elif field_type == 'password_input' or 'password' in label:
                # Password will be filled from credential manager at execution time
                plan.actions.append(PlannedAction(
                    action=ActionType.FILL,
                    element_index=field_el['index'],
                    value="__CREDENTIAL_PASSWORD__",
                    source=f"credentials.{site_name}",
                    reason="Login password"
                ))

        # Check "Remember me" if present
        for field_el in analysis.form_fields:
            if field_el['type'] == 'checkbox':
                label = (field_el.get('label') or '').lower()
                if 'remember' in label or 'keep me' in label or 'stay signed' in label:
                    if field_el.get('current_value') != 'checked':
                        plan.actions.append(PlannedAction(
                            action=ActionType.CHECK,
                            element_index=field_el['index'],
                            reason="Stay logged in"
                        ))

        # Click login button
        if analysis.primary_action:
            plan.actions.append(PlannedAction(
                action=ActionType.CLICK,
                element_index=analysis.primary_action['index'],
                reason="Submit login form"
            ))

        return plan

    def _plan_registration(self, analysis, site_name: str) -> ActionPlan:
        """Plan registration form actions."""
        plan = ActionPlan(
            strategy=Strategy.REGISTER,
            expected_outcome="Account created, redirected to verification or dashboard",
            requires_confirmation=True,
            confirmation_reason=f"First-time registration on {site_name}"
        )

        unfilled = analysis.unfilled_fields
        profile_data = self.profile.get('profile', {})

        for field_el in unfilled:
            field_type = field_el['type']
            label = (field_el.get('label') or '').lower()

            action = self._map_field_to_action(field_el, profile_data)
            if action:
                plan.actions.append(action)

        # Click register button
        if analysis.primary_action:
            plan.actions.append(PlannedAction(
                action=ActionType.CLICK,
                element_index=analysis.primary_action['index'],
                reason="Submit registration form"
            ))

        return plan

    def _plan_form_fill(
        self, analysis, goal: str, site_name: str, job_context: dict
    ) -> ActionPlan:
        """Plan generic form filling (job application, profile, etc.)."""
        plan = ActionPlan(
            strategy=Strategy.FILL_AND_SUBMIT,
            expected_outcome="Form submitted, moved to next step or confirmation"
        )

        unfilled = analysis.unfilled_fields
        profile_data = self.profile.get('profile', {})

        # Map each unfilled field to an action
        for field_el in unfilled:
            action = self._map_field_to_action(field_el, profile_data, job_context)
            if action:
                plan.actions.append(action)

        # Handle file uploads that might be on this page
        for field_el in analysis.form_fields:
            if field_el['type'] == 'file_upload':
                label = (field_el.get('label') or '').lower()
                if 'resume' in label or 'cv' in label:
                    plan.actions.append(PlannedAction(
                        action=ActionType.UPLOAD,
                        element_index=field_el['index'],
                        value="__RESUME_PATH__",
                        source="config.MASTER_PDF",
                        reason="Upload resume"
                    ))
                elif 'cover' in label:
                    plan.actions.append(PlannedAction(
                        action=ActionType.UPLOAD,
                        element_index=field_el['index'],
                        value="__AI_GENERATE_COVER_LETTER__",
                        source="ai.generate",
                        reason="Upload AI-generated cover letter"
                    ))

        # Check any terms/agreement checkboxes
        for field_el in analysis.form_fields:
            if field_el['type'] == 'checkbox':
                label = (field_el.get('label') or '').lower()
                value = field_el.get('current_value', '')
                if value != 'checked' and any(
                    kw in label for kw in ['agree', 'terms', 'accept', 'consent', 'acknowledge']
                ):
                    plan.actions.append(PlannedAction(
                        action=ActionType.CHECK,
                        element_index=field_el['index'],
                        reason="Accept terms/conditions"
                    ))

        # Click next/submit button
        if analysis.primary_action:
            plan.actions.append(PlannedAction(
                action=ActionType.CLICK,
                element_index=analysis.primary_action['index'],
                reason="Submit form / go to next step"
            ))

        return plan

    def _plan_file_upload(self, analysis) -> ActionPlan:
        """Plan file upload page actions."""
        plan = ActionPlan(
            strategy=Strategy.UPLOAD,
            expected_outcome="Files uploaded, moved to next step"
        )

        for field_el in analysis.form_fields:
            if field_el['type'] == 'file_upload':
                label = (field_el.get('label') or '').lower()
                if 'resume' in label or 'cv' in label:
                    plan.actions.append(PlannedAction(
                        action=ActionType.UPLOAD,
                        element_index=field_el['index'],
                        value="__RESUME_PATH__",
                        source="config.MASTER_PDF",
                        reason="Upload resume"
                    ))
                else:
                    plan.actions.append(PlannedAction(
                        action=ActionType.ESCALATE,
                        element_index=field_el['index'],
                        reason=f"Unknown file upload: {field_el.get('label', 'unknown')}"
                    ))

        if analysis.primary_action:
            plan.actions.append(PlannedAction(
                action=ActionType.CLICK,
                element_index=analysis.primary_action['index'],
                reason="Continue after upload"
            ))

        return plan

    def _plan_review_submit(self, analysis) -> ActionPlan:
        """Plan review page - just click submit."""
        plan = ActionPlan(
            strategy=Strategy.REVIEW_AND_SUBMIT,
            expected_outcome="Application submitted"
        )

        if analysis.primary_action:
            plan.actions.append(PlannedAction(
                action=ActionType.CLICK,
                element_index=analysis.primary_action['index'],
                reason="Submit application"
            ))

        return plan

    def _plan_job_apply(self, analysis) -> ActionPlan:
        """Plan clicking the Apply button on a job listing."""
        plan = ActionPlan(
            strategy=Strategy.NAVIGATE,
            expected_outcome="Application form opened"
        )

        # Find the apply button
        for btn in analysis.buttons:
            label = (btn.get('label') or btn.get('current_value') or '').lower()
            if 'apply' in label:
                plan.actions.append(PlannedAction(
                    action=ActionType.CLICK,
                    element_index=btn['index'],
                    reason="Click Apply button"
                ))
                break

        return plan

    def _plan_with_ai(
        self, analysis, goal: str, site_name: str, job_context: dict
    ) -> ActionPlan:
        """Use AI to plan actions for unknown/complex pages."""
        try:
            from detached_flows.ai_decision.claude_fast import call_claude_fast
            from detached_flows.ai_decision.dom_snapshot import snapshot_to_text
        except ImportError:
            return ActionPlan(
                strategy=Strategy.ESCALATE_TO_HUMAN,
                expected_outcome="AI not available, needs human"
            )

        snapshot = analysis.raw_snapshot
        if not snapshot:
            return ActionPlan(strategy=Strategy.ESCALATE_TO_HUMAN)

        dom_text = snapshot_to_text(snapshot, max_elements=30)
        profile_summary = self._build_profile_summary()

        prompt = f"""Plan the actions to take on this webpage.

**Goal:** {goal or 'Complete the current step of the job application'}
**Site:** {site_name or 'Unknown'}
**Job:** {job_context.get('title', 'Unknown')} at {job_context.get('company', 'Unknown')}

**Candidate Profile:**
{profile_summary}

**Page DOM:**
{dom_text}

**Respond with JSON only:**
{{
    "strategy": "fill_and_submit|navigate|wait|escalate_to_human",
    "actions": [
        {{
            "action": "fill|select|check|click|upload|skip|escalate",
            "element_index": 0,
            "value": "the value to fill",
            "reason": "why this action"
        }}
    ],
    "expected_outcome": "what should happen after these actions"
}}

Rules:
- Only reference element indices that exist in the DOM above
- For passwords, use "__CREDENTIAL_PASSWORD__" as value
- For resume uploads, use "__RESUME_PATH__" as value
- For unknown questions, provide your best answer based on the profile
- Never click Withdraw, Delete, or Cancel buttons
- If unsure, use "escalate" action"""

        try:
            response = call_claude_fast(prompt, timeout=15)

            if '```json' in response:
                response = response.split('```json')[1].split('```')[0]
            elif '```' in response:
                response = response.split('```')[1].split('```')[0]

            data = json.loads(response.strip())

            plan = ActionPlan(
                strategy=Strategy(data.get('strategy', 'fill_and_submit')),
                expected_outcome=data.get('expected_outcome', '')
            )

            for action_data in data.get('actions', []):
                action_type = action_data.get('action', 'skip')
                try:
                    action_enum = ActionType(action_type)
                except ValueError:
                    action_enum = ActionType.SKIP

                plan.actions.append(PlannedAction(
                    action=action_enum,
                    element_index=action_data.get('element_index', 0),
                    value=action_data.get('value', ''),
                    reason=action_data.get('reason', ''),
                    source="ai.planned"
                ))

            logger.info(f"AI planned {len(plan.actions)} actions: {plan.strategy}")
            return plan

        except Exception as e:
            logger.error(f"AI action planning failed: {e}")
            return ActionPlan(
                strategy=Strategy.ESCALATE_TO_HUMAN,
                expected_outcome="AI planning failed",
                fallback_strategy=str(e)
            )

    def _map_field_to_action(
        self,
        field_el: Dict,
        profile_data: dict,
        job_context: dict = None
    ) -> Optional[PlannedAction]:
        """
        Map a form field to a fill action based on profile data.

        Uses label matching to find the right profile value.
        Returns None if no mapping found (will be handled by AI batch fill).
        """
        field_type = field_el['type']
        label = (field_el.get('label') or '').lower()
        category = field_el.get('field_category', '')

        # Skip buttons, links
        if field_type in ('button', 'submit_button', 'link'):
            return None

        # Personal info mapping
        if category == 'personal_info' or any(kw in label for kw in ['first name', 'given name']):
            name = self._get_profile_value('name', '')
            first_name = name.split()[0] if name else ''
            if first_name:
                return PlannedAction(
                    action=ActionType.FILL,
                    element_index=field_el['index'],
                    value=first_name,
                    source="profile.name.first"
                )

        if any(kw in label for kw in ['last name', 'surname', 'family name']):
            name = self._get_profile_value('name', '')
            last_name = ' '.join(name.split()[1:]) if name and len(name.split()) > 1 else ''
            if last_name:
                return PlannedAction(
                    action=ActionType.FILL,
                    element_index=field_el['index'],
                    value=last_name,
                    source="profile.name.last"
                )

        if 'full name' in label or label == 'name':
            name = self._get_profile_value('name', '')
            if name:
                return PlannedAction(
                    action=ActionType.FILL,
                    element_index=field_el['index'],
                    value=name,
                    source="profile.name"
                )

        # Contact mapping
        if field_type == 'email_input' or 'email' in label:
            email = self._get_profile_value('email', '')
            if email:
                return PlannedAction(
                    action=ActionType.FILL,
                    element_index=field_el['index'],
                    value=email,
                    source="profile.email"
                )

        if field_type == 'phone_input' or 'phone' in label or 'mobile' in label:
            phone = self._get_profile_value('phone', '')
            if phone:
                return PlannedAction(
                    action=ActionType.FILL,
                    element_index=field_el['index'],
                    value=phone,
                    source="profile.phone"
                )

        # Location
        if 'city' in label or 'location' in label:
            location = self._get_profile_value('location', '')
            if location:
                return PlannedAction(
                    action=ActionType.FILL,
                    element_index=field_el['index'],
                    value=location,
                    source="profile.location"
                )

        # LinkedIn URL
        if 'linkedin' in label:
            linkedin = self._get_profile_value('linkedinUrl', '')
            if linkedin:
                return PlannedAction(
                    action=ActionType.FILL,
                    element_index=field_el['index'],
                    value=linkedin,
                    source="profile.linkedinUrl"
                )

        # Password (for registration)
        if field_type == 'password_input':
            return PlannedAction(
                action=ActionType.FILL,
                element_index=field_el['index'],
                value="__CREDENTIAL_PASSWORD__",
                source="credentials.generated"
            )

        # Dropdown fields - need AI to select the right option
        if field_type in ('select', 'combobox', 'listbox'):
            # Will be handled by AI batch fill
            return None

        # For remaining fields - return None to let AI batch fill handle them
        return None

    def _get_profile_value(self, key: str, default: str = "") -> str:
        """Get a value from the user profile."""
        profile_data = self.profile.get('profile', {})

        if key in profile_data:
            return str(profile_data[key])

        metrics = self.profile.get('keyMetrics', {})
        if key in metrics:
            return str(metrics[key])

        experiences = self.profile.get('experiences', [])
        if experiences:
            if key == 'current_company':
                return experiences[0].get('company', default)
            if key == 'current_role':
                return experiences[0].get('position', default)

        return default

    def _build_profile_summary(self) -> str:
        """Build concise profile summary for AI prompts."""
        p = self.profile.get('profile', {})
        metrics = self.profile.get('keyMetrics', {})
        experiences = self.profile.get('experiences', [])
        current_exp = experiences[0] if experiences else {}

        lines = []
        if p.get('name'):
            lines.append(f"Name: {p['name']}")
        if p.get('title'):
            lines.append(f"Title: {p['title']}")
        if p.get('email'):
            lines.append(f"Email: {p['email']}")
        if p.get('phone'):
            lines.append(f"Phone: {p['phone']}")
        if p.get('location'):
            lines.append(f"Location: {p['location']}")
        if metrics.get('yearsExperience'):
            lines.append(f"Experience: {metrics['yearsExperience']} years")
        if current_exp:
            lines.append(f"Current: {current_exp.get('position', '')} at {current_exp.get('company', '')}")

        return '\n'.join(lines)
