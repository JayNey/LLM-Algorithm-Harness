## Purpose

确保模型服务凭证只在调用边界可用，不进入日志、错误、配置快照或报告导出。

## ADDED Requirements

### Requirement: 配置秘密默认不可见
系统 MUST 将 API Key 作为秘密值处理，普通字符串表示、嵌套配置视图、Python/JSON 序列化和结构化日志均不得包含原始值。

#### Scenario: 初始化 Harness
- **WHEN** 配置包含固定假密钥并初始化 Harness
- **THEN** 日志与安全配置视图包含脱敏占位符且不包含假密钥

#### Scenario: 序列化配置
- **WHEN** 调用配置模型的普通字典或 JSON 序列化
- **THEN** 输出不包含 API Key 原文

### Requirement: 原始秘密只在模型调用边界解析
系统 SHALL 支持直接密钥、供应商默认环境变量、`env:NAME` 和 `${NAME}` 引用，并且只向对应模型 SDK 传递解析后的原始值。

#### Scenario: 模型客户端获取密钥
- **WHEN** 使用直接密钥或有效环境变量引用初始化客户端
- **THEN** SDK 收到正确原始值，其他配置表示仍保持脱敏

#### Scenario: 密钥来源缺失
- **WHEN** 直接值为空且默认环境变量缺失，或显式引用的变量不存在
- **THEN** 初始化在请求前失败并说明缺失来源，错误不包含其他环境变量值

### Requirement: 错误和导出内容统一脱敏
系统 MUST 在记录异常以及生成 JSON、CSV、Markdown、HTML 输出前递归清理敏感字段和凭证文本。

#### Scenario: 供应商异常包含密钥
- **WHEN** 模型 SDK 抛出的异常文本包含当前 API Key
- **THEN** 日志和向上传播的错误只包含脱敏占位符

#### Scenario: 结果或报告包含敏感字段
- **WHEN** 结果快照或报告输入包含嵌套 API Key、Authorization 或 token 字段
- **THEN** 所有生成文件不包含原始秘密值
