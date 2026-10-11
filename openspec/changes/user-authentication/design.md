## 实现

- `AuthSettings` 要求配置 SECRET_KEY（至少 32 字节）和 ENCRYPTION_KEY（Fernet），无默认密钥；应用 lifespan 初始化，未配置时拒绝启动。
- `AuthStore` 使用参数化 SQLite SQL，持久化用户、会话、加密密钥和限流窗口。每次操作独立连接和事务，刷新采用条件更新，登出撤销整组会话。该适配器由 #151 后续接替，当前不引入 PostgreSQL 依赖。
- Argon2id 使用库的默认安全参数；不存在用户也进行虚拟哈希验证。JWT 只接受 HS256，验证 issuer/audience/exp/iat/nbf/sub/jti/sid/type 和服务端会话。刷新 Token 单次使用，访问 Token 不能刷新。
- Token 仅从 Authorization Bearer 或刷新 JSON 字段接收；不使用认证 cookie 和查询参数，避免 cookie 型 CSRF。CORS 使用现有明确 origin 白名单。
- IP 限制登录、注册、刷新；账号限制验证密钥和受保护操作。SQLite 原子计数避免多进程绕过。请求日志不记录 query、body 和 Authorization，审计事件只记录用户 ID、资源 ID、动作和成功状态。
- API 密钥只接受真实密钥，拒绝 env:/ENV:/${NAME} 引用；提供商限于 openai、anthropic、siliconflow。连接检查使用现有 LLMClient 的固定服务地址，5 秒超时，不接受自定义 URL；不回传 SDK 错误或密钥，不调用生成接口。
- 每个应用独立评估服务，TaskState 增加 owner_id 和 api_key_id。创建时验证密钥归属；启动时重新验证密钥，跨用户访问与不存在资源统一 404。旧匿名任务对所有用户不可见。当前执行器仍为 #148 的模拟器，真实密钥消耗计数由 #149 的 worker 接入 `record_key_usage`，当前仅记录验证次数和最后验证时间。
- 用户私有题库将在 #153 接入相同 `current_user` 依赖；题库路由尚未存在，不在本 change 另建上传服务。可选 RBAC、密码重置、邮箱验证不实现。

## 验证

真实 TestClient + 临时 SQLite，覆盖两用户隔离、刷新竞态、重启后撤销、JWT 篡改/类型混淆/过期、密码和密钥落盘、验证脱敏、限流、配置失败和评估完整生命周期。全量离线套件、格式/类型检查、独立审查后创建 PR；CI 必须保留 macOS/Ubuntu/Windows 的既有强制门禁。
