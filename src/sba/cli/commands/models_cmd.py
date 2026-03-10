"""ML model management CLI commands."""

import typer
from rich.console import Console

from sba.data.db import get_connection, init_db
from sba.data.db.repository import Repository
from sba.models.ml.pipeline import MLPipeline

console = Console()
models_app = typer.Typer(help="ML model training and management")


@models_app.command("train")
def train(
    player: str = typer.Option(..., "--player", "-p", help="Player name"),
    market: str = typer.Option("player_points", "--market", "-m", help="Prop market"),
):
    """Train a prop prediction model for a player."""
    init_db()
    repo = Repository()

    with get_connection() as conn:
        player_obj = repo.get_player_by_name(conn, player)

    if not player_obj:
        console.print(f"[red]Player '{player}' not found. Run 'sba data backfill --player \"{player}\"' first.[/red]")
        raise typer.Exit(1)

    pipeline = MLPipeline()

    with console.status(f"Training {market} model for {player_obj.name}..."):
        metrics = pipeline.train_prop_model(player_obj.id, market)

    if "error" in metrics:
        console.print(f"[red]Training failed: {metrics['error']}[/red]")
        return

    console.print("[green]Model trained successfully![/green]")

    from rich.table import Table
    table = Table(title="Model Metrics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    for key, val in metrics.items():
        if isinstance(val, float):
            table.add_row(key, f"{val:.4f}")
        else:
            table.add_row(key, str(val))

    console.print(table)


@models_app.command("backtest")
def backtest(
    player: str = typer.Option(..., "--player", "-p", help="Player name"),
    market: str = typer.Option("player_points", "--market", "-m", help="Prop market"),
    line_pct: float = typer.Option(1.0, "--line-pct", help="Fraction of season avg for line (1.0 = season avg)"),
):
    """Run a walk-forward backtest for a player prop model."""
    init_db()
    repo = Repository()

    with get_connection() as conn:
        player_obj = repo.get_player_by_name(conn, player)

    if not player_obj:
        console.print(f"[red]Player '{player}' not found. Run 'sba data backfill --player \"{player}\"' first.[/red]")
        raise typer.Exit(1)

    from sba.services.backtester import Backtester
    from sba.cli.display import render_backtest_result

    bt = Backtester()

    with console.status(f"Running backtest for {player_obj.name} ({market}, line_pct={line_pct})..."):
        result = bt.backtest_player_props(player_obj.id, market, line_pct=line_pct)

    if result is None:
        console.print("[red]Backtest failed — not enough game data (need 35+ games).[/red]")
        raise typer.Exit(1)

    console.print(render_backtest_result(result))


@models_app.command("list")
def list_models():
    """List all trained models."""
    init_db()

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM model_versions ORDER BY trained_at DESC"
        ).fetchall()

    if not rows:
        console.print("[yellow]No models trained yet[/yellow]")
        return

    from rich.table import Table
    table = Table(title="Trained Models", show_header=True)
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("Sport")
    table.add_column("Version")
    table.add_column("Active", justify="center")
    table.add_column("Trained At")

    for row in rows:
        active = "[green]Yes[/green]" if row["is_active"] else "[dim]No[/dim]"
        table.add_row(
            str(row["id"]), row["model_type"], row["sport"],
            row["version"], active, row["trained_at"][:19],
        )

    console.print(table)
