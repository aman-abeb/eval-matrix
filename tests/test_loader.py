"""Unit tests for YAML suite parsing and validation in evalmatrix.loader."""

import pytest
from pathlib import Path
from evalmatrix.loader import (
    SuiteLoadError,
    load_suite_from_string,
    load_suite_from_yaml,
)
from evalmatrix.models import AssertionType


SAMPLE_SUITE_YAML = """
name: "classification-suite"
description: "Evaluates customer intent classification"
provider:
  type: "fixture"
  fixture_file: "fixtures.yaml"
  fixtures:
    inline_case: '{"intent": "greeting"}'
cases:
  - id: "case_1"
    name: "Standard greeting"
    description: "Checks polite user greetings"
    prompt: "Hello there, how are you?"
    variables:
      user_role: "customer"
    assertions:
      - type: "exact_match"
        expected: "greeting"
      - type: "contains"
        expected: "greet"
  - id: "case_2"
    prompt: "Help with refund"
    fixture_response: '{"intent": "refund"}'
"""


def test_load_suite_from_valid_string():
    """Validate parsing a well-formed YAML string into TestSuite model."""
    suite = load_suite_from_string(SAMPLE_SUITE_YAML)
    assert suite.name == "classification-suite"
    assert suite.description == "Evaluates customer intent classification"
    assert suite.provider.type == "fixture"
    assert suite.provider.fixture_file == "fixtures.yaml"
    assert suite.provider.fixtures["inline_case"] == '{"intent": "greeting"}'
    assert len(suite.cases) == 2

    case1 = suite.get_case("case_1")
    assert case1 is not None
    assert case1.name == "Standard greeting"
    assert case1.prompt == "Hello there, how are you?"
    assert case1.variables == {"user_role": "customer"}
    assert len(case1.assertions) == 2
    assert case1.assertions[0].type == AssertionType.EXACT_MATCH
    assert case1.assertions[0].expected == "greeting"

    case2 = suite.get_case("case_2")
    assert case2 is not None
    assert case2.fixture_response == '{"intent": "refund"}'


def test_load_suite_duplicate_case_ids():
    """Ensure error is raised when test cases have duplicate IDs."""
    bad_yaml = """
name: "duplicate-id-suite"
cases:
  - id: "dup_id"
    prompt: "First prompt"
  - id: "dup_id"
    prompt: "Second prompt"
"""
    with pytest.raises(SuiteLoadError, match="Duplicate test case id 'dup_id'"):
        load_suite_from_string(bad_yaml)


def test_load_suite_empty_string():
    """Ensure empty string raises SuiteLoadError."""
    with pytest.raises(SuiteLoadError, match="Provided YAML content is empty"):
        load_suite_from_string("   \n  ")


def test_load_suite_invalid_yaml_syntax():
    """Ensure syntax errors raise SuiteLoadError."""
    malformed_yaml = """
name: [unclosed list
  cases: bad
"""
    with pytest.raises(SuiteLoadError, match="Failed to parse YAML syntax"):
        load_suite_from_string(malformed_yaml)


def test_load_suite_non_dict_root():
    """Ensure root array or scalar raises SuiteLoadError."""
    with pytest.raises(SuiteLoadError, match="Root element of suite must be a dictionary"):
        load_suite_from_string("- item 1\n- item 2")


def test_load_suite_missing_required_fields():
    """Ensure missing required fields raise validation SuiteLoadError."""
    missing_name = """
cases:
  - id: "test1"
    prompt: "hello"
"""
    with pytest.raises(SuiteLoadError, match="Validation failed for suite schema"):
        load_suite_from_string(missing_name)


def test_load_suite_from_yaml_file(tmp_path: Path):
    """Validate loading a suite from an actual filesystem file."""
    fixture_file = tmp_path / "fixtures.yaml"
    fixture_file.write_text("case_1: 'matched'\n", encoding="utf-8")

    suite_file = tmp_path / "test_suite.yaml"
    suite_file.write_text(
        f"""
name: "file-suite"
provider:
  type: "fixture"
  fixture_file: "fixtures.yaml"
cases:
  - id: "case_1"
    prompt: "ping"
""",
        encoding="utf-8",
    )

    suite = load_suite_from_yaml(suite_file)
    assert suite.name == "file-suite"
    assert len(suite.cases) == 1
    assert suite.cases[0].id == "case_1"


def test_load_suite_from_yaml_file_not_found(tmp_path: Path):
    """Ensure SuiteLoadError when file does not exist."""
    non_existent = tmp_path / "non_existent.yaml"
    with pytest.raises(SuiteLoadError, match="Suite file does not exist"):
        load_suite_from_yaml(non_existent)


def test_load_suite_missing_fixture_file_reference(tmp_path: Path):
    """Ensure error when relative fixture_file does not exist."""
    suite_file = tmp_path / "suite.yaml"
    suite_file.write_text(
        """
name: "missing-fixture-suite"
provider:
  type: "fixture"
  fixture_file: "does_not_exist.yaml"
cases:
  - id: "case_1"
    prompt: "ping"
""",
        encoding="utf-8",
    )
    with pytest.raises(SuiteLoadError, match="Configured fixture file not found"):
        load_suite_from_yaml(suite_file)
