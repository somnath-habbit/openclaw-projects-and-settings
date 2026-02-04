import sqlite3

from Auto_job_application.src.config.paths import db_path as project_db_path

DB_PATH = project_db_path()

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Create scans table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        job_title TEXT,
        location TEXT,
        limit_requested INTEGER,
        found_count INTEGER,
        new_count INTEGER,
        status TEXT
    )
    """)
    
    # 2. Add columns to jobs if missing (discovered_at is already there based on app.py)
    # Check if 'source' exists, add if not
    cursor.execute("PRAGMA table_info(jobs)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'source' not in columns:
        cursor.execute("ALTER TABLE jobs ADD COLUMN source TEXT DEFAULT 'linkedin'")
        
    conn.commit()
    conn.close()
    print("Migration complete: 'scans' table created.")

if __name__ == "__main__":
    migrate()
