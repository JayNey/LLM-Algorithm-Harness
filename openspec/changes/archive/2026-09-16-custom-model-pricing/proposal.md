## Why

目前系统在成本估算时使用硬编码的模型定价，存在两个问题：(1) 当用户使用自定义模型或 OpenAI 兼容 API（如 DeepSeek）时，无法准确估算成本；(2) 历史运行报告在模型定价更新后会显示不一致的成本数据。需要支持用户通过配置文件自定义模型定价，并在评测时将定价信息保存到 summary.json 以确保历史报告的准确性。

## What Changes

- 支持从 `pricing.json` 配置文件读取自定义模型定价
- 评测时将使用的定价信息保存到 `summary.json`
- 报告生成时优先使用 `summary.json` 中的历史定价数据
- 实现降级策略：`pricing.json` → 内置定价字典 → 默认值 + 警告日志
- 在 HTML/Markdown 报告中显示使用的定价来源

## Capabilities

### New Capabilities
- `cost-estimation/custom-pricing`: 支持用户通过配置文件自定义模型定价，评测时保存定价到结果文件，报告生成时优先使用历史定价以保证准确性

### Modified Capabilities
<!-- 无现有 capability 的 requirements 变更 -->

## Impact

**受影响的代码：**
- `src/llm_client.py`: `estimate_cost()` 方法需要支持从配置文件读取定价
- `src/harness.py`: `_estimate_cost()` 和 `_generate_report()` 需要将定价信息保存到报告
- `src/reporting/html_generator.py`: 报告生成时需要使用 summary.json 中的定价数据
- `src/reporting/markdown_generator.py`: 同上

**新增文件：**
- `pricing.json`: 用户可选的定价配置文件（示例文件）
- 可能需要新增 `src/utils/pricing.py`: 定价管理工具模块

**API 影响：**
- `StrategyReport` 模型可能需要扩展以包含定价元数据
- LLMClient 的 `estimate_cost()` 方法签名可能需要调整

**配置影响：**
- 新增可选的 `pricing.json` 配置文件
- 不影响现有配置文件向后兼容性
