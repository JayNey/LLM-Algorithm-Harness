# Tasks: fix-benchmark-run-budget

- [x] 先写 RED 回归测试：非 task-service harness 在 `budget_cap_usd` + `auto_stop` 下达到上限暂停；基准服务为带预算运行设置 `auto_stop`；未填预算路径不变
- [x] 在 `AlgorithmHarness.run()` 非 task-service 路径接入 `RunCostMonitor`，按单元结算已知成本并在超限时置 `paused`；仅接受 `auto_stop` 预算动作，保留不支持的组合的明确报错
- [x] 在 `BenchmarkService._execute` 为带 `budget_cap_usd` 的 `HarnessConfig` 设置 `budget_action="auto_stop"`，确认暂停经现有 run/AsyncTask 状态与检查点生效
- [x] 补 API/executor 回归：有预算暂停、无预算完成、恢复重放不重复执行且预算仍不足继续暂停
- [ ] 运行后端相关测试、格式化与构建检查，记录验证证据并完成阶段守卫
