## Why

Issue #156 要求把既有的固定预算实验（`src/experiment.py`）、基准测试（`src/benchmark/`）、帕累托分析（`src/pareto.py`）、成本优化（`src/cost_optimizer.py`）与 A/B 测试（`src/ab_testing.py`）通过 Web API 暴露。#148/#151/#172 合入后，API 骨架、业务数据库与认证密钥库均已就绪，本 change 是并行组里最后一个依赖 DB 层的管理 API。

## What Changes

- 新增 Alembic 迁移 `0002`：`experiments`、`benchmark_suites`、`benchmark_runs`、`ab_tests` 四张表（全部 owner 作用域）。
- 实验管理 API：创建（配置校验、`api_key_id` 归属校验）、列表/详情、异步运行（后台线程调 `ExperimentRunner`）、结果/对比报告/面板数据（解析实验产物目录）。
- 帕累托与成本优化：`POST /pareto/analyze`、`GET /pareto/frontier`、`POST /optimize`、`GET /optimize/ranking`——无状态分析端点，直接调 `src/pareto.py` / `src/cost_optimizer.py`。
- 基准测试 API：Suite 的 list/create/get/update（frozen 拒改）、运行（`BenchmarkExecutor`）、结果查询、学习曲线（按 suite 聚合历史 run 的准确率/成本序列与趋势）。
- A/B 测试 API：创建/详情/运行/结果（`ABTestRunner`，client/sandbox 工厂可注入）。
- 密钥与安全：请求永不携带明文密钥；`api_key_id` 经 #172 认证库归属校验，运行时解密注入 `LLMConfig`；`dataset_path` 限制在数据根目录内，防路径穿越。

## Capabilities

### New Capabilities
- `api/experiment-management`: 实验、基准、A/B 测试的持久化、异步执行与结果分析 API。

### Modified Capabilities
无。

## Impact

影响 `api/`（新增 routes/services、迁移 0002）与文档。CLI 行为不变。分析类 src 模块只被调用不修改。
