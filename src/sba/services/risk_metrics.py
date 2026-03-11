"""Risk-adjusted performance metrics.

Provides institutional-grade metrics:
- Sharpe Ratio (risk-adjusted returns)
- Sortino Ratio (downside-risk adjusted)
- Calmar Ratio (drawdown-adjusted)
- Max Drawdown (peak-to-trough)
- Profit Factor (gross profit / gross loss)
- Kelly Edge (estimated true edge from results)
- Win/Loss Distribution analysis
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class DrawdownInfo:
    """Drawdown analysis details."""
    max_drawdown: float
    max_drawdown_pct: float
    current_drawdown: float
    current_drawdown_pct: float
    avg_drawdown: float
    drawdown_duration: int  # bets in longest drawdown
    recovery_time: int  # bets to recover from max drawdown


@dataclass
class DistributionStats:
    """Win/loss distribution statistics."""
    avg_win: float
    avg_loss: float
    median_win: float
    median_loss: float
    largest_win: float
    largest_loss: float
    win_loss_ratio: float  # avg_win / avg_loss
    skewness: float
    expectancy: float  # avg profit per bet


@dataclass
class RiskMetrics:
    """Complete risk-adjusted performance analysis."""
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    profit_factor: float
    max_drawdown: DrawdownInfo
    distribution: DistributionStats
    kelly_edge: float
    roi_pct: float
    total_profit: float
    total_bets: int
    risk_grade: str  # A+ through F
    risk_summary: str


def calculate_risk_metrics(bets: list[dict], bankroll: float = 1000.0) -> RiskMetrics:
    """Calculate comprehensive risk-adjusted metrics.

    Args:
        bets: List of settled bet dicts with 'profit_loss', 'stake', 'status'.
        bankroll: Starting bankroll for drawdown calculations.
    """
    if not bets:
        return _empty_metrics()

    # Extract P&L series
    pnl_series = [b.get("profit_loss", 0) or 0 for b in bets]
    stakes = [abs(b.get("stake", 0) or b.get("recommended_stake", 0) or 0) for b in bets]
    avg_stake = sum(stakes) / len(stakes) if stakes else 1

    # Per-bet returns (normalized)
    returns = []
    for pnl, stake in zip(pnl_series, stakes):
        if stake > 0:
            returns.append(pnl / stake)
        elif avg_stake > 0:
            returns.append(pnl / avg_stake)

    if not returns:
        return _empty_metrics()

    n = len(returns)
    mean_return = sum(returns) / n
    total_profit = sum(pnl_series)
    total_wagered = sum(stakes) or 1
    roi_pct = total_profit / total_wagered * 100

    # Variance and standard deviation
    variance = sum((r - mean_return) ** 2 for r in returns) / max(n - 1, 1)
    std_dev = math.sqrt(variance)

    # Sharpe Ratio (risk-free rate = 0 for betting)
    sharpe = mean_return / std_dev if std_dev > 0 else 0.0

    # Sortino Ratio (only downside deviation)
    downside_returns = [r for r in returns if r < 0]
    if downside_returns:
        downside_var = sum(r ** 2 for r in downside_returns) / len(downside_returns)
        downside_dev = math.sqrt(downside_var)
        sortino = mean_return / downside_dev if downside_dev > 0 else 0.0
    else:
        sortino = float("inf") if mean_return > 0 else 0.0

    # Drawdown analysis
    dd_info = _calculate_drawdowns(pnl_series, bankroll)

    # Calmar Ratio
    annualized_return = mean_return * min(n, 365)
    calmar = (
        annualized_return / abs(dd_info.max_drawdown_pct) * 100
        if dd_info.max_drawdown_pct > 0 else 0.0
    )

    # Profit Factor
    gross_profit = sum(p for p in pnl_series if p > 0)
    gross_loss = abs(sum(p for p in pnl_series if p < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Distribution stats
    dist = _distribution_stats(pnl_series, bets)

    # Kelly Edge estimation
    wins = sum(1 for b in bets if b.get("status") in ("won", "win"))
    losses = sum(1 for b in bets if b.get("status") in ("lost", "loss"))
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0
    avg_odds_decimal = 1.0
    if wins > 0:
        winning_returns = [r for r in returns if r > 0]
        avg_odds_decimal = 1 + (sum(winning_returns) / len(winning_returns)) if winning_returns else 2.0
    kelly_edge = win_rate * avg_odds_decimal - 1 if avg_odds_decimal > 0 else 0

    # Risk Grade
    grade = _compute_grade(sharpe, sortino, profit_factor, dd_info, n)

    # Risk Summary
    summary = _generate_summary(sharpe, sortino, profit_factor, dd_info, roi_pct, n)

    return RiskMetrics(
        sharpe_ratio=round(sharpe, 3),
        sortino_ratio=round(min(sortino, 99.99), 3),
        calmar_ratio=round(min(calmar, 99.99), 3),
        profit_factor=round(min(profit_factor, 99.99), 2),
        max_drawdown=dd_info,
        distribution=dist,
        kelly_edge=round(kelly_edge, 4),
        roi_pct=round(roi_pct, 2),
        total_profit=round(total_profit, 2),
        total_bets=n,
        risk_grade=grade,
        risk_summary=summary,
    )


def _calculate_drawdowns(pnl_series: list[float], bankroll: float) -> DrawdownInfo:
    """Calculate drawdown metrics from P&L series."""
    cumulative = bankroll
    peak = bankroll
    max_dd = 0.0
    max_dd_pct = 0.0
    current_dd_start = 0
    max_dd_duration = 0
    dd_duration = 0
    recovery_bets = 0
    in_drawdown = False
    max_dd_recovery = 0
    drawdowns = []

    for i, pnl in enumerate(pnl_series):
        cumulative += pnl
        if cumulative > peak:
            if in_drawdown:
                max_dd_recovery = max(max_dd_recovery, i - current_dd_start)
                in_drawdown = False
            peak = cumulative
            dd_duration = 0
        else:
            dd = peak - cumulative
            dd_pct = dd / peak * 100 if peak > 0 else 0
            if not in_drawdown:
                in_drawdown = True
                current_dd_start = i
            dd_duration += 1
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
                max_dd_duration = dd_duration
            drawdowns.append(dd_pct)

    current_dd = peak - cumulative
    current_dd_pct = current_dd / peak * 100 if peak > 0 else 0
    avg_dd = sum(drawdowns) / len(drawdowns) if drawdowns else 0

    return DrawdownInfo(
        max_drawdown=round(max_dd, 2),
        max_drawdown_pct=round(max_dd_pct, 1),
        current_drawdown=round(current_dd, 2),
        current_drawdown_pct=round(current_dd_pct, 1),
        avg_drawdown=round(avg_dd, 1),
        drawdown_duration=max_dd_duration,
        recovery_time=max_dd_recovery,
    )


def _distribution_stats(pnl_series: list[float], bets: list[dict]) -> DistributionStats:
    """Analyze win/loss distribution."""
    wins_pnl = sorted([p for p in pnl_series if p > 0])
    losses_pnl = sorted([p for p in pnl_series if p < 0])

    avg_win = sum(wins_pnl) / len(wins_pnl) if wins_pnl else 0
    avg_loss = abs(sum(losses_pnl) / len(losses_pnl)) if losses_pnl else 0
    median_win = wins_pnl[len(wins_pnl) // 2] if wins_pnl else 0
    median_loss = abs(losses_pnl[len(losses_pnl) // 2]) if losses_pnl else 0
    largest_win = max(wins_pnl) if wins_pnl else 0
    largest_loss = abs(min(losses_pnl)) if losses_pnl else 0
    wl_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")

    # Skewness
    n = len(pnl_series)
    if n >= 3:
        mean = sum(pnl_series) / n
        std = math.sqrt(sum((p - mean) ** 2 for p in pnl_series) / (n - 1)) or 1
        skew = (n / ((n - 1) * (n - 2))) * sum(((p - mean) / std) ** 3 for p in pnl_series)
    else:
        skew = 0.0

    expectancy = sum(pnl_series) / n if n > 0 else 0

    return DistributionStats(
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        median_win=round(median_win, 2),
        median_loss=round(median_loss, 2),
        largest_win=round(largest_win, 2),
        largest_loss=round(largest_loss, 2),
        win_loss_ratio=round(min(wl_ratio, 99.99), 2),
        skewness=round(skew, 3),
        expectancy=round(expectancy, 2),
    )


def _compute_grade(
    sharpe: float, sortino: float, profit_factor: float,
    dd: DrawdownInfo, sample_size: int,
) -> str:
    """Compute letter grade from metrics."""
    score = 0

    # Sharpe contribution (0-30)
    if sharpe > 0.5:
        score += 30
    elif sharpe > 0.2:
        score += 20
    elif sharpe > 0:
        score += 10

    # Sortino contribution (0-25)
    if sortino > 1.0:
        score += 25
    elif sortino > 0.5:
        score += 15
    elif sortino > 0:
        score += 8

    # Profit factor (0-25)
    if profit_factor > 2.0:
        score += 25
    elif profit_factor > 1.5:
        score += 18
    elif profit_factor > 1.0:
        score += 10

    # Drawdown (0-20, lower is better)
    if dd.max_drawdown_pct < 5:
        score += 20
    elif dd.max_drawdown_pct < 15:
        score += 12
    elif dd.max_drawdown_pct < 30:
        score += 5

    # Sample size bonus
    if sample_size < 20:
        score = int(score * 0.6)  # heavy penalty for small samples

    if score >= 85:
        return "A+"
    elif score >= 75:
        return "A"
    elif score >= 65:
        return "B+"
    elif score >= 55:
        return "B"
    elif score >= 45:
        return "C+"
    elif score >= 35:
        return "C"
    elif score >= 25:
        return "D"
    else:
        return "F"


def _generate_summary(
    sharpe: float, sortino: float, profit_factor: float,
    dd: DrawdownInfo, roi: float, n: int,
) -> str:
    """Generate human-readable risk summary."""
    parts = []

    if n < 20:
        parts.append("Small sample size — metrics may not be reliable.")
    elif sharpe > 0.3 and profit_factor > 1.2:
        parts.append("Strong risk-adjusted performance with consistent edge.")
    elif sharpe > 0 and profit_factor > 1.0:
        parts.append("Positive but moderate risk-adjusted returns.")
    elif roi > 0:
        parts.append("Profitable but with high variance — consider reducing stake sizes.")
    else:
        parts.append("Negative returns — review strategy and market selection.")

    if dd.max_drawdown_pct > 25:
        parts.append(f"Significant max drawdown of {dd.max_drawdown_pct:.0f}%.")
    if dd.current_drawdown_pct > 10:
        parts.append(f"Currently in {dd.current_drawdown_pct:.0f}% drawdown.")

    return " ".join(parts)


def _empty_metrics() -> RiskMetrics:
    """Return empty metrics when no data is available."""
    dd = DrawdownInfo(0, 0, 0, 0, 0, 0, 0)
    dist = DistributionStats(0, 0, 0, 0, 0, 0, 0, 0, 0)
    return RiskMetrics(
        sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
        profit_factor=0.0, max_drawdown=dd, distribution=dist,
        kelly_edge=0.0, roi_pct=0.0, total_profit=0.0, total_bets=0,
        risk_grade="N/A", risk_summary="No betting data available.",
    )
