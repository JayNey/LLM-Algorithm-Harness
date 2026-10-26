## Why

真实评估流程（#234 基线）落地后，工作台仍保留全局「业务 · Mock」标注与 Mock 创建弹窗：侧栏、快速操作、空状态和示例页的「创建评估」都会弹出示例表单并模拟提交反馈，与已上线的真实创建页 `/evaluations/new` 并存，误导用户以为创建仍是演示。T13（上游 #228）要求把这些显式创建入口统一到真实流程，并按区域诚实标注 Mock 边界。

## What Changes

- `Shell.onCreate` 从弹出 Mock 创建弹窗改为导航到真实创建页 `/evaluations/new`；删除 `MockActions` 的创建分支与「示例配置已确认」模拟反馈；导入题目示例保留。
- 移除外壳级全局 Mock 标注（顶栏「业务 · Mock」、侧栏 mock-note、页脚与风格选择器的「业务与通知 · Mock」）；Mock 区域（示例仪表盘、帮助页、通知中心、导入弹窗）保留各自的显式 Mock 标注。
- 通知中心保持 Mock：种子通知只指向真实列表/帮助路由（`/results`、`/evaluations`、`/help`），不引用虚构详情 ID；示例仪表盘的示例任务只在 Mock 抽屉中查看，不渲染成真实详情路由。
- 面包屑对创建/任务详情/结果详情的匹配补齐单测锁定（`/evaluations/new`、`/evaluations/:evaluationId`、`/results/:evaluationId`）。
- 修复 `verify-shell.mjs` 自 #214 后未随真实页面更新的过期业务断言（改锚定示例仪表盘与真实创建页导航，并记录该过期为既有差异）；在 `verify-evaluations.mjs` 实现 `entries` 场景作为本变更的行为验收 fixture。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend/app-shell`: 新增「统一创建入口与诚实 Mock 标记」requirement——全部显式创建入口 SHALL 导航到真实创建页；导入示例保持明确 Mock；通知与示例任务 MUST NOT 指向虚构真实详情；全局 Mock 标注移除、区域标注保留。

## Impact

- 前端源码：`frontend/src/layouts/AppLayout.tsx`、`frontend/src/layouts/components/Navigation.tsx`、`frontend/src/mock/MockActions.tsx`、`frontend/src/mock/BusinessPage.tsx`（DashboardPage 的实现）、`frontend/src/store/notifications.ts`。
- 测试与 fixtures：`frontend/src/auth/app-shell.test.ts`、`frontend/src/store/notifications.test.ts`、`frontend/scripts/verify-evaluations.mjs`、`frontend/scripts/verify-shell.mjs`。
- 不改后端、不改路由表与角色守卫；创建页与通知相关的现有 API 契约不变。
- `verify-shell.mjs` 的过期断言是 #214 之后真实页面（#246 等）合入时遗留的既有差异，本变更一并修复并在 PR 中记录。
