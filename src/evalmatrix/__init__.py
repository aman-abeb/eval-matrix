"""EvalMatrix: Declarative prompt evaluation and regression testing framework."""

from evalmatrix.assertions import (
    AssertionResult,
    BaseAssertionEvaluator,
    ContainsEvaluator,
    ExactMatchEvaluator,
    JsonSchemaEvaluator,
    PathNotFoundError,
    RegexEvaluator,
    evaluate_all,
    evaluate_assertion,
    get_evaluator,
    register_evaluator,
)
from evalmatrix.loader import load_suite_from_string, load_suite_from_yaml
from evalmatrix.models import (
    AssertionConfig,
    AssertionType,
    ProviderConfig,
    ProviderResponse,
    TestCase,
    TestSuite,
)
from evalmatrix.providers.base import BaseProvider, ProviderProtocol
from evalmatrix.providers.fixture import FixtureNotFoundError, FixtureProvider

__all__ = [
    "AssertionConfig",
    "AssertionResult",
    "AssertionType",
    "BaseAssertionEvaluator",
    "BaseProvider",
    "ContainsEvaluator",
    "ExactMatchEvaluator",
    "FixtureNotFoundError",
    "FixtureProvider",
    "JsonSchemaEvaluator",
    "PathNotFoundError",
    "ProviderConfig",
    "ProviderProtocol",
    "ProviderResponse",
    "RegexEvaluator",
    "TestCase",
    "TestSuite",
    "evaluate_all",
    "evaluate_assertion",
    "get_evaluator",
    "load_suite_from_string",
    "load_suite_from_yaml",
    "register_evaluator",
]
__version__ = "0.1.0"
