## Why

实验列表/详情、A/B 列表/详情/创建、基准详情等工作流页面在直接打开或刷新时缺少 `workflow.css`：表格的 `min-width`、`border-collapse` 与面板内边距失效，内容挤成一行。当前 20 个页面使用 `evaluation-*` 类，却只有 10 个页面各自 import，样式归属分散且必然漏页。2026-11-03 前后端完成度审查把该问题列为 P0-3。

## What Changes

- 工作流样式改由共享布局 `AppLayout` 统一加载，随应用入口样式一起下发，不再依赖页面懒加载 chunk 的时机。
- 移除 10 个页面中重复的 `@/evaluations/workflow.css` 导入，保留单一来源。
- 新增“直接加载页面”的视觉 smoke：在生产构建上直接打开工作流路由，断言共享样式已进入入口 CSS、关键计算样式生效、无横向溢出与页面异常，并输出截图。
- 同步浏览器验证文档。
- 不改变页面结构、接口语义或数据模型。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/app-shell`: 增加“共享工作流样式随外壳加载”与“直接加载视觉 smoke”要求。

## Impact

- 前端代码：`src/layouts/AppLayout.tsx`、10 个工作流页面的样式导入、新增 `scripts/verify-direct-load.mjs`、验证文档。
- 构建产物：`workflow.css` 从页面 chunk 进入入口 CSS，页面 chunk 不再各自携带；入口 CSS 增大约 4KB。
- 无 API、数据库或后端改动。
