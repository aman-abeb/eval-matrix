"""CLI entry point for EvalMatrix."""

import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from evalmatrix.loader import load_suite_from_yaml
from evalmatrix.providers.fixture import FixtureProvider

app = typer.Typer(
    name="evalmatrix",
    help="EvalMatrix: Declarative prompt evaluation and regression testing CLI.",
    add_completion=False,
)
console = Console()


@app.command()
def run(
    suite_path: Optional[Path] = typer.Argument(
        None,
        help="Path to the YAML evaluation suite file.",
        exists=False,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed logs"),
) -> None:
    """Run evaluation suite against configured provider."""
    if suite_path is None:
        # Fast zero-argument execution demo
        console.print("[bold cyan]EvalMatrix[/bold cyan] - Declarative Prompt Evaluation Engine")
        console.print("No suite file provided. Running built-in self-inspection demo...\n")
        _run_demo()
        return

    try:
        suite = load_suite_from_yaml(suite_path)
    except Exception as err:
        console.print(f"[bold red]Error loading suite:[/bold red] {err}")
        raise typer.Exit(code=1)

    console.print(f"[bold green]Loaded suite:[/bold green] {suite.name} ({len(suite.cases)} cases)")
    provider = FixtureProvider.from_config(suite.provider, base_dir=suite_path.parent, suite_cases=suite.cases)

    table = Table(title=f"Evaluation: {suite.name}")
    table.add_column("Case ID", style="cyan", no_wrap=True)
    table.add_column("Prompt Snippet", style="white")
    table.add_column("Response", style="green")
    table.add_column("Latency", style="magenta", justify="right")

    for case in suite.cases:
        try:
            resp = provider.generate(prompt=case.prompt, case_id=case.id)
            snippet = case.prompt[:35] + "..." if len(case.prompt) > 35 else case.prompt
            resp_snippet = resp.content.replace("\n", " ")[:40] + "..." if len(resp.content) > 40 else resp.content
            table.add_row(case.id, snippet, resp_snippet, f"{resp.latency_ms:.1f}ms")
        except Exception as e:
            table.add_row(case.id, case.prompt[:35], f"[red]ERROR: {e}[/red]", "-")

    console.print(table)


def _run_demo() -> None:
    """Execute quick in-memory demo showing suite loading and fixture resolution."""
    from evalmatrix.loader import load_suite_from_string

    demo_yaml = """
name: "support-intent-demo"
description: "Self-test demo intent classifier suite"
provider:
  type: "fixture"
  fixtures:
    billing_01: '{"intent": "billing_query", "confidence": 0.99}'
    cancel_01: '{"intent": "cancel_subscription", "confidence": 0.95}'
cases:
  - id: "billing_01"
    prompt: "Where can I download my latest invoice?"
    assertions:
      - type: "contains"
        expected: "billing_query"
  - id: "cancel_01"
    prompt: "Please cancel my account immediately."
    assertions:
      - type: "exact_match"
        expected: '{"intent": "cancel_subscription", "confidence": 0.95}'
"""
    suite = load_suite_from_string(demo_yaml)
    provider = FixtureProvider.from_config(suite.provider, suite_cases=suite.cases)

    table = Table(title="EvalMatrix Built-in Self-Test Demo")
    table.add_column("Case ID", style="cyan")
    table.add_column("Prompt", style="white")
    table.add_column("Fixture Output", style="green")
    table.add_column("Status", style="bold green")

    for case in suite.cases:
        resp = provider.generate(prompt=case.prompt, case_id=case.id)
        table.add_row(case.id, case.prompt, resp.content, "READY")

    console.print(table)
    console.print("\n[dim]Run [bold]python main.py --help[/bold] to see CLI usage instructions.[/dim]")


def main() -> None:
    """Main callable entrypoint."""
    app()


if __name__ == "__main__":
    main()
