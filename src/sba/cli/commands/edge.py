"""Edge finder CLI commands."""

import typer
from rich.console import Console

from sba.cli.display import render_arb_table, render_bet_summary, render_edge_table
from sba.config import get_settings
from sba.data.db import get_connection, init_db
from sba.data.db.repository import Repository
from sba.models.domain import TrackedBet
from sba.services.edge_finder import EdgeFinder

console = Console()
edge_app = typer.Typer(help="Betting edge finder - surfaces +EV opportunities")


@edge_app.command("scan")
def scan(
    sport: str = typer.Option(None, "--sport", "-s", help="Sport key (e.g. basketball_nba)"),
    market: str = typer.Option("h2h,spreads,totals", "--market", "-m", help="Markets to scan"),
    min_ev: float = typer.Option(None, "--min-ev", help="Minimum EV threshold (e.g. 0.05)"),
):
    """Scan for +EV betting opportunities across all books."""
    settings = get_settings()
    if not settings.ODDS_API_KEY:
        console.print("[red]Error: Set SBA_ODDS_API_KEY in your .env file[/red]")
        raise typer.Exit(1)

    with console.status("Scanning odds..."):
        finder = EdgeFinder()
        opportunities = finder.scan(sport, market, min_ev)

    console.print(render_edge_table(opportunities))

    credits = finder.credits_remaining()
    if credits is not None:
        console.print(f"\n[dim]API credits remaining: {credits}[/dim]")


@edge_app.command("lines")
def line_movement(
    event_id: str = typer.Argument(..., help="Event ID to check"),
    market: str = typer.Option("h2h", "--market", "-m"),
):
    """View line movement history for an event."""
    finder = EdgeFinder()
    snapshots = finder.get_line_movement(event_id, market)

    if not snapshots:
        console.print("[yellow]No line history found for this event[/yellow]")
        return

    from rich.table import Table
    table = Table(title=f"Line Movement: {event_id}", show_header=True)
    table.add_column("Time")
    table.add_column("Book")
    table.add_column("Outcome")
    table.add_column("Line", justify="right")
    table.add_column("Odds", justify="right")

    for snap in snapshots:
        from sba.cli.display import format_odds
        table.add_row(
            str(snap.snapshot_time)[:19] if snap.snapshot_time else "",
            snap.bookmaker,
            snap.outcome_name,
            f"{snap.outcome_point:g}" if snap.outcome_point else "-",
            format_odds(snap.price_american),
        )

    console.print(table)


@edge_app.command("track")
def track_bet(
    event_id: str = typer.Argument(..., help="Event ID"),
    market: str = typer.Argument(..., help="Market (h2h, spreads, totals)"),
    selection: str = typer.Argument(..., help="Selection/team name"),
    odds: int = typer.Argument(..., help="American odds taken"),
    stake: float = typer.Option(0, "--stake", help="Actual stake amount"),
):
    """Track a bet for performance monitoring."""
    from sba.utils.odds_math import american_to_decimal
    init_db()
    repo = Repository()

    bet = TrackedBet(
        event_id=event_id, market=market, selection=selection,
        line=None, odds_american=odds,
        odds_decimal=american_to_decimal(odds),
        model_probability=0, expected_value=0,
        kelly_fraction=0, recommended_stake=stake,
        bookmaker="manual",
    )

    with get_connection() as conn:
        bet_id = repo.insert_bet(conn, bet)

    console.print(f"[green]Bet tracked (ID: {bet_id})[/green]")


@edge_app.command("history")
def history():
    """View betting history and ROI."""
    init_db()
    repo = Repository()

    with get_connection() as conn:
        bets = repo.get_bet_history(conn)

    if not bets:
        console.print("[yellow]No bets tracked yet[/yellow]")
        return

    console.print(render_bet_summary(bets))


@edge_app.command("settle")
def settle(
    bet_id: int = typer.Argument(..., help="Bet ID to settle"),
    result: str = typer.Argument(..., help="Result: won, lost, or push"),
):
    """Settle a tracked bet with its outcome."""
    if result not in ("won", "lost", "push"):
        console.print("[red]Error: result must be one of: won, lost, push[/red]")
        raise typer.Exit(1)

    init_db()
    repo = Repository()

    with get_connection() as conn:
        repo.settle_bet(conn, bet_id, result)

    console.print(f"[green]Bet {bet_id} settled as {result}[/green]")


@edge_app.command("arbs")
def arbs(
    sport: str = typer.Option(None, "--sport", "-s", help="Sport key (e.g. basketball_nba)"),
    market: str = typer.Option("h2h,spreads,totals", "--market", "-m", help="Markets to scan"),
):
    """Scan for arbitrage opportunities across sportsbooks."""
    settings = get_settings()
    if not settings.ODDS_API_KEY:
        console.print("[red]Error: Set SBA_ODDS_API_KEY in your .env file[/red]")
        raise typer.Exit(1)

    with console.status("Scanning for arbitrage opportunities..."):
        finder = EdgeFinder()
        arb_results = finder.scan_arbs(sport, market)

    if not arb_results:
        console.print("[yellow]No arbitrage opportunities found[/yellow]")
        return

    console.print(render_arb_table(arb_results))
    console.print(f"\n[green]Found {len(arb_results)} arbitrage opportunity(ies)[/green]")

    credits = finder.credits_remaining()
    if credits is not None:
        console.print(f"[dim]API credits remaining: {credits}[/dim]")


@edge_app.command("clv")
def clv(
    bet_id: int = typer.Argument(..., help="Bet ID to calculate CLV for"),
):
    """Calculate closing line value for a tracked bet."""
    init_db()
    finder = EdgeFinder()
    repo = Repository()

    with get_connection() as conn:
        bets = repo.get_bet_history(conn)
        bet = next((b for b in bets if b.id == bet_id), None)

    if bet is None:
        console.print(f"[red]Error: Bet {bet_id} not found[/red]")
        raise typer.Exit(1)

    with console.status("Calculating closing line value..."):
        clv_result = finder.calculate_clv(bet)

    if clv_result is None:
        console.print("[yellow]Could not calculate CLV — closing odds not available[/yellow]")
        return

    clv_pct = clv_result * 100
    style = "green" if clv_result > 0 else "red"
    console.print(f"Bet {bet_id}: CLV = [{style}]{clv_pct:+.2f}%[/{style}]")
    if clv_result > 0:
        console.print("[dim]Positive CLV means you beat the closing line — nice![/dim]")
    else:
        console.print("[dim]Negative CLV means the closing line moved against you[/dim]")
