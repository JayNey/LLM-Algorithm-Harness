## Why
Issue #158 第 5 节缺少可重复执行的 API 性能测试及数据库查询基准。

## What Changes
- 使用可选 Locust 依赖建立负载、压力、并发读测试，保留失败与延迟数据。
- 使用临时数据库和真实应用建立 HTTP 响应及查询基准，输出环境、样本量、吞吐量和分位数。
- 提供运行文档、基准样本和工具自检。

## Capabilities
### New Capabilities
无；仅测试工具。
### Modified Capabilities
无；不改变 API、数据库 schema 或生产行为，skip_specs: true。

## Impact
范围为 tests/performance 和 pyproject.toml 的可选测试依赖；不调用外部 LLM 或启动任务。
