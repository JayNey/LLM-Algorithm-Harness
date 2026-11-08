# 实验取消确认验证报告

变更为 `confirm-experiment-cancellation`，实现提交为 `cac5b7a3`。OpenSpec 任务已完成 1/1，完整验证结果为 PASS。

## 验收场景

- 列表和详情均可用 Enter 或 Space 打开确认。Esc 和「返回」关闭确认，浏览器未发送取消请求。
- 两处入口的确认按钮均经过双击验证。请求只提交一次，路径使用 `queued-task`，与实验 ID `queued-exp` 区分。已有显式关联时未查询全局任务索引。
- 取消成功后两处显示「已取消」并允许删除。模拟服务返回 503 时，两处重新读取并显示「已暂停」，保留取消操作并显示错误。模拟运行先完成时，两处重新读取并显示「已完成」，隐藏取消操作并允许删除。
- 现有排队保护、无任务实验、旧响应查询失败或等待、终态以及启动结果不确定的队列用例通过。

## 命令与结果

- `comet classic openspec -- validate confirm-experiment-cancellation --strict` 通过。
- `npm test` 通过 322 项。Lint 和格式检查通过。
- `npm run build` 通过。Vite 仍报告对比图表分包超过 500 kB 的体积提示。
- Chromium 对生产预览执行 `node scripts/verify-experiment-queue.mjs`，11 个场景通过。回归在主线的两个取消入口均因缺少确认框而失败。
- Chromium 对生产预览执行 `node scripts/verify-experiments.mjs all`，14 个断言通过。目视检查了 1440 px 列表和 390 px 详情的确认弹窗。

## 规格与设计核对

变更涉及六个前端文件。列表和详情共用确认交互和同步防重逻辑，分别沿用列表重载与详情进度重载。API 失败后的反馈在刷新后可见。代码和行为与 OpenSpec 的 proposal、design 和 delta spec 一致。沿用 tweak 的精简设计产物和 `review_mode: off`。浏览器用例通过 HTTP fixture 模拟后端的成功、失败和竞态。
