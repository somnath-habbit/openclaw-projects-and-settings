# Project: Intelligent LinkedIn Auto-Applier (Revised Architecture)

## 🎯 Objective
A fully autonomous agent that fetches user data via API, intelligently handles complex applications by asking the user for help (via Telegram), and dynamically generates ATS-optimized CVs based on real skills.

## 🏗 High-Level Architecture

The system is divided into four autonomous workers sharing a central database.

### 1. Data & Profile Manager (The "Brain")
*   **Input**: User Profile API (JSON).
*   **Function**:
    *   Fetches current User Profile (Skills, Experience, Education).
    *   Updates User Profile via API when new data is learned (from Telegram replies).
    *   **Database**: `user_profile_cache` (synced locally for speed).

### 2. Job Discovery & Triage Agent
*   **Function**: Scrapes LinkedIn for jobs.
*   **Logic**:
    *   Extracts Full JD text.
    *   **Feasibility Check**: Uses LLM to compare JD vs. User Profile.
        *   *Good Match?* -> Send to **CV Generator**.
        *   *Bad Match?* -> Discard.
    *   **Complexity Check**:
        *   *Easy Apply?* -> Queue for **Application Bot**.
        *   *External/Complex?* -> Queue for **Resolution Manager**.

### 3. Dynamic CV Generator (The "Writer")
*   **Trigger**: New "Feasible Job" found.
*   **Logic**:
    *   **Input**: JD Text + User Skills (JSON).
    *   **LLM Task**: "Rewrite the CV summary and bullet points to highlight skills X, Y, Z from the profile that match this JD. Do not hallucinate new skills."
    *   **Output**: Generates a clean Markdown file -> Converts to PDF (`Job_123_CV.pdf`).
    *   **Style**: Modern, ATS-friendly (clean layout, keyword-rich).

### 4. Application Bot (The "Doer")
*   **Function**: Executes the application on LinkedIn.
*   **Logic**:
    *   Uses the *specific* PDF generated for this job ID.
    *   Fills form fields.
    *   **Exception Handling**:
        *   *Field Missing (e.g., "Visa Status")?* -> Check local DB.
        *   *Still Missing?* -> **Pause & Escalate**.

### 5. Resolution & Notification Manager (The "Bridge")
*   **Function**: Handles "Stuck" applications.
*   **Logic**:
    *   Identifies missing data field (e.g., "Do you have a security clearance?").
    *   **Action**: Sends Telegram message: *"Job [Google - Senior Eng] asks: 'Do you have security clearance?'"*
    *   **User Reply**: *"No"*
    *   **Action**:
        1.  Updates Local DB (for this job).
        2.  Updates User API (permanently save "Security Clearance = No").
        3.  Resumes Application Bot.

## 🛠 Tech Stack
*   **Core**: Python 3.10+
*   **Browser**: OpenClaw Browser (Chrome Remote Debugging)
*   **Database**: SQLite (local state) + PostgreSQL (optional for scale)
*   **LLM**: Gemini Pro or GPT-4o (for JD analysis and CV writing)
*   **PDF Engine**: `WeasyPrint` or `ReportLab` (Markdown -> PDF)
*   **Notifications**: Telegram Bot API

## 📅 Revised Phased Rollout

### Phase 0: Initialization (Completed)
*   [x] Scrape LinkedIn Profile and create `data/user_profile.json`.
*   [x] Create project directory structure.

### Phase 1: Foundation (In Progress)
*   [ ] Build `job_search.py` to discover "Easy Apply" jobs.
*   Setup SQLite DB schema (`Jobs`, `UserProfile`, `PendingQuestions`).
*   Build **API Client** to fetch/update user profile.
*   Build **Telegram Bot** wrapper for sending/receiving messages.

### Phase 2: CV Generation Engine (Days 4-6)
*   Implement LLM prompt for JD matching.
*   Create the "Base CV" template (Jinja2 or Markdown).
*   Test PDF generation pipeline.

### Phase 3: The Application Loop (Days 7-10)
*   Connect `job_search.py` to the CV Engine.
*   Build the browser automation for "Easy Apply".
*   Implement the "Missing Info" exception catcher.

### Phase 4: Integration & Testing (Days 11+)
*   End-to-end test:
    1.  Fetch Profile.
    2.  Find Job.
    3.  Generate CV.
    4.  Hit "Apply".
    5.  Encounter unknown question -> Message Telegram -> User Reply -> Finish Apply.

## 💾 Database Schema Draft

**Table: Jobs**
*   `id` (PK)
*   `linkedin_id`
*   `jd_text`
*   `status` (NEW, GENERATING_CV, READY_TO_APPLY, BLOCKED_ON_USER, APPLIED)
*   `missing_info_field` (nullable)

**Table: UserProfile**
*   (Cached JSON from API)

**Table: GeneratedCVs**
*   `job_id` (FK)
*   `file_path`
