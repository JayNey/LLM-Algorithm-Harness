# 交互调试运行摘要验证

结论为通过。变更 `fix-debug-run-summary` 对应 GitHub #373，验证对象为提交 `4b10cab`。

## 完整性

OpenSpec 任务完成 1/1。增量规范包含一条运行结果摘要需求和三个场景，通过严格校验。

## 正确性

- 正常返回时，`Debugger._run` 使用 `ExecutionResult.success` 和 `len(ExecutionResult.iterations)`。CLI 用例用真实 VanillaStrategy 覆盖成功和答错，检查一轮摘要以及后续轨迹查询和手动导出。
- 零轮场景用真实的空迭代结果，验证失败状态和零轮摘要。策略抛出异常时，CLI 显示脱敏后的执行失败信息，并继续接收 `status`。
- 在临时快照中恢复旧的 `attempts` 读取后，成功、答错和零轮用例均复现失败。修复后的提交快照通过 26 项调试测试，Black、Ruff、Git diff 检查和离线 wheel 构建均通过。
- 在允许绑定本机回环端口的临时快照中运行 `python3 -m pytest -m "not online"`，得到 3,981 项通过、18 项跳过和 93.08% 覆盖率。5 项失败或错误均在纠正环境后的定向重跑中通过，该次重跑共通过 39 项。

### 全量运行中的环境差异

- `test_runner_executes_all_combinations_with_metadata` 需要读取 Git 提交号。在带有 Git 元数据的工作区重跑通过。
- `test_self_consistency_controls_candidate_count_at_sdk_boundary[anthropic]`、`test_few_shot_controls_retrieval_without_leaking[anthropic]`、`test_reflexion_controls_context_on_generation_and_reflection[anthropic]` 和 `test_cache_uses_provider_params_but_not_strategy_controls[anthropic]` 在预装 Anthropic 1.5.0 时被 SDK 拒绝传入的 HTTP 客户端。以仓库约束范围内的 Anthropic 0.125.0 重跑通过。

## 一致性

现有运行时代码覆盖规范场景。新增用例沿用 CLI 测试入口，模型和沙箱使用受控响应。设计、任务和增量规范一致。Tweak 的 `review_mode: off` 跳过独立自动代码审查。
