from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from Auto_job_application.src.tools.database_tool import DatabaseManager
from pathlib import Path
import json

app = Flask(__name__)

# Paths
BASE_DIR = Path("/home/somnath/.openclaw/workspace/Auto_job_application")
DB_PATH = BASE_DIR / "data" / "autobot.db"
PROFILE_PATH = BASE_DIR / "data" / "user_profile.json"
TEMPLATES_DIR = BASE_DIR / "src" / "ui" / "templates"

db = DatabaseManager(DB_PATH)

def get_profile():
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH, 'r') as f:
            return json.load(f)
    return {}

@app.route('/')
def index():
    jobs = db.execute("SELECT * FROM jobs ORDER BY fit_score DESC, discovered_at DESC", fetch=True)
    return render_template('index.html', jobs=jobs)

@app.route('/db')
def db_viewer():
    """Raw DB Viewer and Editor."""
    jobs = db.execute("SELECT * FROM jobs", fetch=True)
    return render_template('db_viewer.html', jobs=jobs)

@app.route('/edit_job/<int:job_id>', methods=['GET', 'POST'])
def edit_job(job_id):
    if request.method == 'POST':
        title = request.form.get('title')
        status = request.form.get('status')
        jd_text = request.form.get('jd_text')
        db.execute("UPDATE jobs SET title = ?, status = ?, jd_text = ? WHERE id = ?", (title, status, jd_text, job_id))
        return redirect(url_for('index'))
    
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch=True)[0]
    return render_template('edit_job.html', job=job)

@app.route('/resume_preview/<int:job_id>')
def resume_preview(job_id):
    """Preview the tailored resume for a specific job."""
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch=True)[0]
    profile = get_profile()
    
    # Placeholder for tailoring logic - currently shows base profile
    # Later, this will fetch the LLM-tailored version from the DB
    return render_template('resume_templates/modern_ats.html', job=job, profile=profile)

@app.route('/profile', methods=['GET', 'POST'])
def profile_editor():
    """Edit the base user profile."""
    if request.method == 'POST':
        # Simple implementation for now
        new_profile = request.form.get('profile_json')
        with open(PROFILE_PATH, 'w') as f:
            f.write(new_profile)
        return redirect(url_for('index'))
    
    profile = get_profile()
    return render_template('profile_editor.html', profile_json=json.dumps(profile, indent=2))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
