## 实现
评估解析上下文时使用其 session_factory 读取 PricingOverride，按 created_at 排序后每模型保留最新版本；保存为独立的 PricingInfo 快照。预建策略 runtime 后向各 LLMClient 的 PricingManager 注入快照。数据库精确覆盖优先于文件精确/前缀与内置价格，不将 Web 覆盖推广为其他模型的前缀价格。

缓存命中且当前模型存在 Web 覆盖时，复制响应并以缓存 token 用量与当前快照重建定价元数据，缺失用量继续保留未知成本。非覆盖模型沿用既有行为。历史结果不重算，在途评估不热更新价格；恢复时重新加载。既有 _estimate_cost、spent_usd 和单元边界预算控制消费统一的 trace 成本。

## 验证
以真实 SQLite 覆盖版本和模拟 provider/sandbox 验证最新版本、优先级、零价、未知用量、缓存、恢复刷新、策略成本与预算暂停。
