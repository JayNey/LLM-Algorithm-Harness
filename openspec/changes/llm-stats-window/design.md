## Context
现有 MonitorStore 原子累计真实 SDK 尝试；API 与 worker 共用认证数据库。累计数据没有时间分布，无法回填历史窗口。

## Decisions
- 在现有数据库新增 api_monitor_llm_calls，仅保存 id、timestamp、succeeded、duration_ms。与累计计数在同一事务写入，避免两个口径分叉。
- llm_stats(window_seconds=None) 保持旧调用语义。指定窗口时聚合 [now-window_seconds, now] 内记录，成功率=成功/全部，平均耗时包含失败尝试。完成时间恰好落在两端均计入，未来记录不计。
- 记录表使用现有 retention_seconds/max_rows，独立持久化采集起点和删除水位，查询在同一事务清理并聚合。不完整窗口的主指标为 null，retained_sample 提供已保留样本，window_complete=false；完整空窗口计数为零、比例和均值为 null。
- 启动时初始化窗口采集起点，升级前累计值不回填。用量登记与密钥验证仍为累计独立字段。现有无参数接口、performance 的累计行为保持兼容。

## Risks / Trade-offs
每次 SDK 尝试增加一条数值记录和有界清理；保留限制会使较大窗口不可完整查询，但响应明确说明。采集仍为 best-effort，完整仅指已配置采集和记录保留覆盖，不保证无遗漏。旧版本 worker 需统一升级，否则其写入没有窗口记录。
