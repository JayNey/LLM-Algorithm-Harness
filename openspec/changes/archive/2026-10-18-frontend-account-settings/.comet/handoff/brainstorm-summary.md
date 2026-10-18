# Brainstorm Summary

- Change: frontend-account-settings
- Date: 2026-10-18

## 确认的技术方案

用户已确认。

设置页保持 `/settings`，只放「个人资料」和「API 密钥」两个链接，不发请求。`/settings/profile` 与 `/settings/api-keys` 加在现有 `RequireSession` 内，不放进 `appPages`，顶栏仍是原来六个入口。

资料和密钥都走 `useAuthStore.getState().httpClient()`。路径相对于已含 `/api/v1` 的 `baseURL`：`/users/me`、`/api-keys`、`/api-keys/{id}`、`/api-keys/{id}/verify`。

用户名和邮箱校验与注册共用同一组规则。密钥分组、非法密钥拒绝和改名载荷放在不依赖 Vite 的纯模块里，用 Node 测试覆盖。页面不引入新依赖，也不做组件测试。

## 关键取舍与风险

- 验证结束后重新拉取列表。界面只显示「验证成功」或「验证失败」，不展示后端英文 `message`。
- 资料更新成功后，若用户名变了，同步内存会话里的用户名，避免顶栏仍显示旧名。
- 改名载荷若带上 `api_key`，后端会清除已验证状态。编辑函数只返回 `{ key_name }`。
- 列表类型不包含密钥字段，页面无法渲染明文、掩码或后四位。
- 依赖已满足：`frontend-auth-session` 已在 `main` 合入，当前分支已合并该提交。

## 测试策略

- Node 测试：按 `openai`、`anthropic`、`siliconflow` 分组；空组没有卡片；`last_used_at` 为空时表示尚未使用且使用次数为 0。
- Node 测试：空白、`env:`、`ENV:`、`${` 开头的密钥在提交前被拒绝。
- Node 测试：改名载荷只有 `key_name`。
- 页面与路由：类型检查、代码检查和生产构建成功退出。

## Spec Patch

无。
