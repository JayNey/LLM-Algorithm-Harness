# 设计：拒绝尚未实现的评估执行配置

## Context

动机见 proposal.md。已核对 `api/models.py`、`api/services/evaluation_service.py`、`api/db/models.py` 和 `src/tasks/evaluation.py`：创建请求字段没有落库，更新只处理预算，worker 固定 `max_workers=1`，构造默认 `SandboxConfig()`。历史设计 `docs/superpowers/specs/2026-10-13-evaluation-real-executor-design.md` 第 6 节也明确将两个字段留待后续支持。

## Goals / Non-Goals

入口返回的成功与真实执行能力一致。实现采用 Issue 允许的明确拒绝方向；不引入每题总时限调度机制，不将每题超时重解释为每个测试用例超时，不开启共享策略、重试预算状态的并行执行。

## Decisions

1. 在请求模型按字段校验显式提供的 `timeout_seconds`、`max_concurrency`。用字段校验器使错误定位到对应字段；任何显式值都拒绝，包括历史 schema 默认值和 null，防止调用方误以为设置成功。省略字段不触发校验，保留既有合法请求。
2. 复用创建基类校验覆盖派生模型；更新模型单独拒绝显式超时。错误说明字段暂不支持并要求省略，不泄露凭证。
3. 保留遗留字段的 schema 形状与默认值以减少结构变更，但通过描述和弃用标记明确：默认值是历史兼容占位，不是实际执行参数。请求示例不再发送它们。仅按实际生成差异同步三个请求组件的弃用标记，兼容门禁保持严格比较。
4. 在版本说明中明确这项运行时输入收紧，需要用户对本次 v1 修复例外的明确批准。若用户希望持久化并贯通两个参数，则本提案不适用，需先重新确定预算、并发状态和超时语义。

## Risks / Trade-offs

- 显式发送遗留默认值的旧客户端也会收到 400 → API 文档给出删除字段的迁移示例；用户先批准这一行为变化。
- OpenAPI 历史数字默认值不能代表有效配置 → 描述明确字段不可设置、标记弃用并从示例删除；测试检查公开说明。
- 只测试请求 schema 会漏掉副作用 → 真实鉴权 HTTP 测试核对持久化、PATCH 前后记录与 broker 发布次数；合法请求还跟踪真实 worker 的 TaskService 和 HarnessConfig。
- 不提供自定义超时或并发能力 → 文档明确当前执行语义；需要该能力时另行设计与实施。

## Migration Plan

调用方删除创建请求中的 `timeout_seconds` 和 `max_concurrency`，删除 PATCH 中的 `timeout_seconds`；模型请求时限继续使用独立的 `generation_timeout_seconds`。本次不要求数据迁移。回滚为撤销入口校验及相应文档与测试变更。
