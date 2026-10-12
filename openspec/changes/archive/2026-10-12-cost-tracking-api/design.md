# 设计说明：cost-tracking-api

## 决策

1. **成本数据只读聚合，不重复记账**：任务的 `spent_usd`/`cost_usd` 已由 #151/#156 的表维护；成本端点跨 `evaluations`/`experiments`/`benchmark_runs`/`ab_tests` 四表按 id 解析与聚合，不新增记账写入路径。按难度使用量为比例估计（任务花费均摊到 problems 表可匹配的难度上），口径在响应 `basis` 字段注明。
2. **每用户一份预算配置**（`budgets.user_id` 唯一）：全局上限 + `difficulty_caps` JSON + `action`（pause/downgrade，与 HarnessConfig 的预算行为词汇一致）。upsert 语义，避免多行歧义。
3. **预警规则与触发历史分离**：`alert_rules` 存配置（threshold_pct、channel、target），`alert_events` 存触发事实。运行期阈值评估与投递（沿用 CostAlertManager 的通道机制）随 #149 队列接线，本 change 只交付规则/历史的配置面与数据面。
4. **定价覆盖追加式版本化**：`pricing_overrides` 只追加不更新（同 model 多行，latest 生效），满足"定价历史版本用于历史成本追溯"；读取端合并 PricingManager 内置/自定义文件与覆盖行，覆盖优先。webhook/邮件目标按敏感信息处理：响应中脱敏（保留协议与主机），加密存储延后至统一的 secrets 任务。
5. **优化建议复用 #176 模式**：`build_advisory` 需要 comparison 形状；从用户 benchmark_runs 按 model 聚合（accuracy 均值、成本合计、solved 计数）与 evaluations（completed/problem_count 代理）合成组合行，注明为估计。

## 非目标

- 运行期预警投递与预算暂停的执行接线（#149 任务队列）
- runner 侧读取数据库定价覆盖（#159）
- 通道凭据加密存储（延后至统一 secrets 处理）
