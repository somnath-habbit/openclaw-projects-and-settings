from Auto_job_application.src.tools.linkedin_tools import TriageEngine
from Auto_job_application.src.tools.database_tool import DatabaseManager
from pathlib import Path
import time

def process_pending_letters():
    db_path = Path("/home/somnath/.openclaw/workspace/Auto_job_application/data/autobot.db")
    db = DatabaseManager(db_path)
    engine = TriageEngine()

    print("🤖 Monitoring for Cover Letter requests...")
    
    # Get one pending job
    job = db.execute("SELECT * FROM jobs WHERE cover_letter = 'PENDING_GENERATION' LIMIT 1", fetch=True)
    
    if job:
        job = job[0]
        print(f"✨ Found request for: {job['title']} ({job['external_id']})")
        prompt = engine.generate_cover_letter_prompt(job['title'], job['company'], job['jd_text'])
        
        # We return the prompt and the job ID so the main agent can spawn it
        return {"job_id": job['id'], "external_id": job['external_id'], "prompt": prompt}
    
    return None

if __name__ == "__main__":
    res = process_pending_letters()
    if res:
        # Output for main agent to capture
        import json
        print(f"COMMAND_START:{json.dumps(res)}:COMMAND_END")
