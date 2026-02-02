import json
import subprocess
import time
import re
from abc import ABC, abstractmethod
from pathlib import Path
from Auto_job_application.src.tools.database_tool import DatabaseManager

class BaseAgent(ABC):
    """Base class for all portal-specific agents."""
    def __init__(self, workspace_dir="/home/somnath/.openclaw/workspace/Auto_job_application"):
        self.workspace_dir = Path(workspace_dir)
        self.data_dir = self.workspace_dir / "data"
        self.db = DatabaseManager(self.data_dir / "autobot.db")
        self.browser_profile = "openclaw"

    def run_browser(self, cmd: list[str], timeout: int = 120) -> tuple[bool, str]:
        full_cmd = ["openclaw", "browser", "--browser-profile", self.browser_profile] + cmd
        try:
            result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0, result.stdout + result.stderr
        except Exception as e:
            return False, str(e)

class LinkedInAgent(BaseAgent):
    """Specific implementation for LinkedIn."""
    def search(self, keywords, location):
        url = f"https://www.linkedin.com/jobs/search/?keywords={keywords.replace(' ', '%20')}&location={location.replace(' ', '%20')}&f_AL=true"
        print(f"🌐 [LinkedIn] Opening: {url}")
        self.run_browser(["open", url])
        time.sleep(15)
        success, snapshot = self.run_browser(["snapshot", "--format", "aria"])
        return snapshot if success else None

    def parse_job_ids(self, snapshot_text):
        return list(dict.fromkeys(re.findall(r'/jobs/view/(\d+)', snapshot_text)))

class TriageEngine(BaseAgent):
    """Fit assessment and tailoring engine."""
    def __init__(self, profile_path=None):
        super().__init__()
        self.profile_path = profile_path or self.data_dir / "user_profile.json"
        with open(self.profile_path, 'r') as f:
            self.profile_data = json.load(f)

    def generate_triage_prompt(self, title, jd):
        return f"Evaluate fit for {self.profile_data['personal_info']['first_name']}...\nJob: {title}\nJD: {jd}"

    def generate_cover_letter_prompt(self, job_title, company, jd):
        """Generates a prompt for the sub-agent to write a tailored cover letter."""
        profile = self.profile_data.get('profile', self.profile_data.get('personal_info', {}))
        experiences = self.profile_data.get('experiences', self.profile_data.get('experience', []))
        skills = self.profile_data.get('skills', [])
        
        # Extract projects for deeper tailoring if available
        all_projects = []
        for exp in experiences:
            all_projects.extend(exp.get('projects', []))

        # Format skills for prompt
        if skills and isinstance(skills[0], dict):
            skill_names = [s['name'] for s in skills]
        else:
            skill_names = skills

        prompt = f"""
Write a professional, highly tailored cover letter for the following job application.
The letter should be concise (max 300 words), highlight matching skills, and sound enthusiastic but benevolent (Vision-like tone).

### JOB DETAILS
Company: {company or 'The Company'}
Title: {job_title}
Job Description: {jd[:2000]}

### CANDIDATE PROFILE
Name: {profile.get('name', f"{profile.get('first_name', '')} {profile.get('last_name', '')}")}
Current Role: {experiences[0].get('position', experiences[0].get('title', ''))} at {experiences[0].get('company', '')}
Key Skills: {', '.join(skill_names[:15])}
Relevant Projects: {json.dumps(all_projects[:5], indent=2)}

### INSTRUCTIONS
- Address it to "Hiring Manager" or the specific company.
- Select the 2 most relevant projects from the list above that match the job description.
- Focus on how the candidate's background in platform engineering and leadership solves the company's specific needs.
- Return ONLY the text of the cover letter.
"""
        return prompt
