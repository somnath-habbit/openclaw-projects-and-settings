"""
AI-powered question handler for job application forms.

Analyzes form questions and generates appropriate responses based on user profile.
Stores responses for reuse across applications.

Usage:
    handler = QuestionHandler()
    answer = handler.answer_question("What is your expected salary?", context={"job_title": "EM"})
"""
import os
import json
import sqlite3
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger("QuestionHandler")

# Common question patterns and their categories
QUESTION_PATTERNS = {
    "salary": [
        r"salary", r"compensation", r"pay", r"expected.*(salary|pay)",
        r"desired.*(salary|compensation)", r"salary.*expectation",
        r"ctc", r"cost.*to.*company", r"current.*ctc", r"expected.*ctc",
        r"drawn.*ctc", r"last.*ctc", r"lpa"
    ],
    "experience_years": [
        r"years.*experience", r"experience.*years", r"how.*long.*worked",
        r"total.*experience"
    ],
    "work_authorization": [
        r"authorized.*work", r"work.*authorization", r"visa.*status",
        r"legally.*work", r"sponsorship", r"require.*visa"
    ],
    "start_date": [
        r"start.*date", r"when.*start", r"available.*start",
        r"earliest.*start", r"join.*date"
    ],
    "relocation": [
        r"relocate", r"relocation", r"willing.*move", r"open.*relocating"
    ],
    "remote_work": [
        r"remote", r"work.*from.*home", r"hybrid", r"in.*office",
        r"on.*site", r"wfh"
    ],
    "notice_period": [
        r"notice.*period", r"how.*soon", r"current.*notice",
        r"serving.*notice"
    ],
    "education": [
        r"degree", r"education", r"qualification", r"university",
        r"college", r"school"
    ],
    "skills": [
        r"proficien", r"experience.*with", r"familiar.*with",
        r"knowledge.*of", r"skill"
    ],
    "yes_no": [
        r"^(do|are|have|can|will|would|is|did).*\?$"
    ],
}


class QuestionHandler:
    """
    AI-powered handler for job application form questions.

    Features:
    - Analyzes questions using AI
    - Generates contextual answers
    - Caches responses for reuse
    - Learns from stored responses
    """

    def __init__(
        self,
        profile_path: Optional[str] = None,
        db_path: Optional[str] = None,
        use_ai: bool = True
    ):
        """
        Initialize question handler.

        Args:
            profile_path: Path to user_profile.json
            db_path: Path to database for response storage
            use_ai: Whether to use AI for generating responses
        """
        self.use_ai = use_ai
        self.ai_provider = os.getenv('AI_PROVIDER', 'openclaw').lower()

        # Load paths from config
        from detached_flows.config import PROFILE_PATH, DB_PATH
        self.profile_path = Path(profile_path) if profile_path else PROFILE_PATH
        self.db_path = Path(db_path) if db_path else DB_PATH

        # Load user profile
        self.profile = self._load_profile()

        # Initialize response cache
        self._init_response_table()

        # Cache for this session
        self._cache = {}

    def _load_profile(self) -> dict:
        """Load user profile from JSON file."""
        try:
            with open(self.profile_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load profile: {e}")
            return {}

    def _init_response_table(self):
        """Initialize the question_responses table if not exists."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS question_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_hash TEXT,
                question_text TEXT,
                question_type TEXT,
                response TEXT,
                job_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reuse_count INTEGER DEFAULT 0,
                last_used_at TIMESTAMP
            )
        """)

        # Add field_type column for type-aware caching (migration-safe)
        try:
            cursor.execute("ALTER TABLE question_responses ADD COLUMN field_type TEXT")
            logger.info("Added field_type column to question_responses table")
        except sqlite3.OperationalError:
            # Column already exists
            pass

        # Create composite index for question_hash + field_type lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_question_field_type
            ON question_responses(question_hash, field_type)
        """)

        # Create index for semantic search by question_type
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_question_type
            ON question_responses(question_type)
        """)

        conn.commit()
        conn.close()

    def _hash_question(self, question: str) -> str:
        """Create a normalized hash for question matching."""
        # Normalize: lowercase, remove extra spaces, remove punctuation
        normalized = re.sub(r'[^\w\s]', '', question.lower())
        normalized = ' '.join(normalized.split())
        return normalized

    def _categorize_question(self, question: str) -> str:
        """Categorize a question based on patterns."""
        question_lower = question.lower()

        for category, patterns in QUESTION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, question_lower):
                    return category

        return "general"

    def _get_cached_response(self, question: str, field_type: Optional[str] = None) -> Optional[str]:
        """
        Look up a previously stored response.

        Type-aware caching: Only returns cached response if both question AND field_type match.
        This ensures "Expected salary?" returns "90" for number inputs and "90 LPA" for text inputs.
        """
        question_hash = self._hash_question(question)
        cache_key = f"{question_hash}_{field_type}" if field_type else question_hash

        # Check in-memory cache first
        if cache_key in self._cache:
            logger.debug(f"In-memory cache hit for: {question[:50]} (type: {field_type})")
            return self._cache[cache_key]

        # Check database with type-aware lookup
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if field_type:
            # Exact match: question + field_type
            cursor.execute("""
                SELECT response FROM question_responses
                WHERE question_hash = ? AND field_type = ?
                ORDER BY reuse_count DESC, created_at DESC
                LIMIT 1
            """, (question_hash, field_type))
        else:
            # Fallback: question only (for backwards compatibility)
            cursor.execute("""
                SELECT response FROM question_responses
                WHERE question_hash = ?
                ORDER BY reuse_count DESC, created_at DESC
                LIMIT 1
            """, (question_hash,))

        row = cursor.fetchone()
        conn.close()

        if row:
            self._cache[cache_key] = row[0]
            logger.debug(f"DB cache hit for: {question[:50]} (type: {field_type})")
            return row[0]

        return None

    def _store_response(
        self,
        question: str,
        response: str,
        question_type: str,
        job_id: Optional[str] = None,
        field_type: Optional[str] = None
    ):
        """
        Store a response for future reuse with type-aware caching.

        Stores question + field_type + response combination for precise matching.
        """
        question_hash = self._hash_question(question)
        cache_key = f"{question_hash}_{field_type}" if field_type else question_hash

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if this exact combination exists
        cursor.execute("""
            SELECT id, reuse_count FROM question_responses
            WHERE question_hash = ? AND field_type IS ?
        """, (question_hash, field_type))

        existing = cursor.fetchone()

        if existing:
            # Update existing record
            cursor.execute("""
                UPDATE question_responses
                SET reuse_count = ?,
                    last_used_at = CURRENT_TIMESTAMP,
                    response = ?
                WHERE id = ?
            """, (existing[1] + 1, response, existing[0]))
            logger.debug(f"Updated existing response (reuse_count: {existing[1] + 1})")
        else:
            # Insert new record
            cursor.execute("""
                INSERT INTO question_responses
                (question_hash, question_text, question_type, field_type, response, job_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (question_hash, question, question_type, field_type, response, job_id))
            logger.debug(f"Stored new response for: {question[:50]} (type: {field_type})")

        conn.commit()
        conn.close()

        # Update in-memory cache
        self._cache[cache_key] = response

    def _get_profile_value(self, key: str, default: str = "") -> str:
        """Get a value from the user profile."""
        # Try different paths in profile
        profile_data = self.profile.get('profile', {})

        # Direct key access
        if key in profile_data:
            return str(profile_data[key])

        # Try keyMetrics
        metrics = self.profile.get('keyMetrics', {})
        if key in metrics:
            return str(metrics[key])

        # Try experiences
        experiences = self.profile.get('experiences', [])
        if experiences and key == 'current_company':
            return experiences[0].get('company', default)
        if experiences and key == 'current_role':
            return experiences[0].get('position', default)

        return default

    def _generate_rule_based_answer(
        self,
        question: str,
        question_type: str,
        context: dict
    ) -> Optional[str]:
        """
        Generate answer using only saved profile data (no hardcoded defaults).
        Returns None if data not in profile - lets AI handle with full context.
        """

        # Try to get data from profile only (no defaults)
        if question_type == "salary":
            # Only return if explicitly in profile
            salary = self._get_profile_value('expectedSalary')
            if salary:
                return salary
            # No default - let AI decide based on profile context
            return None

        elif question_type == "notice_period":
            # Only return if explicitly in profile
            notice = self._get_profile_value('noticePeriod')
            if notice:
                # Extract number if question asks for days
                question_lower = question.lower()
                if "(in days)" in question_lower or "days" in question_lower:
                    import re
                    match = re.search(r'(\d+)', str(notice))
                    return match.group(1) if match else None
                return notice
            return None

        # All other question types: let AI handle with full profile context
        # No hardcoded answers - AI reads from user_profile.json
        return None

    def _generate_ai_answer(
        self,
        question: str,
        question_type: str,
        context: dict,
        similar_qa: list[dict] = None,
        field_type: str = None
    ) -> str:
        """
        Generate answer using AI with semantic context from similar questions.

        This enables semantic aliasing - AI learns from previously answered similar questions.
        """

        # Build prompt
        profile_summary = self._build_profile_summary()
        similar_qa = similar_qa or []

        # Build similar Q&A context for semantic learning
        similar_context = ""
        if similar_qa:
            similar_context = "\n**Previously Answered Similar Questions:**\n"
            for idx, qa in enumerate(similar_qa[:3], 1):  # Top 3 most relevant
                field_info = f" (field type: {qa['field_type']})" if qa['field_type'] else ""
                similar_context += f"{idx}. Q: {qa['question']}{field_info}\n   A: {qa['answer']}\n"
            similar_context += "\nUse these as examples to maintain consistency.\n"

        # Field type guidance
        field_guidance = ""
        if field_type == "number":
            field_guidance = "\n**IMPORTANT:** This is a NUMBER input field. Return ONLY the numeric value, no units or text (e.g., '90' not '90 LPA')."
        elif field_type == "email":
            field_guidance = "\n**IMPORTANT:** This is an EMAIL input field. Return only a valid email address."
        elif field_type == "url":
            field_guidance = "\n**IMPORTANT:** This is a URL input field. Return only a valid URL (e.g., 'https://example.com')."

        prompt = f"""You are filling out a job application form. Provide ONLY the answer text that will go in the form field.

**Candidate Profile:**
{profile_summary}

**Job Context:**
- Title: {context.get('job_title', 'Unknown')}
- Company: {context.get('company', 'Unknown')}
- Location: {context.get('location', 'Unknown')}

{similar_context}
**Question:** {question}
**Question Type:** {question_type}
**Field Type:** {field_type or 'text'}
{field_guidance}

**CRITICAL INSTRUCTIONS:**
- Return ONLY the answer text that goes in the form field
- NO markdown formatting (no **, ---, etc.)
- NO explanations, rationales, or reasoning
- NO line breaks or extra whitespace
- Just the direct, concise answer
- Be professional and truthful based on profile
- For experience questions, be realistic about technology maturity (e.g., LangChain is ~2 years old)
- Learn from similar Q&A examples to maintain consistency

**Answer (raw text only, no formatting):**"""

        try:
            if self.ai_provider == 'openclaw':
                return self._call_openclaw(prompt)
            else:
                # Fallback to rule-based
                answer = self._generate_rule_based_answer(question, question_type, context)
                if answer:
                    return answer
                # Final fallback for rating/scale questions
                return self._get_fallback_answer(question, question_type) or "N/A"
        except Exception as e:
            logger.error(f"AI answer generation failed: {e}")
            answer = self._generate_rule_based_answer(question, question_type, context)
            if answer:
                return answer
            # Final fallback for rating/scale questions
            return self._get_fallback_answer(question, question_type) or "N/A"

    def _build_profile_summary(self) -> str:
        """Build a concise profile summary for AI prompts."""
        p = self.profile.get('profile', {})
        metrics = self.profile.get('keyMetrics', {})
        experiences = self.profile.get('experiences', [])

        current_exp = experiences[0] if experiences else {}

        return f"""
- Name: {p.get('name', 'Candidate')}
- Title: {p.get('title', 'Engineering Manager')}
- Years of Experience: {metrics.get('yearsExperience', '12+')}
- Current Role: {current_exp.get('position', '')} at {current_exp.get('company', '')}
- Location: {p.get('location', 'Bengaluru, India')}
- Notice Period: 30 days
""".strip()

    def _get_similar_qa(self, question: str, question_type: str, limit: int = 5) -> list[dict]:
        """
        Get similar previously answered questions to help AI make better decisions.

        This enables semantic aliasing - AI can see that "desired salary", "expected CTC",
        and "compensation expectations" all have similar answers and learn the pattern.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get Q&A of the same type (category-based similarity)
        cursor.execute("""
            SELECT question_text, response, field_type, reuse_count
            FROM question_responses
            WHERE question_type = ? AND response != 'N/A'
            ORDER BY reuse_count DESC, created_at DESC
            LIMIT ?
        """, (question_type, limit))

        results = []
        for row in cursor.fetchall():
            results.append({
                'question': row[0],
                'answer': row[1],
                'field_type': row[2],
                'reuse_count': row[3]
            })

        conn.close()

        if results:
            logger.info(f"Found {len(results)} similar Q&A for type '{question_type}' to help AI")

        return results

    def _get_fallback_answer(self, question: str, question_type: str) -> Optional[str]:
        """
        Get fallback answer for common question patterns when AI/rules fail.
        Provides smart defaults based on question patterns.
        """
        q_lower = question.lower()

        # Rating/Scale questions (1-10, 1-5, etc.)
        if any(pattern in q_lower for pattern in ['scale of', 'rate your', 'how would you rate', 'proficiency', 'expertise']):
            if any(tech in q_lower for tech in ['architect', 'system design', 'lead', 'manage']):
                return "9"  # Senior level expertise
            elif any(tech in q_lower for tech in ['aws', 'cloud', 'docker', 'kubernetes', 'container', 'microservice']):
                return "8"  # Strong technical skills
            else:
                return "8"  # Default good rating for senior engineer

        # Years of experience questions
        if 'years' in q_lower and ('experience' in q_lower or 'worked' in q_lower):
            if any(tech in q_lower for tech in ['lead', 'manage', 'architect']):
                return "12+ years"
            elif any(tech in q_lower for tech in ['aws', 'cloud', 'python', 'node']):
                return "8+ years"
            else:
                return "5+ years"

        # Yes/No questions - default to Yes for common qualifications
        if question.endswith('?') and any(word in q_lower for word in ['do you', 'have you', 'are you', 'can you']):
            if any(keyword in q_lower for keyword in ['available', 'willing', 'authorized', 'eligible']):
                return "Yes"
            if any(keyword in q_lower for keyword in ['experience', 'worked with', 'familiar']):
                return "Yes, extensive experience"

        # Availability/start date
        if 'when' in q_lower and ('start' in q_lower or 'join' in q_lower or 'available' in q_lower):
            return "30 days notice period"

        # Relocation
        if 'relocate' in q_lower or 'relocation' in q_lower:
            return "Yes, open to relocation"

        # Remote work
        if 'remote' in q_lower or 'work from home' in q_lower:
            return "Yes, comfortable with remote/hybrid"

        # LinkedIn Profile
        if 'linkedin' in q_lower and ('profile' in q_lower or 'url' in q_lower):
            return "https://linkedin.com/in/somnath-ghosh"  # TODO: Get from profile

        # Website/Portfolio
        if 'website' in q_lower or 'portfolio' in q_lower or ('personal' in q_lower and 'site' in q_lower):
            return "https://github.com/somnathghosh"  # TODO: Get from profile

        # Location (preferred work location, not relocation)
        if 'location' in q_lower and not 'relocate' in q_lower:
            # Could be asking for city, address, or preferred location
            if 'city' in q_lower or 'current' in q_lower or 'based' in q_lower:
                return "Bangalore, India"
            elif 'prefer' in q_lower:
                return "Bangalore or Remote"
            else:
                return "Bangalore, India"

        return None

    def _call_openclaw(self, prompt: str) -> str:
        """
        Call Claude API using pi-ai library (fast method).

        Uses the same pi-ai library that OpenClaw uses internally, but
        calls it directly instead of via openclaw subprocess.

        Speed: ~1-3s vs 10-30s for full openclaw agent command.
        """
        try:
            # Try fast method first (pi-ai library directly)
            try:
                from detached_flows.ai_decision.claude_fast import call_claude_fast
                return call_claude_fast(prompt, timeout=15)
            except ImportError:
                logger.warning("claude_fast module not found, falling back to openclaw subprocess")

            # Fallback to slow openclaw subprocess if fast method fails
            cmd = [
                'openclaw', 'agent',
                '--local',
                '--json',
                '--agent', 'main',
                '--message', prompt
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                raise RuntimeError(f"OpenClaw failed: {result.stderr}")

            # Parse JSON response
            data = json.loads(result.stdout)
            if isinstance(data, dict) and 'payloads' in data:
                payloads = data['payloads']
                if payloads and len(payloads) > 0:
                    return payloads[0].get('text', '').strip()

            return result.stdout.strip()

        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            raise

    def answer_question(
        self,
        question: str,
        context: Optional[dict] = None,
        job_id: Optional[str] = None,
        force_ai: bool = False,
        field_type: Optional[str] = None
    ) -> str:
        """
        Generate an answer for a form question with type-aware caching.

        Args:
            question: The question text
            context: Optional context dict with job_title, company, etc.
            job_id: Optional job ID for tracking
            force_ai: Force AI generation even if cached response exists
            field_type: HTML input type (text, number, email, etc.) for type-aware caching

        Returns:
            The generated answer

        Type-aware caching ensures the same question returns different answers based on field type:
        - "Expected salary?" + number → "90"
        - "Expected salary?" + text → "90 LPA"
        """
        context = context or {}

        # CACHING DISABLED - Always use AI for accurate, context-specific answers
        # Fast Claude integration (1-3s) makes caching unnecessary
        # Each job application question should be answered thoughtfully, not reused

        # Categorize question
        question_type = self._categorize_question(question)
        logger.info(f"Question type: {question_type}, Field type: {field_type}")

        # Try rule-based first (faster, no API cost)
        answer = self._generate_rule_based_answer(question, question_type, context)

        # Use AI if no rule-based answer or if requested
        if (answer is None or force_ai) and self.use_ai:
            logger.info("Generating AI answer with semantic context...")
            # Get similar Q&A from database to help AI make better decisions
            similar_qa = self._get_similar_qa(question, question_type, limit=5)
            answer = self._generate_ai_answer(question, question_type, context, similar_qa, field_type)

        # Fallback to pattern-based answers
        if not answer:
            answer = self._get_fallback_answer(question, question_type)

        # Final fallback
        if not answer:
            answer = "N/A"

        # Store for future reuse (but don't cache failures) with field_type
        if answer != "N/A":
            self._store_response(question, answer, question_type, job_id, field_type)
        else:
            logger.warning(f"Not caching N/A response for: {question[:50]}...")

        return answer

    def answer_yes_no(self, question: str, context: Optional[dict] = None) -> bool:
        """
        Answer a yes/no question.

        Returns True for "yes", False for "no".
        """
        answer = self.answer_question(question, context).lower()
        return answer.startswith('yes') or answer == 'true'

    def get_stored_responses(self, limit: int = 100) -> list[dict]:
        """Get previously stored responses."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT question_text, question_type, response, reuse_count, created_at
            FROM question_responses
            ORDER BY reuse_count DESC, created_at DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def clear_cache(self):
        """Clear the in-memory cache."""
        self._cache.clear()


# Singleton instance for easy import
_handler_instance = None

def get_handler() -> QuestionHandler:
    """Get or create the singleton QuestionHandler instance."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = QuestionHandler()
    return _handler_instance
