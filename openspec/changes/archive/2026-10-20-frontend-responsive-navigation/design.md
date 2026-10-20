## Context

现有栈为 React 18、TypeScript、Ant Design、Tailwind、React Router 与 Zustand。视觉依据是 2026-10-20 独立原型的 DESIGN.md、VARIANTS.md、INTEGRATION.md、Frontier SVG 与六套深浅 token；本 change 将规范和资产保存在仓库中，避免依赖临时目录。

## Goals / Non-Goals

实现统一外壳及足以验证布局的 Mock 业务；保留 BrowserRouter、RequireSession、RoleAccess、RequireRole、Cookie/CSRF 客户端和已有账号页面。业务接口、实时通知、Mock 身份切换、数据库及 API 变更不在本期范围。

## Decisions

- 扩展 store/ui.ts，风格、每风格主题偏好和侧栏折叠持久化；主题可选 light/dark/system，系统监听清理。存储不可用时退化为内存，历史 sessionStorage 配色兼容读取。
- data-design/data-theme、Tailwind dark class 与 AntD token 使用同一来源；外壳与 Outlet 不按风格设置 key。共享业务状态不归属于外观组件，切换不刷新、不重挂载。
- 共享 routes.tsx 导航信息，分组和图标由路由元数据派生；Monitoring 继续指向 /settings/system 并遵循 admin 策略。保留既有未知路径回到仪表盘的约定。
- 布局组件按 shell controls、通知、业务示例、公共状态拆分。桌面常驻侧栏，<1024px 抽屉，<768px 四项底栏；320px 无页面横向溢出，触控目标至少 44px。
- 通知为会话内 Mock store，登录身份变化时隔离；分类、未读、全部已读、清空及白名单站内跳转。真实登出调用既有 logout。
- 业务数据来自原型的四条记录，指标计算得出；三种首屏与相同任务列表共享数据。筛选、详情、创建表单和重试仅作本地交互，显式标注 Mock。
- 页面级异常边界、骨架、空数据和错误重试配合 AntD message，保持键盘焦点、跳至正文、抽屉 Esc、减少动态效果。

## Risks / Trade-offs

- 原型 CSS 可能覆盖现有设置表单 → 外壳样式限定选择器，保留原页面功能，运行账号与权限回归。
- 风格切换可能卸载表单或重置通知 → 外观切换只更新 store，浏览器检查输入/筛选/已读状态保持。
- Mock 被误认为真实结果 → 固定 Mock 提示，不发送业务请求；账号、权限和登出维持真实行为。
- Safari/Firefox 与真实设备不可在本会话穷尽 → 报告浏览器和尺寸的实际验证范围。

## Migration Plan

独立分支实施，提交前测试、lint、格式、类型和构建；完整规格一致性验证和桌面/手机检查后交付。回滚该分支的实现提交即可恢复现有外壳，无数据迁移。

## Workflow Decision

用户于2026-10-20明确选择：“继续 comet-tweak：沿用现有设计，完成实现与完整验证”。接受组件拆分超过6文件的提示阈值；保持单一 change、现有架构和已批准的设计，不升级 full。
