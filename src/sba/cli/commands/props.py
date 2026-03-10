"""Prop bet analyzer CLI commands."""

import typer
from rich.console import Console

from sba.cli.display import render_player_profile, render_prop_table
from sba.config import get_settings
from sba.services.prop_analyzer import PropAnalyzer

console = Console()
props_app = typer.Typer(help="Player prop analyzer - ML-powered prop predictions")


@props_app.command("scan")
def scan(
    sport: str = typer.Option(None, "--sport", "-s", help="Sport key"),
    event: str = typer.Option(None, "--event", "-e", help="Specific event ID"),
    markets: str = typer.Option(
        "player_points,player_rebounds,player_assists",
        "--markets", "-m", help="Comma-separated prop markets"
    ),
):
    """Scan for +EV player prop opportunities."""
    settings = get_settings()
    if not settings.ODDS_API_KEY:
        console.print("[red]Error: Set SBA_ODDS_API_KEY in your .env file[/red]")
        raise typer.Exit(1)

    market_list = [m.strip() for m in markets.split(",")]

    with console.status("Analyzing props..."):
        analyzer = PropAnalyzer()
        predictions = analyzer.analyze(sport, event, market_list)

    console.print(render_prop_table(predictions))
    console.print(f"\n[dim]{len(predictions)} actionable props found[/dim]")


@props_app.command("player")
def player_profile(
    name: str = typer.Argument(..., help="Player name to look up"),
):
    """View player stats, trends, and recent performance."""
    analyzer = PropAnalyzer()
    profile = analyzer.player_profile(name)

    if not profile:
        console.print(f"[yellow]Player '{name}' not found. Run 'sba data backfill' first.[/yellow]")
        return

    console.print(render_player_profile(profile))
