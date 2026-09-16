## 1. 创建 PricingManager 模块

- [x] 1.1 创建 `src/utils/pricing.py` 并实现 `PricingManager` 类，包含 `get_pricing()` 和 `load_custom_pricing()` 方法，验证方式：运行 `python -c "from src.utils.pricing import PricingManager; pm = PricingManager(); print(pm)"`
- [x] 1.2 实现内置定价字典，包含 gpt-3.5-turbo, gpt-4, gpt-4-turbo, claude-3-haiku, claude-3-sonnet, claude-3-opus 等模型，验证方式：单元测试 `test_builtin_pricing_models()` 通过
- [x] 1.3 实现从 `pricing.json` 加载自定义定价，支持 JSON 解析和文件不存在的降级处理，验证方式：单元测试 `test_load_custom_pricing()` 通过
- [x] 1.4 实现模型匹配逻辑（精确匹配 → 前缀匹配 → 默认值），验证方式：单元测试 `test_model_matching_strategy()` 覆盖精确匹配、前缀匹配和默认值场景
- [x] 1.5 实现定价来源追踪（返回定价和来源 "custom"/"builtin"/"default"），验证方式：单元测试 `test_pricing_source_tracking()` 通过

## 2. 集成 PricingManager 到 LLMClient

- [x] 2.1 在 `LLMClient.__init__()` 中初始化 `PricingManager` 实例，验证方式：运行现有测试 `tests/test_llm_client.py` 通过
- [x] 2.2 修改 `LLMClient.estimate_cost()` 使用 `PricingManager.get_pricing()` 替代硬编码定价字典，验证方式：单元测试 `test_estimate_cost_with_custom_pricing()` 通过
- [x] 2.3 在 `estimate_cost()` 中记录未知模型警告日志，包含模型名称和使用的默认定价，验证方式：单元测试验证 logger.warning 被调用且包含正确参数
- [x] 2.4 扩展 `LLMResponse` 或 `estimate_cost()` 返回值包含定价元数据（model, prompt_price, completion_price, source），验证方式：单元测试验证返回结构包含所有必需字段

## 3. 保存定价元数据到 summary.json

- [x] 3.1 在 `src/models.py` 的 `StrategyReport` 模型中添加 `pricing_metadata` 可选字段（包含 model, prompt_price_per_1k, completion_price_per_1k, source），验证方式：运行 `python -c "from src.models import StrategyReport; print(StrategyReport.__annotations__)"`
- [x] 3.2 修改 `Harness._generate_report()` 在构建 `StrategyReport` 时包含定价元数据，验证方式：运行评测并检查生成的 `summary.json` 包含 `pricing_metadata` 字段
- [x] 3.3 确保定价元数据在序列化到 JSON 时格式正确，验证方式：运行 `python -c "import json; data = json.load(open('results/summary.json')); assert 'pricing_metadata' in data['strategies']['vanilla']"`

## 4. 更新报告生成模块使用历史定价

- [x] 4.1 修改 `src/reporting/html_generator.py` 的 `generate()` 方法，优先从 summary 中读取 `pricing_metadata`，验证方式：使用包含 `pricing_metadata` 的 summary.json 生成 HTML 报告，检查报告中显示正确成本
- [x] 4.2 在 HTML 报告的成本部分添加定价来源显示（"自定义配置"/"内置定价"/"默认值"），验证方式：生成的 HTML 包含定价来源文本
- [x] 4.3 实现 `pricing_metadata` 缺失时的降级逻辑，使用当前 `PricingManager` 重新估算并记录 WARNING，验证方式：使用旧格式 summary.json 生成报告，检查日志包含 WARNING
- [x] 4.4 修改 `src/reporting/markdown_generator.py` 实现相同的历史定价逻辑和来源显示，验证方式：生成 Markdown 报告并检查定价来源信息正确显示

## 5. 创建配置文件示例和文档

- [x] 5.1 创建 `pricing.example.json` 包含常见模型的示例定价配置，验证方式：文件存在且可被 JSON 解析
- [x] 5.2 在 README.md 中添加"自定义模型定价"章节，说明 `pricing.json` 的格式、位置和降级策略，验证方式：文档包含完整的配置示例和说明

## 6. 测试和验证

- [x] 6.1 编写 `tests/test_pricing.py` 覆盖 PricingManager 的所有场景（文件加载、模型匹配、降级策略），验证方式：运行 `pytest tests/test_pricing.py -v` 全部通过
- [x] 6.2 编写 `tests/test_cost_estimation.py` 验证端到端成本估算流程（自定义定价 → summary.json → 报告生成），验证方式：集成测试通过
- [x] 6.3 使用真实 `pricing.json` 运行完整评测流程，验证 summary.json 包含正确定价元数据，验证方式：手动检查生成的 summary.json 和报告
- [x] 6.4 测试向后兼容性：使用不含 `pricing_metadata` 的旧 summary.json 生成报告，验证方式：报告生成成功且包含降级警告
