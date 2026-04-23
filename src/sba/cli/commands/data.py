"""Data management CLI commands."""

import typer
from rich.console import Console

from sba.config import get_settings
from sba.data.db import get_connection, init_db
from sba.data.db.repository import Repository
from sba.data.sync import DataSyncer

console = Console()
data_app = typer.Typer(help="Data sync and management")


@data_app.command("sync")
def sync(
    sport: str = typer.Option(None, "--sport", "-s", help="Sport key"),
):
    """Sync current odds and scores from APIs."""
    settings = get_settings()
    if not settings.ODDS_API_KEY:
        console.print("[red]Error: Set SBA_ODDS_API_KEY in your .env file[/red]")
        raise typer.Exit(1)

    syncer = DataSyncer()

    with console.status("Syncing odds..."):
        odds_count = syncer.sync_odds(sport or settings.DEFAULT_SPORT)

    with console.status("Syncing scores..."):
        score_count = syncer.sync_scores(sport or settings.DEFAULT_SPORT)

    console.print(f"[green]Synced {odds_count} events, updated {score_count} scores[/green]")

    status = syncer.get_status()
    if status["odds_api_credits_remaining"] is not None:
        console.print(f"[dim]API credits remaining: {status['odds_api_credits_remaining']}[/dim]")


@data_app.command("backfill")
def backfill(
    player: str = typer.Option(None, "--player", "-p", help="Player name to search and backfill"),
    seasons: str = typer.Option("2024,2025", "--seasons", help="Comma-separated seasons"),
):
    """Backfill player stats from historical data."""
    season_list = [int(s.strip()) for s in seasons.split(",")]
    syncer = DataSyncer()

    if player:
        with console.status(f"Backfilling stats for '{player}'..."):
            count = syncer.search_and_sync_player(player, season_list)
        console.print(f"[green]Synced {count} game logs for '{player}'[/green]")
    else:
        console.print("[yellow]Specify --player to backfill. Example: sba data backfill --player 'LeBron James'[/yellow]")


@data_app.command("status")
def status():
    """Show data sync status and API credit usage."""
    init_db()

    with get_connection() as conn:
        events = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
        snapshots = conn.execute("SELECT COUNT(*) as c FROM odds_snapshots").fetchone()["c"]
        players = conn.execute("SELECT COUNT(*) as c FROM players").fetchone()["c"]
        logs = conn.execute("SELECT COUNT(*) as c FROM player_game_logs").fetchone()["c"]
        bets = conn.execute("SELECT COUNT(*) as c FROM bets").fetchone()["c"]

    from rich.table import Table
    table = Table(title="Database Status", show_header=True)
    table.add_column("Table", style="white")
    table.add_column("Rows", justify="right")

    table.add_row("Events", str(events))
    table.add_row("Odds Snapshots", str(snapshots))
    table.add_row("Players", str(players))
    table.add_row("Player Game Logs", str(logs))
    table.add_row("Tracked Bets", str(bets))

    console.print(table)


@data_app.command("export")
def export(
    format: str = typer.Option("csv", "--format", "-f", help="Export format: csv or json"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Export bet history to CSV or JSON."""
    import csv
    import json
    import sys
    from io import StringIO

    if format not in ("csv", "json"):
        console.print("[red]Error: format must be csv or json[/red]")
        raise typer.Exit(1)

    init_db()
    repo = Repository()

    with get_connection() as conn:
        bets = repo.get_bet_history(conn)

    if not bets:
        console.print("[yellow]No bets to export[/yellow]")
        return

    if format == "csv":
        buf = StringIO()
        fieldnames = [
            "id", "event_id", "market", "selection", "line",
            "odds_american", "odds_decimal", "bookmaker",
            "recommended_stake", "status", "profit_loss",
        ]
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        for bet in bets:
            writer.writerow({
                "id": bet.id,
                "event_id": bet.event_id,
                "market": bet.market,
                "selection": bet.selection,
                "line": bet.line or "",
                "odds_american": bet.odds_american,
                "odds_decimal": f"{bet.odds_decimal:.4f}",
                "bookmaker": bet.bookmaker,
                "recommended_stake": f"{bet.recommended_stake:.2f}",
                "status": bet.status,
                "profit_loss": f"{bet.profit_loss:.2f}" if bet.profit_loss else "0.00",
            })
        content = buf.getvalue()
    else:
        records = []
        for bet in bets:
            records.append({
                "id": bet.id,
                "event_id": bet.event_id,
                "market": bet.market,
                "selection": bet.selection,
                "line": bet.line,
                "odds_american": bet.odds_american,
                "odds_decimal": bet.odds_decimal,
                "bookmaker": bet.bookmaker,
                "recommended_stake": bet.recommended_stake,
                "status": bet.status,
                "profit_loss": bet.profit_loss,
            })
        content = json.dumps(records, indent=2)

    if output:
        with open(output, "w") as f:
            f.write(content)
        console.print(f"[green]Exported {len(bets)} bets to {output}[/green]")
    else:
        sys.stdout.write(content)
        if not content.endswith("\n"):
            sys.stdout.write("\n")
