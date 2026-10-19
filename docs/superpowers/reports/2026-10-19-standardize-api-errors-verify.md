# standardize-api-errors 验证报告

## 范围与决策

完成 #158 第8节的统一 HTTP 错误格式和错误码体系。用户选择2A：从最新main建立独立分支，确认继续单一tweak流程。实际涉及中央错误处理、请求日志、认证服务/中间件、上传边界、应用注册、测试和README，均属于已确认契约范围。可选国际化不实施，成功响应和WebSocket协议不变。

## 实现与兼容

- 规范错误体success=false、error.code/message/details/request_id；顶层message/detail/details兼容现有前端。
- 普通HTTP异常按状态映射，显式ApiError可选择业务码；不根据英文文案猜测，不新增预算或配额能力。
- 请求ID由服务端生成并复用；错误体与X-Request-ID及日志一致，不接受客户端ID。
- 使用响应开始前的ASGI异常边界消费异常，阻断Uvicorn二次日志；CORS预检仍采用上游策略判断，仅规范失败格式。统一异常和ASGI提前拒绝，保留401/429等状态、认证/限流/CORS/缓存头以及上传清理。
- 5xx仅返回通用消息；异常日志只含ID与类型。校验错误不回显input/ctx，敏感字段的正常校验提示保持可用。
- OpenAPI公开ErrorResponse和ErrorCode，校验声明与实际400一致。

## 测试证据

- 初始契约测试22个全部失败，原因是缺少结构化契约、请求ID及OpenAPI模型；实现后22个通过。
- 补充密码字段校验提示回归先失败（错误地按敏感键隐藏提示），修正后相关套件151 passed。
- 相关套件：tests/test_api_errors.py、tests/test_api_auth.py、tests/test_api_files.py，151 passed；上传超时/断连保留原资源清理测试并追加规范错误断言。
- 前端npm test：96 passed、0 failed，未修改前端源码。
- 核心中间件mypy：4个文件通过。整体src类型检查仍有既有api/files/parsing.py:93和api/progress.py:139错误；扩展API入口类型检查还暴露未改动的task_snapshots/routes既有类型问题，不计作通过。本次新增核心类型错误已修复。
- wheel构建、ruff、black、显式编码检查、git diff --check通过。
- 最终完整离线套件：`python3 -m pytest -m "not online"` 退出0，1781 passed、6 skipped、115 warnings，269.57秒。总覆盖率91.35%；src 90.45%（10856行、1037未覆盖），api 93.26%（5176行、349未覆盖），两个独立门禁均退出0。errors.py覆盖率97.95%。HTML/XML均已生成。
- 独立集成审查：PASS。同一审查者发现并复核修复两项问题：Starlette将异常重新抛给Uvicorn造成原始异常日志泄漏，以及CORS拒绝预检返回纯文本。严格TestClient和预检测试修复前失败、修复后通过；边界+CORS+流式/非HTTP行为复核无剩余问题。

## OpenSpec完整验证

- verify_mode=full；重新读取proposal/design/tasks/delta，OpenSpec strict validate通过。verify阶段独立重跑tests/test_api_errors.py：30 passed、退出0（19.07秒）。
- 完整性：3/3任务完成；4/4 Requirement实现；8/8 Scenario有验证。
- 正确性：参数校验、HTTP/业务错误、凭证/令牌、限流/上传边界、内部异常、并发ID和OpenAPI八类Scenario（含被拒绝的CORS预检）分别由契约测试和文件回归覆盖。
- 一致性：遵循design.md的中央构造、显式业务码、兼容字段和敏感信息保护决策。Tweak无独立Superpowers深度Design Doc或完整plan，使用本change design.md；非缺失产物。

## 限制

未执行远端CI；外部Redis/Celery/Docker/在线测试可能按环境跳过，不能据此声称生产依赖可用。已开始发送的流式响应、生命周期和WebSocket关闭事件不改写为JSON。

## 场景到验证的映射

- 参数校验：test_validation_preserves_field_details_without_echoing_input、test_validation_messages_for_credential_fields_remain_useful。
- HTTP与业务异常：test_http_error_codes_and_headers、test_framework_not_found_and_method_not_allowed、test_explicit_business_code_and_conflict_status、test_structured_detail_remains_compatible。
- 凭证与令牌：test_missing_and_invalid_tokens_in_routes_and_upload_boundary、test_login_rate_limit_and_refresh_errors，及原认证回归。
- 限流与上传边界：test_upload_capacity_size_and_length_errors_preserve_headers、test_auth_body_limit_uses_error_contract、原test_interrupted_and_idle_upload_closes_disk_spool新增响应断言；原文件套件保持资源清理覆盖。
- CORS预检：test_rejected_cors_preflight_is_a_json_error_without_weakening_policy，检查来源/方法拒绝和允许预检原格式。
- 未处理异常：test_internal_failures_do_not_leak_private_data、test_internal_failure_does_not_escape_to_server_traceback_logging、test_unexpected_route_and_upload_boundary_failures_have_cors_and_no_store；严格客户端证明异常没有继续传播给服务器。
- 并发请求ID：test_request_ids_are_server_generated_and_isolated。
- 契约文档：test_openapi_error_contract_matches_validation_status；README公开迁移说明、默认码和显式业务码。
- 额外协议边界：test_stream_failure_after_headers_is_not_rewritten_as_another_response验证不产生第二次响应；完整WebSocket套件验证既有帧和关闭码不变。

## 结论

PASS。实现、测试、OpenSpec delta与design一致；独立集成审查发现的P1/P2均已修复并复核，无剩余CRITICAL/IMPORTANT或需接受的契约偏差。保留已知的本机项目级类型检查问题作为验证限制，不将其宣称为通过。可进入归档前用户确认。
