"""Reporting engine providing Rich terminal matrix tables and GitHub Actions CI markdown summaries."""

from pathlib import Path
from typing import Any, List, Optional, Union
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from evalmatrix.diff import format_diff_markdown, render_diff_panel, render_text_diff
from evalmatrix.runner import CaseResult, SuiteResult


def render_terminal_matrix(
    suite_result: SuiteResult,
    console: Optional[Console] = None,
    verbose: bool = False,
    show_diffs: bool = True,
) -> None:
    """Render an interactive terminal matrix table and failure diff panels using Rich."""
    c = console or Console()

    # Overall status banner
    status_color = "green" if suite_result.passed else "red"
    status_symbol = "✓ PASS" if suite_result.passed else "✗ FAIL"
    c.print(
        f"\n[bold {status_color}]{status_symbol}[/bold {status_color}] "
        f"[bold white]{suite_result.suite_name}[/bold white] "
        f"([cyan]{suite_result.passed_cases}/{suite_result.total_cases} cases passed[/cyan] "
        f"in [magenta]{suite_result.duration_ms:.1f}ms[/magenta])\n"
    )

    # Primary Matrix Table
    table = Table(
        title=f"EvalMatrix Evaluation Matrix: {suite_result.suite_name}",
        title_style="bold cyan",
        header_style="bold white",
        border_style="blue",
        show_lines=False,
    )

    table.add_column("Status", justify="center", width=8)
    table.add_column("Case ID", style="cyan", no_wrap=True)
    table.add_column("Name / Prompt", style="white", overflow="ellipsis", max_width=42)
    table.add_column("Assertions", justify="center", width=12)
    table.add_column("Latency", justify="right", style="magenta", width=10)
    table.add_column("Tokens (P/C/T)", justify="right", style="yellow", width=14)

    for case in suite_result.case_results:
        if case.error:
            st = Text("ERROR", style="bold red")
            assert_str = "-"
        elif case.passed:
            st = Text("PASS", style="bold green")
            assert_str = f"{case.passed_assertions}/{case.total_assertions}"
        else:
            st = Text("FAIL", style="bold red")
            assert_str = f"{case.passed_assertions}/{case.total_assertions}"

        prompt_display = case.case_name or case.prompt
        if len(prompt_display) > 40:
            prompt_display = prompt_display[:37] + "..."

        p_tok = case.response.prompt_tokens if case.response else "-"
        c_tok = case.response.completion_tokens if case.response else "-"
        t_tok = case.response.total_tokens if case.response else "-"
        tokens_str = f"{p_tok}/{c_tok}/{t_tok}"

        table.add_row(
            st,
            case.case_id,
            prompt_display,
            assert_str,
            f"{case.latency_ms:.1f}ms",
            tokens_str,
        )

    c.print(table)

    # Assertion Failure Deep Dives and Diffs
    failed_cases = [c for c in suite_result.case_results if not c.passed]
    if show_diffs and failed_cases:
        c.print(f"\n[bold red]─── Failure Inspections ({len(failed_cases)}) ───[/bold red]")
        for case in failed_cases:
            c.print(f"\n[bold cyan]● Case ID:[/bold cyan] [bold white]{case.case_id}[/bold white] "
                    f"({case.case_name or 'unnamed'})")
            if case.error:
                c.print(Panel(f"[red]{case.error}[/red]", title="Runtime Exception", border_style="red"))
                continue

            for idx, a in enumerate(case.assertions):
                if not a.passed:
                    title = f"Assertion #{idx + 1} Failed: {a.assertion_type}"
                    if a.path:
                        title += f" (path: {a.path})"

                    c.print(f"  [bold red]✗[/bold red] [yellow]{title}[/yellow]")
                    c.print(f"    [dim]Message:[/dim] {a.message}")

                    # Render diff panel if expected and actual are available
                    if a.expected is not None and a.actual is not None:
                        diff_panel = render_diff_panel(
                            expected=a.expected,
                            actual=a.actual,
                            title=f"{case.case_id} — {a.assertion_type} Diff",
                        )
                        c.print(diff_panel)
                    elif a.error_details:
                        err_lines = "\n".join(f"  • {e}" for e in a.error_details)
                        c.print(Panel(err_lines, title="Schema / Validation Errors", border_style="red"))

    # Footer Summary Line
    c.print(
        f"\n[bold {status_color}]Result:[/bold {status_color}] "
        f"{suite_result.passed_cases}/{suite_result.total_cases} cases passed "
        f"({suite_result.pass_rate:.1f}%), "
        f"{suite_result.passed_assertions}/{suite_result.total_assertions} assertions passed "
        f"({suite_result.assertion_pass_rate:.1f}%), "
        f"Duration: {suite_result.duration_ms:.1f}ms\n"
    )


def generate_markdown_report(
    suite_result: SuiteResult,
    include_diffs: bool = True,
) -> str:
    """Generate GitHub Actions Step Summary compatible Markdown report."""
    status_icon = "✅" if suite_result.passed else "❌"
    status_label = "PASSED" if suite_result.passed else "FAILED"

    lines: List[str] = []
    lines.append(f"# {status_icon} EvalMatrix Summary: {suite_result.suite_name}\n")
    lines.append(f"> **Status**: `{status_label}` | **Pass Rate**: `{suite_result.pass_rate:.1f}%` | **Duration**: `{suite_result.duration_ms:.1f}ms`\n")

    # Summary metrics table
    lines.append("### 📊 Test Suite Metrics\n")
    lines.append("| Metric | Total | Passed | Failed | Pass Rate |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    lines.append(
        f"| **Cases** | {suite_result.total_cases} | {suite_result.passed_cases} | "
        f"{suite_result.failed_cases + suite_result.errored_cases} | {suite_result.pass_rate:.1f}% |"
    )
    lines.append(
        f"| **Assertions** | {suite_result.total_assertions} | {suite_result.passed_assertions} | "
        f"{suite_result.failed_assertions} | {suite_result.assertion_pass_rate:.1f}% |\n"
    )

    # Case breakdown table
    lines.append("### 📋 Case Results\n")
    lines.append("| Status | Case ID | Name | Assertions | Latency | Tokens |")
    lines.append("| :---: | :--- | :--- | :---: | :---: | :---: |")

    for case in suite_result.case_results:
        c_status = "✅ PASS" if case.passed else ("⚠️ ERROR" if case.error else "❌ FAIL")
        name = case.case_name or "-"
        assert_str = f"{case.passed_assertions}/{case.total_assertions}" if not case.error else "-"
        lat_str = f"{case.latency_ms:.1f}ms"
        tok_str = f"{case.response.total_tokens}" if (case.response and case.response.total_tokens is not None) else "-"
        lines.append(f"| {c_status} | `{case.case_id}` | {name} | {assert_str} | {lat_str} | {tok_str} |")

    lines.append("")

    # Collapsible Failure Details with Diff code blocks
    failed_cases = [c for c in suite_result.case_results if not c.passed]
    if include_diffs and failed_cases:
        lines.append("### 🔍 Failure Diffs & Inspection\n")
        for case in failed_cases:
            lines.append(f"<details><summary><b>❌ {case.case_id}</b>: {case.case_name or 'Details'}</summary>\n")
            lines.append(f"- **Rendered Prompt**: `{case.rendered_prompt or case.prompt}`")
            if case.error:
                lines.append(f"- **Runtime Error**: `{case.error}`\n")
            else:
                for a in case.assertions:
                    if not a.passed:
                        path_info = f" (path: `{a.path}`)" if a.path else ""
                        lines.append(f"- **Failed Assertion**: `{a.assertion_type}`{path_info}")
                        lines.append(f"  - Reason: {a.message}")
                        if a.error_details:
                            for err in a.error_details:
                                lines.append(f"    - `{err}`")
                        if a.expected is not None and a.actual is not None:
                            diff_md = format_diff_markdown(a.expected, a.actual, title="Expected vs Actual Diff")
                            lines.append(f"\n{diff_md}\n")
            lines.append("</details>\n")

    lines.append("---\n*Generated by EvalMatrix*")
    return "\n".join(lines)


def export_markdown_report(
    suite_result: SuiteResult,
    output_path: Union[str, Path],
    include_diffs: bool = True,
) -> Path:
    """Export Markdown summary report to disk, creating parent directories if needed."""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = generate_markdown_report(suite_result, include_diffs=include_diffs)
    p.write_text(content, encoding="utf-8")
    return p
