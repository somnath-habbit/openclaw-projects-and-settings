"""
Test AI job screening system (TDD approach).

Tests ensure:
- Profile loading from JSON
- Job data retrieval from database
- AI provider integration
- Fit score calculation (0.0-1.0)
- Reasoning extraction
- Database updates

Run with: pytest tests/test_ai_screening.py -v
"""
import pytest
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from detached_flows.ai_decision.job_screener import JobScreener


class TestJobScreenerInitialization:
    """Test job screener initialization and configuration."""

    def test_screener_initialization(self):
        """
        TEST: JobScreener should initialize with default configuration.
        
        EXPECTED:
        - Loads AI provider from env (openclaw/anthropic)
        - Loads user profile from data/user_profile.json
        - Has score method available
        """
        screener = JobScreener()
        
        assert screener is not None
        assert hasattr(screener, 'score_job')
        assert screener.user_profile is not None
        assert 'profile' in screener.user_profile

    def test_user_profile_loading(self):
        """
        TEST: User profile should load correctly from JSON.
        
        EXPECTED:
        - Profile contains name, title, bio
        - Skills and experiences loaded
        """
        screener = JobScreener()
        profile = screener.user_profile
        
        assert 'profile' in profile
        assert 'name' in profile['profile']
        assert 'title' in profile['profile']
        assert 'bio' in profile['profile']
        assert 'skills' in profile
        assert 'experiences' in profile
        assert len(profile['experiences']) > 0


class TestJobScoring:
    """Test job fit score calculation."""

    @pytest.fixture
    def sample_job(self):
        """Sample enriched job data."""
        return {
            "external_id": "test_123",
            "job_title": "Engineering Manager",
            "company": "Tech Corp",
            "about_job": """
            We are seeking an experienced Engineering Manager to lead our backend team.
            
            Responsibilities:
            - Lead team of 10+ engineers
            - Drive technical architecture decisions
            - Collaborate with product and design
            - Manage sprint planning and delivery
            
            Requirements:
            - 8+ years software engineering experience
            - 3+ years engineering management
            - Strong AWS/cloud experience
            - Python, Node.js expertise
            - Proven track record building high-performing teams
            
            Nice to have:
            - Experience with microservices
            - SAFe/Agile certification
            """,
            "location": "Bangalore, India",
            "work_mode": "Hybrid",
            "compensation": "₹40-50 LPA"
        }

    @pytest.fixture
    def poor_fit_job(self):
        """Sample job that's a poor fit."""
        return {
            "external_id": "test_456",
            "job_title": "Junior Frontend Developer",
            "company": "Startup XYZ",
            "about_job": """
            Looking for a junior frontend developer to build UI components.
            
            Requirements:
            - 0-2 years experience
            - HTML/CSS/JavaScript
            - React basics
            
            We are a small startup looking for someone to learn and grow.
            """,
            "location": "Remote",
            "work_mode": "Remote"
        }

    def test_score_job_returns_valid_score(self, sample_job):
        """
        TEST: score_job() should return fit_score between 0.0-1.0.
        
        EXPECTED:
        - fit_score is float
        - 0.0 <= fit_score <= 1.0
        - reasoning is non-empty string
        """
        screener = JobScreener()
        result = screener.score_job(sample_job)
        
        assert 'fit_score' in result
        assert 'reasoning' in result
        
        fit_score = result['fit_score']
        reasoning = result['reasoning']
        
        assert isinstance(fit_score, (float, int))
        assert 0.0 <= fit_score <= 1.0
        assert isinstance(reasoning, str)
        assert len(reasoning) > 50, "Reasoning should be detailed"

    def test_good_fit_job_scores_high(self, sample_job):
        """
        TEST: Well-matched job should score >= 0.7.
        
        The sample job matches user's profile:
        - Engineering Manager role (matches title)
        - 8+ years required (user has 12+)
        - AWS/Python/Node.js (matches skills)
        - Team leadership (matches experience)
        """
        screener = JobScreener()
        result = screener.score_job(sample_job)
        
        fit_score = result['fit_score']
        reasoning = result['reasoning']
        
        assert fit_score >= 0.7, (
            f"Good fit job should score >= 0.7\n"
            f"Got: {fit_score}\n"
            f"Reasoning: {reasoning}"
        )

    def test_poor_fit_job_scores_low(self, poor_fit_job):
        """
        TEST: Poorly matched job should score <= 0.4.
        
        The poor fit job doesn't match:
        - Junior role (user is senior/manager)
        - 0-2 years (user has 12+)
        - Only frontend/basic skills
        """
        screener = JobScreener()
        result = screener.score_job(poor_fit_job)
        
        fit_score = result['fit_score']
        reasoning = result['reasoning']
        
        assert fit_score <= 0.4, (
            f"Poor fit job should score <= 0.4\n"
            f"Got: {fit_score}\n"
            f"Reasoning: {reasoning}"
        )

    def test_reasoning_explains_score(self, sample_job):
        """
        TEST: Reasoning should explain why the score was given.
        
        EXPECTED:
        - Mentions skills match/mismatch
        - Mentions experience level
        - Mentions role fit
        """
        screener = JobScreener()
        result = screener.score_job(sample_job)
        
        reasoning = result['reasoning'].lower()
        
        # Should mention relevant factors
        relevant_terms = ['experience', 'skill', 'manager', 'lead', 'team']
        found_terms = [term for term in relevant_terms if term in reasoning]
        
        assert len(found_terms) >= 2, (
            f"Reasoning should mention relevant factors\n"
            f"Expected at least 2 of: {relevant_terms}\n"
            f"Found: {found_terms}\n"
            f"Reasoning: {reasoning}"
        )


class TestJobScreenerWithDatabase:
    """Test screening integrated with database."""

    @pytest.mark.integration
    def test_score_job_from_database(self):
        """
        TEST: score_job_from_db() should load job from database and score it.
        
        EXPECTED:
        - Fetches job by external_id
        - Returns fit_score and reasoning
        - Updates job record with fit_score
        
        NOTE: This is an integration test requiring database
        """
        # This will be implemented after basic scoring works
        pass

    @pytest.mark.integration  
    def test_batch_screening(self):
        """
        TEST: screen_jobs_batch() should score multiple jobs efficiently.
        
        EXPECTED:
        - Processes multiple jobs in batch
        - Updates database with scores
        - Returns summary statistics
        """
        # This will be implemented after basic scoring works
        pass


class TestAIProviderIntegration:
    """Test AI provider integration (OpenClaw/Anthropic)."""

    def test_ai_provider_selection(self):
        """
        TEST: Should use correct AI provider based on env.
        
        EXPECTED:
        - Reads AI_PROVIDER from env
        - Initializes correct provider (openclaw/anthropic)
        """
        screener = JobScreener()
        
        assert hasattr(screener, 'ai_provider')
        assert screener.ai_provider in ['openclaw', 'anthropic']

    def test_prompt_construction(self, sample_job):
        """
        TEST: Should construct proper screening prompt.
        
        EXPECTED:
        - Includes user profile summary
        - Includes job description
        - Asks for 0.0-1.0 score
        - Asks for reasoning
        """
        screener = JobScreener()
        prompt = screener._build_screening_prompt(sample_job)
        
        assert isinstance(prompt, str)
        assert len(prompt) > 200
        assert '0.0' in prompt or '0-1' in prompt
        assert 'reasoning' in prompt.lower() or 'explain' in prompt.lower()


# Unit tests for helper functions
def test_extract_score_from_response():
    """Test score extraction from AI response."""
    from detached_flows.ai_decision.job_screener import extract_score_from_response
    
    # Test various response formats
    responses = [
        "Fit Score: 0.85\nReasoning: Great match",
        "Score: 0.7, Reasoning: Good fit",
        "0.9 - Excellent match",
        '{"fit_score": 0.75, "reasoning": "Good"}',
    ]
    
    for response in responses:
        score, reasoning = extract_score_from_response(response)
        assert 0.0 <= score <= 1.0
        assert reasoning is not None


def test_summarize_profile():
    """Test user profile summarization."""
    from detached_flows.ai_decision.job_screener import summarize_profile
    
    profile = {
        "profile": {
            "name": "John Doe",
            "title": "Senior Engineer",
            "bio": "10 years of experience"
        },
        "skills": [
            {"name": "Python", "rating": 5},
            {"name": "AWS", "rating": 4}
        ],
        "experiences": [
            {
                "position": "Senior Engineer",
                "company": "Tech Corp",
                "skills": ["Python", "AWS"]
            }
        ]
    }
    
    summary = summarize_profile(profile)
    
    assert isinstance(summary, str)
    assert len(summary) > 100
    assert 'John Doe' in summary or 'Senior Engineer' in summary
    assert 'Python' in summary


if __name__ == "__main__":
    """Run tests manually for debugging."""
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
