# Preset file-count authorization

- status: active
- workflow: tweak
- decision: continue-on-file-count-only
- scope: GitHub #525；阈值及数量输入、请求校验与传递、100 道容量说明、中英文文案、API 与浏览器验收。交付文件 9 个（实现 4、文案资源 2、测试 2、验收报告 1）。
- allowed-file-categories: implementation, tests, user-docs, config, generated
- authorization-basis: user-explicit
- reason: 用户在阅读 Open 提案、设计和任务清单链接后明确回复“批准”；已批准设计的 Risks / Trade-offs 预估 7–9 个交付文件。当前 9 个文件仍在该范围，无新模块、端点、数据库 schema 或架构协调；本次仅贯通已批准的既有接口参数。

文件对应：api/evaluation_options.py、api/routes/evaluation_results.py、frontend/src/evaluations/RecommendationPanel.tsx、frontend/src/evaluations/client.ts 为实现；frontend/src/i18n/zh-CN.ts、frontend/src/i18n/en-US.ts 为文案资源；tests/test_api_evaluation_options.py、frontend/scripts/verify-recommendation-controls.mjs 为测试。OpenSpec 与本 Comet 元数据不计交付文件。

验收报告按 Runtime 强制目录保存到 docs/superpowers/reports/2026-11-27-web-recommendation-controls-verify.md，属于已批准的文档范围。
