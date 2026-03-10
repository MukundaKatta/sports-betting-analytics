"""Main CLI application."""

import logging

import typer
from rich.console import Console
from rich.logging import RichHandler

from sba.cli.commands.data import data_app
from sba.cli.commands.edge import edge_app
from sba.cli.commands.models_cmd import models_app
from sba.cli.commands.monitor import monitor_command
from sba.cli.commands.props import props_app

app = typer.Typer(
    name="sba",
    help="Sports Betting Analytics — Edge finder & prop analyzer",
    no_args_is_help=True,
)

app.add_typer(edge_app, name="edge")
app.add_typer(props_app, name="props")
app.add_typer(data_app, name="data")
app.add_typer(models_app, name="models")
app.command("monitor")(monitor_command)

console = Console()


@app.command("web")
def web_command(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on changes"),
):
    """Launch the web dashboard."""
    import uvicorn

    console.print("[bold green]Starting SBA Web Dashboard[/bold green]")
    console.print(f"[dim]Open http://localhost:{port} in your browser[/dim]\n")
    uvicorn.run(
        "sba.web.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


def _setup_logging(level: str = "INFO"):
    """Configure structured logging with Rich output."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )


@app.command("version")
def version():
    """Show version."""
    from sba import __version__

    console.print(f"sba v{__version__}")


@app.callback()
def callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose/debug logging"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging (alias for --verbose)"),
):
    """Sports Betting Analytics — Find +EV opportunities and analyze player props."""
    from sba.config import get_settings

    settings = get_settings()
    if verbose or debug:
        level = "DEBUG"
    else:
        level = settings.LOG_LEVEL
    _setup_logging(level)
    if verbose or debug:
        logging.debug("Debug logging enabled")


def main():
    app()


if __name__ == "__main__":
    main()
