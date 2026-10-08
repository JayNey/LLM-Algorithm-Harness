"""Encoding regressions independent of Unix process/locking support (#136)."""

import builtins
import io
import logging
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from src.code_quality.readability_analyzer import ReadabilityAnalyzer
from src.code_quality.style_analyzer import StyleConsistencyAnalyzer
from src.importers.local_json import LocalJsonImporter
from src.models import Problem, SandboxConfig
from src.pareto import build_pareto_analysis, write_pareto_artifacts
from src.sandbox_executor import SandboxExecutor
from src.utils.encoding import utf8_subprocess_env
from src.utils.logging import get_logger, setup_logging

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = runpy.run_path(str(REPO_ROOT / "scripts" / "find_missing_encoding.py"))
UNICODE_TEXT = "算法评测 Ω 😀"


@pytest.fixture
def legacy_default_encoding(monkeypatch):
    """Make omitted encodings behave like Windows cp1252 on every test host."""

    def legacy_open(original):
        def wrapped(*args, **kwargs):
            mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")
            if "b" not in mode:
                if len(args) > 3:
                    values = list(args)
                    if values[3] is None:
                        values[3] = "cp1252"
                    args = tuple(values)
                elif kwargs.get("encoding") is None:
                    kwargs["encoding"] = "cp1252"
            return original(*args, **kwargs)

        return wrapped

    monkeypatch.setattr(builtins, "open", legacy_open(builtins.open))
    monkeypatch.setattr(io, "open", legacy_open(io.open))


@pytest.mark.parametrize(
    "source",
    [
        "open('file.json')",
        "open('file.json', 'w')",
        "path.read_text()",
        "path.write_text('文本')",
        "path.open('r')",
        "import tempfile; tempfile.NamedTemporaryFile(mode='w')",
        "from tempfile import NamedTemporaryFile as tmp; tmp(mode='w')",
        "import subprocess; subprocess.run(['tool'], text=True)",
        "from subprocess import run as launch; launch(['tool'], universal_newlines=True)",
        "import logging; logging.FileHandler('log.txt')",
        "open('file.json', encoding=None)",
    ],
)
def test_scanner_catches_implicit_text_encoding(source):
    assert len(SCANNER["missing_encoding_calls"](source)) == 1


def test_scanner_preserves_binary_and_explicit_encoding_operations():
    source = """
import tempfile
import subprocess
from PIL import Image
open('file', 'rb')
path.open('wb')
Image.open('chart.png')
tempfile.NamedTemporaryFile()
open('file', 'r', -1, 'utf-8')
path.read_text('utf-8')
path.write_text('文本', 'utf-8')
subprocess.run(['tool'], capture_output=True)
subprocess.run(['tool'], text=True, encoding='utf-8')
"""
    assert SCANNER["missing_encoding_calls"](source) == []


def test_repository_has_no_implicit_text_file_or_subprocess_encodings():
    findings = [
        f"{path.relative_to(REPO_ROOT)}:{node.lineno}"
        for path in SCANNER["repository_sources"](REPO_ROOT)
        for node in SCANNER["missing_encoding_calls"](path.read_text(encoding="utf-8"))
    ]
    assert findings == []


def test_utf8_python_pipe_contract_overrides_only_stdio():
    original = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"}
    environment = utf8_subprocess_env(original)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; print({UNICODE_TEXT!r}); sys.stderr.write({UNICODE_TEXT!r})",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == UNICODE_TEXT
    assert result.stderr == UNICODE_TEXT
    assert original["PYTHONIOENCODING"] == "cp1252"
    assert environment["PYTHONUTF8"] == "0"
    assert utf8_subprocess_env({"PATH": "isolated"}) == {
        "PATH": "isolated",
        "PYTHONIOENCODING": "utf-8",
    }


def test_report_and_import_round_trip_with_cp1252_default(tmp_path, legacy_default_encoding):
    # This string cannot be written as cp1252: success proves an explicit UTF-8 boundary.
    with pytest.raises(UnicodeEncodeError):
        UNICODE_TEXT.encode("cp1252")
    analysis = build_pareto_analysis([{"combinations": []}])
    write_pareto_artifacts(analysis, tmp_path / "报告")
    report = (tmp_path / "报告" / "PARETO.md").read_bytes().decode("utf-8")
    assert "成本-准确率" in report
    source = tmp_path / "题库.json"
    source.write_bytes(
        bytes(
            '[{"problem_id":"utf8", "title":"算法题", "description":"中文题目描述足够长用于导入验证",'
            '"difficulty":"easy", "tags":["数组"], "test_cases":[{"input":{"x":1},"expected_output":1}]}]',
            "utf-8",
        )
    )
    imported = LocalJsonImporter().fetch_problems(str(source))
    assert imported[0]["title"] == "算法题"


def test_log_file_round_trip_with_cp1252_default(tmp_path, legacy_default_encoding):
    root = logging.getLogger()
    previous = list(root.handlers)
    log_path = tmp_path / "中文日志.txt"
    try:
        setup_logging(log_file=str(log_path), console_format="console")
        get_logger("utf8-test").info("编码检查", value=UNICODE_TEXT)
        for handler in root.handlers:
            handler.flush()
        assert UNICODE_TEXT in log_path.read_bytes().decode("utf-8")
    finally:
        for handler in root.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.close()
        root.handlers = previous


def test_quality_tools_receive_utf8_source_and_utf8_stdio(monkeypatch, legacy_default_encoding):
    source = f"# {UNICODE_TEXT}\ndef solution(x):\n    return x\n"
    calls = []

    def execute(command, **kwargs):
        path = Path(command[2] if command[0] in {"black", "radon"} else command[1])
        assert path.read_bytes().decode("utf-8") == source
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
        calls.append(path)
        return subprocess.CompletedProcess(
            command, 0, "rated at 10.00/10\nAverage complexity: 1.0\n", ""
        )

    monkeypatch.setattr(subprocess, "run", execute)
    analyzer = ReadabilityAnalyzer()
    assert analyzer._run_pylint(source) == 10
    assert analyzer._run_flake8(source) == 2
    assert analyzer._run_radon(source) == 1
    assert StyleConsistencyAnalyzer()._check_black_format(source)[0]
    assert len(calls) == 4
    assert all(not path.exists() for path in calls)


def test_sandbox_utf8_wrapper_and_pipe_environment(monkeypatch, legacy_default_encoding):
    executor = SandboxExecutor(SandboxConfig(backend="host"))
    problem = Problem(
        problem_id="stdio-utf8",
        title="UTF-8",
        description="Echo UTF-8 input through standard streams.",
        difficulty="easy",
        input_output_mode="stdin_stdout",
        test_cases=[{"input": UNICODE_TEXT, "expected_output": UNICODE_TEXT}],
    )

    def execute(command, **kwargs):
        assert UNICODE_TEXT in Path(command[1]).read_bytes().decode("utf-8")
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
        assert kwargs["input_data"] == UNICODE_TEXT.encode("utf-8")
        return subprocess.CompletedProcess(command, 0, UNICODE_TEXT, "")

    monkeypatch.setattr(executor, "_run_command", execute)
    assert (
        executor._run_in_subprocess(f"print({UNICODE_TEXT!r})", UNICODE_TEXT, problem)
        == UNICODE_TEXT
    )
    assert "PYTHONIOENCODING=utf-8" in executor._build_docker_command("workdir", "runner.py")
