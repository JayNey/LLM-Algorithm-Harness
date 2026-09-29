## 1. 缓存模块核心实现

- [x] 1.1 创建 `src/cache.py` 并实现 `CacheKey` 类，生成基于 SHA256 的缓存键，验证相同参数生成相同键、不同参数生成不同键
- [x] 1.2 实现 `LLMResponseCache` 类的 `get()` 方法，从磁盘读取缓存文件并解析为 `LLMResponse` 对象，验证读取现有缓存文件返回正确响应
- [x] 1.3 实现 `LLMResponseCache` 类的 `set()` 方法，将 `LLMResponse` 序列化为 JSON 并原子写入磁盘，验证写入后文件存在且内容正确
- [x] 1.4 实现 TTL 检查逻辑，在 `get()` 中判断缓存是否过期，验证未过期缓存返回、过期缓存返回 None
- [x] 1.5 实现 LRU 淘汰机制，维护访问记录文件 `.cache/llm_responses/.access_log.json`，验证访问时更新记录
- [x] 1.6 实现磁盘空间检查和淘汰逻辑，当缓存超过 `max_size_mb` 时删除最久未访问的条目，验证超限时触发淘汰

## 2. 配置模型扩展

- [x] 2.1 在 `src/models.py` 中添加 `CacheConfig` 模型，包含 `enabled`、`backend`、`ttl_days`、`max_size_mb` 字段，验证配置解析正确
- [x] 2.2 在 `LLMConfig` 或主配置模型中集成 `CacheConfig`，验证配置文件加载时 `cache.*` 字段被正确解析

## 3. LLMClient 集成

- [x] 3.1 在 `LLMClient.__init__()` 中初始化 `LLMResponseCache` 实例，读取配置决定是否启用，验证客户端初始化后缓存实例可用
- [x] 3.2 修改 `LLMClient.generate()` 方法，在调用 provider 前检查缓存，命中时直接返回，验证缓存命中时不调用 API
- [x] 3.3 在 `LLMClient.generate()` 中，API 调用成功后将响应写入缓存，验证新响应被正确缓存
- [x] 3.4 为 `LLMClient.generate()` 添加可选参数 `problem_id` 和 `strategy_name`，用于缓存键生成，验证传入这些参数时缓存键包含它们
- [x] 3.5 确保缓存禁用时（`cache.enabled=false`）跳过所有缓存逻辑，验证禁用配置下每次都调用 API

## 4. CLI 命令实现

- [x] 4.1 在 CLI 模块中添加 `cache` 子命令组，验证 `harness cache --help` 显示可用命令
- [x] 4.2 实现 `harness cache clear` 命令，删除所有缓存文件，验证执行后 `.cache/llm_responses/` 目录为空
- [x] 4.3 实现 `harness cache clear --model <model_id>` 命令，仅删除指定模型的缓存，验证只删除匹配模型的文件
- [x] 4.4 实现 `harness cache stats` 命令，显示缓存命中率、总条目数、磁盘占用和节省的 API 调用次数，验证输出包含所有统计信息

## 5. 单元测试

- [x] 5.1 为 `CacheKey` 编写单元测试，覆盖相同参数、不同参数、缺失可选参数的场景，验证所有测试通过
- [x] 5.2 为 `LLMResponseCache.get()` 和 `set()` 编写单元测试，覆盖缓存命中、未命中、过期、并发写入场景，验证所有测试通过
- [x] 5.3 为 LRU 淘汰机制编写单元测试，模拟磁盘空间超限场景，验证正确删除最久未访问的条目
- [x] 5.4 为 `LLMClient.generate()` 缓存集成编写单元测试，mock LLM API 调用，验证缓存命中时不调用 API、未命中时调用并缓存
- [x] 5.5 为 CLI 命令编写单元测试，验证 `cache clear` 和 `cache stats` 的行为正确

## 6. 集成测试与文档

- [x] 6.1 端到端测试：运行完整实验流程，验证相同 prompt 第二次运行时使用缓存，通过日志或统计确认零 API 调用
- [x] 6.2 更新项目文档或 README，说明缓存机制、配置选项和 CLI 命令使用方法，验证文档清晰完整
