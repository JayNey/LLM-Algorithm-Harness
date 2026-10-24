## 1. 用户准入限制

- [x] 1.1 配置正整数用户并发限额，并在两种评估提交入口实现共享数据库事务锁及原子计数；以状态、隔离、回滚和多进程竞争测试验证。
- [x] 1.2 将超限错误映射为 HTTP 429，验证启动、异步创建、恢复均受限且拒绝时不发布消息。

## 2. 集成验证

- [x] 2.1 补充配置与部署说明，运行评估/TaskManager/API 回归、格式检查和编译，并记录最终验证证据。

构建证据：定向回归 163 passed；新增准入测试 18 passed；ruff、black、compileall 和 OpenSpec strict validate 通过。命令输出保存在 `/private/tmp/user-evaluation-concurrency-final-regression.log` 与 `/private/tmp/user-evaluation-concurrency-final-target.log`；验证阶段另行汇总完整套件结果和审查结论。
