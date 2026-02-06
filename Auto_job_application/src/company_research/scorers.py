"""
Scoring Algorithms for Company Research

Calculates overall score, India fit, and component scores
"""


class OverallScorer:
    """Calculate overall company score (0-100)"""

    def __init__(self):
        self.weights = {
            'company_health': 0.30,
            'employee_sentiment': 0.30,
            'growth_trajectory': 0.20,
            'compensation': 0.20
        }

    def calculate(self, collected_data: dict, offer_details: dict = None) -> dict:
        """
        Calculate overall score and component scores

        Args:
            collected_data: Data from all collectors
            offer_details: Optional salary info for compensation scoring

        Returns:
            dict: Scores and recommendation
        """
        # Calculate component scores
        components = {
            'company_health': self._score_company_health(collected_data),
            'employee_sentiment': self._score_employee_sentiment(collected_data),
            'growth_trajectory': self._score_growth_trajectory(collected_data),
            'compensation': self._score_compensation(offer_details) if offer_details else None
        }

        # Filter out None values
        available = {k: v for k, v in components.items() if v is not None}

        if not available:
            return {
                'overall_score': None,
                'recommendation': 'insufficient_data',
                'confidence': 0.0,
                **components
            }

        # Normalize weights for available data
        total_weight = sum(self.weights[k] for k in available.keys())
        normalized_weights = {k: self.weights[k] / total_weight for k in available.keys()}

        # Calculate weighted score
        overall = sum(available[k] * normalized_weights[k] for k in available.keys())

        # Generate recommendation
        recommendation = self._generate_recommendation(overall)

        # Calculate confidence
        confidence = len(available) / len(self.weights)

        return {
            'overall_score': round(overall, 1),
            'recommendation': recommendation,
            'confidence': round(confidence, 2),
            **components
        }

    def _score_company_health(self, data: dict) -> float:
        """Score based on company health indicators"""
        score = 50  # Base score

        # Stock data (for public companies)
        stock_data = data.get('stock_market', {}).get('data', {})
        if stock_data.get('status') == 'public_company':
            # Performance score
            perf_1yr = stock_data.get('performance_1yr', 0)
            if perf_1yr:
                if perf_1yr > 30:
                    score += 30
                elif perf_1yr > 10:
                    score += 20
                elif perf_1yr > 0:
                    score += 10
                else:
                    score += 5

            # Profitability
            if stock_data.get('profitable'):
                score += 20

        # Trends data (brand health)
        trends_data = data.get('google_trends', {}).get('data', {})
        india_interest = trends_data.get('india_interest_avg', 0)
        if india_interest > 70:
            score += 20
        elif india_interest > 40:
            score += 10
        elif india_interest > 10:
            score += 5

        return min(score, 100)

    def _score_employee_sentiment(self, data: dict) -> float:
        """Score based on employee reviews and ratings"""
        glassdoor_data = data.get('glassdoor', {}).get('data', {})

        rating = glassdoor_data.get('overall_rating')
        if rating is None:
            return None  # No data

        # Convert 1-5 rating to 0-100 score
        score = (rating - 1.0) / 4.0 * 100

        # Bonus for high CEO approval
        ceo_approval = glassdoor_data.get('ceo_approval')
        if ceo_approval:
            if ceo_approval >= 90:
                score += 10
            elif ceo_approval >= 80:
                score += 5

        # Bonus for high recommendation rate
        recommend = glassdoor_data.get('recommend_to_friend')
        if recommend:
            if recommend >= 80:
                score += 10
            elif recommend >= 70:
                score += 5

        return min(score, 100)

    def _score_growth_trajectory(self, data: dict) -> float:
        """Score based on growth indicators"""
        score = 50  # Base

        # Trend direction
        trends_data = data.get('google_trends', {}).get('data', {})
        direction = trends_data.get('trend_direction', 'stable')

        if direction == 'rising':
            score += 30
        elif direction == 'stable':
            score += 10
        else:  # falling
            score -= 10

        # High absolute interest indicates market presence
        india_interest = trends_data.get('india_interest_avg', 0)
        if india_interest >= 70:
            score += 20
        elif india_interest >= 40:
            score += 10

        return max(min(score, 100), 0)

    def _score_compensation(self, offer_details: dict) -> float:
        """Score compensation offer (if provided)"""
        if not offer_details:
            return None

        total_comp = offer_details.get('total_compensation', 0)

        # Simple scoring based on total compensation
        # Adjust these thresholds based on your market
        if total_comp >= 5000000:  # 50 LPA+
            return 100
        elif total_comp >= 4000000:  # 40 LPA
            return 90
        elif total_comp >= 3000000:  # 30 LPA
            return 75
        elif total_comp >= 2000000:  # 20 LPA
            return 60
        elif total_comp >= 1500000:  # 15 LPA
            return 50
        else:
            return 40

    def _generate_recommendation(self, score: float) -> str:
        """Generate recommendation based on overall score"""
        if score >= 85:
            return 'highly_recommended'
        elif score >= 70:
            return 'recommended'
        elif score >= 55:
            return 'moderate'
        elif score >= 40:
            return 'caution'
        else:
            return 'not_recommended'


class IndiaFitScorer:
    """Calculate India fit score (0-100)"""

    def __init__(self):
        self.weights = {
            'brand_awareness': 0.40,
            'market_presence': 0.30,
            'growth_in_india': 0.30
        }

    def calculate(self, collected_data: dict) -> dict:
        """
        Calculate India fit score

        Args:
            collected_data: Data from all collectors

        Returns:
            dict: India fit score and breakdown
        """
        trends_data = collected_data.get('google_trends', {}).get('data', {})

        # Component scores
        components = {
            'brand_awareness': self._score_brand_awareness(trends_data),
            'market_presence': self._score_market_presence(trends_data),
            'growth_in_india': self._score_growth(trends_data)
        }

        # Calculate weighted score
        overall = sum(components[k] * self.weights[k] for k in components.keys())

        recommendation = self._generate_recommendation(overall)

        return {
            'india_fit_score': round(overall, 1),
            'india_recommendation': recommendation,
            **components
        }

    def _score_brand_awareness(self, trends_data: dict) -> float:
        """Score based on brand awareness in India"""
        india_interest = trends_data.get('india_interest_avg', 0)

        if india_interest >= 80:
            return 100
        elif india_interest >= 60:
            return 85
        elif india_interest >= 40:
            return 70
        elif india_interest >= 20:
            return 50
        elif india_interest > 0:
            return 30
        else:
            return 10

    def _score_market_presence(self, trends_data: dict) -> float:
        """Score based on market presence in Indian cities"""
        regions = trends_data.get('india_regions', {})

        if not regions:
            return 50  # No data

        # Check presence in top tech cities
        top_cities = ['Karnataka', 'Maharashtra', 'Delhi', 'Haryana', 'Tamil Nadu']
        scores = [regions.get(city, 0) for city in top_cities if city in regions]

        if not scores:
            return 50

        avg_score = sum(scores) / len(scores)
        return min(avg_score, 100)

    def _score_growth(self, trends_data: dict) -> float:
        """Score based on growth trend in India"""
        direction = trends_data.get('trend_direction', 'stable')

        if direction == 'rising':
            return 100
        elif direction == 'stable':
            return 70
        else:  # falling
            return 40

    def _generate_recommendation(self, score: float) -> str:
        """Generate India fit recommendation"""
        if score >= 80:
            return 'Excellent fit for India-based candidates'
        elif score >= 60:
            return 'Good fit for India-based candidates'
        elif score >= 40:
            return 'Moderate fit - limited Indian presence'
        else:
            return 'Limited fit - primarily non-India focused'
