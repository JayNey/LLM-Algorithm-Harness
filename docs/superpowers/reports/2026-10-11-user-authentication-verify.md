# Issue #152 用户认证与授权验证报告

日期：2026-10-11（Asia/Shanghai）。基线：`efbe22e`（#171）。分支：`tweak/20261011/user-authentication`。

## 范围与实现

- 注册、登录、刷新轮换、持久化撤销、用户资料更新。
- Argon2id 密码哈希、严格 HS256/issuer/audience/必需声明校验。
- 独立 SQLite 事务存储，多实例共享会话、加密密钥与限流状态。
- Fernet 加密密钥 CRUD，固定提供商连接验证、验证次数及真实请求计数接入接口。
- 全部现有评估 API 的身份与所有权校验、创建/启动时密钥归属检查。
- 无 cookie 身份、无查询参数 Token、16 KiB 认证请求上限、no-store 响应、敏感日志清理及安全审计。

## 验证证据

- `pytest tests/test_api_auth.py --no-cov -q`：**61 passed**。
- 最终全量 `pytest -m 'not online' --cov --cov-report=term --cov-report=xml`：**1212 passed、4 skipped**，覆盖率 **93.31%**，90% 门禁保持不变。通过 `comet check run user-authentication build --local` 实际执行，exit=0。
- `ruff check .`、`black --check .`、文本编码扫描（0 处隐式编码）：通过。
- `mypy src/ --ignore-missing-imports`：87 文件通过；额外 `mypy api/auth --ignore-missing-imports --follow-imports=silent`：7 文件通过。
- OpenSpec `user-authentication` strict 校验：通过。
- 连接测试均使用替身，未访问生成端点，未使用真实凭据；真实 SQLite 和 HTTP 请求覆盖权限边界。

## 独立审查

Bugbot 第一轮发现 1 个 P1：上传校验仅拒绝 `ENV:`，而现有 LLMClient 解析 `env:NAME` 和 `${NAME}`，存在使用服务端凭据的风险。

已修复新增/编辑路径，并对解密后的持久化记录再次拒绝引用，避免导入旧记录绕过；补四种引用的完整回归。复审未发现新的确定问题，审查者独立运行 **61 passed**。另在实现检查中修正 SDK 模型列表超时未生效问题，明确设置 5 秒 SDK 超时、零重试及固定地址。

## 规格场景映射

- 刷新单次使用：`test_refresh_race_has_only_one_winner_across_services`、`test_refresh_rotation_and_logout_persist_after_restart`。
- 登出后重启：`test_refresh_rotation_and_logout_persist_after_restart`。
- 跨用户资源：`test_every_evaluation_operation_checks_ownership`（六操作）、`test_keys_encrypted_isolated_editable_and_survive_restart`。
- 密钥验证失败脱敏：`test_provider_check_is_bounded_sanitized_and_counted`、`test_provider_exceptions_and_wrong_encryption_key_do_not_leak`。
- 限流持久化/原子性：`test_rate_limits_persist_and_ignore_spoofed_forwarded_headers`、`test_rate_limit_atomic_across_store_instances_and_expiry`。
- 安全配置失败：`test_missing_and_invalid_secret_configuration_fails_closed`。
- 服务端密钥引用拒绝：`test_no_api_path_can_use_server_environment_credentials`。

## 依赖与限制

- #151 未合并，因此使用隔离的 SQLite 认证适配器；不修改其计划中的业务数据库 schema。
- #148 现有评估执行器仍是模拟器，业务任务仍存内存；本 PR 没有实现 #149 的 worker。真实执行接入 `llm_config` / `record_key_usage`，不把模拟任务伪记为实际使用。
- #153 的私有题库端点和 #150 的订阅权限使用本 PR 的公共身份依赖，由各自 issue 接入。
- 可选 RBAC、密码重置、邮箱验证不包含在此次实现。
- 跨平台结果以本 PR 最新 CI 为准；本机不能替代 Windows/Ubuntu runner。

## 交付

实现、测试、独立审查及文档完成。提交关联 #152 的 PR 后记录链接和远端 CI 结果；不直接合并。
