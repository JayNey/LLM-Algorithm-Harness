## 1. 修复 src/harness.py 中的成本计算 bug

- [x] 1.1 修复成本累加逻辑：从 trace 顶层读取 `prompt_tokens` 和 `completion_tokens`，而非从 `pricing_metadata` 嵌套字段读取，并验证测试通过
- [x] 1.2 修复定价字段名称：使用 `prompt_price_per_1k` 和 `completion_price_per_1k` 替代错误的 `input_price_per_mtok` 和 `output_price_per_mtok`，并验证定价元数据正确保存
- [x] 1.3 在 LLMClient 的 pricing_metadata 中添加 `total_cost` 字段计算，并验证 summary.json 包含该字段

## 2. 修复 src/utils/pricing.py 前缀匹配 bug

- [x] 2.1 修复前缀匹配逻辑：在匹配前按键长度降序排序，确保最长匹配优先，并验证 `gpt-4o-mini` 匹配 `gpt-4o` 而非 `gpt-4`
- [x] 2.2 修复类型标注：从 typing 模块导入 `Any` 并替换小写 `any`，并验证类型检查通过

## 3. 清理 src/llm_client.py 死代码

- [x] 3.1 删除第 237 行重复的 return 语句，并验证代码可正常运行

## 4. 验证修复

- [x] 4.1 运行现有测试套件并验证所有测试通过
- [x] 4.2 运行成本估算流程并验证 summary.json 包含正确的 pricing_metadata 和 total_cost
