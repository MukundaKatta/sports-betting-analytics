"""All calculator endpoints (odds, hedge, parlay, freebet, novig, devig, sgp, promo)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["calculators"])


# ── Pydantic models ─────────────────────────────────────────────────

class CalcRequest(BaseModel):
    odds_american: int | None = None
    odds_decimal: float | None = None
    odds_fractional: str | None = None
    stake: float = 100
    win_probability: float | None = None


class HedgeRequest(BaseModel):
    original_odds: int
    original_stake: float
    hedge_odds: int


class ParlayLeg(BaseModel):
    odds_american: int
    description: str = ""


class ParlayRequest(BaseModel):
    legs: list[ParlayLeg]
    stake: float = 100.0


class FreeBetRequest(BaseModel):
    free_bet_amount: float
    free_bet_odds: int
    hedge_odds: int


class NoVigOutcome(BaseModel):
    name: str
    odds_american: int


class NoVigRequest(BaseModel):
    outcomes: list[NoVigOutcome]


class DevigRequest(BaseModel):
    odds_american: list[int]
    outcome_names: list[str] | None = None
    method: str = "multiplicative"


class MultiDevigRequest(BaseModel):
    book_odds: list[dict]  # [{"bookmaker": str, "odds": [int, ...]}]
    outcome_names: list[str] | None = None
    methods: list[str] | None = None
    method_weights: dict[str, float] | None = None


class SGPLegRequest(BaseModel):
    market: str
    selection: str
    direction: str  # over, under, cover, yes, no
    odds_american: int
    player_name: str = ""


class SGPRequest(BaseModel):
    legs: list[SGPLegRequest]
    stake: float = 100.0
    sport: str = "nba"


class PromoRequest(BaseModel):
    promo_type: str  # risk_free, deposit_match, profit_boost, free_bet
    amount: float
    rollover: float = 1.0  # Rollover requirement multiplier
    min_odds: int = -200  # Minimum odds requirement


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/calculator")
def bet_calculator(req: CalcRequest):
    """Convert odds formats, calculate payouts, EV, and Kelly."""
    from sba.utils.odds_math import american_to_decimal

    # Determine base decimal odds
    if req.odds_decimal and req.odds_decimal > 1:
        dec = req.odds_decimal
    elif req.odds_american is not None:
        dec = american_to_decimal(req.odds_american)
    elif req.odds_fractional:
        parts = req.odds_fractional.replace(" ", "").split("/")
        if len(parts) == 2 and float(parts[1]) > 0:
            dec = float(parts[0]) / float(parts[1]) + 1
        else:
            dec = 2.0
    else:
        dec = 2.0

    # Convert to all formats
    if dec >= 2:
        american = round((dec - 1) * 100)
    else:
        american = round(-100 / (dec - 1))

    # Fractional
    from fractions import Fraction
    frac = Fraction(dec - 1).limit_denominator(100)
    fractional = f"{frac.numerator}/{frac.denominator}"

    implied_prob = 1 / dec
    payout = req.stake * (dec - 1)
    total_return = req.stake + payout

    # EV and Kelly if win probability given
    ev = None
    kelly = None
    if req.win_probability and 0 < req.win_probability < 1:
        ev = round(
            (req.win_probability * payout - (1 - req.win_probability) * req.stake)
            / req.stake * 100, 2
        )
        b = dec - 1
        kelly = round(
            max(0, (req.win_probability * b - (1 - req.win_probability)) / b) * 100, 2
        )

    return {
        "odds_american": american,
        "odds_decimal": round(dec, 4),
        "odds_fractional": fractional,
        "implied_probability": round(implied_prob * 100, 2),
        "stake": req.stake,
        "payout": round(payout, 2),
        "total_return": round(total_return, 2),
        "ev_pct": ev,
        "kelly_pct": kelly,
    }


@router.post("/calculator/hedge")
def hedge_calculator(req: HedgeRequest):
    """Calculate optimal hedge stake for guaranteed profit."""
    from sba.utils.odds_math import american_to_decimal

    orig_dec = american_to_decimal(req.original_odds)
    hedge_dec = american_to_decimal(req.hedge_odds)

    orig_return = req.original_stake * orig_dec
    # For equal profit on both sides: hedge_stake = orig_return / hedge_dec
    hedge_stake = round(orig_return / hedge_dec, 2)
    total_invested = req.original_stake + hedge_stake

    profit_if_original_wins = round(orig_return - total_invested, 2)
    profit_if_hedge_wins = round(hedge_stake * hedge_dec - total_invested, 2)
    guaranteed = round(min(profit_if_original_wins, profit_if_hedge_wins), 2)

    return {
        "hedge_stake": hedge_stake,
        "total_invested": round(total_invested, 2),
        "profit_if_original_wins": profit_if_original_wins,
        "profit_if_hedge_wins": profit_if_hedge_wins,
        "guaranteed_profit": guaranteed,
    }


@router.post("/calculator/parlay")
def parlay_calculator(req: ParlayRequest):
    """Calculate parlay odds and payout from multiple legs."""
    from sba.utils.odds_math import american_to_decimal, decimal_to_american

    if len(req.legs) < 2:
        raise HTTPException(400, "Parlay requires at least 2 legs")

    combined_decimal = 1.0
    leg_details = []
    for leg in req.legs:
        dec = american_to_decimal(leg.odds_american)
        combined_decimal *= dec
        imp_prob = 1.0 / dec
        leg_details.append({
            "description": leg.description,
            "odds_american": leg.odds_american,
            "odds_decimal": round(dec, 4),
            "implied_probability": round(imp_prob, 4),
        })

    combined_american = decimal_to_american(combined_decimal)
    payout = round(req.stake * combined_decimal, 2)
    profit = round(payout - req.stake, 2)
    combined_prob = 1.0 / combined_decimal

    return {
        "legs": leg_details,
        "num_legs": len(req.legs),
        "combined_odds_decimal": round(combined_decimal, 4),
        "combined_odds_american": combined_american,
        "combined_probability": round(combined_prob, 4),
        "stake": req.stake,
        "payout": payout,
        "profit": profit,
    }


@router.post("/calculator/freebet")
def free_bet_converter(req: FreeBetRequest):
    """Calculate optimal hedge to convert a free bet into guaranteed cash.

    Free bets typically don't return the stake, so the profit calculation
    differs from a normal hedge.
    """
    from sba.utils.odds_math import american_to_decimal

    fb_dec = american_to_decimal(req.free_bet_odds)
    hedge_dec = american_to_decimal(req.hedge_odds)

    # Free bet profit if it wins = amount * (decimal - 1) since stake isn't returned
    fb_profit = req.free_bet_amount * (fb_dec - 1.0)

    # Hedge stake so that hedge_profit = fb_profit - hedge_stake
    # hedge_stake * hedge_dec = fb_profit  =>  hedge_stake = fb_profit / hedge_dec
    hedge_stake = fb_profit / hedge_dec
    hedge_payout = hedge_stake * hedge_dec

    # If free bet wins: profit = fb_profit - hedge_stake
    profit_if_fb_wins = round(fb_profit - hedge_stake, 2)
    # If hedge wins: profit = hedge_payout - hedge_stake (net, since free bet loses = $0)
    profit_if_hedge_wins = round(hedge_payout - hedge_stake, 2)
    guaranteed = round(min(profit_if_fb_wins, profit_if_hedge_wins), 2)
    conversion_rate = round(guaranteed / req.free_bet_amount * 100, 1)

    return {
        "free_bet_amount": req.free_bet_amount,
        "free_bet_odds": req.free_bet_odds,
        "hedge_odds": req.hedge_odds,
        "hedge_stake": round(hedge_stake, 2),
        "profit_if_free_bet_wins": profit_if_fb_wins,
        "profit_if_hedge_wins": profit_if_hedge_wins,
        "guaranteed_profit": guaranteed,
        "conversion_rate": conversion_rate,
    }


@router.post("/calculator/novig")
def novig_calculator(req: NoVigRequest):
    """Remove vig to calculate fair/true probabilities and no-vig odds."""
    from sba.utils.odds_math import (
        american_to_decimal,
        decimal_to_american,
        decimal_to_implied_prob,
    )

    if len(req.outcomes) < 2:
        raise HTTPException(400, "Need at least 2 outcomes")

    raw = []
    for o in req.outcomes:
        dec = american_to_decimal(o.odds_american)
        imp = decimal_to_implied_prob(dec)
        raw.append({"name": o.name, "decimal": dec, "implied": imp})

    total_implied = sum(r["implied"] for r in raw)
    vig_pct = round((total_implied - 1.0) * 100, 2)

    results = []
    for r in raw:
        fair_prob = r["implied"] / total_implied
        fair_decimal = 1.0 / fair_prob if fair_prob > 0 else 0
        fair_american = decimal_to_american(fair_decimal) if fair_decimal > 1 else 0
        results.append({
            "name": r["name"],
            "original_odds": decimal_to_american(r["decimal"]),
            "original_implied_prob": round(r["implied"] * 100, 2),
            "fair_probability": round(fair_prob * 100, 2),
            "fair_odds_decimal": round(fair_decimal, 4),
            "fair_odds_american": fair_american,
        })

    return {
        "total_implied_probability": round(total_implied * 100, 2),
        "vig_percentage": vig_pct,
        "outcomes": results,
    }


@router.post("/calculator/devig")
def devig_calculator(req: DevigRequest):
    """Devig odds using a single method."""
    from sba.services.devig import devig_single

    result = devig_single(
        req.odds_american,
        method=req.method,
        outcome_names=req.outcome_names,
    )
    return {
        "method": result.method,
        "outcomes": [
            {
                "name": name,
                "fair_prob": round(prob * 100, 2),
                "fair_american": am,
                "fair_decimal": dec,
            }
            for name, prob, am, dec in zip(
                result.outcome_names,
                result.fair_probabilities,
                result.fair_odds_american,
                result.fair_odds_decimal,
            )
        ],
        "vig_removed": result.vig_removed,
    }


@router.post("/calculator/devig/multi")
def multi_devig_calculator(req: MultiDevigRequest):
    """Multi-book, multi-method devigging like Outlier Pro."""
    from sba.services.devig import devig_multi

    result = devig_multi(
        req.book_odds,
        methods=req.methods,
        method_weights=req.method_weights,
        outcome_names=req.outcome_names,
    )
    return {
        "outcomes": result.outcomes,
        "books_used": result.books_used,
        "consensus_vig": result.consensus_vig,
        "best_method": result.best_method,
        "weighted_consensus": [
            {
                "name": name,
                "fair_prob": round(prob * 100, 2),
                "fair_american": am,
                "fair_decimal": dec,
            }
            for name, prob, am, dec in zip(
                result.outcomes,
                result.weighted_fair_probs,
                result.weighted_fair_american,
                result.weighted_fair_decimal,
            )
        ],
        "methods": [
            {
                "method": m.method,
                "outcomes": [
                    {
                        "name": name,
                        "fair_prob": round(p * 100, 2),
                        "fair_american": am,
                    }
                    for name, p, am in zip(
                        m.outcome_names, m.fair_probabilities, m.fair_odds_american
                    )
                ],
                "vig_removed": m.vig_removed,
            }
            for m in result.methods
        ],
    }


@router.post("/calculator/sgp")
def sgp_builder(req: SGPRequest):
    """Build a same-game parlay with correlation adjustments.

    Unlike naive parlay calculators, this accounts for statistical
    correlations between markets (e.g., points & threes are correlated).
    """
    from sba.services.correlations import SGPLeg, build_sgp
    from sba.utils.odds_math import american_to_decimal, decimal_to_implied_prob

    if len(req.legs) < 2:
        raise HTTPException(400, "SGP requires at least 2 legs")

    legs = []
    for leg in req.legs:
        dec = american_to_decimal(leg.odds_american)
        imp = decimal_to_implied_prob(dec)
        legs.append(SGPLeg(
            market=leg.market,
            selection=leg.selection,
            direction=leg.direction,
            odds_american=leg.odds_american,
            odds_decimal=round(dec, 4),
            implied_prob=round(imp, 4),
            player_name=leg.player_name,
        ))

    analysis = build_sgp(legs, sport=req.sport)

    payout = round(req.stake * analysis.correlated_odds_decimal, 2)
    profit = round(payout - req.stake, 2)

    return {
        "num_legs": len(legs),
        "naive_odds_american": analysis.naive_odds_american,
        "naive_odds_decimal": analysis.naive_odds_decimal,
        "correlated_odds_american": analysis.correlated_odds_american,
        "correlated_odds_decimal": analysis.correlated_odds_decimal,
        "naive_probability": round(analysis.naive_probability * 100, 3),
        "correlated_probability": round(analysis.correlated_probability * 100, 3),
        "correlation_adjustment_pct": analysis.correlation_adjustment,
        "correlations": analysis.correlations,
        "stake": req.stake,
        "payout": payout,
        "profit": profit,
        "legs": [
            {
                "player": l.player_name,
                "market": l.market,
                "direction": l.direction,
                "odds_american": l.odds_american,
                "implied_prob": round(l.implied_prob * 100, 1),
            }
            for l in legs
        ],
    }


@router.post("/calculator/promo")
def promo_optimizer(req: PromoRequest):
    """Calculate optimal strategy for sportsbook promotions.

    Handles risk-free bets, deposit matches, profit boosts, and free bets.
    """
    from sba.utils.odds_math import american_to_decimal

    if req.promo_type == "risk_free":
        # Risk-free: if you lose, get the stake back as free bet
        # Best strategy: bet on a heavy favorite, then convert free bet
        # Expected conversion: ~70% on risk-free, ~65-70% free bet portion
        expected_value = round(req.amount * 0.70, 2)
        strategy = (
            "Place on slight underdog (+200 to +300). If it loses, "
            "convert the free bet using the Free Bet Converter at ~65-70% rate."
        )
        optimal_odds = "+250"

    elif req.promo_type == "deposit_match":
        # Deposit match: play through rollover, minimize expected loss
        min_dec = american_to_decimal(req.min_odds)
        implied_hold = 1.0 - (1.0 / min_dec)  # Approximate house edge
        play_through = req.amount * req.rollover
        expected_loss = round(play_through * 0.02, 2)  # ~2% house edge on low-hold
        expected_value = round(req.amount - expected_loss, 2)
        strategy = (
            f"Bet ${play_through:.0f} total on low-hold markets (≤2% vig). "
            f"Expected loss: ${expected_loss}. Net value: ${expected_value}."
        )
        optimal_odds = "-110 / -110 (low hold)"

    elif req.promo_type == "profit_boost":
        # Profit boost: increased odds on a bet
        boosted_value = round(req.amount * 0.05 * req.rollover, 2)  # ~5% boost value
        expected_value = round(boosted_value, 2)
        strategy = (
            "Use on a bet you'd make anyway. The boost adds ~5% to your EV. "
            "Best used on heavy underdogs to maximize the dollar value of the boost."
        )
        optimal_odds = "+300 or longer"

    elif req.promo_type == "free_bet":
        # Same as free bet converter - ~65-70% conversion
        expected_value = round(req.amount * 0.70, 2)
        strategy = (
            "Use the Free Bet Converter. Place the free bet on a long underdog "
            "(+300 to +500) and hedge on a different book for ~70% conversion."
        )
        optimal_odds = "+400 free bet, hedge at -400"

    else:
        raise HTTPException(400, f"Unknown promo type: {req.promo_type}")

    return {
        "promo_type": req.promo_type,
        "amount": req.amount,
        "rollover": req.rollover,
        "expected_value": expected_value,
        "strategy": strategy,
        "optimal_odds": optimal_odds,
        "conversion_rate": round(expected_value / req.amount * 100, 1),
    }
