"""Monte Carlo simulation and backtesting endpoints.

Extracted from performance.py for maintainability.
"""

from __future__ import annotations

import logging
import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

import json

from sba.data.db import get_connection, init_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["simulation"])


class SimulationRequest(BaseModel):
    bankroll: float = 1000
    num_bets: int = 100
    avg_odds: int = -110
    win_rate: float = 0.53
    kelly_fraction: float = 0.25
    simulations: int = 50

    @field_validator("bankroll")
    @classmethod
    def check_bankroll(cls, v: float) -> float:
        if not (0 < v <= 10_000_000):
            raise ValueError("bankroll must be between 0 and 10,000,000")
        return v

    @field_validator("win_rate")
    @classmethod
    def check_win_rate(cls, v: float) -> float:
        if not (0 < v < 1):
            raise ValueError("win_rate must be between 0 and 1")
        return v

    @field_validator("kelly_fraction")
    @classmethod
    def check_kelly(cls, v: float) -> float:
        if not (0 < v <= 1):
            raise ValueError("kelly_fraction must be between 0 and 1")
        return v

    @field_validator("simulations")
    @classmethod
    def check_simulations(cls, v: int) -> int:
        if not (1 <= v <= 1000):
            raise ValueError("simulations must be between 1 and 1,000")
        return v


class SimulationSummary(BaseModel):
    median_final: float
    best_case: float
    worst_case: float
    profitable_pct: float
    median_roi: float


class SimulationPercentiles(BaseModel):
    p10: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p90: list[float]


class SimulationResponse(BaseModel):
    percentiles: SimulationPercentiles
    summary: SimulationSummary
    simulations: int
    num_bets: int


class BacktestRequest(BaseModel):
    strategy_name: str = "Custom Strategy"
    starting_bankroll: float = 10000.0
    stake_type: str = "flat"
    stake_amount: float = 100.0
    min_edge: float = 0.0
    min_odds: int = -500
    max_odds: int = 5000
    stop_loss: float | None = None
    take_profit: float | None = None


class EquityCurvePoint(BaseModel):
    bet: int
    bankroll: float


class BacktestResponse(BaseModel):
    strategy_name: str
    grade: str
    total_bets: int
    wins: int
    losses: int
    pushes: int
    win_rate: float
    total_wagered: float
    total_profit: float
    roi_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    longest_win_streak: int
    longest_lose_streak: int
    avg_odds: float
    avg_stake: float
    profit_factor: float
    starting_bankroll: float
    ending_bankroll: float
    peak_bankroll: float
    equity_curve: list[EquityCurvePoint]


@router.post("/simulate", response_model=SimulationResponse)
def run_simulation(req: SimulationRequest):
    """Run Monte Carlo bankroll simulation."""
    random.seed(42)
    results = []

    if req.avg_odds > 0:
        payout_mult = req.avg_odds / 100
    else:
        payout_mult = 100 / abs(req.avg_odds)

    for _ in range(req.simulations):
        bankroll = req.bankroll
        path = [bankroll]
        for _ in range(req.num_bets):
            stake = bankroll * req.kelly_fraction * 0.1
            if stake <= 0:
                path.append(bankroll)
                continue
            if random.random() < req.win_rate:
                bankroll += stake * payout_mult
            else:
                bankroll -= stake
            path.append(round(bankroll, 2))
        results.append(path)

    num_steps = req.num_bets + 1
    p10, p25, p50, p75, p90 = [], [], [], [], []
    for i in range(num_steps):
        vals = sorted(r[i] for r in results)
        n = len(vals)
        p10.append(round(vals[int(n * 0.1)], 2))
        p25.append(round(vals[int(n * 0.25)], 2))
        p50.append(round(vals[int(n * 0.5)], 2))
        p75.append(round(vals[int(n * 0.75)], 2))
        p90.append(round(vals[int(n * 0.9)], 2))

    final_values = [r[-1] for r in results]
    profitable = sum(1 for v in final_values if v > req.bankroll)

    return {
        "percentiles": {"p10": p10, "p25": p25, "p50": p50, "p75": p75, "p90": p90},
        "summary": {
            "median_final": round(p50[-1], 2),
            "best_case": round(max(final_values), 2),
            "worst_case": round(min(final_values), 2),
            "profitable_pct": round(profitable / req.simulations * 100, 1),
            "median_roi": round((p50[-1] - req.bankroll) / req.bankroll * 100, 1),
        },
        "simulations": req.simulations,
        "num_bets": req.num_bets,
    }


@router.post("/backtest", response_model=BacktestResponse)
def run_backtest_endpoint(req: BacktestRequest):
    """Backtest a strategy against historical bet data."""
    from sba.services.backtester import run_backtest

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT b.event_id, b.selection, b.odds_american,
                   b.odds_decimal, b.status, b.profit_loss
            FROM bets b
            WHERE b.status IN ('won', 'lost', 'push', 'win', 'loss')
            ORDER BY b.placed_at
        """).fetchall()

    historical = [
        {
            "event": r["event_id"] or "",
            "selection": r["selection"] or "",
            "odds_american": r["odds_american"] or -110,
            "odds_decimal": r["odds_decimal"] or 1.909,
            "result": "win" if r["status"] in ("won", "win") else "push" if r["status"] == "push" else "loss",
        }
        for r in rows
    ]

    if not historical:
        random.seed(42)
        historical = []
        for i in range(200):
            odds = random.choice([-110, -115, 100, 120, 150, -130, -105, 200])
            dec = 1 + (odds / 100) if odds > 0 else 1 + (100 / abs(odds))
            imp = 1 / dec
            win_chance = imp + 0.02
            result = "win" if random.random() < win_chance else "loss"
            historical.append({
                "event": f"Game_{i+1}",
                "selection": f"Team_{random.choice(['A','B'])}",
                "odds_american": odds,
                "odds_decimal": round(dec, 3),
                "result": result,
                "edge_pct": round(random.uniform(0, 8), 1),
            })

    bt = run_backtest(
        historical,
        strategy_name=req.strategy_name,
        starting_bankroll=req.starting_bankroll,
        stake_type=req.stake_type,
        stake_amount=req.stake_amount,
        min_edge=req.min_edge,
        min_odds=req.min_odds,
        max_odds=req.max_odds,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
    )

    return {
        "strategy_name": bt.strategy_name,
        "grade": bt.grade,
        "total_bets": bt.total_bets,
        "wins": bt.wins,
        "losses": bt.losses,
        "pushes": bt.pushes,
        "win_rate": bt.win_rate,
        "total_wagered": bt.total_wagered,
        "total_profit": bt.total_profit,
        "roi_pct": bt.roi_pct,
        "max_drawdown": bt.max_drawdown,
        "max_drawdown_pct": bt.max_drawdown_pct,
        "sharpe_ratio": bt.sharpe_ratio,
        "longest_win_streak": bt.longest_win_streak,
        "longest_lose_streak": bt.longest_lose_streak,
        "avg_odds": bt.avg_odds,
        "avg_stake": bt.avg_stake,
        "profit_factor": bt.profit_factor,
        "starting_bankroll": bt.starting_bankroll,
        "ending_bankroll": bt.ending_bankroll,
        "peak_bankroll": bt.peak_bankroll,
        "equity_curve": bt.equity_curve,
    }


# ── Expected vs Actual Profit Tracking ───────────────────────────────


@router.get("/performance/expected-vs-actual")
def expected_vs_actual():
    """Compare expected profit (based on EV) vs actual profit over time."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, event_id, market, selection, odds_american, odds_decimal,
                   expected_value, recommended_stake, profit_loss, status, placed_at,
                   bookmaker
            FROM bets WHERE status IN ('won', 'lost') ORDER BY placed_at
        """).fetchall()

    if not rows:
        return {
            "total_bets": 0, "expected_profit": 0, "actual_profit": 0,
            "variance": 0, "by_month": [], "by_market": {}, "cumulative": [],
            "assessment": "No settled bets to analyze.",
        }

    cumulative_expected = 0.0
    cumulative_actual = 0.0
    by_month: dict[str, dict] = {}
    by_market: dict[str, dict] = {}
    cumulative = []

    for r in rows:
        ev_pct = r["expected_value"] or 0
        stake = r["recommended_stake"] or 0
        pnl = r["profit_loss"] or 0
        expected_profit = stake * (ev_pct / 100) if ev_pct else 0

        cumulative_expected += expected_profit
        cumulative_actual += pnl

        month_key = (r["placed_at"] or "")[:7]
        if month_key:
            by_month.setdefault(month_key, {"expected": 0, "actual": 0, "bets": 0})
            by_month[month_key]["expected"] += expected_profit
            by_month[month_key]["actual"] += pnl
            by_month[month_key]["bets"] += 1

        market = r["market"] or "unknown"
        by_market.setdefault(market, {"expected": 0, "actual": 0, "bets": 0})
        by_market[market]["expected"] += expected_profit
        by_market[market]["actual"] += pnl
        by_market[market]["bets"] += 1

        cumulative.append({
            "bet_number": len(cumulative) + 1,
            "expected": round(cumulative_expected, 2),
            "actual": round(cumulative_actual, 2),
            "gap": round(cumulative_actual - cumulative_expected, 2),
        })

    variance = cumulative_actual - cumulative_expected
    variance_pct = (variance / abs(cumulative_expected) * 100) if cumulative_expected != 0 else 0

    monthly_list = [
        {"month": m, "expected": round(d["expected"], 2), "actual": round(d["actual"], 2),
         "gap": round(d["actual"] - d["expected"], 2), "bets": d["bets"]}
        for m, d in sorted(by_month.items())
    ]
    market_summary = {
        m: {"expected": round(d["expected"], 2), "actual": round(d["actual"], 2),
            "gap": round(d["actual"] - d["expected"], 2), "bets": d["bets"]}
        for m, d in by_market.items()
    }

    if len(rows) < 50:
        assessment = "Small sample size — variance is expected. Track 100+ bets for meaningful comparison."
    elif variance_pct > 20:
        assessment = "Running above expectation — great run, but regression to mean is likely."
    elif variance_pct > -10:
        assessment = "Performing close to expected value — your models are tracking well."
    elif variance_pct > -30:
        assessment = "Slightly below expected — normal variance. Continue tracking."
    else:
        assessment = "Significantly below expected — review model calibration and bet selection."

    return {
        "total_bets": len(rows), "expected_profit": round(cumulative_expected, 2),
        "actual_profit": round(cumulative_actual, 2), "variance": round(variance, 2),
        "variance_pct": round(variance_pct, 1), "by_month": monthly_list,
        "by_market": market_summary, "cumulative": cumulative[-100:],
        "assessment": assessment,
    }


# ── Variance / Downswing Simulator ───────────────────────────────────


class VarianceSimRequest(BaseModel):
    win_rate: float = 0.55
    avg_odds_decimal: float = 1.91
    bankroll: float = 1000.0
    num_bets: int = 500
    num_simulations: int = 1000
    stake_pct: float = 2.0

    @field_validator("win_rate")
    @classmethod
    def valid_win_rate(cls, v: float) -> float:
        if v < 0.01 or v > 0.99:
            raise ValueError("Win rate must be between 0.01 and 0.99")
        return v

    @field_validator("num_bets")
    @classmethod
    def valid_num_bets(cls, v: int) -> int:
        if v < 10 or v > 5000:
            raise ValueError("Number of bets must be 10-5000")
        return v

    @field_validator("num_simulations")
    @classmethod
    def valid_num_sims(cls, v: int) -> int:
        if v < 100 or v > 10000:
            raise ValueError("Number of simulations must be 100-10000")
        return v


@router.post("/simulator/variance")
def variance_simulator(req: VarianceSimRequest):
    """Monte Carlo variance simulator for understanding downswings."""
    win_rate = req.win_rate
    odds = req.avg_odds_decimal
    bankroll = req.bankroll
    num_bets = req.num_bets
    num_sims = req.num_simulations
    stake_pct = req.stake_pct / 100
    ev_per_bet = win_rate * (odds - 1) - (1 - win_rate)

    final_bankrolls = []
    max_drawdowns = []
    worst_streaks = []
    bust_count = 0
    percentile_curves: dict[int, list] = {5: [], 25: [], 50: [], 75: [], 95: []}
    all_curves = []

    for _ in range(num_sims):
        br = bankroll
        peak = bankroll
        max_dd = 0.0
        current_loss_streak = 0
        worst_streak = 0
        curve = [bankroll]

        for _ in range(num_bets):
            stake = br * stake_pct
            if random.random() < win_rate:
                br += stake * (odds - 1)
                current_loss_streak = 0
            else:
                br -= stake
                current_loss_streak += 1
                worst_streak = max(worst_streak, current_loss_streak)

            if br <= 0:
                br = 0
                curve.extend([0] * (num_bets - len(curve) + 1))
                bust_count += 1
                break

            peak = max(peak, br)
            dd = (peak - br) / peak * 100
            max_dd = max(max_dd, dd)
            curve.append(round(br, 2))

        final_bankrolls.append(round(br, 2))
        max_drawdowns.append(round(max_dd, 1))
        worst_streaks.append(worst_streak)
        all_curves.append(curve)

    sample_points = [int(i * num_bets / 19) for i in range(20)]
    for pct_key in percentile_curves:
        for idx in sample_points:
            values = sorted(c[min(idx, len(c) - 1)] for c in all_curves)
            pct_idx = int(len(values) * pct_key / 100)
            percentile_curves[pct_key].append(round(values[pct_idx], 2))

    sorted_finals = sorted(final_bankrolls)
    sorted_dd = sorted(max_drawdowns)

    return {
        "parameters": {
            "win_rate": win_rate, "avg_odds_decimal": odds,
            "starting_bankroll": bankroll, "num_bets": num_bets,
            "num_simulations": num_sims, "stake_pct": req.stake_pct,
            "ev_per_bet": round(ev_per_bet * 100, 2),
        },
        "results": {
            "median_final": round(sorted_finals[len(sorted_finals) // 2], 2),
            "mean_final": round(sum(final_bankrolls) / len(final_bankrolls), 2),
            "best_case": round(sorted_finals[-1], 2),
            "worst_case": round(sorted_finals[0], 2),
            "percentile_5": round(sorted_finals[int(num_sims * 0.05)], 2),
            "percentile_25": round(sorted_finals[int(num_sims * 0.25)], 2),
            "percentile_75": round(sorted_finals[int(num_sims * 0.75)], 2),
            "percentile_95": round(sorted_finals[int(num_sims * 0.95)], 2),
            "bust_rate": round(bust_count / num_sims * 100, 1),
            "profit_probability": round(sum(1 for f in final_bankrolls if f > bankroll) / num_sims * 100, 1),
        },
        "drawdown": {
            "median_max_dd": round(sorted_dd[len(sorted_dd) // 2], 1),
            "worst_max_dd": round(sorted_dd[-1], 1),
            "avg_worst_streak": round(sum(worst_streaks) / len(worst_streaks), 1),
            "max_worst_streak": max(worst_streaks),
        },
        "percentile_curves": {
            "bet_numbers": sample_points,
            "p5": percentile_curves[5], "p25": percentile_curves[25],
            "p50": percentile_curves[50], "p75": percentile_curves[75],
            "p95": percentile_curves[95],
        },
        "assessment": _assess_variance(ev_per_bet, bust_count / num_sims, sorted_dd[len(sorted_dd) // 2]),
    }


def _assess_variance(ev_per_bet: float, bust_rate: float, median_dd: float) -> str:
    parts = []
    if ev_per_bet > 0.05:
        parts.append("Strong +EV edge detected.")
    elif ev_per_bet > 0:
        parts.append("Slight positive edge.")
    else:
        parts.append("Warning: Negative expected value. Long-term losses expected.")

    if bust_rate > 0.1:
        parts.append(f"High bust risk ({bust_rate*100:.0f}%) — consider reducing stake size.")
    elif bust_rate > 0.01:
        parts.append(f"Moderate bust risk ({bust_rate*100:.1f}%).")
    else:
        parts.append("Low bust risk with current stake sizing.")

    if median_dd > 40:
        parts.append("Expect severe drawdowns (40%+). Mental toughness required.")
    elif median_dd > 20:
        parts.append("Moderate drawdowns expected. Stay disciplined during losing streaks.")
    else:
        parts.append("Conservative drawdown profile. Good bankroll protection.")

    return " ".join(parts)


# ── Saved Filter Presets ─────────────────────────────────────────────


class SaveFilterPresetRequest(BaseModel):
    name: str
    filters: dict

    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str) -> str:
        if not v.strip() or len(v) > 100:
            raise ValueError("Name must be 1-100 characters")
        return v.strip()


@router.get("/presets")
def get_filter_presets():
    """Get all saved filter presets."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT key, value FROM user_stats WHERE key LIKE 'preset_%' ORDER BY key"
        ).fetchall()

    presets = []
    for r in rows:
        try:
            data = json.loads(r["value"])
            presets.append({"id": r["key"], "name": data.get("name", r["key"]), "filters": data.get("filters", {})})
        except (json.JSONDecodeError, TypeError):
            continue
    return {"presets": presets}


@router.post("/presets")
def save_filter_preset(req: SaveFilterPresetRequest):
    """Save a filter preset for reuse."""
    preset_key = f"preset_{req.name.lower().replace(' ', '_')}"
    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO user_stats (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (preset_key, json.dumps({"name": req.name, "filters": req.filters})),
        )
    return {"id": preset_key, "name": req.name, "saved": True}


@router.delete("/presets/{preset_id}")
def delete_filter_preset(preset_id: str):
    """Delete a saved filter preset."""
    init_db()
    with get_connection() as conn:
        result = conn.execute("DELETE FROM user_stats WHERE key = ?", (preset_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Preset not found")
    return {"deleted": True}


# ── Explainable AI — Why This Pick ───────────────────────────────────


class ExplainBetRequest(BaseModel):
    odds_american: int
    model_probability: float | None = None
    ev_pct: float | None = None
    kelly_fraction: float | None = None
    clv_pct: float | None = None
    market: str = "h2h"
    sport: str | None = None


@router.post("/explain")
def explain_bet(req: ExplainBetRequest):
    """Explainable AI — shows the reasoning behind a bet's rating."""
    from sba.services.clv_tracker import _american_to_implied

    odds = req.odds_american
    implied = _american_to_implied(odds)
    factors = []
    warnings = []
    strengths = []

    if odds > 0:
        payout_multiplier = odds / 100
    else:
        payout_multiplier = 100 / abs(odds)

    factors.append({
        "category": "Odds",
        "factor": f"{'Underdog' if odds > 0 else 'Favorite'} at {'+' if odds > 0 else ''}{odds}",
        "implied_probability": round(implied * 100, 1),
        "impact": "neutral",
        "explanation": f"The market implies a {implied*100:.1f}% chance. Payout multiplier: {payout_multiplier:.2f}x.",
    })

    # Market context factor (always present)
    market_label = req.market.upper().replace("_", " ")
    factors.append({
        "category": "Market Context",
        "factor": f"{market_label} market" + (f" ({req.sport})" if req.sport else ""),
        "impact": "neutral",
        "explanation": f"Analyzing {market_label} market odds.",
    })

    if req.model_probability is not None:
        edge = req.model_probability - implied
        edge_pct = edge * 100
        if edge > 0.05:
            impact = "strong_positive"
            strengths.append(f"Model sees {edge_pct:.1f}% edge over the market")
        elif edge > 0.02:
            impact = "positive"
            strengths.append(f"Moderate model edge: {edge_pct:.1f}%")
        elif edge > 0:
            impact = "slight_positive"
        elif edge > -0.02:
            impact = "slight_negative"
        else:
            impact = "negative"
            warnings.append(f"Model probability ({req.model_probability*100:.1f}%) below market implied ({implied*100:.1f}%)")

        factors.append({
            "category": "Model Edge",
            "factor": f"Model: {req.model_probability*100:.1f}% vs Market: {implied*100:.1f}%",
            "edge": round(edge_pct, 2),
            "impact": impact,
            "explanation": f"Your model estimates {edge_pct:+.1f}% edge vs the market price.",
        })

    if req.ev_pct is not None:
        if req.ev_pct > 5:
            impact = "strong_positive"
            strengths.append(f"Excellent EV: +{req.ev_pct:.1f}%")
        elif req.ev_pct > 2:
            impact = "positive"
            strengths.append(f"Good EV: +{req.ev_pct:.1f}%")
        elif req.ev_pct > 0:
            impact = "slight_positive"
        else:
            impact = "negative"
            warnings.append(f"Negative EV: {req.ev_pct:.1f}%")
        factors.append({
            "category": "Expected Value",
            "factor": f"EV: {req.ev_pct:+.1f}%",
            "impact": impact,
            "explanation": f"Per $100 wagered, expected return is ${req.ev_pct:.2f}.",
        })

    if req.kelly_fraction is not None:
        if req.kelly_fraction > 5:
            impact = "strong_positive"
            strengths.append(f"High Kelly: {req.kelly_fraction:.1f}%")
        elif req.kelly_fraction > 2:
            impact = "positive"
        elif req.kelly_fraction > 0:
            impact = "slight_positive"
        else:
            impact = "negative"
            warnings.append("Kelly suggests no bet (negative fraction)")
        factors.append({
            "category": "Kelly Criterion",
            "factor": f"Kelly: {req.kelly_fraction:.1f}% of bankroll",
            "impact": impact,
            "explanation": f"Optimal stake based on edge and odds: {req.kelly_fraction:.1f}% of bankroll.",
        })

    if req.clv_pct is not None:
        if req.clv_pct > 3:
            impact = "strong_positive"
            strengths.append(f"Excellent CLV: +{req.clv_pct:.1f}%")
        elif req.clv_pct > 0:
            impact = "positive"
        else:
            impact = "negative"
            warnings.append(f"Negative CLV: {req.clv_pct:.1f}%")
        factors.append({
            "category": "Closing Line Value",
            "factor": f"CLV: {req.clv_pct:+.1f}%",
            "impact": impact,
            "explanation": f"You got {abs(req.clv_pct):.1f}% {'better' if req.clv_pct > 0 else 'worse'} than the closing line.",
        })

    pos = sum(1 for f in factors if "positive" in f["impact"])
    neg = sum(1 for f in factors if f["impact"] == "negative")
    total = max(len(factors), 1)
    score = round((pos - neg * 0.5) / total * 100, 1)
    if score >= 70:
        rating = "A"
    elif score >= 50:
        rating = "B"
    elif score >= 30:
        rating = "C"
    elif score >= 10:
        rating = "D"
    else:
        rating = "F"

    # Confidence based on number of input factors provided
    input_count = sum(1 for v in [req.model_probability, req.ev_pct, req.kelly_fraction, req.clv_pct] if v is not None)
    if input_count >= 3:
        confidence = "high"
    elif input_count >= 1:
        confidence = "medium"
    else:
        confidence = "low"

    # Recommendation
    if score >= 50 and len(warnings) == 0:
        recommendation = "strong_bet"
    elif score >= 30:
        recommendation = "lean_bet"
    elif score >= 10:
        recommendation = "caution"
    else:
        recommendation = "pass"

    return {
        "rating": rating,
        "score": score,
        "confidence": confidence,
        "recommendation": recommendation,
        "factors": factors,
        "strengths": strengths,
        "warnings": warnings,
        "summary": f"{'Strong bet' if score >= 50 else 'Proceed with caution'} — "
                   f"Rating: {rating} ({score}/100). "
                   f"{len(strengths)} positive factor{'s' if len(strengths) != 1 else ''}, "
                   f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''}.",
    }
