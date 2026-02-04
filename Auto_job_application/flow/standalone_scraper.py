import json
import time
import argparse
from Auto_job_application.src.tools.linkedin_tools import LinkedInAgent
from Auto_job_application.src.tools.database_tool import DatabaseManager
from Auto_job_application.src.config.paths import db_path as project_db_path

class StandaloneScraper:
    """Independent scraper job that populates the database with rich metadata."""
    def __init__(self, db_path=None, debug=False, max_failures=5, testing_mode=False):
        self.agent = LinkedInAgent(debug=debug, max_failures=max_failures, testing_mode=testing_mode)
        self.db_path = db_path or project_db_path()
        self.db = DatabaseManager(self.db_path)
        self.debug = debug

    def run(self, keywords="Engineering Manager", location=None, limit=200, dry_run=False):
        location = location or "Bengaluru"
        print(f"🚀 [Standalone Scraper] Starting for '{keywords}' in '{location}' (Limit: {limit})")

        new_jobs = self.agent.search(keywords, location, limit=limit)

        found_count = len(new_jobs)
        new_count = 0

        if dry_run:
            print("🧪 [Standalone Scraper] Dry run enabled. Skipping DB writes.")
        else:
            for job in new_jobs:
                query = """
                    INSERT OR IGNORE INTO jobs 
                    (external_id, source, title, company, company_id, location, status, job_url, about_job, about_company, compensation, work_mode, apply_type, enrich_status, last_enrich_error, discovered_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """
                status = "NEEDS_ENRICH" if job.get("enrich_status") == "NEEDS_ENRICH" else "NEW"
                self.db.execute(query, (
                    job['external_id'],
                    "linkedin",
                    job.get('title'),
                    job.get('company'),
                    job.get('company_id'),
                    job.get('location'),
                    status,
                    job.get('job_url'),
                    job.get('about_job'),
                    job.get('about_company'),
                    job.get('compensation'),
                    job.get('work_mode'),
                    job.get('apply_type'),
                    job.get('enrich_status'),
                    job.get('last_enrich_error'),
                ))
                new_count += 1
                print(f"   💾 Saved: {job.get('title')} @ {job.get('company')}")

            self.db.execute("""
                INSERT INTO scans (job_title, location, limit_requested, found_count, new_count, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (keywords, location, limit, found_count, new_count, "COMPLETED"))

        print(f"✅ [Scraper Job Finished] Found: {found_count} | New Added: {new_count}")
        return found_count, new_count

    def run_phased(self, keywords="Engineering Manager", location=None, phases=None, early_stop=False, dry_run=False):
        phases = phases or [10, 25, 50]
        location = location or "Bengaluru"
        for phase_limit in phases:
            print(f"\n🧪 [Phase] Starting phased scrape (limit={phase_limit})")
            _, new_count = self.run(keywords=keywords, location=location, limit=phase_limit, dry_run=dry_run)
            if early_stop and new_count == 0:
                print("🛑 [Phase] No new jobs added in the last phase. Stopping phased run.")
                break


def _parse_args():
    parser = argparse.ArgumentParser(description="Run standalone LinkedIn scraper")
    parser.add_argument("--keywords", default="Engineering Manager")
    parser.add_argument("--location", default=None)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--phased", action="store_true", default=False)
    parser.add_argument("--early-stop", action="store_true", default=False)
    parser.add_argument("--phases", default=None, help="Comma-separated list of phase limits")
    parser.add_argument("--debug", action="store_true", default=False, help="Enable verbose logs and screenshots on failures")
    parser.add_argument("--testing", action="store_true", default=False, help="Enable testing mode (screenshots at each stage)")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Run scraper without writing to DB")
    parser.add_argument("--max-failures", type=int, default=5, help="Stop run after N consecutive failures")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    scraper = StandaloneScraper(debug=args.debug, max_failures=args.max_failures, testing_mode=args.testing)
    phases = None
    if args.phases:
        phases = [int(p.strip()) for p in args.phases.split(",") if p.strip()]
    if args.phased:
        scraper.run_phased(
            keywords=args.keywords,
            location=args.location,
            phases=phases,
            early_stop=args.early_stop,
            dry_run=args.dry_run,
        )
    else:
        scraper.run(
            keywords=args.keywords,
            location=args.location,
            limit=args.limit,
            dry_run=args.dry_run,
        )
