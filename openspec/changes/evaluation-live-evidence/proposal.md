## Why

#232 要求把真实评估流程的 API、数据库、Redis/Celery、沙箱、模型提供方与浏览器联调证据分层记录。当前本地没有运行中的 Harness 服务，也没有可确认属于本人的测试账号、应用 API key 或明确预算；已有 Chromium fixture 不能证明真实端到端完成。

## What Changes

- 新增 `docs/frontend/EVALUATIONS_QA.md`，分别说明 fixture 验证与真实联调步骤。
- 记录本次只读环境盘点、缺少的依赖、未执行层级和恢复条件。
- 明确凭证与预算安全边界，防止 fixture、Codex 主机凭证或健康检查被写成真实模型成功证据。

## Capabilities

### New Capabilities

无。此次仅整理验收证据和恢复步骤，不改变产品行为。

### Modified Capabilities

无。本 change 只处理文档和验收记录。

## Impact

- 新增 `docs/frontend/EVALUATIONS_QA.md`。
- 不更改运行时代码，也不启动付费模型请求。
- 正式 T17 联调仍须等 #231 完成并合入 main；真实运行还要求可用测试账号、本人配置的 provider key、可访问的 API/Redis/Celery/沙箱和用户确认的小额预算。
