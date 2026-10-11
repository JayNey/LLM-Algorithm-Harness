## ADDED Requirements

### Requirement: 用户认证与安全会话
系统 SHALL 提供注册、登录、刷新、登出和当前用户资料接口，使用 Argon2id 哈希密码，严格校验 JWT，并持久化刷新轮换及会话撤销。

#### Scenario: 刷新单次使用
- **WHEN** 两个请求同时提交相同有效 refresh Token
- **THEN** 仅一个请求取得新 Token，旧 refresh Token 不再可用

#### Scenario: 登出后重启
- **WHEN** 会话登出后服务重启
- **THEN** 该会话的访问与刷新 Token 都不可用

### Requirement: 资源所有权
系统 SHALL 要求所有评估端点使用 Bearer Token，并仅允许所有者列出、读取、修改、删除、启动、取消任务及读取进度。

#### Scenario: 跨用户请求
- **WHEN** 用户 B 请求用户 A 的任务或密钥
- **THEN** 返回 404，列表不包含 A 的资源

### Requirement: 加密密钥管理
系统 SHALL 支持用户范围的多提供商密钥 CRUD，Fernet 加密落盘，连接验证仅访问固定提供商，响应和日志不得包含密钥明文。

#### Scenario: 验证失败
- **WHEN** 提供商连接检查返回包含密钥的异常
- **THEN** API 返回通用失败结果，更新验证计数，并不泄露错误中的密钥

### Requirement: 配置与限流
系统 SHALL 在缺失安全配置时拒绝启动，并为认证和密钥验证提供持久化原子限流。

#### Scenario: 暴力尝试
- **WHEN** 请求超过配置的认证窗口限额
- **THEN** 返回 429 和 Retry-After，限额不会因服务实例重建而重置
