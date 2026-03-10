"""AI-powered insights engine.

Analyzes betting history and patterns to generate personalized, actionable
recommendations — inspired by Action Network's insights and BetQL's star
rating system.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Insight:
    """A single personalized insight/recommendation."""
    id: str
    category: str  # performance, strategy, risk, opportunity, warning
    severity: str  # info, success, warning, critical
    title: str
    message: str
    action: str  # suggested action
    metric_value: float | None = None
    link: str | None = None  # page to navigate to


def generate_insights(bets: list[dict], bankroll: float = 0) -> list[Insight]:
    """Generate personalized insights from betting history.

    Analyzes patterns across multiple dimensions and returns actionable
    recommendations sorted by priority.
    """
    if not bets:
        return [Insight(
            "no_data", "performance", "info",
            "Start Tracking Your Bets",
            "You haven't recorded any bets yet. Start tracking to unlock personalized insights.",
            "Place and track your first bet to begin.",
            link="/my-bets"
        )]

    insights = []
    settled = [b for b in bets if b.get("status") in ("won", "lost", "push")]
    won = [b for b in settled if b["status"] == "won"]
    lost = [b for b in settled if b["status"] == "lost"]

    total_profit = sum(b.get("profit_loss", 0) for b in settled)
    total_staked = sum(abs(b.get("stake", 0)) for b in settled) or 1
    win_rate = len(won) / len(settled) * 100 if settled else 0
    roi = total_profit / total_staked * 100 if total_staked > 0 else 0

    # ── Performance insights ──
    if roi > 10 and len(settled) >= 20:
        insights.append(Insight(
            "great_roi", "performance", "success",
            "Outstanding ROI",
            f"Your {roi:.1f}% ROI over {len(settled)} bets is exceptional. "
            "You're significantly outperforming the market.",
            "Consider gradually increasing your unit size.",
            metric_value=roi, link="/analytics"
        ))
    elif roi < -10 and len(settled) >= 10:
        insights.append(Insight(
            "negative_roi", "performance", "warning",
            "ROI Needs Attention",
            f"Your ROI is {roi:.1f}% over {len(settled)} bets. "
            "Review your strategy and consider adjusting your approach.",
            "Focus on higher-EV opportunities and reduce bet frequency.",
            metric_value=roi, link="/analytics"
        ))

    # ── Streak analysis ──
    current_streak = 0
    streak_type = None
    for b in reversed(settled):
        if streak_type is None:
            streak_type = b["status"]
            current_streak = 1
        elif b["status"] == streak_type:
            current_streak += 1
        else:
            break

    if streak_type == "lost" and current_streak >= 5:
        insights.append(Insight(
            "cold_streak", "risk", "critical",
            f"Cold Streak Alert: {current_streak} Consecutive Losses",
            "Extended losing streaks can lead to tilt betting. Take a step back and review.",
            "Consider taking a break and reviewing your recent selections.",
            metric_value=current_streak, link="/analytics"
        ))
    elif streak_type == "won" and current_streak >= 5:
        insights.append(Insight(
            "hot_streak", "performance", "success",
            f"Hot Streak: {current_streak} Wins in a Row!",
            "Great run! Stay disciplined and don't overextend your bankroll.",
            "Stick to your staking plan — don't increase stakes based on streaks.",
            metric_value=current_streak
        ))

    # ── Sport analysis ──
    by_sport = {}
    for b in settled:
        sport = b.get("sport", "unknown")
        by_sport.setdefault(sport, []).append(b)

    best_sport = None
    best_sport_roi = -999
    worst_sport = None
    worst_sport_roi = 999
    for sport, sport_bets in by_sport.items():
        sp = sum(b.get("profit_loss", 0) for b in sport_bets)
        ss = sum(abs(b.get("stake", 0)) for b in sport_bets) or 1
        sr = sp / ss * 100
        if sr > best_sport_roi and len(sport_bets) >= 5:
            best_sport_roi = sr
            best_sport = sport
        if sr < worst_sport_roi and len(sport_bets) >= 5:
            worst_sport_roi = sr
            worst_sport = sport

    if best_sport and best_sport_roi > 5:
        insights.append(Insight(
            "best_sport", "strategy", "success",
            f"Your Best Sport: {best_sport.replace('_', ' ').title()}",
            f"You're achieving {best_sport_roi:.1f}% ROI in {best_sport.replace('_', ' ')}. "
            "This is clearly where you have an edge.",
            f"Consider focusing more of your bankroll on {best_sport.replace('_', ' ')}.",
            metric_value=best_sport_roi, link="/api/analytics/by-sport"
        ))

    if worst_sport and worst_sport_roi < -10:
        insights.append(Insight(
            "worst_sport", "warning", "warning",
            f"Underperforming: {worst_sport.replace('_', ' ').title()}",
            f"Your ROI in {worst_sport.replace('_', ' ')} is {worst_sport_roi:.1f}%. "
            "You may not have an edge in this sport.",
            "Consider reducing or eliminating bets in this sport.",
            metric_value=worst_sport_roi, link="/api/analytics/by-sport"
        ))

    # ── Day-of-week analysis ──
    by_day = {}
    for b in settled:
        placed = b.get("placed_at")
        if isinstance(placed, str):
            try:
                placed = datetime.fromisoformat(placed.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
        if isinstance(placed, datetime):
            day = placed.strftime("%A")
            by_day.setdefault(day, []).append(b)

    best_day = None
    best_day_roi = -999
    for day, day_bets in by_day.items():
        dp = sum(b.get("profit_loss", 0) for b in day_bets)
        ds = sum(abs(b.get("stake", 0)) for b in day_bets) or 1
        dr = dp / ds * 100
        if dr > best_day_roi and len(day_bets) >= 3:
            best_day_roi = dr
            best_day = day

    if best_day and best_day_roi > 5:
        insights.append(Insight(
            "best_day", "strategy", "info",
            f"Your Lucky Day: {best_day}",
            f"You perform best on {best_day}s with {best_day_roi:.1f}% ROI.",
            f"Consider increasing activity on {best_day}s.",
            metric_value=best_day_roi
        ))

    # ── Bookmaker analysis ──
    by_book = {}
    for b in settled:
        book = b.get("bookmaker", "unknown")
        by_book.setdefault(book, []).append(b)

    if len(by_book) == 1:
        insights.append(Insight(
            "single_book", "opportunity", "info",
            "Line Shopping Opportunity",
            "You're only using one bookmaker. Shopping lines across multiple books "
            "can improve your expected returns by 2-5%.",
            "Add accounts at other sportsbooks to find better odds.",
            link="/odds-comparison"
        ))

    # ── Bankroll risk ──
    if bankroll > 0:
        avg_stake = total_staked / len(settled) if settled else 0
        stake_pct = avg_stake / bankroll * 100
        if stake_pct > 10:
            insights.append(Insight(
                "high_stakes", "risk", "warning",
                "High Stake Sizing",
                f"Your average bet is {stake_pct:.1f}% of your bankroll. "
                "Professional bettors typically risk 1-3% per bet.",
                "Reduce your average stake to protect against drawdowns.",
                metric_value=stake_pct, link="/bankroll"
            ))

    # ── Market analysis ──
    by_market = {}
    for b in settled:
        market = b.get("market", "unknown")
        by_market.setdefault(market, []).append(b)

    best_market = None
    best_market_roi = -999
    for market, market_bets in by_market.items():
        mp = sum(b.get("profit_loss", 0) for b in market_bets)
        ms = sum(abs(b.get("stake", 0)) for b in market_bets) or 1
        mr = mp / ms * 100
        if mr > best_market_roi and len(market_bets) >= 5:
            best_market_roi = mr
            best_market = market

    if best_market and best_market_roi > 3:
        insights.append(Insight(
            "best_market", "strategy", "success",
            f"Your Best Market: {best_market.upper()}",
            f"You have a {best_market_roi:.1f}% edge in {best_market} bets.",
            f"Focus your research and capital on {best_market} bets.",
            metric_value=best_market_roi, link="/api/analytics/by-market"
        ))

    # ── Odds range analysis ──
    favorites = [b for b in settled if (b.get("odds_american") or 0) < -150]
    underdogs = [b for b in settled if (b.get("odds_american") or 0) > 150]

    if len(favorites) >= 5:
        fav_profit = sum(b.get("profit_loss", 0) for b in favorites)
        fav_staked = sum(abs(b.get("stake", 0)) for b in favorites) or 1
        fav_roi = fav_profit / fav_staked * 100
        if fav_roi < -15:
            insights.append(Insight(
                "chalk_trap", "warning", "warning",
                "Chalk Trap Warning",
                f"You're losing {abs(fav_roi):.1f}% ROI on heavy favorites. "
                "Favorites are often overpriced by the market.",
                "Reduce your exposure to heavy favorites (below -150).",
                metric_value=fav_roi
            ))

    if len(underdogs) >= 5:
        dog_profit = sum(b.get("profit_loss", 0) for b in underdogs)
        dog_staked = sum(abs(b.get("stake", 0)) for b in underdogs) or 1
        dog_roi = dog_profit / dog_staked * 100
        if dog_roi > 10:
            insights.append(Insight(
                "underdog_edge", "opportunity", "success",
                "Underdog Edge Detected",
                f"You're achieving {dog_roi:.1f}% ROI on underdogs (+150 or longer). "
                "This is a strong signal of an analytical edge.",
                "Increase underdog exposure with proper bankroll management.",
                metric_value=dog_roi
            ))

    # ── Recency bias check ──
    if len(settled) >= 20:
        recent = settled[-10:]
        older = settled[:-10]
        recent_profit = sum(b.get("profit_loss", 0) for b in recent)
        older_profit = sum(b.get("profit_loss", 0) for b in older)
        recent_staked = sum(abs(b.get("stake", 0)) for b in recent) or 1
        older_staked = sum(abs(b.get("stake", 0)) for b in older) or 1
        recent_roi = recent_profit / recent_staked * 100
        older_roi = older_profit / older_staked * 100

        if recent_roi < older_roi - 15:
            insights.append(Insight(
                "declining", "risk", "warning",
                "Performance Declining",
                f"Your recent ROI ({recent_roi:.1f}%) is significantly below your historical "
                f"average ({older_roi:.1f}%). This could signal model decay or market shift.",
                "Re-evaluate your current strategy and models.",
                metric_value=recent_roi - older_roi
            ))

    # Sort by severity
    severity_order = {"critical": 0, "warning": 1, "success": 2, "info": 3}
    insights.sort(key=lambda x: severity_order.get(x.severity, 99))

    return insights


def rate_bet(odds_american: int, model_prob: float | None = None,
             ev_pct: float | None = None, kelly: float | None = None,
             clv: float | None = None) -> dict:
    """Rate a bet on a 1-5 star scale like BetQL.

    Considers multiple factors: EV, Kelly fraction, CLV, and edge magnitude.
    """
    score = 0
    factors = []

    # EV component (0-40 points)
    if ev_pct is not None:
        if ev_pct >= 10:
            score += 40
            factors.append(f"Excellent EV: {ev_pct:.1f}%")
        elif ev_pct >= 5:
            score += 30
            factors.append(f"Strong EV: {ev_pct:.1f}%")
        elif ev_pct >= 2:
            score += 20
            factors.append(f"Positive EV: {ev_pct:.1f}%")
        elif ev_pct > 0:
            score += 10
            factors.append(f"Marginal EV: {ev_pct:.1f}%")
        else:
            factors.append(f"Negative EV: {ev_pct:.1f}%")

    # Kelly component (0-25 points)
    if kelly is not None:
        if kelly >= 0.05:
            score += 25
            factors.append("Full Kelly recommended")
        elif kelly >= 0.02:
            score += 15
            factors.append("Quarter Kelly stake")
        elif kelly > 0:
            score += 8
            factors.append("Small Kelly edge")

    # CLV component (0-20 points)
    if clv is not None:
        if clv > 5:
            score += 20
            factors.append(f"Strong CLV: +{clv:.1f}%")
        elif clv > 2:
            score += 12
            factors.append(f"Positive CLV: +{clv:.1f}%")
        elif clv > 0:
            score += 5
            factors.append(f"Slight CLV: +{clv:.1f}%")

    # Model confidence (0-15 points)
    if model_prob is not None:
        implied = _american_to_prob(odds_american)
        edge = model_prob - implied
        if edge > 0.10:
            score += 15
            factors.append(f"Large model edge: {edge*100:.1f}%")
        elif edge > 0.05:
            score += 10
            factors.append(f"Solid model edge: {edge*100:.1f}%")
        elif edge > 0.02:
            score += 5
            factors.append(f"Small model edge: {edge*100:.1f}%")

    # Convert to 1-5 stars
    if score >= 80:
        stars = 5
        label = "Elite"
        color = "green"
    elif score >= 60:
        stars = 4
        label = "Strong"
        color = "green"
    elif score >= 40:
        stars = 3
        label = "Good"
        color = "yellow"
    elif score >= 20:
        stars = 2
        label = "Fair"
        color = "yellow"
    else:
        stars = 1
        label = "Weak"
        color = "red"

    return {
        "stars": stars,
        "score": score,
        "label": label,
        "color": color,
        "factors": factors,
    }


def _american_to_prob(odds: int) -> float:
    """Convert American odds to implied probability."""
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)
