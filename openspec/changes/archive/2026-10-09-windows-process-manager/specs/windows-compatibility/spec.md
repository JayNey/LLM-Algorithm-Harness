## ADDED Requirements

### Requirement: 跨平台进程组与超时终止

沙箱执行器的进程启动与终止 SHALL 通过统一的跨平台抽象层实现，而非在调用处直接使用平台条件分支。Unix 平台 SHALL 使用进程组（`start_new_session=True` + `os.killpg`）；Windows 平台 SHALL 使用 Job Objects API（通过 `ctypes` 调用 `CreateJobObjectW` / `AssignProcessToJobObject` / `TerminateJobObject`）。超时或异常时 SHALL 终止目标进程及其所有子进程树。

#### Scenario: Unix 平台沙箱超时终止进程组

- **WHEN** 在 macOS/Linux 上沙箱执行超时
- **THEN** 目标进程及其创建的所有子进程通过 `os.killpg` 被一次性终止

#### Scenario: Windows 平台沙箱超时终止 Job

- **WHEN** 在 Windows 上沙箱执行超时
- **THEN** 目标进程及其创建的所有子进程通过关闭 Job Object 被一次性终止

#### Scenario: 跨平台抽象层可导入

- **WHEN** 在任意平台上导入 `src.utils.process_manager`
- **THEN** 模块成功导入，不抛出 `AttributeError` 或 `ModuleNotFoundError`

#### Scenario: 沙箱执行器使用统一接口

- **WHEN** `sandbox_executor.py` 需要启动或终止进程
- **THEN** 通过 `process_manager` 提供的统一接口完成，而非在调用处直接使用 `if os.name == "nt"` 条件分支

#### Scenario: 进程终止失败时优雅降级

- **WHEN** 进程已提前退出导致终止调用失败（Unix `ProcessLookupError`，Windows `OSError`）
- **THEN** 异常被捕获并静默处理，不中断清理流程
