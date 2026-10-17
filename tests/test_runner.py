"""Unit tests for EvalMatrix evaluation suite runner and result aggregation."""

import json
from pathlib import Path
from typing import Any, Dict, Optional
import pytest

from evalmatrix.loader import load_suite_from_string
from evalmatrix.models import (
    AssertionConfig,
    ProviderConfig,
    ProviderResponse,
    TestCase,
    TestSuite,
)
from evalmatrix.providers.base import BaseProvider
from evalmatrix.runner import CaseResult, SuiteResult, SuiteRunner, run_suite


ALL_PASSING_SUITE_YAML = r"""
name: "passing-suite"
description: "Suite where all cases pass assertions"
provider:
  type: "fixture"
  fixtures:
    greeting_case: '{"intent": "greeting", "confidence": 0.99}'
    refund_case: '{"intent": "refund", "confidence": 0.85, "amount": 50.0}'
    regex_case: "Ticket #9876 created successfully"
cases:
  - id: "greeting_case"
    name: "Greeting recognition"
    prompt: "Hello there!"
    assertions:
      - type: "contains"
        expected: "greeting"
      - type: "exact_match"
        path: "intent"
        expected: "greeting"
  - id: "refund_case"
    name: "Refund schema check"
    prompt: "I want my $50 back"
    assertions:
      - type: "json_schema"
        expected:
          type: "object"
          required: ["intent", "confidence", "amount"]
          properties:
            intent: {type: "string"}
            confidence: {type: "number", minimum: 0.0, maximum: 1.0}
            amount: {type: "number", minimum: 0.0}
  - id: "regex_case"
    name: "Regex ticket pattern"
    prompt: "Open a ticket for missing order"
    assertions:
      - type: "regex"
        expected: 'Ticket #\d+'
"""


def test_suite_runner_all_passing():
    """Verify all-passing test suite execution and statistical aggregation."""
    suite = load_suite_from_string(ALL_PASSING_SUITE_YAML)
    runner = SuiteRunner()
    result = runner.run_suite(suite)

    assert isinstance(result, SuiteResult)
    assert result.suite_name == "passing-suite"
    assert result.passed is True
    assert result.total_cases == 3
    assert result.passed_cases == 3
    assert result.failed_cases == 0
    assert result.errored_cases == 0
    assert result.pass_rate == 100.0
    assert result.total_assertions == 4
    assert result.passed_assertions == 4
    assert result.failed_assertions == 0
    assert result.assertion_pass_rate == 100.0
    assert result.duration_ms >= 0.0

    case1 = result.get_case_result("greeting_case")
    assert case1 is not None
    assert case1.passed is True
    assert case1.total_assertions == 2
    assert case1.passed_assertions == 2
    assert case1.failed_assertions == 0
    assert case1.error is None
    assert case1.response is not None
    assert case1.latency_ms > 0
    assert case1.rendered_prompt == "Hello there!"
    assert case1.raw_prompt == "Hello there!"


def test_suite_runner_mixed_failures():
    """Verify detection of assertion failures and correct summary stats."""
    suite_yaml = """
name: "mixed-suite"
provider:
  type: "fixture"
  fixtures:
    pass_case: '{"status": "ok"}'
    fail_case: '{"status": "error"}'
cases:
  - id: "pass_case"
    prompt: "Check status"
    assertions:
      - type: "exact_match"
        path: "status"
        expected: "ok"
  - id: "fail_case"
    prompt: "Check status expected to fail"
    assertions:
      - type: "exact_match"
        path: "status"
        expected: "ok"
"""
    result = run_suite(suite_yaml)

    assert result.passed is False
    assert result.total_cases == 2
    assert result.passed_cases == 1
    assert result.failed_cases == 1
    assert result.errored_cases == 0
    assert result.pass_rate == 50.0
    assert result.total_assertions == 2
    assert result.passed_assertions == 1
    assert result.failed_assertions == 1
    assert result.assertion_pass_rate == 50.0

    failing = result.get_case_result("fail_case")
    assert failing is not None
    assert failing.passed is False
    assert failing.failed_assertions == 1
    assert "Expected 'ok' at path 'status', but got 'error'" in failing.assertions[0].message


def test_suite_runner_provider_exception_handling():
    """Verify runtime exceptions during provider execution are gracefully captured."""
    suite_yaml = """
name: "exception-suite"
provider:
  type: "fixture"
  fixtures:
    known_case: "valid content"
cases:
  - id: "known_case"
    prompt: "Should succeed"
    assertions:
      - type: "exact_match"
        expected: "valid content"
  - id: "missing_case"
    prompt: "Has no fixture match"
    assertions:
      - type: "exact_match"
        expected: "anything"
"""
    result = run_suite(suite_yaml)

    assert result.passed is False
    assert result.total_cases == 2
    assert result.passed_cases == 1
    assert result.failed_cases == 1
    assert result.errored_cases == 1

    errored_case = result.get_case_result("missing_case")
    assert errored_case is not None
    assert errored_case.passed is False
    assert errored_case.error is not None
    assert "FixtureNotFoundError" in errored_case.error
    assert errored_case.response is None


class CustomUppercaseProvider(BaseProvider):
    """Custom mock provider returning uppercase prompts with custom metadata."""
    def __init__(self, prefix: str = "ECHO: ") -> None:
        self.prefix = prefix
        self.call_count = 0

    def generate(
        self,
        prompt: str,
        case_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        self.call_count += 1
        return ProviderResponse(
            content=f"{self.prefix}{prompt.upper()}",
            latency_ms=2.5,
            metadata={"called_with_id": case_id, **(metadata or {})},
        )


def test_suite_runner_custom_provider():
    """Verify execution against an arbitrary custom ProviderProtocol."""
    custom_prov = CustomUppercaseProvider(prefix="PROCESSED: ")
    suite = TestSuite(
        name="custom-provider-suite",
        cases=[
            TestCase(
                id="case_1",
                prompt="hello world",
                metadata={"tag": "unit"},
                assertions=[
                    AssertionConfig(type="contains", expected="PROCESSED: HELLO WORLD"),
                ],
            )
        ],
    )

    runner = SuiteRunner(provider=custom_prov)
    result = runner.run_suite(suite)

    assert result.passed is True
    assert result.total_cases == 1
    assert custom_prov.call_count == 1
    case1 = result.get_case_result("case_1")
    assert case1 is not None
    assert case1.response.metadata.get("called_with_id") == "case_1"
    assert case1.response.metadata.get("tag") == "unit"


def test_suite_runner_input_types(tmp_path: Path):
    """Verify run_suite accepts TestSuite model, YAML file Path, and raw YAML string."""
    yaml_text = """
name: "input-formats-suite"
provider:
  type: "fixture"
  fixtures:
    c1: "pong"
cases:
  - id: "c1"
    prompt: "ping"
    assertions:
      - type: "exact_match"
        expected: "pong"
"""
    # 1. Raw YAML string
    res_str = run_suite(yaml_text)
    assert res_str.passed is True

    # 2. File Path
    file_path = tmp_path / "suite.yaml"
    file_path.write_text(yaml_text, encoding="utf-8")
    res_file = run_suite(file_path)
    assert res_file.passed is True

    # 3. TestSuite model
    model = load_suite_from_string(yaml_text)
    res_model = run_suite(model)
    assert res_model.passed is True


def test_suite_runner_case_without_assertions():
    """A case with no assertions succeeds if provider generates response without error."""
    suite = TestSuite(
        name="no-assertions-suite",
        provider=ProviderConfig(fixtures={"only_case": "output"}),
        cases=[TestCase(id="only_case", prompt="some prompt")],
    )
    result = run_suite(suite)
    assert result.passed is True
    assert result.total_cases == 1
    assert result.total_assertions == 0
    assert result.pass_rate == 100.0
    assert result.assertion_pass_rate == 100.0


def test_suite_runner_unsupported_provider_raises():
    """Verify ValueError raised if provider type is unsupported and no provider supplied."""
    suite = TestSuite(
        name="bad-provider-suite",
        provider=ProviderConfig(type="non_existent_provider_xyz"),
        cases=[TestCase(id="c1", prompt="test")],
    )
    runner = SuiteRunner()
    with pytest.raises(ValueError, match="Unsupported provider type 'non_existent_provider_xyz'"):
        runner.run_suite(suite)


def test_suite_runner_prompt_template_and_vars():
    """Verify suite-level prompt_template is parameterized across multiple cases."""
    suite_yaml = """
name: "parameterized-template-suite"
prompt_template: "Translate '{{ phrase }}' into {{ language }}"
provider:
  type: "fixture"
  fixtures:
    case_fr: "Bonjour"
    case_es: "Hola"
cases:
  - id: "case_fr"
    vars:
      phrase: "Hello"
      language: "French"
    assertions:
      - type: "exact_match"
        expected: "Bonjour"
  - id: "case_es"
    vars:
      phrase: "Hello"
      language: "Spanish"
    assertions:
      - type: "exact_match"
        expected: "Hola"
"""
    result = run_suite(suite_yaml)
    assert result.passed is True
    assert result.total_cases == 2

    case_fr = result.get_case_result("case_fr")
    assert case_fr is not None
    assert case_fr.prompt == "Translate 'Hello' into French"
    assert case_fr.rendered_prompt == "Translate 'Hello' into French"
    assert case_fr.raw_prompt == "Translate '{{ phrase }}' into {{ language }}"

    case_es = result.get_case_result("case_es")
    assert case_es is not None
    assert case_es.prompt == "Translate 'Hello' into Spanish"
    assert case_es.rendered_prompt == "Translate 'Hello' into Spanish"


def test_suite_runner_case_prompt_overrides_suite_template():
    """Verify individual case prompt overrides suite-wide template."""
    suite_yaml = """
name: "override-template-suite"
prompt_template: "Default template: {{ item }}"
provider:
  type: "fixture"
  fixtures:
    case_default: "Default item: Book"
    case_custom: "Custom template for Toy"
cases:
  - id: "case_default"
    vars:
      item: "Book"
    assertions:
      - type: "contains"
        expected: "Book"
  - id: "case_custom"
    prompt: "Custom template for {{ item }}"
    vars:
      item: "Toy"
    assertions:
      - type: "contains"
        expected: "Toy"
"""
    result = run_suite(suite_yaml)
    assert result.passed is True
    c_def = result.get_case_result("case_default")
    c_cust = result.get_case_result("case_custom")
    assert c_def.prompt == "Default template: Book"
    assert c_cust.prompt == "Custom template for Toy"


def test_suite_runner_nested_variables_interpolation():
    """Verify nested dot-notation access in test case variables."""
    suite_yaml = """
name: "nested-vars-suite"
provider:
  type: "fixture"
  fixtures:
    c1: "Processed: Alice with role admin"
cases:
  - id: "c1"
    prompt: "User: {{ user.profile.name }} ({{ user.role }})"
    vars:
      user:
        profile:
          name: "Alice"
        role: "admin"
    assertions:
      - type: "exact_match"
        expected: "Processed: Alice with role admin"
"""
    result = run_suite(suite_yaml)
    assert result.passed is True
    c1 = result.get_case_result("c1")
    assert c1.rendered_prompt == "User: Alice (admin)"


def test_suite_runner_missing_template_variable_error():
    """Verify missing template variable in strict mode records an execution error."""
    suite_yaml = """
name: "missing-var-suite"
provider:
  type: "fixture"
  fixtures:
    c1: "never reached"
cases:
  - id: "c1"
    prompt: "Hello {{ required_var }}"
    vars: {}
"""
    result = run_suite(suite_yaml)
    assert result.passed is False
    assert result.errored_cases == 1
    c1 = result.get_case_result("c1")
    assert c1.passed is False
    assert "UndefinedVariableError" in c1.error
    assert "required_var" in c1.error
    assert c1.rendered_prompt is None


def test_suite_runner_variables_alias_compatibility():
    """Verify both 'vars' and 'variables' dictionary keys are accepted."""
    suite_yaml = """
name: "variables-alias-suite"
provider:
  type: "fixture"
  fixtures:
    c1: "Resolved"
cases:
  - id: "c1"
    prompt: "Value: {{ key }}"
    variables:
      key: "expected_value"
    assertions:
      - type: "exact_match"
        expected: "Resolved"
"""
    result = run_suite(suite_yaml)
    assert result.passed is True
    c1 = result.get_case_result("c1")
    assert c1.rendered_prompt == "Value: expected_value"


def test_offline_performance_success_criterion():
    """Success criterion: 10+ case evaluation suite offline in under 2 seconds."""
    cases = []
    fixtures = {}
    for i in range(15):
        case_id = f"case_{i:02d}"
        payload = {"index": i, "status": "success", "score": 0.95}
        fixtures[case_id] = json.dumps(payload)
        cases.append(
            TestCase(
                id="case_" + f"{i:02d}",
                prompt=f"Test prompt {i}",
                assertions=[
                    AssertionConfig(type="contains", expected="success"),
                    AssertionConfig(type="exact_match", path="index", expected=i),
                    AssertionConfig(
                        type="json_schema",
                        expected={
                            "type": "object",
                            "required": ["index", "status", "score"],
                            "properties": {
                                "index": {"type": "integer"},
                                "status": {"type": "string"},
                                "score": {"type": "number"},
                            },
                        },
                    ),
                ],
            )
        )

    suite = TestSuite(
        name="perf-15-case-suite",
        provider=ProviderConfig(fixtures=fixtures),
        cases=cases,
    )

    runner = SuiteRunner()
    result = runner.run_suite(suite)

    assert result.total_cases == 15
    assert result.passed_cases == 15
    assert result.total_assertions == 45
    assert result.passed is True
    # Strict offline execution time check: must be well under 2000ms
    assert result.duration_ms < 2000.0
