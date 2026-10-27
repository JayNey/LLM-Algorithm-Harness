# Tasks

- [x] 1. TDD：在 `verify-evaluations.mjs` 实现 `entries` 场景——五类显式创建入口（侧栏、快速操作、页头、空态、帮助页示例）断言全部落到 `/evaluations/new` 且无创建弹窗残留；导入入口保持明确 Mock；通知三类点击只落真实列表/帮助路由；示例仪表盘任务停留在 Mock 抽屉。先运行确认 RED（当前 dispatch 抛「尚未实现」）。
- [x] 2. Shell 收敛创建入口：`AppLayout.tsx` 的 `onCreate` 导航 `/evaluations/new` 并收窄 modal 状态；`MockActions.tsx` 删除创建分支与模拟反馈；`BusinessPage.tsx` 示例按钮统一真实入口并清理死分支。
- [x] 3. 按区域诚实标注：移除外壳级全局 Mock 标注（顶栏/侧栏/页脚/风格选择器），保留区域级标注；`notifications.ts` 种子文案调整。
- [x] 4. 单测：`app-shell.test.ts` 补 `/results/:id` 面包屑与「无全局 Mock 标注」断言；`notifications.test.ts` 补种子路由边界；运行 app-shell/notifications 单测确认 GREEN。
- [x] 5. 修复 `verify-shell.mjs` 过期业务段：改锚定示例仪表盘与真实创建页导航，业务 API 白名单按真实创建页只读接口调整；运行确认 GREEN。
- [x] 6. 重跑 `entries` fixture 确认 GREEN；`npm run lint`、`npm test`、`npm run build` 全绿，记录命令与退出码。
- [x] 7. 两轮独立只读审查（general-purpose 子代理）：全量审查 approves（P2×3：死 CSS 已清理、快速操作断言已补强、既有文案留待后续）→ 定点复审 approves，无遗留。
- [x] 8. 撰写验证报告（docs/superpowers/reports/2026-10-25-unified-entry-honest-mock-verify.md），记录 fixture/单测/构建证据与未验证层级。
