## Why

代码审查发现三个 BLOCKER 级别的关键问题，可能导致数据损坏、资源泄漏和成本统计不准确，必须立即修复以确保系统的可靠性和正确性。

## What Changes

- 在并发执行模式下为 `self.results` 和 `self.cost_monitor` 添加线程锁保护，消除竞态条件
- 将所有成本计算从 `float` 替换为 `Decimal`，确保货币计算精度
- 加固 Docker 容器清理逻辑，使用 try-finally 确保所有异常路径都执行清理

## Capabilities

### New Capabilities
<!-- 本次修复不引入新能力 -->

### Modified Capabilities
- `cost-estimation/custom-pricing`: 成本计算精度要求从浮点数提升为 Decimal，影响 PricingManager 和所有成本累计逻辑
- `sandbox-preflight`: Docker 容器清理机制加强，确保资源不泄漏

## Impact

**受影响模块**:
- `src/harness.py`: 添加线程锁，保护并发写入
- `src/models.py`: TokenUsage 和 PricingManager 的成本计算改用 Decimal
- `src/sandbox_executor.py`: Docker 容器清理逻辑重构为 try-finally 模式

**API 变化**:
- `cost_estimate_usd` 属性返回类型从 `float` 变更为 `Decimal` (**BREAKING**)
- PricingManager 相关方法返回类型从 `float` 变更为 `Decimal` (**BREAKING**)

**依赖变化**:
- 无新增外部依赖（Decimal 是标准库）
