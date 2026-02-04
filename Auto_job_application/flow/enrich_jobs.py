import time

from Auto_job_application.src.tools.linkedin_tools import LinkedInAgent
from Auto_job_application.src.tools.database_tool import DatabaseManager
from Auto_job_application.src.config.paths import db_path as project_db_path

FINAL_STATUSES = {"APPLIED", "SKIPPED", "BLOCKED", "FAILED"}


def enrich_jobs(limit=50):
    agent = LinkedInAgent()
    db_path = project_db_path()
    db = DatabaseManager(db_path)

    print(f"🧩 [Enrich] Starting enrichment pass (limit={limit})")
    rows = db.execute(
        """
        SELECT * FROM jobs
        WHERE source = 'linkedin'
          AND (
            job_url IS NULL OR job_url = '' OR
            apply_type IS NULL OR apply_type = '' OR
            about_job IS NULL OR about_job = '' OR
            about_company IS NULL OR about_company = '' OR
            enrich_status = 'NEEDS_ENRICH'
          )
        ORDER BY discovered_at ASC
        LIMIT ?
        """,
        (limit,),
        fetch=True,
    )

    print(f"📦 [Enrich] Found {len(rows)} jobs needing enrichment.")

    for job in rows:
        job_url = job["job_url"] or f"https://www.linkedin.com/jobs/view/{job['external_id']}/"
        details = agent.fetch_job_details(job["external_id"], job_url)

        company_id = job["company_id"]
        if not company_id and job["company"]:
            company_id = db.upsert_company(job["company"], about=details.get("about_company"))

        apply_type = details.get("apply_type") or job["apply_type"]
        next_status = job["status"]
        if job["status"] not in FINAL_STATUSES:
            if apply_type == "Easy Apply":
                next_status = "READY_TO_APPLY"
            elif apply_type in {"Company Site", "Apply"}:
                next_status = "SKIPPED"
            else:
                next_status = "NEEDS_ENRICH"

        db.execute(
            """
            UPDATE jobs
            SET job_url = ?,
                about_job = COALESCE(?, about_job),
                about_company = COALESCE(?, about_company),
                compensation = COALESCE(?, compensation),
                work_mode = COALESCE(?, work_mode),
                apply_type = COALESCE(?, apply_type),
                company_id = COALESCE(?, company_id),
                status = ?,
                enrich_status = COALESCE(?, enrich_status),
                last_enrich_error = COALESCE(?, last_enrich_error),
                enriched_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                job_url,
                details.get("about_job"),
                details.get("about_company"),
                details.get("compensation"),
                details.get("work_mode"),
                details.get("apply_type"),
                company_id,
                next_status,
                details.get("enrich_status"),
                details.get("last_enrich_error"),
                job["id"],
            ),
        )
        print(
            f"   ✅ Enriched {job['external_id']} -> apply_type={apply_type}, status={next_status}"
        )
        time.sleep(2)

    print("✅ [Enrich] Enrichment pass complete.")


if __name__ == "__main__":
    import sys

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    enrich_jobs(limit=limit)
