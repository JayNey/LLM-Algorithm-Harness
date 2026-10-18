## Context

本分支基于 `frontend-auth-session`。该 change 已经规定受保护请求带 Bearer、未登录进入登录页，以及一个共享 HTTP 客户端。设置页目前是不请求后端的占位页。`GET/PATCH /api/v1/users/me` 只处理用户名、邮箱和注册时间。密钥列表只返回 `id`、`provider`、`key_name`、`created_at`、`last_used_at`、`usage_count`、`verification_count`、`last_verified_at` 和 `verified`。`created_at` 与 `last_used_at` 是 Unix 秒。验证结果只有 `ok`、`provider` 和通用 `message`。

## Goals / Non-Goals

**Goals:**

- 设置页只负责跳转，资料和密钥各自请求自己的接口
- 改名请求只包含新名称
- 密钥值只在添加时输入一次，之后任何响应和界面都不再出现

**Non-Goals:**

- 不提供替换密钥值的表单，尽管后端 `PATCH` 可以接收新密钥
- 不新增 HTTP 客户端，也不改登录守卫
- 不展示验证次数；规格要求的是验证状态、使用次数和最后使用时间

## Decisions

### 1. 设置页拆成入口和两个子路由

`/settings` 保留为入口，放个人资料和 API 密钥两个链接，不发起请求。`/settings/profile` 和 `/settings/api-keys` 放在既有会话守卫内。时间用已有的 dayjs 从 Unix 秒格式化为本地时间。

备选是在同一个设置页里用标签同时加载资料和密钥。那样设置页本身会请求业务数据，和现有外壳“后端不可用时仍可打开且不请求业务数据”冲突。

### 2. 复用会话 change 的 HTTP 客户端

资料和密钥请求走 `frontend-auth-session` 的客户端，从而自动带认证头和处理过期刷新。表单继续用 react-hook-form。用户名和邮箱规则与注册相同。

备选是再创建一个 axios 实例。那会复制刷新和认证头逻辑。

### 3. 密钥按返回结果在客户端分组

列表请求返回后，按 `provider` 分成 `openai`、`anthropic`、`siliconflow` 三组，空组不渲染卡片。添加表单的密钥框使用密码输入，成功后清空。编辑只提交 `{ "key_name": "..." }`。删除先用确认框，确认后才发 `DELETE`。验证后根据 `ok` 刷新该条的已验证状态，失败时展示接口返回的通用消息。

备选是让后端按提供商分组。当前列表已经是当前用户的扁平元数据，前端分组就够了。

### 4. 用 Node 测试锁住分组和改名载荷

提供商分组、空的最后使用时间，以及改名载荷只含 `key_name`，用 Node 自带测试运行器覆盖。页面仍用类型检查和生产构建确认。

备选是引入组件测试库。密钥值泄漏的高风险点在请求载荷和渲染字段，不在组件结构。

## Risks / Trade-offs

- [用户可能期望看到密钥后四位] → 文案说明密钥保存后不再显示；列表组件不读取不存在的密钥字段
- [改名误传 `api_key` 会清除已验证状态] → 编辑表单没有密钥框，测试断言载荷只有 `key_name`
- [本 change 依赖会话客户端尚未编码] → 实现顺序放在 `frontend-auth-session` 的客户端和守卫之后；本分支已经包含那份提案
- [验证接口可能较慢或被限流] → 验证按钮单独显示加载状态，失败只展示通用消息

## Migration Plan

随前端静态资源一起发布。没有数据迁移。回滚时恢复上一版前端；已保存的资料和密钥仍留在后端。
