## Context

旧题库没有用途元数据，所有测试都通过 `Problem.test_cases` 暴露给策略和执行器。需要在不破坏旧数据的前提下建立公开、反馈、隐藏三层边界。

## Decisions

1. **用三个显式列表表达测试用途。** `public_test_cases`、`feedback_test_cases` 和 `hidden_test_cases` 分别对应模型初始输入、可用于迭代反馈的测试和策略结束后的正式评分。
2. **旧字段只迁移到公开列表。** 输入含 `test_cases` 且没有新列表时，模型验证器将其复制到 `public_test_cases` 并标记 `legacy_test_cases_as_public`。
3. **提示词使用公开视图。** `Problem.prompt_view()` 只返回公开用例和非敏感元数据；隐藏输入和答案不会进入初始提示词或反馈文本。
4. **隐藏评测在策略结束后运行。** Harness 向策略传入移除 hidden 列表的题目副本，并使用自己保留的完整题目在策略返回后单独执行隐藏用例；隐藏结果不回流给策略，有隐藏用例的题才计入正式可评测题数。
5. **测试来源随用例保存。** 每个 `TestCase` 记录 `source`（public/feedback/hidden）和可选标识，便于审计数据版本与迁移状态。
6. **可选阶段显式跳过。** 题目可以缺少 public 或 feedback 列表；执行器拒绝把空阶段当作通过，策略在没有可见测试时交给 Harness 的隐藏阶段定案，并在 CSV/Markdown/HTML/CLI 中保留正式评测边界。

## Risks / Trade-offs

- [旧题库没有真正隐藏用例] → 明确标记为仅样例验证，不把公开用例冒充正式评分。
- [三层测试增加执行路径] → 执行器提供显式 stage 参数，默认仍运行公开用例，调用方必须明确请求隐藏评测。
- [隐藏结果仍存在本地对象中] → 隐藏结果只在策略完成后生成，不进入 prompt/feedback；导出边界由现有脱敏和报告模块负责。
