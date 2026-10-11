## Why

Issue #152 要求 REST API 具备用户身份、资源权限和 LLM 密钥管理。现有评估端点允许匿名访问所有任务，不能支撑多用户使用。

## What Changes

- 注册、登录、刷新、登出和当前用户资料端点。
- Argon2id 密码哈希、严格 JWT 校验、持久化会话撤销和刷新轮换。
- 用户范围的 Fernet 加密密钥 CRUD、连接验证与使用统计。
- **BREAKING**：评估 CRUD、启动、进度、取消需要 Bearer Token，并按所有者隔离。
- SQLite 认证存储适配器与跨进程限流，为 #151 提供后续迁移边界。

## Capabilities

### New Capabilities
- `api/user-authentication`: 用户身份、会话、所有权和加密密钥管理。

### Modified Capabilities
无。

## Impact

影响 `api/`、依赖声明和 API 文档。CLI 保持现有密钥配置方式。#151 尚未合并，因此认证使用独立 SQLite 数据库，不修改该任务计划中的业务数据库 schema。
