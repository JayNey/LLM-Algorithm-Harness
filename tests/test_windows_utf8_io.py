"""Guard: text-mode file IO in src/ must declare encoding explicitly.

Windows defaults to a legacy ANSI code page (cp1252/charmap); implicit-encoding
text reads/writes break on non-ASCII content there. See upstream issue #136 and
the windows-compatibility spec (delta: windows-utf8-encoding).
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"

# Module-qualified .open() calls whose semantics are not "text file with a
# mode string" — excluded from the .open() rule to keep it pathlib-shaped.
NON_TEXT_OPEN_MODULES = {
    "webbrowser",
    "tarfile",
    "zipfile",
    "gzip",
    "bz2",
    "lzma",
    "shelve",
    "dbm",
    "socket",
    "urllib",
}


def _string_const(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _keyword_map(call: ast.Call) -> dict:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}


def _textual_mode(mode_node: ast.AST | None, default_text: bool) -> bool:
    mode = _string_const(mode_node)
    if mode is None:
        # Dynamic mode: judge by the call's own default (open/fdopen are text,
        # NamedTemporaryFile defaults to "w+b").
        return default_text
    return "b" not in mode


def _positional_mode(call: ast.Call, keywords: dict, index: int) -> ast.AST | None:
    if keywords.get("mode") is not None:
        return keywords["mode"]
    if len(call.args) > index:
        return call.args[index]
    return None


def _subprocess_text_mode(keywords: dict) -> bool:
    return any(
        name in keywords
        and isinstance(keywords[name], ast.Constant)
        and keywords[name].value is True
        for name in ("text", "universal_newlines")
    )


def _import_maps(tree: ast.AST) -> tuple[dict, dict]:
    """Resolve ``import x as y`` aliases and ``from subprocess import run`` names."""
    module_aliases: dict = {}
    direct_calls: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    module_aliases[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.asname:
                    direct_calls[alias.asname] = alias.name
                else:
                    direct_calls[alias.name] = alias.name
    return module_aliases, direct_calls


def _check_call(
    path: Path,
    call: ast.Call,
    violations: list,
    module_aliases: dict | None = None,
    direct_calls: dict | None = None,
) -> None:
    module_aliases = module_aliases or {}
    direct_calls = direct_calls or {}
    func = call.func
    keywords = _keyword_map(call)
    has_encoding = "encoding" in keywords

    if isinstance(func, ast.Name):
        if func.id == "open":
            mode = _positional_mode(call, keywords, 1)
            if _textual_mode(mode, default_text=True) and not has_encoding:
                violations.append(f"{path}:{call.lineno} open() without encoding=")
        elif func.id in direct_calls:
            # ``from subprocess import run`` style direct calls.
            if direct_calls[func.id] in {"run", "Popen", "check_output"}:
                if _subprocess_text_mode(keywords) and not has_encoding:
                    violations.append(
                        f"{path}:{call.lineno} subprocess.{func.id}(text=True) without encoding="
                    )
        return

    if not isinstance(func, ast.Attribute):
        return
    attr = func.attr
    root = func.value.id if isinstance(func.value, ast.Name) else None
    module = module_aliases.get(root, root) if root is not None else None

    if attr in {"read_text", "write_text"}:
        if not has_encoding:
            violations.append(f"{path}:{call.lineno} {attr}() without encoding=")
    elif attr == "open":
        if root is None or root == "os" or module in NON_TEXT_OPEN_MODULES:
            return
        mode = _positional_mode(call, keywords, 1)
        if _textual_mode(mode, default_text=True) and not has_encoding:
            violations.append(f"{path}:{call.lineno} .open() without encoding=")
    elif attr == "fdopen":
        mode = _positional_mode(call, keywords, 1)
        if _textual_mode(mode, default_text=True) and not has_encoding:
            violations.append(f"{path}:{call.lineno} fdopen() without encoding=")
    elif attr == "NamedTemporaryFile":
        mode = _positional_mode(call, keywords, 0)
        if _textual_mode(mode, default_text=False) and not has_encoding:
            violations.append(f"{path}:{call.lineno} NamedTemporaryFile(text) without encoding=")
    elif attr in {"run", "Popen", "check_output"} and module == "subprocess":
        if _subprocess_text_mode(keywords) and not has_encoding:
            violations.append(
                f"{path}:{call.lineno} subprocess.{attr}(text=True) without encoding="
            )


def _scan() -> list:
    violations = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        module_aliases, direct_calls = _import_maps(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                _check_call(path, node, violations, module_aliases, direct_calls)
    return violations


def _scan_snippet(source: str) -> list:
    tree = ast.parse(source)
    module_aliases, direct_calls = _import_maps(tree)
    violations: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            _check_call(Path("<snippet>"), node, violations, module_aliases, direct_calls)
    return violations


def test_src_text_io_declares_utf8_encoding():
    violations = _scan()
    assert not violations, "implicit-encoding text IO in src/:\n" + "\n".join(violations)


def test_guard_flags_missing_encoding(tmp_path):
    """Sensitivity check: the scanner must flag a text write without encoding."""
    sample = tmp_path / "sample.py"
    sample.write_text('Path("x").write_text(data)\n', encoding="utf-8")
    tree = ast.parse(sample.read_text(encoding="utf-8"))
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            _check_call(sample, node, violations)
    assert violations, "scanner failed to flag write_text without encoding"


def test_guard_positive_controls():
    """The scanner must flag every flavour of implicit-encoding text IO."""
    positive_cases = [
        'open("f")\n',
        'open("f", "w")\n',
        'Path("f").read_text()\n',
        "os.fdopen(fd)\n",
        'tempfile.NamedTemporaryFile(mode="w", delete=False)\n',
        "subprocess.run(cmd, capture_output=True, text=True)\n",
        "import subprocess as sp\nsp.run(cmd, text=True)\n",
        "from subprocess import run\nrun(cmd, text=True)\n",
        'p.open("w")\n',
    ]
    for source in positive_cases:
        violations = _scan_snippet(source)
        assert violations, f"scanner failed to flag: {source!r}"


def test_guard_negative_controls():
    """Binary IO, low-level fds and non-text .open() owners must stay exempt."""
    negative_cases = [
        'open("f", "rb")\n',
        'open("f", mode="wb")\n',
        "data.write_bytes(payload)\n",
        "os.open(target, os.O_WRONLY | os.O_CREAT)\n",
        'tempfile.NamedTemporaryFile(mode="w+b", delete=False)\n',
        'tempfile.NamedTemporaryFile(suffix=".bin")\n',
        "subprocess.run(cmd, capture_output=True)\n",
        'subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")\n',
        "import subprocess as sp\nsp.run(cmd, capture_output=True)\n",
        'p.open("w", encoding="utf-8")\n',
        'webbrowser.open("https://example.com")\n',
        'tarfile.open("x.tar.gz")\n',
        'zipfile.ZipFile("z").open("a.txt")\n',
    ]
    for source in negative_cases:
        violations = _scan_snippet(source)
        assert not violations, f"scanner produced false positive: {source!r} -> {violations}"
