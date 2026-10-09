## Why

本变更解决 Windows 兼容性中与文件系统路径处理相关的问题。当前代码库存在硬编码的 Unix 风格路径分隔符，以及将 URL 路径解析中的正斜杠误当作文件系统分隔符的情况，导致在 Windows 上运行失败。这是 Windows 兼容性工作的第 4/4 部分。

## What Changes

- 修正 URL 路径解析中硬编码的正斜杠 (`"/"`) 字符串分割，确保 URL 感知的处理不会混淆 URL 路径与文件系统路径
- 审查并修复测试与实现中对大小写敏感文件系统的假设
- 确保测试数据不使用 Windows 保留文件名（`CON`、`PRN`、`AUX`、`NUL`、`COM1-9`、`LPT1-9`）
- 为贡献者编写路径处理规范文档

## Capabilities

### New Capabilities

无 - 这是兼容性修复，不引入新行为。

### Modified Capabilities

- `windows-compatibility`: 扩展现有的跨平台进程与文件管理，覆盖文件系统路径语义。变更需求确保 URL 路径解析不会混淆正斜杠与文件系统分隔符，且测试数据避免使用 Windows 保留名称。

## Impact

- **Code**: `src/importers/leetcode.py`（URL 路径解析）、`src/code_quality/readability_analyzer.py`（pylint 分数解析）
- **Tests**: 审查测试 fixture 文件名是否存在 Windows 保留名称
- **Dependencies**: 无
- **Systems**: Windows CI 必须通过，不得有路径相关失败
