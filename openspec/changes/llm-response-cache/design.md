## Context

当前 `LLMClient.generate()` 每次调用都直接请求 LLM API。项目中存在大量重复实验和调试场景，相同的 prompt 会被多次调用。现有代码结构清晰：`LLMClient` 负责 API 调用，`LLMConfig` 管理配置，`LLMResponse` 封装响应。

## Goals / Non-Goals

**Goals:**
- 透明集成缓存层，不改变 `LLMClient.generate()` 的外部接口
- 支持本地磁盘缓存，无需额外依赖
- 提供可配置的缓存策略（TTL、LRU、启用/禁用）
- 提供缓存管理命令

**Non-Goals:**
- 不支持分布式缓存（Redis 等）作为初始实现
- 不缓存流式响应（如需支持需单独设计）
- 不自动处理 prompt 语义相似性（仅精确匹配）

## Decisions

### 决策 1：缓存键设计

**选择**：`hash(model_id + prompt + system_prompt + temperature + max_tokens + problem_id + strategy_name)`

**理由**：
- 包含所有影响 LLM 响应的参数，确保缓存准确性
- 使用哈希而非明文拼接，避免文件名过长和特殊字符问题
- `problem_id` 和 `strategy_name` 来自调用上下文，需要通过 `LLMClient.generate()` 的新可选参数传入

**备选方案**：
- 不包含 `problem_id` 和 `strategy_name`：会导致不同问题/策略的相同 prompt 被错误缓存
- 使用明文拼接：文件名可能超长，且包含特殊字符

### 决策 2：缓存存储格式

**选择**：每个缓存条目为独立 JSON 文件，文件名为 `{cache_key}.json`

**理由**：
- 简单直接，无需额外数据库依赖
- JSON 人类可读，便于调试
- 文件系统天然支持并发读取

**备选方案**：
- SQLite：增加依赖，对于缓存场景过重
- 单一大文件：并发写入需要锁机制，复杂度高

### 决策 3：缓存层集成点

**选择**：在 `LLMClient.generate()` 内部，调用 provider 前检查缓存，调用后写入缓存

**理由**：
- 对调用方完全透明，无需修改现有调用代码
- 集中管理缓存逻辑，易于维护
- 可以复用现有的 `LLMResponse` 对象

**备选方案**：
- 在调用方包装 `LLMClient`：侵入性强，需要修改所有调用点
- 独立缓存服务：过度设计，增加复杂度

### 决策 4：LRU 实现

**选择**：基于文件的 `atime`（访问时间）或自维护的访问记录文件

**理由**：
- 文件系统的 `atime` 在某些系统上默认禁用（如 macOS 的 noatime）
- 自维护访问记录文件（如 `.cache/llm_responses/.access_log.json`）更可靠
- 淘汰时读取所有文件的元数据，按访问时间排序删除

**备选方案**：
- 依赖文件系统 `atime`：不可靠
- 使用 SQLite 记录访问：增加依赖

### 决策 5：配置方案

**选择**：在现有配置文件中新增 `cache` 段，包含 `enabled`、`backend`、`ttl_days`、`max_size_mb`

**理由**：
- 复用现有配置机制
- `backend` 字段预留扩展性（未来可支持 `redis`）
- 默认 `enabled=true`，`ttl_days=30`，`max_size_mb=1000`

## Risks / Trade-offs

**Risk 1**：缓存键冲突导致错误响应
- **Mitigation**：使用 `hashlib.sha256` 生成 256 位哈希，冲突概率极低；包含所有关键参数确保唯一性

**Risk 2**：磁盘空间耗尽
- **Mitigation**：实现 LRU 淘汰机制，配置 `max_size_mb` 限制；提供 `harness cache clear` 手动清理

**Risk 3**：缓存过期响应（模型更新后）
- **Mitigation**：缓存键包含 `model_id`，不同模型版本不共享缓存；用户可通过 `harness cache clear --model` 清理特定模型缓存

**Risk 4**：并发写入同一缓存键
- **Mitigation**：使用原子写入（先写临时文件再 `rename`）；并发写入同一键的场景极少（相同参数同时调用）

**Trade-off 1**：精确匹配 vs 语义相似性
- **选择**：仅支持精确匹配
- **理由**：语义相似性匹配需要向量化和相似度计算，复杂度高且可能引入错误缓存；精确匹配足够覆盖重复实验场景

**Trade-off 2**：磁盘 I/O 开销
- **影响**：每次缓存读取需要读文件，可能略慢于内存缓存
- **可接受性**：相比 LLM API 调用的网络延迟和成本，磁盘 I/O 可忽略；且缓存命中可节省数秒的 API 调用时间

## Migration Plan

1. 实现 `src/cache.py` 缓存模块
2. 修改 `LLMClient.generate()` 集成缓存层（向后兼容）
3. 添加 CLI 命令 `harness cache clear` 和 `harness cache stats`
4. 更新配置文件结构，添加 `cache.*` 配置项
5. 单元测试覆盖缓存逻辑
6. 文档更新：说明缓存机制和配置选项

**Rollback 策略**：
- 配置 `cache.enabled=false` 即可禁用缓存，回退到直接 API 调用
- 删除 `.cache/llm_responses/` 目录清空所有缓存

## Open Questions

无
