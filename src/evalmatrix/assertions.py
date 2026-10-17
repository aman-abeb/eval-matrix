"""Assertion evaluators for exact-match, contains, regex, and JSON schema validation."""

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence, Type, Union
from pydantic import BaseModel, Field

from evalmatrix.models import AssertionConfig, AssertionType, ProviderResponse

try:
    import jsonschema
    import jsonschema.exceptions
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


class PathNotFoundError(Exception):
    """Raised when a requested dot-notation or JSON path cannot be resolved."""
    pass


class AssertionResult(BaseModel):
    """Deterministic outcome of evaluating a single assertion."""
    passed: bool = Field(..., description="Whether the assertion succeeded")
    assertion_type: str = Field(..., description="Type of assertion executed")
    message: str = Field(..., description="Human-readable outcome or failure explanation")
    actual: Optional[Any] = Field(default=None, description="Actual extracted or evaluated value")
    expected: Optional[Any] = Field(default=None, description="Expected value or pattern")
    path: Optional[str] = Field(default=None, description="Path traversed in JSON output if applicable")
    error_details: List[str] = Field(default_factory=list, description="Detailed list of specific errors")

    def __bool__(self) -> bool:
        return self.passed

    @property
    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        prefix = f"[{status}] {self.assertion_type}"
        if self.path:
            prefix += f" (path: {self.path})"
        return f"{prefix}: {self.message}"


def get_response_content(response: Union[str, ProviderResponse]) -> str:
    """Extract text content from string or ProviderResponse."""
    if isinstance(response, ProviderResponse):
        return response.content
    return str(response)


def extract_json_payload(response: Union[str, ProviderResponse]) -> Any:
    """Extract and decode JSON payload from text or ProviderResponse.

    Handles raw JSON, objects, and LLM markdown code blocks (e.g. ```json ... ```).
    """
    if isinstance(response, ProviderResponse) and isinstance(response.raw, (dict, list)):
        return response.raw

    content = get_response_content(response).strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    return json.loads(content)


def resolve_path(data: Any, path: Optional[str]) -> Any:
    """Traverse dot and bracket path syntax on nested dictionaries and lists.

    Examples:
        resolve_path(data, "user.name")
        resolve_path(data, "items[0].id")
        resolve_path(data, "$.results.count")
    """
    if not path or path.strip() in ("", "$"):
        return data

    p = path.strip()
    if p.startswith("$."): 
        p = p[2:]
    elif p.startswith("$"):
        p = p[1:]
    if not p:
        return data

    # Tokenize identifiers, numeric indices, or quoted keys
    parts = re.findall(r"\[(\d+)\]|\['([^']+)'\]|\[\"([^\"]+)\"\]|([^\.\[\]]+)", p)
    tokens: List[Union[str, int]] = []
    for part in parts:
        if part[0]:  # digit index in [0]
            tokens.append(int(part[0]))
        elif part[1]:  # single quoted key
            tokens.append(part[1])
        elif part[2]:  # double quoted key
            tokens.append(part[2])
        elif part[3]:  # identifier
            id_val = part[3]
            if id_val.isdigit():
                tokens.append(int(id_val))
            else:
                tokens.append(id_val)

    curr = data
    for i, token in enumerate(tokens):
        traversed = ".".join(str(t) for t in tokens[:i]) or "$"
        if isinstance(curr, dict):
            if str(token) in curr:
                curr = curr[str(token)]
            elif isinstance(token, int) and token in curr:
                curr = curr[token]
            else:
                raise PathNotFoundError(f"Key '{token}' not found at path '{traversed}'")
        elif isinstance(curr, (list, tuple)):
            if not isinstance(token, int):
                raise PathNotFoundError(f"Expected integer index for list at path '{traversed}', got '{token}'")
            if token < 0 or token >= len(curr):
                raise PathNotFoundError(f"Index {token} out of range (length {len(curr)}) at path '{traversed}'")
            curr = curr[token]
        else:
            raise PathNotFoundError(
                f"Cannot traverse key '{token}' into scalar {type(curr).__name__} at path '{traversed}'"
            )
    return curr


def _builtin_validate_schema(instance: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    """Fallback offline JSON Schema validator for common draft constraints."""
    errors: List[str] = []

    # Type checking
    expected_type = schema.get("type")
    if expected_type:
        type_list = [expected_type] if isinstance(expected_type, str) else expected_type
        matched = False
        for t in type_list:
            if t == "object" and isinstance(instance, dict):
                matched = True
            elif t == "array" and isinstance(instance, list):
                matched = True
            elif t == "string" and isinstance(instance, str):
                matched = True
            elif t == "integer" and isinstance(instance, int) and not isinstance(instance, bool):
                matched = True
            elif t == "number" and (isinstance(instance, (int, float)) and not isinstance(instance, bool)):
                matched = True
            elif t == "boolean" and isinstance(instance, bool):
                matched = True
            elif t == "null" and instance is None:
                matched = True
        if not matched:
            errors.append(f"{path}: expected type '{expected_type}', got '{type(instance).__name__}'")
            return errors

    # Enum constraint
    if "enum" in schema:
        if instance not in schema["enum"]:
            errors.append(f"{path}: {instance!r} is not one of {schema['enum']!r}")

    # Object constraints
    if isinstance(instance, dict):
        required = schema.get("required", [])
        for req in required:
            if req not in instance:
                errors.append(f"{path}: missing required property '{req}'")

        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name in instance:
                prop_path = f"{path}.{prop_name}" if path != "$" else f"$.{prop_name}"
                errors.extend(_builtin_validate_schema(instance[prop_name], prop_schema, path=prop_path))

        additional_props = schema.get("additionalProperties", True)
        if additional_props is False:
            allowed_keys = set(properties.keys())
            for key in instance:
                if key not in allowed_keys:
                    p_path = f"{path}.{key}" if path != "$" else f"$.{key}"
                    errors.append(f"{p_path}: unexpected additional property '{key}'")
        elif isinstance(additional_props, dict):
            allowed_keys = set(properties.keys())
            for key, val in instance.items():
                if key not in allowed_keys:
                    p_path = f"{path}.{key}" if path != "$" else f"$.{key}"
                    errors.extend(_builtin_validate_schema(val, additional_props, path=p_path))

    # Array constraints
    if isinstance(instance, list):
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for idx, item in enumerate(instance):
                item_path = f"{path}[{idx}]"
                errors.extend(_builtin_validate_schema(item, items_schema, path=item_path))

    # String constraints
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: string length {len(instance)} is shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: string length {len(instance)} is longer than maxLength {schema['maxLength']}")
        if "pattern" in schema:
            pattern = schema["pattern"]
            if not re.search(pattern, instance):
                errors.append(f"{path}: string does not match pattern '{pattern}'")

    # Numeric constraints
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: value {instance} is less than minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: value {instance} is greater than maximum {schema['maximum']}")

    return errors


def validate_json_schema(instance: Any, schema: Dict[str, Any]) -> List[str]:
    """Validate JSON instance against schema, preferring jsonschema with robust fallback."""
    if HAS_JSONSCHEMA:
        try:
            validator_cls = jsonschema.validators.validator_for(schema)
            validator_cls.check_schema(schema)
            validator = validator_cls(schema)
            raw_errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
            errors: List[str] = []
            for err in raw_errors:
                path_parts = list(err.absolute_path)
                path_str = "$." + ".".join(str(p) for p in path_parts) if path_parts else "$"
                errors.append(f"{path_str}: {err.message}")
            return errors
        except jsonschema.exceptions.SchemaError as s_err:
            return [f"$: Invalid JSON Schema definition: {s_err.message}"]
        except Exception:
            return _builtin_validate_schema(instance, schema)
    return _builtin_validate_schema(instance, schema)


class BaseAssertionEvaluator(ABC):
    """Base class for assertion evaluators."""

    assertion_type: str

    @abstractmethod
    def evaluate(
        self, response: Union[str, ProviderResponse], config: AssertionConfig
    ) -> AssertionResult:
        """Evaluate the assertion against provider response."""
        raise NotImplementedError("Subclasses must implement evaluate()")


class ExactMatchEvaluator(BaseAssertionEvaluator):
    """Evaluates exact equality on full response text or extracted JSON paths."""

    assertion_type = AssertionType.EXACT_MATCH.value

    def evaluate(
        self, response: Union[str, ProviderResponse], config: AssertionConfig
    ) -> AssertionResult:
        if config.path:
            try:
                data = extract_json_payload(response)
            except Exception as err:
                return AssertionResult(
                    passed=False,
                    assertion_type=self.assertion_type,
                    message=f"Failed to parse JSON response for path '{config.path}': {err}",
                    expected=config.expected,
                    path=config.path,
                )
            try:
                actual = resolve_path(data, config.path)
            except PathNotFoundError as err:
                return AssertionResult(
                    passed=False,
                    assertion_type=self.assertion_type,
                    message=str(err),
                    expected=config.expected,
                    path=config.path,
                )

            passed = actual == config.expected
            if passed:
                msg = f"Value at path '{config.path}' exact matched expected value."
            else:
                msg = f"Expected {config.expected!r} at path '{config.path}', but got {actual!r}"
            return AssertionResult(
                passed=passed,
                assertion_type=self.assertion_type,
                message=msg,
                actual=actual,
                expected=config.expected,
                path=config.path,
            )

        content = get_response_content(response)
        # If expected is structured, attempt JSON comparison first
        if isinstance(config.expected, (dict, list)):
            try:
                parsed_content = extract_json_payload(content)
                passed = parsed_content == config.expected
                actual_val = parsed_content
            except Exception:
                passed = False
                actual_val = content
        else:
            expected_str = str(config.expected) if config.expected is not None else ""
            passed = content == expected_str
            actual_val = content

        if passed:
            msg = "Exact match succeeded."
        else:
            msg = f"Expected exact match {config.expected!r}, but got {actual_val!r}"

        return AssertionResult(
            passed=passed,
            assertion_type=self.assertion_type,
            message=msg,
            actual=actual_val,
            expected=config.expected,
        )


class ContainsEvaluator(BaseAssertionEvaluator):
    """Evaluates substring or item presence in full text or extracted paths."""

    assertion_type = AssertionType.CONTAINS.value

    def evaluate(
        self, response: Union[str, ProviderResponse], config: AssertionConfig
    ) -> AssertionResult:
        if config.path:
            try:
                data = extract_json_payload(response)
            except Exception as err:
                return AssertionResult(
                    passed=False,
                    assertion_type=self.assertion_type,
                    message=f"Failed to parse JSON response for path '{config.path}': {err}",
                    expected=config.expected,
                    path=config.path,
                )
            try:
                actual = resolve_path(data, config.path)
            except PathNotFoundError as err:
                return AssertionResult(
                    passed=False,
                    assertion_type=self.assertion_type,
                    message=str(err),
                    expected=config.expected,
                    path=config.path,
                )
        else:
            actual = get_response_content(response)

        expected = config.expected
        if isinstance(actual, (list, tuple, set)):
            passed = expected in actual or str(expected) in [str(x) for x in actual]
        elif isinstance(actual, dict):
            passed = str(expected) in actual or expected in actual.values()
        else:
            expected_str = str(expected) if expected is not None else ""
            passed = expected_str in str(actual)

        if passed:
            msg = f"Found expected element/substring {expected!r} in target value."
        else:
            msg = f"Expected target to contain {expected!r}, but was not found."

        return AssertionResult(
            passed=passed,
            assertion_type=self.assertion_type,
            message=msg,
            actual=actual,
            expected=expected,
            path=config.path,
        )


class RegexEvaluator(BaseAssertionEvaluator):
    """Evaluates regex pattern match against output or extracted path."""

    assertion_type = AssertionType.REGEX.value

    def evaluate(
        self, response: Union[str, ProviderResponse], config: AssertionConfig
    ) -> AssertionResult:
        if config.path:
            try:
                data = extract_json_payload(response)
            except Exception as err:
                return AssertionResult(
                    passed=False,
                    assertion_type=self.assertion_type,
                    message=f"Failed to parse JSON response for path '{config.path}': {err}",
                    expected=config.expected,
                    path=config.path,
                )
            try:
                actual = resolve_path(data, config.path)
            except PathNotFoundError as err:
                return AssertionResult(
                    passed=False,
                    assertion_type=self.assertion_type,
                    message=str(err),
                    expected=config.expected,
                    path=config.path,
                )
            target_str = str(actual)
        else:
            target_str = get_response_content(response)
            actual = target_str

        pattern_str = str(config.expected) if config.expected is not None else ""
        try:
            pattern = re.compile(pattern_str)
        except re.error as err:
            return AssertionResult(
                passed=False,
                assertion_type=self.assertion_type,
                message=f"Invalid regex pattern '{pattern_str}': {err}",
                actual=actual,
                expected=pattern_str,
                path=config.path,
            )

        match = pattern.search(target_str)
        if match:
            return AssertionResult(
                passed=True,
                assertion_type=self.assertion_type,
                message=f"Pattern '{pattern_str}' matched successfully.",
                actual=match.group(0),
                expected=pattern_str,
                path=config.path,
            )

        snippet = (target_str[:80] + "...") if len(target_str) > 80 else target_str
        return AssertionResult(
            passed=False,
            assertion_type=self.assertion_type,
            message=f"Pattern '{pattern_str}' did not match: {snippet!r}",
            actual=actual,
            expected=pattern_str,
            path=config.path,
        )


class JsonSchemaEvaluator(BaseAssertionEvaluator):
    """Evaluates structured response against a strict JSON Schema specification."""

    assertion_type = AssertionType.JSON_SCHEMA.value

    def evaluate(
        self, response: Union[str, ProviderResponse], config: AssertionConfig
    ) -> AssertionResult:
        if config.expected is None:
            return AssertionResult(
                passed=False,
                assertion_type=self.assertion_type,
                message="JSON Schema assertion requires an 'expected' schema definition.",
                path=config.path,
            )

        schema = config.expected
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except json.JSONDecodeError as err:
                return AssertionResult(
                    passed=False,
                    assertion_type=self.assertion_type,
                    message=f"Expected JSON schema definition is not valid JSON: {err}",
                    expected=config.expected,
                    path=config.path,
                )

        if not isinstance(schema, dict):
            return AssertionResult(
                passed=False,
                assertion_type=self.assertion_type,
                message=f"JSON Schema must be a dictionary object, got {type(schema).__name__}",
                expected=config.expected,
                path=config.path,
            )

        try:
            data = extract_json_payload(response)
        except Exception as err:
            return AssertionResult(
                passed=False,
                assertion_type=self.assertion_type,
                message=f"Response content is not valid JSON: {err}",
                actual=get_response_content(response),
                expected=schema,
                path=config.path,
            )

        if config.path:
            try:
                target_instance = resolve_path(data, config.path)
            except PathNotFoundError as err:
                return AssertionResult(
                    passed=False,
                    assertion_type=self.assertion_type,
                    message=str(err),
                    actual=data,
                    expected=schema,
                    path=config.path,
                )
        else:
            target_instance = data

        errors = validate_json_schema(target_instance, schema)
        if not errors:
            return AssertionResult(
                passed=True,
                assertion_type=self.assertion_type,
                message="JSON Schema validation succeeded.",
                actual=target_instance,
                expected=schema,
                path=config.path,
            )

        formatted_errors = "\n".join(f"  - {err}" for err in errors)
        return AssertionResult(
            passed=False,
            assertion_type=self.assertion_type,
            message=f"JSON Schema validation failed with {len(errors)} error(s):\n{formatted_errors}",
            actual=target_instance,
            expected=schema,
            path=config.path,
            error_details=errors,
        )


EVALUATOR_REGISTRY: Dict[str, Type[BaseAssertionEvaluator]] = {
    AssertionType.EXACT_MATCH.value: ExactMatchEvaluator,
    AssertionType.CONTAINS.value: ContainsEvaluator,
    AssertionType.REGEX.value: RegexEvaluator,
    AssertionType.JSON_SCHEMA.value: JsonSchemaEvaluator,
}


def register_evaluator(assertion_type: Union[AssertionType, str], evaluator_cls: Type[BaseAssertionEvaluator]) -> None:
    """Register a custom assertion evaluator."""
    key = assertion_type.value if isinstance(assertion_type, AssertionType) else str(assertion_type)
    EVALUATOR_REGISTRY[key] = evaluator_cls


def get_evaluator(assertion_type: Union[AssertionType, str]) -> BaseAssertionEvaluator:
    """Retrieve an instantiated evaluator for a given assertion type."""
    key = assertion_type.value if isinstance(assertion_type, AssertionType) else str(assertion_type)
    evaluator_cls = EVALUATOR_REGISTRY.get(key)
    if evaluator_cls is None:
        raise ValueError(f"Unsupported assertion type: '{key}'. Available types: {list(EVALUATOR_REGISTRY.keys())}")
    return evaluator_cls()


def evaluate_assertion(
    response: Union[str, ProviderResponse], config: AssertionConfig
) -> AssertionResult:
    """Evaluate a single assertion against a response."""
    try:
        evaluator = get_evaluator(config.type)
        return evaluator.evaluate(response, config)
    except ValueError as err:
        return AssertionResult(
            passed=False,
            assertion_type=str(config.type),
            message=str(err),
            expected=config.expected,
            path=config.path,
        )


def evaluate_all(
    response: Union[str, ProviderResponse], assertions: Sequence[AssertionConfig]
) -> List[AssertionResult]:
    """Evaluate all configured assertions sequentially against a provider response."""
    return [evaluate_assertion(response, cfg) for cfg in assertions]
