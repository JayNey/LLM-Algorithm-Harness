## Why

[#443](https://github.com/JayNey/LLM-Algorithm-Harness/issues/443) 要求在候选构建上核对生产 Web 入口和四条从浏览器到沙箱的业务链。历史验收覆盖不同构建及依赖组合。

## What Changes

- 在隔离 Linux 环境使用生产编排执行可复现的发布验收。
- 记录真实服务、故障恢复、任务结果和模型替身边界。真实供应商另行授权。
- 修复 PostgreSQL 恢复后的旧池连接故障，以及基准运行留空策略后的执行失败。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/experiment-management`。明确基准运行的默认策略。

## Impact

生产 Compose 验收、业务数据库连接池、基准 worker 执行配置和脱敏证据。
