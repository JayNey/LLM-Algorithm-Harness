## Why
普通评估执行个人题，但标签分析关联公共题库，导致标签缺失、同 ID 覆盖混用及历史漂移（#318）。

## What Changes
- 保存实际执行题目的标签、难度和来源快照，检查点恢复使用冻结题目。
- 标签筛选、成功率、失败统计和雷达统一优先快照，空标签不降级。
- 明确历史无快照记录兼容行为，补齐 Worker 到 HTTP 的回归及文档。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `api/evaluation-execution`: 执行题目快照与分析一致性。

## Impact
Worker、TaskUnit 检查点、结果查询服务、回归测试、API 文档；无新端点、无数据库迁移。用户已选择新建 tweak/20261030/execution-metadata-analysis 分支，继续单一 tweak，接受跨模块范围。
