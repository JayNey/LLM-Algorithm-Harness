# frontend/api-keys Specification

## Purpose
让已登录用户管理自己的 LLM API 密钥，包括添加、改名、删除和验证，同时不暴露密钥值；按受支持的供应商分组展示元数据，并保留会话认证和本人资源归属边界。

## Requirements

### Requirement: 按提供商列出密钥

已登录用户 SHALL 能看到自己的 API 密钥，并按 `openai`、`anthropic`、`siliconflow`、`deepseek` 分组。每条记录 SHALL 显示名称、提供商、创建时间、是否已验证、使用次数和最后使用时间。没有最后使用时间时 SHALL 明确表示尚未使用。当服务端提供 `masked_preview` 时，列表 SHALL 显示该掩码字符串；MUST NOT 显示密钥明文、密文，或仅展示末尾若干字符的片段。没有 `masked_preview` 的旧记录 SHALL 不显示掩码行。

#### Scenario: 列出两个提供商的密钥

- **WHEN** 当前用户有一条 OpenAI 密钥和一条 Anthropic 密钥，且两条均有 `masked_preview`
- **THEN** 两条密钥分别出现在对应提供商分组下，每条显示名称与掩码，且不出现完整密钥值

#### Scenario: 尚未使用的密钥

- **WHEN** 一条密钥没有最后使用时间
- **THEN** 该记录表明尚未使用，并显示使用次数为 0

#### Scenario: 旧记录无掩码

- **WHEN** 一条密钥的 `masked_preview` 为空
- **THEN** 列表仍显示该密钥的元数据，但不渲染掩码行

#### Scenario: DeepSeek 分组

- **WHEN** 服务端返回本人的 DeepSeek 密钥
- **THEN** 页面正确解析并在 DeepSeek 分组显示元数据，不丢弃记录或暴露密钥

### Requirement: 添加密钥

添加表单 SHALL 要求选择 `openai`、`anthropic`、`siliconflow` 或 `deepseek`，填写 1–100 个字符的名称，并在密码框中输入密钥值。空白密钥，以及以 `env:`、`ENV:` 或 `${` 开头的值，MUST 在提交前被拒绝且不发送请求。添加成功后列表 SHALL 出现新记录，并且页面不再显示刚才输入的密钥值。

#### Scenario: 添加 SiliconFlow 密钥

- **WHEN** 已登录用户提交提供商、名称和合法密钥值
- **THEN** 对应分组出现这条新密钥，页面不显示密钥值

#### Scenario: 添加 DeepSeek 密钥

- **WHEN** 已登录用户选择 DeepSeek 并提交合法密钥
- **THEN** 服务端保存本人密钥，列表显示对应分组且输入值被清空

#### Scenario: 拒绝环境变量引用

- **WHEN** 用户在密钥框输入以 `env:` 开头的文本并提交
- **THEN** 页面指出需要真实密钥值，且不发送添加请求

### Requirement: 修改密钥名称

用户 SHALL 能修改已有密钥的名称。编辑提交 MUST 只改变名称，MUST NOT 要求或发送新的密钥值。保存成功后列表 SHALL 显示新名称。

#### Scenario: 只修改名称

- **WHEN** 用户把一条密钥的名称改为新的非空名称并保存
- **THEN** 列表显示新名称，且编辑过程没有出现密钥值

### Requirement: 确认后删除密钥

删除 SHALL 先请求用户确认。用户取消时密钥 MUST 保留。用户确认后密钥 SHALL 从列表消失。

#### Scenario: 取消删除

- **WHEN** 用户选择删除后取消确认
- **THEN** 该密钥仍在列表中

#### Scenario: 确认删除

- **WHEN** 用户选择删除并确认
- **THEN** 该密钥从列表中消失

### Requirement: 验证密钥

用户 SHALL 能对一条密钥发起验证。验证成功时该记录 SHALL 显示为已验证。验证失败时 SHALL 显示通用失败说明，MUST NOT 显示提供商返回的原始错误，也 MUST NOT 显示密钥值。

#### Scenario: 验证成功

- **WHEN** 用户验证一条密钥且验证结果为成功
- **THEN** 该记录显示为已验证

#### Scenario: 验证失败

- **WHEN** 用户验证一条密钥且验证结果为失败
- **THEN** 页面显示通用失败说明，不显示密钥值或提供商原始错误

### Requirement: 未登录不能管理密钥

未登录用户打开 API 密钥页时 SHALL 进入登录页，并且 MUST NOT 展示密钥列表。

#### Scenario: 未登录打开密钥页

- **WHEN** 未登录用户打开 API 密钥页
- **THEN** 应用进入登录页，并且不展示任何密钥记录
