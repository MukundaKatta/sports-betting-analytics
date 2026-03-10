"""Player prop situation splits service.

Inspired by Outlier.bet's contextual player analysis — the feature users
pay $20+/month for. Breaks down player performance by situation context.
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import date, timedelta

from sba.data.db import get_connection
from sba.data.db.repository import Repository
from sba.models.domain import PlayerGameLog, SituationSplit

logger = logging.getLogger(__name__)
repo = Repository()

STAT_FIELDS = {
    "points": "Points",
    "rebounds": "Rebounds",
    "assists": "Assists",
    "threes": "3-Pointers",
    "steals": "Steals",
    "blocks": "Blocks",
    "turnovers": "Turnovers",
}


def _compute_split(logs: list[PlayerGameLog], stat: str, line: float, label: str, situation: str) -> SituationSplit | None:
    """Compute a situation split from a subset of game logs."""
    if len(logs) < 3:
        return None

    values = [getattr(log, stat) for log in logs]
    avg = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    hit_rate = sum(1 for v in values if v > line) / len(values)

    # Trend: compare last 5 vs overall
    if len(values) >= 5:
        recent_avg = statistics.mean(values[:5])  # logs are sorted DESC
        if recent_avg > avg * 1.08:
            trend = "up"
        elif recent_avg < avg * 0.92:
            trend = "down"
        else:
            trend = "flat"
    else:
        trend = "flat"

    return SituationSplit(
        situation=situation,
        label=label,
        games=len(logs),
        avg_value=round(avg, 1),
        hit_rate=round(hit_rate * 100, 1),
        std_dev=round(std, 1),
        trend=trend,
    )


def get_situation_splits(player_name: str, stat: str = "points",
                         line: float = 0.0) -> dict:
    """Get all situation splits for a player and stat.

    Returns splits for: overall, home, away, vs each opponent,
    rest days, back-to-back, recent form windows.
    """
    if stat not in STAT_FIELDS:
        return {"error": f"Unknown stat '{stat}'. Use one of: {list(STAT_FIELDS.keys())}"}

    with get_connection() as conn:
        player = repo.get_player_by_name(conn, player_name)
        if not player:
            return {"error": f"Player '{player_name}' not found. Backfill data first."}

        logs = repo.get_player_logs(conn, player.id)

    if not logs:
        return {"error": f"No game logs for '{player_name}'. Run: sba data backfill --player \"{player_name}\""}

    # Auto-set line to season average if not provided
    if line <= 0:
        values = [getattr(log, stat) for log in logs]
        line = round(statistics.mean(values), 1)

    splits: list[dict] = []

    # Overall
    overall = _compute_split(logs, stat, line, "Season Average", "overall")
    if overall:
        splits.append(_split_to_dict(overall))

    # Home vs Away
    home_logs = [l for l in logs if l.home_away == "home"]
    away_logs = [l for l in logs if l.home_away == "away"]

    home_split = _compute_split(home_logs, stat, line, "Home Games", "home")
    away_split = _compute_split(away_logs, stat, line, "Away Games", "away")
    if home_split:
        splits.append(_split_to_dict(home_split))
    if away_split:
        splits.append(_split_to_dict(away_split))

    # By opponent (top 5 most-faced)
    opponent_logs: dict[str, list] = defaultdict(list)
    for log in logs:
        if log.opponent:
            opponent_logs[log.opponent].append(log)

    opp_sorted = sorted(opponent_logs.items(), key=lambda x: len(x[1]), reverse=True)
    for opp, opp_games in opp_sorted[:8]:
        opp_split = _compute_split(opp_games, stat, line, f"vs {opp}", f"vs_{opp}")
        if opp_split:
            splits.append(_split_to_dict(opp_split))

    # Recent form windows
    for window, label in [(3, "Last 3 Games"), (5, "Last 5 Games"),
                           (10, "Last 10 Games"), (20, "Last 20 Games")]:
        if len(logs) >= window:
            window_split = _compute_split(logs[:window], stat, line, label, f"last_{window}")
            if window_split:
                splits.append(_split_to_dict(window_split))

    # Rest days analysis (back-to-back detection)
    sorted_logs = sorted(logs, key=lambda l: l.game_date)
    b2b_logs = []
    rested_logs = []
    for i, log in enumerate(sorted_logs):
        if i > 0:
            days_rest = (log.game_date - sorted_logs[i - 1].game_date).days
            if days_rest <= 1:
                b2b_logs.append(log)
            elif days_rest >= 3:
                rested_logs.append(log)

    b2b_split = _compute_split(b2b_logs, stat, line, "Back-to-Back", "back_to_back")
    rest_split = _compute_split(rested_logs, stat, line, "3+ Days Rest", "well_rested")
    if b2b_split:
        splits.append(_split_to_dict(b2b_split))
    if rest_split:
        splits.append(_split_to_dict(rest_split))

    # High minutes vs low minutes
    if logs:
        avg_mins = statistics.mean([l.minutes for l in logs if l.minutes > 0])
        high_min_logs = [l for l in logs if l.minutes >= avg_mins + 3]
        low_min_logs = [l for l in logs if 0 < l.minutes <= avg_mins - 3]

        hi = _compute_split(high_min_logs, stat, line, "High Minutes Games", "high_minutes")
        lo = _compute_split(low_min_logs, stat, line, "Low Minutes Games", "low_minutes")
        if hi:
            splits.append(_split_to_dict(hi))
        if lo:
            splits.append(_split_to_dict(lo))

    # ── Enhanced v2.2 Splits ────────────────────────────────────────

    # Win/loss context (team performance impact)
    # Use plus_minus as proxy: positive = team winning
    win_context = [l for l in logs if (l.plus_minus or 0) > 0]
    loss_context = [l for l in logs if (l.plus_minus or 0) < 0]
    ws = _compute_split(win_context, stat, line, "Team Winning (+ plus/minus)", "team_winning")
    ls = _compute_split(loss_context, stat, line, "Team Losing (- plus/minus)", "team_losing")
    if ws:
        splits.append(_split_to_dict(ws))
    if ls:
        splits.append(_split_to_dict(ls))

    # Day of week splits
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for day_idx, day_name in enumerate(day_names):
        day_logs = [l for l in logs if l.game_date.weekday() == day_idx]
        ds = _compute_split(day_logs, stat, line, f"{day_name} Games", f"day_{day_name.lower()}")
        if ds:
            splits.append(_split_to_dict(ds))

    # Month-based splits (early vs late season)
    month_names = {10: "October", 11: "November", 12: "December",
                   1: "January", 2: "February", 3: "March", 4: "April"}
    for month_num, month_name in month_names.items():
        month_logs = [l for l in logs if l.game_date.month == month_num]
        ms = _compute_split(month_logs, stat, line, f"{month_name}", f"month_{month_num}")
        if ms:
            splits.append(_split_to_dict(ms))

    # Scoring efficiency context: high FGA vs low FGA games
    fga_logs = [l for l in logs if hasattr(l, 'fga') and l.fga and l.fga > 0]
    if len(fga_logs) >= 6:
        avg_fga = statistics.mean([l.fga for l in fga_logs])
        high_usage = [l for l in fga_logs if l.fga >= avg_fga + 2]
        low_usage = [l for l in fga_logs if l.fga <= avg_fga - 2]
        hu = _compute_split(high_usage, stat, line, "High Usage (FGA above avg)", "high_usage")
        lu = _compute_split(low_usage, stat, line, "Low Usage (FGA below avg)", "low_usage")
        if hu:
            splits.append(_split_to_dict(hu))
        if lu:
            splits.append(_split_to_dict(lu))

    return {
        "player": player.name,
        "team": player.team,
        "stat": stat,
        "stat_label": STAT_FIELDS.get(stat, stat),
        "line": line,
        "total_games": len(logs),
        "splits": splits,
    }


def _split_to_dict(split: SituationSplit) -> dict:
    """Convert a SituationSplit to a serializable dict."""
    return {
        "situation": split.situation,
        "label": split.label,
        "games": split.games,
        "avg_value": split.avg_value,
        "hit_rate": split.hit_rate,
        "std_dev": split.std_dev,
        "trend": split.trend,
    }
