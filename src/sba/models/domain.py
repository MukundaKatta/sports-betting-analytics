from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Sport:
    key: str
    title: str
    active: bool = True


@dataclass
class Event:
    id: str
    sport: str
    home_team: str
    away_team: str
    commence_time: datetime
    completed: bool = False
    home_score: int | None = None
    away_score: int | None = None


@dataclass
class Outcome:
    name: str
    price_american: int
    price_decimal: float
    point: float | None = None


@dataclass
class BookmakerOdds:
    bookmaker: str
    market: str
    outcomes: list[Outcome] = field(default_factory=list)
    last_update: datetime | None = None


@dataclass
class EventOdds:
    event: Event
    bookmakers: list[BookmakerOdds] = field(default_factory=list)


@dataclass
class Player:
    id: int
    name: str
    team: str = ""
    position: str = ""


@dataclass
class PlayerGameLog:
    player_id: int
    game_date: date
    opponent: str = ""
    home_away: str = ""
    minutes: float = 0.0
    points: int = 0
    rebounds: int = 0
    assists: int = 0
    threes: int = 0
    steals: int = 0
    blocks: int = 0
    turnovers: int = 0
    fga: int = 0
    fgm: int = 0
    fta: int = 0
    ftm: int = 0
    plus_minus: int = 0


@dataclass
class OddsSnapshot:
    event_id: str
    bookmaker: str
    market: str
    outcome_name: str
    outcome_point: float | None
    price_american: int
    price_decimal: float
    snapshot_time: datetime | None = None
    id: int | None = None


@dataclass
class EdgeOpportunity:
    event: Event
    market: str
    selection: str
    line: float | None
    best_odds: Outcome
    bookmaker: str
    model_prob: float
    implied_prob: float
    ev: float
    kelly_pct: float
    recommended_stake: float
    confidence: str = "medium"


@dataclass
class PropPrediction:
    player: Player
    market: str
    predicted_value: float
    line: float
    over_prob: float
    under_prob: float
    best_over_odds: Outcome | None = None
    best_under_odds: Outcome | None = None
    over_ev: float = 0.0
    under_ev: float = 0.0
    recommendation: str = ""
    top_features: list[str] = field(default_factory=list)


@dataclass
class TrackedBet:
    event_id: str
    market: str
    selection: str
    line: float | None
    odds_american: int
    odds_decimal: float
    model_probability: float
    expected_value: float
    kelly_fraction: float
    recommended_stake: float
    bookmaker: str
    status: str = "pending"
    profit_loss: float = 0.0
    placed_at: datetime | None = None
    settled_at: datetime | None = None
    id: int | None = None


@dataclass
class BankrollEntry:
    amount: float
    change: float = 0.0
    reason: str = ""
    bet_id: int | None = None
    created_at: datetime | None = None
    id: int | None = None


@dataclass
class ClosingLine:
    bet_id: int
    closing_odds_american: int
    closing_odds_decimal: float
    clv_american: int = 0
    clv_percentage: float = 0.0
    captured_at: datetime | None = None


@dataclass
class SharpMove:
    event_id: str
    market: str
    outcome: str
    move_type: str
    bookmaker: str
    odds_before: int
    odds_after: int
    line_before: float | None = None
    line_after: float | None = None
    magnitude: float = 0.0
    detected_at: datetime | None = None
    id: int | None = None


@dataclass
class LeaderboardEntry:
    username: str
    display_name: str = ""
    total_bets: int = 0
    wins: int = 0
    losses: int = 0
    total_profit: float = 0.0
    roi_pct: float = 0.0
    win_rate: float = 0.0
    avg_odds: int = 0
    best_streak: int = 0
    rank_score: float = 0.0
    id: int | None = None


@dataclass
class PublicPick:
    username: str
    event_id: str
    market: str
    selection: str
    odds_american: int
    line: float | None = None
    confidence: str = "medium"
    analysis: str = ""
    status: str = "pending"
    profit_loss: float = 0.0
    created_at: datetime | None = None
    id: int | None = None


@dataclass
class AlertRule:
    rule_type: str
    condition_json: str = "{}"
    enabled: bool = True
    last_triggered: datetime | None = None
    id: int | None = None
