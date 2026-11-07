## Why

[Issue #377](https://github.com/JayNey/LLM-Algorithm-Harness/issues/377) 指出 API 文档把改密描述为撤销全部会话，导致用户无法判断其他登录设备是否需要重新认证。现有改密流程保留用户的现有会话。

## What Changes

- 同步 API.md 和 OpenAPI 的改密操作说明，明确当前会话和其他现有会话继续有效，访问和刷新令牌仍按原规则使用。
- 同步 OpenAPI 的 `new_password` 字段说明，并写明 12–1024 个字符的限制。

## Capabilities

### New Capabilities

无新增能力。

### Modified Capabilities

无规范行为变更。本次将文档与既有 `api/password-change` 行为对齐。

## Impact

涉及 API.md 和 api/documentation.py。验收覆盖生成的 OpenAPI，以及改密后的访问和刷新行为。
