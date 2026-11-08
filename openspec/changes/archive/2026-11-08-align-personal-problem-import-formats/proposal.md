## Why

[#399](https://github.com/JayNey/LLM-Algorithm-Harness/issues/399) 发现个人题库主规格列出 YAML，实际表单、客户端和服务端导入只接受 JSON/CSV。[#163 的验收记录](https://github.com/JayNey/LLM-Algorithm-Harness/issues/163#issuecomment-6380734161) 已按 JSON/CSV 交付。

## What Changes

- 将个人题库文件导入的规格范围明确为 JSON/CSV，覆盖同步直导和异步任务。
- 在前端验收文档中记录支持格式及 YAML 文件的拒绝预期。

## Capabilities

### New Capabilities

### Modified Capabilities

- `frontend/problems-management` 的个人题库文件导入格式。

## Impact

变更涉及个人题库主规格及前端验收文档。文件服务指南已列明个人题库使用 JSON/CSV，配置文件可使用 YAML。
