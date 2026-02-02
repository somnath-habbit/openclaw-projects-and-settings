from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from Auto_job_application.src.tools.database_tool import DatabaseManager
from pathlib import Path
import json
import subprocess

app = Flask(__name__)

# Paths
BASE_DIR = Path("/home/somnath/.openclaw/workspace/Auto_job_application")
DB_PATH = BASE_DIR / "data" / "autobot.db"
PROFILE_PATH = BASE_DIR / "data" / "user_profile.json"
RESUME_DIR = BASE_DIR / "data" / "resumes"
RESUME_DIR.mkdir(exist_ok=True)

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
    jobs = db.execute("SELECT * FROM jobs", fetch=True)
    return render_template('db_viewer.html', jobs=jobs)

@app.route('/edit_job/<int:job_id>', methods=['GET', 'POST'])
def edit_job(job_id):
    if request.method == 'POST':
        title = request.form.get('title')
        status = request.form.get('status')
        jd_text = request.form.get('jd_text')
        cover_letter = request.form.get('cover_letter')
        db.execute("UPDATE jobs SET title = ?, status = ?, jd_text = ?, cover_letter = ? WHERE id = ?", 
                   (title, status, jd_text, cover_letter, job_id))
        return redirect(url_for('index'))
    
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch=True)[0]
    return render_template('edit_job.html', job=job)

@app.route('/resume_preview/<int:job_id>')
def resume_preview(job_id):
    template_name = request.args.get('template', 'modern_ats')
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch=True)[0]
    profile = get_profile()
    return render_template(f'resume_templates/{template_name}.html', job=job, profile=profile, preview_mode=True)

@app.route('/cover_letter/<int:job_id>')
def cover_letter_preview(job_id):
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch=True)[0]
    return render_template('cover_letter.html', job=job)

@app.route('/generate_pdf/<int:job_id>', methods=['POST'])
def generate_pdf(job_id):
    template_name = request.form.get('template', 'modern_ats')
    url = f"http://localhost:5000/resume_preview/{job_id}?template={template_name}"
    pdf_filename = f"resume_job_{job_id}.pdf"
    target_path = RESUME_DIR / pdf_filename
    
    subprocess.run(["openclaw", "browser", "open", url])
    import time
    time.sleep(3)
    subprocess.run(["openclaw", "browser", "pdf", "--path", str(target_path)])
    
    db.execute("UPDATE jobs SET cv_path = ? WHERE id = ?", (str(target_path), job_id))
    return jsonify({"status": "success", "path": str(target_path)})

@app.route('/profile', methods=['GET', 'POST'])
def profile_editor():
    if request.method == 'POST':
        new_profile = request.form.get('profile_json')
        with open(PROFILE_PATH, 'w') as f:
            f.write(new_profile)
        return redirect(url_for('index'))
    
    profile = get_profile()
    return render_template('profile_editor.html', profile_json=json.dumps(profile, indent=2))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
