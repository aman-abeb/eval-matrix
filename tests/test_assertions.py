"""Unit tests for EvalMatrix assertion evaluators and path traversal."""

import json
import pytest

from evalmatrix.assertions import (
    AssertionResult,
    ContainsEvaluator,
    ExactMatchEvaluator,
    JsonSchemaEvaluator,
    PathNotFoundError,
    RegexEvaluator,
    SimilarityEvaluator,
    TokenBudgetEvaluator,
    evaluate_all,
    evaluate_assertion,
    get_evaluator,
    register_evaluator,
    resolve_path,
)
from evalmatrix.models import AssertionConfig, AssertionType, ProviderResponse


# --- Path resolution tests ---

def test_resolve_path_empty_and_root():
    data = {"user": "alice"}
    assert resolve_path(data, None) == data
    assert resolve_path(data, "") == data
    assert resolve_path(data, "$") == data
    assert resolve_path(data, "$.user") == "alice"


def test_resolve_path_nested_and_indexed():
    data = {
        "orders": [
            {"id": "ord_1", "items": [{"name": "keyboard", "price": 79.99}]},
            {"id": "ord_2", "items": [{"name": "mouse", "price": 29.99}]},
        ]
    }
    assert resolve_path(data, "orders[0].id") == "ord_1"
    assert resolve_path(data, "orders[1].items[0].name") == "mouse"
    assert resolve_path(data, "orders.1.items.0.price") == 29.99


def test_resolve_path_missing_key_raises():
    data = {"user": {"profile": {}}}
    with pytest.raises(PathNotFoundError, match="Key 'address' not found"):
        resolve_path(data, "user.profile.address.city")


def test_resolve_path_index_out_of_range():
    data = {"items": [1, 2]}
    with pytest.raises(PathNotFoundError, match="Index 5 out of range"):
        resolve_path(data, "items[5]")


# --- ExactMatchEvaluator tests ---

def test_exact_match_string_pass():
    evaluator = ExactMatchEvaluator()
    config = AssertionConfig(type="exact_match", expected="hello world")
    result = evaluator.evaluate("hello world", config)
    assert result.passed is True
    assert bool(result) is True
    assert "succeeded" in result.message


def test_exact_match_string_fail():
    evaluator = ExactMatchEvaluator()
    config = AssertionConfig(type="exact_match", expected="expected text")
    result = evaluator.evaluate("actual text", config)
    assert result.passed is False
    assert result.actual == "actual text"
    assert result.expected == "expected text"


def test_exact_match_json_dict():
    evaluator = ExactMatchEvaluator()
    config = AssertionConfig(type="exact_match", expected={"status": "ok", "code": 200})
    response_text = '{"status": "ok", "code": 200}'
    result = evaluator.evaluate(response_text, config)
    assert result.passed is True


def test_exact_match_with_path():
    evaluator = ExactMatchEvaluator()
    config = AssertionConfig(type="exact_match", path="intent.category", expected="billing")
    response_json = '{"intent": {"category": "billing", "confidence": 0.99}}'
    result = evaluator.evaluate(response_json, config)
    assert result.passed is True
    assert result.actual == "billing"


def test_exact_match_with_missing_path():
    evaluator = ExactMatchEvaluator()
    config = AssertionConfig(type="exact_match", path="intent.category", expected="billing")
    response_json = '{"intent": {"other": 1}}'
    result = evaluator.evaluate(response_json, config)
    assert result.passed is False
    assert "not found" in result.message


# --- ContainsEvaluator tests ---

def test_contains_substring_pass():
    evaluator = ContainsEvaluator()
    config = AssertionConfig(type="contains", expected="refund")
    result = evaluator.evaluate("Please process my refund immediately.", config)
    assert result.passed is True
    assert "Found expected element/substring" in result.message


def test_contains_substring_fail():
    evaluator = ContainsEvaluator()
    config = AssertionConfig(type="contains", expected="refund")
    result = evaluator.evaluate("Where is my receipt?", config)
    assert result.passed is False


def test_contains_with_path_in_list():
    evaluator = ContainsEvaluator()
    config = AssertionConfig(type="contains", path="tags", expected="priority")
    response = '{"tags": ["billing", "priority", "urgent"]}'
    result = evaluator.evaluate(response, config)
    assert result.passed is True


def test_contains_with_path_in_list_fail():
    evaluator = ContainsEvaluator()
    config = AssertionConfig(type="contains", path="tags", expected="marketing")
    response = '{"tags": ["billing", "urgent"]}'
    result = evaluator.evaluate(response, config)
    assert result.passed is False


# --- RegexEvaluator tests ---

def test_regex_pass():
    evaluator = RegexEvaluator()
    config = AssertionConfig(type="regex", expected=r"order #\d{4,6}")
    result = evaluator.evaluate("Tracking for order #54321 is active", config)
    assert result.passed is True
    assert result.actual == "order #54321"


def test_regex_fail():
    evaluator = RegexEvaluator()
    config = AssertionConfig(type="regex", expected=r"order #\d{4,6}")
    result = evaluator.evaluate("No order number provided here", config)
    assert result.passed is False


def test_regex_with_path():
    evaluator = RegexEvaluator()
    config = AssertionConfig(type="regex", path="ticket.id", expected=r"^TCK-\d+$")
    response = '{"ticket": {"id": "TCK-9901"}}'
    result = evaluator.evaluate(response, config)
    assert result.passed is True


def test_regex_invalid_pattern():
    evaluator = RegexEvaluator()
    config = AssertionConfig(type="regex", expected="[unclosed bracket")
    result = evaluator.evaluate("any text", config)
    assert result.passed is False
    assert "Invalid regex pattern" in result.message


# --- JsonSchemaEvaluator tests ---

SCHEMA_INTENT = {
    "type": "object",
    "required": ["intent", "confidence"],
    "properties": {
        "intent": {"type": "string", "enum": ["billing", "refund", "support"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}


def test_json_schema_pass():
    evaluator = JsonSchemaEvaluator()
    config = AssertionConfig(type="json_schema", expected=SCHEMA_INTENT)
    response = '{"intent": "billing", "confidence": 0.95, "tags": ["invoice"]}'
    result = evaluator.evaluate(response, config)
    assert result.passed is True
    assert result.error_details == []


def test_json_schema_markdown_code_fenced():
    evaluator = JsonSchemaEvaluator()
    config = AssertionConfig(type="json_schema", expected=SCHEMA_INTENT)
    response = """```json
{
  "intent": "refund",
  "confidence": 0.88
}
```"""
    result = evaluator.evaluate(response, config)
    assert result.passed is True


def test_json_schema_missing_required_property():
    evaluator = JsonSchemaEvaluator()
    config = AssertionConfig(type="json_schema", expected=SCHEMA_INTENT)
    response = '{"intent": "billing"}'
    result = evaluator.evaluate(response, config)
    assert result.passed is False
    assert len(result.error_details) > 0
    assert any("confidence" in err for err in result.error_details)


def test_json_schema_type_mismatch():
    evaluator = JsonSchemaEvaluator()
    config = AssertionConfig(type="json_schema", expected=SCHEMA_INTENT)
    response = '{"intent": 123, "confidence": 0.9}'
    result = evaluator.evaluate(response, config)
    assert result.passed is False
    assert any("intent" in err for err in result.error_details)


def test_json_schema_enum_violation():
    evaluator = JsonSchemaEvaluator()
    config = AssertionConfig(type="json_schema", expected=SCHEMA_INTENT)
    response = '{"intent": "unknown_intent", "confidence": 0.9}'
    result = evaluator.evaluate(response, config)
    assert result.passed is False
    assert any("unknown_intent" in err for err in result.error_details)


def test_json_schema_numeric_bounds():
    evaluator = JsonSchemaEvaluator()
    config = AssertionConfig(type="json_schema", expected=SCHEMA_INTENT)
    response = '{"intent": "refund", "confidence": 1.5}'
    result = evaluator.evaluate(response, config)
    assert result.passed is False
    assert any("confidence" in err for err in result.error_details)


def test_json_schema_additional_properties_violation():
    evaluator = JsonSchemaEvaluator()
    config = AssertionConfig(type="json_schema", expected=SCHEMA_INTENT)
    response = '{"intent": "billing", "confidence": 0.9, "rogue_field": "bad"}'
    result = evaluator.evaluate(response, config)
    assert result.passed is False
    assert any("rogue_field" in err for err in result.error_details)


def test_json_schema_invalid_json_response():
    evaluator = JsonSchemaEvaluator()
    config = AssertionConfig(type="json_schema", expected=SCHEMA_INTENT)
    result = evaluator.evaluate("not a json text {[", config)
    assert result.passed is False
    assert "not valid JSON" in result.message


def test_json_schema_with_path():
    schema_user = {
        "type": "object",
        "required": ["id", "email"],
        "properties": {
            "id": {"type": "integer"},
            "email": {"type": "string"},
        },
    }
    evaluator = JsonSchemaEvaluator()
    config = AssertionConfig(type="json_schema", path="data.user", expected=schema_user)
    response = '{"data": {"user": {"id": 42, "email": "user@example.com"}}}'
    result = evaluator.evaluate(response, config)
    assert result.passed is True


def test_json_schema_string_expected_schema():
    evaluator = JsonSchemaEvaluator()
    schema_str = json.dumps({"type": "object", "required": ["status"]})
    config = AssertionConfig(type="json_schema", expected=schema_str)
    result = evaluator.evaluate('{"status": "active"}', config)
    assert result.passed is True


# --- SimilarityEvaluator tests ---

def test_similarity_exact_pass():
    evaluator = SimilarityEvaluator()
    config = AssertionConfig(type="similarity", expected="hello world", threshold=0.9)
    result = evaluator.evaluate("hello world", config)
    assert result.passed is True
    assert result.actual == 1.0
    assert result.expected == 0.9
    assert "meets or exceeds" in result.message


def test_similarity_minor_drift_pass():
    evaluator = SimilarityEvaluator()
    # 1 char edit out of 11 chars -> ratio > 0.85
    config = AssertionConfig(type="similarity", expected="hello world", threshold=0.8)
    result = evaluator.evaluate("hello word", config)
    assert result.passed is True
    assert result.actual >= 0.8


def test_similarity_drift_failure_detailed():
    evaluator = SimilarityEvaluator()
    config = AssertionConfig(
        type="similarity",
        expected="The package was delivered to your front porch",
        threshold=0.85,
    )
    result = evaluator.evaluate("No package found anywhere", config)
    assert result.passed is False
    assert result.actual < 0.85
    assert "below threshold" in result.message
    assert len(result.error_details) == 3


def test_similarity_target_alias_and_metric_options():
    evaluator = SimilarityEvaluator()
    config = AssertionConfig(
        type="similarity",
        target="invoice payment received",
        metric="jaccard",
        threshold=0.4,
    )
    result = evaluator.evaluate("invoice payment processed", config)
    assert result.passed is True
    assert "jaccard" in result.message


def test_similarity_with_path():
    evaluator = SimilarityEvaluator()
    config = AssertionConfig(
        type="similarity",
        path="summary.text",
        expected="User requested account cancellation",
        threshold=0.8,
    )
    response = '{"summary": {"text": "User requested account cancellation."}}'
    result = evaluator.evaluate(response, config)
    assert result.passed is True


def test_similarity_missing_target():
    evaluator = SimilarityEvaluator()
    config = AssertionConfig(type="similarity")
    result = evaluator.evaluate("some text", config)
    assert result.passed is False
    assert "requires an 'expected' or 'target'" in result.message


# --- TokenBudgetEvaluator tests ---

def test_token_budget_total_pass():
    evaluator = TokenBudgetEvaluator()
    config = AssertionConfig(type="token_budget", max_tokens=50, scope="total")
    resp = ProviderResponse(
        content="Short response",
        prompt_tokens=10,
        completion_tokens=15,
        total_tokens=25,
    )
    result = evaluator.evaluate(resp, config)
    assert result.passed is True
    assert result.actual == 25
    assert result.expected == 50
    assert "within budget" in result.message


def test_token_budget_total_exceeded():
    evaluator = TokenBudgetEvaluator()
    config = AssertionConfig(type="token_budget", max_tokens=20, scope="total")
    resp = ProviderResponse(
        content="Lengthy response",
        prompt_tokens=15,
        completion_tokens=15,
        total_tokens=30,
    )
    result = evaluator.evaluate(resp, config)
    assert result.passed is False
    assert result.actual == 30
    assert result.expected == 20
    assert "exceeded budget" in result.message
    assert len(result.error_details) == 4
    assert any("Overage: 10 tokens" in err for err in result.error_details)


def test_token_budget_completion_scope():
    evaluator = TokenBudgetEvaluator()
    config = AssertionConfig(type="token_budget", max_tokens=10, scope="completion")
    resp = ProviderResponse(
        content="Four words text",
        prompt_tokens=50,
        completion_tokens=5,
    )
    result = evaluator.evaluate(resp, config)
    assert result.passed is True
    assert result.actual == 5


def test_token_budget_prompt_scope():
    evaluator = TokenBudgetEvaluator()
    config = AssertionConfig(type="token_budget", max_tokens=30, scope="prompt")
    resp = ProviderResponse(
        content="Any text",
        prompt_tokens=35,
        completion_tokens=2,
    )
    result = evaluator.evaluate(resp, config)
    assert result.passed is False
    assert result.actual == 35


def test_token_budget_heuristic_estimation_fallback():
    evaluator = TokenBudgetEvaluator()
    config = AssertionConfig(type="token_budget", max_tokens=20)
    # Plain string response with no provider token metrics
    result = evaluator.evaluate("This is a brief text under twenty tokens.", config)
    assert result.passed is True
    assert result.actual > 0
    assert result.actual <= 20


def test_token_budget_invalid_scope():
    evaluator = TokenBudgetEvaluator()
    config = AssertionConfig(type="token_budget", max_tokens=20, scope="invalid_scope")
    result = evaluator.evaluate("test", config)
    assert result.passed is False
    assert "Invalid token budget scope" in result.message


def test_token_budget_missing_limit():
    evaluator = TokenBudgetEvaluator()
    config = AssertionConfig(type="token_budget")
    result = evaluator.evaluate("test", config)
    assert result.passed is False
    assert "requires 'max_tokens' or 'expected' limit" in result.message


# --- Dispatcher and multi-assertion tests ---

def test_evaluate_all_with_similarity_and_budget():
    assertions = [
        AssertionConfig(type="similarity", expected="Status OK", threshold=0.7),
        AssertionConfig(type="token_budget", max_tokens=20),
    ]
    resp = ProviderResponse(content="Status: OK", prompt_tokens=2, completion_tokens=3)
    results = evaluate_all(resp, assertions)
    assert len(results) == 2
    assert results[0].passed is True
    assert results[1].passed is True


def test_evaluate_assertion_unknown_type():
    config = AssertionConfig(type="unsupported_type", expected="foo")
    result = evaluate_assertion("some text", config)
    assert result.passed is False
    assert "Unsupported assertion type" in result.message


def test_custom_evaluator_registration():
    from evalmatrix.assertions import BaseAssertionEvaluator

    class UpperCaseEvaluator(BaseAssertionEvaluator):
        assertion_type = "is_uppercase"
        def evaluate(self, response, config):
            text = str(response.content if isinstance(response, ProviderResponse) else response)
            passed = text.isupper()
            return AssertionResult(
                passed=passed,
                assertion_type=self.assertion_type,
                message="Text is uppercase" if passed else "Text is not uppercase",
            )

    register_evaluator("is_uppercase", UpperCaseEvaluator)
    config = AssertionConfig(type="is_uppercase")
    assert evaluate_assertion("HELLO WORLD", config).passed is True
    assert evaluate_assertion("Hello World", config).passed is False
