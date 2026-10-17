# EvalMatrix

<!-- builder:badges:start -->
[![CI](https://github.com/aman-abeb/eval-matrix/actions/workflows/ci.yml/badge.svg)](https://github.com/aman-abeb/eval-matrix/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white) ![License: MIT](https://img.shields.io/badge/license-MIT-green)
<!-- builder:badges:end -->


Declarative prompt evaluation and regression testing CLI with offline fixtures, schema assertions, and terminal diffs.

## Features

- **Declarative YAML Test Suites**: Specify prompts, test variables, expectations, and assertions in clean, version-controllable YAML files.
- **Zero-Network Offline Fixture Provider**: Execute comprehensive regression test suites deterministically in milliseconds without API keys or remote calls.
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

Execute programmatic loading, fixture resolution, and assertion validation:

```python
from evalmatrix.loader import load_suite_from_yaml
from evalmatrix.providers.fixture import FixtureProvider
from evalmatrix.assertions import evaluate_all

suite = load_suite_from_yaml("suite.yaml")
provider = FixtureProvider.from_config(suite.provider, suite_cases=suite.cases)

for case in suite.cases:
    response = provider.generate(prompt=case.prompt, case_id=case.id)
    results = evaluate_all(response, case.assertions)
    status = "PASS" if all(r.passed for r in results) else "FAIL"
    print(f"[{status}] {case.id} -> {len(results)} assertions checked")
```

Sample Output:

```text
[PASS] billing_inquiry -> 2 assertions checked
[PASS] refund_request -> 1 assertions checked
```

## How It Works

1. **Suite Loader (`evalmatrix.loader`)**: Reads YAML files and validates test cases, variable inputs, and provider settings into strongly typed `TestSuite` models.
2. **Provider Protocol (`evalmatrix.providers.base`)**: Implements an extensible runtime interface (`ProviderProtocol` & `BaseProvider`) that decouples prompt generation from evaluation logic.
3. **Fixture Provider (`evalmatrix.providers.fixture`)**: Resolves prompt responses offline through case IDs, direct inline responses, or static fixture dictionaries with simulated token metrics and zero network latency.
4. **Assertion Engine (`evalmatrix.assertions`)**: Validates model output against exact matches, substring containment, regex patterns, or strict JSON schemas with path traversal and granular error path reporting.

## Running Tests

Run the test suite offline with `pytest`:

```bash
pytest tests -v
```

<!-- builder:roadmap:start -->
## Status

**In active development:** 0 of 3 milestones done.

## Roadmap

- [ ] **Core Runner, Provider Interface, and Schema Assertions**: Implement the extensible LLM Provider protocol, an offline FixtureProvider, YAML suite parsing, and strict JSON Schema and exact-match validators with full unit test coverage.
- [ ] **Fuzzy Evaluators, Token Budgets, and Prompt Templating**: Add Jinja-style prompt variable interpolation, character n-gram similarity scoring, token budget constraint checks, and fixture recording utilities.
- [ ] **Rich CLI, CI Markdown Exporter, and Realistic Extraction Demo**: Build the Typer CLI with interactive colored matrix outputs, failure inspection diffs, markdown CI reporting, and a turnkey customer-support extraction evaluation demo.
<!-- builder:roadmap:end -->
