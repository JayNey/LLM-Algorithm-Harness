## Why

[#418](https://github.com/JayNey/LLM-Algorithm-Harness/issues/418) 的通知抽屉在窗口聚焦和轮询时退回第一页。后台请求还可能让已经成功的批量操作回读失效，导致未读徽章显示旧值。

## What Changes

- 同一账号和分类内对账已加载的通知、后续游标和全局未读数。
- 保留仍可用的已加载通知及其控件，识别新通知和服务端移除的条目。
- 在筛选切换、分页和写操作交错时保持响应归属，覆盖失效游标恢复。

## Capabilities

### New Capabilities

### Modified Capabilities

- `frontend/app-shell` 补充通知分页刷新、并发回读和隔离场景。

## Impact

前端通知 store、抽屉刷新入口和通知回归测试。继续使用既有通知接口和认证会话。
