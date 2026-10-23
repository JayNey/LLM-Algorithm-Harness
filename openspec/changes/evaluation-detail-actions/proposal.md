## Why

Issue #224 要求将评估回执页变为可直接访问、刷新的真实详情页；当前页面依赖内存回执，无法核对服务端任务与操作能力。

## What Changes

- 展示 GET 返回的模型、策略、状态、预算、成本、进度和失败原因。
- 根据 can_start/can_cancel 提供真实操作，与创建协调器互斥；操作响应后重新读取快照，失败保留 ID 和数据。
- 补齐 detail 浏览器 fixture、创建重试与取消竞争回归。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/app-shell`: 补充已注册评估详情路由的数据加载与操作行为。

## Impact

仅前端评估页面、协调器和验收脚本；复用 Cookie/CSRF 客户端，不改后端、API 或认证协议。基线 fa60243（origin/main），前置 #218/#220/#221/#222/#223 已关闭且代码已在 main。用户已确认超过六文件提示阈值仍继续 tweak，使用新分支。
