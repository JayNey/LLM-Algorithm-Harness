## Why
Issue #158 第 4 节要求以集成测试保护主要业务流程；现有局部测试未把认证、题库、任务执行、结果和报告串联。

## What Changes
- 新增离线 HTTP + SQLite 集成测试，覆盖注册登录至查询结果、上传至报告下载、实验运行与对比。
- 验证真实检查点恢复、并发请求及预算暂停与继续执行。
- 说明运行方式、外部替身边界与验收映射。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
无。仅增加现有行为的测试与文档，使用 skip_specs，修复既有流程，不新增 API 或能力规格。

## Impact
新增集成测试与说明，并修复评估任务的私有题目读取、实验 worker 的认证注入；使用已有 pytest/httpx 及项目依赖，不需要真实模型、Docker 或 Redis。
