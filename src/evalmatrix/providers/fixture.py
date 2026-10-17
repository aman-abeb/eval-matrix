"""Deterministic offline fixture provider for zero-latency, network-free evaluation."""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union
import yaml

from evalmatrix.models import ProviderConfig, ProviderResponse, TestCase
from evalmatrix.providers.base import BaseProvider


class FixtureNotFoundError(KeyError):
    """Raised when a requested prompt or case ID has no configured fixture response."""
    pass


class FixtureProvider(BaseProvider):
    """Offline provider that resolves responses from in-memory maps or fixture files.

    Resolution order:
    1. Direct test case fixture override (if provided).
    2. Match by exact `case_id`.
    3. Match by exact `prompt` text.
    4. Match by normalized prompt (stripped whitespace).
    5. Match by raw unrendered prompt template (from metadata).
    6. Fallback response (if configured).
    """

    def __init__(
        self,
        fixtures: Optional[Dict[str, Any]] = None,
        fallback: Optional[str] = None,
        default_latency_ms: float = 1.5,
    ) -> None:
        """Initialize the FixtureProvider with a dictionary of fixtures.

        Args:
            fixtures: Dictionary mapping case IDs or prompt strings to response contents.
            fallback: Optional default string to return if no key matches.
            default_latency_ms: Simulated execution latency in milliseconds.
        """
        self._fixtures: Dict[str, Any] = fixtures or {}
        self.fallback = fallback
        self.default_latency_ms = default_latency_ms

    @classmethod
    def from_config(
        cls,
        config: ProviderConfig,
        base_dir: Optional[Path] = None,
        suite_cases: Optional[Iterable[TestCase]] = None,
    ) -> "FixtureProvider":
        """Construct a FixtureProvider from a ProviderConfig and optional test cases.

        Args:
            config: Provider configuration containing inline fixtures or file paths.
            base_dir: Base directory used to resolve relative fixture file paths.
            suite_cases: Optional iterable of TestCase objects containing inline fixtures.

        Returns:
            Configured FixtureProvider instance.
        """
        fixtures: Dict[str, Any] = {}

        # 1. Load from external fixture file if specified
        if config.fixture_file:
            file_path = Path(config.fixture_file)
            if base_dir and not file_path.is_absolute():
                file_path = base_dir / file_path
            loaded = cls._load_fixture_file(file_path)
            fixtures.update(loaded)

        # 2. Add inline fixtures from ProviderConfig
        if config.fixtures:
            fixtures.update(config.fixtures)

        # 3. Add test case specific inline fixtures
        if suite_cases:
            for case in suite_cases:
                if case.fixture_response is not None:
                    fixtures[case.id] = case.fixture_response

        fallback = config.options.get("fallback")
        latency = float(config.options.get("latency_ms", 1.5))
        return cls(fixtures=fixtures, fallback=fallback, default_latency_ms=latency)

    @staticmethod
    def _load_fixture_file(path: Path) -> Dict[str, Any]:
        """Load key-value fixtures from a JSON or YAML file."""
        if not path.is_file():
            raise FileNotFoundError(f"Fixture file not found: {path}")

        content = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content)
        elif suffix == ".json":
            data = json.loads(content)
        else:
            # Try JSON first, fallback to YAML
            try:
                data = json.loads(content)
            except Exception:
                data = yaml.safe_load(content)

        if not isinstance(data, dict):
            raise ValueError(f"Fixture file must contain a key-value mapping, got {type(data).__name__}")
        return data

    def set_fixture(self, key: str, response: Union[str, Dict[str, Any]]) -> None:
        """Register or update a fixture entry."""
        self._fixtures[key] = response

    def generate(
        self,
        prompt: str,
        case_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Resolve fixture content for a given test case or prompt."""
        resolved_val: Optional[Any] = None

        # Step 1: Check direct case_id
        if case_id and case_id in self._fixtures:
            resolved_val = self._fixtures[case_id]

        # Step 2: Check exact prompt
        elif prompt in self._fixtures:
            resolved_val = self._fixtures[prompt]

        # Step 3: Check stripped prompt
        elif prompt.strip() in self._fixtures:
            resolved_val = self._fixtures[prompt.strip()]

        # Step 4: Check raw prompt template from metadata if present
        elif metadata and metadata.get("raw_prompt") in self._fixtures:
            resolved_val = self._fixtures[metadata["raw_prompt"]]

        # Step 5: Fallback if configured
        elif self.fallback is not None:
            resolved_val = self.fallback

        # Step 6: Fail if not found
        else:
            id_info = f"case_id='{case_id}'" if case_id else "no case_id"
            snippet = (prompt[:40] + "...") if len(prompt) > 40 else prompt
            raise FixtureNotFoundError(
                f"No fixture match found for {id_info} or prompt: {snippet!r}. "
                f"Available fixture keys: {list(self._fixtures.keys())}"
            )

        # Format value into string content
        if isinstance(resolved_val, (dict, list)):
            content_str = json.dumps(resolved_val, indent=2)
        else:
            content_str = str(resolved_val)

        # Estimate token counts (approx 4 chars per token)
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(content_str) // 4)

        return ProviderResponse(
            content=content_str,
            raw=resolved_val,
            latency_ms=self.default_latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            metadata={
                "provider": "fixture",
                "matched_case_id": case_id,
                **(metadata or {}),
            },
        )
