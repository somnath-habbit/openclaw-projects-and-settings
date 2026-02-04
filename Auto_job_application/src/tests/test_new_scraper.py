import json
import time
from Auto_job_application.src.tools.linkedin_tools import LinkedInAgent

def test_full_pipeline():
    agent = LinkedInAgent()
    print("🧪 [Test] Running Structured Scraper Phased Test (10 → 25 → 50)")

    phases = [10, 25, 50]
    for phase_limit in phases:
        print(f"\n🧪 [Phase] Running with limit={phase_limit}")
        new_jobs = agent.search("Engineering Manager", "Bengaluru", limit=phase_limit)

        print("\n📊 --- PHASE RESULTS ---")
        print(f"Total Unique New Jobs Discovered: {len(new_jobs)}")

        if len(new_jobs) > 0:
            print("✅ SUCCESS: Discovered new jobs with metadata.")
            for i, j in enumerate(new_jobs[:10]):
                print(f"   {i+1}. [{j['external_id']}] {j.get('title')} @ {j.get('company')} ({j.get('location')})")
        else:
            print("❌ FAILURE: No jobs discovered.")

        if any(j.get('company') not in (None, 'Unknown') for j in new_jobs):
            print("✅ SUCCESS: Metadata (Company) successfully extracted.")
        else:
            print("⚠️ WARNING: Metadata extraction might have failed (all 'Unknown').")

        if phase_limit != phases[-1] and len(new_jobs) == 0:
            print("🛑 Stopping phased test early due to empty results.")
            break

if __name__ == "__main__":
    test_full_pipeline()
