import sqlite3
from pathlib import Path

# Paths
VOICE_DB_PATH = Path("/home/somnath/.openclaw/workspace/Auto_job_application/data/voice_history.db")

def init_voice_db():
    conn = sqlite3.connect(VOICE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voice_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcription TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print(f"✅ Voice history database initialized at {VOICE_DB_PATH}")

if __name__ == "__main__":
    init_voice_db()
