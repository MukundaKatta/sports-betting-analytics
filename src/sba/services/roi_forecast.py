"""ROI forecasting and projection engine.

Uses historical betting performance to project future ROI
with confidence intervals via bootstrap resampling.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class ForecastPoint:
    """A single point on the ROI forecast curve."""
    bet_number: int
    projected_profit: float
    lower_bound: float  # 10th percentile
    upper_bound: float  # 90th percentile
    projected_roi: float


@dataclass
class ROIForecast:
    """Complete ROI forecast result."""
    current_roi: float
    projected_roi_30: float  # 30-bet projection
    projected_roi_100: float  # 100-bet projection
    confidence_level: str  # low/medium/high
    sample_size: int
    edge_per_bet: float
    variance: float
    break_even_probability: float
    forecast_curve: list[ForecastPoint]
    risk_assessment: str
    recommendations: list[str]


def forecast_roi(
    bets: list[dict],
    bankroll: float = 1000.0,
    projection_bets: int = 100,
    bootstrap_iterations: int = 500,
) -> ROIForecast:
    """Generate ROI forecast using bootstrap resampling of historical results.

    Args:
        bets: List of settled bet dicts with 'profit_loss' and 'stake' keys.
        bankroll: Current bankroll for projections.
        projection_bets: Number of future bets to project.
        bootstrap_iterations: Number of bootstrap samples.
    """
    if not bets:
        return ROIForecast(
            current_roi=0.0,
            projected_roi_30=0.0,
            projected_roi_100=0.0,
            confidence_level="low",
            sample_size=0,
            edge_per_bet=0.0,
            variance=0.0,
            break_even_probability=50.0,
            forecast_curve=[],
            risk_assessment="Insufficient data for meaningful forecast.",
            recommendations=["Place at least 30 bets to enable ROI forecasting."],
        )

    # Calculate per-bet returns
    returns = []
    for b in bets:
        pnl = b.get("profit_loss", 0) or 0
        stake = abs(b.get("stake", 0) or b.get("recommended_stake", 0) or 0)
        if stake > 0:
            returns.append(pnl / stake)
        elif pnl != 0:
            returns.append(pnl / bankroll * 10)  # normalize

    if not returns:
        return ROIForecast(
            current_roi=0.0, projected_roi_30=0.0, projected_roi_100=0.0,
            confidence_level="low", sample_size=0, edge_per_bet=0.0,
            variance=0.0, break_even_probability=50.0, forecast_curve=[],
            risk_assessment="No stake data available.",
            recommendations=["Record stake amounts when tracking bets."],
        )

    n = len(returns)
    mean_return = sum(returns) / n
    variance = sum((r - mean_return) ** 2 for r in returns) / max(n - 1, 1)
    std_dev = math.sqrt(variance)

    total_profit = sum(b.get("profit_loss", 0) or 0 for b in bets)
    total_wagered = sum(
        abs(b.get("stake", 0) or b.get("recommended_stake", 0) or 0) for b in bets
    ) or 1
    current_roi = total_profit / total_wagered * 100

    # Bootstrap resampling for projections
    random.seed(42)
    projection_results = {i: [] for i in range(0, projection_bets + 1, max(1, projection_bets // 20))}
    final_profits = []

    for _ in range(bootstrap_iterations):
        cumulative = 0.0
        for bet_num in range(1, projection_bets + 1):
            sampled_return = random.choice(returns)
            cumulative += sampled_return * (total_wagered / n)  # scale to avg stake
            if bet_num in projection_results:
                projection_results[bet_num].append(cumulative)
        final_profits.append(cumulative)

    # Build forecast curve
    curve = [ForecastPoint(bet_number=0, projected_profit=0, lower_bound=0,
                           upper_bound=0, projected_roi=0)]

    for bet_num in sorted(projection_results.keys()):
        if bet_num == 0:
            continue
        values = sorted(projection_results[bet_num])
        if not values:
            continue
        p10 = values[int(len(values) * 0.1)]
        p50 = values[int(len(values) * 0.5)]
        p90 = values[int(len(values) * 0.9)]
        avg_wagered = total_wagered / n * bet_num
        curve.append(ForecastPoint(
            bet_number=bet_num,
            projected_profit=round(p50, 2),
            lower_bound=round(p10, 2),
            upper_bound=round(p90, 2),
            projected_roi=round(p50 / max(avg_wagered, 1) * 100, 1),
        ))

    # Key projections
    final_sorted = sorted(final_profits)
    break_even_count = sum(1 for p in final_profits if p > 0)
    break_even_prob = break_even_count / len(final_profits) * 100

    projected_30 = 0.0
    projected_100 = 0.0
    for pt in curve:
        if pt.bet_number == 30 or (pt.bet_number > 25 and projected_30 == 0):
            projected_30 = pt.projected_roi
        if pt.bet_number == projection_bets:
            projected_100 = pt.projected_roi

    # Confidence level
    if n >= 100 and std_dev < abs(mean_return) * 3:
        confidence = "high"
    elif n >= 30:
        confidence = "medium"
    else:
        confidence = "low"

    # Risk assessment
    if mean_return > 0.03:
        risk = "Strong positive edge detected. Maintain discipline and bet sizing."
    elif mean_return > 0:
        risk = "Slight positive edge. Variance may dominate in short term."
    elif mean_return > -0.02:
        risk = "Near break-even. Focus on finding higher-edge opportunities."
    else:
        risk = "Negative expected value. Review strategy and market selection."

    # Recommendations
    recs = []
    if n < 30:
        recs.append("Minimum 30 settled bets needed for reliable projections.")
    if std_dev > 1.5:
        recs.append("High variance detected — consider reducing stake sizes.")
    if mean_return > 0.05:
        recs.append("Strong edge — consider increasing Kelly fraction slightly.")
    if mean_return < 0:
        recs.append("Negative ROI — review losing markets and consider reducing exposure.")
    if break_even_prob < 40:
        recs.append("Low probability of profit — reassess strategy fundamentals.")
    elif break_even_prob > 70:
        recs.append("High probability of continued profitability. Stay consistent.")

    return ROIForecast(
        current_roi=round(current_roi, 2),
        projected_roi_30=round(projected_30, 1),
        projected_roi_100=round(projected_100, 1),
        confidence_level=confidence,
        sample_size=n,
        edge_per_bet=round(mean_return * 100, 2),
        variance=round(variance, 4),
        break_even_probability=round(break_even_prob, 1),
        forecast_curve=curve,
        risk_assessment=risk,
        recommendations=recs,
    )
