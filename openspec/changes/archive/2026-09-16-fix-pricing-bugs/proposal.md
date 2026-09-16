## Why

Code review 发现自定义模型定价实现中存在 6 个 bug，导致成本估算完全错误、按模型统计失效、前缀匹配不可靠。这些 bug 会直接破坏 `cost-estimation/custom-pricing` 能力的核心功能，必须立即修复以确保定价系统可用。

## What Changes

- 修复 `src/harness.py` 中成本累加逻辑，正确从 trace 顶层读取 token 计数并计算 total_cost
- 修复 `src/harness.py` 中定价字段名称映射错误，使用正确的 `prompt_price_per_1k` 和 `completion_price_per_1k`
- 修复 `src/utils/pricing.py` 中前缀匹配逻辑，按最长匹配优先排序以避免错误匹配
- 移除 `src/llm_client.py` 中的死代码（重复 return 语句）
- 修复 `src/utils/pricing.py` 中的类型标注错误（`any` → `Any`）

## Capabilities

### New Capabilities

<!-- 无新能力 -->

### Modified Capabilities

- `cost-estimation/custom-pricing`: 修复现有实现的 6 个正确性 bug，确保定价元数据正确保存、成本计算正确执行、前缀匹配可靠工作。这些修复不改变 spec 要求，只是让实现符合已有 requirements。

## Impact

影响文件：
- `src/harness.py` — 成本累加和定价元数据保存逻辑
- `src/utils/pricing.py` — 定价加载和前缀匹配逻辑
- `src/llm_client.py` — 清理死代码

不影响用户可见行为或 API，只修复内部 bug。现有测试应全部通过，cost estimation 功能将正常工作。
