## Purpose

缓存 LLM API 响应以避免重复调用，降低实验成本并提升调试效率。

## ADDED Requirements

### Requirement: 缓存键唯一性

系统 SHALL 为每次 LLM 调用生成唯一的缓存键，基于 `hash(model_id + prompt + temperature + max_tokens + problem_id + strategy_name)` 的组合。

#### Scenario: 相同参数生成相同缓存键

- **WHEN** 两次调用使用相同的 model、prompt、temperature、max_tokens、problem_id 和 strategy_name
- **THEN** 系统生成相同的缓存键

#### Scenario: 任一参数不同生成不同缓存键

- **WHEN** 两次调用中任一参数（model、prompt、temperature、max_tokens、problem_id 或 strategy_name）不同
- **THEN** 系统生成不同的缓存键

### Requirement: 缓存命中时零 API 调用

系统 SHALL 在缓存命中时直接返回缓存的响应，不调用 LLM API。

#### Scenario: 缓存命中直接返回

- **WHEN** 调用参数的缓存键在缓存中存在且未过期
- **THEN** 系统直接返回缓存的响应文本、token 使用量和元数据，不调用 LLM API

#### Scenario: 缓存未命中调用 API

- **WHEN** 调用参数的缓存键在缓存中不存在
- **THEN** 系统调用 LLM API 并将响应存入缓存

### Requirement: 本地磁盘存储

系统 SHALL 将缓存数据存储在本地磁盘的 `.cache/llm_responses/` 目录下，每个缓存条目为一个独立的 JSON 文件。

#### Scenario: 缓存文件格式

- **WHEN** 系统缓存一个 LLM 响应
- **THEN** 系统在 `.cache/llm_responses/{cache_key}.json` 创建文件，包含 `response_text`、`token_usage`、`timestamp`、`model`、`finish_reason` 和 `pricing_metadata` 字段

#### Scenario: 缓存目录自动创建

- **WHEN** 缓存目录 `.cache/llm_responses/` 不存在
- **THEN** 系统自动创建该目录

### Requirement: TTL 失效策略

系统 SHALL 实现基于时间的缓存失效机制，默认 TTL 为 30 天，超过 TTL 的缓存条目视为过期。

#### Scenario: 未过期缓存可用

- **WHEN** 缓存条目的时间戳距当前时间小于配置的 TTL
- **THEN** 系统视该缓存条目为有效并可返回

#### Scenario: 过期缓存不可用

- **WHEN** 缓存条目的时间戳距当前时间大于等于配置的 TTL
- **THEN** 系统视该缓存条目为过期，重新调用 LLM API 并更新缓存

### Requirement: LRU 淘汰机制

系统 SHALL 实现 LRU（最近最少使用）淘汰机制，当缓存占用磁盘空间超过配置的上限时，删除最久未访问的缓存条目。

#### Scenario: 磁盘空间未超限不淘汰

- **WHEN** 缓存占用磁盘空间小于配置的 `max_size_mb`
- **THEN** 系统不删除任何缓存条目

#### Scenario: 磁盘空间超限触发淘汰

- **WHEN** 缓存占用磁盘空间大于等于配置的 `max_size_mb`
- **THEN** 系统按 LRU 策略删除最久未访问的缓存条目，直到磁盘占用降至上限以下

### Requirement: 缓存配置选项

系统 SHALL 支持通过配置文件配置缓存行为，包括 `enabled`（是否启用）、`backend`（存储后端）、`ttl_days`（TTL 天数）和 `max_size_mb`（最大磁盘占用 MB）。

#### Scenario: 缓存禁用时不使用缓存

- **WHEN** 配置 `cache.enabled = false`
- **THEN** 系统每次调用都直接请求 LLM API，不读取或写入缓存

#### Scenario: 自定义 TTL

- **WHEN** 配置 `cache.ttl_days = 7`
- **THEN** 系统将缓存条目的 TTL 设置为 7 天

### Requirement: 手动清理命令

系统 SHALL 提供 `harness cache clear` 命令，允许用户手动清空所有缓存。

#### Scenario: 清空所有缓存

- **WHEN** 用户运行 `harness cache clear`
- **THEN** 系统删除 `.cache/llm_responses/` 目录下的所有缓存文件

#### Scenario: 清空特定模型缓存

- **WHEN** 用户运行 `harness cache clear --model <model_id>`
- **THEN** 系统仅删除与指定模型相关的缓存文件

### Requirement: 缓存统计查询

系统 SHALL 提供 `harness cache stats` 命令，显示缓存命中率、总条目数、磁盘占用和节省的 API 调用次数。

#### Scenario: 显示缓存统计

- **WHEN** 用户运行 `harness cache stats`
- **THEN** 系统显示缓存命中率、总条目数、磁盘占用（MB）和自启用缓存以来节省的 API 调用次数
