"""
AI Decision Layer for Auto Job Application.

This module provides AI-powered decision making for:
- Job screening and fit score calculation
- Application form handling (QuestionHandler)
- Multi-step navigation decisions
"""

from .job_screener import JobScreener
from .question_handler import QuestionHandler, get_handler

__all__ = ["JobScreener", "QuestionHandler", "get_handler"]
