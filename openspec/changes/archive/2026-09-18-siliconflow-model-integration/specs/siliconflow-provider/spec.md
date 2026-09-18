## Purpose

定义硅基流动作为 OpenAI 兼容服务商的接入行为：服务预设与密钥边界、模型列表查询、连接检查，以及真实验证与 Mock 的区分。

## ADDED Requirements

### Requirement: 硅基流动服务预设
系统 SHALL 提供 `siliconflow` provider 预设：默认兼容地址 `https://api.siliconflow.cn/v1`，复用 OpenAI 协议客户端；密钥按显式配置 → `SILICONFLOW_API_KEY` → `env:`/`${}` 引用的顺序解析；显式 `base_url` 可覆盖预设；既有 OpenAI/Anthropic 接入不受影响。

#### Scenario: 使用预设初始化客户端
- **WHEN** 配置 `provider=siliconflow` 且未显式指定 `base_url`
- **THEN** SDK 收到预设兼容地址与解析后的密钥，密钥不进入日志或序列化输出

#### Scenario: 既有接入不回归
- **WHEN** 使用 `openai` 或 `anthropic` provider 运行原有流程
- **THEN** 行为与密钥解析结果与本变更前一致

### Requirement: 模型列表查询与手动回退
系统 SHALL 通过官方模型列表接口返回可选模型 ID；接口失败时报告错误原因，并允许用户手动配置完整模型 ID 继续使用；小模型规模元数据仅在有可靠来源时展示，缺失时标注未知。

#### Scenario: 模型列表成功
- **WHEN** 凭证有效且接口可用
- **THEN** 返回模型 ID 列表，规模未知时明确标注未知而不是编造数值

#### Scenario: 模型列表失败
- **WHEN** 鉴权失败或网络不可达
- **THEN** 报告具体错误原因，并提示可手动配置模型 ID 继续

### Requirement: 连接检查与计费说明
系统 SHALL 提供连接检查：默认使用模型列表接口（不产生计费）；命令说明 MUST 明确生成式检查会产生计费；鉴权失败与模型不存在给出明确错误。

#### Scenario: 连接检查通过
- **WHEN** 凭证与网络正常时执行连接检查
- **THEN** 报告成功状态与使用的兼容地址，且未发起任何生成请求

#### Scenario: 鉴权失败
- **WHEN** 使用无效凭证执行连接检查
- **THEN** 报告鉴权失败原因，不泄露密钥原文

### Requirement: 真实验证与 Mock 区分
真实凭证的端到端验证 MUST 以 `online` 标记显式标注；无凭证环境自动跳过；Mock 测试的结果不得被描述为真实 API 验证。

#### Scenario: 无凭证环境
- **WHEN** CI 或本地环境没有硅基流动凭证
- **THEN** 标记为 online 的用例被跳过且跳过原因可见

#### Scenario: 有凭证的在线验证
- **WHEN** 环境存在有效凭证并执行 online 用例
- **THEN** 记录实际使用的模型 ID 与验证日期，完成单题生成、执行与结果保存
