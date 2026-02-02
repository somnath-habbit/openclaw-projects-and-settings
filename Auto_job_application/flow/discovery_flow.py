from Auto_job_application.src.tools.linkedin_tools import LinkedInAgent
from Auto_job_application.src.tools.database_tool import DatabaseManager
from pathlib import Path

class DiscoveryFlow:
    """Orchestrates job discovery using the specific LinkedIn Agent."""
    def __init__(self):
        self.agent = LinkedInAgent()
        # Ensure schema is initialized correctly for multi-source
        self.agent.db.initialize_schema()

    def run(self, keywords="Engineering Manager", location="Bengaluru"):
        print(f"🚀 [Flow] Starting search for '{keywords}' in '{location}'...")
        snapshot = self.agent.search(keywords, location)
        
        if not snapshot:
            print("❌ Flow failed: Snapshot empty.")
            return

        job_ids = self.agent.parse_job_ids(snapshot)
        print(f"🔎 Detected {len(job_ids)} LinkedIn jobs.")

        new_count = 0
        for jid in job_ids[:10]:
            query = "INSERT OR IGNORE INTO jobs (external_id, source, title, url, status) VALUES (?, ?, ?, ?, ?)"
            url = f"https://www.linkedin.com/jobs/view/{jid}/"
            if self.agent.db.execute(query, (jid, "linkedin", "Discovered via Flow", url, "NEW")) > 0:
                new_count += 1
        
        print(f"✅ Flow complete. Added {new_count} new entries to DB.")

if __name__ == "__main__":
    flow = DiscoveryFlow()
    flow.run()
