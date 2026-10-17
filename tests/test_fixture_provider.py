"""Unit tests for FixtureProvider and BaseProvider resolution in evalmatrix.providers."""

import json
import pytest
from pathlib import Path

from evalmatrix.models import ProviderConfig, ProviderResponse, TestCase
from evalmatrix.providers.base import BaseProvider, ProviderProtocol
from evalmatrix.providers.fixture import FixtureNotFoundError, FixtureProvider


def test_fixture_provider_protocol_conformance():
    """Verify FixtureProvider conforms to runtime ProviderProtocol."""
    provider = FixtureProvider()
    assert isinstance(provider, ProviderProtocol)
    assert isinstance(provider, BaseProvider)


def test_fixture_resolution_by_case_id():
    """Verify lookup prioritized by test case ID."""
    fixtures = {
        "test_case_1": "Response from case ID",
        "prompt text": "Response from prompt",
    }
    provider = FixtureProvider(fixtures=fixtures)
    resp = provider.generate(prompt="prompt text", case_id="test_case_1")
    assert resp.content == "Response from case ID"
    assert resp.metadata["matched_case_id"] == "test_case_1"
    assert resp.prompt_tokens is not None
    assert resp.completion_tokens is not None
    assert resp.total_tokens == resp.prompt_tokens + resp.completion_tokens


def test_fixture_resolution_by_prompt():
    """Verify lookup falls back to prompt match when case_id not found."""
    fixtures = {
        "hello world": "Hello human!",
    }
    provider = FixtureProvider(fixtures=fixtures)
    resp = provider.generate(prompt="hello world", case_id="unknown_case")
    assert resp.content == "Hello human!"


def test_fixture_resolution_by_stripped_prompt():
    """Verify lookup strips leading/trailing whitespace on prompt fallback."""
    fixtures = {
        "query with space": "Answer with space",
    }
    provider = FixtureProvider(fixtures=fixtures)
    resp = provider.generate(prompt="  query with space  \n")
    assert resp.content == "Answer with space"


def test_fixture_resolution_dict_serialization():
    """Verify structured dictionary fixtures are serialized to pretty JSON."""
    data = {"status": "ok", "items": [1, 2, 3]}
    provider = FixtureProvider(fixtures={"test_json": data})
    resp = provider.generate(prompt="get json", case_id="test_json")
    assert resp.raw == data
    parsed = json.loads(resp.content)
    assert parsed == data


def test_fixture_not_found_raises():
    """Verify FixtureNotFoundError is raised when no matching key exists."""
    provider = FixtureProvider(fixtures={"alpha": "one"})
    with pytest.raises(FixtureNotFoundError, match="No fixture match found for case_id='beta'"):
        provider.generate(prompt="beta prompt", case_id="beta")


def test_fixture_fallback_when_not_found():
    """Verify fallback string returned if configured."""
    provider = FixtureProvider(fixtures={}, fallback="default fallback response")
    resp = provider.generate(prompt="unknown query", case_id="unknown_id")
    assert resp.content == "default fallback response"


def test_from_config_merges_inline_and_suite_cases(tmp_path: Path):
    """Verify from_config correctly aggregates provider fixtures and case overrides."""
    # Create external fixture file
    fixture_file = tmp_path / "fixtures.json"
    fixture_file.write_text(json.dumps({"from_file": "file_val"}), encoding="utf-8")

    config = ProviderConfig(
        type="fixture",
        fixture_file="fixtures.json",
        fixtures={"from_inline": "inline_val"},
        options={"fallback": "config_fallback", "latency_ms": 5.0},
    )

    case_override = TestCase(
        id="case_with_direct_override",
        prompt="Prompt text",
        fixture_response="direct_override_val",
    )

    provider = FixtureProvider.from_config(
        config=config,
        base_dir=tmp_path,
        suite_cases=[case_override],
    )

    # Test resolution of all sources
    assert provider.generate(prompt="", case_id="from_file").content == "file_val"
    assert provider.generate(prompt="", case_id="from_inline").content == "inline_val"
    assert provider.generate(prompt="", case_id="case_with_direct_override").content == "direct_override_val"
    assert provider.generate(prompt="missing", case_id="missing").content == "config_fallback"


def test_set_fixture_dynamically():
    """Verify dynamically registering fixtures on instance."""
    provider = FixtureProvider()
    provider.set_fixture("dynamic_case", "dynamic_val")
    resp = provider.generate(prompt="p", case_id="dynamic_case")
    assert resp.content == "dynamic_val"
