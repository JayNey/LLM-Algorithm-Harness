# API 用户认证与密钥管理（#152）

## 配置与启动

安装 `pip install -e '.[dev]'` 后，设置两个独立的随机密钥。可以将命令输出保存到本机受保护的 `.env`，不要提交或分享该文件：

```bash
python -c 'import secrets; print("SECRET_KEY=" + secrets.token_urlsafe(48))'
python -c 'from cryptography.fernet import Fernet; print("ENCRYPTION_KEY=" + Fernet.generate_key().decode())'
```

环境变量或 `.env` 支持：

- `SECRET_KEY`：至少 32 字节，用于 HS256 签名，无默认值。
- `ENCRYPTION_KEY`：有效 Fernet 密钥，无默认值。
- `AUTH_DATABASE_PATH`：默认 `data/auth/auth.sqlite3`。
- `ACCESS_TOKEN_EXPIRE_MINUTES`：默认 30。
- `REFRESH_TOKEN_EXPIRE_DAYS`：默认 7，刷新不延长原会话最长有效期。
- `AUTH_RATE_LIMIT`：默认每客户端 IP 每 60 秒共 10 次注册、登录、刷新；每用户每窗口最多 10 次密钥验证。
- `AUTH_RATE_WINDOW_SECONDS`：默认 60。
- `AUTH_PROTECTED_RATE_LIMIT`：默认每用户每窗口 120 次受保护请求。

启动 `./run_api.sh`。缺失或无效密钥会导致启动失败。保持签名和加密密钥稳定，否则旧 Token 或已加密凭据将失效。更换加密密钥前需要迁移密文；本版本不提供自动密钥轮换。

## 认证接口

所有请求使用 JSON，成功响应保留 `success/data/message` 包装。

1. `POST /api/v1/auth/register`：`username`、`email`、`password`。用户名 3–64 字符，限字母、数字、`_.-`；密码 12–1024 字符。用户名和邮箱不区分大小写，重复返回 409。
2. `POST /api/v1/auth/login`：`username` 可为用户名或邮箱，另提供 `password`。返回 `access_token`、`refresh_token`、`token_type`、`expires_in`。
3. `POST /api/v1/auth/refresh`：提供 `refresh_token`，获得新的 Token 对。旧刷新 Token 单次使用；并发刷新仅一项成功。
4. `POST /api/v1/auth/logout`：使用访问 Token，返回 204，撤销该登录会话的所有 Token。其他独立登录会话保持有效。
5. `GET /api/v1/users/me`：查询自己的公开资料。
6. `PATCH /api/v1/users/me`：更新用户名或邮箱，不接受角色和用户 ID。

后续请求使用 `Authorization: Bearer <access_token>`。刷新 Token 不能用来访问资源，访问 Token 不能刷新。Token 不从 cookie 或 URL 参数读取，因此不会使用浏览器自动附带的 cookie 身份；前端自行管理 Bearer Token。所有 API 响应带 `Cache-Control: no-store`。无身份或无效 Token 返回 401；限流返回 429 和 `Retry-After`。认证、资料和密钥 JSON 请求最多 16 KiB，含分块传输，超出返回 413。

## LLM API 密钥

- `GET /api/v1/api-keys`：只列出当前用户的密钥元数据。
- `POST /api/v1/api-keys`：`provider`、`key_name`、`api_key`；provider 支持 `openai`、`anthropic`、`siliconflow`。
- `PATCH /api/v1/api-keys/{id}`：更新名称或实际密钥；更新密钥清除已验证状态。
- `DELETE /api/v1/api-keys/{id}`：删除密钥，返回 204。
- `POST /api/v1/api-keys/{id}/verify`：调用现有 `LLMClient.check_connection()`，只访问固定提供商的模型列表，SDK 请求超时 5 秒、禁用重试，不发起生成。

不接受 `env:` / `${NAME}` / `ENV:` 引用、自定义 `base_url` 或本地提供商，防止读取服务端环境密钥和访问任意地址。返回元数据包含 `id/provider/key_name/created_at/verified/verification_count/last_verified_at/usage_count/last_used_at`，永不返回密钥明文、部分密钥或密文。验证失败返回 `data.ok=false` 及通用消息，不回传提供商错误。编辑与验证并发时，旧密钥的验证结果不能把新密钥标记为已验证。

密码使用 [Argon2id](https://argon2-cffi.readthedocs.io/en/stable/api.html) 哈希；密钥使用 [Fernet](https://cryptography.io/en/latest/fernet/) 加密；JWT 固定算法与必需声明检查遵循 [PyJWT API](https://pyjwt.readthedocs.io/en/stable/api.html)。请求日志不包含 body、query 或 Authorization；审计事件只包含动作、用户 ID 和资源 ID。

## 评估任务与所有权

全部 `/api/v1/evaluations` 路由需要认证。创建任务必须提供自己的密钥 ID 和 `model`（`model` 为必填，缺失返回 400）：

```json
{
  "problem_ids": ["1", "2"],
  "strategy_names": ["vanilla"],
  "api_key_id": "id-returned-by-api-keys",
  "model": "gpt-4o-mini",
  "budget_cap_usd": 10.0
}
```

列表、读取、更新、删除、启动、进度和取消都按 `owner_id` 隔离。跨用户资源和不存在资源同样返回 404。启动前再次检查密钥存在且属于用户；已删除的密钥不能启动任务。CLI 的密钥读取方式保持不变。

## 与 #149 / #151 / #153 的接入边界

- #148 评估接口已由 #151 接入持久化业务数据库。#179 已合并 Celery/Redis 与异步任务管理基础，#180 已合入实验、导入和基准三类 Celery 任务实现；其端到端执行与真实 LLM 指标仍未接通或验证，HTTP 也没有自动改为队列。当前 `/evaluations` 路由仍使用旧评估流程。异步评估 worker 现已改为经真实 `AlgorithmHarness` 执行（LLM 调用 + Docker 沙箱运行 + 成本统计），逐单元结果落库，不再返回模拟结果。身份和凭据引用绑定到任务；真实 LLM 调用的端到端执行与使用计量仍待生产环境验证（测试不发起在线调用），#149 保持开放。
- #149 worker 应以可信任务的 `owner_id/api_key_id` 调用 `AuthService.llm_config(key_id, user_id, model)`，获得只在内存使用的配置；每次真实提供商请求后调用 `AuthStore.record_key_usage`。禁止将解密凭据写入 broker、任务 JSON 或结果文件。
- #151 业务数据库已合并，但认证仍使用 `api/auth/store.py` 的独立、持久化 SQLite 适配器，包含 `auth_users/auth_sessions/auth_keys/auth_rates`。业务任务的 `user_id` 引用认证用户 ID，不使用跨库外键。后续替换认证 Repository 时需保留刷新条件更新、撤销、参数化查询、加密值和原子限流语义。不同实例必须共享同一认证数据库文件；不支持跨机器独立 SQLite 文件共享认证状态。
- 评估与异步任务状态跨重启持久化；现有评估服务的启动恢复规则不能当成真实队列恢复执行保障。认证用户、密钥、会话和限流在同机共享文件的多进程及重启场景有效。
- #153 私有题库/文件 API 和 #150 的订阅权限可复用 `current_user` / `AuthService.authenticate`；各自还需在资源查询时验证 owner，不能只检查 Token。
- 完整 RBAC、管理员账号创建、邮箱验证和密码重置为 issue 中的可选项，当前不开放。#157 的监控管理员由部署者设置 `MONITOR_ADMIN_USER_IDS` UUID 白名单，仅授权监控端点；用户名或客户端 Token 角色不能赋予权限，详见 [监控指南](api-monitoring.md)。

正式部署使用 HTTPS，保护数据库目录及 `.env` 权限，并明确配置可信代理。应用限流使用 ASGI 的客户端地址，不直接信任请求中的 `X-Forwarded-For`；代理是否信任由服务启动参数控制。#157 已持久化脱敏的 API 生命周期与可信任务事件，并提供管理员全局查询和所有者任务日志下载；它不代表完整运维审计平台，异步 worker 的真实事件尚待绑定。

## 验证

```bash
python -m pytest tests/test_api_auth.py -q --no-cov
python -m pytest -m 'not online' --cov --cov-report=term
```

测试使用临时数据库和随机测试配置。连接验证使用模拟提供商，不读取真实用户密钥，也不访问生成 API。
