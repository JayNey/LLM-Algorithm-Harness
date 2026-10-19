## Why

Issue #158 第 7 节要求明确 API 版本策略、标注文档版本并检查向后兼容性。当前路由已采用 `/api/v1`，但缺少演进规则和契约回归基线。

## What Changes

- 记录 URL 主版本策略、与 Header 版本的取舍、兼容变更及破坏性变更处理规则。
- 在 OpenAPI/Swagger UI/ReDoc 中明确 API 契约版本，与应用发布版本区分。
- 保存现有 HTTP OpenAPI 契约基线，由现有 pytest CI 检查；新增端点允许，既有契约变化要求审查。

## Capabilities

无运行时能力或已有验收行为变化；仅文档与测试工具，设置 `skip_specs: true`。

## Impact

仅文档生成元数据、版本策略文档、测试及基线；不修改 URL、业务模型、认证或数据库，不新增依赖。
