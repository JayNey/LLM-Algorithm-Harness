## Why

每次运行都重新调用 LLM API，即使相同的 prompt 也会重复调用，导致调试或重跑实验时浪费成本和时间。实现响应缓存可以显著降低重复实验的成本，提升实验可复现性，加速调试周期。

## What Changes

- 新增 LLM 响应缓存模块，支持本地磁盘存储
- 在 `LLMClient.generate()` 中集成缓存层，命中时直接返回缓存响应
- 实现基于哈希的缓存键生成（model + prompt + temperature + max_tokens + problem_id + strategy_name）
- 实现 TTL 失效策略（默认 30 天）和 LRU 淘汰机制
- 添加缓存管理命令：`harness cache clear`、`harness cache stats`
- 添加配置选项：`cache.enabled`, `cache.backend`, `cache.ttl_days`, `cache.max_size_mb`

## Capabilities

### New Capabilities

- `llm-response-cache`: LLM 响应缓存机制，包括缓存键生成、本地磁盘存储、TTL/LRU 策略、配置管理和统计功能

### Modified Capabilities

<!-- 无现有 capability 的 requirement 变更 -->

## Impact

**新增文件**：
- `src/cache.py` - 缓存核心逻辑
- `src/cache/` - 缓存模块（如需拆分为多个子模块）

**修改文件**：
- `src/llm_client.py` - 在 `generate()` 方法中集成缓存层
- `src/models.py` - 可能需要添加缓存相关的配置模型
- `src/cli.py` 或类似的 CLI 入口 - 添加 `cache` 子命令

**配置影响**：
- 配置文件需要支持新的 `cache.*` 配置项
- 需要在 `.cache/llm_responses/` 目录下存储缓存文件

**依赖项**：
- 可能需要添加文件系统操作相关的标准库使用（无需新增外部依赖）
