## Context

现有 BenchmarkRun 已保存完整生命周期、指标和用户 ID；AsyncTask 通过 task_type/entity_id/user_id 关联，无需迁移。单次运行视图尚未带任务 ID，学习曲线只校验套件归属。

## Goals / Non-Goals

为 issue #309 提供可分页、可导航且隔离用户的读取契约；不修改执行流程、任务状态机、数据库结构或前端。

## Decisions

- 新列表使用 `limit=20`（1..100）、`offset=0`（非负）及可选单一 `status`，状态明确为 pending/running/paused/completed/failed/cancelled；无效参数遵循现有 400 错误格式。
- 校验套件所有者后，以 suite_id 和 user_id 查询运行，先过滤再 COUNT；数据库使用 `created_at DESC, id DESC` 排序和 limit/offset。固定数据集下分页顺序稳定，不承诺并发新增下的快照分页。
- 复用运行视图，并增加 task_id、started_at、completed_at；列表响应模型显式描述字段。详情同样返回安全任务关联，启动响应保留已有字段。
- 任务关联批量查询当前页的 benchmark 任务，要求 user_id 相同；若出现多条历史关联，确定性选取 `created_at DESC, id DESC` 的最新记录。无关联返回 null，不暴露其他任务类型或用户的 ID。
- 详情同时校验运行和套件所有者；曲线按所有者过滤运行，保留 completed-only、指标和趋势算法，增加 run_id。
- 在现有 HTTP 测试文件复用真实认证及数据库 fixture，仅外部 Celery 发布继续使用现有替身。

## Risks / Trade-offs

- offset 分页在并发新增时可能移动边界：文档明确固定数据集的稳定排序语义。
- 老记录缺少任务/时间/指标：按真实值输出 null，不推算或用零替代。
- 新增 public API 已由用户选择 A2 确认继续 tweak；源码/测试/文档预计 5 个文件。
