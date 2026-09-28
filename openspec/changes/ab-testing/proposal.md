# 提议：Prompt A/B 测试框架

## Problem

策略 prompt 目前依赖人工修改和整体成功率比较，无法确认两个 prompt 版本是否在相同题目分布上产生了显著差异。

## Goal

- 支持同一策略的两个 prompt 变体、描述、版本和系统提示覆盖。
- 按难度和标签分层、用固定随机种子均衡分配题目。
- 输出成功率差异、95% 置信区间、Fisher/卡方检验、Welch t 检验、Token/耗时和标签分组。
- 提供 `harness ab-test --config ab_config.json` 入口及 JSON/CSV/Markdown 报告。

## Non-goals

- 不支持超过两个变体、多臂老虎机、贝叶斯检验或序贯分析。
- 不复制评测策略和沙箱逻辑。
