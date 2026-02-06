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


# ========== Q&A Management for Easy Apply ==========

@app.route('/qa')
def qa_manager():
    """View and manage common Q&A for job applications."""
    type_filter = request.args.get('type', 'all')

    if type_filter == 'all':
        responses = db.execute(
            "SELECT id, question_text, question_type, response, reuse_count, created_at FROM question_responses ORDER BY question_type, question_text",
            fetch=True
        )
    else:
        responses = db.execute(
            "SELECT id, question_text, question_type, response, reuse_count, created_at FROM question_responses WHERE question_type = ? ORDER BY question_text",
            (type_filter,),
            fetch=True
        )

    # Get unique question types for filter
    types = db.execute("SELECT DISTINCT question_type FROM question_responses ORDER BY question_type", fetch=True)
    types = [t[0] for t in types] if types else []

    return render_template('qa_manager.html', responses=responses, types=types, type_filter=type_filter)


@app.route('/qa/add', methods=['POST'])
def qa_add():
    """Add a new Q&A entry."""
    import re

    question = request.form.get('question', '').strip()
    answer = request.form.get('answer', '').strip()
    q_type = request.form.get('type', 'general')

    if question and answer:
        # Create normalized hash
        question_hash = re.sub(r'[^\w\s]', '', question.lower())
        question_hash = ' '.join(question_hash.split())

        db.execute(
            "INSERT OR REPLACE INTO question_responses (question_hash, question_text, question_type, response) VALUES (?, ?, ?, ?)",
            (question_hash, question, q_type, answer)
        )

    return redirect(url_for('qa_manager'))


@app.route('/qa/edit/<int:qa_id>', methods=['POST'])
def qa_edit(qa_id):
    """Edit an existing Q&A entry."""
    answer = request.form.get('answer', '').strip()
    q_type = request.form.get('type', 'general')

    if answer:
        db.execute(
            "UPDATE question_responses SET response = ?, question_type = ? WHERE id = ?",
            (answer, q_type, qa_id)
        )

    return redirect(url_for('qa_manager'))


@app.route('/qa/delete/<int:qa_id>', methods=['POST'])
def qa_delete(qa_id):
    """Delete a Q&A entry."""
    db.execute("DELETE FROM question_responses WHERE id = ?", (qa_id,))
    return redirect(url_for('qa_manager'))


@app.route('/qa/bulk_update', methods=['POST'])
def qa_bulk_update():
    """Bulk update common fields (CTC, notice period, etc.)."""
    current_ctc = request.form.get('current_ctc', '').strip()
    expected_ctc = request.form.get('expected_ctc', '').strip()
    notice_period = request.form.get('notice_period', '').strip()

    if current_ctc:
        # Update all current CTC related questions
        db.execute(
            "UPDATE question_responses SET response = ? WHERE question_text LIKE '%Current%CTC%' OR question_text LIKE '%current ctc%'",
            (current_ctc,)
        )

    if expected_ctc:
        # Update all expected CTC related questions
        db.execute(
            "UPDATE question_responses SET response = ? WHERE question_text LIKE '%expected%CTC%' OR question_text LIKE '%Expected%CTC%' OR question_text LIKE '%expected salary%'",
            (expected_ctc,)
        )

    if notice_period:
        # Update all notice period related questions
        db.execute(
            "UPDATE question_responses SET response = ? WHERE question_type = 'notice_period' OR question_text LIKE '%notice%'",
            (notice_period,)
        )

    return redirect(url_for('qa_manager'))


# ========== Company Research Module ==========

from Auto_job_application.src.company_research.orchestrator import ResearchOrchestrator
from Auto_job_application.src.company_research.models import (
    init_company_research_tables,
    get_all_researched_companies,
    get_latest_report,
    get_or_create_company
)
import threading
import uuid

# Initialize company research tables
try:
    init_company_research_tables(db)
except Exception as e:
    print(f"Company research tables already exist or error: {e}")

# Active research tasks (in-memory storage for progress tracking)
active_research_tasks = {}


@app.route('/company-research')
def company_research():
    """Main company research page"""

    # Get companies from researched history
    researched_companies = get_all_researched_companies(db)

    # Get jobs in offer/final stage
    offers = db.execute("""
        SELECT id, title, company, status, discovered_at
        FROM jobs
        WHERE status IN ('OFFER', 'FINAL_INTERVIEW', 'OFFER_RECEIVED')
        ORDER BY discovered_at DESC
    """, fetch=True)

    return render_template('company_research/index.html',
                          offers=offers or [],
                          researched=researched_companies or [])


@app.route('/company-research/research', methods=['GET', 'POST'])
def company_research_form():
    """Research form and execution"""

    if request.method == 'GET':
        company_name = request.args.get('company', '')
        return render_template('company_research/research_form.html',
                              company_name=company_name)

    # POST - Start research
    company_name = request.form.get('company_name')

    # Offer details (optional)
    offer_details = None
    if request.form.get('base_salary'):
        base = float(request.form.get('base_salary', 0))
        bonus = float(request.form.get('bonus', 0))
        equity = float(request.form.get('equity', 0))
        offer_details = {
            'total_compensation': base + bonus + equity,
            'base_salary': base,
            'bonus': bonus,
            'equity': equity
        }

    # Sources to use
    enabled_sources = request.form.getlist('sources')
    if not enabled_sources:
        enabled_sources = ['google_trends', 'glassdoor', 'stock_market']

    # Generate task ID
    task_id = str(uuid.uuid4())

    # Start research in background
    def run_research():
        orchestrator = ResearchOrchestrator(db)

        def progress_callback(message, progress):
            if task_id in active_research_tasks:
                active_research_tasks[task_id]['progress'] = progress
                active_research_tasks[task_id]['message'] = message

        try:
            result = orchestrator.research_company(
                company_name=company_name,
                offer_details=offer_details,
                enabled_sources=enabled_sources,
                progress_callback=progress_callback
            )

            active_research_tasks[task_id]['status'] = 'complete'
            active_research_tasks[task_id]['result'] = result
            active_research_tasks[task_id]['company_id'] = result['company_id']

        except Exception as e:
            active_research_tasks[task_id]['status'] = 'error'
            active_research_tasks[task_id]['error'] = str(e)

    # Initialize task
    active_research_tasks[task_id] = {
        'status': 'running',
        'progress': 0.0,
        'message': 'Starting research...',
        'company_name': company_name
    }

    # Start thread
    thread = threading.Thread(target=run_research)
    thread.daemon = True
    thread.start()

    # Redirect to progress page
    return redirect(url_for('company_research_progress', task_id=task_id))


@app.route('/company-research/progress/<task_id>')
def company_research_progress(task_id):
    """Progress tracking page"""

    if task_id not in active_research_tasks:
        return "Task not found", 404

    task = active_research_tasks[task_id]

    return render_template('company_research/progress.html',
                          task_id=task_id,
                          company_name=task.get('company_name'))


@app.route('/company-research/api/progress/<task_id>')
def company_research_api_progress(task_id):
    """API endpoint for progress updates"""

    if task_id not in active_research_tasks:
        return jsonify({'error': 'Task not found'}), 404

    task = active_research_tasks[task_id]

    response = {
        'status': task['status'],
        'progress': task.get('progress', 0),
        'message': task.get('message', ''),
        'company_id': task.get('company_id')
    }

    if task['status'] == 'error':
        response['error'] = task.get('error', 'Unknown error')

    return jsonify(response)


@app.route('/company-research/report/<int:company_id>')
def company_research_report(company_id):
    """Display research report"""

    # Get company info
    company = db.execute(
        "SELECT name FROM companies WHERE id = ?",
        (company_id,),
        fetch=True
    )

    if not company or len(company) == 0:
        return "Company not found", 404

    company_name = company[0][0]

    # Get latest report
    report = get_latest_report(db, company_id)

    if not report:
        return "No report found for this company", 404

    return render_template('company_research/report.html',
                          company_name=company_name,
                          company_id=company_id,
                          report=report)


@app.route('/company-research/compare', methods=['GET', 'POST'])
def company_research_compare():
    """Compare multiple companies"""

    if request.method == 'GET':
        # Show selection form
        companies = get_all_researched_companies(db)
        return render_template('company_research/compare.html',
                              companies=companies or [])

    # POST - Generate comparison
    company_ids = request.form.getlist('company_ids')

    if len(company_ids) < 2:
        return "Please select at least 2 companies to compare", 400

    # Get reports for all companies
    reports = []
    for company_id in company_ids:
        company = db.execute(
            "SELECT name FROM companies WHERE id = ?",
            (int(company_id),),
            fetch=True
        )

        if company and len(company) > 0:
            report = get_latest_report(db, int(company_id))
            if report:
                report['company_name'] = company[0][0]
                reports.append(report)

    return render_template('company_research/comparison.html',
                          reports=reports)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
