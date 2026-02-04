"""
Test job enrichment extraction quality (TDD).

Tests ensure that job details are extracted completely and accurately.
Run with: pytest tests/test_enrichment_extraction.py -v
"""
import pytest
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from detached_flows.Playwright.browser_session import BrowserSession
from detached_flows.Playwright.job_enricher import JobEnricher


class TestEnrichmentExtraction:
    """Test suite for job detail extraction quality."""

    @pytest.mark.asyncio
    async def test_job_description_minimum_length(self, sample_job_urls):
        """
        TEST: Job description should be at least 500 characters.

        EXPECTED: Full job descriptions are typically 1000-3000 chars
        CURRENT ISSUE: Only getting ~100-200 chars
        """
        session = BrowserSession()
        await session.launch()

        try:
            enricher = JobEnricher(session=session, debug=False)

            for job_url in sample_job_urls[:1]:  # Test first URL
                external_id = job_url.split("/")[-2]
                result = await enricher.enrich_job(external_id, job_url)

                about_job = result.get("about_job", "")

                # ASSERTION: Description should be substantial
                assert len(about_job) >= 500, (
                    f"Job {external_id}: Description too short\n"
                    f"Expected: >= 500 chars\n"
                    f"Got: {len(about_job)} chars\n"
                    f"Preview: {about_job[:200]}..."
                )

        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_job_description_contains_key_sections(self, sample_job_urls):
        """
        TEST: Description should contain key sections (responsibilities, requirements, etc.).

        EXPECTED: Job descriptions include structured content
        CURRENT ISSUE: Extraction may be incomplete
        """
        session = BrowserSession()
        await session.launch()

        try:
            enricher = JobEnricher(session=session, debug=False)

            for job_url in sample_job_urls[:1]:
                external_id = job_url.split("/")[-2]
                result = await enricher.enrich_job(external_id, job_url)

                about_job = result.get("about_job", "").lower()

                # Check for common job description keywords
                key_terms = [
                    'responsibilities', 'requirements', 'qualifications',
                    'skills', 'experience', 'duties', 'role', 'position'
                ]

                found_terms = [term for term in key_terms if term in about_job]

                # ASSERTION: Should contain at least 2 key terms
                assert len(found_terms) >= 2, (
                    f"Job {external_id}: Missing key sections\n"
                    f"Expected: At least 2 of {key_terms}\n"
                    f"Found: {found_terms}\n"
                    f"Content length: {len(about_job)} chars"
                )

        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_apply_button_detection(self, sample_job_urls):
        """
        TEST: Should correctly identify apply button type.

        EXPECTED: 'Easy Apply' | 'Company Site' | 'Apply'
        CURRENT ISSUE: May return None
        """
        session = BrowserSession()
        await session.launch()

        try:
            enricher = JobEnricher(session=session, debug=False)

            for job_url in sample_job_urls[:2]:  # Test first 2 URLs
                external_id = job_url.split("/")[-2]
                result = await enricher.enrich_job(external_id, job_url)

                apply_type = result.get("apply_type")

                # ASSERTION: Must detect apply type
                assert apply_type is not None, (
                    f"Job {external_id}: Failed to detect apply button type\n"
                    f"Expected: 'Easy Apply' | 'Company Site' | 'Apply'\n"
                    f"Got: None"
                )

                assert apply_type in ['Easy Apply', 'Company Site', 'Apply'], (
                    f"Job {external_id}: Invalid apply type\n"
                    f"Expected: 'Easy Apply' | 'Company Site' | 'Apply'\n"
                    f"Got: {apply_type}"
                )

        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_enrichment_quality_validation(self, sample_job_urls):
        """
        TEST: Enricher's own quality check should pass.

        EXPECTED: enrich_status = 'ENRICHED' (not 'NEEDS_ENRICH')
        CURRENT ISSUE: May fail quality check due to short descriptions
        """
        session = BrowserSession()
        await session.launch()

        try:
            enricher = JobEnricher(session=session, debug=False)

            for job_url in sample_job_urls[:1]:
                external_id = job_url.split("/")[-2]
                result = await enricher.enrich_job(external_id, job_url)

                enrich_status = result.get("enrich_status")
                last_error = result.get("last_enrich_error")

                # ASSERTION: Should pass quality validation
                assert enrich_status == "ENRICHED", (
                    f"Job {external_id}: Failed quality validation\n"
                    f"Expected status: 'ENRICHED'\n"
                    f"Got status: {enrich_status}\n"
                    f"Error: {last_error}\n"
                    f"Description length: {len(result.get('about_job', ''))} chars"
                )

        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_multiple_jobs_consistency(self, sample_job_urls):
        """
        TEST: Extraction should work consistently across multiple jobs.

        EXPECTED: All jobs should be enriched successfully
        CURRENT ISSUE: May fail on some jobs
        """
        session = BrowserSession()
        await session.launch()

        try:
            enricher = JobEnricher(session=session, debug=False)

            results = []
            for job_url in sample_job_urls:
                external_id = job_url.split("/")[-2]
                result = await enricher.enrich_job(external_id, job_url)
                results.append({
                    "external_id": external_id,
                    "desc_length": len(result.get("about_job", "")),
                    "apply_type": result.get("apply_type"),
                    "status": result.get("enrich_status")
                })
                await asyncio.sleep(2)  # Be nice to LinkedIn

            # ASSERTION: At least 2 out of 3 should be successfully enriched
            successful = sum(1 for r in results if r["status"] == "ENRICHED")

            assert successful >= 2, (
                f"Consistency check failed\n"
                f"Expected: At least 2/3 jobs enriched successfully\n"
                f"Got: {successful}/3 successful\n"
                f"Results: {results}"
            )

        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_extraction_includes_full_paragraphs(self, sample_job_urls):
        """
        TEST: Description should include full paragraphs, not just headings.

        EXPECTED: Multiple sentences forming complete paragraphs
        CURRENT ISSUE: May only extract first line or heading
        """
        session = BrowserSession()
        await session.launch()

        try:
            enricher = JobEnricher(session=session, debug=False)

            for job_url in sample_job_urls[:1]:
                external_id = job_url.split("/")[-2]
                result = await enricher.enrich_job(external_id, job_url)

                about_job = result.get("about_job", "")

                # Count sentences (rough heuristic)
                sentence_count = about_job.count('.') + about_job.count('!') + about_job.count('?')

                # Count newlines (paragraphs)
                paragraph_count = len([line for line in about_job.split('\n') if line.strip()])

                # ASSERTION: Should have multiple sentences and paragraphs
                assert sentence_count >= 5, (
                    f"Job {external_id}: Too few sentences\n"
                    f"Expected: >= 5 sentences\n"
                    f"Got: {sentence_count} sentences\n"
                    f"Content: {about_job[:300]}..."
                )

                assert paragraph_count >= 3, (
                    f"Job {external_id}: Too few paragraphs\n"
                    f"Expected: >= 3 paragraphs\n"
                    f"Got: {paragraph_count} paragraphs"
                )

        finally:
            await session.close()


class TestExtractionHelpers:
    """Test individual extraction helper functions."""

    @pytest.mark.asyncio
    async def test_show_more_button_expansion(self, sample_job_urls):
        """
        TEST: 'Show more' buttons should be clicked to expand content.

        EXPECTED: Content expands after clicking
        CURRENT ISSUE: May not find or click show more buttons
        """
        session = BrowserSession()
        await session.launch()

        try:
            # Navigate to job page
            await session.page.goto(sample_job_urls[0], wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # Get initial content length
            initial_content = await session.page.evaluate("""
                () => {
                    const container = document.querySelector('.jobs-description__content');
                    return container ? container.innerText.length : 0;
                }
            """)

            # Try to click show more buttons
            show_more_buttons = await session.page.locator(
                'button:has-text("Show more"), button:has-text("See more")'
            ).all()

            for button in show_more_buttons[:3]:
                try:
                    if await button.is_visible():
                        await button.click()
                        await asyncio.sleep(1)
                except Exception:
                    pass

            # Get expanded content length
            expanded_content = await session.page.evaluate("""
                () => {
                    const container = document.querySelector('.jobs-description__content');
                    return container ? container.innerText.length : 0;
                }
            """)

            # ASSERTION: Content should expand (or already be full)
            assert expanded_content >= initial_content, (
                f"Show more expansion failed\n"
                f"Initial: {initial_content} chars\n"
                f"After expansion: {expanded_content} chars"
            )

            # If buttons were found, content should be longer
            if len(show_more_buttons) > 0:
                assert expanded_content > initial_content or expanded_content > 500, (
                    f"Found {len(show_more_buttons)} show more buttons but content didn't expand\n"
                    f"Initial: {initial_content} chars\n"
                    f"After: {expanded_content} chars"
                )

        finally:
            await session.close()


# Utility for manual inspection
if __name__ == "__main__":
    """Run a single enrichment and print results for manual inspection."""
    import asyncio

    async def inspect():
        session = BrowserSession()
        await session.launch()

        try:
            enricher = JobEnricher(session=session, debug=True)

            job_url = "https://www.linkedin.com/jobs/view/4367707125/"
            external_id = "4367707125"

            print(f"\n{'='*60}")
            print(f"Inspecting job: {external_id}")
            print(f"{'='*60}\n")

            result = await enricher.enrich_job(external_id, job_url)

            print(f"About Job Length: {len(result.get('about_job', ''))} chars")
            print(f"Apply Type: {result.get('apply_type')}")
            print(f"Work Mode: {result.get('work_mode')}")
            print(f"Compensation: {result.get('compensation')}")
            print(f"Enrich Status: {result.get('enrich_status')}")
            print(f"Last Error: {result.get('last_enrich_error')}")

            print(f"\nAbout Job Preview (first 500 chars):")
            print(f"{result.get('about_job', '')[:500]}")

            print(f"\nScreenshots saved to: data/screenshots/")

        finally:
            await session.close()

    asyncio.run(inspect())
