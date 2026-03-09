"""Main CLI application."""

import typer
from rich.console import Console

from sba.cli.commands.edge import edge_app
from sba.cli.commands.props import props_app
from sba.cli.commands.data import data_app
from sba.cli.commands.models_cmd import models_app
from sba.cli.commands.monitor import monitor_command

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


@app.command("version")
def version():
    """Show version."""
    from sba import __version__
    console.print(f"sba v{__version__}")


@app.callback()
def callback():
    """Sports Betting Analytics — Find +EV opportunities and analyze player props."""
    pass


def main():
    app()


if __name__ == "__main__":
    main()
