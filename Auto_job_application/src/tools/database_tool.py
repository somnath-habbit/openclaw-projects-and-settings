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

    def _get_columns(self, table_name: str) -> set[str]:
        rows = self.execute(f"PRAGMA table_info({table_name})", fetch=True)
        return {row[1] for row in rows}

    def _ensure_column(self, table_name: str, column_name: str, column_def: str):
        columns = self._get_columns(table_name)
        if column_name not in columns:
            self.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")

    def upsert_company(self, name: str, linkedin_url: str | None = None, about: str | None = None, website: str | None = None,
                       industry: str | None = None, size: str | None = None, headquarters: str | None = None,
                       specialties: str | None = None) -> int | None:
        if not name:
            return None
        self.execute(
            """
            INSERT INTO companies (name, linkedin_url, about, website, industry, size, headquarters, specialties)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                linkedin_url = COALESCE(excluded.linkedin_url, companies.linkedin_url),
                about = COALESCE(excluded.about, companies.about),
                website = COALESCE(excluded.website, companies.website),
                industry = COALESCE(excluded.industry, companies.industry),
                size = COALESCE(excluded.size, companies.size),
                headquarters = COALESCE(excluded.headquarters, companies.headquarters),
                specialties = COALESCE(excluded.specialties, companies.specialties),
                updated_at = CURRENT_TIMESTAMP
            """,
            (name, linkedin_url, about, website, industry, size, headquarters, specialties),
        )
        row = self.execute("SELECT id FROM companies WHERE name = ?", (name,), fetch=True)
        return row[0][0] if row else None

    def initialize_schema(self):
        """Initializes the generic jobs, companies, and interactions tables."""
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
                cover_letter TEXT,
                cover_letter_path TEXT,
                resume_json TEXT,
                tailored_resume_json TEXT,
                apply_attempts INTEGER DEFAULT 0,
                last_attempt_at DATETIME,
                last_apply_result TEXT,
                enriched_at DATETIME,
                discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.execute('''
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                linkedin_url TEXT,
                about TEXT,
                website TEXT,
                industry TEXT,
                size TEXT,
                headquarters TEXT,
                specialties TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.execute('''
            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT,
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
        self.execute('''
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
        ''')
        self._ensure_column("jobs", "company_id", "INTEGER")
        self._ensure_column("jobs", "about_job", "TEXT")
        self._ensure_column("jobs", "about_company", "TEXT")
        self._ensure_column("jobs", "compensation", "TEXT")
        self._ensure_column("jobs", "work_mode", "TEXT")
        self._ensure_column("jobs", "apply_type", "TEXT")
        self._ensure_column("jobs", "job_url", "TEXT")
        self._ensure_column("jobs", "apply_attempts", "INTEGER DEFAULT 0")
        self._ensure_column("jobs", "last_attempt_at", "DATETIME")
        self._ensure_column("jobs", "last_apply_result", "TEXT")
        self._ensure_column("jobs", "enriched_at", "DATETIME")
        self._ensure_column("jobs", "enrich_status", "TEXT")
        self._ensure_column("jobs", "last_enrich_error", "TEXT")
        print(f"✅ Database initialized at {self.db_path}")
