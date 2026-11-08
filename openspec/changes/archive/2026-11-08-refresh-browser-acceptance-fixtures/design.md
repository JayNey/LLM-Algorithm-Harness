## Context

浏览器验收在真实 SPA 上执行，Playwright 拦截其 API 请求。登录后的共享外壳会读取持久化通知，旧脚本需要声明相应路由。

## Decisions

- 对精确匹配的 `GET /notifications` 返回空页，包含 `items`、`next_cursor`、`unread_count` 和 `server_time`。其余请求继续经过原有匹配与未知请求断言。
- 根据页面现有的可访问名称和请求契约更新题库、设置和其他失效的 fixture，并保留失败恢复及权限断言。
- 在 QA 文档中标明本组 fixture 的 Vite 启动模式、地址和执行命令，并区分生产构建的直接加载检查。

## Scope

用户确认使用独立分支，并在预计超过文件数提示阈值的情况下继续 tweak。改动集中于同一组前端验收脚本及文档。
