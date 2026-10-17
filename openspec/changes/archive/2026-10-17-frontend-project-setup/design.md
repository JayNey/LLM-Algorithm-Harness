## Context

见 `proposal.md`。后端 API 前缀是 `/api/v1`，默认监听 `http://localhost:8000`。进度推送是原生 WebSocket `GET /api/v1/ws/progress`，不是 Socket.IO。仓库根目录还没有 `frontend/`，`.gitignore` 也未忽略 `node_modules`。

## Goals / Non-Goals

**Goals:**

- 用 issue #160 指定的 React 技术栈搭好可开发、可检查、可构建的 `frontend/`。
- 环境变量和开发代理对齐现有后端，而不是对齐 issue 草稿里的 `/ws` 路径。

**Non-Goals:**

- 不实现仪表盘、题目、评估、结果、实验、设置的业务界面。
- 不连接真实 WebSocket 会话，不调用后端业务接口。
- 不改后端、数据库或既有 spec。

## Decisions

1. **React 18 + TypeScript + Vite。** issue 的依赖清单和目录都是这套。安装时使用与 React 18 兼容的当前稳定版本，不锁死草稿里的旧补丁号。
2. **UI 用 Ant Design，样式用 Tailwind。** 组件库按草稿 `package.json` 取 Ant Design；深色模式用 Tailwind 的 `class` 策略，由外壳切换 `<html>` 的 `dark` class。
3. **状态用 Zustand，路由用 React Router，请求用 Axios。** 本变更只建立入口和占位页，不写入业务 store。
4. **表格用 TanStack Table，图表用 ECharts，编辑器用 Monaco，表单用 React Hook Form，日期用 dayjs。** 依赖按 issue 安装；AG-Grid 不引入，避免双表格库和许可证。本变更不渲染这些库的业务实例。
5. **安装 `socket.io-client`，但不把它当作进度通道。** issue 要求该依赖；现有后端是原生 WebSocket。`VITE_WS_URL` 指向 `ws://localhost:8000/api/v1/ws/progress`。
6. **环境文件区分 development、test、production。** 必填变量为 `VITE_API_BASE_URL`、`VITE_WS_URL`、`VITE_APP_NAME`；功能开关使用 `VITE_FEATURE_FLAGS`。读取模块在缺必填项时抛出带变量名的错误。
7. **开发服务器端口 3000，代理 `/api` 到 `http://localhost:8000`，并开启 WebSocket 代理。** 别名 `@` 指向 `frontend/src`。六个页面用 `React.lazy` 分割。
8. **husky 钩子放在 `frontend/.husky`，从仓库根安装，只对 `frontend/` 暂存文件运行 lint-staged。** 不改 Python 工具链。

## Risks / Trade-offs

- [根目录 `.gitignore` 已忽略任意 `dist/` 和 `lib/`] → 前端产物沿用 `dist/`；源码不使用 `src/lib`。
- [子目录 husky 容易装到错误的 Git 根] → `prepare` 脚本显式指向仓库根和 `frontend/.husky`。
- [Socket.IO 客户端与原生 WebSocket 不兼容] → 只安装依赖，连接留到后续进度页面。
- [依赖体积大] → 页面懒加载；Monaco 不在首屏同步导入。

## Migration Plan

新增 `frontend/` 和一条 gitignore 规则。回滚时删除该目录并还原 gitignore，无数据迁移。

## Open Questions

无。issue 已给定技术栈；与后端不一致的 WebSocket 路径按现有 API 纠正。

## 继续 tweak 的确认

用户在升级判定中选择继续 tweak。命中的信号是新增 capability `frontend/app-shell`，以及脚手架文件数会超过 6。用户确认范围仍是 issue #160 这一个 change，不升级完整 Classic。工作区隔离选择为新建分支 `tweak/20261017/frontend-project-setup`。
