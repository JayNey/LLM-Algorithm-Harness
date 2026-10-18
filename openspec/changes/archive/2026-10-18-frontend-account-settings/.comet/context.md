# Comet Design Handoff

- Change: frontend-account-settings
- Phase: design
- Mode: compact
- Context hash: 61a41eb52799801a14cf10290d5f3ae7dab987da7d79f80bbc2db8bd82dd1e8a

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/frontend-account-settings/proposal.md

- Source: openspec/changes/frontend-account-settings/proposal.md
- Lines: 1-29
- SHA256: b4bcc0d592e359466a3f894789d7b6e45439849674c9669d39917b4260a2c872

```md
## Why

登录会话建立后，用户仍然不能查看或修改自己的资料，也不能管理评估要使用的 LLM API 密钥。这些后端接口已经可用，Issue #161 的后半部分需要把它们接到设置页。

## What Changes

- 设置页改为个人资料和 API 密钥的入口，页面本身不请求业务数据
- 新增个人资料页：展示用户名、邮箱和注册时间，并允许修改用户名和邮箱
- 新增 API 密钥页：按 `openai`、`anthropic`、`siliconflow` 分组，支持添加、修改名称、确认后删除和验证，并展示使用次数与最后使用时间
- 界面不接收、不展示密钥明文、掩码或后四位；后端响应里也没有这些值
- 未登录用户不能打开资料页和密钥页
- 不修改后端接口，也不重做登录、刷新和路由守卫

## Capabilities

### New Capabilities

- `frontend/user-profile`: 查看和修改当前用户的用户名、邮箱，并展示注册时间
- `frontend/api-keys`: 管理当前用户的 LLM API 密钥元数据和验证状态

### Modified Capabilities

无。六个既有页面的行为不变；资料和密钥是设置页下的新路由。

## Impact

- `frontend/src` 的设置入口、资料页、密钥页，以及对应的请求封装
- 依赖 `frontend-auth-session` 已提供的登录会话、认证请求客户端和路由守卫
- 调用 `GET /api/v1/users/me`、`PATCH /api/v1/users/me`、`GET /api/v1/api-keys`、`POST /api/v1/api-keys`、`PATCH /api/v1/api-keys/{id}`、`DELETE /api/v1/api-keys/{id}` 和 `POST /api/v1/api-keys/{id}/verify`

```

## openspec/changes/frontend-account-settings/design.md

- Source: openspec/changes/frontend-account-settings/design.md
- Lines: 1-54
- SHA256: 9dda7eba3c9e3ec3f39efc1beeb305cd789db0c8cf931fef023a3da4fce23eda

```md
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

```

## openspec/changes/frontend-account-settings/tasks.md

- Source: openspec/changes/frontend-account-settings/tasks.md
- Lines: 1-15
- SHA256: faf81c65b4a4cb624d3e3f135c3ffcfe57033e72d7ea1a208cb22b74a9f41d2f

```md
## 1. 资料与入口

- [ ] 1.1 把 `/settings` 改成个人资料和 API 密钥的入口，页面不请求这两类数据。用类型检查确认设置页通过编译
- [ ] 1.2 增加受守卫保护的资料页，读取 `GET /api/v1/users/me`，用本地时间显示注册时间，并在失败时显示错误。用类型检查确认页面通过编译
- [ ] 1.3 资料表单按注册规则校验用户名和邮箱，成功后显示新值，占用冲突时保留表单并显示错误。用类型检查确认校验逻辑通过编译

## 2. API 密钥

- [ ] 2.1 实现按 `openai`、`anthropic`、`siliconflow` 分组的列表模型，空组不产生卡片，没有 `last_used_at` 时表示为尚未使用。用 Node 测试验证分组和未使用状态
- [ ] 2.2 增加密钥页：密码框添加密钥，成功后清空输入且列表不渲染密钥值；拒绝空白和 `env:`、`ENV:`、`${` 开头的值。用 Node 测试验证拒绝规则，并用类型检查确认页面通过编译
- [ ] 2.3 编辑只提交 `{ "key_name": "..." }`，删除必须确认后才发请求，验证结果只展示通用成功或失败。用 Node 测试验证改名载荷不含 `api_key`

## 3. 整体验证

- [ ] 3.1 运行前端类型检查、代码检查和生产构建，三者都成功退出。Node 测试覆盖分组、非法密钥值和改名载荷

```
