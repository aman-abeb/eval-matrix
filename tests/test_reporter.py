"""Tests for Rich terminal matrix rendering and Markdown CI reporting."""

import json
from pathlib import Path
from rich.console import Console
import pytest

from evalmatrix.diff import format_diff_markdown, generate_unified_diff, render_text_diff
from evalmatrix.loader import load_suite_from_string
from evalmatrix.reporter import export_markdown_report, generate_markdown_report, render_terminal_matrix
from evalmatrix.runner import SuiteRunner


def test_generate_unified_diff():
    """Unified diff accurately captures text and structured JSON changes."""
    actual = "line 1\nline 2 modified\nline 3"
    expected = "line 1\nline 2 original\nline 3"

    diff_lines = generate_unified_diff(expected, actual)
    assert any("-line 2 original" in l for l in diff_lines)
    assert any("+line 2 modified" in l for l in diff_lines)


def test_generate_json_diff():
    """JSON structures are formatted and diffed cleanly."""
    actual = {"intent": "billing", "confidence": 0.8}
    expected = {"intent": "billing", "confidence": 0.99}

    diff_lines = generate_unified_diff(expected, actual)
    assert any("-  \"confidence\": 0.99" in l for l in diff_lines)
    assert any("+  \"confidence\": 0.8" in l for l in diff_lines)


def test_format_diff_markdown():
    """Markdown diff block formats properly with GitHub syntax."""
    actual = "hello world"
    expected = "hello there"
    md = format_diff_markdown(expected, actual, title="Sample Diff")
    assert "**Sample Diff**" in md
    assert "```diff" in md
    assert "-hello there" in md
    assert "+hello world" in md


def test_markdown_report_generation_and_export(tmp_path: Path):
    """Markdown report generates valid metrics table and collapsible failure diffs."""
    yaml_text = """
name: "ci-test-suite"
prompt_template: "Tell me about {{ topic }}"
provider:
  type: "fixture"
  fixtures:
    c1: '{"name": "Alice", "role": "admin"}'
    c2: '{"name": "Bob", "role": "guest"}'
cases:
  - id: "c1"
    vars: {topic: "Alice"}
    assertions:
      - type: "exact_match"
        path: "role"
        expected: "admin"
  - id: "c2"
    vars: {topic: "Bob"}
    assertions:
      - type: "exact_match"
        path: "role"
        expected: "admin"
"""
    suite = load_suite_from_string(yaml_text)
    runner = SuiteRunner()
    res = runner.run_suite(suite)
    assert not res.passed

    md = generate_markdown_report(res, include_diffs=True)
    assert "# ❌ EvalMatrix Summary: ci-test-suite" in md
    assert "| **Cases** | 2 | 1 | 1 | 50.0% |" in md
    assert "<details><summary><b>❌ c2</b>" in md
    assert "```diff" in md

    # Test disk export
    out_file = tmp_path / "reports" / "ci_summary.md"
    exported = export_markdown_report(res, out_file)
    assert exported.is_file()
    assert exported.read_text(encoding="utf-8") == md


def test_render_terminal_matrix_smoke():
    """Verify terminal matrix renders across passed and failed cases without errors."""
    yaml_text = """
name: "smoke-terminal-matrix"
provider:
  type: "fixture"
  fixtures:
    c1: "success"
    c2: "failed"
cases:
  - id: "c1"
    prompt: "p1"
    assertions:
      - type: "exact_match"
        expected: "success"
  - id: "c2"
    prompt: "p2"
    assertions:
      - type: "exact_match"
        expected: "expected_value"
"""
    suite = load_suite_from_string(yaml_text)
    runner = SuiteRunner()
    res = runner.run_suite(suite)

    # Render to a silent string console to test execution
    console = Console(record=True, width=120)
    render_terminal_matrix(res, console=console, show_diffs=True)
    output = console.export_text()
    assert "smoke-terminal-matrix" in output
    assert "c1" in output
    assert "c2" in output
    assert "FAIL" in output
    assert "PASS" in output
