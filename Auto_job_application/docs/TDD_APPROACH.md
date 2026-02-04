# Test-Driven Development (TDD) Approach

> **Philosophy:** Write tests first, then make them pass
> **Benefits:** Better code design, fewer bugs, living documentation

---

## 🎯 Priority 1: Fix Job Enrichment Extraction

**Current Issue:** Job descriptions only extracting 100-200 chars instead of full text

### Step 1: Write Tests First ❌ (Should Fail)

**File:** `tests/test_enrichment_extraction.py`

```python
"""Test job enrichment extraction quality."""
import pytest
from playwright.sync_api import sync_playwright

class TestEnrichmentExtraction:
    """Test suite for job detail extraction."""

    @pytest.fixture
    def sample_job_url(self):
        """A known LinkedIn job URL for testing."""
        return "https://www.linkedin.com/jobs/view/4367707125/"

    def test_job_description_length(self, sample_job_url):
        """Job description should be at least 500 characters."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(sample_job_url)

            # Extract description (using current logic)
            description = page.evaluate("""
                () => {
                    const container = document.querySelector('.jobs-description__content');
                    return container ? container.innerText : '';
                }
            """)

            browser.close()

            # ASSERTION: Should have substantial content
            assert len(description) >= 500, f"Description too short: {len(description)} chars"
            assert "responsibilities" in description.lower() or "qualifications" in description.lower()

    def test_job_description_completeness(self, sample_job_url):
        """Description should contain key sections."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(sample_job_url)

            description = page.evaluate("""
                () => {
                    const container = document.querySelector('.jobs-description__content');
                    return container ? container.innerText : '';
                }
            """)

            browser.close()

            # Check for common job description sections
            description_lower = description.lower()
            has_requirements = any(word in description_lower for word in ['requirements', 'qualifications', 'skills'])
            has_responsibilities = any(word in description_lower for word in ['responsibilities', 'duties', 'role'])

            assert has_requirements or has_responsibilities, "Missing key job description sections"

    def test_apply_button_detection(self, sample_job_url):
        """Should correctly identify apply button type."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(sample_job_url)

            apply_type = page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button, a'));
                    const easyApply = buttons.find(el => el.textContent.includes('Easy Apply'));
                    if (easyApply) return 'Easy Apply';

                    const companySite = buttons.find(el => /Apply on company/i.test(el.textContent));
                    if (companySite) return 'Company Site';

                    return null;
                }
            """)

            browser.close()

            # ASSERTION: Must detect apply type
            assert apply_type is not None, "Failed to detect apply button type"
            assert apply_type in ['Easy Apply', 'Company Site', 'Apply']

    def test_company_info_extraction(self, sample_job_url):
        """Should extract company information."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(sample_job_url)

            company_info = page.evaluate("""
                () => {
                    // Try multiple selectors
                    const selectors = [
                        '.company-name',
                        '.jobs-unified-top-card__company-name',
                        '.job-details-jobs-unified-top-card__company-name'
                    ];

                    for (const selector of selectors) {
                        const element = document.querySelector(selector);
                        if (element) return element.innerText.trim();
                    }
                    return null;
                }
            """)

            browser.close()

            # ASSERTION: Should extract company name
            assert company_info is not None, "Failed to extract company name"
            assert len(company_info) > 0

    def test_work_mode_detection(self, sample_job_url):
        """Should detect work mode (Remote/Hybrid/On-site)."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(sample_job_url)

            work_mode = page.evaluate("""
                () => {
                    const text = document.body.innerText.toLowerCase();
                    if (text.includes('remote') || text.includes('work from home')) return 'Remote';
                    if (text.includes('hybrid')) return 'Hybrid';
                    if (text.includes('on-site') || text.includes('onsite')) return 'On-site';
                    return null;
                }
            """)

            browser.close()

            # ASSERTION: Should detect work mode (may be null for some jobs)
            if work_mode:
                assert work_mode in ['Remote', 'Hybrid', 'On-site']
```

### Step 2: Run Tests (Should Fail) 🔴

```bash
# Install pytest if needed
pip install pytest pytest-playwright

# Run tests - EXPECT FAILURES
pytest tests/test_enrichment_extraction.py -v

# Expected output:
# FAILED test_job_description_length - AssertionError: Description too short: 187 chars
# FAILED test_job_description_completeness - AssertionError: Missing key job description sections
```

### Step 3: Fix Code to Make Tests Pass ✅

**Update:** `detached_flows/Playwright/job_enricher.py`

```python
async def _extract_job_details(self) -> dict:
    """Extract all job details with improved selectors."""

    details = await self.session.page.evaluate("""
        () => {
            // IMPROVED: More robust section extraction
            function extractSection(headings) {
                for (const heading of headings) {
                    // Strategy 1: Direct container selector
                    const container = document.querySelector('.jobs-description__content');
                    if (container) {
                        // Get ALL text from container, not just siblings
                        return container.innerText.trim();
                    }

                    // Strategy 2: Find by heading and get parent
                    const allHeadings = document.querySelectorAll('h2, h3, .section-title');
                    for (const h of allHeadings) {
                        if (h.textContent.toLowerCase().includes(heading.toLowerCase())) {
                            const parent = h.closest('section, article, div[class*="description"]');
                            if (parent) return parent.innerText.trim();
                        }
                    }
                }
                return null;
            }

            // IMPROVED: More robust apply button detection
            function extractApplyType() {
                const buttons = Array.from(document.querySelectorAll('button, a, span'));

                // Check for Easy Apply
                const easyApply = buttons.find(el =>
                    el.textContent.trim() === 'Easy Apply' ||
                    el.className.includes('easy-apply') ||
                    el.getAttribute('aria-label')?.includes('Easy Apply')
                );
                if (easyApply) return 'Easy Apply';

                // Check for Company Site
                const companySite = buttons.find(el =>
                    /Apply on company/i.test(el.textContent) ||
                    /Apply on .* site/i.test(el.textContent)
                );
                if (companySite) return 'Company Site';

                // Generic Apply
                const apply = buttons.find(el => el.textContent.trim() === 'Apply');
                if (apply) return 'Apply';

                return null;
            }

            // Extract all fields
            return {
                about_job: extractSection(['About the job', 'Job description']),
                about_company: extractSection(['About the company', 'About us']),
                compensation: extractCompensation(),
                work_mode: extractWorkMode(),
                apply_type: extractApplyType()
            };
        }
    """)

    return details
```

### Step 4: Run Tests Again (Should Pass) ✅

```bash
pytest tests/test_enrichment_extraction.py -v

# Expected output:
# PASSED test_job_description_length
# PASSED test_job_description_completeness
# PASSED test_apply_button_detection
# PASSED test_company_info_extraction
# PASSED test_work_mode_detection
```

### Step 5: Refactor & Optimize 🔧

Once tests pass, refactor for:
- Code clarity
- Performance
- Maintainability

---

## 🎯 Priority 2: AI Job Screening (TDD)

**Goal:** Filter jobs based on profile match

### Step 1: Write Tests First ❌

**File:** `tests/test_ai_screening.py`

```python
"""Test AI job screening functionality."""
import pytest
from detached_flows.ai_decision.job_screener import JobScreener

class TestJobScreening:
    """Test suite for AI-based job screening."""

    @pytest.fixture
    def sample_profile(self):
        """Sample user profile."""
        return {
            "name": "Somnath Ghosh",
            "title": "Engineering Manager",
            "skills": ["Python", "Team Leadership", "System Architecture"],
            "experience_years": 10,
            "preferences": {
                "work_mode": "Remote",
                "min_salary": 5000000,  # 50 LPA
                "locations": ["Bengaluru", "Remote"]
            }
        }

    @pytest.fixture
    def matching_job(self):
        """A job that should match the profile."""
        return {
            "external_id": "123456",
            "title": "Engineering Manager",
            "about_job": """
                We are seeking an experienced Engineering Manager to lead our Python team.
                Requirements:
                - 8+ years of software engineering experience
                - 3+ years in leadership roles
                - Strong Python and system architecture skills
                - Experience with distributed systems
                Remote work available.
            """,
            "work_mode": "Remote",
            "compensation": "50-70 LPA"
        }

    @pytest.fixture
    def non_matching_job(self):
        """A job that should NOT match the profile."""
        return {
            "external_id": "789012",
            "title": "Junior Frontend Developer",
            "about_job": """
                Looking for a junior React developer.
                Requirements:
                - 0-2 years experience
                - React, JavaScript, CSS
                - No management experience needed
                On-site in Mumbai office.
            """,
            "work_mode": "On-site",
            "compensation": "8-12 LPA"
        }

    @pytest.mark.asyncio
    async def test_screening_returns_score(self, sample_profile, matching_job):
        """Screening should return fit_score between 0.0 and 1.0."""
        screener = JobScreener(provider="ollama")  # Use local for testing

        result = await screener.screen_job(matching_job, sample_profile)

        assert "fit_score" in result
        assert 0.0 <= result["fit_score"] <= 1.0
        assert "fit_reasoning" in result

    @pytest.mark.asyncio
    async def test_matching_job_high_score(self, sample_profile, matching_job):
        """Matching job should get high fit_score (>0.7)."""
        screener = JobScreener(provider="ollama")

        result = await screener.screen_job(matching_job, sample_profile)

        assert result["fit_score"] >= 0.7, f"Expected high score, got {result['fit_score']}"
        assert "engineering manager" in result["fit_reasoning"].lower()

    @pytest.mark.asyncio
    async def test_non_matching_job_low_score(self, sample_profile, non_matching_job):
        """Non-matching job should get low fit_score (<0.5)."""
        screener = JobScreener(provider="ollama")

        result = await screener.screen_job(non_matching_job, sample_profile)

        assert result["fit_score"] < 0.5, f"Expected low score, got {result['fit_score']}"
        assert "junior" in result["fit_reasoning"].lower() or "not a match" in result["fit_reasoning"].lower()

    @pytest.mark.asyncio
    async def test_screening_respects_work_mode_preference(self, sample_profile, non_matching_job):
        """Should penalize jobs that don't match work mode preference."""
        screener = JobScreener(provider="ollama")

        # Profile wants Remote, job is On-site
        result = await screener.screen_job(non_matching_job, sample_profile)

        assert "on-site" in result["fit_reasoning"].lower() or "location" in result["fit_reasoning"].lower()

    @pytest.mark.asyncio
    async def test_batch_screening(self, sample_profile, matching_job, non_matching_job):
        """Should be able to screen multiple jobs efficiently."""
        screener = JobScreener(provider="ollama")

        jobs = [matching_job, non_matching_job]
        results = await screener.screen_jobs_batch(jobs, sample_profile)

        assert len(results) == 2
        assert results[0]["fit_score"] > results[1]["fit_score"]
```

### Step 2: Create Implementation

**File:** `detached_flows/ai_decision/job_screener.py`

```python
"""AI-based job screening to match jobs with user profile."""
import logging
from typing import Dict, List

logger = logging.getLogger("JobScreener")

SCREENING_PROMPT = """You are a job matching expert. Analyze how well this job matches the candidate's profile.

CANDIDATE PROFILE:
Name: {name}
Current Title: {title}
Skills: {skills}
Experience: {experience_years} years
Preferences:
- Work Mode: {work_mode_pref}
- Min Salary: {min_salary}
- Locations: {locations}

JOB DETAILS:
Title: {job_title}
Work Mode: {job_work_mode}
Compensation: {job_compensation}
Description:
{job_description}

INSTRUCTIONS:
1. Rate the match from 0.0 (terrible fit) to 1.0 (perfect fit)
2. Consider: skills match, experience level, work mode, compensation, location
3. Provide brief reasoning (2-3 sentences)

Return ONLY valid JSON:
{{
    "fit_score": 0.0-1.0,
    "fit_reasoning": "Brief explanation of match quality and key factors"
}}
"""

class JobScreener:
    """Screen jobs using AI to calculate fit scores."""

    def __init__(self, provider: str = "ollama"):
        """Initialize screener with AI provider."""
        from detached_flows.ai_decision.decision_engine import _get_provider
        self.provider = _get_provider()

    async def screen_job(self, job: Dict, profile: Dict) -> Dict:
        """Screen a single job against profile."""
        # TODO: Implement
        pass

    async def screen_jobs_batch(self, jobs: List[Dict], profile: Dict) -> List[Dict]:
        """Screen multiple jobs efficiently."""
        # TODO: Implement
        pass
```

### Step 3: Run Tests (Will Fail) 🔴

```bash
pytest tests/test_ai_screening.py -v

# Expected: All tests FAIL (NotImplementedError)
```

### Step 4: Implement to Make Tests Pass ✅

```python
class JobScreener:
    async def screen_job(self, job: Dict, profile: Dict) -> Dict:
        """Screen a single job against profile."""

        # Format prompt
        prompt = SCREENING_PROMPT.format(
            name=profile["name"],
            title=profile["title"],
            skills=", ".join(profile["skills"]),
            experience_years=profile["experience_years"],
            work_mode_pref=profile["preferences"]["work_mode"],
            min_salary=profile["preferences"]["min_salary"],
            locations=", ".join(profile["preferences"]["locations"]),
            job_title=job["title"],
            job_work_mode=job.get("work_mode", "Not specified"),
            job_compensation=job.get("compensation", "Not specified"),
            job_description=job["about_job"][:1000]  # Limit length
        )

        # Call AI provider
        response = await self.provider.analyze(
            screenshot_b64="",  # Not needed for text analysis
            a11y_snapshot=prompt,
            context=profile,
            goal="Screen job for fit"
        )

        return {
            "external_id": job["external_id"],
            "fit_score": response.get("fit_score", 0.0),
            "fit_reasoning": response.get("fit_reasoning", "")
        }
```

### Step 5: Run Tests Again ✅

```bash
pytest tests/test_ai_screening.py -v

# Expected: All tests PASS
```

---

## 🎯 Priority 3: Application Flow Testing (TDD)

### Test Scenarios

1. **Test Easy Apply Button Detection**
2. **Test Multi-Step Form Navigation**
3. **Test Resume Upload**
4. **Test Form Field Auto-Fill**
5. **Test Error Handling (CAPTCHA, etc.)**

*(Similar TDD structure - write tests first, implement to pass)*

---

## 📋 TDD Workflow Summary

```
┌─────────────────────┐
│ 1. Write Test (RED) │  ❌ Test should fail
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. Run Test         │  🔴 Confirm failure
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 3. Write Code       │  ✅ Make test pass
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 4. Run Test         │  ✅ Verify pass
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 5. Refactor         │  🔧 Improve code
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 6. Repeat           │  ♻️  Next feature
└─────────────────────┘
```

---

## 🛠️ Setup Testing Environment

```bash
# Install test dependencies
pip install pytest pytest-playwright pytest-asyncio

# Create pytest config
cat > pytest.ini << EOF
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
EOF

# Run all tests
pytest

# Run specific test file
pytest tests/test_enrichment_extraction.py -v

# Run tests with coverage
pytest --cov=detached_flows --cov-report=html

# Run only fast tests
pytest -m "not slow"
```

---

## 📊 Benefits of TDD Approach

1. **Better Design** - Forces you to think about API before implementation
2. **Documentation** - Tests serve as executable examples
3. **Confidence** - Refactor without fear of breaking things
4. **Debugging** - Catch bugs early, pinpoint exact failure
5. **Coverage** - Ensures all code paths tested

---

## 🎯 Next Steps

1. **Create test file:** `tests/test_enrichment_extraction.py`
2. **Run tests (expect failures)**
3. **Fix enricher code**
4. **Re-run tests (expect passes)**
5. **Move to next priority (AI screening)**

Ready to start? Let's create the first test file!
