"""
Universal Question Handler - 5-tier answer generation for any job site.

Expands the LinkedIn-specific QuestionHandler to work across all job sites
with smarter profile matching, site-specific rules, and semantic matching.

Tier 1: PROFILE DIRECT MATCH - Name, email, phone from profile
Tier 2: SITE-SPECIFIC RULES - Known field mappings per site
Tier 3: SEMANTIC MATCHING - AI matches question to profile fields
Tier 4: AI GENERATION - Full context AI answer
Tier 5: HUMAN ESCALATION - Can't answer, need human

Usage:
    handler = UniversalQuestionHandler(profile)
    answer = handler.answer(question, field_type="text", site="naukri", job_context={})
"""
import re
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("UniversalQuestionHandler")

# Profile field mappings for common labels
PROFILE_FIELD_MAP = {
    # Personal info
    'first name': 'name_first',
    'given name': 'name_first',
    'last name': 'name_last',
    'surname': 'name_last',
    'family name': 'name_last',
    'full name': 'name',
    'name': 'name',

    # Contact
    'email': 'email',
    'email address': 'email',
    'phone': 'phone',
    'phone number': 'phone',
    'mobile': 'phone',
    'mobile number': 'phone',

    # Location
    'city': 'location',
    'current city': 'location',
    'location': 'location',
    'current location': 'location',
    'address': 'address',

    # Professional
    'linkedin': 'linkedinUrl',
    'linkedin url': 'linkedinUrl',
    'linkedin profile': 'linkedinUrl',
    'github': 'githubUrl',
    'github url': 'githubUrl',
    'portfolio': 'portfolioUrl',
    'website': 'portfolioUrl',
    'personal website': 'portfolioUrl',

    # Current job
    'current company': 'current_company',
    'current employer': 'current_company',
    'company name': 'current_company',
    'current title': 'current_role',
    'current role': 'current_role',
    'current designation': 'current_role',
    'job title': 'current_role',
}

# Site-specific field mappings (known patterns per job site)
SITE_FIELD_MAP = {
    'naukri': {
        'current ctc': 'currentCTC',
        'expected ctc': 'expectedCTC',
        'annual salary': 'currentCTC',
        'notice period': 'noticePeriod',
        'total experience': 'yearsExperience',
        'key skills': 'skills',
        'resume headline': 'title',
    },
    'indeed': {
        'desired salary': 'expectedSalary',
        'desired job title': 'title',
    },
    'instahyre': {
        'current ctc': 'currentCTC',
        'expected ctc': 'expectedCTC',
        'notice period': 'noticePeriod',
    },
    'foundit': {
        'current salary': 'currentCTC',
        'expected salary': 'expectedCTC',
        'notice period': 'noticePeriod',
    },
    'linkedin': {
        'salary expectation': 'expectedSalary',
    },
}

# Numeric field indicators (label patterns that should return digits only)
NUMERIC_PATTERNS = [
    r'years?\s*(of)?\s*experience',
    r'how\s+many\s+years',
    r'ctc|salary|compensation|pay|lpa',
    r'notice\s+period',
    r'rate\s+your|scale\s+of|proficiency',
    r'gpa|cgpa|percentage|score',
    r'age|number\s+of',
]


class UniversalQuestionHandler:
    """
    5-tier answer generation system for any job application form.
    """

    def __init__(self, profile: dict, use_ai: bool = True):
        """
        Args:
            profile: User profile dict from user_profile.json
            use_ai: Whether to use AI for answer generation
        """
        self.profile = profile
        self.use_ai = use_ai
        self._human_answers = {}  # Stored human-provided answers

    def answer(
        self,
        question: str,
        field_type: str = "text",
        site_name: str = "",
        job_context: dict = None,
        options: List[str] = None,
    ) -> Optional[str]:
        """
        Generate an answer using the 5-tier system.

        Args:
            question: The field label/question text
            field_type: HTML field type (text, number, select, etc.)
            site_name: Name of the job site
            job_context: Job details for context
            options: Available options for select/radio fields

        Returns:
            Answer string, or None if human escalation needed
        """
        job_context = job_context or {}
        question_clean = question.strip()

        if not question_clean:
            return None

        # TIER 1: Profile Direct Match
        answer = self._tier1_profile_match(question_clean, field_type)
        if answer:
            logger.debug(f"Tier 1 match: '{question_clean[:40]}' → '{answer[:30]}'")
            return self._format_answer(answer, field_type, options)

        # TIER 2: Site-Specific Rules
        answer = self._tier2_site_rules(question_clean, field_type, site_name)
        if answer:
            logger.debug(f"Tier 2 match: '{question_clean[:40]}' → '{answer[:30]}'")
            return self._format_answer(answer, field_type, options)

        # TIER 3: Semantic Matching (AI matches question to profile field)
        if self.use_ai:
            answer = self._tier3_semantic_match(question_clean, field_type, options)
            if answer:
                logger.debug(f"Tier 3 match: '{question_clean[:40]}' → '{answer[:30]}'")
                return self._format_answer(answer, field_type, options)

        # TIER 4: AI Generation (full context answer)
        if self.use_ai:
            answer = self._tier4_ai_generate(
                question_clean, field_type, site_name, job_context, options
            )
            if answer:
                logger.debug(f"Tier 4 AI: '{question_clean[:40]}' → '{answer[:30]}'")
                return answer  # Already formatted by AI

        # TIER 5: Human Escalation
        logger.info(f"Tier 5: Human escalation needed for '{question_clean[:50]}'")
        return self._tier5_human_escalation(question_clean)

    def _tier1_profile_match(self, question: str, field_type: str) -> Optional[str]:
        """Direct profile field matching based on label keywords."""
        q_lower = question.lower().strip()

        # Remove common suffixes
        for suffix in ['*', '(required)', '(optional)', ':', '-']:
            q_lower = q_lower.rstrip(suffix).strip()

        # Try exact and partial matches against known field mappings
        for pattern, profile_key in PROFILE_FIELD_MAP.items():
            if pattern in q_lower or q_lower == pattern:
                value = self._get_profile_value(profile_key)
                if value:
                    return value

        return None

    def _tier2_site_rules(
        self, question: str, field_type: str, site_name: str
    ) -> Optional[str]:
        """Site-specific field mappings."""
        if not site_name:
            return None

        site_map = SITE_FIELD_MAP.get(site_name.lower(), {})
        q_lower = question.lower().strip()

        for pattern, profile_key in site_map.items():
            if pattern in q_lower:
                value = self._get_profile_value(profile_key)
                if value:
                    return value

        return None

    def _tier3_semantic_match(
        self, question: str, field_type: str, options: List[str] = None
    ) -> Optional[str]:
        """Use AI to match question to the closest profile field."""
        try:
            from detached_flows.ai_decision.claude_fast import call_claude_fast
        except ImportError:
            return None

        # Build available profile data
        profile_fields = self._get_all_profile_fields()
        if not profile_fields:
            return None

        profile_text = "\n".join(
            f"- {key}: {value}" for key, value in profile_fields.items() if value
        )

        options_text = ""
        if options:
            options_text = f"\nAvailable options: {', '.join(options[:15])}"

        prompt = f"""Match this form field to the best profile data. Return ONLY the answer value, nothing else.

**Field:** {question}
**Field type:** {field_type}
{options_text}

**Available Profile Data:**
{profile_text}

If no profile field matches, return exactly "NO_MATCH".
If the field asks for a dropdown option, return the exact option text.
If it's a number field, return only digits.
Return ONLY the answer, no explanation."""

        try:
            response = call_claude_fast(prompt, timeout=8)
            response = response.strip().strip('"').strip("'")

            if response == "NO_MATCH" or not response:
                return None

            return response

        except Exception as e:
            logger.debug(f"Tier 3 semantic match failed: {e}")
            return None

    def _tier4_ai_generate(
        self,
        question: str,
        field_type: str,
        site_name: str,
        job_context: dict,
        options: List[str] = None
    ) -> Optional[str]:
        """Generate answer using AI with full context."""
        try:
            from detached_flows.ai_decision.claude_fast import call_claude_fast
        except ImportError:
            return None

        profile_summary = self._build_profile_summary()

        options_text = ""
        if options:
            options_text = f"\nAvailable options (choose exactly one): {', '.join(options[:15])}"

        field_guidance = ""
        if self._is_numeric_field(question, field_type):
            field_guidance = "\nIMPORTANT: This is a numeric field. Return ONLY a number, no units or text."
        elif field_type == 'select' and options:
            field_guidance = "\nIMPORTANT: Return EXACTLY one of the provided options, word for word."

        prompt = f"""Answer this job application question. Return ONLY the answer, nothing else.

**Question:** {question}
**Field type:** {field_type}
**Site:** {site_name or 'Unknown'}
**Job:** {job_context.get('title', 'Unknown')} at {job_context.get('company', 'Unknown')}
{options_text}
{field_guidance}

**Candidate Profile:**
{profile_summary}

**Rules:**
- Be concise and professional
- No markdown formatting
- No explanations or reasoning
- Just the direct answer"""

        try:
            response = call_claude_fast(prompt, timeout=12)
            response = response.strip().strip('"').strip("'")

            if not response:
                return None

            # Clean up AI response
            # Remove common prefixes AI might add
            prefixes_to_remove = ['answer:', 'response:', 'a:', 'the answer is']
            response_lower = response.lower()
            for prefix in prefixes_to_remove:
                if response_lower.startswith(prefix):
                    response = response[len(prefix):].strip()
                    break

            return response

        except Exception as e:
            logger.error(f"Tier 4 AI generation failed: {e}")
            return None

    def _tier5_human_escalation(self, question: str) -> Optional[str]:
        """Check if we have a stored human answer for this question."""
        # Check stored human answers
        q_normalized = question.lower().strip()
        if q_normalized in self._human_answers:
            return self._human_answers[q_normalized]

        # No stored answer - return None to signal escalation needed
        return None

    def store_human_answer(self, question: str, answer: str):
        """Store an answer provided by human for future reuse."""
        q_normalized = question.lower().strip()
        self._human_answers[q_normalized] = answer
        logger.info(f"Stored human answer for: {question[:50]}")

    def _format_answer(
        self, answer: str, field_type: str, options: List[str] = None
    ) -> str:
        """Format answer based on field type."""
        if not answer:
            return answer

        # For numeric fields, extract digits only
        if self._is_numeric_field('', field_type) or field_type in ('number', 'number_input'):
            digits = re.sub(r'[^\d.]', '', str(answer))
            if digits:
                return digits

        # For select fields with options, find best match
        if options and field_type in ('select', 'radio'):
            answer_lower = answer.lower().strip()
            for opt in options:
                if opt.lower().strip() == answer_lower:
                    return opt  # Exact match
            # Partial match
            for opt in options:
                if answer_lower in opt.lower() or opt.lower() in answer_lower:
                    return opt

        return answer

    def _is_numeric_field(self, question: str, field_type: str) -> bool:
        """Check if a field expects a numeric value."""
        if field_type in ('number', 'number_input'):
            return True

        q_lower = question.lower()
        return any(re.search(pattern, q_lower) for pattern in NUMERIC_PATTERNS)

    def _get_profile_value(self, key: str) -> Optional[str]:
        """Get a value from the user profile with smart key resolution."""
        profile_data = self.profile.get('profile', {})
        metrics = self.profile.get('keyMetrics', {})
        experiences = self.profile.get('experiences', [])

        # Handle composite keys
        if key == 'name_first':
            name = profile_data.get('name', '')
            return name.split()[0] if name else None

        if key == 'name_last':
            name = profile_data.get('name', '')
            parts = name.split()
            return ' '.join(parts[1:]) if len(parts) > 1 else None

        if key == 'current_company':
            if experiences:
                return experiences[0].get('company')
            return None

        if key == 'current_role':
            if experiences:
                return experiences[0].get('position')
            return None

        if key == 'skills':
            skills = self.profile.get('skills', [])
            if isinstance(skills, list):
                return ', '.join(skills[:10])
            return None

        # Direct profile lookup
        if key in profile_data:
            val = profile_data[key]
            return str(val) if val else None

        # Metrics lookup
        if key in metrics:
            val = metrics[key]
            return str(val) if val else None

        return None

    def _get_all_profile_fields(self) -> Dict[str, str]:
        """Get all available profile fields as a flat dict."""
        result = {}
        profile_data = self.profile.get('profile', {})
        metrics = self.profile.get('keyMetrics', {})
        experiences = self.profile.get('experiences', [])

        # Profile fields
        for key, value in profile_data.items():
            if value and isinstance(value, (str, int, float)):
                result[key] = str(value)

        # Metrics
        for key, value in metrics.items():
            if value and isinstance(value, (str, int, float)):
                result[key] = str(value)

        # Current experience
        if experiences:
            exp = experiences[0]
            result['current_company'] = exp.get('company', '')
            result['current_role'] = exp.get('position', '')
            result['current_duration'] = exp.get('duration', '')

        # Skills
        skills = self.profile.get('skills', [])
        if skills:
            result['skills'] = ', '.join(skills[:10]) if isinstance(skills, list) else str(skills)

        # Education
        education = self.profile.get('education', [])
        if education:
            edu = education[0]
            result['degree'] = edu.get('degree', '')
            result['university'] = edu.get('school', '')

        return {k: v for k, v in result.items() if v}

    def _build_profile_summary(self) -> str:
        """Build concise profile summary for AI prompts."""
        fields = self._get_all_profile_fields()

        lines = []
        priority_keys = [
            'name', 'title', 'email', 'phone', 'location',
            'yearsExperience', 'current_company', 'current_role',
            'skills', 'degree', 'university',
            'noticePeriod', 'expectedSalary', 'currentCTC',
        ]

        for key in priority_keys:
            if key in fields:
                lines.append(f"- {key}: {fields[key]}")

        # Add remaining fields
        for key, value in fields.items():
            if key not in priority_keys:
                lines.append(f"- {key}: {value}")

        return '\n'.join(lines[:20])
