## 实现
认证库创建用户/周期类型/UTC 起点唯一的聚合表，同一事务原子递增日与月。查询当前桶，无定时清零，历史不回填。
凭证解析以 Pydantic 私有回调绑定服务端用户和 AuthStore，禁止序列化或外部输入。真实生成 SDK 尝试完成后回调独立执行，计时失效仍能计数，持久化失败不影响模型结果；重试预算扣除 SDK 返回后的计量等待，保留请求及退避耗时。缓存、列表、验证、无用户 CLI 排除。
quotas 原字段返回 status=metered、limit=null、整数 used、timezone、period_start、resets_at、scope、collection_mode；UTC 完成时间，周期左闭右开。best-effort 失败可能漏计。
## 决策
用户选择独立分支、继续 tweak、真实 LLM 尝试及建议 UTC。预计包含超过六个文件，属于同一计量链路。
