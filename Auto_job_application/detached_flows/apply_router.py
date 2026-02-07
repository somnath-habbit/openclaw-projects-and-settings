"""
Apply Router - Routes jobs to the correct application method.

Decides whether to use LinkedIn Easy Apply or the Universal Apply Bot
based on the job source and available application methods.

Usage:
    router = ApplyRouter(session, profile)
    result = await router.apply(job)
"""
import asyncio
import logging
from typing import Dict, Optional

from detached_flows.Playwright.browser_session import BrowserSession

logger = logging.getLogger("ApplyRouter")


class ApplyMethod:
    """Available application methods."""
    EASY_APPLY = "easy_apply"       # LinkedIn Easy Apply
    EXTERNAL_APPLY = "external_apply"  # Universal Apply Bot
    REDIRECT = "redirect"            # Follow redirect, then universal apply
    SKIP = "skip"                    # No apply method available


class ApplyRouter:
    """
    Routes job applications to the correct bot/method.

    Existing flow: LinkedIn Easy Apply only
    New flow: LinkedIn OR Universal Apply Bot
    """

    def __init__(
        self,
        session: BrowserSession,
        profile: dict,
        debug: bool = False,
        dry_run: bool = False,
    ):
        self.session = session
        self.profile = profile
        self.debug = debug
        self.dry_run = dry_run

    def route(self, job: dict) -> str:
        """
        Determine which application method to use for a job.

        Args:
            job: Job dict with keys like 'source', 'easy_apply', 'apply_url', etc.

        Returns:
            ApplyMethod constant
        """
        source = (job.get('source') or '').lower()
        easy_apply = job.get('easy_apply', False)
        apply_url = job.get('apply_url', '')
        job_url = job.get('url') or job.get('job_url', '')

        # LinkedIn Easy Apply
        if source == 'linkedin' and easy_apply:
            return ApplyMethod.EASY_APPLY

        # External apply URL provided
        if apply_url:
            # Check if the apply URL redirects to another site
            if source == 'linkedin' and not easy_apply:
                return ApplyMethod.REDIRECT
            return ApplyMethod.EXTERNAL_APPLY

        # Job URL available but no specific apply method
        if job_url:
            if 'linkedin.com' in job_url:
                # LinkedIn job without Easy Apply - has an external apply link
                return ApplyMethod.REDIRECT
            return ApplyMethod.EXTERNAL_APPLY

        return ApplyMethod.SKIP

    async def apply(self, job: dict) -> Dict:
        """
        Route and execute application for a job.

        Args:
            job: Job dict

        Returns:
            Result dict with 'status', 'method', etc.
        """
        method = self.route(job)
        job_url = job.get('url') or job.get('job_url', '')
        apply_url = job.get('apply_url', '')

        logger.info(f"Routing job to method: {method}")

        if method == ApplyMethod.SKIP:
            return {
                'status': 'SKIPPED',
                'method': method,
                'reason': 'No application method available',
            }

        if method == ApplyMethod.EASY_APPLY:
            return await self._apply_easy(job)

        if method in (ApplyMethod.EXTERNAL_APPLY, ApplyMethod.REDIRECT):
            target_url = apply_url or job_url
            return await self._apply_universal(job, target_url)

        return {'status': 'UNKNOWN_METHOD', 'method': method}

    async def _apply_easy(self, job: dict) -> Dict:
        """Route to LinkedIn Easy Apply bot."""
        from detached_flows.Playwright.easy_apply_bot import EasyApplyBot

        job_url = job.get('url') or job.get('job_url', '')
        resume_path = job.get('resume_path', '')

        try:
            bot = EasyApplyBot(
                session=self.session,
                debug=self.debug,
                dry_run=self.dry_run,
            )

            result = await bot.apply_to_job(job_url, resume_path)

            return {
                'status': result.get('status', 'UNKNOWN'),
                'method': ApplyMethod.EASY_APPLY,
                'details': result,
            }

        except Exception as e:
            logger.error(f"Easy Apply failed: {e}")
            return {
                'status': 'FAILED',
                'method': ApplyMethod.EASY_APPLY,
                'error': str(e),
            }

    async def _apply_universal(self, job: dict, target_url: str) -> Dict:
        """Route to Universal Apply Bot."""
        from detached_flows.Playwright.universal_apply_bot import (
            UniversalApplyBot, ApplicationResult
        )

        site_name = job.get('source', '')
        job_context = {
            'title': job.get('title', ''),
            'company': job.get('company', ''),
            'location': job.get('location', ''),
            'description': job.get('description', '')[:500],
        }

        try:
            bot = UniversalApplyBot(
                session=self.session,
                profile=self.profile,
                debug=self.debug,
                dry_run=self.dry_run,
            )

            result = await bot.apply_to_job(
                job_url=target_url,
                site_name=site_name,
                job_context=job_context,
            )

            return {
                'status': result.status,
                'method': ApplyMethod.EXTERNAL_APPLY,
                'pages_navigated': result.pages_navigated,
                'fields_filled': result.fields_filled,
                'errors': result.errors,
                'duration': result.duration_seconds,
            }

        except Exception as e:
            logger.error(f"Universal Apply failed: {e}")
            return {
                'status': 'FAILED',
                'method': ApplyMethod.EXTERNAL_APPLY,
                'error': str(e),
            }

    async def apply_batch(
        self,
        jobs: list,
        max_per_site: int = 5,
        delay_between: int = 30,
    ) -> list:
        """
        Apply to multiple jobs with rate limiting.

        Args:
            jobs: List of job dicts
            max_per_site: Max applications per site
            delay_between: Delay between applications in seconds

        Returns:
            List of result dicts
        """
        results = []
        site_counts = {}

        for job in jobs:
            site = (job.get('source') or 'unknown').lower()

            # Rate limit check
            site_counts[site] = site_counts.get(site, 0) + 1
            if site_counts[site] > max_per_site:
                logger.info(f"Rate limit reached for {site} ({max_per_site})")
                results.append({
                    'status': 'RATE_LIMITED',
                    'job_url': job.get('url', ''),
                    'site': site,
                })
                continue

            # Apply
            result = await self.apply(job)
            result['job_url'] = job.get('url', '')
            result['site'] = site
            results.append(result)

            # Delay between applications
            if delay_between > 0:
                logger.info(f"Waiting {delay_between}s before next application...")
                await asyncio.sleep(delay_between)

        return results
