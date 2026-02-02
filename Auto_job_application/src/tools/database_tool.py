import sqlite3
from pathlib import Path

class DatabaseManager:
    """A generic SQLite manager for job discovery projects."""
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def execute(self, query, params=(), commit=True, fetch=False):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            if commit: conn.commit()
            if fetch: return cursor.fetchall()
            return cursor.rowcount
        finally:
            conn.close()

    def initialize_schema(self):
        """Initializes the generic jobs and interactions tables."""
        self.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL,
                title TEXT,
                company TEXT,
                location TEXT,
                jd_text TEXT,
                url TEXT,
                status TEXT DEFAULT 'NEW',
                fit_score INTEGER,
                fit_reasoning TEXT,
                cv_path TEXT,
                discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.execute('''
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                question TEXT,
                answer TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        ''')
        print(f"✅ Database initialized at {self.db_path}")
