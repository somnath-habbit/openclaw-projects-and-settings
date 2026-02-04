import sqlite3

from Auto_job_application.src.config.paths import db_path as project_db_path

DB_PATH = project_db_path()

JOB_COLUMNS = {
    "job_url": "TEXT",
    "apply_type": "TEXT",
    "about_job": "TEXT",
    "about_company": "TEXT",
    "compensation": "TEXT",
    "work_mode": "TEXT",
    "company_id": "INTEGER",
    "apply_attempts": "INTEGER DEFAULT 0",
    "last_attempt_at": "DATETIME",
    "last_apply_result": "TEXT",
    "enriched_at": "DATETIME",
}

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(jobs)")
    existing = {row[1] for row in cursor.fetchall()}

    for column, col_def in JOB_COLUMNS.items():
        if column not in existing:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {column} {col_def}")

    conn.commit()
    conn.close()
    print("Migration complete: jobs schema updated.")

if __name__ == "__main__":
    migrate()
