## Why

多轮策略只在成功时赋值 `final_result`，所有轮次失败时最终测试结果与失败用例全部丢失；修复提示只保留标题、旧代码与反馈，未保留题面和约束；Harness 捕获执行异常后不追加任何结果，题目从报告中消失；`execution_time_seconds` 恒为 0，`llm_traces` 从未填充（对应上游 issue #13）。

## What Changes

- 无论成功失败都保留最后一次有效沙箱结果，区分 `wrong_answer`、`code_extraction_failed`、`model_error`、`system_error` 等失败原因。
- 修复提示补回题意、输入输出契约与约束；反馈仍只使用沙箱可见失败信息（为 #6 公开/隐藏测试分离预留反馈视图边界）。
- 策略内捕获模型调用与沙箱异常并记录原因，保留已完成轮次；Harness 为未捕获异常合成 `system_error` 终态记录，保证每个题目×策略组合都有终态。
- 每轮保存脱敏请求、原始文本响应、提取代码、每轮测试摘要与 token/耗时数据；供应商 usage 缺失时显式标记而不是报错。
- `execution_time_seconds` 改为实际测量。
- 统一策略汇总与 `compare_strategies` 的分母口径，单独统计系统失败与模型失败；导出器输出新计数。

## Capabilities

### New Capabilities

- `result-recording`: 定义执行结果的终态保存、失败分类、反馈上下文完整性、每轮轨迹记录与汇总对账行为。

## Impact

- 影响 `src/models.py`、`src/llm_client.py`、`src/strategy_base.py`、`src/strategies/*`、`src/harness.py` 与 `src/reporting/*` 导出器。
- 不改变沙箱执行协议、供应商请求协议与现有 `status` 字段的既有取值；跨进程恢复与任务级存储由 #14 负责。
