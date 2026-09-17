## Context

当前实现存在五处缺陷：多轮策略 `final_result` 仅在 `all_passed` 时赋值；`build_feedback_prompt` 丢失题面与约束；`llm_client.generate()` 抛错会穿透 `execute()` 导致整题结果被 Harness 丢弃（仅记日志）；`create_execution_result` 写死 `execution_time_seconds=0.0` 且从不填充 `llm_traces`；`response.usage` 直接解包，缺失 usage 的兼容服务会触发 `AttributeError`。另外 `_generate_report` 以题目总数为分母而 `compare_strategies` 以结果数为分母，口径不一致。

## Goals / Non-Goals

**Goals:**

- 每个题目×策略组合都有终态 `ExecutionResult`，失败结果与失败用例可查、失败原因可分类统计。
- 每轮轨迹完整（脱敏请求、原始响应、提取代码、测试摘要、token、耗时），usage 缺失显式标记。
- 报告总数、成功数与各类失败数可对账，汇总与对比口径一致。

**Non-Goals:**

- 跨进程恢复与任务级存储（#14）。
- 公开/隐藏测试分离与题目 Schema 升级（#6），仅在反馈组装处保留"可反馈视图"边界。
- 不改变 `status` 既有取值语义和现有下游过滤逻辑。

## Decisions

1. **`final_result` 语义改为"最后一次非 None 沙箱结果"。** 成功标记单独维护，失败时仍能查看测试明细。
2. **新增 `failure_category` 字段而非复用 `status`。** 取值 `wrong_answer` / `code_extraction_failed` / `model_error` / `system_error`，避免改动现有 `success/failed/error` 取值破坏下游。
3. **扩展 `IterationResult` 承载每轮轨迹**（prompt、response_text、llm_error、sandbox_error、usage_missing、elapsed_seconds），`llm_traces` 由 iterations 派生填充，写入前统一过 `redact_sensitive_text`。
4. **LLM 客户端容错 usage。** 供应商响应缺少 usage 时返回零值 usage 并置 `usage_missing=True`，不再抛错。
5. **异常就地捕获、终态兜底。** 策略内捕获 API 异常并记录带 `llm_error` 的迭代后终止循环仍返回结果；Harness 的 except 分支合成 `system_error` 终态记录追加进结果列表。
6. **汇总口径统一。** `total = solved + wrong_answer_failed + model_failed + system_failed`；`StrategyReport` 增加 `model_failed_problems`、`system_failed_problems` 计数，`compare_strategies` 与报告使用同一分母。
7. **反馈提示复用题意与约束段落。** `build_feedback_prompt` 补回 `description` 与 `constraints`，反馈数据仍仅来自本轮沙箱可见结果。

## Risks / Trade-offs

- [保存原始响应会增大结果文件体积] → 接受：诊断价值优先，导出边界已有统一脱敏。
- [新增 `failure_category` 可能与 `status` 表面不一致] → 报告计数只依赖 `failure_category`，`status` 仅维持兼容语义。
- [usage 缺失时 token 统计偏小] → 显式标记 `usage_missing`，不将其视为可对账数据。
