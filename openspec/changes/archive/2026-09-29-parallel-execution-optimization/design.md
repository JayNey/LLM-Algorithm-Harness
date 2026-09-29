# Design: 并行执行优化

## 实现方案

基于现有的 `TaskService` 架构，该服务已经实现了基于 `ThreadPoolExecutor` 的并行框架。本次优化将：

1. **利用现有并行能力**：`TaskService` 已在 `src/task_service.py` 中实现了 `max_workers` 参数和并发执行
2. **扩展配置支持**：在 `HarnessConfig` 中添加 `max_workers` 配置项
3. **增强进度监控**：使用 `rich` 库实现实时进度条
4. **完善成本追踪**：确保 `RunCostMonitor` 的线程安全性

## 技术细节

### 1. 并行执行架构

`TaskService.run()` 方法已实现：
- 使用 `ThreadPoolExecutor` 管理工作线程池
- 通过 `max_workers` 参数控制并发数
- 支持任务单元的独立执行和结果收集

现有代码位置：
- [src/task_service.py:133-228](src/task_service.py#L133-L228) - TaskService 类
- [src/harness.py:120-271](src/harness.py#L120-L271) - `_run_with_task_service` 方法

### 2. 配置增强

在 `src/models.py` 的 `HarnessConfig` 中添加：
```python
max_workers: int = Field(default=5, ge=1, le=20)
```

### 3. 进度监控

使用 `rich.progress` 实现：
- 实时显示已完成/总任务数
- 显示当前成功率
- 显示预计剩余时间
- 支持多策略并行进度跟踪

### 4. 资源控制

- Docker 容器资源限制：通过 `SandboxConfig` 的现有 `memory_limit_mb` 配置
- LLM API 速率限制：通过 `max_workers` 隐式控制并发请求数
- 成本预算控制：利用现有的 `RunCostMonitor` 和 `budget_cap_usd`

### 5. 线程安全

确保以下组件的线程安全：
- `RunCostMonitor`：已有锁机制保护成本累计
- `AlgorithmHarness.results`：已有 `_results_lock` 保护
- `TaskService.store`：使用 `threading.RLock` 保护文件写入

## 非功能性需求

- **性能目标**：提升评估速度 5-10 倍
- **资源限制**：默认 5 个并发工作线程，可配置到 20
- **错误处理**：单个任务失败不影响其他任务
- **可观测性**：实时进度显示，详细日志记录
