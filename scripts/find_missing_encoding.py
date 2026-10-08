"""Find implicit text encodings in repository Python file/subprocess operations.

This is an AST check of direct calls, not a type checker. Embedded candidate
program strings and third-party internals are intentionally outside its scope.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


def _name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_name(node.value)}.{node.attr}"
    return ""


def missing_encoding_calls(source: str) -> list[ast.Call]:
    """Return direct text IO calls without an explicit non-None encoding."""
    tree = ast.parse(source)
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _name(node.func)
        prefix, _, suffix = name.partition(".")
        name = aliases.get(prefix, prefix) + (f".{suffix}" if suffix else "")
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        mode_index = None
        encoding_index = None
        default_mode = "r"
        if name.endswith(".read_text"):
            encoding_index = 0
        elif name.endswith(".write_text"):
            encoding_index = 1
        elif name in {"open", "builtins.open", "io.open", "os.fdopen", "gzip.open"}:
            mode_index = 1
            encoding_index = 3
            default_mode = "rb" if name == "gzip.open" else "r"
        elif name in {"tempfile.NamedTemporaryFile", "tempfile.TemporaryFile"}:
            mode_index = 0
            encoding_index = 2
            default_mode = "w+b"
        elif name in {"logging.FileHandler", "logging.handlers.WatchedFileHandler"}:
            mode_index, encoding_index, default_mode = 1, 2, "a"
        elif name == "logging.handlers.RotatingFileHandler":
            mode_index, encoding_index, default_mode = 1, 4, "a"
        elif name.endswith(".open") and not name.startswith(("PIL.", "urllib.", "zipfile.")):
            # Path.open calls use mode, buffering, encoding as bound arguments.
            mode_index, encoding_index = 0, 2
        elif name.startswith("subprocess."):
            text_mode = (
                any(
                    isinstance(keywords.get(key), ast.Constant) and keywords[key].value is True
                    for key in ("text", "universal_newlines")
                )
                or "errors" in keywords
            )
            if not text_mode:
                continue
        else:
            continue

        mode = keywords.get("mode")
        if mode is None and mode_index is not None and len(node.args) > mode_index:
            mode = node.args[mode_index]
        if mode is None:
            mode = ast.Constant(default_mode)
        if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" in mode.value:
            continue
        encoding = keywords.get("encoding")
        if encoding is None and encoding_index is not None and len(node.args) > encoding_index:
            encoding = node.args[encoding_index]
        if encoding is None or (isinstance(encoding, ast.Constant) and encoding.value is None):
            findings.append(node)
    return sorted(findings, key=lambda node: (node.lineno, node.col_offset))


def repository_sources(root: Path) -> list[Path]:
    paths = set(root.glob("*.py"))
    for name in ("src", "harness", "tests", "scripts"):
        paths.update((root / name).rglob("*.py"))
    return sorted(paths)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    count = 0
    for path in repository_sources(args.root):
        for node in missing_encoding_calls(path.read_text(encoding="utf-8")):
            print(
                f"{path.relative_to(args.root)}:{node.lineno}: missing encoding: {_name(node.func)}"
            )
            count += 1
    print(f"Implicit text encodings: {count}")
    return 1 if count else 0


if __name__ == "__main__":
    raise SystemExit(main())
