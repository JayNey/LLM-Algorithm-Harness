# Windows Support

As of October 2026, LLM Algorithm Harness fully supports Windows platforms.

## Status

✅ **All tests passing** on Windows with Python 3.11 and 3.12

The project is tested on Windows via GitHub Actions CI (`windows-latest`).

## What Was Fixed

### 1. Cross-Platform Process Management (PR #144)

Windows doesn't support POSIX process groups. We implemented platform-specific solutions:

- **Unix/Linux/macOS**: Uses process groups (`os.setpgrp`, `os.killpg`)
- **Windows**: Uses Job Objects API via ctypes with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`

The abstraction is in `src/utils/process_manager.py` and handles:
- Process tree termination
- Timeout enforcement
- Output capture with size limits
- Graceful fallback on Windows permission issues

### 2. UTF-8 Encoding

All file operations explicitly specify `encoding='utf-8'` to avoid Windows' default `cp1252` encoding issues.

### 3. File Handle Management

Windows has stricter file locking than Unix. Temporary files are properly closed before deletion or renaming.

### 4. Path Handling (PR #146)

Cross-platform path handling using `pathlib.Path` throughout the codebase.

### 5. Test Timing Precision

Tests that rely on precise timing use larger margins to accommodate platform differences in `time.sleep()` precision.

## Development on Windows

### Prerequisites

- Python 3.11 or 3.12
- Git for Windows

### Setup

```bash
# Clone the repository
git clone https://github.com/JayNey/LLM-Algorithm-Harness.git
cd LLM-Algorithm-Harness

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all offline tests
pytest -m "not online"

# Run with coverage
pytest --cov --cov-report=term

# Run specific test file
pytest tests/test_process_manager.py -v
```

### Known Limitations

- Docker-based sandbox tests are skipped on Windows (Docker Desktop for Windows has different permission models)
- Some network-dependent tests may require additional firewall configuration

## CI Configuration

Windows tests run on every PR and push to main:

```yaml
- Python 3.11 on windows-latest
- Python 3.12 on windows-latest
```

All tests must pass on all platforms (Linux, macOS, Windows) before merging.

## Troubleshooting

### UTF-8 Encoding Errors

If you encounter `UnicodeDecodeError` with 'charmap' codec, ensure:

1. All file operations use `encoding='utf-8'`
2. Subprocess calls use `text=True, encoding='utf-8'`
3. Set `PYTHONUTF8=1` environment variable as a global default

### Process Termination Issues

The process manager automatically detects the platform and uses the appropriate termination strategy. If you encounter issues:

1. Check Windows Event Viewer for access denied errors
2. Run tests as Administrator if needed (though this shouldn't be required)

### File Access Errors

Windows keeps file handles open longer than Unix. If you see "file in use" errors:

1. Ensure files are closed in `finally` blocks or context managers
2. Use `delete=False` with `NamedTemporaryFile` and manually delete after closing

## Related Issues

- Issue #118: Windows Compatibility Support
- PR #144: Cross-platform process management
- PR #146: Windows path compatibility
- Issue #137: Process management for sandbox host backend

## Credits

Windows compatibility work was completed in October 2026, with significant contributions addressing process management, encoding, and file handling issues.
