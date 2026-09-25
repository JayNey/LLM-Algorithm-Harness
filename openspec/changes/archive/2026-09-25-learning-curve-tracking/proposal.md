## Why

当前评估都是独立进行的，无法跟踪模型性能的时间演变。学习曲线追踪功能可定期运行相同题目集，记录性能趋势，支持模型版本对比，帮助了解模型能力的发展和版本迭代的影响。这对于研究 LLM 能力发展趋势和版本选型决策具有长期价值。

## What Changes

- 添加基准题目集（Benchmark Suite）定义和管理功能
- 实现定期评估调度机制（手动触发和定时任务）
- 建立历史数据存储和管理系统
- 实现趋势分析和可视化功能（时间序列图、多模型对比、版本对比）
- 生成学习曲线报告（包含趋势图、里程碑标注、性能预测）
- 添加 CLI 命令：`harness benchmark --suite <name> --compare`

## Capabilities

### New Capabilities
- `benchmark/suite-management`: 基准题目集的定义、存储和管理
- `benchmark/scheduling`: 定期评估调度和执行机制
- `benchmark/history-storage`: 历史评估结果的存储和索引
- `benchmark/trend-analysis`: 趋势分析和可视化（时间序列图、多模型对比）
- `benchmark/reporting`: 学习曲线报告生成

### Modified Capabilities
<!-- 无需修改现有 capabilities 的 requirements -->

## Impact

- 新增模块：benchmark suite 管理、历史数据存储、趋势分析可视化
- 新增 CLI 命令和子命令
- 新增配置文件：`benchmark.json` 用于定义基准题目集
- 新增数据存储目录：`results/benchmark/` 用于存储历史评估结果
- 依赖：复用现有的评估框架（与 issue #15 相关）
- 文档更新：添加基准评估使用指南
