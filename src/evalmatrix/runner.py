"""Evaluation suite runner orchestrating test cases, providers, and assertion checks."""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from evalmatrix.assertions import AssertionResult, evaluate_all
from evalmatrix.loader import load_suite_from_string, load_suite_from_yaml
from evalmatrix.models import ProviderResponse, TestCase, TestSuite
from evalmatrix.providers.base import ProviderProtocol
from evalmatrix.providers.fixture import FixtureProvider
from evalmatrix.templating import render_template


class CaseResult(BaseModel):
    """Evaluation outcome for a single test case."""
    case_id: str = Field(..., description="Unique test case identifier")
    case_name: Optional[str] = Field(default=None, description="Descriptive case name")
    passed: bool = Field(..., description="Whether all assertions passed with no runtime errors")
    error: Optional[str] = Field(default=None, description="Exception or error message if execution failed")
    duration_ms: float = Field(default=0.0, description="Total execution duration in milliseconds")
    latency_ms: float = Field(default=0.0, description="Provider response generation latency in milliseconds")
    prompt: str = Field(..., description="Effective prompt string submitted to provider")
    rendered_prompt: Optional[str] = Field(default=None, description="Rendered prompt string after template interpolation")
    raw_prompt: Optional[str] = Field(default=None, description="Original unrendered prompt template")
    response: Optional[ProviderResponse] = Field(default=None, description="Underlying provider response")
    assertions: List[AssertionResult] = Field(default_factory=list, description="Evaluated assertion results")

    @property
    def total_assertions(self) -> int:
        """Total number of assertions executed on this case."""
        return len(self.assertions)

    @property
    def passed_assertions(self) -> int:
        """Count of assertions that passed."""
        return sum(1 for a in self.assertions if a.passed)

    @property
    def failed_assertions(self) -> int:
        """Count of assertions that failed."""
        return sum(1 for a in self.assertions if not a.passed)


class SuiteResult(BaseModel):
    """Aggregated outcome for an entire evaluation suite run."""
    suite_name: str = Field(..., description="Evaluation suite name")
    passed: bool = Field(..., description="Whether all cases passed without errors")
    total_cases: int = Field(default=0, description="Total number of evaluated test cases")
    passed_cases: int = Field(default=0, description="Count of passed test cases")
    failed_cases: int = Field(default=0, description="Count of failed test cases")
    errored_cases: int = Field(default=0, description="Count of cases encountering runtime exceptions")
    total_assertions: int = Field(default=0, description="Total assertions executed across all cases")
    passed_assertions: int = Field(default=0, description="Total assertions passed")
    failed_assertions: int = Field(default=0, description="Total assertions failed")
    duration_ms: float = Field(default=0.0, description="Total suite execution duration in milliseconds")
    case_results: List[CaseResult] = Field(default_factory=list, description="Individual test case results")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata from suite run")

    @property
    def pass_rate(self) -> float:
        """Percentage of test cases that passed (0.0 to 100.0)."""
        if self.total_cases == 0:
            return 100.0
        return (self.passed_cases / self.total_cases) * 100.0

    @property
    def assertion_pass_rate(self) -> float:
        """Percentage of assertions that passed (0.0 to 100.0)."""
        if self.total_assertions == 0:
            return 100.0
        return (self.passed_assertions / self.total_assertions) * 100.0

    def get_case_result(self, case_id: str) -> Optional[CaseResult]:
        """Retrieve evaluation result for a specific case ID."""
        for res in self.case_results:
            if res.case_id == case_id:
                return res
        return None


class SuiteRunner:
    """Executes test cases against configured providers and aggregates assertion outcomes."""

    def __init__(
        self,
        provider: Optional[ProviderProtocol] = None,
        base_dir: Optional[Union[str, Path]] = None,
        strict_templates: bool = True,
    ) -> None:
        """Initialize the suite runner.

        Args:
            provider: Optional default provider instance. If not provided, constructed
                      from TestSuite.provider configuration.
            base_dir: Optional base directory to resolve relative fixture file paths.
            strict_templates: Whether missing template variables raise execution errors.
        """
        self.provider = provider
        self.base_dir = Path(base_dir) if base_dir else None
        self.strict_templates = strict_templates

    def _resolve_provider(
        self,
        suite: TestSuite,
        override_provider: Optional[ProviderProtocol] = None,
        base_dir: Optional[Path] = None,
    ) -> ProviderProtocol:
        """Determine the provider instance to use for the suite run."""
        if override_provider is not None:
            return override_provider
        if self.provider is not None:
            return self.provider

        effective_base_dir = base_dir or self.base_dir
        provider_type = suite.provider.type.lower()

        if provider_type == "fixture":
            return FixtureProvider.from_config(
                suite.provider,
                base_dir=effective_base_dir,
                suite_cases=suite.cases,
            )

        raise ValueError(
            f"Unsupported provider type '{suite.provider.type}'. "
            f"Supply an explicit ProviderProtocol implementation to SuiteRunner."
        )

    def run_case(
        self,
        case: TestCase,
        provider: ProviderProtocol,
        default_template: Optional[str] = None,
    ) -> CaseResult:
        """Execute a single test case against the given provider and evaluate assertions.

        Renders template variables prior to calling the provider.

        Args:
            case: The TestCase definition.
            provider: The target evaluation provider.
            default_template: Optional suite-level prompt template if case.prompt is None.

        Returns:
            CaseResult with assertion evaluations and latency metrics.
        """
        start_time = time.perf_counter()
        raw_template = case.prompt or default_template

        if not raw_template:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return CaseResult(
                case_id=case.id,
                case_name=case.name,
                passed=False,
                error=f"ValueError: Case '{case.id}' has no prompt and no suite-level prompt_template is defined.",
                duration_ms=round(elapsed_ms, 2),
                latency_ms=0.0,
                prompt="",
                rendered_prompt=None,
                raw_prompt=None,
                response=None,
                assertions=[],
            )

        try:
            # Interpolate prompt variables
            vars_map = case.get_variables()
            rendered_prompt = render_template(
                raw_template,
                vars_map,
                strict=self.strict_templates,
            )

            response = provider.generate(
                prompt=rendered_prompt,
                case_id=case.id,
                metadata={**(case.metadata or {}), "raw_prompt": raw_template},
            )
            eval_results = evaluate_all(response, case.assertions)
            passed = all(r.passed for r in eval_results)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            return CaseResult(
                case_id=case.id,
                case_name=case.name,
                passed=passed,
                error=None,
                duration_ms=round(elapsed_ms, 2),
                latency_ms=round(response.latency_ms, 2),
                prompt=rendered_prompt,
                rendered_prompt=rendered_prompt,
                raw_prompt=raw_template,
                response=response,
                assertions=eval_results,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return CaseResult(
                case_id=case.id,
                case_name=case.name,
                passed=False,
                error=f"{type(exc).__name__}: {str(exc)}",
                duration_ms=round(elapsed_ms, 2),
                latency_ms=0.0,
                prompt=raw_template,
                rendered_prompt=None,
                raw_prompt=raw_template,
                response=None,
                assertions=[],
            )

    def run_suite(
        self,
        suite: Union[TestSuite, Path, str],
        provider: Optional[ProviderProtocol] = None,
        base_dir: Optional[Union[str, Path]] = None,
    ) -> SuiteResult:
        """Execute all cases in a suite and aggregate comprehensive statistics.

        Args:
            suite: TestSuite model instance, filesystem Path, or raw YAML string.
            provider: Optional provider override.
            base_dir: Optional base directory for relative fixture paths.

        Returns:
            SuiteResult with pass/fail counts, duration, and detailed case results.
        """
        start_suite_time = time.perf_counter()
        effective_base_dir = Path(base_dir) if base_dir else self.base_dir

        # Resolve suite input into TestSuite instance
        if isinstance(suite, Path):
            effective_base_dir = effective_base_dir or suite.parent
            actual_suite = load_suite_from_yaml(suite)
        elif isinstance(suite, str):
            is_file = False
            looks_like_path = ("\n" not in suite) and (
                suite.strip().endswith((".yaml", ".yml", ".json")) or "/" in suite or "\\" in suite
            )
            if "\n" not in suite and len(suite) < 1024:
                try:
                    p = Path(suite)
                    is_file = p.is_file()
                except OSError:
                    is_file = False
            if is_file or (looks_like_path and "\n" not in suite):
                p = Path(suite)
                effective_base_dir = effective_base_dir or p.parent
                actual_suite = load_suite_from_yaml(p)
            else:
                actual_suite = load_suite_from_string(suite, base_dir=effective_base_dir)
        elif isinstance(suite, TestSuite):
            actual_suite = suite
        else:
            raise TypeError(f"Expected TestSuite, Path, or str, got {type(suite).__name__}")

        resolved_provider = self._resolve_provider(
            actual_suite,
            override_provider=provider,
            base_dir=effective_base_dir,
        )

        case_results: List[CaseResult] = []
        for case in actual_suite.cases:
            case_res = self.run_case(
                case,
                resolved_provider,
                default_template=actual_suite.prompt_template,
            )
            case_results.append(case_res)

        total_cases = len(case_results)
        passed_cases = sum(1 for c in case_results if c.passed)
        errored_cases = sum(1 for c in case_results if c.error is not None)
        failed_cases = total_cases - passed_cases

        total_assertions = sum(c.total_assertions for c in case_results)
        passed_assertions = sum(c.passed_assertions for c in case_results)
        failed_assertions = sum(c.failed_assertions for c in case_results)
        total_duration_ms = (time.perf_counter() - start_suite_time) * 1000.0

        suite_passed = (failed_cases == 0 and errored_cases == 0)

        return SuiteResult(
            suite_name=actual_suite.name,
            passed=suite_passed,
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            errored_cases=errored_cases,
            total_assertions=total_assertions,
            passed_assertions=passed_assertions,
            failed_assertions=failed_assertions,
            duration_ms=round(total_duration_ms, 2),
            case_results=case_results,
            metadata=dict(actual_suite.metadata),
        )


def run_suite(
    suite: Union[TestSuite, Path, str],
    provider: Optional[ProviderProtocol] = None,
    base_dir: Optional[Union[str, Path]] = None,
) -> SuiteResult:
    """Convenience function to instantiate SuiteRunner and execute a suite.

    Args:
        suite: TestSuite model, file path to YAML suite, or raw YAML string.
        provider: Optional provider implementation.
        base_dir: Optional base directory to resolve relative fixture file paths.

    Returns:
        SuiteResult with structured summary statistics and assertion details.
    """
    runner = SuiteRunner(provider=provider, base_dir=base_dir)
    return runner.run_suite(suite=suite, provider=provider, base_dir=base_dir)
