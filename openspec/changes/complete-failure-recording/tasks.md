## 1. 模型与客户端

- [ ] 1.1 先增加 usage 缺失容错测试，再更新模型客户端返回零值 usage 并标记 `usage_missing`
- [ ] 1.2 先增加模型字段测试，再扩展 `IterationResult` 轨迹字段、`ExecutionResult.failure_category` 与 `StrategyReport` 失败计数

## 2. 策略与结果组装

- [ ] 2.1 先增加连续多轮失败保留 `final_result` 与失败用例的测试，再修改多轮策略终态逻辑与失败分类
- [ ] 2.2 先增加中途模型调用失败保留已完成轮次的测试，再在策略内捕获模型异常并终止循环
- [ ] 2.3 先增加后续轮次提示包含题意与约束的测试，再补全 `build_feedback_prompt`
- [ ] 2.4 先增加单轮策略沙箱异常原因记录测试，再为 vanilla 与 chain_of_thought 补充 `sandbox_error`
- [ ] 2.5 先增加 `llm_traces` 填充与轨迹脱敏测试，再扩展 `create_execution_result` 并接入实测耗时

## 3. 汇总与导出

- [ ] 3.1 先增加 Harness 异常合成 `system_error` 终态记录的测试，再修改 `_run_strategy` 异常分支
- [ ] 3.2 先增加报告计数对账与对比口径测试，再统一 `_generate_report` 与 `compare_strategies`
- [ ] 3.3 更新 CSV、Markdown、HTML 导出失败分类与计数并补充导出测试

## 4. 文档与验证

- [ ] 4.1 运行全量测试、静态检查与 OpenSpec 严格校验
