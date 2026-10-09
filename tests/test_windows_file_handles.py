"""Guard: temp-file handles follow close-before-delete; locking is cross-platform.

Windows cannot delete or replace a file while any handle is open and has
no fcntl module; see upstream issue #138 and the windows-compatibility
spec (delta: windows-file-locking).
"""

import ast
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from src.utils import file_lock as fl
from src.utils.file_lock import exclusive_lock

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


def _tempfile_call_attr(node: ast.Call, direct_names: set[str]) -> str | None:
    """Return the attr name for tempfile.<attr> calls, else None.

    Recognises both ``tempfile.<attr>()`` and direct-name calls created by
    ``from tempfile import <attr> [as alias]``.
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        if (
            isinstance(func.value, ast.Name)
            and func.value.id == "tempfile"
            and func.attr in {"NamedTemporaryFile", "mkstemp"}
        ):
            return func.attr
    elif isinstance(func, ast.Name) and func.id in direct_names:
        return direct_names[func.id]
    return None


class _TempHandleScanner(ast.NodeVisitor):
    """Collect NamedTemporaryFile/fdopen/mkstemp usages and their with-depth."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[str] = []
        self._depth = 0
        self._direct_names: dict[str, str] = {}
        self._legal_mkstemp_assigns: set[int] = set()
        self._mkstemp_fd_targets: dict[str, int] = {}
        self._fdopen_consumed: set[str] = set()

    def visit_With(self, node: ast.With) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_AsyncWith = visit_With

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "tempfile":
            for alias in node.names:
                if alias.name in {"NamedTemporaryFile", "mkstemp"}:
                    self._direct_names[alias.asname or alias.name] = alias.name
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if (
            isinstance(node.value, ast.Call)
            and _tempfile_call_attr(node.value, self._direct_names) == "mkstemp"
        ):
            targets = node.targets
            if (
                len(targets) == 1
                and isinstance(targets[0], ast.Tuple)
                and len(targets[0].elts) == 2
                and isinstance(targets[0].elts[0], ast.Name)
            ):
                self._legal_mkstemp_assigns.add(id(node.value))
                self._mkstemp_fd_targets[targets[0].elts[0].id] = node.lineno
            else:
                self.violations.append(
                    f"{self.path}:{node.lineno} mkstemp() must be assigned as an "
                    "(fd, name) tuple with the fd consumed via os.fdopen in a with-block"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        kind = _tempfile_call_attr(node, self._direct_names)
        if kind == "NamedTemporaryFile" and self._depth == 0:
            self.violations.append(
                f"{self.path}:{node.lineno} NamedTemporaryFile() outside with-block"
            )
        elif isinstance(func, ast.Attribute) and func.attr == "fdopen":
            if self._depth == 0:
                self.violations.append(f"{self.path}:{node.lineno} os.fdopen() outside with-block")
            else:
                for arg in node.args:
                    if isinstance(arg, ast.Name):
                        self._fdopen_consumed.add(arg.id)
                for kw in node.keywords:
                    if kw.arg == "fd" and isinstance(kw.value, ast.Name):
                        self._fdopen_consumed.add(kw.value.id)
        elif kind == "mkstemp" and id(node) not in self._legal_mkstemp_assigns:
            self.violations.append(
                f"{self.path}:{node.lineno} mkstemp() must be assigned as an "
                "(fd, name) tuple with the fd consumed via os.fdopen in a with-block"
            )
        self.generic_visit(node)

    def finish(self) -> list[str]:
        for name, lineno in self._mkstemp_fd_targets.items():
            if name not in self._fdopen_consumed:
                self.violations.append(
                    f"{self.path}:{lineno} mkstemp() fd never wrapped in os.fdopen with-block"
                )
        return self.violations


def _scan() -> list[str]:
    violations = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        scanner = _TempHandleScanner(path)
        scanner.visit(tree)
        violations.extend(scanner.finish())
    return violations


def test_src_temp_handles_in_with_blocks():
    violations = _scan()
    assert not violations, "dangling temp-file handles in src/:\n" + "\n".join(violations)


def test_guard_positive_controls(tmp_path):
    """The scanner must flag dangling-handle flavours."""
    cases = [
        (  # NTF assigned outside with (the pre-fix benchmark/executor pattern)
            "import tempfile\n"
            "f = tempfile.NamedTemporaryFile(mode='w', delete=False)\n"
            "f.close()\n"
        ),
        (  # mkstemp fd consumed by raw os.write instead of fdopen-with
            "import os\n"
            "import tempfile\n"
            "fd, name = tempfile.mkstemp(suffix='.json')\n"
            "os.write(fd, b'x')\n"
        ),
        ("import os\nfd = 3\nf = os.fdopen(fd)\n"),  # fdopen outside with
        (  # direct-name import + dangling NTF (bypass attempt)
            "from tempfile import NamedTemporaryFile\n"
            "f = NamedTemporaryFile(delete=False)\n"
            "f.close()\n"
        ),
        "import tempfile\ntempfile.mkstemp(suffix='.json')\n",  # bare mkstemp call
        "import tempfile\ntmp = tempfile.mkstemp()\n",  # single-name mkstemp assignment
    ]
    for source in cases:
        sample = tmp_path / "sample.py"
        sample.write_text(source, encoding="utf-8")
        tree = ast.parse(source)
        scanner = _TempHandleScanner(sample)
        scanner.visit(tree)
        assert scanner.finish(), f"scanner failed to flag: {source!r}"


def test_guard_negative_controls(tmp_path):
    """with-block NTF, mkstemp+fdopen-with and os.open+fdopen-with stay exempt."""
    cases = [
        (
            "import tempfile\n"
            "with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:\n"
            "    f.write(code)\n"
        ),
        (
            "import os\n"
            "import tempfile\n"
            "fd, name = tempfile.mkstemp(suffix='.json')\n"
            "with os.fdopen(fd, 'w', encoding='utf-8') as f:\n"
            "    json.dump(data, f)\n"
        ),
        (
            "import os\n"
            "descriptor = os.open(path, os.O_WRONLY | os.O_CREAT)\n"
            "with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:\n"
            "    stream.write(data)\n"
        ),
        (  # direct-name import consumed inside with
            "from tempfile import NamedTemporaryFile\n"
            "with NamedTemporaryFile(mode='w') as f:\n"
            "    f.write(code)\n"
        ),
        (  # fdopen keyword form inside with
            "import os\n"
            "import tempfile\n"
            "fd, name = tempfile.mkstemp()\n"
            "with os.fdopen(fd=fd, mode='w', encoding='utf-8') as f:\n"
            "    f.write('x')\n"
        ),
    ]
    for source in cases:
        sample = tmp_path / "sample.py"
        sample.write_text(source, encoding="utf-8")
        tree = ast.parse(source)
        scanner = _TempHandleScanner(sample)
        scanner.visit(tree)
        assert not scanner.finish(), f"scanner false positive: {source!r}"


def test_no_direct_fcntl_import_in_src():
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path.name == "file_lock.py":
            continue  # the sanctioned fcntl isolation point
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
                assert "fcntl" not in imports, (
                    f"{path}:{node.lineno} direct 'import fcntl' breaks Windows imports; "
                    "use src.utils.file_lock.exclusive_lock instead"
                )
            elif isinstance(node, ast.ImportFrom):
                members = [alias.name for alias in node.names]
                assert node.module != "fcntl" and "fcntl" not in members, (
                    f"{path}:{node.lineno} 'from fcntl import ...' breaks Windows imports; "
                    "use src.utils.file_lock.exclusive_lock instead"
                )


def test_msvcrt_branch_locks_and_unlocks_same_offset(monkeypatch):
    """Regression: msvcrt.locking is position-relative, so unlock must seek
    back to the locked anchor even after buffered writes advanced the position
    (payloads >= ~8KB flush mid-write)."""

    class FakeFile:
        def __init__(self):
            self.pos = 0

        def fileno(self):
            return 1

        def flush(self):
            pass

        def seek(self, pos):
            self.pos = pos

        def tell(self):
            return self.pos

        def write(self, data):
            self.pos += len(data)

    fake_file = FakeFile()
    calls: list[tuple[int, int, int]] = []

    class FakeMSVCRT:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(fd, mode, nbytes):
            calls.append((mode, fake_file.pos, nbytes))

    monkeypatch.setattr(fl, "fcntl", None)
    monkeypatch.setattr(fl, "msvcrt", FakeMSVCRT)

    with exclusive_lock(fake_file):
        fake_file.write("x" * 20000)  # forces OS position past the buffered flush boundary

    assert calls == [
        (FakeMSVCRT.LK_NBLCK, 0, 1),
        (FakeMSVCRT.LK_UNLCK, 0, 1),
    ], f"lock/unlock offsets drifted: {calls}"


def test_exclusive_lock_is_exclusive_and_released(tmp_path):
    target = tmp_path / "lockme.json"
    target.write_text("{}", encoding="utf-8")

    with open(target, "w", encoding="utf-8") as f1:
        with exclusive_lock(f1):
            with open(target, "a+", encoding="utf-8") as f2:
                if fl.fcntl is not None:
                    with pytest.raises(OSError):
                        fl.fcntl.flock(f2.fileno(), fl.fcntl.LOCK_EX | fl.fcntl.LOCK_NB)
                elif fl.msvcrt is not None:
                    with pytest.raises(OSError):
                        fl.msvcrt.locking(f2.fileno(), fl.msvcrt.LK_NBLCK, 1)
                else:
                    pytest.skip("no locking primitive on this platform")

    # Lock must be released once the context exits.
    with open(target, "a+", encoding="utf-8") as f3:
        if fl.fcntl is not None:
            fl.fcntl.flock(f3.fileno(), fl.fcntl.LOCK_EX | fl.fcntl.LOCK_NB)
            fl.fcntl.flock(f3.fileno(), fl.fcntl.LOCK_UN)
        elif fl.msvcrt is not None:
            fl.msvcrt.locking(f3.fileno(), fl.msvcrt.LK_NBLCK, 1)
            fl.msvcrt.locking(f3.fileno(), fl.msvcrt.LK_UNLCK, 1)


def test_exclusive_lock_noop_without_primitives(monkeypatch, tmp_path):
    monkeypatch.setattr(fl, "fcntl", None)
    monkeypatch.setattr(fl, "msvcrt", None)
    target = tmp_path / "noop.json"

    with open(target, "w", encoding="utf-8") as f:
        with exclusive_lock(f):
            f.write("ok")

    assert target.read_text(encoding="utf-8") == "ok"


def test_history_saves_without_fcntl(monkeypatch, tmp_path):
    """Simulate a platform with no locking primitives: save must still work."""
    monkeypatch.setattr(fl, "fcntl", None)
    monkeypatch.setattr(fl, "msvcrt", None)

    from src.incremental.history import IncrementalHistory

    target = tmp_path / "history.json"
    IncrementalHistory(runs=[]).save(target)

    loaded = IncrementalHistory.load(target)
    assert loaded.runs == []


def test_history_save_retries_then_raises(monkeypatch, tmp_path):
    from src.incremental import history as history_mod

    attempts: list = []

    @contextmanager
    def failing_lock(file_obj):
        attempts.append(file_obj)
        raise OSError("lock busy")
        yield  # pragma: no cover

    monkeypatch.setattr(history_mod, "exclusive_lock", failing_lock)

    history = history_mod.IncrementalHistory(runs=[])
    with pytest.raises(OSError):
        history.save(tmp_path / "history.json")

    assert len(attempts) == 3


def test_benchmark_temp_dataset_removed_on_harness_failure(tmp_path, monkeypatch):
    import tempfile as tempfile_mod

    from src.benchmark import executor as executor_mod
    from src.benchmark.suite import BenchmarkSuite
    from src.models import HarnessConfig, LLMConfig

    suite = BenchmarkSuite(name="suite", problems=["p1"], frozen=True, version="1.0")
    dataset_file = tmp_path / "ds.json"
    dataset_file.write_text(
        json.dumps(
            [
                {
                    "problem_id": "p1",
                    "title": "Problem 1",
                    "description": "Problem description for lock test",
                    "difficulty": "easy",
                    "tags": [],
                    "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
                }
            ]
        ),
        encoding="utf-8",
    )
    config = HarnessConfig(
        dataset_path=str(dataset_file),
        llm_config=LLMConfig(provider="openai", api_key="test-key", model="gpt-3.5-turbo"),
    )

    created: dict[str, str] = {}
    real_mkstemp = tempfile_mod.mkstemp

    def tracking_mkstemp(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        created["path"] = name
        return fd, name

    monkeypatch.setattr(tempfile_mod, "mkstemp", tracking_mkstemp)

    class ExplodingHarness:
        def __init__(self, harness_config):
            pass

        def run(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(executor_mod, "AlgorithmHarness", ExplodingHarness)

    executor = executor_mod.BenchmarkExecutor(suite, config)
    with pytest.raises(RuntimeError):
        executor.execute()

    assert created, "executor did not create a temp dataset"
    assert not Path(created["path"]).exists()
