## Context

当前 `src/sandbox_executor.py` 在 `_run_with_output_limit` 和 `_terminate_process_group` 中使用平台条件分支来处理进程组管理：Unix 使用 `start_new_session=True` 创建进程组并通过 `os.killpg` 终止，Windows 则回退到简单的 `process.kill()`，无法终止子进程树。这导致 Windows 平台上超时子进程可能泄漏，且平台差异分散在调用点。

## Goals / Non-Goals

**Goals:**
- 提供统一的跨平台进程管理接口（启动、终止整个进程树）
- Windows 平台通过 Job Objects 实现完整的子进程树终止能力
- Unix 平台行为保持不变（进程组语义）
- 消除 `sandbox_executor.py` 中的平台条件分支

**Non-Goals:**
- 不改变沙箱超时时长或重试逻辑
- 不引入第三方进程管理库（使用标准库 `ctypes` + Windows API）
- 不改变 Docker 后端的进程管理（Docker 容器生命周期由 Docker 管理）

## Decisions

### 决策 1: 新建独立抽象层 `src/utils/process_manager.py`

**选择**: 创建专门的进程管理模块，提供 `ManagedProcess` 类封装平台差异

**理由**:
- 集中平台差异处理，避免在业务逻辑中散落 `if os.name == "nt"`
- 便于单元测试（可独立测试 Unix/Windows 路径）
- 未来其他模块如需进程组管理可复用

**替代方案**:
- 保持现状在 `sandbox_executor.py` 内部处理：代码耦合度高，测试困难
- 使用第三方库如 `psutil`：引入额外依赖，且 Job Objects 需求较特化

### 决策 2: Windows 使用 Job Objects 而非进程树遍历

**选择**: 通过 `ctypes` 调用 Windows Job Objects API (`kernel32.CreateJobObjectW`, `AssignProcessToJobObject`, `CloseHandle` 触发终止)

**理由**:
- Job Objects 是 Windows 内核级别的进程组机制，关闭 job 句柄时自动终止所有关联进程
- 无需手动遍历进程树（进程树遍历在快速 fork 场景下存在竞态窗口）
- Python 标准库 `ctypes` 可直接调用，无需第三方依赖

**替代方案**:
- 使用 `psutil.Process.children(recursive=True)` 遍历终止：引入外部依赖，且存在 TOCTOU 竞态
- 仅终止父进程：无法清理子进程树，违背规格要求

### 决策 3: 接口设计为上下文管理器

**选择**: `ManagedProcess` 实现 `__enter__` / `__exit__`，在 `__exit__` 中自动终止

```python
with ManagedProcess(command, ...) as proc:
    # 使用 proc.process (subprocess.Popen)
    pass
# 离开 with 块时自动终止进程树
```

**理由**:
- 与现有 `subprocess.Popen` 生命周期模式一致
- 保证异常路径下也能执行清理
- 调用方无需显式调用终止方法

**替代方案**:
- 显式 `terminate()` 方法：容易在异常路径下遗漏调用

## Risks / Trade-offs

**[风险] Windows Job Objects API 调用失败（权限、系统限制）** → Mitigation: `CreateJobObjectW` 失败时 fallback 到 `process.kill()` 并记录 warning 日志，保持向后兼容

**[风险] ctypes 声明错误导致 Windows 崩溃** → Mitigation: 充分的 Windows 平台测试，参考 CPython 内部实现和 MSDN 文档确保签名正确

**[Trade-off] Job Objects 无法嵌套（已在 Job 中的进程无法再加入新 Job）** → 影响有限：沙箱场景下进程由 harness 直接启动，不存在嵌套 Job 场景；若未来需要嵌套，可通过 `JOB_OBJECT_LIMIT_BREAKAWAY_OK` flag 允许子进程逃逸

**[Trade-off] Unix 进程组语义与 Windows Job Objects 存在细微差异** → 影响有限：两者都满足"终止整个子进程树"的核心需求；差异（如信号传递语义）不影响沙箱超时终止场景

## Migration Plan

1. 实现 `src/utils/process_manager.py`（Unix 和 Windows 路径）
2. 在 `sandbox_executor.py` 中替换 `_terminate_process_group` 和 `subprocess.Popen` 调用点
3. 运行现有测试套件确认 Unix 平台无回归
4. 在 Windows 环境运行测试确认 Job Objects 路径工作正常
5. 合并后无需部署步骤（纯实现重构，无配置或数据迁移）

**Rollback**: Git revert 即可，无外部依赖或配置变更
