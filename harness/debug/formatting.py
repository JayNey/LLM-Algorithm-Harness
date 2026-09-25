"""
Formatting utilities for interactive debugging output.
"""

from typing import Optional

# Try to import pygments for syntax highlighting
try:
    from pygments import highlight
    from pygments.lexers import PythonLexer
    from pygments.formatters import TerminalFormatter
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False


def format_section(title: str, content: str, width: int = 60) -> str:
    """
    Format a section with title and content.

    Args:
        title: Section title
        content: Section content
        width: Width of separators

    Returns:
        Formatted section string
    """
    lines = []
    lines.append("─" * width)
    lines.append(f"▸ {title}")
    lines.append("─" * width)
    lines.append(content)
    lines.append("")
    return "\n".join(lines)


def format_prompt(prompt: str, max_lines: Optional[int] = None) -> str:
    """
    Format prompt for display.

    Args:
        prompt: Prompt text
        max_lines: Maximum lines to show (None for all)

    Returns:
        Formatted prompt
    """
    lines = prompt.split("\n")
    if max_lines and len(lines) > max_lines:
        displayed_lines = lines[:max_lines]
        displayed_lines.append(f"... ({len(lines) - max_lines} more lines)")
        lines = displayed_lines

    return "\n".join(lines)


def format_code(code: str, language: str = "python") -> str:
    """
    Format code with syntax highlighting if available.

    Args:
        code: Code to format
        language: Programming language (default: python)

    Returns:
        Formatted code string
    """
    if PYGMENTS_AVAILABLE and language == "python":
        try:
            return highlight(code, PythonLexer(), TerminalFormatter())
        except Exception:
            # Fall back to plain text if highlighting fails
            pass

    # Plain text fallback
    return code


def format_execution_result(result: dict) -> str:
    """
    Format execution result for display.

    Args:
        result: Execution result dictionary

    Returns:
        Formatted result string
    """
    lines = []

    status = result.get("status", "unknown")
    status_symbol = {
        "success": "✓",
        "passed": "✓",
        "failed": "✗",
        "error": "!",
    }.get(status, "?")

    lines.append(f"Status: {status.upper()} {status_symbol}")

    if "passed" in result:
        lines.append(f"Passed: {result['passed']}/{result.get('total', '?')}")

    if "error" in result and result["error"]:
        lines.append(f"Error: {result['error']}")

    if "output" in result and result["output"]:
        lines.append(f"Output: {result['output'][:200]}")

    return "\n".join(lines)


def format_feedback(feedback: str) -> str:
    """
    Format feedback for display.

    Args:
        feedback: Feedback text

    Returns:
        Formatted feedback
    """
    # Truncate very long feedback
    max_length = 500
    if len(feedback) > max_length:
        return feedback[:max_length] + f"\n... ({len(feedback) - max_length} more characters)"
    return feedback


def format_iteration_display(
    round_num: int,
    prompt: Optional[str] = None,
    response: Optional[str] = None,
    code: Optional[str] = None,
    execution_result: Optional[dict] = None,
    feedback: Optional[str] = None,
) -> str:
    """
    Format a complete iteration for display.

    Args:
        round_num: Round number
        prompt: Prompt text
        response: LLM response
        code: Extracted code
        execution_result: Execution result
        feedback: Feedback text

    Returns:
        Formatted iteration string
    """
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append(f"Round {round_num}")
    lines.append("=" * 60 + "\n")

    if prompt:
        lines.append(format_section("Prompt", format_prompt(prompt, max_lines=10)))

    if response:
        lines.append(format_section(
            "LLM Response",
            response[:300] + ("..." if len(response) > 300 else "")
        ))

    if code:
        lines.append(format_section("Generated Code", format_code(code)))

    if execution_result:
        lines.append(format_section(
            "Execution Result",
            format_execution_result(execution_result)
        ))

    if feedback:
        lines.append(format_section("Feedback", format_feedback(feedback)))

    lines.append("=" * 60 + "\n")
    return "\n".join(lines)


def print_banner(text: str, width: int = 60, char: str = "=") -> None:
    """
    Print a banner with text.

    Args:
        text: Banner text
        width: Banner width
        char: Character to use for border
    """
    print(char * width)
    print(text.center(width))
    print(char * width)


def print_status(message: str, status: str = "info") -> None:
    """
    Print a status message with appropriate symbol.

    Args:
        message: Message text
        status: Status type (info, success, error, warning)
    """
    symbols = {
        "info": "ℹ",
        "success": "✓",
        "error": "✗",
        "warning": "⚠",
    }
    symbol = symbols.get(status, "•")
    print(f"{symbol} {message}")
