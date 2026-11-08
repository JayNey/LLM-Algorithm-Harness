## Why

Web 评估可以执行完成并保存结果，但未关联公开的运行标识，导致结果详情无法下载报告或打开单次分析。参见 [#393](https://github.com/JayNey/LLM-Algorithm-Harness/issues/393)。

## What Changes

- 在 Web 评估进入执行时持久化稳定的公开运行标识。
- 为已有落库单元的历史评估提供兼容标识，并复用报告和分析的所有权校验。
- 验证刷新后的报告下载、单次分析以及部分结果提示。

## Capabilities

### Modified Capabilities

- `api/evaluation-results` 的所有者范围内的结果查询。

## Impact

评估 worker、结果查询服务及相关验收测试。沿用现有 `evaluations.run_id` 字段、HTTP 接口和前端完整性判断。
