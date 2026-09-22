## Why

当前只有 Vanilla、CoT、Multi-Round Feedback 三种策略，缺少基于多样本投票的策略。Self-Consistency 通过并行生成多个候选解并投票选择最佳答案，学术界验证可提升 5-15% 准确率，且实现相对简单，是丰富策略库的高价值选择。

## What Changes

- 新增 `SelfConsistencyStrategy` 类，继承 `StrategyBase`
- 支持并行生成 N 个候选解（N 可配置，默认 5）
- 对所有候选解执行测试，统计通过测试的结果
- 通过投票机制选择出现频率最高的正确答案
- 记录每个候选解的生成过程和投票统计
- 支持温度参数配置以增加候选解的多样性
- 集成到现有评测流程和报告系统

## Capabilities

### New Capabilities

- `strategies/self-consistency`: Self-Consistency 求解策略，通过多样本生成和投票提升准确率

### Modified Capabilities

- `result-recording`: 需要扩展以支持记录候选解投票统计信息

## Impact

- 新增文件：`src/strategies/self_consistency.py`
- 修改文件：`src/strategies/__init__.py`（注册新策略）
- 修改文件：`src/models.py`（可能需要扩展 ExecutionResult 以记录投票信息）
- 评测配置：用户可通过配置文件指定策略参数（候选数量、温度等）
- Token 消耗：N 倍生成成本，需在报告中准确统计
