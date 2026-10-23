# 修复任务

- [x] 1. 新增确定性回归测试并记录 RED，修复历史文件锁定与刷盘顺序并确认 GREEN。
- [x] 2. 完成相关测试、格式检查及构建验证，检查根因消除并记录验证证据。

## 构建证据
- RED：`python3 -m pytest tests/test_incremental_history.py -q --no-cov`，4 failed / 9 passed：加锁前空文件、加锁失败丢失历史、解锁前未刷盘、读取未等待锁。
- GREEN：`python3 -m pytest tests/test_incremental_history.py tests/test_windows_file_handles.py -q --no-cov`，23 passed。
- 相关验证：`python3 -m pytest tests/test_incremental*.py tests/test_windows_file_handles.py tests/test_utf8_io.py -q --no-cov`，48 passed。
- `python3 -m black --check src/incremental/history.py tests/test_incremental_history.py`、`python3 -m ruff check src/incremental/history.py tests/test_incremental_history.py` 与 `git diff --check` 通过。
- 构建：`python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/history-hotfix-dist` 成功。最初 `python3 -m build` 因 build 模块缺失失败，改用已安装 pip 的 PEP 517 构建入口解决，无源码原因。
- 根因消除：save 不再以 w 打开，seek(0) 后加锁、锁内截断和 flush；load 在锁内解析 JSON。
