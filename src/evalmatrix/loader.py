"""YAML and dictionary suite loader for EvalMatrix."""

from pathlib import Path
from typing import Any, Dict, Optional, Union
import yaml
from pydantic import ValidationError

from evalmatrix.models import TestSuite


class SuiteLoadError(Exception):
    """Raised when loading or validating a test suite fails."""
    pass


def load_suite_from_string(yaml_content: str, base_dir: Optional[Path] = None) -> TestSuite:
    """Parse and validate a TestSuite from a YAML string.

    Args:
        yaml_content: Raw YAML string defining the test suite.
        base_dir: Optional base directory for resolving relative paths.

    Returns:
        Validated TestSuite instance.

    Raises:
        SuiteLoadError: If YAML parsing fails or schema validation fails.
    """
    if not yaml_content.strip():
        raise SuiteLoadError("Provided YAML content is empty.")

    try:
        raw_data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as err:
        raise SuiteLoadError(f"Failed to parse YAML syntax: {err}") from err

    if not isinstance(raw_data, dict):
        raise SuiteLoadError(f"Root element of suite must be a dictionary, got {type(raw_data).__name__}")

    return _parse_suite_dict(raw_data, base_dir=base_dir)


def load_suite_from_yaml(file_path: Union[str, Path]) -> TestSuite:
    """Read and validate a TestSuite from a YAML file path.

    Args:
        file_path: Path to the YAML suite file.

    Returns:
        Validated TestSuite instance.

    Raises:
        SuiteLoadError: If the file cannot be read, parsed, or validated.
    """
    path = Path(file_path)
    if not path.is_file():
        raise SuiteLoadError(f"Suite file does not exist: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as err:
        raise SuiteLoadError(f"Failed to read suite file {path}: {err}") from err

    return load_suite_from_string(text, base_dir=path.parent)


def _parse_suite_dict(data: Dict[str, Any], base_dir: Optional[Path] = None) -> TestSuite:
    """Convert dictionary data into a validated TestSuite model."""
    try:
        suite = TestSuite.model_validate(data)
    except ValidationError as err:
        errors = err.errors()
        error_messages = [
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in errors
        ]
        raise SuiteLoadError(
            f"Validation failed for suite schema:\n" + "\n".join(f"  - {msg}" for msg in error_messages)
        ) from err

    # Validate uniqueness of test case IDs
    seen_ids = set()
    for case in suite.cases:
        if case.id in seen_ids:
            raise SuiteLoadError(f"Duplicate test case id '{case.id}' found in suite '{suite.name}'.")
        seen_ids.add(case.id)

    # If fixture_file is defined, check relative to base_dir if base_dir provided
    if suite.provider.fixture_file and base_dir:
        fixture_path = Path(suite.provider.fixture_file)
        if not fixture_path.is_absolute():
            resolved_path = base_dir / fixture_path
            if not resolved_path.exists():
                raise SuiteLoadError(
                    f"Configured fixture file not found: {resolved_path} (resolved from {base_dir})"
                )

    return suite
