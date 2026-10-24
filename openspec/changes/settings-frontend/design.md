# Design: settings-frontend

> 范围：#167 真实契约缺口（四簇），范围对齐见 issue #167 留言（2026-10-24）。基线 e68f420。
>
> 流程确认（2026-10-24）：预计 16–18 文件超 tweak 提示阈值；四簇各自自包含、全部只消费既有后端端点、无后端改动，与此前四步（#166 两簇/#225/#163，用户均确认继续 tweak）同构，按既定先例单 tweak 推进。若单 PR 体量被维护者反馈过大，拆分点在簇边界（A+D / B+C）。

## 契约盘点（upstream/main e68f420，侦察已逐行核对）

- **监控（admin，api/routes/monitoring.py）**：`/system/status`（uptime/task_count/async_task_count + health{database/redis/workers/sandbox} + resources{cpu/memory/disk/file_storage} + workers + queue_metrics + containers + evaluation_capability）；`/system/resources`；`/metrics/api-stats?window_seconds=1..86400`（request_count/errors/error_rate/avg_response_time_ms/p95_response_time_ms/requests_per_second + by_route）；`/metrics/llm-stats[?window_seconds]`（total/successful/failed/success_rate/avg_latency_ms）；`/metrics/cache-stats`（跨 worker 命中/未命中/容量）；`/system/health?include_sandbox`；`/logs?level&start&end&search&limit&offset`（admin）；`/config/sandbox|strategies|providers`（只读，admin）。
- **预算/预警（owner，api/routes/costs.py）**：budgets GET/POST/PATCH + `/budgets/usage`（global_cap_usd、difficulty_caps{easy,medium,hard}、action: pause|downgrade）；alerts GET/POST/PATCH/{id} DELETE + `/alerts/history`（name、threshold_pct 1–100、channel: slack|webhook|smtp|log、target、enabled）——**AlertEvent 无写入方，history 恒空，文案注明**。
- **定价（owner，costs.py）**：`GET /pricing`（builtin+custom_file+override 三源合并）、`GET /pricing/{model_id}/history`、`POST /pricing/{model_id}`（追加式，最新生效；无编辑/删除）。
- **前端现状**：SystemPage 116 行只解析 3 字段；Profile/ApiKeys 已完整不动；routes.tsx settingsPages 仅 3 条目。

## 关键决策

1. **零后端改动**：只消费既有端点；不新增 monitoring 端点（#157 进行中）；不碰 quotas UI（#262 在改）。
2. **数据层四簇分目录**：monitoring/budgets/pricing/systemlogs 各自 client+types（严格解析白名单，同五簇先例）；session 复用既有 Provider 模式——监控簇 admin 域挂 SystemPage 局部（不新增全局 Provider，admin 页面自建实例），budgets/pricing 挂 AppLayout 两个新 Provider。
3. **轮询**：SystemPage 30s 间隔自动刷新（Switch 可关，默认开；页面隐藏时暂停——visibilitychange）；其余页面手动刷新。快照派生模式（同 useTaskProgress 先例），effect 内零同步 setState。
4. **角色**：/settings/logs 与监控面板 admin（RequireRole 既有机制 + 后端 administrator 门禁双保险）；budgets/pricing 全员。
5. **时间窗口**：api-stats 与 llm-stats 的 window_seconds 提供预设 Select（60/300/3600/86400，默认 3600），窗口变化触发重取。
6. **预算动作语义**：pause（超限暂停）与 downgrade（降级模型）单选展示说明文案；difficulty_caps 三档输入非负浮点；usage 展示已用/上限与占比。
7. **定价追加表单**：model_id 必填 + input/output 每百万 token 非负价；提交后刷新目录与历史；「追加式、最新覆盖」语义在 UI 说明。
8. **测试**：四簇 client 严格解析测试（真实形状夹具 + 拒绝路径）+ budgets/pricing 表单校验测试；verify-settings.mjs 新增（monitor/budgets/pricing/logs 场景，浏览器 fixture 层）。

## 风险与回退

- #157 后续可能再改 monitoring 响应形状——严格解析会显式报错（预期行为）；本 PR 不依赖其未落地部分。
- #262 若给 budgets/usage 加字段——增量字段解析器不拒（仅白名单读取所需字段），无冲突。
- 回退：还原 SystemPage + 删三新目录 + 还原路由/glob 两处增量。
