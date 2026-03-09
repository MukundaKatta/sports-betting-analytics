"""Monitor CLI command."""

import typer
from rich.console import Console

from sba.config import get_settings

console = Console()


def monitor_command(
    sport: str = typer.Option(None, "--sport", "-s", help="Sport key"),
    interval: int = typer.Option(None, "--interval", "-i", help="Refresh interval in seconds"),
    no_props: bool = typer.Option(False, "--no-props", help="Disable prop scanning"),
):
    """Start real-time monitoring with live display."""
    settings = get_settings()
    if not settings.ODDS_API_KEY:
        console.print("[red]Error: Set SBA_ODDS_API_KEY in your .env file[/red]")
        raise typer.Exit(1)

    from sba.services.monitor import RealtimeMonitor

    console.print("[bold]Starting real-time monitor...[/bold]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    monitor = RealtimeMonitor()
    monitor.start(sport, interval, include_props=not no_props)
    console.print("\n[dim]Monitor stopped[/dim]")
