# EvalMatrix

<!-- builder:badges:start -->
[![CI](https://github.com/aman-abeb/eval-matrix/actions/workflows/ci.yml/badge.svg)](https://github.com/aman-abeb/eval-matrix/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white) ![License: MIT](https://img.shields.io/badge/license-MIT-green)
<!-- builder:badges:end -->

Declarative prompt evaluation and regression testing CLI with offline fixtures, schema assertions, and terminal diffs.

## Features

- **Declarative YAML Test Suites**: Specify prompts, parameterized templates, test variables, expectations, and assertions in clean, version-controllable YAML files.
- **Interactive Rich CLI**: Typer-powered terminal interface featuring colored evaluation matrices, per-case latency metrics, and token consumption breakdowns.
- **Terminal Regression Diffs**: Visual line and word diffs for text drift and structured JSON regressions with instant highlighted feedback.
- **CI Markdown Exporter**: Automated GitHub Actions Step Summary reports (`$GITHUB_STEP_SUMMARY`) with collapsible failure diffs and native CI exit codes.
- **Prompt Variable Interpolation Engine**: Parameterize prompts with `{{ var }}` syntax, nested dot-notation (`{{ user.profile.name }}`), list indexing (`{{ items.0 }}`), and fallback filters (`{{ var | default('fallback') }}`).
- **Strict Typed Schemas**: Built on Pydantic v2 and JSON Schema draft validation with exact error path reporting (`$.entities.order_id`).
- **Fuzzy Text Similarity Assertions**: Detect prompt output drift using normalized Levenshtein ratio, character n-gram Jaccard overlap, and Sørensen–Dice multiset coefficients.
- **Token Budget Bounds Constraints**: Guard against cost regression and verbose drift by validating `prompt`, `completion`, or `total` token consumption limits.
- **Zero-Network Offline Fixture Provider**: Execute comprehensive 10+ case suites deterministically in milliseconds without remote API keys or network calls.
- **Fixture Recording**: Seamlessly record live provider outputs directly into reusable YAML/JSON fixtures with `--merge` support.

## Quickstart

### Installation

```bash
# Install in editable mode with dependencies
pip install -e .

# Or install via requirements.txt
pip install -r requirements.txt
```

### Running EvalMatrix

Run the built-in CLI self-test demo:

```bash
evalmatrix run
```

Execute the 12-case customer-support extraction evaluation suite:

```bash
evalmatrix run examples/customer_support_extraction.yaml
```

Export a GitHub Actions CI Markdown report:

```bash
evalmatrix run examples/customer_support_extraction.yaml --output-markdown summary.md
```

Inspect a specific test case in detail with highlighted prompt and response panels:

```bash
evalmatrix inspect examples/customer_support_extraction.yaml case_01_billing_dispute
```

Record evaluation responses into a new fixture file:

```bash
evalmatrix record examples/customer_support_extraction.yaml --output examples/recorded_fixtures.yaml
```

## Example

Define an evaluation suite in YAML (`customer_support_extraction.yaml`):

```yaml
name: "customer-support-extraction"
description: "Customer query triage and entity extraction"
prompt_template: "Extract intent and entities from: '{{ query }}'"
provider:
  type: "fixture"
  fixture_file: "support_fixtures.yaml"
cases:
  - id: "case_01_billing_dispute"
    name: "Billing Dispute"
    vars:
      query: "Why was my card billed $49.00 on May 1st?"
    assertions:
      - type: "json_schema"
        expected:
          type: "object"
          required: ["intent", "urgency", "confidence"]
          properties:
            intent: {type: "string", enum: ["billing_dispute", "refund_request"]}
            urgency: {type: "string", enum: ["low", "medium", "high", "critical"]}
            confidence: {type: "number", minimum: 0.0, maximum: 1.0}
      - type: "exact_match"
        path: "intent"
        expected: "billing_dispute"
      - type: "token_budget"
        scope: "completion"
        max_tokens: 100
```

Running `evalmatrix run examples/customer_support_extraction.yaml` produces the terminal matrix output:

```text
✓ PASS customer-support-extraction (12/12 cases passed in 24.2ms)

                     EvalMatrix Evaluation Matrix: customer-support-extraction                     
┏━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Status ┃ Case ID                      ┃ Name / Prompt               ┃ Assertions ┃  Latency ┃ Tokens (P/C/T) ┃
┡━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│  PASS  │ case_01_billing_dispute      │ Billing Dispute Extraction  │    5/5     │    1.5ms │      64/61/125 │
│  PASS  │ case_02_account_cancellation │ Account Cancellation Risk   │    4/4     │    1.5ms │      67/55/122 │
│  PASS  │ case_03_password_reset       │ Auth & Password Reset Link  │    4/4     │    1.5ms │      64/53/117 │
│  PASS  │ case_04_order_status         │ Order Shipping Status       │    4/4     │    1.5ms │      68/49/117 │
│  PASS  │ case_05_refund_request       │ Damaged Product Refund      │    4/4     │    1.5ms │      76/63/139 │
│  PASS  │ case_06_bug_report           │ Critical Checkout 500 Outa… │    4/4     │    1.5ms │      73/65/138 │
│  PASS  │ case_07_feature_request      │ Mobile Dark Mode Suggestion │    4/4     │    1.5ms │      69/56/125 │
│  PASS  │ case_08_plan_upgrade         │ Enterprise 50-Seat Upgrade  │    4/4     │    1.5ms │      70/63/133 │
│  PASS  │ case_09_address_change       │ Pre-Dispatch Address Update │    4/4     │    1.5ms │      75/57/132 │
│  PASS  │ case_10_discount_inquiry     │ Coupon Code Failure         │    3/3     │    1.5ms │      67/49/116 │
│  PASS  │ case_11_hardware_warranty    │ Hardware Replacement Warra… │    4/4     │    1.5ms │      75/58/133 │
│  PASS  │ case_12_positive_feedback    │ Agent Kudos Recognition     │    4/4     │    1.5ms │      74/53/127 │
└────────┴──────────────────────────────┴─────────────────────────────┴────────────┴──────────┴────────────────┘

Result: 12/12 cases passed (100.0%), 48/48 assertions passed (100.0%), Duration: 24.2ms
```

### GitHub Actions CI Integration

Add prompt regression tests directly into your GitHub Actions workflow:

```yaml
- name: Run Prompt Evaluation Suite
  run: |
    evalmatrix run examples/customer_support_extraction.yaml \
      --output-markdown "$GITHUB_STEP_SUMMARY" \
      --exit-code
```

If any prompt output violates schemas, drifts unexpectedly, or breaks token bounds, the action fails and writes a collapsible Markdown regression diff directly into the workflow summary tab.

## How It Works

1. **Suite Loader (`evalmatrix.loader`)**: Reads YAML files and validates test cases, variable inputs, and provider settings into strongly typed `TestSuite` models.
2. **Template Engine (`evalmatrix.templating`)**: Renders Jinja-style prompt variables (`{{ var }}`), traverses nested objects (`{{ user.profile.name }}`), and evaluates default filters prior to generation.
3. **Metrics & Token Estimator (`evalmatrix.metrics`)**: Computes offline string similarity metrics (Levenshtein ratio, Jaccard index, Sørensen–Dice n-gram overlaps) and performs subword-aware heuristic token count estimation.
4. **Assertion Engine (`evalmatrix.assertions`)**: Validates model output against exact matches, substring containment, regex patterns, strict JSON schemas, fuzzy text similarity scores, and token budget ceilings.
5. **Terminal Diff Generator (`evalmatrix.diff`)**: Highlights text drift and JSON regression differences with unified line/word diffs and Rich color syntax.
6. **CI & Terminal Reporter (`evalmatrix.reporter`)**: Renders interactive terminal matrices and exports GitHub-compatible Markdown summary reports with collapsible failure diffs.
7. **Fixture Recorder (`evalmatrix.recorder`)**: Intercepts evaluation runs and serializes live responses into offline YAML/JSON fixtures.

## Running Tests

Run the test suite offline with `pytest`:

```bash
pytest tests -v
```

<!-- builder:roadmap:start -->
## Status

**In active development:** 2 of 3 milestones done.

## Roadmap

- [x] **Core Runner, Provider Interface, and Schema Assertions**: Implement the extensible LLM Provider protocol, an offline FixtureProvider, YAML suite parsing, and strict JSON Schema and exact-match validators with full unit test coverage.
- [x] **Fuzzy Evaluators, Token Budgets, and Prompt Templating**: Add Jinja-style prompt variable interpolation, character n-gram similarity scoring, token budget constraint checks, and fixture recording utilities.
- [ ] **Rich CLI, CI Markdown Exporter, and Realistic Extraction Demo**: Build the Typer CLI with interactive colored matrix outputs, failure inspection diffs, markdown CI reporting, and a turnkey customer-support extraction evaluation demo.
<!-- builder:roadmap:end -->
