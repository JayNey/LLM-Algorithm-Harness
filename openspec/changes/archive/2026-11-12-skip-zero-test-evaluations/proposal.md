## Why

缺少全部测试用例的导入题仍可获得成功判定，导致 CLI 与 Web 的通过率失真（#477）。

## What Changes

- 共享评估入口将公开、反馈和隐藏用例均为空的题标记为 `not_evaluable`，说明缺少测试用例。
- CLI 与 Web 保留逐题逐策略记录，并从通过率分母和失败分析中排除该状态。
- 验证已有导入格式及仅有反馈或隐藏用例时的执行路径。

## Capabilities

### New Capabilities

### Modified Capabilities

- `execution-protocol`：定义零用例单元的评估结果。
- `api/evaluation-results`：明确结果明细与通过率统计口径。

## Impact

共享 Harness、CLI 汇总、Web 结果查询及展示。沿用现有题目和结果存储结构。
