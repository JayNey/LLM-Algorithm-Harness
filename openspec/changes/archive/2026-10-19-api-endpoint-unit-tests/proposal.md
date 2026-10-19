## Why
Issue #158 第三节要求所有 API 端点具有正常、错误、边界及外部依赖隔离测试。现有场景测试较多，但任务接口部分仅测试管理器，缺少统一的路由单元测试覆盖清单。

## What Changes
- 增加按 HTTP 方法和路径维护的端点单元测试，断言响应、服务调用参数及身份传递。
- 覆盖无效输入、未认证、管理员权限、服务异常和分页边界；保留已有业务场景测试。
- Mock 服务、队列、进度流等依赖，测试不访问 LLM API、Docker、Redis 或业务数据库。
- 检查测试清单与应用注册端点一致，防止新增端点遗漏。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
无。仅增加测试工具与验收证据，设置 skip_specs: true，不改变生产行为。

## Impact
新增 tests/unit/ 路由单元测试，复用 pytest、FastAPI TestClient 和 unittest.mock。范围仅限 issue 第三节，不扩展到集成、性能或文档任务。
