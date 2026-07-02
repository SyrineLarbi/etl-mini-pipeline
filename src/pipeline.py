"""
ETL CLI — orchestrates extract → transform → load.

Usage:
    python -m src.pipeline run            # default: extract + transform + load
    python -m src.pipeline run --no-load  # skip the warehouse insert
    python -m src.pipeline list-runs      # peek at history table
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import duckdb
import typer
from rich.console import Console
from rich.table import Table

from .extract import extract
from .load import DB_PATH, load_gold
from .transform import to_bronze, to_gold, to_silver

app = typer.Typer(add_completion=False, help='Daily weather ETL pipeline.')
console = Console()

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'


@app.command()
def run(
    load: bool = typer.Option(True, '--load/--no-load', help='Insert gold into DuckDB'),
) -> None:
    """Run the full pipeline once."""
    console.rule('[bold cyan]1. extract[/bold cyan]')
    raw = extract(DATA / 'raw')
    console.print(f'  → [green]{raw}[/green]')

    console.rule('[bold cyan]2. transform → bronze[/bold cyan]')
    bronze = to_bronze(raw, DATA / 'bronze')
    console.print(f'  → [green]{bronze}[/green]')

    console.rule('[bold cyan]3. transform → silver[/bold cyan]')
    silver = to_silver(bronze, DATA / 'silver')
    console.print(f'  → [green]{silver}[/green]')

    console.rule('[bold cyan]4. transform → gold[/bold cyan]')
    gold = to_gold(silver, DATA / 'gold')
    console.print(f'  → [green]{gold}[/green]')

    if not load:
        console.rule('[yellow]skipped: load[/yellow]')
        return

    console.rule('[bold cyan]5. load → DuckDB[/bold cyan]')
    result = load_gold(gold)
    console.print(
        f'  → [green]summary[/green] = {result["summary_rows"]} rows, '
        f'[green]history[/green] = {result["history_rows"]} rows, '
        f'loaded at [cyan]{result["loaded_at"]}[/cyan]'
    )


@app.command('list-runs')
def list_runs(limit: int = 20) -> None:
    """Show the latest N rows of weather_history."""
    if not DB_PATH.exists():
        console.print('[red]No warehouse yet — run `python -m src.pipeline run` first.[/red]')
        raise typer.Exit(code=1)

    con = duckdb.connect(str(DB_PATH))
    rows = con.execute(
        f'''
        SELECT loaded_at, city, ROUND(temp_avg, 1) AS temp_avg,
               windy_days, rainy_days, days
        FROM gold.weather_history
        ORDER BY loaded_at DESC, city
        LIMIT {int(limit)}
        '''
    ).fetchall()
    cols = [d[0] for d in con.description]
    con.close()

    table = Table(*cols, title='Recent runs')
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print(table)


@app.command()
def dashboard(port: int = 8501) -> None:
    """Launch the Streamlit dashboard over the warehouse."""
    script = ROOT / 'src' / 'dashboard.py'
    console.print(f'[cyan]Starting dashboard[/cyan] → http://localhost:{port}  (Ctrl+C to stop)')
    subprocess.run(
        [sys.executable, '-m', 'streamlit', 'run', str(script), '--server.port', str(port)]
    )


@app.command()
def doctor() -> None:
    """Check that the environment + warehouse are healthy."""
    issues = []

    if not (DATA / 'raw').exists():
        issues.append('data/raw missing')
    if not DB_PATH.exists():
        issues.append('warehouse missing — run `python -m src.pipeline run`')

    if not issues:
        console.print('[bold green]all good[/bold green]')
        return

    for i in issues:
        console.print(f'  [red]✗[/red] {i}')
    raise typer.Exit(code=1)


if __name__ == '__main__':
    app()
