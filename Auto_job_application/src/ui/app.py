from flask import Flask, render_template, request, redirect, url_for
from Auto_job_application.src.tools.database_tool import DatabaseManager
from pathlib import Path
import os

app = Flask(__name__)
db_path = Path("/home/somnath/.openclaw/workspace/Auto_job_application/data/autobot.db")
db = DatabaseManager(db_path)

@app.route('/')
def index():
    jobs = db.execute("SELECT * FROM jobs ORDER BY discovered_at DESC", fetch=True)
    return render_template('index.html', jobs=jobs)

@app.route('/edit_job/<int:job_id>', methods=['GET', 'POST'])
def edit_job(job_id):
    if request.method == 'POST':
        title = request.form['title']
        status = request.form['status']
        db.execute("UPDATE jobs SET title = ?, status = ? WHERE id = ?", (title, status, job_id))
        return redirect(url_for('index'))
    
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,), fetch=True)[0]
    return render_template('edit_job.html', job=job)

if __name__ == '__main__':
    # Running on a port accessible via OpenClaw browser/tunnel if needed
    app.run(host='0.0.0.0', port=5000, debug=True)
