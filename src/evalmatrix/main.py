"""CLI entry point for EvalMatrix prompt evaluation and regression testing."""

import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from evalmatrix.diff import render_diff_panel
from evalmatrix.loader import load_suite_from_string, load_suite_from_yaml
from evalmatrix.reporter import export_markdown_report, render_terminal_matrix
from evalmatrix.runner import SuiteRunner

app = typer.Typer(
    name="evalmatrix",
    help="EvalMatrix: Declarative prompt evaluation and regression testing CLI.",
    add_completion=False,
    no_args_is_help=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def cli_callback(ctx: typer.Context) -> None:
    """EvalMatrix CLI entry callback running demo when invoked without command."""
    if ctx.invoked_subcommand is None:
        console.print("[bold cyan]EvalMatrix[/bold cyan] - Declarative Prompt Evaluation Engine")
        console.print("No suite file provided. Running built-in self-inspection demo...\n")
        _run_demo()


@app.command()
def run(
    suite_path: Optional[Path] = typer.Argument(
        None,
        help="Path to the YAML evaluation suite file.",
        exists=False,
    ),
    output_markdown: Optional[Path] = typer.Option(
        None,
        "--output-markdown",
        "-m",
        help="Path to export Markdown CI summary report (e.g. $GITHUB_STEP_SUMMARY).",
    ),
    diff: bool = typer.Option(
        True,
        "--diff/--no-diff",
        help="Show highlighted terminal diffs on assertion failures.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Display detailed assertion breakdown.",
    ),
    strict_templates: bool = typer.Option(
        True,
        "--strict/--lenient",
        help="Fail on undefined template variables.",
    ),
    exit_code: bool = typer.Option(
        True,
        "--exit-code/--no-exit-code",
        help="Return non-zero exit code on failure for CI integration.",
    ),
) -> None:
    """Execute evaluation suite against configured offline fixtures or LLM providers."""
    if suite_path is None:
        # Fast zero-argument execution demo
        console.print("[bold cyan]EvalMatrix[/bold cyan] - Declarative Prompt Evaluation Engine")
        console.print("No suite file provided. Running built-in self-inspection demo...\n")
        _run_demo()
        return

    try:
        suite = load_suite_from_yaml(suite_path)
    except Exception as err:
        console.print(f"[bold red]Error loading suite '{suite_path}':[/bold red] {err}")
        raise typer.Exit(code=1)

    runner = SuiteRunner(base_dir=suite_path.parent, strict_templates=strict_templates)
    suite_result = runner.run_suite(suite, base_dir=suite_path.parent)

    # Render Rich Terminal Matrix
    render_terminal_matrix(
        suite_result=suite_result,
        console=console,
        verbose=verbose,
        show_diffs=diff,
    )

    # Export Markdown CI report if requested
    if output_markdown is not None:
        out_path = export_markdown_report(suite_result, output_path=output_markdown, include_diffs=diff)
        console.print(f"[bold green]Report exported successfully:[/bold green] {out_path}")

    if exit_code and not suite_result.passed:
        raise typer.Exit(code=1)


@app.command()
def inspect(
    suite_path: Path = typer.Argument(
        ...,
        help="Path to the YAML evaluation suite file.",
    ),
    case_id: str = typer.Argument(
        ...,
        help="Specific test case ID to inspect in detail.",
    ),
) -> None:
    """Inspect a single evaluation test case, rendered prompt, and detailed diffs."""
    try:
        suite = load_suite_from_yaml(suite_path)
    except Exception as err:
        console.print(f"[bold red]Error loading suite:[/bold red] {err}")
        raise typer.Exit(code=1)

    case = suite.get_case(case_id)
    if not case:
        available = [c.id for c in suite.cases]
        console.print(f"[bold red]Case '{case_id}' not found in suite.[/bold red] Available IDs: {available}")
        raise typer.Exit(code=1)

    runner = SuiteRunner(base_dir=suite_path.parent)
    case_res = runner.run_case(
        case=case,
        provider=runner._resolve_provider(suite, base_dir=suite_path.parent),
        default_template=suite.prompt_template,
    )

    status_style = "bold green" if case_res.passed else "bold red"
    console.print(f"\n[bold cyan]EvalMatrix Inspection:[/bold cyan] [{status_style}]{case.id}[/{status_style}]")
    if case.name:
        console.print(f"[white]Name:[/white] {case.name}")

    console.print(Panel(case_res.prompt, title="Effective Rendered Prompt", border_style="cyan"))

    content = case_res.response.content if case_res.response else "<No Response>"
    console.print(Panel(content, title="Provider Response", border_style="green"))

    console.print("\n[bold]Assertions:[/bold]")
    for idx, a in enumerate(case_res.assertions):
        st = "[bold green]PASS[/bold green]" if a.passed else "[bold red]FAIL[/bold red]"
        path_str = f" (path: {a.path})" if a.path else ""
        console.print(f"  {idx + 1}. {st} [cyan]{a.assertion_type}[/cyan]{path_str} - {a.message}")
        if not a.passed and a.expected is not None and a.actual is not None:
            console.print(render_diff_panel(expected=a.expected, actual=a.actual))

    if not case_res.passed:
        raise typer.Exit(code=1)


@app.command()
def record(
    suite_path: Path = typer.Argument(
        ...,
        help="Path to the YAML evaluation suite file.",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Destination path for recorded fixtures (.yaml or .json).",
    ),
    merge: bool = typer.Option(
        False,
        "--merge",
        help="Merge into existing fixture file instead of overwriting.",
    ),
) -> None:
    """Execute suite and record responses into an offline fixture file."""
    from evalmatrix.recorder import record_suite

    try:
        suite = load_suite_from_yaml(suite_path)
    except Exception as err:
        console.print(f"[bold red]Error loading suite:[/bold red] {err}")
        raise typer.Exit(code=1)

    runner = SuiteRunner(base_dir=suite_path.parent)
    prov = runner._resolve_provider(suite, base_dir=suite_path.parent)
    result, recorder = record_suite(
        suite=suite,
        provider=prov,
        output_path=output,
        merge=merge,
        base_dir=suite_path.parent,
    )

    console.print(f"[bold green]Recorded {len(recorder)} fixtures to {output}[/bold green]")
    console.print(f"Pass rate: {result.pass_rate:.1f}% ({result.passed_cases}/{result.total_cases} cases passed)")


def _run_demo() -> None:
    """Execute quick in-memory demo showing matrix table output and diffs."""
    demo_yaml = """
name: "support-intent-demo"
description: "Self-test demo intent classifier suite"
prompt_template: "Classify support request: '{{ query }}'"
provider:
  type: "fixture"
  fixtures:
    billing_01: '{"intent": "billing_query", "confidence": 0.99}'
    cancel_01: '{"intent": "cancel_subscription", "confidence": 0.95}'
cases:
  - id: "billing_01"
    vars:
      query: "Where can I download my latest invoice?"
    assertions:
      - type: "contains"
        expected: "billing_query"
      - type: "json_schema"
        expected:
          type: "object"
          required: ["intent", "confidence"]
          properties:
            intent: {type: "string"}
            confidence: {type: "number"}
  - id: "cancel_01"
    vars:
      query: "Please cancel my account immediately."
    assertions:
      - type: "exact_match"
        expected: '{"intent": "cancel_subscription", "confidence": 0.95}'
"""
    suite = load_suite_from_string(demo_yaml)
    runner = SuiteRunner()
    result = runner.run_suite(suite)
    render_terminal_matrix(result, console=console, show_diffs=True)
    console.print("[dim]Run [bold]evalmatrix run <suite.yaml>[/bold] or [bold]python main.py --help[/bold] for full options.[/dim]")


def main() -> None:
    """Main callable entrypoint."""
    app()


if __name__ == "__main__":
    main()
