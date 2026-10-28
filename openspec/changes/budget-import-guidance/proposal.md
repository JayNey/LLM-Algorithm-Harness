## Why

预算页仍告知用户通知渠道只会保存规则，但 Web 评估 worker 已能实际投递 Slack、Webhook 和 SMTP 邮件；导入暂停提示也承诺可在不存在的通用任务列表中恢复或取消。两处说明会让用户误判已配置但未触发的投递，也可能重复提交仍处于暂停状态的导入。

## What Changes

- 更新预算预警提示，准确说明触发范围、用户预算与启用规则条件、Slack/Webhook 目标及 SMTP worker 配置，并说明保存规则不代表已经投递。
- 明确站内通知仍为 Mock，预算预警由评估 worker 的实际执行边界检查，不承诺后台轮询或覆盖所有任务类型。
- 更新导入暂停说明：题库导入当前没有页面级恢复/取消操作；提示用户不要盲目重复提交，持续暂停时联系管理员并提供任务标识。
- 检查相邻活跃界面的同类过期文案，并同步中英文资源。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/budget-alerts`：将渠道未实现的说明改为真实的投递条件、配置和边界。
- `frontend/problems-management`：准确说明暂停的题库导入目前没有页面级恢复或取消操作。

## Impact

- 影响 `frontend/src/pages/Settings/BudgetsPage.tsx`、`frontend/src/pages/Problems/ProblemsPage.tsx` 及中英文资源。
- 不新增后端接口，不实现通用任务管理、非评估任务恢复或站内通知。
