from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from Auto_job_application.src.tools.database_tool import DatabaseManager
from Auto_job_application.src.config.paths import db_path, profile_path, resumes_dir, master_pdf_path, openclaw_bin
import json
import subprocess

app = Flask(__name__)

# Paths
DB_PATH = db_path()
PROFILE_PATH = profile_path()
RESUME_DIR = resumes_dir()
RESUME_DIR.mkdir(parents=True, exist_ok=True)
MASTER_PDF_PATH = master_pdf_path()
OPENCLAW_BIN = openclaw_bin()

db = DatabaseManager(DB_PATH)

@app.template_filter('from_json')
def from_json_filter(s):
    return json.loads(s) if s else None

def get_profile_from_db():
    try:
        row = db.execute("SELECT data FROM profile WHERE id = 1", fetch=True)
        if row and row[0]:
            return json.loads(row[0][0])
    except Exception as e:
        print(f"Error loading profile from DB: {e}")
    return {}

@app.route('/')
def index():
    # Pagination & Sorting
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    sort_by = request.args.get('sort', 'latest') # latest, fit, applied, pending
    status_filter = request.args.get('status', 'all')
    
    offset = (page - 1) * per_page
    
    # Base query
    query = "SELECT * FROM jobs WHERE 1=1"
    params = []
    
    if status_filter != 'all':
        query += " AND status = ?"
        params.append(status_filter)
        
    # Order mapping
    if sort_by == 'fit':
        query += " ORDER BY fit_score DESC, discovered_at DESC"
    elif sort_by == 'applied':
        query += " ORDER BY (CASE WHEN status='APPLIED' THEN 0 ELSE 1 END), discovered_at DESC"
    elif sort_by == 'pending':
        query += " ORDER BY (CASE WHEN status='NEW' THEN 0 ELSE 1 END), discovered_at DESC"
    else: # latest
        query += " ORDER BY discovered_at DESC"
        
    # Get total count for pagination
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total_count = db.execute(count_query, tuple(params), fetch=True)[0][0]
    
    # Add limit/offset
    query += " LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    
    jobs = db.execute(query, tuple(params), fetch=True)
    
    # Stats
    stats = {
        "total": db.execute("SELECT COUNT(*) FROM jobs", fetch=True)[0][0],
        "applied": db.execute("SELECT COUNT(*) FROM jobs WHERE status = 'APPLIED'", fetch=True)[0][0],
        "pending": db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('NEW', 'PENDING_TAILORING', 'PENDING_GENERATION')", fetch=True)[0][0],
        "blocked": db.execute("SELECT COUNT(*) FROM jobs WHERE status = 'BLOCKED'", fetch=True)[0][0]
    }
    
    return render_template('index.html', 
                           jobs=jobs, 
                           stats=stats, 
                           page=page, 
                           per_page=per_page, 
                           total_pages=(total_count // per_page) + (1 if total_count % per_page > 0 else 0),
                           sort_by=sort_by,
                           status_filter=status_filter)

@app.route('/reports')
def reports():
    scans = db.execute("SELECT * FROM scans ORDER BY timestamp DESC LIMIT 50", fetch=True)
    return render_template('reports.html', scans=scans)

@app.route('/db')
def db_viewer():
    jobs = db.execute("SELECT * FROM jobs", fetch=True)
    return render_template('db_viewer.html', jobs=jobs)

@app.route('/view_master_pdf')
def view_master_pdf():
    if MASTER_PDF_PATH.exists():
        return send_from_directory(MASTER_PDF_PATH.parent, MASTER_PDF_PATH.name)
    else:
        return "Master Resume PDF not found. Please ensure 'Somnath_Ghosh_Resume_Master.pdf' is in the data directory.", 404

@app.route('/edit_status/<int:job_id>', methods=['GET', 'POST'])
def edit_status(job_id):
    if request.method == 'POST':
        status = request.form.get('status')
        db.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
        return redirect(url_for('index'))
    
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch=True)[0]
    return render_template('edit_status.html', job=job)

@app.route('/bulk_status_update', methods=['POST'])
def bulk_status_update():
    status = request.form.get('status')
    job_ids = request.form.getlist('job_ids')
    
    if status and job_ids:
        for job_id in job_ids:
            db.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
            
    return redirect(url_for('index'))

@app.route('/edit_cover_letter/<int:job_id>', methods=['GET', 'POST'])
def edit_cover_letter(job_id):
    if request.method == 'POST':
        cover_letter = request.form.get('cover_letter')
        db.execute("UPDATE jobs SET cover_letter = ? WHERE id = ?", 
                   (cover_letter, job_id))
        return redirect(url_for('index'))
    
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch=True)[0]
    return render_template('edit_cover_letter.html', job=job)

@app.route('/save_resume', methods=['POST'])
def save_resume():
    data = request.json
    resume_type = data.get('type') # 'master' or 'tailored'
    job_id = data.get('job_id')
    resume_data = data.get('data') # dict
    
    if resume_type == 'master':
        # Update Profile DB
        db.execute("UPDATE profile SET data = ? WHERE id = 1", (json.dumps(resume_data),))
        return jsonify({"status": "success", "msg": "Master Resume Updated"})
        
    elif resume_type == 'tailored' and job_id:
        # Update Job DB
        db.execute("UPDATE jobs SET resume_json = ? WHERE id = ?", (json.dumps(resume_data), job_id))
        return jsonify({"status": "success", "msg": "Tailored Resume Saved"})
        
    return jsonify({"status": "error", "msg": "Invalid Request"}), 400

@app.route('/voice_logs')
def voice_logs():
    logs = db.execute("SELECT * FROM voice_logs ORDER BY timestamp DESC", fetch=True)
    return render_template('voice_logs.html', logs=logs)

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
    profile = get_profile_from_db()
    return render_template(f'resume_templates/{template_name}.html', job=job, profile=profile, preview_mode=True)

@app.route('/resume_editor/<int:job_id>')
def resume_editor(job_id):
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch=True)[0]
    master_profile = get_profile_from_db()
    return render_template('resume_editor.html', job=job, master_profile=master_profile)

@app.route('/cover_letter/<int:job_id>')
def cover_letter_preview(job_id):
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch=True)[0]
    return render_template('cover_letter.html', job=job)

@app.route('/trigger_letter/<int:job_id>', methods=['POST'])
def trigger_letter(job_id):
    db.execute("UPDATE jobs SET cover_letter = 'PENDING_GENERATION' WHERE id = ?", (job_id,))
    return redirect(url_for('index'))

@app.route('/trigger_tailor_resume/<int:job_id>', methods=['POST'])
def trigger_tailor_resume(job_id):
    db.execute("UPDATE jobs SET tailored_resume_json = 'PENDING_TAILORING' WHERE id = ?", (job_id,))
    return redirect(url_for('index'))

@app.route('/generate_pdf/<int:job_id>', methods=['POST'])
def generate_pdf(job_id):
    template_name = request.form.get('template', 'modern_ats')
    url = f"http://localhost:5000/resume_preview/{job_id}?template={template_name}"
    pdf_filename = f"resume_job_{job_id}.pdf"
    target_path = RESUME_DIR / pdf_filename
    subprocess.run([OPENCLAW_BIN, "browser", "open", url])
    import time
    time.sleep(3)
    subprocess.run([OPENCLAW_BIN, "browser", "pdf", "--path", str(target_path)])
    db.execute("UPDATE jobs SET cv_path = ? WHERE id = ?", (str(target_path), job_id))
    return jsonify({"status": "success", "path": str(target_path)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
