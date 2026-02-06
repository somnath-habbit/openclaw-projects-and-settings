"""
Research Orchestrator

Coordinates the entire research workflow
"""

from .collectors import GoogleTrendsCollector, GlassdoorCollector, StockDataCollector
from .scorers import OverallScorer, IndiaFitScorer
from .report_generator import ReportGenerator
from .models import (
    get_or_create_company,
    save_research_data,
    save_research_report,
    get_latest_report
)


class ResearchOrchestrator:
    """Coordinates company research workflow"""

    def __init__(self, db):
        """
        Initialize orchestrator

        Args:
            db: DatabaseManager instance
        """
        self.db = db
        self.collectors = {
            'google_trends': GoogleTrendsCollector(),
            'glassdoor': GlassdoorCollector(),
            'stock_market': StockDataCollector()
        }
        self.overall_scorer = OverallScorer()
        self.india_scorer = IndiaFitScorer()
        self.report_generator = ReportGenerator()

    def research_company(self, company_name: str, offer_details: dict = None,
                        enabled_sources: list = None,
                        progress_callback=None) -> dict:
        """
        Perform complete company research

        Args:
            company_name: Name of the company
            offer_details: Optional salary information
            enabled_sources: List of sources to use (default: all)
            progress_callback: Function to call with progress updates

        Returns:
            dict: Complete research results with report
        """
        if progress_callback:
            progress_callback(f"Starting research for {company_name}...", 0)

        # Get or create company
        company_id = get_or_create_company(self.db, company_name)

        # Determine which sources to use
        if enabled_sources is None:
            enabled_sources = list(self.collectors.keys())

        # Collect data from all sources
        collected_data = {}
        total_sources = len(enabled_sources)

        for i, source in enumerate(enabled_sources):
            if source not in self.collectors:
                continue

            progress_pct = (i / total_sources) * 0.7  # 0-70% for collection

            if progress_callback:
                progress_callback(f"Collecting from {source}...", progress_pct)

            collector = self.collectors[source]
            result = collector.collect(company_name, progress_callback)

            collected_data[source] = result

            # Save to database
            save_research_data(
                self.db,
                company_id,
                source,
                result.get('data', {}),
                result.get('success', False),
                result.get('error')
            )

        # Calculate scores
        if progress_callback:
            progress_callback("Analyzing data and calculating scores...", 0.75)

        overall_scores = self.overall_scorer.calculate(collected_data, offer_details)
        india_fit_scores = self.india_scorer.calculate(collected_data)

        # Generate report
        if progress_callback:
            progress_callback("Generating report...", 0.90)

        report_markdown = self.report_generator.generate_markdown(
            company_name,
            collected_data,
            overall_scores,
            india_fit_scores
        )

        # Save report to database
        report_data = {
            'overall_score': overall_scores.get('overall_score'),
            'india_fit_score': india_fit_scores.get('india_fit_score'),
            'recommendation': overall_scores.get('recommendation'),
            'company_health_score': overall_scores.get('company_health_score'),
            'employee_sentiment_score': overall_scores.get('employee_sentiment_score'),
            'growth_trajectory_score': overall_scores.get('growth_trajectory_score'),
            'compensation_score': overall_scores.get('compensation_score'),
            'report_markdown': report_markdown,
            'sources_used': [s for s in enabled_sources if collected_data.get(s, {}).get('success')],
            'missing_sources': [s for s in enabled_sources if not collected_data.get(s, {}).get('success')]
        }

        save_research_report(self.db, company_id, report_data)

        if progress_callback:
            progress_callback("Research complete!", 1.0)

        # Return complete results
        return {
            'company_id': company_id,
            'company_name': company_name,
            'overall_score': overall_scores.get('overall_score'),
            'india_fit_score': india_fit_scores.get('india_fit_score'),
            'recommendation': overall_scores.get('recommendation'),
            'india_recommendation': india_fit_scores.get('india_recommendation'),
            'report_markdown': report_markdown,
            'collected_data': collected_data,
            'all_scores': {
                **overall_scores,
                **india_fit_scores
            }
        }

    def get_company_report(self, company_id: int) -> dict:
        """
        Get latest report for a company

        Args:
            company_id: Company ID

        Returns:
            dict: Report data or None
        """
        return get_latest_report(self.db, company_id)
