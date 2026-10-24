## 1. 用户准入限制

- [x] 1.1 配置正整数用户并发限额，并在评估创建、入队及原地恢复入口实现共享数据库事务锁及原子计数；以状态、隔离、回滚和多进程竞争测试验证。
- [x] 1.2 将超限错误映射为 HTTP 429，验证启动、异步创建、恢复均受限且拒绝时不发布消息。

## 2. 集成验证

- [x] 2.1 补充配置与部署说明，运行评估/TaskManager/API 回归、格式检查和编译，并记录最终验证证据。

构建证据：定向回归 163 passed；新增准入测试 18 passed；ruff、black、compileall 和 OpenSpec strict validate 通过。命令输出保存在 `/private/tmp/user-evaluation-concurrency-final-regression.log` 与 `/private/tmp/user-evaluation-concurrency-final-target.log`；验证阶段另行汇总完整套件结果和审查结论。

验证修复：补齐通用任务原地恢复入口，并在用户锁内重新读取状态以阻止竞争恢复重复发布；增加对应准入与竞争回归（含任务 API 的回归 181 passed）。全量检查暴露的 `.env.example` 新配置遗漏及测试子进程 UTF-8 编码已补齐，进行最终全量复验。

最终增量证据：EvaluationService 恢复改为先提交关联后发布，真实 worker 读连接回归由 RED 转为 GREEN；相关回归 239 passed（含 21 项新准入测试、任务 API、部署与 UTF-8 约束）。全量离线复验 3115 passed、8 skipped、覆盖率 91.88%，该轮在最终恢复关联修复前启动，最终修复由上述增量回归覆盖。用户明确确认文件数超过提示阈值后继续 tweak。
