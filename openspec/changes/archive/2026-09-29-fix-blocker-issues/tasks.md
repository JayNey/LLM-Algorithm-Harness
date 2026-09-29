## 1. 修复并发竞态条件

- [x] 1.1 在 `AlgorithmHarness.__init__` 中添加 `self._results_lock = threading.Lock()`，验证初始化代码编译通过
- [x] 1.2 在 `src/harness.py:228` 的 `_collect_cost_aware_results` 中使用 `with self._results_lock:` 保护 `self.results["cost_aware"] = results`，验证并发测试无竞态
- [x] 1.3 在 `src/harness.py:262` 的 worker 函数中使用 `with self._results_lock:` 保护 `self.results[strategy_config.name] = results`，验证并发测试无竞态

## 2. 替换 float 为 Decimal 进行成本计算

- [x] 2.1 在 `src/models.py` 顶部添加 `from decimal import Decimal` 导入，验证导入无错误
- [x] 2.2 修改 `TokenUsage.cost_estimate_usd` 属性（第438-446行）返回 `Decimal`，使用 `Decimal("0.0005")` 和 `Decimal("0.0015")` 作为定价常量，验证单元测试通过
- [x] 2.3 修改 `StrategyReport.total_cost_estimate_usd` 方法（第709-716行）返回 `Decimal`，验证成本计算测试通过
- [x] 2.4 更新所有调用 `cost_estimate_usd` 的代码以处理 `Decimal` 返回值，验证集成测试通过
- [x] 2.5 更新 `RunCostMonitor` 使用 `Decimal` 累计成本，验证成本累计精度测试通过

## 3. 加固 Docker 容器清理逻辑

- [x] 3.1 在 `src/sandbox_executor.py` 的 `_run_in_docker` 方法（第652-738行）中重构容器清理，移除 cleanup 参数传递，验证代码结构正确
- [x] 3.2 在 `_run_command` 调用外层添加 try-finally 块，在 finally 中执行 `subprocess.run(["docker", "rm", "--force", container_name], capture_output=True, timeout=5, check=False)`，验证容器清理在异常路径执行
- [x] 3.3 在清理失败时记录 `logger.warning("container_cleanup_failed", container=container_name, error=str(cleanup_exc))`，验证日志输出正确
- [x] 3.4 运行沙箱测试并手动触发超时异常，验证容器被正确清理且无泄漏

## 4. 验证和测试

- [x] 4.1 运行完整测试套件 `pytest tests/` 确保所有测试通过
- [x] 4.2 运行并发测试验证无竞态条件和数据损坏
- [x] 4.3 运行成本计算测试验证 Decimal 精度正确
- [x] 4.4 手动测试 Docker 容器清理在各种异常路径下都执行
