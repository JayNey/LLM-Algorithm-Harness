# 设计：可审计的 Reflexion 策略

`ReflexionStrategy` 复用 `StrategyBase` 的生成、代码提取、沙箱和结果记录能力。每一轮先生成候选代码并执行公共测试和反馈测试；失败时使用单独的反思调用解释可见失败，再把最近的反思日志放入下一轮修复提示。默认日志上限为 6000 个字符，可由 `custom_params.reflection_context_chars` 覆盖。

反思提示只包含题目元数据、候选代码、可见执行结果和已保存的反思。`Problem.hidden_test_cases` 不参与任何提示或执行。反思调用通过同一个 LLM 客户端，因此预算、重试和供应商配置仍由现有基础设施负责。

`IterationResult` 增加反思文本、错误、Token、usage 缺失标记、定价和 reasoning 字段。策略基类在迭代 trace 和 `ExecutionResult.total_tokens` 中合并代码生成与反思调用的统计，并把两次调用的已知成本合并到该轮的 pricing metadata。反思预算停止会将执行标记为 `budget_exhausted`，普通反思错误则被记录后继续使用没有反思的修复提示。
