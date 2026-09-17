## Purpose

在评测模型生成代码时提供明确的隔离后端和资源边界，避免代码访问宿主敏感内容或消耗无限资源。

## ADDED Requirements

### Requirement: 后端选择必须显式且安全
系统 SHALL 默认使用 Docker sandbox；Docker 不可用时 MUST 返回结构化后端不可用失败，不得自动退回宿主执行。

#### Scenario: Docker 后端不可用
- **WHEN** 默认 Docker daemon、镜像或命令不可用
- **THEN** 评测返回 `backend_unavailable` 或等价结构化失败，并说明修复方向

#### Scenario: 显式测试后端
- **WHEN** 测试明确选择 host 后端
- **THEN** 系统只在该显式配置下使用宿主 subprocess，并在文档中标明不具备生产隔离能力

### Requirement: 容器必须限制边界
Docker runner MUST 禁用网络、只读根文件系统、移除 capabilities、禁止提权、限制内存/进程数，并只挂载临时工作目录。

#### Scenario: 访问宿主资源
- **WHEN** 生成代码读取宿主文件、环境变量或发起网络请求
- **THEN** 访问失败且不会获得模型密钥或项目文件内容

#### Scenario: 普通算法代码
- **WHEN** 代码只使用允许的 Python 标准库完成数组、哈希表等算法
- **THEN** 在容器中正常执行并返回通过结果

### Requirement: 资源违规必须结构化终止
执行器 MUST 限制墙钟时间、内存、输出体积和派生进程，并在终止后清理临时文件和子进程。

#### Scenario: 超时或无限循环
- **WHEN** 代码超过 timeout_seconds
- **THEN** 返回 `timeout`，终止执行进程/容器且无残留子进程

#### Scenario: 输出、内存或进程超限
- **WHEN** 代码超过输出、内存或进程预算
- **THEN** 返回对应结构化状态，不把未限制输出写入宿主结果
