# Design: 证据驱动的失败模式分类与报告

## 分类输入与输出

分类器接受一条 `ExecutionResult` 字典和可选题目信息，输出 `mode`、`confidence` 与 `evidence`。证据只包含规则标识，不包含原始代码、测试输入或错误全文。`failure_mode` 是更细的分析字段；粗粒度 `failure_category` 继续供已有计数、CLI 和实验报告使用。

支持 `syntax_error`、`logic_error`、`timeout`、`boundary_condition`、`understanding_error`，并为运行时异常、基础设施问题和无法判定的结果提供 `runtime_error`、`infrastructure_error`、`unknown`。明确的沙箱终态优先于推测性文本线索。边界和题意判断必须依赖有区分力的失败用例或错误线索；证据不足时落到 `logic_error` 或 `unknown`，避免把所有 wrong answer 都当作题意错误。

成功、`budget_exhausted`、`unsupported` 和 `cancelled` 不是已完成的失败记录，分类器返回空结果。任务服务未产出结果时写 `evaluation_completed: false` 占位，分类器和报告都排除此记录。记录时保留一次分类结果；分析缺少新字段的历史结果时可即时分类，不回写旧文件。

## 聚合口径

`summarize_failure_modes(results, problem_info)` 返回：

- `total_evaluated`：状态为 `success`、`failed` 或 `error` 的记录数。
- `total_failures`：已评估记录中状态不为 `success` 的记录数。
- `categories`：每种模式的失败次数及其占全部失败记录的比例，计数总和等于 `total_failures`。
- `by_tags`：每个标签的已评估数、失败数、失败率和失败模式计数。多标签题目分别进入各自标签分组，因此标签分组的计数不能相加为运行总数。
- `top_weaknesses`：按观察到的标签失败率排序，仅显示至少 3 条已评估记录且有失败的标签，并展示分子和分母。这是描述性排序，不表示统计显著或模型的稳定能力缺陷。

Markdown 明示分母与小样本限制。PNG 图只展示有失败记录的类型及其次数和占比；无失败时不生成图。标签文本在 Markdown 中转义。

## 持久化与兼容

普通运行的每策略结果 JSON 带细分类字段。运行目录写 `failure_mode_summary.json`（总体与按策略汇总）、`failure_mode_report.md` 和有失败时的 `failure_mode_distribution.png`；`summary.json.failure_modes` 镜像同一统计。实验对比 JSON 追加 `failure_modes`，其组合和整体汇总采用相同口径。已有字段不删除，旧结果的统计兼容按需重新分类。

## 验证

分类规则在固定、人工标注且覆盖五类主要模式的案例集上测量准确率：正确分类数除以可评估标注案例总数，目标严格大于 85%。测试同时覆盖已知混淆情况（例如异常文本与错误输出同现）、没有充分证据时的保守回退、未执行记录不计数、标签分母和 PNG 格式。此指标只说明该样本集上的规则表现，不外推到所有模型与题库。
