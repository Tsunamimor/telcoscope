"""Command-line interface for telcoscope.

Run `telcoscope --help` after installing the package.
"""
from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="telcoscope",
    help="3GPP KPI observability and RCA for mobile networks.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Print the installed version."""
    from telcoscope import __version__
    console.print(f"telcoscope v{__version__}")


@app.command()
def seed(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to generate"),
    cells: int = typer.Option(100, "--cells", "-c", help="Number of cells to model"),
    seed: int = typer.Option(42, "--seed", help="Random seed"),
) -> None:
    """Generate synthetic PM/FM/CM data and load it into the database."""
    from telcoscope.synth.generator import generate_and_load
    generate_and_load(num_cells=cells, num_days=days, seed=seed)


@app.command()
def detect(
    method: str = typer.Option("robust_zscore", "--method", "-m"),
) -> None:
    """Run anomaly detection over the current marts and persist results."""
    console.print(f"[yellow]Stub: would run detection with method={method}[/yellow]")
    # TODO: implemented in Week 3


@app.command()
def rca(
    anomaly_id: int = typer.Argument(..., help="Anomaly UID to investigate"),
) -> None:
    """Run RCA against a specific anomaly and print the result."""
    console.print(f"[yellow]Stub: would run RCA on anomaly {anomaly_id}[/yellow]")
    # TODO: implemented in Week 4


if __name__ == "__main__":
    app()
