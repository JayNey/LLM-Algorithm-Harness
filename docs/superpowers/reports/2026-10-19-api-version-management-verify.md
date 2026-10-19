# API 版本管理验证报告

- Change：`api-version-management`
- 对应需求：GitHub issue #158 第 7 节的三个子项。
- 分支：`comet/api-version-management`
- 基线：`c01a125a1b0a6d082568555e37c706a463bbf767`
- 实现提交：`273d0b4`、`071aefb`、`36f3f48`
- 结论：PASS，无未解决的 CRITICAL/IMPORTANT 问题。

## 交付与需求对应

1. `docs/api-versioning.md` 明确采用 URL 主版本，说明不采用 Header 协商的原因、主次修订版本规则、兼容变更及新主版本迁移/退役流程；`API.md` 链接该策略。
2. `/openapi.json` 的 `info.version=1.0.0`，概览及各操作标注 API v1；Swagger UI/ReDoc 读取相同元数据。现有 `/api/v1` URL 保留；健康检查的应用发布版本仍为 `0.1.0`。
3. `tests/fixtures/openapi-v1.json` 保存变更前全部 126 个 HTTP 操作及引用组件。`tests/test_api_versioning.py` 比较真实应用生成的契约，允许新增路径/HTTP 方法/组件，既有结构及全局、路径级配置改变时失败。现有 CI 的全量 pytest 自动包含此门禁。

## 验证证据

- RED：版本元数据测试在修改前失败，实际 `0.1.0` 与目标契约版本 `1.0.0` 不同；另一项 URL/发布版本测试通过。
- 初始相关测试：33 passed；增加参数、媒体类型、枚举变更检测后 36 passed。
- 全量离线套件：`MPLCONFIGDIR=/tmp/llm-harness-matplotlib python3 -m pytest -m 'not online'`，退出 0；**2625 passed, 6 skipped, 115 warnings**，耗时 301.20 秒，总覆盖率 **91.77%**。输出位于 `/tmp/issue158-section7-pytest.log`。
- 独立覆盖率门禁：`python3 -m coverage report --include='api/*' --fail-under=81` 为 **94.22%**；`--include='src/*' --fail-under=90` 为 **90.56%**；均退出 0。
- 最终审查指出路径级配置与新增方法需区分。三个最小回归用例先复现失败，再固定比较路径级 `parameters`、`servers`、`$ref` 等配置；最后执行 `python3 -m pytest tests/test_api_versioning.py tests/test_api_documentation.py -q --no-cov`，**39 passed, 5 warnings**，退出 0。输出位于 `/tmp/issue158-section7-final-targeted.log`。
- 全量运行完成后仅修改测试工具及新增该工具的三个回归用例，运行时代码未再改变；最终版本相关测试已重新执行，全量套件未重复执行。
- `python3 -m compileall -q api`、Black 检查、Ruff、`git diff --check` 及 `comet classic openspec -- validate api-version-management --strict` 均通过。
- 独立从基线提交的 `api/documentation.py` 再生成规范，剔除文档注释及独立检查的 info 元数据后与冻结基线完全一致。

## 轻量验证六项

- [x] 两项实施任务全部完成。
- [x] 修改与任务范围一致：5 个交付文件，另有当前报告和 Comet 自动元数据；未涉及数据库或业务路由修改。
- [x] Python 编译检查通过。
- [x] 相关测试及全量离线测试通过，两个覆盖率门禁通过。
- [x] 无新增密钥、外部调用、数据写入或权限扩展。
- [x] 最终独立集成审查完成，无阻塞项；路径级配置建议已修复并通过 RED/GREEN 回归。

规模脚本因统计 Comet 状态与快照等文件而返回 full；实际为两个任务、零 delta spec、5 个交付文件的文档/测试工具变更，按允许的覆盖机制采用 light。未触发架构或新增运行时能力升级条件。

## 范围与已知限制

基线门禁采用保守结构比较，可阻止可疑的既有契约变化，也会拦截部分兼容扩展；需按策略人工审查后更新基线，不能在 CI 自动重录。业务语义、未声明的动态响应字段、WebSocket 帧及外部服务行为不由 OpenAPI 基线证明，已有运行时回归予以补充。本次未运行线上凭证验证或托管 CI；测试输出中的既有弃用等警告未影响通过结果。

本次为文档与测试工具变更，`skip_specs: true`，不新增或修改主规格。用户已选择 C：确认归档、立即推送并创建 PR。归档目录为 `openspec/changes/archive/2026-10-19-api-version-management`；归档完整性守卫通过，报告与验证状态包含在本次唯一归档提交中。
