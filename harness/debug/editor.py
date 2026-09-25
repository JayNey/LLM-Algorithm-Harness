"""
Prompt editing functionality for interactive debugging.
"""

import os
import tempfile
import subprocess
from typing import Optional


def edit_prompt(current_prompt: str) -> Optional[str]:
    """
    Edit prompt text using external editor or inline input.

    Tries to use $EDITOR environment variable first, falls back to
    inline multi-line input if editor is not available.

    Args:
        current_prompt: Current prompt text to edit

    Returns:
        Edited prompt text, or None if editing was cancelled
    """
    editor = os.environ.get("EDITOR")

    if editor:
        # Try external editor
        try:
            return _edit_with_external_editor(current_prompt, editor)
        except Exception as e:
            print(f"Failed to open external editor: {e}")
            print("Falling back to inline input mode...")
            return _edit_inline(current_prompt)
    else:
        # No editor configured, use inline input
        return _edit_inline(current_prompt)


def _edit_with_external_editor(prompt: str, editor: str) -> Optional[str]:
    """
    Edit prompt using external editor.

    Args:
        prompt: Current prompt text
        editor: Editor command

    Returns:
        Edited prompt text, or None if cancelled
    """
    # Create temporary file with current prompt
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
        encoding="utf-8"
    ) as tmp_file:
        tmp_file.write(prompt)
        tmp_path = tmp_file.name

    try:
        # Open editor
        result = subprocess.run(
            [editor, tmp_path],
            check=False
        )

        if result.returncode != 0:
            print(f"Editor exited with code {result.returncode}")
            return None

        # Read edited content
        with open(tmp_path, "r", encoding="utf-8") as f:
            edited_prompt = f.read()

        return edited_prompt

    finally:
        # Clean up temporary file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _edit_inline(current_prompt: str) -> Optional[str]:
    """
    Edit prompt using inline multi-line input.

    Args:
        current_prompt: Current prompt text

    Returns:
        Edited prompt text, or None if cancelled
    """
    print("\n--- Current Prompt ---")
    print(current_prompt)
    print("\n--- Enter New Prompt (end with Ctrl+D on Unix or Ctrl+Z on Windows) ---")
    print("Or type 'cancel' on first line to abort editing.")
    print()

    lines = []
    try:
        while True:
            try:
                line = input()
                if not lines and line.strip().lower() == "cancel":
                    print("Editing cancelled.")
                    return None
                lines.append(line)
            except EOFError:
                break
    except KeyboardInterrupt:
        print("\nEditing cancelled.")
        return None

    edited_prompt = "\n".join(lines).strip()

    if not edited_prompt:
        print("Empty prompt, keeping original.")
        return current_prompt

    return edited_prompt
