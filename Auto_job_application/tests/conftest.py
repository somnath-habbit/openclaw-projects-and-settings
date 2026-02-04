"""
Pytest configuration and shared fixtures.

Configure test job URLs via:
- Environment variable: TEST_JOB_URLS="url1,url2,url3"
- Command line: pytest --job-urls="url1,url2,url3"
"""
import os
import pytest


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--job-urls",
        action="store",
        default=None,
        help="Comma-separated list of LinkedIn job URLs to test"
    )


@pytest.fixture(scope="session")
def sample_job_urls(request):
    """
    Provide sample LinkedIn job URLs for testing.

    Priority:
    1. Command line: pytest --job-urls="url1,url2,url3"
    2. Environment variable: TEST_JOB_URLS="url1,url2,url3"
    3. Default hardcoded URLs (may be outdated)

    Returns:
        list[str]: List of LinkedIn job URLs
    """
    # Check command line option
    cli_urls = request.config.getoption("--job-urls")
    if cli_urls:
        return [url.strip() for url in cli_urls.split(",")]

    # Check environment variable
    env_urls = os.environ.get("TEST_JOB_URLS")
    if env_urls:
        return [url.strip() for url in env_urls.split(",")]

    # Default URLs (may be outdated - override via --job-urls or TEST_JOB_URLS)
    return [
        "https://www.linkedin.com/jobs/view/4367707125/",
        "https://www.linkedin.com/jobs/view/4362158368/",
        "https://www.linkedin.com/jobs/view/4366465744/",
    ]
