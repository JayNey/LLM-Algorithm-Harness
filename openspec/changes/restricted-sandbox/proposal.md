## Why

当前 `SandboxExecutor` 使用普通宿主 `subprocess.run` 执行模型代码。`memory_limit_mb` 没有生效，子进程继承宿主环境，网络、文件系统、输出体积和派生进程都没有可靠边界。

## What Changes

- 增加显式 sandbox 后端配置，生产默认使用 Docker；后端不可用时返回结构化失败，不静默退回宿主进程。
- Docker 执行固定禁用网络、只读根文件系统、移除 Linux capabilities、限制内存/进程数/CPU/临时目录和环境变量。
- 增加输出体积、超时、内存和派生进程限制，并在结束或失败时清理临时资源。
- 保留显式 `host` 后端供单元测试使用，文档明确其不具备生产隔离能力。
- 将后端不可用、超时、内存、输出超限和运行错误统一映射为结构化结果。

## Capabilities

### New Capabilities

- `restricted-sandbox`: 定义不受信任代码的隔离后端、资源边界和失败语义。

## Impact

- 影响 `SandboxConfig`、`SandboxResult`、`SandboxExecutor`、CLI 配置示例和沙箱测试。
- 不改变题目协议、策略接口或模型调用协议。
