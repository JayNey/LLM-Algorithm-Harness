## 修复方案

### 1. 温度参数可配置化

**修改位置**：`src/strategies/self_consistency.py`

**方案**：从 `custom_params` 读取温度参数，如果未配置则使用默认值 0.8。

**实现细节**：
- 在 `execute()` 方法中，从 `self.config.custom_params` 获取 `temperature`
- 使用 `get()` 方法提供默认值 0.8
- 传递给 `llm_client.generate()` 时使用变量而非硬编码

**兼容性**：
- 现有配置未指定温度时自动使用 0.8，向后兼容
- 用户可以通过配置文件自定义温度，满足验收标准

### 2. 策略类导出

**修改位置**：`src/strategies/__init__.py`

**方案**：导出所有策略类，遵循 Python 包的标准做法。

**实现细节**：
- 导入所有策略类：`VanillaStrategy`, `ChainOfThoughtStrategy`, `MultiRoundFeedbackStrategy`, `SelfConsistencyStrategy`
- 声明 `__all__` 列表，明确导出的公共接口
- 保持文档字符串

**影响**：
- 其他模块可以通过 `from src.strategies import SelfConsistencyStrategy` 导入
- 提高代码可维护性和一致性

### 3. 文档更新

**修改位置**：`README.md`

**方案**：更新配置示例，说明温度参数可配置。

**实现细节**：
- 在 Self-Consistency 配置示例中添加 `temperature` 参数
- 在策略说明部分将"固定为 0.8"改为"默认 0.8，可配置"
- 保持其他配置示例的一致性

## 风险评估

- **低风险**：修改范围小（3个文件），逻辑简单
- **无破坏性**：向后兼容，现有配置无需修改即可正常工作
- **无架构变更**：仅参数化硬编码值和补充导出语句
