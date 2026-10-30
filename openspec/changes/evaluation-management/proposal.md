## Why
Issue #320 要求评估详情形成暂停、恢复、预算更新和删除闭环，可靠区分评估 ID 与 AsyncTask ID。
## What Changes
- 扩展响应为服务端操作能力与当前关联任务 ID；客户端接入现有端点。
- 增加确认、预算校验、互斥、失败对账及路由/会话隔离，保持启动取消行为。
- 补充中英文、键盘、移动及真实 HTTP 验证。
## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `frontend/app-shell`: 评估管理操作闭环。
## Impact
评估响应投影、客户端、详情页面、翻译和测试；无数据库迁移。用户确认继续 tweak，已选择新分支，允许所需跨模块集成及超过六文件的最小范围。
