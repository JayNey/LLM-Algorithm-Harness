## Why

Issue #158 第 6 节要求覆盖率目标、报告和 CI 检查。当前本地 pytest 仅显式统计 src，CI 的无路径 --cov 又会改变统计范围；统一总覆盖率不能独立保护 API。

## What Changes

- 统一统计 src/ 和 api/，保持 src 行覆盖率至少 90%，API 行覆盖率至少 81%（严格高于 issue 要求的 80%）。
- 生成终端、HTML、XML 报告，使用 coverage 原生 report 命令提供独立的分模块门禁。
- CI 保留测试失败状态，在测试失败或门禁失败时也上传可用报告；补充复现命令并验证门禁的成功/失败路径。

## Capabilities

### New Capabilities

无。仅修改测试工具、CI 与开发文档，设置 skip_specs: true。

### Modified Capabilities

无。不改变产品 API、数据模型和运行时行为。

## Impact

pyproject.toml、CI workflow、README 开发说明。沿用 pytest-cov/coverage，不增加依赖或自定义检查脚本。不涉及 #158 其他章节或性能测试。
