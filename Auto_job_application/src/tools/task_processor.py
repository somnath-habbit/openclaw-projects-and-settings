from Auto_job_application.src.tools.linkedin_tools import TriageEngine
from Auto_job_application.src.tools.database_tool import DatabaseManager
from Auto_job_application.src.config.paths import db_path as project_db_path
import json

def process_pending_tasks():
    db_path = project_db_path()
    db = DatabaseManager(db_path)
    engine = TriageEngine()

    print("🤖 Monitoring for background tasks...")
    
    # 1. Check for Pending Cover Letters
    job_cl = db.execute("SELECT * FROM jobs WHERE cover_letter = 'PENDING_GENERATION' LIMIT 1", fetch=True)
    if job_cl:
        job = job_cl[0]
        print(f"✨ Found Cover Letter request for: {job['title']}")
        prompt = engine.generate_cover_letter_prompt(job['title'], job['company'], job['jd_text'])
        return {"type": "COVER_LETTER", "job_id": job['id'], "external_id": job['external_id'], "prompt": prompt}

    # 2. Check for Pending Resume Tailoring
    job_rt = db.execute("SELECT * FROM jobs WHERE tailored_resume_json = 'PENDING_TAILORING' LIMIT 1", fetch=True)
    if job_rt:
        job = job_rt[0]
        print(f"🎨 Found Resume Tailoring request for: {job['title']}")
        # Use profile from DB if available
        try:
            profile_row = db.execute("SELECT data FROM profile WHERE id = 1", fetch=True)
            if profile_row:
                engine.profile_data = json.loads(profile_row[0][0])
        except:
            pass
        prompt = engine.generate_resume_tailoring_prompt(job['title'], job['company'], job['jd_text'])
        return {"type": "RESUME_TAILORING", "job_id": job['id'], "external_id": job['external_id'], "prompt": prompt}
    
    return None

if __name__ == "__main__":
    res = process_pending_tasks()
    if res:
        print(f"COMMAND_START:{json.dumps(res)}:COMMAND_END")
