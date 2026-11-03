## Context

`AppLayout` 由 `App.tsx` 静态导入，因此它的样式会进入入口 CSS；业务页面由 `React.lazy` 加载，页面级 CSS 只在路由 chunk 到达后才注入。直接打开深链接时，首屏可能先渲染出没有 `evaluation-*` 规则的内容。现状是 20 个页面使用这些类，只有 10 个页面各自导入 `workflow.css`，其余 10 个页面（实验、A/B、基准详情、预算、定价、系统页）完全依赖页面自身的偶然导入。

## Goals / Non-Goals

**Goals:**

- 工作流样式随共享布局进入入口 CSS，直接打开与站内导航表现一致。
- 样式只保留一个导入来源，避免新增页面再次漏导入。
- 提供可重复执行、能失败的“直接加载”视觉 smoke。

**Non-Goals:**

- 不重写页面样式、不迁移到 CSS-in-JS、不改外观主题体系。
- 不为全部 20 个页面各写一套 fixture，只覆盖代表性工作流路由。
- 不引入新的前端依赖或 CI 配置文件。

## Decisions

1. 在 `src/layouts/AppLayout.tsx` 顶部导入 `@/evaluations/workflow.css`。文件路径保持不变，避免无谓移动；`AppLayout` 只包裹已登录工作台路由，登录/注册页不会加载表格样式。
2. 删除 10 个页面级导入：仪表盘、题目、评估列表/创建/详情、结果列表/详情、实验创建、基准列表、帮助。原本未导入的预算、定价、系统日志、系统状态页由共享布局补齐。
3. smoke 针对生产构建：脚本先确认 `dist/index.html` 存在，未指定 `DIRECT_LOAD_BASE_URL` 时自动以 `vite preview` 启动 5191 端口；已指定时复用现有服务。API 全部用 Playwright 路由拦截的 fixture，不连接真实后端。
4. 断言分三层：静态检查入口 CSS 是否包含 `.evaluation-list-table` 与 `.evaluation-panel`，并确认 `src/pages/**` 不再出现 `workflow.css` 导入；浏览器计算样式检查表格折叠边框、760px 最小宽度、面板 24px 内边距和 `.evaluation-workflow` 的 `min-width: 0`；布局检查 1440 与 390 宽度无整体横向溢出、无 `pageerror`。截图和 JSON 报告写入默认 `docs/frontend/assets/direct-load/`。
5. 样式顺序：`main.tsx` 先导入 `index.css`（其中 `@import` 了 `layouts/shell.css`），`AppLayout` 在其后进入模块图，因此 `workflow.css` 规则位于外壳规则之后，与原先页面 chunk 后注入的层叠顺序一致。

## Risks / Trade-offs

- [入口 CSS 增大约 4KB] → 换取所有工作流页面直接加载可用，接受。
- [smoke 依赖构建产物与外部 Playwright 包] → 沿用 `PLAYWRIGHT_MODULE`、`CHROME_PATH` 约定，不把 Playwright 写进依赖；缺少构建产物时脚本给出明确提示。
- [页面在 AppLayout 之外复用会失去样式] → 当前无此路径；静态检查会在页面重新导入时失败，提示是否应继续放在共享布局。

## Migration Plan

无数据迁移。CI 或本地顺序为 `npm run build` 后运行 smoke；`npm test`、`npm run lint`、`npm run build` 不受影响。

## Open Questions

无。
