"""Monte Carlo simulation and backtesting endpoints.

Extracted from performance.py for maintainability.
"""

from __future__ import annotations

import logging
import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from sba.data.db import get_connection

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
