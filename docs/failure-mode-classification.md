# 失败模式自动分类与报告

Issue #89 为每条已完成的失败结果补充可复查的细分类，帮助定位语法、算法逻辑、超时、边界条件和题意理解方面的问题。运行时不需要额外的模型请求；分类基于已保存的执行证据，结果可重复。

## 分类字段

每条详细结果中的 `failure_mode` 采用以下值：

| 值 | 含义 |
|---|---|
| `syntax_error` | 代码语法或缩进错误 |
| `logic_error` | 可观察到的算法逻辑或输出错误，尚无更具体的可靠线索 |
| `timeout` | 执行时间超过限制 |
| `boundary_condition` | 有明确边界标记，或错误集中在空输入、单元素输入等可观察的边界情形 |
| `understanding_error` | 错误与题意、输入输出约定或要求的目标不符 |
| `runtime_error` | 代码运行时抛出异常 |
| `infrastructure_error` | 沙箱或模型调用等环境问题 |
| `unknown` | 证据不足，无法可靠归入以上类别 |

`failure_mode_confidence` 是规则证据强弱，范围 0–1，**不是**校准后的正确概率。`failure_mode_evidence` 只包含命中的规则标识，不保存原始代码、私密输入或完整错误消息。已有的 `status` 和粗粒度 `failure_category` 含义不变；固定预算实验的旧版七类 `error_analysis` 也继续保留。不同视图的分类目标不同，不应直接相加比较。

规则会优先使用最终执行信号。最终模型调用失败时，不会让前一轮保留的沙箱错误覆盖它；输出不符消息中的期望值和实际值也不会被误当成异常线索。边界条件与题意理解需要有区分力的失败线索；仅有一次输出不符时，结果通常保持为 `logic_error` 或 `unknown`。`success`、`budget_exhausted`、`unsupported`、`cancelled`（或 `canceled`）不分类。没有执行结果的任务占位记录用 `evaluation_completed: false` 标记，也不分类。缺少新字段的历史结果在生成报告时可以即时分类，原结果文件不会被改写。

## 查看报告

普通运行在 `output_dir/<run_id>/` 生成以下文件：

- `failure_mode_summary.json`：`overall` 和 `by_strategy` 两层结构化汇总；`summary.json.failure_modes` 保存同一统计。
- `failure_mode_report.md`：总体和各策略的失败类型、标签统计及弱项描述。
- `failure_mode_distribution.png`：总体失败类型分布；没有失败时不生成。
- `<strategy>_results.json`：每条已完成失败结果的 `failure_mode`、`failure_mode_confidence` 和 `failure_mode_evidence`。

固定预算实验的 `comparison.json.failure_modes` 提供总体与组合层的同口径统计。报告数值均来自已完成的结果，报告生成不会追加模型调用。

## 统计口径

- `total_evaluated` 只计有实际结果的 `success`、`failed`、`error`。`evaluation_completed: false` 的任务占位记录、预算耗尽、不支持、取消及无效状态都不进入分母。
- `total_failures` 只计已评估记录中的 `failed` 和 `error`。各类型的 `share` 以此数为分母；各类型计数之和应等于失败总数。
- 标签失败率是该标签的失败记录数除以该标签的已评估记录数。一个题目有多个标签时，会分别进入各标签组；标签组计数不能相加当作全局总数。
- “高频弱项”按观察到的标签失败率排序，只展示至少 3 条已评估记录且有失败的标签，并同时展示失败数和样本数。这是描述性线索，不表示统计显著性或模型的稳定短板。

当看到很高的标签失败率时，先检查样本数和主要失败模式，再查看对应的详细结果。`infrastructure_error` 表示运行环境问题，不能据此判断模型的算法能力；`unknown` 表示需要查看更多执行证据。

## 准确率验证

分类器使用固定的人工标注案例集做离线验收。当前案例集有 27 条可分类失败、4 条应排除的终态记录，涵盖全部八种模式；准确率以“正确分类的可分类失败数 / 27”计算，门槛为严格大于 85%。当前规则在这 27 条中判对 27 条。测试也要求四条非失败记录返回空分类。这个数字衡量的是该案例集上的规则表现，不能直接外推到任意模型、数据集或真实线上运行。
