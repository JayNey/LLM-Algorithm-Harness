# LLM Algorithm Harness 代码审查报告

**审查日期**: 2026-09-28  
**审查范围**: 完整项目代码库  
**审查标准**: 安全性、正确性、性能、可维护性

---

## 执行摘要

本次审查发现：
- **BLOCKER**: 3个（必须立即修复）
- **SHOULDFIX**: 12个（应该在下个版本修复）
- **NIT**: 8个（可选改进）

最高优先级问题集中在并发安全、浮点数精度和Docker容器清理的异常处理路径。

---

## BLOCKER 级别问题

### [BLOCKER] 并发模式下的竞态条件风险

**位置**: `src/harness.py:58,228,262`

**问题描述**:
在并行执行模式下（`execution="parallel"`），多个worker线程可能同时访问和修改 `self.results` 字典和 `self.cost_monitor`，导致数据竞争和不一致的状态。

**当前代码**:
```python
# Line 58
self.results: Dict[str, List[ExecutionResult]] = {}

# Line 228 - 在worker函数中
self.results["cost_aware"] = results

# Line 262 - 在worker函数中
self.results[strategy_config.name] = results
```

**影响**:
- 结果丢失或覆盖
- cost_monitor的累计成本不准确
- 可能导致预算cap失效

**建议修复**:
```python
import threading

class AlgorithmHarness:
    def __init__(self, config: HarnessConfig, budget_tracker: Optional[BudgetTracker] = None):
        self.config = config
        self.budget_tracker = budget_tracker
        self.cost_monitor: Optional[RunCostMonitor] = None
        self.problem_loader = ProblemLoader()
        self.results: Dict[str, List[ExecutionResult]] = {}
        self.problem_totals: Dict[str, int] = {}
        self.task_record = None
        self._results_lock = threading.Lock()  # 添加锁保护
        
    def _collect_cost_aware_results(self, ...):
        # 使用锁保护results字典的写入
        with self._results_lock:
            self.results["cost_aware"] = results
```

**理由**:
字典的并发写入在CPython中虽然有GIL保护，但逻辑层面的竞态（如两个线程同时追加到同一个list）仍可能导致数据损坏。使用显式锁确保线程安全。

**优先级**: 高

---

### [BLOCKER] 浮点数成本计算存在精度问题

**位置**: `src/models.py:438-446,709-716`

**问题描述**:
使用 `float` 进行货币计算会导致精度丢失，累计误差可能影响成本统计和预算控制。

**当前代码**:
```python
@property
def cost_estimate_usd(self) -> float:
    """Estimate cost in USD (based on GPT-3.5 pricing)."""
    INPUT_PRICE_PER_1K = 0.0005
    OUTPUT_PRICE_PER_1K = 0.0015

    return (
        self.prompt_tokens * INPUT_PRICE_PER_1K / 1000
        + self.completion_tokens * OUTPUT_PRICE_PER_1K / 1000
    )
```

**影响**:
- 大量调用后累计误差显著（`0.1 + 0.2 != 0.3`）
- 预算cap可能在错误的边界触发
- 成本报告不准确

**建议修复**:
```python
from decimal import Decimal

@property
def cost_estimate_usd(self) -> Decimal:
    """Estimate cost in USD with precise decimal arithmetic."""
    INPUT_PRICE_PER_1K = Decimal("0.0005")
    OUTPUT_PRICE_PER_1K = Decimal("0.0015")

    return (
        Decimal(str(self.prompt_tokens)) * INPUT_PRICE_PER_1K / 1000
        + Decimal(str(self.completion_tokens)) * OUTPUT_PRICE_PER_1K / 1000
    )

# 同时需要修改PricingManager和所有成本累计逻辑使用Decimal
```

**理由**:
货币计算应使用 `Decimal` 保证精度，这是金融软件的标准实践。虽然当前误差可能很小，但在大规模实验中会累积。

**优先级**: 高

---

### [BLOCKER] Docker容器清理在某些异常路径下可能失败

**位置**: `src/sandbox_executor.py:697-702,627-639`

**问题描述**:
当 `_run_command` 在cleanup之前因超时或其他异常退出时，Docker容器可能未被正确清理，导致资源泄漏。

**当前代码**:
```python
def cleanup_container():
    subprocess.run(
        ["docker", "rm", "--force", container_name],
        capture_output=True,
        timeout=5,
    )

result = self._run_command(
    command,
    timeout=self.config.timeout_seconds + 2,
    env={"PATH": os.environ.get("PATH", "")},
    cleanup=cleanup_container,  # 只有在_run_command的finally中才会调用
    input_data=input_data,
)
```

**影响**:
- 长时间运行后可能累积大量停止的容器
- 消耗磁盘空间和Docker资源
- 最终可能导致Docker守护进程响应缓慢

**建议修复**:
```python
def _run_in_docker(self, code: str, test_input: Any, problem: Problem | None = None) -> Any:
    # ... 准备代码 ...
    
    with tempfile.TemporaryDirectory(prefix="llm-harness-sandbox-") as workdir:
        os.chmod(workdir, 0o755)
        runner_path = Path(workdir) / "runner.py"
        runner_path.write_text(wrapper, encoding="utf-8")
        runner_path.chmod(0o644)
        container_name = f"llm-harness-{uuid.uuid4().hex}"
        command = self._build_docker_command(workdir, str(runner_path), container_name)

        try:
            result = self._run_command(
                command,
                timeout=self.config.timeout_seconds + 2,
                env={"PATH": os.environ.get("PATH", "")},
                cleanup=None,  # 不依赖_run_command的cleanup
                input_data=input_data,
            )
            # ... 处理结果 ...
        finally:
            # 保证容器清理在所有退出路径执行
            try:
                subprocess.run(
                    ["docker", "rm", "--force", container_name],
                    capture_output=True,
                    timeout=5,
                    check=False,  # 即使容器不存在也不抛异常
                )
            except Exception as cleanup_exc:
                logger.warning(
                    "container_cleanup_failed",
                    container=container_name,
                    error=str(cleanup_exc)
                )
```

**理由**:
资源清理必须在所有异常路径执行，包括外层函数提前返回的情况。使用try-finally确保清理代码总是运行。

**优先级**: 高

---