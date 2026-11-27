# 提案：Web 推荐参数

## Why

GitHub #525 指出 Web 推荐未展示已有失败率阈值，且 API 未向共享分析传入数量，导致推荐固定使用默认 20。用户需要按薄弱程度与下一轮规模配置推荐。

## What Changes

- 页面增加失败率阈值（默认 0.5，范围 0 < 值 ≤ 1）及推荐数量（默认 20，整数 1–100）。
- 请求模型校验 limit 并传入共享 analyze_recommendations；省略参数仍使用现有默认值。
- 展示最多选择、保存及带入评估 100 道题的现有容量限制，沿用来源、历史权限、人工选题与题集流程。
- 使用固定数据与本地 mock 验证输入、请求、分析结果及保存后继续评估，不调用付费模型。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/evaluation-results`：扩展推荐参数及页面输入约束，明确容量及默认兼容行为。

## Impact

涉及 API 请求模型与推荐路由、前端客户端和 RecommendationPanel、英文文案以及已有后端和前端测试设施。不改数据库或共享推荐排名算法。执行配置沿用 Runtime 的 tweak 预设：buildMode=direct、tddMode=direct、reviewMode=off，仍进行相关检查及自查。
