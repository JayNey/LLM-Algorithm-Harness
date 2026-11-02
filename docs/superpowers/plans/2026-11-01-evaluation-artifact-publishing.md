---
change: evaluation-artifact-publishing
design-doc: openspec/changes/evaluation-artifact-publishing/design.md
base-ref: 06f8d4e85ae5cb0edbadaba796b79115e019a948
---

# 实施计划

<!-- comet-task-authority: openspec/changes/evaluation-artifact-publishing/tasks.md -->

采用用户确认的 autonomous / tdd / standard。范围及技术取舍以已确认 design.md 和 delta spec 为准。保持独立分支；修复在该范围内的问题，无需重复确认；不自动合并 PR。

按以下依赖顺序实施。每项先写能复现待实现行为的测试，记录真实 RED，再写最小实现并记录 GREEN；环境错误不记为行为 RED。任务状态只更新 tasks.md。受风险影响的分段和最终集成由独立审查者核对。

## 1.1

<!-- comet-task-ref:714ee1d7-5776-4573-b4d1-d28107985c61 -->

1.1 添加原始执行载荷与当前发布记录的兼容模型/迁移；验证旧数据库升级/降级、新旧结果空值语义和 PostgreSQL 离线 SQL。

## 1.2

<!-- comet-task-ref:920bbb87-dd55-40df-aba1-54382c5c9de9 -->

1.2 实现真实结果快照、完整性计算和单调版本分配；以测试验证快照与已提交行一致、未知字段不补造、重复内容幂等和旧代际拒绝。

## 2.1

<!-- comet-task-ref:7ebc2395-4101-43ff-a5cb-ad7a115ecbc2 -->

2.1 扩展文件版本/摘要和候选激活流程；故障与竞争测试验证旧版本拒绝、同版本幂等、激活后确认前崩溃恢复及配额/候选清理。

## 2.2

<!-- comet-task-ref:32792741-abaf-4cd8-8676-f356f7f39e5d -->

2.2 接入 Worker 单元/生命周期持久化边界与独立发布任务；真实编排测试覆盖完成、暂停/恢复、失败/取消、提交后退出，确认发布失败不改变执行真值。

## 2.3

<!-- comet-task-ref:6d8967f8-a8b7-4632-ad3a-b762cd61bbdf -->

2.3 实现认证的发布状态/独立重试和安全错误分类；HTTP 测试验证归属、CSRF、无结果、重复请求、队列失败、文件过期和重试不增加模型调用。

## 2.4

<!-- comet-task-ref:4c7c62cb-c182-457f-8bb1-df8e2bad5d4a -->

2.4 兼容版本化产物的多格式下载与完整性元数据；解析 JSON/CSV/Markdown/HTML/PNG/ZIP，验证执行原始字段、P8 元数据、未知费用及旧格式回归。

## 3.1

<!-- comet-task-ref:072dce93-1669-4901-8445-856a7ae7afbe -->

3.1 完成 Worker → 发布 → HTTP 下载的完整集成链、跨账号/删除/延迟消息/清理回归、定向测试及格式类型编码检查；更新 API 文档并提交可复跑验证报告。

## 3.2

<!-- comet-task-ref:c4eb5f79-0f22-4cde-831f-0f15e2943341 -->

3.2 完成分段独立审查并修复问题，核对规格和提交归属，备齐独立 PR 交付材料；以实际复审、检查及提交记录验收。

## 实施边界与回退

以现有 HTTP 客户端、所有者与实体关联为信任边界；不得从 UI 标识猜测任务。先验证合同和纯状态策略，再接观察/发布与界面/路由，最后跑跨模块联调。失败先定位根因并补回归；保留通过检查对应的提交引用和故障证据。

模型与迁移 → 持久化快照 → 单调文件激活/回收 → Worker/独立任务 → HTTP 状态重试 → 多格式 → 完整链验证。先落实业务锁顺序、跨库崩溃幂等和删除 tombstone，再接发布，文件渲染在锁外。发布失败不回写执行 failed；无原始执行载荷保持 null。配额严格计实际并存占用，记录不足而不超额。

检查：pytest 定向新发布/文件/评估执行回归，Alembic 升降级和 PostgreSQL 离线 SQL、ruff、black、相关 mypy 及编码扫描；可控模型替身走真实 Worker → 业务库 → 文件服务 → 受认证 HTTP 下载。注入队列、文件及提交失败，测试版本竞争/重复/旧代际/删除/过期/配额。回滚先停止新发布任务，再回滚代码；不自动数据库降级删除数据。
