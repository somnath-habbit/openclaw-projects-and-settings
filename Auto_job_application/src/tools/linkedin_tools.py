import json
import os
import subprocess
import time
import re
import logging
from datetime import datetime
from abc import ABC, abstractmethod
from pathlib import Path
from Auto_job_application.src.tools.database_tool import DatabaseManager
from Auto_job_application.src.config.paths import project_root, data_dir, db_path, openclaw_bin

class BaseAgent(ABC):
    """Base class for all portal-specific agents."""
    def __init__(
        self,
        workspace_dir: str | Path | None = None,
        debug: bool = False,
        testing_mode: bool = False,
        max_failures: int = 5,
    ):
        self.workspace_dir = Path(workspace_dir).expanduser().resolve() if workspace_dir else project_root()
        self.data_dir = self.workspace_dir / "data" if workspace_dir else data_dir()
        db_override = os.environ.get("AUTO_JOB_APPLICATION_DB")
        resolved_db_path = None
        if db_override:
            resolved_db_path = Path(db_override).expanduser().resolve()
        elif workspace_dir:
            resolved_db_path = self.data_dir / "autobot.db"
        else:
            resolved_db_path = db_path()
        self.db = DatabaseManager(resolved_db_path)
        self.db.initialize_schema()
        self.browser_profile = "openclaw"
        self.debug = debug
        self.testing_mode = testing_mode
        self.max_failures = max_failures
        self.openclaw_bin = openclaw_bin()
        self.snapshots_dir = self.data_dir / "snapshots"
        self.screenshots_dir = self.data_dir / "screenshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG if self.debug else logging.INFO)

    def _log_event(self, level: int, payload: dict):
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            **payload,
        }
        self.logger.log(level, json.dumps(payload, ensure_ascii=False))

    def _apply_backoff(self, failures: int):
        if failures <= 2:
            delay = 2
        elif failures <= 4:
            delay = 5
        else:
            delay = 10
        time.sleep(delay)

    def _save_snapshot_text(self, job_id: str, aria_snap: str) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = self.snapshots_dir / f"{job_id}_{timestamp}.txt"
        path.write_text(aria_snap, encoding="utf-8")
        return path

    def _capture_debug_artifacts(self, job_id: str, target_id: str | None, reason: str, aria_snap: str | None = None):
        if not self.debug:
            return
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        if aria_snap:
            self._save_snapshot_text(job_id, aria_snap)
        screenshot_path = self.screenshots_dir / f"{job_id}_{timestamp}.png"
        cmd = ["screenshot", "--path", str(screenshot_path)]
        if target_id:
            cmd += ["--target-id", target_id]
        ok, output = self.run_browser(cmd)
        if not ok:
            self._log_event(logging.WARNING, {
                "event": "screenshot_failed",
                "job_id": job_id,
                "reason": reason,
                "error": output,
            })

    def run_browser(self, cmd: list[str], timeout: int = 180) -> tuple[bool, str]:
        """Wrapper for OpenClaw browser CLI."""
        full_cmd = [self.openclaw_bin, "browser", "--browser-profile", self.browser_profile] + cmd
        try:
            result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

    def _capture_state(self, stage: str, target_id: str | None = None):
        """Captures a screenshot if testing mode is enabled."""
        if not self.testing_mode:
            return
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        name = f"test_{stage}_{timestamp}"
        screenshot_path = self.screenshots_dir / f"{name}.png"
        cmd = ["screenshot", "--path", str(screenshot_path)]
        if target_id:
            cmd += ["--target-id", target_id]
        self.run_browser(cmd)
        self._log_event(logging.INFO, {"event": "test_screenshot_captured", "path": str(screenshot_path), "stage": stage})

    def _wait_for_selector(self, selector_text: str, target_id: str | None = None, timeout: int = 15) -> bool:
        """Waits for a specific text/element to appear in the snapshot."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            cmd = ["snapshot", "--format", "aria"]
            if target_id:
                cmd += ["--target-id", target_id]
            ok, snap = self.run_browser(cmd)
            # Simple text check since we are using Aria snapshots
            if ok and selector_text in snap:
                return True
            time.sleep(1)
        return False


class LinkedInAgent(BaseAgent):
    """Specific implementation for LinkedIn."""

    def __init__(self, *args, retry_attempts: int = 3, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry_attempts = retry_attempts

    def _open_new_tab(self, url: str) -> tuple[str | None, str, bool]:
        success, output = self.run_browser(["open", url])
        target_id = None
        if success:
            match = re.search(r'id:\s*([^\n]+)', output)
            if match:
                target_id = match.group(1).strip()
        return target_id, output, success

    def _close_tab(self, target_id: str | None):
        if target_id:
            self.run_browser(["close", target_id])

    def _snapshot_aria(self, target_id: str | None = None) -> tuple[bool, str]:
        cmd = ["snapshot", "--format", "aria"]
        if target_id:
            cmd += ["--target-id", target_id]
        return self.run_browser(cmd)

    def _extract_section(self, aria_snap: str, headers: list[str]) -> str | None:
        lines = aria_snap.splitlines()
        for header in headers:
            for idx, line in enumerate(lines):
                if f'heading "{header}"' in line or f'"{header}"' in line:
                    collected = []
                    for j in range(idx + 1, len(lines)):
                        next_line = lines[j]
                        if 'heading "' in next_line and j > idx + 1:
                            break
                        if 'button "' in next_line:
                            continue
                        text_match = re.search(r':\s*(.+)$', next_line)
                        if text_match:
                            text = text_match.group(1).strip()
                            if text and not text.lower().startswith('see more'):
                                collected.append(text)
                    if collected:
                        return "\n".join(collected).strip()
        return None

    def _extract_compensation(self, aria_snap: str) -> str | None:
        lines = aria_snap.splitlines()
        for idx, line in enumerate(lines):
            if re.search(r'(pay|salary|compensation)', line, re.IGNORECASE):
                text = re.sub(r'^.*?:\s*', '', line).strip()
                if text:
                    return text
                if idx + 1 < len(lines):
                    nxt = re.sub(r'^.*?:\s*', '', lines[idx + 1]).strip()
                    if nxt:
                        return nxt
        for line in lines:
            if re.search(r'[$€₹£]\s*\d', line):
                return re.sub(r'^.*?:\s*', '', line).strip()
        return None

    def _extract_work_mode(self, aria_snap: str) -> str | None:
        match = re.search(r'\b(Remote|Hybrid|On[- ]site|Onsite)\b', aria_snap)
        if match:
            return match.group(1).replace('Onsite', 'On-site').replace('On site', 'On-site')
        return None

    def _extract_apply_type(self, aria_snap: str) -> str | None:
        if re.search(r'Easy Apply', aria_snap, re.IGNORECASE):
            return "Easy Apply"
        if re.search(r'Apply on company site|Apply on company website|Apply on company', aria_snap, re.IGNORECASE):
            return "Company Site"
        if re.search(r'Apply', aria_snap, re.IGNORECASE):
            return "Apply"
        return None

    def _expand_see_more(self, aria_snap: str, target_id: str | None = None):
        see_more_refs = re.findall(r'button "(?:See more|Show more|… more|\.\.\. more)[^"]*" \[ref=([^\]]+)\]', aria_snap)
        for ref in see_more_refs[:5]:
            cmd = ["click", ref]
            if target_id:
                cmd += ["--target-id", target_id]
            self.run_browser(cmd)
            time.sleep(1)

    def _assess_enrichment_quality(self, about_job: str | None, apply_type: str | None) -> tuple[bool, str | None]:
        if not apply_type:
            return True, "apply_type_missing"
        if not about_job or len(about_job.strip()) < 100:
            return True, "about_job_too_short"
        return False, None

    def _fetch_job_details_once(self, external_id: str, job_url: str) -> tuple[dict, bool, str | None]:
        target_id, open_output, success = self._open_new_tab(job_url)
        default_response = {
            "about_job": None,
            "about_company": None,
            "compensation": None,
            "work_mode": None,
            "apply_type": None,
            "job_url": job_url,
            "enrich_status": "NEEDS_ENRICH",
            "last_enrich_error": "open_tab_failed",
        }
        if not success:
            self._log_event(logging.ERROR, {
                "event": "open_tab_failed",
                "job_id": external_id,
                "error": open_output,
            })
            return default_response, False, "open_tab_failed"

        target_opts = ["--target-id", target_id] if target_id else []
        try:
            # Wait for content instead of blind sleep
            loaded = self._wait_for_selector("About the job", target_id, timeout=10)
            if not loaded:
                # Fallback to simple sleep if selector not found (maybe different layout)
                time.sleep(5)
            
            self._capture_state("job_loaded", target_id)

            self.run_browser(["press", "End", *target_opts])
            time.sleep(1)
            self.run_browser(["press", "Home", *target_opts])
            time.sleep(1)
            
            self._capture_state("job_scrolled", target_id)

            ok, aria_snap = self._snapshot_aria(target_id)
            if not ok:
                self._capture_debug_artifacts(external_id, target_id, "snapshot_failed")
                return default_response, False, "snapshot_failed"

            self._expand_see_more(aria_snap, target_id)
            time.sleep(1)
            
            self._capture_state("job_expanded", target_id)

            ok, aria_snap = self._snapshot_aria(target_id)

            if not ok:
                self._capture_debug_artifacts(external_id, target_id, "snapshot_failed")
                return default_response, False, "snapshot_failed"

            about_job = self._extract_section(aria_snap, ["About the job", "Job description", "Job Description"])
            about_company = self._extract_section(aria_snap, ["About the company", "About us", "Company overview"])
            compensation = self._extract_compensation(aria_snap)
            work_mode = self._extract_work_mode(aria_snap)
            apply_type = self._extract_apply_type(aria_snap)

            needs_enrich, enrich_error = self._assess_enrichment_quality(about_job, apply_type)
            if needs_enrich:
                self._capture_debug_artifacts(external_id, target_id, enrich_error or "needs_enrich", aria_snap)

            return {
                "about_job": about_job,
                "about_company": about_company,
                "compensation": compensation,
                "work_mode": work_mode,
                "apply_type": apply_type,
                "job_url": job_url,
                "enrich_status": "NEEDS_ENRICH" if needs_enrich else "ENRICHED",
                "last_enrich_error": enrich_error,
            }, True, enrich_error
        finally:
            self._close_tab(target_id)

    def fetch_job_details(self, external_id: str, job_url: str) -> dict:
        self._log_event(logging.INFO, {
            "event": "detail_fetch_start",
            "job_id": external_id,
        })
        for attempt in range(1, self.retry_attempts + 1):
            details, success, error = self._fetch_job_details_once(external_id, job_url)
            if success and details.get("enrich_status") == "ENRICHED":
                return details
            if attempt < self.retry_attempts:
                self._log_event(logging.WARNING, {
                    "event": "detail_retry",
                    "job_id": external_id,
                    "attempt": attempt,
                    "error": error,
                })
                time.sleep(2)
        return details

    def search(self, keywords, location, limit=200, detail=True):
        self._log_event(logging.INFO, {
            "event": "search_start",
            "keywords": keywords,
            "location": location,
            "limit": limit,
            "detail": detail,
        })
        all_found_jobs = []
        new_jobs = []
        failures = 0

        for offset in range(0, limit, 25):
            url = f"https://www.linkedin.com/jobs/search/?keywords={keywords.replace(' ', '%20')}&location={location.replace(' ', '%20')}&f_AL=true&start={offset}"
            self._log_event(logging.INFO, {"event": "open_search", "offset": offset, "url": url})
            ok, output = self.run_browser(["open", url])
            if not ok:
                failures += 1
                self._log_event(logging.ERROR, {"event": "open_search_failed", "offset": offset, "error": output})
                if failures > self.max_failures:
                    break
                self._apply_backoff(failures)
                continue

            # Wait for search results
            self._wait_for_selector("Filter", timeout=15)
            self._capture_state("search_loaded")

            self.run_browser(["press", "End"])
            time.sleep(2)
            self.run_browser(["press", "Home"])
            time.sleep(2)

            self._capture_state("search_scrolled")

            ok, aria_snap = self.run_browser(["snapshot"])
            if not ok:
                failures += 1
                self._log_event(logging.ERROR, {"event": "snapshot_failed", "offset": offset})
                if failures > self.max_failures:
                    break
                self._apply_backoff(failures)
                continue

            job_matches = re.finditer(r'link "([^"]+)" \[ref=[^\]]+\]:\s*\n\s*- /url: /jobs/view/(\d+)', aria_snap)

            page_jobs = []
            for match in job_matches:
                title = match.group(1).replace(" with verification", "").strip()
                jid = match.group(2)

                if any(j['external_id'] == jid for j in all_found_jobs):
                    continue

                company = "LinkedIn"
                post_match = aria_snap[match.end():match.end()+500]
                comp_match = re.search(r'- generic \[ref=[^\]]+\]: ([^\n]+)', post_match)
                if comp_match:
                    company = comp_match.group(1).strip()

                job_url = f"https://www.linkedin.com/jobs/view/{jid}/"
                page_jobs.append({
                    "external_id": jid,
                    "title": title,
                    "company": company,
                    "location": location,
                    "job_url": job_url
                })

            if not page_jobs:
                job_matches = re.finditer(r'link "([^"]+)" \[ref=[^\]]+\]:.*?- /url: /jobs/view/(\d+)', aria_snap, re.DOTALL)
                for match in job_matches:
                    jid = match.group(2)
                    page_jobs.append({
                        "external_id": jid,
                        "title": match.group(1).replace(" with verification", "").strip(),
                        "company": "LinkedIn",
                        "location": location,
                        "job_url": f"https://www.linkedin.com/jobs/view/{jid}/"
                    })

            if not page_jobs:
                ids = list(dict.fromkeys(re.findall(r'/jobs/view/(\d+)', aria_snap)))
                page_jobs = [
                    {
                        "external_id": i,
                        "title": "Discovered Job",
                        "company": "LinkedIn",
                        "location": location,
                        "job_url": f"https://www.linkedin.com/jobs/view/{i}/",
                    }
                    for i in ids
                ]

            self._log_event(logging.INFO, {"event": "page_processed", "offset": offset, "count": len(page_jobs)})

            new_on_this_page = 0
            for job in page_jobs:
                existing = self.db.execute("SELECT id FROM jobs WHERE external_id = ?", (job['external_id'],), fetch=True)
                if not existing:
                    new_on_this_page += 1
                    new_jobs.append(job)
                all_found_jobs.append(job)

            self._log_event(logging.INFO, {"event": "page_new_jobs", "offset": offset, "count": new_on_this_page})
            if offset > 0 and len(page_jobs) > 5 and new_on_this_page == 0:
                self._log_event(logging.INFO, {"event": "duplicate_threshold_reached", "offset": offset})
                break

            if len(all_found_jobs) >= limit:
                break

        if detail and new_jobs:
            enriched_jobs = []
            for job in new_jobs:
                details = self.fetch_job_details(job['external_id'], job['job_url'])
                job.update(details)
                company_id = self.db.upsert_company(job.get("company"), about=job.get("about_company"))
                if company_id:
                    job["company_id"] = company_id
                enriched_jobs.append(job)
                if details.get("enrich_status") != "ENRICHED":
                    failures += 1
                    if failures > self.max_failures:
                        self._log_event(logging.ERROR, {"event": "max_failures_reached", "stage": "detail"})
                        break
                    self._apply_backoff(failures)
                else:
                    failures = 0
            return enriched_jobs

        return new_jobs

class ApplicationBot(BaseAgent):
    """Handles the automated application process and question solving."""

    def _detect_apply_type(self, aria_snap: str) -> str | None:
        if re.search(r"Easy Apply", aria_snap, re.IGNORECASE):
            return "Easy Apply"
        if re.search(r"Apply on company site|Apply on company website|Apply on company", aria_snap, re.IGNORECASE):
            return "Company Site"
        if re.search(r"Apply", aria_snap, re.IGNORECASE):
            return "Apply"
        return None

    def apply_to_job(self, job, cv_path):
        external_id = job["external_id"]
        url = job["job_url"] or f"https://www.linkedin.com/jobs/view/{external_id}/"
        print(f"🚀 [Apply] Starting for Job {external_id}...")
        self.run_browser(["open", url])
        time.sleep(5)

        _, snap = self.run_browser(["snapshot", "--format", "aria"])
        apply_type = job["apply_type"] or self._detect_apply_type(snap)
        if not job["apply_type"] and apply_type:
            self.db.execute(
                "UPDATE jobs SET apply_type = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (apply_type, job["id"]),
            )

        if apply_type != "Easy Apply":
            return "SKIPPED"

        match = re.search(r'(?:button|link) "Easy Apply[^"]*" \[ref=([^\]]+)\]', snap)
        if not match:
            return "SKIPPED"

        self.run_browser(["click", match.group(1)])
        time.sleep(3)

        for step in range(1, 11):
            _, step_snap = self.run_browser(["snapshot", "--format", "aria"])

            if "Upload resume" in step_snap and cv_path:
                upload_match = re.search(r'button "Upload resume[^"]*" \[ref=([^\]]+)\]', step_snap)
                if upload_match:
                    self.run_browser(
                        [
                            "upload",
                            "--paths",
                            str(cv_path),
                            "--request",
                            json.dumps({"kind": "click", "ref": upload_match.group(1)}),
                        ]
                    )
                    time.sleep(2)

            if "Submit application" in step_snap:
                submit_match = re.search(r'button "Submit application" \[ref=([^\]]+)\]', step_snap)
                if submit_match:
                    self.run_browser(["click", submit_match.group(1)])
                    return "APPLIED"

            next_match = re.search(r'button "(?:Next|Review|Continue)[^"]*" \[ref=([^\]]+)\]', step_snap)
            if next_match:
                self.run_browser(["click", next_match.group(1)])
                time.sleep(3)
            else:
                if "application was sent" in step_snap or "Applied" in step_snap:
                    return "APPLIED"
                return "BLOCKED"

        return "FAILED"
