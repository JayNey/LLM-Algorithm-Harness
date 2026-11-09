# 预算与定价页宽表验证

变更 `fix-settings-table-overflow`，实现提交 `b72b6a46`。OpenSpec 任务 1/1 完成，增量规格通过严格校验。[Issue #430](https://github.com/JayNey/LLM-Algorithm-Harness/issues/430)

## 验收结果

- 修复前，本机 Chrome 在 320px 视口打开有数据的预算和定价页，两页文档宽度均为 785px。
- 修复后，生产预览中的两个页面和定价历史抽屉在 320、390、768、1024 和 1440px 下均通过文档宽度检查。
- 浏览器 fixture 覆盖预算用量、预警规则与投递历史、费用汇总与趋势、按来源/模型/策略分项、定价目录及覆盖模型的定价历史。各表使用具名的独立滚动区。键盘 Tab 可进入滚动区，溢出时方向键移动表格，Tab 可到达预警编辑和定价历史按钮。Enter 打开历史抽屉，Escape 关闭。
- 核对了 390px 下聚焦的预警编辑按钮和定价历史滚动区截图。浏览器检查使用本机 Chrome 和模拟 API 响应。
- 共享工作流样式仍由 `AppLayout` 单点加载。生产构建的直接加载回归覆盖实验、A/B 测试及基准详情页面。

## 验证命令

- `npm test` 通过 344 项测试。
- `npm run build`、`npm run lint`、`npm run format:check` 和 `git diff --check 4def021f...HEAD` 通过。Vite 报告 CompareCharts 构建产物超过 500 kB 阈值。
- `node scripts/verify-settings.mjs all` 通过 18 项断言，未知 API 请求为零。
- `node scripts/verify-direct-load.mjs` 通过 75 项断言，未知 API 请求为零。
- `comet classic openspec -- validate fix-settings-table-overflow --strict` 通过。

## 结论

PASS。完整验证核对了任务、增量规格、精简设计和最终改动。Tweak 状态的 `review_mode` 为 `off`，验证证据来自自动化检查和人工对照。
