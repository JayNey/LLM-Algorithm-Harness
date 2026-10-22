# Celery 基准任务认证注入验证

结论：PASS。Change：fix-celery-benchmark-auth；实现提交：b12eb88；分支：hotfix/20261022/fix-celery-benchmark-auth。

## 验证规模

自动规模统计 14 个变更文件，包含 12 个 Comet/OpenSpec 状态、快照及文档文件，实际代码范围为 1 个 worker 文件和 1 个测试文件、3 项任务，无 delta spec。按 comet-verify 允许的人工覆盖，采用 light 验证。review_mode=off 为 hotfix 默认值，因此跳过自动集成代码审查。

## 六项检查

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 任务完成 | PASS | tasks.md 共 3 项全部 [x] |
| 范围一致 | PASS | 实现仅涉及认证注入和连接释放，测试覆盖真实任务体认证及所有权拒绝；其余为本 change 的工作流产物 |
| 编译 | PASS | python3 -m compileall -q src/tasks/benchmark.py，退出 0 |
| 相关测试 | PASS | build 阶段 85 passed；提交后 verify 阶段基准任务 13 passed |
| 安全 | PASS | 按运行所属用户取密钥、继续由 AuthService 解密；外用户密钥被拒绝；源码无新增明文密钥，测试密钥仅临时离线使用 |
| 自动集成审查 | 按配置跳过 | hotfix 默认 review_mode=off，无审查派发 |

## 命令与结果

- RED：`MPLCONFIGDIR=/private/tmp/celery-benchmark-mpl pytest tests/test_benchmark_task.py -k 'disables_recovery or disposes_engine or resolves_owned_credentials' --no-cov`，4 failed。合法密钥任务失败，实际错误 authentication service is not configured，AuthService 构造断言失败。
- GREEN/相关测试：`MPLCONFIGDIR=/private/tmp/celery-benchmark-mpl pytest tests/test_benchmark_task.py tests/test_experiment_task.py tests/test_api_experiment_benchmark.py tests/benchmark --no-cov`，85 passed，退出 0。
- 提交后 verify：`MPLCONFIGDIR=/private/tmp/celery-benchmark-mpl pytest tests/test_benchmark_task.py --no-cov`，13 passed，退出 0。所属用户密钥解密后传入执行器，指标 0.75/1.25 落库；外用户密钥错误为 API key not found。
- `black --check src/tasks/benchmark.py tests/test_benchmark_task.py`、`ruff check src/tasks/benchmark.py tests/test_benchmark_task.py`、`python3 -m compileall -q src/tasks/benchmark.py`、`git diff --check` 均退出 0。
- `comet classic openspec -- validate fix-celery-benchmark-auth --strict` 通过，无规格行为变更。

## 根因与限制

原先未注入的直接执行语句已被显式注入 AuthService(AuthSettings()) 替代，recover=False 保留；执行正常或抛出异常时均在 finally 释放服务 engine。

真实认证回归调用进程内的 Celery 任务体，使用临时业务库、真实 AuthService、加密持久化测试密钥，只替换最终 BenchmarkExecutor.execute。未验证真实 Redis broker、独立 worker、模型提供商或 Docker 沙箱。测试的 5 条警告来自既有 Pydantic Config 弃用提示。

验证结束时未提交变更均为本 change 的阶段状态和本报告，无其他来源变更。用户于 2026-10-22 选择 C，授权归档、提交、立即推送当前绑定分支并创建 PR。归档成功，branch_status=handled 表示交付方式已确认；远端交付按此选择执行。

上下文插件因 ~/.comet/plugins/state.json.lock 权限不足未运行，不阻断验证。
