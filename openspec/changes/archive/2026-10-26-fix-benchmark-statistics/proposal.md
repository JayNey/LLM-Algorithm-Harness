## Why

真实 BenchmarkExecutor 只输出策略级 accuracy/total_cost，API 却从顶层或 summary 读取 accuracy/cost_usd，导致运行记录与学习曲线缺少统计。API 的布尔回退还会把有效零值当作缺失。

## What Changes

- 在执行器中汇总既有策略结果，提供 API 可直接消费的 accuracy 与 cost_usd。
- API 仅在顶层指标为 None 时回退到 summary，保留 0.0。
- 用真实执行器到 API 的离线回归覆盖多策略、零值、缺失值和学习曲线。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。修复 api/experiment-management 中既有「基准 Suite 与运行管理」「学习曲线追踪」要求的实现，不改变要求、端点或数据库结构。skip_specs: true。

## Impact

范围限于 src/benchmark/executor.py、api/services/benchmark_service.py 及其现有测试文件。保留策略级结果字段与已有 JSON 历史格式；不回填历史数据库记录。
