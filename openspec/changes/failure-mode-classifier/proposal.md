# Proposal: 失败模式自动分类器

## Why

现有 `failure_category` 记录的是 wrong_answer、model_error 等执行层原因；`error_analysis` 在实验报告中做只读的错误消息归类。用户还需要能解释算法求解失败的细分模式，例如边界条件遗漏和题意理解错误，并在每次运行结果中持久化，便于按题目标签分析弱项。

## What Changes

- 在 `ExecutionResult` 中增加独立的 `failure_mode`、规则置信度和非敏感证据代码，不改变 `status` 与 `failure_category` 的现有含义。
- 对已完成的失败结果使用确定性规则分类；规则只读取沙箱状态、失败测试、错误轨迹和题目信息。成功、预算耗尽、不支持与取消的结果不分类。
- 每次运行汇总失败模式的数量与占比、题目标签分组的失败率和样本数，并生成 Markdown 报告与 PNG 分布图。
- 实验对比结果可读取同一细分类口径，仍保留既有七类 `error_analysis`。
- 使用固定的人工标注样本集验证分类准确率超过 85%，并覆盖五类主要失败模式与易混淆案例。

## Non-goals

- 不发起额外的模型请求。Issue 中提到的 LLM 辅助分析是可选方案，本变更采用可复现的规则分类。
- 不声称规则置信度是校准后的概率，也不以少量标签样本推断稳定弱点。
- 不替换已有的 `failure_category` 或 `error_analysis` 字段。

## Impact

涉及结果模型、Harness 的结果注释、保存结果与实验报告路径，新增 `src/failure_classifier.py`、`src/failure_report.py` 及相应测试和使用文档。旧结果文件没有细分类字段时，报告可在读取时重新分类；原文件保持不变。
