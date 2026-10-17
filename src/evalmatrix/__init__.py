"""EvalMatrix: Declarative prompt evaluation and regression testing framework."""

from evalmatrix.assertions import (
    AssertionResult,
    BaseAssertionEvaluator,
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
)
from evalmatrix.diff import (
    format_diff_markdown,
    generate_unified_diff,
    render_diff_panel,
    render_text_diff,
)
from evalmatrix.loader import load_suite_from_string, load_suite_from_yaml
from evalmatrix.metrics import (
    compute_similarity,
    estimate_prompt_and_completion_tokens,
    estimate_token_count,
    get_character_ngrams,
    get_word_ngrams,
    jaccard_similarity,
    levenshtein_distance,
    levenshtein_similarity,
    ngram_dice_similarity,
)
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
from evalmatrix.recorder import (
    FixtureRecorder,
    RecordedEntry,
    SuiteRecordResult,
    record_suite,
)
from evalmatrix.reporter import (
    export_markdown_report,
    generate_markdown_report,
    render_terminal_matrix,
)
from evalmatrix.runner import CaseResult, SuiteResult, SuiteRunner, run_suite
from evalmatrix.templating import (
    TemplateRenderError,
    UndefinedVariableError,
    extract_template_variables,
    render_template,
)

__all__ = [
    "AssertionConfig",
    "AssertionResult",
    "AssertionType",
    "BaseAssertionEvaluator",
    "BaseProvider",
    "CaseResult",
    "ContainsEvaluator",
    "ExactMatchEvaluator",
    "FixtureNotFoundError",
    "FixtureProvider",
    "FixtureRecorder",
    "JsonSchemaEvaluator",
    "PathNotFoundError",
    "ProviderConfig",
    "ProviderProtocol",
    "ProviderResponse",
    "RecordedEntry",
    "RegexEvaluator",
    "SimilarityEvaluator",
    "SuiteRecordResult",
    "SuiteResult",
    "SuiteRunner",
    "TestCase",
    "TestSuite",
    "TemplateRenderError",
    "TokenBudgetEvaluator",
    "UndefinedVariableError",
    "compute_similarity",
    "estimate_prompt_and_completion_tokens",
    "estimate_token_count",
    "evaluate_all",
    "evaluate_assertion",
    "export_markdown_report",
    "extract_template_variables",
    "format_diff_markdown",
    "generate_markdown_report",
    "generate_unified_diff",
    "get_character_ngrams",
    "get_evaluator",
    "get_word_ngrams",
    "jaccard_similarity",
    "levenshtein_distance",
    "levenshtein_similarity",
    "load_suite_from_string",
    "load_suite_from_yaml",
    "ngram_dice_similarity",
    "record_suite",
    "register_evaluator",
    "render_diff_panel",
    "render_template",
    "render_terminal_matrix",
    "render_text_diff",
    "run_suite",
]
__version__ = "0.1.0"
