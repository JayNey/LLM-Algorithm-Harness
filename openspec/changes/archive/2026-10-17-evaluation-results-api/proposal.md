## Why

Issue #155 要求为已完成的评估提供查询、统计、对比、可视化和报告导出 API。评估执行已经把每个（策略 × 题目）单元写入 `evaluation_results`，但 API 目前只能看到任务状态和聚合计数，前端无法按任务、题目、策略或模型读取结果。

## What Changes

- 新增 owner 作用域的结果查询：单个任务详情、分页列表、题目历史，以及按策略、难度、标签过滤。
- 新增统计分析：成功率、token、迭代次数、执行时间、失败模式。口径与该次运行已落库的单元结果一致，不重新执行评估。
- 新增对比：策略对比、模型对比、同一配置的历史对比；A/B 结果复用现有 A/B 测试服务。
- 新增可视化数据：成功率、token、迭代分布、能力雷达、成本-准确率、学习曲线。雷达分数沿用 `src/reporting/capability_profiler.py` 的维度与 0–100 分口径。
- 新增失败分析：按已落库的 `failure_mode` / `failure_category` 与错误信息汇总，错误聚类沿用 `src/error_analysis.py` 的归一化规则。
- 新增报告导出：Markdown、CSV、HTML，以及现有 `ChartGenerator` 已支持的 PNG。
- 单元落库补记迭代次数，供迭代统计和分布图使用。不保存完整沙箱轨迹或生成代码。

## Capabilities

### New Capabilities

- `api/evaluation-results`: 评估结果的查询、统计、对比、可视化数据、失败分析和报告导出。

### Modified Capabilities

无。现有记录、雷达图和错误分析规格的 CLI 行为不变；本 change 只增加 API 消费方式和一个落库计数字段。

## Impact

影响 `api/`（新路由与服务）、`src/tasks/evaluation.py` 的单元度量写入，以及 `API.md`。不新增业务表，不把 Redis 作为正确性依赖。分析与报告模块只被调用，不改其 CLI 产物契约。
