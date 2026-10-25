# Proposal: settings-frontend（issue #167：设置与系统管理页，真实契约缺口）

## Why

#167 的验收面在 main 上绝大部分未实现：SystemPage 只渲染 `/system/status` 的 3 个数字（health/resources/workers/queue/containers 全部丢弃），预算/预警/定价/日志/配置查询端点后端全有而前端零消费。缺口核实与范围对齐见 issue #167 留言（2026-10-24）；后端不支持项不做假入口。

## What Changes

四个自包含小簇，全部**只消费既有后端端点、零后端改动**（避免与 #157 相撞）：

- **簇 A：SystemPage 监控面板增强**（admin）：新增 `frontend/src/monitoring/` 数据层（严格解析：/system/status 全量、/system/resources、/metrics/api-stats（可配窗口）、/metrics/llm-stats（窗口）、/metrics/cache-stats、/system/health）；页面按分区渲染——健康卡片（DB/Redis/Workers/沙箱）、资源（CPU/内存/磁盘）、队列（pending/reserved）、任务计数、API 统计（QPS/平均/P95/错误率）、LLM 统计、跨 worker 缓存命中；手动刷新 + 30s 自动轮询（可关）。
- **簇 B：预算与预警页**（owner）：`frontend/src/budgets/` 数据层（budgets CRUD + usage、alerts CRUD）；`/settings/budgets` 新页——预算编辑（global_cap_usd、按难度三档、pause/downgrade 动作）+ 使用量展示 + 预警规则列表（threshold_pct/channel/enabled）；文案注明**通知投递后端未实现**（channel 仅存储）。
- **簇 C：定价管理页**（owner）：`frontend/src/pricing/` 数据层（三源合并目录、按模型版本历史、追加式自定义定价）；`/settings/pricing` 新页——目录表（builtin/custom_file/override 标注）、模型历史抽屉、追加自定义定价表单。
- **簇 D：admin 日志查看器 + 配置展示**：`frontend/src/systemlogs/` 数据层（/logs 级别/时间范围/搜索/分页）；`/settings/logs` 新页（admin）；SystemPage 增「沙箱/策略/提供商」只读 Tab（/config/sandbox、/config/strategies、/config/providers）。

路由：settingsPages 追加 `/settings/budgets`、`/settings/pricing`（全员）、`/settings/logs`（admin）；package.json glob 追加三个新目录；verify-settings.mjs 新场景。

**明确不做（后端不支持，issue 留言已声明）**：系统配置写（LLM 默认/沙箱写/缓存开关清空/worker 数）、通知投递、用户管理、头像、server 侧偏好、LLM 按提供商分组、实时日志流、admin 日志下载、反馈表单、帮助页动态文档（config 门禁）。

## Capabilities

### New Capabilities

- `frontend/system-monitoring`：admin 监控面板（健康/资源/队列/任务/API/LLM/缓存统计的只读聚合展示与轮询）。
- `frontend/budget-alerts`：预算与预警规则的用户侧管理。
- `frontend/pricing-management`：模型定价目录、历史与自定义追加。
- `frontend/system-logs`：admin 日志查询（级别/时间/搜索/分页）。

## Impact

- 新文件约 16 个，修改 3 个（SystemPage 重写、routes.tsx、package.json）。
- 不新增依赖；监控图表面使用既有表格/Descriptions（数值+进度条），不引实时图表库。
- SystemPage 近乎无历史（1 提交）、Settings 目录无人占用；#262 改 quotas 字段——预算簇 UI 不碰 quotas，规避。
