"""Fixture recording utilities to capture provider responses into reusable offline YAML/JSON fixtures."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Union
import yaml
from pydantic import BaseModel, Field

from evalmatrix.models import ProviderResponse, TestSuite
from evalmatrix.providers.base import BaseProvider, ProviderProtocol
from evalmatrix.providers.fixture import FixtureProvider
from evalmatrix.runner import SuiteResult, SuiteRunner


class RecordedEntry(BaseModel):
    """Container holding captured prompt, response, latency, tokens, and metadata."""

    case_id: Optional[str] = Field(default=None, description="Test case identifier if executed in suite context")
    prompt: str = Field(..., description="Effective prompt string passed to provider")
    content: str = Field(..., description="Generated text content from provider response")
    raw: Optional[Any] = Field(default=None, description="Raw provider response payload")
    latency_ms: float = Field(default=0.0, description="Provider generation latency in milliseconds")
    prompt_tokens: Optional[int] = Field(default=None, description="Prompt token count")
    completion_tokens: Optional[int] = Field(default=None, description="Completion token count")
    total_tokens: Optional[int] = Field(default=None, description="Total token count")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata captured during execution")
    recorded_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO UTC timestamp of recording",
    )

    def to_flat_dict(self) -> Any:
        """Convert entry into flat value suitable for simple fixture mappings."""
        return self.content

    def to_detailed_dict(self) -> Dict[str, Any]:
        """Convert entry into structured dictionary preserving token metrics and metadata."""
        return {
            "__evalmatrix_record__": True,
            "content": self.content,
            "raw": self.raw,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "prompt": self.prompt,
            "metadata": self.metadata,
            "recorded_at": self.recorded_at,
        }


class FixtureRecorder(BaseProvider):
    """Wraps any ProviderProtocol to intercept generation calls and record reusable fixtures."""

    def __init__(    
        self,
        provider: ProviderProtocol,
        key_by: str = "case_id",
        default_latency_ms: Optional[float] = None,
    ) -> None:
        """Initialize FixtureRecorder.

        Args:
            provider: Target provider to wrap and record from.
            key_by: Strategy for indexing entries ('case_id', 'prompt', or 'both').
            default_latency_ms: Optional fallback latency in ms if provider returns 0.0.
        """
        self.provider = provider
        self.key_by = key_by
        self.default_latency_ms = default_latency_ms
        self._records: List[RecordedEntry] = []
        self._records_by_case_id: Dict[str, RecordedEntry] = {}
        self._records_by_prompt: Dict[str, RecordedEntry] = {}

    @property
    def records(self) -> List[RecordedEntry]:
        """Return ordered list of all recorded entries."""
        return list(self._records)

    @property
    def records_by_case_id(self) -> Dict[str, RecordedEntry]:
        """Return mapping of recorded entries indexed by test case ID."""
        return dict(self._records_by_case_id)

    @property
    def records_by_prompt(self) -> Dict[str, RecordedEntry]:
        """Return mapping of recorded entries indexed by prompt string."""
        return dict(self._records_by_prompt)

    def get_record(self, key: str) -> Optional[RecordedEntry]:
        """Retrieve recorded entry by case_id or prompt string."""
        if key in self._records_by_case_id:
            return self._records_by_case_id[key]
        if key in self._records_by_prompt:
            return self._records_by_prompt[key]
        stripped = key.strip()
        if stripped in self._records_by_prompt:
            return self._records_by_prompt[stripped]
        return None

    def clear(self) -> None:
        """Reset all recorded entries."""
        self._records.clear()
        self._records_by_case_id.clear()
        self._records_by_prompt.clear()

    def __len__(self) -> int:
        """Count of entries recorded so far."""
        return len(self._records)

    def generate(
        self,
        prompt: str,
        case_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Intercept provider call, measure duration, store record, and return response."""
        start_time = time.perf_counter()
        response = self.provider.generate(
            prompt=prompt,
            case_id=case_id,
            metadata=metadata,
            **kwargs,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        latency = (
            response.latency_ms
            if response.latency_ms > 0
            else (self.default_latency_ms if self.default_latency_ms is not None else round(elapsed_ms, 2))
        )

        merged_metadata = {**(response.metadata or {}), **(metadata or {})}

        entry = RecordedEntry(
            case_id=case_id,
            prompt=prompt,
            content=response.content,
            raw=response.raw,
            latency_ms=round(latency, 2),
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            metadata=merged_metadata,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )

        self._records.append(entry)
        if case_id:
            self._records_by_case_id[case_id] = entry
        self._records_by_prompt[prompt] = entry
        self._records_by_prompt[prompt.strip()] = entry

        return response

    def to_dict(
        self,
        format: str = "flat",
        key_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Export recorded fixtures to a dictionary suitable for FixtureProvider.

        Args:
            format: 'flat' for direct content string, 'detailed' for rich record dict.
            key_by: Indexing key ('case_id', 'prompt', or 'both'). Defaults to self.key_by.

        Returns:
            Dictionary mapping keys to fixture contents or record objects.
        """
        effective_key_by = (key_by or self.key_by).lower()
        out: Dict[str, Any] = {}

        for entry in self._records:
            val = entry.to_detailed_dict() if format.lower() == "detailed" else entry.to_flat_dict()

            if effective_key_by == "prompt":
                out[entry.prompt] = val
            elif effective_key_by == "both":
                if entry.case_id:
                    out[entry.case_id] = val
                out[entry.prompt] = val
            else:
                # Default to case_id with prompt fallback
                k = entry.case_id if entry.case_id else entry.prompt
                out[k] = val

        return out

    def to_yaml(
        self,
        format: str = "flat",
        key_by: Optional[str] = None,
    ) -> str:
        """Serialize recorded fixtures to a YAML formatted string."""
        data = self.to_dict(format=format, key_by=key_by)
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

    def to_json(
        self,
        format: str = "flat",
        key_by: Optional[str] = None,
        indent: int = 2,
    ) -> str:
        """Serialize recorded fixtures to a JSON formatted string."""
        data = self.to_dict(format=format, key_by=key_by)
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def save(
        self,
        path: Union[str, Path],
        format: str = "flat",
        merge: bool = False,
        key_by: Optional[str] = None,
        indent: int = 2,
    ) -> Path:
        """Save recorded fixtures to a YAML or JSON file with optional merge mode.

        In merge mode (merge=True), unrecorded existing keys in the target file are
        preserved, while updated and new keys are merged into place.

        Args:
            path: Destination file path (.yaml, .yml, or .json).
            format: Fixture content format ('flat' or 'detailed').
            merge: Whether to merge with existing file if it already exists.
            key_by: Fixture key indexing strategy ('case_id', 'prompt', or 'both').
            indent: Indentation spaces for JSON formatting.

        Returns:
            Resolved Path to the saved fixture file.
        """
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        new_fixtures = self.to_dict(format=format, key_by=key_by)
        is_json = file_path.suffix.lower() == ".json"

        if merge and file_path.is_file():
            content = file_path.read_text(encoding="utf-8").strip()
            existing_data: Dict[str, Any] = {}
            if content:
                try:
                    if is_json:
                        existing_data = json.loads(content)
                    else:
                        existing_data = yaml.safe_load(content) or {}
                except Exception:
                    existing_data = {}

            if isinstance(existing_data, dict):
                if "fixtures" in existing_data and isinstance(existing_data["fixtures"], dict):
                    existing_data["fixtures"].update(new_fixtures)
                    merged_data = existing_data
                elif "cases" in existing_data and isinstance(existing_data["cases"], dict):
                    existing_data["cases"].update(new_fixtures)
                    merged_data = existing_data
                else:
                    merged_data = {**existing_data, **new_fixtures}
            else:
                merged_data = new_fixtures
        else:
            merged_data = new_fixtures

        if is_json:
            file_path.write_text(json.dumps(merged_data, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            file_path.write_text(yaml.safe_dump(merged_data, sort_keys=False, allow_unicode=True), encoding="utf-8")

        return file_path

    def export_yaml(
        self,
        path: Union[str, Path],
        format: str = "flat",
        merge: bool = False,
        key_by: Optional[str] = None,
    ) -> Path:
        """Export fixtures to YAML file."""
        return self.save(path=path, format=format, merge=merge, key_by=key_by)

    def export_json(
        self,
        path: Union[str, Path],
        format: str = "flat",
        merge: bool = False,
        key_by: Optional[str] = None,
        indent: int = 2,
    ) -> Path:
        """Export fixtures to JSON file."""
        p = Path(path)
        if p.suffix.lower() != ".json":
            p = p.with_suffix(".json")
        return self.save(path=p, format=format, merge=merge, key_by=key_by, indent=indent)

    def as_fixture_provider(
        self,
        format: str = "flat",
        key_by: Optional[str] = None,
    ) -> FixtureProvider:
        """Create a FixtureProvider pre-populated with currently recorded entries."""
        fixtures = self.to_dict(format=format, key_by=key_by)
        return FixtureProvider(fixtures=fixtures)


class SuiteRecordResult(NamedTuple):
    """Named tuple containing both suite execution results and the recorder instance."""

    suite_result: SuiteResult
    recorder: FixtureRecorder


def record_suite(
    suite: Union[TestSuite, Path, str],
    provider: ProviderProtocol,
    output_path: Optional[Union[str, Path]] = None,
    key_by: str = "case_id",
    format: str = "flat",
    merge: bool = False,
    base_dir: Optional[Union[str, Path]] = None,
    strict_templates: bool = True,
) -> SuiteRecordResult:
    """Execute an evaluation suite with a recording wrapper and optionally export fixtures.

    Args:
        suite: TestSuite instance, filesystem Path to YAML suite, or raw YAML string.
        provider: Provider instance to record live responses from.
        output_path: Optional destination file path (.yaml or .json) to write recorded fixtures.
        key_by: Indexing strategy for fixture keys ('case_id', 'prompt', or 'both').
        format: Fixture content format ('flat' or 'detailed').
        merge: Whether to merge into existing fixture file instead of overwriting.
        base_dir: Optional base directory for resolving relative paths.
        strict_templates: Whether missing template variables raise errors.

    Returns:
        SuiteRecordResult tuple of (suite_result, recorder).
    """
    recorder = FixtureRecorder(provider=provider, key_by=key_by)
    runner = SuiteRunner(provider=recorder, base_dir=base_dir, strict_templates=strict_templates)
    suite_result = runner.run_suite(suite=suite, base_dir=base_dir)

    if output_path is not None:
        recorder.save(output_path, format=format, merge=merge, key_by=key_by)

    return SuiteRecordResult(suite_result=suite_result, recorder=recorder)
