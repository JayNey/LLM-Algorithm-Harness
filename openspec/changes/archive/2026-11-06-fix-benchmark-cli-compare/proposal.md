## Why

`harness benchmark --compare` 会启动新的评估并保存历史，即使指定了 `--output` 也不会生成报告。这个行为可能产生意外的模型调用费用，见 [issue #376](https://github.com/JayNey/LLM-Algorithm-Harness/issues/376)。

## What Changes

- 从指定题目集的历史生成多模型 Markdown 报告，支持自定义输出路径。
- 对历史缺失、可比较数据不足和报告写入失败返回非零退出状态。
- 在 CLI 帮助和 README 中注明 `--output` 的适用模式。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `benchmark` 的多模型对比和学习曲线报告行为。

## Impact

影响 Benchmark CLI、报告图表链接、CLI 回归测试和使用说明。复用现有历史格式和报告组件。
