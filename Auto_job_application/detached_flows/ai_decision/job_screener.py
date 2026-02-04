"""
AI-powered job screening system.

Calculates fit_score (0.0-1.0) for jobs based on user profile match.
Supports multiple AI providers: OpenClaw, Anthropic.
"""
import os
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, Tuple, Optional


def summarize_profile(profile: dict) -> str:
    """
    Summarize user profile for AI screening prompt.
    
    Args:
        profile: User profile dict from user_profile.json
    
    Returns:
        Concise profile summary (500-1000 chars)
    """
    p = profile.get('profile', {})
    name = p.get('name', 'Candidate')
    title = p.get('title', '')
    bio = p.get('bio', '')
    
    # Extract key skills
    skills = profile.get('skills', [])
    top_skills = [s['name'] for s in skills if s.get('rating', 0) >= 4][:10]
    
    # Extract recent experience
    experiences = profile.get('experiences', [])
    recent_exp = experiences[0] if experiences else {}
    current_role = recent_exp.get('position', '')
    current_company = recent_exp.get('company', '')
    
    # Extract years of experience
    metrics = profile.get('keyMetrics', {})
    years_exp = metrics.get('yearsExperience', 'N/A')
    
    summary = f"""
**Candidate Profile:**
- Name: {name}
- Title: {title}
- Years of Experience: {years_exp}
- Current Role: {current_role} at {current_company}

**Bio:** {bio[:300]}...

**Top Skills:** {', '.join(top_skills)}

**Recent Experience:**
{recent_exp.get('description', [''])[0] if recent_exp.get('description') else 'N/A'}
""".strip()
    
    return summary


def extract_score_from_response(response: str) -> Tuple[float, str]:
    """
    Extract fit_score and reasoning from AI response.
    
    Handles various response formats:
    - "Fit Score: 0.85\nReasoning: ..."
    - "Score: 0.7, Reasoning: ..."
    - "0.9 - Excellent match"
    - JSON: {"fit_score": 0.75, "reasoning": "..."}
    
    Args:
        response: AI provider response text
    
    Returns:
        (fit_score, reasoning) tuple
    """
    # Try JSON format first
    try:
        data = json.loads(response)
        if 'fit_score' in data:
            return float(data['fit_score']), data.get('reasoning', response)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Try regex patterns
    score_patterns = [
        r'(?:match[\s_]?score|fit[\s_]?score|score)[:\s]+([0-9]*\.?[0-9]+)',  # "Match Score: 0.92" or "Fit Score: 0.85"
        r'\*\*([0-9]*\.?[0-9]+)\*\*',  # "**0.92**" (markdown bold)
        r'^([0-9]*\.?[0-9]+)\s*[-–—]',  # "0.85 - reasoning"
        r'([0-9]*\.?[0-9]+)/1\.0',  # "0.85/1.0"
    ]
    
    score = None
    for pattern in score_patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            try:
                score = float(match.group(1))
                if 0.0 <= score <= 1.0:
                    break
            except ValueError:
                continue
    
    # Extract reasoning (everything after score, or full response)
    reasoning_patterns = [
        r'reasoning[:\s]+(.+)',
        r'(?:fit[\s_]?score|score)[:\s]+[0-9.]+[,\s]+(.+)',
        r'^[0-9.]+\s*[-–—]\s*(.+)',
    ]
    
    reasoning = response
    for pattern in reasoning_patterns:
        match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
        if match:
            reasoning = match.group(1).strip()
            break
    
    # Default score if not found
    if score is None:
        score = 0.5  # neutral score
        reasoning = f"Could not parse score from response. Response: {response[:200]}"
    
    return score, reasoning


class JobScreener:
    """
    AI-powered job screening system.
    
    Calculates fit_score (0.0-1.0) based on user profile match.
    """
    
    def __init__(self, profile_path: Optional[str] = None):
        """
        Initialize job screener.
        
        Args:
            profile_path: Path to user_profile.json (default: data/user_profile.json)
        """
        # Load AI provider config from env
        self.ai_provider = os.getenv('AI_PROVIDER', 'openclaw').lower()
        self.ai_model = os.getenv('AI_MODEL', 'sonnet').lower()
        
        # Load user profile
        if profile_path is None:
            root_dir = Path(__file__).parent.parent.parent
            profile_path = root_dir / 'data' / 'user_profile.json'
        
        with open(profile_path, 'r') as f:
            self.user_profile = json.load(f)
        
        self.profile_summary = summarize_profile(self.user_profile)
    
    def _build_screening_prompt(self, job: dict) -> str:
        """
        Build AI screening prompt.
        
        Args:
            job: Job data dict with about_job, job_title, company, etc.
        
        Returns:
            Screening prompt string
        """
        job_title = job.get('job_title', 'Unknown')
        company = job.get('company', 'Unknown')
        about_job = job.get('about_job', '')
        location = job.get('location', 'Unknown')
        work_mode = job.get('work_mode', 'Unknown')
        compensation = job.get('compensation', 'Not specified')
        
        prompt = f"""
You are an expert career advisor. Evaluate how well this job matches the candidate's profile.

{self.profile_summary}

**Job Details:**
- Title: {job_title}
- Company: {company}
- Location: {location}
- Work Mode: {work_mode}
- Compensation: {compensation}

**Job Description:**
{about_job}

---

**Task:** Rate this job match on a scale of 0.0 to 1.0:
- 0.0-0.3: Poor fit (major mismatch in role, skills, or experience level)
- 0.4-0.6: Moderate fit (some match but significant gaps)
- 0.7-0.8: Good fit (strong match with minor concerns)
- 0.9-1.0: Excellent fit (near-perfect match)

**Response Format:**
Fit Score: [0.0-1.0]
Reasoning: [2-3 sentences explaining the score, mentioning key matches or mismatches]

Consider:
1. Role level match (e.g., junior vs senior vs manager)
2. Skills alignment (required vs candidate's skills)
3. Experience years match
4. Industry/domain relevance
5. Location/work mode preferences
""".strip()
        
        return prompt
    
    def _call_ai_provider(self, prompt: str) -> str:
        """
        Call AI provider (OpenClaw or Anthropic).
        
        Args:
            prompt: Screening prompt
        
        Returns:
            AI response text
        """
        if self.ai_provider == 'openclaw':
            return self._call_openclaw(prompt)
        elif self.ai_provider == 'anthropic':
            return self._call_anthropic(prompt)
        else:
            raise ValueError(f"Unsupported AI provider: {self.ai_provider}")
    
    def _call_openclaw(self, prompt: str) -> str:
        """Call OpenClaw CLI for AI response."""
        try:
            # Use 'openclaw agent --local' for local AI execution
            # Use --agent main (default agent) or --session-id for stateless calls
            cmd = [
                'openclaw', 'agent',
                '--local',
                '--json',
                '--agent', 'main',  # Use default 'main' agent
                '--message', prompt
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                raise RuntimeError(f"OpenClaw failed: {result.stderr}")

            # Parse JSON response
            try:
                data = json.loads(result.stdout)
                # Extract message content from payloads[0].text
                if isinstance(data, dict) and 'payloads' in data:
                    payloads = data['payloads']
                    if payloads and len(payloads) > 0:
                        return payloads[0].get('text', result.stdout)
                # Fallback to other fields
                if isinstance(data, dict):
                    return data.get('reply', data.get('message', result.stdout))
                return result.stdout
            except json.JSONDecodeError:
                return result.stdout.strip()

        except FileNotFoundError:
            raise RuntimeError("OpenClaw CLI not found. Install from: https://docs.openclaw.ai")
        except subprocess.TimeoutExpired:
            raise RuntimeError("OpenClaw request timed out after 60s")
    
    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic API directly."""
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed. Install with: pip install anthropic")
        
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")
        
        client = anthropic.Anthropic(api_key=api_key)
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        return message.content[0].text
    
    def score_job(self, job: dict) -> dict:
        """
        Score a job based on profile fit.
        
        Args:
            job: Job data dict with about_job, job_title, company, etc.
        
        Returns:
            {
                "fit_score": float (0.0-1.0),
                "reasoning": str
            }
        """
        # Build prompt
        prompt = self._build_screening_prompt(job)
        
        # Call AI provider
        try:
            response = self._call_ai_provider(prompt)
        except Exception as e:
            return {
                "fit_score": 0.5,
                "reasoning": f"AI provider error: {str(e)}"
            }
        
        # Extract score and reasoning
        fit_score, reasoning = extract_score_from_response(response)
        
        return {
            "fit_score": fit_score,
            "reasoning": reasoning
        }
