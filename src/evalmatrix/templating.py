"""Prompt template interpolation engine supporting nested keys and filters."""

import json
import re
from typing import Any, Dict, List, Optional, Union


class TemplateRenderError(Exception):
    """Base exception raised when prompt template rendering fails."""
    pass


class UndefinedVariableError(TemplateRenderError):
    """Raised when a template variable cannot be resolved in strict mode."""
    pass


VARIABLE_PATTERN = re.compile(r"\{\{\s*(.*?)\s*\}\}")


def _split_pipe_expressions(expr: str) -> List[str]:
    """Split an expression by pipe '|', ignoring pipes inside quoted strings."""
    tokens: List[str] = []
    current: List[str] = []
    in_single_quote = False
    in_double_quote = False

    for ch in expr:
        if ch == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(ch)
        elif ch == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(ch)
        elif ch == "|" and not in_single_quote and not in_double_quote:
            tokens.append("".join(current).strip())
            current = []
        else:
            current.append(ch)

    if current:
        tokens.append("".join(current).strip())
    return [t for t in tokens if t]


def _parse_filter(filter_str: str) -> tuple[str, Optional[str]]:
    """Parse filter name and argument, e.g. default('val') -> ('default', 'val')."""
    f = filter_str.strip()
    m = re.match(
        r"^([a-zA-Z_][a-zA-Z0-9_]*)(?:\(\s*['\"]?(.*?)['\"]?\s*\)|:\s*['\"]?(.*?)['\"]?|\s+['\"]?(.*?)['\"]?)?$",
        f,
    )
    if m:
        filter_name = m.group(1).lower()
        arg = m.group(2) if m.group(2) is not None else (
            m.group(3) if m.group(3) is not None else m.group(4)
        )
        return filter_name, arg
    return f.lower(), None


def _resolve_path_expression(variables: Dict[str, Any], path_expr: str) -> Any:
    """Traverse dot and bracket path syntax on nested dictionaries and lists."""
    cleaned = path_expr.strip()
    if not cleaned:
        raise UndefinedVariableError("Empty variable expression in template.")

    # Tokenize path like: user.profile.name, items[0], data['user']['name']
    token_pattern = re.compile(r"\[(\d+)\]|\['([^']+)'\]|\[\"([^\"]+)\"\]|([^\.\[\]]+)")
    tokens: List[Union[str, int]] = []
    for match in token_pattern.finditer(cleaned):
        idx_match, sq_match, dq_match, id_match = match.groups()
        if idx_match is not None:
            tokens.append(int(idx_match))
        elif sq_match is not None:
            tokens.append(sq_match)
        elif dq_match is not None:
            tokens.append(dq_match)
        elif id_match is not None:
            ident = id_match.strip()
            if ident.isdigit():
                tokens.append(int(ident))
            else:
                tokens.append(ident)

    if not tokens:
        raise UndefinedVariableError(f"Cannot parse variable expression '{path_expr}'.")

    curr: Any = variables
    traversed: List[str] = []
    for token in tokens:
        traversed.append(str(token))
        path_so_far = ".".join(traversed)
        if isinstance(curr, dict):
            if token in curr:
                curr = curr[token]
            elif isinstance(token, int) and str(token) in curr:
                curr = curr[str(token)]
            elif isinstance(token, str) and token.isdigit() and int(token) in curr:
                curr = curr[int(token)]
            else:
                raise KeyError(f"Key '{token}' not found at '{path_so_far}'")
        elif isinstance(curr, (list, tuple)):
            if not isinstance(token, int):
                raise KeyError(f"Expected integer index for list at '{path_so_far}', got '{token}'")
            if token < 0 or token >= len(curr):
                raise IndexError(f"Index {token} out of range (length {len(curr)}) at '{path_so_far}'")
            curr = curr[token]
        else:
            raise KeyError(
                f"Cannot traverse key '{token}' into scalar {type(curr).__name__} at '{path_so_far}'"
            )

    return curr


def _evaluate_expression(
    expr: str,
    variables: Dict[str, Any],
    strict: bool,
    default: Optional[str],
) -> str:
    """Evaluate a single variable expression with optional filter pipeline."""
    pipe_parts = _split_pipe_expressions(expr)
    if not pipe_parts:
        return ""

    var_expr = pipe_parts[0]
    filter_parts = pipe_parts[1:]

    has_default_filter = False
    filter_default_val: Optional[str] = None
    transform_filters: List[str] = []

    for fp in filter_parts:
        fname, farg = _parse_filter(fp)
        if fname == "default":
            has_default_filter = True
            filter_default_val = farg if farg is not None else ""
        else:
            transform_filters.append(fname)

    # Resolve the variable value
    try:
        val = _resolve_path_expression(variables, var_expr)
        if val is None or (isinstance(val, str) and val == ""):
            resolved: Any = filter_default_val if has_default_filter else val
        else:
            resolved = val
    except (KeyError, IndexError, UndefinedVariableError):
        if has_default_filter:
            resolved = filter_default_val
        elif strict:
            available_keys = list(variables.keys())
            raise UndefinedVariableError(
                f"Template variable '{var_expr}' is not defined. Available variables: {available_keys}"
            )
        else:
            resolved = default if default is not None else ""

    # Convert value to string
    if isinstance(resolved, (dict, list)):
        resolved_str = json.dumps(resolved)
    elif resolved is None:
        resolved_str = ""
    elif isinstance(resolved, bool):
        resolved_str = "True" if resolved else "False"
    else:
        resolved_str = str(resolved)

    # Apply string transformations
    for fname in transform_filters:
        if fname == "upper":
            resolved_str = resolved_str.upper()
        elif fname == "lower":
            resolved_str = resolved_str.lower()
        elif fname == "trim":
            resolved_str = resolved_str.strip()

    return resolved_str


def extract_template_variables(template: str, base_only: bool = False) -> set[str]:
    """Extract variable names referenced in {{ ... }} expressions.

    Args:
        template: Template string to analyze.
        base_only: If True, returns only root variable names (e.g. 'user' for 'user.name').
                   If False, returns the full path expression (e.g. 'user.name').

    Returns:
        Set of variable names or paths found in template.
    """
    if not template:
        return set()

    extracted: set[str] = set()
    for match in VARIABLE_PATTERN.finditer(template):
        expr = match.group(1).strip()
        pipe_parts = _split_pipe_expressions(expr)
        if not pipe_parts:
            continue
        var_path = pipe_parts[0].strip()
        if not var_path:
            continue

        if base_only:
            root_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)", var_path)
            if root_match:
                extracted.add(root_match.group(1))
            else:
                extracted.add(var_path)
        else:
            extracted.add(var_path)

    return extracted


def render_template(
    template: str,
    variables: Optional[Dict[str, Any]] = None,
    strict: bool = True,
    default: Optional[str] = None,
) -> str:
    """Render a template string by interpolating variables inside {{ ... }} blocks.

    Supports nested dot-notation access (e.g. 'user.profile.name'), list indexing
    (e.g. 'items[0]' or 'items.0'), default fallback filter ('var | default("val")'),
    and strict or lenient missing variable handling.

    Args:
        template: The template string containing {{ var }} expressions.
        variables: Dictionary of variable values for substitution.
        strict: If True, raises UndefinedVariableError for missing variables without defaults.
                If False, substitutes with `default` or empty string.
        default: Fallback string to use for missing variables when strict=False.

    Returns:
        The rendered string with all expressions substituted.

    Raises:
        UndefinedVariableError: If strict is True and a variable is not found.
        TemplateRenderError: If expression syntax or resolution encounters an error.
    """
    if not template:
        return "" if template is None else template

    vars_dict = variables or {}

    def _replacer(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        return _evaluate_expression(expr, vars_dict, strict=strict, default=default)

    return VARIABLE_PATTERN.sub(_replacer, template)
