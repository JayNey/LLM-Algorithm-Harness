# LLM Response Cache

## 概述

LLM Response Cache 是一个本地磁盘缓存系统，用于存储 LLM API 响应。通过缓存相同参数的响应，可以显著降低重复实验的成本，提升实验可复现性，并加速调试周期。

## 功能特性

- **精确匹配缓存**：基于 model、prompt、temperature、max_tokens、problem_id 和 strategy_name 生成唯一缓存键
- **本地磁盘存储**：缓存文件存储在 `.cache/llm_responses/` 目录，每个响应一个 JSON 文件
- **TTL 失效策略**：支持配置缓存过期时间（默认 30 天）
- **LRU 淘汰机制**：当缓存超过磁盘空间限制时，自动删除最久未访问的条目
- **透明集成**：对调用方完全透明，无需修改现有代码
- **CLI 管理命令**：提供命令行工具管理缓存

## 配置

在配置文件中添加 `cache` 配置段：

```yaml
llm_config:
  provider: openai
  model: gpt-4
  api_key: ${OPENAI_API_KEY}
  cache:
    enabled: true          # 是否启用缓存，默认 true
    backend: disk          # 存储后端，目前只支持 disk
    ttl_days: 30           # 缓存过期时间（天），默认 30
    max_size_mb: 1000      # 最大磁盘占用（MB），默认 1000
```

或在 JSON 配置文件中：

```json
{
  "llm_config": {
    "provider": "openai",
    "model": "gpt-4",
    "api_key": "${OPENAI_API_KEY}",
    "cache": {
      "enabled": true,
      "backend": "disk",
      "ttl_days": 30,
      "max_size_mb": 1000
    }
  }
}
```

## 使用方法

### 自动缓存

缓存功能默认启用，无需修改代码。相同参数的 LLM 调用会自动从缓存返回：

```python
from src.llm_client import LLMClient
from src.models import LLMConfig

config = LLMConfig(
    provider="openai",
    model="gpt-4",
    api_key="your-key",
)

client = LLMClient(config)

# 第一次调用 - 请求 API
response1 = client.generate(
    prompt="Solve this problem",
    problem_id="leetcode-001",
    strategy_name="cot"
)

# 第二次调用相同参数 - 从缓存返回，零 API 调用
response2 = client.generate(
    prompt="Solve this problem",
    problem_id="leetcode-001",
    strategy_name="cot"
)
```

### 禁用缓存

临时禁用缓存：

```python
config = LLMConfig(
    provider="openai",
    model="gpt-4",
    api_key="your-key",
    cache=CacheConfig(enabled=False)
)
```

## CLI 命令

### 查看缓存统计

```bash
harness cache stats
```

输出示例：

```
Cache Statistics:
  Enabled: True
  Total entries: 42
  Disk usage: 3.45 MB
  Hit rate: 67.50%
  Hits: 27
  Misses: 13
  API calls saved: 27
```

### 清空所有缓存

```bash
harness cache clear
```

### 清空特定模型的缓存

```bash
harness cache clear --model gpt-4
```

## 缓存键生成

缓存键基于以下参数的 SHA256 哈希生成：

- `model`: 模型标识符（如 `gpt-4`）
- `prompt`: 用户 prompt
- `system_prompt`: 系统 prompt（如果有）
- `temperature`: 采样温度
- `max_tokens`: 最大生成 token 数
- `problem_id`: 问题标识符（可选）
- `strategy_name`: 策略名称（可选）

任一参数不同都会生成不同的缓存键。

## 缓存文件格式

每个缓存条目是一个 JSON 文件，包含以下字段：

```json
{
  "response_text": "LLM 生成的文本",
  "token_usage": {
    "prompt_tokens": 100,
    "completion_tokens": 200,
    "total_tokens": 300,
    "reasoning_tokens": 0
  },
  "timestamp": 1234567890.123,
  "model": "gpt-4",
  "finish_reason": "stop",
  "pricing_metadata": {
    "model": "gpt-4",
    "prompt_price_per_1k": 0.03,
    "completion_price_per_1k": 0.06,
    "total_cost": 0.015
  },
  "usage_missing": false,
  "reasoning_text": null,
  "effective_params": {
    "temperature": 0.7,
    "max_tokens": 2000
  }
}
```

## LRU 淘汰

当缓存占用磁盘空间超过 `max_size_mb` 时，系统会：

1. 读取访问记录文件 `.cache/llm_responses/.access_log.json`
2. 按访问时间排序所有缓存条目
3. 删除最久未访问的条目，直到磁盘占用降至限制以下

访问记录在每次缓存读取或写入时自动更新。

## TTL 失效

缓存条目在创建后超过 `ttl_days` 天会自动过期。过期的条目在读取时会被忽略，系统会重新调用 LLM API 并更新缓存。

## 最佳实践

1. **合理设置 TTL**：根据模型更新频率设置 TTL。频繁更新的模型使用较短的 TTL。
2. **监控磁盘占用**：定期使用 `harness cache stats` 检查缓存大小。
3. **清理旧缓存**：模型升级后使用 `harness cache clear --model <old-model>` 清理旧模型缓存。
4. **调试时禁用**：调试 prompt 变化时临时禁用缓存，避免混淆。
5. **包含上下文参数**：使用 `problem_id` 和 `strategy_name` 参数确保缓存准确性。

## 性能影响

- **缓存命中**：零 API 调用，响应时间通常 < 10ms
- **缓存未命中**：正常 API 调用 + 写入缓存（~1-5ms）
- **磁盘 I/O**：相比 LLM API 调用（通常数秒），磁盘 I/O 可忽略

## 故障排除

### 缓存不生效

1. 检查配置：`cache.enabled` 是否为 `true`
2. 检查参数：确认两次调用的所有参数完全相同
3. 检查日志：查看是否有 `cache_hit` 日志

### 磁盘空间不足

1. 增加 `max_size_mb` 配置
2. 清理旧缓存：`harness cache clear`
3. 减少 `ttl_days` 让缓存更快过期

### 缓存响应错误

1. 清空缓存：`harness cache clear`
2. 检查模型是否已更新，清理旧模型缓存
3. 如果问题持续，临时禁用缓存并报告 issue

## 技术细节

- **原子写入**：使用临时文件 + `rename` 确保写入原子性
- **并发安全**：文件系统天然支持并发读取，写入冲突极少（相同参数同时调用）
- **哈希冲突**：使用 SHA256，冲突概率极低（~1/2^256）
- **访问记录**：JSON 格式，键为缓存键，值为 Unix 时间戳

## 限制

- 仅支持本地磁盘存储（不支持 Redis 等分布式缓存）
- 仅支持精确匹配（不支持语义相似性缓存）
- 不缓存流式响应
- 不支持跨机器共享缓存
