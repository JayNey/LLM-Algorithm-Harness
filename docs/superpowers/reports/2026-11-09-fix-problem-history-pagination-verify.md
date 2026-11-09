# 题目评估历史分页验证

- [Issue #427](https://github.com/JayNey/LLM-Algorithm-Harness/issues/427)
- 变更 `fix-problem-history-pagination`，实现提交 `53e4d07c`
- OpenSpec 任务 1/1 完成，题库管理增量规格通过严格校验

## 验收证据

- 修复前，浏览器从题目 A 的第二页切到 B，观测到 B 的首个请求携带 `offset=20`，回归断言预期为 `0`。
- 修复后，B 的首个请求携带 `offset=0`，并显示 B 的运行记录。
- 暂停 A 的请求，关闭 A 并打开 B。B 的记录显示后释放 A 的请求，抽屉仍显示 B 的记录。
- A 的下一页显示独立的运行记录，历史聚合与无记录题目的空态通过验证。
- 导出场景通过代码对照，题库页仍通过现有客户端下载地址打开 JSON 或 CSV。浏览器验证使用模拟 API。

## 实现与验证命令

评估历史内容按 `problem_id` 使用独立组件实例。切题时从初始偏移读取，旧组件卸载时由现有 `useList` 取消请求并校验响应身份。实现与精简设计及增量规格一致。

- `node scripts/verify-problems.mjs all` 在 Chrome 和 Vite 上通过 14 项断言，未知 API 请求为 0。
- `npm test` 通过 341 项测试。
- `npm run build` 通过。Vite 提示 CompareCharts 构建产物超过默认大小阈值。
- `npm run lint`、`npm run format:check` 和 `git diff --check origin/main...HEAD` 通过。
- `comet classic openspec -- validate fix-problem-history-pagination --strict` 通过。
- 实现提交后复跑 `node scripts/verify-problems.mjs history`，6 项断言通过，未知 API 请求为 0。

## 结论

PASS。独立审查核对了分页状态、请求取消和响应身份检查，未发现需要修改的问题。关闭后重新打开同一题也会从首页读取。
