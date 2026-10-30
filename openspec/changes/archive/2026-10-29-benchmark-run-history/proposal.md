## Why

Issue #309：刷新页面后无法枚举套件运行，学习曲线缺少可跳转的运行标识。后端需要提供按用户隔离的历史分页契约，供后续 F7 使用。

## What Changes

- 新增 `GET /api/v1/benchmarks/suites/{suite_id}/runs`，提供状态过滤、稳定排序、准确总数和分页信息。
- 历史记录包含运行、套件和同所有者基准任务标识，以及已有指标和生命周期时间；未知值保持 null。
- 学习曲线仅统计当前用户已完成的运行，并兼容增加 `run_id`。
- 补充响应模型、API 文档及 HTTP 契约测试，不改动前端页面。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/experiment-management`：扩充基准运行历史查询及学习曲线的导航与归属约束。

## Impact

涉及基准路由、BenchmarkService、接口模型、HTTP 测试及 API 文档；无需数据库迁移或新增依赖。用户选择 A2，确认新增 public API 仍采用 tweak，并使用独立分支。
