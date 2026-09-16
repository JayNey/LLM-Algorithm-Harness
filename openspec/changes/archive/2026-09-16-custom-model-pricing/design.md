## Context

当前成本估算逻辑硬编码在 `src/llm_client.py` 的 `estimate_cost()` 方法中，包含约 9 个主流模型的定价。用户使用自定义模型或 OpenAI 兼容 API（如 DeepSeek）时会收到 "unknown_model_pricing" 警告并返回 0.0 成本。

报告生成模块（`src/reporting/html_generator.py` 和 `markdown_generator.py`）直接从 `summary.json` 读取 `estimated_cost_usd` 字段，但该字段在评测时计算，无法在定价更新后重新生成准确的历史报告。

## Goals / Non-Goals

**Goals:**
- 用户可通过 `pricing.json` 自定义任意模型的 Token 定价
- 评测结果中保存定价元数据，确保历史报告准确性
- 实现清晰的降级策略链：custom → builtin → default
- 报告中显示定价来源，提升透明度

**Non-Goals:**
- 不支持动态定价（如基于时间的计费规则）
- 不实现定价的自动更新或在线获取
- 不修改现有 summary.json 结构的向后兼容性（仅新增字段）

## Decisions

### 决策 1: 创建独立的 PricingManager 模块

**选择:** 在 `src/utils/pricing.py` 中创建 `PricingManager` 类集中管理定价逻辑。

**理由:**
- 职责分离：从 `LLMClient` 中解耦定价逻辑
- 便于测试：独立模块更易进行单元测试
- 复用性：Harness 和报告生成模块可共享同一定价逻辑

**替代方案:**
- 直接在 `LLMClient` 中扩展：会使该类职责过重，违反单一职责原则
- 使用全局配置：缺乏封装性，难以追踪定价来源

### 决策 2: pricing.json 格式设计

**选择:**
```json
{
  "models": {
    "gpt-4": {
      "prompt": 0.03,
      "completion": 0.06
    },
    "deepseek-chat": {
      "prompt": 0.0014,
      "completion": 0.0028
    }
  }
}
```

**理由:**
- 扁平结构简单直观，易于用户手动编辑
- 单位统一为 USD/1000 tokens，与行业惯例一致
- 支持模型前缀匹配（如 `gpt-4` 匹配 `gpt-4-0613`）

**替代方案:**
- 嵌套结构（按 provider 分组）：增加复杂度，对单一模型配置不友好
- 支持多种单位：增加解析复杂度和出错风险

### 决策 3: 定价元数据保存到 summary.json

**选择:** 在每个策略报告中新增 `pricing_metadata` 字段：
```json
{
  "strategies": {
    "vanilla": {
      "strategy_name": "vanilla",
      "estimated_cost_usd": 0.010122,
      "pricing_metadata": {
        "model": "gpt-3.5-turbo",
        "prompt_price_per_1k": 0.0015,
        "completion_price_per_1k": 0.002,
        "source": "builtin"
      }
    }
  }
}
```

**理由:**
- 每个策略可能使用不同模型，需独立记录定价
- 保留足够信息以在报告生成时重新计算成本
- `source` 字段追踪定价来源，便于审计

**替代方案:**
- 全局定价元数据：无法支持多策略使用不同模型的场景
- 仅保存定价来源：无法在定价文件变更后准确重现历史成本

### 决策 4: 降级策略实现

**选择:** 三级查找链
1. `pricing.json`（精确匹配 → 前缀匹配）
2. 内置定价字典
3. 默认值 (prompt: $0.002/1k, completion: $0.002/1k) + WARNING 日志

**理由:**
- 优先用户配置，体现用户主权
- 内置字典保证常见模型的开箱即用
- 默认值避免评测因定价问题而失败

**替代方案:**
- 未知模型直接报错：对探索性评测不友好
- 所有模型必须配置：增加用户负担

### 决策 5: 模型匹配策略

**选择:** 精确匹配 → 前缀匹配
- 精确匹配：`gpt-4-0613` 匹配 `gpt-4-0613`
- 前缀匹配：`gpt-4-0613` 匹配 `gpt-4`（若精确匹配失败）

**理由:**
- 支持模型版本灵活性（用户无需为每个小版本配置定价）
- 避免配置冗余

**替代方案:**
- 仅精确匹配：配置文件会非常冗长
- 正则表达式匹配：过于复杂，增加出错风险

## Risks / Trade-offs

### 风险 1: pricing.json 与内置定价冲突导致混淆
**缓解:** 在日志中明确记录使用的定价来源；报告中显示定价来源标识

### 风险 2: 前缀匹配可能误匹配模型
**示例:** `gpt-4` 配置被 `gpt-4o` 误用
**缓解:** 精确匹配优先；文档中说明前缀匹配规则；建议用户为新模型系列单独配置

### 风险 3: 历史 summary.json 缺少 pricing_metadata
**缓解:** 报告生成时检测字段是否存在，缺失时回退到当前配置并记录 WARNING

### 风险 4: 用户修改 pricing.json 后历史报告不一致
**权衡:** 设计目标是保证历史数据准确性，summary.json 中的定价元数据不受后续配置变更影响

## Migration Plan

**部署步骤:**
1. 实现 `PricingManager` 模块并添加单元测试
2. 修改 `LLMClient.estimate_cost()` 使用 `PricingManager`
3. 修改 `Harness._generate_report()` 保存定价元数据
4. 更新报告生成模块使用历史定价
5. 创建 `pricing.example.json` 作为模板

**向后兼容性:**
- 现有 summary.json 文件不包含 `pricing_metadata`，报告生成时会回退到当前配置
- 不影响现有评测工作流

**回滚策略:**
- 新增字段不破坏现有功能，可直接回滚代码
- 用户创建的 `pricing.json` 文件会被忽略

## Open Questions

无需在实施前解决的问题。
