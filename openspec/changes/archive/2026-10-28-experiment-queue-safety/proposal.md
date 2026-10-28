## Why

修复 #296：实验提交后业务状态仍为 pending，连续或并发请求可以重复入队，删除可留下孤立任务，刷新详情又会丢失排队任务关联。前置 #295 已合并，必须保留取消状态同步行为。

## What Changes

- 在同一数据库事务中串行化实验启动、已有任务检查与删除。
- 详情与列表返回所有者隔离的 task_id；前端据此恢复排队任务、禁止重复启动和直接删除。
- 验证已有 Broker 发布失败处理与 P1 取消同步，不增加数据库表或状态。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/experiment-management`: 原子入队、活动任务删除保护、明确任务关联及发布失败结果。
- `frontend/experiments-management`: 排队任务刷新恢复与对应生命周期操作。

## Impact

涉及实验 service、前端 client/type、详情与列表及回归测试，不改通用队列协议或数据库 schema。用户已选择新分支并明确继续 tweak；此处前后端协调和相应测试文件属于已确认范围。
