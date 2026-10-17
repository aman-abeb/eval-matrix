"""Data models for EvalMatrix suites, test cases, assertions, and responses."""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, model_validator


class AssertionType(str, Enum):
    """Supported assertion evaluation types."""
    EXACT_MATCH = "exact_match"
    CONTAINS = "contains"
    REGEX = "regex"
    JSON_SCHEMA = "json_schema"
    SIMILARITY = "similarity"
    TOKEN_BUDGET = "token_budget"


class AssertionConfig(BaseModel):
    """Specification for an assertion executed against a provider response."""
    type: Union[AssertionType, str] = Field(
        ...,
        description="Type of assertion to execute (e.g. exact_match, json_schema, contains)",
    )
    expected: Optional[Any] = Field(
        default=None,
        description="Expected value, substring, regex pattern, or JSON schema object",
    )
    path: Optional[str] = Field(
        default=None,
        description="Optional dot-notation or JSONPath target in structured JSON responses",
    )
    threshold: Optional[float] = Field(
        default=None,
        description="Threshold score for fuzzy or metric comparisons (e.g. 0.0 to 1.0)",
    )
    description: Optional[str] = Field(
        default=None,
        description="Human-readable label explaining the assertion requirement",
    )


class ProviderConfig(BaseModel):
    """Configuration for LLM or offline test execution provider."""
    type: str = Field(
        default="fixture",
        description="Provider backend identifier (e.g. fixture, openai, mock)",
    )
    model: Optional[str] = Field(
        default=None,
        description="LLM model name if using a remote or local model backend",
    )
    temperature: Optional[float] = Field(
        default=0.0,
        description="Sampling temperature for generative runs",
    )
    max_tokens: Optional[int] = Field(
        default=None,
        description="Maximum generation token budget",
    )
    fixture_file: Optional[str] = Field(
        default=None,
        description="Path to external JSON or YAML file containing fixture responses",
    )
    fixtures: Dict[str, Any] = Field(
        default_factory=dict,
        description="Inline mapping of case_id or prompt strings to expected responses",
    )
    options: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary provider-specific extra options",
    )


class ProviderResponse(BaseModel):
    """Standardized response output from a prompt evaluation provider."""
    content: str = Field(..., description="The generated text or serialized JSON string")
    raw: Optional[Any] = Field(default=None, description="Underlying provider raw payload")
    latency_ms: float = Field(default=0.0, description="Execution latency in milliseconds")
    prompt_tokens: Optional[int] = Field(default=None, description="Prompt token usage count")
    completion_tokens: Optional[int] = Field(default=None, description="Completion token usage count")
    total_tokens: Optional[int] = Field(default=None, description="Total token usage count")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional response metadata")

    @model_validator(mode="after")
    def calculate_total_tokens(self) -> "ProviderResponse":
        """Ensure total_tokens is set if prompt and completion tokens are provided."""
        if self.total_tokens is None:
            if self.prompt_tokens is not None or self.completion_tokens is not None:
                self.total_tokens = (self.prompt_tokens or 0) + (self.completion_tokens or 0)
        return self


class TestCase(BaseModel):
    """Individual test case specification within an evaluation suite."""
    id: str = Field(..., description="Unique alphanumeric identifier for this test case")
    name: Optional[str] = Field(default=None, description="Descriptive title for test reporting")
    description: Optional[str] = Field(default=None, description="Detailed explanation of scenario")
    prompt: str = Field(..., description="Prompt text or prompt template")
    variables: Dict[str, Any] = Field(
        default_factory=dict,
        description="Template variable substitutions for dynamic prompts",
    )
    assertions: List[AssertionConfig] = Field(
        default_factory=list,
        description="Ordered list of assertions to validate against the response",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary tags, categories, or notes",
    )
    fixture_response: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None,
        description="Direct offline response override for this specific test case",
    )


class TestSuite(BaseModel):
    """Declarative evaluation suite holding test cases and execution configuration."""
    name: str = Field(..., description="Identifier or name of the test suite")
    description: Optional[str] = Field(default=None, description="Description of evaluation scope")
    provider: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(type="fixture"),
        description="Provider configuration used for test case execution",
    )
    cases: List[TestCase] = Field(default_factory=list, description="List of test cases in this suite")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Suite metadata and tags")

    def get_case(self, case_id: str) -> Optional[TestCase]:
        """Lookup a test case by its unique id."""
        for case in self.cases:
            if case.id == case_id:
                return case
        return None
