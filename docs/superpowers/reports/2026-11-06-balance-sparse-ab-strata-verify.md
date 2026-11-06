# A/B 稀疏分层验证

变更 `balance-sparse-ab-strata`，对应 GitHub Issue #364，实现提交为 `08d79fa` 和 `79a7f7e`。

## 结论

通过。OpenSpec 任务 2/2 完成，四个增量规格场景均有验证证据。

- `tests/test_ab_testing.py` 覆盖 20 个单题层、混合奇偶层、偶数层和极小样本。同样的输入和 `seed=42` 可复现。问题复现从 `a=20、b=0` 变为 `a=10、b=10`。
- runner 入口拒绝筛选后只剩一题、零题或 ID 重复的题集。回归测试核对错误原因，并验证模型和沙箱工厂未被调用、输出目录未创建。
- `tests/test_api_experiment_benchmark.py` 覆盖 A/B 任务标识和跨用户隔离。`tests/test_business_checkpoints.py`、`tests/test_budget_coverage.py` 和 `tests/test_api_cost.py` 覆盖检查点恢复、预算暂停与恢复以及重复投递后的费用去重。

## 执行证据

- `python3 -m pytest --no-cov -q tests/test_ab_testing.py tests/test_business_checkpoints.py tests/test_spend_execution.py tests/test_budget_coverage.py tests/test_api_experiment_benchmark.py tests/test_api_cost.py` 通过 133 项。HTTP 用例使用本机回环端口。六条告警来自依赖弃用或统计测试中的常量数据。
- `python3 -m pip wheel --no-build-isolation --no-deps --wheel-dir <临时目录> .` 成功构建 wheel。
- `comet classic openspec -- validate balance-sparse-ab-strata --strict`、三个变动 Python 文件的 Ruff 格式与 lint 检查及 Git 空白检查均通过。

## 实现与规范一致性

偶数层沿用原分配顺序。奇数层轮流分配多出的一题，各层和全局的组间题数差都至多为一。runner 校验发生在输出目录和检查点初始化之前。跨版本恢复时，检查点继续按题目与变体匹配，重新分到另一变体的题目会在该变体下执行。实现与 tweak 的精简 `design.md` 一致。`review_mode: off`，验证中直接核对了提交差异、规范与场景证据。
