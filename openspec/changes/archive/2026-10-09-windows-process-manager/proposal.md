## Why

当前 `src/sandbox_executor.py` 使用 Unix 专属的进程组管理（`start_new_session` 和 `os.killpg`）来实现超时控制与子进程清理。在 Windows 上 `os.killpg` 不存在，导致 `ProcessLookupError` 或 `AttributeError`，使得沙箱执行器无法在 Windows 平台正常终止超时进程及其子进程树。

## What Changes

- 新建 `src/utils/process_manager.py` 跨平台进程管理抽象层
- Unix 平台：继续使用进程组（`start_new_session` + `os.killpg`）
- Windows 平台：使用 Job Objects API（通过 `ctypes` 调用 `CreateJobObjectW` / `AssignProcessToJobObject`），超时后关闭 job 自动终止所有子进程
- 重构 `sandbox_executor.py`：使用统一的跨平台接口替代平台条件分支
- 为 Unix 专属进程组测试添加平台跳过标记，补充 Windows Job Objects 专属测试

## Capabilities

### New Capabilities

无新 capability。本次为纯实现重构，将现有进程管理从平台条件分支提升为显式抽象层。

### Modified Capabilities

- `windows-compatibility`: 追加进程管理跨平台需求（Requirement: 跨平台进程组与超时终止）

## Impact

- **受影响模块**: `src/sandbox_executor.py`（进程启动与终止逻辑）、新建 `src/utils/process_manager.py`
- **测试**: `tests/test_sandbox_executor.py` 需补充 Windows Job Objects 场景，现有 Unix 进程组测试需添加 `@pytest.mark.skipif(IS_WINDOWS, reason="Unix-specific")`
- **行为**: Unix 平台行为不变；Windows 平台首次获得完整的超时子进程树终止能力
- **依赖**: 无新增外部依赖（Job Objects 通过标准库 `ctypes` 调用 Windows API）
