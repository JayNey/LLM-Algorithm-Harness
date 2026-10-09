# windows-compatibility Specification

## Purpose
建立 Windows 兼容契约中"文件锁定与句柄时序"部分：历史运行记录的并发写保护在所有平台真实生效（或显式降级），临时文件句柄遵循"先关后删"时序。本 capability 由上游 issue #138 重建（编码类需求由 `text-encoding` capability 承担）；后续 #137（进程管理）、#139（路径差异）在同一 capability 下追加需求。

## Requirements

### Requirement: 跨平台历史文件写锁

`IncrementalHistory.save()` 的并发写保护 SHALL 在 fcntl（Unix）、msvcrt（Windows）之上实现为跨平台排他锁，且 SHALL NOT 因平台缺少 fcntl 而无法导入或保存；两者皆缺时锁 SHALL 降级为 no-op 并输出 debug 日志。锁获取失败时 SHALL 保留既有的重试语义（默认 3 次后抛 OSError）。

#### Scenario: Unix 锁行为不变

- **WHEN** 在 macOS/Linux 上并发调用 save() 与既有测试
- **THEN** 写入串行化、内容完整，行为与改动前一致

#### Scenario: 无 fcntl 平台可导入可保存

- **WHEN** 在没有 fcntl 模块的平台上导入 `src.incremental.history` 并执行 save()
- **THEN** 模块导入成功、保存成功（Windows 经 msvcrt 真实加锁），不抛 ModuleNotFoundError

#### Scenario: 锁获取失败按重试语义放弃

- **WHEN** 锁持续被占用导致加锁失败
- **THEN** save() 重试至默认 3 次后抛出 OSError，且日志记录每次失败

### Requirement: 临时文件句柄先关后删

src/ 中所有 `tempfile.NamedTemporaryFile` 与 `tempfile.mkstemp` 的使用 SHALL 处于 with 块（或 `os.fdopen` 包装的 with 块）内，保证任何路径上的删除/替换发生在句柄关闭之后。

#### Scenario: 守护扫描拦截悬空句柄

- **WHEN** src/ 下出现不在 with 块内的 NamedTemporaryFile/mkstemp 调用
- **THEN** 守护测试失败并列出违规位置

#### Scenario: benchmark 执行异常路径不泄漏句柄

- **WHEN** benchmark 套件执行中途抛出异常
- **THEN** 临时数据集文件仍被清理，且清理发生在句柄关闭之后（无悬空句柄形态）

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
