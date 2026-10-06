## Why

当前项目支持多种求解策略（Vanilla、CoT、Multi-Round Feedback、Self-Consistency、Reflexion、ToT），但缺少利用历史成功案例的 Few-Shot Learning 策略。Few-Shot Learning 通过检索相似的已解决题目作为示例，帮助 LLM 更好地理解和求解新问题，预期可提升 5-10% 的准确率，特别适合简单到中等难度的问题。

## What Changes

- 新增 Few-Shot Learning 策略实现
- 实现基于标签重叠的相似度计算（第一阶段）
- 实现相似题目检索功能
- 实现动态 few-shot prompt 构建
- 添加配置支持（示例数量、相似度阈值等）
- 添加完整的单元测试（覆盖率 >= 90%）
- 更新文档和配置示例

## Capabilities

### New Capabilities
- `strategies/few-shot-learning`: Few-Shot Learning 策略核心实现，支持基于标签的相似题目检索和动态 prompt 构建

### Modified Capabilities
<!-- 无需修改现有 capabilities 的 REQUIREMENTS -->

## Impact

**影响范围：**
- 新增文件：
  - `src/strategies/few_shot_learning.py` - 策略主实现
  - `src/strategies/similarity/tag_based.py` - 标签相似度计算
  - `tests/test_few_shot_learning.py` - 单元测试
- 修改文件：
  - `src/harness.py` - 注册新策略到 STRATEGY_MAP
  - `config.example.json` - 添加配置示例
  - `README.md` - 更新策略说明

**API 影响：** 无破坏性变更，纯增量功能

**依赖影响：** 无新增外部依赖
