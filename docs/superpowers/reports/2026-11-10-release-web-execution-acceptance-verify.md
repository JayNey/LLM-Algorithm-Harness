# 生产 Web 执行链正式验证

2026-11-10，变更 `release-web-execution-acceptance`，分支 `tweak/20261109/release-web-execution-acceptance`。核对分支提交 `0519e833` 与验收候选 `96951b4fa0ed7aa4df5beb1c24526b34ca1cdd64`。两者的应用源码、依赖和生产编排一致。验证结论为 **PASS**，范围为两项修复和模型替身发布验收。

## 完整性

- 五项任务均有勾选和证据。统一候选覆盖生产入口与就绪恢复、四条执行链、断线和跨进程恢复、基准预算暂停以及策略默认值。
- OpenSpec 严格校验通过，原生 delta 输出识别 `api/experiment-management` 的 1 项增量要求和 3 个场景。Comet 的规模统计把嵌套能力计为 0，本次按原生 delta 输出逐项核对并使用完整验证模式。
- 统一候选证据 ZIP 的 SHA-256 与验收记录一致，ZIP 测试及包内 20 项校验全部通过。候选的四条业务链和恢复证据见 [验收记录](../../../openspec/changes/archive/2026-11-10-release-web-execution-acceptance/evidence.md)。

## 正确性

- 省略策略及空数组。API 回归覆盖两种请求，均解析为单一 `vanilla`。候选浏览器留空策略时，真实 worker 完成 3/3，学习曲线刷新可读。留空策略的低预算运行调用替身一次后暂停，手动刷新读回 `paused`。
- 显式策略及参数。API 回归提交 `self_refine` 和 3 次迭代，worker 执行配置保留两项值。[API 回归](../../../tests/test_api_experiment_benchmark.py#L736)
- 旧记录。停止候选 worker 后通过生产 Nginx 提交两个测试运行，一个在隔离数据库中移除 `strategies` 字段，一个保留空数组。启动真实 worker 后，两条运行及各自的 Celery 任务均完成，均只使用 `vanilla`，每条通过 1 道合成题。运行标识 SHA-256 前缀分别为 `6d0b97bd2dec` 和 `c00cd9785310`。[worker 配置解析](../../../api/services/benchmark_service.py#L300)
- PostgreSQL 恢复。真实数据库空闲连接终止回归通过。重新预热业务连接池并停启 PostgreSQL，故障中就绪和业务均为 503。恢复就绪 200 后，实验创建、A/B 创建、基准套件列表的首个请求分别为 201、201、200。故障前后 API 容器 ID 与启动时间一致。[连接池配置](../../../api/db/engine.py#L38)

## 一致性与验证命令

默认策略在 worker 读取持久化配置时解析，与精简设计及增量规格一致。PostgreSQL 取用连接前检查集中在业务引擎工厂。按 tweak 工作流使用变更内的精简设计。配置 `review_mode: off`，集成核对使用源码差异、规格和运行证据。

```sh
python3 -m pytest tests/test_api_experiment_benchmark.py tests/test_benchmark_task.py tests/test_benchmark_run_budget.py tests/test_api_database.py tests/test_api_readiness.py tests/test_deployment_readiness.py -q --no-cov
comet classic openspec -- validate release-web-execution-acceptance --type change --strict --no-interactive
black --check api/db/engine.py api/services/benchmark_service.py tests/test_api_database.py tests/test_api_experiment_benchmark.py
ruff check api/db/engine.py api/services/benchmark_service.py tests/test_api_database.py tests/test_api_experiment_benchmark.py
git diff --check 73e7050a HEAD
```

宿主回归 143 项通过，1 项连接池用例因缺少 `TEST_POSTGRESQL_URL` 跳过，已在候选 API 容器连接真实 PostgreSQL 单独通过。5 条 Pydantic 弃用警告来自既有配置和模型类。生产 Compose 四个镜像重新构建成功，隔离服务已停止。

真实供应商联调仍待专用凭证和预算授权。正式验证通过仅适用于上述范围，[#443](https://github.com/JayNey/LLM-Algorithm-Harness/issues/443) 的供应商证据继续单独跟踪。
