"""
Site Registry - Registry of known job sites with their URLs, quirks, and configs.

Provides site-specific information for the registration engine, login engine,
and universal apply bot to use when interacting with different job platforms.

Usage:
    registry = SiteRegistry()
    site = registry.get("naukri")
    print(site.login_url)
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("SiteRegistry")


@dataclass
class SiteConfig:
    """Configuration for a single job site."""
    name: str
    key: str  # Internal identifier (lowercase, no spaces)
    base_url: str
    login_url: str = ""
    registration_url: str = ""
    job_search_url: str = ""
    apply_url_pattern: str = ""  # Pattern to identify apply pages

    # Credential config
    credential_tier: str = "medium"  # OpenClaw security tier
    login_email_field: str = ""  # If known, the email field identifier
    login_password_field: str = ""  # If known, the password field identifier

    # Site behavior
    requires_resume_upload: bool = False
    has_captcha: bool = False
    has_2fa: bool = False
    supports_easy_apply: bool = False  # Site has a quick-apply feature

    # Rate limiting
    max_applications_per_hour: int = 5
    min_delay_between_applies: int = 30  # seconds

    # AI config
    requires_ai_navigation: bool = False  # True if URLs are unknown/dynamic
    known_field_mappings: Dict[str, str] = field(default_factory=dict)

    # Session config
    session_cookie_name: str = ""  # Primary auth cookie name
    session_duration_hours: int = 24

    def __repr__(self):
        return f"SiteConfig({self.key}: {self.name})"


# Pre-configured job sites
SITE_CONFIGS = {
    "linkedin": SiteConfig(
        name="LinkedIn",
        key="linkedin",
        base_url="https://www.linkedin.com",
        login_url="https://www.linkedin.com/login",
        registration_url="https://www.linkedin.com/signup",
        job_search_url="https://www.linkedin.com/jobs/search/",
        credential_tier="high",
        requires_resume_upload=False,
        has_captcha=True,
        has_2fa=True,
        supports_easy_apply=True,
        max_applications_per_hour=10,
        min_delay_between_applies=20,
        session_cookie_name="li_at",
        session_duration_hours=72,
    ),

    "naukri": SiteConfig(
        name="Naukri.com",
        key="naukri",
        base_url="https://www.naukri.com",
        login_url="https://www.naukri.com/nlogin/login",
        registration_url="https://www.naukri.com/registration/createAccount",
        job_search_url="https://www.naukri.com/jobs",
        apply_url_pattern="/apply/",
        credential_tier="medium",
        requires_resume_upload=True,
        has_captcha=False,
        max_applications_per_hour=5,
        min_delay_between_applies=30,
        known_field_mappings={
            "current ctc": "currentCTC",
            "expected ctc": "expectedCTC",
            "notice period": "noticePeriod",
            "total experience": "yearsExperience",
            "key skills": "skills",
            "resume headline": "title",
        },
        session_duration_hours=24,
    ),

    "indeed": SiteConfig(
        name="Indeed",
        key="indeed",
        base_url="https://www.indeed.com",
        login_url="https://secure.indeed.com/auth",
        registration_url="https://secure.indeed.com/auth",
        job_search_url="https://www.indeed.com/jobs",
        credential_tier="medium",
        requires_resume_upload=True,
        has_captcha=True,
        max_applications_per_hour=5,
        min_delay_between_applies=45,
        known_field_mappings={
            "desired salary": "expectedSalary",
            "desired job title": "title",
        },
        session_duration_hours=48,
    ),

    "instahyre": SiteConfig(
        name="Instahyre",
        key="instahyre",
        base_url="https://www.instahyre.com",
        login_url="https://www.instahyre.com/login/",
        registration_url="https://www.instahyre.com/signup/",
        credential_tier="medium",
        requires_resume_upload=True,
        max_applications_per_hour=8,
        min_delay_between_applies=20,
        known_field_mappings={
            "current ctc": "currentCTC",
            "expected ctc": "expectedCTC",
            "notice period": "noticePeriod",
        },
    ),

    "foundit": SiteConfig(
        name="Foundit (Monster India)",
        key="foundit",
        base_url="https://www.foundit.in",
        login_url="https://www.foundit.in/login",
        registration_url="https://www.foundit.in/register",
        job_search_url="https://www.foundit.in/srp/results",
        credential_tier="medium",
        requires_resume_upload=True,
        max_applications_per_hour=5,
        known_field_mappings={
            "current salary": "currentCTC",
            "expected salary": "expectedCTC",
            "notice period": "noticePeriod",
        },
    ),

    "wellfound": SiteConfig(
        name="Wellfound (AngelList)",
        key="wellfound",
        base_url="https://wellfound.com",
        login_url="https://wellfound.com/login",
        registration_url="https://wellfound.com/join",
        credential_tier="medium",
        max_applications_per_hour=5,
        min_delay_between_applies=30,
    ),

    "glassdoor": SiteConfig(
        name="Glassdoor",
        key="glassdoor",
        base_url="https://www.glassdoor.co.in",
        login_url="https://www.glassdoor.co.in/profile/login_input.htm",
        registration_url="https://www.glassdoor.co.in/member/join.htm",
        credential_tier="medium",
        has_captcha=True,
        max_applications_per_hour=3,
        min_delay_between_applies=60,
    ),

    "cutshort": SiteConfig(
        name="CutShort",
        key="cutshort",
        base_url="https://cutshort.io",
        login_url="https://cutshort.io/login",
        registration_url="https://cutshort.io/signup",
        credential_tier="medium",
        max_applications_per_hour=5,
    ),

    "hirist": SiteConfig(
        name="Hirist",
        key="hirist",
        base_url="https://www.hirist.tech",
        login_url="https://www.hirist.tech/login",
        registration_url="https://www.hirist.tech/signup",
        credential_tier="medium",
        max_applications_per_hour=5,
    ),
}


class SiteRegistry:
    """Registry for job site configurations."""

    def __init__(self):
        self._sites = dict(SITE_CONFIGS)

    def get(self, site_key: str) -> Optional[SiteConfig]:
        """
        Get site configuration by key.

        Args:
            site_key: Site identifier (e.g., "naukri", "indeed")

        Returns:
            SiteConfig or None if not found
        """
        return self._sites.get(site_key.lower().strip())

    def get_or_create_unknown(self, site_key: str, base_url: str = "") -> SiteConfig:
        """
        Get existing config or create a minimal one for an unknown site.

        Args:
            site_key: Site identifier
            base_url: Base URL of the site

        Returns:
            SiteConfig (existing or newly created)
        """
        existing = self.get(site_key)
        if existing:
            return existing

        # Create minimal config for unknown site
        config = SiteConfig(
            name=site_key.capitalize(),
            key=site_key.lower().strip(),
            base_url=base_url,
            credential_tier="medium",
            requires_ai_navigation=True,
            max_applications_per_hour=3,
            min_delay_between_applies=60,
        )

        self._sites[config.key] = config
        logger.info(f"Created config for unknown site: {site_key}")
        return config

    def identify_site(self, url: str) -> Optional[SiteConfig]:
        """
        Identify which job site a URL belongs to.

        Args:
            url: Any URL

        Returns:
            SiteConfig if matched, None otherwise
        """
        url_lower = url.lower()

        # Extract just the domain (netloc) for key matching to avoid
        # false positives from UTM params like utm_source=linkedin
        try:
            from urllib.parse import urlparse
            domain = urlparse(url_lower).netloc
        except Exception:
            domain = url_lower

        for key, config in self._sites.items():
            if config.base_url and config.base_url.lower() in url_lower:
                return config

            # Only match site key against the domain, not the full URL
            if key in domain:
                return config

        return None

    def list_sites(self) -> List[SiteConfig]:
        """Get all registered sites."""
        return list(self._sites.values())

    def list_site_keys(self) -> List[str]:
        """Get all registered site keys."""
        return list(self._sites.keys())

    def add_site(self, config: SiteConfig):
        """Add or update a site configuration."""
        self._sites[config.key] = config
        logger.info(f"Added site config: {config.key}")
