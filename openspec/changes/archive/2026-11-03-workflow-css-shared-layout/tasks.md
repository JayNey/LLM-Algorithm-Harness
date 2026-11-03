## 1. 共享样式

- [x] 1.1 在 `frontend/src/layouts/AppLayout.tsx` 导入 `@/evaluations/workflow.css`，并删除仪表盘、题目、评估列表/创建/详情、结果列表/详情、实验创建、基准列表、帮助页的重复导入。验证：`npm run build` 通过，入口 CSS 含 `.evaluation-list-table`，`src/pages/**` 不再出现该导入。

## 2. 直接加载视觉 smoke

- [x] 2.1 新增 `frontend/scripts/verify-direct-load.mjs`：校验构建产物、自动启动 `vite preview`、以 fixture 拦截 `/api/v1/**`、直接加载 6 个工作流路由，断言入口 CSS、计算样式、无横向溢出与页面异常，输出截图与 JSON 报告。验证：`npm run build` 后运行脚本以 0 退出；断言失败时以非 0 退出。
- [x] 2.2 在 `docs/frontend/QA.md` 记录脚本的运行方式、环境变量与覆盖范围。验证：文档命令与脚本实际行为一致。

## 3. 验收

- [x] 3.1 运行 `npm test`、`npm run lint`、`npm run build`、`npm run format:check` 与直接加载 smoke，并执行 `comet classic openspec -- validate workflow-css-shared-layout --type change --strict --no-interactive`。验证：`npm test`、`npm run lint`、`npm run build`、直接加载 smoke 与 `validate` 通过；`npm run format:check` 全仓仅因既有 `scripts/verify-settings.mjs` 未格式化而失败，与本 change 无关，本次改动文件均通过 Prettier。直接打开六个工作流路由均无样式缺失。
