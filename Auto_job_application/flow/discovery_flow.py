from Auto_job_application.src.tools.linkedin_tools import LinkedInAgent
from Auto_job_application.src.tools.database_tool import DatabaseManager
from pathlib import Path
import argparse

class DiscoveryFlow:
    """Orchestrates job discovery using the LinkedIn agent with rich metadata capture."""
    def __init__(self):
        self.agent = LinkedInAgent()
        self.agent.db.initialize_schema()

    def run(self, keywords="Engineering Manager", location=None, limit=50, detail=True):
        location = location or "Bengaluru"
        print(f"🚀 [Flow] Starting search for '{keywords}' in '{location}' (limit={limit})...")
        jobs = self.agent.search(keywords, location, limit=limit, detail=detail)

        if not jobs:
            print("❌ No jobs discovered.")
            return 0, 0

        found_count = len(jobs)
        new_count = 0
        for job in jobs:
            status = "NEEDS_ENRICH" if job.get("enrich_status") == "NEEDS_ENRICH" else "NEW"
            query = """
                INSERT OR IGNORE INTO jobs 
                (external_id, source, title, company, company_id, location, status, job_url, about_job, about_company, compensation, work_mode, apply_type, enrich_status, last_enrich_error) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            inserted = self.agent.db.execute(query, (
                job.get('external_id'),
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
            if inserted:
                new_count += 1

        self.agent.db.execute(
            """
            INSERT INTO scans (job_title, location, limit_requested, found_count, new_count, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (keywords, location, limit, found_count, new_count, "COMPLETED"),
        )

        print(f"✅ Flow complete. Found: {found_count} | Inserted new: {new_count}")
        return found_count, new_count

    def run_phased(self, keywords="Engineering Manager", location=None, phases=None, detail=True, early_stop=False):
        phases = phases or [10, 25, 50]
        location = location or "Bengaluru"
        for phase_limit in phases:
            print(f"\n🧪 [Phase] Starting phased scrape (limit={phase_limit})")
            _, new_count = self.run(
                keywords=keywords,
                location=location,
                limit=phase_limit,
                detail=detail,
            )
            if early_stop and new_count == 0:
                print("🛑 [Phase] No new jobs added in the last phase. Stopping phased run.")
                break


def _parse_args():
    parser = argparse.ArgumentParser(description="Run LinkedIn discovery flow")
    parser.add_argument("--keywords", default="Engineering Manager")
    parser.add_argument("--location", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--phased", action="store_true", default=False)
    parser.add_argument("--early-stop", action="store_true", default=False)
    parser.add_argument("--phases", default=None, help="Comma-separated list of phase limits")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    flow = DiscoveryFlow()
    phases = None
    if args.phases:
        phases = [int(p.strip()) for p in args.phases.split(",") if p.strip()]
    if args.phased:
        flow.run_phased(
            keywords=args.keywords,
            location=args.location,
            phases=phases,
            early_stop=args.early_stop,
        )
    else:
        flow.run(
            keywords=args.keywords,
            location=args.location,
            limit=args.limit,
        )
