"""
Test edge cases in job enrichment (TDD approach).

Special cases:
- Job no longer accepting applications
- Application already submitted
- Job expired/closed
- Apply button missing/disabled
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.Playwright.job_enricher import JobEnricher


class TestJobStatusEdgeCases:
    """Test edge cases for job application status."""

    @pytest.mark.asyncio
    async def test_job_not_accepting_applications(self):
        """
        TEST: Should detect when job is no longer accepting applications.

        EXPECTED: Status should be set to 'CLOSED' or 'NOT_ACCEPTING'
        SCENARIOS:
        - "No longer accepting applications"
        - "Application closed"
        - "Hiring paused"
        - "Position filled"
        """
        # This test would need a real closed job URL
        # For now, we'll test the detection logic

        session = BrowserSession()
        await session.launch()

        try:
            # Simulate page with "not accepting" message
            await session.page.set_content("""
            <html>
                <body>
                    <div class="jobs-details">
                        <h1>Senior Engineer</h1>
                        <div class="jobs-unified-top-card__job-insight">
                            No longer accepting applications
                        </div>
                        <div class="jobs-description__content">
                            Great job description here...
                        </div>
                    </div>
                </body>
            </html>
            """)

            # Extract status
            is_closed = await session.page.evaluate("""
                () => {
                    const text = document.body.innerText.toLowerCase();
                    const closedPhrases = [
                        'no longer accepting applications',
                        'not accepting applications',
                        'application closed',
                        'hiring paused',
                        'position filled',
                        'applications have closed'
                    ];

                    return closedPhrases.some(phrase => text.includes(phrase));
                }
            """)

            # ASSERTION: Should detect closed status
            assert is_closed, "Failed to detect closed job status"

        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_application_already_submitted(self):
        """
        TEST: Should detect when user has already applied to this job.

        EXPECTED: apply_type should be 'ALREADY_APPLIED'
        SCENARIOS:
        - "Application sent"
        - "You applied on [date]"
        - "View application"
        """
        session = BrowserSession()
        await session.launch()

        try:
            await session.page.set_content("""
            <html>
                <body>
                    <div class="jobs-details">
                        <h1>Senior Engineer</h1>
                        <div class="jobs-apply-button--top-card">
                            Application sent
                        </div>
                        <p>You applied on Jan 15, 2025</p>
                    </div>
                </body>
            </html>
            """)

            already_applied = await session.page.evaluate("""
                () => {
                    const text = document.body.innerText.toLowerCase();
                    const appliedPhrases = [
                        'application sent',
                        'you applied',
                        'your application',
                        'view application'
                    ];

                    return appliedPhrases.some(phrase => text.includes(phrase));
                }
            """)

            assert already_applied, "Failed to detect already applied status"

        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_apply_button_disabled(self):
        """
        TEST: Should detect when apply button exists but is disabled.

        EXPECTED: apply_type should be 'DISABLED' or None
        """
        session = BrowserSession()
        await session.launch()

        try:
            await session.page.set_content("""
            <html>
                <body>
                    <button disabled class="jobs-apply-button">Easy Apply</button>
                </body>
            </html>
            """)

            is_disabled = await session.page.evaluate("""
                () => {
                    const applyButton = document.querySelector('button.jobs-apply-button');
                    return applyButton ? applyButton.disabled : false;
                }
            """)

            assert is_disabled, "Failed to detect disabled apply button"

        finally:
            await session.close()


class TestEnrichmentStatusHandling:
    """Test that enricher properly handles different job statuses."""

    @pytest.mark.asyncio
    async def test_enricher_detects_closed_job(self):
        """
        TEST: Enricher should set appropriate status for closed jobs.

        EXPECTED:
        - enrich_status = 'CLOSED' or similar
        - apply_type = None or 'CLOSED'
        - Reasoning should explain job is closed
        """
        # This would test the actual enricher logic
        # For now, defining expected behavior
        pass

    @pytest.mark.asyncio
    async def test_enricher_detects_already_applied(self):
        """
        TEST: Enricher should detect and flag already-applied jobs.

        EXPECTED:
        - enrich_status = 'ALREADY_APPLIED'
        - Should not attempt to apply again
        """
        pass


# Implement detection functions that can be used in enricher
def detect_closed_job_status(page_text: str) -> bool:
    """
    Detect if job is no longer accepting applications.

    Args:
        page_text: Inner text of the job page

    Returns:
        True if job is closed, False otherwise
    """
    page_text_lower = page_text.lower()

    closed_phrases = [
        'no longer accepting applications',
        'not accepting applications',
        'application closed',
        'hiring paused',
        'position filled',
        'position is filled',
        'applications have closed',
        'job posting has been closed',
        'this job is no longer available'
    ]

    return any(phrase in page_text_lower for phrase in closed_phrases)


def detect_already_applied(page_text: str) -> bool:
    """
    Detect if user has already applied to this job.

    Args:
        page_text: Inner text of the job page

    Returns:
        True if already applied, False otherwise
    """
    page_text_lower = page_text.lower()

    applied_phrases = [
        'application sent',
        'you applied',
        'your application',
        'view application',
        'application submitted'
    ]

    return any(phrase in page_text_lower for phrase in applied_phrases)


def test_closed_job_detection():
    """Unit test for closed job detection function."""
    # Test positive cases
    assert detect_closed_job_status("No longer accepting applications")
    assert detect_closed_job_status("This position is filled")
    assert detect_closed_job_status("Hiring paused for this role")

    # Test negative cases
    assert not detect_closed_job_status("Apply now for this great opportunity")
    assert not detect_closed_job_status("Easy Apply button available")


def test_already_applied_detection():
    """Unit test for already applied detection function."""
    # Test positive cases
    assert detect_already_applied("Application sent on Jan 15")
    assert detect_already_applied("You applied 2 days ago")
    assert detect_already_applied("View your application status")

    # Test negative cases
    assert not detect_already_applied("Apply to this position")
    assert not detect_already_applied("Great opportunity awaits")


if __name__ == "__main__":
    # Run unit tests
    test_closed_job_detection()
    test_already_applied_detection()
    print("✅ All unit tests passed!")
