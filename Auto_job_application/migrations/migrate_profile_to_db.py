import sqlite3
import json

from Auto_job_application.src.config.paths import project_root, db_path as project_db_path, profile_path

# Paths
BASE_DIR = project_root()
DB_PATH = project_db_path()
PROFILE_PATH = BASE_DIR / "data" / "extracted_profile.json"
OLD_PROFILE_PATH = profile_path()

def migrate():
    print(f"Migrating profile data to {DB_PATH}...")
    
    # 1. Connect to DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 2. Create 'profile' table if not exists
    # We will store the entire profile JSON blob in a single column for flexibility
    # ID is always 1 for the main user profile
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY,
            data JSON
        )
    """)
    
    # 2.5 Add 'resume_json' column to 'jobs' table if not exists
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN resume_json JSON")
        print("Added 'resume_json' column to 'jobs' table.")
    except sqlite3.OperationalError:
        print("'resume_json' column already exists in 'jobs' table.")
    
    # 3. Load JSON Data
    final_profile = {}
    
    if PROFILE_PATH.exists():
        print(f"Loading extracted profile from {PROFILE_PATH}")
        with open(PROFILE_PATH, 'r') as f:
            final_profile = json.load(f)
    elif OLD_PROFILE_PATH.exists():
        print(f"Loading basic profile from {OLD_PROFILE_PATH}")
        with open(OLD_PROFILE_PATH, 'r') as f:
            # Wrap in structure if needed, but extracted_profile has root keys
            final_profile = json.load(f)
    else:
        print("No profile JSON found!")
        return

    # 4. Insert/Update DB
    # We ensure row with id=1 exists
    cursor.execute("INSERT OR REPLACE INTO profile (id, data) VALUES (1, ?)", (json.dumps(final_profile),))
    
    conn.commit()
    conn.close()
    print("Migration complete. Profile data saved to DB.")

if __name__ == "__main__":
    migrate()
