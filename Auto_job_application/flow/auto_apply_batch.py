from Auto_job_application.src.tools.linkedin_tools import LinkedInAgent, ApplicationBot
from Auto_job_application.src.tools.database_tool import DatabaseManager
from Auto_job_application.src.config.paths import master_pdf_path
import time

class AutoApplyFlow:
    """Orchestrates job discovery and automated 'Easy Apply' submission."""
    def __init__(self):
        self.agent = LinkedInAgent()
        self.bot = ApplicationBot()
        self.db = self.agent.db
        self.master_cv = master_pdf_path()

    def run(self, keywords="Engineering Manager", location="Bengaluru", limit=200, apply_limit=10, skip_discovery=False):
        self.db.initialize_schema()
        print(f"🚀 [Flow] Starting Auto-Apply for '{keywords}' (Scan Limit: {limit}, Apply Limit: {apply_limit})")
        
        # 1. Discover Jobs
        if not skip_discovery:
            new_jobs = self.agent.search(keywords, location, limit=limit)
            found_count = len(new_jobs)
            new_count = len(new_jobs) # search() now returns only new jobs based on internal check
            
            for job in new_jobs:
                query = """
                    INSERT OR IGNORE INTO jobs 
                    (external_id, source, title, company, company_id, location, status, job_url, about_job, about_company, compensation, work_mode, apply_type) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                self.db.execute(query, (
                    job['external_id'],
                    "linkedin",
                    job.get('title'),
                    job.get('company'),
                    job.get('company_id'),
                    job.get('location'),
                    "NEW",
                    job.get('job_url'),
                    job.get('about_job'),
                    job.get('about_company'),
                    job.get('compensation'),
                    job.get('work_mode'),
                    job.get('apply_type')
                ))

            # Log the scan
            self.db.execute("""
                INSERT INTO scans (job_title, location, limit_requested, found_count, new_count, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (keywords, location, limit, found_count, new_count, "COMPLETED"))
        else:
            print("⏩ [Flow] Skipping discovery step.")

        # 2. Fetch jobs ready to apply (small test batch)
        jobs_to_apply = self.db.execute(
            """
            SELECT * FROM jobs
            WHERE status = 'READY_TO_APPLY' AND source = 'linkedin'
            ORDER BY discovered_at ASC
            LIMIT ?
            """,
            (apply_limit,),
            fetch=True,
        )

        print(f"📦 [Flow] Queue ready: {len(jobs_to_apply)} jobs to process.")

        for job in jobs_to_apply:
            print(f"👉 [Flow] Processing Job {job['external_id']}...")
            if job["apply_type"] and job["apply_type"] != "Easy Apply":
                result = "SKIPPED"
            else:
                self.db.execute(
                    """
                    UPDATE jobs
                    SET status = 'APPLYING',
                        apply_attempts = COALESCE(apply_attempts, 0) + 1,
                        last_attempt_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (job["id"],),
                )
                result = self.bot.apply_to_job(job, self.master_cv)

            # Update status in DB
            self.db.execute(
                """
                UPDATE jobs
                SET status = ?,
                    last_apply_result = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (result, result, job["id"]),
            )
            print(f"📊 [Flow] Job {job['external_id']} result: {result}")

            # Anti-detection delay
            time.sleep(15)

        print("✅ [Flow] Batch processing finished.")

if __name__ == "__main__":
    flow = AutoApplyFlow()
    flow.run(limit=200)
