## Why

Issue #154 要求成本追踪与预算管理的 Web API。#151 的业务库已持久化评估任务（`evaluations.spent_usd`）与基准运行（`benchmark_runs.cost_usd`），#172 提供认证与 owner 隔离；`src/budget.py`（BudgetTracker）、`src/cost_alert.py`（CostAlertManager）、`src/models.py`（PricingManager）、`src/cost_optimizer.py` 提供既有逻辑。用户级预算配置、预警规则与定价覆盖尚无持久化载体。

## What Changes

- Alembic 迁移 `0003`：`budgets`（每用户一份：全局上限 + 按难度分配 + 阈值行为）、`alert_rules`（阈值/通道/目标）、`alert_events`（触发历史）、`pricing_overrides`（追加式定价覆盖版本）。
- 成本查询 API：任务成本详情（跨四类任务表解析）、用户成本汇总（时间段）、趋势序列（按日聚合）、成本分解（按来源类型/模型/策略）。
- 预算管理 API：预算配置 get/upsert/update、使用情况（全局 used/remaining/percentage + 按难度比例估计，口径注明）。
- 预警配置 API：规则 CRUD + 触发历史表（运行期阈值评估与投递接线随 #149 队列落地，本 change 交付配置面与数据面）。
- 定价 API：目录读取（PricingManager 内置 + 自定义文件）、自定义覆盖入库（追加版本，成本查询侧生效；runner 侧接线随 #159）。
- 成本报告：任务成本报告；`/reports/cost-optimization` 从用户自己的 run 数据合成 comparison 喂 `src/cost_optimizer.build_advisory`。

## Capabilities

### New Capabilities
- `api/cost-management`: 成本查询聚合、预算/预警配置持久化与定价覆盖版本管理。

### Modified Capabilities
无。

## Impact

影响 `api/`（迁移 0003、新服务与路由）与文档。分析类 src 模块只被调用不修改；runner 侧定价/预警接线不在本 change。
