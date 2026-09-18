## Why

仓库已有 OpenAI 兼容协议的 `base_url` 支持，硅基流动官方提供兼容的 Chat Completions 接口（对应上游 issue #11）。当前用户需手工拼 `provider=openai` + `base_url` + key 环境变量，缺少服务预设、模型列表查询与连接检查，配置体验断裂。

## What Changes

- `LLMConfig.provider` 新增 `siliconflow` 预设：复用 OpenAI 协议客户端，默认兼容地址 `https://api.siliconflow.cn/v1`，密钥优先显式配置，回退 `SILICONFLOW_API_KEY` 环境变量（继续支持 `env:NAME` / `${NAME}` 引用）。
- 新增模型列表查询（官方 `GET /models` 接口）：列出可选模型 ID；小模型规模元数据无可靠来源时标记未知；查询失败时报告原因并允许手动配置模型 ID。
- 新增连接检查：默认走模型列表接口（不产生计费）；命令说明中明确"生成式检查会产生计费"。
- `config.example.json` 提供无真实密钥的硅基流动示例；README 补充三种策略的调用说明。
- 在线单题验证以 `online` 标记显式标注，无凭证环境自动跳过，Mock 成功不作为真实 API 验证。

## Capabilities

### New Capabilities

- `siliconflow-provider`: 定义硅基流动服务预设、密钥解析边界、模型列表查询与连接检查行为。

## Impact

- 影响 `src/models.py`（provider 枚举）、`src/llm_client.py`（预设与查询）、`src/main.py`（CLI 参数）、`config.example.json`、`README.md`、`pyproject.toml`（online 标记注册）。
- 不改变 OpenAI/Anthropic 既有接入行为；不承诺任何模型的效果或免费额度。
