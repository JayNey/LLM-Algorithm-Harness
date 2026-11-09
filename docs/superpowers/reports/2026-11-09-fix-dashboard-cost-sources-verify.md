# 首页累计费用来源验证

实现提交 `7b9f35df`，对应 GitHub #417。结论为通过。

## 规格与实现

- 任务完成 1/1。OpenSpec 严格校验通过。
- 首页从当前账号汇总的 `evaluations` 和 `benchmarks` 读取已知费用及未知记录数。服务端的 `benchmarks` 仅包含已完成基准。混合来源及仅实验与 A/B 场景均通过。
- 空账号显示真实零值。已知金额为零且有未知记录时显示「成本未知」和记录数，有正数已知金额时同时显示该金额。请求失败保留错误、重试入口和其他已加载的指标。
- 通用费用 API 与费用页沿用全来源契约。既有真实 API 测试验证实验和 A/B 汇总及历史未知费用。
- 首页原有最近任务、权限、会话隔离和三套外观继续由浏览器验收覆盖。实现与精简设计及增量规格一致。

## 执行结果

- 前端 `npm test` 335 项通过，`npm run lint`、`npm run format:check`、`npm run build` 退出码均为 0。构建输出包含 Vite 大分块提示。
- Chrome 使用 HTTP fixture。首页 `verify-dashboard.mjs` 29 项通过，评估入口 `verify-evaluations.mjs --scenario entries` 17 项通过，`verify-i18n.mjs` 11 项通过。
- `pytest -q --no-cov tests/test_api_cost.py -k 'experiment_ab_accounting_same_scope or unknown_experiment_cost_is_partial'` 2 项通过。首次定向运行的用例断言均通过，默认全仓覆盖率门槛使该次进程返回 1。按定向模式重跑后退出码为 0。
- `git diff --check 362f8389..HEAD` 通过。按 tweak 的 `review_mode: off`，独立审查未启用。已对照最终实现、规格和验收场景检查。
