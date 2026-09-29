## Context

当前代码存在三个关键缺陷：
1. `AlgorithmHarness` 在并行模式下多个 worker 线程同时写入 `self.results` 字典，存在竞态条件
2. 成本计算使用 `float`，在大量调用后累计误差显著（`0.1 + 0.2 != 0.3`）
3. `SandboxExecutor._run_in_docker` 的容器清理依赖 `_run_command` 的 cleanup 参数，在某些异常路径下可能未执行

## Goals / Non-Goals

**Goals:**
- 确保并发执行模式下 results 和 cost_monitor 的线程安全
- 使用 Decimal 进行精确的货币计算
- 保证 Docker 容器在所有退出路径都被清理

**Non-Goals:**
- 不改变现有的并发执行逻辑（仍使用 ThreadPoolExecutor）
- 不优化成本计算性能（Decimal 略慢于 float，但精度更重要）
- 不重构整个沙箱执行器

## Decisions

### Decision 1: 使用 threading.Lock 保护共享状态

**方案**: 在 `AlgorithmHarness.__init__` 中添加 `self._results_lock = threading.Lock()`，在所有写入 `self.results` 的位置使用 `with self._results_lock:`

**理由**: 
- CPython 的 GIL 不保护逻辑层面的竞态条件（如两个线程同时追加到列表）
- Lock 是最简单直接的同步原语，性能开销可忽略

**备选方案**:
- 使用 `queue.Queue`: 过度设计，需要重构现有的结果收集逻辑
- 使用进程池代替线程池: 开销更大，且无法共享 cost_monitor

### Decision 2: 全面采用 Decimal 进行成本计算

**方案**: 
- `TokenUsage.cost_estimate_usd` 返回 `Decimal`
- `PricingManager` 所有定价相关方法返回 `Decimal`
- `RunCostMonitor` 使用 `Decimal` 累计成本
- 定价常量使用字符串初始化 `Decimal("0.0005")` 避免浮点数污染

**理由**:
- 货币计算的行业标准实践
- Python `decimal` 模块是标准库，无需新增依赖
- 虽然性能略低，但成本计算不是热路径

**备选方案**:
- 使用整数分（cents）: 需要大量转换代码，可读性差
- 继续使用 float 并增加容差: 治标不治本，累计误差仍存在

**Breaking Change**: `cost_estimate_usd` 返回类型变更，调用方需要适配（但项目内部调用，影响可控）

### Decision 3: 在 _run_in_docker 层面使用 try-finally 清理容器

**方案**: 
- 移除 `_run_command` 的 cleanup 参数
- 在 `_run_in_docker` 中直接使用 try-finally 包裹容器执行和清理
- 清理失败时记录 warning 日志但不抛异常（`check=False`）

**理由**:
- try-finally 保证清理代码在所有退出路径执行（包括提前 return、异常等）
- 清理逻辑靠近资源创建点，更容易理解和维护
- 清理失败不应影响主流程结果（容器可能已被删除）

**备选方案**:
- 使用 contextlib.contextmanager: 更优雅但需要重构现有结构
- 依赖 Docker 的自动清理: 不可靠，长时间运行会累积停止的容器

## Risks / Trade-offs

**[Risk]** Decimal 性能略低于 float  
→ **Mitigation**: 成本计算不在热路径，性能影响可忽略；精度比性能重要

**[Risk]** 线程锁可能成为瓶颈  
→ **Mitigation**: results 写入频率低（每个问题完成后），锁竞争不会成为问题

**[Risk]** Breaking change 影响下游  
→ **Mitigation**: 项目内部 API，影响范围可控；测试覆盖可验证兼容性

**[Trade-off]** try-finally 增加代码嵌套层级  
→ **Accept**: 清晰的资源清理语义比扁平结构更重要
