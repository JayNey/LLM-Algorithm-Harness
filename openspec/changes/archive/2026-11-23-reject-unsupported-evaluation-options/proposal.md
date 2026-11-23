# 评估执行选项的明确拒绝

## Why

Issue #513 指出公开评估 API 接受 `timeout_seconds` 和 `max_concurrency`，但没有持久化或应用，导致创建和更新成功响应产生错误预期。现有执行器为预算控制固定串行，沙箱超时是每个测试用例 5 秒，不能直接等同于 API 宣称的每题超时。

## What Changes

- 采用 Issue 明确允许的“入口拒绝不支持值并更新契约”方向：显式传入这两个尚不支持的配置字段时，返回字段级 HTTP 400 `validation_error`；PATCH 显式传入 `timeout_seconds` 同样拒绝。
- 所有继承评估创建请求的入口统一校验，包含普通创建、异步创建与个人集合版本创建；拒绝发生在持久化、启动及消息发布之前。
- 省略上述字段的请求继续按现有执行行为运行，`generation_timeout_seconds` 仍按原有契约保存、传递。
- OpenAPI 将遗留字段标记为不支持并弃用，示例移除它们；文档给出省略字段的迁移方式及当前真实限制。
- **BREAKING（待用户批准）**：原先显式发送这些字段会成功但被忽略的调用，现在返回 400。此项是对 v1 静默忽略行为的定向纠错，必须在本次 Open 确认时明确批准，并在版本文档记录契约收紧；不能将其称为完全兼容变更。仅定向同步弃用标记，不重录或放宽 OpenAPI 门禁。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/evaluation-execution`：评估创建与更新入口拒绝未实现的执行配置，并公开真实执行限制。

## Impact

工作区沿用当前目录与 `main` 分支。预计最多六个交付文件：`api/models.py`、`API.md`、`docs/api-versioning.md`、`tests/integration/test_api_workflows.py`、`tests/test_api_evaluations.py`、`tests/fixtures/openapi-v1.json`。不增加数据库字段，不修改执行器或并发调度；若实际实施需要改变范围，沿原 Run 重新复核。执行配置采用 Runtime 当前值：`direct/direct/off`，规格验证覆盖本次 delta。

验证包含真实 HTTP 请求、数据库无新增/无变更、消息未发布，以及合法省略字段请求从持久化到 worker 的固定串行与沙箱配置；使用离线供应商替身，不调用付费模型。
