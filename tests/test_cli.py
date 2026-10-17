"""Tests for EvalMatrix Typer CLI commands."""

from pathlib import Path
from typer.testing import CliRunner
import pytest

from evalmatrix.main import app

runner = CliRunner()


def test_cli_zero_args_runs_demo():
    """Running CLI with no arguments executes the self-test demo quickly."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "EvalMatrix" in result.stdout
    assert "PASS" in result.stdout


def test_cli_run_example_suite(tmp_path: Path):
    """Run evaluation on customer support extraction suite."""
    example_path = Path("examples/customer_support_extraction.yaml")
    assert example_path.is_file()

    md_out = tmp_path / "summary.md"
    result = runner.invoke(app, ["run", str(example_path), "--output-markdown", str(md_out)])
    assert result.exit_code == 0
    assert "customer-support-extraction" in result.stdout
    assert "PASS" in result.stdout
    assert md_out.is_file()
    assert "EvalMatrix Summary" in md_out.read_text()


def test_cli_run_failing_suite_returns_exit_code_1(tmp_path: Path):
    """Failing assertions cause non-zero exit code 1 when --exit-code is enabled."""
    failing_yaml = tmp_path / "failing_suite.yaml"
    failing_yaml.write_text("""
name: "failing-suite"
prompt_template: "Test prompt {{ x }}"
provider:
  type: "fixture"
  fixtures:
    c1: "wrong value"
cases:
  - id: "c1"
    vars:
      x: "sample"
    assertions:
      - type: "exact_match"
        expected: "expected target value"
""")

    result = runner.invoke(app, ["run", str(failing_yaml)])
    assert result.exit_code == 1
    assert "FAIL" in result.stdout
    assert "expected target value" in result.stdout


def test_cli_inspect_case():
    """Inspect command renders detailed case info, prompt, and assertions."""
    example_path = Path("examples/customer_support_extraction.yaml")
    result = runner.invoke(app, ["inspect", str(example_path), "case_01_billing_dispute"])
    assert result.exit_code == 0
    assert "case_01_billing_dispute" in result.stdout
    assert "Effective Rendered Prompt" in result.stdout
    assert "billing_dispute" in result.stdout


def test_cli_inspect_unknown_case_fails():
    """Inspect command returns 1 when case ID does not exist."""
    example_path = Path("examples/customer_support_extraction.yaml")
    result = runner.invoke(app, ["inspect", str(example_path), "non_existent_case_xyz"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_cli_record_command(tmp_path: Path):
    """Record command executes suite and serializes offline fixture file."""
    example_path = Path("examples/customer_support_extraction.yaml")
    out_fixture = tmp_path / "recorded_fixtures.yaml"

    result = runner.invoke(app, ["record", str(example_path), "--output", str(out_fixture)])
    assert result.exit_code == 0
    assert out_fixture.is_file()
    content = out_fixture.read_text()
    assert "case_01_billing_dispute" in content
