"""Unit tests for EvalMatrix fixture recording utilities and round-trip replay."""

import json
from pathlib import Path
from typing import Any, Dict, Optional
import pytest
import yaml

from evalmatrix.models import ProviderResponse
from evalmatrix.providers.base import BaseProvider
from evalmatrix.providers.fixture import FixtureProvider
from evalmatrix.recorder import FixtureRecorder, RecordedEntry, record_suite
from evalmatrix.runner import run_suite


class DummyProvider(BaseProvider):
    """Synthetic deterministic provider simulating dynamic LLM generation."""

    def __init__(self, responses: Optional[Dict[str, str]] = None) -> None:
        self.responses = responses or {}
        self.call_count = 0

    def generate(
        self,
        prompt: str,
        case_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        self.call_count += 1
        content = self.responses.get(case_id or "", self.responses.get(prompt, f"Echo: {prompt}"))
        return ProviderResponse(
            content=content,
            latency_ms=12.5,
            prompt_tokens=len(prompt) // 3 + 1,
            completion_tokens=len(content) // 3 + 1,
            metadata={"call_index": self.call_count, "model": "synthetic-v1"},
        )


def test_recorder_intercepts_generate_and_records():
    """Verify FixtureRecorder intercepts calls and populates RecordedEntry."""
    dummy = DummyProvider({"case_1": "{\"intent\": \"refund\"}"})
    recorder = FixtureRecorder(dummy)

    resp = recorder.generate(prompt="Refund inquiry", case_id="case_1", metadata={"tag": "support"})

    assert resp.content == "{\"intent\": \"refund\"}"
    assert resp.latency_ms == 12.5
    assert len(recorder) == 1

    rec = recorder.records[0]
    assert rec.case_id == "case_1"
    assert rec.prompt == "Refund inquiry"
    assert rec.content == "{\"intent\": \"refund\"}"
    assert rec.latency_ms == 12.5
    assert rec.prompt_tokens == resp.prompt_tokens
    assert rec.completion_tokens == resp.completion_tokens
    assert rec.metadata["tag"] == "support" or rec.metadata.get("model") == "synthetic-v1"
    assert rec.recorded_at is not None


def test_recorder_indexing_strategies():
    """Verify indexing by case_id, prompt, and both."""
    dummy = DummyProvider()
    recorder = FixtureRecorder(dummy, key_by="case_id")

    recorder.generate(prompt="Prompt A", case_id="case_a")
    recorder.generate(prompt="Prompt B", case_id="case_b")

    # Lookup via get_record
    assert recorder.get_record("case_a") is not None
    assert recorder.get_record("Prompt A") is not None
    assert recorder.get_record("nonexistent") is None

    # to_dict flat with case_id
    flat_cases = recorder.to_dict(format="flat", key_by="case_id")
    assert set(flat_cases.keys()) == {"case_a", "case_b"}

    # to_dict flat with prompt
    flat_prompts = recorder.to_dict(format="flat", key_by="prompt")
    assert set(flat_prompts.keys()) == {"Prompt A", "Prompt B"}

    # to_dict with both
    flat_both = recorder.to_dict(format="flat", key_by="both")
    assert set(flat_both.keys()) == {"case_a", "case_b", "Prompt A", "Prompt B"}


def test_recorder_serialization_flat_and_detailed():
    """Verify to_yaml and to_json for flat and detailed formats."""
    dummy = DummyProvider({"login_case": "User logged in successfully"})
    recorder = FixtureRecorder(dummy)
    recorder.generate(prompt="User logs in", case_id="login_case")

    # Flat YAML
    yaml_flat = recorder.to_yaml(format="flat")
    parsed_yaml = yaml.safe_load(yaml_flat)
    assert parsed_yaml == {"login_case": "User logged in successfully"}

    # Detailed JSON
    json_det = recorder.to_json(format="detailed", indent=2)
    parsed_json = json.loads(json_det)
    assert "login_case" in parsed_json
    entry_data = parsed_json["login_case"]
    assert entry_data["__evalmatrix_record__"] is True
    assert entry_data["content"] == "User logged in successfully"
    assert entry_data["latency_ms"] == 12.5
    assert entry_data["prompt"] == "User logs in"


def test_recorder_save_and_export_files(tmp_path: Path):
    """Verify file saving to YAML and JSON destinations."""
    dummy = DummyProvider({"t1": "res1", "t2": "res2"})
    recorder = FixtureRecorder(dummy)
    recorder.generate(prompt="p1", case_id="t1")
    recorder.generate(prompt="p2", case_id="t2")

    yaml_dest = tmp_path / "fixtures" / "saved.yaml"
    saved_path = recorder.export_yaml(yaml_dest)
    assert saved_path.is_file()
    content_yaml = yaml.safe_load(saved_path.read_text(encoding="utf-8"))
    assert content_yaml == {"t1": "res1", "t2": "res2"}

    json_dest = tmp_path / "fixtures" / "saved.json"
    saved_json_path = recorder.export_json(json_dest)
    assert saved_json_path.is_file()
    content_json = json.loads(saved_json_path.read_text(encoding="utf-8"))
    assert content_json == {"t1": "res1", "t2": "res2"}


def test_recorder_merge_mode_preserves_unrecorded(tmp_path: Path):
    """Verify merge mode updates existing entries without dropping unrecorded ones."""
    dest = tmp_path / "existing_fixtures.yaml"
    initial_data = {
        "case_stable": "stable old value",
        "case_to_update": "initial value",
    }
    dest.write_text(yaml.safe_dump(initial_data), encoding="utf-8")

    dummy = DummyProvider({
        "case_to_update": "updated new value",
        "case_brand_new": "brand new value",
    })
    recorder = FixtureRecorder(dummy)
    recorder.generate(prompt="p1", case_id="case_to_update")
    recorder.generate(prompt="p2", case_id="case_brand_new")

    # Save with merge=True
    recorder.save(dest, merge=True)

    merged = yaml.safe_load(dest.read_text(encoding="utf-8"))
    # Unrecorded preserved
    assert merged["case_stable"] == "stable old value"
    # Updated value overwritten
    assert merged["case_to_update"] == "updated new value"
    # New value added
    assert merged["case_brand_new"] == "brand new value"


def test_recorder_merge_with_nested_fixtures_wrapper(tmp_path: Path):
    """Verify merge mode respects top-level 'fixtures' block if present in target file."""
    dest = tmp_path / "wrapped_fixtures.json"
    initial_data = {
        "version": 1,
        "fixtures": {
            "old_key": "old_value",
        },
    }
    dest.write_text(json.dumps(initial_data), encoding="utf-8")

    dummy = DummyProvider({"new_key": "new_val"})
    recorder = FixtureRecorder(dummy)
    recorder.generate(prompt="p", case_id="new_key")

    recorder.save(dest, merge=True)

    loaded = json.loads(dest.read_text(encoding="utf-8"))
    assert loaded["version"] == 1
    assert loaded["fixtures"]["old_key"] == "old_value"
    assert loaded["fixtures"]["new_key"] == "new_val"


def test_recorder_as_fixture_provider_in_memory():
    """Verify instant in-memory replay via as_fixture_provider()."""
    dummy = DummyProvider({"inquiry": "Billing response details"})
    recorder = FixtureRecorder(dummy)
    recorder.generate(prompt="Where is my bill?", case_id="inquiry")

    fixture_provider = recorder.as_fixture_provider()
    assert isinstance(fixture_provider, FixtureProvider)

    replayed_resp = fixture_provider.generate(prompt="Any prompt", case_id="inquiry")
    assert replayed_resp.content == "Billing response details"


def test_record_suite_and_roundtrip_offline_replay(tmp_path: Path):
    """End-to-end integration: record live suite to YAML, then execute offline with zero network."""
    suite_yaml = """
name: "customer-support-eval"
prompt_template: "Process user ticket: {{ message }}"
cases:
  - id: "ticket_refund"
    vars:
      message: "I want my $50 back."
    assertions:
      - type: "exact_match"
        expected: '{"action": "refund", "amount": 50}'
      - type: "contains"
        expected: "refund"
  - id: "ticket_greeting"
    vars:
      message: "Hello there!"
    assertions:
      - type: "similarity"
        expected: "Welcome to customer support! How can I help you today?"
        threshold: 0.8
"""

    dummy_live_llm = DummyProvider({
        "ticket_refund": '{"action": "refund", "amount": 50}',
        "ticket_greeting": "Welcome to customer support! How can I help you today?",
    })

    fixture_file = tmp_path / "captured_fixtures.yaml"

    # 1. Record suite execution
    suite_result, recorder = record_suite(
        suite=suite_yaml,
        provider=dummy_live_llm,
        output_path=fixture_file,
        format="flat",
    )

    assert suite_result.passed is True
    assert suite_result.total_cases == 2
    assert len(recorder) == 2
    assert fixture_file.is_file()

    # 2. Configure offline suite referencing captured fixture file
    offline_suite_yaml = f"""
name: "offline-customer-support-eval"
prompt_template: "Process user ticket: {{{{ message }}}}"
provider:
  type: "fixture"
  fixture_file: "{fixture_file.as_posix()}"
cases:
  - id: "ticket_refund"
    vars:
      message: "I want my $50 back."
    assertions:
      - type: "exact_match"
        expected: '{{"action": "refund", "amount": 50}}'
  - id: "ticket_greeting"
    vars:
      message: "Hello there!"
    assertions:
      - type: "similarity"
        expected: "Welcome to customer support! How can I help you today?"
        threshold: 0.8
"""

    # 3. Replay completely offline with no custom provider passed
    offline_result = run_suite(offline_suite_yaml, base_dir=tmp_path)

    assert offline_result.passed is True
    assert offline_result.passed_cases == 2
    assert offline_result.passed_assertions == 2


def test_detailed_format_roundtrip_retains_token_metrics(tmp_path: Path):
    """Verify detailed format records and reloads prompt/completion token metrics."""
    dummy = DummyProvider({"case_detail": "Structured classification output"})
    recorder = FixtureRecorder(dummy)
    recorder.generate(prompt="Classify: query", case_id="case_detail")

    dest_yaml = tmp_path / "detailed.yaml"
    recorder.save(dest_yaml, format="detailed")

    # Load via FixtureProvider
    provider = FixtureProvider.from_config(
        config=type("Config", (), {"fixture_file": str(dest_yaml), "fixtures": {}, "options": {}})(),
        base_dir=tmp_path,
    )

    resp = provider.generate(prompt="Any", case_id="case_detail")
    assert resp.content == "Structured classification output"
    assert resp.prompt_tokens is not None
    assert resp.completion_tokens is not None
    assert resp.latency_ms == 12.5


def test_recorder_clear_and_len():
    """Verify clear() method cleans records."""
    dummy = DummyProvider()
    recorder = FixtureRecorder(dummy)
    assert len(recorder) == 0
    recorder.generate(prompt="p1")
    assert len(recorder) == 1
    recorder.clear()
    assert len(recorder) == 0
    assert recorder.records == []
