## Why

用户授权先恢复 Windows 回归、补 #225 浏览器验收再推进 #226。最新 main d0f275c 已合并 #255 的 SQLite 锁等待修复及 #256 的应用接线，相关 PR CI 全绿；本轮实际 progress fixture 首次运行超时，需先补齐可信验证。

## What Changes

- 保留已合并 SQLite 修复，实测并发和持锁等待回归。
- 修复 progress fixture 的 WebSocket 方向与断言同步/异步传播，保留真实 React、路由、观察器和 HTTP 客户端。
- 实跑 progress/detail/create/list，独立审查，发布脱敏证据和验证层级，确认 #226 的前置状态。

## Capabilities

修改 `frontend/evaluation-observer` 的 React 接线验收场景：已复现403后旧live快照保留详情，补齐权限清理与手动刷新/动作的同一观察器协调。无新API或架构。

## Impact

只涉及浏览器测试脚本、其断言助手回归及文档。共享脚本按 main 基线验证，不重复已合入的后端修复，也不扩展到真实供应商/Redis/Celery/沙箱联调。
