# EvalMatrix

<!-- builder:badges:start -->
[![CI](https://github.com/aman-abeb/eval-matrix/actions/workflows/ci.yml/badge.svg)](https://github.com/aman-abeb/eval-matrix/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white) ![License: MIT](https://img.shields.io/badge/license-MIT-green)
<!-- builder:badges:end -->


Declarative prompt evaluation and regression testing CLI with offline fixtures, schema assertions, and terminal diffs.

## Features

- **Declarative YAML Test Suites**: Specify prompts, test variables, expectations, and assertions in clean, version-controllable YAML files.
- **Zero-Network Offline Fixture Provider**: Execute comprehensive regression test suites deterministically in milliseconds without API keys or remote calls.
- **Unified Suite Runner Engine**: Orchestrate test cases, capture latency, aggregate assertion outcomes, and calculate pass/fail rates.
- **Strict Typed Schemas**: Built on Pydantic v2 to validate test suites, provider configurations, and response metadata.
- **Comprehensive Assertion Evaluators**: Deterministic validators for `exact_match`, `contains`, `regex`, and strict `json_schema` with JSON path traversal.
- **Granular Schema Error Paths**: Pinpoint exact field paths (`$.user.email`, `$.items[0].id`) on validation failures.
- **Extensible Architecture**: Clean provider protocols and assertion registries supporting custom evaluators.

## Quickstart

### Installation

```bash
# Install in editable mode with dependencies
pip install -e .

# Or install via requirements.txt
pip install -r requirements.txt
```

### Running EvalMatrix

Run the built-in CLI demo or inspection entrypoint:

```bash
python main.py
```

Or execute using the module syntax:

```bash
python -m evalmatrix.main --help
```

## Example

Define a declarative evaluation suite in YAML (`suite.yaml`):

```yaml
name: "customer-support-intent-eval"
description: "Tests intent extraction against customer queries"
provider:
  type: "fixture"
  fixtures:
    billing_inquiry: '{"intent": "billing", "confidence": 0.98}'
    refund_request: '{"intent": "refund", "confidence": 0.94}'
cases:
  - id: "billing_inquiry"
    name: "Billing question routing"
    prompt: "Classify user intent: Why was I charged $49 on May 1st?"
    assertions:
      - type: "exact_match"
        expected: '{"intent": "billing", "confidence": 0.98}'
      - type: "json_schema"
        expected:
          type: "object"
          required: ["intent", "confidence"]
          properties:
            intent: {type: "string", enum: ["billing", "refund"]}
            confidence: {type: "number", minimum: 0.0, maximum: 1.0}
  - id: "refund_request"
    name: "Refund request classification"
    prompt: "Classify user intent: I need my money back for order #123."
    assertions:
      - type: "contains"
        expected: "refund"
```

Execute programmatic loading and evaluation via `run_suite`:

```python
from evalmatrix import run_suite

result = run_suite("suite.yaml")
status = "PASS" if result.passed else "FAIL"
print(f"[{status}] {result.suite_name} -> {result.passed_cases}/{result.total_cases} cases passed in {result.duration_ms:.1f}ms")
for case in result.case_results:
    print(f"  - {case.case_id}: {case.passed_assertions}/{case.total_assertions} assertions passed")
```

Sample Output:

```text
[PASS] customer-support-intent-eval -> 2/2 cases passed in 3.4ms
  - billing_inquiry: 2/2 assertions passed
  - refund_request: 1/1 assertions passed
```

## How It Works

1. **Suite Loader (`evalmatrix.loader`)**: Reads YAML files and validates test cases, variable inputs, and provider settings into strongly typed `TestSuite` models.
2. **Provider Protocol (`evalmatrix.providers.base`)**: Implements an extensible runtime interface (`ProviderProtocol` & `BaseProvider`) that decouples prompt generation from evaluation logic.
3. **Fixture Provider (`evalmatrix.providers.fixture`)**: Resolves prompt responses offline through case IDs, direct inline responses, or static fixture dictionaries with simulated token metrics and zero network latency.
4. **Assertion Engine (`evalmatrix.assertions`)**: Validates model output against exact matches, substring containment, regex patterns, or strict JSON schemas with path traversal and granular error path reporting.
5. **Evaluation Suite Runner (`evalmatrix.runner`)**: Executes test cases against providers, captures generation latency and execution duration, isolates runtime exceptions, and aggregates summary metrics.

## Running Tests

Run the test suite offline with `pytest`:

```bash
pytest tests -v
```

<!-- builder:roadmap:start -->
## Status

**In active development:** 1 of 3 milestones done.

## Roadmap

- [x] **Core Runner, Provider Interface, and Schema Assertions**: Implement the extensible LLM Provider protocol, an offline FixtureProvider, YAML suite parsing, and strict JSON Schema and exact-match validators with full unit test coverage.
- [ ] **Fuzzy Evaluators, Token Budgets, and Prompt Templating**: Add Jinja-style prompt variable interpolation, character n-gram similarity scoring, token budget constraint checks, and fixture recording utilities.
- [ ] **Rich CLI, CI Markdown Exporter, and Realistic Extraction Demo**: Build the Typer CLI with interactive colored matrix outputs, failure inspection diffs, markdown CI reporting, and a turnkey customer-support extraction evaluation demo.
<!-- builder:roadmap:end -->
