## Why

现有 React 工作台仅提供中文界面，英文使用者无法完整理解操作与反馈；语言偏好尚无保存机制。

## What Changes

- 接入 i18next / react-i18next，维护中文与英文翻译资源。
- 覆盖认证页、工作台导航、业务页、表单、反馈、图表和设置中的前端界面文案。
- 登录前后均提供可访问的语言选择器，切换立即生效且不清空表单或改变路由。
- 持久化语言偏好，刷新恢复；同步 Ant Design、dayjs 与 HTML lang。

## Capabilities

### New Capabilities

- `frontend/internationalization`: 中英文资源、实时切换、偏好恢复和安全降级。

### Modified Capabilities

无。

## Impact

限于 frontend 源码、依赖与验证脚本；不修改后端 API、数据库或用户输入/服务端返回的业务内容。用户已于 2026-10-28 明确选择继续 tweak，并创建独立分支；已确认新增 capability 及超过六个文件的范围。
