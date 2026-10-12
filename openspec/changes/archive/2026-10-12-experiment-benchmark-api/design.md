# 设计说明：experiment-benchmark-api

## 决策

1. **薄腰设计：DB 存任务状态，产物目录存结果**。`ExperimentRunner`/`ABTestRunner` 本就以产物目录为输出契约（experiment.json、comparison 报告等），结果端点直接解析产物，不把大结果塞进数据库。四张新表只存配置（脱敏）、状态、owner、产物路径与错误信息。基准 run 例外：其结果本身是小型指标记录（accuracy/cost），作为行存储以支撑学习曲线聚合。
2. **密钥注入**：请求只带 `api_key_id`（沿用 #172 评估端点先例）。创建时 `auth.owned_key` 校验归属；运行时经认证库解密密钥注入 `LLMConfig.api_key`（SecretStr），模型配置序列化时自动脱敏（`redacted_dict`）。多模型实验共用该密钥；跨提供商多密钥留待需要时扩展。
3. **数据集路径约束**：`dataset_path` 解析后必须位于数据根目录（`settings.DATA_ROOT`，默认 `data/`）内，拒绝越界路径，防服务端任意文件读取。
4. **异步执行与可测试性**：后台线程模式与评估服务一致（semaphore 限并发、终态守卫、with_for_update 行锁）。runner 类经构造参数注入（默认真实实现；`ABTestRunner` 原生支持 client/sandbox 工厂；`ExperimentRunner`/`BenchmarkExecutor` 以工厂参数传入类而非实例），测试注入 fake 而无需真实 LLM。
5. **分析端点无状态化**：帕累托/成本优化不落库，POST payload 直通 `build_pareto_analysis`/`build_advisory` 等纯函数；输入校验失败映射为 400（捕获 ValueError）。
6. **frozen 语义**：Suite 的 frozen 字段来自 `src/benchmark/suite.BenchmarkSuite` 模型；frozen=True 的 Suite 更新/删除返回 400。 Suite 创建时允许 frozen=False。
7. **表结构**（迁移 0002）：`experiments`（config JSON 脱敏 + api_key_id + output_dir）、`benchmark_suites`（config JSON）、`benchmark_runs`（suite_id FK CASCADE、model JSON、accuracy/cost 浮点、results JSON——学习曲线的行来源）、`ab_tests`（config JSON 脱敏 + output_dir）。全部含 owner 作用域与时间戳列，模式与 0001 一致（naive UTC）。

## 非目标

- 实验队列调度与抢占（#149 任务队列后续统一）
- WebSocket 进度推送（#150）
- 学习曲线的图表渲染（返回数据，可视化属前端批次）
- 修改任何 `src/` 分析模块（只调用）
