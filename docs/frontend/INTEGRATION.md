# Issue #168 · 当前接入结构

本文描述已经接入仓库的实现，后端业务适配仍留待后续工作。当前模块均位于 `frontend/`，不依赖历史原型目录或原型 HTML 入口。

## 模块职责

- `src/layouts/AppLayout.tsx`：共享工作台、ConfigProvider、AntD App、Outlet、抽屉、用户菜单、真实登出与公共 Mock 操作。
- `src/layouts/components/Navigation.tsx`：分组侧栏、抽屉导航、四项手机导航、面包屑、风格和主题选择。
- `src/layouts/components/NotificationCenter.tsx` 与 `src/store/notifications.ts`：session marker 隔离的本地通知、分类、已读和清空。
- `src/store/ui.ts`：三种风格、各风格主题偏好、解析后的浅深模式、系统偏好与持久化侧栏状态。
- `src/layouts/appearance.ts` 与 `src/layouts/shell.css`：AntD 与外壳配色、排版、响应式与动效权威。
- `src/mock/BusinessPage.tsx`、`DesignFocus.tsx`、`RunList.tsx`、`MockActions.tsx`、`data.ts`：示例业务数据和本地行为。
- `src/components/common/Feedback.tsx`：公共加载、空、模拟错误、React 异常边界与 Toast 示例。
- `src/routes.tsx`：路径、标签、分组、图标和角色元数据。`src/App.tsx` 继续使用 BrowserRouter、RequireSession、RoleAccess 与 RequireRole。

## 路由与权限

“评估工作台”包括 `/` 仪表盘、`/problems` 题目库、`/evaluations` 评估任务；“分析与对比”包括 `/results` 评估结果、`/experiments` 实验、`/benchmarks` 基准测试。“系统”包括 `/help` 帮助文档、`/settings` 设置，以及设置子路由 `/settings/system` 系统状态。

`/settings/system` 的 `allowedRoles` 为 `['admin']`；侧栏和设置页通过现有角色上下文过滤入口，路由本身继续由 RequireRole 守卫。`/settings/profile` 与 `/settings/api-keys` 为个人资料和 API 密钥入口，不加入主导航分组。`/login` 与 `/register` 继续由 AuthLayout 承载。

角色来自既有真实身份读取链路；当前实现没有 Mock 角色切换。用户菜单调用原有 `logout()`，最终跳转登录页；这里没有“退出预览”或伪登录替代。前端可见性与守卫不能替代后端授权。

## 状态边界

风格改变不会通过 `key={appearanceVariant}` 重挂载外壳，不修改 URL 或刷新页面。同一路由中仍挂载的搜索、筛选、详情、表单及通知状态按各自组件生命周期保留；跨路由持久化业务状态没有另行承诺。

UI 偏好采用 `llm-harness-ui` 浏览器存储，且白名单验证值；凭证不加入 UI store。通知使用 session marker 对应的内存 store；认证会话变化重新建种子数据，刷新同样恢复。通知的“本次会话内保存”指本次挂载运行中的内存状态，不是 sessionStorage。

## 后续真实服务适配

认证、Cookie/CSRF、刷新协调、用户资料、密码与 API 密钥继续复用已有实现。业务页面当前不调用真实评估、结果、实验、基准、成本或监控服务；创建、导入和恢复只做明确标注的本地演示。

接入真实业务时应先核对现有 API 的实体、分页、筛选、进度、费用和结果统计口径，再替换 `src/mock/` 的数据与动作。任务未完成前不可把局部结果当成最终准确率，基线对比须保持数据集与策略一致。

专用通知收件箱的 API、用户隔离、游标、未读数、已读/归档、去重、TTL 和重连契约仍需确认。预算预警与任务事件不能自动视作用户通知收件箱。当前没有假定 `/notifications` 存在，也没有把已安装的 socket.io-client 当作任意 WebSocket 后端的兼容保证。

后续服务回归需要覆盖真实 401/403、CSRF 刷新、角色重读、不同账号切换、资源归属、断线重连和请求失败恢复。这些不由本地外壳验证替代。

## 本地验证入口

在 `frontend/` 下运行 `npm test`、`npm run lint` 与 `npm run build`。浏览器脚本为 `frontend/scripts/verify-shell.mjs`，用法及验证范围见 [QA.md](QA.md)。
