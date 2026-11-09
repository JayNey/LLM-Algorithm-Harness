# 零价模型定价验证

[GitHub #433](https://github.com/JayNey/LLM-Algorithm-Harness/issues/433) · `tweak/20261109/allow-zero-model-pricing` · 实现提交 `37a14965`、`a6749126`

结论 **PASS**。两份增量规格和 Issue 验收场景均已核对。

## 完整性

- OpenSpec 两项任务均已完成。严格校验通过，变更详情识别 `api/cost-management` 和 `frontend/pricing-management` 两份增量规格。
- 产品决定沿用 `cost-estimation/custom-pricing` 规定的已知零价语义。输入和输出单价均可分别为零，表单提示说明零价代表该项免费。

## 正确性

- 表单和 API 接受零与正价，拒绝负数和非有限值。表单保留必填校验。修改前的回归确认表单和响应解析拒绝零价，API 对零价返回 400，并曾接受 `Infinity`。
- `tests/test_api_cost.py::TestPricing` 验证旧正价与新零价同时保留在历史中，保存响应和目录回读零价。原有认证、模型 ID 边界、斜杠及百分号编码、目录来源和历史顺序仍有回归覆盖。
- `test_saved_free_price_counts_as_known_cost` 通过真实 API 保存零价，读取数据库定价快照，以相同 token 用量运行客户端计费、费用持久化及 HTTP 汇总。免费模型得到 `0.0`，缺失定价模型得到 `null`，汇总的 `missing_pricing` 计数为 1。
- Chrome 使用隔离的 API 夹具验证表单提示、负数和空值拒绝、提交零价后目录和历史显示 `$0`。共 8 项通过，包含 320 至 1440 像素视口下的目录和历史滚动。

## 一致性

- 实现符合 `design.md`，OpenAPI 基线仅将两个单价的排他下限更新为含零下限。定价持久化、快照和成本汇总复用现有逻辑。
- Tweak 使用变更内的 `design.md`。按 `review_mode: off` 跳过独立自动审查，已核对最终 diff、输入边界与保留场景。

## 执行证据

- 前端 `npm test` 344 项通过，`npm run build` 成功。改动文件的 Prettier、ESLint、Black、Ruff 检查及 `git diff --check` 通过。
- 定价和端点定向测试 19 项通过，OpenAPI 契约和文档测试 48 项通过。已知免费与缺失定价的集成用例单独复验通过。
- `/tmp/issue351-venv/bin/python -m pytest -m 'not online'` 通过 4,069 项，跳过 18 项，覆盖率 93.46%，达到 90% 门槛。使用项目约束内的 Anthropic 依赖，并允许测试服务绑定本机回环端口。
- Comet 可选上下文插件尝试锁定全局状态文件时返回 `EPERM`。本次规格、阶段守卫和验证证据通过公开 CLI 独立处理。

## 归档交付

- 用户确认归档、推送当前绑定分支并创建关联 #433 的 PR。
- 归档后严格校验指出前端主规格原有的 `Purpose` 占位符，已补充页面用途说明。
