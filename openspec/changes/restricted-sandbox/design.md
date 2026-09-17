## Context

Docker 可提供本项目需要的网络、挂载和能力边界；本机可能没有运行中的 Docker daemon，因此执行器必须能报告明确的后端不可用状态。现有宿主 subprocess 逻辑保留为显式测试后端，不能在 Docker 失败后自动启用。

## Goals / Non-Goals

**Goals:**

- 默认路径使用 Docker，代码不接触宿主密钥、网络和项目文件。
- 以 Docker flags 和进程级 watchdog 共同落实时间、内存、输出、进程数限制。
- 对后端不可用和资源违规提供稳定的 `SandboxResult` 状态。

**Non-Goals:**

- 不宣称 Docker 是绝对安全边界，不实现多租户容器编排。
- 不在本 Issue 中实现 Windows/macOS 原生沙箱；Docker Desktop 是支持方式。

## Decisions

1. **Docker 是默认后端，host 是显式选择。** 默认运行没有 Docker 时失败并说明安装/启动要求；不会静默降级。
2. **容器使用最小权限。** 使用 `--network none`、`--read-only`、`--cap-drop ALL`、`--security-opt no-new-privileges`、非 root 用户、只读代码挂载和受限 tmpfs。
3. **Docker 外部仍有 watchdog。** 父进程限制命令时长并读取有界 stdout/stderr，超过输出预算立即终止进程，避免宿主内存被日志拖垮。
4. **环境变量白名单为空。** 容器只接收必要的 Python 运行变量，模型 API Key、宿主环境和工作目录不传入。

## Risks / Trade-offs

- [需要预拉取 Python 镜像] → 后端不可用或镜像缺失时结构化失败，文档说明准备命令。
- [Docker 启动开销增加] → 生产安全优先；单元测试使用显式 host 后端或 mock 命令。
- [不同平台 Docker 行为有差异] → 把平台能力和限制记录到错误信息，不宣称跨平台同等隔离。
