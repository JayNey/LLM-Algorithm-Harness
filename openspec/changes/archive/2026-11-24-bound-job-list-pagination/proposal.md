# 修复业务列表的数据库分页边界

## Why

Issue #515 指出，评估、实验和 A/B 列表先加载所有者的全部历史再在 Python 中切片，页大小无法限制实体加载数量；实验与 A/B 配置还包含完整冻结题库。历史增长会放大每次列表和仪表盘查询的内存及传输开销。

## What Changes

- 三处列表使用数据库 LIMIT/OFFSET，仅构造当前页实体；匹配总数通过独立 COUNT 查询获得。
- 保持所有者与可选状态过滤、created_at/id 升序稳定排序、现有分页响应及任务关联语义。
- 列表仅查询响应所需字段；实验与 A/B 在数据库查询中去除冻结快照的 problems 和 owner_id，保留公开配置及快照摘要，兼容 SQLite 与 PostgreSQL。
- 增加查询边界回归，覆盖历史增长、状态/归属过滤、同时间排序、空页以及快照裁剪。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/evaluation-execution`：明确评估列表的数据库分页与必要字段读取边界。
- `api/experiment-management`：明确实验与 A/B 列表的数据库分页和公开配置投影边界。

## Impact

预计修改三个 service、共享数据集查询辅助代码和一个测试文件，共五个交付文件；另有本 change 的 OpenSpec 产物。无需数据库迁移、前端调整或新增依赖。范围限于列表读取，不改变创建、详情和 worker 使用的完整持久化快照。

采用 tweak 预设：当前目录与 main 分支，direct 实施、direct 检查、review off；完成针对性回归及规格一致性验证。
