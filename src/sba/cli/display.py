"""Rich terminal display formatting."""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from sba.models.domain import EdgeOpportunity, PropPrediction, TrackedBet


def format_odds(american: int) -> Text:
    text = f"+{american}" if american > 0 else str(american)
    color = "green" if american > 0 else "white"
    return Text(text, style=color)


def format_ev(ev: float) -> Text:
    pct = f"{ev * 100:+.1f}%"
    if ev >= 0.08:
        return Text(pct, style="bold green")
    elif ev >= 0.04:
        return Text(pct, style="green")
    elif ev >= 0:
        return Text(pct, style="yellow")
    return Text(pct, style="red")


def format_prob(prob: float) -> str:
    return f"{prob * 100:.1f}%"


def format_confidence(conf: str) -> Text:
    colors = {"high": "bold green", "medium": "yellow", "low": "dim"}
    return Text(conf.upper(), style=colors.get(conf, "white"))


def render_edge_table(opportunities: list[EdgeOpportunity]) -> Table:
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Event", style="white", max_width=30)
    table.add_column("Market", style="dim")
    table.add_column("Selection", style="white")
    table.add_column("Best Odds", justify="right")
    table.add_column("Book", style="dim")
    table.add_column("Model", justify="right")
    table.add_column("Implied", justify="right")
    table.add_column("EV", justify="right")
    table.add_column("Kelly%", justify="right")
    table.add_column("Stake", justify="right")
    table.add_column("Conf", justify="center")

    if not opportunities:
        table.add_row("No +EV opportunities found", *[""] * 10)
        return table

    for opp in opportunities:
        event_str = f"{opp.event.away_team} @ {opp.event.home_team}"
        line_str = f" ({opp.line:+g})" if opp.line else ""

        table.add_row(
            event_str,
            opp.market,
            f"{opp.selection}{line_str}",
            format_odds(opp.best_odds.price_american),
            opp.bookmaker,
            format_prob(opp.model_prob),
            format_prob(opp.implied_prob),
            format_ev(opp.ev),
            f"{opp.kelly_pct * 100:.1f}%",
            f"${opp.recommended_stake:.0f}",
            format_confidence(opp.confidence),
        )

    return table


def render_prop_table(predictions: list[PropPrediction]) -> Table:
    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Player", style="white", max_width=20)
    table.add_column("Market", style="dim")
    table.add_column("Predicted", justify="right")
    table.add_column("Line", justify="right")
    table.add_column("Over%", justify="right")
    table.add_column("Over Odds", justify="right")
    table.add_column("Over EV", justify="right")
    table.add_column("Under EV", justify="right")
    table.add_column("Rec", justify="center")

    if not predictions:
        table.add_row("No prop predictions available", *[""] * 8)
        return table

    for pred in predictions:
        over_odds_str = format_odds(pred.best_over_odds.price_american) if pred.best_over_odds else Text("-")

        rec_style = "bold green" if "OVER" in pred.recommendation or "UNDER" in pred.recommendation else "dim"

        table.add_row(
            pred.player.name,
            pred.market.replace("player_", ""),
            f"{pred.predicted_value:.1f}",
            f"{pred.line:.1f}",
            format_prob(pred.over_prob),
            over_odds_str,
            format_ev(pred.over_ev),
            format_ev(pred.under_ev),
            Text(pred.recommendation, style=rec_style),
        )

    return table


def render_player_profile(profile: dict) -> Group:
    player = profile["player"]

    # Header
    header = Panel(
        f"[bold]{player.name}[/bold] | {player.team} | {player.position}",
        title="Player Profile",
    )

    # Averages comparison
    avg_table = Table(title="Averages", show_header=True, header_style="bold")
    avg_table.add_column("Stat")
    avg_table.add_column("Last 5", justify="right")
    avg_table.add_column("Last 20", justify="right")
    avg_table.add_column("Trend", justify="right")

    for stat in ["points", "rebounds", "assists", "minutes"]:
        l5 = profile["last_5"][stat]
        l20 = profile["last_20"][stat]
        trend = profile["trends"].get(f"{stat}_trend", l5 - l20)
        trend_text = format_ev(trend / max(l20, 0.1)) if stat != "minutes" else Text(f"{trend:+.1f}")

        avg_table.add_row(stat.title(), f"{l5:.1f}", f"{l20:.1f}", trend_text)

    # Recent games
    games_table = Table(title="Recent Games", show_header=True, header_style="bold dim")
    games_table.add_column("Date")
    games_table.add_column("Opp")
    games_table.add_column("Min", justify="right")
    games_table.add_column("Pts", justify="right")
    games_table.add_column("Reb", justify="right")
    games_table.add_column("Ast", justify="right")
    games_table.add_column("3PM", justify="right")

    for log in profile["recent_games"][:10]:
        games_table.add_row(
            str(log.game_date), log.opponent,
            f"{log.minutes:.0f}", str(log.points), str(log.rebounds),
            str(log.assists), str(log.threes),
        )

    return Group(header, avg_table, games_table)


def render_bet_summary(bets: list[TrackedBet]) -> Table:
    settled = [b for b in bets if b.status in ("won", "lost", "push")]
    pending = [b for b in bets if b.status == "pending"]

    total_staked = sum(b.recommended_stake for b in settled)
    total_profit = sum(b.profit_loss for b in settled)
    wins = sum(1 for b in settled if b.status == "won")
    losses = sum(1 for b in settled if b.status == "lost")
    roi = (total_profit / total_staked * 100) if total_staked > 0 else 0

    table = Table(title="Betting Summary", show_header=True, header_style="bold")
    table.add_column("Metric", style="white")
    table.add_column("Value", justify="right")

    table.add_row("Total Bets", str(len(settled)))
    table.add_row("Wins", str(wins))
    table.add_row("Losses", str(losses))
    table.add_row("Win Rate", format_prob(wins / max(len(settled), 1)))
    table.add_row("Total Staked", f"${total_staked:.2f}")
    table.add_row("Total Profit", Text(f"${total_profit:+.2f}", style="green" if total_profit >= 0 else "red"))
    table.add_row("ROI", format_ev(roi / 100))
    table.add_row("Pending Bets", str(len(pending)))

    return table
