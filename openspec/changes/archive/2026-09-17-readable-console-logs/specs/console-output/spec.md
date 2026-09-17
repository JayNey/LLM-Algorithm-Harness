## Purpose

定义评测过程日志在终端的呈现方式：默认人类可读、机器格式显式可选，且两种格式下脱敏行为一致。

## ADDED Requirements

### Requirement: 控制台默认人类可读
系统 MUST 默认以人类可读的紧凑格式向终端输出结构化日志（短时间戳、键值对），而非 JSON 行。

#### Scenario: 默认运行评测
- **WHEN** 用户不带日志格式参数运行评测
- **THEN** 终端日志为可读键值行而非 JSON 行，最终结果紧随其后

### Requirement: 机器格式显式可选
系统 SHALL 提供 `--log-format` 参数，`json` 取值完整保留现有 JSON 行为。

#### Scenario: 管道消费日志
- **WHEN** 以 `--log-format json` 运行
- **THEN** 日志行为 JSON 对象，与既有机器消费格式一致

### Requirement: 第三方噪音压制
系统 SHALL 将 httpx、httpcore、openai 等第三方日志源压制到 WARNING 级别。

#### Scenario: 模型请求重试
- **WHEN** 模型 SDK 记录请求级 INFO 日志（如 HTTP 请求行）
- **THEN** 终端不再出现该类刷屏，异常仍经 harness 自身事件呈现

### Requirement: 双格式脱敏一致
脱敏处理器 MUST 在控制台与 JSON 两种格式下均生效。

#### Scenario: 控制台日志含凭证字段
- **WHEN** 日志事件包含 API Key 等敏感字段
- **THEN** 控制台与 JSON 输出均只含脱敏占位符
