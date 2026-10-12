## 1. 数据与基础
- [x] 1.1 迁移 0002：experiments/benchmark_suites/benchmark_runs/ab_tests 四张表；ORM 模型与迁移一致
- [x] 1.2 `api/config.py` 增加 `DATA_ROOT`；数据集路径约束工具（防穿越）

## 2. 实验管理 API
- [x] 2.1 experiment_service：创建/列表/详情/删除（owner 作用域、密钥归属校验、脱敏持久化）+ 异步运行（ExperimentRunner 工厂注入、状态机、终态守卫）
- [x] 2.2 结果分析端点：results/comparison/panel 解析实验产物；未完成或产物缺失返回明确错误
- [x] 2.3 路由 `/api/v1/experiments` 全套接线（沿用 ApiResponse/PaginatedData/owner 依赖）

## 3. 基准与 A/B API
- [x] 3.1 benchmark_service：Suite list/create/get/update（frozen 拒改）/run（BenchmarkExecutor 工厂注入）/results；learning-curve 聚合（含空历史返回空序列）
- [x] 3.2 ab_test_service：创建/详情/运行（ABTestRunner 工厂注入）/结果（显著性检验）；owner 隔离
- [x] 3.3 pareto/optimize 无状态分析端点（ValueError → 400）

## 4. 验证与交付
- [x] 4.1 测试：四类资源生命周期 + 状态机 + frozen/越界路径/跨用户拒绝 + 学习曲线空历史；离线全量通过且覆盖率 ≥ 90
- [x] 4.2 独立审查、修复、文档（API.md）与验证报告

## 交付门禁
提交并创建关联 #156 的 PR，检查远端 CI，并在验证报告中记录交付结果。
