"""Unit tests for prompt template variable interpolation and filter pipeline."""

import pytest
from evalmatrix.templating import (
    TemplateRenderError,
    UndefinedVariableError,
    extract_template_variables,
    render_template,
)


def test_render_simple_variables():
    template = "Hello {{ name }}, welcome to {{ location }}!"
    rendered = render_template(template, {"name": "Alice", "location": "Wonderland"})
    assert rendered == "Hello Alice, welcome to Wonderland!"


def test_render_whitespace_tolerance():
    template = "Values: {{a}}, {{  b  }}, {{\t c \n}}"
    rendered = render_template(template, {"a": "1", "b": "2", "c": "3"})
    assert rendered == "Values: 1, 2, 3"


def test_render_nested_dot_notation():
    template = "User {{ user.profile.name }} has role {{ user.auth.role }}"
    vars_dict = {
        "user": {
            "profile": {"name": "Bob"},
            "auth": {"role": "admin"},
        }
    }
    rendered = render_template(template, vars_dict)
    assert rendered == "User Bob has role admin"


def test_render_list_indices():
    template = "First: {{ items.0 }}, Second: {{ items[1] }}, Nested: {{ matrix.0.1 }}"
    vars_dict = {
        "items": ["apple", "banana"],
        "matrix": [[10, 20], [30, 40]],
    }
    rendered = render_template(template, vars_dict)
    assert rendered == "First: apple, Second: banana, Nested: 20"


def test_render_bracket_quoted_keys():
    template = "Order: {{ order['id'] }} - {{ order[\"status\"] }}"
    vars_dict = {"order": {"id": "ord_100", "status": "shipped"}}
    rendered = render_template(template, vars_dict)
    assert rendered == "Order: ord_100 - shipped"


def test_render_scalar_types():
    template = "Count: {{ count }}, Price: {{ price }}, Active: {{ active }}"
    vars_dict = {"count": 42, "price": 19.99, "active": True}
    rendered = render_template(template, vars_dict)
    assert rendered == "Count: 42, Price: 19.99, Active: True"


def test_render_dict_and_list_to_json():
    template = "Payload: {{ payload }}"
    vars_dict = {"payload": {"status": "ok", "code": 200}}
    rendered = render_template(template, vars_dict)
    assert '"status": "ok"' in rendered
    assert '"code": 200' in rendered


def test_render_strict_mode_missing_variable_raises():
    template = "Hello {{ missing_var }}"
    with pytest.raises(UndefinedVariableError, match="Template variable 'missing_var' is not defined"):
        render_template(template, {"other": 1}, strict=True)


def test_render_strict_mode_nested_missing_key_raises():
    template = "Nested {{ user.missing.deep }}"
    with pytest.raises(UndefinedVariableError, match="user.missing.deep"):
        render_template(template, {"user": {"profile": "val"}}, strict=True)


def test_render_lenient_mode_default_fallback():
    template = "Hello {{ missing_var }}"
    assert render_template(template, {}, strict=False) == "Hello "
    assert render_template(template, {}, strict=False, default="[UNKNOWN]") == "Hello [UNKNOWN]"


def test_default_filter_expression():
    template = "Contact: {{ email | default('no-reply@example.com') }}"
    # Missing variable falls back to filter default
    assert render_template(template, {}) == "Contact: no-reply@example.com"
    # Provided variable overrides filter default
    assert render_template(template, {"email": "user@evalmatrix.dev"}) == "Contact: user@evalmatrix.dev"


def test_default_filter_alternate_syntaxes():
    assert render_template("{{ x | default(\"fallback\") }}", {}) == "fallback"
    assert render_template("{{ x | default: fallback }}", {}) == "fallback"
    assert render_template("{{ x | default: 'fallback' }}", {}) == "fallback"


def test_default_filter_handles_pipes_inside_quotes():
    template = "{{ val | default('A|B|C') }}"
    assert render_template(template, {}) == "A|B|C"


def test_string_transform_filters():
    template = "{{ name | trim | upper }} - {{ role | lower }}"
    rendered = render_template(template, {"name": "  alice  ", "role": "ENGINEER"})
    assert rendered == "ALICE - engineer"


def test_preserves_single_curly_braces_and_json():
    template = 'Classify into JSON format: {"intent": "{{ intent }}", "score": 1}'
    rendered = render_template(template, {"intent": "billing"})
    assert rendered == 'Classify into JSON format: {"intent": "billing", "score": 1}'


def test_extract_template_variables():
    template = "Hello {{ user.name }}, order {{ order.id }} has items {{ items[0] }}"
    all_paths = extract_template_variables(template, base_only=False)
    assert all_paths == {"user.name", "order.id", "items[0]"}

    base_keys = extract_template_variables(template, base_only=True)
    assert base_keys == {"user", "order", "items"}


def test_render_empty_or_no_variables():
    assert render_template("") == ""
    assert render_template("Plain text", None) == "Plain text"
