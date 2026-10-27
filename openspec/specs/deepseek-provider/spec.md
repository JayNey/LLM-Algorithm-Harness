# deepseek-provider Specification

## Purpose
规定 DeepSeek 官方端点、本人凭证边界、真实模型枚举及评估生成行为，确保 Web 与 CLI 的受控接入和可验证执行。

## Requirements

### Requirement: DeepSeek 官方地址与凭证边界

系统 SHALL 提供独立的 `deepseek` provider，使用 OpenAI 兼容 SDK 并固定官方地址 `https://api.deepseek.com`。该 provider MUST NOT 将凭证发送到任意用户地址或 SDK 环境变量覆盖的其他地址。CLI 可使用显式密钥或 `DEEPSEEK_API_KEY`，Web MUST 继续只接受本人提交的 literal key 并加密保存，不返回明文或密文。

#### Scenario: 初始化官方客户端

- **WHEN** 使用 deepseek provider 初始化客户端
- **THEN** SDK 使用官方地址、解析后的密钥和禁用的 SDK 内置重试；配置非官方 base_url 被明确拒绝

#### Scenario: Web 密钥安全

- **WHEN** 已登录用户添加或列出 DeepSeek 密钥
- **THEN** 只处理本人资源，列表仅返回既有掩码和元数据，拒绝环境引用与任意 endpoint 字段

### Requirement: DeepSeek 实际模型枚举与验证

系统 SHALL 使用本人 DeepSeek 密钥读取真实模型列表并执行连接检查，复用既有 5 秒单请求限制、总调度预算、SDK 重试关闭、归属重核、客户端关闭及错误脱敏。枚举失败 MUST 返回明确失败，不返回静态模型作为成功。

#### Scenario: 完整无分页模型列表

- **WHEN** 官方接口返回完整的 OpenAI SDK 非分页列表
- **THEN** 响应携带真实模型 ID、provider=deepseek 和 complete=true，不产生生成调用

### Requirement: DeepSeek 真实评估生成

系统 SHALL 将 DeepSeek 生成请求通过 OpenAI 协议调用官方供应商，并复用已有用量、用户计量、预算、重试与响应解析，再由真实 worker 和沙箱执行评估。

#### Scenario: 生成与执行

- **WHEN** 本人 DeepSeek 密钥、模型、队列和沙箱可用并启动评估
- **THEN** 调用真实供应商，记录实际 token/成本和沙箱结果，不使用 fixture 或缓存成功冒充真实执行
