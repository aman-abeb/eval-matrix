"""EvalMatrix: Declarative prompt evaluation and regression testing framework."""

from evalmatrix.models import (
    AssertionConfig,
    AssertionType,
    ProviderConfig,
    ProviderResponse,
    TestCase,
    TestSuite,
)
from evalmatrix.loader import load_suite_from_string, load_suite_from_yaml
from evalmatrix.providers.base import BaseProvider, ProviderProtocol
from evalmatrix.providers.fixture import FixtureNotFoundError, FixtureProvider

__all__ = [
    "AssertionConfig",
    "AssertionType",
    "BaseProvider",
    "FixtureNotFoundError",
    "FixtureProvider",
    "ProviderConfig",
    "ProviderProtocol",
    "ProviderResponse",
    "TestCase",
    "TestSuite",
    "load_suite_from_string",
    "load_suite_from_yaml",
]
__version__ = "0.1.0"
