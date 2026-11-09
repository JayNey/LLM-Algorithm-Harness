# 实验整数预算验证

变更 `validate-experiment-integer-budgets`，实现提交 `a07920c2`。OpenSpec 任务 1/1 完成，增量规格通过严格校验。 [Issue #428](https://github.com/JayNey/LLM-Algorithm-Harness/issues/428)

## 验收结果

- 修复前，草稿分别生成了含 `max_calls: 1.5` 和 `max_tokens: 0.5` 的请求体。两项回归测试均因缺少预算字段错误而失败。
- 修复后，浏览器对两种整数预算分别提交小数、零、负数、非法文本和空值。每次都在预算限制值字段显示正整数提示，创建请求数为零。
- 浏览器捕获到四种有效请求体预算值，分别为 `{ max_calls: 12 }`、`{ max_tokens: 50 }`、`{ max_seconds: 0.5 }` 和 `null`。非空预算对象仅含所选类型。创建成功后导航和详情启动入口也通过原有浏览器断言。
- 单测覆盖预算数字转换、超出 JavaScript 安全整数范围的输入和未选择预算时忽略限制值。实验创建页与请求体构造共用校验，符合精简设计和增量规格。

## 验证命令

- `npm test` 通过 344 项测试。
- `npm run build` 通过。Vite 提示 CompareCharts 构建产物超过默认大小阈值。
- `npm run lint`、`npm run format:check` 和 `git diff --check bba45771...HEAD` 通过。
- `node scripts/verify-experiments.mjs all` 使用本机 Chrome、生产预览和模拟 API，通过 16 项断言，未知 API 请求为零。开发服务器返回过过期依赖缓存的 504 响应，因此使用生产预览完成浏览器验收。
- `comet classic openspec -- validate validate-experiment-integer-budgets --strict` 通过。

## 结论

PASS。Tweak 的 `review_mode` 为 `off`，完整验证核对了任务、增量规格、精简设计和最终改动，采用上述自动化测试及人工对照作为证据。
