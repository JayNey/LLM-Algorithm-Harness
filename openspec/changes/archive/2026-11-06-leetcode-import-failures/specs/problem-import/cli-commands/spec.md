## ADDED Requirements

### Requirement: LeetCode 导入失败贯穿整轮生命周期

LeetCode importer SHALL 独立保存抓取失败，并保留 transform_failures 汇总读取兼容性；转换不得清除本轮抓取失败。每轮 fetch 开始 SHALL 重置旧失败，转换重复运行 SHALL 替换旧转换错误且保留本轮抓取错误。

#### Scenario: 部分抓取失败
- **WHEN** 批量两题，一题成功、另一题 404 或瞬态重试耗尽，执行 fetch → transform → report
- **THEN** 报告含失败题号和原因，普通模式退出 1、strict 退出 3；预览不写入，force 模式仅保存成功题目

#### Scenario: 全部失败或全部成功
- **WHEN** 两题详情全部抓取失败或全部成功
- **THEN** 报告 failed 分别为 2 或 0；保持原有全部失败退出 2（含 strict）、全部成功退出 0 的契约

#### Scenario: 实例复用
- **WHEN** 同一 importer 从有抓取/转换错误的一轮进入下一轮单题、批量、空结果或抓取异常
- **THEN** 不携带上一轮失败，也不把本轮抓取失败在转换时清掉或重复累计
