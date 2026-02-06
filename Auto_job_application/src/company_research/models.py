"""
Database models for Company Research

Simple schema using SQLite through DatabaseManager
"""

def init_company_research_tables(db):
    """
    Initialize company research tables in the database

    Args:
        db: DatabaseManager instance from Auto_job_application.src.tools.database_tool
    """

    # Companies table
    db.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            domain TEXT,
            industry TEXT,
            headquarters TEXT,
            company_type TEXT CHECK(company_type IN ('startup', 'unicorn', 'public', 'acquired', 'unknown')),
            employee_count INTEGER,
            has_india_office BOOLEAN DEFAULT 0,
            india_offices TEXT,  -- JSON array
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Research Data table (stores raw data from collectors)
    db.execute("""
        CREATE TABLE IF NOT EXISTS research_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            source TEXT NOT NULL CHECK(source IN (
                'google_trends', 'glassdoor', 'stock_market',
                'crunchbase', 'linkedin', 'news'
            )),
            data_json TEXT NOT NULL,  -- JSON blob with collected data
            success BOOLEAN DEFAULT 1,
            error_message TEXT,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        )
    """)

    # Research Reports table
    db.execute("""
        CREATE TABLE IF NOT EXISTS research_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            overall_score REAL,
            india_fit_score REAL,
            recommendation TEXT CHECK(recommendation IN (
                'highly_recommended', 'recommended', 'moderate',
                'caution', 'not_recommended', 'insufficient_data'
            )),
            company_health_score REAL,
            employee_sentiment_score REAL,
            growth_trajectory_score REAL,
            compensation_score REAL,
            report_markdown TEXT NOT NULL,
            sources_used TEXT,  -- JSON array
            missing_sources TEXT,  -- JSON array
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        )
    """)

    # Indexes for better query performance
    db.execute("CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_research_data_company ON research_data(company_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_research_data_source ON research_data(source)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_research_reports_company ON research_reports(company_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_research_reports_generated ON research_reports(generated_at)")

    print("✅ Company research tables initialized")


def get_or_create_company(db, company_name: str) -> int:
    """
    Get existing company or create new one

    Args:
        db: DatabaseManager instance
        company_name: Name of the company

    Returns:
        company_id: ID of the company
    """
    # Check if exists
    result = db.execute(
        "SELECT id FROM companies WHERE name = ?",
        (company_name,),
        fetch=True
    )

    if result and len(result) > 0:
        return result[0][0]

    # Create new
    db.execute(
        "INSERT INTO companies (name) VALUES (?)",
        (company_name,)
    )

    # Get the ID
    result = db.execute(
        "SELECT id FROM companies WHERE name = ?",
        (company_name,),
        fetch=True
    )

    return result[0][0]


def save_research_data(db, company_id: int, source: str, data: dict, success: bool = True, error: str = None):
    """
    Save raw research data from a collector

    Args:
        db: DatabaseManager instance
        company_id: Company ID
        source: Data source name
        data: Dictionary of collected data
        success: Whether collection was successful
        error: Error message if failed
    """
    import json

    db.execute("""
        INSERT INTO research_data (company_id, source, data_json, success, error_message)
        VALUES (?, ?, ?, ?, ?)
    """, (company_id, source, json.dumps(data), 1 if success else 0, error))


def save_research_report(db, company_id: int, report_data: dict):
    """
    Save generated research report

    Args:
        db: DatabaseManager instance
        company_id: Company ID
        report_data: Dictionary with all report data
    """
    import json

    db.execute("""
        INSERT INTO research_reports (
            company_id, overall_score, india_fit_score, recommendation,
            company_health_score, employee_sentiment_score,
            growth_trajectory_score, compensation_score,
            report_markdown, sources_used, missing_sources
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_id,
        report_data.get('overall_score'),
        report_data.get('india_fit_score'),
        report_data.get('recommendation'),
        report_data.get('company_health_score'),
        report_data.get('employee_sentiment_score'),
        report_data.get('growth_trajectory_score'),
        report_data.get('compensation_score'),
        report_data.get('report_markdown'),
        json.dumps(report_data.get('sources_used', [])),
        json.dumps(report_data.get('missing_sources', []))
    ))


def get_latest_report(db, company_id: int) -> dict:
    """
    Get the most recent research report for a company

    Args:
        db: DatabaseManager instance
        company_id: Company ID

    Returns:
        dict: Report data or None
    """
    result = db.execute("""
        SELECT id, overall_score, india_fit_score, recommendation,
               company_health_score, employee_sentiment_score,
               growth_trajectory_score, compensation_score,
               report_markdown, generated_at
        FROM research_reports
        WHERE company_id = ?
        ORDER BY generated_at DESC
        LIMIT 1
    """, (company_id,), fetch=True)

    if not result or len(result) == 0:
        return None

    row = result[0]
    return {
        'id': row[0],
        'overall_score': row[1],
        'india_fit_score': row[2],
        'recommendation': row[3],
        'company_health_score': row[4],
        'employee_sentiment_score': row[5],
        'growth_trajectory_score': row[6],
        'compensation_score': row[7],
        'report_markdown': row[8],
        'generated_at': row[9]
    }


def get_all_researched_companies(db) -> list:
    """
    Get all companies that have been researched

    Args:
        db: DatabaseManager instance

    Returns:
        list: List of (company_id, company_name, latest_score, latest_date) tuples
    """
    result = db.execute("""
        SELECT
            c.id,
            c.name,
            r.overall_score,
            r.generated_at
        FROM companies c
        LEFT JOIN research_reports r ON c.id = r.company_id
        WHERE r.id IN (
            SELECT MAX(id)
            FROM research_reports
            GROUP BY company_id
        )
        OR r.id IS NULL
        ORDER BY r.generated_at DESC
    """, fetch=True)

    return result if result else []
