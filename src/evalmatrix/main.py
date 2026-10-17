"""CLI entry point for EvalMatrix."""

import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from evalmatrix.loader import load_suite_from_yaml
from evalmatrix.runner import SuiteRunner

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
    runner = SuiteRunner(base_dir=suite_path.parent)
    suite_result = runner.run_suite(suite)

    table = Table(title=f"Evaluation: {suite.name}")
    table.add_column("Case ID", style="cyan", no_wrap=True)
    table.add_column("Prompt Snippet", style="white")
    table.add_column("Status", justify="center")
    table.add_column("Assertions", justify="center")
    table.add_column("Latency", style="magenta", justify="right")

    for case_res in suite_result.case_results:
        if case_res.error:
            status = "[bold red]ERROR[/bold red]"
            assert_str = "-"
        elif case_res.passed:
            status = "[bold green]PASS[/bold green]"
            assert_str = f"{case_res.passed_assertions}/{case_res.total_assertions}"
        else:
            status = "[bold red]FAIL[/bold red]"
            assert_str = f"{case_res.passed_assertions}/{case_res.total_assertions}"

        snippet = case_res.prompt[:35] + "..." if len(case_res.prompt) > 35 else case_res.prompt
        table.add_row(
            case_res.case_id,
            snippet,
            status,
            assert_str,
            f"{case_res.latency_ms:.1f}ms",
        )

    console.print(table)
    status_style = "green" if suite_result.passed else "red"
    console.print(
        f"[{status_style}]Summary:[/{status_style}] {suite_result.passed_cases}/{suite_result.total_cases} cases passed "
        f"({suite_result.passed_assertions}/{suite_result.total_assertions} assertions) in {suite_result.duration_ms:.1f}ms"
    )

    if not suite_result.passed:
        raise typer.Exit(code=1)


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
    runner = SuiteRunner()
    result = runner.run_suite(suite)

    table = Table(title="EvalMatrix Built-in Self-Test Demo")
    table.add_column("Case ID", style="cyan")
    table.add_column("Prompt", style="white")
    table.add_column("Fixture Output", style="green")
    table.add_column("Status", style="bold green")

    for case_res in result.case_results:
        content = case_res.response.content if case_res.response else "-"
        status = "PASS" if case_res.passed else "FAIL"
        table.add_row(case_res.case_id, case_res.prompt, content, status)

    console.print(table)
    console.print(f"\n[bold green]Demo finished successfully in {result.duration_ms:.1f}ms![/bold green]")
    console.print("[dim]Run [bold]python main.py --help[/bold] to see CLI usage instructions.[/dim]")


def main() -> None:
    """Main callable entrypoint."""
    app()


if __name__ == "__main__":
    main()
