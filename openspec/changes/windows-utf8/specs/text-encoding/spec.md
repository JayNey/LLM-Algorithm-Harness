# Text Encoding Specification

## ADDED Requirements

### Requirement: 文本文件使用显式 UTF-8

系统 MUST 为直接文本文件、临时代码文件和日志文件读写指定 UTF-8；二进制文件操作 MUST 保持二进制模式。

#### Scenario: Windows 默认编码读取报告

- **Given** 默认编码为 cp1252，报告含中文、Ω 与 emoji
- **When** 系统保存并重新读取报告
- **Then** UTF-8 内容无损往返，不产生 charmap 编码或解码错误

### Requirement: Python 子进程标准流编码一致

系统 MUST 在将 Python 子进程输出按 UTF-8 解码时约定子进程使用 UTF-8 标准流，并保留父进程环境与沙箱隔离设置。

#### Scenario: 原始子进程环境为 cp1252

- **Given** 子进程环境声明 cp1252 标准流且关闭默认 UTF-8 模式
- **When** 构造 UTF-8 标准流环境并运行输出中文的子进程
- **Then** 输出完整解码为 UTF-8，父进程环境不变，文件默认 UTF-8 模式不被强制启用

### Requirement: 编码回归验证

系统 MUST 提供直接文本调用的静态检查和独立的跨平台 Unicode 回归测试，macOS 与 Ubuntu CI MUST 继续通过。

#### Scenario: Windows 其他兼容问题阻塞完整收集

- **Given** Windows 完整套件因 Unix 文件锁模块而收集失败
- **When** CI 执行编码验证
- **Then** 编码测试先独立执行并给出结论，Windows 容错移除仍由父 issue 在全部子项完成后处理
