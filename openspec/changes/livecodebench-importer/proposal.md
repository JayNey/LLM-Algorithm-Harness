# 提议：导入 LiveCodeBench 基准题库

## Problem

项目目前可以导入本地 JSON 和 LeetCode 公开题面，但缺少固定版本、带独立测试的公开基准来源，无法稳定复现实验题目集合。

## Goal

- 支持固定 LiveCodeBench release 版本和日期/难度/数量过滤。
- 支持本地 JSON/JSONL 缓存和可信静态文件 URL 下载。
- 映射题目来源、日期、入口、public/hidden 测试和数据摘要。
- 拒绝任意 pickle/压缩序列化反序列化，遇到不支持格式给出明确错误。
- 记录确定的题目 ID 列表和内容摘要，保证重复导入可审计。

## Non-goals

- 不执行上游数据中的任意代码或 pickle。
- 不实现更多平台适配器。
- 不修改 LiveCodeBench 上游数据或声称拥有官方隐藏测试之外的额外权限。

## Impact

- 新增 `LiveCodeBenchImporter`，复用现有导入预览、去重、报告和原子写入流程。
- 扩展 CLI 的 `import` 参数和导入报告元数据。
