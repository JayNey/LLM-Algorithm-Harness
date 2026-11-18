# 修复 Few-Shot 历史示例泄漏与复用

## Why

Issue #494 指出现有 Few-Shot 检索会选中目标题自己的历史答案，且正常策略结果未携带加载器需要的题目元数据。两者仍存在于当前 main，必须先阻断泄漏，再恢复历史检索，确保实验条件可追溯。

## What Changes

- A：先加入历史已有目标答案的失败回归，再在检索和提示构建处排除相同 problem_id、相同来源身份/来源 URL、规范化后相同题面的重复题。阈值为 0 时同样执行排除；不以相似标题或语义推断同题。
- B：标准 ExecutionResult 增加可选、带版本的最小题目快照，由 StrategyBase 统一写入标题、描述、标签、难度和来源身份；不包含反馈/隐藏测试及参考答案。
- 历史加载器使用统一快照，兼容信息完整的旧顶层字段和 problem_metadata；缺少必要题意、结构损坏及不合格成功结果明确告警并跳过，单条损坏不阻断其他示例。
- 对示例集合做稳定排序、内容寻址和来源记录；每个 Few-Shot 结果记录集合身份、选中示例和重叠排除信息。
- 正式 ExperimentRunner 在组合开始前冻结同一示例集合并记录版本、摘要、来源和全目标集合重叠检查；恢复时复用原快照并校验一致性，拒绝无法证明一致的旧 Few-Shot checkpoint。
- 保留阶段 3 已建立的 Few-Shot 禁用增量结果复用规则，不让动态历史库绕过执行兼容性检查。
- A、B 分别验证并分别提交，最后完成同一 change 的验证与归档交付。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `strategies/few-shot-learning`：目标排除、历史快照契约、集合身份和安全降级。
- `result-recording`：正常策略结果保存最小题目快照，同时保持旧结果可读取。
- `experiment/budget-comparison`：Few-Shot 正式实验固定示例集合和审计重叠，恢复时校验集合身份。

## Impact

- 预计交付文件 10–12 个：`src/models.py`、`src/strategy_base.py`、`src/strategies/few_shot_learning.py`、一个示例集合共享模块、`src/experiment.py`；对应 Few-Shot/结果/实验/增量兼容测试及 README 使用说明。
- 仅实施、测试、用户文档类别；OpenSpec、Comet 及 walkthrough 属于流程产物。若实际范围、验收或风险扩大则重新复核。
- 涉及向后兼容的结果字段和实验集合快照格式，须在 Open 确认时明确批准在同一 tweak 中完成；无需数据库迁移、外部服务或模型调用。
- 当前目录 main，基线 `2d79bd95889c0305316bd989853cd43de2fcfe11`；采用 direct/direct/off 预设，仍运行真实缺陷回归和离线集成检查。

来源：[GitHub issue #494](https://github.com/JayNey/LLM-Algorithm-Harness/issues/494)。
