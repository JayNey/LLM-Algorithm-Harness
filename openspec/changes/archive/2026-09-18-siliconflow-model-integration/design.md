## Context

`LLMConfig.provider` 为 `Literal["openai", "anthropic", "local"]`；OpenAI 分支已支持 `base_url` 与 `max_retries`，密钥解析（直接值 / 供应商默认环境变量 / `env:NAME` / `${NAME}`）集中在 `_resolve_api_key`。硅基流动提供 OpenAI 兼容协议与官方模型列表接口（`GET /models`，不计费）。

## Goals / Non-Goals

**Goals:**

- 一行配置接入硅基流动（provider 预设 + 独立密钥来源），OpenAI/Anthropic 零回归。
- 模型列表与连接检查可通过 CLI 直接使用，失败时给出可行动的错误原因。
- 真实 API 验证与 Mock 验证明确区分（`online` 标记）。

**Non-Goals:**

- 不为每个兼容平台新增协议分支或请求层。
- 不承诺模型效果、不写死"永久可用/免费"的模型 ID、不代理用户密钥。

## Decisions

1. **provider 预设而非新协议。** `siliconflow` 分支复用 OpenAI SDK 客户端，仅注入预设 `base_url` 与独立密钥解析（默认环境变量 `SILICONFLOW_API_KEY`）；显式配置的 `base_url` 仍可覆盖预设。
2. **模型列表走 OpenAI SDK 的 `models.list()`。** 与 Chat Completions 同源鉴权与错误语义；SDK 已带重试。规模元数据官方接口不可靠，CLI 一律标注未知，宁缺毋滥。
3. **连接检查 = 模型列表 + 明确说明。** 列表接口不计费，命令帮助注明"生成式连接检查才会计费"；鉴权失败、网络失败分别给出可行动原因，并列出手动配置模型 ID 的提示。
4. **在线验证显式标记。** 注册 `pytest.ini` 的 `online` marker，在线用例在无 `SILICONFLOW_API_KEY` 时自动 skip；Mock 用例不得标注成功为真实 API 验证。

## Risks / Trade-offs

- [provider 枚举扩展影响既有校验] → 仅新增字面量，不改动既有取值；回归测试覆盖 OpenAI/Anthropic。
- [模型列表接口与 Chat 接口的错误语义可能不一致] → 错误映射集中在一处并保留原始原因，测试断言错误信息可读。
- [在线验证依赖真实凭证与外部服务稳定性] → 无凭证自动跳过并在报告中显式标注"未执行真实 API 验证"。
