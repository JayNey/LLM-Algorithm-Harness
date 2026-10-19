# LLM Algorithm Harness 前端

React 18、TypeScript 和 Vite 工程。源码别名 `@` 指向 `src/`。

```bash
cd frontend
npm install
npm run dev
npm run lint
npm run format:check
npm run build
```

开发服务器端口是 3000，并把 `/api` 代理到 `http://localhost:8000`。

## 角色访问控制

普通用户可以访问现有业务页面、个人资料和 API 密钥管理。管理员另可在「设置 → 系统状态」查看当前 API 进程的运行时间和两类任务数量；直接地址为 `/settings/system`。

管理员由部署者在后端 `MONITOR_ADMIN_USER_IDS` 中配置已注册用户的 UUID，配置方法见 [监控指南](../docs/api-monitoring.md)。登录名为 `admin` 不会自动获得管理员权限，也没有前端自助提权入口。更改环境变量后需要重启 API。

前端在登录布局挂载时读取 `GET /api/v1/users/me` 的 `role`，不从浏览器存储或 JWT 读取角色。角色尚未确认、查询失败或未知时不会打开管理员页面；失败后可以重试。后端始终检查管理员权限，403 会触发前端重新读取角色。管理员角色不授予访问其他用户私有资源的权限。

`npm test` 覆盖角色策略、异步请求隔离和实际路由守卫与设置组件的渲染；组件测试直接使用已有 Vite 编译 TSX，不监听端口。
