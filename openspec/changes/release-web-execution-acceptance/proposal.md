## Why

[#443](https://github.com/JayNey/LLM-Algorithm-Harness/issues/443) 要求在候选构建上核对生产 Web 入口和四条从浏览器到沙箱的业务链。历史验收覆盖不同构建及依赖组合。

## What Changes

- 在隔离 Linux 环境使用生产编排执行可复现的发布验收。
- 记录真实服务、故障恢复、任务结果和模型替身边界。真实供应商另行授权。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。交付验收针对现有契约。

## Impact

生产 Compose 验收和脱敏证据。
