## Why

#223 的评估列表仍导出 Mock 页面，无法核对本人真实创建的任务。#220–#222 所需实现已在最新 main，需接入现有认证客户端并保留工作台外观。

## What Changes

- 以当前会话客户端加载本人评估列表，展示真实 ID、模型、策略、状态、进度与费用。
- 用 URL 保存 status/limit/offset，提供分页、加载、空集、错误重试和超页恢复。
- 用取消和会话/请求代际隔离迟到响应。扩展 list 浏览器 fixture 与查询单测，完成独立审查及公开验证报告。

## Capabilities

### New Capabilities
- `frontend/evaluation-list`：真实评估列表、URL 筛选分页及异步隔离。

### Modified Capabilities
无。保留既有 Cookie/CSRF、三风格、主题、移动导航及创建会话。

## Impact

仅前端列表、局部样式、浏览器 fixture 和相关测试/文档。不新增 API，不改共享路由或客户端契约。#226/#229/#232 等待各自前置；本轮不将 fixture 当真实端到端。
