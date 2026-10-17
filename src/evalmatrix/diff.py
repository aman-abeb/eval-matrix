"""Terminal diff utilities for text drift and structured JSON regressions."""

import difflib
import json
from typing import Any, List, Optional, Tuple, Union
from rich.console import RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


def _normalize_to_formatted_json(val: Any) -> Optional[str]:
    """Attempt to parse and serialize value to indented canonical JSON."""
    if isinstance(val, (dict, list)):
        return json.dumps(val, indent=2, sort_keys=True, ensure_ascii=False)
    if isinstance(val, str):
        s = val.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                parsed = json.loads(s)
                return json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False)
            except Exception:
                return None
    return None


def generate_unified_diff(
    expected: Union[str, Any],
    actual: Union[str, Any],
    label_expected: str = "expected",
    label_actual: str = "actual",
    n_context: int = 3,
) -> List[str]:
    """Generate unified diff lines between expected and actual values.

    Canonicalizes JSON objects into indented strings if applicable.
    """
    exp_json = _normalize_to_formatted_json(expected)
    act_json = _normalize_to_formatted_json(actual)

    if exp_json is not None and act_json is not None:
        exp_str = exp_json
        act_str = act_json
    else:
        exp_str = str(expected) if expected is not None else ""
        act_str = str(actual) if actual is not None else ""

    exp_lines = exp_str.splitlines(keepends=True)
    act_lines = act_str.splitlines(keepends=True)

    return list(
        difflib.unified_diff(
            exp_lines,
            act_lines,
            fromfile=label_expected,
            tofile=label_actual,
            n=n_context,
        )
    )


def render_text_diff(
    expected: Union[str, Any],
    actual: Union[str, Any],
    label_expected: str = "expected",
    label_actual: str = "actual",
) -> Text:
    """Create Rich Text object with colored unified diff (+ green, - red, @@ cyan)."""
    diff_lines = generate_unified_diff(
        expected=expected,
        actual=actual,
        label_expected=label_expected,
        label_actual=label_actual,
    )

    result = Text()
    if not diff_lines:
        result.append("No differences detected.\n", style="dim italic")
        return result

    for line in diff_lines:
        stripped = line.rstrip("\r\n")
        if line.startswith("+++") or line.startswith("---"):
            result.append(f"{stripped}\n", style="bold white")
        elif line.startswith("+"):
            result.append(f"{stripped}\n", style="green")
        elif line.startswith("-"):
            result.append(f"{stripped}\n", style="red")
        elif line.startswith("@@"):
            result.append(f"{stripped}\n", style="bold cyan")
        else:
            result.append(f"{stripped}\n", style="dim")

    return result


def format_diff_markdown(
    expected: Union[str, Any],
    actual: Union[str, Any],
    title: Optional[str] = None,
) -> str:
    """Format a diff into a GitHub-flavored Markdown diff code block."""
    diff_lines = generate_unified_diff(expected, actual)
    if not diff_lines:
        return "*No text difference detected.*"

    diff_content = "".join(diff_lines)
    out = []
    if title:
        out.append(f"**{title}**:\n")
    out.append("```diff\n")
    out.append(diff_content.rstrip())
    out.append("\n```")
    return "".join(out)


def render_diff_panel(
    expected: Union[str, Any],
    actual: Union[str, Any],
    title: str = "Regression Diff (Expected vs Actual)",
    subtitle: Optional[str] = None,
) -> Panel:
    """Wrap a Rich-rendered diff into a high-visibility terminal Panel."""
    text_diff = render_text_diff(expected=expected, actual=actual)
    return Panel(
        text_diff,
        title=f"[bold red]{title}[/bold red]",
        subtitle=subtitle or "[dim]- expected | + actual[/dim]",
        border_style="red",
        padding=(0, 1),
    )
