## 修复任务

- [x] 1. 登录和刷新设置 HttpOnly cookie，登出清除 cookie。无 Authorization 时接受访问令牌 cookie，显式 Bearer 和刷新 JSON 优先。查询参数令牌仍然无效。补充失败回归测试并在修复后转绿。
- [x] 2. 浏览器会话不再保存令牌。请求携带 cookie，刷新不在脚本中附带令牌。更新前端会话测试。
- [x] 3. 更新认证说明，使文档与 cookie 会话一致。
